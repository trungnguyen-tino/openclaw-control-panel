import { IctsaigonLogo } from "./IctsaigonLogo";
import { cn } from "@/lib/cn";

interface BrandLogoProps {
  size?: number;
  /** Show wordmark + mark together (true) or just the icon mark (false). */
  full?: boolean;
  className?: string;
}

/**
 * Renders the active brand logo per `<html data-theme="…">`.
 *
 * - `default` (or unset) → inline OpenClaw SVG mark + wordmark, single-color
 *   via `currentColor` so it adapts to parent text color (dark on light bg,
 *   white on dark hero).
 * - `ictsaigon` → existing inline ICTSAIGON SVG mark + wordmark (hardcoded
 *   blue + yellow fills).
 */
function currentTheme(): string {
  if (typeof document === "undefined") return "default";
  return document.documentElement.dataset.theme || "default";
}

export function BrandLogo({ size = 32, full = true, className }: BrandLogoProps) {
  if (currentTheme() === "ictsaigon") {
    return <IctsaigonLogo size={size} full={full} className={className} />;
  }
  return <OpenclawLogo size={size} full={full} className={className} />;
}

/**
 * OpenClaw default mark — stylized open-claw "O" (circle with claw notch on
 * the right) + Opencrawl wordmark. Single colour via `currentColor`.
 */
function OpenclawLogo({ size, full, className }: Required<Pick<BrandLogoProps, "size">> & BrandLogoProps) {
  if (!full) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 50 50"
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="OpenClaw"
      >
        <OpenclawMark />
      </svg>
    );
  }
  // Use inline-flex so the SVG mark and HTML wordmark share the same baseline
  // and the wordmark picks up the page font (Plus Jakarta Sans).
  return (
    <span
      className={cn("inline-flex items-center gap-2", className)}
      style={{ height: size }}
      aria-label="OpenClaw"
    >
      <svg width={size} height={size} viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg">
        <OpenclawMark />
      </svg>
      <span
        className="font-extrabold tracking-tight leading-none"
        style={{ fontSize: size * 0.62, color: "currentColor" }}
      >
        Opencrawl
      </span>
    </span>
  );
}

function OpenclawMark() {
  // The mark is a thick C-shape opening to the right (claw silhouette), with
  // a small accent dot. All paths use `currentColor` so callers control hue.
  return (
    <g fill="currentColor">
      {/* Outer claw ring: ~3/4 circle, gap on the right between 50° and -50° */}
      <path d="M25 4 a21 21 0 1 1 14.85 35.85 l-5.66-5.66 a13 13 0 1 0 -9.19 -3.81 z" />
      {/* Accent dot inside the mouth, suggesting a target / grabbed object */}
      <circle cx="36" cy="25" r="3.5" opacity="0.7" />
    </g>
  );
}
