from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
import os, time, datetime

DATABASE_URL = os.getenv("DATABASE_URL")
engine = None

def get_engine():
    global engine
    if engine is None:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    return engine

def init_db():
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS complaints(
            id BIGSERIAL PRIMARY KEY,
            ticket_no TEXT,
            user_id BIGINT,
            username TEXT,
            full_name TEXT,
            category TEXT CHECK (category in ('complaint','suggestion')) DEFAULT 'complaint',
            message_text TEXT,
            file_type TEXT,
            file_id TEXT,
            file_url TEXT,
            status TEXT DEFAULT 'new',
            created_at TIMESTAMP DEFAULT NOW()
        );
        """))
        conn.execute(text("ALTER TABLE complaints ADD COLUMN IF NOT EXISTS file_url TEXT"))
        conn.execute(text("ALTER TABLE complaints ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'new'"))
        conn.execute(text("ALTER TABLE complaints ADD COLUMN IF NOT EXISTS ticket_no TEXT"))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS user_state(
            user_id BIGINT PRIMARY KEY,
            category TEXT CHECK (category in ('complaint','suggestion')) DEFAULT 'complaint',
            updated_at TIMESTAMP DEFAULT NOW()
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS user_profile(
            user_id BIGINT PRIMARY KEY,
            lang TEXT CHECK (lang in ('ru','uz')) DEFAULT 'ru',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS blocked_users(
            user_id BIGINT PRIMARY KEY,
            reason TEXT,
            blocked_at TIMESTAMP DEFAULT NOW()
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS rate_limiter(
            user_id BIGINT PRIMARY KEY,
            last_submit_at TIMESTAMP
        );
        """))

def set_user_category(user_id: int, category: str):
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("""
        INSERT INTO user_state(user_id, category)
        VALUES (:uid, :cat)
        ON CONFLICT (user_id) DO UPDATE SET category = EXCLUDED.category, updated_at = NOW()
        """), dict(uid=user_id, cat=category))

def get_user_category(user_id: int):
    eng = get_engine()
    with eng.connect() as conn:
        row = conn.execute(text("SELECT category FROM user_state WHERE user_id = :uid"),
                           dict(uid=user_id)).fetchone()
        return row[0] if row else None

def set_user_lang(user_id: int, lang: str):
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("""
        INSERT INTO user_profile(user_id, lang)
        VALUES (:uid, :lang)
        ON CONFLICT (user_id) DO UPDATE SET lang = EXCLUDED.lang, updated_at = NOW()
        """), dict(uid=user_id, lang=lang))

def get_user_lang(user_id: int):
    eng = get_engine()
    with eng.connect() as conn:
        row = conn.execute(text("SELECT lang FROM user_profile WHERE user_id = :uid"),
                           dict(uid=user_id)).fetchone()
        return row[0] if row else None

def is_blocked(user_id: int) -> bool:
    eng = get_engine()
    with eng.connect() as conn:
        row = conn.execute(text("SELECT 1 FROM blocked_users WHERE user_id = :uid"),
                           dict(uid=user_id)).fetchone()
        return bool(row)

def block_user(user_id: int, reason: str = None):
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("""
        INSERT INTO blocked_users(user_id, reason) VALUES (:uid, :reason)
        ON CONFLICT (user_id) DO NOTHING
        """), dict(uid=user_id, reason=reason))

def unblock_user(user_id: int):
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM blocked_users WHERE user_id = :uid"),
                     dict(uid=user_id))

def list_blocked(limit: int = 50, offset: int = 0):
    eng = get_engine()
    with eng.connect() as conn:
        return conn.execute(text("""
        SELECT user_id, reason, blocked_at
        FROM blocked_users
        ORDER BY blocked_at DESC
        LIMIT :lim OFFSET :off
        """), dict(lim=limit, off=offset)).fetchall()

def list_users(limit: int = 50, offset: int = 0):
    eng = get_engine()
    with eng.connect() as conn:
        return conn.execute(text("""
        SELECT user_id,
               max(username) as username,
               max(full_name) as full_name,
               max(created_at) as last_activity,
               COUNT(*) as total_messages
        FROM complaints
        GROUP BY user_id
        ORDER BY last_activity DESC
        LIMIT :lim OFFSET :off
        """), dict(lim=limit, off=offset)).fetchall()

def list_complaints(category: str | None, limit: int = 30, offset: int = 0, by_user: int | None = None):
    eng = get_engine()
    with eng.connect() as conn:
        base = """
        SELECT id, ticket_no, user_id, username, full_name, category, message_text, file_type, status, created_at
        FROM complaints
        """
        where = []
        params = {"lim": limit, "off": offset}
        if category in ("complaint", "suggestion"):
            where.append("category = :cat"); params["cat"] = category
        if by_user:
            where.append("user_id = :uid"); params["uid"] = by_user
        if where: base += " WHERE " + " AND ".join(where)
        base += " ORDER BY created_at DESC LIMIT :lim OFFSET :off"
        return conn.execute(text(base), params).fetchall()

def next_ticket_no(conn) -> str:
    year = datetime.datetime.utcnow().year
    seq = conn.execute(text("SELECT COALESCE(MAX(id),0)+1 FROM complaints")).scalar()
    return f"{year}-{int(seq):06d}"

def insert_complaint(user_id, username, full_name, category, message_text, file_type, file_id, file_url=None):
    eng = get_engine()
    with eng.begin() as conn:
        ticket = next_ticket_no(conn)
        conn.execute(text("""
            INSERT INTO complaints(ticket_no, user_id, username, full_name, category, message_text, file_type, file_id, file_url)
            VALUES (:ticket, :uid, :uname, :fname, :cat, :text, :ftype, :fid, :furl)
        """), dict(ticket=ticket, uid=user_id, uname=username, fname=full_name,
                   cat=category, text=message_text, ftype=file_type, fid=file_id, furl=file_url))
        return ticket

def get_by_ticket(ticket_no: str):
    eng = get_engine()
    with eng.connect() as conn:
        return conn.execute(text("""
        SELECT id, ticket_no, user_id, status FROM complaints WHERE ticket_no = :t
        """), dict(t=ticket_no)).fetchone()

def set_status(ticket_no: str, status: str):
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("UPDATE complaints SET status = :st WHERE ticket_no = :t"),
                     dict(st=status, t=ticket_no))

def touch_rate_limit(user_id: int, now_ts: datetime.datetime):
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("""
        INSERT INTO rate_limiter(user_id, last_submit_at)
        VALUES (:uid, :ts)
        ON CONFLICT (user_id) DO UPDATE SET last_submit_at = EXCLUDED.last_submit_at
        """), dict(uid=user_id, ts=now_ts))

def last_submit_time(user_id: int):
    eng = get_engine()
    with eng.connect() as conn:
        row = conn.execute(text("SELECT last_submit_at FROM rate_limiter WHERE user_id = :uid"),
                           dict(uid=user_id)).fetchone()
        return row[0] if row else None

def stats_counts():
    eng = get_engine()
    with eng.connect() as conn:
        out = {}
        out["total"] = conn.execute(text("SELECT COUNT(*) FROM complaints")).scalar()
        out["today"] = conn.execute(text("SELECT COUNT(*) FROM complaints WHERE created_at::date = CURRENT_DATE")).scalar()
        out["week"]  = conn.execute(text("SELECT COUNT(*) FROM complaints WHERE created_at >= NOW() - INTERVAL '7 days'")).scalar()
        out["month"] = conn.execute(text("SELECT COUNT(*) FROM complaints WHERE created_at >= NOW() - INTERVAL '30 days'")).scalar()
        out["complaints"] = conn.execute(text("SELECT COUNT(*) FROM complaints WHERE category='complaint'")).scalar()
        out["suggestions"] = conn.execute(text("SELECT COUNT(*) FROM complaints WHERE category='suggestion'")).scalar()
        return out

def wait_db(max_sec=60):
    start = time.time()
    while time.time() - start < max_sec:
        try:
            eng = get_engine()
            with eng.connect() as c:
                c.execute(text("SELECT 1"))
            return
        except OperationalError:
            time.sleep(1)
    raise RuntimeError("DB not ready")
