import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np

from powernext.contracts.models import MODEL_VERSION, DomainError
from powernext.correction.features import TARGETS, extract_features, manifest, workbook_data
from powernext.correction.scaling import scaling_manifest, scaling_trace, standardised_regressor
from powernext.correction.validation import artifact_metadata, file_hash, validation_report
from powernext.profiles.registry import digest


class ResidualModel:
    def __init__(self, model_dir):
        self.directory = Path(model_dir)
        self.models = {}
        self.manifests = {}
        for category in ("Lightning", "Switching"):
            path = self.directory / f"{category}.json"
            if path.exists():
                self.manifests[category] = json.loads(path.read_text())

    @property
    def fingerprint(self):
        return digest(self.manifests)

    def report(self):
        return {
            "model_version": MODEL_VERSION,
            "checkpoint_version": "v2",
            "bundle_hash": self.fingerprint,
            "status": "fitted" if self.manifests else "not_fitted",
            "categories": self.manifests,
            "lab_validated": False,
            "training_mode": "pretrained_in_context",
            "epochs_applicable": False,
        }

    def support(self, context, features, category) -> dict[str, Any]:
        mf = self.manifests.get(category)
        if not mf:
            return {"status": "unsupported", "reasons": ["model_not_fitted"]}
        reasons = []
        if (
            context.request.physics_mode != mf["baseline_mode"]
            or context.request.equipment_profile_id != mf["baseline_profile"]
        ):
            reasons.append("baseline_profile_or_mode_mismatch")
        if context.request.load.model_id != "capacitive_v1":
            reasons.append("load_model_unseen")
        if context.hardware["C_stage_F"] != 3e-6:
            reasons.append("stage_capacitance_unseen")
        for f, (lo, hi) in mf["feature_ranges"].items():
            v = features[f]
            eps = max(abs(lo), abs(hi), 1e-15) * 1e-10
            if v < lo - eps or v > hi + eps:
                reasons.append("feature_outside_training_envelope:" + f)
        return {
            "status": "supported_diagnostic" if not reasons else "unsupported",
            "reasons": reasons,
            "joint_domain_validated": False,
            "lab_validated": False,
        }

    def _load(self, category):
        if category not in self.models:
            if self.manifests[category].get("model_version") != MODEL_VERSION:
                raise DomainError(
                    "model_artifact_version_mismatch",
                    "Refit the residual model for the current standardisation contract",
                    "correction",
                )
            import torch

            torch.set_num_threads(2)
            expected = self.manifests[category].get("artifact_sha256")
            if expected is not None and file_hash(self.directory / f"{category}.pkl") != expected:
                raise DomainError(
                    "model_artifact_hash_mismatch",
                    "Model artifact does not match manifest",
                    "correction",
                )
            # Only this service's own locally produced model artifacts may be loaded.
            with (self.directory / f"{category}.pkl").open("rb") as stream:
                self.models[category] = pickle.load(stream)
        return self.models[category]

    def correct(self, context, candidate, baseline) -> dict[str, Any]:
        if context.request.model_version != self.report()["model_version"]:
            raise DomainError("unknown_model_version", context.request.model_version, "correction")
        frozen_hash = context.data.get("model_bundle_hash")
        if frozen_hash is not None and frozen_hash != self.fingerprint:
            raise DomainError(
                "model_artifact_changed", "Model changed after context resolution", "correction"
            )
        category = context.test["category"]
        features = extract_features(context, candidate, baseline)
        support = self.support(context, features, category)
        environment_effects = {
            "status": "not_modelled",
            "requested_conditions": context.request.environment.values,
            "reason": "Current synthetic training data has no environmental measurements or labels",
        }
        if support["status"] == "unsupported" and (
            context.request.purpose == "diagnostic"
            and context.request.ml_domain_policy == "diagnostic_extrapolation"
            and support["reasons"]
            and all(
                reason.startswith("feature_outside_training_envelope:")
                or reason == "stage_capacitance_unseen"
                for reason in support["reasons"]
            )
        ):
            support = {**support, "status": "extrapolated_diagnostic", "prediction_trusted": False}
        if support["status"] == "unsupported":
            return {
                "model_version": context.request.model_version,
                "support": support,
                "features": features,
                "input_effects_not_modelled": self.manifests.get(category, {}).get(
                    "unavailable", ["model not fitted"]
                ),
                "hardware_feasible": None,
                "physics_constraints": [],
                "residuals": None,
                "corrected_metrics": None,
                "status": "unsupported",
                "lab_validated": False,
                "environment_effects": environment_effects,
                "normalisation": {"status": "not_invoked", "reason": "unsupported_model_domain"},
            }
        mf = self.manifests[category]
        models = self._load(category)
        x = np.array([[features[f] for f in mf["selected_features"]]])
        residual = np.array([model.predict(x)[0] for model in models], float)
        values = (
            np.array([baseline["metrics"][k] for k in ("front_s", "tail_s", "crest_V")]) + residual
        )
        if not np.isfinite(values).all() or (values <= 0).any():
            raise DomainError(
                "invalid_corrected_prediction",
                "Corrected values must be positive finite",
                "correction",
            )
        return {
            "corrected_constraint_checks": [],
            "model_version": context.request.model_version,
            "support": support,
            "features": features,
            "input_effects_not_modelled": mf["unavailable"],
            "hardware_feasible": None,
            "physics_constraints": [],
            "residuals": dict(zip(TARGETS, residual.tolist())),
            "corrected_metrics": dict(zip(("front_s", "tail_s", "crest_V"), values.tolist())),
            "status": "predicted_extrapolation"
            if support["status"] == "extrapolated_diagnostic"
            else "predicted_diagnostic",
            "lab_validated": False,
            "explanation_status": "available_on_request",
            "environment_effects": environment_effects,
            "normalisation": scaling_trace(mf, features, residual),
        }

    def explain(self, context, candidate, baseline):
        correction = self.correct(context, candidate, baseline)
        if correction["corrected_metrics"] is None:
            return {"status": "unavailable", "reason": correction["support"]}
        import shap

        category = context.test["category"]
        mf = self.manifests[category]
        models = self._load(category)
        background = np.load(self.directory / f"{category}_background.npy")
        values = np.array([[correction["features"][f] for f in mf["selected_features"]]])
        explanations = []
        for name, model in zip(TARGETS, models):
            scaler = model.regressor_.named_steps["features"]
            estimator = model.regressor_.named_steps["regressor"]
            target_scaler = model.transformer_

            # Dimensionless inputs/outputs avoid SHAP's absolute cutoffs for tiny SI quantities.
            z_values = scaler.transform(values)
            explainer = shap.KernelExplainer(estimator.predict, scaler.transform(background))
            sv_z = np.asarray(explainer.shap_values(z_values, nsamples=32, silent=True, l1_reg=0))
            sv = sv_z * target_scaler.scale_[0]
            ref = float(explainer.expected_value * target_scaler.scale_[0] + target_scaler.mean_[0])
            pred = float(model.predict(values)[0])
            explanations.append(
                {
                    "output_name": name,
                    "reference_residual": ref,
                    "feature_contributions": [
                        {
                            "feature": f,
                            "value": float(v),
                            "standardised_value": float(z),
                            "contribution": float(c),
                        }
                        for f, v, z, c in zip(
                            mf["selected_features"], values[0], z_values[0], sv[0]
                        )
                    ],
                    "additivity_error": abs(pred - ref - float(sv.sum())),
                    "method": "Kernel SHAP",
                    "masking_space": "training-standardised features",
                    "attribution_space": "standardised residual; contributions inverse-scaled to SI",
                    "contribution_unit": "V" if name.endswith("V") else "s",
                    "nsamples": 32,
                    "unsupported_effects": mf["unavailable"],
                    "causal_claim": False,
                }
            )
        return {
            "status": "complete",
            "outputs": explanations,
            "background_count": len(background),
            "background_source": "saved sample of training rows only",
            "physical_evidence": baseline["component_stresses"],
        }


def fit_workbook(directory, device="cpu"):
    import torch
    from tabpfn import TabPFNRegressor
    from tabpfn.constants import ModelVersion

    torch.set_num_threads(2)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    frame, X, Y = workbook_data()
    reports = {}
    for category in ("Lightning", "Switching"):
        mf = manifest(frame, X, Y, category)
        train = (frame.Impulse_Type == category) & (frame.Split == "Train")
        validation = (frame.Impulse_Type == category) & (frame.Split == "Validation")
        models = []
        metrics = {}
        for target in TARGETS:
            model = standardised_regressor(
                TabPFNRegressor.create_default_for_version(
                    ModelVersion.V2, device=device, n_estimators=2, random_state=42
                )
            )
            model.fit(
                X.loc[train, mf["selected_features"]].to_numpy(), Y.loc[train, target].to_numpy()
            )
            prediction = model.predict(X.loc[validation, mf["selected_features"]].to_numpy())
            actual = Y.loc[validation, target].to_numpy()
            metrics[target] = {
                "validation_MAE": float(np.abs(prediction - actual).mean()),
                "mean_residual_baseline_MAE": float(
                    np.abs(actual - Y.loc[train, target].mean()).mean()
                ),
            }
            models.append(model)
        mf["standardisation"] = scaling_manifest(
            models, mf["selected_features"], TARGETS, mf["train_count"]
        )
        mf["model_version"] = MODEL_VERSION
        mf["validation_metrics"] = validation_report(
            frame, X, Y, category, mf["selected_features"], models
        )
        reports[category] = mf
        with (directory / f"{category}.pkl").open("wb") as stream:
            pickle.dump(models, stream)
        np.save(
            directory / f"{category}_background.npy",
            X.loc[train, mf["selected_features"]].sample(8, random_state=42).to_numpy(),
        )
        mf.update(artifact_metadata(directory, category, models, mf))
        mf["device"] = device
        (directory / f"{category}.json").write_text(json.dumps(mf, indent=2))
    return reports
