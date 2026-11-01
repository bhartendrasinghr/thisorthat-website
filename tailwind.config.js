/* One config for the whole site.
 *
 * This replaces twelve of them. Every page carried its own copy of
 * `tailwind.config = {...}` inline for the Play CDN to read, and they had
 * drifted into twelve variants: mostly subsets of each other, but with one
 * real collision. index.html called #FCFBF8 "paper" while every other page
 * called #F6F4EE "paper", so the same class meant two colours depending on
 * which page you were on. The homepage's uses were renamed to `cream`, which
 * is the site-wide name for that exact hex, and the vocabulary is now one.
 *
 * Values are the union of all twelve, so no page loses a shade it was using.
 * Brand Guidelines v1.0 is the source of truth for the named colours.
 */
module.exports = {
  // Every file a class name can appear in. episodes.js carries seven of them
  // in its rendering code, and the JSON under content/ is read into markup,
  // so both are scanned: a class the scanner never sees is a class that does
  // not get generated, and that failure is silent.
  content: [
    './*.html',
    './*.js',
    './content/**/*.json',
  ],
  theme: {
    extend: {
      colors: {
        // ── Brand Guidelines v1.0 ──────────────────────────────────────
        marigold:  { DEFAULT: '#FFC21F', 50: '#FFF7DE', 200: '#FFE9AE', 400: '#FFD15C', 600: '#D99B00' },
        thisblue:  { DEFAULT: '#0249B1', 700: '#013580' },
        thatred:   { DEFAULT: '#FF302D', 700: '#B4231F' },
        ink:       { DEFAULT: '#1A1813', 2: '#2C2A23', 3: '#57534A' },
        warmpaper: { DEFAULT: '#FCFBF8', 2: '#F6F4EE', 3: '#E1DDD1', 4: '#8A8275' },

        // Accessible text tokens. The brand gold #D99B00 is 2.35:1 on warm
        // paper and fails AA for small text; these are the ones for type.
        goldink: '#8F6600',
        gainink: '#1B7A50',
        gain: '#1F8A5B',
        loss: '#E0211E',
        warn: '#D99B00',

        // ── Legacy aliases, so the old class names keep working ─────────
        navy:    { DEFAULT: '#0249B1', deep: '#013580', ink: '#1A1813' },
        mustard: { DEFAULT: '#FFC21F', soft: '#FFD15C', deep: '#D99B00' },
        alert:   '#FF302D',
        cream:   '#FCFBF8',
        paper:   '#F6F4EE',

        // ── The homepage's own set, kept because only it uses them ──────
        surf: '#F6F4EE',
        body: '#57534A',
        meta: '#7A7368',
        line: '#E1DDD1',
        edge: '#8E8574',
        dark: '#16150F',
        gold: '#8F6600',
      },
      fontSize: {
        xs: ['13px', '1.45'],
        sm: ['15px', '1.5'],
      },
      fontFamily: {
        sans:    ['Hanken Grotesk', 'system-ui', 'sans-serif'],
        serif:   ['Bricolage Grotesque', 'Georgia', 'serif'],
        display: ['Bricolage Grotesque', 'Georgia', 'serif'],
        mono:    ['IBM Plex Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
        script:  ['Caveat', 'cursive'],
      },
    },
  },
};
