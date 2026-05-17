import { ReactNode } from "react";
import { cn } from "@/lib/cn";

interface FieldProps {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
  className?: string;
  htmlFor?: string;
}

export function Field({ label, hint, children, className, htmlFor }: FieldProps) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={htmlFor} className="text-xs font-semibold text-slate-600">
        {label}
      </label>
      {children}
      {hint && <div className="text-[11.5px] text-slate-400">{hint}</div>}
    </div>
  );
}
