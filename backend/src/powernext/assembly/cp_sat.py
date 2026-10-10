import math
from collections import OrderedDict
from fractions import Fraction
from time import monotonic

from ortools.sat.python import cp_model

from powernext.assembly.dp import build_options, to_assembly
from powernext.assembly.validate import candidate_identity
from powernext.contracts.models import Candidate, DomainError, Proposal
from powernext.profiles.registry import digest
from powernext.profiles.resolve import stock_bounds


class AssemblyEngine:
    def __init__(self):
        self.cache = OrderedDict()
        self.max_cache_entries = 4

    def pool(self, context, N, role, target, tolerance):
        types = getattr(context.inventory, role)
        limits = context.request.search
        key = digest(
            {
                "role": role,
                "types": [t.model_dump() for t in types],
                "capacities": [t.capacity(N) for t in types],
                "parts": limits.dp_max_parts,
                "states": limits.dp_max_states,
                "seconds": limits.dp_seconds,
            }
        )
        cache_hit = key in self.cache
        if not cache_hit:
            recipes, report = build_options(
                types, N, limits.dp_max_parts, limits.dp_max_states, limits.dp_seconds
            )
            self.cache[key] = ([to_assembly(recipe, role) for recipe in recipes], report)
            if len(self.cache) > self.max_cache_entries:
                self.cache.popitem(last=False)
        self.cache.move_to_end(key)
        all_options, report = self.cache[key]
        numerical_pad = max(math.ulp(target) * 4, 1e-15)
        options = [
            a
            for a in all_options
            if abs(a.equivalent_ohm - target) <= target * tolerance + numerical_pad
        ]
        options = [
            a
            for a in options
            if abs(
                Fraction(a.nominal_fraction["numerator"], a.nominal_fraction["denominator"])
                - Fraction(str(target))
            )
            <= Fraction(str(target)) * Fraction(str(tolerance))
        ]
        if not options:
            raise DomainError(
                "resistance_tolerance_unmet",
                f"No {role} assembly in declared tolerance/scope",
                "assembly",
            )
        options.sort(
            key=lambda a: (abs(a.equivalent_ohm - target), a.total_resistors, a.assembly_id)
        )
        # The candidate pool is explicitly bounded to prevent solver size explosions.
        return options[:50], {
            **report,
            "cache_hit": cache_hit,
            "option_count": len(options),
            "selected_pool_count": min(50, len(options)),
            "pool_truncated": len(options) > 50,
        }

    def realise(self, context, proposal: Proposal, forbidden_pairs=()):
        bounds = stock_bounds(context.inventory, proposal.N)
        hw = context.hardware
        if not hw["N_min"] <= proposal.N <= hw["N_max"]:
            raise DomainError("stages_out_of_range", "Stage count outside hardware", "assembly")
        req = context.request
        for role, target, tol in (
            ("front", proposal.Rf_required_ohm, req.dp_tolerances.front_relative),
            ("tail", proposal.Rt_required_ohm, req.dp_tolerances.tail_relative),
        ):
            b = bounds[role]
            if (
                b["min_ohm"] is None
                or target * (1 + tol) < b["min_ohm"]
                or target * (1 - tol) > b["max_ohm"]
            ):
                raise DomainError(
                    "inventory_range_infeasible",
                    f"{role} required interval outside supplied stock bounds",
                    "assembly",
                )
        front, fr = self.pool(
            context, proposal.N, "front", proposal.Rf_required_ohm, req.dp_tolerances.front_relative
        )
        tail, tr = self.pool(
            context, proposal.N, "tail", proposal.Rt_required_ohm, req.dp_tolerances.tail_relative
        )
        model = cp_model.CpModel()
        xs = [model.new_bool_var(f"f_{i}") for i in range(len(front))]
        ys = [model.new_bool_var(f"t_{i}") for i in range(len(tail))]
        model.add_exactly_one(xs)
        model.add_exactly_one(ys)
        for role, options, variables in (("front", front, xs), ("tail", tail, ys)):
            for resistor in getattr(context.inventory, role):
                model.add(
                    sum(
                        v * a.type_counts.get(resistor.type_id, 0)
                        for v, a in zip(variables, options)
                    )
                    <= resistor.capacity(proposal.N)
                )
        for i, f in enumerate(front):
            for j, t in enumerate(tail):
                if (f.assembly_id, t.assembly_id) in forbidden_pairs:
                    model.add(xs[i] + ys[j] <= 1)
        scale = 10**8
        mismatches = [
            round(scale * abs(a.equivalent_ohm - target) / target)
            for options, target in (
                (front, proposal.Rf_required_ohm),
                (tail, proposal.Rt_required_ohm),
            )
            for a in options
        ]
        variables = xs + ys
        options = front + tail
        primary = sum(v * c for v, c in zip(variables, mismatches))
        model.minimize(primary)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = req.search.cp_sat_seconds
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = req.seed
        solve_start = monotonic()
        status = solver.solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise DomainError(
                "cp_sat_" + solver.status_name(status).lower(),
                "No selected pair in finite option pool",
                "assembly",
            )
        selected_front = next(i for i, x in enumerate(xs) if solver.value(x))
        selected_tail = next(i for i, y in enumerate(ys) if solver.value(y))
        quantity_status = "not_run_primary_unproven"
        first_status = solver.status_name(status)
        bound = solver.best_objective_bound
        # Lexicographic second phase: minimise quantity only after a proven primary optimum.
        if status == cp_model.OPTIMAL:
            model.add(primary == round(solver.objective_value))
            model.minimize(sum(v * a.total_resistors for v, a in zip(variables, options)))
            solver.parameters.max_time_in_seconds = max(
                1e-6, req.search.cp_sat_seconds - (monotonic() - solve_start)
            )
            second = solver.solve(model)
            quantity_status = solver.status_name(second)
            if second in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                selected_front = next(i for i, x in enumerate(xs) if solver.value(x))
                selected_tail = next(i for i, y in enumerate(ys) if solver.value(y))
                status = second
            else:
                status = cp_model.FEASIBLE
        f = front[selected_front]
        t = tail[selected_tail]
        identity = candidate_identity(context, proposal.N, f, t)
        candidate = Candidate(
            candidate_id=identity,
            context_hash=context.context_hash,
            proposal=proposal,
            N=proposal.N,
            U_charge_V=context.charge,
            front=f,
            tail=t,
        )
        return candidate, {
            "solver": "OR-Tools CP-SAT",
            "status": solver.status_name(status),
            "primary_status": first_status,
            "quantity_tiebreak_status": quantity_status,
            "lexicographic_optimal": first_status == "OPTIMAL" and quantity_status == "OPTIMAL",
            "primary_bound": bound,
            "integer_scale": scale,
            "front": fr,
            "tail": tr,
            "guarantee": "Finite option pool; integer-scaled mismatch, quantity tie-break; exact tolerance rechecked",
        }
