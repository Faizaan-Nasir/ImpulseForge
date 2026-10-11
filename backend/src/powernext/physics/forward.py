import math
from collections.abc import Callable
from time import monotonic
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp

from powernext.assembly.validate import validate_candidate
from powernext.contracts.models import Candidate, DomainError, Metrics
from powernext.physics.waveform import double_exponential, extract


def parameters(context, N, rf, rt):
    req = context.request
    hw = context.hardware
    if N < 1:
        raise DomainError(
            "invalid_stage_count", "Positive stage count required for formulas", "physics"
        )
    basic = hw["C_basic_F"] if req.setup.basic_capacitance_inclusion == "add_separately" else 0
    C2 = req.load.C_F + req.setup.divider_C_F + req.setup.stray_C_F + basic
    return {
        "C1_F": hw["C_stage_F"] / N,
        "C2_F": C2,
        "L_effective_H": req.setup.stray_L_H,
        "R1_ohm": N * rf + (req.setup.external_front_series_ohm or 0),
        "R2_ohm": N * rt,
        "V0_V": N * context.charge,
        "N": N,
        "topology": hw["topology"],
        "external_front_assumed_zero": req.setup.external_front_series_ohm is None,
    }


def inverse(context, N):
    req = context.request
    hw = context.hardware
    test = context.test
    p = parameters(context, N, 1, 1)
    c = hw["constants"]
    D = (test["front_s"] / c["k_front"]) ** 2 - c["k_LC"] * p["L_effective_H"] * p["C2_F"]
    if D <= 0:
        raise DomainError("inductance_limited_front", "No positive calculator inverse", "physics")
    rf = (math.sqrt(D) / p["C2_F"] - (req.setup.external_front_series_ohm or 0)) / N
    rt = test["tail_s"] / (c["k_tail"] * (p["C1_F"] + p["C2_F"])) / N
    if rf <= 0:
        raise DomainError(
            "external_front_limited", "No positive internal front resistance", "physics"
        )
    return {
        "N": N,
        "Rf_required_ohm": rf,
        "Rt_required_ohm": rt,
        "U_charge_V": context.charge,
        "derived": p,
        "inverse_mode": "calculator_seed",
        "topology": p["topology"],
    }


def calculator_metrics(context, N, rf, rt):
    if context.request.load.model_id != "capacitive_v1":
        raise DomainError(
            "unsupported_calculator_load", "Calculator supports capacitance only", "physics"
        )
    p = parameters(context, N, rf, rt)
    c = context.hardware["constants"]
    return Metrics(
        front_s=c["k_front"]
        * math.sqrt((p["R1_ohm"] * p["C2_F"]) ** 2 + c["k_LC"] * p["L_effective_H"] * p["C2_F"]),
        tail_s=c["k_tail"] * p["R2_ohm"] * (p["C1_F"] + p["C2_F"]),
        crest_V=context.request.expected_voltage_efficiency * p["V0_V"],
    )


def evaluate(context, candidate: Candidate, include_trace=True, deadline=None) -> dict[str, Any]:
    deadline = (
        deadline
        if deadline is not None
        else monotonic() + min(60, context.request.search.wall_time_seconds)
    )
    validate_candidate(context, candidate)
    req = context.request
    hw = context.hardware
    test = context.test
    N = candidate.N
    if N != candidate.proposal.N:
        raise DomainError("candidate_stage_mismatch", "Proposal/stages disagree", "physics")
    p = parameters(context, N, candidate.front.equivalent_ohm, candidate.tail.equivalent_ohm)
    C1, C2, R1, R2, L, V0 = (
        p[k] for k in ["C1_F", "C2_F", "R1_ohm", "R2_ohm", "L_effective_H", "V0_V"]
    )
    E = 0.5 * hw["C_stage_F"] * candidate.U_charge_V**2
    landmarks = {}
    rates = {}
    v1_values = None
    i_values = None
    time = None
    voltage = None
    if req.physics_mode == "calculator":
        if req.load.model_id != "capacitive_v1":
            raise DomainError(
                "unsupported_calculator_load", "Calculator supports capacitance only", "physics"
            )
        metrics = calculator_metrics(
            context, N, candidate.front.equivalent_ohm, candidate.tail.equivalent_ohm
        )
        diagnostics = {
            "method": "calculator",
            "trace_available": False,
            "crest_is_efficiency_assumption": True,
        }
    else:
        horizon = max(test["tail_s"] * 3, 10 * R2 * (C1 + C2))
        method = "analytic"
        fn: Callable[[Any], Any]
        states: Callable[[Any], Any]
        if req.load.model_id == "capacitive_v1" and L == 0:
            fn, rates = double_exponential(C1, C2, R1, R2, V0)

            def analytic_states(ts):
                v = fn(ts)
                a = rates["alpha_per_s"]
                b = rates["beta_per_s"]
                difference = b - a
                if difference <= 1e-12 * b:
                    current = V0 * np.exp(-a * ts) * (1 - a * ts) / R1
                else:
                    current = (
                        V0
                        * np.exp(-a * ts)
                        * (
                            -a * (-np.expm1(-difference * ts))
                            + difference * np.exp(-difference * ts)
                        )
                        / (R1 * difference)
                    )
                return v + R1 * current, current, v

            states = analytic_states
        else:
            method = "Radau"
            has_loop = L > 0
            has_load_L = req.load.model_id == "parallel_rlc_v1"

            # Scaled voltages and branch currents per erected volt.
            def rhs(t, y):
                if monotonic() >= deadline:
                    raise DomainError(
                        "physics_wall_time_budget",
                        "Numerical evaluation exceeded its deadline",
                        "physics",
                    )
                vg = y[0]
                vl = y[1]
                idx = 2
                loop = y[idx] if has_loop else (vg - vl) / R1
                idx += int(has_loop)
                il = y[idx] if has_load_L else 0
                leak = vl / req.load.R_ohm if req.load.R_ohm else 0
                dy = [(-vg / R2 - loop) / C1, (loop - leak - il) / C2]
                if has_loop:
                    dy.append((vg - R1 * loop - vl) / L)
                if has_load_L:
                    dy.append(vl / req.load.L_H)
                return dy

            y0 = [1.0, 0.0] + ([0.0] if has_loop else []) + ([0.0] if has_load_L else [])
            sol = None
            for _ in range(5):
                if horizon / (test["front_s"] / 200) > 250000:
                    raise DomainError(
                        "physics_work_budget",
                        "Requested horizon exceeds 250000 maximum-step intervals",
                        "physics",
                    )
                sol = solve_ivp(
                    rhs,
                    (0, horizon),
                    y0,
                    method="Radau",
                    rtol=1e-9,
                    atol=1e-12,
                    dense_output=True,
                    max_step=test["front_s"] / 200,
                )
                if not sol.success:
                    raise DomainError("ode_failed", sol.message, "physics")
                if sol.y[1, -1] < 0.01 * np.max(sol.y[1]):
                    break
                horizon *= 2

            assert sol is not None and sol.sol is not None
            solution = sol.sol

            fn = lambda ts: V0 * solution(ts)[1]

            def ode_states(ts):
                ys = solution(ts)
                vg = V0 * ys[0]
                vl = V0 * ys[1]
                return vg, (V0 * ys[2] if has_loop else (vg - vl) / R1), vl

            states = ode_states

        metrics, landmarks = extract(fn, horizon, test["category"], test["front_s"])
        time = np.unique(
            np.concatenate(
                (
                    np.linspace(0, min(horizon, 10 * metrics.front_s), 500),
                    np.geomspace(max(metrics.front_s / 100, 1e-12), horizon, 1500),
                    list(landmarks.values()),
                )
            )
        )
        time = time[time >= 0]
        v1_values, i_values, voltage = states(time)
        diagnostics = {
            "method": method,
            "horizon_s": horizon,
            "trace_available": True,
            "rtol": 1e-9,
            "standard_compliance_verified": False,
            "energy_integration_truncated_at_horizon": True,
            "ringing_evaluator_verified": False,
        }
    from powernext.physics.stress import component_stresses

    stress = component_stresses(context, candidate, time, i_values, v1_values)
    return {
        "candidate_id": candidate.candidate_id,
        "context_hash": context.context_hash,
        "physics_version": "0.1.0",
        "baseline_mode": req.physics_mode,
        "derived": p,
        "metrics": metrics.model_dump(mode="json"),
        "voltage_efficiency": metrics.crest_V / V0,
        "voltage_utilisation": candidate.U_charge_V / hw["U_stage_max_V"],
        "stage_energy_J": E,
        "total_energy_J": N * E,
        "landmarks": landmarks,
        "rates": rates,
        "trace": {
            "time_s": time.tolist(),
            "voltage_V": np.asarray(voltage).tolist(),
            "origin": "physics",
        }
        if time is not None and include_trace
        else None,
        "component_stresses": stress["components"],
        "constraints": [],
        "constraint_owner": "calibration_pending",
        "diagnostics": diagnostics,
        "hardware_feasible": None,
    }
