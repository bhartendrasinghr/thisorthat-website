# Market Pulse, monthly update

How to publish a new edition of **thisorthatshow.in/market-pulse**.

Budget about **20 minutes**. It used to be 45. No code, no terminal. Everything is
done in the CMS at `thisorthatshow.in/admin` under **Market Pulse**.

---

## You will be told when this is due

You do not have to remember any of this. Every morning a job works out which figures
and sentences have gone stale and, when any have, opens a single GitHub issue assigned
to you, titled **"Market Pulse: N things only you can do"**. GitHub emails it to you.

- It stays open and gets rewritten each morning, so the ages in it are always today's.
- It only emails you again when something **new** goes stale, not as things get older.
- It closes itself when the list empties.
- Close it unfixed and it stays shut for a week. If you are not going to do a thing
  this week, closing the issue is a legitimate answer.

The list lives at `content/market-pulse-review.json` too, if you would rather look than
be told.

---

## First, what you do NOT have to do

**Thirteen of the seventeen figures update themselves every night**, from the exchange
and from official feeds. They carry a green dot and a "live" date on the page.
**Never type over these.** If you do, the next nightly run will overwrite you, and for
a few hours the page will show a number nobody can trace.

| Figure | Where it comes from |
|---|---|
| Nifty 50, year to date | NSE daily index archive |
| Nifty 50 P/E | NSE daily index archive |
| Indices up on the day | NSE daily index archive |
| Stocks up year to date | NSE bhavcopy, adjusted for splits and bonuses |
| Rupee per dollar, and the USD/INR card | open.er-api.com, against the year-open rate |
| S&P 500 in ₹ | FRED, converted at the live rupee |
| Gold in ₹ | api.gold-api.com, converted at the live rupee |
| Crude, both the tile and the card | FRED, Brent spot, from the EIA |
| US 10-year yield | US Treasury daily yield curve |
| Dollar index | FRED, the Fed's broad index |
| Real interest rate | repo minus CPI, computed from the two cards below |

In the CMS these have **Auto** ticked. Leave that tick alone.

Two notes on what the robot picked, because they are not the figures Google shows you:

- **Crude** is Brent **spot** from the EIA, not the front-month future. It is the only
  Brent series a build box can reach. The small print under the number says so.
- **Dollar index** is the Fed's **broad** trade-weighted index, not DXY. Arguably the
  better one for India, since DXY is six rich-world currencies and ours is not in it.
  Again, the small print says which.

The **real interest rate** is computed, so you never touch it. Update CPI and it
follows on the next build.

---

## The monthly job

Do this in the first few working days of the month, once the previous month has closed.

### 1. Set the edition

- **Edition** → the month just finished, e.g. `October 2026`
- **Updated on** → today

### 2. Four figures by hand

That is all that is left.

| Field | Source | How |
|---|---|---|
| **10-yr G-sec** tile | fbil.org.in | The 10-year benchmark yield, and the change in basis points since 1 January |
| **India 10-year G-sec** card | same | Same number. Yes, it appears twice. Keep them equal. |
| **RBI repo rate** card | rbi.org.in | Only moves at an MPC meeting. The **stance** wording matters as much as the rate: it is the sentence that tells a reader which way the next move leans. |
| **CPI inflation** card | mospi.gov.in | Published around the 12th. There is no official core series, so if you show a core figure, name whose estimate it is. |

Set each one's **as of** date to the date the figure refers to, not today.

For each card, set the **Signal**: headwind, tailwind, mixed or watch. Be consistent
month to month, because a signal that flips without the number moving looks like an
error.

Why the G-sec is still manual: FBIL is the official source but sits behind a login and
bars commercial use of its website data. worldgovernmentbonds.com renders its table in
JavaScript, so a build box sees no numbers at all. Both were tried.

### 3. The two charts we cannot compute

- **Asset classes**: from the First Global Monthly Action Report
- **India against the world**: same report. Update India's rank in the heading.

Enter each bar as a name and a number. The chart redraws itself. Tick **Highlight this
one** on India only.

### 4. The behaviour gap

From **DSP Netra**, published monthly. This one never automates: investor returns need
flow data only the fund houses hold.

Usually worth changing only once a quarter. If Netra has not moved, leave it and update
the source line.

### 5. The writing

This is now most of the job, which is the right way round.

- **Headline** and **Opening paragraph**: what actually happened, in two sentences
- **The short version**: the three or four lines a reader takes away. **Check these
  against the scoreboard above them.** The numbers up there move every night and the
  sentences down here do not, so this is where the page goes wrong first. The morning
  issue checks this for you and names the figure it disagrees with.
- **The chain**: six links. Numbers mostly repeat from the scoreboard; the "why" line
  is the work.
- **What we are watching**: three things. Not predictions. Things that would change the
  picture if they moved.
- **If you track only ten**: rarely changes. That is the point of it.

### 6. Publish

Save in the CMS. The site rebuilds itself in a minute or two. Then open
`thisorthatshow.in/market-pulse` and check:

- [ ] The edition month in the top right is the new one
- [ ] The header reads "N figures last checked" with a recent date
- [ ] Each of the four hand-written fields says "as of" with the right date
- [ ] Every live tile still has its green dot
- [ ] No tile is blank
- [ ] The short version does not contradict the scoreboard
- [ ] The two charts have bars, and India is the red one
- [ ] It reads correctly on a phone

---

## Once a year, in January

Two constants. The morning issue nags for both from 1 January and will not stop until
they are set, because everything else on the page either fetches itself or is written,
and these are the only two numbers that go quietly wrong by sitting still.

**`fx_year_open`** → the FBIL USD/INR reference rate for 1 January. Then set
`fx_year_open_year` to the new year. Every rupee figure on the page hangs off this,
including both conversion tiles, so a wrong value here is wrong in three places at once.

> The 2026 value is **89.9792**, read from FBIL. It previously held 90.63, which had
> been derived from an earlier edition's own figure rather than read from the source,
> and it understated the rupee's fall by about a point.

**`gold_year_open`** → gold in dollars an ounce at the last close of the previous year.
Then set `gold_year_open_year`. The live price is fetched; no free source gives us the
history to measure it against.

> The 2026 value is **4341.10**.

---

## If a live figure looks wrong

1. Look at the page header. It says how many figures were last checked, and when. If
   that date is old, the nightly job has been failing and every live number is stale.
2. A single odd number is usually a real market move. Check it against the NSE site
   before assuming a bug.
3. The morning nudge job fetches the same figures from GitHub's network, not Vercel's.
   So if its log has today's numbers and the page does not, the **deploy** is broken,
   not the feed. That is a different problem and worth saying out loud.
4. If the nightly job is stuck, a redeploy re-runs it.

The refresher is deliberately cautious. Every figure is bounds-checked before it is
written, and if a source is unreachable or returns nonsense it leaves the old number
and the old date in place rather than publishing a guess. So a wrong-looking number is
far more likely to be stale than invented, and the date stamp will tell you which.

---

## What is deliberately not automated

**The behaviour gap**, the **global asset-class ladder** and the **42-market ranking**
are licensed work from DSP and First Global. There is no open source for them.

**India's 10-year G-sec** has no source a server can reach. See above.

**The writing** is not automated because it should not be. The numbers say what
happened. The paragraphs say what it meant, and that is the part worth a person's time.
