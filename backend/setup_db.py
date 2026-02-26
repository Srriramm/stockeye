"""
setup_db.py — One-time script to create all tables on Supabase.
Run once after setting DATABASE_URL in .env:
    python setup_db.py
"""

import os, sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')

DATABASE_URL = os.getenv('DATABASE_URL', '')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in .env")
    sys.exit(1)

try:
    import psycopg2
except ImportError:
    print("ERROR: Run:  pip install psycopg2-binary")
    sys.exit(1)

schema_path = Path(__file__).parent / 'schema.sql'
sql = schema_path.read_text(encoding='utf-8')

from urllib.parse import urlparse, unquote

parsed = urlparse(DATABASE_URL)
host = parsed.hostname or ''
port = parsed.port or 5432
user = unquote(parsed.username or '')
password = unquote(parsed.password or '')
dbname = (parsed.path or '/postgres').lstrip('/')

print(f"Connecting to Supabase...")
try:
    conn = psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=dbname,
        sslmode='require',
    )
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(sql)
    conn.close()
    print("✅ Schema created successfully on Supabase!")
    print("   Tables: holdings, monitored_stocks, alerts, price_alerts,")
    print("           portfolio_snapshots, watchlists, watchlist_items,")
    print("           advanced_alerts, orders, trades, trading_portfolio,")
    print("           trading_balance, conversations, conversation_messages")
    print("   RLS policies and indexes applied.")
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
