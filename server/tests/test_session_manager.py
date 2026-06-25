import asyncio

import pytest

from app.config import Settings
from app.models import CommentatorStats, StartSessionRequest
from app.session_manager import SessionManager


class FakeCommentator:
    instances: list["FakeCommentator"] = []

    def __init__(self, **kwargs: object):
        self.kwargs = kwargs
        self.started = False
        self.stopped = False
        self._stats = CommentatorStats()
        FakeCommentator.instances.append(self)

    def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    def stats(self) -> CommentatorStats:
        return self._stats


def _settings() -> Settings:
    return Settings(
        agora_app_id="app-id",
        agora_app_certificate="app-cert",
        openai_api_key="openai-key",
    )


def _guarded_settings(
    *,
    live_session_max_seconds: float = 10,
    viewer_heartbeat_timeout_seconds: float = 10,
) -> Settings:
    settings = _settings()
    settings.live_session_max_seconds = live_session_max_seconds
    settings.viewer_heartbeat_timeout_seconds = viewer_heartbeat_timeout_seconds
    return settings


def _request(channel_name: str) -> StartSessionRequest:
    return StartSessionRequest(
        requester_id="browser-user",
        channel_name=channel_name,
    )


@pytest.fixture(autouse=True)
def reset_fakes():
    FakeCommentator.instances = []


@pytest.mark.asyncio
async def test_start_replaces_existing_live_session(monkeypatch):
    monkeypatch.setattr("app.session_manager.BackendVisionCommentator", FakeCommentator)
    manager = SessionManager(_settings())

    await manager.start(_request("first-channel"))
    await manager.start(_request("second-channel"))

    assert FakeCommentator.instances[0].stopped
    assert FakeCommentator.instances[1].started
    assert len(manager._sessions) == 1
    await manager.close()


@pytest.mark.asyncio
async def test_start_uses_agora_gateway_mode_and_passes_media_uid(monkeypatch):
    monkeypatch.setattr("app.session_manager.BackendVisionCommentator", FakeCommentator)
    manager = SessionManager(_settings())

    response = await manager.start(
        StartSessionRequest(
            requester_id="browser-user",
            channel_name="live-finals",
            media_uid=777,
            agent_uid=888,
        )
    )

    assert response.source_mode == "agora-gateway"
    assert response.media_uid == "777"
    assert response.agent_uid == "888"
    assert response.commentator_profile_id == "zh-cn-fish-meme"
    assert FakeCommentator.instances[0].kwargs["media_uid"] == 777
    assert "source_url" not in FakeCommentator.instances[0].kwargs
    await manager.close()


@pytest.mark.asyncio
async def test_start_uses_selected_commentator_profile(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_VOICE_ID_EN_SPORTSCASTER", "public-demo-voice")
    monkeypatch.setattr("app.session_manager.BackendVisionCommentator", FakeCommentator)
    manager = SessionManager(_settings())

    response = await manager.start(
        StartSessionRequest(
            requester_id="browser-user",
            channel_name="live-finals",
            commentator_profile_id="en-us-sportscaster",
        )
    )

    assert response.commentator_profile_id == "en-us-sportscaster"
    assert response.commentator_profile_label == "English Sportscaster"
    assert FakeCommentator.instances[0].kwargs["profile"].id == "en-us-sportscaster"
    assert FakeCommentator.instances[0].kwargs["settings"].tts_provider == "elevenlabs"
    assert (
        FakeCommentator.instances[0].kwargs["settings"].elevenlabs_voice_id
        == "public-demo-voice"
    )
    await manager.close()


@pytest.mark.asyncio
async def test_profile_without_configured_voice_falls_back_to_openai(monkeypatch):
    monkeypatch.setattr("app.session_manager.BackendVisionCommentator", FakeCommentator)
    manager = SessionManager(_settings())

    await manager.start(
        StartSessionRequest(
            requester_id="browser-user",
            channel_name="live-finals",
            commentator_profile_id="zh-cn-fish-meme",
        )
    )

    assert FakeCommentator.instances[0].kwargs["profile"].id == "zh-cn-fish-meme"
    assert FakeCommentator.instances[0].kwargs["settings"].tts_provider == "openai"
    await manager.close()


@pytest.mark.asyncio
async def test_start_rolls_back_partial_session_on_failure(monkeypatch):
    class FailingCommentator(FakeCommentator):
        def start(self) -> None:
            raise RuntimeError("commentator failed")

    monkeypatch.setattr("app.session_manager.BackendVisionCommentator", FailingCommentator)
    manager = SessionManager(_settings())

    with pytest.raises(RuntimeError, match="commentator failed"):
        await manager.start(_request("broken-channel"))

    assert FailingCommentator.instances[0].stopped
    assert manager._sessions == {}


@pytest.mark.asyncio
async def test_heartbeat_marks_session_active(monkeypatch):
    monkeypatch.setattr("app.session_manager.BackendVisionCommentator", FakeCommentator)
    manager = SessionManager(_guarded_settings())

    response = await manager.start(_request("heartbeat-channel"))
    before = next(iter(manager._sessions.values())).last_viewer_heartbeat_at

    assert await manager.heartbeat(session_id=response.session_id, agent_id=None)
    assert next(iter(manager._sessions.values())).last_viewer_heartbeat_at >= before
    assert await manager.heartbeat(session_id=None, agent_id=response.agent_id)
    assert not await manager.heartbeat(session_id="missing", agent_id=None)

    await manager.close()


@pytest.mark.asyncio
async def test_status_reports_idle_active_and_stopped(monkeypatch):
    monkeypatch.setattr("app.session_manager.BackendVisionCommentator", FakeCommentator)
    manager = SessionManager(_guarded_settings())

    response = await manager.start(_request("status-channel"))
    idle = await manager.status(session_id=response.session_id, agent_id=None)

    assert idle.state == "running"
    assert idle.ai_spending_state == "idle_no_video"
    assert idle.stats.frames_sampled == 0
    assert idle.events[-1].event == "session_started"

    FakeCommentator.instances[0]._stats = CommentatorStats(
        frames_sampled=3,
        vision_requests=1,
        tts_requests=1,
    )
    active = await manager.status(session_id=response.session_id, agent_id=None)

    assert active.ai_spending_state == "active"
    assert active.stats.vision_requests == 1

    await manager.stop(session_id=response.session_id, agent_id=None)
    stopped = await manager.status(session_id=response.session_id, agent_id=None)

    assert stopped.state == "stopped"
    assert stopped.ai_spending_state == "stopped"
    assert stopped.stop_reason == "explicit stop requested"
    assert stopped.events[-1].event == "session_stopped"


@pytest.mark.asyncio
async def test_viewer_heartbeat_timeout_stops_session(monkeypatch):
    monkeypatch.setattr("app.session_manager.BackendVisionCommentator", FakeCommentator)
    manager = SessionManager(
        _guarded_settings(
            live_session_max_seconds=10,
            viewer_heartbeat_timeout_seconds=0.05,
        )
    )

    response = await manager.start(_request("timeout-channel"))
    await asyncio.sleep(0.18)

    assert FakeCommentator.instances[0].stopped
    assert manager._sessions == {}
    status = await manager.status(session_id=response.session_id, agent_id=None)
    assert status.state == "stopped"
    assert status.stop_reason == "viewer heartbeat timeout reached"


@pytest.mark.asyncio
async def test_viewer_heartbeat_extends_session(monkeypatch):
    monkeypatch.setattr("app.session_manager.BackendVisionCommentator", FakeCommentator)
    manager = SessionManager(
        _guarded_settings(
            live_session_max_seconds=10,
            viewer_heartbeat_timeout_seconds=0.5,
        )
    )

    response = await manager.start(_request("kept-alive-channel"))
    await asyncio.sleep(0.1)
    assert await manager.heartbeat(session_id=response.session_id, agent_id=None)
    await asyncio.sleep(0.1)

    assert not FakeCommentator.instances[0].stopped
    assert len(manager._sessions) == 1
    await manager.close()


@pytest.mark.asyncio
async def test_live_session_max_age_stops_session(monkeypatch):
    monkeypatch.setattr("app.session_manager.BackendVisionCommentator", FakeCommentator)
    manager = SessionManager(
        _guarded_settings(
            live_session_max_seconds=0.05,
            viewer_heartbeat_timeout_seconds=10,
        )
    )

    await manager.start(_request("ttl-channel"))
    await asyncio.sleep(0.18)

    assert FakeCommentator.instances[0].stopped
    assert manager._sessions == {}
