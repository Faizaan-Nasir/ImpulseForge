import numpy as np
import pandas as pd

from powernext.contracts.models import DomainError
from powernext.profiles.registry import DOCS

FEATURES = [
    "N",
    "U_charge_V",
    "Rf_stage_actual_ohm",
    "Rt_stage_actual_ohm",
    "C_object_F",
    "C_divider_F",
    "C_stray_F",
    "L_effective_H",
    "C_generator_F",
    "C_load_effective_F",
    "R_front_effective_ohm",
    "R_tail_effective_ohm",
    "physics_front_s",
    "physics_tail_s",
    "physics_crest_V",
    "expected_voltage_efficiency",
]
TARGETS = ["residual_front_s", "residual_tail_s", "residual_crest_V"]


def extract_features(context, candidate, baseline):
    p = baseline["derived"]
    req = context.request
    m = baseline["metrics"]
    return {
        "N": candidate.N,
        "U_charge_V": candidate.U_charge_V,
        "Rf_stage_actual_ohm": candidate.front.equivalent_ohm,
        "Rt_stage_actual_ohm": candidate.tail.equivalent_ohm,
        "C_object_F": req.load.C_F,
        "C_divider_F": req.setup.divider_C_F,
        "C_stray_F": req.setup.stray_C_F,
        "L_effective_H": p["L_effective_H"],
        "C_generator_F": p["C1_F"],
        "C_load_effective_F": p["C2_F"],
        "R_front_effective_ohm": p["R1_ohm"],
        "R_tail_effective_ohm": p["R2_ohm"],
        "physics_front_s": m["front_s"],
        "physics_tail_s": m["tail_s"],
        "physics_crest_V": m["crest_V"],
        "expected_voltage_efficiency": req.expected_voltage_efficiency,
    }


def workbook_data(path=None):
    frame = pd.read_excel(
        path or DOCS / "Hybrid_Physics_ML_Impulse_Generator_Optimiser.xlsx",
        sheet_name="Synthetic Dataset",
        engine="openpyxl",
    )
    mapped = {
        "N": frame.Stages,
        "U_charge_V": frame.Charge_kV_Stage * 1000,
        "Rf_stage_actual_ohm": frame.Front_R_Stage,
        "Rt_stage_actual_ohm": frame.Tail_R_Stage,
        "C_object_F": frame.Load_C_pF * 1e-12,
        "C_divider_F": frame.Divider_C_pF * 1e-12,
        "C_stray_F": frame.Stray_C_pF * 1e-12,
        "L_effective_H": frame.L_uH * 1e-6,
        "C_generator_F": 3e-6 / frame.Stages,
        "C_load_effective_F": (frame.Load_C_pF + frame.Divider_C_pF + frame.Stray_C_pF) * 1e-12,
        "R_front_effective_ohm": frame.Stages * frame.Front_R_Stage,
        "R_tail_effective_ohm": frame.Stages * frame.Tail_R_Stage,
        "physics_front_s": frame.Physics_FrontPeak_us * 1e-6,
        "physics_tail_s": frame.Physics_Tail_us * 1e-6,
        "physics_crest_V": frame.Physics_Crest_kV * 1000,
        "expected_voltage_efficiency": frame.Efficiency,
    }
    X = pd.DataFrame(mapped)
    Y = pd.DataFrame(
        {
            "residual_front_s": (frame.Observed_FrontPeak_us - frame.Physics_FrontPeak_us) * 1e-6,
            "residual_tail_s": (frame.Observed_Tail_us - frame.Physics_Tail_us) * 1e-6,
            "residual_crest_V": (frame.Observed_Crest_kV - frame.Physics_Crest_kV) * 1000,
        }
    )
    stored = np.column_stack(
        (frame.Residual_FrontPeak * 1e-6, frame.Residual_Tail * 1e-6, frame.Residual_Crest * 1000)
    )
    if not np.allclose(Y.to_numpy(), stored, rtol=1e-8, atol=1e-9):
        raise DomainError(
            "invalid_residual_identity",
            "Workbook residual labels differ from observed minus physics",
            "data",
        )
    return frame, X, Y


def manifest(frame, X, Y, category):
    mask = (frame.Impulse_Type == category) & (frame.Split == "Train")
    train = X[mask]
    selected = [f for f in FEATURES if train[f].nunique() > 1]
    return {
        "category": category,
        "features": FEATURES,
        "selected_features": selected,
        "feature_ranges": {f: [float(train[f].min()), float(train[f].max())] for f in FEATURES},
        "feature_status": {
            f: "selected" if f in selected else "excluded_constant" for f in FEATURES
        },
        "unavailable": [
            "exact wiring",
            "generator topology measurement",
            "overshoot",
            "environment",
            "per-resistor heat",
        ],
        "targets": TARGETS,
        "target_units": ["s", "s", "V"],
        "baseline_mode": "calculator",
        "baseline_profile": "workbook_benchmark_v1",
        "train_count": int(mask.sum()),
        "validation_count": int(
            ((frame.Impulse_Type == category) & (frame.Split == "Validation")).sum()
        ),
        "hidden_test_count": int(
            ((frame.Impulse_Type == category) & (frame.Split == "Hidden Test")).sum()
        ),
        "provenance": "synthetic_only",
        "lab_validated": False,
        "training_mode": "pretrained_in_context",
        "epochs_applicable": False,
        "epochs": None,
        "downstream_gradient_updates": 0,
    }
