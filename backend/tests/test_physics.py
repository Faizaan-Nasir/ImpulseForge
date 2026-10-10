import pytest

from powernext.assembly.cp_sat import AssemblyEngine
from powernext.contracts.models import DomainError, Proposal, RunRequest
from powernext.physics.forward import evaluate, inverse
from powernext.profiles.resolve import resolve


def actual(context):
    return AssemblyEngine().realise(context, Proposal(N=9, Rf_required_ohm=50, Rt_required_ohm=25))[
        0
    ]


def test_calculator_benchmark(context):
    seed = inverse(context, 9)
    assert seed["Rf_required_ohm"] == pytest.approx(49.52213922066368)
    assert seed["Rt_required_ohm"] == pytest.approx(23.942283773045347)
    result = evaluate(context, actual(context))
    assert result["metrics"]["front_s"] == pytest.approx(1.210029958306818e-6)
    assert result["metrics"]["tail_s"] == pytest.approx(5.22088875e-5)
    assert result["metrics"]["crest_V"] == pytest.approx(1425000)
    assert not result["hardware_feasible"]
    assert result["trace"] is None


def test_exact_analytic_reference(request_data):
    request_data["physics_mode"] = "exact"
    request_data["setup"]["stray_L_H"] = 0
    ctx = resolve(RunRequest.model_validate(request_data))
    result = evaluate(ctx, actual(ctx))
    assert result["metrics"]["front_s"] == pytest.approx(1.9356218151e-6, rel=1e-6)
    assert result["metrics"]["tail_s"] == pytest.approx(5.6448212493e-5, rel=1e-6)
    assert result["metrics"]["crest_V"] == pytest.approx(1658013.7612, rel=1e-6)
    assert len(result["component_stresses"]) == 18
    assert result["component_stresses"][0]["pulse_energy_J"] > 0
    assert result["component_stresses"][0]["estimated_peak_temperature_K"] is None


def test_ode_matches_near_zero_inductance(request_data):
    request_data["physics_mode"] = "exact"
    request_data["setup"]["stray_L_H"] = 1e-9
    ctx = resolve(RunRequest.model_validate(request_data))
    result = evaluate(ctx, actual(ctx))
    assert result["metrics"]["front_s"] == pytest.approx(1.9356218151e-6, rel=0.001)
    assert result["metrics"]["tail_s"] == pytest.approx(5.6448212493e-5, rel=0.001)
    assert result["diagnostics"]["method"] == "Radau"


def test_capacitor_energy_pdf(request_data):
    request_data["equipment_profile_id"] = "haefely_pdf_v1"
    request_data["equipment_inputs"]["C_stage_F"] = None
    request_data["setup"]["basic_capacitance_inclusion"] = "add_separately"
    request_data["charging_policy"]["U_charge_V"] = 100000
    ctx = resolve(RunRequest.model_validate(request_data))
    result = evaluate(ctx, actual(ctx))
    assert result["stage_energy_J"] == 625
    assert result["total_energy_J"] == 5625
    assert result["derived"]["C2_F"] == pytest.approx(1500e-12)


@pytest.mark.parametrize("charge_V,expected_status", [(100000, "pass"), (200000, "fail")])
def test_fifteen_stage_project_bound_retains_only_energy_limits(
    request_data, charge_V, expected_status
):
    request_data["equipment_profile_id"] = "haefely_pdf_v1"
    request_data["equipment_inputs"]["C_stage_F"] = None
    request_data["setup"]["basic_capacitance_inclusion"] = "add_separately"
    request_data["charging_policy"]["U_charge_V"] = charge_V
    ctx = resolve(RunRequest.model_validate(request_data))
    candidate, _ = AssemblyEngine().realise(
        ctx, Proposal(N=15, Rf_required_ohm=50, Rt_required_ohm=25)
    )
    result = evaluate(ctx, candidate)
    checks = {item["constraint_id"]: item for item in result["constraints"]}
    assert checks["HW_STAGES"]["status"] == "pass"
    assert checks["HW_STAGES"]["limit_value"] == [1, 15]
    assert "HW_STACK_CHARGE" not in checks
    assert "HW_CREST" not in checks
    assert checks["HW_TOTAL_ENERGY"]["status"] == expected_status
    assert result["total_energy_J"] == 15 * 0.5 * 1.25e-7 * charge_V**2
    with pytest.raises(DomainError):
        AssemblyEngine().realise(ctx, Proposal(N=16, Rf_required_ohm=50, Rt_required_ohm=25))


def test_parallel_rc_load(request_data):
    request_data["physics_mode"] = "exact"
    request_data["setup"]["stray_L_H"] = 0
    request_data["load"] = {"model_id": "parallel_rc_v1", "C_F": 850e-12, "R_ohm": 10000}
    ctx = resolve(RunRequest.model_validate(request_data))
    result = evaluate(ctx, actual(ctx))
    assert result["metrics"]["crest_V"] > 0
    assert result["diagnostics"]["method"] == "Radau"


def test_frontend_capacitance_reaches_physics_and_stored_energy(request_data):
    request_data["equipment_profile_id"] = "haefely_pdf_v1"
    request_data["setup"]["basic_capacitance_inclusion"] = "add_separately"
    request_data["equipment_inputs"] = {
        "N_max": 10,
        "C_stage_F": 3e-6,
        "U_stage_max_V": 40000,
    }
    request_data["charging_policy"]["U_charge_V"] = 30000
    context = resolve(RunRequest.model_validate(request_data))
    result = evaluate(context, actual(context))
    assert result["derived"]["C1_F"] == pytest.approx(3e-6 / 9)
    assert result["stage_energy_J"] == 1350
    assert result["total_energy_J"] == 12150
    checks = {item["constraint_id"]: item for item in result["constraints"]}
    assert checks["HW_STAGES"]["limit_value"] == [1, 10]
    assert checks["HW_STAGE_CHARGE"]["limit_value"] == 40000
    assert checks["HW_STAGE_CHARGE"]["origin"] == "frontend_input"
    assert checks["HW_STAGE_ENERGY"]["limit_value"] == 2500


def test_impractical_ode_scope_rejected(request_data):
    from powernext.contracts.models import DomainError

    request_data["physics_mode"] = "exact"
    request_data["inventory"]["tail"][0]["nominal_ohm"] = 1e12
    context = resolve(RunRequest.model_validate(request_data))
    candidate, _ = AssemblyEngine().realise(
        context, Proposal(N=9, Rf_required_ohm=50, Rt_required_ohm=1e12)
    )
    with pytest.raises(DomainError, match="250000"):
        evaluate(context, candidate)
