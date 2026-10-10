"""Linear resistor thermal RC response to a periodic, piecewise-linear pulse."""

import math

import numpy as np

from powernext.contracts.models import DomainError


def thermal_response(time_s, power_W, ambient_K, R_theta, C_theta, period_s):
    times = np.asarray(time_s, dtype=float)
    power = np.asarray(power_W, dtype=float)
    if (
        len(times) < 2
        or times.shape != power.shape
        or times[0] != 0
        or not np.all(np.diff(times) > 0)
        or times[-1] > period_s
        or not np.all(np.isfinite(power))
        or np.any(power < 0)
        or min(ambient_K, R_theta, C_theta, period_s) <= 0
    ):
        raise DomainError(
            "invalid_thermal_input", "Invalid periodic pulse or thermal parameters", "physics"
        )
    tau = R_theta * C_theta

    def integrate(initial):
        rise = [initial]
        for a, b, p0, p1 in zip(times[:-1], times[1:], power[:-1], power[1:]):
            dt = b - a
            one_minus_decay = -math.expm1(-dt / tau)
            x = dt / tau
            ramp_integral = (
                tau * x * x * (0.5 - x / 6 + x * x / 24 - x**3 / 120)
                if x < 1e-4
                else dt - tau * one_minus_decay
            )
            slope = (p1 - p0) / dt
            rise.append(
                rise[-1] * (1 - one_minus_decay)
                + R_theta * (p0 * one_minus_decay + slope * ramp_integral)
            )
        return np.asarray(rise)

    single = integrate(0.0)
    decay_rest = math.exp(-(period_s - times[-1]) / tau)
    start = single[-1] * decay_rest / (-math.expm1(-period_s / tau))
    steady = integrate(start)
    return {
        "method": "linear_thermal_RC_periodic_steady_state",
        "thermal_time_constant_s": tau,
        "period_s": period_s,
        "initial_temperature_K": ambient_K + start,
        "estimated_peak_temperature_K": ambient_K + float(steady.max()),
        "single_pulse_adiabatic_upper_temperature_K": ambient_K
        + float(np.trapezoid(power, times)) / C_theta,
        "temperature_K": (ambient_K + steady).tolist(),
        "assumptions": [
            "supplied R_theta/C_theta",
            "periodic identical pulses",
            "zero heating outside trace horizon",
            "constant ambient",
            "linear thermal parameters",
        ],
        "experimentally_validated": False,
    }
