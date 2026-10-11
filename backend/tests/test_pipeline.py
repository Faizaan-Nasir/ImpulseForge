import pytest
from test_optimisation import MockProposer, evaluation

from powernext.contracts.models import RunRequest
from powernext.pipeline.runner import run
from powernext.pipeline.storage import Store
from powernext.profiles.resolve import resolve


def test_one_match_does_not_stop_and_failures_do_not_fill_success_slots(request_data, tmp_path):
    request_data["search"]["max_proposals"] = 6
    context = resolve(RunRequest.model_validate(request_data))
    store = Store(tmp_path / "jobs.sqlite")
    ident, _ = store.create_run(context)
    errors = [0, 1, 1, 1, 0.01, 0.02]
    result = run(
        context,
        ident,
        store,
        tmp_path,
        proposer=MockProposer(),
        evaluator=lambda p: evaluation(context, str(p.proposal_index), errors[p.proposal_index]),
    )
    assert result["counters"]["proposals"] == 6
    assert result["ml_converged"] and result["returned_successful_predictions"] == 3
    assert {e["candidate_id"] for e in result["predicted_setups"]} == {"0", "4", "5"}
    assert all(e["objective"]["waveform_within_tolerance"] for e in result["predicted_setups"])


def test_one_match_plus_failures_returns_one_success_with_shortfall(context, tmp_path):
    store = Store(tmp_path / "jobs.sqlite")
    ident, _ = store.create_run(context)
    result = run(
        context,
        ident,
        store,
        tmp_path,
        proposer=MockProposer(),
        evaluator=lambda p: evaluation(
            context, str(p.proposal_index), 0 if p.proposal_index == 0 else 1
        ),
    )
    assert result["stop_reason"] == "maximum_proposals"
    assert not result["ml_converged"]
    assert result["returned_successful_predictions"] == result["returned_predictions"] == 1
    assert len(result["evaluated_setups"]) == 3
    assert (
        result["prediction_shortfall_reason"]
        == "fewer_than_three_distinct_ml_matches_without_known_constraint_failures"
    )


def test_resume_preserves_budgets_and_archive(context, tmp_path):
    store = Store(tmp_path / "jobs.sqlite")
    ident, _ = store.create_run(context)
    first = evaluation(context, "earlier-best", 0)
    store.save("candidate", first["candidate_id"], first)
    store.event(
        ident,
        {
            "pipeline_stage_name": "evaluation",
            "candidate_id": first["candidate_id"],
            "proposal": {"N": 9, "Rf_required_ohm": 50, "Rt_required_ohm": 25},
            "cost": 0,
        },
    )
    previous = store.get("run", ident)
    store.save(
        "run",
        ident,
        {
            **previous,
            "status": "interrupted",
            "resume_count": 1,
            "counters": {"proposals": 1, "physics_evaluations": 1},
        },
    )
    result = run(
        context,
        ident,
        store,
        tmp_path,
        proposer=MockProposer(),
        evaluator=lambda p: evaluation(context, str(p.proposal_index), 0.01),
    )
    assert result["counters"]["proposals"] == 3
    assert result["recommendations"][0]["candidate_id"] == "earlier-best"


def test_cancellation_before_first_proposal(context, tmp_path):
    store = Store(tmp_path / "jobs.sqlite")
    ident, _ = store.create_run(context)
    store.save("run", ident, {**store.get("run", ident), "cancel_requested": True})
    result = run(context, ident, store, tmp_path, proposer=MockProposer())
    assert result["status"] == "cancelled"
    assert result["counters"]["proposals"] == 0


@pytest.mark.parametrize("charge", [30000, 190000])
def test_hardware_verdict_does_not_skip_ml(request_data, tmp_path, charge):
    request_data["purpose"] = "recommendation"
    request_data["charging_policy"]["U_charge_V"] = charge
    context = resolve(RunRequest.model_validate(request_data))

    class CorrectionModel:
        def report(self):
            return {"status": "mock"}

        def correct(self, *args):
            return {
                "status": "predicted_diagnostic",
                "model_version": args[0].request.model_version,
                "corrected_metrics": args[2]["metrics"],
                "support": {"status": "supported_diagnostic"},
                "lab_validated": False,
            }

    store = Store(tmp_path / "jobs.sqlite")
    ident, _ = store.create_run(context)
    result = run(context, ident, store, tmp_path, proposer=MockProposer(), model=CorrectionModel())
    assert result["returned_recommendations"] == 0
    assert result["counters"]["ml_evaluations"] == 1
    assert result["counters"]["physics_evaluations"] == 1
    assert result["counters"]["cache_hits"] == (0 if charge == 190000 else 3)
    candidates = store.list("candidate")
    assert len(candidates) == 1
    performance = candidates[0][1]["performance"]
    assert performance["correction_status"] == "predicted_diagnostic"
    assert performance["corrected"] is not None
    assert performance["runtime"]["stage_seconds"]["physics"] > 0
    assert result["performance"]["cache_hit_fraction"] == (0 if charge == 190000 else 0.75)
    assert result["performance"]["elapsed_seconds"] > 0
    evaluation_events = [
        e for e in store.event_page(ident, 0, 100) if e["pipeline_stage_name"] == "evaluation"
    ]
    assert [e["cache_hit"] for e in evaluation_events] == (
        [False] if charge == 190000 else [False, True, True, True]
    )
    checks = {c["constraint_id"]: c for c in candidates[0][1]["physics"]["constraints"]}
    assert checks["HW_STAGE_ENERGY"]["status"] == ("fail" if charge == 190000 else "pass")


def test_diagnostic_ml_runs_without_waiving_energy_or_eligibility(request_data, tmp_path):
    class DiagnosticModel:
        def report(self):
            return {"status": "fixture"}

        def correct(self, ctx, candidate, baseline):
            return {
                "status": "predicted_diagnostic",
                "model_version": ctx.request.model_version,
                "corrected_metrics": baseline["metrics"],
                "support": {"status": "supported_diagnostic"},
                "lab_validated": False,
            }

    context = resolve(RunRequest.model_validate(request_data))
    store = Store(tmp_path / "jobs.sqlite")
    ident, _ = store.create_run(context)
    result = run(context, ident, store, tmp_path, proposer=MockProposer(), model=DiagnosticModel())
    assert result["counters"]["ml_evaluations"] == 1
    assert result["returned_recommendations"] == 0
    candidate = store.list("candidate")[0][1]
    assert candidate["correction"]["status"] == "predicted_diagnostic"
    assert not candidate["eligible"]
    assert 1 <= candidate["cost"] < 2
    assert candidate["objective_origin"] == "residual_corrected"
    assert any(
        c["constraint_id"] == "HW_STAGE_ENERGY" and c["status"] == "fail"
        for c in candidate["physics"]["constraints"]
    )


def test_disjoint_durable_updates_preserve_cancellation(context, tmp_path):
    store = Store(tmp_path / "jobs.sqlite")
    ident, _ = store.create_run(context)
    store.patch("run", ident, {"cancel_requested": True})
    store.patch("run", ident, {"counters": {"proposals": 1}})
    assert store.get("run", ident)["cancel_requested"]


def test_missing_ml_prediction_never_uses_physics_as_calibration_objective(context, tmp_path):
    class UnsupportedModel:
        def report(self):
            return {}

        def correct(self, *args):
            return {
                "status": "unsupported",
                "corrected_metrics": None,
                "support": {"status": "unsupported"},
            }

    store = Store(tmp_path / "jobs.sqlite")
    ident, _ = store.create_run(context)
    result = run(context, ident, store, tmp_path, proposer=MockProposer(), model=UnsupportedModel())
    record = store.list("candidate")[0][1]
    assert record["physics"]["metrics"]
    assert record["objective"] is None and record["objective_origin"] is None
    assert record["cost"] == 2 and record["cost_basis"] == "ml_prediction_unavailable"
    assert result["returned_predictions"] == 0 and not result["ml_converged"]
    assert result["counters"]["physics_predictions"] == result["counters"]["ml_evaluations"] == 1
    assert result["counters"]["ml_predictions"] == 0


def test_loop_continues_after_three_undervoltage_ml_predictions(request_data, tmp_path):
    request_data["equipment_inputs"]["C_stage_F"] = 0.125e-6
    from powernext.contracts.models import Proposal

    request_data["search"]["max_proposals"] = 6
    request_data["inventory"]["front"] = [
        {"type_id": f"f{v}", "nominal_ohm": v, "available_quantity": 4}
        for v in (40, 45, 50, 55, 60, 65)
    ]
    context = resolve(RunRequest.model_validate(request_data))

    class Proposer:
        def ask(self, i):
            return i, Proposal(
                N=9, Rf_required_ohm=40 + 5 * i, Rt_required_ohm=25, proposal_index=i
            )

        def tell(self, trial, cost):
            pass

    class CorrectionFixture:
        def report(self):
            return {}

        def correct(self, ctx, candidate, baseline):
            crest = ctx.request.target.crest_V
            if candidate.front.equivalent_ohm <= 50:
                crest *= 0.999  # Previously counted as within the symmetric 3% band.
            return {
                "status": "predicted_diagnostic",
                "model_version": ctx.request.model_version,
                "corrected_metrics": {"front_s": 1.2e-6, "tail_s": 50e-6, "crest_V": crest},
                "support": {"status": "supported_diagnostic"},
                "lab_validated": False,
            }

    store = Store(tmp_path / "jobs.sqlite")
    ident, _ = store.create_run(context)
    result = run(context, ident, store, tmp_path, proposer=Proposer(), model=CorrectionFixture())
    assert result["counters"]["ml_predictions"] == 6
    assert result["ml_converged"]
    assert result["stop_reason"] == "three_ml_waveforms_within_tolerance"
    assert all(e["objective"]["crest_minimum_satisfied"] for e in result["predicted_setups"])
    assert sum(e[1]["objective"]["calibration_required"] for e in store.list("candidate")) == 3


def test_undervoltage_budget_stop_is_not_convergence(context, tmp_path):
    def below(p):
        e = evaluation(context, str(p.proposal_index), 0)
        e["correction"]["corrected_metrics"]["crest_V"] *= 0.999
        from powernext.optimisation.objective import evaluate_objective

        e["objective"] = evaluate_objective(context, e["correction"]["corrected_metrics"])
        e["cost"] = e["objective"]["cost"]
        return e

    store = Store(tmp_path / "jobs.sqlite")
    ident, _ = store.create_run(context)
    result = run(context, ident, store, tmp_path, proposer=MockProposer(), evaluator=below)
    assert result["counters"]["proposals"] == 4
    assert result["stop_reason"] == "maximum_proposals"
    assert not result["ml_converged"]


def test_loop_uses_corrected_metrics_and_stops_at_three_ml_matches(request_data, tmp_path):
    request_data["equipment_inputs"]["C_stage_F"] = 0.125e-6
    from powernext.contracts.models import Proposal

    request_data["inventory"]["front"] = [
        {"type_id": f"f{v}", "nominal_ohm": v, "available_quantity": 4} for v in (45, 50, 55)
    ]
    context = resolve(RunRequest.model_validate(request_data))

    class Proposer:
        def __init__(self):
            self.costs = []

        def ask(self, i):
            return i, Proposal(
                N=9, Rf_required_ohm=(45, 50, 55)[i], Rt_required_ohm=25, proposal_index=i
            )

        def tell(self, trial, cost):
            self.costs.append(cost)

    class CorrectionFixture:
        def report(self):
            return {"status": "fixture"}

        def correct(self, ctx, candidate, baseline):
            # Distinct from the raw physics: correction puts all three inside target tolerances.
            return {
                "status": "predicted_diagnostic",
                "model_version": ctx.request.model_version,
                "corrected_metrics": {"front_s": 1.2e-6, "tail_s": 50e-6, "crest_V": 1425000},
                "support": {"status": "supported_diagnostic"},
                "lab_validated": False,
            }

    proposer = Proposer()
    store = Store(tmp_path / "jobs.sqlite")
    ident, _ = store.create_run(context)
    result = run(context, ident, store, tmp_path, proposer=proposer, model=CorrectionFixture())
    assert result["stop_reason"] == "three_ml_waveforms_within_tolerance"
    assert result["ml_converged"] and result["returned_predictions"] == 3
    assert result["returned_recommendations"] == 0
    assert proposer.costs == [0, 0, 0]
    assert result["counters"]["physics_predictions"] == result["counters"]["ml_predictions"] == 3
    for e in result["predicted_setups"]:
        assert e["objective_origin"] == "residual_corrected" and e["objective"]["S"] == 0
        assert not e["eligible"]
    stages = [e["pipeline_stage_name"] for e in store.event_page(ident, 0, 100)]
    assert [stage for stage in stages if stage in ("physics", "correction", "evaluation")] == [
        "physics",
        "correction",
        "evaluation",
    ] * 3
