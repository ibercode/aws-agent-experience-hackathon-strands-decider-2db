import asyncio
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from .auth import Auth
from .catalog import CURRENT_SCENARIO_VERSION, Catalog
from .config import Settings, settings
from .decisions import DecisionClient
from .engine import Engine
from .store import Conflict, LimitExceeded, Store


class CreateSession(BaseModel):
    scenarioId: Literal["incorrect-readback", "words-versus-actions", "missing-evidence"]
    scenarioVersion: Literal["1", "2", "3"] = CURRENT_SCENARIO_VERSION
    preset: Literal["missed", "partial", "complete"] = "partial"
    playback: Literal["typed", "spoken"] = "typed"


def create_app(config: Settings | None = None):
    config = config or settings()
    auth = Auth(config)
    store = Store(config)
    catalog = Catalog(config)
    engine = Engine(config, store, catalog, DecisionClient(config))

    @asynccontextmanager
    async def lifespan(app):
        yield
        await engine.shutdown()

    app = FastAPI(title="Clearance Gap · Air Traffic Controller Assistant", version="0.1.0", lifespan=lifespan,
                  docs_url=None if config.app_env == "production" else "/docs",
                  redoc_url=None if config.app_env == "production" else "/redoc",
                  openapi_url=None if config.app_env == "production" else "/openapi.json")
    app.state.engine, app.state.auth = engine, auth

    @app.middleware("http")
    async def private_responses(request: Request, call_next):
        response = await call_next(request)
        # Session records and access failures must never be shared by an intermediary cache.
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(Conflict)
    async def conflict_handler(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(LimitExceeded)
    async def limit_handler(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=429, content={"detail": str(exc)},
                            headers={"Retry-After": str(exc.retry_after)})

    async def identity(request: Request):
        return await auth.identity(request)

    async def owned(session_id: str, request: Request):
        user = await identity(request)
        try:
            return await engine.get(session_id, user.sub)
        except KeyError as exc:
            raise HTTPException(404, "Session not found") from exc
        except PermissionError as exc:
            raise HTTPException(404, "Session not found") from exc

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "providerMode": config.provider_mode, "authMode": config.auth_mode}

    @app.get("/api/config")
    async def public_config():
        return dict(authMode=config.auth_mode, providerMode=config.provider_mode,
                    issuer=config.issuer if config.auth_mode == "cognito" else None,
                    clientId=config.cognito_client_id, domain=config.cognito_domain,
                    requiredScope=config.cognito_required_scope)

    @app.get("/api/me")
    async def me(user=Depends(identity)):
        return {"id": user.sub, "name": user.name, "authMode": config.auth_mode}

    @app.get("/api/scenarios")
    async def scenarios(user=Depends(identity)):
        return await asyncio.to_thread(catalog.list)

    @app.get("/api/sessions")
    async def sessions(user=Depends(identity)):
        return await asyncio.to_thread(store.list_sessions, user.sub)

    @app.post("/api/sessions", status_code=201)
    async def create_session(body: CreateSession, idempotency_key: Annotated[str, Header(min_length=8, max_length=128)],
                             user=Depends(identity)):
        try:
            session = await engine.create(user.sub, body.model_dump(), idempotency_key)
            return engine.view(session)
        except (KeyError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/sessions/{session_id}")
    async def session_view(session=Depends(owned)):
        async with session.lock:
            return engine.view(session)

    @app.post("/api/sessions/{session_id}/{operation}")
    async def control(operation: Literal["start", "pause", "resume"],
                      idempotency_key: Annotated[str, Header(min_length=8, max_length=128)],
                      session=Depends(owned)):
        await engine.control(session, operation, idempotency_key)
        return engine.view(session)

    return app
