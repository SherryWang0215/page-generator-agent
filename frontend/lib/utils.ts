import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function timeAgo(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  const now = new Date();
  const sec = Math.max(1, Math.floor((now.getTime() - d.getTime()) / 1000));
  const rtf = new Intl.RelativeTimeFormat('zh-CN', { numeric: 'auto' });
  const ranges: Array<[number, Intl.RelativeTimeFormatUnit]> = [
    [60, 'second'],
    [3600, 'minute'],
    [86400, 'hour'],
    [604800, 'day'],
    [2629800, 'week'],
    [31557600, 'month'],
  ];
  let unit: Intl.RelativeTimeFormatUnit = 'year';
  let value = -Math.floor(sec / 31557600);
  for (const [limit, u] of ranges) {
    if (sec < limit) {
      unit = u;
      const divisors: Record<string, number> = {
        second: 1,
        minute: 60,
        hour: 3600,
        day: 86400,
        week: 604800,
        month: 2629800,
      };
      value = -Math.floor(sec / divisors[u]);
      break;
    }
  }
  return rtf.format(value, unit);
}
