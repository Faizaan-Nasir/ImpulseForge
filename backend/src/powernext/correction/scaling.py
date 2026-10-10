"""Training-only standardisation; callers and explanations retain physical SI units."""

import numpy as np
from sklearn.compose import TransformedTargetRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def standardised_regressor(estimator):
    return TransformedTargetRegressor(
        regressor=Pipeline([("features", StandardScaler()), ("regressor", estimator)]),
        transformer=StandardScaler(),
    )


def scaling_manifest(models, features, targets, train_count):
    feature_scaler = models[0].regressor_.named_steps["features"]
    return {
        "method": "z_score",
        "formula": "z = (value - training_mean) / training_scale",
        "inverse_formula": "value = z * training_scale + training_mean",
        "fit_split": "Train",
        "fit_count": train_count,
        "std_ddof": 0,
        "constant_scale": 1,
        "clip": False,
        "features": {
            name: {"mean": float(mean), "scale": float(scale)}
            for name, mean, scale in zip(features, feature_scaler.mean_, feature_scaler.scale_)
        },
        "targets": {
            name: {
                "mean": float(model.transformer_.mean_[0]),
                "scale": float(model.transformer_.scale_[0]),
                "unit": "V" if name.endswith("V") else "s",
            }
            for name, model in zip(targets, models)
        },
        "prediction_units": "SI; inverse target transformation applied before physics addition",
        "tabpfn_internal_preprocessing": "Retained; independent of this explicit outer transform",
    }


def scaling_trace(manifest, features, residuals=None):
    stats = manifest.get("standardisation")
    if not stats:
        return {"status": "not_available_for_this_artifact"}
    trace = {
        "status": "applied",
        "method": stats["method"],
        "fit_split": stats["fit_split"],
        "fit_count": stats["fit_count"],
        "standardised_features": {
            name: (features[name] - p["mean"]) / p["scale"] for name, p in stats["features"].items()
        },
        "target_parameters": stats["targets"],
        "prediction_units": stats["prediction_units"],
    }
    if residuals is not None:
        trace["standardised_residuals"] = {
            name: float((value - p["mean"]) / p["scale"])
            for (name, p), value in zip(stats["targets"].items(), np.asarray(residuals))
        }
    return trace
