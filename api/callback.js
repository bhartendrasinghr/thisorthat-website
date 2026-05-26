// Step 2 of GitHub OAuth flow for Decap CMS.
// GitHub redirects here with ?code=...
// We exchange the code for an access token, then render an HTML page
// that posts the token back to the Decap CMS window via postMessage.

export default async function handler(req, res) {
  const { code, error: ghError } = req.query;
  const clientId = process.env.GITHUB_CLIENT_ID;
  const clientSecret = process.env.GITHUB_CLIENT_SECRET;

  if (ghError) return renderPopupResponse(res, 'error', { message: ghError });
  if (!code) return renderPopupResponse(res, 'error', { message: 'No code returned from GitHub' });
  if (!clientId || !clientSecret) {
    return renderPopupResponse(res, 'error', {
      message: 'GITHUB_CLIENT_ID or GITHUB_CLIENT_SECRET not set in Vercel env vars',
    });
  }

  try {
    const tokenRes = await fetch('https://github.com/login/oauth/access_token', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'User-Agent': 'thisorthat-cms',
      },
      body: JSON.stringify({
        client_id: clientId,
        client_secret: clientSecret,
        code,
      }),
    });

    const data = await tokenRes.json();

    if (data.error || !data.access_token) {
      return renderPopupResponse(res, 'error', {
        message: data.error_description || data.error || 'Token exchange failed',
      });
    }

    return renderPopupResponse(res, 'success', {
      token: data.access_token,
      provider: 'github',
    });
  } catch (err) {
    return renderPopupResponse(res, 'error', { message: String(err.message || err) });
  }
}

// Decap CMS expects an HTML page that does:
//   window.opener.postMessage('authorization:github:success:{...}', '*')
// then closes itself.
function renderPopupResponse(res, status, payload) {
  const message = `authorization:github:${status}:${JSON.stringify(payload)}`;
  const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Authorising…</title></head>
<body style="font-family:system-ui;padding:40px;text-align:center;color:#0A0E3D;background:#FAF7F0">
<p>Finishing sign-in…</p>
<script>
(function() {
  function send() {
    if (!window.opener) {
      document.body.innerHTML = '<p style="color:#D32F2F">No opener window — please close and try again.</p>';
      return;
    }
    window.opener.postMessage(${JSON.stringify(message)}, '*');
    setTimeout(function(){ window.close(); }, 500);
  }
  // Decap listens for this handshake first:
  window.addEventListener('message', function(e) {
    if (e.data === 'authorizing:github') send();
  }, false);
  // Some Decap versions just expect us to send immediately:
  send();
})();
</script>
</body></html>`;
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.status(200).send(html);
}
