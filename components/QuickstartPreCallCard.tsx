'use client';

import Image from 'next/image';
import { Activity, ArrowRight, Eye, Loader2, Mic2, RadioTower } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { CommentaryMatch } from '@/types/conversation';

type QuickstartPreCallCardProps = {
  isLoading: boolean;
  error: string | null;
  selectedMatch: CommentaryMatch;
  onStartConversation: () => void;
};

export function QuickstartPreCallCard({
  isLoading,
  error,
  selectedMatch,
  onStartConversation,
}: QuickstartPreCallCardProps) {
  return (
    <div className="mx-auto w-[min(94vw,72rem)] animate-fade-up">
      <section className="group overflow-hidden rounded-lg border border-[#163f34] bg-[#050c0a] text-left shadow-[0_22px_58px_rgba(0,0,0,0.38)] transition duration-300 hover:border-primary/55 hover:shadow-[0_28px_78px_rgba(0,0,0,0.46)]">
        <div className="grid lg:grid-cols-[1.35fr_0.65fr]">
          <div className="relative aspect-[4/5] bg-[#07130f] sm:aspect-video lg:aspect-auto lg:min-h-[31rem]">
            <Image
              key={selectedMatch.id}
              src={selectedMatch.posterUrl}
              alt={selectedMatch.title}
              fill
              sizes="(min-width: 1024px) 58vw, 94vw"
              unoptimized
              priority
              className="object-cover opacity-90 transition duration-500 group-hover:scale-[1.018] group-hover:saturate-[0.82]"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-black/84 via-black/28 to-black/24 transition duration-300 group-hover:via-black/42" />
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(0,0,0,0.24)_0%,rgba(0,0,0,0.04)_34%,rgba(0,0,0,0.28)_100%)] transition duration-300 group-hover:bg-[radial-gradient(circle_at_center,rgba(0,0,0,0.38)_0%,rgba(0,0,0,0.14)_36%,rgba(0,0,0,0.34)_100%)]" />
            <div className="absolute right-4 top-4 flex items-center gap-2 rounded-full border border-white/18 bg-black/72 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-white shadow-[0_10px_28px_rgba(0,0,0,0.35)] backdrop-blur">
              <span className="h-2 w-2 rounded-full bg-red-500 shadow-[0_0_14px_rgba(239,68,68,0.85)]" />
              AI live
            </div>
            <div className="absolute inset-0 flex items-center justify-center px-5">
              <Button
                onClick={onStartConversation}
                disabled={isLoading}
                className="h-16 min-w-[15.5rem] gap-3 rounded-lg border border-cyan-100/80 bg-[#60dcff] px-8 text-base font-black uppercase tracking-[0.08em] text-[#041513] shadow-[0_0_0_8px_rgba(3,169,244,0.18),0_24px_62px_rgba(3,169,244,0.42)] transition-[transform,background-color,border-color,box-shadow] duration-200 hover:scale-[1.07] hover:border-white hover:bg-[#8be8ff] hover:text-[#041513] hover:shadow-[0_0_0_10px_rgba(3,169,244,0.22),0_30px_78px_rgba(3,169,244,0.52)] focus-visible:scale-[1.04] disabled:hover:scale-100 disabled:hover:border-cyan-100/80 disabled:hover:bg-[#60dcff] disabled:hover:text-[#041513] md:h-[4.5rem] md:min-w-[17rem] md:text-lg"
                aria-label={
                  isLoading ? 'Entering live booth' : 'Enter live booth'
                }
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Entering...
                  </>
                ) : (
                  <>
                    <span>Enter Live Booth</span>
                    <ArrowRight className="h-5 w-5 stroke-[2.6]" />
                  </>
                )}
              </Button>
            </div>

            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/68 via-black/10 to-transparent p-4 pt-10 md:p-5 md:pt-14">
              <div className="mb-3 flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary">
                <RadioTower className="h-4 w-4" />
                <span>{selectedMatch.gameDate}</span>
              </div>
              <h2 className="max-w-4xl text-2xl font-semibold leading-tight text-white md:text-4xl">
                {selectedMatch.title}
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-white/78 md:text-base">
                {selectedMatch.competition} · {selectedMatch.venue}
              </p>
            </div>
          </div>

          <aside className="flex flex-col justify-between gap-6 border-t border-white/10 bg-[#06100d] p-5 lg:border-t-0 lg:p-6">
            <div>
              <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-red-500/35 bg-red-500/12 px-2.5 py-1 font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-red-300">
                <span className="h-1.5 w-1.5 rounded-full bg-red-400 shadow-[0_0_12px_rgba(248,113,113,0.8)]" />
                Waiting for signal
              </div>
              <h3 className="text-xl font-semibold leading-tight text-white">
                Turn a live match into an AI commentary booth.
              </h3>
              <p className="mt-3 text-sm leading-6 text-white/62">
                Enter the booth, wait for the live feed, then start the AI
                commentator when the match is moving. Stop the AI without
                interrupting the broadcast.
              </p>
            </div>

            <div className="grid gap-3">
              <div className="flex gap-3 rounded-lg border border-white/10 bg-white/[0.025] p-3">
                <Activity className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <div>
                  <p className="text-sm font-semibold text-white">
                    Live match input
                  </p>
                  <p className="mt-1 text-xs leading-5 text-white/52">
                    A live source pushes RTMP into Media Gateway as the match feed UID.
                  </p>
                </div>
              </div>
              <div className="flex gap-3 rounded-lg border border-white/10 bg-white/[0.025] p-3">
                <Eye className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <div>
                  <p className="text-sm font-semibold text-white">
                    AI watches the same feed
                  </p>
                  <p className="mt-1 text-xs leading-5 text-white/52">
                    The viewer and backend subscribe to RTC video; the browser does not capture screenshots.
                  </p>
                </div>
              </div>
              <div className="flex gap-3 rounded-lg border border-white/10 bg-white/[0.025] p-3">
                <Mic2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <div>
                  <p className="text-sm font-semibold text-white">
                    AI voice returns live
                  </p>
                  <p className="mt-1 text-xs leading-5 text-white/52">
                    The commentator samples frames and publishes voice back to RTC.
                  </p>
                </div>
              </div>
            </div>

          </aside>
        </div>
        {error && <p className="px-5 py-3 text-xs text-destructive">{error}</p>}
      </section>
    </div>
  );
}
