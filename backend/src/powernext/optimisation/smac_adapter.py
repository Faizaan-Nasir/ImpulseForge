import math
from pathlib import Path
from typing import cast

from ConfigSpace import Configuration, ConfigurationSpace, Constant, Float, Integer
from ConfigSpace.hyperparameters import UniformFloatHyperparameter
from smac import HyperparameterOptimizationFacade, Scenario
from smac.model.random_forest.random_forest import RandomForest
from smac.runhistory.dataclasses import TrialInfo, TrialValue

from powernext.contracts.models import Proposal
from powernext.physics.forward import inverse
from powernext.profiles.resolve import stock_bounds


class SmacAdapter:
    def __init__(self, context, directory):
        hw = context.hardware
        req = context.request
        bounds = [stock_bounds(context.inventory, n) for n in range(hw["N_min"], hw["N_max"] + 1)]
        self.context = context
        cs = ConfigurationSpace(seed=req.seed)
        cs.add(
            Constant("N", hw["N_min"])
            if hw["N_min"] == hw["N_max"]
            else Integer("N", (hw["N_min"], hw["N_max"]))
        )
        for role, name in (("front", "Rf_required_ohm"), ("tail", "Rt_required_ohm")):
            lows = [b[role]["min_ohm"] for b in bounds if b[role]["min_ohm"] is not None]
            highs = [b[role]["max_ohm"] for b in bounds if b[role]["max_ohm"] is not None]
            low, high = min(lows), max(highs)
            if low == high:
                high = low * (1 + 1e-9)
            cs.add(Float(name, (low, high), log=True))
        self.cs = cs
        scenario = Scenario(
            cs,
            deterministic=True,
            n_trials=req.search.max_proposals,
            seed=req.seed,
            output_directory=Path(directory),
            n_workers=1,
        )
        seeds = []
        for n in sorted({context.data["seed_N"], min(hw["N_max"], context.data["seed_N"] + 1)}):
            try:
                seed_values = inverse(context, n)
                values = {k: seed_values[k] for k in ("N", "Rf_required_ohm", "Rt_required_ohm")}
                for key in ("Rf_required_ohm", "Rt_required_ohm"):
                    hp = cast(UniformFloatHyperparameter, cs[key])
                    values[key] = min(hp.upper, max(hp.lower, values[key]))
                if req.physics_mode == "calculator":
                    rounded = {
                        **values,
                        "Rf_required_ohm": 5 * math.floor(seed_values["Rf_required_ohm"] / 5 + 0.5),
                        "Rt_required_ohm": 5 * math.floor(seed_values["Rt_required_ohm"] / 5 + 0.5),
                    }
                    if all(
                        cast(UniformFloatHyperparameter, cs[k]).lower
                        <= rounded[k]
                        <= cast(UniformFloatHyperparameter, cs[k]).upper
                        for k in ("Rf_required_ohm", "Rt_required_ohm")
                    ):
                        seeds.append(Configuration(cs, values=rounded))
                seeds.append(Configuration(cs, values=values))
                if req.physics_mode == "calculator" and n == context.data["seed_N"]:
                    neighbour = {
                        **values,
                        "Rf_required_ohm": values["Rf_required_ohm"] * 0.95,
                        "Rt_required_ohm": values["Rt_required_ohm"] * 1.05,
                    }
                    if all(
                        cast(UniformFloatHyperparameter, cs[k]).lower
                        <= neighbour[k]
                        <= cast(UniformFloatHyperparameter, cs[k]).upper
                        for k in ("Rf_required_ohm", "Rt_required_ohm")
                    ):
                        seeds.append(Configuration(cs, values=neighbour))
            except ValueError:
                continue
        n_options = sorted(
            range(hw["N_min"], hw["N_max"] + 1), key=lambda n: (abs(n - context.data["seed_N"]), n)
        )
        for n in n_options:
            available = {
                role: [t for t in getattr(context.inventory, role) if t.capacity(n) > 0]
                for role in ("front", "tail")
            }
            if all(available.values()):
                seeds.append(
                    Configuration(
                        cs,
                        values={
                            "N": n,
                            "Rf_required_ohm": available["front"][0].nominal_ohm,
                            "Rt_required_ohm": available["tail"][0].nominal_ohm,
                        },
                    )
                )
                break
        seeds = list(dict.fromkeys(seeds))[: req.search.max_proposals]
        initial = HyperparameterOptimizationFacade.get_initial_design(
            scenario,
            n_configs=min(4, req.search.max_proposals - len(seeds)),
            additional_configs=seeds,
        )
        self.smac = HyperparameterOptimizationFacade(
            scenario,
            target_function=None,
            initial_design=initial,
            overwrite=True,
            model=RandomForest(
                configspace=cs,
                seed=req.seed,
                log_y=True,
                n_trees=10,
                ratio_features=1.0,
                min_samples_split=2,
                min_samples_leaf=1,
                n_jobs=1,
            ),
        )

    def replay(self, proposal, cost):
        values = {k: proposal[k] for k in ("N", "Rf_required_ohm", "Rt_required_ohm")}
        trial = TrialInfo(
            config=Configuration(self.cs, values=values), seed=self.context.request.seed
        )
        self.tell(trial, cost)

    def ask(self, index):
        trial = self.smac.ask()
        v = dict(trial.config)
        return trial, Proposal(
            N=int(v["N"]),
            Rf_required_ohm=float(v["Rf_required_ohm"]),
            Rt_required_ohm=float(v["Rt_required_ohm"]),
            proposal_index=index,
            source="SMAC3",
        )

    def tell(self, trial, cost):
        self.smac.tell(trial, TrialValue(cost=cost, time=0.0))
