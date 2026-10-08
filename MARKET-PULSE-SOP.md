# Market Pulse, monthly update

How to publish a new edition of **thisorthatshow.in/market-pulse**.

Budget about **45 minutes**. No code, no terminal. Everything is done in the CMS at
`thisorthatshow.in/admin` under **Market Pulse**.

---

## First, what you do NOT have to do

Five figures update themselves every night, straight from the exchange. They carry a
green dot and a "live" date on the page. **Never type over these.** If you do, the next
nightly run will overwrite you, and for a few hours the page will show a number nobody
can trace.

| Figure | Where it comes from |
|---|---|
| Nifty 50, year to date | NSE daily index archive |
| Nifty 50 P/E, P/B, dividend yield | NSE daily index archive |
| Indices up on the day | NSE daily index archive, 149 indices |
| Stocks up year to date | NSE bhavcopy, adjusted for splits and bonuses |
| Rupee per dollar | open.er-api.com, against the year-open rate |

In the CMS these have **Auto** ticked. Leave that tick alone.

---

## The monthly job

Do this in the first few working days of the month, once the previous month has closed.

### 1. Set the edition

- **Edition** → the month just finished, e.g. `October 2026`
- **Updated on** → today

### 2. The scoreboard, four tiles by hand

| Tile | Source | How |
|---|---|---|
| S&P 500 in ₹ | Any market site | Take the S&P 500 year-to-date percentage, then add the rupee's fall for the same period. The rupee figure is on the page already, in the live tile. |
| Gold in ₹ | Any market site | Same method: global gold YTD, plus the rupee move. |
| 10-yr G-sec | fbil.org.in | The 10-year benchmark yield. Note the change in basis points since 1 January. |
| Crude (energy) | Any market site | Brent, year to date, in dollars. |

Keep the wording short. The small print under each number is where the context goes.

### 3. The tracker cards, seven by hand

Under **The tracker**, these need refreshing:

- **Crude oil**, **Dollar index**, **US 10-year yield**: any market site
- **India 10-year G-sec**: fbil.org.in
- **RBI repo rate**: rbi.org.in, only changes at a policy meeting
- **CPI inflation**: mospi.gov.in, released around the 12th each month
- **Real interest rate**: repo rate minus CPI. Do the subtraction yourself.

For each, set the **Signal**: headwind, tailwind, mixed or watch. Be consistent month to
month, because a signal that flips without the number moving looks like an error.

### 4. The two charts we cannot compute

- **Asset classes**: from the First Global Monthly Action Report
- **India against the world**: same report. Update India's rank in the heading.

Enter each bar as a name and a number. The chart redraws itself. Tick **Highlight this
one** on India only.

### 5. The behaviour gap

From **DSP Netra**, published monthly. This one never automates: investor returns need
flow data only the fund houses hold.

Usually worth changing only once a quarter. If Netra has not moved, leave it and update
the source line.

### 6. The writing

- **Headline** and **Opening paragraph**: what actually happened, in two sentences
- **The chain**: six links. Numbers mostly repeat from the scoreboard; the "why" line
  is the work.
- **What we are watching**: three things. Not predictions. Things that would change the
  picture if they moved.
- **If you track only ten**: rarely changes. That is the point of it.

### 7. Publish

Save in the CMS. The site rebuilds itself in a minute or two. Then open
`thisorthatshow.in/market-pulse` and check:

- [ ] The edition month in the top right is the new one
- [ ] Every hand-written tile says "as of" with today's date
- [ ] Every live tile still has its green dot
- [ ] No tile is blank
- [ ] The two charts have bars, and India is the red one
- [ ] It reads correctly on a phone

---

## Once a year, in January

**Set `fx_year_open`** to the USD/INR rate on the first trading day of the year, from the
RBI reference rate. Without it the rupee tile shows the level instead of the move.

The current value, 90.63, was derived from the September 2026 edition's own figure rather
than read from the RBI. **Check it against the RBI reference rate for 1 January 2026 and
correct it.**

---

## If a live figure looks wrong

1. Open `thisorthatshow.in/content/market-pulse.json` and look at `auto_refreshed`. If
   that date is old, the nightly job has been failing and every live number is stale.
2. A single odd number is usually a real market move. Check it against the NSE site
   before assuming a bug.
3. If the nightly job is stuck, a redeploy re-runs it. Ask whoever maintains the site.

The refresher is deliberately cautious: if a source is unreachable it leaves the old
number in place rather than writing a zero. So a wrong-looking number is far more likely
to be stale than invented, and the date stamp will tell you which.

---

## What is deliberately not automated

**The behaviour gap**, the **global asset-class ladder** and the **42-market ranking** are
licensed work from DSP and First Global. There is no open source for them.

**The writing** is not automated because it should not be. The numbers say what happened.
The paragraphs say what it meant, and that is the part worth a person's time.
