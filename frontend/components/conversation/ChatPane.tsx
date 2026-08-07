'use client';

import { useEffect, useRef } from 'react';
import { Loader2, Square } from 'lucide-react';
import type { ConversationItem, MessageItem } from '@/lib/api';
import Message from './Message';
import Composer from './Composer';

function ThinkingMessage({ onPause }: { onPause: () => void }) {
  return (
    <Message role="assistant">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1">
          <div className="h-2 w-2 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.3s]" />
          <div className="h-2 w-2 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.15s]" />
          <div className="h-2 w-2 animate-bounce rounded-full bg-zinc-400" />
        </div>
        <span className="text-sm text-zinc-500">AI 思考中...</span>
        <button
          type="button"
          onClick={onPause}
          className="ml-auto inline-flex items-center gap-1 rounded-full border border-zinc-300 px-2 py-1 text-xs text-zinc-600 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800"
        >
          <Square className="h-3 w-3" /> 取消
        </button>
      </div>
    </Message>
  );
}

export default function ChatPane({
  conversation,
  messages,
  isThinking,
  onPauseThinking,
  onSend,
  busy,
}: {
  conversation: ConversationItem | null;
  messages: MessageItem[];
  isThinking: boolean;
  onPauseThinking: () => void;
  onSend: (text: string) => Promise<void>;
  busy: boolean;
}) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      <div className="flex-1 space-y-5 overflow-y-auto px-4 py-6 sm:px-8">
        {conversation ? (
          <>
            <div className="mb-2 text-2xl font-semibold tracking-tight">
              {conversation.title || '新对话'}
            </div>
            <div className="mb-4 text-sm text-zinc-500 dark:text-zinc-400">
              {conversation.page_id ? (
                <a
                  href={`/preview/${conversation.page_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="cursor-pointer text-blue-600 hover:underline dark:text-blue-400"
                >
                  查看关联页面 →
                </a>
              ) : (
                '暂无关联页面'
              )}
            </div>
          </>
        ) : (
          <div className="mb-2 text-2xl font-semibold tracking-tight">新对话</div>
        )}

        {messages.length === 0 ? (
          <div className="rounded-xl border border-dashed border-zinc-300 p-6 text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
            还没有消息，在下方输入开始对话。
          </div>
        ) : (
          <>
            {messages.map((m) => (
              <Message
                key={m.message_id}
                role={m.role}
                pageId={(m.metadata?.page_id as string | undefined) ?? null}
              >
                {m.content}
              </Message>
            ))}
            {isThinking && <ThinkingMessage onPause={onPauseThinking} />}
          </>
        )}
        <div ref={endRef} />
      </div>

      <Composer onSend={onSend} busy={busy} />
    </div>
  );
}