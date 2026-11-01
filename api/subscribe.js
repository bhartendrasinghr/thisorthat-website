// Slow Thought signups.
//
// The site promised "Slow Thought, weekly. One honest idea. Every week." on
// 78 pages and then put a Subscribe on YouTube button underneath it. The
// promise and the payload did not match, and there was no way at all to give
// Bhartendra an email address. Every path off this site led to a platform he
// does not own.
//
// POST: stores the address as a JSON blob in the private thisorthat-leads
// store, the same place the "talk to a human" leads go.
// GET ?key=<LEADS_KEY>: the list, as HTML or CSV, for Bhartendra.
import { put, list } from '@vercel/blob';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// Deliberately permissive. The job here is to catch a typo and an empty box,
// not to adjudicate RFC 5322; a real address that a strict regex rejects is a
// reader lost for nothing.
const LOOKS_LIKE_EMAIL = /^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$/;

function toCsv(subs) {
  const cell = (v) => '"' + String(v ?? '').replace(/"/g, '""') + '"';
  const head = ['When (UTC)', 'Email', 'Signed up from'];
  const body = subs.map(s => [
    (s.at || '').replace('T', ' ').slice(0, 19), s.email, s.page
  ].map(cell).join(','));
  // Excel and Numbers need the BOM or they mangle anything non-ASCII.
  return '﻿' + [head.map(cell).join(','), ...body].join('\r\n');
}

async function allSubs() {
  const { blobs } = await list({ prefix: 'subs/', limit: 1000 });
  blobs.sort((a, b) => (a.pathname < b.pathname ? 1 : -1));   // newest first
  const out = [];
  for (const b of blobs) {
    try {
      let r = await fetch(b.downloadUrl || b.url);
      if (!r.ok) {
        r = await fetch(b.url, {
          headers: { authorization: `Bearer ${process.env.BLOB_READ_WRITE_TOKEN}` }
        });
      }
      if (r.ok) out.push(await r.json());
    } catch (e) { /* skip unreadable blob */ }
  }
  return out;
}

export default async function handler(req, res) {
  if (req.method === 'POST') {
    const b = req.body || {};
    // Honeypot: bots fill every field, this one is invisible to people.
    if (b.website) return res.status(200).json({ ok: true });

    const email = String(b.email ?? '').trim().slice(0, 160).toLowerCase();
    if (!LOOKS_LIKE_EMAIL.test(email)) {
      return res.status(400).json({ ok: false, error: 'email' });
    }

    const sub = {
      at: new Date().toISOString(),
      email,
      page: String(b.page ?? '').trim().slice(0, 80) || 'unknown',
      ua: String(req.headers['user-agent'] ?? '').slice(0, 200)
    };

    try {
      // One blob per address, so signing up twice overwrites rather than
      // adding a duplicate. The key is the address, url-safe.
      const id = Buffer.from(email).toString('base64url');
      await put(`subs/${id}.json`, JSON.stringify(sub, null, 2), {
        access: 'private',
        contentType: 'application/json',
        allowOverwrite: true
      });
      return res.status(200).json({ ok: true });
    } catch (err) {
      console.error('subscribe store failed:', err);
      return res.status(500).json({ ok: false, error: 'store' });
    }
  }

  if (req.method === 'GET') {
    const key = req.query.key || '';
    if (!process.env.LEADS_KEY || key !== process.env.LEADS_KEY) {
      return res.status(404).send('Not found');
    }
    try {
      const subs = await allSubs();
      res.setHeader('X-Robots-Tag', 'noindex');
      if (req.query.format === 'json') {
        return res.status(200).json({ count: subs.length, subs });
      }
      if (req.query.format === 'csv') {
        const stamp = new Date().toISOString().slice(0, 10);
        res.setHeader('Content-Type', 'text/csv; charset=utf-8');
        res.setHeader('Content-Disposition',
          `attachment; filename="slow-thought-subscribers-${stamp}.csv"`);
        return res.status(200).send(toCsv(subs));
      }
      const rows = subs.map(s => `<tr>
        <td>${esc((s.at || '').replace('T', ' ').slice(0, 16))}</td>
        <td><strong>${esc(s.email)}</strong></td>
        <td>${esc(s.page)}</td></tr>`).join('');
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      return res.status(200).send(`<!doctype html><html><head><meta charset="utf-8">
        <title>Slow Thought (${subs.length})</title><meta name="robots" content="noindex">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>body{font-family:-apple-system,system-ui,sans-serif;margin:24px;color:#1A1813;background:#FCFBF8}
        h1{font-size:20px} table{border-collapse:collapse;width:100%;font-size:13px}
        th,td{border-bottom:1px solid #E1DDD1;padding:8px 10px;text-align:left;vertical-align:top}
        th{background:#F6F4EE;position:sticky;top:0}</style></head>
        <body><h1>Slow Thought subscribers &middot; ${subs.length}</h1>
        <p style="margin:-6px 0 18px">
          <a href="?key=${encodeURIComponent(key)}&amp;format=csv" style="display:inline-block;background:#1A1813;color:#FCFBF8;font-weight:700;font-size:13px;padding:9px 16px;border-radius:99px;text-decoration:none">Download CSV</a>
          <a href="?key=${encodeURIComponent(key)}&amp;format=json" style="margin-left:10px;font-size:13px;color:#57534A">or JSON</a></p>
        <table><tr><th>When (UTC)</th><th>Email</th><th>Signed up from</th></tr>${rows}</table>
        </body></html>`);
    } catch (err) {
      console.error('subscriber list failed:', err);
      return res.status(500).send('Error listing subscribers');
    }
  }

  res.setHeader('Allow', 'GET, POST');
  return res.status(405).json({ ok: false, error: 'method' });
}
