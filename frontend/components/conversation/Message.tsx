import { cn } from '@/lib/utils';

export default function Message({
  role,
  pageId,
  children,
}: {
  role: 'user' | 'assistant' | 'system';
  pageId?: string | null;
  children: React.ReactNode;
}) {
  const isUser = role === 'user';
  return (
    <div className={cn('flex gap-3', isUser ? 'justify-end' : 'justify-start')}>
      {!isUser && (
        <div className="mt-0.5 grid h-7 w-7 place-items-center rounded-full bg-zinc-900 text-[10px] font-bold text-white dark:bg-white dark:text-zinc-900">
          AI
        </div>
      )}
      <div
        className={cn(
          'max-w-[80%] rounded-2xl px-3 py-2 text-sm shadow-sm',
          isUser
            ? 'bg-zinc-900 text-white dark:bg-white dark:text-zinc-900'
            : 'bg-white text-zinc-900 dark:bg-zinc-900 dark:text-zinc-100 border border-zinc-200 dark:border-zinc-800',
        )}
      >
        <div className="whitespace-pre-wrap">{children}</div>
        {pageId ? (
          <a
            href={`/preview/${pageId}`}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 inline-block cursor-pointer text-xs text-blue-600 hover:underline dark:text-blue-400"
          >
            查看生成的页面 →
          </a>
        ) : null}
      </div>
      {isUser && (
        <div className="mt-0.5 grid h-7 w-7 place-items-center rounded-full bg-zinc-900 text-[10px] font-bold text-white dark:bg-white dark:text-zinc-900">
          我
        </div>
      )}
    </div>
  );
}