import pickle

import numpy as np
import pytest
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import Ridge

from powernext.correction.features import TARGETS
from powernext.correction.scaling import (
    scaling_manifest,
    scaling_trace,
    standardised_regressor,
)


def test_training_only_scaling_and_inverse_predictions_across_units():
    x = np.array([[1e6, 1e-9], [2e6, 2e-9], [3e6, 3e-9]])
    y = np.array([[1e-9, 1e-6, 1000], [2e-9, 2e-6, 2000], [3e-9, 3e-6, 3000]])
    models = [standardised_regressor(DummyRegressor()).fit(x, y[:, i]) for i in range(3)]
    stats = scaling_manifest(models, ["voltage", "capacitance"], TARGETS, 3)
    assert stats["fit_split"] == "Train" and stats["fit_count"] == 3
    assert stats["features"]["capacitance"]["scale"] == pytest.approx(np.std(x[:, 1]), abs=1e-20)
    for i, model in enumerate(models):
        assert np.allclose(model.regressor_.named_steps["features"].transform(x).mean(0), 0)
        assert np.allclose(model.regressor_.named_steps["features"].transform(x).std(0), 1)
        assert np.allclose(model.transformer_.transform(y[:, i : i + 1]).std(0), 1)
        # A far-out inference row must not refit scalers or clip to the training range.
        prediction = pickle.loads(pickle.dumps(model)).predict([[1e9, 1e-6]])[0]
        assert prediction == pytest.approx(y[:, i].mean(), abs=1e-20)
    raw = dict(zip(TARGETS, y.mean(0)))
    trace = scaling_trace(
        {"standardisation": stats}, {"voltage": 1e9, "capacitance": 1e-6}, list(raw.values())
    )
    assert trace["standardised_features"]["voltage"] > 100
    assert np.allclose(list(trace["standardised_residuals"].values()), 0)


def test_unit_conversion_does_not_change_the_standardised_learning_problem():
    x = np.arange(30, dtype=float).reshape(10, 3) + 1
    y = x[:, 0] * 2 + x[:, 1] * 3
    first = standardised_regressor(Ridge()).fit(x, y)
    # volts->kV, seconds->microseconds, farads->pF; targets also change units.
    conversions = np.array([1e-3, 1e6, 1e12])
    second = standardised_regressor(Ridge()).fit(x * conversions, y * 1e-6)
    assert np.allclose(first.predict(x), second.predict(x * conversions) * 1e6)


def test_constant_residual_target_remains_finite():
    model = standardised_regressor(DummyRegressor()).fit([[1], [2], [3]], [1e-9] * 3)
    assert model.transformer_.scale_[0] == 1
    assert model.predict([[4]])[0] == pytest.approx(1e-9, abs=1e-20)


def test_explanations_preserve_tiny_timing_contributions(context, tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    from powernext.assembly.cp_sat import AssemblyEngine
    from powernext.contracts.models import Proposal
    from powernext.correction.model import ResidualModel
    from powernext.physics.forward import evaluate

    x = np.array([[8], [9], [10]], float)
    scales = [1e-12, 1e-9, 1000]
    models = [standardised_regressor(Ridge(alpha=0)).fit(x, np.arange(1, 4) * s) for s in scales]
    model = ResidualModel(tmp_path)
    model.models["Lightning"] = models
    model.manifests["Lightning"] = {
        "baseline_mode": "calculator",
        "baseline_profile": "workbook_benchmark_v1",
        "feature_ranges": {"N": [8, 10]},
        "selected_features": ["N"],
        "unavailable": [],
        "standardisation": scaling_manifest(models, ["N"], TARGETS, 3),
    }
    np.save(tmp_path / "Lightning_background.npy", x[:1])

    class CutoffExplainer:
        def __init__(self, predict, background):
            self.predict = predict
            self.expected_value = float(predict(background)[0])
            assert 0.1 < abs(self.expected_value) < 5

        def shap_values(self, values, **kwargs):
            phi = (self.predict(values) - self.expected_value).reshape(-1, 1)
            # Reproduce SHAP's numerical cutoff, independent of the physical output unit.
            phi[np.abs(phi) < 1e-10] = 0
            return phi

    monkeypatch.setitem(sys.modules, "shap", SimpleNamespace(KernelExplainer=CutoffExplainer))
    candidate, _ = AssemblyEngine().realise(
        context, Proposal(N=9, Rf_required_ohm=50, Rt_required_ohm=25)
    )
    explanation = model.explain(context, candidate, evaluate(context, candidate, False))
    for output, scale in zip(explanation["outputs"], scales):
        assert output["feature_contributions"][0]["contribution"] == pytest.approx(scale, abs=1e-22)
        assert output["additivity_error"] < max(1e-22, scale * 1e-12)
