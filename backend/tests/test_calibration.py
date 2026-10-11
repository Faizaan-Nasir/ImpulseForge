import numpy as np
import pytest
from test_physics import actual

from powernext.calibration.labels import build_labels
from powernext.contracts.models import DomainError, RunRequest
from powernext.physics.plot_reconstruction import fit
from powernext.profiles.resolve import resolve


def test_measured_labels_are_observed_minus_physics(context):
    candidate = actual(context)
    _, fn = fit({"front_s": 1.2e-6, "tail_s": 50e-6, "crest_V": 1420000}, "Lightning")
    time = np.unique(
        np.concatenate([np.linspace(0, 15e-6, 5000), np.linspace(15e-6, 250e-6, 3000)])
    )
    measurement = {
        "measurement_id": "external-mock-trace",
        "equipment_profile_id": "workbook_benchmark_v1",
        "actual_settings": {
            "N": candidate.N,
            "U_charge_V": candidate.U_charge_V,
            "front_assembly_id": candidate.front.assembly_id,
            "tail_assembly_id": candidate.tail.assembly_id,
            "context_hash": context.context_hash,
        },
        "time_s": time,
        "voltage_V": fn(time),
    }
    labels = build_labels(context, candidate, measurement)
    assert labels["residual_targets"]["residual_crest_V"] == pytest.approx(-5000, abs=2)
    assert labels["observed_metrics"]["front_s"] == pytest.approx(1.2e-6, rel=1e-4)
    assert not labels["training_approved"]
    assert not labels["automatic_model_retraining"]
    measurement["actual_settings"]["N"] = 10
    with pytest.raises(DomainError, match="Recorded actual settings"):
        build_labels(context, candidate, measurement)


def test_minimum_efficiency_is_considered(request_data):
    from powernext.physics.forward import evaluate

    request_data["minimum_voltage_efficiency"] = 0.9
    context = resolve(RunRequest.model_validate(request_data))
    from powernext.calibration.constraints import assess

    candidate = actual(context)
    report = evaluate(context, candidate)
    assert report["constraints"] == []
    assess(context, candidate, report, {"corrected_metrics": report["metrics"]})
    constraint = next(
        c for c in report["constraints"] if c["constraint_id"] == "REQUEST_MIN_EFFICIENCY"
    )
    assert constraint["status"] == "fail"


def test_energy_windows_and_stage_only_infeasibility(context):
    from powernext.calibration.constraints import assess
    from powernext.physics.forward import evaluate

    candidate = actual(context)
    baseline = evaluate(context, candidate)
    assert baseline["constraints"] == [] and baseline["hardware_feasible"] is None
    result = assess(context, candidate, baseline, {"corrected_metrics": baseline["metrics"]})
    assert all(c["enforced_by"] == ["calibration"] for c in result["constraints"])
    w = result["feasibility_windows"]
    assert w["fixed_charge_energy_feasible_stage_counts"] == []
    assert w["current_stage_capacitance_upper_F"] == pytest.approx(2 * 2500 / context.charge**2)
    assert w["current_stage_charge_upper_V"] == pytest.approx(np.sqrt(2 * 2500 / 3e-6))
    assert w["required_current_total_energy_rating_J"] == pytest.approx(
        9 * baseline["stage_energy_J"]
    )
    assert w["conditional_target_capacitance_upper_at_N_max_F"] == pytest.approx(
        2 * 30000 / (15 * (1425000 / (15 * 0.82)) ** 2)
    )
    assert not w["waveform_or_ml_feasibility_guaranteed"]


def test_n_can_fix_total_energy_when_stage_energy_passes(request_data):
    from powernext.calibration.windows import feasibility_windows

    request_data["equipment_inputs"]["C_stage_F"] = 0.125e-6
    request_data["charging_policy"]["U_charge_V"] = 200000
    ctx = resolve(RunRequest.model_validate(request_data))
    w = feasibility_windows(ctx)
    assert w["fixed_charge_energy_feasible_stage_counts"] == list(range(1, 13))
    assert not w["fixed_charge_energy_infeasible"]


def test_calibration_can_change_n_and_does_not_stop_on_energy_failing_waveforms(
    request_data, tmp_path
):
    from powernext.contracts.models import Proposal
    from powernext.pipeline.runner import run
    from powernext.pipeline.storage import Store

    request_data["equipment_inputs"]["C_stage_F"] = 0.125e-6
    request_data["charging_policy"]["U_charge_V"] = 200000
    request_data["search"]["max_proposals"] = 4
    ctx = resolve(RunRequest.model_validate(request_data))

    class Proposer:
        def __init__(self):
            self.costs = []

        def ask(self, index):
            return index, Proposal(
                N=(15, 12, 11, 10)[index], Rf_required_ohm=50, Rt_required_ohm=25
            )

        def tell(self, trial, cost):
            self.costs.append(cost)

    class Model:
        def report(self):
            return {}

        def correct(self, ctx, candidate, baseline):
            assert baseline["constraints"] == [] and baseline["hardware_feasible"] is None
            return {
                "status": "fixture",
                "model_version": ctx.request.model_version,
                "corrected_metrics": {"front_s": 1.2e-6, "tail_s": 50e-6, "crest_V": 1425000},
                "support": {"status": "supported_diagnostic"},
                "lab_validated": False,
            }

    store = Store(tmp_path / "constraints.sqlite")
    rid, _ = store.create_run(ctx)
    p = Proposer()
    result = run(ctx, rid, store, tmp_path, proposer=p, model=Model())
    assert result["counters"]["physics_predictions"] == result["counters"]["ml_predictions"] == 4
    assert {e["candidate"]["N"] for e in result["predicted_setups"]} == {10, 11, 12}
    assert result["ml_converged"] and p.costs[0] > p.costs[1]
    assert result["returned_recommendations"] == 0  # unknown ratings remain unverified
    events = store.event_page(rid, 0, 100)
    stages = [e["pipeline_stage_name"] for e in events]
    assert stages.index("physics") < stages.index("correction") < stages.index("calibration")
    from powernext.dashboard.attempts import attempt_history

    history = attempt_history(store, rid, ctx)
    assert history[0]["constraint_owner"] == "calibration"
    assert "HW_TOTAL_ENERGY" in history[0]["failed_hardware_constraints"]
    assert history[0]["hardware_feasible"] is False
    assert all(r["known_constraints_satisfied"] for r in history[1:])
