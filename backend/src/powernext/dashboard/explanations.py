"""Cached SHAP evidence for the exact prediction saved with a candidate."""

import logging
import math
from threading import Lock
from time import monotonic

from powernext.contracts.models import Candidate, DomainError
from powernext.profiles.registry import digest

logger = logging.getLogger(__name__)
EXPLANATION_POLICY = "saved-residual-shap-v1"


class ExplanationService:
    def __init__(self, store, model):
        self.store = store
        self.model = model
        self.lock = Lock()

    def explain(self, context, record):
        metrics = record.get("correction", {}).get("corrected_metrics")
        if not metrics:
            return {"status": "unavailable", "reason": "no_saved_ml_prediction"}
        identity = digest(
            {
                "policy": EXPLANATION_POLICY,
                "context": context.context_hash,
                "candidate": record["candidate_id"],
                "model": self.model.fingerprint,
                "saved_metrics": metrics,
                "physics_metrics": record["physics"]["metrics"],
            }
        )
        with self.lock:
            saved = self.store.get("candidate_explanation", identity)
            if saved:
                return {**saved, "cached": True}
            started = monotonic()
            try:
                candidate = Candidate.model_validate(record["candidate"])
                if candidate.context_hash != context.context_hash:
                    raise DomainError(
                        "candidate_context_mismatch", "Candidate context changed", "explanation"
                    )
                raw = self.model.explain(context, candidate, record["physics"])
                if raw.get("status") != "complete":
                    return raw
                by_name = {o["output_name"]: o for o in raw["outputs"]}
                for key in ("front_s", "tail_s", "crest_V"):
                    output = by_name["residual_" + key]
                    contributions = [f["contribution"] for f in output["feature_contributions"]]
                    residual = metrics[key] - record["physics"]["metrics"][key]
                    reference = output["reference_residual"]
                    tolerance = max(
                        1e-7 if key == "crest_V" else 1e-18,
                        max(abs(residual), abs(reference), sum(map(abs, contributions))) * 1e-6,
                    )
                    if not all(math.isfinite(v) for v in [reference, residual, *contributions]):
                        raise DomainError(
                            "invalid_shap_values", "Nonfinite SHAP evidence", "explanation"
                        )
                    if abs(residual - reference - sum(contributions)) > tolerance:
                        raise DomainError(
                            "shap_saved_prediction_mismatch",
                            "Attributions do not reconstruct the saved prediction",
                            "explanation",
                        )
                    output.update(
                        saved_residual=residual,
                        reconstructed_residual=reference + sum(contributions),
                        saved_prediction_additivity_error=abs(
                            residual - reference - sum(contributions)
                        ),
                        additivity_tolerance=tolerance,
                        additivity_verified=True,
                    )
                result = {
                    **raw,
                    "cached": False,
                    "evidence_hash": identity,
                    "policy": EXPLANATION_POLICY,
                    "model_bundle_hash": self.model.fingerprint,
                    "background_count": raw.get("background_count"),
                    "generation_seconds": monotonic() - started,
                    "prediction_origin": "saved_ml_corrected_metrics",
                }
                self.store.save("candidate_explanation", identity, result)
                return result
            except DomainError as exc:
                return {"status": "unavailable", "reason": exc.code}
            except Exception:
                logger.exception("SHAP computation failed for candidate %s", record["candidate_id"])
                return {"status": "unavailable", "reason": "shap_computation_failed"}
