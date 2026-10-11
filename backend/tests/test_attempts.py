from fastapi.testclient import TestClient
from test_optimisation import MockProposer

from powernext.api.app import create_app
from powernext.contracts.models import Proposal
from powernext.dashboard.attempts import attempt_history
from powernext.pipeline.runner import run
from powernext.pipeline.storage import Store
from powernext.profiles.resolve import Context


class LowCrestModel:
    def report(self):
        return {}

    def correct(self, ctx, candidate, baseline):
        return {
            "status": "predicted_diagnostic",
            "model_version": "fixture",
            "corrected_metrics": {
                "front_s": ctx.test["front_s"],
                "tail_s": ctx.test["tail_s"],
                "crest_V": ctx.request.target.crest_V * 0.999,
            },
            "support": {"status": "supported_diagnostic"},
            "lab_validated": False,
        }


def test_history_retains_cached_repeats_and_original_ml_values(context, tmp_path):
    store = Store(tmp_path / "jobs.sqlite")
    ident, _ = store.create_run(context)
    result = run(context, ident, store, tmp_path, proposer=MockProposer(), model=LowCrestModel())
    rows = attempt_history(store, ident, context)
    assert [r["attempt_number"] for r in rows] == [1, 2, 3, 4]
    assert [r["prediction_source"] for r in rows] == ["fresh_ml"] + ["cached_ml"] * 3
    assert [r["ml_evaluation_number"] for r in rows] == [1, None, None, None]
    assert rows[-1]["source_ml_evaluation_number"] == 1
    assert len({r["candidate_id"] for r in rows}) == 1
    assert all(r["ml_metrics"]["crest_V"] == context.request.target.crest_V * 0.999 for r in rows)
    assert all(not r["waveform_within_tolerance"] for r in rows)
    assert rows[0]["front_recipe"] and rows[0]["tail_recipe"]
    assert result["returned_successful_predictions"] == 0


def test_cached_success_is_one_configuration_not_three(context, tmp_path):
    class ExactModel(LowCrestModel):
        def correct(self, ctx, candidate, baseline):
            output = super().correct(ctx, candidate, baseline)
            output["corrected_metrics"]["crest_V"] = ctx.request.target.crest_V
            return output

    store = Store(tmp_path / "jobs.sqlite")
    ident, _ = store.create_run(context)
    result = run(context, ident, store, tmp_path, proposer=MockProposer(), model=ExactModel())
    rows = attempt_history(store, ident, context)
    assert result["counters"]["proposals"] == 4
    assert result["returned_successful_predictions"] == 1
    assert not result["ml_converged"]
    assert len(rows) == 4 and all(r["waveform_within_tolerance"] for r in rows)
    assert len({r["candidate_id"] for r in rows}) == 1


def test_attempt_endpoint_paginates_rejections_and_unavailable_ml(request_data, tmp_path):
    class Proposer:
        def ask(self, i):
            return i, Proposal(
                N=9, Rf_required_ohm=(1000, 50, 50, 1000)[i], Rt_required_ohm=25, proposal_index=i
            )

        def tell(self, trial, cost):
            pass

    class Unsupported:
        def report(self):
            return {}

        def correct(self, *args):
            return {
                "status": "unsupported",
                "corrected_metrics": None,
                "support": {"reasons": ["fixture_outside_domain"]},
            }

    with TestClient(create_app(tmp_path, False)) as client:
        created = client.post("/v1/runs", json=request_data).json()
        store = client.app.state.store
        context = Context.model_validate(store.get("context", created["context_id"]))
        run(context, created["run_id"], store, tmp_path, proposer=Proposer(), model=Unsupported())
        path = f"/v1/runs/{created['run_id']}/attempts"
        response = client.get(path)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["total"] == data["proposal_count"] == 4
        assert [r["attempt_number"] for r in data["items"]] == [1, 2, 3, 4]
        assert all(r["ml_metrics"] is None for r in data["items"])
        assert data["items"][0]["attempt_status"] == "rejected"
        assert data["items"][0]["reason_codes"] == ["inventory_range_infeasible"]
        assert data["items"][2]["prediction_source"] == "cached_ml"
        assert [
            r["attempt_number"] for r in client.get(path + "?offset=1&limit=2").json()["items"]
        ] == [2, 3]


def test_multiple_ml_evaluations_in_one_attempt_keep_event_snapshots(context, tmp_path):
    store = Store(tmp_path / "jobs.sqlite")
    ident, _ = store.create_run(context)
    proposal = Proposal(N=9, Rf_required_ohm=50, Rt_required_ohm=25).model_dump()
    store.event(ident, {"pipeline_stage_name": "proposal", "proposal": proposal})
    for number, factor in ((1, 0.999), (2, 1.001)):
        identity = f"recipe-{number}"
        candidate = {
            "candidate_id": identity,
            "N": 9,
            "U_charge_V": 190000,
            "front": {"equivalent_ohm": number * 20},
            "tail": {"equivalent_ohm": 25},
        }
        correction = {
            "status": "predicted_diagnostic",
            "model_version": "fixture",
            "corrected_metrics": {
                "front_s": 1.2e-6,
                "tail_s": 50e-6,
                "crest_V": context.request.target.crest_V * factor,
            },
        }
        store.event(ident, {"pipeline_stage_name": "assembly", "candidate": candidate})
        store.event(
            ident,
            {
                "pipeline_stage_name": "physics",
                "candidate_id": identity,
                "output": {"hardware_feasible": False, "constraints": []},
            },
        )
        store.event(
            ident,
            {"pipeline_stage_name": "correction", "candidate_id": identity, "output": correction},
        )
    store.save("candidate", identity, {"candidate": candidate, "correction": correction})
    store.event(
        ident, {"pipeline_stage_name": "evaluation", "candidate_id": identity, "eligible": False}
    )
    rows = attempt_history(store, ident, context)
    assert [r["evaluation_in_attempt"] for r in rows] == [1, 2]
    assert [r["ml_evaluation_number"] for r in rows] == [1, 2]
    assert [r["waveform_within_tolerance"] for r in rows] == [False, True]
    assert [r["Rf_actual_ohm"] for r in rows] == [20, 40]
