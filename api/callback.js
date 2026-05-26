// Step 2 of GitHub OAuth flow for Decap CMS.
// GitHub redirects here with ?code=...
// We exchange the code for an access token, then post it back to the
// Decap CMS window using the handshake protocol.

export default async function handler(req, res) {
  const { code, error: ghError, error_description } = req.query;
  const clientId = process.env.GITHUB_CLIENT_ID;
  const clientSecret = process.env.GITHUB_CLIENT_SECRET;

  if (ghError) {
    return renderPopupResponse(res, 'error', {
      message: `GitHub: ${ghError} — ${error_description || ''}`,
    });
  }
  if (!code) {
    return renderPopupResponse(res, 'error', {
      message: 'No code returned from GitHub',
    });
  }
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
    return renderPopupResponse(res, 'error', {
      message: String(err.message || err),
    });
  }
}

// Decap CMS handshake protocol:
//   1. Popup loads this page
//   2. Decap (parent) polls the popup with `authorizing:github` every 500ms
//   3. We listen for that message; when it arrives, we respond with
//      `authorization:github:success:{...json...}`
//   4. Decap parses the response, calls its onAuth callback, and closes the popup
function renderPopupResponse(res, status, payload) {
  const message = `authorization:github:${status}:${JSON.stringify(payload)}`;
  const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Authorising…</title>
<style>
  body{font-family:system-ui,-apple-system,sans-serif;padding:40px;text-align:center;color:#0A0E3D;background:#FAF7F0;max-width:560px;margin:0 auto}
  h1{font-size:24px;margin:0 0 12px}
  p{margin:8px 0;line-height:1.5}
  .ok{color:#1A237E}
  .err{color:#D32F2F}
  pre{background:#fff;padding:12px;border-radius:8px;text-align:left;font-size:12px;overflow:auto;border:1px solid #ddd}
  .small{font-size:12px;color:#666;margin-top:24px}
</style>
</head>
<body>
<h1 class="${status === 'success' ? 'ok' : 'err'}">${status === 'success' ? '✓ Signed in to GitHub' : '✗ Sign-in failed'}</h1>
<p>${status === 'success' ? 'Returning you to the editor…' : 'Details below. Close this window and try again.'}</p>
${status !== 'success' ? `<pre>${JSON.stringify(payload, null, 2)}</pre>` : ''}
<p id="status-line" class="small">Waiting for Decap CMS to acknowledge…</p>
<script>
(function() {
  var message = ${JSON.stringify(message)};
  var sent = false;
  var statusLine = document.getElementById('status-line');

  function send(reason) {
    if (!window.opener) {
      statusLine.textContent = '✗ No opener window. Close this and try again from /admin.';
      return;
    }
    sent = true;
    window.opener.postMessage(message, '*');
    statusLine.textContent = '✓ Token sent to editor (' + reason + '). This window should close.';
  }

  // 1. Listen for the handshake from Decap
  window.addEventListener('message', function(e) {
    if (e.data === 'authorizing:github' || (typeof e.data === 'string' && e.data.indexOf('authorizing:github') === 0)) {
      send('handshake received');
    }
  }, false);

  // 2. Also send immediately in case Decap isn't using the handshake (newer Decap versions)
  setTimeout(function(){ send('immediate'); }, 100);

  // 3. Re-send a few times in case parent is slow to listen
  var attempts = 0;
  var retry = setInterval(function() {
    attempts++;
    if (attempts > 10 || !window.opener) { clearInterval(retry); return; }
    send('retry ' + attempts);
  }, 300);

  // Don't auto-close — let Decap close us, or let the user close after seeing an error
})();
</script>
</body></html>`;
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.status(200).send(html);
}
