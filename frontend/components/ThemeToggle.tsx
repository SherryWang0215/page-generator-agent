'use client';

import { Moon, Sun } from 'lucide-react';
import { useEffect, useState } from 'react';

export type Theme = 'light' | 'dark';

export default function ThemeToggle({
  theme,
  setTheme,
}: {
  theme: Theme;
  setTheme: (t: Theme) => void;
}) {
  // Avoid SSR/CSR mismatch: theme is only known after mount (localStorage / matchMedia).
  // Render a stable placeholder until then.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <button
      type="button"
      className="inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-white px-2.5 py-1.5 text-sm hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:bg-zinc-800"
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      aria-label="Toggle theme"
      title="Toggle theme"
      suppressHydrationWarning
    >
      {mounted && theme === 'dark' ? (
        <Sun className="h-4 w-4" />
      ) : (
        <Moon className="h-4 w-4" />
      )}
      <span className="hidden sm:inline" suppressHydrationWarning>
        {mounted ? (theme === 'dark' ? '亮色' : '暗色') : '暗色'}
      </span>
    </button>
  );
}
