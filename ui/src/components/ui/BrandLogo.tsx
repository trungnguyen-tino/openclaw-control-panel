import { IctsaigonLogo } from "./IctsaigonLogo";

interface BrandLogoProps {
  size?: number;
  /** Show wordmark + mark together (true) or just the icon mark (false). */
  full?: boolean;
  className?: string;
}

/**
 * Renders the active brand logo per `<html data-theme="…">`.
 *
 * - `default` (or unset) → Tino logo from /themes/tino-logo.png
 * - `ictsaigon` → existing inline ICTSAIGON SVG mark + wordmark
 *
 * Reads the theme once from the DOM at module-load. SPA reloads on theme
 * change (server-side env switch), so a static read is enough.
 */
function currentTheme(): string {
  if (typeof document === "undefined") return "default";
  return document.documentElement.dataset.theme || "default";
}

export function BrandLogo({ size = 32, full = true, className }: BrandLogoProps) {
  const theme = currentTheme();
  if (theme === "ictsaigon") {
    return <IctsaigonLogo size={size} full={full} className={className} />;
  }
  // Tino mobile-light logo PNG (512×69, ratio ≈ 7.42:1). Sized by height so
  // the wordmark scales identically to the ICTSAIGON ratio (≈2.95:1) when
  // `full` is true. For `full=false` we crop the leftmost square via CSS.
  const wordmarkRatio = 7.42;
  const markCropPct = 100 * (1 / wordmarkRatio);
  if (!full) {
    // Square crop of the left side (mark only).
    return (
      <div
        className={className}
        style={{
          width: size,
          height: size,
          overflow: "hidden",
        }}
      >
        <img
          src="/themes/tino-logo.png"
          alt="Tino"
          style={{
            height: size,
            width: `${size * wordmarkRatio}px`,
            objectFit: "cover",
            objectPosition: "left",
            clipPath: `inset(0 ${100 - markCropPct}% 0 0)`,
          }}
        />
      </div>
    );
  }
  return (
    <img
      src="/themes/tino-logo.png"
      alt="Tino"
      style={{ height: size, width: "auto" }}
      className={className}
    />
  );
}
