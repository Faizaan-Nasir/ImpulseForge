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
    report = evaluate(context, actual(context))
    constraint = next(
        c for c in report["constraints"] if c["constraint_id"] == "REQUEST_MIN_EFFICIENCY"
    )
    assert constraint["status"] == "fail"
