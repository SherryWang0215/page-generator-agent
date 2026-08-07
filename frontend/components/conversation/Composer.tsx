'use client';

import { useEffect, useRef, useState } from 'react';
import { Loader2, Send } from 'lucide-react';
import { cn } from '@/lib/utils';

export default function Composer({
  onSend,
  busy,
}: {
  onSend: (text: string) => Promise<void>;
  busy: boolean;
}) {
  const [value, setValue] = useState('');
  const [sending, setSending] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (inputRef.current) {
      const textarea = inputRef.current;
      const lineHeight = 24;
      textarea.style.height = 'auto';
      const scrollHeight = textarea.scrollHeight;
      const calculatedLines = Math.max(1, Math.ceil(scrollHeight / lineHeight));
      if (calculatedLines <= 12) {
        textarea.style.height = `${Math.max(lineHeight, scrollHeight)}px`;
        textarea.style.overflowY = 'hidden';
      } else {
        textarea.style.height = `${12 * lineHeight}px`;
        textarea.style.overflowY = 'auto';
      }
    }
  }, [value]);

  async function handleSend() {
    if (!value.trim() || sending) return;
    setSending(true);
    try {
      await onSend(value);
      setValue('');
      inputRef.current?.focus();
    } finally {
      setSending(false);
    }
  }

  const hasContent = value.trim().length > 0;

  return (
    <div className="border-t border-zinc-200/60 p-4 dark:border-zinc-800">
      <div
        className={cn(
          'mx-auto flex flex-col rounded-3xl border bg-white shadow-sm dark:bg-zinc-950 transition-all duration-200',
          'max-w-3xl border-zinc-200 dark:border-zinc-800',
        )}
      >
        <div className="flex-1 px-4 pt-4 pb-2">
          <textarea
            ref={inputRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="输入消息，如：帮我生成一个科技风格的落地页 / 把标题改得更商务一点"
            rows={1}
            className="w-full resize-none bg-transparent text-sm outline-none placeholder:text-zinc-400 transition-all duration-200 min-h-[24px] text-left leading-6"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void handleSend();
              }
            }}
          />
        </div>
        <div className="flex items-center justify-end px-3 pb-3">
          <button
            type="button"
            onClick={handleSend}
            disabled={sending || busy || !hasContent}
            className={cn(
              'inline-flex shrink-0 items-center justify-center rounded-full p-2.5 transition-colors',
              hasContent
                ? 'bg-zinc-900 text-white hover:bg-zinc-800 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200'
                : 'bg-zinc-200 text-zinc-400 dark:bg-zinc-800 dark:text-zinc-600 cursor-not-allowed',
            )}
          >
            {sending || busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
          </button>
        </div>
      </div>
    </div>
  );
}