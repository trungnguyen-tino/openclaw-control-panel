import { forwardRef, ButtonHTMLAttributes } from "react";
import { Slot } from "@radix-ui/react-slot";
import { cn } from "@/lib/cn";

// v2 design variants. `default` is alias for `primary` to preserve old callers.
type Variant =
  | "primary"
  | "default"
  | "secondary"
  | "ghost"
  | "danger"
  | "destructive"
  | "outline"
  | "success";
type Size = "sm" | "md" | "lg" | "icon";

const variants: Record<Variant, string> = {
  primary: "bg-brand-600 text-white shadow-brand hover:bg-brand-700",
  default: "bg-brand-600 text-white shadow-brand hover:bg-brand-700",
  secondary: "bg-slate-100 text-ink border border-slate-200 hover:bg-slate-200/70",
  ghost: "text-slate-600 hover:bg-slate-100",
  danger: "bg-white text-red-600 border border-slate-200 hover:bg-red-50 hover:border-red-200",
  destructive: "bg-red-600 text-white hover:bg-red-700 shadow-sm",
  outline: "border border-slate-200 bg-white text-ink hover:bg-slate-50",
  success: "bg-emerald-600 text-white hover:bg-emerald-700",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-xs rounded-lg",
  md: "h-9 px-4 text-[13px] rounded-lg",
  lg: "h-11 px-5 text-sm rounded-lg",
  icon: "h-9 w-9 rounded-lg",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", className, asChild = false, ...props }, ref) => {
    const Comp: React.ElementType = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center gap-2 font-semibold transition-colors whitespace-nowrap",
          "focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-100",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          variants[variant],
          sizes[size],
          className,
        )}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";
