// Step 1 of GitHub OAuth flow for Decap CMS.
// Decap opens this URL in a popup. We redirect to GitHub's authorize endpoint.

export default function handler(req, res) {
  const clientId = process.env.GITHUB_CLIENT_ID;
  if (!clientId) {
    return res
      .status(500)
      .send('GITHUB_CLIENT_ID env var not set in Vercel project settings');
  }

  const host = req.headers['x-forwarded-host'] || req.headers.host;
  const protocol = req.headers['x-forwarded-proto'] || 'https';
  const redirectUri = `${protocol}://${host}/api/callback`;

  // Decap passes a `state` param we should echo back through GitHub
  const state = (req.query.state || Math.random().toString(36).slice(2)).toString();

  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    scope: 'repo,user',
    state,
    allow_signup: 'false',
  });

  res.setHeader('Location', `https://github.com/login/oauth/authorize?${params}`);
  res.status(302).end();
}
