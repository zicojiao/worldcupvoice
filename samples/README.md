# Sample Broadcast Clip

This folder is where you place a short football clip used as a **local RTMP
source** for development. It is not played by the product UI — the script pushes
it through Agora Media Gateway so the app and AI commentator receive it as live
Agora RTC video.

## No video is shipped (copyright)

Broadcast match footage is copyrighted and cannot be redistributed, so **no
source video is committed to this repo**. You need to supply your own football
match clip (any 16:9 `.mp4`). `samples/*.mp4` is gitignored so a local clip is
never committed by accident.

> For reference, the material used during local testing came from:
> https://www.youtube.com/watch?v=RgqKdplLIk4
> Obtain and use any third-party footage at your own responsibility.

## Tune the AI for your clip first

For grounded commentary, fill in the match context **before** streaming so the
AI knows who is on screen. Edit [`lib/commentary.ts`](../lib/commentary.ts):

- `homeTeam` / `awayTeam`, jersey colors, competition, venue
- `homeRoster` / `awayRoster` — shirt numbers, names, positions
- `playerIdentificationNotes` / `broadcastNotes` — how to name players and call
  the game
- `storyline` — the situation at the start of your clip

The closer this matches your video, the better the AI identifies players and
calls the action.

## Stream your clip

```bash
RTMP_STREAM_KEY=<your Agora Media Gateway stream key> \
RTMP_INPUT=/path/to/your-match.mp4 \
pnpm run stream:sample
```

If `RTMP_INPUT` is unset, the script streams the first `.mp4` it finds in
`samples/`. It loops the clip until you press `Ctrl+C`.
