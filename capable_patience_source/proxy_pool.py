"""
proxy_pool.py — shared per-user proxy pool (DB-backed).

All non-razorpay gates read the user's OWN proxies here (added via /proxy).
Razorpay keeps its own pool inside the :9000 API (proxy_manager/proxy_db.json).

Also provides prune_proxy_if_dead(): on a proxy_error from /sh or /msh,
test the proxy and remove it from the user's pool only if it is really dead.
"""
import asyncio
import logging

from database import get_db_connection


def get_user_proxies_sync(user_id: int) -> list:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT proxy FROM proxies WHERE user_id = %s ORDER BY id", (user_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows]
    except Exception as e:
        logging.error(f"[proxy_pool] fetch proxies for {user_id}: {e}")
        return []


async def get_user_proxies(user_id: int) -> list:
    return await asyncio.to_thread(get_user_proxies_sync, user_id)


def add_proxy_sync(user_id: int, proxy: str) -> bool:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM proxies WHERE user_id = %s AND proxy = %s", (user_id, proxy)
        )
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO proxies (user_id, proxy) VALUES (%s, %s)", (user_id, proxy)
            )
            conn.commit()
            added = True
        else:
            added = False
        conn.close()
        return added
    except Exception as e:
        logging.error(f"[proxy_pool] add proxy for {user_id}: {e}")
        return False


def remove_proxy_sync(user_id: int, proxy: str) -> bool:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM proxies WHERE user_id = %s AND proxy = %s", (user_id, proxy)
        )
        removed = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return removed
    except Exception as e:
        logging.error(f"[proxy_pool] remove proxy for {user_id}: {e}")
        return False


async def prune_proxy_if_dead(user_id: int, proxy: str) -> bool:
    """Test a proxy that just returned proxy_error.

    Returns True if the proxy is still alive (kept in pool),
    False if it was dead and removed from the pool.
    Never raises — on any test error the proxy is kept.
    """
    try:
        from proxy import parse_proxy_input, check_proxy_live
    except Exception as e:
        logging.error(f"[proxy_pool] import error: {e}")
        return True

    parsed = parse_proxy_input(proxy)
    if not parsed:
        return True

    url = parsed["url_format"]
    db_fmt = parsed["db_format"]

    try:
        is_alive, _info = await check_proxy_live(url)
    except Exception as e:
        logging.error(f"[proxy_pool] liveness check error: {e}")
        return True

    if not is_alive:
        await asyncio.to_thread(remove_proxy_sync, user_id, db_fmt)
        if proxy.strip() != db_fmt.strip():
            await asyncio.to_thread(remove_proxy_sync, user_id, proxy)
        logging.warning(
            f"[proxy_pool] removed dead proxy for user {user_id}: {db_fmt[:24]}..."
        )
        return False
    return True
