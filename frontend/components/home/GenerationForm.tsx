'use client';

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';

import { generatePage, waitForGenerationResult } from '@/lib/api';
import type { PageType, ThemeType } from '@/lib/pageDsl';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

export default function GenerationForm() {
  const router = useRouter();
  const [prompt, setPrompt] = useState('生成一个智能手表产品推广页，突出健康监测和续航能力');
  const [pageType, setPageType] = useState<PageType>('landing_page');
  const [brandStyle, setBrandStyle] = useState<ThemeType>('tech_clean');
  const [submitting, setSubmitting] = useState(false);
  const [taskStatus, setTaskStatus] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setTaskStatus(null);
    try {
      const task = await generatePage({
        prompt,
        page_type: pageType,
        brand_style: brandStyle,
      });
      setTaskStatus(`任务已提交：${task.request_id}`);

      const result = await waitForGenerationResult(task.request_id, (status) => {
        setTaskStatus(`任务状态：${status}`);
      });
      if (!result.page_id || !result.preview_url) {
        throw new Error('生成完成但缺少页面信息');
      }
      router.push(result.preview_url);
    } catch (submitError) {
      const msg = submitError instanceof Error ? submitError.message : '生成失败';
      toast.error(msg);
      setTaskStatus(null);
    } finally {
      setSubmitting(false);
    }
  }

  const disabled = submitting || prompt.trim().length < 8;

  return (
    <form onSubmit={handleSubmit} className="grid gap-6">
      <div className="grid gap-2">
        <Label htmlFor="prompt">页面需求</Label>
        <Textarea
          id="prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={5}
          placeholder="描述你想生成的页面，至少 8 个字"
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor="pageType">页面类型</Label>
          <Select value={pageType} onValueChange={(v) => setPageType(v as PageType)}>
            <SelectTrigger id="pageType">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="landing_page">landing_page</SelectItem>
              <SelectItem value="product_page">product_page</SelectItem>
              <SelectItem value="campaign_page">campaign_page</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="grid gap-2">
          <Label htmlFor="brandStyle">品牌风格</Label>
          <Select value={brandStyle} onValueChange={(v) => setBrandStyle(v as ThemeType)}>
            <SelectTrigger id="brandStyle">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="tech_clean">tech_clean</SelectItem>
              <SelectItem value="business_formal">business_formal</SelectItem>
              <SelectItem value="growth_marketing">growth_marketing</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={disabled} size="lg">
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {submitting ? '生成中...' : '生成页面'}
        </Button>
        {taskStatus ? (
          <span className="text-sm text-muted-foreground">{taskStatus}</span>
        ) : null}
      </div>

      <p className="text-xs text-muted-foreground">
        当前版本先稳定支持 4 个组件：hero_banner、feature_cards、cta_button、testimonials。
      </p>
    </form>
  );
}
