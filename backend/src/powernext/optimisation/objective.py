import math

from powernext.contracts.models import DomainError


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
            "lower_limit": target[key] - allowed,
            "upper_limit": target[key] + allowed,
            "normalised_error": error,
            "within_tolerance": error <= 1,
        }
    S = max(normalised)
    weights = context.request.objective.weights
    J = sum(weights[r] * errors[r]["normalised_error"] for r in errors) / sum(weights.values())
    return {
        "errors": errors,
        "S": S,
        "J": J,
        "cost": S / (1 + S),
        "waveform_within_tolerance": S <= 1,
    }


class Archive:
    def __init__(self, secondary_preference="balanced", require_eligible=True):
        self.entries = {}
        self.secondary_preference = secondary_preference
        self.require_eligible = require_eligible

    def add(self, evaluation):
        if not evaluation.get("objective"):
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
                o["S"],
                o["J"],
                *ties,
                e["candidate_id"],
            )

        return sorted(self.entries.values(), key=key)[:3]
