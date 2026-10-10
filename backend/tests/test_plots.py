import numpy as np
import pytest

from powernext.physics.plot_reconstruction import bundle, fit


@pytest.mark.parametrize(
    "category,front,tail", [("Lightning", 1.2e-6, 50e-6), ("Switching", 250e-6, 2500e-6)]
)
def test_shape_reextracts_metrics(category, front, tail):
    record, fn = fit({"front_s": front, "tail_s": tail, "crest_V": 1425000}, category)
    assert max(record["relative_errors"].values()) < 1e-8
    assert fn(record["landmarks"]["peak_s"]) == pytest.approx(1425000)


def test_three_curves_and_target(context):
    candidates = [
        {
            "candidate_id": str(i),
            "correction": {
                "model_version": "mock",
                "corrected_metrics": {
                    "front_s": 1.2e-6 + i * 1e-8,
                    "tail_s": 50e-6 + i * 1e-7,
                    "crest_V": 1425000,
                },
            },
        }
        for i in range(3)
    ]
    result = bundle(context, candidates)
    assert len(result["curves"]) == 4
    assert len(result["plot_views"]["comparison_pairs"]) == 3
    assert all(len(c["voltage_V"]) == len(result["time_s"]) for c in result["curves"])
    assert (np.diff(result["time_s"]) > 0).all()
    assert result["curves"][1]["origin"] == "ml_parameter_reconstruction"


def test_target_only(context):
    result = bundle(context, [])
    assert len(result["curves"]) == 1
    assert result["shortfall"] == 3
