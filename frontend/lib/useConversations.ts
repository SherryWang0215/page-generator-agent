'use client';

import { useCallback, useEffect, useState } from 'react';
import { listConversations, type ConversationItem } from '@/lib/api';

export function useConversations() {
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listConversations();
      setConversations(data.conversations);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { conversations, setConversations, refresh, loading };
}
