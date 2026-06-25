import asyncio
import logging
import time
from collections import deque
from collections.abc import Iterable

from .backend_commentator import BackendVisionCommentator
from .config import Settings
from .models import (
    SessionLifecycleEvent,
    SessionStatusResponse,
    StartSessionRequest,
    StartSessionResponse,
)

logger = logging.getLogger(__name__)


class LiveSession:
    def __init__(
        self,
        *,
        session_id: str,
        agent_id: str,
        channel_name: str,
        commentator: BackendVisionCommentator,
        created_at: int,
        created_at_monotonic: float,
    ):
        self.session_id = session_id
        self.agent_id = agent_id
        self.channel_name = channel_name
        self.commentator = commentator
        self.created_at = created_at
        self.created_at_monotonic = created_at_monotonic
        self.last_viewer_heartbeat_at = created_at_monotonic
        self.last_viewer_heartbeat_ts = created_at
        self.stopped_at: int | None = None
        self.stop_reason: str | None = None
        self.events: deque[SessionLifecycleEvent] = deque(maxlen=40)
        self.monitor_task: asyncio.Task[None] | None = None


class SessionManager:
    RECORD_LIMIT = 100

    def __init__(self, settings: Settings):
        self._settings = settings
        self._sessions: dict[str, LiveSession] = {}
        self._records: dict[str, LiveSession] = {}
        self._lock = asyncio.Lock()

    async def start(self, request: StartSessionRequest) -> StartSessionResponse:
        async with self._lock:
            if not self._settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is required for realtime vision commentary.")

            existing_sessions = list(self._sessions.values())
            self._sessions.clear()
            await self._stop_live_sessions(
                existing_sessions,
                reason="replaced by newer live session",
            )

            agent_uid = request.agent_uid or self._settings.agent_uid
            media_uid = request.media_uid or self._settings.match_feed_uid
            session_id = f"{request.channel_name}:{media_uid}:{int(time.time())}"

            commentator = BackendVisionCommentator(
                settings=self._settings,
                channel_name=request.channel_name,
                agent_uid=agent_uid,
                match_context=request.match_context,
                media_uid=media_uid,
            )
            try:
                commentator.start()
            except Exception:
                await self._stop_live_sessions(
                    [
                        LiveSession(
                            session_id=session_id,
                            agent_id="startup-rollback",
                            channel_name=request.channel_name,
                            commentator=commentator,
                            created_at=int(time.time()),
                            created_at_monotonic=time.monotonic(),
                        )
                    ],
                    reason="startup rollback",
                )
                raise
            agent_id = f"backend-commentator-{request.channel_name}-{int(time.time())}"

            created_at = int(time.time())
            session = LiveSession(
                session_id=session_id,
                agent_id=agent_id,
                channel_name=request.channel_name,
                commentator=commentator,
                created_at=created_at,
                created_at_monotonic=time.monotonic(),
            )
            self._sessions[session_id] = session
            self._remember_session_record_locked(session)
            self._emit_event(
                session,
                "session_started",
                "Backend AI session started; waiting for OBS frames before AI vision spend.",
            )
            session.monitor_task = asyncio.create_task(
                self._monitor_session(session_id),
                name=f"live-session-monitor-{request.channel_name}",
            )
            logger.info("Started live session id=%s agent_id=%s", session_id, agent_id)

            return StartSessionResponse(
                session_id=session_id,
                agent_id=agent_id,
                create_ts=created_at,
                state="RUNNING",
                channel_name=request.channel_name,
                agent_uid=str(agent_uid),
                media_uid=str(media_uid),
                source_mode="agora-gateway",
                vision_mode="backend-openai-vision-rtc",
                warnings=[],
            )

    async def stop(self, *, session_id: str | None, agent_id: str | None) -> None:
        async with self._lock:
            session = None
            if session_id:
                session = self._sessions.pop(session_id, None)
            if session is None and agent_id:
                for key, candidate in list(self._sessions.items()):
                    if candidate.agent_id == agent_id:
                        session = self._sessions.pop(key)
                        break

        await self._stop_live_sessions(
            [session] if session is not None else [],
            reason="explicit stop requested",
        )

    async def heartbeat(self, *, session_id: str | None, agent_id: str | None) -> bool:
        async with self._lock:
            session = self._find_session_locked(session_id=session_id, agent_id=agent_id)
            if session is None:
                return False
            session.last_viewer_heartbeat_at = time.monotonic()
            session.last_viewer_heartbeat_ts = int(time.time())
            self._emit_event(
                session,
                "viewer_heartbeat",
                "Viewer heartbeat received; keeping backend AI session alive.",
            )
            return True

    async def status(
        self,
        *,
        session_id: str | None,
        agent_id: str | None,
    ) -> SessionStatusResponse:
        async with self._lock:
            session = self._find_session_locked(session_id=session_id, agent_id=agent_id)
            if session is None:
                session = self._find_record_locked(session_id=session_id, agent_id=agent_id)
            if session is None:
                return SessionStatusResponse(
                    success=False,
                    state="missing",
                    ai_spending_state="missing",
                    live_session_max_seconds=self._settings.live_session_max_seconds,
                    viewer_heartbeat_timeout_seconds=(
                        self._settings.viewer_heartbeat_timeout_seconds
                    ),
                )
            return self._build_status_locked(session)

    async def close(self) -> None:
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        await self._stop_live_sessions(sessions, reason="backend shutdown")

    def _find_session_locked(
        self,
        *,
        session_id: str | None,
        agent_id: str | None,
    ) -> LiveSession | None:
        if session_id:
            session = self._sessions.get(session_id)
            if session is not None:
                return session
        if agent_id:
            for session in self._sessions.values():
                if session.agent_id == agent_id:
                    return session
        return None

    def _find_record_locked(
        self,
        *,
        session_id: str | None,
        agent_id: str | None,
    ) -> LiveSession | None:
        if session_id:
            session = self._records.get(session_id)
            if session is not None:
                return session
        if agent_id:
            for session in self._records.values():
                if session.agent_id == agent_id:
                    return session
        return None

    def _build_status_locked(self, session: LiveSession) -> SessionStatusResponse:
        is_running = session.session_id in self._sessions
        now = time.monotonic()
        stats = session.commentator.stats()
        if not is_running:
            ai_spending_state = "stopped"
            state = "stopped"
        elif stats.frames_sampled > 0:
            ai_spending_state = "active"
            state = "running"
        else:
            ai_spending_state = "idle_no_video"
            state = "running"

        return SessionStatusResponse(
            success=True,
            state=state,
            ai_spending_state=ai_spending_state,
            session_id=session.session_id,
            agent_id=session.agent_id,
            channel_name=session.channel_name,
            created_at=session.created_at,
            stopped_at=session.stopped_at,
            stop_reason=session.stop_reason,
            last_viewer_heartbeat_at=session.last_viewer_heartbeat_ts,
            last_viewer_heartbeat_age_seconds=max(
                0.0,
                now - session.last_viewer_heartbeat_at,
            ),
            live_session_max_seconds=self._settings.live_session_max_seconds,
            viewer_heartbeat_timeout_seconds=(
                self._settings.viewer_heartbeat_timeout_seconds
            ),
            stats=stats,
            events=list(session.events)[-12:],
        )

    def _remember_session_record_locked(self, session: LiveSession) -> None:
        self._records[session.session_id] = session
        while len(self._records) > self.RECORD_LIMIT:
            oldest_session_id = next(iter(self._records))
            self._records.pop(oldest_session_id, None)

    def _emit_event(
        self,
        session: LiveSession,
        event: str,
        message: str,
        *,
        level: int = logging.INFO,
    ) -> None:
        lifecycle_event = SessionLifecycleEvent(
            event=event,
            message=message,
            created_at=int(time.time()),
        )
        session.events.append(lifecycle_event)
        logger.log(
            level,
            "SESSION_EVENT event=%s session_id=%s agent_id=%s channel=%s message=%s",
            event,
            session.session_id,
            session.agent_id,
            session.channel_name,
            message,
        )

    async def _monitor_session(self, session_id: str) -> None:
        poll_seconds = self._monitor_poll_seconds()
        try:
            while True:
                await asyncio.sleep(poll_seconds)
                now = time.monotonic()
                stop_reason = None
                session = None
                async with self._lock:
                    candidate = self._sessions.get(session_id)
                    if candidate is None:
                        return
                    session_age = now - candidate.created_at_monotonic
                    if session_age >= self._settings.live_session_max_seconds:
                        stop_reason = "max session age reached"
                    heartbeat_timeout = self._settings.viewer_heartbeat_timeout_seconds
                    heartbeat_age = now - candidate.last_viewer_heartbeat_at
                    if (
                        stop_reason is None
                        and heartbeat_timeout > 0
                        and heartbeat_age >= heartbeat_timeout
                    ):
                        stop_reason = "viewer heartbeat timeout reached"

                    if stop_reason is None:
                        continue

                    session = self._sessions.pop(session_id, None)

                if session is None:
                    return
                self._emit_event(
                    session,
                    "auto_stop_requested",
                    f"Auto-stopping backend AI session: {stop_reason}.",
                    level=logging.WARNING,
                )
                await self._stop_live_sessions([session], reason=stop_reason)
                return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Live session monitor failed id=%s", session_id, exc_info=True)

    def _monitor_poll_seconds(self) -> float:
        guard_seconds = self._settings.live_session_max_seconds
        if self._settings.viewer_heartbeat_timeout_seconds > 0:
            guard_seconds = min(
                guard_seconds,
                self._settings.viewer_heartbeat_timeout_seconds,
            )
        return max(0.05, min(5.0, guard_seconds / 3))

    async def _stop_live_sessions(
        self,
        sessions: list[LiveSession],
        *,
        reason: str,
    ) -> None:
        if not sessions:
            return

        logger.info(
            "Stopping %s existing live session(s), reason=%s",
            len(sessions),
            reason,
        )
        for session in sessions:
            self._emit_event(
                session,
                "stop_requested",
                f"Stopping backend AI session: {reason}.",
            )
        await self._cancel_monitor_tasks(session.monitor_task for session in sessions)
        results = await asyncio.gather(
            *(session.commentator.stop() for session in sessions),
            return_exceptions=True,
        )
        stopped_at = int(time.time())
        for session, result in zip(sessions, results, strict=False):
            session.stopped_at = stopped_at
            session.stop_reason = reason
            if isinstance(result, Exception):
                self._emit_event(
                    session,
                    "stop_failed",
                    f"Backend AI session stop raised: {type(result).__name__}.",
                    level=logging.WARNING,
                )
                logger.warning("Failed to stop a live session", exc_info=result)
            else:
                self._emit_event(
                    session,
                    "session_stopped",
                    f"Backend AI session stopped. AI spend is now off. Reason: {reason}.",
                )

    async def _cancel_monitor_tasks(
        self,
        tasks: Iterable[asyncio.Task[None] | None],
    ) -> None:
        current_task = asyncio.current_task()
        cancellable = [
            task
            for task in tasks
            if task is not None and task is not current_task and not task.done()
        ]
        for task in cancellable:
            task.cancel()
        if cancellable:
            await asyncio.gather(*cancellable, return_exceptions=True)
