from __future__ import annotations

import os

from .config import load_pipelines
from .contracts import Mode
from .pipeline import request_from_dict


def create_app():
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as error:
        raise RuntimeError('install Trade One with the "api" extra') from error

    config_path = os.getenv("TRADE_ONE_CONFIG", "config/trade-one.json")
    registry, pipelines = load_pipelines(config_path)
    app = FastAPI(title="Trade One", version="0.1.0")

    @app.get("/health")
    def health():
        return {"status": "ok", "read_only": True, "components": registry.doctor()}

    @app.post("/v1/intelligence/pregame")
    def pregame(payload: dict):
        try:
            request = request_from_dict(payload)
            return pipelines[Mode.PREGAME].evaluate(request).to_dict()
        except (ValueError, RuntimeError, KeyError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/v1/intelligence/live")
    def live(payload: dict):
        try:
            request = request_from_dict(payload)
            return pipelines[Mode.LIVE].evaluate(request).to_dict()
        except (ValueError, RuntimeError, KeyError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return app

