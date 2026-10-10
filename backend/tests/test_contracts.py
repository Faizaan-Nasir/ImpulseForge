import json
from pathlib import Path

import jsonschema
from test_physics import actual

from powernext.contracts.models import PhysicsEvaluation, RunRequest
from powernext.physics.forward import evaluate
from powernext.profiles.registry import DOCS


def test_json_schema_request_roundtrip(request_data):
    jsonschema.Draft202012Validator(RunRequest.model_json_schema()).validate(request_data)
    request = RunRequest.model_validate(request_data)
    assert RunRequest.model_validate_json(request.model_dump_json()) == request


def test_output_schema_roundtrip(context):
    baseline = evaluate(context, actual(context))
    jsonschema.Draft202012Validator(PhysicsEvaluation.model_json_schema()).validate(baseline)
    assert PhysicsEvaluation.model_validate(baseline).metrics.crest_V == 1425000


def test_committed_standalone_fixtures():
    for path in (Path(__file__).parent / "fixtures").glob("*_request.json"):
        raw = json.loads(path.read_text())
        jsonschema.Draft202012Validator(RunRequest.model_json_schema()).validate(raw)
    assert (DOCS / "api" / "openapi.json").exists()
