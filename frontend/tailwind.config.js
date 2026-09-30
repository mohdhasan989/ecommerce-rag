import colors from 'tailwindcss/colors';
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: { brand: colors.indigo },
      fontFamily: { sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'] },
      boxShadow: { card: '0 1px 2px rgba(15,23,42,.05), 0 1px 3px rgba(15,23,42,.06)', lift: '0 10px 30px rgba(15,23,42,.10)' },
    },
  },
  plugins: [],
};
