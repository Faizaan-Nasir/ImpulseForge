"""Training/validation-only comparisons; hidden test is never evaluated here."""

import hashlib
import importlib.metadata
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from powernext.correction.features import TARGETS
from powernext.profiles.registry import DOCS, digest, equipment


def file_hash(path):
    with Path(path).open("rb") as stream:
        value = hashlib.file_digest(stream, "sha256")
    return value.hexdigest()


def validation_report(frame, X, Y, category, selected, models):
    train = (frame.Impulse_Type == category) & (frame.Split == "Train")
    valid = (frame.Impulse_Type == category) & (frame.Split == "Validation")
    train_x = X.loc[train, selected].to_numpy()
    valid_x = X.loc[valid, selected].to_numpy()
    results = {}
    for name, model in zip(TARGETS, models):
        train_y = Y.loc[train, name].to_numpy()
        actual = Y.loc[valid, name].to_numpy()
        prediction = model.predict(valid_x)
        linear = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(train_x, train_y)
        units = "V" if name.endswith("V") else "s"
        residual_errors = prediction - actual
        results[name] = {
            "unit": units,
            "validation_count": len(actual),
            "validation_MAE": float(np.abs(residual_errors).mean()),
            "validation_RMSE": float(np.sqrt(np.mean(residual_errors**2))),
            "validation_bias": float(np.mean(residual_errors)),
            "validation_MAE_over_train_residual_std": float(
                np.abs(residual_errors).mean() / max(np.std(train_y), 1e-20)
            ),
            "physics_only_MAE": float(np.abs(actual).mean()),
            "mean_residual_baseline_MAE": float(np.abs(actual - train_y.mean()).mean()),
            "linear_residual_baseline_MAE": float(np.abs(actual - linear.predict(valid_x)).mean()),
        }
    return results


def artifact_metadata(directory, category, models, manifest):
    checkpoint = Path(models[0].model_path)
    return {
        "checkpoint_version": "v2",
        "checkpoint_filename": checkpoint.name,
        "checkpoint_sha256": file_hash(checkpoint),
        "artifact_sha256": file_hash(directory / f"{category}.pkl"),
        "background_sha256": file_hash(directory / f"{category}_background.npy"),
        "dataset_sha256": file_hash(DOCS / "Hybrid_Physics_ML_Impulse_Generator_Optimiser.xlsx"),
        "feature_manifest_hash": digest(
            {"features": manifest["selected_features"], "units": manifest["target_units"]}
        ),
        "baseline_profile_hash": digest(equipment("workbook_benchmark_v1")),
        "package_versions": {
            name: importlib.metadata.version(name)
            for name in ("tabpfn", "torch", "numpy", "scikit-learn")
        },
        "device": "cpu",
        "seed": 42,
        "n_estimators": 2,
        "hidden_test_evaluated": False,
    }
