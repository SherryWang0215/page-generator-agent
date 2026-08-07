'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { toast } from 'sonner';

import {
  archiveConversation,
  createConversation,
  fetchPage,
  sendMessage,
  waitForGenerationResult,
} from '@/lib/api';
import type { AgentTraceStep, PageDSL } from '@/lib/pageDsl';
import PageRenderer from '@/components/renderer/PageRenderer';
import AppShell from '@/components/layout/AppShell';
import Header from '@/components/conversation/Header';
import AgentTracePanel from '@/components/preview/AgentTracePanel';
import RevisionPanel from '@/components/preview/RevisionPanel';
import { useConversations } from '@/lib/useConversations';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

export default function PreviewPage() {
  const params = useParams<{ pageId: string }>();
  const router = useRouter();
  const pageId = params.pageId;

  const { conversations, refresh } = useConversations();

  const [page, setPage] = useState<PageDSL | null>(null);
  const [agentTrace, setAgentTrace] = useState<AgentTraceStep[]>([]);
  const [generationSource, setGenerationSource] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [revising, setRevising] = useState(false);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadPage() {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchPage(pageId);
        if (cancelled) return;
        setPage(result.page_dsl);
        setGenerationSource(result.generation_source ?? null);
        setAgentTrace(result.agent_trace ?? []);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : '加载失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadPage();
    return () => {
      cancelled = true;
    };
  }, [pageId]);

  async function handleRevise(instruction: string) {
    setRevising(true);
    setTaskStatus(null);
    try {
      let convId = conversationId;
      if (!convId) {
        const conv = await createConversation(pageId);
        convId = conv.conversation_id;
        setConversationId(convId);
      }
      const result = await sendMessage(convId, instruction);
      if (!result.request_id) throw new Error('修改任务未返回 request_id');
      setTaskStatus(`任务已提交：${result.request_id}`);
      const taskResult = await waitForGenerationResult(result.request_id, (status) => {
        setTaskStatus(`任务状态：${status}`);
      });
      if (!taskResult.page_id || !taskResult.page_dsl) {
        throw new Error('修改完成但缺少页面结果');
      }
      setPage(taskResult.page_dsl);
      setGenerationSource(taskResult.generation_source ?? null);
      setAgentTrace(taskResult.agent_trace ?? []);
      setTaskStatus(null);
      router.replace(`/preview/${taskResult.page_id}`);
    } catch (e) {
      setTaskStatus(null);
      const msg = e instanceof Error ? e.message : '修改失败';
      toast.error(msg);
    } finally {
      setRevising(false);
    }
  }

  async function handleArchive(id: string) {
    try {
      await archiveConversation(id);
      await refresh();
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="h-screen w-full bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-zinc-200/60 bg-white/80 px-4 py-2.5 backdrop-blur dark:border-zinc-800 dark:bg-zinc-900/70">
        <span className="text-sm text-muted-foreground">page_id: {pageId}</span>
        {page ? (
          <span className="text-sm text-muted-foreground">
            {page.page_meta.page_type} / {page.page_meta.theme}
            {generationSource ? ` / ${generationSource}` : ''}
          </span>
        ) : null}
        <div className="ml-auto">
          {conversationId ? (
            <Link href={`/conversations/${conversationId}`}>
              <Button variant="ghost" size="sm">
                查看对话记录 →
              </Button>
            </Link>
          ) : null}
        </div>
      </header>

      {loading ? (
        <div className="mx-auto max-w-6xl space-y-3 p-6">
          <Skeleton className="h-8 w-1/3" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : error ? (
        <div className="mx-auto max-w-2xl p-6">
          <div className="rounded-xl border border-red-200 p-6 text-center dark:border-red-900">
            <p className="text-red-600 dark:text-red-400">{error}</p>
            <Link href="/" className="mt-3 inline-block">
              <Button variant="outline" size="sm">
                返回首页
              </Button>
            </Link>
          </div>
        </div>
      ) : page ? (
        <div className="h-[calc(100vh-49px)] overflow-y-auto p-4">
          <div className="mx-auto max-w-5xl space-y-4">
            {/* 上方：Trace + Revision */}
            <AgentTracePanel trace={agentTrace} />
            <RevisionPanel onRevise={handleRevise} busy={revising} />
            {taskStatus ? (
              <div className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
                {taskStatus}
              </div>
            ) : null}

            {/* 下方：生成的页面 */}
            <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
              <PageRenderer page={page} />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}