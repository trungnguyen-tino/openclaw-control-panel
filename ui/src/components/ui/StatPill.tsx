import { cn } from "@/lib/cn";

interface StatPillProps {
  label: string;
  value: string;
  dot?: "emerald" | "amber" | "red";
  className?: string;
}

const dotMap = {
  emerald: "bg-emerald-500 ring-emerald-200",
  amber: "bg-amber-500 ring-amber-200",
  red: "bg-red-500 ring-red-200",
};

export function StatPill({ label, value, dot, className }: StatPillProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-full",
        "text-[12px] text-slate-600 whitespace-nowrap",
        className,
      )}
    >
      {dot && (
        <span className={cn("w-1.5 h-1.5 rounded-full ring-2", dotMap[dot])} />
      )}
      <span className="text-slate-400">{label}</span>
      <span className="font-semibold text-ink font-mono">{value}</span>
    </div>
  );
}
