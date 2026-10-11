"""Postgres in production (DATABASE_URL), SQLite file for local dev."""
import os, sqlite3
URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
PG = bool(URL)
if PG:
    import psycopg
    from psycopg.rows import dict_row
DB = os.getenv("DB_PATH", "app.db")
PK = "bigserial primary key" if PG else "integer primary key"
TS = "timestamptz default now()" if PG else "text default current_timestamp"
SCHEMA = [
 f"create table if not exists users(id {PK}, email text unique, pw text, token text)",
 f"create table if not exists bots(id {PK}, user_id integer, name text, site_url text, public_key text unique, email_mode text default 'draft', created {TS})",
 f"create table if not exists chunks(id {PK}, bot_id integer, source text, text text, emb text)",
 "create index if not exists ix_chunks_bot on chunks(bot_id)",
 f"create table if not exists conversations(id {PK}, bot_id integer, session text, ip text, ts bigint, question text, answer text, answered integer, created {TS})",
 "create index if not exists ix_conv_bot on conversations(bot_id, ts)",
 "create index if not exists ix_conv_ip on conversations(ip, ts)",
 f"create table if not exists emails(id {PK}, bot_id integer, sender text, subject text, body text, category text, reason text, reply text, status text, created {TS})",
 "create index if not exists ix_users_token on users(token)",
 f"create table if not exists gmail_accounts(id {PK}, bot_id integer unique, email text, refresh_token text, last_sync bigint, created {TS})",
 f"create table if not exists leads(id {PK}, bot_id integer, name text, email text, message text, question text, ip text, ts bigint, created {TS})",
 "create index if not exists ix_leads_bot on leads(bot_id)",
 f"create table if not exists guides(id {PK}, bot_id integer, title text, steps text, url text, target text)",
 "create index if not exists ix_guides_bot on guides(bot_id)",
 f"create table if not exists navlinks(id {PK}, bot_id integer, label text, url text, area text)",
 "create index if not exists ix_nav_bot on navlinks(bot_id)",
]
MIGRATIONS = [("chunks", "emb text"), ("bots", "allowed_domains text"), ("bots", "color text"), ("bots", "title text"),
              ("bots", "greeting text"), ("bots", "domain_lock integer default 0"), ("bots", "reader_job text"), ("bots", "auto_relearn text default 'weekly'"), ("bots", "last_learned bigint"), ("bots", "last_attempt bigint"),
              ("bots", "learn_mode text default 'plain'"), ("bots", "learn_note text"), ("bots", "reader_job_ts bigint"), ("chunks", "src_hash text"), ("chunks", "seen bigint"), ("conversations", "helpful integer"),
              ("emails", "gmail_id text"), ("emails", "thread_id text"), ("emails", "draft_id text"), ("emails", "ts bigint")]
def _conn():
    if PG: return psycopg.connect(URL, row_factory=dict_row, autocommit=True, prepare_threshold=None)  # pooler-safe
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c
def _q(sql): return sql.replace("?", "%s") if PG else sql
def init():
    c = _conn()
    try:
        for s in SCHEMA: c.execute(s)
        for t, col in MIGRATIONS:  # adds new columns to databases created by older versions
            try: c.execute(f"alter table {t} add column " + ("if not exists " if PG else "") + col)
            except Exception: pass
        try: c.execute("create index if not exists ix_emails_gid on emails(bot_id, gmail_id)")
        except Exception: pass
        if not PG: c.commit()
    finally: c.close()
def run(sql, args=()):
    ins = sql.lstrip().lower().startswith("insert"); c = _conn()
    try:
        if PG:
            cur = c.execute(_q(sql) + (" returning id" if ins else ""), args)
            return cur.fetchone()["id"] if ins else None
        cur = c.execute(sql, args); c.commit(); return cur.lastrowid
    finally: c.close()
def rows(sql, args=()):
    c = _conn()
    try: return [dict(x) for x in c.execute(_q(sql), args).fetchall()]
    finally: c.close()
def one(sql, args=()):
    r = rows(sql, args); return r[0] if r else None
def run_many(sql, seq):
    seq = list(seq)
    if not seq: return
    c = _conn()
    try:
        if PG:
            with c.cursor() as cur: cur.executemany(_q(sql), seq)
        else: c.executemany(sql, seq); c.commit()
    finally: c.close()
