import copy

import pytest
from pydantic import ValidationError

from powernext.contracts.models import InlineInventory, RunRequest
from powernext.profiles.resolve import resolve, stock_bounds


def test_benchmark_constants(context):
    assert context.hardware["N_max"] == 15
    assert context.hardware["C_stage_F"] == 3e-6
    assert context.hardware["stage_energy_max_J"] == 2500
    assert context.hardware["total_energy_max_J"] == 30000


def test_pdf_all_constants(request_data):
    request_data["equipment_profile_id"] = "haefely_pdf_v1"
    request_data["equipment_inputs"]["C_stage_F"] = None
    request_data["setup"]["basic_capacitance_inclusion"] = "add_separately"
    hw = resolve(RunRequest.model_validate(request_data)).hardware
    assert (hw["N_max"], hw["C_stage_F"], hw["stage_energy_max_J"], hw["total_energy_max_J"]) == (
        15,
        1.25e-7,
        2500,
        30000,
    )
    assert hw["source_data"]["retained_problem_statement_parameters"] == {
        "total_energy_max_J": 30000,
        "stage_energy_max_J": 2500,
        "C_stage_F": 1.25e-7,
    }
    assert hw["C_basic_F"] == 0
    assert set(hw).isdisjoint({"U_stack_max_V", "crest_min_V", "crest_max_V", "shots_per_minute"})


def test_context_deep_immutability(context):
    old = context.context_hash
    context.hardware["N_max"] = 100
    context.request.setup.geometry["changed"] = True
    assert context.hardware["N_max"] == 15
    assert not context.request.setup.geometry
    assert context.context_hash == old


@pytest.mark.parametrize(
    "field,value",
    [
        ("nominal_ohm", 0),
        ("nominal_ohm", float("nan")),
        ("available_quantity", -1),
        ("available_quantity", True),
    ],
)
def test_bad_inventory(request_data, field, value):
    request_data["inventory"]["front"][0][field] = value
    with pytest.raises(ValidationError):
        RunRequest.model_validate(request_data)


def test_duplicate_ids(request_data):
    request_data["inventory"]["front"].append(copy.deepcopy(request_data["inventory"]["front"][0]))
    with pytest.raises(ValidationError):
        RunRequest.model_validate(request_data)


def test_global_stock_and_independent_roles():
    inv = InlineInventory(
        front=[
            {
                "type_id": "same",
                "nominal_ohm": 37.5,
                "available_quantity": 10,
                "quantity_scope": "global",
            }
        ],
        tail=[{"type_id": "same", "nominal_ohm": 37.5, "available_quantity": 4}],
    )
    b = stock_bounds(inv, 4)
    assert b["front"]["effective_quantities"]["same"] == 2
    assert b["tail"]["effective_quantities"]["same"] == 4
    assert b["front"]["max_ohm"] == 75


def test_charge_limit(request_data):
    request_data["charging_policy"]["U_charge_V"] = 200001
    ctx = resolve(RunRequest.model_validate(request_data))
    assert ctx.charge == 200001  # final calibration owns the charge verdict


def test_hidden_profile_override(request_data):
    request_data["N_max"] = 999
    with pytest.raises(ValidationError):
        RunRequest.model_validate(request_data)


def test_global_stock_can_supply_single_stage(request_data):
    for role in ("front", "tail"):
        request_data["inventory"][role][0].update(quantity_scope="global", available_quantity=1)
    context = resolve(RunRequest.model_validate(request_data))
    assert context.data["stock_by_N"]["1"]["front"]["available_parts"] == 1
    assert context.data["stock_by_N"]["2"]["front"]["available_parts"] == 0


def test_frontend_equipment_inputs_replace_profile_values(request_data):
    request_data["equipment_profile_id"] = "haefely_pdf_v1"
    request_data["setup"]["basic_capacitance_inclusion"] = "add_separately"
    request_data["equipment_inputs"] = {
        "N_max": 20,
        "U_stage_max_V": 250000,
        "C_stage_F": 3e-6,
    }
    request_data["charging_policy"]["U_charge_V"] = 225000
    context = resolve(RunRequest.model_validate(request_data))
    assert context.hardware["N_max"] == 20
    assert context.hardware["U_stage_max_V"] == 250000
    assert context.hardware["C_stage_F"] == 3e-6
    assert context.hardware["stage_energy_max_J"] == 2500
    assert context.hardware["total_energy_max_J"] == 30000
    assert context.data["value_sources"]["C_stage_F"]["source"] == "frontend_input"
    assert not context.data["value_sources"]["C_stage_F"]["fallback_applied"]
    assert context.data["stock_by_N"]["20"]


def test_partial_or_null_inputs_fall_back_individually(request_data):
    request_data["equipment_profile_id"] = "haefely_pdf_v1"
    request_data["setup"]["basic_capacitance_inclusion"] = "add_separately"
    request_data["equipment_inputs"] = {"N_max": 10, "C_stage_F": None}
    context = resolve(RunRequest.model_validate(request_data))
    assert context.hardware["N_max"] == 10
    assert context.hardware["C_stage_F"] == 1.25e-7
    assert context.hardware["U_stage_max_V"] == 200000
    assert context.data["value_sources"]["C_stage_F"]["fallback_applied"]
    assert context.data["value_sources"]["C_stage_F"]["source"] == "problem_statement_fallback"


def test_supplied_voltage_limit_is_enforced(request_data):
    request_data["equipment_inputs"] = {"U_stage_max_V": 100000}
    ctx = resolve(RunRequest.model_validate(request_data))
    assert ctx.charge > ctx.hardware["U_stage_max_V"]


@pytest.mark.parametrize(
    "values", [{"N_max": 0}, {"N_max": 2.5}, {"U_stage_max_V": 0}, {"C_stage_F": -1}]
)
def test_invalid_frontend_equipment_inputs(request_data, values):
    request_data["equipment_inputs"] = values
    with pytest.raises(ValidationError):
        RunRequest.model_validate(request_data)


def test_changed_frontend_equipment_changes_context_identity(request_data):
    original = resolve(RunRequest.model_validate(request_data))
    request_data["equipment_inputs"] = {"C_stage_F": 2e-6}
    changed = resolve(RunRequest.model_validate(request_data))
    assert original.context_hash != changed.context_hash


def test_frontend_target_is_not_replaced_or_clamped_to_document_example(request_data):
    request_data["equipment_profile_id"] = "haefely_pdf_v1"
    request_data["setup"]["basic_capacitance_inclusion"] = "add_separately"
    request_data["target"]["crest_V"] = 10000
    context = resolve(RunRequest.model_validate(request_data))
    assert context.request.target.crest_V == 10000
    assert context.data["input_sources"]["target.crest_V"]["source"] == "frontend_input"


@pytest.mark.parametrize("value", [None, 60000.0])
def test_editable_stage_energy_limit_and_provenance(request_data, value):
    original = resolve(RunRequest.model_validate(request_data))
    request_data["equipment_inputs"]["stage_energy_max_J"] = value
    ctx = resolve(RunRequest.model_validate(request_data))
    assert ctx.hardware["stage_energy_max_J"] == (2500 if value is None else value)
    source = ctx.data["value_sources"]["stage_energy_max_J"]
    assert source["source"] == ("problem_statement_fallback" if value is None else "frontend_input")
    assert source["workbook_cell"] is None
    assert source["fallback_applied"] is (value is None)
    assert ctx.hardware["total_energy_max_J"] == 30000
    if value is not None:
        assert ctx.context_hash != original.context_hash


@pytest.mark.parametrize("value", [0, -1, float("inf")])
def test_invalid_stage_energy_limit(request_data, value):
    request_data["equipment_inputs"]["stage_energy_max_J"] = value
    with pytest.raises(ValidationError):
        RunRequest.model_validate(request_data)
