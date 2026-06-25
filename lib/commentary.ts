import type { CommentaryMatch, MatchContext } from '@/types/conversation';
import argentinaFrance2022Final from '@/data/matches/argentina-france-2022-final.json';

// ─── Match context ────────────────────────────────────────────────────────────
// Each match is one JSON file in `data/matches/`. This metadata is sent to the
// AI as a prompt so it can identify teams/players and call the action in
// context — it is NOT shown to viewers.
//
// ⚠️ FILL THIS IN FOR YOUR OWN VIDEO. The example below describes our test clip
// (the 2022 World Cup final). If you stream a different match, copy
// `data/matches/_template.json`, edit it, import it here, and list it FIRST —
// the booth uses COMMENTARY_MATCHES[0]. See `data/matches/README.md`.
//
// JSON imports widen `role`/`position` to `string`, so we assert the shape back
// to CommentaryMatch (the fields are documented in the template).
export const COMMENTARY_MATCHES: CommentaryMatch[] = [
  argentinaFrance2022Final as unknown as CommentaryMatch,
  // 👉 Add your own match: import its JSON above and put it first.
];

export function toMatchContext(match: CommentaryMatch): MatchContext {
  return {
    sport: match.sport,
    title: match.title,
    competition: match.competition,
    venue: match.venue,
    homeTeam: match.homeTeam,
    awayTeam: match.awayTeam,
    gameDate: match.gameDate,
    localTipTime: match.localTipTime,
    finalScore: match.finalScore,
    homeTeamAbbr: match.homeTeamAbbr,
    awayTeamAbbr: match.awayTeamAbbr,
    homeJerseyColor: match.homeJerseyColor,
    awayJerseyColor: match.awayJerseyColor,
    homeRoster: match.homeRoster,
    awayRoster: match.awayRoster,
    playerIdentificationNotes: match.playerIdentificationNotes,
    broadcastNotes: match.broadcastNotes,
    storyline: match.storyline,
  };
}
