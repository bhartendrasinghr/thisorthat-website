# This or That with Bhartendra — Website

## What this repo is
Static website for the "This or That with Bhartendra" Indian personal-finance podcast.
- Stack: Static HTML + Decap CMS + deployed on Vercel
- Repo: bhartendrasinghr/thisorthat-website (PUBLIC)
- Live: https://thisorthat-website.vercel.app

## Brand (per Brand Guidelines v1.0 · June 2026)

**Tagline:** beyond the noise
**Big idea:** Every episode is a fork. One money decision, two sides, we pick one.

**Colors** (use brand names; legacy `navy`/`mustard`/`alert` are aliases mapped to these):
- **Marigold** #FFC21F — the stage; brand moments only (headers, hero cards). Class: `bg-marigold` or legacy `bg-mustard`
- **This-blue** #0249B1 — "This" side; the ONE primary action per view (CTAs, links). Class: `bg-thisblue` or legacy `bg-navy`
- **That-red** #FF302D — "That" side; rare counter accent. Class: `bg-thatred` or legacy `bg-alert`
- **Warm paper** #FCFBF8 — background. Class: `bg-warmpaper` or legacy `bg-cream`
- **Paper-2** #F6F4EE — secondary surface. Class: `bg-warmpaper-2` or legacy `bg-paper`
- **Ink** #1A1813 — primary text. Class: `text-ink` or legacy `text-navy-ink`
- **Gain/Loss** #1F8A5B / #E0211E — numbers only, always with +/− sign

**Accessible text tokens (use these for TEXT, always):**
- `text-goldink` #8F6600 — gold for eyebrows/labels. The brand gold #D99B00 measures **2.35:1** on warm paper and fails WCAG AA for small text; #8F6600 measures **4.99:1**. Never use `text-mustard-deep` or `text-marigold-600`.
- `text-gainink` #1B7A50 — green for small text (5.14:1). Plain `gain` #1F8A5B is 4.19:1 and fails.
- `text-loss` #E0211E passes at 4.61:1. `that-red` #FF302D is 3.55:1, so it is for graphics and large type only, never small text.
- #D99B00 and #FFC21F remain correct for **borders, backgrounds and chart fills**. The restriction is text only.

**Typography:**
- Display: **Bricolage Grotesque** 700–800 (was Fraunces) — `font-serif` or `font-display`
- UI / body: **Hanken Grotesk** 400–700 (was Inter) — `font-sans`
- Numbers: **IBM Plex Mono** — `font-mono`
- Script accent: **Caveat** — `font-script` (use for "or" / margin notes only)

**Rules:**
- One blue primary per view; marigold is for brand moments only, never for text background
- Never put white text on marigold (fails AA contrast)
- Numbers always in mono, always with thousands separators (Indian system: 1,20,000)
- Headlines in sentence case (not Title Case)
- 8px grid for spacing (8/16/24/32/48/64)
- Radii: sm 6px · md 12px · lg 18px · xl 36px

**Voice (warm AND sharp — locked in July 2026, applies to ALL copy):**
- On the reader's side, never across the table. "A friend who has their life sorted, helping you get there" — not "a smart person correcting you."
- No shame: money confusion is never the reader's fault. Blame the system, never the reader.
- Every hard number leaves a door open: "This isn't a no, it's a not-like-this." Verdicts hold the reader, then hand them the next step.
- Still sharp and honest — the truth doesn't get softer, the hand delivering it does. Never hedgy advisor-mush.
- No em-dashes anywhere (the "AI give-away") except brand.html. Use commas, colons, or hyphens.
- No emoji spam, no cutesy tone. Disclaimers stay precise and serious.
- Gold-standard reference: calc-goal.html verdict strings.
- Naming: it's "Honest SIP" (renamed from "Brutal SIP" in the warm pass).
- Pose a fork → guide → pick one. We don't promise returns, hedge endlessly, or shout in caps.

**Logo:**
- `logo.png` — square mark for cover art / avatars / app icon
- Always circular crop in nav (40px) and footer (40px)
- Clear space: 1× the cap-height of "T" on every side
- Never on blue or red — strokes disappear

## What Claude should help with here
1. Adding/updating episode pages
2. Editing copy (guest bios, episode descriptions)
3. SEO — title tags, meta descriptions, structured data
4. Design updates (HTML/CSS)
5. CMS schema changes

## Deploy
Push to main → Vercel auto-deploys.

## Don't do
- Never expose API keys or private guest contact details
- Don't make the repo private (it is intentionally public)
