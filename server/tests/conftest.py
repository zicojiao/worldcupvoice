import sys
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))

LOCAL_ENV_KEYS = {
    "AGORA_APP_ID",
    "AGORA_APP_CERTIFICATE",
    "NEXT_PUBLIC_AGORA_APP_ID",
    "NEXT_AGORA_APP_CERTIFICATE",
    "BACKEND_API_SECRET",
    "OPENAI_API_KEY",
    "NEXT_OPENAI_API_KEY",
    "NEXT_LLM_API_KEY",
    "TTS_PROVIDER",
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_VOICE_ID",
    "ELEVENLABS_VOICE_ID_EN_SPORTSCASTER",
    "ELEVENLABS_VOICE_ID_FR_SPORTSCASTER",
    "FISH_AUDIO_API_KEY",
    "FISH_AUDIO_VOICE_ID",
    "FISH_AUDIO_VOICE_ID_ZH_MEME",
    "FISH_AUDIO_VOICE_ID_ZH_TACTICAL",
}


@pytest.fixture(autouse=True)
def isolate_local_env(monkeypatch):
    for key in LOCAL_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
