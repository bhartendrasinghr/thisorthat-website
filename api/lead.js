// Lead capture for money-person.html ("Talk to a human").
// POST: stores the lead as a JSON blob in the private thisorthat-leads store.
// GET ?key=<LEADS_KEY>: renders all captured leads (newest first) for Bhartendra.
import { put, list } from '@vercel/blob';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const clip = (v, n) => (typeof v === 'string' ? v.trim().slice(0, n) : '');

export default async function handler(req, res) {
  if (req.method === 'POST') {
    const b = req.body || {};
    // honeypot: bots fill every field; humans never see this one
    if (b.website) return res.status(200).json({ ok: true });

    const lead = {
      at: new Date().toISOString(),
      name: clip(b.name, 120),
      age: clip(b.age, 12),
      email: clip(b.email, 160),
      phone: clip(b.phone, 30),
      types: Array.isArray(b.types) ? b.types.slice(0, 12).map(t => clip(t, 60)) : [],
      goals: clip(b.goals, 3000),
      advisor: clip(b.advisor, 120),
      page: clip(b.page, 60) || 'money-person',
      ua: clip(req.headers['user-agent'], 200)
    };
    if (!lead.name) return res.status(400).json({ ok: false, error: 'name' });
    if (!lead.email && !lead.phone) return res.status(400).json({ ok: false, error: 'contact' });
    if (b.consent !== true) return res.status(400).json({ ok: false, error: 'consent' });

    try {
      const stamp = lead.at.replace(/[:.]/g, '-');
      await put(`leads/${stamp}.json`, JSON.stringify(lead, null, 2), {
        access: 'private',
        contentType: 'application/json'
      });
      return res.status(200).json({ ok: true });
    } catch (err) {
      console.error('lead store failed:', err);
      return res.status(500).json({ ok: false, error: 'store' });
    }
  }

  if (req.method === 'GET') {
    const key = req.query.key || '';
    if (!process.env.LEADS_KEY || key !== process.env.LEADS_KEY) {
      return res.status(404).send('Not found');
    }
    try {
      const { blobs } = await list({ prefix: 'leads/', limit: 1000 });
      blobs.sort((a, b2) => (a.pathname < b2.pathname ? 1 : -1)); // newest first
      const leads = [];
      for (const b of blobs) {
        try {
          let r = await fetch(b.downloadUrl || b.url);
          if (!r.ok) r = await fetch(b.url, { headers: { authorization: `Bearer ${process.env.BLOB_READ_WRITE_TOKEN}` } });
          if (r.ok) leads.push(await r.json());
        } catch (e) { /* skip unreadable blob */ }
      }
      if (req.query.format === 'json') return res.status(200).json({ count: leads.length, leads });
      const rows = leads.map(l => `
        <tr>
          <td>${esc((l.at || '').replace('T', ' ').slice(0, 16))}</td>
          <td><strong>${esc(l.name)}</strong>${l.age ? ', ' + esc(l.age) : ''}</td>
          <td>${esc(l.email)}${l.email && l.phone ? '<br>' : ''}${esc(l.phone)}</td>
          <td>${esc(l.advisor) || '<span style="color:#999">no preference</span>'}</td>
          <td>${esc((l.types || []).join(', '))}</td>
          <td style="max-width:340px">${esc(l.goals)}</td>
        </tr>`).join('');
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      res.setHeader('X-Robots-Tag', 'noindex');
      return res.status(200).send(`<!doctype html><html><head><meta charset="utf-8"><title>Leads (${leads.length})</title>
        <meta name="robots" content="noindex"><meta name="viewport" content="width=device-width, initial-scale=1">
        <style>body{font-family:-apple-system,system-ui,sans-serif;margin:24px;color:#1A1813;background:#FCFBF8}
        h1{font-size:20px} table{border-collapse:collapse;width:100%;font-size:13px}
        th,td{border-bottom:1px solid #E1DDD1;padding:8px 10px;text-align:left;vertical-align:top}
        th{background:#F6F4EE;position:sticky;top:0}</style></head>
        <body><h1>Talk-to-a-human leads &middot; ${leads.length}</h1>
        <table><tr><th>When (UTC)</th><th>Who</th><th>Contact</th><th>Wants intro to</th><th>Looking for</th><th>Goals</th></tr>${rows}</table>
        </body></html>`);
    } catch (err) {
      console.error('lead list failed:', err);
      return res.status(500).send('Error listing leads');
    }
  }

  res.setHeader('Allow', 'GET, POST');
  return res.status(405).json({ ok: false, error: 'method' });
}
