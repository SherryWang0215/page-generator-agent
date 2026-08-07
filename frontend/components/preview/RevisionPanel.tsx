'use client';

import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

export default function RevisionPanel({
  onRevise,
  busy,
}: {
  onRevise: (instruction: string) => void;
  busy: boolean;
}) {
  const [instruction, setInstruction] = useState('');

  const disabled = busy || instruction.trim().length < 8;

  return (
    <div className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="mb-2 text-sm font-semibold">修订当前页面</div>
      <Textarea
        value={instruction}
        onChange={(e) => setInstruction(e.target.value)}
        placeholder="输入修改指令，至少 8 个字，如：把主标题改得更商务一点"
        rows={3}
      />
      <div className="mt-3 flex justify-end">
        <Button onClick={() => onRevise(instruction)} disabled={disabled}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {busy ? '修改中...' : '修改当前页面'}
        </Button>
      </div>
    </div>
  );
}