from collections import Counter

import numpy as np

from powernext.assembly.dp import equivalent
from powernext.physics.thermal import thermal_response


def component_stresses(context, candidate, time, loop_current, generator_voltage):
    types = {
        role: {t.type_id: t for t in getattr(context.inventory, role)} for role in ("front", "tail")
    }
    shot_rate = context.request.setup.shot_rate_per_minute
    components = []
    checks = []
    for role, assembly in (("front", candidate.front), ("tail", candidate.tail)):
        occurrences = Counter()
        wires = {leaf["component_id"]: leaf for leaf in assembly.netlist}
        voltage = (
            (
                candidate.front.equivalent_ohm * loop_current
                if role == "front"
                else generator_voltage / candidate.N
            )
            if time is not None
            else None
        )

        def walk(node, v, role=role, occurrences=occurrences, wires=wires):
            if node.op != "resistor":
                if node.op == "parallel":
                    for child in node.children:
                        walk(child, v)
                else:
                    total = float(equivalent(node))
                    for child in node.children:
                        walk(child, None if v is None else v * float(equivalent(child)) / total)
                return
            occurrences[node.type_id] += 1
            t = types[role][node.type_id]
            r = t.nominal_ohm
            pulse = None if v is None else v * v / r
            energy = None if pulse is None else float(np.trapezoid(pulse, time))
            peak_v = None if v is None else float(np.max(np.abs(v)))
            peak_i = None if v is None else float(np.max(np.abs(v / r)))
            peak_p = None if pulse is None else float(np.max(pulse))
            avg = None if energy is None or shot_rate is None else energy * shot_rate / 60
            ambient = context.request.environment.values.get("ambient_temperature_K")
            thermal = None
            thermal_details = None
            if (
                time is not None
                and ambient is not None
                and t.ratings.C_theta_J_per_K
                and t.ratings.R_theta_K_per_W
                and shot_rate is not None
            ):
                thermal_details = thermal_response(
                    time,
                    pulse,
                    ambient,
                    t.ratings.R_theta_K_per_W,
                    t.ratings.C_theta_J_per_K,
                    60 / shot_rate,
                )
                thermal = thermal_details["estimated_peak_temperature_K"]
            limits = {
                "pulse_voltage_limit_V": t.ratings.pulse_voltage_limit_V,
                "pulse_current_limit_A": t.ratings.pulse_current_limit_A,
                "pulse_energy_limit_J": t.ratings.pulse_energy_limit_J,
                "average_power_limit_W": t.ratings.average_power_limit_W,
                "temperature_limit_K": t.ratings.temperature_limit_K,
            }
            for stage in range(1, candidate.N + 1):
                local_id = f"{role}/{node.type_id}-{occurrences[node.type_id]}"
                prefix = f"stage_{stage:02d}/{role}/"
                cid = f"stage_{stage:02d}/" + local_id
                wire = wires[local_id]
                components.append(
                    {
                        "component_id": cid,
                        "generator_stage_index": stage,
                        "role": role,
                        "type_id": node.type_id,
                        "nominal_ohm": r,
                        "node_a": prefix + wire["node_a"],
                        "node_b": prefix + wire["node_b"],
                        "resistance_interval_ohm": [
                            r * (1 - t.tolerance_fraction),
                            r * (1 + t.tolerance_fraction),
                        ],
                        "peak_voltage_V": peak_v,
                        "peak_current_A": peak_i,
                        "peak_power_W": peak_p,
                        "pulse_energy_J": energy,
                        "average_power_W": avg,
                        "initial_temperature_K": ambient,
                        "estimated_peak_temperature_K": thermal,
                        "thermal_status": "unknown" if thermal is None else "periodic_RC_estimate",
                        "thermal_details": thermal_details,
                        "ratings_status": "not_assessed",
                        "rating_limits": limits,
                        "rating_checks": [],
                        "equal_sharing_assumed": True,
                        "assumptions": [
                            "nominal constant resistance",
                            "identical stage sharing",
                            "trace horizon bounds energy integration",
                        ],
                    }
                )

        walk(assembly.recipe, voltage)
    return {"components": components, "constraints": checks}
