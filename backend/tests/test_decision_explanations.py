from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from google.genai import errors
from pydantic import SecretStr
from test_dashboard import saved_diagnostic

from powernext.api.app import create_app
from powernext.config import Settings
from powernext.dashboard.explanations import ExplanationService
from powernext.dashboard.reasoning import build_reasoning
from powernext.dashboard.summary import generate_summary
from powernext.dashboard.view import evidence


class ModelFixture:
    fingerprint = "fitted-model-fixture"

    def __init__(self):
        self.calls = 0
        self.multiplier = 1

    def explain(self, ctx, candidate, physics):
        self.calls += 1
        outputs = []
        for key, residual in (("front_s", 3e-9), ("tail_s", -2e-7), ("crest_V", 700)):
            outputs.append(
                {
                    "output_name": "residual_" + key,
                    "reference_residual": residual * 0.25 * self.multiplier,
                    "feature_contributions": [
                        {
                            "feature": "N",
                            "value": 9,
                            "contribution": residual * 0.5 * self.multiplier,
                        },
                        {
                            "feature": "physics_front_s",
                            "value": physics["metrics"]["front_s"],
                            "contribution": residual * 0.25 * self.multiplier,
                        },
                    ],
                    "additivity_error": 0,
                    "method": "Kernel SHAP",
                    "nsamples": 32,
                }
            )
        return {"status": "complete", "outputs": outputs, "background_count": 8}


def prepared(context, tmp_path):
    store, _, cases = saved_diagnostic(context, tmp_path)
    record = deepcopy(cases[0])
    for key, residual in (("front_s", 3e-9), ("tail_s", -2e-7), ("crest_V", 700)):
        record["correction"]["corrected_metrics"][key] = (
            record["physics"]["metrics"][key] + residual
        )
    return store, record, ModelFixture()


def enriched(context, tmp_path):
    store, record, model = prepared(context, tmp_path)
    data = evidence(
        context, {"status": "completed", "counters": {}}, [record], "diagnostic_evaluated_cases"
    )
    data["cases"][0]["shap"] = ExplanationService(store, model).explain(context, record)
    return store, data


def test_cache_and_exact_saved_prediction_additivity(context, tmp_path):
    store, record, model = prepared(context, tmp_path)
    service = ExplanationService(store, model)
    first = service.explain(context, record)
    second = service.explain(context, record)
    assert first["status"] == "complete" and second["cached"] and model.calls == 1
    assert all(o["additivity_verified"] for o in first["outputs"])
    assert max(o["saved_prediction_additivity_error"] for o in first["outputs"]) < 1e-10
    model.fingerprint = "different-fitted-model"
    assert service.explain(context, record)["status"] == "complete" and model.calls == 2


def test_wrong_attributions_are_rejected(context, tmp_path):
    store, record, model = prepared(context, tmp_path)
    model.multiplier = 2
    output = ExplanationService(store, model).explain(context, record)
    assert (
        output["status"] == "unavailable" and output["reason"] == "shap_saved_prediction_mismatch"
    )
    assert store.list("candidate_explanation") == []


def test_shap_failure_preserves_numbers_without_inventing_drivers(context, tmp_path):
    store, data = enriched(context, tmp_path)
    data["cases"][0]["shap"] = {"status": "unavailable", "reason": "model_artifact_changed"}
    result = generate_summary(Settings(gemini_api_key=None), data, store)
    assert result["explanation_status"] == "partial"
    for output in result["analysis"]["cases"][0]["outputs"]:
        assert output["physics_value"] and output["corrected_value"]
        assert output["contributions"] == [] and output["shap_reason"] == "model_artifact_changed"


def test_units_background_and_model_scope(context, tmp_path):
    _, data = enriched(context, tmp_path)
    report = build_reasoning(data)
    assert report["status"] == "complete"
    front, tail, crest = report["cases"][0]["outputs"]
    assert front["sum_contributions"] * front["display_scale"] == pytest.approx(0.00225)
    assert tail["sum_contributions"] * tail["display_scale"] == pytest.approx(-0.15)
    assert crest["sum_contributions"] * crest["display_scale"] == pytest.approx(0.525)
    assert front["reference_residual"] + front["sum_contributions"] == pytest.approx(
        front["ml_residual"]
    )
    assert "not the physics baseline" in front["reference_meaning"]
    assert "does not establish physical causation" in report["interpretation"]
    assert "per-resistor heat" in report["scope"]


def test_rank_decisive_criterion(context, tmp_path):
    _, data = enriched(context, tmp_path)
    first = data["cases"][0]
    first.update(S=0.1, J=0.4, resistors_per_stage=8)
    second = deepcopy(first)
    second.update(
        candidate_id="alternative",
        case_number=2,
        evidence_id="case_2",
        S=0.2,
        J=0.1,
        resistors_per_stage=2,
    )
    data["cases"].append(second)
    report = build_reasoning(data)
    assert report["comparison"][0]["criterion"] == "S"
    assert "before J or resistor counts" in report["comparison"][0]["reason"]
    second["S"] = first["S"]
    first["J"], second["J"] = 0.1, 0.4
    assert build_reasoning(data)["comparison"][0]["criterion"] == "J"
    second["J"] = first["J"]
    first["resistors_per_stage"], second["resistors_per_stage"] = 2, 8
    assert build_reasoning(data)["comparison"][0]["criterion"] == "secondary_tie_break"


@pytest.mark.parametrize("code", [402, 404, 429])
def test_provider_failure_keeps_complete_shap_explanation(context, tmp_path, monkeypatch, code):
    store, data = enriched(context, tmp_path)

    def broken(**kwargs):
        raise errors.ClientError(
            code, {"error": {"message": "private-secret-url", "status": "RESOURCE_EXHAUSTED"}}
        )

    monkeypatch.setattr("google.genai.Client", broken)
    result = generate_summary(Settings(gemini_api_key=SecretStr("private-key")), data, store)
    assert result["status"] == "provider_error" and result["provider_http_status"] == code
    assert result["explanation_status"] == "complete" and result["highest_ranked_candidate_id"]
    assert result["recommended_candidate_id"] is None
    assert len(result["analysis"]["cases"][0]["outputs"]) == 3 and "private" not in str(result)


def test_api_uses_shared_shap_service(context, tmp_path, monkeypatch):
    _, record, model = prepared(context, tmp_path)
    raw = model.explain(context, None, record["physics"])
    for o in raw["outputs"]:
        o["additivity_verified"] = True
    calls = []

    def explain(self, ctx, candidate_record):
        calls.append(candidate_record["candidate_id"])
        return raw

    monkeypatch.setattr(ExplanationService, "explain", explain)
    with TestClient(create_app(tmp_path / "api", False, Settings(gemini_api_key=None))) as client:
        store = client.app.state.store
        store.save("context", context.context_id, context.model_dump())
        run_id, _ = store.create_run(context)
        store.save("candidate", record["candidate_id"], record)
        store.save("result", run_id, {"predicted_setups": []})
        store.event(
            run_id, {"pipeline_stage_name": "evaluation", "candidate_id": record["candidate_id"]}
        )
        store.patch("run", run_id, {"status": "completed"})
        summary = client.post(f"/v1/runs/{run_id}/decision-summary", json={})
        assert summary.status_code == 200, summary.text
        assert summary.json()["explanation_status"] == "complete"
        assert (
            client.get(f"/v1/candidates/{record['candidate_id']}/explanations").json()["status"]
            == "complete"
        )
        assert calls == [record["candidate_id"]] * 2


def test_gemini_output_refs_completeness_and_cache(context, tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    store, data = enriched(context, tmp_path)
    narrative = {
        "lead": "The recorded model explanation is diagnostic.",
        "why_others_rank_lower": [],
        "needs_attention": [],
        "evidence_refs": ["case_1_front_s"],
        "physics_explanation": "The actual circuit supplies the physics baseline.",
        "why_first_ranked": "Only one successful configuration was evaluated.",
        "ml_explanations": [
            {
                "candidate_id": data["cases"][0]["candidate_id"],
                "explanation": "The residual changes front, tail and crest relative to the background.",
                "evidence_refs": ["case_1_front_s", "case_1_tail_s", "case_1_crest_V"],
            }
        ],
    }
    calls = []

    class Client:
        def __init__(self, **kwargs):
            self.models = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text=json.dumps(narrative))

    monkeypatch.setattr("google.genai.Client", Client)
    settings = Settings(gemini_api_key=SecretStr("fixture-key"))
    result = generate_summary(settings, data, store)
    assert result["status"] == "generated"
    schema = calls[0]["config"].response_json_schema
    assert "case_1_front_s" in schema["properties"]["evidence_refs"]["items"]["enum"]
    data["cases"][0]["shap"].update(cached=True, generation_seconds=123)
    assert generate_summary(settings, data, store)["cached"] and len(calls) == 1
    narrative["ml_explanations"] = []
    incomplete = generate_summary(settings, data, store, True)
    assert incomplete["reason_code"] == "gemini_missing_required_sections"
    assert incomplete["explanation_status"] == "complete"
