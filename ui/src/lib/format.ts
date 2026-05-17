export function bytes(n: number | undefined | null): string {
  if (!n || n < 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}

export function pct(n: number | undefined | null): string {
  if (n == null || isNaN(n)) return "—";
  return `${n.toFixed(1)}%`;
}

export function uptime(seconds: number | undefined | null): string {
  if (!seconds || seconds < 0) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return [d && `${d}d`, h && `${h}h`, m && `${m}m`].filter(Boolean).join(" ") || "<1m";
}

export function classNames(...arr: (string | false | null | undefined)[]): string {
  return arr.filter(Boolean).join(" ");
}
