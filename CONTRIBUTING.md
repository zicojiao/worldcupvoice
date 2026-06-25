# Contributing to WorldCupVoice

Thanks for taking a look. WorldCupVoice is an AI commentator for World Cup live
streams. The product goal is simple: let AI watch the match, call the action in
a commentator voice, and make live football moments easier to share while World
Cup attention is peaking.

Changes should keep the live commentary path intact:

```text
OBS / licensed encoder -> Agora Media Gateway -> Agora RTC -> browser + AI commentator
```

## Setup

```bash
git clone <your-fork-url>
cd WorldCupVoice
pnpm install
cp .env.example .env.local
```

For backend work:

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env.local
```

Fill local env files with your own Agora/OpenAI/ElevenLabs credentials. Do not
commit secrets or generated provider metadata.

## Development

- Keep the browser as a subscriber, not a video-frame capture source.
- Keep Media Gateway as the live ingest path.
- Keep AI sessions explicit and stoppable; new background loops need clear stop
  conditions and logs.
- Prefer small, observable changes over hidden behavior.
- Add or update tests when changing token generation, session lifecycle, audio
  pacing, frame sampling, or prompt assembly.

## Checks

Run these before opening a pull request:

```bash
pnpm run lint
pnpm run typecheck
pnpm run build

cd server
pytest
```

`pnpm run verify` runs the frontend lint, typecheck, and production build.

## Pull Requests

- Use a focused title and explain the AI commentary or live-media behavior you changed.
- Include screenshots for UI changes.
- Include logs or reproduction steps for backend/session bugs.
- Call out any new environment variables.

## License

By contributing, you agree that your contributions are licensed under the MIT
License.
