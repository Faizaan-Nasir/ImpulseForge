import argparse
import json
from pathlib import Path

from powernext.assembly.cp_sat import AssemblyEngine
from powernext.config import Settings
from powernext.contracts.models import Candidate, DomainError, Proposal, RunRequest
from powernext.correction.model import ResidualModel, fit_workbook
from powernext.optimisation.objective import evaluate_objective
from powernext.physics.forward import evaluate, inverse
from powernext.physics.plot_reconstruction import bundle
from powernext.profiles.resolve import resolve


def read_json(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser(description="PowerNext independent backend sections")
    parser.add_argument("--output", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    server = sub.add_parser("serve")
    server.add_argument("--port", type=int, default=Settings().port)
    server.add_argument(
        "--reload", action="store_true", help="Reload the local API after source changes"
    )
    sub.add_parser("fit")
    sub.add_parser("model-report")
    for name in ("validate", "inverse", "realise", "physics", "correct", "objective", "waveforms"):
        module = sub.add_parser(name)
        module.add_argument("request", type=Path)
        if name in ("inverse", "realise"):
            module.add_argument("--N", type=int, required=True)
        if name == "realise":
            module.add_argument("--rf", type=float, required=True)
            module.add_argument("--rt", type=float, required=True)
        if name in ("physics", "correct"):
            module.add_argument("candidate", type=Path)
        if name in ("objective", "waveforms"):
            module.add_argument("metrics", type=Path)
    args = parser.parse_args()
    settings = Settings()
    models = ResidualModel(settings.artifacts_dir / "models")
    try:
        if args.command == "serve":
            import uvicorn

            uvicorn.run(
                "powernext.api.app:app",
                host=settings.host,
                port=args.port,
                workers=1,
                reload=args.reload,
                reload_dirs=[str(Path(__file__).resolve().parents[1])] if args.reload else None,
            )
            return
        if args.command == "fit":
            result = fit_workbook(settings.artifacts_dir / "models")
        elif args.command == "model-report":
            result = models.report()
        else:
            ctx = resolve(
                RunRequest.model_validate(read_json(args.request)),
                model_bundle_hash=models.fingerprint,
            )
            if args.command == "validate":
                result = ctx.public()
            elif args.command == "inverse":
                result = inverse(ctx, args.N)
            elif args.command == "realise":
                candidate, report = AssemblyEngine().realise(
                    ctx, Proposal(N=args.N, Rf_required_ohm=args.rf, Rt_required_ohm=args.rt)
                )
                result = {"candidate": candidate.model_dump(mode="json"), "solver_report": report}
            elif args.command in ("physics", "correct"):
                raw = read_json(args.candidate)
                candidate = Candidate.model_validate(raw.get("candidate", raw))
                baseline = evaluate(ctx, candidate)
                result = (
                    baseline
                    if args.command == "physics"
                    else models.correct(ctx, candidate, baseline)
                )
            elif args.command == "objective":
                result = evaluate_objective(ctx, read_json(args.metrics))
            else:
                metrics = read_json(args.metrics)
                result = bundle(
                    ctx,
                    [
                        {
                            "candidate_id": f"fixture-{i}",
                            "correction": {
                                "corrected_metrics": m,
                                "model_version": ctx.request.model_version,
                            },
                        }
                        for i, m in enumerate(metrics)
                    ],
                )
        encoded = json.dumps(result, indent=2, allow_nan=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded + "\n")
        else:
            print(encoded)
    except DomainError as exc:
        parser.exit(
            2, json.dumps({"code": exc.code, "stage": exc.stage, "message": str(exc)}) + "\n"
        )
