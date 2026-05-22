export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      boxShadow: {
        glow: '0 0 0 1px rgba(96, 165, 250, 0.12), 0 24px 60px -20px rgba(59, 130, 246, 0.25)',
        'glow-emerald': '0 0 0 1px rgba(16, 185, 129, 0.18), 0 24px 60px -24px rgba(16, 185, 129, 0.35)',
        'glow-rose': '0 0 0 1px rgba(244, 63, 94, 0.18), 0 24px 60px -24px rgba(244, 63, 94, 0.35)',
        card: '0 1px 0 0 rgba(255,255,255,0.04) inset, 0 18px 40px -24px rgba(0,0,0,0.8)',
      },
      keyframes: {
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.6s infinite',
        'fade-up': 'fade-up 0.4s ease-out both',
      },
    },
  },
  plugins: [],
}
