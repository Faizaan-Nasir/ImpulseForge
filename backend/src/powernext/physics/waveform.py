import math
from typing import Any, cast

import numpy as np
from scipy.optimize import brentq, minimize_scalar

from powernext.contracts.models import DomainError, Metrics


def extract(function, horizon, category, front_hint=1e-6):
    grid = np.unique(
        np.concatenate(([0.0], np.geomspace(max(front_hint / 1000, 1e-12), horizon, 4000)))
    )
    values = np.asarray(function(grid))
    peak_index = int(np.argmax(values))
    if peak_index == len(grid) - 1 or values[peak_index] <= 0:
        raise DomainError("waveform_peak_unresolved", "No interior positive peak", "physics")
    lo = grid[max(0, peak_index - 1)]
    hi = grid[min(len(grid) - 1, peak_index + 1)]
    opt = minimize_scalar(
        lambda t: -float(function(t)), bounds=(lo, hi), method="bounded", options={"xatol": 1e-15}
    )
    tp = float(cast(Any, opt).x)
    vp = float(function(tp))

    def crossing(fraction, rising):
        xs = grid[grid < tp] if rising else grid[grid > tp]
        xs = np.concatenate((xs, [tp])) if rising else np.concatenate(([tp], xs))
        ys = np.asarray(function(xs)) - fraction * vp
        for a, b, va, vb in zip(xs[:-1], xs[1:], ys[:-1], ys[1:]):
            if va <= 0 <= vb if rising else va >= 0 >= vb:
                return float(
                    cast(
                        Any, brentq(lambda t: float(function(t)) - fraction * vp, a, b, xtol=1e-16)
                    )
                )
        raise DomainError("waveform_crossing_unresolved", f"No {fraction} crossing", "physics")

    t30 = crossing(0.3, True)
    t90 = crossing(0.9, True)
    t50 = crossing(0.5, False)
    origin = t30 - 0.5 * (t90 - t30) if category == "Lightning" else 0.0
    front = 1.67 * (t90 - t30) if category == "Lightning" else tp
    return Metrics(front_s=front, tail_s=t50 - origin, crest_V=vp), {
        "t30_s": t30,
        "t90_s": t90,
        "t_peak_s": tp,
        "t50_falling_s": t50,
        "virtual_origin_s": origin,
    }


def double_exponential(C1, C2, R1, R2, V0):
    a = 1 / (R1 * C1) + 1 / (R1 * C2) + 1 / (R2 * C1)
    b = 1 / (R1 * R2 * C1 * C2)
    discriminant = max(0.0, a * a - 4 * b)
    beta = (a + math.sqrt(discriminant)) / 2
    alpha = b / beta
    difference = beta - alpha

    def function(t):
        t = np.asarray(t)
        if difference <= 1e-12 * beta:
            return V0 * t * np.exp(-alpha * t) / (R1 * C2)
        return V0 * np.exp(-alpha * t) * (-np.expm1(-difference * t)) / (R1 * C2 * difference)

    return function, {"alpha_per_s": alpha, "beta_per_s": beta}
