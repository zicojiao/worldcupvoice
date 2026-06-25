'use client';

import {
  useState,
  useRef,
  Suspense,
  useEffect,
  useCallback,
  type FormEvent,
} from 'react';
import dynamic from 'next/dynamic';
import { Lock } from 'lucide-react';
import type { RTMClient } from 'agora-rtm';
import type {
  AgoraTokenData,
  AgoraRenewalTokens,
} from '../types/conversation';
import { ErrorBoundary } from './ErrorBoundary';
import { LoadingSkeleton } from './LoadingSkeleton';
import { QuickstartPreCallCard } from './QuickstartPreCallCard';
import { QuickstartLobbyFrame } from './QuickstartLobbyFrame';
import { Button } from '@/components/ui/button';
import { COMMENTARY_MATCHES } from '@/lib/commentary';

// Dynamically import the ConversationComponent with ssr disabled
const ConversationComponent = dynamic(() => import('./ConversationComponent'), {
  ssr: false,
});

let hasConfiguredAgoraArea = false;

// Dynamically import AgoraRTCProvider (browser-only).
// The AgoraVoiceAI toolkit is initialized inside ConversationComponent after
// the RTC join succeeds, so this wrapper only needs to provide the RTC client.
const AgoraProvider = dynamic(
  async () => {
    const { AgoraRTCProvider, default: AgoraRTC } =
      await import('agora-rtc-react');
    return {
      default: function AgoraProviders({
        children,
      }: {
        children: React.ReactNode;
      }) {
        // useRef persists across StrictMode's simulated unmount/remount, so only
        // one RTC client is ever created per session (useMemo creates two in StrictMode).
        const clientRef = useRef<ReturnType<
          typeof AgoraRTC.createClient
        > | null>(null);
        if (!clientRef.current) {
          if (!hasConfiguredAgoraArea) {
            const areaCode = process.env.NEXT_PUBLIC_AGORA_AREA_CODE
              ?.trim()
              .toLowerCase();
            const areaNameByCode: Record<string, string> = {
              cn: 'CHINA',
              china: 'CHINA',
              as: 'ASIA',
              asia: 'ASIA',
              na: 'NORTH_AMERICA',
              'north-america': 'NORTH_AMERICA',
              eu: 'EUROPE',
              europe: 'EUROPE',
              jp: 'JAPAN',
              japan: 'JAPAN',
              in: 'INDIA',
              india: 'INDIA',
            };
            const areaName = areaCode ? areaNameByCode[areaCode] : undefined;
            const rtcWithArea = AgoraRTC as unknown as {
              AREAS?: Record<string, string>;
              setArea?: (params: { areaCode: string[] }) => void;
            };
            const area = areaName ? rtcWithArea.AREAS?.[areaName] : undefined;
            if (area && rtcWithArea.setArea) {
              rtcWithArea.setArea({ areaCode: [area] });
            }
            hasConfiguredAgoraArea = true;
          }
          clientRef.current = AgoraRTC.createClient({
            mode: 'live',
            codec: 'h264',
          });
        }
        return (
          <AgoraRTCProvider client={clientRef.current}>
            {children}
          </AgoraRTCProvider>
        );
      },
    };
  },
  { ssr: false },
);

export default function LandingPage() {
  const [showConversation, setShowConversation] = useState(false);
  const selectedMatch = COMMENTARY_MATCHES[0];

  // Preload heavy modules on mount so they're already cached when the user
  // starts the commentator - eliminates the ~1.8s dynamic-import delay.
  useEffect(() => {
    import('agora-rtc-react').catch(() => {});
    import('agora-rtm').catch(() => {});
  }, []);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [agoraData, setAgoraData] = useState<AgoraTokenData | null>(null);
  const [rtmClient, setRtmClient] = useState<RTMClient | null>(null);
  const [sessionAccessPassword, setSessionAccessPassword] = useState('');
  const [isAccessOpen, setIsAccessOpen] = useState(false);
  const [accessPassword, setAccessPassword] = useState('');
  const [accessError, setAccessError] = useState<string | null>(null);
  const [isVerifying, setIsVerifying] = useState(false);

  const handleOpenAccessGate = () => {
    setAccessError(null);
    setIsAccessOpen(true);
  };

  const handleSubmitAccess = async (event: FormEvent) => {
    event.preventDefault();
    if (isVerifying) return;
    setIsVerifying(true);
    setAccessError(null);
    try {
      const res = await fetch('/api/verify-access', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: accessPassword }),
      });
      if (!res.ok) {
        setAccessError('Incorrect access code. Try again.');
        return;
      }
      const submitted = accessPassword;
      setIsAccessOpen(false);
      setAccessPassword('');
      await handleStartConversation(submitted);
    } catch {
      setAccessError('Could not verify access. Check your connection.');
    } finally {
      setIsVerifying(false);
    }
  };

  const handleStartConversation = async (password: string) => {
    setIsLoading(true);
    setError(null);

    try {
      // 1. Fetch RTC token + channel
      // console.log('Fetching Agora token...');
      const agoraResponse = await fetch('/api/generate-agora-token');
      const responseData = await agoraResponse.json();
      // console.log('Agora token response: uid =', responseData.uid, 'channel =', responseData.channel);

      if (!agoraResponse.ok) {
        throw new Error(
          `Failed to generate Agora token: ${JSON.stringify(responseData)}`,
        );
      }

      const { default: AgoraRTM } = await import('agora-rtm');
      const rtm: RTMClient = new AgoraRTM.RTM(
        process.env.NEXT_PUBLIC_AGORA_APP_ID!,
        responseData.uid,
      );
      await rtm.login({ token: responseData.token });
      await rtm.subscribe(responseData.channel);

      setRtmClient(rtm);
      setAgoraData({
        ...responseData,
        agentUid: process.env.NEXT_PUBLIC_AGENT_UID,
        mediaUid: process.env.NEXT_PUBLIC_MATCH_FEED_UID,
        sourceMode: 'agora-gateway',
      });
      setSessionAccessPassword(password);
      setShowConversation(true);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to start conversation. Please try again.',
      );
      console.error('Error starting conversation:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleTokenWillExpire = useCallback(
    async (uid: string): Promise<AgoraRenewalTokens> => {
      try {
        const channel = agoraData?.channel;
        if (!channel) {
          throw new Error('Missing channel for token renewal');
        }

        // RTC and RTM tokens are renewed independently:
        //   - RTC uses the browser client's assigned UID (passed in from ConversationComponent).
        //   - RTM uses the same UID that was used during RTM login (agoraData.uid).
        // Both are fetched in parallel to stay within the token-expiry grace-period window.
        const [rtcResponse, rtmResponse] = await Promise.all([
          fetch(`/api/generate-agora-token?channel=${channel}&uid=${uid}`),
          fetch(`/api/generate-agora-token?channel=${channel}&uid=${agoraData.uid}`),
        ]);
        const [rtcData, rtmData] = await Promise.all([
          rtcResponse.json(),
          rtmResponse.json(),
        ]);

        if (!rtcResponse.ok || !rtmResponse.ok) {
          throw new Error('Failed to generate renewal tokens');
        }

        return {
          rtcToken: rtcData.token,
          rtmToken: rtmData.token,
        };
      } catch (error) {
        console.error('Error renewing token:', error);
        throw error;
      }
    },
    [agoraData],
  );

  const handleEndConversation = async () => {
    // Tear down RTM — owned here since we created it here
    rtmClient?.logout().catch((err) => console.error('RTM logout error:', err));
    setRtmClient(null);
    setShowConversation(false);
  };

  // Live session: desktop stays viewport-locked; mobile scrolls naturally.
  if (showConversation) {
    return (
      <div className="theme-dark booth-stage relative flex min-h-dvh flex-col overflow-y-auto text-foreground lg:h-dvh lg:overflow-hidden">
        <div className="flex min-h-0 flex-1 flex-col items-stretch justify-start">
          <div className="z-10 flex h-full min-h-0 w-full flex-1 flex-col items-stretch gap-0 px-0 text-left">
            {agoraData && rtmClient ? (
              <>
                {/* Browser-only conversation mount: RTC provider, error boundary, and lazy-loaded call UI. */}
                <Suspense fallback={<LoadingSkeleton />}>
                  <ErrorBoundary>
                    <AgoraProvider>
                      <ConversationComponent
                        agoraData={agoraData}
                        rtmClient={rtmClient}
                        match={selectedMatch}
                        accessPassword={sessionAccessPassword}
                        onTokenWillExpire={handleTokenWillExpire}
                        onEndConversation={handleEndConversation}
                      />
                    </AgoraProvider>
                  </ErrorBoundary>
                </Suspense>
              </>
            ) : (
              /* Fallback if session bootstrap partially succeeded but required state is missing. */
              <p className="text-sm text-muted-foreground">
                Failed to load conversation data.
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Pre-call lobby: the broadcast control-room stage that frames the booth console.
  return (
    <div className="booth-stage relative flex min-h-dvh flex-col text-white">
      <div className="relative z-10 flex flex-1 flex-col">
        <QuickstartLobbyFrame>
          <QuickstartPreCallCard
            isLoading={isLoading}
            error={error}
            selectedMatch={selectedMatch}
            onStartConversation={handleOpenAccessGate}
          />
        </QuickstartLobbyFrame>
      </div>

      {isAccessOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="access-gate-title"
          onClick={() => {
            if (!isVerifying) setIsAccessOpen(false);
          }}
        >
          <form
            className="w-full max-w-sm rounded-lg border border-[#163f34] bg-[#070f0c] p-5 text-left text-white shadow-[0_30px_80px_rgba(0,0,0,0.6)]"
            onClick={(event) => event.stopPropagation()}
            onSubmit={handleSubmitAccess}
          >
            <div className="mb-3 inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.24em] text-primary">
              <Lock className="h-3.5 w-3.5" />
              Access required
            </div>
            <h2
              id="access-gate-title"
              className="text-base font-semibold text-white"
            >
              Enter access code
            </h2>
            <p className="mt-2 text-sm leading-6 text-white/60">
              This live booth is in private preview. Enter the access code to
              start the AI commentator.
            </p>
            <input
              type="password"
              autoFocus
              value={accessPassword}
              onChange={(event) => {
                setAccessPassword(event.target.value);
                if (accessError) setAccessError(null);
              }}
              placeholder="Access code"
              aria-label="Access code"
              aria-invalid={accessError ? true : undefined}
              autoComplete="off"
              className="mt-4 h-10 w-full rounded-md border border-white/15 bg-white/[0.04] px-3 text-sm text-white outline-none placeholder:text-white/35 focus-visible:border-primary/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-[#070f0c]"
            />
            {accessError ? (
              <p className="mt-2 text-xs text-red-400">{accessError}</p>
            ) : null}
            <div className="mt-5 flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-9 border-white/15 bg-transparent px-4 text-white/80 hover:bg-white/10 hover:text-white"
                onClick={() => setIsAccessOpen(false)}
                disabled={isVerifying}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                size="sm"
                className="h-9 px-4"
                disabled={isVerifying || !accessPassword.trim()}
              >
                {isVerifying ? 'Checking…' : 'Continue'}
              </Button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
