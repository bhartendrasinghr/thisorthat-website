// Hit daily by Vercel Cron (see vercel.json). Triggers a fresh production
// deploy via a Deploy Hook, which re-runs build.py → sync.py and picks up
// any new YouTube episodes.
export default async function handler(req, res) {
  const url = process.env.DEPLOY_HOOK_URL;
  if (!url) {
    return res.status(500).json({ ok: false, error: 'DEPLOY_HOOK_URL not set' });
  }
  try {
    const r = await fetch(url, { method: 'POST' });
    const body = await r.text();
    return res.status(r.ok ? 200 : 502).json({ ok: r.ok, status: r.status, body: body.slice(0, 400) });
  } catch (err) {
    return res.status(500).json({ ok: false, error: String(err) });
  }
}
