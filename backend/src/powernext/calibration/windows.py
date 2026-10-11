"""Analytical necessary energy windows, not a promise of waveform feasibility."""

import math


def feasibility_windows(context, candidate=None, baseline=None, checks=()):
    hw = context.hardware
    C, U = hw["C_stage_F"], context.charge
    Es, Et = hw["stage_energy_max_J"], hw["total_energy_max_J"]
    eta = context.request.expected_voltage_efficiency
    V = context.request.target.crest_V
    n = candidate.N if candidate else min(hw["N_max"], max(hw["N_min"], context.data["seed_N"]))
    E = 0.5 * C * U**2
    options = []
    for count in range(hw["N_min"], hw["N_max"] + 1):
        umax = min(hw["U_stage_max_V"], math.sqrt(2 * Es / C), math.sqrt(2 * Et / (count * C)))
        required = V / (eta * count)
        options.append(
            {
                "N": count,
                "charge_upper_V": umax,
                "charge_required_from_expected_efficiency_V": required,
                "necessary_target_energy_window_exists": required <= umax,
            }
        )
    fixed_counts = [
        count
        for count in range(hw["N_min"], hw["N_max"] + 1)
        if U <= hw["U_stage_max_V"] and E <= Es and count * E <= Et
    ]
    best = options[-1]
    at_current = {
        "charge_upper_V": min(
            hw["U_stage_max_V"], math.sqrt(2 * Es / C), math.sqrt(2 * Et / (n * C))
        )
    }
    cmax = min(2 * Es / U**2, 2 * Et / (n * U**2))
    # Conditional alternative: charge is adjusted externally to meet the expected
    # crest at N_max. Charge is not silently added to SMAC's three decisions.
    retuned_u = V / (eta * hw["N_max"])
    retuned_cmax = min(2 * Es / retuned_u**2, 2 * Et / (hw["N_max"] * retuned_u**2))
    suggestions = [
        f"At N={n} and fixed charge {U / 1000:.6f} kV/stage, stage capacitance must be >0 and <= {cmax * 1e6:.6f} µF to satisfy both stored-energy limits. Retest timing and ML after changing capacitance.",
        f"At N={n} and {C * 1e6:.6f} µF/stage, charge must be >0 and <= {at_current['charge_upper_V'] / 1000:.6f} kV/stage for energy/charging limits. This alone does not meet the requested crest.",
        f"If charge is deliberately retuned at N={hw['N_max']}, the expected-efficiency formula requires {retuned_u / 1000:.6f} kV/stage; capacitance must be <= {retuned_cmax * 1e6:.6f} µF, and the stage-voltage rating must also permit that charge.",
        f"To operate the current N={n} configuration unchanged, different equipment would need at least {E / 1000:.3f} kJ/stage and {n * E / 1000:.3f} kJ total stored-energy capability. These are required capabilities, not changes to the configured limits.",
    ]
    for check in checks:
        if check["status"] != "unknown":
            continue
        key = check["constraint_id"]
        if key.startswith("RESISTOR_"):
            continue
        if key == "CIRCUIT_TOPOLOGY_VERIFIED":
            suggestions.append(
                "Topology has no numerical safe window until its circuit/branch arrangement is verified and recorded; provide circuit evidence and external-front resistance."
            )
        elif key == "CAPACITOR_TRANSIENT_RATING":
            suggestions.append(
                "Capacitor transient/reversal rating needs internal capacitor stress evidence and manufacturer ratings. Per-stage charging voltage is not a verified transient rating."
            )
    if any(c["constraint_id"].startswith("RESISTOR_") and c["status"] == "unknown" for c in checks):
        suggestions.append(
            "Resistor ratings require manufacturer/equipment evidence plus voltage, current, pulse energy, average power and temperature limits. Calculator mode supplies no current/voltage traces, so it cannot establish these rating windows; an exact, supported circuit evaluation or measurement is required."
        )
    required_ratings = [
        {
            "component_id": component["component_id"],
            "role": component["role"],
            "type_id": component["type_id"],
            "minimum_required_ratings": {
                "pulse_voltage_limit_V": component["peak_voltage_V"],
                "pulse_current_limit_A": component["peak_current_A"],
                "pulse_energy_limit_J": component["pulse_energy_J"],
                "average_power_limit_W": component["average_power_W"],
                "temperature_limit_K": component["estimated_peak_temperature_K"],
            },
            "status": "required_capability_only_not_equipment_approval",
        }
        for component in (baseline or {}).get("component_stresses", [])
    ]
    return {
        "owner": "calibration",
        "scope": "necessary_analytical_energy_and_voltage_conditions_only",
        "waveform_or_ml_feasibility_guaranteed": False,
        "charge_policy": "fixed_during_this_search",
        "actual_stage_count": n,
        "stage_capacitance_F": C,
        "actual_charge_V": U,
        "fixed_charge_energy_feasible_stage_counts": fixed_counts,
        "fixed_charge_energy_infeasible": not fixed_counts,
        "energy_infeasibility_stops_search": False,
        "stage_energy_limit_J": Es,
        "total_energy_limit_J": Et,
        "current_stage_capacitance_upper_F": cmax,
        "current_stage_charge_upper_V": at_current["charge_upper_V"],
        "required_current_stage_energy_rating_J": E,
        "required_current_total_energy_rating_J": n * E,
        "stage_options_with_charge_retuning": options,
        "expected_efficiency_crest_upper_at_N_max_V": eta * hw["N_max"] * best["charge_upper_V"],
        "conditional_target_charge_at_N_max_V": retuned_u,
        "conditional_target_capacitance_upper_at_N_max_F": retuned_cmax,
        "expected_efficiency_assumption": eta,
        "suggestions": suggestions,
        "component_required_ratings": required_ratings,
    }
