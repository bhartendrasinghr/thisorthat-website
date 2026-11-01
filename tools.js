/* Shared behaviour for the calculators and the allocator.

   Three things every tool needed and none of them had:

   1. A result you can send someone. Fifteen of seventeen tools produced a
      number that could not leave the tab: no link, no share, nothing. The
      answer is the most shareable thing on this site and it was a dead end.
   2. A result you can come back to. Three of seventeen remembered anything.
      Close the tab and your plan was gone.
   3. The answer visible while you are changing the question. On a phone the
      result sits a few hundred pixels below the first slider.

   Loaded at the end of <body>, after each page's own script, so the page has
   already run its first calc() before any of this touches it.

   The contract with a page is deliberately small:
     - nothing at all is required; URL state, restore and sharing work on any
       page with inputs
     - data-tool-headline="Label"  on the element holding the headline number
       turns on the sticky bar
     - data-tool-share             marks a spot for an inline share button
     - data-tool-ignore            on a wrapper keeps its inputs out of state
*/
(function () {
  'use strict';

  var LS_KEY = 'tot:tool:' + location.pathname;
  var SAVE_MS = 400;

  // Only the controls that are the actual state of the tool. Several pages
  // pair a slider with a text box that mirrors it; the slider is the one that
  // holds the value, and calc() writes the text box back, so serialising both
  // would double the URL and let them disagree on restore.
  function fields() {
    var out = [];
    var all = document.querySelectorAll(
      'input[type="range"][id], input[type="number"][id], ' +
      'input[type="checkbox"][id], input[type="radio"][id], select[id]');
    for (var i = 0; i < all.length; i++) {
      if (!all[i].closest('[data-tool-ignore]')) out.push(all[i]);
    }
    return out;
  }

  function read() {
    var s = {};
    fields().forEach(function (el) {
      if (el.type === 'checkbox') { if (el.checked) s[el.id] = 1; }
      else if (el.type === 'radio') { if (el.checked) s[el.name || el.id] = el.value; }
      else if (el.value !== '') { s[el.id] = el.value; }
    });
    return s;
  }

  // Apply, then tell the page. Every tool listens for 'input' on its controls
  // and some selects listen for 'change', so both go out; firing them is more
  // robust than guessing at a function name that differs on every page.
  function apply(s) {
    var touched = false;
    fields().forEach(function (el) {
      var key = el.type === 'radio' ? (el.name || el.id) : el.id;
      if (!(key in s)) return;
      var v = String(s[key]);
      if (el.type === 'checkbox') { el.checked = v === '1'; }
      else if (el.type === 'radio') { if (el.value !== v) return; el.checked = true; }
      else { el.value = v; }
      touched = true;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    });
    return touched;
  }

  function encode(s) {
    var p = new URLSearchParams();
    Object.keys(s).sort().forEach(function (k) { p.set(k, s[k]); });
    return p.toString();
  }

  // ── state in the URL, so the address bar is always the shareable thing ──
  var saveTimer = null;
  function persist() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () {
      var s = read();
      if (!Object.keys(s).length) return;
      var q = encode(s);
      try {
        history.replaceState(null, '', location.pathname + (q ? '?' + q : '') + location.hash);
      } catch (e) { /* history is unavailable in some embedded views */ }
      try { localStorage.setItem(LS_KEY, JSON.stringify(s)); } catch (e) { /* private mode */ }
    }, SAVE_MS);
  }

  function restore() {
    var q = new URLSearchParams(location.search);
    if (q.toString()) {
      var fromUrl = {};
      q.forEach(function (v, k) { fromUrl[k] = v; });
      if (apply(fromUrl)) return 'url';
    }
    // No link to go on: pick up where this browser left off. A shared link
    // always wins, so someone else's numbers are never silently replaced by
    // your own.
    try {
      var saved = localStorage.getItem(LS_KEY);
      if (saved && apply(JSON.parse(saved))) return 'storage';
    } catch (e) { /* unreadable or blocked, start fresh */ }
    return null;
  }

  // ── share ───────────────────────────────────────────────────────────────
  function shareUrl() {
    var q = encode(read());
    return location.origin + location.pathname + (q ? '?' + q : '');
  }

  function share(btn, restingLabel) {
    var url = shareUrl();
    var title = document.title;
    function copied() {
      var was = btn.textContent;
      btn.textContent = 'Link copied';
      setTimeout(function () { btn.textContent = was || restingLabel; }, 1600);
    }
    if (navigator.share) {
      navigator.share({ title: title, url: url }).catch(function () { /* dismissed */ });
      return;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(copied, function () { prompt('Copy this link', url); });
      return;
    }
    prompt('Copy this link', url);
  }

  // ── the sticky answer ───────────────────────────────────────────────────
  function stickyBar(head) {
    // Several tools write part of the label from the inputs ("At 8.0%, your
    // money doubles in"), so where the page marks its label element we track
    // that live rather than freezing a string at build time.
    var labelEl = document.querySelector('[data-tool-headline-label]');
    var label = head.getAttribute('data-tool-headline')
      || (labelEl && labelEl.textContent.trim())
      || 'Your answer';
    var bar = document.createElement('div');
    bar.id = 'tool-bar';
    bar.setAttribute('role', 'status');
    bar.setAttribute('aria-live', 'polite');
    bar.innerHTML =
      '<div style="min-width:0">' +
        '<div class="tool-bar-label"></div>' +
        '<div class="tool-bar-value"></div>' +
      '</div>' +
      '<button type="button" class="tool-bar-share">Share</button>';
    bar.querySelector('.tool-bar-label').textContent = label;
    document.body.appendChild(bar);
    document.body.classList.add('has-tool-bar');

    var valueEl = bar.querySelector('.tool-bar-value');
    var btn = bar.querySelector('.tool-bar-share');
    btn.addEventListener('click', function () { share(btn, 'Share'); });

    var labelOut = bar.querySelector('.tool-bar-label');
    function sync() {
      valueEl.textContent = (head.textContent || '').trim();
      if (labelEl) labelOut.textContent = labelEl.textContent.trim();
    }
    sync();
    var opts = { childList: true, characterData: true, subtree: true };
    new MutationObserver(sync).observe(head, opts);
    if (labelEl) new MutationObserver(sync).observe(labelEl, opts);

    // Show it only while the real answer is off screen. A bar repeating a
    // number the reader is already looking at is just clutter.
    if ('IntersectionObserver' in window) {
      // The viewport minus the bar itself: the moment any of the real answer
      // clears the bar, the bar is redundant and goes away.
      new IntersectionObserver(function (entries) {
        bar.setAttribute('data-show', entries[0].isIntersecting ? '0' : '1');
      }, { rootMargin: '0px 0px -72px 0px' }).observe(head);
    } else {
      bar.setAttribute('data-show', '1');
    }
  }

  // ── wire up ─────────────────────────────────────────────────────────────
  function init() {
    if (!fields().length) return;

    restore();

    document.addEventListener('input', persist, true);
    document.addEventListener('change', persist, true);

    var slot = document.querySelector('[data-tool-share]');
    if (slot) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'tool-share-inline';
      b.textContent = slot.getAttribute('data-tool-share') || 'Copy link to these numbers';
      b.addEventListener('click', function () { share(b, 'Copy link to these numbers'); });
      slot.appendChild(b);
    }

    var head = document.querySelector('[data-tool-headline]');
    if (head) stickyBar(head);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
