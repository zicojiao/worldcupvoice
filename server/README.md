# WorldCupVoice Backend

FastAPI service for the live AI commentator. Agora Media Gateway receives OBS
RTMP outside this service; this backend waits for the fixed match feed UID,
subscribes to live RTC video frames with the Agora Python Server SDK, generates
visual commentary, and publishes AI audio/transcript back into the same Agora
channel.

## Local

Prepare the backend environment:

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env.local
```

Required variables:

Generate `BACKEND_API_SECRET` once and use the same value in the frontend
environment:

```bash
openssl rand -hex 32
```

```bash
AGORA_APP_ID=
AGORA_APP_CERTIFICATE=
BACKEND_API_SECRET=<same-generated-secret>
OPENAI_API_KEY=
```

OpenAI TTS works by default. For the best live commentator effect, use
ElevenLabs with a custom sportscaster voice:

```bash
TTS_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
ELEVENLABS_VOICE_ID_EN_SPORTSCASTER=
ELEVENLABS_VOICE_ID_FR_SPORTSCASTER=
```

For Chinese commentary voices, Fish Audio is also supported:

```bash
TTS_PROVIDER=fish_audio
FISH_AUDIO_API_KEY=
FISH_AUDIO_VOICE_ID_ZH_MEME=
FISH_AUDIO_VOICE_ID_ZH_TACTICAL=
```

Profile voice IDs are deployment config, not source code. Your public fork can
run without them because the backend falls back to OpenAI TTS when a selected
third-party profile has no profile-specific or generic configured voice ID.

In ElevenLabs, open **VoiceLab**, click **Create Voice**, choose **Voice
Design**, paste the prompt below, generate and save a sportscaster voice, then
copy its **Voice ID** into `ELEVENLABS_VOICE_ID`.

Suggested ElevenLabs voice prompt:

```text
Native English, neutral American broadcast style. Male, 35-50. Broadcast quality.

Persona: elite sports commentator. Emotion: explosive, urgent, passionate.

A powerful, resonant, high-energy voice built for live football and basketball commentary. Deep but agile timbre, crisp articulation, close-mic broadcast presence, and clean studio-quality audio. Speaks at a fast, rhythmic pace during live action, with sudden bursts of excitement, sharp emphasis on player names, and dramatic pauses after huge moments. The delivery should feel like a professional television play-by-play announcer calling a World Cup final: intense, emotionally invested, breathless during attacks, and thunderous when a goal or game-changing moment happens.
```

Start the backend after `.env.local` is filled:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Model, frame sampling, audio pacing, heartbeat, and session TTL defaults are set
in [`app/config.py`](./app/config.py). Leave them out of `.env.local` unless you
are intentionally tuning runtime behavior.

## Railway

Deploy this directory as a Docker service. Set env vars from
[`.env.example`](./.env.example), then set the frontend `AGENT_BACKEND_URL` to the
Railway public URL. Set the same `BACKEND_API_SECRET` in Railway and Vercel.

The service exposes:

- `GET /health`
- `POST /sessions/start`
- `POST /sessions/heartbeat`
- `POST /sessions/status`
- `POST /sessions/stop`

All `/sessions/*` endpoints require `X-WorldCupVoice-Backend-Secret` when
`BACKEND_API_SECRET` is set. Keep `/health` public for deployment checks.
