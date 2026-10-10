import numpy as np

from powernext.correction.features import manifest, workbook_data
from powernext.correction.model import ResidualModel


def test_workbook_targets_and_splits():
    frame, X, Y = workbook_data()
    assert len(frame) == 2000
    assert X.shape == (2000, 16)
    assert Y.shape == (2000, 3)
    for category in ("Lightning", "Switching"):
        mf = manifest(frame, X, Y, category)
        assert (mf["train_count"], mf["validation_count"], mf["hidden_test_count"]) == (
            700,
            150,
            150,
        )
        assert not mf["epochs_applicable"]
        assert mf["epochs"] is None
        assert set(mf["features"]).isdisjoint({"ID", "Split", "Observed_Crest_kV"})
    assert "Rt_stage_actual_ohm" not in manifest(frame, X, Y, "Lightning")["selected_features"]


def test_missing_model_no_fake_prediction(context, tmp_path):
    model = ResidualModel(tmp_path)
    assert model.report()["status"] == "not_fitted"
    assert model.support(context, {}, "Lightning")["reasons"] == ["model_not_fitted"]


def test_residual_arithmetic():
    baseline = np.array([1.21e-6, 52.2e-6, 1425000])
    correction = np.array([-0.01e-6, -2.2e-6, -5000])
    assert np.allclose(baseline + correction, [1.2e-6, 50e-6, 1420000])


def test_changed_capacitance_is_not_silently_supported(request_data, tmp_path):
    from powernext.contracts.models import RunRequest
    from powernext.profiles.resolve import resolve

    request_data["equipment_inputs"] = {"C_stage_F": 2e-6}
    context = resolve(RunRequest.model_validate(request_data))
    model = ResidualModel(tmp_path)
    model.manifests["Lightning"] = {
        "baseline_mode": "calculator",
        "baseline_profile": "workbook_benchmark_v1",
        "feature_ranges": {},
    }
    result = model.support(context, {}, "Lightning")
    assert result["status"] == "unsupported"
    assert "stage_capacitance_unseen" in result["reasons"]


def test_diagnostic_extrapolation_is_actual_inference_and_environment_is_not_fabricated(
    request_data, tmp_path
):
    from powernext.assembly.cp_sat import AssemblyEngine
    from powernext.contracts.models import Proposal, RunRequest
    from powernext.physics.forward import evaluate
    from powernext.profiles.resolve import resolve

    request_data["ml_domain_policy"] = "diagnostic_extrapolation"
    request_data["environment"] = {
        "availability": "recorded",
        "values": {"ambient_temperature_K": 313.15},
    }
    ctx = resolve(RunRequest.model_validate(request_data))
    candidate, _ = AssemblyEngine().realise(
        ctx, Proposal(N=9, Rf_required_ohm=50, Rt_required_ohm=25)
    )
    baseline = evaluate(ctx, candidate, False)
    model = ResidualModel(tmp_path)
    model.manifests["Lightning"] = {
        "baseline_mode": "calculator",
        "baseline_profile": "workbook_benchmark_v1",
        "feature_ranges": {"Rt_stage_actual_ohm": [24, 24]},
        "selected_features": ["N"],
        "unavailable": ["environment"],
    }

    class Predictor:
        def predict(self, x):
            return np.zeros(len(x))

    model.models["Lightning"] = [Predictor(), Predictor(), Predictor()]
    result = model.correct(ctx, candidate, baseline)
    assert result["status"] == "predicted_extrapolation"
    assert result["support"]["status"] == "extrapolated_diagnostic"
    assert result["support"]["reasons"] == ["feature_outside_training_envelope:Rt_stage_actual_ohm"]
    assert result["corrected_metrics"] == baseline["metrics"]
    assert result["environment_effects"]["status"] == "not_modelled"
    assert result["environment_effects"]["requested_conditions"] == {
        "ambient_temperature_K": 313.15
    }
    request_data["ml_domain_policy"] = "strict"
    strict = model.correct(resolve(RunRequest.model_validate(request_data)), candidate, baseline)
    assert strict["status"] == "unsupported" and strict["corrected_metrics"] is None
    request_data["ml_domain_policy"] = "diagnostic_extrapolation"
    request_data["physics_mode"] = "exact"
    incompatible = model.correct(
        resolve(RunRequest.model_validate(request_data)), candidate, baseline
    )
    assert incompatible["status"] == "unsupported" and incompatible["corrected_metrics"] is None
