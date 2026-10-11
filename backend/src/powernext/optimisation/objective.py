import math

from powernext.contracts.models import DomainError

OBJECTIVE_POLICY = "crest_no_shortfall_v1"


def objective_order(objective):
    """Respect the minimum crest before comparing remaining waveform deviations."""
    return (
        not objective["crest_minimum_satisfied"],
        objective["S"],
        objective["J"],
    )


def evaluate_objective(context, metrics):
    target = {
        "front_s": context.test["front_s"],
        "tail_s": context.test["tail_s"],
        "crest_V": context.request.target.crest_V,
    }
    errors = {}
    normalised = []
    for role, key in (("front", "front_s"), ("tail", "tail_s"), ("crest", "crest_V")):
        value = metrics[key]
        if not math.isfinite(value) or value <= 0:
            raise DomainError("invalid_prediction", "Positive finite metrics required", "objective")
        delta = value - target[key]
        allowed = context.test["tolerances"][role] * target[key]
        error = abs(delta) / allowed
        minimum_satisfied = role != "crest" or delta >= 0
        normalised.append(error)
        errors[role] = {
            "unit": "V" if role == "crest" else "s",
            "target": target[key],
            "predicted": value,
            "signed_delta": delta,
            "absolute_delta": abs(delta),
            "percentage_delta": 100 * delta / target[key],
            "absolute_percentage_delta": 100 * abs(delta) / target[key],
            "allowed_delta": allowed,
            "lower_limit": target[key] if role == "crest" else target[key] - allowed,
            "upper_limit": target[key] + allowed,
            "allowed_negative_delta": 0 if role == "crest" else allowed,
            "allowed_positive_delta": allowed,
            "normalised_error": error,
            "within_tolerance": minimum_satisfied and error <= 1,
            "reason_code": "crest_below_required" if not minimum_satisfied else None,
        }
    S = max(normalised)
    crest_minimum_satisfied = metrics["crest_V"] >= target["crest_V"]
    if not crest_minimum_satisfied:
        # Make even a small shortfall a failing score, while retaining a smooth
        # deficit signal for SMAC. Do not clamp or change the ML prediction.
        S = max(S, 1 + errors["crest"]["normalised_error"])
    weights = context.request.objective.weights
    J = sum(weights[r] * errors[r]["normalised_error"] for r in errors) / sum(weights.values())
    return {
        "acceptance_policy": OBJECTIVE_POLICY,
        "errors": errors,
        "S": S,
        "J": J,
        "cost": S / (1 + S),
        "crest_minimum_satisfied": crest_minimum_satisfied,
        "crest_shortfall_V": max(0, -errors["crest"]["signed_delta"]),
        "calibration_required": not all(e["within_tolerance"] for e in errors.values()),
        "waveform_within_tolerance": all(e["within_tolerance"] for e in errors.values()),
    }


class Archive:
    def __init__(
        self, secondary_preference="balanced", require_eligible=True, require_waveform=False
    ):
        self.entries = {}
        self.secondary_preference = secondary_preference
        self.require_eligible = require_eligible
        self.require_waveform = require_waveform

    def add(self, evaluation):
        if not evaluation.get("objective"):
            return False
        if self.require_waveform and not evaluation["objective"]["waveform_within_tolerance"]:
            return False
        if self.require_eligible and not evaluation["eligible"]:
            return False
        if not self.require_eligible and not evaluation.get("correction", {}).get(
            "corrected_metrics"
        ):
            return False
        before = [c["candidate_id"] for c in self.best()]
        self.entries[evaluation["candidate_id"]] = evaluation
        self.entries = {c["candidate_id"]: c for c in self.best()}
        return before != [c["candidate_id"] for c in self.best()]

    def best(self):
        def key(e):
            c = e["candidate"]
            o = e["objective"]
            parts = c["front"]["total_resistors"] + c["tail"]["total_resistors"]
            ties = {
                "balanced": (parts, c["N"], c["U_charge_V"]),
                "accuracy": (parts, c["N"], c["U_charge_V"]),
                "resistors": (parts, c["N"], c["U_charge_V"]),
                "stages": (c["N"], parts, c["U_charge_V"]),
                "voltage": (c["U_charge_V"], parts, c["N"]),
            }[self.secondary_preference]
            return (
                *objective_order(o),
                *ties,
                e["candidate_id"],
            )

        return sorted(self.entries.values(), key=key)[:3]
