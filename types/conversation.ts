import type { RTMClient } from 'agora-rtm';

export interface AgoraTokenData {
  token: string;
  uid: string;
  channel: string;
  sourceMode?: SourceMode;
  agentId?: string;
  sessionId?: string;
  agentUid?: string;
  mediaUid?: string;
}

export type SourceMode = 'agora-gateway';

export interface ActiveAgentSession {
  agentId: string;
  sessionId: string;
  agentUid: string;
  mediaUid: string;
}

export interface CommentaryMatch {
  id: string;
  sport: string;
  title: string;
  competition: string;
  venue: string;
  homeTeam: string;
  awayTeam: string;
  gameDate?: string;
  localTipTime?: string;
  finalScore?: string;
  homeTeamAbbr?: string;
  awayTeamAbbr?: string;
  homeJerseyColor?: string;
  awayJerseyColor?: string;
  homeRoster?: PlayerIdentity[];
  awayRoster?: PlayerIdentity[];
  playerIdentificationNotes?: string[];
  broadcastNotes?: string[];
  posterUrl: string;
  storyline: string;
}

export interface MatchContext {
  sport: string;
  title: string;
  competition: string;
  venue: string;
  homeTeam: string;
  awayTeam: string;
  gameDate?: string;
  localTipTime?: string;
  finalScore?: string;
  homeTeamAbbr?: string;
  awayTeamAbbr?: string;
  homeJerseyColor?: string;
  awayJerseyColor?: string;
  homeRoster?: PlayerIdentity[];
  awayRoster?: PlayerIdentity[];
  playerIdentificationNotes?: string[];
  broadcastNotes?: string[];
  storyline: string;
}

export interface PlayerIdentity {
  number: string;
  name: string;
  shortName: string;
  role: 'starter' | 'bench' | 'dnp';
  position?: string;
  notes?: string;
}

export interface ClientStartRequest {
  requester_id: string;
  channel_name: string;
  source_mode?: SourceMode;
  match_context?: MatchContext;
  // Access gate password, validated server-side; never forwarded to the Python backend.
  access_password?: string;
}

export interface StopConversationRequest {
  agent_id?: string;
  session_id?: string;
}

export interface SessionHeartbeatRequest {
  agent_id?: string;
  session_id?: string;
}

export interface SessionHeartbeatResponse {
  success: boolean;
  state: 'running' | 'missing';
}

export interface SessionStatusRequest {
  agent_id?: string;
  session_id?: string;
}

export interface SessionLifecycleEvent {
  event: string;
  message: string;
  created_at: number;
}

export interface CommentatorStats {
  frames_sampled: number;
  vision_requests: number;
  tts_requests: number;
  audio_sample_rate: number;
  audio_consume_interval_ms: number;
  audio_buffer_ms: number;
  audio_consume_calls: number;
  audio_consume_errors: number;
  audio_buffer_clears: number;
  audio_backlog_skips: number;
  audio_underflows: number;
  audio_keepalive_calls: number;
  audio_send_calls: number;
  audio_send_errors: number;
  audio_sent_ms: number;
  last_audio_send_ms?: number | null;
  last_audio_send_ret?: number | null;
  last_audio_send_gap_ms?: number | null;
  max_audio_send_gap_ms: number;
  slow_audio_send_gaps: number;
  last_audio_send_duration_ms?: number | null;
  max_audio_send_duration_ms: number;
  slow_audio_send_durations: number;
  last_consume_result?: number | null;
  audio_consumer_completed: boolean;
  last_audio_duration_ms?: number | null;
  last_frame_at?: number | null;
  last_commentary_at?: number | null;
  last_audio_at?: number | null;
}

export interface SessionStatusResponse {
  success: boolean;
  state: 'running' | 'stopped' | 'missing';
  ai_spending_state: 'active' | 'idle_no_video' | 'stopped' | 'missing';
  session_id?: string | null;
  agent_id?: string | null;
  channel_name?: string | null;
  created_at?: number | null;
  stopped_at?: number | null;
  stop_reason?: string | null;
  last_viewer_heartbeat_at?: number | null;
  last_viewer_heartbeat_age_seconds?: number | null;
  live_session_max_seconds?: number | null;
  viewer_heartbeat_timeout_seconds?: number | null;
  stats: CommentatorStats;
  events: SessionLifecycleEvent[];
}

export interface AgentResponse {
  agent_id: string;
  session_id: string;
  create_ts: number;
  state: string;
  channel_name: string;
  source_mode?: SourceMode;
  agent_uid: string;
  media_uid: string;
  vision_mode?: string;
  warnings?: string[];
}

export interface AgentErrorResponse {
  error: string;
  reason?: string;
  detail?: string;
  statusCode?: number;
}

export interface AgoraRenewalTokens {
  rtcToken: string;
  rtmToken: string;
}

export interface ConversationComponentProps {
  agoraData: AgoraTokenData;
  rtmClient: RTMClient;
  match: CommentaryMatch;
  accessPassword: string;
  onTokenWillExpire: (uid: string) => Promise<AgoraRenewalTokens>;
  onEndConversation: () => void;
}
