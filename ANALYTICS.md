# What this site measures

Google Analytics 4, property `G-QDF1DKH66W`.

The tag sits inline in every page's `<head>`, where Google wants it. The
events live in [`analytics.js`](analytics.js), which loads deferred, so a
blocked or slow copy costs the detail and never the page. Both are written
by `build.py` (`ANALYTICS_TAG` and `check_analytics()`), so the tag is
defined in exactly one place and every build rewrites all 115 public pages
to match. Editing the tag by hand in a page will be undone on the next build,
which is the point.

## What is deliberately not collected

**No calculator input, and no calculator result.** privacy.html promises
those never leave the browser, and that promise is worth more than the data.
The tool events carry behaviour and never numbers: which tool, how many
controls were touched, how many adjustments, how long, whether it was shared.
That answers every question we actually had.

**No field from the introduction form.** Name, age, goals and contact
details go to Bhartendra and nowhere else. Only the step reached is counted.

Google Signals and ad personalisation are switched off for this property, so
a visit is not added to an advertising profile. privacy.html says all of
this in plain language.

## The questions this was built to answer

| Question | How to read it |
|---|---|
| Which tools do people actually finish? | `tool_open` → `tool_start` → `tool_engaged` → `tool_result`, split by `tool`. The drop between open and start is the headline number. |
| Did the chooser work? | `tool_click` where `intent` is set, against `tool_click` where it is not. One is the chooser, the other is someone scrolling the list. |
| Does anyone press play? | `episode_play` ÷ page views on `page_type = episode`, then `episode_progress` for how far they got. |
| Which part of an hour matters? | `chapter_click` by `chapter_label` and `chapter_seconds`. |
| Where do people give up reading? | `scroll_depth` quartiles by `page_type`. |
| Do the episodes feed the tools? | `episode_tool_nudge`, and `tool_click` with `region = body` on episode pages. |
| What are people looking for that we do not have? | `search` by `search_term`, especially where `results` is 0. |
| Which links are broken? | `not_found` by `broken_path` and `referrer`. |

## The events

Every event also carries `page_type` and `page_name`.

**Tools** (on `page_type = tool` only)

| Event | Parameters |
|---|---|
| `tool_open` | `tool`, `state` (blank / storage / url) |
| `tool_start` | `tool`. First control a person moves. |
| `tool_engaged` | `tool`, `controls_used`. Three different controls, the line between a poke and real use. |
| `tool_result` | `tool`, `adjustments`, `controls_used`, `seconds`. Fires once, 2.5s after the last change. |
| `tool_session` | the same, plus `reached_result` and `max_scroll`, on the way out |
| `tool_share` | `tool`, `method` (web_share / clipboard / prompt), `placement` |
| `tool_click` | `tool`, `region`, `intent`. A link to a tool, from anywhere. |
| `chooser_pick` | `intent`. A question picked on calculators.html. |

**Episodes**

| Event | Parameters |
|---|---|
| `episode_play` | `episode`, `video_id`. Needs `enablejsapi=1` on the embed, which `episode-detail.html` sets. |
| `episode_progress` | `episode`, `video_id`, `percent` (25 / 50 / 75 / 95) |
| `chapter_click` | `episode`, `chapter_seconds`, `chapter_label` |
| `episode_tool_nudge` | `episode`, `tool` |
| `episode_click` | `episode`, `region` |

**Forms**

| Event | Parameters |
|---|---|
| `newsletter_start` | first focus in the email box |
| `newsletter_submit` / `newsletter_signup` / `newsletter_error` | `reason` on the error |
| `lead_start` / `lead_submit` / `lead_invalid` / `lead_error` | `reason` on the error |
| `generate_lead` | the introduction form went through. GA4's own name for it, so it lands in the standard reports. |

**Everything else**

| Event | Parameters |
|---|---|
| `scroll_depth` | `percent` (25 / 50 / 75 / 100) |
| `search` | `search_term`, `surface` (episodes / guests / funds), `results` |
| `filter_click` | `filter` (topic / role), `label` |
| `outbound_click` | `destination`, `link_domain`, `link_url`, `link_text`, `region`, `episode` |
| `internal_click` | `target`, `label`, `region` (nav / footer / body) |
| `guest_click`, `article_click`, `email_click` | `region`, plus `guest` or `article` |
| `fund_select` | `fund`, `category`. The NAV is stripped: it moves daily and would scatter one fund across a hundred rows. |
| `compass_preset`, `compass_category` | `preset` / `category` |
| `not_found` | `broken_path`, `referrer` |

`page_type` is one of: home, episode, episode_index, guest, guest_index,
tool, tool_index, article, article_index, guide, pulse, data, lead, legal,
not_found, internal, page.

User properties: `returning_tool_user` (yes / no) and `tools_saved`, both
from whether this browser has ever saved a tool's state. No identity.

## Setup still to do in the GA4 interface

Parameters are collected from the moment this is live, but they do **not**
appear in standard reports until they are registered as custom dimensions.
Admin → Data display → Custom definitions → Create custom dimension. Scope
is Event unless stated.

Register these eight first. They carry most of the value:

1. `page_type`
2. `tool`
3. `episode`
4. `intent`
5. `state`
6. `reached_result`
7. `search_term`
8. `percent`

Then, as they are needed: `adjustments`, `controls_used`, `seconds`,
`region`, `destination`, `surface`, `results`, `method`, `placement`,
`chapter_label`, `chapter_seconds`, `fund`, `category`, `preset`, `filter`,
`label`, `target`, `reason`, `broken_path`, `referrer`, `video_id`,
`link_domain`, `max_scroll`, `page_name`.

Two more, scope User: `returning_tool_user` and `tools_saved`.

Worth marking as key events (Admin → Events): `generate_lead`,
`newsletter_signup`, `tool_result`, `episode_play`.

There is a limit of 50 event-scoped custom dimensions on the free tier, and
registering one does not backfill history, so register a dimension before
the month you want to report on it.

## Checking it works

Add `?ga_debug=1` to any URL and every event prints to the browser console
as it fires. Nothing else changes.

GA4's own DebugView (Admin → DebugView) shows live hits, but only from a
browser with the GA Debugger extension or a page loaded with `debug_mode`.

To test without putting hits into the real property, copy the site, replace
the measurement id, and serve it: `window.dataLayer` fills either way,
because the inline block defines `gtag` whether or not Google answers.

## Adding an event

Two conventions, so new pages do not need new JavaScript:

```html
<a href="..." data-ga-event="pricing_click" data-ga-plan="annual">
```

fires `pricing_click` with `plan: "annual"`. Any `data-ga-*` attribute
becomes a parameter. From a page's own script, call
`window.totTrack('name', { param: 'value' })`, guarded with
`typeof window.totTrack === 'function'` so the page still works when
analytics.js was blocked.
