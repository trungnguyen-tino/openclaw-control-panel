/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        success: "hsl(var(--success))",
        warning: "hsl(var(--warning))",
        // ICTSAIGON brand palette (v2 design)
        brand: {
          50: "#EBF4FF",
          100: "#DBEAFE",
          200: "#BFDBFE",
          300: "#93C5FD",
          400: "#60A5FA",
          500: "#1E88E5",
          600: "#0A6BFF",
          700: "#0052CC",
          800: "#003A99",
          900: "#0A2540",
        },
        ink: "#0E1A2B",
        sand: "#F5B82E",
      },
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        brand: "0 8px 24px rgba(10,107,255,.22)",
        soft: "0 1px 2px rgba(15,23,42,.04), 0 1px 3px rgba(15,23,42,.04)",
        lift: "0 4px 12px rgba(15,42,84,.06), 0 2px 4px rgba(15,42,84,.04)",
      },
      keyframes: {
        "pulse-dot": {
          "0%": { boxShadow: "0 0 0 0 rgba(34,197,94,.55)" },
          "100%": { boxShadow: "0 0 0 8px rgba(34,197,94,0)" },
        },
      },
      animation: {
        "pulse-dot": "pulse-dot 1.6s ease-out infinite",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
