from collections import Counter
from datetime import UTC, datetime
from time import monotonic

from powernext.assembly.cp_sat import AssemblyEngine
from powernext.contracts.models import DomainError
from powernext.correction.model import ResidualModel
from powernext.optimisation.objective import Archive, evaluate_objective, objective_order
from powernext.optimisation.smac_adapter import SmacAdapter
from powernext.performance.metrics import build_report, model_quality
from powernext.physics.forward import evaluate
from powernext.physics.plot_reconstruction import bundle


def run(context, run_id, store, artifact_dir, model=None, proposer=None, evaluator=None):
    req = context.request
    start = monotonic()
    epoch_started_at = datetime.now(UTC).isoformat()
    archive = Archive(req.objective.secondary_preference)
    prediction_archive = Archive(req.objective.secondary_preference, require_eligible=False)
    engine = AssemblyEngine()
    model = model or ResidualModel(artifact_dir / "models")
    previous_run = store.get("run", run_id) or {}
    resume_count = previous_run.get("resume_count", 0)
    proposer = proposer or SmacAdapter(context, artifact_dir / run_id / f"smac-{resume_count}")
    counters = {
        "proposals": 0,
        "physics_evaluations": 0,
        "ml_evaluations": 0,
        "physics_predictions": 0,
        "ml_predictions": 0,
        "cache_hits": 0,
        "unique_realised": 0,
    }
    counters.update(previous_run.get("counters", {}))
    cache = {}
    rejections = Counter(previous_run.get("rejections", {}))
    stagnant = previous_run.get("stagnant", 0)
    diagnostic_best_key = previous_run.get("diagnostic_best_key")
    repeated = previous_run.get("repeated", 0)
    elapsed_prior = previous_run.get("elapsed_seconds", 0.0)
    stage_totals = dict(previous_run.get("performance", {}).get("stage_seconds", {}))

    def timed_stage(name, started):
        duration = monotonic() - started
        stage_totals[name] = stage_totals.get(name, 0.0) + duration
        return duration

    for record in store.event_page(run_id, 0, 1000000):
        if record["pipeline_stage_name"] == "evaluation":
            cached = store.get("candidate", record["candidate_id"])
            if cached is not None:
                cache[record["candidate_id"]] = cached
                archive.add(cached)
                prediction_archive.add(cached)
        if record["pipeline_stage_name"] in ("evaluation", "rejection") and hasattr(
            proposer, "replay"
        ):
            proposer.replay(record["proposal"], record.get("cost", 2))
    stop = "maximum_proposals"

    def event(stage, **data):
        store.event(
            run_id,
            dict(
                pipeline_stage_name=stage,
                context_hash=context.context_hash,
                emitted_at_utc=datetime.now(UTC).isoformat(),
                elapsed_run_seconds=elapsed_prior + monotonic() - start,
                **data,
            ),
        )

    def persist():
        store.patch(
            "run",
            run_id,
            {
                "status": "running",
                "counters": counters.copy(),
                "top_three_ids": [e["candidate_id"] for e in archive.best()],
                "top_three_prediction_ids": [e["candidate_id"] for e in prediction_archive.best()],
                "loop_policy": "ml_correction_required_v1",
                "rejections": dict(rejections),
                "stagnant": stagnant,
                "diagnostic_best_key": diagnostic_best_key,
                "repeated": repeated,
                "elapsed_seconds": elapsed_prior + monotonic() - start,
                "model_report": model.report(),
                "worker_started_at_utc": epoch_started_at,
                "started_epoch_elapsed_seconds": elapsed_prior,
                "performance": {"stage_seconds": stage_totals.copy()},
            },
        )

    persist()
    event("context", input=context.request.model_dump(mode="json"), output=context.public())
    for index in range(counters["proposals"], req.search.max_proposals):
        state = store.get("run", run_id) or {}
        if state.get("cancel_requested"):
            stop = "cancelled"
            break
        if elapsed_prior + monotonic() - start >= req.search.wall_time_seconds:
            stop = "wall_time_budget"
            break
        if (
            counters["physics_evaluations"] >= req.search.max_forward_evaluations
            or counters["ml_evaluations"] >= req.search.max_ml_evaluations
        ):
            stop = "evaluation_budget"
            break
        try:
            proposal_started = monotonic()
            trial, proposal = proposer.ask(index)
            timed_stage("proposal", proposal_started)
        except StopIteration:
            stop = "search_space_exhausted"
            break
        counters["proposals"] += 1
        event("proposal", proposal=proposal.model_dump())
        persist()
        improved = False
        try:
            if evaluator is not None:
                evaluation = evaluator(proposal)
                identity = evaluation["candidate_id"]
            else:
                candidate_started = monotonic()
                candidate_timings = {}
                forbidden = []
                candidate = None
                baseline = None
                correction = None
                for retry in range(req.search.cp_pair_retries):
                    assembly_started = monotonic()
                    candidate, solver_report = engine.realise(context, proposal, forbidden)
                    assembly_duration = timed_stage("assembly", assembly_started)
                    candidate_timings["assembly"] = (
                        candidate_timings.get("assembly", 0.0) + assembly_duration
                    )
                    event(
                        "assembly",
                        candidate=candidate.model_dump(mode="json"),
                        solver_report=solver_report,
                        retry=retry,
                        duration_seconds=assembly_duration,
                    )
                    identity = candidate.candidate_id
                    if identity in cache:
                        break
                    if (
                        counters["physics_evaluations"] >= req.search.max_forward_evaluations
                        or counters["ml_evaluations"] >= req.search.max_ml_evaluations
                    ):
                        raise DomainError(
                            "evaluation_budget", "Forward evaluation limit", "physics"
                        )
                    physics_start = monotonic()
                    counters["physics_evaluations"] += 1
                    persist()
                    baseline = evaluate(
                        context,
                        candidate,
                        include_trace=True,
                        deadline=start + req.search.wall_time_seconds - elapsed_prior,
                    )
                    counters["physics_predictions"] += 1
                    physics_duration = timed_stage("physics", physics_start)
                    candidate_timings["physics"] = (
                        candidate_timings.get("physics", 0.0) + physics_duration
                    )
                    event(
                        "physics",
                        candidate_id=identity,
                        constraints=baseline["constraints"],
                        output=baseline,
                        duration_seconds=physics_duration,
                    )
                    correction_started = monotonic()
                    counters["ml_evaluations"] += 1
                    persist()
                    try:
                        correction = model.correct(context, candidate, baseline)
                    except DomainError as exc:
                        correction = {
                            "status": "failed",
                            "corrected_metrics": None,
                            "model_version": req.model_version,
                            "support": {"status": "unsupported", "reasons": [exc.code]},
                            "error": {"code": exc.code, "message": str(exc)},
                        }
                    if correction.get("corrected_metrics"):
                        counters["ml_predictions"] += 1
                    correction_duration = timed_stage("correction", correction_started)
                    candidate_timings["correction"] = (
                        candidate_timings.get("correction", 0.0) + correction_duration
                    )
                    event(
                        "correction",
                        candidate_id=identity,
                        output=correction,
                        retry=retry,
                        duration_seconds=correction_duration,
                    )
                    failed_checks = {
                        c["constraint_id"] for c in baseline["constraints"] if c["status"] == "fail"
                    }
                    # Stored energy depends on frozen N/charge/capacitance, not the resistor pair.
                    # Retain the failed evaluation so its settings/checks remain inspectable.
                    if (
                        req.purpose == "diagnostic"
                        or not failed_checks
                        or failed_checks.intersection({"HW_STAGE_ENERGY", "HW_TOTAL_ENERGY"})
                    ):
                        break
                    forbidden.append((candidate.front.assembly_id, candidate.tail.assembly_id))
                if identity in cache:
                    counters["cache_hits"] += 1
                    repeated += 1
                    evaluation = cache[identity]
                else:
                    counters["unique_realised"] += 1
                    repeated = 0
                    assert candidate is not None and baseline is not None
                    assert correction is not None
                    objective_started = monotonic()
                    objective = (
                        evaluate_objective(context, correction["corrected_metrics"])
                        if correction.get("corrected_metrics")
                        else None
                    )
                    candidate_timings["objective"] = timed_stage("objective", objective_started)
                    eligible = bool(
                        baseline["hardware_feasible"]
                        and objective
                        and correction.get("lab_validated", False)
                        and correction["support"]["status"] == "supported"
                        and all(
                            c["status"] == "pass"
                            for c in correction.get("corrected_constraint_checks", [])
                        )
                    )
                    evaluation = {
                        "candidate_id": identity,
                        "candidate": candidate.model_dump(mode="json"),
                        "physics": baseline,
                        "correction": correction,
                        "objective": objective,
                        "eligible": eligible,
                        "cost": objective["cost"]
                        if eligible and objective is not None
                        else 1 + objective["cost"]
                        if req.purpose == "diagnostic" and objective is not None
                        else 2,
                        "objective_origin": "residual_corrected"
                        if correction.get("corrected_metrics")
                        else None,
                        "cost_basis": "eligible_waveform"
                        if eligible
                        else "diagnostic_waveform_with_ineligibility_penalty"
                        if req.purpose == "diagnostic" and objective is not None
                        else "ml_prediction_unavailable"
                        if objective is None
                        else "hard_rejection",
                        "performance": build_report(
                            context,
                            candidate,
                            baseline,
                            correction,
                            model.report(),
                            {
                                "scope": "original_unique_candidate_evaluation_including_pair_retries",
                                "stage_seconds": candidate_timings,
                                "total_seconds": monotonic() - candidate_started,
                            },
                        ),
                    }
                    if objective is None:
                        rejections["ml_prediction_unavailable"] += 1
                    cache[identity] = evaluation
            store.save("candidate", identity, evaluation)
            event(
                "evaluation",
                candidate_id=identity,
                proposal=proposal.model_dump(),
                cost=evaluation["cost"],
                eligible=evaluation["eligible"],
                cache_hit=evaluator is None and identity in cache and repeated > 0,
            )
            improved = archive.add(evaluation)
            improved = prediction_archive.add(evaluation) or improved
            if req.purpose == "diagnostic" and evaluation.get("objective"):
                key = list(objective_order(evaluation["objective"]))
                if diagnostic_best_key is None or key < diagnostic_best_key:
                    diagnostic_best_key = key
                    improved = True
            proposer.tell(trial, evaluation["cost"])
            if not evaluation["eligible"]:
                rejections["ineligible_evaluated_candidate"] += 1
        except DomainError as exc:
            rejections[exc.code] += 1
            event(
                "rejection",
                reason_code=exc.code,
                component_stage=exc.stage,
                message=str(exc),
                proposal=proposal.model_dump(),
            )
            proposer.tell(trial, 2)
        stagnant = 0 if improved else stagnant + 1
        persist()
        best = archive.best()
        if len(best) == 3 and all(e["objective"]["waveform_within_tolerance"] for e in best):
            stop = "three_satisfactory_setups"
            break
        if (
            req.purpose == "diagnostic"
            and len(prediction_archive.best()) == 3
            and all(e["objective"]["waveform_within_tolerance"] for e in prediction_archive.best())
        ):
            stop = "three_ml_waveforms_within_tolerance"
            break
        if repeated >= req.search.repeat_window:
            stop = "repeated_candidates"
            break
        if stagnant >= req.search.archive_stagnation_window:
            stop = "archive_stagnation"
            break
    best = archive.best()
    predicted = prediction_archive.best()
    waveforms = bundle(context, predicted if req.purpose == "diagnostic" else best)
    store.save("waveforms", run_id, waveforms)
    result = {
        "schema_version": "1.0",
        "run_id": run_id,
        "status": "cancelled"
        if stop == "cancelled"
        else "completed"
        if len(best) == 3
        else "completed_with_shortfall",
        "context_id": context.context_id,
        "stop_reason": stop,
        "requested_recommendations": 3,
        "returned_recommendations": len(best),
        "shortfall_reason": None
        if len(best) == 3
        else "fewer_than_three_supported_hardware_verified_candidates",
        "recommendations": best,
        "predicted_setups": predicted,
        "requested_predictions": 3,
        "returned_predictions": len(predicted),
        "prediction_shortfall_reason": None
        if len(predicted) == 3
        else "fewer_than_three_distinct_ml_predictions",
        "ml_converged": len(predicted) == 3
        and all(e["objective"]["waveform_within_tolerance"] for e in predicted),
        "calibration_basis": "ML corrected metrics only; no physics-only objective fallback",
        "loop_policy": "ml_correction_required_v1",
        "counters": counters,
        "rejections": dict(rejections),
        "history_url": f"/v1/runs/{run_id}/candidates",
        "waveform_plot_bundle_url": f"/v1/runs/{run_id}/waveforms",
        "guarantee": "Best distinct eligible setups among evaluated candidates only",
        "physical_recommendation_verified": bool(best) and evaluator is None,
        "evaluation_mode": "mock_fixture" if evaluator is not None else "production_pipeline",
        "performance": {
            "clock": "monotonic_wall_clock",
            "scope": "cumulative_active_worker_time_excluding_queue_and_interruption",
            "elapsed_seconds": elapsed_prior + monotonic() - start,
            "stage_seconds": stage_totals,
            "proposals_per_second": counters["proposals"]
            / max(elapsed_prior + monotonic() - start, 1e-12),
            "cache_hit_fraction": counters["cache_hits"]
            / max(counters["cache_hits"] + counters["unique_realised"], 1),
            "model_quality": model_quality(model.report(), context.test["category"]),
        },
    }
    store.save("result", run_id, result)
    previous = store.get("run", run_id) or {}
    store.save("run", run_id, {**previous, **result})
    event("complete", stop_reason=stop, returned_recommendations=len(best))
    return result
