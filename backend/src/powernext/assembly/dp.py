from collections import Counter
from fractions import Fraction
from itertools import combinations_with_replacement, product
from time import monotonic

from powernext.contracts.models import Assembly, DomainError, Recipe
from powernext.profiles.registry import digest


def equivalent(recipe):
    if recipe.op == "resistor":
        return Fraction(str(recipe.ohm))
    values = [equivalent(r) for r in recipe.children]
    return (
        sum(values, Fraction())
        if recipe.op == "series"
        else 1 / sum((1 / v for v in values), Fraction())
    )


def canonical(recipe):
    if recipe.op == "resistor":
        return recipe
    children = []
    for child in recipe.children:
        child = canonical(child)
        children.extend(child.children if child.op == recipe.op else [child])
    children.sort(key=lambda c: c.model_dump_json())
    return Recipe(op=recipe.op, children=tuple(children))


def leaf_counts(recipe):
    if recipe.op == "resistor":
        return Counter({recipe.type_id: 1})
    result = Counter()
    for c in recipe.children:
        result.update(leaf_counts(c))
    return result


def to_assembly(recipe, role, guarantee="All canonical recipes within completed bounded search"):
    recipe = canonical(recipe)
    value = equivalent(recipe)
    counts = leaf_counts(recipe)
    netlist = []
    occurrences = Counter()
    nodes = 0

    def wire(node, a, b):
        nonlocal nodes
        if node.op == "resistor":
            occurrences[node.type_id] += 1
            netlist.append(
                {
                    "component_id": f"{role}/{node.type_id}-{occurrences[node.type_id]}",
                    "type_id": node.type_id,
                    "nominal_ohm": node.ohm,
                    "node_a": a,
                    "node_b": b,
                }
            )
        elif node.op == "parallel":
            for c in node.children:
                wire(c, a, b)
        else:
            previous = a
            for idx, c in enumerate(node.children):
                nodes += 1
                following = b if idx == len(node.children) - 1 else f"node_{nodes}"
                wire(c, previous, following)
                previous = following

    wire(recipe, "in", "out")
    return Assembly(
        assembly_id=digest({"role": role, "recipe": recipe.model_dump()})[:24],
        role=role,
        equivalent_ohm=float(value),
        nominal_fraction={"numerator": value.numerator, "denominator": value.denominator},
        recipe=recipe,
        netlist=tuple(netlist),
        type_counts=dict(counts),
        total_resistors=sum(counts.values()),
        search_guarantee=guarantee,
    )


def build_options(types, N, max_parts, max_states, seconds):
    start = monotonic()
    usable = [t for t in types if t.capacity(N) > 0]
    if not usable:
        raise DomainError(
            "inventory_unavailable_at_stage_count", "No stock for repeated stages", "assembly"
        )
    quantities = [t.capacity(N) for t in usable]
    tables = {}
    all_recipes = []
    entries = 0

    def budget():
        if entries >= max_states or monotonic() - start >= seconds:
            raise DomainError(
                "dp_budget_exhausted", "No incomplete closest-value claim is returned", "assembly"
            )

    for parts in range(1, min(max_parts, sum(quantities)) + 1):
        for selection in combinations_with_replacement(range(len(usable)), parts):
            budget()
            counts = tuple(selection.count(i) for i in range(len(usable)))
            if any(c > q for c, q in zip(counts, quantities)):
                continue
            results = {}
            if parts == 1:
                t = usable[selection[0]]
                recipe = Recipe(op="resistor", type_id=t.type_id, ohm=t.nominal_ohm)
                results[recipe.model_dump_json()] = recipe
            else:
                for left in product(*(range(c + 1) for c in counts)):
                    budget()
                    if not 0 < sum(left) < parts:
                        continue
                    right = tuple(c - a for c, a in zip(counts, left))
                    if left > right:
                        continue
                    for a in tables[left]:
                        for b in tables[right]:
                            budget()
                            for op in ("series", "parallel"):
                                recipe = canonical(Recipe(op=op, children=(a, b)))
                                key = recipe.model_dump_json()
                                if key not in results:
                                    budget()
                                    results[key] = recipe
                                    entries += 1
            if parts == 1:
                entries += len(results)
            tables[counts] = list(results.values())
            all_recipes.extend(results.values())
    return all_recipes, {
        "status": "completed",
        "canonical_recipes": len(all_recipes),
        "count_vectors": len(tables),
        "max_parts": max_parts,
        "elapsed_s": monotonic() - start,
        "scope": "bounded canonical series-parallel recipes",
    }
