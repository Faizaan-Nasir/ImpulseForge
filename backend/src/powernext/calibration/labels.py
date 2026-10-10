"""Turn linked external measurements into residual labels; never use predictions as labels."""

import numpy as np

from powernext.contracts.models import Candidate, DomainError
from powernext.physics.forward import evaluate
from powernext.physics.waveform import extract


def build_labels(context, candidate: Candidate, measurement):
    if measurement["equipment_profile_id"] != context.request.equipment_profile_id:
        raise DomainError(
            "measurement_profile_mismatch",
            "Measurement belongs to another equipment profile",
            "calibration",
        )
    actual = measurement["actual_settings"]
    expected = {
        "N": candidate.N,
        "U_charge_V": candidate.U_charge_V,
        "front_assembly_id": candidate.front.assembly_id,
        "tail_assembly_id": candidate.tail.assembly_id,
        "context_hash": context.context_hash,
    }
    if actual != expected:
        raise DomainError(
            "measurement_settings_mismatch",
            "Recorded actual settings must exactly identify the realised setup/context",
            "calibration",
        )
    times = np.asarray(measurement["time_s"], dtype=float)
    voltage = np.asarray(measurement["voltage_V"], dtype=float)
    if times[0] != 0 or len(times) < 20 or not np.all(np.diff(times) > 0):
        raise DomainError(
            "measurement_resolution_insufficient",
            "At least 20 increasing samples beginning at declared impulse origin required",
            "calibration",
        )
    waveform = lambda t: np.interp(t, times, voltage)
    observed, landmarks = extract(
        waveform, times[-1], context.test["category"], context.test["front_s"]
    )
    baseline = evaluate(context, candidate, include_trace=False)
    baseline_metrics = baseline["metrics"]
    return {
        "measurement_id": measurement["measurement_id"],
        "candidate_id": candidate.candidate_id,
        "context_hash": context.context_hash,
        "provenance": "external_measured_trace",
        "observed_metrics": observed.model_dump(),
        "physics_metrics": baseline_metrics,
        "residual_targets": {
            "residual_" + key: value - baseline_metrics[key]
            for key, value in observed.model_dump().items()
        },
        "landmarks": landmarks,
        "interpolation": "piecewise_linear",
        "baseline_version": baseline["physics_version"],
        "baseline_mode": baseline["baseline_mode"],
        "standard_compliance_verified": False,
        "training_approved": False,
        "review_required": [
            "measurement calibration",
            "time/voltage uncertainty",
            "setup/session split",
            "hardware evidence",
            "sampling resolution",
        ],
        "automatic_model_retraining": False,
    }
