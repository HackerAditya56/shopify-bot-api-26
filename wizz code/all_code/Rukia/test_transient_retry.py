"""Verify transient retry logic."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "mass_gates"))

import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")

from unittest.mock import AsyncMock, MagicMock
import mass_gates.msh as msh


async def main():
    # Mock proxy_manager and session
    sess_mock = MagicMock()
    sess_mock.get = MagicMock(return_value=False)

    proxy_manager = MagicMock()
    proxy_manager.get_next_proxy = MagicMock(side_effect=lambda: ("proxy1", False))
    proxy_manager.report_result = MagicMock()
    proxy_manager.is_real_proxy_error = MagicMock(return_value=False)

    session = {
        'proxy_manager': proxy_manager,
        'sites_list': [
            'https://site-a.com',
            'https://site-b.com',
            'https://site-c.com',
            'https://site-d.com',
            'https://site-e.com',
        ],
        'is_group': False,
        'checked': 0,
        'charged': 0,
        'charged_cards': [],
        'approved': 0,
        'live': 0,
        'live_cards': [],
        'dead': 0,
        'dead_cards': [],
        'declined': 0,
        'errors': 0,
        'error_cards': [],
        'total_cards': 0,
        'is_stopped': False,
        'processed': set(),
        'stop_event': asyncio.Event(),
        'start_time': 0,
    }

    # Patch process_card_api to return controlled responses
    call_log = []

    async def fake_process_card_api(cc, mes, ano, cvv, site, proxy):
        idx = len(call_log)
        # Always return ERROR for scenario 1
        resp = "ERROR"
        call_log.append((site, resp))
        return (False, resp, site, "Stripe", "0.00", "USD", "Dead", 200)

    msh.process_card_api = fake_process_card_api
    msh.MSH_SESSIONS = {'test': session}

    # SCENARIO 1: Always ERROR (4 attempts, then ERROR)
    call_log.clear()
    proxy_manager.get_next_proxy = MagicMock(side_effect=lambda: ("p1", False))

    from mass_gates.msh import process_single_card
    await process_single_card('test', '4111111111111111|12|2030|123', '4111111111111111', 1, None, None, None)

    print("\n=== SCENARIO 1: 4× ERROR (3 retries then give up) ===")
    print(f"Calls made: {len(call_log)}")
    print(f"Sites tried: {[c[0] for c in call_log]}")
    print(f"Last response: {call_log[-1][1]}")
    assert len(call_log) == 4, f"Expected 4 attempts, got {len(call_log)}"
    assert call_log[-1][1] == "ERROR"
    assert len(set(c[0] for c in call_log)) == 4, "Each retry should use a different site"
    print("PASS: 4 attempts on 4 different sites, gave up after 3 retries")

    # SCENARIO 2: ERROR, ERROR, ERROR, CARD_DECLINED
    print("\n=== SCENARIO 2: 3× ERROR then CARD_DECLINED ===")
    call_log.clear()
    proxy_manager.get_next_proxy = MagicMock(side_effect=lambda: ("p1", False))

    async def fake_3err_1decl(cc, mes, ano, cvv, site, proxy):
        idx = len(call_log)
        resp = "ERROR" if idx < 3 else "CARD_DECLINED"
        call_log.append((site, resp))
        return (False, resp, site, "Stripe",
                "10.00" if resp == "CARD_DECLINED" else "0.00",
                "USD", "Dead", 200)
    msh.process_card_api = fake_3err_1decl

    await process_single_card('test', '4111111111111111|12|2030|123', '4111111111111111', 1, None, None, None)
    print(f"Calls made: {len(call_log)}")
    print(f"Sites tried: {[c[0] for c in call_log]}")
    print(f"Last response: {call_log[-1][1]}")
    assert call_log[-1][1] == "CARD_DECLINED"
    assert len(call_log) == 4
    print("PASS: 3 transient retries then accepts CARD_DECLINED as proper response")

    # SCENARIO 3: First ERROR, then 503, then CARD_DECLINED on 3rd
    print("\n=== SCENARIO 3: 503 -> CARD_DECLINED ===")
    call_log.clear()
    proxy_manager.get_next_proxy = MagicMock(side_effect=lambda: ("p1", False))

    async def fake_503(cc, mes, ano, cvv, site, proxy):
        idx = len(call_log)
        if idx == 0:
            resp = "ERROR"
        elif idx == 1:
            resp = "<b>Site Error! Status: 503</b>"
        else:
            resp = "CARD_DECLINED"
        call_log.append((site, resp))
        return (False, resp, site, "Stripe", "15.00" if resp == "CARD_DECLINED" else "0.00",
                "USD", "Dead", 200)
    msh.process_card_api = fake_503

    await process_single_card('test', '4111111111111111|12|2030|123', '4111111111111111', 1, None, None, None)
    print(f"Calls made: {len(call_log)}")
    print(f"Sites tried: {[c[0] for c in call_log]}")
    print(f"Last response: {call_log[-1][1]}")
    assert call_log[-1][1] == "CARD_DECLINED"
    print("PASS: 503 also triggers retry-on-different-site")

    # SCENARIO 4: NON-transient error (404) should NOT retry - break immediately
    print("\n=== SCENARIO 4: 'Site Error! Status: 404' should NOT retry (only ERROR/503 retry) ===")
    call_log.clear()
    proxy_manager.get_next_proxy = MagicMock(side_effect=lambda: ("p1", False))

    async def fake_404(cc, mes, ano, cvv, site, proxy):
        resp = "<b>Site Error! Status: 404</b>"
        call_log.append((site, resp))
        return (False, resp, site, "Stripe", "0.00", "USD", "Dead", 200)
    msh.process_card_api = fake_404

    await process_single_card('test', '4111111111111111|12|2030|123', '4111111111111111', 1, None, None, None)
    print(f"Calls made: {len(call_log)}")
    print(f"Last response: {call_log[-1][1]}")
    assert len(call_log) == 1, f"Expected 1 attempt (no retry on 404), got {len(call_log)}"
    print("PASS: Non-transient error (404) breaks immediately, no retry")

    # SCENARIO 5: Mixed - INVALID_PAYMENT_METHOD (a real card decline) should NOT retry
    print("\n=== SCENARIO 5: 'INVALID_PAYMENT_METHOD' (real card decline) breaks immediately ===")
    call_log.clear()
    proxy_manager.get_next_proxy = MagicMock(side_effect=lambda: ("p1", False))

    async def fake_invalid(cc, mes, ano, cvv, site, proxy):
        resp = "INVALID_PAYMENT_METHOD"
        call_log.append((site, resp))
        return (False, resp, site, "Stripe", "0.00", "USD", "Dead", 200)
    msh.process_card_api = fake_invalid

    await process_single_card('test', '4111111111111111|12|2030|123', '4111111111111111', 1, None, None, None)
    print(f"Calls made: {len(call_log)}")
    print(f"Last response: {call_log[-1][1]}")
    assert len(call_log) == 1
    print("PASS: Real card decline (DECLINED_RESPONSES match) breaks immediately")

    # SCENARIO 6: lowercase 'error' should also retry (we use upper().strip() == 'ERROR')
    print("\n=== SCENARIO 6: lowercase 'error' should retry (case-insensitive) ===")
    call_log.clear()
    proxy_manager.get_next_proxy = MagicMock(side_effect=lambda: ("p1", False))

    async def fake_lower_error(cc, mes, ano, cvv, site, proxy):
        resp = "error"  # lowercase
        call_log.append((site, resp))
        return (False, resp, site, "Stripe", "0.00", "USD", "Dead", 200)
    msh.process_card_api = fake_lower_error

    await process_single_card('test', '4111111111111111|12|2030|123', '4111111111111111', 1, None, None, None)
    print(f"Calls made: {len(call_log)}")
    print(f"Last response: {call_log[-1][1]}")
    assert len(call_log) == 4, f"Expected 4 attempts (1 + 3 retries), got {len(call_log)}"
    print("PASS: Lowercase 'error' is normalized to 'ERROR' and triggers retry")

    print("\n=== ALL TESTS PASSED ===")


asyncio.run(main())
