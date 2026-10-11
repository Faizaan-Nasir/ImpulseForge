"""Chronological proposal history; never deduplicate or substitute physics for ML."""

from powernext.contracts.models import DomainError
from powernext.optimisation.objective import evaluate_objective


def attempt_history(store, run_id, context):
    groups = []
    current = None
    candidates = {}
    baselines = {}
    cached_predictions = {}
    ml_calls = 0

    def row(candidate, correction, baseline, sequence, source, ml_number=None):
        metrics = correction.get("corrected_metrics")
        objective = None
        reasons = list(correction.get("support", {}).get("reasons", []))
        if metrics:
            try:
                objective = evaluate_objective(context, metrics)
            except DomainError as exc:
                reasons.append(exc.code)
        matched = bool(objective and objective["waveform_within_tolerance"])
        return {
            "event_sequence": sequence,
            "candidate_id": candidate.get("candidate_id"),
            "N": candidate.get("N"),
            "U_charge_V": candidate.get("U_charge_V"),
            "Rf_actual_ohm": candidate.get("front", {}).get("equivalent_ohm"),
            "Rt_actual_ohm": candidate.get("tail", {}).get("equivalent_ohm"),
            "front_recipe": candidate.get("front", {}).get("recipe"),
            "tail_recipe": candidate.get("tail", {}).get("recipe"),
            "ml_metrics": metrics,
            "ml_evaluation_number": ml_number,
            "prediction_source": source,
            "correction_status": correction.get("status", "not_invoked"),
            "model_version": correction.get("model_version"),
            "model_support": correction.get("support"),
            "objective": objective,
            "waveform_within_tolerance": matched,
            "hardware_feasible": baseline.get("hardware_feasible"),
            "failed_hardware_constraints": [
                c["constraint_id"] for c in baseline.get("constraints", []) if c["status"] == "fail"
            ],
            "eligible": None,
            "reason_codes": reasons,
            "status": "thresholds_met"
            if matched
            else "outside_thresholds"
            if objective
            else "ml_unavailable",
        }

    for event in store.event_page(run_id, 0, 1000000):
        stage = event["pipeline_stage_name"]
        if stage == "proposal":
            current = {
                "attempt_number": event["proposal"]["proposal_index"] + 1,
                "proposal": event["proposal"],
                "rows": [],
                "status": "pending",
                "reason_codes": [],
                "sequence": event["sequence"],
                "candidate": {},
            }
            groups.append(current)
        elif current is not None:
            if stage == "assembly":
                candidate = event["candidate"]
                current["candidate"] = candidate
                candidates[candidate["candidate_id"]] = candidate
            elif stage == "physics":
                baselines[event["candidate_id"]] = event["output"]
            elif stage == "correction":
                ml_calls += 1
                identity = event["candidate_id"]
                item = row(
                    candidates.get(identity, {}),
                    event["output"],
                    baselines.get(identity, {}),
                    event["sequence"],
                    "fresh_ml",
                    ml_calls,
                )
                current["rows"].append(item)
                cached_predictions[identity] = item
            elif stage == "evaluation":
                identity = event["candidate_id"]
                evaluation = store.get("candidate", identity) or {}
                if not current["rows"]:
                    if event.get("cache_hit") and identity in cached_predictions:
                        item = {
                            **cached_predictions[identity],
                            "event_sequence": event["sequence"],
                            "prediction_source": "cached_ml",
                            "source_ml_evaluation_number": cached_predictions[identity][
                                "ml_evaluation_number"
                            ],
                            "ml_evaluation_number": None,
                        }
                    else:
                        item = row(
                            evaluation.get("candidate", {}),
                            evaluation.get("correction", {}),
                            evaluation.get("physics", {}),
                            event["sequence"],
                            "cached_ml" if event.get("cache_hit") else "recorded_ml",
                        )
                    current["rows"].append(item)
                current["rows"][-1]["eligible"] = event.get("eligible")
                current["status"] = "evaluated"
            elif stage == "rejection":
                current["status"] = "rejected"
                current["reason_codes"].append(event["reason_code"])

    history = []
    for group in groups:
        items = group["rows"] or [row(group["candidate"], {}, {}, group["sequence"], "not_invoked")]
        for index, item in enumerate(items, 1):
            history.append(
                {
                    **item,
                    "attempt_number": group["attempt_number"],
                    "evaluation_in_attempt": index,
                    "proposal": group["proposal"],
                    "attempt_status": group["status"],
                    "reason_codes": list(
                        dict.fromkeys(item["reason_codes"] + group["reason_codes"])
                    ),
                }
            )
    return history
