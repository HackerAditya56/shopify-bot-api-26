"""Diagnostic: capture a real checkout page + persisted-query ids for a shop.

    ./venv/bin/python capture_fixture.py https://anthroverse.myshopify.com

Read-only: performs GETs only, stops before Step 4 (no Proposal/Submit/payment).
"""
import asyncio
import re
import sys
import pathlib

sys.path.insert(0, "/home/administrator/api")
import auto_async as A

SITE = (sys.argv[1] if len(sys.argv) > 1 else "https://fe4be9-5e.myshopify.com").rstrip("/")
SLUG = SITE.split("://", 1)[-1].split(".")[0]
OUT = pathlib.Path("/tmp/shopify_fixture") / SLUG
OUT.mkdir(parents=True, exist_ok=True)


def slug(u):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", u.split("/")[-1])[:70]


async def main():
    print(f"=== {SITE} ===\n")
    async with A.AsyncTLSClient(timeout=25) as c:
        # ---- Step 0: catalog ----
        try:
            r = await c.get(f"{SITE}/products.json?limit=250&page=1", timeout=20)
            prods = (r.json() or {}).get("products", []) if r.status_code == 200 else []
            tot = sum(len(p.get("variants", [])) for p in prods)
            av = sum(1 for p in prods for v in p.get("variants", []) if v.get("available"))
            print(f"[step0] products.json {r.status_code}: {len(prods)} products, "
                  f"{tot} variants, {av} available")
            try:
                cur = (await c.get(f"{SITE}/meta.json", timeout=15)).json().get("currency")
            except Exception:
                cur = "?"
            print(f"[step0] currency={cur}")
            try:
                title, pid, handle, vid, price = await A.find_cheapest_product(c, SITE)
                print(f"[step0] find_cheapest_product OK: {title!r} price={price} variant={vid}")
            except Exception as e:
                print(f"[step0] find_cheapest_product FAILED: {e}")
                prods = [p for p in prods if p.get("variants")]
                p0 = prods[0]
                v0 = p0["variants"][0]
                title, pid, handle, vid, price = (
                    p0.get("title", ""), str(p0.get("id", "")), p0.get("handle", ""),
                    str(v0.get("id", "")), v0.get("price", ""))
                print(f"[step0] forcing unavailable variant {vid} to reach Step 1")
        except Exception as e:
            raise SystemExit(f"[step0] catalog unreachable: {e}")

        # ---- Step 1: checkout page ----
        url, token, sess, page = await A.add_to_cart_and_checkout(c, SITE, vid, pid, handle)
        print(f"\n[step1] checkout_url  = {url}")
        print(f"[step1] checkout_token = {token}")
        print(f"[step1] html bytes     = {len(page)}")
        (OUT / "checkout.html").write_text(page, encoding="utf-8", errors="replace")

        print("\n[step1] scrapers from checkout HTML:")
        for name, pat in (
            ("stableId", r'"stableId"\s*:\s*"([0-9a-f-]{36})"'),
            ("commitSha", r'"commitSha"\s*:\s*"([a-f0-9]{40})"'),
            ("sourceToken", r'<meta\s+name="serialized-sourceToken"\s+content="([^"]*)"'),
            ("patId", r'private_access_tokens\?id=([0-9a-f-]+)'),
            ("identSig", r'checkoutCardsinkCallerIdentificationSignature":"([^"]+)"'),
        ):
            m = re.search(pat, page)
            got = (m.group(1) or m.group(2)) if m else None
            g = (got[:58] + "...") if got and len(str(got)) > 58 else got
            print(f"          {name:<14} {g if got else '*** MISSING ***'}")

        # ---- Step 3: persisted-query discovery (the code under test) ----
        print(f"\n[step3] legacy actions.js hint -> {A.extract_actions_js_url(page, SITE)!r}")
        refs = A.extract_js_refs(page, SITE)
        print(f"[step3] extract_js_refs -> {len(refs)} checkout-web bundles")
        shapes = sorted({re.sub(r"\.[0-9a-fA-F]{6,}", ".<hash>", u.split("/assets/")[-1])
                         for u in refs})
        print(f"[step3] filename shapes: {len(shapes)} distinct, e.g. {shapes[:3]}")
        (OUT / "js_refs.txt").write_text("\n".join(refs), encoding="utf-8")

        build_id = A.extract_commit_sha(page)
        import time
        t = time.time()
        ops = await A.discover_persisted_ids(c, page, SITE, build_id)
        el = time.time() - t
        print(f"\n[step3] discover_persisted_ids COLD: {el:.1f}s")
        for k, v in ops.items():
            print(f"          {k:<22} {v if v else '*** MISSING ***'}")
        print(f"[step3] all three resolved: {all(ops.values())}")

        t = time.time()
        await A.discover_persisted_ids(c, page, SITE, build_id)
        print(f"[step3] discover_persisted_ids WARM: {time.time()-t:.4f}s")

    print(f"\nsaved -> {OUT}")
    for p in sorted(OUT.iterdir()):
        print(f"   {p.name:<52} {p.stat().st_size:>9}")


asyncio.run(main())