import numpy as np
import pytest

from powernext.assembly.cp_sat import AssemblyEngine
from powernext.contracts.models import DomainError, Proposal, RunRequest
from powernext.physics.stress import component_stresses
from powernext.physics.thermal import thermal_response
from powernext.profiles.resolve import resolve


def test_per_leaf_stress_and_thermal(request_data):
    request_data["setup"]["shot_rate_per_minute"] = 2
    ratings = {
        "pulse_voltage_limit_V": 1000,
        "pulse_current_limit_A": 100,
        "pulse_energy_limit_J": 10,
        "average_power_limit_W": 100,
        "temperature_limit_K": 400,
        "R_theta_K_per_W": 1,
        "C_theta_J_per_K": 0.2,
        "evidence_id": "mock-data",
    }
    request_data["inventory"]["front"] = [
        {
            "type_id": "f100",
            "nominal_ohm": 100,
            "available_quantity": 4,
            "approved": True,
            "ratings": ratings,
        }
    ]
    request_data["environment"] = {
        "availability": "recorded",
        "values": {"ambient_temperature_K": 300},
    }
    context = resolve(RunRequest.model_validate(request_data))
    candidate, _ = AssemblyEngine().realise(
        context, Proposal(N=9, Rf_required_ohm=100, Rt_required_ohm=25)
    )
    times = np.linspace(0, 0.001, 101)
    result = component_stresses(context, candidate, times, np.full(101, 2.0), np.full(101, 100.0))
    first = result["components"][0]
    assert first["peak_voltage_V"] == 200
    assert first["peak_power_W"] == 400
    assert first["pulse_energy_J"] == pytest.approx(0.4)
    assert first["thermal_details"]["single_pulse_adiabatic_upper_temperature_K"] == pytest.approx(
        302
    )
    assert first["estimated_peak_temperature_K"] == pytest.approx(
        300 + 400 * (1 - np.exp(-0.001 / 0.2))
    )
    assert first["node_a"].startswith("stage_01/front/")
    assert len(result["components"]) == 18
    assert result["components"][9]["estimated_peak_temperature_K"] is None


def test_periodic_thermal_steady_constant_power():
    result = thermal_response([0, 10], [2, 2], 300, 5, 2, 10)
    assert result["initial_temperature_K"] == pytest.approx(310)
    assert result["estimated_peak_temperature_K"] == pytest.approx(310)


def test_thermal_invalid_time():
    with pytest.raises(DomainError, match="Invalid periodic"):
        thermal_response([0, 1, 0.5], [1, 1, 1], 300, 1, 1, 10)


def test_short_pulse_large_time_constant_does_not_lose_heat():
    result = thermal_response([0, 0.001], [0, 1], 300, 1e6, 1e6, 30)
    # At a very long thermal time constant, steady rise approaches average power * R_theta.
    assert result["initial_temperature_K"] == pytest.approx(300 + (0.0005 / 30) * 1e6, rel=1e-8)
