'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { toast } from 'sonner';

import {
  archiveConversation,
  createConversation,
  getConversation,
  sendMessage,
  waitForGenerationResult,
  type ConversationItem,
  type MessageItem,
} from '@/lib/api';
import AppShell from '@/components/layout/AppShell';
import Header from '@/components/conversation/Header';
import ChatPane from '@/components/conversation/ChatPane';
import { useConversations } from '@/lib/useConversations';
import { Button } from '@/components/ui/button';
import SearchDialog from '@/components/conversation/SearchDialog';
import ProfileDialog from '@/components/conversation/ProfileDialog';

export default function ConversationDetailPage() {
  const params = useParams<{ conversationId: string }>();
  const router = useRouter();
  const conversationId = params.conversationId;

  const { conversations, refresh } = useConversations();
  const [conversation, setConversation] = useState<ConversationItem | null>(null);
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);

  const [searchOpen, setSearchOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  const loadConversation = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getConversation(conversationId);
      setConversation(data.conversation);
      setMessages(data.messages);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '加载会话失败');
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    void loadConversation();
  }, [loadConversation]);

  async function handleSend(text: string) {
    setSending(true);
    setTaskStatus(null);
    const now = new Date().toISOString();
    const optimistic: MessageItem = {
      message_id: `opt-${Date.now()}`,
      conversation_id: conversationId,
      role: 'user',
      content: text,
      metadata: {},
      created_at: now,
    };
    setMessages((prev) => [...prev, optimistic]);
    setIsThinking(true);

    try {
      const result = await sendMessage(conversationId, text);
      if (result.request_id) {
        setTaskStatus(`任务已提交：${result.request_id}`);
        const taskResult = await waitForGenerationResult(result.request_id, (status) => {
          setTaskStatus(`任务状态：${status}`);
        });
        setTaskStatus(null);
      }
      await loadConversation();
      await refresh();
    } catch (e) {
      const msg = e instanceof Error ? e.message : '发送失败';
      toast.error(msg);
    } finally {
      setIsThinking(false);
      setSending(false);
    }
  }

  async function handleNewChat() {
    const conv = await createConversation();
    await refresh();
    router.push(`/conversations/${conv.conversation_id}`);
  }

  async function handleArchive(id: string) {
    await archiveConversation(id);
    await refresh();
    if (id === conversationId) {
      router.push('/conversations');
    }
  }

  return (
    <AppShell
      conversations={conversations}
      selectedId={conversationId}
      onSelectConversation={(id) => router.push(`/conversations/${id}`)}
      onNewChat={handleNewChat}
      onArchive={handleArchive}
      onSearchClick={() => setSearchOpen(true)}
      onProfileClick={() => setProfileOpen(true)}
    >
      <Header sidebarCollapsed={false} setMobileOpen={() => {}}>
        {conversation ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void handleArchive(conversationId)}
          >
            归档
          </Button>
        ) : null}
      </Header>

      {loading ? (
        <div className="flex flex-1 items-center justify-center text-muted-foreground">
          加载中...
        </div>
      ) : (
        <ChatPane
          conversation={conversation}
          messages={messages}
          isThinking={isThinking}
          onPauseThinking={() => setIsThinking(false)}
          onSend={handleSend}
          busy={sending}
        />
      )}

      {taskStatus ? (
        <div className="border-t border-zinc-200/60 bg-muted/30 px-4 py-2 text-center text-xs text-muted-foreground dark:border-zinc-800">
          {taskStatus}
        </div>
      ) : null}

      <SearchDialog open={searchOpen} onOpenChange={setSearchOpen} />
      <ProfileDialog open={profileOpen} onOpenChange={setProfileOpen} />
    </AppShell>
  );
}