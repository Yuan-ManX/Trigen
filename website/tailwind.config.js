/** @type {import('tailwindcss').Config} */

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    container: {
      center: true,
    },
    extend: {
      colors: {
        void: "#0A0A0A",
        ink: "#050505",
        snow: "#FFFFFF",
        ash: "#9CA3AF",
        cyber: "#00F0FF",
        amber: "#FFB800",
        ember: "#FF4D2E",
      },
      fontFamily: {
        display: ['"Space Grotesk"', '"Noto Sans SC"', "sans-serif"],
        mono: ['"JetBrains Mono"', '"Noto Sans SC"', "monospace"],
        sans: ['"Noto Sans SC"', "system-ui", "sans-serif"],
      },
      letterSpacing: {
        ultra: "0.4em",
        mega: "0.2em",
        tightish: "-0.015em",
        snug: "0.005em",
      },
      lineHeight: {
        copy: "1.75",
        airy: "1.85",
        tightish: "1.15",
      },
      fontSize: {
        "2xs": ["11px", "1.5"],
      },
      animation: {
        "spin-slow": "spin 24s linear infinite",
        "float": "float 6s ease-in-out infinite",
        "pulse-glow": "pulseGlow 3s ease-in-out infinite",
        "scan": "scan 4s linear infinite",
        "drift": "drift 18s linear infinite",
        "shimmer": "shimmer 3s linear infinite",
      },
      keyframes: {
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-12px)" },
        },
        pulseGlow: {
          "0%, 100%": { opacity: "0.4", filter: "blur(40px)" },
          "50%": { opacity: "0.8", filter: "blur(60px)" },
        },
        scan: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100vh)" },
        },
        drift: {
          "0%": { transform: "translate3d(0,0,0)" },
          "50%": { transform: "translate3d(20px,-20px,0)" },
          "100%": { transform: "translate3d(0,0,0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
    },
  },
  plugins: [],
};
