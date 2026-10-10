"""Metrics for one actual candidate, without claiming per-shot accuracy from a target."""

from collections import Counter

from powernext.contracts.models import DomainError, PerformanceReport
from powernext.optimisation.objective import evaluate_objective


def model_quality(report, category):
    manifest = report.get("categories", {}).get(category, {})
    return {
        "status": "available" if manifest.get("validation_metrics") else "unavailable",
        "model_version": report.get("model_version"),
        "bundle_hash": report.get("bundle_hash"),
        "category": category,
        "split": "Validation",
        "dataset_origin": "synthetic_workbook",
        "train_count": manifest.get("train_count"),
        "validation_count": manifest.get("validation_count"),
        "hidden_test_evaluated": manifest.get(
            "hidden_test_evaluated", report.get("hidden_test_evaluated", False)
        ),
        "lab_validated": report.get("lab_validated", False),
        "metrics": manifest.get("validation_metrics", {}),
        "error_definition": "prediction_minus_observation",
        "scope": "Dataset aggregate; not an error bound or accuracy score for this input",
    }


def build_report(
    context,
    candidate,
    baseline,
    correction,
    model_report,
    runtime,
    observed_metrics=None,
    observation_provenance=None,
):
    """No inference or circuit solving: callers supply independently computed section outputs."""
    if (
        candidate.context_hash != context.context_hash
        or baseline["candidate_id"] != candidate.candidate_id
        or baseline["context_hash"] != context.context_hash
    ):
        raise DomainError(
            "performance_identity_mismatch",
            "Matching context, candidate and baseline required",
            "performance",
        )
    request = context.request
    corrected = correction.get("corrected_metrics")
    observed_accuracy = {
        "status": "unavailable",
        "reason": "A matched measured result is required to assess this input's accuracy",
        "errors": None,
        "provenance": None,
    }
    if observed_metrics is not None:
        observed_accuracy = {
            "status": "available" if corrected else "correction_unavailable",
            "provenance": observation_provenance,
            "identity_verified": False,
            "observation_origin": "caller_supplied_observation",
            "observed_metrics": observed_metrics,
            "errors": None,
            "physics_errors": comparison(baseline["metrics"], observed_metrics),
        }
        if corrected:
            observed_accuracy["errors"] = comparison(corrected, observed_metrics)
    V0 = candidate.N * candidate.U_charge_V
    checks = baseline["constraints"]
    corrected_checks = correction.get("corrected_constraint_checks", [])
    result = {
        "candidate_id": candidate.candidate_id,
        "context_hash": context.context_hash,
        "target": {
            "front_s": context.test["front_s"],
            "tail_s": context.test["tail_s"],
            "crest_V": request.target.crest_V,
        },
        "physics": {
            "metrics": baseline["metrics"],
            **evaluate_objective(context, baseline["metrics"]),
        },
        "corrected": {"metrics": corrected, **evaluate_objective(context, corrected)}
        if corrected
        else None,
        "correction_status": correction.get("status", "not_invoked"),
        "efficiency": {
            "definition": "crest_V / (N * U_charge_V); voltage transfer, not energy efficiency",
            "initial_erected_voltage_V": V0,
            "expected": request.expected_voltage_efficiency,
            "requested_minimum": request.minimum_voltage_efficiency,
            "physics_voltage_transfer": baseline["metrics"]["crest_V"] / V0,
            "corrected_voltage_transfer": corrected["crest_V"] / V0 if corrected else None,
            "stage_voltage_utilisation": baseline["voltage_utilisation"],
        },
        "stored_energy": {
            "stage_J": baseline["stage_energy_J"],
            "stage_limit_J": context.hardware["stage_energy_max_J"],
            "stage_utilisation": baseline["stage_energy_J"]
            / context.hardware["stage_energy_max_J"],
            "total_J": baseline["total_energy_J"],
            "total_limit_J": context.hardware["total_energy_max_J"],
            "total_utilisation": baseline["total_energy_J"]
            / context.hardware["total_energy_max_J"],
        },
        "hardware": {
            "feasible": baseline["hardware_feasible"],
            "constraint_counts": counts(checks),
            "failed_constraint_ids": [c["constraint_id"] for c in checks if c["status"] == "fail"],
            "unknown_constraint_ids": [
                c["constraint_id"] for c in checks if c["status"] == "unknown"
            ],
            "corrected_constraint_counts": counts(corrected_checks),
        },
        "model_quality": model_quality(model_report, context.test["category"]),
        "observed_accuracy": observed_accuracy,
        "runtime": runtime,
        "interpretation": "Computed values are predictions. Target mismatch is not model accuracy; "
        "dataset validation does not establish this setup's measured result.",
    }
    return PerformanceReport.model_validate(result).model_dump(mode="json")


def counts(checks):
    values = Counter(c["status"] for c in checks)
    return {key: values[key] for key in ("pass", "fail", "unknown", "not_applicable")}


def comparison(prediction, observation):
    return {
        key: {
            "unit": "V" if key == "crest_V" else "s",
            "predicted": prediction[key],
            "observed": observation[key],
            "signed_error": prediction[key] - observation[key],
            "absolute_error": abs(prediction[key] - observation[key]),
            "absolute_percentage_error": 100
            * abs(prediction[key] - observation[key])
            / observation[key],
        }
        for key in ("front_s", "tail_s", "crest_V")
    }
