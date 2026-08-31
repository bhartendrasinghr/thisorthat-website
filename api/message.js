// Contact messages from the "Write to me" form on about.html.
//
// Separate from api/lead.js on purpose. A lead is somebody asking to be
// introduced to an adviser, and those are stored and exported as one CSV.
// A message is just somebody writing to Bhartendra, and mixing the two would
// quietly corrupt that spreadsheet.
//
// Reuses the same RESEND_API_KEY and LEAD_EMAIL_TO that the lead form already
// runs on, so there is nothing new to configure.
import { put } from '@vercel/blob';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const clip = (v, n) => (typeof v === 'string' ? v.trim().slice(0, n) : '');

async function sendMessage(m) {
  const key = process.env.RESEND_API_KEY;
  const to = process.env.LEAD_EMAIL_TO;
  if (!key || !to) return { sent: false, why: 'not configured' };

  const html = `<div style="font-family:-apple-system,system-ui,sans-serif;max-width:560px">
    <p style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#8F6600;font-weight:800;margin:0 0 6px">Message from the website</p>
    <h2 style="font-size:22px;margin:0 0 4px;color:#1A1813">${esc(m.subject)}</h2>
    <p style="font-size:14px;color:#57534A;margin:0 0 18px">
      from <strong style="color:#1A1813">${esc(m.name)}</strong>
      &lt;<a href="mailto:${esc(m.email)}" style="color:#0249B1">${esc(m.email)}</a>&gt;
    </p>
    <div style="background:#F6F4EE;border-left:4px solid #FFC21F;padding:16px 18px;font-size:15px;line-height:1.65;color:#2C2A23;white-space:pre-wrap">${esc(m.message)}</div>
    <p style="font-size:13px;color:#57534A;margin-top:22px;padding-top:16px;border-top:1px solid #E1DDD1">
      Hit reply and it goes straight back to them.</p>
    <p style="font-size:12px;color:#9A9284;margin-top:10px">${esc(m.at)} UTC &middot; from /${esc(m.page)}</p>
  </div>`;

  try {
    const r = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${key}` },
      body: JSON.stringify({
        from: process.env.LEAD_EMAIL_FROM || 'ThisOrThat <onboarding@resend.dev>',
        to: to.split(',').map(x => x.trim()).filter(Boolean),
        reply_to: m.email,
        subject: `Website message: ${m.subject}`,
        html
      })
    });
    if (!r.ok) {
      console.error('message email failed', r.status, (await r.text()).slice(0, 300));
      return { sent: false, why: 'upstream' };
    }
    return { sent: true };
  } catch (e) {
    console.error('message email threw', e);
    return { sent: false, why: 'threw' };
  }
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ ok: false, error: 'method' });

  const b = req.body || {};
  // honeypot: bots fill every field, humans never see this one
  if (b.website) return res.status(200).json({ ok: true });

  const m = {
    at: new Date().toISOString(),
    name: clip(b.name, 120),
    email: clip(b.email, 160),
    subject: clip(b.subject, 200),
    message: clip(b.message, 5000),
    page: clip(b.page, 60) || 'about',
    ua: clip(req.headers['user-agent'], 200)
  };

  if (!m.name) return res.status(400).json({ ok: false, error: 'name' });
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(m.email)) return res.status(400).json({ ok: false, error: 'email' });
  if (!m.subject) return res.status(400).json({ ok: false, error: 'subject' });
  if (m.message.length < 2) return res.status(400).json({ ok: false, error: 'message' });

  // Store first, then send. A message nobody sees is somebody who wrote in and
  // got silence, so it must survive Resend having a bad day.
  try {
    const stamp = m.at.replace(/[:.]/g, '-');
    await put(`messages/${stamp}.json`, JSON.stringify(m, null, 2), {
      access: 'private',
      contentType: 'application/json'
    });
  } catch (e) {
    console.error('message store failed, still trying to send', e);
  }

  const mail = await sendMessage(m);
  if (!mail.sent) return res.status(502).json({ ok: false, error: 'send' });
  return res.status(200).json({ ok: true });
}
