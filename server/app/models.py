from typing import Literal

from pydantic import BaseModel, Field


class PlayerIdentity(BaseModel):
    number: str
    name: str
    shortName: str
    role: Literal["starter", "bench", "dnp"]
    position: str | None = None
    notes: str | None = None


class MatchContext(BaseModel):
    sport: str
    title: str
    competition: str
    venue: str
    homeTeam: str
    awayTeam: str
    gameDate: str | None = None
    localTipTime: str | None = None
    finalScore: str | None = None
    homeTeamAbbr: str | None = None
    awayTeamAbbr: str | None = None
    homeJerseyColor: str | None = None
    awayJerseyColor: str | None = None
    homeRoster: list[PlayerIdentity] = Field(default_factory=list)
    awayRoster: list[PlayerIdentity] = Field(default_factory=list)
    playerIdentificationNotes: list[str] = Field(default_factory=list)
    broadcastNotes: list[str] = Field(default_factory=list)
    storyline: str


class StartSessionRequest(BaseModel):
    requester_id: str = Field(min_length=1)
    channel_name: str = Field(min_length=1)
    source_mode: Literal["agora-gateway"] = "agora-gateway"
    match_context: MatchContext | None = None
    agent_uid: int | None = None
    media_uid: int | None = None


class StartSessionResponse(BaseModel):
    session_id: str
    agent_id: str
    create_ts: int
    state: Literal["RUNNING"]
    channel_name: str
    source_mode: Literal["agora-gateway"] = "agora-gateway"
    agent_uid: str
    media_uid: str
    vision_mode: Literal["agora-convoai-mllm", "backend-openai-vision-rtc"]
    warnings: list[str] = []


class StopSessionRequest(BaseModel):
    session_id: str | None = None
    agent_id: str | None = None


class StopSessionResponse(BaseModel):
    success: bool
    state: str = "stopped"


class HeartbeatSessionRequest(BaseModel):
    session_id: str | None = None
    agent_id: str | None = None


class HeartbeatSessionResponse(BaseModel):
    success: bool
    state: Literal["running", "missing"]


class SessionStatusRequest(BaseModel):
    session_id: str | None = None
    agent_id: str | None = None


class SessionLifecycleEvent(BaseModel):
    event: str
    message: str
    created_at: int


class CommentatorStats(BaseModel):
    frames_sampled: int = 0
    vision_requests: int = 0
    tts_requests: int = 0
    audio_sample_rate: int = 0
    audio_consume_interval_ms: int = 0
    audio_buffer_ms: int = 0
    audio_consume_calls: int = 0
    audio_consume_errors: int = 0
    audio_buffer_clears: int = 0
    audio_backlog_skips: int = 0
    audio_underflows: int = 0
    audio_keepalive_calls: int = 0
    audio_send_calls: int = 0
    audio_send_errors: int = 0
    audio_sent_ms: int = 0
    last_audio_send_ms: int | None = None
    last_audio_send_ret: int | None = None
    last_audio_send_gap_ms: int | None = None
    max_audio_send_gap_ms: int = 0
    slow_audio_send_gaps: int = 0
    last_audio_send_duration_ms: int | None = None
    max_audio_send_duration_ms: int = 0
    slow_audio_send_durations: int = 0
    last_consume_result: int | None = None
    audio_consumer_completed: bool = True
    last_audio_duration_ms: int | None = None
    last_frame_at: int | None = None
    last_commentary_at: int | None = None
    last_audio_at: int | None = None


class SessionStatusResponse(BaseModel):
    success: bool
    state: Literal["running", "stopped", "missing"]
    ai_spending_state: Literal["active", "idle_no_video", "stopped", "missing"]
    session_id: str | None = None
    agent_id: str | None = None
    channel_name: str | None = None
    created_at: int | None = None
    stopped_at: int | None = None
    stop_reason: str | None = None
    last_viewer_heartbeat_at: int | None = None
    last_viewer_heartbeat_age_seconds: float | None = None
    live_session_max_seconds: float | None = None
    viewer_heartbeat_timeout_seconds: float | None = None
    stats: CommentatorStats = Field(default_factory=CommentatorStats)
    events: list[SessionLifecycleEvent] = Field(default_factory=list)
