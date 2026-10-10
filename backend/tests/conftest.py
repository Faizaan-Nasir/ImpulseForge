import pytest

from powernext.contracts.models import RunRequest
from powernext.profiles.resolve import resolve


@pytest.fixture
def request_data():
    return {
        "equipment_profile_id": "workbook_benchmark_v1",
        "equipment_inputs": {"N_max": 15, "U_stage_max_V": 200000, "C_stage_F": 3e-6},
        "physics_mode": "calculator",
        "inventory": {
            "source": "inline",
            "front": [{"type_id": "f50", "nominal_ohm": 50, "available_quantity": 4}],
            "tail": [{"type_id": "t25", "nominal_ohm": 25, "available_quantity": 4}],
        },
        "target": {"crest_V": 1425000},
        "load": {"C_F": 850e-12},
        "setup": {
            "divider_C_F": 500e-12,
            "stray_C_F": 150e-12,
            "stray_L_H": 18.5e-6,
            "basic_capacitance_inclusion": "benchmark_omitted",
        },
        "charging_policy": {"kind": "fixed", "U_charge_V": 1425000 / (9 * 0.82)},
        "search": {"max_proposals": 4, "dp_max_parts": 1, "archive_stagnation_window": 10},
        "dp_tolerances": {"front_relative": 0.02, "tail_relative": 0.10},
    }


@pytest.fixture
def context(request_data):
    return resolve(RunRequest.model_validate(request_data))
