/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f0f7ff',
          100: '#e0effe',
          500: '#0066cc',
          600: '#0052a3',
          700: '#003d7a',
          noc: '#2870c2',
          nocDark: '#1b4d85',
        },
        darkBg: {
          base: '#0d1117',
          card: '#161b22',
          sidebar: '#11151c',
          border: '#30363d',
          hover: '#1c2128',
        }
      }
    },
  },
  plugins: [],
}
