import math
from typing import Any, cast

import numpy as np
from scipy.optimize import brentq

from powernext.contracts.models import DomainError


def shape(r, category):
    peak = -math.log(r) / (1 - r)

    def raw(t):
        return np.exp(-r * np.asarray(t)) * (-np.expm1(-(1 - r) * np.asarray(t)))

    maximum = float(raw(peak))

    def fn(t):
        return raw(t) / maximum

    t30 = float(cast(Any, brentq(lambda t: float(fn(t)) - 0.3, 0, peak)))
    t90 = float(cast(Any, brentq(lambda t: float(fn(t)) - 0.9, 0, peak)))
    hi = peak * 2
    while fn(hi) > 0.5:
        hi *= 2
    half = float(cast(Any, brentq(lambda t: float(fn(t)) - 0.5, peak, hi)))
    origin = t30 - 0.5 * (t90 - t30) if category == "Lightning" else 0
    front = 1.67 * (t90 - t30) if category == "Lightning" else peak
    return (
        front,
        half - origin,
        {"t30": t30, "t90": t90, "peak": peak, "half": half, "origin": origin},
        fn,
    )


def fit(metrics, category):
    if any(not math.isfinite(v) or v <= 0 for v in metrics.values()):
        raise DomainError("invalid_plot_metrics", "Positive finite metrics required", "plot")
    ratio = metrics["front_s"] / metrics["tail_s"]

    def residual(z):
        front, tail, *_ = shape(math.exp(z), category)
        return front / tail - ratio

    z = float(cast(Any, brentq(residual, math.log(1e-8), math.log(0.99999), xtol=1e-12)))
    r = math.exp(z)
    front, tail, marks, fn = shape(r, category)
    beta = front / metrics["front_s"]
    alpha = r * beta
    corrected = {"front_s": front / beta, "tail_s": tail / beta, "crest_V": metrics["crest_V"]}
    errors = {k: abs(corrected[k] - metrics[k]) / metrics[k] for k in metrics}
    if max(errors.values()) > 1e-4:
        raise DomainError(
            "reconstruction_metric_mismatch", "Curve fit does not reproduce metrics", "plot"
        )
    return {
        "alpha_per_s": alpha,
        "beta_per_s": beta,
        "desired_metrics": metrics,
        "reextracted_metrics": corrected,
        "relative_errors": errors,
        "landmarks": {k + "_s": v / beta for k, v in marks.items()},
    }, lambda t: metrics["crest_V"] * fn(beta * np.asarray(t))


def bundle(context, candidates, max_points=12000):
    test = context.test
    target = {
        "front_s": test["front_s"],
        "tail_s": test["tail_s"],
        "crest_V": context.request.target.crest_V,
    }
    definitions: list[dict[str, Any]] = [
        {"curve_id": "target", "origin": "target_reference", "metrics": target}
    ]
    for index, candidate in enumerate(candidates):
        definitions.append(
            {
                "curve_id": candidate["candidate_id"],
                "candidate_id": candidate["candidate_id"],
                "rank": index + 1,
                "origin": candidate.get("waveform_origin", "ml_parameter_reconstruction"),
                "metrics": candidate["correction"]["corrected_metrics"],
                "model_version": candidate["correction"]["model_version"],
            }
        )
    good = []
    failed = []
    for definition in definitions:
        try:
            fitted, fn = fit(definition["metrics"], test["category"])
            good.append((dict(**definition, fit=fitted, reconstruction_status="complete"), fn))
        except (ValueError, DomainError) as exc:
            failed.append(
                dict(**definition, reconstruction_status="failed", reason=str(exc), voltage_V=None)
            )
    if not good:
        return {
            "availability": "failed",
            "time_s": [],
            "curves": failed,
            "shortfall": 3 - len(candidates),
        }
    horizon = 3 * max(c["metrics"]["tail_s"] for c, _ in good)
    for _ in range(20):
        if all(fn(horizon) < 0.01 * c["metrics"]["crest_V"] for c, fn in good):
            break
        horizon *= 2
    min_front = min(c["metrics"]["front_s"] for c, _ in good)
    zoom = min(horizon, 10 * max(c["metrics"]["front_s"] for c, _ in good))
    front_count = min(max_points // 2, max(500, math.ceil(zoom / (min_front / 200))))
    times = np.unique(
        np.concatenate(
            (
                np.linspace(0, zoom, front_count),
                np.geomspace(max(min_front / 1000, 1e-12), horizon, max_points // 2),
                [v for c, _ in good for k, v in c["fit"]["landmarks"].items() if k != "origin_s"],
            )
        )
    )
    curves = []
    for c, fn in good:
        values = fn(times)
        curves.append(
            {
                **c,
                "voltage_V": values.tolist(),
                "legend": "Target reference"
                if c["origin"] == "target_reference"
                else f"Candidate {c['rank']} — reconstruction from ML-corrected parameters",
            }
        )
    return {
        "bundle_id": context.context_id + "-waveforms",
        "context_id": context.context_id,
        "time_s": times.tolist(),
        "units": {"time": "s", "voltage": "V"},
        "time_origin": "impulse_start",
        "curves": curves + failed,
        "availability": "partial" if failed else "complete",
        "shortfall": 3 - len(candidates),
        "sampling": {
            "point_count": len(times),
            "horizon_s": horizon,
            "front_grid_step_s": zoom / (front_count - 1),
            "resolution_cap_limited": (
                front_count == max_points // 2 and zoom / (front_count - 1) > min_front / 200
            ),
        },
        "plot_views": {
            "overlay": [c["curve_id"] for c in definitions],
            "comparison_pairs": [
                ["target", c["candidate_id"]] for c in definitions if "candidate_id" in c
            ],
            "front_zoom_s": [0, zoom],
            "full_domain_s": [0, horizon],
        },
    }
