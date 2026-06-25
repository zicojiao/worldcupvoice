from app.config import get_settings


def test_settings_accept_next_env_aliases(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("NEXT_PUBLIC_AGORA_APP_ID", "app-id")
    monkeypatch.setenv("NEXT_AGORA_APP_CERTIFICATE", "app-cert")
    monkeypatch.setenv("NEXT_PUBLIC_AGENT_UID", "111")
    monkeypatch.setenv("MATCH_FEED_UID", "222")

    settings = get_settings()

    assert settings.agora_app_id == "app-id"
    assert settings.agora_app_certificate == "app-cert"
    assert settings.agent_uid == 111
    assert settings.match_feed_uid == 222
    assert settings.commentary_interval_seconds == 4.0
    assert settings.commentary_frame_sample_seconds == 0.55
    assert settings.commentary_context_frames == 4
    assert settings.commentary_frame_width == 960
    assert settings.commentary_frame_jpeg_quality == 72
    assert settings.commentary_audio_sample_rate == 24000
    assert settings.commentary_audio_consume_interval_ms == 60
    assert settings.commentary_audio_backlog_limit_ms == 2500
    assert settings.commentary_audio_keepalive is False
    assert settings.elevenlabs_speed == 1.12
    assert settings.live_session_max_seconds == 900
    assert settings.viewer_heartbeat_timeout_seconds == 45
    assert settings.backend_api_secret is None
    assert settings.agora_area_code == "global"

    get_settings.cache_clear()


def test_settings_accept_agora_area_env(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("NEXT_PUBLIC_AGORA_APP_ID", "app-id")
    monkeypatch.setenv("NEXT_AGORA_APP_CERTIFICATE", "app-cert")
    monkeypatch.setenv("AGORA_AREA_CODE", "eu")

    settings = get_settings()

    assert settings.agora_area_code == "eu"

    get_settings.cache_clear()


def test_settings_accept_elevenlabs_tts_env(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("NEXT_PUBLIC_AGORA_APP_ID", "app-id")
    monkeypatch.setenv("NEXT_AGORA_APP_CERTIFICATE", "app-cert")
    monkeypatch.setenv("TTS_PROVIDER", "elevenlabs")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "eleven-key")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice-id")
    monkeypatch.setenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")
    monkeypatch.setenv("ELEVENLABS_SPEED", "1.18")

    settings = get_settings()

    assert settings.tts_provider == "elevenlabs"
    assert settings.elevenlabs_api_key == "eleven-key"
    assert settings.elevenlabs_voice_id == "voice-id"
    assert settings.elevenlabs_model == "eleven_flash_v2_5"
    assert settings.elevenlabs_output_format == "pcm_24000"
    assert settings.elevenlabs_speed == 1.18

    get_settings.cache_clear()


def test_settings_accept_fish_audio_tts_env(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("NEXT_PUBLIC_AGORA_APP_ID", "app-id")
    monkeypatch.setenv("NEXT_AGORA_APP_CERTIFICATE", "app-cert")
    monkeypatch.setenv("TTS_PROVIDER", "fish-audio")
    monkeypatch.setenv("FISH_AUDIO_API_KEY", "fish-key")
    monkeypatch.setenv("FISH_AUDIO_VOICE_ID", "fish-voice")
    monkeypatch.setenv("FISH_AUDIO_MODEL", "s2-pro")
    monkeypatch.setenv("FISH_AUDIO_SAMPLE_RATE", "24000")
    monkeypatch.setenv("FISH_AUDIO_LATENCY", "balanced")
    monkeypatch.setenv("FISH_AUDIO_CHUNK_LENGTH", "150")
    monkeypatch.setenv("FISH_AUDIO_SPEED", "1.08")

    settings = get_settings()

    assert settings.tts_provider == "fish_audio"
    assert settings.fish_audio_api_key == "fish-key"
    assert settings.fish_audio_voice_id == "fish-voice"
    assert settings.fish_audio_model == "s2-pro"
    assert settings.fish_audio_format == "pcm"
    assert settings.fish_audio_sample_rate == 24000
    assert settings.fish_audio_latency == "balanced"
    assert settings.fish_audio_chunk_length == 150
    assert settings.fish_audio_speed == 1.08

    get_settings.cache_clear()


def test_elevenlabs_safe_mode_prefers_agora_stable_pcm(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("NEXT_PUBLIC_AGORA_APP_ID", "app-id")
    monkeypatch.setenv("NEXT_AGORA_APP_CERTIFICATE", "app-cert")
    monkeypatch.setenv("TTS_PROVIDER", "elevenlabs")
    monkeypatch.setenv("ELEVENLABS_OUTPUT_FORMAT", "pcm_24000")
    monkeypatch.setenv("COMMENTARY_AUDIO_SAMPLE_RATE", "24000")
    monkeypatch.setenv("COMMENTARY_AUDIO_AGORA_SAFE_MODE", "true")

    settings = get_settings()

    assert settings.elevenlabs_output_format == "pcm_16000"
    assert settings.commentary_audio_sample_rate == 16000

    get_settings.cache_clear()


def test_settings_accept_session_guard_env(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("NEXT_PUBLIC_AGORA_APP_ID", "app-id")
    monkeypatch.setenv("NEXT_AGORA_APP_CERTIFICATE", "app-cert")
    monkeypatch.setenv("LIVE_SESSION_MAX_SECONDS", "120")
    monkeypatch.setenv("VIEWER_HEARTBEAT_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("BACKEND_API_SECRET", "shared-secret")

    settings = get_settings()

    assert settings.live_session_max_seconds == 120
    assert settings.viewer_heartbeat_timeout_seconds == 12.5
    assert settings.backend_api_secret == "shared-secret"

    get_settings.cache_clear()
