import { forwardRef, InputHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "w-full h-9 px-3 border border-slate-200 rounded-lg bg-white text-[13px] outline-none",
        "focus:border-brand-400 focus:ring-4 focus:ring-brand-100",
        "placeholder:text-slate-400 disabled:opacity-50 disabled:cursor-not-allowed",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
