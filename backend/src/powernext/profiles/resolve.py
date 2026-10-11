import json
import math

from powernext.contracts.models import (
    MODEL_VERSION,
    DomainError,
    InlineInventory,
    Record,
    RunRequest,
)
from powernext.optimisation.objective import OBJECTIVE_POLICY
from powernext.profiles.registry import (
    WORKBOOK_INPUTS,
    digest,
    equipment,
    example_inventory,
    test_profile,
)


class Context(Record):
    context_id: str
    context_hash: str
    snapshot_json: str

    @property
    def data(self):
        return json.loads(self.snapshot_json)

    @property
    def request(self):
        return RunRequest.model_validate(self.data["request"])

    @property
    def hardware(self):
        return self.data["hardware"]

    @property
    def test(self):
        return self.data["test"]

    @property
    def inventory(self):
        return InlineInventory.model_validate(self.data["inventory"])

    @property
    def charge(self):
        return self.data["U_charge_V"]

    def public(self):
        return {**self.model_dump(exclude={"snapshot_json"}), **self.data}


def stock_bounds(inventory, N):
    result = {}
    for role in ("front", "tail"):
        types = getattr(inventory, role)
        usable = [(r, r.capacity(N)) for r in types if r.capacity(N) > 0]
        result[role] = {
            "type_count": len(usable),
            "effective_quantities": {r.type_id: q for r, q in usable},
            "available_parts": sum(q for _, q in usable),
            "min_ohm": 1 / sum(q / r.nominal_ohm for r, q in usable) if usable else None,
            "max_ohm": sum(q * r.nominal_ohm for r, q in usable) if usable else None,
            "count_vectors": math.prod(q + 1 for _, q in usable),
        }
    return result


def resolve(request: RunRequest, saved_inventories=None, model_bundle_hash=None) -> Context:
    if request.model_version != MODEL_VERSION:
        raise DomainError("unknown_model_version", request.model_version, "correction")
    hw = equipment(request.equipment_profile_id)
    fallback_source = "problem_statement_fallback"
    value_sources = {
        name: {
            "source": (
                "problem_statement_fallback"
                if name in ("stage_energy_max_J", "total_energy_max_J")
                else fallback_source
                if name == "C_stage_F"
                else "workbook_example_default"
                if name in ("N_max", "U_stage_max_V")
                else "project_model_policy"
            ),
            "value": value,
        }
        for name, value in hw.items()
        if name != "source_data"
    }
    workbook_cells = {"N_max": "B13", "U_stage_max_V": "B14", "C_stage_F": "B15"}
    for name, supplied in request.equipment_inputs.model_dump().items():
        fallback = hw[name]
        field_fallback_source = value_sources[name]["source"]
        if supplied is not None:
            hw[name] = supplied
        value_sources[name] = {
            "source": "frontend_input" if supplied is not None else field_fallback_source,
            "input_field": f"equipment_inputs.{name}",
            "workbook_cell": (
                f"Hybrid Calculator!{workbook_cells[name]}" if name in workbook_cells else None
            ),
            "value": hw[name],
            "fallback_value": fallback,
            "fallback_applied": supplied is None,
        }
    if request.impulse_type is not None:
        if "impulse_profile_id" not in request.model_fields_set:
            profile = (
                "lightning_project_v1"
                if request.impulse_type == "Lightning"
                else "switching_workbook_legacy_v1"
            )
            request = request.model_copy(update={"impulse_profile_id": profile})
        if test_profile(request.impulse_profile_id)["category"] != request.impulse_type:
            raise DomainError("impulse_category_profile_mismatch", "Impulse type/profile disagree")
    test = test_profile(request.impulse_profile_id)
    target_sources = {}
    for key in ("front_s", "tail_s", "tolerances"):
        value = getattr(request.target, key)
        if value is not None:
            test[key] = value.model_dump() if key == "tolerances" else value
        target_sources[key] = "frontend_input" if value is not None else "impulse_profile_default"
    hw["C_basic_F"] = request.setup.basic_C_F
    value_sources["C_basic_F"] = {
        "source": "frontend_input"
        if "basic_C_F" in request.setup.model_fields_set
        else "api_default",
        "input_field": "setup.basic_C_F",
        "value": hw["C_basic_F"],
    }
    if isinstance(request.inventory, InlineInventory):
        inv = request.inventory
    elif (
        request.inventory.profile_id == "project_front10_tail12_v1"
        and request.inventory.version == "1"
    ):
        inv = example_inventory()
    else:
        record = (saved_inventories or {}).get(request.inventory.profile_id)
        if record is None or record["version"] != request.inventory.version:
            raise DomainError("unknown_inventory", request.inventory.profile_id)
        inv = InlineInventory.model_validate(record["inventory"])
    if any(not any(r.available_quantity for r in getattr(inv, role)) for role in ("front", "tail")):
        raise DomainError("empty_inventory", "Each role requires available stock")
    if not any(
        all(stock_bounds(inv, n)[role]["available_parts"] > 0 for role in ("front", "tail"))
        for n in range(hw["N_min"], hw["N_max"] + 1)
    ):
        raise DomainError(
            "inventory_unavailable_for_any_stage_count",
            "Global stock cannot supply the minimum repeated stages",
            "assembly",
        )
    seed = max(
        hw["N_min"],
        math.ceil(
            request.target.crest_V / (request.expected_voltage_efficiency * hw["U_stage_max_V"])
        ),
    )
    charge = request.charging_policy.U_charge_V
    if request.charging_policy.kind == "seed_then_fixed":
        charge = request.target.crest_V / (seed * request.expected_voltage_efficiency)
    if charge is None:
        raise DomainError("missing_charging_voltage", "Charging voltage required")
    data = {
        "constraint_policy": "calibration_budgeted_constraints_v2",
        "objective_acceptance_policy": OBJECTIVE_POLICY,
        "request": request.model_dump(mode="json"),
        "model_bundle_hash": model_bundle_hash,
        "hardware": hw,
        "value_sources": value_sources,
        "source_precedence": [
            "frontend_input",
            "workbook_example_default",
            "retained_problem_statement_fallback",
        ],
        "input_sources": workbook_input_sources(request, value_sources),
        "test": test,
        "target_sources": target_sources,
        "inventory": inv.model_dump(mode="json"),
        "inventory_hash": digest(inv.model_dump(mode="json")),
        "U_charge_V": charge,
        "seed_N": min(seed, hw["N_max"]),
        "charge_policy_derivation": {
            "policy": request.charging_policy.kind,
            "seed_N": seed,
            "selected_V": charge,
        },
        "unknowns": [
            "equipment circuit approval",
            "component ratings unless provided",
            "model laboratory validation",
        ],
        "stock_by_N": {str(n): stock_bounds(inv, n) for n in range(hw["N_min"], hw["N_max"] + 1)},
    }
    context_hash = digest(data)
    return Context(
        context_id=context_hash[:24],
        context_hash=context_hash,
        snapshot_json=json.dumps(data, allow_nan=False),
    )


def workbook_input_sources(request, value_sources):
    result = {}
    for path, metadata in WORKBOOK_INPUTS.items():
        parent = request
        keys = path.split(".")
        for key in keys[:-1]:
            parent = getattr(parent, key)
        field = keys[-1]
        if keys[0] == "equipment_inputs":
            record = value_sources[field]
            value, source = record["value"], record["source"]
        else:
            value = getattr(parent, field)
            source = "frontend_input" if field in parent.model_fields_set else "api_default"
            if path == "impulse_type" and value is None:
                value = test_profile(request.impulse_profile_id)["category"]
                source = "selected_impulse_profile"
        result[path] = {
            **metadata,
            "sheet": "Hybrid Calculator",
            "value": value,
            "source": source,
        }
    return result
