import {
  type AgentTranscription,
  TurnStatus,
  type TranscriptHelperItem,
  type UserTranscription,
} from 'agora-agent-client-toolkit';
import { type IMessageListItem } from 'agora-agent-uikit';

// Fixes compacted punctuation emitted by some TTS/ASR providers where sentence-ending
// characters run directly into the next word (e.g. "Hello.World" → "Hello. World").
export function normalizeTranscriptSpacing(text: string): string {
  return text
    .replace(/([.!?])([A-Za-z])/g, '$1 $2')
    .replace(/,([A-Za-z])/g, ', $1')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

// Agora timestamps vary by source: some RTM payloads use Unix-seconds while
// RTC events use milliseconds. Values already above 1e12 are milliseconds; others need scaling.
export function normalizeTimestampMs(timestamp: number): number {
  return timestamp > 1e12 ? timestamp : timestamp * 1000;
}

// Adapts a toolkit TranscriptHelperItem to the shape expected by agora-agent-uikit.
// `status` is cast via `unknown` because the two packages define structurally
// equivalent TurnStatus enums that TypeScript won't narrow across package boundaries.
// `_time` may arrive in seconds or milliseconds depending on the event source.
export function toMessageListItem(
  item: TranscriptHelperItem<Partial<UserTranscription | AgentTranscription>>,
): IMessageListItem {
  return {
    turn_id: item.turn_id,
    uid: Number(item.uid) || 0,
    text: typeof item.text === 'string' ? item.text : '',
    status: item.status as unknown as IMessageListItem['status'],
    createdAt:
      typeof item._time === 'number'
        ? normalizeTimestampMs(item._time)
        : undefined,
  };
}

// uid="0" is the toolkit's sentinel for local-user speech. Without remapping it to
// the actual RTC UID, the transcript panel renders the user's speech on the agent's side.
// Also normalises punctuation spacing so all turns display consistently.
export function normalizeTranscript(
  transcript: TranscriptHelperItem<Partial<UserTranscription | AgentTranscription>>[],
  localUID: string,
) {
  return transcript.map((item) => {
    const remappedUID = item.uid === '0' ? localUID : item.uid;
    const normalizedText =
      typeof item.text === 'string'
        ? normalizeTranscriptSpacing(item.text)
        : item.text;
    return { ...item, uid: remappedUID, text: normalizedText };
  });
}

// Returns completed and interrupted turns for the message history list.
// IN_PROGRESS turns are intentionally excluded — they are rendered separately
// as a streaming partial bubble via getCurrentInProgressMessage.
// INTERRUPTED turns must be included: if the agent's first turn is cut off and
// omitted, messageList stays empty and the first interrupted turn is never shown.
export function getMessageList(
  transcript: TranscriptHelperItem<Partial<UserTranscription | AgentTranscription>>[],
) {
  return transcript
    .filter((item) => item.status !== TurnStatus.IN_PROGRESS)
    .map(toMessageListItem);
}

// Returns the single active in-progress turn, or null when none exists.
// At most one turn is in-progress at a time. The transcript panel renders this
// as a live streaming bubble, distinct from the static message history.
export function getCurrentInProgressMessage(
  transcript: TranscriptHelperItem<Partial<UserTranscription | AgentTranscription>>[],
) {
  const item = transcript.find((entry) => entry.status === TurnStatus.IN_PROGRESS);
  return item ? toMessageListItem(item) : null;
}
