'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Calendar, LayoutGrid, MoreHorizontal } from 'lucide-react';
import type { ConversationItem } from '@/lib/api';
import type { Theme } from '@/components/ThemeToggle';
import GhostIconButton from '@/components/GhostIconButton';
import Sidebar from '@/components/conversation/Sidebar';
import Header from '@/components/conversation/Header';

export default function AppShell({
  conversations,
  selectedId,
  onSelectConversation,
  onNewChat,
  onArchive,
  onSearchClick,
  onProfileClick,
  children,
}: {
  conversations: ConversationItem[];
  selectedId: string | null;
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  onArchive: (id: string) => void;
  onSearchClick: () => void;
  onProfileClick: () => void;
  children: React.ReactNode;
}) {
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof window === 'undefined') return 'light';
    const saved = localStorage.getItem('theme');
    if (saved === 'light' || saved === 'dark') return saved;
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
    return 'light';
  });

  useEffect(() => {
    if (theme === 'dark') document.documentElement.classList.add('dark');
    else document.documentElement.classList.remove('dark');
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.style.colorScheme = theme;
    localStorage.setItem('theme', theme);
  }, [theme]);

  useEffect(() => {
    const media = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
    if (!media) return;
    const listener = (e: MediaQueryListEvent) => {
      const saved = localStorage.getItem('theme');
      if (!saved) setTheme(e.matches ? 'dark' : 'light');
    };
    media.addEventListener('change', listener);
    return () => media.removeEventListener('change', listener);
  }, []);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="h-screen w-full bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <div className="md:hidden sticky top-0 z-40 flex items-center gap-2 border-b border-zinc-200/60 bg-white/80 px-3 py-2 backdrop-blur dark:border-zinc-800 dark:bg-zinc-900/70">
        <Link href="/" className="ml-1 flex items-center gap-2 text-sm font-semibold tracking-tight">
          <span className="inline-flex h-4 w-4 items-center justify-center">✱</span> Page Generator
        </Link>
        <div className="ml-auto flex items-center gap-2">
          <GhostIconButton label="日程">
            <Calendar className="h-4 w-4" />
          </GhostIconButton>
          <GhostIconButton label="应用">
            <LayoutGrid className="h-4 w-4" />
          </GhostIconButton>
          <GhostIconButton label="更多">
            <MoreHorizontal className="h-4 w-4" />
          </GhostIconButton>
        </div>
      </div>

      <div className="mx-auto flex h-[calc(100vh-0px)] max-w-[1400px] overflow-hidden rounded-xl border border-zinc-200 dark:border-[color:var(--color-zinc-800)]">
        <Sidebar
          conversations={conversations}
          selectedId={selectedId}
          onSelect={onSelectConversation}
          onNewChat={onNewChat}
          onSearchClick={onSearchClick}
          onProfileClick={onProfileClick}
          onArchive={onArchive}
          sidebarCollapsed={sidebarCollapsed}
          setSidebarCollapsed={setSidebarCollapsed}
          theme={theme}
          setTheme={setTheme}
          mobileOpen={mobileOpen}
          setMobileOpen={setMobileOpen}
        />
        <main className="relative flex min-w-0 flex-1 flex-col">{children}</main>
      </div>
    </div>
  );
}