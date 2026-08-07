import { cn } from '@/lib/utils';
import type { AgentTraceStep } from '@/lib/pageDsl';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Badge } from '@/components/ui/badge';
import { ChevronDown } from 'lucide-react';
import { useState } from 'react';

function MetadataSummary({ metadata }: { metadata: Record<string, unknown> }) {
  const keys = Object.keys(metadata);
  if (!keys.length) return null;
  const preview = keys
    .slice(0, 3)
    .map((k) => {
      const v = metadata[k];
      if (v === null || v === undefined) return `${k}: -`;
      if (typeof v === 'string') return `${k}: ${v.length > 16 ? v.slice(0, 16) + '…' : v}`;
      if (typeof v === 'object') return `${k}: {…}`;
      return `${k}: ${String(v)}`;
    })
    .join(' · ');
  return (
    <div className="mt-1 truncate text-[11px] text-muted-foreground" title={preview}>
      {preview}
      {keys.length > 3 ? ` · +${keys.length - 3}` : ''}
    </div>
  );
}

function StepCard({ step }: { step: AgentTraceStep }) {
  const [open, setOpen] = useState(false);
  const hasMeta = Object.keys(step.metadata).length > 0;
  return (
    <div className="rounded-lg border border-zinc-200 p-3 text-xs dark:border-zinc-800">
      <div className="mb-2 flex items-center justify-between gap-2 font-semibold">
        <span>{step.node}</span>
        <Badge variant={step.status === 'success' ? 'default' : 'destructive'}>
          {step.status}
        </Badge>
      </div>
      <div className="text-muted-foreground">{step.duration_ms} ms</div>
      {step.message ? (
        <div className="mt-1 text-muted-foreground">{step.message}</div>
      ) : null}
      {hasMeta ? (
        <>
          <MetadataSummary metadata={step.metadata} />
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="mt-1 text-[11px] font-medium text-blue-600 hover:underline dark:text-blue-400"
          >
            {open ? '收起详情' : '查看详情'}
          </button>
          {open ? (
            <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-all rounded bg-zinc-50 p-2 text-[11px] text-muted-foreground dark:bg-zinc-900">
              {JSON.stringify(step.metadata, null, 2)}
            </pre>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

export default function AgentTracePanel({ trace }: { trace: AgentTraceStep[] }) {
  const [open, setOpen] = useState(false);
  if (!trace.length) return null;

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-xl border border-zinc-200 dark:border-zinc-800">
      <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-sm font-semibold">
        <span>Agent Trace ({trace.length})</span>
        <ChevronDown className={cn('h-4 w-4 transition-transform', open && 'rotate-180')} />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="grid gap-3 px-4 pb-4">
          {trace.map((step) => (
            <StepCard key={step.node} step={step} />
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
