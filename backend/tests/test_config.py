import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from powernext.api.app import create_app
from powernext.config import Settings


def test_environment_budgets_reach_bootstrap_and_omitted_request_fields(
    monkeypatch, request_data, tmp_path
):
    monkeypatch.setenv("POWERNEXT_CALIBRATION_WALL_TIME_SECONDS", "900")
    monkeypatch.setenv("POWERNEXT_CALIBRATION_MAX_ATTEMPTS", "41")
    settings = Settings(_env_file=None)
    request_data.pop("search")
    with TestClient(create_app(tmp_path, False, settings)) as client:
        defaults = client.get("/v1/dashboard/bootstrap").json()["defaults"]["search"]
        response = client.post("/v1/requests/validate", json=request_data)
        assert response.status_code == 200, response.text
        search = response.json()["request"]["search"]
        assert defaults["wall_time_seconds"] == search["wall_time_seconds"] == 900
        for key in ("max_proposals", "max_forward_evaluations", "max_ml_evaluations"):
            assert defaults[key] == search[key] == 41


def test_explicit_budgets_override_environment_and_stay_in_saved_context(request_data, tmp_path):
    settings = Settings(calibration_max_attempts=41, calibration_wall_time_seconds=900)
    request_data["search"] = {"max_proposals": 7, "wall_time_seconds": 120}
    with TestClient(create_app(tmp_path, False, settings)) as client:
        response = client.post("/v1/requests/validate", json=request_data)
        assert response.status_code == 200, response.text
        context = response.json()
        search = context["request"]["search"]
        assert search["max_proposals"] == 7 and search["wall_time_seconds"] == 120
        assert search["max_ml_evaluations"] == 41
        saved = client.get(f"/v1/requests/{context['context_id']}/constraints").json()
        assert saved["request"]["search"] == search
        # Environment changes apply to future contexts, not saved runs or resumes.
        settings.calibration_max_attempts = 20
        settings.calibration_wall_time_seconds = 600
        assert client.get(f"/v1/requests/{context['context_id']}/constraints").json() == saved


@pytest.mark.parametrize(
    "name,value",
    [
        ("POWERNEXT_CALIBRATION_MAX_ATTEMPTS", "0"),
        ("POWERNEXT_CALIBRATION_MAX_ATTEMPTS", "1.5"),
        ("POWERNEXT_CALIBRATION_MAX_ATTEMPTS", "10001"),
        ("POWERNEXT_CALIBRATION_WALL_TIME_SECONDS", "0"),
        ("POWERNEXT_CALIBRATION_WALL_TIME_SECONDS", "nan"),
        ("POWERNEXT_CALIBRATION_WALL_TIME_SECONDS", "inf"),
    ],
)
def test_invalid_environment_budgets_fail_configuration(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
