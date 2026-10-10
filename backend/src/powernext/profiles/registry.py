import hashlib
import json
from pathlib import Path
from typing import Any

from powernext.contracts.models import DomainError, InlineInventory

DOCS = Path(__file__).resolve().parents[4] / "docs"
WORKBOOK_INPUTS = {
    "system_max_voltage_V": {"cell": "B5", "unit": "V", "workbook_to_SI": 1000},
    "impulse_type": {"cell": "B6", "unit": "category", "workbook_to_SI": None},
    "target.crest_V": {"cell": "B7", "unit": "V", "workbook_to_SI": 1000},
    "load.C_F": {"cell": "B8", "unit": "F", "workbook_to_SI": 1e-12},
    "setup.divider_C_F": {"cell": "B9", "unit": "F", "workbook_to_SI": 1e-12},
    "setup.stray_C_F": {"cell": "B10", "unit": "F", "workbook_to_SI": 1e-12},
    "setup.stray_L_H": {"cell": "B11", "unit": "H", "workbook_to_SI": 1e-6},
    "expected_voltage_efficiency": {"cell": "B12", "unit": "fraction", "workbook_to_SI": 1},
    "equipment_inputs.N_max": {"cell": "B13", "unit": "stages", "workbook_to_SI": 1},
    "equipment_inputs.U_stage_max_V": {"cell": "B14", "unit": "V", "workbook_to_SI": 1000},
    "equipment_inputs.C_stage_F": {"cell": "B15", "unit": "F", "workbook_to_SI": 1e-6},
}
DOCUMENT_PARAMETERS = {
    "total_energy_max_J": 30000,
    "stage_energy_max_J": 2500,
    "C_stage_F": 1.25e-7,
}
PDF_PROFILE: dict[str, Any] = {
    "profile_id": "haefely_pdf_v1",
    **DOCUMENT_PARAMETERS,
    "N_min": 1,  # Positive-integer model domain, not a PDF hardware restriction.
    "N_max": 15,  # Workbook input example; frontend value takes precedence.
    "U_stage_max_V": 200000,  # Workbook input example, not a PDF constraint.
    "C_basic_F": 0,  # Workbook load formula sums supplied load/divider/stray only.
    "per_type_stage_cap": 4,  # Explicit project decision, separately per role.
    "topology": "generator_side_tail_series_v1",
    "physical_verified": False,
    "constants": {"k_front": 1.67, "k_LC": 2.5, "k_tail": 0.693},
    "source_data": {"retained_problem_statement_parameters": DOCUMENT_PARAMETERS},
}
BENCHMARK: dict[str, Any] = {
    **PDF_PROFILE,
    "profile_id": "workbook_benchmark_v1",
}
TESTS: dict[str, Any] = {
    "lightning_project_v1": {
        "category": "Lightning",
        "front_s": 1.2e-6,
        "tail_s": 50e-6,
        "tolerances": {"front": 0.30, "tail": 0.20, "crest": 0.03},
        "timing": "virtual_origin_lightning",
        "standard_verified": False,
    },
    "switching_workbook_legacy_v1": {
        "category": "Switching",
        "front_s": 250e-6,
        "tail_s": 2500e-6,
        "tolerances": {"front": 0.20, "tail": 0.20, "crest": 0.03},
        "timing": "legacy_peak_true_origin",
        "standard_verified": False,
    },
    "switching_legacy_extended_tail_v1": {
        "category": "Switching",
        "front_s": 250e-6,
        "tail_s": 2500e-6,
        "tolerances": {"front": 0.20, "tail": 0.60, "crest": 0.03},
        "timing": "legacy_peak_true_origin",
        "standard_verified": False,
    },
}


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def equipment(name):
    profiles = {PDF_PROFILE["profile_id"]: PDF_PROFILE, BENCHMARK["profile_id"]: BENCHMARK}
    if name not in profiles:
        raise DomainError("unknown_equipment", name)
    return json.loads(json.dumps(profiles[name]))


def test_profile(name):
    if name not in TESTS:
        raise DomainError("unknown_test_profile", name)
    return json.loads(json.dumps(TESTS[name]))


def example_inventory() -> InlineInventory:
    roles = {}
    for role in ("front", "tail"):
        data = json.loads((DOCS / f"resistor_inventory_{role}.json").read_text())
        roles[role] = [
            {
                "type_id": f"{role}_{item['ohms']}",
                "nominal_ohm": item["ohms"],
                "available_quantity": item["quantity"],
            }
            for item in data
        ]
    return InlineInventory(**roles)
