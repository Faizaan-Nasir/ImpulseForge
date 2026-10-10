import logging
import multiprocessing
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

from powernext.pipeline.runner import run
from powernext.pipeline.storage import Store
from powernext.profiles.resolve import Context


def execute_job(database_path, context_data, run_id, artifacts):
    store = Store(database_path)
    try:
        run(Context.model_validate(context_data), run_id, store, Path(artifacts))
    except Exception as exc:
        logger.exception("Worker failed for run %s", run_id)
        previous = store.get("run", run_id) or {}
        store.save(
            "run",
            run_id,
            {
                **previous,
                "status": "failed",
                "error": {"type": type(exc).__name__, "message": str(exc)},
            },
        )
        store.event(run_id, {"pipeline_stage_name": "job_failure", "message": str(exc)})


class JobManager:
    def __init__(self, database, artifacts):
        self.database = database
        self.artifacts = artifacts
        self.processes = {}
        self.lock = Lock()
        self.max_workers = 2

    def submit(self, context, run_id):
        with self.lock:
            self.processes = {k: p for k, p in self.processes.items() if p.is_alive()}
            if len(self.processes) >= self.max_workers:
                from powernext.contracts.models import DomainError

                raise DomainError("worker_capacity", "Two local workers are already active", "jobs")
            self._start(context, run_id)

    def _start(self, context, run_id):
        process = multiprocessing.get_context("spawn").Process(
            target=execute_job,
            args=(str(self.database), context.model_dump(), run_id, str(self.artifacts)),
            daemon=True,
        )
        process.start()
        self.processes[run_id] = process

    def close(self):
        for process in self.processes.values():
            if process.is_alive():
                process.terminate()
            process.join(timeout=2)
