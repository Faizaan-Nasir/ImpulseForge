"""Export contracts, source evidence, fixtures and environment after local verification."""

import importlib.metadata
import inspect
import json
import platform
import shutil
from pathlib import Path

from pydantic import BaseModel

from powernext.api import app as api_contracts
from powernext.api.app import create_app
from powernext.contracts import models
from powernext.correction.data import workbook_fixture
from powernext.correction.model import ResidualModel
from powernext.correction.validation import file_hash
from powernext.dashboard import summary as summary_contracts
from powernext.performance.metrics import model_quality
from powernext.profiles.registry import (
    BENCHMARK,
    DOCS,
    DOCUMENT_PARAMETERS,
    PDF_PROFILE,
    TESTS,
    WORKBOOK_INPUTS,
)

BACKEND = Path(__file__).resolve().parents[1]
ARTIFACTS = BACKEND / "artifacts"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def main():
    api = DOCS / "api"
    write(api / "openapi.json", create_app(ARTIFACTS, False).openapi())
    for module in (models, api_contracts, summary_contracts):
        for name, value in inspect.getmembers(module, inspect.isclass):
            if issubclass(value, BaseModel) and value.__module__ == module.__name__:
                write(api / "schemas" / f"{name}.json", value.model_json_schema())
    for category in ("Lightning", "Switching"):
        request, proposal = workbook_fixture(category)
        write(
            BACKEND / "examples" / f"{category.lower()}_request.json",
            request.model_dump(mode="json"),
        )
        write(
            BACKEND / "examples" / f"{category.lower()}_module_input.json",
            {
                "request": request.model_dump(mode="json"),
                "proposal": proposal.model_dump(mode="json"),
            },
        )
        write(
            BACKEND / "tests" / "fixtures" / f"{category.lower()}_request.json",
            request.model_dump(mode="json"),
        )
    write(
        BACKEND / "examples" / "plot_metrics.json",
        [
            {"front_s": 1.2e-6, "tail_s": 50e-6, "crest_V": 1425000},
            {"front_s": 1.22e-6, "tail_s": 49e-6, "crest_V": 1420000},
            {"front_s": 1.18e-6, "tail_s": 51e-6, "crest_V": 1430000},
        ],
    )
    model = ResidualModel(ARTIFACTS / "models")
    write(
        DOCS / "model_performance_report.json",
        {
            "model_version": model.report()["model_version"],
            "categories": {c: model_quality(model.report(), c) for c in ("Lightning", "Switching")},
        },
    )
    sources = [
        p
        for p in DOCS.iterdir()
        if p.suffix.lower() in (".pdf", ".xlsx", ".md", ".json", ".py")
        and p.name
        not in (
            "source_manifest.json",
            "environment_report.json",
            "constraint_responsibility.json",
            "model_fit_report.json",
        )
    ]
    write(
        DOCS / "source_manifest.json",
        {
            "files": [
                {"name": p.name, "sha256": file_hash(p), "size_bytes": p.stat().st_size}
                for p in sorted(sources)
            ],
            "frontend_reference": {
                "url": "https://claude.ai/artifact/UbRz4HMvFDn8LUzFdiKqJo",
                "files": [
                    {"name": str(p.relative_to(DOCS)), "sha256": file_hash(p)}
                    for p in sorted((DOCS / "reference").glob("claude-dashboard.*"))
                ],
                "authority": "Visual reference; prior project constraints override illustrative values",
            },
            "authority": {
                "hardware": "Frontend workbook inputs; exactly two retained document energy limits plus capacitance fallback",
                "workbook_input_sheet": "Hybrid Calculator!B5:B15; Resistor Inventory",
                "retained_document_parameters": DOCUMENT_PARAMETERS,
                "workbook": "primary input-field definition; example values and synthetic diagnostic data",
                "architecture": "latest user instructions and technical Markdown",
            },
            "unresolved": [
                "capacitor transient/reverse ratings",
                "approved stage connections",
                "component ratings",
                "laboratory/environmental data",
            ],
        },
    )
    write(
        DOCS / "api" / "profiles.json",
        {
            "hardware": PDF_PROFILE,
            "benchmark": BENCHMARK,
            "tests": TESTS,
            "profile_role": "fallback templates; explicit equipment_inputs take precedence",
            "workbook_input_fields": WORKBOOK_INPUTS,
            "retained_document_parameters": DOCUMENT_PARAMETERS,
        },
    )
    write(DOCS / "model_fit_report.json", model.report())
    import torch

    write(
        DOCS / "environment_report.json",
        {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "packages": {
                d.metadata["Name"]: d.version
                for d in sorted(
                    importlib.metadata.distributions(), key=lambda d: d.metadata["Name"].lower()
                )
            },
            "device_used": "cpu",
            "cuda_available": torch.cuda.is_available(),
            "mps_available": torch.backends.mps.is_available(),
            "lockfile_sha256": file_hash(BACKEND / "uv.lock"),
            "model": model.report(),
            "backend_artifacts_directory": "backend/artifacts",
            "frontend": "React/Tailwind dashboard in frontend/; local Vite proxy",
        },
    )
    for name in (
        "tests.txt",
        "target-input-test.txt",
        "lint.txt",
        "typecheck.txt",
        "live-api-report.json",
        "model-explanation-report.json",
        "dashboard-api-report.json",
    ):
        source = ARTIFACTS / name
        if source.exists():
            destination = DOCS / "verification" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)


if __name__ == "__main__":
    main()
