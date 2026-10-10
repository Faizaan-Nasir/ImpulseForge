"""Exercise a real HTTP server and worker, recording exactly observed outcomes."""

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx

BACKEND = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    report = {}
    with httpx.Client(base_url=args.base_url, timeout=120) as client:
        response = client.get("/health")
        response.raise_for_status()
        report["health"] = response.json()
        body = json.loads((BACKEND / "examples" / "lightning_module_input.json").read_text())
        supplied_request = {
            **body["request"],
            "equipment_profile_id": "haefely_pdf_v1",
            "equipment_inputs": {"N_max": 8, "U_stage_max_V": 250000, "C_stage_F": 3e-6},
            "setup": {**body["request"]["setup"], "basic_capacitance_inclusion": "add_separately"},
        }
        response = client.post("/v1/requests/validate", json=supplied_request)
        response.raise_for_status()
        resolved = response.json()
        assert resolved["hardware"]["N_max"] == 8
        assert resolved["hardware"]["C_stage_F"] == 3e-6
        assert resolved["hardware"]["U_stage_max_V"] == 250000
        assert resolved["hardware"]["stage_energy_max_J"] == 2500
        assert resolved["hardware"]["C_basic_F"] == 0
        assert set(resolved["hardware"]).isdisjoint(
            {"U_stack_max_V", "crest_min_V", "crest_max_V", "shots_per_minute"}
        )
        assert resolved["value_sources"]["C_stage_F"]["source"] == "frontend_input"
        report["frontend_input_precedence"] = {
            "status": "passed",
            "resolved_hardware": resolved["hardware"],
            "value_sources": resolved["value_sources"],
            "input_sources": resolved["input_sources"],
        }
        response = client.post("/v1/assemblies/realise", json=body)
        response.raise_for_status()
        candidate = response.json()["candidate"]
        body["candidate"] = candidate
        response = client.post("/v1/physics/evaluate", json=body)
        response.raise_for_status()
        report["physics"] = response.json()
        assert not {"HW_STACK_CHARGE", "HW_CREST"}.intersection(
            check["constraint_id"] for check in report["physics"]["constraints"]
        )
        response = client.post("/v1/corrections/predict", json=body)
        response.raise_for_status()
        report["correction"] = response.json()
        assert report["correction"]["status"] == "predicted_diagnostic"
        assert not any(
            check["constraint_id"] == "ML_HW_CREST"
            for check in report["correction"]["corrected_constraint_checks"]
        )
        assert (
            report["correction"]["performance"]["corrected"]["metrics"]
            == report["correction"]["corrected_metrics"]
        )
        response = client.post("/v1/performance/evaluate", json=body)
        response.raise_for_status()
        report["performance"] = response.json()
        assert report["performance"]["corrected"] is not None
        assert report["performance"]["model_quality"]["train_count"] == 700
        assert report["performance"]["model_quality"]["validation_count"] == 150
        assert (
            report["performance"]["model_quality"]["metrics"]["residual_crest_V"]["validation_MAE"]
            > 0
        )
        assert report["performance"]["observed_accuracy"]["status"] == "unavailable"
        assert float(response.headers["X-Processing-Time-Seconds"]) > 0
        response = client.post(
            "/v1/runs",
            json=body["request"],
            headers={"Idempotency-Key": "local-smoke-" + uuid4().hex},
        )
        response.raise_for_status()
        run_id = response.json()["run_id"]
        for _ in range(120):
            state = client.get(f"/v1/runs/{run_id}").json()
            if state["status"] not in ("queued", "running"):
                break
            time.sleep(0.5)
        assert state["status"] == "completed_with_shortfall", state
        report["run"] = client.get(f"/v1/runs/{run_id}/result").json()
        report["events_count"] = len(client.get(f"/v1/runs/{run_id}/events").json())
        candidates = client.get(f"/v1/runs/{run_id}/candidates").json()["items"]
        if candidates:
            identifier = candidates[0]["candidate_id"]
            report["generator_stages"] = client.get(
                f"/v1/candidates/{identifier}/generator-stages"
            ).json()
            report["candidate_performance"] = client.get(
                f"/v1/candidates/{identifier}/performance"
            ).json()
            assert report["candidate_performance"]["candidate_id"] == identifier
        assert report["run"]["performance"]["elapsed_seconds"] > 0
        assert report["run"]["returned_recommendations"] == 0
        assert report["run"]["counters"]["physics_evaluations"] >= 1
        assert len(report.get("generator_stages", [])) >= 2
        response = client.get(f"/v1/runs/{run_id}/waveforms?format=csv")
        response.raise_for_status()
        report["csv_rows"] = len(response.text.splitlines())
        plots = json.loads((BACKEND / "examples" / "plot_metrics.json").read_text())
        response = client.post(
            "/v1/waveforms/reconstruct",
            json={"request": body["request"], "candidate_metrics": plots},
        )
        response.raise_for_status()
        plot_bundle = response.json()
        assert len(plot_bundle["curves"]) == 4
        report["four_curve_plot"] = {
            "curves": len(plot_bundle["curves"]),
            "points": len(plot_bundle["time_s"]),
            "origins": [c["origin"] for c in plot_bundle["curves"]],
        }
        (BACKEND / "artifacts" / "four_curve_plot.json").write_text(json.dumps(plot_bundle))
    (BACKEND / "artifacts" / "live-api-report.json").write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                "status": "passed",
                "run_id": run_id,
                "events": report["events_count"],
                "plot_curves": 4,
                "recommendations": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
