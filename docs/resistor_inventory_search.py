"""Exact nominal series-parallel resistance search, bounded by inventory and parts.

This prototype selects a nominal resistance and one wiring witness. It does not
validate voltage, pulse-energy, insulation, parasitics, or permitted HV assemblies.
Input JSON: [{"ohms": 50, "quantity": 4}, ...]. Quantities apply to one assembly.
No third-party dependencies are required.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations_with_replacement, product
import json
from pathlib import Path


@dataclass(frozen=True)
class Network:
    resistance: Fraction
    expression: str


def load_inventory(items: list[dict]) -> tuple[tuple[Fraction, ...], tuple[int, ...]]:
    """Merge equal nominal values; appropriate only for interchangeable parts."""
    stock: Counter = Counter()
    for item in items:
        value = Fraction(str(item["ohms"]))
        quantity = item["quantity"]
        if value <= 0:
            raise ValueError("Resistances must be positive and finite.")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            raise ValueError("Quantities must be nonnegative integers.")
        stock[value] += quantity
    values = tuple(sorted(value for value, quantity in stock.items() if quantity))
    if not values:
        raise ValueError("Inventory must contain at least one available resistor.")
    return values, tuple(stock[value] for value in values)


def resistance_label(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else str(value)


def build_catalogue(
    items: list[dict], max_parts: int, max_entries: int = 250_000
) -> tuple[tuple[Fraction, ...], dict, dict]:
    """Return all nominal values per count vector, with one witness per value.

    Combining every nonempty unordered partition covers all two-terminal
    series-parallel networks. Exact fractions avoid floating-point deduplication
    errors. One witness is sufficient for nominal matching, not rating checks.
    The entry budget aborts rather than silently returning an incomplete search.
    """
    if isinstance(max_parts, bool) or not isinstance(max_parts, int) or max_parts < 1:
        raise ValueError("max_parts must be a positive integer.")
    if max_entries < 1:
        raise ValueError("max_entries must be positive.")
    values, quantities = load_inventory(items)
    max_parts = min(max_parts, sum(quantities))
    size = len(values)
    tables: dict[tuple[int, ...], dict[Fraction, Network]] = {}
    entries = 0
    statistics = {}

    for parts in range(1, max_parts + 1):
        layer_entries = 0
        layer_values: set[Fraction] = set()
        layer_states = 0
        for selection in combinations_with_replacement(range(size), parts):
            counts_list = [0] * size
            for index in selection:
                counts_list[index] += 1
            counts = tuple(counts_list)
            if any(count > available for count, available in zip(counts, quantities)):
                continue
            results: dict[Fraction, Network] = {}

            def save(value: Fraction, expression: str) -> None:
                nonlocal entries, layer_entries
                if value in results:
                    return
                if entries >= max_entries:
                    raise ValueError(
                        f"Exact-search budget of {max_entries} entries exceeded. "
                        "Reduce max_parts or explicitly raise max_entries. "
                        "No incomplete optimum is returned."
                    )
                results[value] = Network(value, expression)
                entries += 1
                layer_entries += 1

            if parts == 1:
                index = selection[0]
                save(values[index], resistance_label(values[index]))
            else:
                for left_counts in product(*(range(count + 1) for count in counts)):
                    if not 0 < sum(left_counts) < parts:
                        continue
                    right_counts = tuple(c - a for c, a in zip(counts, left_counts))
                    if left_counts > right_counts:
                        continue  # Series and parallel are commutative.
                    left_table = tables[left_counts]
                    right_table = tables[right_counts]
                    for left in left_table.values():
                        for right in right_table.values():
                            if left_counts == right_counts and left.resistance > right.resistance:
                                continue
                            a, b = left.resistance, right.resistance
                            save(a + b, f"({left.expression} + {right.expression})")
                            save(a * b / (a + b), f"({left.expression} || {right.expression})")
            tables[counts] = results
            layer_values.update(results)
            layer_states += 1
        statistics[parts] = {
            "inventory_count_states": layer_states,
            "state_resistance_entries": layer_entries,
            "distinct_resistances_using_exactly_this_many_parts": len(layer_values),
        }
    return values, tables, statistics


def closest_network(items: list[dict], target, max_parts: int, max_entries=250_000) -> dict:
    desired = Fraction(str(target))
    if desired <= 0:
        raise ValueError("Target must be positive and finite.")
    values, tables, statistics = build_catalogue(items, max_parts, max_entries)
    best = None
    best_key = None
    distinct: set[Fraction] = set()
    for counts, networks in tables.items():
        distinct.update(networks)
        for value, network in networks.items():
            key = (abs(value - desired), sum(counts), network.expression)
            if best_key is None or key < best_key:
                best_key = key
                best = (counts, network)
    counts, network = best
    error = network.resistance - desired
    return {
        "target_ohms": float(desired),
        "equivalent_ohms": float(network.resistance),
        "exact_equivalent_ohms": str(network.resistance),
        "signed_error_ohms": float(error),
        "absolute_error_percent": float(abs(error) / desired * 100),
        "parts_used": sum(counts),
        "assembly": network.expression,
        "notation": "+ means series; || means parallel; leaves are ohms",
        "components": [
            {"ohms": float(value), "quantity": count}
            for value, count in zip(values, counts) if count
        ],
        "distinct_resistances_up_to_limit": len(distinct),
        "statistics_by_part_count": statistics,
        "guarantee": (
            "Closest nominal resistance across all series-parallel networks "
            "within supplied inventory quantities and max_parts. "
            "Equal-error ties prefer fewer parts, then a deterministic witness."
        ),
        "hardware_status": "Not checked: permitted wiring, ratings and parasitics.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--target", required=True, help="Target in ohms")
    parser.add_argument("--max-parts", type=int, required=True)
    parser.add_argument("--max-entries", type=int, default=250_000)
    args = parser.parse_args()
    try:
        result = closest_network(
            json.loads(args.inventory.read_text()), args.target,
            args.max_parts, args.max_entries,
        )
    except (ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        parser.exit(2, f"Search failed: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
