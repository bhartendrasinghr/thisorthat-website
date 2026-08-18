// Lead capture for money-person.html ("Talk to a human").
// POST: stores the lead as a JSON blob in the private thisorthat-leads store.
// GET ?key=<LEADS_KEY>: renders all captured leads (newest first) for Bhartendra.
import { put, list } from '@vercel/blob';

// Email the lead the moment it lands. Storing it is not enough: a lead nobody
// sees is somebody's money question going unanswered. Sending must never be able
// to lose a lead, so it happens after the blob is written and every failure is
// swallowed and logged.
async function emailLead(lead) {
  const keyR = process.env.RESEND_API_KEY;
  const to = process.env.LEAD_EMAIL_TO;
  if (!keyR || !to) return { sent: false, why: 'not configured' };

  const row = (k, v) => v ? `<tr><td style="padding:6px 14px 6px 0;color:#7A7368;white-space:nowrap;vertical-align:top">${k}</td><td style="padding:6px 0;color:#1A1813"><strong>${esc(v)}</strong></td></tr>` : '';
  const html = `<div style="font-family:-apple-system,system-ui,sans-serif;max-width:560px">
    <p style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#8F6600;font-weight:800;margin:0 0 6px">New lead, talk to a human</p>
    <h2 style="font-size:22px;margin:0 0 14px;color:#1A1813">${esc(lead.name)}${lead.age ? ', ' + esc(lead.age) : ''}</h2>
    <table style="font-size:14px;border-collapse:collapse">
      ${row('Email', lead.email)}${row('Phone', lead.phone)}
      ${row('Wants intro to', lead.advisor || 'No preference, wants a suggestion')}
      ${row('Looking for', (lead.types || []).join(', '))}
    </table>
    ${lead.goals ? `<p style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#7A7368;font-weight:800;margin:20px 0 6px">In their words</p>
      <div style="background:#F6F4EE;border-left:4px solid #FFC21F;padding:14px 16px;font-size:15px;line-height:1.6;color:#2C2A23;white-space:pre-wrap">${esc(lead.goals)}</div>` : ''}
    <p style="font-size:12px;color:#9A9284;margin-top:22px">${esc(lead.at)} UTC &middot; from /${esc(lead.page)}</p>
  </div>`;

  try {
    const r = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${keyR}` },
      body: JSON.stringify({
        from: process.env.LEAD_EMAIL_FROM || 'ThisOrThat <onboarding@resend.dev>',
        to: to.split(',').map(x => x.trim()).filter(Boolean),
        reply_to: lead.email || undefined,
        subject: `New lead: ${lead.name}${lead.advisor ? ' wants ' + lead.advisor : ''}`,
        html
      })
    });
    if (!r.ok) { console.error('lead email failed', r.status, (await r.text()).slice(0, 300)); return { sent: false, why: 'upstream' }; }
    return { sent: true };
  } catch (e) {
    console.error('lead email threw', e);
    return { sent: false, why: 'threw' };
  }
}

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
      // stored, so the lead is safe whatever the mail server does next
      const mail = await emailLead(lead);
      return res.status(200).json({ ok: true, emailed: mail.sent });
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

      // Download. Excel and Numbers both want a BOM or they mangle rupee signs
      // and Devanagari, and goals are free text so every field gets quoted.
      if (req.query.format === 'csv') {
        const cell = (v) => '"' + String(v ?? '').replace(/"/g, '""') + '"';
        const head = ['When (UTC)', 'Name', 'Age', 'Email', 'Phone', 'Wants intro to', 'Looking for', 'Goals', 'Page'];
        const body = leads.map(l => [
          (l.at || '').replace('T', ' ').slice(0, 19),
          l.name, l.age, l.email, l.phone,
          l.advisor || 'no preference',
          (l.types || []).join('; '),
          l.goals, l.page
        ].map(cell).join(','));
        const stamp = new Date().toISOString().slice(0, 10);
        res.setHeader('Content-Type', 'text/csv; charset=utf-8');
        res.setHeader('Content-Disposition', `attachment; filename="thisorthat-leads-${stamp}.csv"`);
        res.setHeader('X-Robots-Tag', 'noindex');
        return res.status(200).send('\uFEFF' + [head.map(cell).join(','), ...body].join('\r\n'));
      }
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
        <p style="margin:-6px 0 18px">
          <a href="?key=${encodeURIComponent(key)}&amp;format=csv" style="display:inline-block;background:#1A1813;color:#FCFBF8;font-weight:700;font-size:13px;padding:9px 16px;border-radius:99px;text-decoration:none">Download CSV</a>
          <a href="?key=${encodeURIComponent(key)}&amp;format=json" style="margin-left:10px;font-size:13px;color:#57534A">or JSON</a>
        </p>
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
