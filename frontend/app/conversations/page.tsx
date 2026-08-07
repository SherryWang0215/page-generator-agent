'use client';

import { useRouter } from 'next/navigation';
import AppShell from '@/components/layout/AppShell';
import Header from '@/components/conversation/Header';
import ChatPane from '@/components/conversation/ChatPane';
import { useConversations } from '@/lib/useConversations';
import { archiveConversation, createConversation, type MessageItem } from '@/lib/api';

export default function ConversationsPage() {
  const router = useRouter();
  const { conversations, refresh } = useConversations();

  async function handleNewChat() {
    const conv = await createConversation();
    await refresh();
    router.push(`/conversations/${conv.conversation_id}`);
  }

  async function handleArchive(id: string) {
    await archiveConversation(id);
    await refresh();
  }

  return (
    <AppShell
      conversations={conversations}
      selectedId={null}
      onSelectConversation={(id) => router.push(`/conversations/${id}`)}
      onNewChat={handleNewChat}
      onArchive={handleArchive}
      onSearchClick={() => {}}
      onProfileClick={() => {}}
    >
      <Header sidebarCollapsed={false} setMobileOpen={() => {}} />
      <ChatPane
        conversation={null}
        messages={[] as MessageItem[]}
        isThinking={false}
        onPauseThinking={() => {}}
        onSend={async () => {}}
        busy={false}
      />
    </AppShell>
  );
}