# ThisOrThat with Bhartendra — Website

A media-brand website for the podcast. Static site, free hosting, full content editing via web UI.

## What's in this repo

| File / Folder | Purpose |
|---|---|
| `index.html`, `episodes.html`, `articles.html`, etc. | The actual pages |
| `episodes.js` | Auto-generated list of episodes (from YouTube) |
| `content/articles/*.md` | Articles — edit these in `/admin` |
| `content/site.json` | All editable page text (hero, about, links) |
| `admin/` | Decap CMS — your web-based content editor |
| `sync.py` | Pulls latest episodes from your YouTube channel |
| `build.py` | Compiles articles + runs sync. Runs on every deploy |
| `netlify.toml` | Hosting config |
| `logo.png` | Your channel logo |

## Going live — 4 one-time steps

You only do this once. After that, editing content takes 30 seconds.

### Step 1 — Push to GitHub (5 min)

If you don't have a GitHub account, create one at https://github.com (free).

```bash
cd thisorthat-website
git add .
git commit -m "Initial commit"
# Create a new repo on github.com (call it 'thisorthat-website'), then:
git remote add origin https://github.com/YOUR-USERNAME/thisorthat-website.git
git branch -M main
git push -u origin main
```

### Step 2 — Connect to Netlify (3 min)

1. Sign up at https://app.netlify.com (free, use GitHub login)
2. Click **Add new site → Import an existing project**
3. Choose **GitHub**, authorize, and pick your `thisorthat-website` repo
4. Leave defaults (it reads `netlify.toml` automatically). Click **Deploy site**
5. Wait ~60 seconds. You'll get a URL like `https://random-name.netlify.app`

### Step 3 — Turn on the CMS editor (3 min)

This is what lets you edit content via web UI instead of code.

1. In your Netlify site dashboard → **Site configuration → Identity** → click **Enable Identity**
2. Under **Registration**, change to **Invite only** (so randoms can't sign up)
3. Under **Identity → Services**, scroll to **Git Gateway** → click **Enable Git Gateway**
4. Click **Invite users** at the top, enter your email, send invite
5. Check your email, click the invite link, set a password

Now visit `https://YOUR-SITE.netlify.app/admin/` — log in with the email/password you just set, and you can edit articles, page text, etc. Every save commits to GitHub and re-deploys the site automatically (takes ~60 seconds).

### Step 4 — Custom domain (10 min, optional but recommended)

1. Buy `thisorthat.in` (or whatever) from any registrar — Namecheap, Cloudflare, GoDaddy. ~₹800/year
2. In Netlify → **Domain settings → Add a domain** → enter your domain
3. Netlify gives you DNS records — copy them into your registrar's DNS settings
4. Wait 15 min to a few hours for DNS to propagate
5. Netlify auto-issues a free HTTPS certificate

Done. You now have `https://thisorthat.in` (or whatever) with full editing via `/admin`.

## Daily use — adding content

### Add a new article
1. Visit `https://your-site.com/admin/`
2. Log in
3. Click **Articles → New Article**
4. Fill in title, body, etc. → Publish
5. Site rebuilds in 60 seconds, article goes live

### Edit page text (hero, about, etc.)
1. `/admin/` → **Site Settings → Brand & Social Links**
2. Edit any field → Publish

### Add a new podcast episode
You don't need to. Episodes auto-sync from your YouTube channel.
- Either: wait — `build.py` runs `sync.py` on every deploy, so it refreshes every time you publish an article or edit text.
- Or: manually trigger by running `python3 sync.py` locally + push, or hit **Trigger deploy** in Netlify.

### Override a guest name or category for an auto-synced episode
1. `/admin/` → **Episode Overrides → Episode metadata overrides**
2. Add an entry with the YouTube video ID and the override

## Local development

To preview changes before pushing:

```bash
cd thisorthat-website
python3 build.py             # compile articles + sync episodes
python3 -m http.server 8000  # serve locally
open http://localhost:8000
```

To use the CMS locally without auth:
```bash
npx decap-server &           # in one terminal
python3 -m http.server 8000  # in another
# Visit http://localhost:8000/admin/
```

## Costs

| Item | Cost |
|---|---|
| Netlify hosting (free tier) | ₹0 |
| GitHub repo | ₹0 |
| Decap CMS | ₹0 |
| Custom domain (optional) | ~₹800/year |
| **Total to launch** | **₹0** (or ₹800/year with domain) |

Free tier limits: 100GB bandwidth/month, 300 build minutes/month. You'll outgrow none of this for years.

## Architecture notes

- **Static site.** Every page is plain HTML loaded by the browser. No server runtime.
- **YouTube videos** stay on YouTube — embedded via iframe. They count against YouTube's bandwidth, not yours.
- **Episodes** are scraped from your channel's public video list. No YouTube API key needed.
- **Content** is stored as files in git. Decap CMS edits commit to GitHub, which triggers a Netlify rebuild. Everything is versioned and revertible.

## Future moves

When the site outgrows this setup (likely never, but if):
- Add a search box (Algolia / Pagefind — both free tiers)
- Add analytics (Plausible — privacy-friendly, ~$9/mo)
- Add newsletter signup (Buttondown / Beehiiv — free tiers)
- Migrate to Next.js + Sanity if you need user accounts, comments, paid content
