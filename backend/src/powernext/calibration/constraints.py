"""Physical constraint verdicts belong to calibration, after physics and ML."""

from powernext.contracts.models import Constraint


def check_bound(name, value, limit, unit, origin="equipment_profile"):
    return Constraint(
        constraint_id=name,
        origin=origin,
        enforced_by=("calibration",),
        rule=f"value <= {limit}",
        observed_value=value,
        limit_value=limit,
        unit=unit,
        margin=limit - value if limit is not None else None,
        status=("unknown" if limit is None else "pass" if value <= limit else "fail"),
        reason_code="missing_rating" if limit is None else None,
    ).model_dump(mode="json")


def assess(context, candidate, baseline, correction=None):
    req = context.request
    hw = context.hardware
    N = candidate.N
    E = baseline["stage_energy_J"]
    value_sources = context.data.get("value_sources", {})
    fallback_source = (
        "workbook_benchmark_profile"
        if hw["profile_id"] == "workbook_benchmark_v1"
        else "problem_statement_fallback"
    )
    checks = [
        Constraint(
            constraint_id="HW_STAGES",
            origin=value_sources.get("N_max", {}).get("source", fallback_source),
            enforced_by=("calibration",),
            rule="N_min <= active stages <= N_max",
            observed_value=N,
            limit_value=[hw["N_min"], hw["N_max"]],
            status="pass",
        ).model_dump(mode="json"),
        check_bound(
            "HW_STAGE_CHARGE",
            candidate.U_charge_V,
            hw["U_stage_max_V"],
            "V",
            value_sources.get("U_stage_max_V", {}).get("source", fallback_source),
        ),
        check_bound(
            "HW_STAGE_ENERGY",
            E,
            hw["stage_energy_max_J"],
            "J",
            value_sources.get("stage_energy_max_J", {}).get("source", "problem_statement_fallback"),
        ),
        check_bound(
            "HW_TOTAL_ENERGY", N * E, hw["total_energy_max_J"], "J", "problem_statement_fallback"
        ),
    ]
    for role in ("front", "tail"):
        assembly = getattr(candidate, role)
        for resistor in getattr(context.inventory, role):
            observed = assembly.type_counts.get(resistor.type_id, 0)
            checks.append(
                Constraint(
                    constraint_id=f"STOCK_{role}_{resistor.type_id}",
                    origin="request_inventory",
                    enforced_by=("calibration",),
                    rule="Independent role per-type per-stage/global quantity cap",
                    observed_value=observed,
                    limit_value=resistor.capacity(N),
                    margin=resistor.capacity(N) - observed,
                    status="pass" if observed <= resistor.capacity(N) else "fail",
                ).model_dump(mode="json")
            )
    verified = (
        hw["physical_verified"]
        and bool(req.setup.circuit_evidence_id)
        and req.setup.external_front_series_ohm is not None
    )
    checks.append(
        Constraint(
            constraint_id="CIRCUIT_TOPOLOGY_VERIFIED",
            origin="equipment_evidence",
            enforced_by=("calibration",),
            rule="Registered topology/branch states have equipment evidence",
            status="pass" if verified else "unknown",
            reason_code=None if verified else "unresolved_circuit_evidence",
        ).model_dump(mode="json")
    )
    checks.append(
        Constraint(
            constraint_id="CAPACITOR_TRANSIENT_RATING",
            origin="equipment_evidence",
            enforced_by=("calibration",),
            rule="Internal transient/reversal rating verified",
            status="unknown",
            reason_code="lumped_model_cannot_certify_internal_stresses",
        ).model_dump(mode="json")
    )
    checks[0]["status"] = "pass" if hw["N_min"] <= N <= hw["N_max"] else "fail"
    for component in baseline.get("component_stresses", []):
        verdicts = []
        for rating, observed in (
            ("pulse_voltage_limit_V", "peak_voltage_V"),
            ("pulse_current_limit_A", "peak_current_A"),
            ("pulse_energy_limit_J", "pulse_energy_J"),
            ("average_power_limit_W", "average_power_W"),
            ("temperature_limit_K", "estimated_peak_temperature_K"),
        ):
            limit = component["rating_limits"][rating]
            value = component[observed]
            t = next(
                t
                for t in getattr(context.inventory, component["role"])
                if t.type_id == component["type_id"]
            )
            status = (
                "unknown"
                if value is None or limit is None or not t.ratings.evidence_id
                else "pass"
                if value <= limit
                else "fail"
            )
            verdicts.append(
                {
                    "rating": rating,
                    "observed": value,
                    "limit": limit,
                    "status": status,
                    "margin": None if value is None or limit is None else limit - value,
                }
            )
        status = (
            "fail"
            if any(v["status"] == "fail" for v in verdicts)
            else "pass"
            if t.approved and all(v["status"] == "pass" for v in verdicts)
            else "unknown"
        )
        component.update(
            rating_checks=verdicts, ratings_status=status, constraint_owner="calibration"
        )
        if component["generator_stage_index"] == 1:
            leaf = component["component_id"].split("/", 1)[1]
            role, identifier = leaf.split("/", 1)
            type_id, occurrence = identifier.rsplit("-", 1)
            checks.append(
                Constraint(
                    constraint_id=f"RESISTOR_{role}_{type_id}_{occurrence}",
                    origin="component_rating_evidence",
                    enforced_by=("calibration",),
                    rule="All applicable per-component ratings verified",
                    status=status,
                    reason_code="unresolved_component_rating" if status == "unknown" else None,
                ).model_dump(mode="json")
            )
    metrics = (correction or {}).get("corrected_metrics")
    if req.minimum_voltage_efficiency is not None:
        eta = metrics["crest_V"] / (N * candidate.U_charge_V) if metrics else None
        minimum = req.minimum_voltage_efficiency
        checks.append(
            Constraint(
                constraint_id="REQUEST_MIN_EFFICIENCY",
                origin="request",
                enforced_by=("calibration",),
                rule="ML corrected voltage transfer efficiency >= requested minimum",
                observed_value=eta,
                limit_value=minimum,
                margin=None if eta is None else eta - minimum,
                status="unknown" if eta is None else "pass" if eta >= minimum else "fail",
            ).model_dump(mode="json")
        )
    report = {
        "owner": "calibration",
        "evaluated_after": "physics_and_ml",
        "constraints": checks,
        "hardware_feasible": all(c["status"] == "pass" for c in checks if c["kind"] == "hard"),
        "known_constraints_satisfied": not any(
            c["status"] == "fail" for c in checks if c["kind"] == "hard"
        ),
    }
    from powernext.calibration.windows import feasibility_windows

    report["feasibility_windows"] = feasibility_windows(context, candidate, baseline, checks)
    # Compatibility projection for existing dashboard/performance consumers. These
    # fields are filled here, never by the physics/ML engines.
    baseline.update(
        constraints=checks,
        hardware_feasible=report["hardware_feasible"],
        constraint_owner="calibration",
        feasibility_windows=report["feasibility_windows"],
    )
    return report
