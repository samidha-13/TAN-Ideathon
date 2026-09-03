/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        aviation: {
          dark: '#0f172a',
          panel: '#1e293b',
          border: '#334155',
          text: '#94a3b8',
          textHover: '#cbd5e1',
          highlight: '#f8fafc',
          green: '#22c55e',          // Healthy/Active
          greenBright: '#4ade80',    // TAN + EKF route
          red: '#ef4444',            // Denied/Fault
          magenta: '#d946ef',        // INS prediction
          pathBg: 'rgba(0,0,0,0.4)',
        }
      },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', '"Liberation Mono"', '"Courier New"', 'monospace'],
        display: ['Inter', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
