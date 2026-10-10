"""Workbook fixture conversion, keeping labels separate from inference requests."""

from powernext.contracts.models import Proposal, RunRequest
from powernext.correction.features import workbook_data


def workbook_fixture(category="Lightning", index=0):
    frame, _, _ = workbook_data()
    row = frame[(frame.Impulse_Type == category) & (frame.Split == "Validation")].iloc[index]
    request = RunRequest.model_validate(
        {
            "purpose": "diagnostic",
            "equipment_profile_id": "workbook_benchmark_v1",
            "equipment_inputs": {
                "N_max": 15,
                "U_stage_max_V": 200000,
                "C_stage_F": 3e-6,
            },
            "impulse_profile_id": "lightning_project_v1"
            if category == "Lightning"
            else "switching_workbook_legacy_v1",
            "physics_mode": "calculator",
            "inventory": {
                "source": "inline",
                "front": [
                    {
                        "type_id": "fixture_front",
                        "nominal_ohm": float(row.Front_R_Stage),
                        "available_quantity": 4,
                    }
                ],
                "tail": [
                    {
                        "type_id": "fixture_tail",
                        "nominal_ohm": float(row.Tail_R_Stage),
                        "available_quantity": 4,
                    }
                ],
            },
            "target": {"crest_V": float(row.Physics_Crest_kV) * 1000},
            "load": {"C_F": float(row.Load_C_pF) * 1e-12},
            "setup": {
                "divider_C_F": float(row.Divider_C_pF) * 1e-12,
                "stray_C_F": float(row.Stray_C_pF) * 1e-12,
                "stray_L_H": float(row.L_uH) * 1e-6,
                "basic_capacitance_inclusion": "benchmark_omitted",
            },
            "expected_voltage_efficiency": float(row.Efficiency),
            "charging_policy": {"kind": "fixed", "U_charge_V": float(row.Charge_kV_Stage) * 1000},
            "search": {"max_proposals": 4, "dp_max_parts": 1},
        }
    )
    proposal = Proposal(
        N=int(row.Stages),
        Rf_required_ohm=float(row.Front_R_Stage),
        Rt_required_ohm=float(row.Tail_R_Stage),
    )
    return request, proposal
