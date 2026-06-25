export type ConnectionIssue = {
  id: string;
  source: 'rtm' | 'agent' | 'rtm-signaling';
  agentUserId: string;
  code: string | number;
  message: string;
  timestamp: number;
};

export type ConnectionIssueSeverity = 'warning' | 'error';

// Some agent errors embed HTTP codes inside the message string (e.g. "LLM: 401" or "HTTP 404")
// rather than exposing them in the numeric `code` field. Extracting them gives us a semantically
// richer signal for severity classification and CTA generation.
function getEmbeddedIssueCode(issue: ConnectionIssue): string | null {
  const msg = issue.message.toLowerCase();

  const moduleCodeMatch = msg.match(/\b(?:llm|asr|tts)\s*:\s*(\d{3})\b/);
  if (moduleCodeMatch?.[1]) return moduleCodeMatch[1];

  const httpCodeMatch = msg.match(/\bhttp\s*(\d{3})\b/);
  if (httpCodeMatch?.[1]) return httpCodeMatch[1];

  return null;
}

// Prefers the HTTP code embedded in the message over the raw transport code,
// so severity and CTA logic consistently operate on the most specific error identifier.
function getEffectiveIssueCode(issue: ConnectionIssue): string {
  return String(getEmbeddedIssueCode(issue) ?? issue.code);
}

// Classifies an issue as "warning" (transient, self-resolving) or "error" (action required).
// Rate-limit (429), timeout (408), and conflict (409) errors are transient — the status dot
// stays amber rather than red so the developer isn't alarmed by momentary backpressure.
export function getConversationIssueSeverity(
  issue: ConnectionIssue
): ConnectionIssueSeverity {
  const msg = issue.message.toLowerCase();
  const code = getEffectiveIssueCode(issue).toLowerCase();

  if (
    code === '429' ||
    msg.includes('rate limit') ||
    msg.includes('timeout') ||
    code === '408' ||
    code === '409'
  ) {
    return 'warning';
  }
  return 'error';
}

// Translates generic provider 401 messages into module-specific copy so the developer
// knows immediately which API key (LLM / ASR / TTS) is invalid without reading the raw payload.
function getNormalizedMessage(issue: ConnectionIssue): string {
  const lowered = issue.message.toLowerCase();
  const code = getEffectiveIssueCode(issue).toLowerCase();

  if (code === '401' || lowered.includes('http 401')) {
    if (lowered.includes('llm')) return 'LLM authentication failed (401 Unauthorized).';
    if (lowered.includes('asr')) return 'ASR authentication failed (401 Unauthorized).';
    if (lowered.includes('tts')) return 'TTS authentication failed (401 Unauthorized).';
    return 'Authentication failed (401 Unauthorized).';
  }
  return issue.message;
}

// Returns a short, actionable next-step for known HTTP / error codes so the developer
// sees remediation guidance inline without having to cross-reference documentation.
function getCta(issue: ConnectionIssue): string | null {
  const msg = issue.message.toLowerCase();
  const code = getEffectiveIssueCode(issue).toLowerCase();

  if (msg.includes('http 401') || code === '401') return 'Verify provider API key.';
  if (msg.includes('http 403') || code === '403')
    return 'Verify provider API permissions.';
  if (msg.includes('http 404') || code === '404')
    return 'Verify provider endpoint and model ID.';
  if (msg.includes('http 408') || msg.includes('timeout') || code === '408')
    return 'Check network stability and retry.';
  if (msg.includes('http 409') || code === '409')
    return 'Retry after session state settles.';
  if (msg.includes('http 429') || code === '429' || msg.includes('rate limit'))
    return 'Reduce request rate or increase quota.';
  if (
    msg.includes('http 500') ||
    msg.includes('http 502') ||
    msg.includes('http 503') ||
    msg.includes('http 504')
  ) {
    return 'Retry shortly or switch provider region/model.';
  }
  if (msg.includes('websocket') && msg.includes('reject')) {
    return 'Verify provider auth, endpoint, and region.';
  }
  if (code === 'vp_register_fail' || code === 'vp_register_duplicate') {
    return 'Verify RTM configuration and reconnect.';
  }
  return null;
}

type ConversationErrorCardProps = {
  issue: ConnectionIssue;
};

export function ConversationErrorCard({ issue }: ConversationErrorCardProps) {
  const normalizedMessage = getNormalizedMessage(issue);
  const showNormalizedMessage = normalizedMessage !== issue.message;
  const cta = getCta(issue);
  const transportCode = String(issue.code);
  const showRaw = issue.message !== normalizedMessage;

  return (
    // Compact diagnostic card: headline for quick triage, optional CTA, raw payload for deeper debugging.
    <div className="rounded border border-destructive/30 bg-destructive/10 px-2 py-1.5 text-xs">
      <div className="font-medium text-destructive">
        Conversation AI Engine Error: {transportCode}
      </div>
      {showNormalizedMessage && <div className="text-foreground">{normalizedMessage}</div>}
      {cta && <div className="text-[11px] text-destructive/90">{cta}</div>}
      {showRaw && (
        <div className="mt-2 border-t border-destructive/20 pt-2 text-muted-foreground break-words">
          {issue.message}
        </div>
      )}
      <div className="text-muted-foreground">
        agent {issue.agentUserId} at {new Date(issue.timestamp).toLocaleTimeString()}
      </div>
    </div>
  );
}
