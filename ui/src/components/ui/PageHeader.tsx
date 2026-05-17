import { ReactNode } from "react";
import { cn } from "@/lib/cn";

interface PageHeaderProps {
  title: string;
  desc?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

export function PageHeader({ title, desc, actions, className }: PageHeaderProps) {
  return (
    <div className={cn("flex items-start justify-between gap-3 flex-wrap", className)}>
      <div className="min-w-0">
        <h1 className="text-2xl font-bold tracking-tight text-ink">{title}</h1>
        {desc && <p className="text-sm text-slate-500 mt-1">{desc}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
    </div>
  );
}
