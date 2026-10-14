/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        galvanised: '#D5DADE',
        'cold-blue': '#1C57F2',
        'hot-red': '#D93A2B',
        'hivis-yellow': '#FFD60A',
        teflon: '#F6F8F9',
        'slate-ink': '#14222E',
      },
      fontFamily: {
        display: ['Bricolage Grotesque', 'sans-serif'],
        body: ['Instrument Sans', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
