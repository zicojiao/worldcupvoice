'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { toast } from 'sonner';
import {
  useRTCClient,
  useRemoteUsers,
  useClientEvent,
  useJoin,
  RemoteUser,
  type UID,
} from 'agora-rtc-react';
import {
  AgoraVoiceAI,
  AgoraVoiceAIEvents,
  MessageSalStatus,
  TranscriptHelperMode,
  type TranscriptHelperItem,
  type UserTranscription,
  type AgentTranscription,
} from 'agora-agent-client-toolkit';
import { DEFAULT_AGENT_UID, DEFAULT_MATCH_FEED_UID } from '@/lib/agora';
import {
  getCurrentInProgressMessage,
  getMessageList,
  normalizeTimestampMs,
  normalizeTranscript,
} from '@/lib/conversation';
import {
  getConversationIssueSeverity,
  type ConnectionIssue,
} from './ConversationErrorCard';
import { ConnectionStatusPanel } from './ConnectionStatusPanel';
import { QuickstartConversationLayout } from './QuickstartConversationLayout';
import {
  QuickstartPipelineMetrics,
  type QuickstartAgentMetric,
} from './QuickstartPipelineMetrics';
import { QuickstartTranscriptPanel } from './QuickstartTranscriptPanel';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toMatchContext } from '@/lib/commentary';
import {
  COMMENTATOR_PROFILES,
  DEFAULT_COMMENTATOR_PROFILE_ID,
  type CommentatorProfileId,
} from '@/lib/commentatorProfiles';
import type {
  ActiveAgentSession,
  AgentErrorResponse,
  AgentResponse,
  ClientStartRequest,
  ConversationComponentProps,
  SessionStatusResponse,
} from '@/types/conversation';

const MAX_CONNECTION_ISSUES = 6;
const SESSION_STATUS_POLL_MS = 5_000;
const SESSION_HEARTBEAT_MS = 15_000;

type RtmMessageErrorPayload = {
  object: 'message.error';
  module?: string;
  code?: number;
  message?: string;
  send_ts?: number;
};

type RtmSalStatusPayload = {
  object: 'message.sal_status';
  status?: string;
  timestamp?: number;
};

type ClientAudioStats = {
  transportDelay: number;
  receiveDelay: number;
  receiveBitrate: number;
  packetLossRate: number;
  currentPacketLossRate: number;
  receivePacketsLost: number;
  receivePacketsDiscarded: number;
  freezeRate: number;
  totalFreezeTime: number;
  volumeLevel: number;
};

function isRtmMessageErrorPayload(
  value: unknown,
): value is RtmMessageErrorPayload {
  return (
    !!value &&
    typeof value === 'object' &&
    (value as { object?: unknown }).object === 'message.error'
  );
}

function isRtmSalStatusPayload(value: unknown): value is RtmSalStatusPayload {
  return (
    !!value &&
    typeof value === 'object' &&
    (value as { object?: unknown }).object === 'message.sal_status'
  );
}

function isVisualObservationTick(text: string | undefined): boolean {
  return Boolean(text?.includes('[Visual observation tick]'));
}

function formatUnixTime(timestamp: number | null | undefined): string {
  if (!timestamp) return 'unknown';
  return new Date(timestamp * 1000).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function aiSpendLabel(status: SessionStatusResponse | null): string {
  if (!status) return 'Checking';
  if (status.ai_spending_state === 'active') return 'Active';
  if (status.ai_spending_state === 'idle_no_video') return 'Idle, no video';
  if (status.ai_spending_state === 'stopped') return 'Stopped';
  return 'Missing';
}

function aiSpendClass(status: SessionStatusResponse | null): string {
  if (!status) return 'border-white/15 bg-white/5 text-white/70';
  if (status.ai_spending_state === 'active') {
    return 'border-red-400/35 bg-red-500/10 text-red-100';
  }
  if (status.ai_spending_state === 'idle_no_video') {
    return 'border-amber-300/30 bg-amber-400/10 text-amber-100';
  }
  return 'border-emerald-300/30 bg-emerald-400/10 text-emerald-100';
}

function BackendSessionMonitor({
  status,
  activeAgent,
  isAiStarting,
  actionError,
  clientAudioStats,
  selectedProfileId,
  onStartAi,
  onStopAi,
  onProfileChange,
}: {
  status: SessionStatusResponse | null;
  activeAgent: ActiveAgentSession | null;
  isAiStarting: boolean;
  actionError: string | null;
  clientAudioStats: ClientAudioStats | null;
  selectedProfileId: CommentatorProfileId;
  onStartAi: () => void;
  onStopAi: () => void;
  onProfileChange: (profileId: CommentatorProfileId) => void;
}) {
  const events = status?.events.slice(-12).reverse() ?? [];
  const isAiRunning = Boolean(activeAgent);
  const stats = status?.stats;
  const selectedProfile =
    COMMENTATOR_PROFILES.find((profile) => profile.id === selectedProfileId) ??
    COMMENTATOR_PROFILES[0];
  const metricItems = [
    ['Frames', String(stats?.frames_sampled ?? 0)],
    ['Vision', String(stats?.vision_requests ?? 0)],
    ['TTS', String(stats?.tts_requests ?? 0)],
    ['Buffer', `${stats?.audio_buffer_ms ?? 0}ms`],
    ['Client delay', `${clientAudioStats?.receiveDelay ?? 0}ms`],
    ['Loss', `${clientAudioStats?.packetLossRate ?? 0}%`],
    ['Freeze', String(clientAudioStats?.freezeRate ?? 0)],
  ];
  const issueItems = [
    stats?.audio_consume_errors
      ? ['Audio errors', String(stats.audio_consume_errors)]
      : null,
    stats?.audio_backlog_skips
      ? ['Backlog skips', String(stats.audio_backlog_skips)]
      : null,
  ].filter((item): item is [string, string] => Boolean(item));

  return (
    <section className="rounded-lg border border-border bg-card p-3 text-sm shadow-sm">
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="font-semibold text-foreground">AI commentary</p>
          <p className="text-xs text-muted-foreground">
            {isAiRunning
              ? `${status?.state ?? 'starting'} · ${status?.commentator_profile_label ?? selectedProfile.label}`
              : 'Off · live video continues without AI spend'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="grid gap-1 text-xs text-muted-foreground">
            <span>Commentator</span>
            <Select
              value={selectedProfileId}
              disabled={isAiRunning || isAiStarting}
              onValueChange={(value) =>
                onProfileChange(value as CommentatorProfileId)
              }
            >
              <SelectTrigger className="h-8 min-w-[14rem] border-border/80 bg-background/80 px-2.5 text-xs font-semibold text-foreground shadow-sm hover:bg-accent/20">
                <SelectValue placeholder="Select commentator" />
              </SelectTrigger>
              <SelectContent align="end" className="min-w-[14rem]">
                {COMMENTATOR_PROFILES.map((profile) => (
                  <SelectItem key={profile.id} value={profile.id} className="text-xs">
                    {profile.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div
            className={`w-fit rounded-md border px-2.5 py-1 text-xs font-semibold ${aiSpendClass(status)}`}
          >
            AI spend: {isAiRunning ? aiSpendLabel(status) : 'Off'}
          </div>
          {isAiRunning ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onStopAi}
              disabled={isAiStarting}
            >
              Stop AI
            </Button>
          ) : (
            <Button
              type="button"
              size="sm"
              onClick={onStartAi}
              disabled={isAiStarting}
            >
              {isAiStarting ? 'Starting AI' : 'Start AI'}
            </Button>
          )}
        </div>
      </div>

      <div
        className="mt-3 flex max-w-full gap-2 overflow-x-auto pb-1 text-xs"
        aria-label="AI commentary summary metrics"
      >
        {metricItems.map(([label, value]) => (
          <div
            key={label}
            className="flex shrink-0 items-center gap-1.5 rounded-md border border-border/70 bg-background/25 px-2.5 py-1"
          >
            <span className="text-muted-foreground">{label}</span>
            <span className="font-mono font-semibold text-foreground">
              {value}
            </span>
          </div>
        ))}
        {issueItems.map(([label, value]) => (
          <div
            key={label}
            className="flex shrink-0 items-center gap-1.5 rounded-md border border-amber-300/35 bg-amber-400/10 px-2.5 py-1 text-amber-100"
          >
            <span>{label}</span>
            <span className="font-mono font-semibold">{value}</span>
          </div>
        ))}
      </div>

      {status?.stop_reason ? (
        <p className="mt-2 text-xs text-muted-foreground">
          Stop reason: {status.stop_reason} at {formatUnixTime(status.stopped_at)}
        </p>
      ) : null}

      {actionError ? (
        <p className="mt-2 text-xs text-destructive">{actionError}</p>
      ) : null}

      {events.length > 0 ? (
        <div className="mt-3 border-t border-border pt-2">
          <p className="mb-1 text-xs font-semibold text-foreground">
            Recent lifecycle
          </p>
          <div
            className="max-h-24 overflow-y-auto rounded-md border border-border/70 bg-background/25 p-2 pr-3"
            aria-label="Recent lifecycle events"
          >
            <div className="grid gap-1">
              {events.map((event) => (
                <p
                  key={`${event.created_at}-${event.event}-${event.message}`}
                  className="break-words text-xs leading-5 text-muted-foreground"
                >
                  <span className="font-mono text-foreground">
                    {formatUnixTime(event.created_at)}
                  </span>{' '}
                  {event.event}: {event.message}
                </p>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default function ConversationComponent({
  agoraData,
  rtmClient,
  match,
  accessPassword,
  onTokenWillExpire,
  onEndConversation,
}: ConversationComponentProps) {
  const client = useRTCClient();
  const remoteUsers = useRemoteUsers();

  const agentUID =
    agoraData.agentUid ??
    process.env.NEXT_PUBLIC_AGENT_UID ??
    String(DEFAULT_AGENT_UID);
  const mediaUID =
    agoraData.mediaUid ??
    process.env.NEXT_PUBLIC_MATCH_FEED_UID ??
    String(DEFAULT_MATCH_FEED_UID);
  const [activeAgent, setActiveAgent] = useState<ActiveAgentSession | null>(
    agoraData.agentId && agoraData.sessionId
      ? {
          agentId: agoraData.agentId,
          sessionId: agoraData.sessionId,
          agentUid: agentUID,
          mediaUid: mediaUID,
        }
      : null,
  );

  const [isConnectionDetailsOpen, setIsConnectionDetailsOpen] = useState(false);
  const [connectionState, setConnectionState] = useState<string>('CONNECTING');
  const [joinedUID, setJoinedUID] = useState<UID>(0);
  const [rawTranscript, setRawTranscript] = useState<
    TranscriptHelperItem<Partial<UserTranscription | AgentTranscription>>[]
  >([]);
  const [agentMetrics, setAgentMetrics] = useState<QuickstartAgentMetric[]>([]);
  const [sessionStatus, setSessionStatus] =
    useState<SessionStatusResponse | null>(null);
  const [isAiStarting, setIsAiStarting] = useState(false);
  const [aiActionError, setAiActionError] = useState<string | null>(null);
  const [selectedProfileId, setSelectedProfileId] =
    useState<CommentatorProfileId>(DEFAULT_COMMENTATOR_PROFILE_ID);
  const [connectionIssues, setConnectionIssues] = useState<ConnectionIssue[]>(
    [],
  );

  const mediaUser = useMemo(
    () => remoteUsers.find((user) => user.uid.toString() === mediaUID),
    [remoteUsers, mediaUID],
  );
  const agentUser = useMemo(
    () => remoteUsers.find((user) => user.uid.toString() === agentUID),
    [remoteUsers, agentUID],
  );
  const agentAudioTrack = agentUser?.audioTrack;
  const isMediaFeedConnected = Boolean(mediaUser);
  const [clientAudioStats, setClientAudioStats] =
    useState<ClientAudioStats | null>(null);

  const addConnectionIssue = useCallback((issue: ConnectionIssue) => {
    setConnectionIssues((prev) => {
      const isDuplicate = prev.some(
        (x) =>
          x.agentUserId === issue.agentUserId &&
          x.code === issue.code &&
          x.message === issue.message &&
          Math.abs(x.timestamp - issue.timestamp) < 1500,
      );
      if (isDuplicate) return prev;
      return [issue, ...prev].slice(0, MAX_CONNECTION_ISSUES);
    });
  }, []);

  useEffect(() => {
    if (connectionIssues.length > 0) {
      setIsConnectionDetailsOpen(true);
    }
  }, [connectionIssues.length]);

  const [isReady, setIsReady] = useState(false);
  useEffect(() => {
    let cancelled = false;
    const id = setTimeout(() => {
      if (!cancelled) setIsReady(true);
    }, 0);
    return () => {
      cancelled = true;
      clearTimeout(id);
      setIsReady(false);
    };
  }, []);

  const { isConnected: joinSuccess } = useJoin(
    {
      appid: process.env.NEXT_PUBLIC_AGORA_APP_ID!,
      channel: agoraData.channel,
      token: agoraData.token,
      uid: parseInt(agoraData.uid, 10),
    },
    isReady,
  );

  useEffect(() => {
    if (joinSuccess && client) {
      const uid = client.uid;
      if (uid !== null && uid !== undefined) {
        setJoinedUID(uid);
      }
    }
  }, [joinSuccess, client]);

  useEffect(() => {
    if (!isReady || !joinSuccess) return;

    let cancelled = false;

    (async () => {
      try {
        const ai = await AgoraVoiceAI.init({
          rtcEngine: client,
          rtmConfig: { rtmEngine: rtmClient },
          renderMode: TranscriptHelperMode.TEXT,
          enableLog: true,
        });

        if (cancelled) {
          try {
            if (AgoraVoiceAI.getInstance() === ai) {
              ai.unsubscribe();
              ai.destroy();
            }
          } catch {}
          return;
        }

        ai.on(AgoraVoiceAIEvents.TRANSCRIPT_UPDATED, (t) => {
          setRawTranscript([...t]);
        });
        ai.on(AgoraVoiceAIEvents.AGENT_METRICS, (_, metrics) => {
          setAgentMetrics((prev) => [...prev, metrics].slice(-8));
        });
        ai.on(AgoraVoiceAIEvents.MESSAGE_ERROR, (agentUserId, error) => {
          addConnectionIssue({
            id: `${Date.now()}-${agentUserId}-message-error-${error.code}`,
            source: 'rtm',
            agentUserId,
            code: error.code,
            message: error.message,
            timestamp: normalizeTimestampMs(error.timestamp),
          });
        });
        ai.on(
          AgoraVoiceAIEvents.MESSAGE_SAL_STATUS,
          (agentUserId, salStatus) => {
            if (
              salStatus.status === MessageSalStatus.VP_REGISTER_FAIL ||
              salStatus.status === MessageSalStatus.VP_REGISTER_DUPLICATE
            ) {
              addConnectionIssue({
                id: `${Date.now()}-${agentUserId}-sal-${salStatus.status}`,
                source: 'rtm',
                agentUserId,
                code: salStatus.status,
                message: `SAL status: ${salStatus.status}`,
                timestamp: normalizeTimestampMs(salStatus.timestamp),
              });
            }
          },
        );
        ai.on(AgoraVoiceAIEvents.AGENT_ERROR, (agentUserId, error) => {
          addConnectionIssue({
            id: `${Date.now()}-${agentUserId}-agent-error-${error.code}`,
            source: 'agent',
            agentUserId,
            code: error.code,
            message: `${error.type}: ${error.message}`,
            timestamp: normalizeTimestampMs(error.timestamp),
          });
        });
        ai.subscribeMessage(agoraData.channel);
      } catch (error) {
        if (!cancelled) {
          console.error('[AgoraVoiceAI] init failed:', error);
        }
      }
    })();

    return () => {
      cancelled = true;
      try {
        const ai = AgoraVoiceAI.getInstance();
        if (ai) {
          ai.unsubscribe();
          ai.destroy();
        }
      } catch {}
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isReady, joinSuccess]);

  useEffect(() => {
    const handleRtmMessage = (event: {
      message: string | Uint8Array;
      publisher: string;
    }) => {
      const payloadText =
        typeof event.message === 'string'
          ? event.message
          : new TextDecoder().decode(event.message);

      let parsed: unknown;
      try {
        parsed = JSON.parse(payloadText);
      } catch {
        return;
      }

      if (isRtmMessageErrorPayload(parsed)) {
        const p = parsed;
        addConnectionIssue({
          id: `${Date.now()}-${event.publisher}-rtm-msg-error-${p.code ?? 'unknown'}`,
          source: 'rtm-signaling',
          agentUserId: event.publisher,
          code: p.code ?? 'unknown',
          message: `${p.module ?? 'unknown'}: ${p.message ?? 'Unknown signaling error'}`,
          timestamp: normalizeTimestampMs(p.send_ts ?? Date.now()),
        });
        return;
      }

      if (isRtmSalStatusPayload(parsed)) {
        const p = parsed;
        if (
          p.status === 'VP_REGISTER_FAIL' ||
          p.status === 'VP_REGISTER_DUPLICATE'
        ) {
          addConnectionIssue({
            id: `${Date.now()}-${event.publisher}-rtm-sal-${p.status}`,
            source: 'rtm-signaling',
            agentUserId: event.publisher,
            code: p.status,
            message: `SAL status: ${p.status}`,
            timestamp: normalizeTimestampMs(p.timestamp ?? Date.now()),
          });
        }
      }
    };

    rtmClient.addEventListener('message', handleRtmMessage);
    return () => {
      rtmClient.removeEventListener('message', handleRtmMessage);
    };
  }, [rtmClient, addConnectionIssue]);

  const transcript = useMemo(() => {
    return normalizeTranscript(rawTranscript, String(client.uid)).filter(
      (item) => !isVisualObservationTick(item.text),
    );
  }, [rawTranscript, client.uid]);

  const messageList = useMemo(() => getMessageList(transcript), [transcript]);

  const currentInProgressMessage = useMemo(() => {
    return getCurrentInProgressMessage(transcript);
  }, [transcript]);

  useClientEvent(client, 'connection-state-change', (curState) => {
    setConnectionState(curState);
  });

  const fetchSessionStatus = useCallback(
    async (identity: { sessionId?: string; agentId?: string }) => {
      const sessionId = identity.sessionId;
      const agentId = identity.agentId;
      if (!sessionId && !agentId) return null;
      const response = await fetch('/api/session-status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, agent_id: agentId }),
        cache: 'no-store',
      });
      const payload = (await response.json().catch(() => null)) as
        | SessionStatusResponse
        | null;
      if (response.ok && payload) {
        setSessionStatus(payload);
        return payload;
      }
      return null;
    },
    [],
  );

  const heartbeatSession = useCallback(
    async (identity: { sessionId?: string; agentId?: string }) => {
      const sessionId = identity.sessionId;
      const agentId = identity.agentId;
      if (!sessionId && !agentId) return null;
      const response = await fetch('/api/session-heartbeat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, agent_id: agentId }),
        cache: 'no-store',
      });
      const payload = await response.json().catch(() => null);
      if (response.ok) return payload;
      throw new Error(
        payload?.detail ?? payload?.error ?? `Heartbeat failed. HTTP ${response.status}`,
      );
    },
    [],
  );

  const handleStartAi = useCallback(async () => {
    if (activeAgent || isAiStarting) return;
    if (!isMediaFeedConnected) {
      toast.warning('No live video feed yet', {
        description:
          'Start the match stream into the channel first, then turn on the AI commentator.',
      });
      return;
    }
    setIsAiStarting(true);
    setAiActionError(null);
    setSessionStatus(null);
    try {
      const response = await fetch('/api/invite-agent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          requester_id: agoraData.uid,
          channel_name: agoraData.channel,
          source_mode: 'agora-gateway',
          match_context: toMatchContext(match),
          commentator_profile_id: selectedProfileId,
          access_password: accessPassword,
        } as ClientStartRequest),
        cache: 'no-store',
      });
      const payload = (await response.json().catch(() => null)) as
        | AgentResponse
        | AgentErrorResponse
        | null;
      if (!response.ok || !payload || 'error' in payload) {
        const issue = payload as AgentErrorResponse | null;
        throw new Error(
          issue?.detail ??
            issue?.reason ??
            issue?.error ??
            `AI commentator failed to start. HTTP ${response.status}`,
        );
      }
      const nextAgent: ActiveAgentSession = {
        agentId: payload.agent_id,
        sessionId: payload.session_id,
        agentUid: payload.agent_uid,
        mediaUid: payload.media_uid,
      };
      setActiveAgent(nextAgent);
      await fetchSessionStatus(nextAgent);
    } catch (error) {
      setAiActionError(
        error instanceof Error ? error.message : 'Failed to start AI commentary.',
      );
    } finally {
      setIsAiStarting(false);
    }
  }, [
    accessPassword,
    activeAgent,
    agoraData.channel,
    agoraData.uid,
    fetchSessionStatus,
    isAiStarting,
    isMediaFeedConnected,
    match,
    selectedProfileId,
  ]);

  const handleStopAi = useCallback(async () => {
    if (!activeAgent) return;
    setIsAiStarting(true);
    setAiActionError(null);
    const identity = activeAgent;
    try {
      const response = await fetch('/api/stop-conversation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent_id: identity.agentId,
          session_id: identity.sessionId,
        }),
        cache: 'no-store',
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(
          payload?.detail ?? payload?.error ?? `Failed to stop AI. HTTP ${response.status}`,
        );
      }
      await fetchSessionStatus(identity);
      setActiveAgent(null);
    } catch (error) {
      setAiActionError(
        error instanceof Error ? error.message : 'Failed to stop AI commentary.',
      );
    } finally {
      setIsAiStarting(false);
    }
  }, [activeAgent, fetchSessionStatus]);

  useEffect(() => {
    const sessionId = activeAgent?.sessionId;
    const agentId = activeAgent?.agentId;
    if (!sessionId && !agentId) return;
    let cancelled = false;

    const fetchStatus = () => {
      fetchSessionStatus({ sessionId, agentId })
        .then((payload) => {
          if (!cancelled && payload?.state === 'stopped') {
            setActiveAgent(null);
          }
        })
        .catch((error) => {
          console.warn('Failed to fetch backend session status', error);
        });
    };

    fetchStatus();
    const interval = window.setInterval(fetchStatus, SESSION_STATUS_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [activeAgent?.agentId, activeAgent?.sessionId, fetchSessionStatus]);

  useEffect(() => {
    const sessionId = activeAgent?.sessionId;
    const agentId = activeAgent?.agentId;
    if (!sessionId && !agentId) return;
    let cancelled = false;

    const heartbeat = () => {
      heartbeatSession({ sessionId, agentId })
        .then((payload) => {
          if (!cancelled && payload?.state === 'missing') {
            setActiveAgent(null);
          }
        })
        .catch((error) => {
          console.warn('Failed to heartbeat backend session', error);
        });
    };

    heartbeat();
    const interval = window.setInterval(heartbeat, SESSION_HEARTBEAT_MS);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [activeAgent?.agentId, activeAgent?.sessionId, heartbeatSession]);

  const connectionSeverity = useMemo<'normal' | 'warning' | 'error'>(() => {
    if (
      connectionState === 'DISCONNECTED' ||
      connectionState === 'DISCONNECTING'
    ) {
      return 'error';
    }
    if (
      connectionState === 'CONNECTING' ||
      connectionState === 'RECONNECTING'
    ) {
      return 'warning';
    }
    if (connectionIssues.length === 0) {
      return 'normal';
    }
    return connectionIssues.some(
      (issue) => getConversationIssueSeverity(issue) === 'error',
    )
      ? 'error'
      : 'warning';
  }, [connectionState, connectionIssues]);

  const mediaStatusLabel = useMemo(() => {
    if (isMediaFeedConnected) return 'Agora RTC video live';
    if (joinSuccess) return 'Waiting for live feed';
    return 'Joining channel';
  }, [joinSuccess, isMediaFeedConnected]);

  const handleTokenWillExpire = useCallback(async () => {
    if (!onTokenWillExpire || !joinedUID) return;
    try {
      const { rtcToken, rtmToken } = await onTokenWillExpire(
        joinedUID.toString(),
      );
      await client?.renewToken(rtcToken);
      await rtmClient.renewToken(rtmToken);
    } catch (error) {
      console.error('Failed to renew Agora token:', error);
    }
  }, [client, onTokenWillExpire, joinedUID, rtmClient]);

  useClientEvent(client, 'token-privilege-will-expire', handleTokenWillExpire);

  useEffect(() => {
    if (!agentAudioTrack) {
      setClientAudioStats(null);
      return;
    }

    const readStats = () => {
      const stats = agentAudioTrack.getStats();
      const nextStats: ClientAudioStats = {
        transportDelay: Math.round(stats.transportDelay ?? 0),
        receiveDelay: Math.round(stats.receiveDelay ?? 0),
        receiveBitrate: Math.round(stats.receiveBitrate ?? 0),
        packetLossRate: Number((stats.packetLossRate ?? 0).toFixed(3)),
        currentPacketLossRate: Number(
          (stats.currentPacketLossRate ?? 0).toFixed(3),
        ),
        receivePacketsLost: stats.receivePacketsLost ?? 0,
        receivePacketsDiscarded: stats.receivePacketsDiscarded ?? 0,
        freezeRate: Number((stats.freezeRate ?? 0).toFixed(3)),
        totalFreezeTime: Number((stats.totalFreezeTime ?? 0).toFixed(3)),
        volumeLevel: Number(agentAudioTrack.getVolumeLevel().toFixed(3)),
      };
      setClientAudioStats(nextStats);
      console.info('[AI_AUDIO_CLIENT]', nextStats);
    };

    readStats();
    const interval = window.setInterval(readStats, 2000);
    return () => window.clearInterval(interval);
  }, [agentAudioTrack]);

  const handleEndConversation = useCallback(async () => {
    onEndConversation();
  }, [onEndConversation]);

  const hiddenRemoteUsers = remoteUsers.filter(
    (user) =>
      user.uid.toString() !== mediaUID && user.uid.toString() !== agentUID,
  );

  return (
    <QuickstartConversationLayout
      statusPanel={
        <ConnectionStatusPanel
          connectionState={connectionState}
          connectionSeverity={connectionSeverity}
          connectionIssues={connectionIssues}
          isOpen={isConnectionDetailsOpen}
          onToggle={() => setIsConnectionDetailsOpen((open) => !open)}
        />
      }
      pipelineMetrics={<QuickstartPipelineMetrics metrics={agentMetrics} />}
      transcriptPanel={
        <QuickstartTranscriptPanel
          messageList={messageList}
          currentInProgressMessage={currentInProgressMessage}
          agentUID={agentUID}
        />
      }
      visualizer={
        <div className="w-full lg:h-full lg:min-h-[22rem]">
          <section className="flex w-full flex-col rounded-lg border border-[#214634] bg-[#07130f] p-2 shadow-[0_12px_32px_rgba(0,0,0,0.28)] sm:p-3 lg:h-full lg:min-h-[22rem]">
            <div className="relative grid aspect-video w-full place-items-center overflow-hidden rounded-md bg-black lg:min-h-[22rem] lg:flex-1">
          {mediaUser ? (
                <div
                  className="h-full w-full [&_video]:h-full [&_video]:w-full [&_video]:object-contain"
                >
                  <RemoteUser user={mediaUser} />
                </div>
              ) : (
                <div className="w-full max-w-2xl px-6 text-center">
                  <p className="text-sm font-semibold text-white">
                    Waiting for the live video feed
                  </p>
                  <p className="mt-2 text-xs leading-5 text-white/55">
                    Channel {agoraData.channel} · Feed UID {mediaUID}
                  </p>
                </div>
              )}
              <div className="absolute left-3 top-3 rounded-full border border-white/15 bg-black/70 px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-white">
                {mediaStatusLabel}
              </div>
            </div>
            <div className="mt-3 flex flex-col gap-1 px-1 text-sm md:flex-row md:items-center md:justify-between">
              <div>
                <p className="font-semibold text-white">
                  {match.homeTeam} vs {match.awayTeam}
                </p>
                <p className="text-xs text-white/60">
                  {match.competition} - {match.venue}
                </p>
              </div>
            </div>
          </section>

          {hiddenRemoteUsers.map((user) => (
            <div
              key={user.uid}
              className="pointer-events-none fixed h-px w-px overflow-hidden opacity-0"
              aria-hidden="true"
            >
              <RemoteUser user={user} playAudio={false} />
            </div>
          ))}
          {agentUser && (
            <div
              className="pointer-events-none fixed h-px w-px overflow-hidden opacity-0"
              aria-hidden="true"
            >
              <RemoteUser user={agentUser} playAudio volume={100} />
            </div>
          )}
        </div>
      }
      controls={
        <BackendSessionMonitor
          status={sessionStatus}
          activeAgent={activeAgent}
          isAiStarting={isAiStarting}
          actionError={aiActionError}
          clientAudioStats={clientAudioStats}
          selectedProfileId={selectedProfileId}
          onStartAi={handleStartAi}
          onStopAi={handleStopAi}
          onProfileChange={setSelectedProfileId}
        />
      }
      onEndConversation={handleEndConversation}
    />
  );
}
