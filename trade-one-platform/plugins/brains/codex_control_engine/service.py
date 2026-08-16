from __future__ import annotations

import os
from pathlib import Path

from .contracts import IntelligenceEnvelope
from .control_plane import ControlPlane
from .inference import ControlInference


def create_app():
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as error:
        raise RuntimeError('install with pip install -e ".[service]"') from error
    app = FastAPI(title="Codex Control Engine", version="0.1.0")
    control = ControlPlane(); artifact = Path(os.getenv("ARTIFACT_DIR", "artifacts")); inference = None
    def engine():
        nonlocal inference
        if inference is None:
            if not (artifact / "model.pt").exists(): raise HTTPException(503, "no trained challenger artifact")
            inference = ControlInference(artifact)
        return inference
    @app.get("/health")
    def health(): return {"ok": True, "mode": os.getenv("CONTROL_ENVIRONMENT", "shadow"), "model_available": (artifact / "model.pt").exists()}
    @app.post("/v1/ingest")
    def ingest(payload: dict):
        admission = control.admit(payload)
        if not admission.accepted: return {"status": admission.status, "reasons": admission.reasons}
        if os.getenv("INSTANCE_CONNECTION_NAME"):
            from .repository import CloudSqlRepository
            repository = CloudSqlRepository(); repository.initialize(); repository.put_record(admission.record)
        return {"status": "accepted", "record_id": admission.record.record_id, "payload_hash": admission.record.payload_hash}
    @app.post("/v1/enrich")
    def enrich(payload: dict):
        admission = control.admit(payload)
        if not admission.accepted and admission.status != "duplicate":
            raise HTTPException(422, {"status": admission.status, "reasons": admission.reasons})
        record = admission.record or IntelligenceEnvelope.from_dict(payload)
        result = engine().predict([record])[0]
        if os.getenv("INSTANCE_CONNECTION_NAME"):
            from .repository import CloudSqlRepository
            repository = CloudSqlRepository(); repository.initialize(); repository.put_intelligence(record.record_id, "challenger", result)
        return result
    return app


app = create_app()
