import pytest
from fastapi.testclient import TestClient

from powernext.api.app import create_app
from powernext.assembly.cp_sat import AssemblyEngine
from powernext.contracts.models import DomainError, Proposal, RunRequest
from powernext.performance.metrics import build_report
from powernext.physics.forward import evaluate
from powernext.pipeline.runner import run
from powernext.pipeline.storage import Store
from powernext.profiles.resolve import resolve


def fixture_report(context, correction=None, observed=None):
    candidate, _ = AssemblyEngine().realise(
        context, Proposal(N=9, Rf_required_ohm=50, Rt_required_ohm=25)
    )
    physics = evaluate(context, candidate)
    return build_report(
        context,
        candidate,
        physics,
        correction or {"status": "not_invoked"},
        {
            "model_version": "fixture",
            "categories": {
                "Lightning": {
                    "train_count": 700,
                    "validation_count": 150,
                    "validation_metrics": {
                        "residual_crest_V": {"validation_MAE": 1234, "unit": "V"}
                    },
                }
            },
        },
        {"scope": "test", "stage_seconds": {"physics": 0.01}, "total_seconds": 0.02},
        observed,
        "fixture_observation" if observed else None,
    )


def test_target_deviation_efficiency_energy_and_no_invented_accuracy(context):
    predicted = {"front_s": 1.26e-6, "tail_s": 49e-6, "crest_V": 1420000}
    report = fixture_report(
        context, {"status": "predicted_diagnostic", "corrected_metrics": predicted}
    )
    front = report["corrected"]["errors"]["front"]
    assert front["signed_delta"] == pytest.approx(0.06e-6)
    assert front["absolute_percentage_delta"] == pytest.approx(5)
    assert front["normalised_error"] == pytest.approx(1 / 6)
    assert front["lower_limit"] == pytest.approx(0.84e-6)
    assert front["upper_limit"] == pytest.approx(1.56e-6)
    assert front["unit"] == "s"
    assert report["corrected"]["errors"]["crest"]["unit"] == "V"
    assert report["efficiency"]["corrected_voltage_transfer"] == pytest.approx(
        1420000 / (1425000 / 0.82)
    )
    assert report["stored_energy"]["stage_utilisation"] > 1
    assert "HW_STAGE_ENERGY" in report["hardware"]["failed_constraint_ids"]
    assert not report["hardware"]["feasible"]
    assert report["observed_accuracy"]["status"] == "unavailable"
    assert report["model_quality"]["validation_count"] == 150
    assert report["model_quality"]["metrics"]["residual_crest_V"]["validation_MAE"] == 1234


def test_observed_accuracy_is_separate_from_target_error(context):
    prediction = {"front_s": 1.2e-6, "tail_s": 50e-6, "crest_V": 1425000}
    observed = {"front_s": 1.3e-6, "tail_s": 52e-6, "crest_V": 1400000}
    report = fixture_report(
        context, {"status": "predicted", "corrected_metrics": prediction}, observed
    )
    assert report["corrected"]["S"] == 0
    accuracy = report["observed_accuracy"]
    assert accuracy["errors"]["crest_V"]["signed_error"] == 25000
    assert accuracy["errors"]["front_s"]["absolute_error"] == pytest.approx(0.1e-6)
    assert accuracy["errors"]["crest_V"]["absolute_percentage_error"] == pytest.approx(
        100 * 25000 / 1400000
    )
    assert not accuracy["identity_verified"]
    assert accuracy["provenance"] == "fixture_observation"


def test_unsupported_prediction_has_no_corrected_metrics(context):
    report = fixture_report(context)
    assert report["corrected"] is None
    assert report["efficiency"]["corrected_voltage_transfer"] is None
    assert report["physics"]["metrics"]["crest_V"] == 1425000


def test_single_setup_api_and_module_timing(request_data, tmp_path):
    body = {
        "request": request_data,
        "proposal": {"N": 9, "Rf_required_ohm": 50, "Rt_required_ohm": 25},
    }
    with TestClient(create_app(tmp_path, False)) as client:
        response = client.post("/v1/performance/evaluate", json=body)
        assert response.status_code == 200, response.text
        assert float(response.headers["X-Processing-Time-Seconds"]) > 0
        report = response.json()
        assert report["correction_status"] == "unsupported"
        assert report["model_quality"]["status"] == "unavailable"
        assert report["runtime"]["total_seconds"] > 0
        assert set(report["runtime"]["stage_seconds"]) == {
            "context",
            "assembly",
            "physics",
            "correction",
        }
        assert (
            sum(report["runtime"]["stage_seconds"].values()) <= report["runtime"]["total_seconds"]
        )
        candidate = client.post("/v1/assemblies/realise", json=body).json()["candidate"]
        response = client.post(
            "/v1/physics/evaluate", json={"request": request_data, "candidate": candidate}
        )
        assert response.json()["performance"]["physics"]["metrics"] == response.json()["metrics"]
        quality = client.get("/v1/models/residual-tabpfn-v2-diagnostic-v1/performance").json()
        assert set(quality["categories"]) == {"Lightning", "Switching"}
        assert not quality["epochs_applicable"]


@pytest.mark.parametrize(
    "observation",
    [
        {"observed_metrics": {"front_s": 1e-6, "tail_s": 50e-6, "crest_V": 1420000}},
        {"observation_provenance": "shot-123"},
        {
            "observed_metrics": {"front_s": 0, "tail_s": 50e-6, "crest_V": 1420000},
            "observation_provenance": "shot-123",
        },
    ],
)
def test_invalid_observation_rejected(request_data, tmp_path, observation):
    with TestClient(create_app(tmp_path, False)) as client:
        response = client.post(
            "/v1/performance/evaluate", json={"request": request_data, **observation}
        )
        assert response.status_code == 422


def test_reporting_rejects_mismatched_baseline(context):
    candidate, _ = AssemblyEngine().realise(
        context, Proposal(N=9, Rf_required_ohm=50, Rt_required_ohm=25)
    )
    physics = evaluate(context, candidate)
    physics["candidate_id"] = "different-assembly"
    with pytest.raises(DomainError, match="Matching context"):
        build_report(
            context,
            candidate,
            physics,
            {},
            {},
            {"scope": "test", "stage_seconds": {}, "total_seconds": 0},
        )


def test_each_of_three_candidates_keeps_its_own_report(request_data, tmp_path, monkeypatch):
    # Fixtures stand in for approved equipment and a lab-validated model; production gates stay intact.
    request_data["charging_policy"]["U_charge_V"] = 30000
    context = resolve(RunRequest.model_validate(request_data))

    def approved_fixture(ctx, candidate, **kwargs):
        baseline = evaluate(ctx, candidate)
        baseline["hardware_feasible"] = True
        baseline["constraints"] = []
        return baseline

    monkeypatch.setattr("powernext.pipeline.runner.evaluate", approved_fixture)

    class Proposer:
        def ask(self, index):
            return index, Proposal(N=7 + index, Rf_required_ohm=50, Rt_required_ohm=25)

        def tell(self, trial, cost):
            pass

    class CorrectionFixture:
        def report(self):
            return {"model_version": "fixture", "lab_validated": True}

        def correct(self, ctx, candidate, baseline):
            return {
                "status": "fixture_prediction",
                "model_version": "fixture",
                "support": {"status": "supported"},
                "lab_validated": True,
                "corrected_metrics": {
                    "front_s": ctx.test["front_s"] * (1 + 0.001 * candidate.N),
                    "tail_s": ctx.test["tail_s"],
                    "crest_V": ctx.request.target.crest_V,
                },
            }

    store = Store(tmp_path / "test.sqlite")
    identifier, _ = store.create_run(context)
    result = run(
        context, identifier, store, tmp_path, model=CorrectionFixture(), proposer=Proposer()
    )
    assert result["returned_recommendations"] == 3
    for record in result["recommendations"]:
        assert record["performance"]["candidate_id"] == record["candidate_id"]
        assert (
            record["performance"]["corrected"]["metrics"]
            == record["correction"]["corrected_metrics"]
        )
        assert record["performance"]["runtime"]["stage_seconds"]["correction"] >= 0
    assert (
        len({r["performance"]["physics"]["metrics"]["crest_V"] for r in result["recommendations"]})
        == 3
    )
    assert result["performance"]["cache_hit_fraction"] == 0
