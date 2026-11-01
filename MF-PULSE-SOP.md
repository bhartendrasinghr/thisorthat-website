# MF Industry Pulse, monthly update

How to publish a new edition of **thisorthatshow.in/mf-pulse**.

Budget about **20 minutes a month**, plus **15 minutes once a quarter** for the fund
house table. No code, no terminal. Everything is done in the CMS at
`thisorthatshow.in/admin` under **MF Industry Pulse**.

---

## First, what you do NOT have to do

Almost every number on this page reads itself off AMFI's own filings. There is no
step where anybody retypes a figure, which is the whole point: that is where errors
come from. These carry a green dot on the page and the date they were read.

| What | Where it comes from |
|---|---|
| Industry assets, and the change on the month and year | AMFI monthly report, the spreadsheet |
| Equity, debt, hybrid and passive net flows, seven months of them | same |
| Assets by kind of fund | same |
| All thirteen equity categories: flows, assets, scheme counts | same |
| Index funds and ETFs, split six ways | same |
| Investor folios | same |
| New schemes launched and what they gathered | AMFI new scheme sheet, same workbook |
| Monthly SIP, SIP accounts, SIP assets, the equity streak | AMFI monthly note, the PDF |
| Specialised investment funds | AMFI's own JSON feed |
| The Nifty 50 card | NSE daily index archive |

**Never type over any of these.** There is nowhere in the CMS to do it, on purpose.
If one of them looks wrong, the number is wrong at AMFI or the parse is wrong, and
either way it is a message to Claude rather than something to patch by hand.

The page picks up a new month on its own, usually within a day of AMFI publishing,
which is around the **8th to the 12th**. You do not have to do anything to make that
happen. What follows is only the writing.

---

## The monthly job, around the 12th

### 1. Check the month turned over (1 minute)

Open **thisorthatshow.in/mf-pulse**. The line at the top right should name last
month, not the month before. If it still says the old month a week after the 12th,
the refresh is stuck: tell Claude, and say which month it is showing.

### 2. Rewrite "What to make of it" (10 minutes)

CMS → **MF Industry Pulse** → **The written half** → **What to make of it**.

This is the only real writing on the page, and it is the only thing a reader cannot
get from AMFI's own PDF. One short paragraph. Set **Written on** to today.

What makes a good one:

- Say what the month *means*, never what it *was*. The numbers above it already say
  what it was, and they say it more precisely than a sentence can.
- Point at the two or three rows a reader should actually look at, and say which rows
  to ignore. The debt swings in particular are almost always company treasuries
  moving cash around a quarter end, and a reader who thinks that is households
  panicking has been misled by a true number.
- No forecasts. Not "small caps look stretched", but "small caps have taken the most
  money in for N months, which is the opposite of what a falling market usually does".
- If the month was dull, say so. A dull month is information.

### 3. Update the four figures AMFI does not publish (4 minutes)

CMS → **Who was buying**. Four cards, all monthly:

| Card | Where to get it |
|---|---|
| FII equity net | NSDL FPI monitor, or the Moneycontrol FII/DII activity page |
| DII equity net | same page |
| Nifty 50 TRI for the month | NSE indices, Nifty 50 TRI monthly return |
| 10-year G-sec yield | CCIL or RBI, the month-end close, with the previous month in the small print |

Set **Entered on** to today. The Nifty 50 card sitting next to these refreshes
itself, so leave it alone.

### 4. Set the edition line and save (1 minute)

Set **Edition** and **Updated on**. Save. The page is live in about two minutes.

---

## The fortnightly job

CMS → **This fortnight in the industry**.

Replace the whole list with the last two weeks. Twenty items is plenty, newest
first. Source is **cafemutual.com/news/archive**, which files everything by date.

Write each one as a sentence a person would say out loud, not a headline:

- Not "SEBI mandates direct plan default on AMC platforms w.e.f. 01.11.2026"
- But "SEBI makes direct plans the default on AMC digital platforms from 1 November"

Set **Dates covered** and **Compiled on**. Themes drive the filter chips, so keep
to the list in the dropdown rather than inventing near duplicates.

---

## The quarterly job: the fund house table

AMFI publishes average assets per fund house about three weeks after each quarter
ends, so: **late January, late April, late July, late October**.

CMS → **Fund house table (quarterly)**.

1. Get the quarter's table. Cafemutual publishes it as a readable list within a day
   or two, and AMFI itself has it under Research and Information → AMFI Data.
2. For each house, move the current **Average AUM this quarter** value down into
   **Average AUM last quarter**, then enter the new one.
3. Update **Industry average AUM for the quarter**, and the **Quarter** label.
4. Set **Entered on** to today.

**Share** and **Change on the quarter** are not computed for you in the CMS, so if
you are doing this by hand, compute them: share is the house's assets divided by the
industry total, and the change is this quarter over last, minus one.

Honestly, this is the one job worth handing to Claude. Paste the quarter's table into
a chat, say "update the fund house table on mf-pulse", and it will do the arithmetic,
check that the 50-odd rows add up to the industry total, and flag any row where they
do not. That check is the real value: a leaderboard where the parts do not sum to the
whole has a typo in it, and the typo is invisible to the eye.

---

## When something looks wrong

**The month has not moved a week after the 12th.** The refresh is failing. Look at
the Actions tab of the repo for "Refresh MF Industry Pulse from AMFI", which runs
daily from the 8th to the 15th and fails loudly. Tell Claude what it says.

**A number disagrees with something you read elsewhere.** Check the source first.
The page links the exact spreadsheet and note it read, at the bottom under "How this
page is built". Two real reasons this happens:

- *Passive flows.* We count index funds plus ETFs, which is how AMFI's own note
  defines it. Several published summaries quietly add overseas fund of funds into
  the same line, which makes their number bigger than ours.
- *New schemes.* We print AMFI's own total, which includes domestic fund of funds and
  is shown separately underneath. Summaries that count only open-ended mutual fund
  schemes will print a smaller number.

Neither is an error. If you want to cite one on the show, cite ours and say what it
includes.

**A category disappeared from the equity table.** AMFI changed the scheme
categorisation in August 2026, and may do it again. The refresh prints a warning when
a category it expects is missing, and the page checks that the thirteen categories add
up to AMFI's own equity total before it publishes. If that check fails, the page says
so rather than showing a table that does not add up. Tell Claude.

---

## What this page is not

It is not advice, and the design keeps it that way on purpose. It says where money
went. It never says where money should go. A category taking in money is a fact about
other people, not a recommendation to you, and the disclaimer at the bottom says that
in plain words. Keep it there.
