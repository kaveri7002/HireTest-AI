/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f1efff',
          500: '#6857e8',
          600: '#5646d0',
        },
      },
    },
  },
  plugins: [],
}
