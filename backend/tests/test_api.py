from fastapi.testclient import TestClient

from powernext.api.app import create_app


def test_equipment_api_exposes_fifteen_stage_limit(tmp_path):
    with TestClient(create_app(tmp_path, False)) as client:
        for profile_id in ("haefely_pdf_v1", "workbook_benchmark_v1"):
            response = client.get(f"/v1/profiles/equipment/{profile_id}")
            assert response.status_code == 200
            assert response.json()["N_max"] == 15


def test_stage_energy_input_reaches_calibration_and_api_provenance(request_data, tmp_path):
    request_data["equipment_inputs"]["stage_energy_max_J"] = 60000
    with TestClient(create_app(tmp_path, False)) as client:
        body = {
            "request": request_data,
            "proposal": {"N": 9, "Rf_required_ohm": 50, "Rt_required_ohm": 25},
        }
        assembly = client.post("/v1/assemblies/realise", json=body)
        assert assembly.status_code == 200, assembly.text
        body["candidate"] = assembly.json()["candidate"]
        response = client.post("/v1/calibration/evaluate", json=body)
        assert response.status_code == 200, response.text
        result = response.json()
        report = result["calibration"]
        energy = next(c for c in report["constraints"] if c["constraint_id"] == "HW_STAGE_ENERGY")
        assert energy["limit_value"] == 60000 and energy["status"] == "pass"
        assert energy["origin"] == "frontend_input"
        assert report["feasibility_windows"]["stage_energy_limit_J"] == 60000


def test_api_exposes_frontend_values_and_fallback_provenance(request_data, tmp_path):
    request_data["equipment_inputs"] = {"N_max": 8, "U_stage_max_V": 250000, "C_stage_F": 2e-6}
    with TestClient(create_app(tmp_path, False)) as client:
        response = client.post("/v1/requests/validate", json=request_data)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["hardware"]["N_max"] == 8
        assert result["hardware"]["C_stage_F"] == 2e-6
        assert result["value_sources"]["N_max"]["source"] == "frontend_input"
        saved = client.get(f"/v1/requests/{result['context_id']}/constraints")
        assert saved.json()["value_sources"] == result["value_sources"]


def test_every_workbook_input_can_be_supplied(request_data, tmp_path):
    request_data.update(
        impulse_type="Switching",
        system_max_voltage_V=500000,
        expected_voltage_efficiency=0.9,
        equipment_inputs={"N_max": 20, "U_stage_max_V": 250000, "C_stage_F": 2e-6},
    )
    request_data["target"]["crest_V"] = 3000000
    request_data["load"]["C_F"] = 900e-12
    request_data["setup"].update(divider_C_F=400e-12, stray_C_F=100e-12, stray_L_H=10e-6)
    with TestClient(create_app(tmp_path, False)) as client:
        response = client.post("/v1/requests/validate", json=request_data)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["test"]["category"] == "Switching"
        assert result["request"]["impulse_profile_id"] == "switching_workbook_legacy_v1"
        assert len(result["input_sources"]) == 11
        assert all(
            value["source"] == "frontend_input" for value in result["input_sources"].values()
        )
        assert result["hardware"]["C_basic_F"] == 0
        assert set(result["hardware"]).isdisjoint(
            {"U_stack_max_V", "crest_max_V", "shots_per_minute"}
        )


def test_category_and_explicit_profile_must_agree(request_data, tmp_path):
    request_data.update(impulse_type="Switching", impulse_profile_id="lightning_project_v1")
    with TestClient(create_app(tmp_path, False)) as client:
        response = client.post("/v1/requests/validate", json=request_data)
        assert response.status_code == 422
        assert response.json()["code"] == "impulse_category_profile_mismatch"


def test_module_routes_and_idempotency(request_data, tmp_path):
    with TestClient(create_app(tmp_path, False)) as c:
        assert c.get("/health").status_code == 200
        response = c.post("/v1/requests/validate", json=request_data)
        assert response.status_code == 200, response.text
        ctx = response.json()
        assert c.get(f"/v1/requests/{ctx['context_id']}/constraints").status_code == 200
        body = {
            "request": request_data,
            "proposal": {"N": 9, "Rf_required_ohm": 50, "Rt_required_ohm": 25},
        }
        assembly = c.post("/v1/assemblies/realise", json=body)
        assert assembly.status_code == 200, assembly.text
        candidate = assembly.json()["candidate"]
        physics = c.post(
            "/v1/physics/evaluate", json={"request": request_data, "candidate": candidate}
        )
        assert physics.status_code == 200, physics.text
        assert physics.json()["metrics"]["crest_V"] == 1425000
        correction = c.post(
            "/v1/corrections/predict", json={"request": request_data, "candidate": candidate}
        )
        assert correction.json()["status"] == "unsupported"
        headers = {"Idempotency-Key": "test"}
        a = c.post("/v1/runs", json=request_data, headers=headers)
        b = c.post("/v1/runs", json=request_data, headers=headers)
        assert a.status_code == 202
        assert a.json()["run_id"] == b.json()["run_id"]
        ident = a.json()["run_id"]
        assert c.post(f"/v1/runs/{ident}/cancel").json()["cancel_requested"]
        assert c.get("/openapi.json").status_code == 200


def test_arbitrary_inline_and_registered_inventory(request_data, tmp_path):
    with TestClient(create_app(tmp_path, False)) as c:
        inv = {
            "source": "inline",
            "front": [
                {
                    "type_id": "special",
                    "nominal_ohm": 37.5,
                    "available_quantity": 10,
                    "quantity_scope": "global",
                }
            ],
            "tail": [{"type_id": "special", "nominal_ohm": 7.5, "available_quantity": 3}],
        }
        r = c.post("/v1/inventories/validate", json={"inventory": inv, "N": 4})
        assert r.status_code == 200, r.text
        assert r.json()["bounds"]["front"]["max_ohm"] == 75
        saved = c.post("/v1/inventories", json=inv).json()
        request_data["inventory"] = {
            "source": "registered",
            "profile_id": saved["profile_id"],
            "version": "1",
        }
        assert c.post("/v1/requests/validate", json=request_data).status_code == 200


def test_bad_request_and_forged_leaf(request_data, tmp_path):
    with TestClient(create_app(tmp_path, False)) as c:
        a = c.post(
            "/v1/assemblies/realise",
            json={
                "request": request_data,
                "proposal": {"N": 9, "Rf_required_ohm": 50, "Rt_required_ohm": 25},
            },
        ).json()["candidate"]
        a["front"]["equivalent_ohm"] = 49
        assert (
            c.post(
                "/v1/physics/evaluate", json={"request": request_data, "candidate": a}
            ).status_code
            == 422
        )
        request_data["equipment_profile_id"] = "unknown"
        assert c.post("/v1/requests/validate", json=request_data).status_code == 422
        assert c.get("/v1/runs/unknown").status_code == 404


def test_four_curve_endpoint(request_data, tmp_path):
    with TestClient(create_app(tmp_path, False)) as c:
        metrics = [
            {"front_s": 1.2e-6, "tail_s": 50e-6, "crest_V": v} for v in (1425000, 1420000, 1430000)
        ]
        r = c.post(
            "/v1/waveforms/reconstruct",
            json={"request": request_data, "candidate_metrics": metrics},
        )
        assert r.status_code == 200, r.text
        assert len(r.json()["curves"]) == 4


def test_measurement_rate_and_shape(tmp_path):
    with TestClient(create_app(tmp_path, False)) as c:
        d = {
            "acquired_at": "2026-10-10T12:00:00+05:30",
            "equipment_profile_id": "haefely_pdf_v1",
            "actual_settings": {"N": 2},
            "time_s": [0, 1e-6, 50e-6],
            "voltage_V": [0, 50000, 25000],
        }
        assert c.post("/v1/measurements", json=d).status_code == 201
        d["acquired_at"] = "2026-10-10T12:00:10+05:30"
        assert c.post("/v1/measurements", json=d).json()["shot_rate_status"] == "not_applicable"
        d["time_s"] = [0, 0, 1]
        assert c.post("/v1/measurements", json=d).status_code == 422


def test_restart_and_resume(tmp_path, request_data):
    with TestClient(create_app(tmp_path, False)) as client:
        ident = client.post("/v1/runs", json=request_data).json()["run_id"]
    with TestClient(create_app(tmp_path, False)) as client:
        assert client.get(f"/v1/runs/{ident}").json()["status"] == "interrupted"
        response = client.post(f"/v1/runs/{ident}/resume")
        assert response.status_code == 202
        assert not response.json()["budgets_reset"]
        assert client.post(f"/v1/runs/{ident}/resume").status_code == 409


def test_unknown_model_version(tmp_path, request_data):
    request_data["model_version"] = "unregistered"
    with TestClient(create_app(tmp_path, False)) as client:
        response = client.post("/v1/requests/validate", json=request_data)
        assert response.status_code == 422
        assert response.json()["code"] == "unknown_model_version"
