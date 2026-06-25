import { ConversationErrorCard, type ConnectionIssue } from './ConversationErrorCard';

type ConnectionStatusPanelProps = {
  connectionState: string;
  connectionSeverity: 'normal' | 'warning' | 'error';
  connectionIssues: ConnectionIssue[];
  isOpen: boolean;
  onToggle: () => void;
};

// Produces an accessible label from the raw RTC state string, with a special case for
// "Connected (issues detected)" when RTM/agent errors exist while RTC transport is healthy.
function getConnectionLabel(
  connectionState: string,
  connectionSeverity: 'normal' | 'warning' | 'error'
): string {
  if (connectionSeverity !== 'normal' && connectionState === 'CONNECTED') {
    return 'Connected (issues detected)';
  }
  if (connectionState === 'CONNECTED') return 'Connected';
  if (connectionState === 'CONNECTING') return 'Connecting...';
  if (connectionState === 'RECONNECTING') return 'Reconnecting...';
  if (connectionState === 'DISCONNECTING') return 'Disconnecting...';
  return 'Disconnected';
}

export function ConnectionStatusPanel({
  connectionState,
  connectionSeverity,
  connectionIssues,
  isOpen,
  onToggle,
}: ConnectionStatusPanelProps) {
  return (
    <div className="relative flex-shrink-0">
      {/* Minimal status affordance: color and ping convey RTC health before the user opens details. */}
      <button
        type="button"
        className="relative block"
        aria-label={getConnectionLabel(connectionState, connectionSeverity)}
        aria-expanded={isOpen}
        aria-controls="connection-details-panel"
        onClick={onToggle}
      >
        <span className="relative flex h-2 w-2">
          {connectionState !== 'DISCONNECTED' && connectionState !== 'DISCONNECTING' && (
            <span
              className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                connectionSeverity === 'normal'
                  ? 'bg-green-500'
                  : connectionSeverity === 'warning'
                    ? 'bg-amber-500'
                    : 'bg-red-500'
              }`}
            />
          )}
          <span
            className={`relative inline-flex h-2 w-2 rounded-full ${
              connectionSeverity === 'normal'
                ? 'bg-green-500'
                : connectionSeverity === 'warning'
                  ? 'bg-amber-500'
                  : 'bg-red-500'
            }`}
          />
        </span>
      </button>

      {/* Expandable detail panel: current RTC state plus the captured agent/RTM issues. */}
      <div
        id="connection-details-panel"
        className={`fixed top-16 left-1/2 z-20 w-[min(92vw,22rem)] -translate-x-1/2 rounded-md border border-border bg-card/95 p-3 space-y-2 backdrop-blur-sm transition-opacity md:absolute md:left-0 md:top-full md:mt-3 md:w-[24rem] md:translate-x-0 md:translate-y-0 ${
          isOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        }`}
        role="status"
        aria-live="polite"
        aria-label="Connection details"
      >
        <div className="flex items-center justify-between gap-2">
          <div className="text-xs font-semibold tracking-wide text-foreground">
            Connection Details
          </div>
          <div className="text-[11px] text-muted-foreground">
            RTC {connectionState.toLowerCase()}
          </div>
        </div>
        {connectionIssues.length === 0 ? (
          <div className="text-xs text-muted-foreground">No RTM or agent errors reported.</div>
        ) : (
          <div className="space-y-2 max-h-56 overflow-auto pr-1">
            {connectionIssues.map((issue) => (
              <ConversationErrorCard key={issue.id} issue={issue} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
