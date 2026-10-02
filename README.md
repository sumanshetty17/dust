# SiteBot: AI chatbot for any company website

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
| `ANTHROPIC_API_KEY` | your key from console.anthropic.com |
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
