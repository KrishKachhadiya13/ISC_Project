import type { Config } from 'tailwindcss';

// Colors are CSS variables (see src/styles/index.css) so the dark and light themes
// share one set of class names.
const token = (name: string): string => `rgb(var(--${name}) / <alpha-value>)`;

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: token('bg'),
        panel: token('panel'),
        raised: token('raised'),
        line: token('line'),
        fg: token('fg'),
        muted: token('muted'),
        accent: token('accent'),
        violet: token('violet'),
        ok: token('ok'),
        bad: token('bad'),
        warn: token('warn'),
        'on-accent': token('on-accent'),
      },
      borderRadius: {
        md: '6px',
        lg: '10px',
        xl: '14px',
        '2xl': '20px',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['"Plus Jakarta Sans"', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
};

export default config;
