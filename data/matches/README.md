# Match Context

**One match = one JSON file in this folder.** Each file describes the game in a
clip so the AI commentator can identify teams and players and call the action in
context. This is metadata only — it is sent to the model as a prompt, not shown
to viewers.

> ⚠️ **You must fill this in to match YOUR video.** The bundled
> [`argentina-france-2022-final.json`](./argentina-france-2022-final.json) is an
> **example** for our test clip. If you stream a different match, the rosters
> and kit colors here will be wrong and the AI will misname players.

## Add your own match

1. Copy [`_template.json`](./_template.json) to a new file, e.g.
   `data/matches/my-match.json`. (`_template.json` is a scaffold and is not
   loaded by the app.)
2. Fill in the fields — especially **jersey colors** and **rosters** (shirt
   number → name), which is what lets the AI tell players apart on screen.
3. Register it in [`lib/commentary.ts`](../../lib/commentary.ts): import the JSON
   and add it to `COMMENTARY_MATCHES`. The booth uses `COMMENTARY_MATCHES[0]`,
   so put the match you are streaming first.

## Field reference

| Field | Purpose |
| --- | --- |
| `homeTeam` / `awayTeam` (+ `Abbr`) | Team names. |
| `homeJerseyColor` / `awayJerseyColor` | Kit description — critical for telling teams apart. |
| `homeRoster` / `awayRoster` | Players: `number`, `name`, `shortName`, `role` (`starter`/`bench`/`dnp`), optional `position`, `notes`. |
| `playerIdentificationNotes` | Rules for when to name a player vs. use a generic role. |
| `broadcastNotes` | Vocabulary, cadence, and the situation at clip start. |
| `finalScore` | Private metadata only — instruct the AI not to announce it live. |
| `storyline` | One or two sentences framing the moment. |
| `posterUrl` | Pre-call poster image under `public/`. |

The more accurate this is, the better the AI grounds its commentary in what is
actually on screen.
