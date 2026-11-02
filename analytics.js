/* The event layer on top of the GA4 tag.

   Before this file, the tag counted page views and nothing else. For a site
   whose point is seventeen tools and seventy-four episodes, that answered
   almost none of the questions worth asking: not which tool anyone finishes,
   not whether a single slider gets moved, not whether anybody presses play.
   You could see that calc-retirement.html was opened and nothing about what
   happened next.

   What is deliberately NOT sent
   -----------------------------
   No calculator input ever leaves the browser, and neither does any result.
   privacy.html promises exactly that, and it is a promise worth more than
   the data. So the tool events carry behaviour and never numbers: which tool,
   how many controls were touched, how many adjustments, how long, whether it
   was shared. That turns out to answer every question we actually had.
   The lead form on money-person.html is treated the same way: the funnel is
   tracked, the fields are not.

   How it is wired
   ---------------
   The tag itself sits inline in each page's <head>, where Google wants it,
   and works on its own. This file loads deferred and adds the events, so a
   slow or blocked analytics.js costs us the detail and never the page.

   Almost everything here is delegated or convention-driven, because the
   alternative is editing a hundred and twenty pages and then forgetting the
   hundred and twenty-first. Two conventions:

     data-ga-event="name"   on any element, fires that event on click
     data-ga-anything="x"   becomes the param anything="x"

   Add ?ga_debug=1 to any URL to see every event in the console as it fires.
*/
(function () {
  'use strict';

  if (typeof window.gtag !== 'function') return;   // tag blocked, or no tag

  var DEBUG = /[?&]ga_debug=1/.test(location.search) ||
              window.TOT_ANALYTICS_DEBUG === true;
  var PAGE = location.pathname.replace(/^\/+/, '').replace(/\.html$/, '') || 'home';
  var PAGE_TYPE = window.TOT_PAGE_TYPE || 'page';
  var EP_NUM = (PAGE.match(/^ep-(\d+)/) || [])[1] || '';

  // ── sending ─────────────────────────────────────────────────────────────

  // GA4 silently truncates a parameter value past 100 characters, which is
  // worse than cutting it ourselves: a half-sent label looks like real data.
  function clip(v) {
    v = v == null ? '' : String(v).replace(/\s+/g, ' ').trim();
    return v.length > 100 ? v.slice(0, 99) + '…' : v;
  }

  var fired = {};
  function track(name, params, oncePerView) {
    if (oncePerView) {
      if (fired[name]) return;
      fired[name] = 1;
    }
    var p = params || {};
    // An empty parameter is not a measurement, it is a "(not set)" row in
    // every report that touches the event. Drop them; zero is kept, because
    // zero is an answer.
    for (var k in p) {
      if (p[k] === '' || p[k] === null || p[k] === undefined) delete p[k];
    }
    p.page_type = PAGE_TYPE;
    p.page_name = PAGE;
    if (DEBUG) {
      try { console.log('[ga] ' + name, p); } catch (e) { /* no console */ }
    }
    try { window.gtag('event', name, p); } catch (e) { /* never break a click */ }
  }

  // tools.js and any page script can reach the same funnel.
  window.totTrack = track;

  // ── who is here ─────────────────────────────────────────────────────────
  // Whether this browser has ever saved a tool's state, which separates
  // "came back to finish the plan" from "first look" without any identity.
  (function userProps() {
    var n = 0;
    try {
      for (var i = 0; i < localStorage.length; i++) {
        if (String(localStorage.key(i)).indexOf('tot:tool:') === 0) n++;
      }
    } catch (e) { return; }                        // private mode, say nothing
    try {
      window.gtag('set', 'user_properties', {
        tools_saved: String(n),
        returning_tool_user: n > 0 ? 'yes' : 'no'
      });
    } catch (e) { /* ignore */ }
  })();

  // ── how far down the page anyone got ────────────────────────────────────
  // GA4's own enhanced measurement fires once, at 90%, which tells you who
  // read to the end and nothing about where everyone else stopped. The whole
  // value is in the quartiles, so this is a separate event, not a duplicate.
  var maxScroll = 0;
  (function scrollDepth() {
    var marks = [25, 50, 75, 100], hit = {}, queued = false;

    // How far down, or -1 when there is no meaningful answer: a page with
    // less than a couple of hundred pixels of travel has no quartiles worth
    // reporting, and a height read mid-layout is not a measurement.
    function percent() {
      var doc = document.documentElement;
      var full = Math.max(doc.scrollHeight, document.body ? document.body.scrollHeight : 0);
      var room = full - window.innerHeight;
      if (room < 200) return -1;
      var off = window.pageYOffset || doc.scrollTop || 0;
      return Math.min(100, Math.round((off / room) * 100));
    }

    // A reported mark cannot be taken back, so each one is read twice, a
    // frame apart, and only the lower of the two is believed. A page whose
    // height is briefly wrong, a font swapping in or a chart sizing itself,
    // otherwise reads as 100% for a single frame and permanently records a
    // reader who got to the bottom of a page they never scrolled.
    function latch() {
      var first = percent();
      if (first < 0) return;
      if (first > maxScroll) maxScroll = first;
      if (document.readyState !== 'complete') return;   // layout still moving
      requestAnimationFrame(function () {
        var second = percent();
        if (second < 0) return;
        var reached = Math.min(first, second);
        for (var i = 0; i < marks.length; i++) {
          if (reached >= marks[i] && !hit[marks[i]]) {
            hit[marks[i]] = 1;
            track('scroll_depth', { percent: marks[i] });
          }
        }
      });
    }

    function onScroll() {
      if (queued) return;
      queued = true;
      requestAnimationFrame(function () { latch(); queued = false; });
    }
    // Once the page has settled, in case it opened partway down at an anchor.
    if (document.readyState === 'complete') latch();
    else window.addEventListener('load', latch);
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
  })();

  // ── every click, once, in one listener ──────────────────────────────────
  // Capture phase, so a page that stops propagation on its own handler does
  // not take the measurement with it.
  var TOOL_HREF = /^(calc-[a-z0-9-]+|asset-allocator|funds|category-compass|ipo-checker|money-person)(\.html|$)/;

  function params(el) {
    var out = {}, a = el.attributes;
    for (var i = 0; i < a.length; i++) {
      var n = a[i].name;
      if (n.indexOf('data-ga-') !== 0 || n === 'data-ga-event') continue;
      out[n.slice(8).replace(/-/g, '_')] = clip(a[i].value);
    }
    return out;
  }

  function region(el) {
    if (el.closest('header')) return 'nav';
    if (el.closest('footer')) return 'footer';
    return 'body';
  }

  document.addEventListener('click', function (e) {
    if (e.isTrusted === false) return;             // a script's click, not a reader's
    var el = e.target && e.target.closest
      ? e.target.closest('a,button,[data-ga-event],[data-pick],.row,.preset')
      : null;
    if (!el) return;

    // 1. Anything that asked to be tracked by name.
    var named = el.getAttribute('data-ga-event');
    if (named) { track(named, params(el)); return; }

    // 2. A chapter in an episode's timeline. Leaves for YouTube at a
    //    timestamp, so it is both a chapter click and the strongest signal
    //    we have about which part of an hour anyone cared about.
    var chapter = el.getAttribute('data-ga-chapter');
    if (chapter) {
      track('chapter_click', {
        episode: EP_NUM,
        chapter_seconds: Number(chapter) || 0,
        // The row reads "4:42 Why 10-12% returns ... >", and the timestamp
        // is already in chapter_seconds. Strip both ends so the label is
        // the chapter title and nothing else, which is what a report wants.
        chapter_label: clip(String(el.textContent || '')
          .replace(/^\s*\d{1,2}:\d{2}(?::\d{2})?\s*/, '')
          .replace(/[\s\u25B6\u25BA>]+$/, ''))
      });
      return;
    }

    // 3. The "run your own numbers" card under an episode.
    if (el.id === 'plan-nudge' || el.closest('#plan-nudge')) {
      var nudge = document.getElementById('plan-nudge');
      track('episode_tool_nudge', {
        episode: EP_NUM,
        tool: clip((nudge && nudge.getAttribute('href')) || '').replace(/\.html$/, '')
      });
      return;
    }

    // 4. The chooser on calculators.html.
    if (el.classList && el.classList.contains('intent-chip')) {
      track('chooser_pick', { intent: clip(el.textContent) });
      return;
    }

    // 5. funds.html: picking a fund out of the suggestions. The row is two
    //    lines, the fund's name and then its category and today's NAV, so
    //    taking the whole row would put a number that moves daily into the
    //    label and scatter every lookup of one fund across a hundred rows
    //    of the report.
    if (el.hasAttribute('data-pick')) {
      var lines = el.children;
      track('fund_select', {
        fund: clip(lines.length ? lines[0].textContent : el.textContent),
        category: clip(lines.length > 1
          ? String(lines[1].textContent).split('\u00B7')[0] : '')
      });
      return;
    }

    // 6. category-compass.html: a weighting preset, or a category row.
    if (el.classList && el.classList.contains('preset')) {
      track('compass_preset', { preset: clip(el.textContent) });
      return;
    }
    if (el.classList && el.classList.contains('row') && el.dataset && el.dataset.k) {
      track('compass_category', { category: clip(el.dataset.k) });
      return;
    }

    // 7. The filter rows on the episode and guest indexes.
    if (el.closest('#chip-row')) {
      track('filter_click', { filter: 'topic', label: clip(el.textContent) });
      return;
    }
    if (el.closest('#role-pills')) {
      track('filter_click', { filter: 'role', label: clip(el.textContent) });
      return;
    }

    // 8. Links, classified by where they go.
    if (el.tagName !== 'A') return;
    var href = el.getAttribute('href') || '';
    if (!href || href.charAt(0) === '#') return;

    if (/^mailto:/i.test(href)) {
      track('email_click', { region: region(el) });
      return;
    }

    if (/^https?:\/\//i.test(href)) {
      var host = '';
      try { host = new URL(href).hostname.replace(/^www\./, ''); } catch (e2) { host = 'unknown'; }
      if (host && host !== location.hostname.replace(/^www\./, '')) {
        track('outbound_click', {
          destination: /youtube|youtu\.be/.test(host) ? 'youtube'
                     : /instagram/.test(host) ? 'instagram'
                     : /linkedin/.test(host) ? 'linkedin'
                     : /(^|\.)x\.com$|twitter/.test(host) ? 'x'
                     : 'other',
          link_domain: clip(host),
          link_url: clip(href),
          link_text: clip(el.textContent),
          region: region(el),
          episode: EP_NUM
        });
        return;
      }
    }

    var path = href.replace(/^\.?\//, '').replace(/[?#].*$/, '');
    var reg = region(el);

    var ep = path.match(/^ep-(\d+)/);
    if (ep) { track('episode_click', { episode: ep[1], region: reg }); return; }

    var tool = path.match(TOOL_HREF);
    if (tool) {
      track('tool_click', {
        tool: tool[1],
        region: reg,
        // Set by the chooser on the cards it builds, so a tool opened from
        // "Should I buy a house?" is distinguishable from one opened by
        // scrolling the list.
        intent: clip(el.getAttribute('data-ga-intent') || '')
      });
      return;
    }

    if (/^guest-detail/.test(path) || /^guests?$/.test(path.replace(/\.html$/, ''))) {
      track('guest_click', { guest: clip(el.textContent), region: reg });
      return;
    }
    if (/^article/.test(path)) {
      track('article_click', { article: clip(path), region: reg });
      return;
    }

    track('internal_click', {
      target: clip(path.replace(/\.html$/, '') || 'home'),
      label: clip(el.textContent),
      region: reg
    });
  }, true);

  // ── what people search for ──────────────────────────────────────────────
  // Three surfaces, three different input ids, one behaviour. Debounced hard,
  // because the useful signal is the query someone settled on, not the seven
  // prefixes they typed on the way to it. Named `search` so it lands in GA4's
  // own site-search reporting rather than in a custom report nobody opens.
  (function searches() {
    var SURFACES = [
      ['search-input', 'episodes', '#ep-grid'],
      ['search', 'guests', '#rest-grid'],
      ['q', 'funds', null]
    ];
    SURFACES.forEach(function (s) {
      var input = document.getElementById(s[0]);
      if (!input) return;
      var timer = null, last = '';
      input.addEventListener('input', function () {
        clearTimeout(timer);
        timer = setTimeout(function () {
          var term = (input.value || '').trim();
          if (term.length < 2 || term === last) return;
          last = term;
          var p = { search_term: clip(term.toLowerCase()), surface: s[1] };
          if (s[2]) {
            var box = document.querySelector(s[2]);
            if (box) p.results = box.children.length;
          }
          track('search', p);
        }, 1100);
      });
    });
  })();

  // ── the newsletter, up to the point of the ask ──────────────────────────
  // The outcome is reported by the form's own handler, which is the only
  // thing that knows whether the server said yes. This half is the intent:
  // how many people put a cursor in the box at all.
  (function newsletter() {
    var forms = document.querySelectorAll('.nl-form');
    for (var i = 0; i < forms.length; i++) {
      (function (form) {
        var box = form.querySelector('input[name=email]');
        if (!box) return;
        box.addEventListener('focus', function () {
          track('newsletter_start', {}, true);
        });
      })(forms[i]);
    }
  })();

  // ── the lead form ───────────────────────────────────────────────────────
  (function leadForm() {
    var form = document.getElementById('lead-form');
    if (!form) return;
    form.addEventListener('focusin', function () {
      track('lead_start', {}, true);
    });
  })();

  // ── the tools ───────────────────────────────────────────────────────────
  // The question this exists to answer: of the people who open a calculator,
  // how many touch it, how many work it properly, and how long do they stay.
  // Values are not part of the answer and are not collected.
  (function tools() {
    // money-person.html also loads tools.js, and a tick on its consent box
    // is not somebody using a calculator.
    if (PAGE_TYPE !== 'tool') return;
    var controls = document.querySelectorAll(
      'input[type="range"][id], input[type="number"][id], ' +
      'input[type="checkbox"][id], input[type="radio"][id], select[id]');
    if (!controls.length) return;

    var tool = PAGE;
    var touched = {}, nTouched = 0, adjustments = 0;
    var landed = Date.now();
    var settle = null;

    function distinct() { return nTouched; }

    document.addEventListener('input', onChange, true);
    document.addEventListener('change', onChange, true);

    function onChange(e) {
      // Only a person moving a control counts. tools.js restores a saved or
      // shared set of numbers by dispatching input events at every field,
      // and several pages mirror a slider into a text box the same way, so
      // without this an arriving reader who touched nothing would be
      // recorded as having worked the tool hard enough to engage with it.
      if (e.isTrusted === false) return;
      var el = e.target;
      if (!el || !el.id || el.closest('[data-tool-ignore]')) return;
      if (!/^(INPUT|SELECT)$/.test(el.tagName)) return;

      // One adjustment is one value the reader settled on, which is what
      // `change` means and what `input` does not: a slider fires `input` for
      // every pixel of a drag and both events for every arrow key, so
      // counting either on its own would make a mouse user look ten times
      // more diligent than a keyboard user doing the same work. `input`
      // still drives everything below, because it arrives first.
      if (e.type === 'change') adjustments++;
      if (!touched[el.id]) { touched[el.id] = 1; nTouched++; }

      track('tool_start', { tool: tool }, true);
      // Three different controls is the line between a poke and real use:
      // one slider moves by accident, three is someone answering questions.
      if (nTouched >= 3) {
        track('tool_engaged', { tool: tool, controls_used: nTouched }, true);
      }

      // Two and a half seconds without a change means they have stopped
      // adjusting and are reading the answer. That is the moment a tool has
      // actually produced something, so it is what we count as a result.
      clearTimeout(settle);
      settle = setTimeout(function () {
        track('tool_result', {
          tool: tool,
          adjustments: adjustments,
          controls_used: distinct(),
          seconds: Math.round((Date.now() - landed) / 1000)
        }, true);
      }, 2500);
    }

    // One summary per visit, on the way out, so a tool that gets opened and
    // abandoned is as visible as one that gets used.
    window.addEventListener('pagehide', function () {
      track('tool_session', {
        tool: tool,
        adjustments: adjustments,
        controls_used: distinct(),
        seconds: Math.round((Date.now() - landed) / 1000),
        reached_result: fired.tool_result ? 'yes' : 'no',
        max_scroll: maxScroll
      });
    });
  })();

  // ── did anyone press play ───────────────────────────────────────────────
  // The single most valuable number on a podcast's website, and the one it
  // has never had. The embed carries enablejsapi=1 so the player can be
  // asked; the API shim is fetched only on a page that has a player, and
  // only once the page has finished loading, so it never competes with the
  // first paint.
  (function episodeVideo() {
    var frame = document.getElementById('yt-iframe');
    if (!frame) return;

    var src = frame.getAttribute('src') || '';
    if (src.indexOf('enablejsapi=1') < 0) return;      // nothing to talk to
    var vid = (src.match(/\/embed\/([^?&/]+)/) || [])[1] || '';

    var marks = [25, 50, 75, 95], hit = {}, timer = null, player = null;

    function began() {
      track('episode_play', { episode: EP_NUM, video_id: vid }, true);
      poll();
    }

    function poll() {
      if (timer) return;
      timer = setInterval(function () {
        var d = 0, t = 0;
        try { d = player.getDuration() || 0; t = player.getCurrentTime() || 0; }
        catch (e) { return; }
        if (d <= 0) return;
        var pct = (t / d) * 100;
        for (var i = 0; i < marks.length; i++) {
          if (pct >= marks[i] && !hit[marks[i]]) {
            hit[marks[i]] = 1;
            track('episode_progress', { episode: EP_NUM, video_id: vid, percent: marks[i] });
          }
        }
        if (hit[95]) { clearInterval(timer); timer = null; }
      }, 5000);
    }

    function attach() {
      try {
        player = new window.YT.Player(frame, {
          events: {
            // Play may already have happened while the shim was loading.
            onReady: function () {
              try {
                if (player.getPlayerState() === window.YT.PlayerState.PLAYING) began();
              } catch (e) { /* ignore */ }
            },
            onStateChange: function (e) {
              if (e.data === window.YT.PlayerState.PLAYING) began();
            }
          }
        });
      } catch (e) { /* no measurement, no harm */ }
    }

    function load() {
      if (window.YT && window.YT.Player) { attach(); return; }
      var prev = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = function () {
        if (typeof prev === 'function') { try { prev(); } catch (e) { /* ignore */ } }
        attach();
      };
      if (!document.querySelector('script[src*="youtube.com/iframe_api"]')) {
        var s = document.createElement('script');
        s.src = 'https://www.youtube.com/iframe_api';
        s.async = true;
        document.head.appendChild(s);
      }
    }

    function later() { setTimeout(load, 1500); }
    if (document.readyState === 'complete') later();
    else window.addEventListener('load', later);
  })();

  // ── the page nobody meant to land on ────────────────────────────────────
  // A 404 with the path and where it came from is the difference between
  // knowing links are broken and knowing which link is broken.
  if (PAGE_TYPE === 'not_found') {
    track('not_found', {
      broken_path: clip(location.pathname + location.search),
      referrer: clip(document.referrer || 'none')
    });
  }

  if (DEBUG) {
    try {
      console.log('[ga] analytics.js ready. page_type=' + PAGE_TYPE + ' page=' + PAGE);
    } catch (e) { /* no console */ }
  }
})();
