"""
JARVIS BOT — Database Migration Script
=======================================
Run this ONCE before starting the fixed jarvis.py to fix your database.

Fixes:
1. welcomer_settings table schema mismatch (wrong column names)
2. Migrates data from old welcome_settings table
3. Creates missing premium_users table
4. Fixes NULL emojis in reaction_roles

Usage:
    python fix_database.py
"""

import sqlite3
import sys
from datetime import datetime

DB_FILE = 'jarvisqueue_full.db'


def migrate():
    print(f"{'='*60}")
    print(f"JARVIS Database Migration — {datetime.now()}")
    print(f"{'='*60}\n")

    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
    except Exception as e:
        print(f"❌ Could not open database: {e}")
        sys.exit(1)

    # ── 1. Fix welcomer_settings schema ──────────────────────────
    print("[1/4] Checking welcomer_settings schema...")
    c.execute("PRAGMA table_info(welcomer_settings)")
    ws_cols = {row[1] for row in c.fetchall()}

    if 'welcome_enabled' in ws_cols:
        print("  ⚠️  Old schema detected (welcome_enabled, welcome_channel_id, ...)")
        print("  → Backing up old data...")

        c.execute('SELECT guild_id, welcome_enabled, welcome_channel_id, welcome_message FROM welcomer_settings')
        old_data = c.fetchall()

        print(f"  → Dropping old table ({len(old_data)} rows backed up)...")
        c.execute('DROP TABLE welcomer_settings')

        print("  → Creating table with correct schema...")
        c.execute('''CREATE TABLE welcomer_settings (
            guild_id INTEGER PRIMARY KEY,
            enabled INTEGER DEFAULT 0,
            channel_id INTEGER,
            message TEXT DEFAULT 'Welcome {user} to **{server}**! You are member #{membercount}.',
            embed_enabled INTEGER DEFAULT 1,
            embed_title TEXT DEFAULT 'Welcome!',
            embed_color INTEGER DEFAULT 3447003,
            embed_image TEXT,
            embed_thumbnail TEXT
        )''')

        for row in old_data:
            c.execute('''INSERT OR IGNORE INTO welcomer_settings
                         (guild_id, enabled, channel_id, message)
                         VALUES (?, ?, ?, ?)''',
                      (row[0], row[1], row[2], row[3]))

        conn.commit()
        print(f"  ✅ Migrated {len(old_data)} rows to new schema")
    elif 'enabled' in ws_cols:
        print("  ✅ Schema is already correct")
    else:
        print("  → Table empty or missing, creating with correct schema...")
        c.execute('''CREATE TABLE IF NOT EXISTS welcomer_settings (
            guild_id INTEGER PRIMARY KEY,
            enabled INTEGER DEFAULT 0,
            channel_id INTEGER,
            message TEXT DEFAULT 'Welcome {user} to **{server}**! You are member #{membercount}.',
            embed_enabled INTEGER DEFAULT 1,
            embed_title TEXT DEFAULT 'Welcome!',
            embed_color INTEGER DEFAULT 3447003,
            embed_image TEXT,
            embed_thumbnail TEXT
        )''')
        conn.commit()
        print("  ✅ Created welcomer_settings table")

    # ── 2. Migrate old welcome_settings data ─────────────────────
    print("\n[2/4] Checking for old welcome_settings table...")
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='welcome_settings'")
    if c.fetchone():
        c.execute('SELECT COUNT(*) FROM welcomer_settings')
        new_count = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM welcome_settings')
        old_count = c.fetchone()[0]

        if new_count == 0 and old_count > 0:
            print(f"  → Migrating {old_count} rows from old welcome_settings...")
            c.execute('SELECT guild_id, channel_id, message, enabled FROM welcome_settings')
            for row in c.fetchall():
                c.execute('''INSERT OR IGNORE INTO welcomer_settings
                             (guild_id, channel_id, message, enabled)
                             VALUES (?, ?, ?, ?)''',
                          (row[0], row[1], row[2], row[3]))
            conn.commit()
            print(f"  ✅ Migrated {old_count} rows")
        else:
            print(f"  ✅ No migration needed (welcomer_settings has {new_count} rows)")
    else:
        print("  ✅ No old welcome_settings table found")

    # ── 3. Create premium_users table ────────────────────────────
    print("\n[3/4] Checking premium_users table...")
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='premium_users'")
    if c.fetchone():
        print("  ✅ premium_users table already exists")
    else:
        c.execute('''CREATE TABLE premium_users (
            user_id INTEGER PRIMARY KEY,
            sku_id TEXT,
            purchased_at TEXT,
            entitlement_id TEXT,
            profile_color TEXT DEFAULT '#FFD700',
            profile_badge TEXT DEFAULT '👑',
            custom_title TEXT
        )''')
        conn.commit()
        print("  ✅ Created premium_users table")

    # ── 4. Fix NULL emojis in reaction_roles ─────────────────────
    print("\n[4/4] Checking reaction_roles for NULL emojis...")
    c.execute('SELECT id, label FROM reaction_roles WHERE emoji IS NULL')
    null_rows = c.fetchall()
    if null_rows:
        print(f"  ⚠️  Found {len(null_rows)} roles with NULL emoji")
        for row_id, label in null_rows:
            # Set a default emoji based on the label
            default_emoji = '🎮'
            label_lower = (label or '').lower()
            if 'cod' in label_lower:
                default_emoji = '🔫'
            elif 'cs' in label_lower:
                default_emoji = '💣'
            elif 'val' in label_lower:
                default_emoji = '🎯'
            elif 'verify' in label_lower:
                default_emoji = '✅'
            c.execute('UPDATE reaction_roles SET emoji = ? WHERE id = ?', (default_emoji, row_id))
            print(f"  → Set emoji {default_emoji} for role '{label}' (id={row_id})")
        conn.commit()
        print(f"  ✅ Fixed {len(null_rows)} NULL emojis")
    else:
        print("  ✅ No NULL emojis found")

    # ── Summary ──────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("MIGRATION COMPLETE")
    print(f"{'='*60}")

    # Show current state
    c.execute('SELECT COUNT(*) FROM welcomer_settings')
    print(f"  welcomer_settings: {c.fetchone()[0]} rows")
    c.execute('SELECT COUNT(*) FROM premium_users')
    print(f"  premium_users:     {c.fetchone()[0]} rows")
    c.execute('SELECT COUNT(*) FROM reaction_roles WHERE emoji IS NOT NULL')
    print(f"  reaction_roles:    {c.fetchone()[0]} rows (with emoji)")

    conn.close()
    print("\n✅ Done! You can now start jarvis.py")


if __name__ == '__main__':
    migrate()
