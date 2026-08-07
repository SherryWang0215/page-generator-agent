'use client';

import { Trash2 } from 'lucide-react';
import { cn, timeAgo } from '@/lib/utils';
import type { ConversationItem } from '@/lib/api';

export default function ConversationRow({
  data,
  active,
  onSelect,
  onArchive,
}: {
  data: ConversationItem;
  active: boolean;
  onSelect: () => void;
  onArchive: () => void;
}) {
  return (
    <div className="group relative">
      <button
        type="button"
        onClick={onSelect}
        className={cn(
          '-mx-1 flex w-[calc(100%+8px)] items-center gap-2 rounded-lg px-2 py-2 text-left',
          active
            ? 'bg-zinc-100 text-zinc-900 dark:bg-zinc-800/60 dark:text-zinc-100'
            : 'hover:bg-zinc-100 dark:hover:bg-zinc-800',
        )}
        title={data.title ?? '新对话'}
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-medium tracking-tight">
              {data.title || '新对话'}
            </span>
            <span className="shrink-0 text-[11px] text-zinc-500 dark:text-zinc-400">
              {timeAgo(data.updated_at)}
            </span>
          </div>
        </div>
        <span
          role="button"
          tabIndex={0}
          onClick={(e) => {
            e.stopPropagation();
            onArchive();
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              e.stopPropagation();
              onArchive();
            }
          }}
          className="cursor-pointer rounded-md p-1 text-zinc-500 opacity-0 transition group-hover:opacity-100 hover:bg-zinc-200/50 hover:text-red-600 dark:text-zinc-300 dark:hover:bg-zinc-700/60 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          aria-label="归档会话"
          title="归档"
        >
          <Trash2 className="h-4 w-4" />
        </span>
      </button>
    </div>
  );
}