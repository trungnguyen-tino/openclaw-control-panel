import { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

// v2 design tones. `default`/`muted` kept for backward compat with existing
// callers using shadcn variant names.
type Tone =
  | "slate"
  | "default"
  | "success"
  | "warn"
  | "danger"
  | "destructive"
  | "info"
  | "brand"
  | "muted";

const tones: Record<Tone, string> = {
  slate: "bg-slate-100 text-slate-600",
  default: "bg-slate-100 text-slate-600",
  muted: "bg-slate-100 text-slate-600",
  success: "bg-emerald-50 text-emerald-700",
  warn: "bg-amber-50 text-amber-700",
  danger: "bg-red-50 text-red-600",
  destructive: "bg-red-50 text-red-600",
  info: "bg-brand-50 text-brand-700",
  brand: "bg-brand-50 text-brand-700",
};

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
  variant?: Tone; // back-compat alias
  dot?: boolean;
}

export function Badge({ className, tone, variant, dot = false, children, ...props }: BadgeProps) {
  const t = tone ?? variant ?? "slate";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11.5px] font-semibold whitespace-nowrap",
        tones[t],
        className,
      )}
      {...props}
    >
      {dot && <span className="w-1.5 h-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}
