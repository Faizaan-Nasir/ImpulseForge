import pytest

from powernext.contracts.models import DomainError, Proposal, RunRequest
from powernext.optimisation.objective import Archive, evaluate_objective
from powernext.optimisation.smac_adapter import SmacAdapter
from powernext.pipeline.runner import run
from powernext.pipeline.storage import Store
from powernext.profiles.resolve import resolve


def evaluation(ctx, identity, error, eligible=True):
    metrics = {
        "front_s": ctx.test["front_s"] * (1 + error),
        "tail_s": ctx.test["tail_s"],
        "crest_V": ctx.request.target.crest_V,
    }
    objective = evaluate_objective(ctx, metrics)
    return {
        "candidate_id": identity,
        "candidate": {
            "N": 9,
            "U_charge_V": ctx.charge,
            "front": {"total_resistors": 1},
            "tail": {"total_resistors": 1},
        },
        "correction": {"corrected_metrics": metrics, "model_version": "mock"},
        "objective": objective,
        "eligible": eligible,
        "cost": objective["cost"] if eligible else 2,
    }


def test_objective_worst_error(context):
    o = evaluate_objective(context, {"front_s": 1.2e-6, "tail_s": 100e-6, "crest_V": 1425000})
    assert o["S"] == pytest.approx(5)
    assert o["cost"] == pytest.approx(5 / 6)
    assert not o["waveform_within_tolerance"]


def test_archive(context):
    archive = Archive()
    for i, error in enumerate([0.1, 0.05, 0.01, 0.2, 0.03]):
        archive.add(evaluation(context, str(i), error))
    assert [e["candidate_id"] for e in archive.best()] == ["2", "4", "1"]
    archive.add(evaluation(context, "2", 0.01))
    archive.add(evaluation(context, "bad", 0, False))
    assert len(archive.best()) == 3


def test_real_smac_ask_tell(context, tmp_path):
    smac = SmacAdapter(context, tmp_path / "smac")
    trial, proposal = smac.ask(0)
    assert 1 <= proposal.N <= 15
    assert proposal.N == 9
    assert proposal.Rf_required_ohm == 50
    assert proposal.Rt_required_ohm == 25
    smac.tell(trial, 0.3)


def test_physical_profile_smac_includes_fifteen_stages(request_data, tmp_path):
    request_data["equipment_profile_id"] = "haefely_pdf_v1"
    request_data["setup"]["basic_capacitance_inclusion"] = "add_separately"
    request_data["charging_policy"]["U_charge_V"] = 100000
    context = resolve(RunRequest.model_validate(request_data))
    smac = SmacAdapter(context, tmp_path / "physical-smac")
    assert smac.cs["N"].lower == 1
    assert smac.cs["N"].upper == 15


def test_smac_uses_supplied_stage_bound(request_data, tmp_path):
    request_data["equipment_inputs"] = {"N_max": 8}
    context = resolve(RunRequest.model_validate(request_data))
    smac = SmacAdapter(context, tmp_path / "frontend-smac")
    assert smac.cs["N"].upper == 8
    with pytest.raises(ValueError):
        smac.replay({"N": 9, "Rf_required_ohm": 50, "Rt_required_ohm": 25}, 0.1)


class MockProposer:
    def __init__(self):
        self.costs = []

    def ask(self, index):
        return index, Proposal(N=9, Rf_required_ohm=50, Rt_required_ohm=25, proposal_index=index)

    def tell(self, trial, cost):
        self.costs.append(cost)


def test_mock_pipeline_top_three(context, tmp_path):
    store = Store(tmp_path / "jobs.sqlite")
    ident, _ = store.create_run(context)
    result = run(
        context,
        ident,
        store,
        tmp_path,
        proposer=MockProposer(),
        evaluator=lambda p: evaluation(context, str(p.proposal_index), p.proposal_index * 0.001),
    )
    assert result["returned_recommendations"] == 3
    assert result["stop_reason"] == "three_satisfactory_setups"
    assert result["counters"]["proposals"] == 3
    assert len(store.get("waveforms", ident)["curves"]) == 4


def test_invalid_proposals_are_bounded(context, tmp_path):
    store = Store(tmp_path / "jobs.sqlite")
    ident, _ = store.create_run(context)

    def bad(p):
        raise DomainError("bad", "Rejected fixture")

    result = run(context, ident, store, tmp_path, proposer=MockProposer(), evaluator=bad)
    assert result["returned_recommendations"] == 0
    assert result["counters"]["proposals"] == 4
    assert result["rejections"]["bad"] == 4


def test_one_trial_has_buildable_seed(request_data, tmp_path):
    from powernext.assembly.cp_sat import AssemblyEngine
    from powernext.contracts.models import RunRequest
    from powernext.profiles.resolve import resolve

    request_data["search"]["max_proposals"] = 1
    context = resolve(RunRequest.model_validate(request_data))
    smac = SmacAdapter(context, tmp_path / "one-trial")
    trial, proposal = smac.ask(0)
    candidate, _report = AssemblyEngine().realise(context, proposal)
    assert candidate.front.equivalent_ohm == 50
    smac.tell(trial, 2)


def test_smac_seed_reproducible(context, tmp_path):
    def proposals(directory):
        adapter = SmacAdapter(context, directory)
        values = []
        for i in range(4):
            trial, proposal = adapter.ask(i)
            values.append(proposal.model_dump())
            adapter.tell(trial, 2)
        return values

    assert proposals(tmp_path / "first") == proposals(tmp_path / "second")


def test_real_smac_warm_replay(context, tmp_path):
    first = SmacAdapter(context, tmp_path / "first")
    trial, proposal = first.ask(0)
    first.tell(trial, 2)
    resumed = SmacAdapter(context, tmp_path / "resumed")
    resumed.replay(proposal.model_dump(), 2)
    trial2, proposal2 = resumed.ask(1)
    assert proposal2.proposal_index == 1
    resumed.tell(trial2, 2)


def test_single_stage_input_supported(request_data, tmp_path):
    request_data["equipment_inputs"] = {"N_max": 1}
    context = resolve(RunRequest.model_validate(request_data))
    smac = SmacAdapter(context, tmp_path / "single-stage")
    trial, proposal = smac.ask(0)
    assert proposal.N == 1
    smac.tell(trial, 0.3)
