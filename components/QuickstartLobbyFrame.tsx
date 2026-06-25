'use client';

import type { ReactNode } from 'react';

const TECH_FLOW_STEPS = [
  {
    label: 'Source',
    title: 'Live source (OBS / encoder)',
    detail: 'Your computer, an OBS scene, or any encoder sends the live feed over RTMP.',
  },
  {
    label: 'Agora ingest',
    title: 'Agora Media Gateway',
    detail: 'RTMP is converted into an RTC publisher with the fixed match feed UID.',
  },
  {
    label: 'Agora RTC',
    title: 'Live RTC channel',
    detail: 'The browser and backend both subscribe to the same low-latency channel.',
  },
  {
    label: 'SDK clients',
    title: 'Viewer + AI commentator',
    detail: 'Agora Web SDK renders video; Python Server SDK samples frames and publishes AI audio.',
  },
];

const TECH_FLOW_CONNECTORS = ['RTMP', 'RTC', 'Agora SDKs'];
const STAGE_WIDTH = 'mx-auto w-[min(94vw,74rem)]';

export function QuickstartLobbyFrame({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-1 flex-col gap-8 pb-14 pt-8 md:gap-10 md:pb-16 md:pt-12">
      <header className={`${STAGE_WIDTH} animate-fade-up px-1`}>
        <div className="grid gap-6 lg:grid-cols-[1.08fr_0.92fr] lg:items-end">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.28em] text-primary/90">
              World Cup Voice
            </p>
            <h1 className="mt-3 max-w-4xl text-4xl font-semibold leading-[1.02] text-white md:text-6xl">
              An AI live commentator for sports streams.
            </h1>
          </div>
          <p className="max-w-2xl text-sm leading-7 text-white/65 md:text-base lg:pb-1">
            Send a live feed into a real-time channel, let the AI watch the same
            video as viewers, and hear its commentary come back live. The World
            Cup is the showcase here, but the same pipeline works for any live
            stream.
          </p>
        </div>
      </header>

      <div className="animate-fade-up animate-fade-up-d1">{children}</div>

      <section
        aria-label="Live streaming architecture"
        className={`${STAGE_WIDTH} animate-fade-up animate-fade-up-d1 px-1`}
      >
        <div className="rounded-lg border border-primary/25 bg-[#04100d]/86 p-4 shadow-[0_22px_58px_rgba(0,0,0,0.32)] backdrop-blur md:p-5">
          <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.26em] text-primary">
                Live streaming flow
              </p>
              <h2 className="mt-2 text-xl font-semibold text-white md:text-2xl">
                From live match feed to AI commentary, then back to viewers.
              </h2>
            </div>
          </div>

          <ol className="grid gap-3 lg:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr] lg:items-stretch">
            {TECH_FLOW_STEPS.map((item, index) => (
              <li
                key={item.label}
                className="contents"
              >
                <div className="rounded-lg border border-white/10 bg-white/[0.026] p-4">
                  <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-primary">
                    {item.label}
                  </p>
                  <p className="mt-2 text-base font-semibold text-white">
                    {item.title}
                  </p>
                  <p className="mt-1.5 text-xs leading-5 text-white/55">
                    {item.detail}
                  </p>
                </div>
                {index < TECH_FLOW_CONNECTORS.length ? (
                  <div
                    className="flex items-center justify-center lg:px-1"
                    aria-hidden="true"
                  >
                    <div className="flex w-full items-center gap-2 lg:w-auto lg:flex-col lg:gap-1">
                      <span className="h-px flex-1 bg-primary/25 lg:h-8 lg:w-px lg:flex-none" />
                      <span className="rounded-full border border-primary/25 bg-primary/10 px-2 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-primary">
                        {TECH_FLOW_CONNECTORS[index]}
                      </span>
                      <span className="h-px flex-1 bg-primary/25 lg:h-8 lg:w-px lg:flex-none" />
                    </div>
                  </div>
                ) : null}
              </li>
            ))}
          </ol>
        </div>
      </section>
    </div>
  );
}
