"""Check dashboard routes against the actual local service and fitted residual models."""

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=120) as client:
        bootstrap = client.get("/v1/dashboard/bootstrap")
        bootstrap.raise_for_status()
        assert len(bootstrap.json()["inventory"]["tail"]) == 12
        report = {
            "bootstrap": {
                "front_types": len(bootstrap.json()["inventory"]["front"]),
                "tail_types": 12,
                "gemini": bootstrap.json()["gemini"],
            }
        }
        module = json.loads((ROOT / "examples/lightning_module_input.json").read_text())
        request = module["request"]
        request["inventory"] = {
            "source": "inline",
            "front": [
                {
                    "type_id": "front50",
                    "nominal_ohm": module["proposal"]["Rf_required_ohm"],
                    "available_quantity": 4,
                }
            ],
            "tail": [
                {
                    "type_id": "tail25",
                    "nominal_ohm": module["proposal"]["Rt_required_ohm"],
                    "available_quantity": 4,
                }
            ],
        }
        request["search"].update(
            max_proposals=4, dp_max_parts=1, wall_time_seconds=30, cp_pair_retries=1
        )
        response = client.post("/v1/runs", json=request, headers={"Idempotency-Key": uuid4().hex})
        response.raise_for_status()
        ident = response.json()["run_id"]
        for _ in range(100):
            state = client.get(f"/v1/runs/{ident}").json()
            if state["status"] not in ("queued", "running"):
                break
            time.sleep(0.2)
        assert state["status"] == "completed_with_shortfall", state
        view = client.get(f"/v1/runs/{ident}/dashboard")
        view.raise_for_status()
        assert view.json()["display_mode"] == "diagnostic_evaluated_cases"
        case = view.json()["cases"][0]
        inspected = client.post(f"/v1/candidates/{case['candidate_id']}/diagnostic-evaluation")
        inspected.raise_for_status()
        assert inspected.json()["correction"]["status"] == "predicted_diagnostic"
        assert not inspected.json()["eligible"]
        original = client.get(f"/v1/candidates/{case['candidate_id']}").json()
        assert (
            original["correction"]["status"] == "predicted_diagnostic" and not original["eligible"]
        )
        assert original["cost_basis"] == "diagnostic_waveform_with_ineligibility_penalty"
        view = client.get(f"/v1/runs/{ident}/dashboard").json()
        curve = next(c for c in view["waveforms"]["curves"] if c.get("candidate_id"))
        assert curve["origin"] == "ml_parameter_reconstruction"
        assert curve["comparison_to_target"]["normalised_rms_percent"] >= 0
        summary = client.post(f"/v1/runs/{ident}/decision-summary", json={})
        summary.raise_for_status()
        assert summary.json()["recommended_candidate_id"] is None
        report.update(
            run_id=ident,
            status="passed",
            diagnostic_candidate_eligible=False,
            production_record_unchanged=True,
            corrected_metrics=inspected.json()["correction"]["corrected_metrics"],
            model_support=inspected.json()["correction"]["support"],
            reconstructed_curve_origin=curve["origin"],
            decision_summary_status=summary.json()["status"],
            actual_gemini_generated=summary.json()["status"] == "generated",
        )
        (ROOT / "artifacts/dashboard-api-report.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
