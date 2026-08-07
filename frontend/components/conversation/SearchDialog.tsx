'use client';

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Search } from 'lucide-react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { searchConversations, type SearchResultItem } from '@/lib/api';

export default function SearchDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [searching, setSearching] = useState(false);

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    try {
      const data = await searchConversations(q);
      setResults(data.results);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '搜索失败');
    } finally {
      setSearching(false);
    }
  }

  function handleSelect(id: string) {
    router.push(`/conversations/${id}`);
    onOpenChange(false);
    setQuery('');
    setResults([]);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>搜索会话</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSearch} className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="输入关键词搜索..."
            className="pl-9"
            autoFocus
          />
        </form>

        <div className="max-h-96 space-y-2 overflow-y-auto">
          {searching ? (
            <p className="text-sm text-muted-foreground">搜索中...</p>
          ) : results.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {query ? '无匹配结果' : '输入关键词后回车搜索'}
            </p>
          ) : (
            results.map((r) => (
              <button
                key={r.conversation_id}
                type="button"
                onClick={() => handleSelect(r.conversation_id)}
                className="w-full rounded-lg border border-zinc-200 p-3 text-left hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{r.title || '无标题'}</span>
                  <Badge variant="secondary">得分 {r.score.toFixed(2)}</Badge>
                </div>
                {r.highlights.length > 0 ? (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {r.highlights.map((h, i) => (
                      <span
                        key={i}
                        className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200"
                        dangerouslySetInnerHTML={{ __html: h }}
                      />
                    ))}
                  </div>
                ) : null}
                <div className="mt-1 text-xs text-muted-foreground">
                  消息 {r.message_count}
                  {r.last_message_at
                    ? ` · ${new Date(r.last_message_at).toLocaleString('zh-CN')}`
                    : ''}
                </div>
              </button>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}