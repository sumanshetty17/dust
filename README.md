# SiteBot: AI chatbot for any company website

**How customers use it:** sign up → paste their website URL → the bot reads the whole site (sitemap, pages, contact info, business details) → copy one line of code into their website. Re-upload all project files to GitHub after updates; Vercel redeploys automatically.


Visitors get an AI assistant trained on the company's own content. Owners get a dashboard showing what customers
struggle with, plus an email assistant that triages and drafts replies.

## Deploy (GitHub → Vercel), about 10 minutes

### 1. Push to GitHub
    git init && git add . && git commit -m "SiteBot"
    git branch -M main
    # create an EMPTY repo on github.com first, then:
    git remote add origin https://github.com/<you>/sitebot.git
    git push -u origin main

### 2. Import into Vercel
vercel.com → Add New → Project → pick the repo → Deploy (zero-config; Vercel detects FastAPI from `main.py`).

### 3. Add a database (required: Vercel has no persistent disk)
Project → Storage → Create Database → **Neon (Postgres)** → connect to the project. This injects `DATABASE_URL`.
Tables are created automatically on first request.

### 4. Environment variables (Project → Settings → Environment Variables)
| Name | Value |
|---|---|
| `GEMINI_API_KEY` | FREE key from aistudio.google.com/apikey (no card needed) |
| `ANTHROPIC_API_KEY` | optional paid alternative; used instead of Gemini if set |
| `CLAUDE_MODEL` | `claude-sonnet-5-5` (optional) |
| `DAILY_CHAT_LIMIT` | max chats per bot per day, default 500 (protects your API bill) |
| `MAX_BOTS_PER_USER` | default 3 |
| `ALERT_WEBHOOK` | optional Slack/Discord webhook for urgent emails |

Redeploy after adding variables. Check `https://<your-app>.vercel.app/api/health`: it should say `"db":"postgres"`.

### 5. Use it
Open your Vercel URL → sign up → create a bot → crawl a site/upload docs → copy the snippet into any website:

    <script src="https://<your-app>.vercel.app/widget.js" data-key="pk_..." data-title="Chat with us"></script>

Optional attributes: `data-color="#16a34a"`, `data-greeting="Hi!"`.

## Local dev
    pip install -r requirements.txt && uvicorn main:app --reload   # uses SQLite if DATABASE_URL is unset

## Known limits (next steps)
- Crawl runs inside one request (≤60s, ≤25 pages). Move to a queue/worker for big sites.
- BM25 keyword retrieval; upgrade to pgvector + embeddings for better recall.
- Email assistant works on submitted emails; Gmail OAuth (+Google security review) is next. Replies are drafted, not sent.
- Add email verification, password reset, per-domain widget allow-list, and billing before public launch.

## Navigation features (visitor asks "where is X?")
- Crawler learns menu/header/footer links, including icon-only ones (aria-label/title/alt).
- Owner adds a **Site guide** (directions for logged-in areas or anything not crawlable); stored per bot, survives re-crawls.
- Answers carry validated **➡ buttons** (server only returns allow-listed pages/guide entries, never AI-invented URLs).
- Widget: button navigates to the page, keeps the chat open across pages (sessionStorage), then scrolls to and highlights the matching link/button. If the item sits in a collapsed menu it says so.
- Optional highlight target in a guide entry: visible text ("Settings") or a CSS selector ("#settings-btn").

## v3 features
- **Human handoff:** when the bot can't answer, the widget offers a contact form; leads appear in the dashboard (and go to ALERT_WEBHOOK if set).
- **Feedback:** 👍/👎 on every answer; dashboard shows totals and the answers marked unhelpful.
- **Customize:** title, colour, greeting set in the dashboard; widget fetches them live (no re-pasting code).
- **Website lock:** optional; chat/lead/feedback endpoints only accept requests from the customer's own domain(s). (Origin header check: deters casual copying; not a hard security boundary.)
- **Verify installation:** server fetches the customer's site and looks for the bot key.
Existing databases are migrated automatically on first start.

## Gmail email assistant (real inbox)
Owner clicks **Connect Gmail** → Google consent → the bot checks unread inbox mail (last 2 days), skips newsletters/no-reply/auto mail, and for each real customer email:
- **routine & answerable from the knowledge base** → writes a tailored reply. Draft mode: saved as a Gmail draft in the same thread (owner clicks *Send this reply* in the dashboard or in Gmail). Auto mode: sent immediately.
- **urgent / needs a person** → never answered; labelled `SiteBot/Needs you` (+ optional ALERT_WEBHOOK).
Safety: max 1 auto-reply per sender per 24 h (then a draft instead), daily auto-reply cap (`GMAIL_DAILY_AUTO_LIMIT`, default 30), `Auto-Submitted` header, AI disclosure footer (`EMAIL_FOOTER` to change), refresh tokens encrypted at rest.

### One-time Google setup (you, the platform owner)
1. console.cloud.google.com → create a project → **APIs & Services → Library → Gmail API → Enable**.
2. **OAuth consent screen** → User type *External* → fill app name/support email → **Scopes: add `.../auth/gmail.modify`** → keep *Testing* and add each Gmail address that will connect under **Test users** (max 100).
3. **Credentials → Create credentials → OAuth client ID → Web application** → Authorized redirect URI: `https://YOUR-APP.vercel.app/api/gmail/callback` (exactly).
4. In Vercel add env vars: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `APP_URL=https://YOUR-APP.vercel.app`, `CRON_SECRET=<any long random string>`; redeploy.
5. Dashboard → Email assistant → **Connect Gmail**.

Notes: in *Testing* mode Google expires connections after ~7 days (owners just click Connect again). Offering this to the public requires Google's OAuth verification (+ a security assessment for Gmail scopes). The dashboard auto-checks every 3 min while open; Vercel Cron checks daily (Hobby limit); for every-5-minute checks point a free pinger (e.g. cron-job.org) at `https://YOUR-APP.vercel.app/api/cron/gmail?secret=<CRON_SECRET>`.

## Deep reading for JavaScript-heavy sites (optional Reader service)
The built-in crawler reads normal HTML sites on Vercel. Sites that build their pages with JavaScript (React/Vue/SPA) need a real browser, which can't run on Vercel, so a separate **SiteBot Reader** service (see the `sitebot-reader` project) does that work. Set in Vercel: `READER_URL=https://YOUR-READER.onrender.com` and `READER_KEY=<same secret as the reader>`, then redeploy.
- Creating a bot from a URL automatically hands over to the Reader when the plain crawl finds almost no text.
- The dashboard also gets a **Deep read (JavaScript sites)** button; progress is shown live and the result feeds the same knowledge base (pages, menus, contacts).
- Only public pages are read. Pages behind a login are never read (see sitebot-reader/README.md for why).

## Automatic re-learning (keeps answers fresh)
- Each bot has **Keep it up to date automatically: every week / every day / off** (default weekly) in the dashboard.
- A scheduled job re-reads due websites. It compares each page with what the bot already knows: **unchanged pages are left alone** (no AI re-indexing), changed and new pages are rewritten, and a page that disappears is only forgotten after 3 weeks of not being found, so one failed crawl never erases knowledge. If the site can't be read, the old knowledge is kept and the dashboard says so.
- Sites that needed the browser Reader are refreshed through it **in the background**: the Reader posts the finished result back to `/api/reader/callback` (signed per bot with `READER_KEY`), so nothing has to wait for the 60-second Vercel limit.
- Scheduling: `vercel.json` runs `/api/cron/daily` once a day (Vercel Hobby allows daily crons): it refreshes due websites, then checks Gmail inboxes. It needs `CRON_SECRET` in Vercel (Vercel sends it automatically). For more frequent runs point a free pinger (e.g. cron-job.org) at `https://YOUR-APP.vercel.app/api/cron/relearn?secret=<CRON_SECRET>` (hourly is plenty; bots are only touched when due; at most 3 per run).
