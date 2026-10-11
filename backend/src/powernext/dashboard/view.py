"""Read persisted results; diagnostic cases never become eligible recommendations."""

import numpy as np

from powernext.optimisation.objective import evaluate_objective, objective_order
from powernext.physics.plot_reconstruction import bundle


def cases_for_run(store, run_id, context):
    result = store.get("result", run_id) or {}

    def passing(records):
        return [
            e
            for e in records
            if e.get("correction", {}).get("corrected_metrics")
            and evaluate_objective(context, e["correction"]["corrected_metrics"])[
                "waveform_within_tolerance"
            ]
        ]

    eligible = passing(result.get("recommendations", []))
    predicted = passing(result.get("predicted_setups", []))
    if eligible and (context.request.purpose != "diagnostic" or len(eligible) >= len(predicted)):
        return eligible, "eligible_recommendations"
    if predicted:
        return predicted, "diagnostic_evaluated_cases"
    ids = list(
        dict.fromkeys(
            e["candidate_id"]
            for e in store.event_page(run_id, 0, 1000000)
            if e["pipeline_stage_name"] == "evaluation"
        )
    )
    evaluated = [store.get("diagnostic_candidate", i) or store.get("candidate", i) for i in ids]
    evaluated = passing([e for e in evaluated if e])

    def key(record):
        metrics = record["correction"]["corrected_metrics"]
        objective = evaluate_objective(context, metrics)
        return (*objective_order(objective), record["candidate_id"])

    return sorted(evaluated, key=key)[:3], "diagnostic_evaluated_cases"


def plot_bundle(context, cases):
    records = []
    for record in cases:
        corrected = record.get("correction", {}).get("corrected_metrics")
        records.append(
            {
                "candidate_id": record["candidate_id"],
                "correction": {
                    "corrected_metrics": corrected or record["physics"]["metrics"],
                    "model_version": record.get("correction", {}).get("model_version"),
                },
                "waveform_origin": "ml_parameter_reconstruction"
                if corrected
                else "physics_parameter_reconstruction",
            }
        )
    data = bundle(context, records)
    target = next(
        (c for c in data["curves"] if c["curve_id"] == "target" and c.get("voltage_V")), None
    )
    times = np.asarray(data["time_s"])
    if target and len(times) > 1:
        for curve in data["curves"]:
            if curve.get("voltage_V") is None:
                continue
            difference = np.asarray(curve["voltage_V"]) - np.asarray(target["voltage_V"])
            rms = float(np.sqrt(np.trapezoid(difference**2, times) / (times[-1] - times[0])))
            curve["comparison_to_target"] = {
                "rms_voltage_V": rms,
                "normalised_rms_percent": 100 * rms / target["metrics"]["crest_V"],
                "horizon_s": float(times[-1] - times[0]),
                "interpretation": "Difference between parameter-reconstructed curves; not measured model accuracy",
            }
    return data


def evidence(context, run_record, cases, display_mode):
    rows = []
    for index, record in enumerate(cases, 1):
        c = record["candidate"]
        physics = record["physics"]
        corrected = record.get("correction", {}).get("corrected_metrics")
        metrics = corrected or physics["metrics"]
        score = evaluate_objective(context, metrics)
        rows.append(
            {
                "evidence_id": f"case_{index}",
                "case_number": index,
                "candidate_id": record["candidate_id"],
                "eligible": record["eligible"],
                "N": c["N"],
                "U_charge_V": c["U_charge_V"],
                "Rf_actual_ohm": c["front"]["equivalent_ohm"],
                "Rt_actual_ohm": c["tail"]["equivalent_ohm"],
                "resistors_per_stage": c["front"]["total_resistors"] + c["tail"]["total_resistors"],
                "metrics": metrics,
                "metrics_origin": "residual_corrected" if corrected else "physics_baseline",
                "S": score["S"],
                "J": score["J"],
                "waveform_within_tolerance": score["waveform_within_tolerance"],
                "crest_minimum_satisfied": score["crest_minimum_satisfied"],
                "calibration_required": score["calibration_required"],
                "acceptance_policy": score["acceptance_policy"],
                "errors": score["errors"],
                "voltage_utilisation": physics["voltage_utilisation"],
                "stage_energy_J": physics["stage_energy_J"],
                "total_energy_J": physics["total_energy_J"],
                "constraints": [
                    {
                        k: x.get(k)
                        for k in (
                            "constraint_id",
                            "status",
                            "observed_value",
                            "limit_value",
                            "reason_code",
                        )
                    }
                    for x in physics["constraints"]
                ],
                "model_support": record.get("correction", {}).get("support"),
                "environment_effects": record.get("correction", {}).get("environment_effects"),
                "model_lab_validated": record.get("correction", {}).get("lab_validated", False),
            }
        )
    return {
        "evidence_id": "run",
        "context_hash": context.context_hash,
        "display_mode": display_mode,
        "status": run_record["status"],
        "stop_reason": run_record.get("stop_reason"),
        "returned_recommendations": run_record.get("returned_recommendations", 0),
        "returned_predictions": run_record.get("returned_predictions", 0),
        "ml_converged": run_record.get("ml_converged", False),
        "calibration_basis": run_record.get("calibration_basis"),
        "counters": run_record.get("counters", {}),
        "target": {
            "crest_V": context.request.target.crest_V,
            "front_s": context.test["front_s"],
            "tail_s": context.test["tail_s"],
        },
        "tolerances": context.test["tolerances"],
        "ordering": "Required crest minimum first, then worst normalised waveform deviation and weighted deviation; hardware eligibility is required for recommendations",
        "cases": rows,
    }
