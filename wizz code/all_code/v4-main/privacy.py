# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PRIVACY / LOG NAME VISIBILITY SETTING
# Global toggle: hide user names in hit-log group messages.
# When enabled, the user name/link in log-group messages is
# wrapped in a spoiler (<tg-spoiler>) so others can't tell
# who the check belongs to.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

import logging

_state = {"enabled": False}


def init_privacy():
    try:
        from database import PooledConn
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            cur.execute(
                "INSERT INTO bot_settings(key, value) VALUES ('hide_names', 'off') "
                "ON CONFLICT (key) DO NOTHING"
            )
            conn.commit()
        _state["enabled"] = _load_from_db()
    except Exception as e:
        logging.error(f"[Privacy] init error: {e}")


def _load_from_db() -> bool:
    try:
        from database import PooledConn
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM bot_settings WHERE key = 'hide_names'")
            row = cur.fetchone()
            return bool(row and str(row[0]).lower() == "on")
    except Exception as e:
        logging.error(f"[Privacy] load error: {e}")
        return False


def names_hidden() -> bool:
    """True when user names in log-group messages should be hidden."""
    return _state["enabled"]


def set_names_hidden(hidden: bool) -> bool:
    """Persist + apply the hide-names toggle. Returns the applied value."""
    _state["enabled"] = bool(hidden)
    try:
        from database import PooledConn
        with PooledConn() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE bot_settings SET value = %s WHERE key = 'hide_names'",
                ("on" if hidden else "off",),
            )
            conn.commit()
    except Exception as e:
        logging.error(f"[Privacy] save error: {e}")
    return _state["enabled"]


def protect(html: str) -> str:
    """
    Replace the given HTML fragment with a "Hidden" spoiler when hide-names is
    enabled. The real value is never included in the message, so tapping the
    spoiler cannot reveal the user name — it only shows the word "Hidden".
    """
    if _state["enabled"]:
        return '<tg-spoiler>Hidden</tg-spoiler>'
    return html


init_privacy()