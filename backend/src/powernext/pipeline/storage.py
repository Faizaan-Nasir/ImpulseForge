import json
from pathlib import Path
from threading import Lock
from uuid import uuid4

from sqlalchemy import Column, Integer, MetaData, String, Table, Text, create_engine, select


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 30}
        )
        md = MetaData()
        self.records = Table(
            "records",
            md,
            Column("kind", String, primary_key=True),
            Column("id", String, primary_key=True),
            Column("payload", Text),
        )
        self.events = Table(
            "events",
            md,
            Column("sequence", Integer, primary_key=True, autoincrement=True),
            Column("run_id", String, index=True),
            Column("payload", Text),
        )
        md.create_all(self.engine)
        with self.engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        self.lock = Lock()

    def save(self, kind, identifier, data):
        payload = json.dumps(data, allow_nan=False)
        with self.lock, self.engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO records(kind,id,payload) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload",
                (kind, identifier, payload),
            )

    def patch(self, kind, identifier, fields):
        # Lock before reading: disjoint worker/API updates must not erase cancellation.
        with self.lock, self.engine.connect() as conn:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            row = conn.execute(
                select(self.records.c.payload).where(
                    self.records.c.kind == kind, self.records.c.id == identifier
                )
            ).first()
            if row is None:
                conn.rollback()
                raise KeyError(identifier)
            merged = {**json.loads(row[0]), **fields}
            conn.exec_driver_sql(
                "UPDATE records SET payload=? WHERE kind=? AND id=?",
                (json.dumps(merged, allow_nan=False), kind, identifier),
            )
            conn.commit()
        return merged

    def get(self, kind, identifier):
        with self.engine.connect() as conn:
            row = conn.execute(
                select(self.records.c.payload).where(
                    self.records.c.kind == kind, self.records.c.id == identifier
                )
            ).first()
        return json.loads(row[0]) if row else None

    def list(self, kind):
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(self.records.c.id, self.records.c.payload).where(self.records.c.kind == kind)
            ).all()
        return [(r[0], json.loads(r[1])) for r in rows]

    def event(self, run_id, data):
        with self.engine.begin() as conn:
            conn.execute(
                self.events.insert().values(
                    run_id=run_id, payload=json.dumps(data, allow_nan=False)
                )
            )

    def event_page(self, run_id, after=0, limit=100):
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(self.events)
                .where(self.events.c.run_id == run_id, self.events.c.sequence > after)
                .order_by(self.events.c.sequence)
                .limit(limit)
            ).all()
        return [dict(sequence=r.sequence, **json.loads(r.payload)) for r in rows]

    def create_run(self, context, key=None):
        # Serialize idempotency lookup+creation within this service process.
        with self.lock:
            if key:
                existing = self.get("idempotency", key)
                if existing:
                    if existing["context_hash"] != context.context_hash:
                        raise ValueError("Idempotency key already used with different request")
                    return existing["run_id"], False
            identifier = uuid4().hex
            payload = {
                "run_id": identifier,
                "status": "queued",
                "context_id": context.context_id,
                "context_hash": context.context_hash,
                "counters": {},
                "cancel_requested": False,
            }
            with self.engine.begin() as conn:
                for kind, ident, data in [("run", identifier, payload)] + (
                    [
                        (
                            "idempotency",
                            key,
                            {"run_id": identifier, "context_hash": context.context_hash},
                        )
                    ]
                    if key
                    else []
                ):
                    conn.execute(
                        self.records.insert().values(kind=kind, id=ident, payload=json.dumps(data))
                    )
            return identifier, True
