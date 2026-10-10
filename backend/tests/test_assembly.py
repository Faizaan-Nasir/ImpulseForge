from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from powernext.assembly.cp_sat import AssemblyEngine
from powernext.assembly.dp import build_options, canonical, equivalent, to_assembly
from powernext.contracts.models import DomainError, Proposal, Recipe, ResistorType


def leaf(name, value):
    return Recipe(op="resistor", type_id=name, ohm=value)


def test_exact_four_part_network():
    recipe = Recipe(
        op="parallel",
        children=(
            Recipe(op="series", children=(leaf("r100", 100), leaf("r30", 30))),
            Recipe(op="series", children=(leaf("r50", 50), leaf("r30", 30))),
        ),
    )
    a = to_assembly(recipe, "front")
    assert equivalent(recipe) == Fraction(1040, 21)
    assert a.type_counts == {"r30": 2, "r50": 1, "r100": 1}
    assert len(a.netlist) == 4
    assert len({r["component_id"] for r in a.netlist}) == 4


@given(st.integers(1, 10000), st.integers(1, 10000))
def test_commutative_exact_values(a, b):
    x, y = leaf("a", a), leaf("b", b)
    for op in ("series", "parallel"):
        left = Recipe(op=op, children=(x, y))
        right = Recipe(op=op, children=(y, x))
        assert equivalent(left) == equivalent(right)
        assert canonical(left) == canonical(right)


def test_quantity_cap_not_assembly_size():
    types = [
        ResistorType(type_id="a", nominal_ohm=10, available_quantity=4),
        ResistorType(type_id="b", nominal_ohm=20, available_quantity=4),
    ]
    recipes, _ = build_options(types, 2, 5, 10000, 5)
    assert any(to_assembly(r, "front").total_resistors == 5 for r in recipes)
    assert all(max(to_assembly(r, "front").type_counts.values()) <= 4 for r in recipes)


def test_dp_budget_fails_without_false_optimum():
    with pytest.raises(DomainError, match="incomplete"):
        build_options([ResistorType(type_id="a", nominal_ohm=10, available_quantity=4)], 2, 4, 1, 5)


def test_cp_sat_selects_independent_four_front_tail(context):
    candidate, report = AssemblyEngine().realise(
        context, Proposal(N=9, Rf_required_ohm=50, Rt_required_ohm=25)
    )
    assert candidate.front.equivalent_ohm == 50
    assert candidate.tail.equivalent_ohm == 25
    assert report["status"] == "OPTIMAL"


def test_stage_limit(context):
    with pytest.raises(DomainError):
        AssemblyEngine().realise(context, Proposal(N=16, Rf_required_ohm=50, Rt_required_ohm=25))


def test_equal_ohms_different_types_stay_distinct():
    from powernext.contracts.models import ResistorType

    options, _report = build_options(
        [
            ResistorType(type_id="brand-a", nominal_ohm=30, available_quantity=1),
            ResistorType(type_id="brand-b", nominal_ohm=30, available_quantity=1),
        ],
        2,
        1,
        100,
        10,
    )
    assert len(options) == 2
    assert options[0].type_id != options[1].type_id


def test_forged_identity_rejected_by_direct_physics(context):
    from powernext.physics.forward import evaluate

    candidate, _ = AssemblyEngine().realise(
        context, Proposal(N=9, Rf_required_ohm=50, Rt_required_ohm=25)
    )
    with pytest.raises(DomainError, match="Candidate ID"):
        evaluate(context, candidate.model_copy(update={"candidate_id": "forged"}))
