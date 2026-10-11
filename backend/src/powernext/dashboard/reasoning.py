"""Deterministic decision explanation from recorded physics, ML and SHAP evidence."""

OUTPUTS = (
    ("front_s", "Front / peak time", 1e6, "µs"),
    ("tail_s", "Tail time", 1e6, "µs"),
    ("crest_V", "Crest voltage", 1e-3, "kV"),
)
FEATURES = {
    "N": ("Active stages", 1, "stages"),
    "U_charge_V": ("Charging voltage per stage", 1e-3, "kV"),
    "Rf_stage_actual_ohm": ("Actual front resistance per stage", 1, "Ω"),
    "Rt_stage_actual_ohm": ("Actual tail resistance per stage", 1, "Ω"),
    "C_object_F": ("Test-object capacitance", 1e12, "pF"),
    "C_divider_F": ("Divider capacitance", 1e12, "pF"),
    "C_stray_F": ("Stray capacitance", 1e12, "pF"),
    "L_effective_H": ("Effective loop inductance", 1e6, "µH"),
    "C_generator_F": ("Erected generator capacitance", 1e6, "µF"),
    "C_load_effective_F": ("Effective load capacitance", 1e12, "pF"),
    "R_front_effective_ohm": ("Effective circuit front resistance", 1, "Ω"),
    "R_tail_effective_ohm": ("Effective circuit tail resistance", 1, "Ω"),
    "physics_front_s": ("Physics front / peak prediction", 1e6, "µs"),
    "physics_tail_s": ("Physics tail prediction", 1e6, "µs"),
    "physics_crest_V": ("Physics crest prediction", 1e-3, "kV"),
    "expected_voltage_efficiency": ("Expected voltage efficiency", 100, "%"),
}


def output_story(row, key, label, scale, unit):
    baseline = row.get("physics_metrics", {}).get(key)
    predicted = row["metrics"][key]
    residual = predicted - baseline if baseline is not None else None
    raw = row.get("shap", {})
    shap_output = next(
        (o for o in raw.get("outputs", []) if o["output_name"] == "residual_" + key), None
    )
    result = {
        "evidence_id": f"{row['evidence_id']}_{key}",
        "output_key": key,
        "label": label,
        "display_unit": unit,
        "display_scale": scale,
        "physics_value": baseline,
        "ml_residual": residual,
        "corrected_value": predicted,
        "target_value": row.get("errors", {}).get(key.split("_")[0], {}).get("target"),
        "shap_status": "complete"
        if raw.get("status") == "complete"
        and shap_output
        and shap_output.get("additivity_verified")
        and baseline is not None
        else "unavailable",
        "shap_reason": raw.get("reason", "not_requested")
        if raw.get("status") != "complete"
        else None,
        "contributions": [],
    }
    if baseline is None:
        result["explanation"] = (
            "The physics baseline was not recorded; no residual explanation is invented."
        )
    else:
        residual = predicted - baseline
        direction = (
            "increased" if residual > 0 else "decreased" if residual < 0 else "left unchanged"
        )
        result["explanation"] = (
            f"Physics gave {baseline * scale:.6f} {unit}. The ML correction {direction} this by "
            f"{abs(residual) * scale:.6f} {unit}, producing {predicted * scale:.6f} {unit}."
        )
    if result["shap_status"] != "complete" or shap_output is None:
        return result
    contributions = []
    for f in shap_output["feature_contributions"]:
        feature_label, value_scale, input_unit = FEATURES.get(f["feature"], (f["feature"], 1, "SI"))
        contributions.append(
            {
                **f,
                "label": feature_label,
                "display_input_value": f["value"] * value_scale,
                "input_unit": input_unit,
                "display_contribution": f["contribution"] * scale,
                "direction": "increases"
                if f["contribution"] > 0
                else "decreases"
                if f["contribution"] < 0
                else "unchanged",
            }
        )
    contributions.sort(key=lambda f: (-abs(f["contribution"]), f["feature"]))
    reference = shap_output["reference_residual"]
    total = sum(f["contribution"] for f in contributions)
    result.update(
        reference_residual=reference,
        sum_contributions=total,
        contributions=contributions,
        top_contributions=contributions[:5],
        other_contributions=sum(f["contribution"] for f in contributions[5:]),
        additivity_error=shap_output.get(
            "saved_prediction_additivity_error", shap_output["additivity_error"]
        ),
        additivity_verified=shap_output.get("additivity_verified", False),
        method=shap_output["method"],
        nsamples=shap_output["nsamples"],
        background_count=raw.get("background_count"),
        reference_meaning="Expected residual prediction on the saved training-background sample; not the physics baseline or an observed measurement.",
    )
    positive = next((f for f in contributions if f["contribution"] > 0), None)
    negative = next((f for f in contributions if f["contribution"] < 0), None)
    shifts = []
    for feature in (positive, negative):
        if feature:
            shifts.append(
                f"{feature['label']} at {feature['display_input_value']:.6g} {feature['input_unit']} "
                f"{feature['direction']} the residual by {feature['display_contribution']:+.6f} {unit}"
            )
    result["shap_explanation"] = (
        f"Relative to the background residual {reference * scale:+.6f} {unit}, "
        + ("; ".join(shifts) + ". " if shifts else "the feature contributions are zero. ")
        + f"All feature contributions sum to {total * scale:+.6f} {unit}; adding the background reconstructs the ML correction."
    )
    return result


def ranking_comparisons(rows, preference):
    if not rows:
        return []
    best = rows[0]
    result = []
    for row in rows[1:]:
        if best["S"] != row["S"]:
            criterion = "S"
            reason = (
                f"Case #1 has the smaller worst tolerance-normalised deviation: S={best['S']:.6f}, "
                f"compared with {row['S']:.6f} for Case #{row['case_number']}. "
                "This decides the order before J or resistor counts are considered."
            )
        elif best["J"] != row["J"]:
            criterion = "J"
            reason = (
                f"S is tied. Case #1 has the smaller weighted deviation: J={best['J']:.6f}, "
                f"compared with {row['J']:.6f} for Case #{row['case_number']}."
            )
        else:
            criterion = "secondary_tie_break"
            if preference == "stages":
                fields = [
                    ("stage count", "N"),
                    ("resistor count", "resistors_per_stage"),
                    ("charge", "U_charge_V"),
                ]
            elif preference == "voltage":
                fields = [
                    ("charge", "U_charge_V"),
                    ("resistor count", "resistors_per_stage"),
                    ("stage count", "N"),
                ]
            else:
                fields = [
                    ("resistor count", "resistors_per_stage"),
                    ("stage count", "N"),
                    ("charge", "U_charge_V"),
                ]
            decisive = next(
                ((label, field) for label, field in fields if best[field] != row[field]), None
            )
            reason = (
                f"S and J are tied; the '{preference}' tie preference selects the lower {decisive[0]} "
                f"({best[decisive[1]]:.6g} versus {row[decisive[1]]:.6g})."
                if decisive
                else "S, J and all configured secondary values are tied; deterministic candidate identity decides the order."
            )
        result.append(
            {
                "candidate_id": row["candidate_id"],
                "case_number": row["case_number"],
                "criterion": criterion,
                "reason": reason,
                "evidence_refs": [best["evidence_id"], row["evidence_id"]],
            }
        )
    return result


def constraint_groups(rows):
    grouped = {}
    for row in rows:
        for check in row["constraints"]:
            if check["status"] not in ("fail", "unknown"):
                continue
            identifier = check["constraint_id"]
            group = "RESISTOR_RATINGS" if identifier.startswith("RESISTOR_") else identifier
            item = grouped.setdefault(
                group, {"constraint_group": group, "status": check["status"], "checks": []}
            )
            item["checks"].append({**check, "case_number": row["case_number"]})
    for group, item in grouped.items():
        first = item["checks"][0]
        if group in ("HW_STAGE_ENERGY", "HW_TOTAL_ENERGY"):
            scope = "per stage" if group == "HW_STAGE_ENERGY" else "for the whole generator"
            item["explanation"] = (
                f"Stored energy {scope} fails in {len(item['checks'])} case checks. "
                f"Case #{first['case_number']} stores {first['observed_value'] / 1000:.3f} kJ against "
                f"the {first['limit_value'] / 1000:.3f} kJ limit. Resistor adjustments cannot reduce "
                "the initial stored energy at fixed stage count, charging voltage and capacitance."
            )
        else:
            label = {
                "RESISTOR_RATINGS": "Resistor voltage/current/energy ratings",
                "CAPACITOR_TRANSIENT_RATING": "Capacitor transient rating",
                "CIRCUIT_TOPOLOGY_VERIFIED": "Circuit topology approval",
            }.get(group, group.replace("_", " ").capitalize())
            item["explanation"] = (
                f"{label}: {item['status']} in {len(item['checks'])} checks across the returned alternatives; this does not establish hardware eligibility."
            )
    return list(grouped.values())


def build_reasoning(evidence):
    rows = evidence["cases"]
    cases = []
    for row in rows:
        outputs = [output_story(row, *description) for description in OUTPUTS]
        p = row.get("physics_derived", {})
        if row.get("physics_mode") == "calculator":
            physics_text = (
                f"Case #{row['case_number']} uses {row['N']} charged stages at "
                f"{row['U_charge_V'] / 1000:.6f} kV/stage. The actual front/tail resistances "
                f"are {row['Rf_actual_ohm']:.6f} Ω and {row['Rt_actual_ohm']:.6f} Ω per stage. "
                "The workbook calculator derives timing from the effective circuit resistances, capacitances and loop inductance. "
                f"Crest is the supplied efficiency ({row['expected_voltage_efficiency']:.6g}) × N × charging voltage; "
                "it is an efficiency assumption, not an independent simulated loss prediction."
            )
        else:
            physics_text = (
                f"Case #{row['case_number']} uses the actual selected resistor networks and "
                "load R/L/C circuit. The numerical physics solver supplies the baseline waveform metrics before residual correction."
            )
        cases.append(
            {
                "candidate_id": row["candidate_id"],
                "case_number": row["case_number"],
                "evidence_id": row["evidence_id"],
                "eligible": row["eligible"],
                "physics_explanation": physics_text,
                "circuit_values": p,
                "physics_constants": row.get("physics_constants", {}),
                "physics_mode": row.get("physics_mode"),
                "outputs": outputs,
                "model_support": row.get("model_support"),
                "model_status": row.get("model_status"),
                "unmodelled_effects": row.get("model_unavailable_effects", []),
                "shap_cached": row.get("shap", {}).get("cached", False),
                "shap_generation_seconds": row.get("shap", {}).get("generation_seconds"),
            }
        )
    best = rows[0] if rows else None
    criterion = (
        max(best.get("errors", {}).items(), key=lambda item: item[1]["normalised_error"])[0]
        if best and best.get("errors")
        else None
    )
    lead = (
        f"Case #1 is the highest-ranked evaluated waveform match: S={best['S']:.6f} and J={best['J']:.6f}. "
        + (f"Its largest tolerance-normalised deviation is {criterion}. " if criterion else "")
        + "The ordering minimises the worst normalised deviation first, the weighted deviation second, and uses the selected secondary preference only for ties."
        if best
        else "No successful ML waveform match is available to rank."
    )
    status = (
        "complete"
        if cases and all(o["shap_status"] == "complete" for c in cases for o in c["outputs"])
        else "partial"
        if cases
        else "unavailable"
    )
    counters = evidence.get("counters", {})
    return {
        "feasibility_windows": evidence.get("feasibility_windows"),
        "status": status,
        "selection_explanation": lead,
        "highest_ranked_candidate_id": best["candidate_id"] if best else None,
        "comparison": ranking_comparisons(rows, evidence.get("secondary_preference", "balanced")),
        "search_explanation": (
            f"The run made {counters.get('proposals', 0)} proposals, completed "
            f"{counters.get('physics_predictions', counters.get('physics_evaluations', 0))} physics predictions "
            f"and produced {counters.get('ml_predictions', 0)} fresh ML predictions. "
            f"It stopped because: {evidence.get('stop_reason', 'not_recorded')}. Cached repeats are not new ML inference."
        ),
        "cases": cases,
        "constraints": constraint_groups(rows),
        "interpretation": "SHAP explains how this fitted model allocates its residual prediction relative to a training-background sample. It does not establish physical causation or measured reality. Correlated and derived features share information; independent masking can create combinations that are not physical circuit configurations.",
        "scope": "The present model uses synthetic workbook data. Environmental conditions, per-resistor heat and exact wiring effects were not learned; no SHAP contribution or causal explanation is invented for them. Extrapolated estimates remain marked as extrapolated.",
        "eligibility_note": "Waveform ranking is separate from physical eligibility. Failed/unknown hardware checks and absent laboratory validation are retained.",
    }
