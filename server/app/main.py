import logging
import os
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .models import (
    HeartbeatSessionRequest,
    HeartbeatSessionResponse,
    SessionStatusRequest,
    SessionStatusResponse,
    StartSessionRequest,
    StartSessionResponse,
    StopSessionRequest,
    StopSessionResponse,
)
from .session_manager import SessionManager

SERVER_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = SERVER_DIR.parent

load_dotenv(SERVER_DIR / ".env")
load_dotenv(SERVER_DIR / ".env.local")
load_dotenv(REPO_DIR / ".env.local")

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger(__name__)

manager: SessionManager | None = None

BACKEND_SECRET_HEADER = "X-WorldCupVoice-Backend-Secret"


def _cors_allow_origins() -> list[str]:
    raw = os.getenv("BACKEND_CORS_ALLOW_ORIGINS", "").strip()
    if not raw:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


async def require_backend_secret(
    provided_secret: Annotated[str | None, Header(alias=BACKEND_SECRET_HEADER)] = None,
) -> None:
    settings = get_settings()
    expected_secret = settings.backend_api_secret
    if not expected_secret:
        return
    if not provided_secret or not secrets.compare_digest(provided_secret, expected_secret):
        raise HTTPException(status_code=401, detail="Invalid backend API secret.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    global manager
    settings = get_settings()
    if not settings.backend_api_secret:
        logger.warning(
            "BACKEND_API_SECRET is not set; session control endpoints are unprotected."
        )
    manager = SessionManager(settings)
    try:
        yield
    finally:
        if manager is not None:
            await manager.close()
            manager = None


app = FastAPI(
    title="WorldCupVoice Backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Content-Type", BACKEND_SECRET_HEADER],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/sessions/start",
    response_model=StartSessionResponse,
    dependencies=[Depends(require_backend_secret)],
)
async def start_session(request: StartSessionRequest) -> StartSessionResponse:
    if manager is None:
        raise HTTPException(status_code=503, detail="Session manager is not ready.")
    try:
        return await manager.start(request)
    except Exception as exc:
        logger.exception("Failed to start live session")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post(
    "/sessions/stop",
    response_model=StopSessionResponse,
    dependencies=[Depends(require_backend_secret)],
)
async def stop_session(request: StopSessionRequest) -> StopSessionResponse:
    if manager is None:
        raise HTTPException(status_code=503, detail="Session manager is not ready.")
    try:
        await manager.stop(session_id=request.session_id, agent_id=request.agent_id)
        return StopSessionResponse(success=True)
    except Exception as exc:
        logger.exception("Failed to stop live session")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post(
    "/sessions/heartbeat",
    response_model=HeartbeatSessionResponse,
    dependencies=[Depends(require_backend_secret)],
)
async def heartbeat_session(request: HeartbeatSessionRequest) -> HeartbeatSessionResponse:
    if manager is None:
        raise HTTPException(status_code=503, detail="Session manager is not ready.")
    try:
        is_running = await manager.heartbeat(
            session_id=request.session_id,
            agent_id=request.agent_id,
        )
        return HeartbeatSessionResponse(
            success=is_running,
            state="running" if is_running else "missing",
        )
    except Exception as exc:
        logger.exception("Failed to heartbeat live session")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post(
    "/sessions/status",
    response_model=SessionStatusResponse,
    dependencies=[Depends(require_backend_secret)],
)
async def status_session(request: SessionStatusRequest) -> SessionStatusResponse:
    if manager is None:
        raise HTTPException(status_code=503, detail="Session manager is not ready.")
    try:
        return await manager.status(
            session_id=request.session_id,
            agent_id=request.agent_id,
        )
    except Exception as exc:
        logger.exception("Failed to read live session status")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
