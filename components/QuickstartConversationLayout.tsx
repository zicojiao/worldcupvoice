'use client';

import { useState, type ReactNode } from 'react';
import { RadioTower } from 'lucide-react';
import { Button } from '@/components/ui/button';

type QuickstartConversationLayoutProps = {
  statusPanel: ReactNode;
  pipelineMetrics: ReactNode;
  transcriptPanel: ReactNode;
  visualizer: ReactNode;
  controls?: ReactNode;
  onEndConversation: () => void;
};

export function QuickstartConversationLayout({
  statusPanel,
  pipelineMetrics,
  transcriptPanel,
  visualizer,
  controls,
  onEndConversation,
}: QuickstartConversationLayoutProps) {
  const [isEndConfirmOpen, setIsEndConfirmOpen] = useState(false);

  return (
    <div className="flex min-h-0 flex-1 flex-col text-left">
      <header className="flex shrink-0 flex-col gap-3 border-b border-border px-4 py-3 md:min-h-[84px] md:flex-row md:items-center md:justify-between md:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
            <RadioTower className="h-5 w-5" />
          </div>
          <div className="flex min-w-0 flex-col justify-center gap-1">
            <span className="truncate text-base font-semibold leading-none text-foreground md:text-lg">
              World Cup Voice
            </span>
            {pipelineMetrics}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2 md:pr-1">
          {statusPanel}
          <Button
            variant="destructive"
            size="sm"
            className="h-8 rounded-md border border-destructive bg-transparent px-3 text-xs font-medium text-destructive hover:bg-destructive/10"
            onClick={() => setIsEndConfirmOpen(true)}
            aria-label="Leave live booth"
            title="Leave live booth"
          >
            Leave Booth
          </Button>
        </div>
      </header>

      <div className="flex w-full flex-1 flex-col gap-4 px-3 pb-4 pt-3 md:px-6 md:pt-4 lg:min-h-0 lg:flex-row lg:gap-0">
        <aside className="order-2 h-[18rem] w-full shrink-0 md:h-[22rem] lg:order-1 lg:h-full lg:min-h-0 lg:w-[24rem] xl:w-[26rem]">
          {transcriptPanel}
        </aside>

        <main className="order-1 flex w-full flex-col lg:order-2 lg:min-h-0 lg:flex-1 lg:border-l lg:border-border/80 lg:pl-6">
          <div className="flex flex-col pb-1 pt-1 md:pb-4 md:pt-2 lg:min-h-0 lg:flex-1">
            <div className="flex w-full items-center justify-center lg:min-h-0 lg:flex-1">
              {visualizer}
            </div>
            {controls ? (
              <div className="max-h-[40vh] shrink-0 overflow-y-auto pt-4 lg:max-h-[38vh]">
                {controls}
              </div>
            ) : null}
          </div>
        </main>
      </div>

      {isEndConfirmOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="end-session-title"
          onClick={() => setIsEndConfirmOpen(false)}
        >
          <div
            className="w-full max-w-sm rounded-lg border border-border bg-card p-5 shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <h2
              id="end-session-title"
              className="text-base font-semibold text-foreground"
            >
              Leave live booth?
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              This only disconnects your browser from the booth. The live source
              keeps streaming, and AI commentary has its own Start/Stop control.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                className="h-9 px-4"
                onClick={() => setIsEndConfirmOpen(false)}
                autoFocus
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                size="sm"
                className="h-9 px-4"
                onClick={() => {
                  setIsEndConfirmOpen(false);
                  onEndConversation();
                }}
              >
                Leave Booth
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
