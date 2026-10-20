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

## Automatic site map (the assistant knows where everything is)
When a website is learned (plain crawl, Reader, or scheduled re-learn) SiteBot builds a map of **where things are** and stores it in `navlinks`:
- **menu** links (nav/header/footer), **page** (every crawled page + title), **link** (any other internal link with a readable label, including menus built from plain `<div>`s and icon-only links via aria-label/title/alt; generic labels like "Read more" are skipped),
- **tool** (buttons, tabs, toggles with where they sit: "button in the header of …"),
- **route** (app pages such as /settings or /billing found by reading the site's own JavaScript files. Only names/paths are read, never page content, and they are marked "may need login").
For each question the assistant is offered the most relevant destinations (ranked by overlap with the question, max 70), answers with a ➡ button, and the widget opens the page and highlights the button/link. The owner can still add directions by hand (Site guide) for anything not discoverable. The dashboard shows what was found ("Show site map").

## Reliability on real-world websites
Real sites contain broken links (`https://[object Object]`, impossible ports, spaces in hosts), hidden NUL characters (Postgres rejects them), huge or deeply nested pages and malformed sitemaps. The crawler ignores malformed links instead of failing, skips any page it cannot parse, strips NUL characters before storing text, leaves headroom under Vercel's 60 s limit, and every server error is returned as readable JSON (the traceback goes to the Vercel logs). `test_nasty.py` / `test_reader_nasty.py` reproduce all of this.
If you still see an error: Vercel → your project → **Logs** → open the failing request → the Python traceback shows the cause.

## Free for now: no limits
There is no cap on assistants per user and no daily chat cap. To bring limits back for paid plans later set `MAX_BOTS_PER_USER` and `DAILY_CHAT_LIMIT` in Vercel (0 = unlimited). Reading the same website again reuses the existing assistant (failed attempts no longer pile up) and the dashboard has **Delete this assistant**.

## Reads the whole website
Up to `MAX_PAGES` (default 300) pages per reading pass, 16 in parallel. If a site has more, or time runs out (Vercel allows ~60 s per request), the rest of the queue is saved and the dashboard keeps reading automatically ("Read N pages so far…") until the whole site is learned. Knowledge cap per assistant: `MAX_CHUNKS` (default 4000 text sections). Search is indexed once per assistant and reused, so answers stay fast on big sites. After reading, the dashboard shows "Teaching the AI… x/y" while embeddings are created (a few minutes for very large sites on the free AI tier).

## Directions
Every link remembers where it was seen (top header, navigation menu, footer, side menu, page content, or a button in a given place). Answers to "where is X?" give a short direction ("in the footer at the bottom of the page, seen on the Home page") plus a ➡ button that opens the page and highlights the link.

## Answer quality (v5)
- **AI health check**: the dashboard shows a red banner when the AI model or smart search isn't working, with the reason (e.g. "Gemini 400: API key not valid") and the fix. `GET /api/ai/status` returns the same. `/api/health` shows `ai_key_set`.
- **Gemini model chain**: free-tier limits are per model, so a rate limit (429/503) or retired model (404) falls through `gemini-2.5-flash-lite → gemini-2.5-flash → gemini-2.0-flash` (override with `GEMINI_MODELS`). A rejected key stops at once and is reported.
- **Follow-ups**: short questions like "just give me the venue names" are searched together with the previous question and the chat history is given to the AI.
- **Better retrieval**: words in a page's title and web address weigh more than words buried in its text; request words (give, show, list, names…) are ignored; singular/plural matching fixed (venues/venue, prices/price, services/service…); continuation sections are added so long lists aren't cut; the index is cached per assistant.
- **Lists**: the AI is told to list every matching item it finds.
- **Emergency mode** (only if the AI is down): shows the best-matching sentences from the best page plus a link button to that page, never a random block of text.
- Repeated questions are answered from a 15-minute cache (no AI call).

## Background web research (what the business does, its history)
When a website is added, SiteBot also researches the business **online, in parallel with reading the site**, with no extra step shown to the user. The research uses live web search through the AI you already configured (Gemini: Google Search grounding on `GEMINI_API_KEY`; Claude: the web search tool when `ANTHROPIC_API_KEY` is set), so no extra key is needed. The result is a short briefing (overview, products/services, history and founding, locations, reputation, other facts) stored in the `research` table.
- It is given to the AI with every question as `<web_research>`, with strict rules: use it only for what the website doesn't answer (history, what the business is, where it operates, reputation); never for prices, availability, policies or contact details; the website wins on any disagreement; never mention that the web was searched.
- The research prompt names the exact domain and tells the AI to ignore similarly named companies and to write "Not found" instead of guessing. Briefings with nothing found are discarded.
- If research didn't finish while the site was read, the dashboard completes it quietly the first time the assistant is opened; failures are retried at most hourly; the scheduler refreshes briefings about monthly.
- Owners can switch it off (Customize & protect → "Also use public information from the web…"), which deletes the briefing. It appears in "Show pages learned" as "Public web research about your business". `WEB_RESEARCH=0` disables it for the whole server.
- Privacy: only the business name and website address are sent to the search; mention in your privacy policy that public web information may be used to answer visitors' questions.
- If the AI plan doesn't include search grounding, research quietly fails and answers continue to work from the website alone.
