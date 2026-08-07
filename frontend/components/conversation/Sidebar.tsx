'use client';

import { Asterisk, PanelLeftClose, PanelLeftOpen, Plus, SearchIcon, User } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useIsMobile } from '@/hooks/use-mobile';
import type { ConversationItem } from '@/lib/api';
import type { Theme } from '@/components/ThemeToggle';
import ThemeToggle from '@/components/ThemeToggle';
import ConversationRow from './ConversationRow';

export default function Sidebar({
  conversations,
  selectedId,
  onSelect,
  onNewChat,
  onSearchClick,
  onProfileClick,
  onArchive,
  sidebarCollapsed,
  setSidebarCollapsed,
  theme,
  setTheme,
  mobileOpen,
  setMobileOpen,
}: {
  conversations: ConversationItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onSearchClick: () => void;
  onProfileClick: () => void;
  onArchive: (id: string) => void;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (v: boolean) => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
  mobileOpen: boolean;
  setMobileOpen: (v: boolean) => void;
}) {
  const isMobile = useIsMobile();

  if (sidebarCollapsed && !isMobile) {
    return (
      <aside className="z-50 flex h-full w-16 shrink-0 flex-col border-r border-zinc-200/60 bg-white transition-all duration-300 dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex items-center justify-center border-b border-zinc-200/60 px-3 py-3 dark:border-zinc-800">
          <button
            type="button"
            onClick={() => setSidebarCollapsed(false)}
            className="rounded-xl p-2 hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:hover:bg-zinc-800"
            aria-label="展开侧栏"
            title="展开侧栏"
          >
            <PanelLeftOpen className="h-5 w-5" />
          </button>
        </div>
        <div className="flex flex-1 flex-col items-center gap-2 pt-4">
          <button
            type="button"
            onClick={onNewChat}
            className="rounded-xl p-2.5 hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:hover:bg-zinc-800"
            title="新对话"
          >
            <Plus className="h-5 w-5" />
          </button>
          <button
            type="button"
            onClick={onSearchClick}
            className="rounded-xl p-2.5 hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:hover:bg-zinc-800"
            title="搜索会话"
          >
            <SearchIcon className="h-5 w-5" />
          </button>
        </div>
      </aside>
    );
  }

  return (
    <>
      {mobileOpen && isMobile && (
        <div
          className="fixed inset-0 z-40 bg-black/60 opacity-50 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}
      <aside
        className={cn(
          'z-50 flex h-full w-80 shrink-0 flex-col border-r border-zinc-200/60 bg-white dark:border-zinc-800 dark:bg-zinc-900',
          'fixed inset-y-0 left-0 md:static md:translate-x-0 transition-transform duration-300',
          mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
        )}
      >
        <div className="flex items-center gap-2 border-b border-zinc-200/60 px-3 py-3 dark:border-zinc-800">
          <div className="flex items-center gap-2">
            <div className="grid h-8 w-8 place-items-center rounded-xl bg-gradient-to-br from-blue-500 to-indigo-500 text-white shadow-sm dark:from-zinc-200 dark:to-zinc-300 dark:text-zinc-900">
              <Asterisk className="h-4 w-4" />
            </div>
            <div className="text-sm font-semibold tracking-tight">Page Generator</div>
          </div>
          <div className="ml-auto flex items-center gap-1">
            <button
              type="button"
              onClick={() => setSidebarCollapsed(true)}
              className="hidden md:block rounded-xl p-2 hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:hover:bg-zinc-800"
              aria-label="折叠侧栏"
              title="折叠侧栏"
            >
              <PanelLeftClose className="h-5 w-5" />
            </button>
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              className="md:hidden rounded-xl p-2 hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:hover:bg-zinc-800"
              aria-label="关闭侧栏"
            >
              <PanelLeftClose className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="px-3 pt-3">
          <button
            type="button"
            onClick={onSearchClick}
            className="flex w-full items-center gap-2 rounded-full border border-zinc-200 bg-white py-2 pl-3 pr-3 text-sm text-zinc-500 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950/50 dark:text-zinc-400"
          >
            <SearchIcon className="h-4 w-4" />
            <span>搜索会话…</span>
          </button>
        </div>

        <div className="px-3 pt-3">
          <button
            type="button"
            onClick={onNewChat}
            className="flex w-full items-center justify-center gap-2 rounded-full bg-zinc-900 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:bg-white dark:text-zinc-900"
            title="新对话"
          >
            <Plus className="h-4 w-4" /> 开始新对话
          </button>
        </div>

        <nav className="mt-4 flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto px-2 pb-4">
          <div className="px-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
            会话
          </div>
          {conversations.length === 0 ? (
            <div className="select-none rounded-lg border border-dashed border-zinc-200 px-3 py-3 text-center text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
              暂无会话，点击上方「开始新对话」
            </div>
          ) : (
            conversations
              .slice()
              .sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1))
              .map((c) => (
                <ConversationRow
                  key={c.conversation_id}
                  data={c}
                  active={c.conversation_id === selectedId}
                  onSelect={() => onSelect(c.conversation_id)}
                  onArchive={() => onArchive(c.conversation_id)}
                />
              ))
          )}
        </nav>

        <div className="mt-auto border-t border-zinc-200/60 px-3 py-3 dark:border-zinc-800">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onProfileClick}
              className="inline-flex items-center gap-2 rounded-lg px-2 py-2 text-sm hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:hover:bg-zinc-800"
            >
              <User className="h-4 w-4" /> 用户画像
            </button>
            <div className="ml-auto">
              <ThemeToggle theme={theme} setTheme={setTheme} />
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}