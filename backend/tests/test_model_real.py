from pathlib import Path

import numpy as np
import pytest

from powernext.assembly.cp_sat import AssemblyEngine
from powernext.correction.data import workbook_fixture
from powernext.correction.model import ResidualModel
from powernext.physics.forward import evaluate
from powernext.profiles.resolve import resolve

MODEL_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "models"


@pytest.mark.model
@pytest.mark.parametrize("category", ["Lightning", "Switching"])
def test_real_v2_residual_models(category):
    if not (MODEL_DIR / f"{category}.pkl").exists():
        pytest.skip("Local TabPFN v2 fitted artifact unavailable; run python -m powernext fit")
    model = ResidualModel(MODEL_DIR)
    request, proposal = workbook_fixture(category)
    context = resolve(request, model_bundle_hash=model.fingerprint)
    candidate, _ = AssemblyEngine().realise(context, proposal)
    physics = evaluate(context, candidate)
    result = model.correct(context, candidate, physics)
    assert result["status"] == "predicted_diagnostic"
    assert not result["lab_validated"]
    assert np.allclose(
        list(result["corrected_metrics"].values()),
        np.array(list(physics["metrics"].values())) + np.array(list(result["residuals"].values())),
    )
    assert model.manifests[category]["checkpoint_filename"] == "tabpfn-v2-regressor.ckpt"
    assert not model.manifests[category]["hidden_test_evaluated"]
    from powernext.correction.features import workbook_data

    frame, X, Y = workbook_data()
    train = (frame.Impulse_Type == category) & (frame.Split == "Train")
    stats = model.manifests[category]["standardisation"]
    assert stats["fit_count"] == 700 and stats["fit_split"] == "Train"
    for name, p in stats["features"].items():
        assert p["mean"] == pytest.approx(X.loc[train, name].mean(), abs=1e-20)
        assert p["scale"] == pytest.approx(X.loc[train, name].std(ddof=0), abs=1e-20)
    for name, p in stats["targets"].items():
        assert p["mean"] == pytest.approx(Y.loc[train, name].mean(), abs=1e-20)
        assert result["residuals"][name] == pytest.approx(
            result["normalisation"]["standardised_residuals"][name] * p["scale"] + p["mean"],
            abs=1e-20,
        )


@pytest.mark.model
def test_out_of_domain_rejected():
    model = ResidualModel(MODEL_DIR)
    if not model.manifests:
        pytest.skip("Fitted models unavailable")
    request, _proposal = workbook_fixture()
    features = {f: lo for f, (lo, hi) in model.manifests["Lightning"]["feature_ranges"].items()}
    features["Rt_stage_actual_ohm"] = 25.01
    report = model.support(resolve(request), features, "Lightning")
    assert "feature_outside_training_envelope:Rt_stage_actual_ohm" in report["reasons"]
