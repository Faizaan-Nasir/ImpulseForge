"""Worksheet calculation as an explicit diagnostic reference, independent of search."""

import math
from time import monotonic

from powernext.contracts.models import DomainError, Proposal, RunRequest
from powernext.optimisation.objective import evaluate_objective
from powernext.performance.metrics import build_report
from powernext.physics.forward import calculator_metrics, check_bound, evaluate, inverse, parameters


def reference_request(request):
    body = request.model_dump(mode="json")
    body.update(
        purpose="diagnostic", physics_mode="calculator", charging_policy={"kind": "seed_then_fixed"}
    )
    body["search"]["dp_max_parts"] = 1
    body["dp_tolerances"] = {"front_relative": 1e-12, "tail_relative": 1e-12}
    return RunRequest.model_validate(body)


def workbook_baseline(context, assembly, residual):
    started = monotonic()
    N = context.data["seed_N"]
    ideal = inverse(context, N)
    # Positive Excel ROUND(x/5, 0)*5: ties go away from zero, not Python's bankers rounding.
    rf, rt = (
        5 * math.floor(ideal[key] / 5 + 0.5) for key in ("Rf_required_ohm", "Rt_required_ohm")
    )
    if min(rf, rt) <= 0:
        raise DomainError(
            "rounded_resistance_nonpositive",
            "Worksheet rounding gives a zero resistor; no buildable reference",
            "assembly",
        )
    settings = {"N": N, "U_charge_V": context.charge, "Rf_actual_ohm": rf, "Rt_actual_ohm": rt}
    physics = {
        "baseline_mode": "calculator",
        "metrics": calculator_metrics(context, N, rf, rt).model_dump(mode="json"),
        "derived": parameters(context, N, rf, rt),
    }
    E = 0.5 * context.hardware["C_stage_F"] * context.charge**2
    physics["constraints"] = [
        check_bound(
            "HW_STAGE_ENERGY",
            E,
            context.hardware["stage_energy_max_J"],
            "J",
            "problem_statement_fallback",
        ),
        check_bound(
            "HW_TOTAL_ENERGY",
            N * E,
            context.hardware["total_energy_max_J"],
            "J",
            "problem_statement_fallback",
        ),
    ]
    correction = {
        "status": "not_invoked",
        "corrected_metrics": None,
        "reason": "reference_not_buildable",
    }
    record = {
        "physics": physics,
        "correction": correction,
        "eligible": False,
        "evaluation_mode": "workbook_reference",
    }
    try:
        candidate, solver = assembly.realise(
            context, Proposal(N=N, Rf_required_ohm=rf, Rt_required_ohm=rt, source="workbook_round5")
        )
    except DomainError as exc:
        if exc.stage != "assembly":
            raise
        return {
            "status": "reference_only",
            "settings": settings,
            "ideal": ideal,
            "record": record,
            "context": context.public(),
            "inventory_check": {"status": "unavailable", "reason": exc.code},
            "policy": "Calculator sizing, five-ohm rounding and one physical resistor per role; mathematical reference is not a recommendation",
        }
    physics = evaluate(context, candidate, include_trace=False)
    correction = residual.correct(context, candidate, physics)
    record.update(
        candidate_id=candidate.candidate_id,
        candidate=candidate.model_dump(mode="json"),
        physics=physics,
        correction=correction,
        objective=evaluate_objective(
            context, correction.get("corrected_metrics") or physics["metrics"]
        ),
        performance=build_report(
            context,
            candidate,
            physics,
            correction,
            residual.report(),
            {
                "scope": "independent_workbook_reference",
                "total_seconds": monotonic() - started,
                "stage_seconds": {},
            },
        ),
    )
    return {
        "status": "evaluated",
        "settings": settings,
        "ideal": ideal,
        "record": record,
        "context": context.public(),
        "inventory_check": {"status": "buildable", "solver": solver},
        "policy": "Calculator sizing, five-ohm rounding and one physical resistor per role; diagnostic correction never waives hard constraints",
    }
