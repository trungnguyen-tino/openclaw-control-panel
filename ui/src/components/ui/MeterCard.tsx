import { ReactNode } from "react";
import { cn } from "@/lib/cn";

interface MeterCardProps {
  title: string;
  value: string | ReactNode;
  pct: number;
  right?: string;
  accent?: "brand" | "cyan" | "amber" | "emerald" | "red";
}

const accentBar = {
  brand: "bg-brand-600",
  cyan: "bg-cyan-500",
  amber: "bg-amber-500",
  emerald: "bg-emerald-500",
  red: "bg-red-500",
};

export function MeterCard({ title, value, pct, right, accent = "brand" }: MeterCardProps) {
  const clamped = Math.max(0, Math.min(100, pct));
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-soft p-5">
      <div className="flex items-baseline justify-between gap-2">
        <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{title}</div>
        {right && <div className="text-[11px] text-slate-400 font-mono">{right}</div>}
      </div>
      <div className="mt-2 font-bold text-lg text-ink font-mono">{value}</div>
      <div className="mt-3 h-2 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-500", accentBar[accent])}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}
