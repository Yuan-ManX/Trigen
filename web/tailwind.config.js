/** @type {import('tailwindcss').Config} */
// Tailwind 配置：深色主题 + Trigen 设计令牌
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // 背景层
        bg: {
          base: '#0a0a0f',
          panel: '#12121a',
          elevated: '#1a1a24',
          hover: '#22222e',
        },
        // 边框
        border: {
          DEFAULT: '#2a2a35',
          subtle: '#1f1f29',
        },
        // 强调色
        accent: {
          cyan: '#00F0FF',
          gold: '#FFB800',
        },
        // 文本
        fg: {
          primary: '#ffffff',
          secondary: '#9ca3af',
          muted: '#6b7280',
        },
      },
      fontFamily: {
        sans: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        sm: '6px',
        md: '8px',
      },
      boxShadow: {
        glow: '0 0 20px rgba(0, 240, 255, 0.25)',
        'glow-gold': '0 0 20px rgba(255, 184, 0, 0.25)',
      },
      animation: {
        'pulse-slow': 'pulse 2.5s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'spin-slow': 'spin 3s linear infinite',
      },
    },
  },
  plugins: [],
}
