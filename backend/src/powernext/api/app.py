import csv
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from time import monotonic

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import AwareDatetime, Field, model_validator

from powernext.assembly.cp_sat import AssemblyEngine
from powernext.config import Settings
from powernext.contracts.models import (
    MODEL_VERSION,
    Candidate,
    CorrectionPrediction,
    DomainError,
    InlineInventory,
    Metrics,
    PerformanceReport,
    PhysicsEvaluation,
    Proposal,
    Record,
    RunRequest,
    WorkbookBaseline,
)
from powernext.correction.model import ResidualModel
from powernext.dashboard.attempts import attempt_history
from powernext.dashboard.baseline import reference_request, workbook_baseline
from powernext.dashboard.summary import DecisionSummary, SummaryRequest, generate_summary
from powernext.dashboard.view import cases_for_run, evidence, plot_bundle
from powernext.optimisation.objective import evaluate_objective
from powernext.performance.metrics import build_report, model_quality
from powernext.physics.forward import evaluate, inverse
from powernext.physics.plot_reconstruction import bundle
from powernext.pipeline.jobs import JobManager
from powernext.pipeline.storage import Store
from powernext.profiles.registry import digest, equipment, example_inventory, test_profile
from powernext.profiles.resolve import Context, resolve, stock_bounds


class ModuleInput(Record):
    request: RunRequest
    proposal: Proposal | None = None
    candidate: Candidate | None = None
    N: int | None = Field(default=None, ge=1)


class PlotInput(Record):
    request: RunRequest
    candidate_metrics: list[Metrics] = Field(default_factory=list, max_length=3)


class PerformanceInput(ModuleInput):
    observed_metrics: Metrics | None = None
    observation_provenance: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def observation_source(self):
        if (self.observed_metrics is None) != (self.observation_provenance is None):
            raise ValueError(
                "Observed metrics and observation provenance must be supplied together"
            )
        return self


class InventoryValidation(Record):
    inventory: InlineInventory
    N: int = Field(default=2, ge=1)


class CalibrationInput(Record):
    request: RunRequest
    candidate: Candidate
    measurement_id: str


class Measurement(Record):
    acquired_at: AwareDatetime
    equipment_profile_id: str
    actual_settings: dict
    time_s: list[float] = Field(min_length=3)
    voltage_V: list[float] = Field(min_length=3)
    provenance: str = "external_measured_trace"


def create_app(artifacts=None, schedule_jobs=True, settings=None):
    settings = settings or Settings()
    artifacts = Path(artifacts or settings.artifacts_dir)
    artifacts.mkdir(parents=True, exist_ok=True)
    database = artifacts / "powernext.sqlite"
    store = Store(database)
    jobs = JobManager(database, artifacts)
    assembly = AssemblyEngine()
    residual = ResidualModel(artifacts / "models")

    @asynccontextmanager
    async def lifespan(app):
        # Interrupted local worker jobs retain their history, rather than pretending completion.
        for ident, record in store.list("run"):
            if record["status"] in ("queued", "running"):
                elapsed = record.get("elapsed_seconds", 0.0)
                if record.get("worker_started_at_utc"):
                    elapsed = max(
                        elapsed,
                        record.get("started_epoch_elapsed_seconds", 0.0)
                        + (
                            datetime.now(UTC)
                            - datetime.fromisoformat(record["worker_started_at_utc"])
                        ).total_seconds(),
                    )
                store.patch(
                    "run",
                    ident,
                    {
                        "status": "interrupted",
                        "reason": "service_restart",
                        "elapsed_seconds": elapsed,
                    },
                )
        yield
        jobs.close()

    app = FastAPI(title="PowerNext Marx Generator Backend", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    app.state.jobs = jobs
    app.state.artifacts = artifacts
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Idempotency-Key"],
        expose_headers=["X-Processing-Time-Seconds"],
    )

    @app.middleware("http")
    async def response_timing(request, call_next):
        started = monotonic()
        response = await call_next(request)
        response.headers["X-Processing-Time-Seconds"] = f"{monotonic() - started:.9f}"
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse(
            status_code=422,
            content={"code": exc.code, "stage": exc.stage, "message": str(exc), "retryable": False},
        )

    def get(kind, ident):
        result = store.get(kind, ident)
        if result is None:
            raise HTTPException(404, detail=f"Unknown {kind}")
        return result

    def context(request):
        request = settings.with_search_defaults(request)
        saved = {i: r for i, r in store.list("inventory")}
        ctx = resolve(request, saved, residual.fingerprint)
        store.save("context", ctx.context_id, ctx.model_dump())
        return ctx

    def candidate_context(record):
        c = Candidate.model_validate(record["candidate"])
        ctx = Context.model_validate(get("context", c.context_hash[:24]))
        if ctx.context_hash != c.context_hash:
            raise DomainError("candidate_context_mismatch", "Candidate context mismatch")
        return c, ctx

    @app.get("/v1/dashboard/bootstrap")
    def dashboard_bootstrap():
        return {
            "inventory": example_inventory().model_dump(mode="json"),
            "profiles": {p: equipment(p) for p in ("haefely_pdf_v1", "workbook_benchmark_v1")},
            "tests": {
                "Lightning": test_profile("lightning_project_v1"),
                "Switching": test_profile("switching_workbook_legacy_v1"),
            },
            "gemini": {
                "model": settings.gemini_model,
                "configured": bool(
                    settings.gemini_api_key and settings.gemini_api_key.get_secret_value().strip()
                ),
            },
            "defaults": {
                "search": settings.search_defaults(),
                "physics_mode": "calculator",
                "ml_domain_policy": "diagnostic_extrapolation",
                "system_max_voltage_V": 400000,
                "load_C_F": 850e-12,
                "divider_C_F": 500e-12,
                "stray_C_F": 150e-12,
                "stray_L_H": 18.5e-6,
                "expected_voltage_efficiency": 0.82,
                "C_stage_F": 3e-6,
            },
            "capabilities": {
                "residual_ml": "calculator/workbook synthetic diagnostics only",
                "environment_correction": "not_modelled_current_dataset",
                "energy_limits_editable": False,
                "timing_targets_editable": True,
                "ranking_priority_scope": "Tie-breakers after S/J only; no learned ranking",
                "overshoot_certified": False,
            },
        }

    @app.post("/v1/dashboard/workbook-baseline", response_model=WorkbookBaseline)
    def dashboard_baseline(body: ModuleInput):
        ctx = context(reference_request(settings.with_search_defaults(body.request)))
        return workbook_baseline(ctx, assembly, residual)

    @app.get("/v1/runs")
    def list_runs(limit: int = Query(default=20, ge=1, le=100)):
        return {
            "items": [
                {
                    k: r.get(k)
                    for k in (
                        "run_id",
                        "status",
                        "context_id",
                        "returned_recommendations",
                        "stop_reason",
                        "performance",
                    )
                }
                for _, r in reversed(store.list("run"))
            ][:limit]
        }

    @app.get("/v1/runs/{identifier}/dashboard")
    def dashboard_result(identifier):
        state = get("run", identifier)
        ctx = Context.model_validate(get("context", state["context_id"]))
        cases, mode = cases_for_run(store, identifier, ctx)
        return {
            "run": state,
            "context": ctx.public(),
            "cases": cases,
            "display_mode": mode,
            "waveforms": plot_bundle(ctx, cases),
            "summary_evidence": evidence(ctx, state, cases, mode),
        }

    @app.post("/v1/runs/{identifier}/decision-summary", response_model=DecisionSummary)
    def decision_summary(identifier, body: SummaryRequest):
        state = get("run", identifier)
        ctx = Context.model_validate(get("context", state["context_id"]))
        cases, mode = cases_for_run(store, identifier, ctx)
        return generate_summary(settings, evidence(ctx, state, cases, mode), store, body.refresh)

    @app.post("/v1/candidates/{identifier}/diagnostic-evaluation")
    def diagnostic_candidate(identifier):
        original = get("candidate", identifier)
        c, ctx = candidate_context(original)
        started = monotonic()
        baseline = original["physics"]
        correction = residual.correct(ctx, c, baseline)
        record = {
            **original,
            "correction": correction,
            "objective": evaluate_objective(ctx, correction["corrected_metrics"])
            if correction.get("corrected_metrics")
            else None,
            "eligible": False,
            "cost": 2,
            "evaluation_mode": "diagnostic_inspection",
            "performance": build_report(
                ctx,
                c,
                baseline,
                correction,
                residual.report(),
                {
                    "scope": "diagnostic_correction_with_reused_physics",
                    "stage_seconds": {"correction": monotonic() - started},
                    "total_seconds": monotonic() - started,
                },
            ),
        }
        store.save("diagnostic_candidate", identifier, record)
        return record

    def required_candidate(body):
        if body.candidate is None:
            raise DomainError("missing_candidate", "Realised candidate required")
        return body.candidate

    def real_baseline(body, ctx):
        candidate = required_candidate(body)
        return candidate, evaluate(ctx, candidate)

    @app.get("/health")
    def health():
        return {"status": "ok", "frontend": "react_dashboard", "version": "0.1.0"}

    @app.get("/v1/profiles/equipment/{identifier}")
    def equipment_route(identifier):
        return equipment(identifier)

    @app.get("/v1/profiles/tests/{identifier}")
    def tests_route(identifier):
        return test_profile(identifier)

    @app.get("/v1/profiles/inventory/{identifier}")
    def inventory_route(identifier):
        return (
            example_inventory().model_dump()
            if identifier == "project_front10_tail12_v1"
            else get("inventory", identifier)
        )

    @app.post("/v1/inventories/validate")
    def validate_inventory(body: InventoryValidation):
        return {
            "inventory": body.inventory.model_dump(),
            "N": body.N,
            "bounds": stock_bounds(body.inventory, body.N),
        }

    @app.post("/v1/inventories", status_code=201)
    def register_inventory(body: InlineInventory):
        identifier = digest(body.model_dump())[:24]
        record = {
            "profile_id": identifier,
            "version": "1",
            "hash": digest(body.model_dump()),
            "inventory": body.model_dump(),
        }
        store.save("inventory", identifier, record)
        return record

    @app.get("/v1/models/{version}")
    def model_report(version):
        if version != MODEL_VERSION:
            raise DomainError("unknown_model_version", version, "correction")
        return residual.report()

    @app.get("/v1/models/{version}/performance")
    def model_performance(version):
        report = model_report(version)
        return {
            "model_version": version,
            "categories": {c: model_quality(report, c) for c in ("Lightning", "Switching")},
            "epochs_applicable": report["epochs_applicable"],
        }

    @app.post("/v1/requests/validate")
    def validate_request(body: RunRequest):
        return context(body).public()

    @app.get("/v1/requests/{identifier}/constraints")
    def request_constraints(identifier):
        return Context.model_validate(get("context", identifier)).public()

    @app.post("/v1/physics/inverse")
    def inverse_route(body: ModuleInput):
        ctx = context(body.request)
        N = (
            body.N
            if body.N is not None
            else body.proposal.N
            if body.proposal is not None
            else ctx.data["seed_N"]
        )
        return inverse(ctx, N)

    @app.post("/v1/assemblies/realise")
    def realise_route(body: ModuleInput):
        if body.proposal is None:
            raise DomainError("missing_proposal", "Proposal required")
        ctx = context(body.request)
        started = monotonic()
        candidate, report = assembly.realise(ctx, body.proposal)
        return {
            "candidate": candidate.model_dump(),
            "solver_report": report,
            "runtime": {"scope": "assembly", "total_seconds": monotonic() - started},
        }

    @app.post("/v1/physics/evaluate", response_model=PhysicsEvaluation)
    def physics_route(body: ModuleInput):
        ctx = context(body.request)
        started = monotonic()
        _, baseline = real_baseline(body, ctx)
        duration = monotonic() - started
        candidate = required_candidate(body)
        baseline["performance"] = build_report(
            ctx,
            candidate,
            baseline,
            {"status": "not_invoked"},
            residual.report(),
            {
                "scope": "physics_evaluation",
                "stage_seconds": {"physics": duration},
                "total_seconds": duration,
            },
        )
        return baseline

    @app.post("/v1/corrections/predict", response_model=CorrectionPrediction)
    def correction_route(body: ModuleInput):
        ctx = context(body.request)
        started = monotonic()
        candidate, baseline = real_baseline(body, ctx)
        physics_duration = monotonic() - started
        correction_started = monotonic()
        prediction = residual.correct(ctx, candidate, baseline)
        prediction["performance"] = build_report(
            ctx,
            candidate,
            baseline,
            prediction,
            residual.report(),
            {
                "scope": "physics_and_correction",
                "stage_seconds": {
                    "physics": physics_duration,
                    "correction": monotonic() - correction_started,
                },
                "total_seconds": monotonic() - started,
            },
        )
        return prediction

    @app.post("/v1/performance/evaluate", response_model=PerformanceReport)
    def performance_route(body: PerformanceInput):
        started = monotonic()
        ctx = context(body.request)
        timings = {"context": monotonic() - started}
        candidate = body.candidate
        if candidate is None:
            if body.proposal is None:
                raise DomainError(
                    "missing_candidate_or_proposal", "Supply an actual candidate or proposal"
                )
            section = monotonic()
            candidate, _ = assembly.realise(ctx, body.proposal)
            timings["assembly"] = monotonic() - section
        section = monotonic()
        baseline = evaluate(ctx, candidate)
        timings["physics"] = monotonic() - section
        section = monotonic()
        prediction = residual.correct(ctx, candidate, baseline)
        timings["correction"] = monotonic() - section
        return build_report(
            ctx,
            candidate,
            baseline,
            prediction,
            residual.report(),
            {
                "scope": "single_setup_diagnostic",
                "stage_seconds": timings,
                "total_seconds": monotonic() - started,
            },
            body.observed_metrics.model_dump() if body.observed_metrics else None,
            body.observation_provenance,
        )

    @app.post("/v1/objectives/evaluate")
    def objective_route(body: PlotInput):
        ctx = context(body.request)
        return [evaluate_objective(ctx, m.model_dump()) for m in body.candidate_metrics]

    @app.post("/v1/waveforms/reconstruct")
    def waveform_route(body: PlotInput):
        ctx = context(body.request)
        cs = [
            {
                "candidate_id": f"metric-fixture-{i}",
                "correction": {
                    "corrected_metrics": m.model_dump(),
                    "model_version": body.request.model_version,
                },
            }
            for i, m in enumerate(body.candidate_metrics, 1)
        ]
        return {
            **bundle(ctx, cs),
            "metrics_origin": "caller_supplied_fixture",
            "ml_inference_executed": False,
        }

    @app.post("/v1/runs", status_code=202)
    def create_run(body: RunRequest, idempotency_key: str | None = Header(default=None)):
        ctx = context(body)
        try:
            ident, created = store.create_run(ctx, idempotency_key)
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc)) from exc
        if created and schedule_jobs:
            try:
                jobs.submit(ctx, ident)
            except DomainError:
                record = get("run", ident)
                store.save(
                    "run", ident, {**record, "status": "interrupted", "reason": "worker_capacity"}
                )
                raise
        return {
            "run_id": ident,
            "context_id": ctx.context_id,
            "status_url": f"/v1/runs/{ident}",
            "created": created,
        }

    @app.get("/v1/runs/{identifier}")
    def run_route(identifier):
        return get("run", identifier)

    @app.get("/v1/runs/{identifier}/events")
    def events_route(
        identifier,
        after: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=1000),
    ):
        get("run", identifier)
        return store.event_page(identifier, after, limit)

    @app.get("/v1/runs/{identifier}/candidates")
    def candidates_route(
        identifier,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=1000),
    ):
        get("run", identifier)
        events = store.event_page(identifier, 0, 1000000)
        ids = list(
            dict.fromkeys(
                e["candidate_id"] for e in events if e["pipeline_stage_name"] == "evaluation"
            )
        )
        return {
            "total": len(ids),
            "items": [get("candidate", i) for i in ids[offset : offset + limit]],
        }

    @app.get("/v1/runs/{identifier}/attempts")
    def attempts_route(
        identifier,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=1000),
    ):
        state = get("run", identifier)
        ctx = Context.model_validate(get("context", state["context_id"]))
        rows = attempt_history(store, identifier, ctx)
        return {
            "run_id": identifier,
            "total": len(rows),
            "proposal_count": len({row["attempt_number"] for row in rows}),
            "offset": offset,
            "limit": limit,
            "ordering": "proposal then ML evaluation, from first to last; repeated proposals retained",
            "items": rows[offset : offset + limit],
        }

    @app.get("/v1/runs/{identifier}/result")
    def result_route(identifier):
        get("run", identifier)
        result = store.get("result", identifier)
        if result is None:
            raise HTTPException(409, detail="Run result not yet available")
        return result

    @app.get("/v1/runs/{identifier}/waveforms")
    def waveform_bundle(identifier, format: str = "json"):
        data = get("waveforms", identifier)
        if format == "json":
            return data
        if format != "csv":
            raise HTTPException(422, detail="format must be json or csv")
        output = StringIO()
        writer = csv.writer(output)
        curves = [c for c in data["curves"] if c.get("voltage_V") is not None]
        writer.writerow(["time_s"] + [c["curve_id"] + "_voltage_V" for c in curves])
        for row in zip(data["time_s"], *(c["voltage_V"] for c in curves)):
            writer.writerow(row)
        return Response(output.getvalue(), media_type="text/csv")

    @app.get("/v1/candidates/{identifier}")
    def candidate_route(identifier):
        return get("candidate", identifier)

    @app.get("/v1/candidates/{identifier}/performance")
    def candidate_performance(identifier):
        record = get("candidate", identifier)
        return record.get("performance") or {
            "status": "unavailable",
            "reason": "Candidate predates performance capture or is a fixture",
        }

    @app.get("/v1/candidates/{identifier}/generator-stages")
    def generator_stages(identifier):
        e = get("candidate", identifier)
        from powernext.recommendations.serialise import generator_stage_records

        return generator_stage_records(e)

    @app.get("/v1/candidates/{identifier}/explanations")
    def explanation_route(identifier):
        e = get("candidate", identifier)
        c = Candidate.model_validate(e["candidate"])
        contexts = [Context.model_validate(r) for _, r in store.list("context")]
        ctx = next((x for x in contexts if x.context_hash == c.context_hash), None)
        if ctx is None:
            raise HTTPException(404, detail="Candidate context unavailable")
        return residual.explain(ctx, c, e["physics"])

    @app.get("/v1/candidates/{identifier}/waveforms/{kind}")
    def candidate_waveform(identifier, kind):
        e = get("candidate", identifier)
        if kind == "physics":
            return e["physics"]["trace"] or {
                "status": "unavailable",
                "reason": "Calculator has no trace",
            }
        if kind == "measured":
            return {"status": "unavailable", "reason": "No linked measured shot"}
        if kind == "ml_parameter_reconstruction":
            if e["correction"].get("corrected_metrics") is None:
                return {"status": "unavailable", "reason": "No supported correction"}
            contexts = [Context.model_validate(r) for _, r in store.list("context")]
            ctx = next(x for x in contexts if x.context_hash == e["candidate"]["context_hash"])
            return bundle(ctx, [e])
        raise HTTPException(422, detail="Unknown trace kind")

    @app.post("/v1/runs/{identifier}/resume", status_code=202)
    def resume(identifier):
        record = get("run", identifier)
        if record["status"] != "interrupted":
            raise HTTPException(409, detail="Only interrupted runs may resume")
        ctx = Context.model_validate(get("context", record["context_id"]))
        store.save(
            "run",
            identifier,
            {
                **record,
                "status": "queued",
                "cancel_requested": False,
                "resume_count": record.get("resume_count", 0) + 1,
            },
        )
        if schedule_jobs:
            try:
                jobs.submit(ctx, identifier)
            except DomainError:
                store.save("run", identifier, {**record, "status": "interrupted"})
                raise
        return {"run_id": identifier, "resume_mode": "warm_start_replay", "budgets_reset": False}

    @app.post("/v1/runs/{identifier}/cancel")
    def cancel(identifier):
        record = get("run", identifier)
        if record["status"] not in ("running", "queued"):
            raise HTTPException(409, detail="Run is not active")
        store.patch("run", identifier, {"cancel_requested": True})
        return {"run_id": identifier, "cancel_requested": True}

    @app.post("/v1/measurements", status_code=201)
    def measurement_route(body: Measurement):
        import math

        if (
            body.time_s[0] < 0
            or len(body.time_s) != len(body.voltage_V)
            or not all(math.isfinite(x) for x in body.time_s + body.voltage_V)
            or not all(a < b for a, b in zip(body.time_s, body.time_s[1:]))
        ):
            raise DomainError(
                "invalid_measured_trace",
                "Equal-length finite arrays and increasing time required",
                "measurement",
            )
        equipment(body.equipment_profile_id)  # Validate profile identity only.
        payload = body.model_dump(mode="json")
        ident = digest(payload)[:24]
        record = {
            **payload,
            "measurement_id": ident,
            "shot_rate_status": "not_applicable",
            "violations": [],
            "shot_rate_policy": "No problem-statement shot-rate restriction imported",
            "provenance": "external_measured_trace",
            "physical_shot_executed": False,
        }
        store.save("measurement", ident, record)
        return record

    @app.get("/v1/measurements/{identifier}")
    def get_measurement(identifier):
        return get("measurement", identifier)

    @app.post("/v1/calibration/labels")
    def calibration_labels(body: CalibrationInput):
        from powernext.calibration.labels import build_labels

        ctx = context(body.request)
        labels = build_labels(ctx, body.candidate, get("measurement", body.measurement_id))
        store.save("calibration_labels", digest(labels)[:24], labels)
        return labels

    return app


app = create_app()
