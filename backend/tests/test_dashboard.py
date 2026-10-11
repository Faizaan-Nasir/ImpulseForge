import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_optimisation import MockProposer

from powernext.api.app import create_app
from powernext.config import Settings
from powernext.contracts.models import RunRequest
from powernext.dashboard.summary import generate_summary
from powernext.dashboard.view import cases_for_run, evidence, plot_bundle
from powernext.optimisation.objective import Archive, evaluate_objective
from powernext.physics.forward import parameters
from powernext.pipeline.runner import run
from powernext.pipeline.storage import Store
from powernext.profiles.resolve import resolve


def test_frontend_targets_tolerances_and_basic_capacitance(request_data):
    request_data["target"].update(
        front_s=1.3e-6, tail_s=55e-6, tolerances={"front": 0.25, "tail": 0.15, "crest": 0.02}
    )
    request_data["setup"].update(basic_C_F=120e-12, basic_capacitance_inclusion="add_separately")
    ctx = resolve(RunRequest.model_validate(request_data))
    assert ctx.test["front_s"] == 1.3e-6 and ctx.test["tolerances"]["crest"] == 0.02
    assert all(x == "frontend_input" for x in ctx.data["target_sources"].values())
    assert parameters(ctx, 9, 50, 25)["C2_F"] == pytest.approx(1620e-12)
    assert ctx.hardware["stage_energy_max_J"] == 2500
    request_data["setup"]["basic_capacitance_inclusion"] = "already_included"
    assert parameters(resolve(RunRequest.model_validate(request_data)), 9, 50, 25)[
        "C2_F"
    ] == pytest.approx(1500e-12)


def test_bootstrap_cors_and_no_credentials(tmp_path):
    settings = Settings(
        gemini_api_key=SecretStr("secret-must-not-appear"), gemini_model="test-model"
    )
    with TestClient(create_app(tmp_path, False, settings)) as client:
        response = client.get(
            "/v1/dashboard/bootstrap", headers={"Origin": "http://127.0.0.1:5173"}
        )
        assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
        assert "secret-must-not-appear" not in response.text
        assert response.json()["gemini"] == {"configured": True, "model": "test-model"}
        assert len(response.json()["inventory"]["tail"]) == 12
        assert not response.json()["capabilities"]["energy_limits_editable"]
        assert client.get("/v1/runs").json() == {"items": []}
        assert response.json()["defaults"]["physics_mode"] == "calculator"


def test_workbook_reference_is_input_driven_and_never_a_recommendation(request_data, tmp_path):
    from powernext.assembly.cp_sat import AssemblyEngine
    from powernext.dashboard.baseline import reference_request, workbook_baseline

    class DiagnosticModel:
        def report(self):
            return {}

        def correct(self, ctx, candidate, baseline):
            return {"status": "unsupported", "corrected_metrics": None}

    ctx = resolve(reference_request(RunRequest.model_validate(request_data)))
    baseline = workbook_baseline(ctx, AssemblyEngine(), DiagnosticModel())
    assert baseline["status"] == "evaluated"
    assert baseline["settings"]["N"] == 9
    assert baseline["settings"]["Rf_actual_ohm"] == 50
    assert baseline["settings"]["Rt_actual_ohm"] == 25
    assert baseline["record"]["physics"]["metrics"]["front_s"] == pytest.approx(
        1.210029958306818e-6
    )
    assert baseline["record"]["physics"]["metrics"]["tail_s"] == pytest.approx(52.2088875e-6)
    assert baseline["record"]["physics"]["metrics"]["crest_V"] == 1425000
    assert not baseline["record"]["eligible"]
    assert baseline["record"]["candidate"]["front"]["total_resistors"] == 1
    request_data["inventory"]["front"][0]["nominal_ohm"] = 55
    changed = workbook_baseline(
        resolve(reference_request(RunRequest.model_validate(request_data))),
        AssemblyEngine(),
        DiagnosticModel(),
    )
    assert changed["status"] == "reference_only"
    assert "candidate" not in changed["record"]
    assert changed["record"]["physics"]["metrics"]["crest_V"] == 1425000


def test_workbook_reference_endpoint_and_changed_capacitance(request_data, tmp_path):
    request_data["equipment_inputs"]["C_stage_F"] = 1.25e-7
    request_data["inventory"]["tail"][0]["nominal_ohm"] = 520
    with TestClient(create_app(tmp_path, False)) as client:
        r = client.post("/v1/dashboard/workbook-baseline", json={"request": request_data})
        r.raise_for_status()
        b = r.json()
        assert b["context"]["hardware"]["C_stage_F"] == 1.25e-7
        assert b["settings"]["Rt_actual_ohm"] != 25
        assert b["record"]["physics"]["metrics"]["tail_s"] > 0


def saved_diagnostic(context, tmp_path):
    store = Store(tmp_path / "dashboard.sqlite")
    store.save("context", context.context_id, context.model_dump())
    identifier, _ = store.create_run(context)

    class CorrectionFixture:
        def report(self):
            return {"status": "fixture"}

        def correct(self, ctx, candidate, baseline):
            return {
                "status": "predicted_diagnostic",
                "model_version": ctx.request.model_version,
                "corrected_metrics": baseline["metrics"],
                "support": {"status": "supported_diagnostic"},
                "lab_validated": False,
            }

    run(context, identifier, store, tmp_path, proposer=MockProposer(), model=CorrectionFixture())
    cases, mode = cases_for_run(store, identifier, context)
    return store, evidence(context, store.get("run", identifier), cases, mode), cases


def test_diagnostic_cases_and_plot_origin(context, tmp_path):
    store, data, cases = saved_diagnostic(context, tmp_path)
    assert (
        data["returned_recommendations"] == 0
        and data["display_mode"] == "diagnostic_evaluated_cases"
    )
    assert data["cases"][0]["metrics_origin"] == "residual_corrected"
    plot = plot_bundle(context, cases)
    curve = next(c for c in plot["curves"] if c.get("candidate_id"))
    assert curve["origin"] == "ml_parameter_reconstruction"
    assert curve["comparison_to_target"]["normalised_rms_percent"] >= 0
    result = generate_summary(Settings(gemini_api_key=None), data, store)
    assert result["status"] == "unavailable" and result["recommended_candidate_id"] is None
    assert "No verified recommendation" in result["narrative"]["lead"]


def test_dashboard_retains_three_matches_when_only_one_is_eligible(context, tmp_path):
    store = Store(tmp_path / "dashboard.sqlite")
    matches = [
        {
            "candidate_id": f"passing-{i}",
            "correction": {
                "corrected_metrics": {
                    "front_s": context.test["front_s"],
                    "tail_s": context.test["tail_s"],
                    "crest_V": context.request.target.crest_V * (1 + i * 0.001),
                }
            },
            "eligible": i == 0,
        }
        for i in range(3)
    ]
    failure = {
        "candidate_id": "legacy-shortfall",
        "correction": {
            "corrected_metrics": {
                "front_s": context.test["front_s"],
                "tail_s": context.test["tail_s"],
                "crest_V": context.request.target.crest_V * 0.999,
            }
        },
    }
    store.save(
        "result",
        "fixture",
        {"recommendations": matches[:1], "predicted_setups": matches + [failure]},
    )
    cases, mode = cases_for_run(store, "fixture", context)
    assert mode == "diagnostic_evaluated_cases"
    assert [c["candidate_id"] for c in cases] == [f"passing-{i}" for i in range(3)]


def test_gemini_summary_is_grounded_cached_and_validated(context, tmp_path, monkeypatch):
    store, data, _cases = saved_diagnostic(context, tmp_path)
    calls = []
    narrative = {
        "lead": "No verified recommendation is available because evidence checks remain unresolved.",
        "why_others_rank_lower": [],
        "needs_attention": ["Review HW_STAGE_ENERGY"],
        "evidence_refs": ["run", "case_1"],
    }

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
    settings = Settings(
        gemini_api_key=SecretStr("test-placeholder"), gemini_model="configured-test-model"
    )
    result = generate_summary(settings, data, store)
    assert result["status"] == "generated" and result["recommended_candidate_id"] is None
    assert calls[0]["model"] == "configured-test-model" and json.loads(calls[0]["contents"]) == data
    assert "test-placeholder" not in json.dumps(result)
    assert generate_summary(settings, data, store)["cached"] and len(calls) == 1
    narrative["evidence_refs"] = ["invented-case"]
    assert generate_summary(settings, data, store, True)["status"] == "invalid_response"


def test_provider_errors_do_not_expose_api_key(context, tmp_path, monkeypatch):
    store, data, _cases = saved_diagnostic(context, tmp_path)

    def broken(**kwargs):
        raise RuntimeError("credential-secret URL request failed")

    monkeypatch.setattr("google.genai.Client", broken)
    result = generate_summary(Settings(gemini_api_key=SecretStr("credential-secret")), data, store)
    assert result["status"] == "provider_error" and "credential-secret" not in json.dumps(result)


def test_dashboard_api_keeps_diagnostics_separate(request_data, tmp_path):
    with TestClient(create_app(tmp_path, False, Settings(gemini_api_key=None))) as client:
        client.post("/v1/requests/validate", json=request_data)
        body = {
            "request": request_data,
            "proposal": {"N": 9, "Rf_required_ohm": 50, "Rt_required_ohm": 25},
        }
        candidate = client.post("/v1/assemblies/realise", json=body).json()["candidate"]
        physics = client.post(
            "/v1/physics/evaluate", json={"request": request_data, "candidate": candidate}
        ).json()
        identifier = client.post("/v1/runs", json=request_data).json()["run_id"]
        store = client.app.state.store
        record = {
            "candidate_id": candidate["candidate_id"],
            "candidate": candidate,
            "physics": physics,
            "correction": {"status": "not_invoked", "corrected_metrics": None},
            "eligible": False,
            "cost": 2,
            "objective": None,
        }
        store.save("candidate", candidate["candidate_id"], record)
        store.event(
            identifier,
            {"pipeline_stage_name": "evaluation", "candidate_id": candidate["candidate_id"]},
        )
        store.patch(
            "run", identifier, {"status": "completed_with_shortfall", "returned_recommendations": 0}
        )
        response = client.get(f"/v1/runs/{identifier}/dashboard")
        assert response.status_code == 200, response.text
        assert response.json()["cases"] == []  # Physics-only records are not calibrated cases.
        inspected = client.post(
            f"/v1/candidates/{candidate['candidate_id']}/diagnostic-evaluation"
        ).json()
        assert inspected["eligible"] is False and inspected["correction"]["status"] == "unsupported"
        assert (
            store.get("candidate", candidate["candidate_id"])["correction"]["status"]
            == "not_invoked"
        )
        summary = client.post(f"/v1/runs/{identifier}/decision-summary", json={}).json()
        assert summary["status"] == "unavailable" and summary["recommended_candidate_id"] is None


def test_preference_only_breaks_equal_waveform_objectives(context):
    def entry(identifier, N, error):
        metrics = {
            "front_s": context.test["front_s"] * (1 + error),
            "tail_s": context.test["tail_s"],
            "crest_V": context.request.target.crest_V,
        }
        return {
            "candidate_id": identifier,
            "eligible": True,
            "objective": evaluate_objective(context, metrics),
            "candidate": {
                "N": N,
                "U_charge_V": 100000,
                "front": {"total_resistors": 1},
                "tail": {"total_resistors": 1},
            },
        }

    archive = Archive("stages")
    archive.add(entry("more-stages-better-waveform", 10, 0))
    archive.add(entry("fewer-stages-worse-waveform", 2, 0.1))
    assert archive.best()[0]["candidate_id"] == "more-stages-better-waveform"
    archive.add(entry("equal-waveform-fewer-stages", 9, 0))
    assert archive.best()[0]["candidate_id"] == "equal-waveform-fewer-stages"
