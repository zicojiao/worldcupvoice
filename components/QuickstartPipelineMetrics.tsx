'use client';

export type QuickstartAgentMetric = {
  type: string;
  name: string;
  value: number;
  timestamp: number;
};

type QuickstartPipelineMetricsProps = {
  metrics: QuickstartAgentMetric[];
};

const PIPELINE = [
  {
    key: 'obs',
    label: 'RTMP ingest',
    metricTypes: ['obs', 'rtmp'],
    description: 'A live source (OBS, encoder) sends RTMP upstream.',
  },
  {
    key: 'gateway',
    label: 'Agora Media Gateway',
    metricTypes: ['gateway', 'ingest'],
    description: 'Agora Media Gateway turns the RTMP input into an RTC feed.',
  },
  {
    key: 'rtc',
    label: 'Agora RTC + Web SDK',
    metricTypes: ['rtc', 'video'],
    description: 'The browser subscribes to the live video with Agora Web SDK.',
  },
  {
    key: 'server',
    label: 'Agora Python Server SDK',
    metricTypes: ['server', 'agent'],
    description: 'The backend agent subscribes to the live RTC video stream.',
  },
  {
    key: 'mllm',
    label: 'OpenAI Vision',
    metricTypes: ['mllm', 'llm'],
    description: 'The AI commentator reasons over sampled live frames.',
  },
  {
    key: 'audio',
    label: 'AI Audio to RTC',
    metricTypes: ['audio', 'tts'],
    description: 'Generated commentary audio is published back to the channel.',
  },
] as const;

function formatMetricName(name: string) {
  return name.replace(/[_-]+/g, ' ');
}

export function QuickstartPipelineMetrics({
  metrics,
}: QuickstartPipelineMetricsProps) {
  const latestByType = new Map<string, QuickstartAgentMetric>();
  for (const metric of metrics) {
    latestByType.set(metric.type.toLowerCase(), metric);
  }

  return (
    <div className="flex min-w-0 max-w-full flex-wrap items-center gap-x-1.5 gap-y-1">
      <span className="shrink-0 text-xs font-medium leading-5 text-muted-foreground">
        Live ingest path
      </span>
      {PIPELINE.map((step, index) => {
        const metric = step.metricTypes
          .map((type) => latestByType.get(type))
          .find(Boolean);

        return (
          <div key={step.key} className="flex min-w-0 items-center gap-1.5">
            {index > 0 && (
              <span className="text-xs text-muted-foreground" aria-hidden="true">
                /
              </span>
            )}
            <span
              className="rounded-md border border-border bg-transparent px-1.5 py-0.5 text-[11px] font-semibold leading-4 text-foreground shadow-sm"
              title={step.description}
            >
              {step.label}
              {metric && (
                <span
                  className="ml-2 text-primary"
                  title={new Date(metric.timestamp).toLocaleTimeString()}
                >
                  {formatMetricName(metric.name)} {Math.round(metric.value)}ms
                </span>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}
