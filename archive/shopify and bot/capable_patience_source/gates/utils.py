import random
import string
import re
import requests
import aiohttp
from urllib.parse import urlparse
from telebot.types import ReplyParameters
from telebot.types import Message


class Utils:
    proxies = []
    firstNames = []
    lastNames = []
    addresses = {
        "US": [
            ("6400 S Lewiston Way", "Aurora", "CO", "80016", "+17132782582", "United States"),
            ("6923 Lakewood Dr W #3", "Tacoma", "WA", "98467", "+12535822125", "United States"),
            ("1776 William Kennerty Drivee", "Charleston", "SC", "29407", "+19516564411", "United States"),
        ],
        "UK": [
            ("105 Ravenhurst St", "Birmingham", "WM", "B12 0HB", "(879) 658-2525", "United Kingdom"),
            ("17 Tewin Rd", "Welwyn Garden City", "", "AL7 1BD", "01707 371619", "United Kingdom"),
        ],
    }
    


    @classmethod
    def load_resources(cls):
        try:
            with open('proxy.txt', 'r') as file:
                cls.proxies = [line.strip() for line in file.readlines()]
            
            cls.firstNames = ["John", "Emily", "Michael", "Sarah", "William", "Olivia", "James", "Ava", "George", "Isabella"]
            cls.lastNames = ["Smith", "Johnson", "Williams", "Jones", "Brown", "Davis", "Miller", "Wilson", "Moore", "Taylor"]

            return True
        except Exception as e:
            print(f"Error loading resources: {e}")
            return False

    @classmethod
    def get_random_proxy(cls):
        if not cls.proxies:
            return None
        return random.choice(cls.proxies)

    @classmethod
    def get_random_name(cls):
        if not cls.firstNames or not cls.lastNames:
            return "John", "Doe"
        return random.choice(cls.firstNames), random.choice(cls.lastNames)

    @classmethod
    def generate_email(cls, first, last):
        return f"{first.lower()}{last.lower()}{random.randint(100, 200)}@gmail.com"

    @classmethod
    def generate_phone(cls):
        return ''.join(random.choices(string.digits, k=10))
    
    @classmethod
    def extract_and_validate_card(cls, msg: Message, depth=0):
        """Extract and validate card from message or its replied message"""
        if depth > 1:
            return False, "Invalid format or no card found", None
        
        text = msg.text or ""
        
        digits = re.findall(r'\d+', text)
        # remove digits which are greater than 4 n less than 12 and greater than 20
        # 5 <= x <= 12 should be removed also greater than 20 length should be removed
        digits = [d for d in digits if not (5 <= len(d) <= 12 or len(d) > 20)]
        
        match = None

        if len(digits) == 4:
            # Initialize variables
            cc = mes = ano = cvv = None
            
            # Find card number (13-19 digits)
            for i, d in enumerate(digits):
                if 13 <= len(d) <= 19:
                    cc = digits.pop(i)
                    break
                    
            # Find month (1-2 digits, 1-12)
            if cc:
                for i, d in enumerate(digits):
                    if len(d) <= 2 and 1 <= int(d) <= 12:
                        mes = digits.pop(i)
                        break
            
            # Find year (2 or 4 digits)
            if mes:
                for i, d in enumerate(digits):
                    if len(d) in [2, 4]:
                        ano = digits.pop(i)
                        break
                        
            # Find CVV (3-4 digits)
            if ano and digits:
                for d in digits:
                    if len(d) in [3, 4]:
                        cvv = d
                        break
            
            if all([cc, mes, ano, cvv]):
                return True, None, (cc, mes, ano, cvv)
        else:
            text = text.replace('/', '|').replace(' ', '|').replace('-', '|').replace('\n', ' ')
            pattern = r"""
(?:^|\D)
(\d{13,19})
\D+?
(\d{1,2})
\D+?
(\d{2,4})
\D+?
(\d{3,4})
(?!\d)
"""
            match = re.search(pattern, text, re.VERBOSE | re.MULTILINE)
            if not match:
                match = re.search(r'(\d{13,19})\|(\d{2})\|(\d{2,4})\|(\d{3,4})', text, re.VERBOSE | re.MULTILINE)    
        
        if not match and msg.reply_to_message:
            if msg.reply_to_message.text:
                return cls.extract_and_validate_card(msg.reply_to_message, depth + 1)
            
        if not match:
            return False, "Invalid format or no card found", None
        
        cc, mes, ano, cvv = match.groups()

        if not cls.luhn_check(cc):
            return False, "Invalid card number", None
        
        if not mes.isdigit() or int(mes) < 1 or int(mes) > 12:
            return False, "Invalid month", None
            
        if not ano.isdigit() or len(ano) not in [2, 4]:
            return False, "Invalid year", None
            
        if not cvv.isdigit() or len(cvv) not in [3, 4]:
            return False, "Invalid CVV", None
        
        return True, None, (cc, mes, ano, cvv)
    
    @classmethod
    def get_random_address(cls, country_code="US"):
        """Get random address for given country code"""
        addresses = cls.addresses.get(country_code, cls.addresses["US"])
        return random.choice(addresses)

    @classmethod
    def format_address(cls, address):
        """Format address tuple into dict"""
        street, city, state, zip_code, phone, country = address
        return {
            "street": street,
            "city": city,
            "state": state,
            "zip": zip_code,
            "phone": phone,
            "country": country
        }

    @classmethod
    def get_formatted_address(cls, country_code="US"):
        """Get random formatted address for country"""
        address = cls.get_random_address(country_code)
        return cls.format_address(address)
    
    @classmethod
    def extract_reply_text(cls, message):
        print(message)
        match = re.search(r'(\d{13,19})\|(\d{2})\|(\d{2,4})\|(\d{3,4})', message)
        if match:
            return match.group(0)
        return None
    
    @staticmethod
    def luhn_check(card_number):
        def digits_of(n):
            return [int(d) for d in str(n)]
        digits = digits_of(card_number)
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]
        checksum = sum(odd_digits)
        for d in even_digits:
            checksum += sum(digits_of(d * 2))
        return checksum % 10 == 0
    
    @staticmethod
    async def fetch_bigcartel(url):
        """Fetch available products from BigCartel store async"""
        url = "https://" + urlparse(url).netloc 
        prods = url + '/products.json'

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(prods) as response:
                    if response.status != 200:
                        return None
                    products = await response.json()
                    available_items = []
                    for product in products:
                        if 'options' in product and product['options']:
                            for option in product['options']:
                                if not option.get('sold_out', False):
                                    available_items.append({
                                        'product_id': product['id'],
                                        'option_id': option['id'],
                                        'product_name': product['name'],
                                        'option_name': option['name'],
                                        'price': option['price'],
                                        'url': f"{url}{product['url']}",
                                        'site': url
                                    })
                        else:
                            available_items.append({
                                'product_id': product['id'],
                                'option_id': None,
                                'product_name': product['name'],
                                'option_name': None,
                                'price': product['price'],
                                'url': f"{url}{product['url']}",
                                'site': url
                            })

                    sorted_items = sorted(available_items, key=lambda x: float(x['price']))
                    return sorted_items[0] if sorted_items else None

            except Exception as e:
                print(f"BigCartel fetch error: {e}")
                return None
    
    @staticmethod
    def extract_multiple_cards(message, cmd,limit=10):
        """Extract multiple cards using similar logic as single card extraction"""
        if not message.text:
            return None
        apiId = re.search(r'api\d+', message.text.lower())
        if apiId:
            apiId = apiId.group(0)
        else:
            apiId = ''
        text = message.text.strip().replace(cmd, '').replace('/', '').replace(apiId, '')

        cards = []

        # Split by newlines and remove command from first line
        lines = text.split('\n')

        for line in lines:
            if len(cards) >= limit:
                break
                
            # Clean the text similar to single card extraction
            line = line.replace('/', '|').replace(' ', '|').replace('-', '|').replace(':', '|')
            
            # Try digit extraction first
            digits = re.findall(r'\d+', line)
            digits = [d for d in digits if not (5 <= len(d) <= 12 or len(d) > 20)]
            
            if len(digits) >= 4:
                # Find card number (13-19 digits)
                cc = next((d for d in digits if 13 <= len(d) <= 19), None)
                if cc:
                    remaining = [d for d in digits if d != cc]
                    # Find month (1-2 digits, 1-12)
                    mes = next((d for d in remaining if len(d) <= 2 and 1 <= int(d) <= 12), None)
                    if mes:
                        remaining.remove(mes)
                        # Find year (2 or 4 digits)
                        ano = next((d for d in remaining if len(d) in [2, 4]), None)
                        if ano:
                            remaining.remove(ano)
                            # Find CVV (3-4 digits)
                            cvv = next((d for d in remaining if len(d) in [3, 4]), None)
                            if cvv and Utils.luhn_check(cc):  # Add Luhn check
                                cards.append((cc, mes, ano, cvv))
                                continue
            
            # If digit extraction fails, try regex pattern
            pattern = r'(\d{13,19})\D+?(\d{1,2})\D+?(\d{2,4})\D+?(\d{3,4})'
            match = re.search(pattern, line)
            if match:
                cc, mes, ano, cvv = match.groups()
                if (13 <= len(cc) <= 19 and 
                    1 <= int(mes) <= 12 and 
                    len(ano) in [2, 4] and 
                    len(cvv) in [3, 4] and 
                    Utils.luhn_check(cc)):
                    cards.append((cc, mes, ano, cvv))
                    
        return cards if cards else None

async def fetchBigCartelProds(url):
    """Fetch BigCartel products async"""
    url = "https://" + urlparse(url).netloc 
    prods = url + '/products.json'
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(prods) as response:
                response.raise_for_status()
                products = await response.json()

                available_items = []
                for product in products:
                    if 'options' in product and product['options']:
                        for option in product['options']:
                            if not option.get('sold_out', False):
                                available_items.append({
                                    'product_id': product['id'],
                                    'option_id': option['id'],
                                    'product_name': product['name'],
                                    'option_name': option['name'],
                                    'price': option['price'],
                                    'url': f"{url}{product['url']}",
                                    'site': url
                                })
                    else:
                        available_items.append({
                            'product_id': product['id'],
                            'option_id': None,
                            'product_name': product['name'],
                            'option_name': None,
                            'price': product['price'],
                            'url': f"{url}{product['url']}"
                        })
                
                sorted_items = sorted(available_items, key=lambda x: float(x['price']))
                return sorted_items[0] if sorted_items else None

        except Exception as e:
            print(f"BigCartel fetch error: {e}")
            return None

def extract_between(text, start, end):
    try:
        if not text or not isinstance(text, str):
            return None
        if start not in text:
            return None
        first_split = text.split(start, 1)
        if len(first_split) < 2:
            return None
        second_split = first_split[1].split(end, 1)
        if len(second_split) < 1:
            return None
        return second_split[0]
    except:
        return None


def get_random_string(length, digits=False, all=False, small=False, caps=False):
    if digits:
        letters = string.digits
    elif all:
        letters = string.ascii_letters + string.digits + string.ascii_uppercase
    elif small:
        letters = string.ascii_lowercase
    elif caps:
        letters = string.ascii_uppercase
    else:
        letters = string.ascii_lowercase + string.ascii_uppercase
    
    return ''.join(random.choice(letters) for i in range(length))


def getCardType(card):
    if re.match(r'^4[0-9]{12}(?:[0-9]{3})?$', card):
        return "VISA"
    if re.match(r'^5[1-5][0-9]{14}$', card):
        return "MASTERCARD"
    if re.match(r'^3[47][0-9]{13}$', card):
        return "AMEX"
    if re.match(r'^6(?:011|5[0-9]{2})[0-9]{12}$', card):
        return "DISCOVER"
    return "VISA"
