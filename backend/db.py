"""
db.py — Centralised database connection helper.

Priority: Supabase PostgreSQL → SQLite Cloud → Local SQLite

Env vars:
  DATABASE_URL      postgresql://...   ← Supabase (highest priority)
  SQLITECLOUD_URL   sqlitecloud://...  ← SQLite Cloud
  (neither set)                        ← local SQLite (dev fallback)

For PostgreSQL a ThreadedConnectionPool is used to avoid opening a new
psycopg2 connection on every request (which would exhaust Supabase's
connection limit at scale).  Pool size: 2–20 connections.
"""

import os, re, sqlite3, logging
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

DATABASE_URL    = os.getenv('DATABASE_URL', '')
SQLITECLOUD_URL = os.getenv('SQLITECLOUD_URL', '')

if DATABASE_URL:
    DB_TYPE = 'postgres'
elif SQLITECLOUD_URL:
    DB_TYPE = 'sqlitecloud'
else:
    DB_TYPE = 'sqlite'

# ─── PostgreSQL connection pool (lazy-initialised) ─────────────
_pg_pool = None

def _get_pg_pool():
    """Return the shared ThreadedConnectionPool, creating it on first call."""
    global _pg_pool
    if _pg_pool is None and DB_TYPE == 'postgres':
        try:
            from psycopg2 import pool as pg_pool
            from urllib.parse import urlparse, unquote
            parsed = urlparse(DATABASE_URL)
            _pg_pool = pg_pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=20,
                host=parsed.hostname or '',
                port=parsed.port or 5432,
                user=unquote(parsed.username or ''),
                password=unquote(parsed.password or ''),
                dbname=(parsed.path or '/postgres').lstrip('/'),
                sslmode='require',
            )
            logger.info("PostgreSQL connection pool initialised (2–20 connections)")
        except Exception as e:
            logger.error(f"Failed to create PG connection pool: {e}")
            _pg_pool = None
    return _pg_pool

_LOCAL_DB = Path(__file__).parent.parent / 'database' / 'stock_assistant.db'

# Maps table → conflict column(s) for INSERT OR REPLACE → ON CONFLICT upsert
_UPSERT_TARGETS = {
    'monitored_stocks':    '(user_id, ticker)',   # UNIQUE(user_id, ticker) in schema
    'portfolio_snapshots': '(snapshot_date)',
}


# ═══════════════════════════════════════════════════════════════
# SQL adapter: SQLite dialect → PostgreSQL
# ═══════════════════════════════════════════════════════════════

def _adapt(sql: str):
    """Convert SQLite SQL to PostgreSQL. Returns (adapted_sql, is_insert)."""
    had_ignore  = bool(re.search(r'INSERT\s+OR\s+IGNORE',  sql, re.I))
    had_replace = bool(re.search(r'INSERT\s+OR\s+REPLACE', sql, re.I))

    sql = sql.replace('?', '%s')
    sql = re.sub(r'INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT', 'SERIAL PRIMARY KEY', sql, flags=re.I)
    sql = re.sub(r'\bBOOLEAN\s+DEFAULT\s+1\b', 'BOOLEAN DEFAULT TRUE',  sql, flags=re.I)
    sql = re.sub(r'\bBOOLEAN\s+DEFAULT\s+0\b', 'BOOLEAN DEFAULT FALSE', sql, flags=re.I)

    if had_ignore:
        sql = re.sub(r'INSERT\s+OR\s+IGNORE\s+INTO', 'INSERT INTO', sql, flags=re.I)
        sql = sql.rstrip('; \n') + ' ON CONFLICT DO NOTHING'

    elif had_replace:
        tbl_m = re.search(r'INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)', sql, re.I)
        table = tbl_m.group(1) if tbl_m else ''
        target = _UPSERT_TARGETS.get(table, '')
        conflict_cols = set(re.findall(r'\b(\w+)\b', target))

        cols_m = re.search(r'INSERT\s+OR\s+REPLACE\s+INTO\s+\w+\s*\(([^)]+)\)', sql, re.I)
        sql = re.sub(r'INSERT\s+OR\s+REPLACE\s+INTO', 'INSERT INTO', sql, flags=re.I)
        if cols_m and target:
            cols   = [c.strip() for c in cols_m.group(1).split(',')]
            update = ', '.join(f'{c}=EXCLUDED.{c}' for c in cols
                               if c not in ('id', *conflict_cols))
            sql = sql.rstrip('; \n') + f' ON CONFLICT {target} DO UPDATE SET {update}'
        else:
            sql = sql.rstrip('; \n') + ' ON CONFLICT DO NOTHING'

    is_insert = bool(re.match(r'\s*INSERT\s+INTO', sql, re.I))
    # Add RETURNING id so lastrowid works (skip for DO NOTHING inserts)
    if is_insert and 'RETURNING' not in sql.upper() and 'DO NOTHING' not in sql.upper():
        sql = sql.rstrip('; \n') + ' RETURNING id'

    return sql, is_insert


# ═══════════════════════════════════════════════════════════════
# Row wrapper — dict + positional index access
# ═══════════════════════════════════════════════════════════════

class _Row(dict):
    """A dict that also supports row[0] positional access (like sqlite3.Row)."""
    def __init__(self, data: dict):
        super().__init__(data)
        self._vals = list(data.values())

    def __getitem__(self, key):
        return self._vals[key] if isinstance(key, int) else super().__getitem__(key)


# ═══════════════════════════════════════════════════════════════
# PostgreSQL cursor / connection wrappers
# ═══════════════════════════════════════════════════════════════

class _PgCursor:
    def __init__(self, cur, is_insert: bool):
        self._cur = cur
        self._lastrowid = None
        if is_insert and cur.description:   # RETURNING id result
            row = cur.fetchone()
            self._lastrowid = row[0] if row else None

    @property
    def lastrowid(self): return self._lastrowid

    @property
    def rowcount(self): return self._cur.rowcount

    def _wrap(self, raw):
        if raw is None: return None
        cols = [d[0] for d in self._cur.description]
        return _Row(dict(zip(cols, raw)))

    def fetchone(self):  return self._wrap(self._cur.fetchone())
    def fetchall(self):
        if not self._cur.description: return []
        cols = [d[0] for d in self._cur.description]
        return [_Row(dict(zip(cols, r))) for r in self._cur.fetchall()]


class _PgConn:
    def __init__(self, conn): self._conn = conn

    def execute(self, sql: str, params=()):
        sql, is_insert = _adapt(sql)
        cur = self._conn.cursor()
        cur.execute(sql, params or None)
        return _PgCursor(cur, is_insert)

    def commit(self):   self._conn.commit()
    def rollback(self): self._conn.rollback()
    def close(self):    self._conn.close()


# ═══════════════════════════════════════════════════════════════
# Public context manager
# ═══════════════════════════════════════════════════════════════

@contextmanager
def get_db_connection():
    """Yields a DB connection, commits on success, rolls back on error."""

    if DB_TYPE == 'postgres':
        pool = _get_pg_pool()
        if pool is None:
            # Pool unavailable — fall back to a one-off connection (dev / first boot)
            try:
                import psycopg2
            except ImportError:
                raise RuntimeError("Run: pip install psycopg2-binary")
            from urllib.parse import urlparse, unquote
            parsed = urlparse(DATABASE_URL)
            raw = psycopg2.connect(
                host=parsed.hostname or '',
                port=parsed.port or 5432,
                user=unquote(parsed.username or ''),
                password=unquote(parsed.password or ''),
                dbname=(parsed.path or '/postgres').lstrip('/'),
                sslmode='require',
            )
            conn = _PgConn(raw)
            try:
                yield conn
                conn.commit()
            except Exception as e:
                logger.error(f"Postgres tx failed: {e}")
                conn.rollback(); raise
            finally:
                conn.close()
        else:
            raw = pool.getconn()
            conn = _PgConn(raw)
            try:
                yield conn
                conn.commit()
            except Exception as e:
                logger.error(f"Postgres tx failed: {e}")
                conn.rollback(); raise
            finally:
                pool.putconn(raw)

    elif DB_TYPE == 'sqlitecloud':
        try:
            import sqlitecloud
        except ImportError:
            raise RuntimeError("Run: pip install sqlitecloud")
        raw = sqlitecloud.connect(SQLITECLOUD_URL)
        raw.row_factory = sqlitecloud.Row
        try:
            yield raw
            raw.commit()
        except Exception as e:
            logger.error(f"SQLiteCloud tx failed: {e}")
            try: raw.rollback()
            except Exception: pass
            raise
        finally:
            try: raw.close()
            except Exception: pass

    else:   # local SQLite
        _LOCAL_DB.parent.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(str(_LOCAL_DB))
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA journal_mode=WAL")
        raw.execute("PRAGMA foreign_keys=ON")
        try:
            yield raw
            raw.commit()
        except Exception as e:
            logger.error(f"Local SQLite tx failed: {e}")
            raw.rollback(); raise
        finally:
            raw.close()
