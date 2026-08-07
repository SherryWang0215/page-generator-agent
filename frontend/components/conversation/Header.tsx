'use client';

import { Menu } from 'lucide-react';

export default function Header({
  sidebarCollapsed,
  setMobileOpen,
  children,
}: {
  sidebarCollapsed: boolean;
  setMobileOpen: (v: boolean) => void;
  children?: React.ReactNode;
}) {
  return (
    <div className="sticky top-0 z-30 flex items-center gap-2 border-b border-zinc-200/60 bg-white/80 px-4 py-3 backdrop-blur dark:border-zinc-800 dark:bg-zinc-900/70">
      {sidebarCollapsed && (
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className="md:hidden inline-flex items-center justify-center rounded-lg p-2 hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:hover:bg-zinc-800"
          aria-label="打开侧栏"
        >
          <Menu className="h-5 w-5" />
        </button>
      )}
      <div className="ml-auto flex items-center gap-2">{children}</div>
    </div>
  );
}