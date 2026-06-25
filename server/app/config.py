from functools import lru_cache
import os

from pydantic import BaseModel, Field


def _first_env(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


class Settings(BaseModel):
    agora_app_id: str = Field(min_length=1)
    agora_app_certificate: str = Field(min_length=1)
    agora_area_code: str = "global"
    openai_api_key: str | None = None
    openai_vision_model: str = "gpt-5.4-mini"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "alloy"
    tts_provider: str = "openai"
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str | None = None
    elevenlabs_model: str = "eleven_flash_v2_5"
    elevenlabs_output_format: str = "pcm_24000"
    elevenlabs_stability: float = 0.35
    elevenlabs_similarity_boost: float = 0.8
    elevenlabs_style: float = 0.35
    elevenlabs_speed: float = 1.12
    elevenlabs_use_speaker_boost: bool = True
    elevenlabs_streaming: bool = True
    agent_uid: int = 123456
    match_feed_uid: int = 234567
    token_expire_seconds: int = 3600
    commentary_interval_seconds: float = 4.0
    commentary_frame_sample_seconds: float = 0.55
    commentary_context_frames: int = 4
    commentary_frame_width: int = 960
    commentary_frame_jpeg_quality: int = 72
    commentary_audio_sample_rate: int = 24000
    commentary_audio_consume_interval_ms: int = 60
    commentary_audio_backlog_limit_ms: int = 2500
    commentary_audio_keepalive: bool = False
    live_session_max_seconds: float = 900.0
    viewer_heartbeat_timeout_seconds: float = 45.0
    backend_api_secret: str | None = None
    log_dir: str = "./agora_rtc_log"


@lru_cache
def get_settings() -> Settings:
    app_id = _first_env("AGORA_APP_ID", "NEXT_PUBLIC_AGORA_APP_ID")
    app_certificate = _first_env("AGORA_APP_CERTIFICATE", "NEXT_AGORA_APP_CERTIFICATE")
    tts_provider = os.getenv("TTS_PROVIDER", "openai").lower()
    elevenlabs_output_format = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "pcm_24000")
    commentary_audio_sample_rate = int(os.getenv("COMMENTARY_AUDIO_SAMPLE_RATE", "24000"))
    commentary_audio_safe_mode = (
        os.getenv("COMMENTARY_AUDIO_AGORA_SAFE_MODE", "false").lower()
        not in {"0", "false", "no"}
    )
    if tts_provider == "elevenlabs" and commentary_audio_safe_mode:
        elevenlabs_output_format = "pcm_16000"
        commentary_audio_sample_rate = 16000
    if not app_id or not app_certificate:
        raise RuntimeError(
            "Missing Agora credentials. Set AGORA_APP_ID and AGORA_APP_CERTIFICATE."
        )

    return Settings(
        agora_app_id=app_id,
        agora_app_certificate=app_certificate,
        agora_area_code=os.getenv("AGORA_AREA_CODE", "global").lower(),
        openai_api_key=_first_env(
            "OPENAI_API_KEY",
            "NEXT_OPENAI_API_KEY",
            "NEXT_LLM_API_KEY",
        ),
        openai_vision_model=os.getenv("OPENAI_VISION_MODEL", "gpt-5.4-mini"),
        openai_tts_model=os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
        openai_tts_voice=os.getenv("OPENAI_TTS_VOICE", "alloy"),
        tts_provider=tts_provider,
        elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY"),
        elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID"),
        elevenlabs_model=os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5"),
        elevenlabs_output_format=elevenlabs_output_format,
        elevenlabs_stability=float(os.getenv("ELEVENLABS_STABILITY", "0.35")),
        elevenlabs_similarity_boost=float(os.getenv("ELEVENLABS_SIMILARITY_BOOST", "0.8")),
        elevenlabs_style=float(os.getenv("ELEVENLABS_STYLE", "0.35")),
        elevenlabs_speed=float(os.getenv("ELEVENLABS_SPEED", "1.12")),
        elevenlabs_use_speaker_boost=os.getenv("ELEVENLABS_USE_SPEAKER_BOOST", "true").lower()
        not in {"0", "false", "no"},
        elevenlabs_streaming=os.getenv("ELEVENLABS_STREAMING", "true").lower()
        not in {"0", "false", "no"},
        agent_uid=int(os.getenv("AGENT_UID", os.getenv("NEXT_PUBLIC_AGENT_UID", "123456"))),
        match_feed_uid=int(os.getenv("MATCH_FEED_UID", "234567")),
        token_expire_seconds=int(os.getenv("AGORA_TOKEN_EXPIRE_SECONDS", "3600")),
        commentary_interval_seconds=float(os.getenv("COMMENTARY_INTERVAL_SECONDS", "4.0")),
        commentary_frame_sample_seconds=float(os.getenv("COMMENTARY_FRAME_SAMPLE_SECONDS", "0.55")),
        commentary_context_frames=int(os.getenv("COMMENTARY_CONTEXT_FRAMES", "4")),
        commentary_frame_width=int(os.getenv("COMMENTARY_FRAME_WIDTH", "960")),
        commentary_frame_jpeg_quality=int(os.getenv("COMMENTARY_FRAME_JPEG_QUALITY", "72")),
        commentary_audio_sample_rate=commentary_audio_sample_rate,
        commentary_audio_consume_interval_ms=int(
            os.getenv("COMMENTARY_AUDIO_CONSUME_INTERVAL_MS", "60")
        ),
        commentary_audio_backlog_limit_ms=int(
            os.getenv("COMMENTARY_AUDIO_BACKLOG_LIMIT_MS", "2500")
        ),
        commentary_audio_keepalive=os.getenv(
            "COMMENTARY_AUDIO_KEEPALIVE", "false"
        ).lower()
        not in {"0", "false", "no"},
        live_session_max_seconds=float(os.getenv("LIVE_SESSION_MAX_SECONDS", "900")),
        viewer_heartbeat_timeout_seconds=float(
            os.getenv("VIEWER_HEARTBEAT_TIMEOUT_SECONDS", "45")
        ),
        backend_api_secret=os.getenv("BACKEND_API_SECRET"),
        log_dir=os.getenv("AGORA_RTC_LOG_DIR", "./agora_rtc_log"),
    )
