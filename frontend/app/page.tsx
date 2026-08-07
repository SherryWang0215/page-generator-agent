'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import GenerationForm from '@/components/home/GenerationForm';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export default function HomePage() {
  const router = useRouter();

  return (
    <div className="min-h-screen w-full bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-zinc-200/60 bg-white/80 px-4 py-2.5 backdrop-blur dark:border-zinc-800 dark:bg-zinc-900/70">
        <Link
          href="/conversations"
          className="text-sm font-medium text-blue-600 hover:underline dark:text-blue-400"
        >
          进入对话模式 →
        </Link>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-8 sm:px-8">
        <div className="mx-auto max-w-3xl">
          <h1 className="mb-2 text-3xl font-bold tracking-tight">Page Generator Agent</h1>
          <p className="mb-8 text-muted-foreground">
            填写需求，AI 自动生成落地页；可在对话中持续修订。
          </p>

          <Card>
            <CardHeader>
              <CardTitle>生成新页面</CardTitle>
            </CardHeader>
            <CardContent>
              <GenerationForm />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
