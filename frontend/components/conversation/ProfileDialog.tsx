'use client';

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { RefreshCw } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { extractProfile, getProfile, type ProfileData } from '@/lib/api';

export default function ProfileDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(false);
  const [extracting, setExtracting] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const p = await getProfile();
        if (!cancelled) setProfile(p);
      } catch {
        if (!cancelled) setProfile(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  async function handleExtract() {
    setExtracting(true);
    try {
      const p = await extractProfile();
      setProfile(p);
      toast.success('画像已更新');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '画像提取失败');
    } finally {
      setExtracting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>用户画像</DialogTitle>
        </DialogHeader>

        {loading ? (
          <p className="text-sm text-muted-foreground">加载中...</p>
        ) : profile ? (
          <div className="space-y-3">
            {profile.extracted_at ? (
              <p className="text-xs text-muted-foreground">
                提取时间: {new Date(profile.extracted_at).toLocaleString('zh-CN')}
              </p>
            ) : null}
            <pre className="max-h-80 overflow-auto rounded-lg bg-muted p-3 text-xs">
              {JSON.stringify(profile.preferences, null, 2)}
            </pre>
            <Button onClick={handleExtract} disabled={extracting} variant="outline" size="sm">
              <RefreshCw className={`h-4 w-4 ${extracting ? 'animate-spin' : ''}`} />
              {extracting ? '提取中...' : '重新提取'}
            </Button>
          </div>
        ) : (
          <div className="space-y-3 text-center">
            <p className="text-sm text-muted-foreground">
              暂无画像数据，消息积累到一定数量后可自动提取。
            </p>
            <Button onClick={handleExtract} disabled={extracting} size="sm">
              <RefreshCw className={`h-4 w-4 ${extracting ? 'animate-spin' : ''}`} />
              {extracting ? '提取中...' : '手动提取'}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}