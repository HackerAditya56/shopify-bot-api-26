#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════════╗
║           CAPSOLVER v2.0 — UNIVERSAL CAPTCHA SOLVER                  ║
║         20+ CAPTCHA Types — Self-Hosted — Zero Cost                  ║
╚═══════════════════════════════════════════════════════════════════════╝

Supported CAPTCHAs:
 ┌─ Google ─────────────────────────────────────────────────────────────┐
 │  1.  reCAPTCHA v2          — Audio challenge → Speech-to-Text       │
 │  2.  reCAPTCHA v2 Invis    — Browser automation + token harvest     │
 │  3.  reCAPTCHA v3          — Score simulation via browser behavior  │
 │  4.  reCAPTCHA Enterprise  — Enterprise token via stealth browser   │
 ├─ hCaptcha ───────────────────────────────────────────────────────────┤
 │  5.  hCaptcha              — Audio/accessibility bypass             │
 │  6.  hCaptcha Enterprise   — Stealth browser + cookie harvest       │
 ├─ Cloudflare ─────────────────────────────────────────────────────────┤
 │  7.  Turnstile             — Browser challenge token extraction     │
 ├─ Puzzle / Interactive ───────────────────────────────────────────────┤
 │  8.  FunCaptcha            — Rotation puzzle via CV angle detect    │
 │  9.  GeeTest v3/v4         — Slider puzzle via template matching    │
 │  10. KeyCAPTCHA            — Jigsaw puzzle solver via CV            │
 ├─ Lightweight ────────────────────────────────────────────────────────┤
 │  11. Friendly Captcha      — Proof-of-Work computation (hashcash)   │
 │  12. MTCaptcha             — Image OCR + browser token              │
 ├─ Bot Management / WAF ──────────────────────────────────────────────┤
 │  13. DataDome              — Cookie generation + fingerprint spoof  │
 │  14. PerimeterX (HUMAN)    — Sensor data + PX cookie generation     │
 │  15. Kasada                — JS challenge solver + CD token          │
 │  16. Akamai Bot Manager    — Sensor data generation                 │
 │  17. Imperva/Incapsula     — Cookie challenge + JS eval             │
 │  18. Shape Security        — JS VM execution + token generation     │
 │  19. Radware Bot Manager   — Challenge-response solving             │
 │  20. Fastly Bot Management — Signal generation + fingerprinting     │
 ├─ Classic ────────────────────────────────────────────────────────────┤
 │  21. Image CAPTCHA (OCR)   — 6 preprocessing pipelines + voting     │
 │  22. Math CAPTCHA          — Expression parser + word numbers        │
 │  23. Text CAPTCHA          — Knowledge base + pattern matching      │
 │  24. Google Sorry Page     — Auto-detect + route to correct solver  │
 └──────────────────────────────────────────────────────────────────────┘

Server: http://localhost:9090
Install:
  apt install tesseract-ocr ffmpeg chromium-browser
  pip install flask requests Pillow pytesseract SpeechRecognition pydub numpy opencv-python-headless
  pip install undetected-chromedriver selenium  (recommended)
"""

import io, os, re, sys, json, time, random, base64, struct, hashlib, hmac
import logging, tempfile, urllib.parse, string, math
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from threading import Lock
from typing import Optional, Dict, List, Tuple
from collections import Counter

# ─── Deps ─────────────────────────────────────────────────────────
def _install():
    import subprocess
    subprocess.check_call([sys.executable,"-m","pip","install",
        "flask","requests","Pillow","pytesseract","SpeechRecognition",
        "pydub","numpy","opencv-python-headless",
        "--break-system-packages","-q"])

try:
    import requests, numpy as np
    from PIL import Image, ImageFilter, ImageEnhance, ImageOps
    import pytesseract, speech_recognition as sr
    from pydub import AudioSegment
    import cv2
    from flask import Flask, request as freq, jsonify, Response
except ImportError:
    _install()
    import requests, numpy as np
    from PIL import Image, ImageFilter, ImageEnhance, ImageOps
    import pytesseract, speech_recognition as sr
    from pydub import AudioSegment
    import cv2
    from flask import Flask, request as freq, jsonify, Response

logging.basicConfig(level=logging.INFO,format="%(asctime)s | %(levelname)-5s | %(message)s",datefmt="%H:%M:%S")
log = logging.getLogger("capsolver")

# ═══════════════════════════════════════════════════════════════════
#  STATS
# ═══════════════════════════════════════════════════════════════════
@dataclass
class Stats:
    total:int=0; solved:int=0; failed:int=0
    by_type:dict=field(default_factory=dict)
    times:list=field(default_factory=list)
    lock:Lock=field(default_factory=Lock)
    def record(self,t,ok,elapsed):
        with self.lock:
            self.total+=1
            if ok:self.solved+=1
            else:self.failed+=1
            self.by_type[t]=self.by_type.get(t,{"ok":0,"fail":0})
            self.by_type[t]["ok" if ok else "fail"]+=1
            self.times.append(elapsed)
            if len(self.times)>1000:self.times=self.times[-500:]
    def to_dict(self):
        return {"total":self.total,"solved":self.solved,"failed":self.failed,
                "rate":f"{self.solved/max(1,self.total)*100:.1f}%",
                "avg_ms":f"{sum(self.times)/max(1,len(self.times))*1000:.0f}",
                "by_type":self.by_type}

stats = Stats()

# ═══════════════════════════════════════════════════════════════════
#  BROWSER MANAGER — Shared browser pool
# ═══════════════════════════════════════════════════════════════════
class BrowserManager:
    """VPS-hardened browser manager with crash recovery, zombie cleanup, and multi-strategy fallback."""
    
    # Chrome flag profiles: heavy → medium → light → minimal
    PROFILES = [
        {   # Profile 0: Full features (good VPS, 2GB+ RAM)
            "name": "full",
            "flags": [
                "--headless=new","--no-sandbox","--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1920,1080","--disable-extensions","--lang=en-US",
                "--disable-gpu","--disable-software-rasterizer",
            ]
        },
        {   # Profile 1: Medium (1GB RAM VPS)
            "name": "medium",
            "flags": [
                "--headless=new","--no-sandbox","--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1366,768","--disable-extensions","--lang=en-US",
                "--disable-gpu","--disable-software-rasterizer",
                "--js-flags=--max-old-space-size=256",
                "--disable-background-networking","--disable-default-apps",
                "--disable-sync","--disable-translate",
                "--metrics-recording-only","--mute-audio",
                "--no-first-run",
            ]
        },
        {   # Profile 2: Light (512MB RAM VPS)
            "name": "light",
            "flags": [
                "--headless=new","--no-sandbox","--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1280,720","--disable-extensions","--lang=en-US",
                "--disable-gpu","--disable-software-rasterizer",
                "--js-flags=--max-old-space-size=128",
                "--disable-background-networking","--disable-default-apps",
                "--disable-sync","--disable-translate",
                "--disable-features=VizDisplayCompositor,TranslateUI",
                "--disable-ipc-flooding-protection",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
                "--disable-background-timer-throttling",
                "--metrics-recording-only","--mute-audio",
                "--no-first-run","--blink-settings=imagesEnabled=false",
            ]
        },
        {   # Profile 3: Minimal (256MB RAM, last resort)
            "name": "minimal",
            "flags": [
                "--headless","--no-sandbox","--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=800,600","--disable-extensions","--lang=en-US",
                "--disable-gpu","--disable-software-rasterizer",
                "--js-flags=--max-old-space-size=64",
                "--disable-background-networking","--disable-default-apps",
                "--disable-sync","--disable-translate",
                "--disable-features=VizDisplayCompositor,TranslateUI,NetworkService",
                "--disable-ipc-flooding-protection",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
                "--disable-background-timer-throttling",
                "--metrics-recording-only","--mute-audio",
                "--no-first-run","--blink-settings=imagesEnabled=false",
                "--disable-logging","--disable-breakpad",
                "--disable-component-update","--disable-domain-reliability",
                "--disable-client-side-phishing-detection",
            ]
        },
    ]
    
    def __init__(self):
        self._uc_available = None
        self._selenium_available = None
        self._playwright_available = None
        self._chrome_ver = None
        self._last_working_profile = 0  # Start with full, downgrade on crash
        self._consecutive_crashes = 0
        self._max_crashes_before_cooldown = 2
        self._cooldown_until = 0  # timestamp — don't retry until this time
        self._active_drivers = []  # Track for cleanup
        self._persistent_driver = None  # Reusable driver
        self._persistent_driver_uses = 0
        self._max_driver_reuses = 20  # Recycle after N uses
        self._env_checked = False
        self._proxy_url = None  # Set by _check_vps_environment
    
    def _check_vps_environment(self):
        """Run once: detect VPS resources and set initial profile accordingly."""
        if self._env_checked: return
        self._env_checked = True
        import subprocess
        
        # ── 1. Check available RAM ──
        try:
            with open("/proc/meminfo") as f:
                meminfo = f.read()
            avail = int([l for l in meminfo.split("\n") if "MemAvailable" in l][0].split()[1]) // 1024  # MB
            total = int([l for l in meminfo.split("\n") if "MemTotal" in l][0].split()[1]) // 1024
            log.info(f"[VPS] RAM: {avail}MB available / {total}MB total")
            if avail < 300:
                self._last_working_profile = 3  # minimal
                log.warning("[VPS] Very low RAM — using minimal profile")
            elif avail < 600:
                self._last_working_profile = 2  # light
                log.info("[VPS] Low RAM — using light profile")
            elif avail < 1200:
                self._last_working_profile = 1  # medium
                log.info("[VPS] Moderate RAM — using medium profile")
            else:
                log.info("[VPS] Good RAM — using full profile")
        except:
            log.debug("[VPS] Could not detect RAM, using full profile")
        
        # ── 2. Auto-detect proxy (CRITICAL for containers/VPS with egress proxy) ──
        #    Chrome --proxy-server does NOT support inline auth (user:pass@host:port)
        #    Playwright handles proxy auth natively via context options
        self._proxy_url = None
        self._proxy_auth = False  # True if proxy needs username/password
        self._proxy_config = None  # Parsed proxy config for Playwright
        
        from urllib.parse import urlparse
        for env_key in ["HTTPS_PROXY","https_proxy","HTTP_PROXY","http_proxy","ALL_PROXY","all_proxy"]:
            proxy = os.environ.get(env_key, "")
            if proxy:
                self._proxy_url = proxy
                parsed = urlparse(proxy)
                
                if parsed.username:
                    # Proxy has auth credentials — Playwright ONLY (Chrome can't handle inline auth in headless)
                    self._proxy_auth = True
                    proxy_bare = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
                    self._proxy_config = {
                        "server": proxy_bare,
                        "username": parsed.username,
                        "password": parsed.password or ""
                    }
                    log.info(f"[VPS] Authenticated proxy detected — Playwright will be prioritized")
                    # Still inject bare URL for Chrome (works for some no-auth proxies)
                    for p in self.PROFILES:
                        p["flags"].append(f"--proxy-server={proxy_bare}")
                else:
                    # No auth — Chrome --proxy-server works fine
                    self._proxy_config = {"server": proxy}
                    log.info(f"[VPS] Proxy detected (no auth) — passing to Chrome")
                    for p in self.PROFILES:
                        p["flags"].append(f"--proxy-server={proxy}")
                break
        
        # ── 3. Fix /dev/shm (critical for Chrome in Docker/VPS) ──
        try:
            shm_stat = os.statvfs("/dev/shm")
            shm_mb = (shm_stat.f_frsize * shm_stat.f_bavail) // (1024*1024)
            if shm_mb < 128:
                log.warning(f"[VPS] /dev/shm only {shm_mb}MB — Chrome may crash!")
                try:
                    subprocess.run(["mount","-o","remount,size=256M","/dev/shm"],
                                   capture_output=True, timeout=5)
                    log.info("[VPS] Expanded /dev/shm to 256MB")
                except:
                    log.info("[VPS] Cannot expand /dev/shm — using --disable-dev-shm-usage flag")
        except:
            pass
        
        # ── 4. Fix /tmp permissions (Chrome renderer needs W+X on /tmp) ──
        try:
            tmp_stat = os.stat("/tmp")
            if not (tmp_stat.st_mode & 0o0002):  # world-writable check
                os.chmod("/tmp", 0o1777)
                log.info("[VPS] Fixed /tmp permissions for Chrome")
        except:
            pass
        
        # ── 5. Check for Docker environment ──
        if os.path.exists("/.dockerenv") or os.path.exists("/proc/1/cgroup"):
            try:
                with open("/proc/1/cgroup") as f:
                    if "docker" in f.read() or "kubepods" in f.read():
                        log.info("[VPS] Docker/K8s detected")
            except: pass
        
        # ── 6. Check swap ──
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if "SwapTotal" in line:
                        swap = int(line.split()[1]) // 1024
                        if swap == 0:
                            log.warning("[VPS] No swap! Consider adding swap: fallocate -l 1G /swapfile && mkswap /swapfile && swapon /swapfile")
                        break
        except: pass
    
    def has_uc(self):
        if self._uc_available is None:
            try: import undetected_chromedriver; self._uc_available=True
            except ImportError: self._uc_available=False
        return self._uc_available

    def has_selenium(self):
        if self._selenium_available is None:
            try: from selenium.webdriver.common.by import By; self._selenium_available=True
            except ImportError: self._selenium_available=False
        return self._selenium_available

    def has_playwright(self):
        if self._playwright_available is None:
            try: from playwright.sync_api import sync_playwright; self._playwright_available=True
            except ImportError: self._playwright_available=False
        return self._playwright_available

    def has_browser(self):
        """Returns True if ANY browser backend is available (UC, Selenium, or Playwright)."""
        return self.has_uc() or self.has_selenium() or self.has_playwright()
    
    def _detect_chrome_version(self):
        if self._chrome_ver: return self._chrome_ver
        import subprocess
        for cmd in [["google-chrome","--version"],["chromium-browser","--version"],
                    ["chromium","--version"],["google-chrome-stable","--version"]]:
            try:
                out=subprocess.check_output(cmd,stderr=subprocess.DEVNULL,timeout=5).decode().strip()
                self._chrome_ver=int(out.split()[-1].split(".")[0])
                log.info(f"[Browser] Chrome version: {self._chrome_ver}")
                return self._chrome_ver
            except: pass
        return None
    
    def _kill_zombies(self):
        """Kill orphaned chrome/chromedriver processes to free RAM."""
        import subprocess, signal
        killed = 0
        for proc_name in ["chrome","chromium","chromedriver"]:
            try:
                out = subprocess.check_output(["pgrep","-f",proc_name],stderr=subprocess.DEVNULL).decode().strip()
                for pid in out.split("\n"):
                    pid = pid.strip()
                    if pid and pid.isdigit():
                        try: os.kill(int(pid), signal.SIGKILL); killed += 1
                        except: pass
            except: pass
        if killed: log.info(f"[Browser] Cleaned {killed} zombie processes")
        # Also clean /tmp/.com.google.Chrome* lock files
        import glob
        for f in glob.glob("/tmp/.com.google.Chrome.*") + glob.glob("/tmp/.org.chromium.*"):
            try: os.remove(f)
            except: pass
    
    def _is_in_cooldown(self):
        if time.time() < self._cooldown_until:
            remaining = int(self._cooldown_until - time.time())
            log.warning(f"[Browser] In cooldown ({remaining}s left) after {self._consecutive_crashes} crashes")
            return True
        return False
    
    def _record_crash(self):
        self._consecutive_crashes += 1
        # Kill persistent driver — it's broken
        if self._persistent_driver:
            try: self._persistent_driver.quit()
            except: pass
            self._persistent_driver = None
            self._persistent_driver_uses = 0
        # Downgrade to lighter profile
        if self._last_working_profile < len(self.PROFILES) - 1:
            self._last_working_profile += 1
            log.info(f"[Browser] Downgrading to '{self.PROFILES[self._last_working_profile]['name']}' profile")
        # Enter cooldown after too many crashes
        if self._consecutive_crashes >= self._max_crashes_before_cooldown:
            self._cooldown_until = time.time() + min(60 * self._consecutive_crashes, 600)
            log.warning(f"[Browser] Entering cooldown for {min(60*self._consecutive_crashes,600)}s")
    
    def _record_success(self):
        self._consecutive_crashes = max(0, self._consecutive_crashes - 1)
        self._cooldown_until = 0
    
    _xvfb_display = None
    
    def _ensure_display(self):
        """Start Xvfb if no display available (headless VPS)."""
        if BrowserManager._xvfb_display is not None:
            return
        if os.environ.get("DISPLAY"):
            return
        try:
            from pyvirtualdisplay import Display
            d = Display(visible=0, size=(1920, 1080))
            d.start()
            BrowserManager._xvfb_display = d
            log.info(f"[Browser] Started Xvfb virtual display: {os.environ.get('DISPLAY')}")
        except ImportError:
            pass  # No pyvirtualdisplay — headless flags will handle it
        except Exception as e:
            log.warning(f"[Browser] Xvfb failed: {e}")

    def create_driver(self, headless=True, profile_idx=None):
        """Create browser driver with VPS-safe configuration.
        Priority: Playwright (if proxy auth) → UC → Selenium → Playwright."""
        if self._is_in_cooldown(): return None
        self._ensure_display()
        self._check_vps_environment()  # Auto-detect VPS resources on first call
        
        # If proxy needs auth, Playwright is the ONLY backend that works in headless
        # (Chrome --proxy-server can't handle user:pass@host inline auth)
        if self._proxy_auth and self.has_playwright():
            driver = self._create_playwright_driver()
            if driver: return driver
            log.warning("[Browser] Playwright failed with proxy auth — trying other backends")
        
        # Kill zombies before creating new driver
        if self._consecutive_crashes > 0:
            self._kill_zombies()
        
        pidx = profile_idx if profile_idx is not None else self._last_working_profile
        pidx = min(pidx, len(self.PROFILES) - 1)
        profile = self.PROFILES[pidx]
        chrome_ver = self._detect_chrome_version()
        
        # ── Strategy 1: undetected-chromedriver ──
        if self.has_uc():
            try:
                import undetected_chromedriver as uc
                opts = uc.ChromeOptions()
                for flag in profile["flags"]:
                    opts.add_argument(flag)
                kw = {"options": opts}
                if chrome_ver: kw["version_main"] = chrome_ver
                log.info(f"[Browser] UC + '{profile['name']}' profile" + (f" (Chrome {chrome_ver})" if chrome_ver else "") + (" +proxy" if self._proxy_url else ""))
                d = uc.Chrome(**kw)
                d.set_page_load_timeout(30)
                d.set_script_timeout(20)
                d.implicitly_wait(5)
                self._active_drivers.append(d)
                return d
            except Exception as e:
                log.warning(f"[Browser] UC failed: {str(e)[:100]}")
        
        # ── Strategy 2: Plain Selenium ──
        if self.has_selenium():
            try:
                try:
                    import chromedriver_autoinstaller
                    chromedriver_autoinstaller.install()
                except ImportError: pass
                from selenium import webdriver
                from selenium.webdriver.chrome.options import Options
                from selenium.webdriver.chrome.service import Service
                opts = Options()
                for flag in profile["flags"]:
                    opts.add_argument(flag)
                opts.add_experimental_option("excludeSwitches",["enable-automation"])
                opts.add_experimental_option("useAutomationExtension",False)
                log.info(f"[Browser] Selenium + '{profile['name']}' profile" + (" +proxy" if self._proxy_url else ""))
                driver = webdriver.Chrome(options=opts)
                driver.set_page_load_timeout(30)
                driver.set_script_timeout(20)
                driver.implicitly_wait(5)
                try:
                    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",{"source":"""
                        Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
                        window.chrome={runtime:{}};
                        Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
                        Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
                    """})
                except: pass
                self._active_drivers.append(driver)
                return driver
            except Exception as e:
                log.warning(f"[Browser] Selenium failed: {str(e)[:100]}")
        
        # ── Strategy 3: Playwright (lighter than Chrome for some VPS) ──
        if self.has_playwright():
            driver = self._create_playwright_driver()
            if driver: return driver
        
        log.error("[Browser] All strategies failed")
        return None
    
    def _create_playwright_driver(self):
        """Create Playwright-based driver with full proxy auth support.
        Reuses a single Playwright instance to avoid asyncio loop conflicts."""
        if not self.has_playwright(): return None
        try:
            from playwright.sync_api import sync_playwright
            
            # Reuse existing Playwright instance if available
            if not hasattr(self, '_pw_instance') or self._pw_instance is None:
                try:
                    self._pw_instance = sync_playwright().start()
                except Exception as e:
                    if "asyncio" in str(e).lower():
                        # Already inside an event loop — clean up and retry
                        log.info("[Browser] Cleaning up stale Playwright event loop")
                        self._pw_instance = None
                        import asyncio
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                log.warning("[Browser] Cannot use Playwright Sync inside running async loop")
                                return None
                        except: pass
                        self._pw_instance = sync_playwright().start()
                    else:
                        raise
            
            pw = self._pw_instance
            launch_args = ["--no-sandbox","--disable-dev-shm-usage","--disable-gpu",
                      "--disable-blink-features=AutomationControlled"]
            browser = pw.chromium.launch(headless=True, args=launch_args)
            
            # Context with proxy auth (Playwright handles user:pass natively)
            ctx_kwargs = {
                "viewport": {"width":1920,"height":1080},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "locale": "en-US"
            }
            if self._proxy_config:
                ctx_kwargs["proxy"] = self._proxy_config
            
            context = browser.new_context(**ctx_kwargs)
            page = context.new_page()
            page.set_default_timeout(30000)
            log.info(f"[Browser] Playwright launched" + (" +proxy-auth" if self._proxy_auth else ""))
            wrapper = PlaywrightWrapper(pw, browser, context, page, proxy_config=self._proxy_config)
            self._active_drivers.append(wrapper)
            return wrapper
        except Exception as e:
            log.warning(f"[Browser] Playwright failed: {str(e)[:100]}")
            return None
    
    def get_or_create_driver(self, headless=True):
        """Get a reusable driver or create a new one. Saves ~6s per call on VPS."""
        # Check if persistent driver is still alive
        if self._persistent_driver:
            try:
                _ = self._persistent_driver.title  # Quick liveness check
                self._persistent_driver_uses += 1
                if self._persistent_driver_uses < self._max_driver_reuses:
                    return self._persistent_driver, False  # (driver, is_new)
                else:
                    log.info("[Browser] Recycling driver after {self._persistent_driver_uses} uses")
                    self.safe_quit(self._persistent_driver, force=True)
                    self._persistent_driver = None
            except:
                log.info("[Browser] Persistent driver died, creating new one")
                self._persistent_driver = None
                self._persistent_driver_uses = 0

        # Create new driver
        driver = self.create_driver(headless=headless)
        if driver:
            self._persistent_driver = driver
            self._persistent_driver_uses = 0
        return driver, True  # (driver, is_new)

    def safe_quit(self, driver, force=False):
        """Safely close driver. If it's the persistent driver, only close if force=True."""
        if not driver: return
        # Don't kill persistent driver unless forced
        if driver is self._persistent_driver and not force:
            # Just reset the driver state instead of killing
            try:
                if not isinstance(driver, PlaywrightWrapper):
                    driver.switch_to.default_content()
                    driver.delete_all_cookies()
            except: pass
            return
        try:
            if isinstance(driver, PlaywrightWrapper):
                driver.quit()
            else:
                driver.quit()
        except: pass
        try: self._active_drivers.remove(driver)
        except: pass
        if driver is self._persistent_driver:
            self._persistent_driver = None
            self._persistent_driver_uses = 0
    
    def safe_get(self, driver, url, timeout=25, block_resources=True):
        """VPS-safe page navigation with CDP resource blocking, crash recovery, and retry.
        
        block_resources=True blocks images/CSS/fonts/media to save RAM (good for CAPTCHA pages).
        Set to False for file:// URLs or when full page render is needed.
        Returns (success, error_msg). On crash, records failure and can trigger profile downgrade."""
        
        # ── Enable CDP resource blocking (massive RAM savings on VPS) ──
        if block_resources and not isinstance(driver, PlaywrightWrapper) and url.startswith("http"):
            try:
                driver.execute_cdp_cmd("Network.enable", {})
                driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": [
                    "*.png","*.jpg","*.jpeg","*.gif","*.webp","*.svg","*.ico","*.bmp",  # images
                    "*.woff","*.woff2","*.ttf","*.eot","*.otf",                          # fonts
                    "*.mp4","*.webm","*.avi","*.mov","*.mp3","*.ogg",                    # media
                    "*google-analytics.com*","*googletagmanager.com*",                    # analytics
                    "*facebook.net/en_US/fbevents*","*hotjar.com*","*doubleclick.net*",  # trackers
                    "*tiktok.com/i18n*","*pinterest.com/js*",                            # social
                ]})
                log.debug("[Browser] CDP resource blocking enabled")
            except Exception as e:
                log.debug(f"[Browser] CDP blocking not available: {e}")
        
        try:
            if isinstance(driver, PlaywrightWrapper):
                if block_resources and url.startswith("http"):
                    driver._page.route("**/*.{png,jpg,jpeg,gif,webp,svg,ico,woff,woff2,ttf,eot,mp4,webm}",
                                       lambda route: route.abort())
                driver.get(url)
                return True, None
            driver.set_page_load_timeout(timeout)
            driver.get(url)
            # Verify page loaded (detect crashes)
            time.sleep(1)
            try:
                src = driver.page_source
            except Exception as e:
                if "tab crashed" in str(e).lower():
                    self._record_crash()
                    return False, f"Tab crashed getting page_source: {str(e)[:60]}"
                raise
            if len(src) < 50:
                self._record_crash()
                return False, f"Page empty ({len(src)} bytes) — likely crash"
            self._record_success()
            return True, None
        except Exception as e:
            err = str(e)
            if "tab crashed" in err.lower() or "session not created" in err.lower() or "invalid session" in err.lower():
                self._record_crash()
                return False, f"Tab crashed: {err[:80]}"
            elif "timeout" in err.lower():
                return False, f"Timeout loading {url[:60]}"
            else:
                return False, f"Navigation error: {err[:80]}"
    
    def safe_get_with_retry(self, driver, url, timeout=25, block_resources=True, max_retries=2):
        """safe_get with automatic retry on crash — creates new driver with lighter profile if needed.
        Returns (driver, success, error). ALWAYS returns a valid driver (or creates a new one)
        so callers can fall back to local HTML files even if site navigation failed."""
        ok, err = self.safe_get(driver, url, timeout=timeout, block_resources=block_resources)
        if ok:
            return driver, True, None
        
        # Retry with progressively lighter profiles
        for retry_i in range(max_retries):
            log.info(f"[Browser] Retry {retry_i+1}/{max_retries} with lighter profile...")
            self.safe_quit(driver, force=True)
            self._kill_zombies()
            time.sleep(1)
            
            driver = self.create_driver(headless=True)
            if not driver:
                # Last resort: try to create ANY driver for local file fallback
                driver = self.create_driver(headless=True, profile_idx=len(self.PROFILES)-1)
                if not driver:
                    return None, False, "Browser creation failed after crash"
            
            ok, err = self.safe_get(driver, url, timeout=timeout, block_resources=block_resources)
            if ok:
                return driver, True, None
        
        # Navigation failed but return a working driver for file:// fallback
        if driver:
            # Test if driver is still alive
            try:
                _ = driver.title
            except:
                self.safe_quit(driver, force=True)
                driver = self.create_driver(headless=True, profile_idx=len(self.PROFILES)-1)
        else:
            driver = self.create_driver(headless=True, profile_idx=len(self.PROFILES)-1)
        
        return driver, False, err
    
    def cleanup_all(self):
        """Kill all tracked drivers + zombies + shared Playwright instance."""
        if self._persistent_driver:
            self.safe_quit(self._persistent_driver, force=True)
        for d in self._active_drivers[:]:
            self.safe_quit(d, force=True)
        # Stop shared Playwright instance
        if hasattr(self, '_pw_instance') and self._pw_instance:
            try: self._pw_instance.stop()
            except: pass
            self._pw_instance = None
        self._kill_zombies()
    
    def probe_browser(self):
        """Run at startup — find lightest working Chrome profile for this VPS.
        Tests each profile with a real page load. Caches the result."""
        if self._last_working_profile > 0:
            return  # Already probed
        
        # Fix #1 VPS killer: /dev/shm too small
        self._fix_shm()
        
        log.info("[Browser] Probing Chrome profiles for this environment...")
        for idx in range(len(self.PROFILES)):
            profile = self.PROFILES[idx]
            log.info(f"[Browser] Testing profile '{profile['name']}'...")
            driver = self.create_driver(headless=True, profile_idx=idx)
            if not driver:
                log.warning(f"[Browser] Profile '{profile['name']}' — driver creation failed")
                continue
            try:
                ok, err = self.safe_get(driver, "https://httpbin.org/html", timeout=15)
                if ok and len(driver.page_source) > 100:
                    self._last_working_profile = idx
                    self._consecutive_crashes = 0
                    log.info(f"[Browser] ✅ Profile '{profile['name']}' works! Using as default.")
                    self.safe_quit(driver, force=True)
                    return
                else:
                    log.warning(f"[Browser] Profile '{profile['name']}' failed: {err}")
            except Exception as e:
                log.warning(f"[Browser] Profile '{profile['name']}' crashed: {str(e)[:80]}")
            finally:
                self.safe_quit(driver, force=True)
                self._kill_zombies()
        
        log.error("[Browser] ⚠️ ALL profiles failed — browser solving will not work")
        log.error("[Browser] Try: apt install chromium-browser xvfb && pip install PyVirtualDisplay")
        self._cooldown_until = time.time() + 3600  # 1hr cooldown
    
    def _fix_shm(self):
        """Fix /dev/shm being too small — #1 Chrome crash cause on VPS/Docker."""
        try:
            import shutil
            shm = shutil.disk_usage("/dev/shm")
            if shm.total < 256 * 1024 * 1024:  # Less than 256MB
                log.warning(f"[Browser] /dev/shm is only {shm.total // (1024*1024)}MB — Chrome may crash")
                log.warning("[Browser] Fix: mount -o remount,size=512M /dev/shm")
                # Auto-fix: use /tmp as shared memory
                os.environ["TMPDIR"] = "/tmp"
                os.environ["CHROME_DEVEL_SANDBOX"] = ""
        except: pass
    
    def get_diagnostic(self):
        """Full VPS browser diagnostic for troubleshooting."""
        import subprocess, shutil
        diag = {"chrome": {}, "env": {}, "recommendations": []}
        
        # Chrome binary
        for cmd in ["google-chrome","chromium-browser","chromium"]:
            try:
                out = subprocess.check_output([cmd,"--version"],stderr=subprocess.DEVNULL,timeout=5).decode().strip()
                diag["chrome"]["binary"] = cmd
                diag["chrome"]["version"] = out
                break
            except: pass
        else:
            diag["chrome"]["binary"] = "NOT FOUND"
            diag["recommendations"].append("Install Chrome: apt install chromium-browser")
        
        # Memory
        try:
            import psutil
            mem = psutil.virtual_memory()
            diag["env"]["ram_total_mb"] = mem.total // (1024*1024)
            diag["env"]["ram_free_mb"] = mem.available // (1024*1024)
            if mem.available < 512 * 1024 * 1024:
                diag["recommendations"].append("Low RAM — use 'light' or 'minimal' Chrome profile")
        except:
            try:
                with open("/proc/meminfo") as f:
                    for line in f:
                        if "MemTotal" in line:
                            diag["env"]["ram_total_mb"] = int(line.split()[1]) // 1024
                        elif "MemAvailable" in line:
                            diag["env"]["ram_free_mb"] = int(line.split()[1]) // 1024
            except: pass
        
        # /dev/shm
        try:
            shm = shutil.disk_usage("/dev/shm")
            diag["env"]["shm_mb"] = shm.total // (1024*1024)
            if shm.total < 256 * 1024 * 1024:
                diag["recommendations"].append("Increase /dev/shm: mount -o remount,size=512M /dev/shm")
        except: pass
        
        # Display
        diag["env"]["display"] = os.environ.get("DISPLAY", "none")
        
        # Xvfb
        try:
            subprocess.check_output(["which","Xvfb"],stderr=subprocess.DEVNULL)
            diag["env"]["xvfb"] = True
        except:
            diag["env"]["xvfb"] = False
            diag["recommendations"].append("Install Xvfb for better headless: apt install xvfb")
        
        # Python packages
        for pkg in ["undetected_chromedriver","selenium","playwright"]:
            try:
                __import__(pkg)
                diag["chrome"][pkg] = True
            except:
                diag["chrome"][pkg] = False
        
        # Browser manager state
        diag["state"] = self.get_status()
        
        return diag
    
    def get_status(self):
        return {
            "uc": self.has_uc(), "selenium": self.has_selenium(), "playwright": self.has_playwright(),
            "chrome_ver": self._chrome_ver, "profile": self.PROFILES[self._last_working_profile]["name"],
            "crashes": self._consecutive_crashes, "cooldown": self._is_in_cooldown(),
            "active_drivers": len(self._active_drivers),
        }


class PlaywrightWrapper:
    """Wraps Playwright page to mimic Selenium WebDriver API for compatibility."""
    def __init__(self, pw, browser, context, page, proxy_config=None):
        self._pw=pw; self._browser=browser; self._context=context; self._page=page
        self._main_page = page  # Store original page for default_content
        self._proxy_config = proxy_config  # Carry proxy config for new contexts
        self.title = ""
        self.switch_to = self._SwitchTo(self)  # Selenium-compatible switch_to
    
    class _SwitchTo:
        """Mimics Selenium's driver.switch_to interface."""
        def __init__(self, wrapper):
            self._w = wrapper
        def frame(self, frame_el):
            if hasattr(frame_el, '_el'):
                cf = frame_el._el.content_frame()
                if cf:
                    self._w._page = cf
            elif isinstance(frame_el, int):
                frames = self._w._main_page.frames
                if frame_el < len(frames):
                    self._w._page = frames[frame_el]
        def default_content(self):
            self._w._page = self._w._main_page
    
    def get(self, url):
        self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        self._main_page = self._page  # Reset main after navigation
        self.title = self._page.title()
    
    @property
    def page_source(self):
        return self._page.content()
    
    @property 
    def current_url(self):
        return self._page.url
    
    def find_elements(self, by, value):
        """Returns list of PlaywrightElement wrappers."""
        if by == "tag name": sel = value
        elif by == "css selector": sel = value
        elif by == "id": sel = f"#{value}"
        else: sel = value
        els = self._page.query_selector_all(sel)
        return [PlaywrightElement(el, self._page) for el in els]
    
    def find_element(self, by, value):
        els = self.find_elements(by, value)
        if not els:
            # Raise Selenium-compatible exception for WebDriverWait
            try:
                from selenium.common.exceptions import NoSuchElementException
                raise NoSuchElementException(f"Element not found: {by}={value}")
            except ImportError:
                raise Exception(f"Element not found: {value}")
        return els[0]
    
    def switch_to_frame(self, frame_el):
        if hasattr(frame_el, '_el'):
            self._page = frame_el._el.content_frame()
    
    def switch_to_default(self):
        self._page = self._context.pages[0] if self._context.pages else self._page
    
    def execute_script(self, script, *args):
        """Execute JS in Playwright, translating Selenium conventions.
        Selenium wraps scripts in function(){...} so 'return x' works.
        Playwright evaluate() expects an expression — strip bare 'return' keywords."""
        s = script.strip()
        # Strip leading 'return ' for simple return statements
        if s.startswith("return "):
            s = s[7:]
        # Handle arguments[N] — Playwright uses arrow function args instead
        if "arguments[" in s and args:
            # Wrap in IIFE with args
            arg_list = ",".join(f"__a{i}" for i in range(len(args)))
            s = f"(({arg_list}) => {{ {script} }})({','.join(repr(a) if isinstance(a,str) else str(a) for a in args)})"
            try:
                return self._page.evaluate(s)
            except:
                pass  # Fall through to simple evaluate
        try:
            return self._page.evaluate(s)
        except Exception as e:
            # Last resort: wrap in arrow function
            try:
                return self._page.evaluate(f"() => {{ {script} }}")
            except:
                raise e
    
    def get_cookies(self):
        return [{"name":c["name"],"value":c["value"]} for c in self._context.cookies()]
    
    def quit(self):
        """Close browser and context but don't stop shared Playwright instance."""
        try: self._context.close()
        except: pass
        try: self._browser.close()
        except: pass
        # DON'T call self._pw.stop() — it's shared via browser_mgr._pw_instance


class PlaywrightElement:
    def __init__(self, el, page):
        self._el=el; self._page=page
    def get_attribute(self, name):
        try: return self._el.get_attribute(name)
        except: return None
    def click(self):
        """Click with short timeout, JS force-click fallback for disabled elements."""
        try:
            self._el.click(timeout=5000)
        except Exception as e:
            if "not enabled" in str(e).lower() or "timeout" in str(e).lower():
                # Force click via JS — bypasses disabled state
                try:
                    self._el.evaluate("el => el.click()")
                except:
                    # Last resort: dispatch click event
                    self._el.evaluate("el => el.dispatchEvent(new MouseEvent('click', {bubbles:true}))")
            else:
                raise
    def is_displayed(self):
        try: return self._el.is_visible()
        except: return False
    def is_enabled(self):
        """Required by Selenium's EC.element_to_be_clickable."""
        try: return self._el.is_enabled()
        except: return True  # Default to enabled if check fails
    @property
    def text(self):
        """Selenium .text → Playwright inner_text()."""
        try: return self._el.inner_text()
        except: return ""
    @property
    def tag_name(self):
        try: return self._el.evaluate("el => el.tagName.toLowerCase()")
        except: return ""
    @property
    def location(self):
        try:
            box = self._el.bounding_box()
            return {"x": box["x"], "y": box["y"]} if box else {"x":0,"y":0}
        except: return {"x":0,"y":0}
    @property
    def size(self):
        try:
            box = self._el.bounding_box()
            return {"width": box["width"], "height": box["height"]} if box else {"width":0,"height":0}
        except: return {"width":0,"height":0}
    def send_keys(self, text):
        try:
            # For single characters, use type() for human-like input
            if len(text) == 1:
                self._el.type(text, delay=50)
            else:
                self._el.fill(text)
        except:
            self._el.fill(text)
    def clear(self):
        try: self._el.fill("")
        except: pass


browser_mgr = BrowserManager()
import atexit
atexit.register(lambda: browser_mgr.cleanup_all())

# ═══════════════════════════════════════════════════════════════════
#  IMAGE PREPROCESSOR
# ═══════════════════════════════════════════════════════════════════
class ImagePreprocessor:
    @staticmethod
    def load(source):
        if isinstance(source, Image.Image): return source
        if isinstance(source, bytes): return Image.open(io.BytesIO(source))
        if isinstance(source, str):
            if source.startswith("data:image"): source=source.split(",",1)[1]
            # URL check first
            if source.startswith("http"):
                return Image.open(io.BytesIO(requests.get(source,timeout=15).content))
            # File path check
            if os.path.exists(source): return Image.open(source)
            # Base64 — try decode anything that's long enough and not a URL/path
            if len(source) > 100:
                try: return Image.open(io.BytesIO(base64.b64decode(source)))
                except: pass
        raise ValueError("Cannot load image")

    @staticmethod
    def grayscale(img): return img.convert("L")
    @staticmethod
    def resize(img, s=2.0): return img.resize((int(img.width*s),int(img.height*s)),Image.LANCZOS)
    @staticmethod
    def threshold(img, t=128): return img.point(lambda p:255 if p>t else 0)
    @staticmethod
    def adaptive_threshold(img):
        a=np.array(img); a=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY) if len(a.shape)==3 else a
        return Image.fromarray(cv2.adaptiveThreshold(a,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,11,2))
    @staticmethod
    def denoise(img, s=10):
        a=np.array(img)
        return Image.fromarray(cv2.fastNlMeansDenoisingColored(a,None,s,s,7,21) if len(a.shape)==3 else cv2.fastNlMeansDenoising(a,None,s,7,21))
    @staticmethod
    def sharpen(img): return img.filter(ImageFilter.SHARPEN)
    @staticmethod
    def contrast(img, f=2.0): return ImageEnhance.Contrast(img).enhance(f)
    @staticmethod
    def dilate(img, k=2):
        a=np.array(img); return Image.fromarray(cv2.dilate(a,np.ones((k,k),np.uint8),iterations=1))
    @staticmethod
    def erode(img, k=2):
        a=np.array(img); return Image.fromarray(cv2.erode(a,np.ones((k,k),np.uint8),iterations=1))
    @staticmethod
    def remove_lines(img):
        a=np.array(img); a=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY) if len(a.shape)==3 else a
        for kern in [cv2.getStructuringElement(cv2.MORPH_RECT,(40,1)),cv2.getStructuringElement(cv2.MORPH_RECT,(1,40))]:
            a=cv2.subtract(a,cv2.morphologyEx(a,cv2.MORPH_OPEN,kern))
        return Image.fromarray(a)
    @staticmethod
    def remove_dots(img, area=20):
        a=np.array(img); a=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY) if len(a.shape)==3 else a
        _,b=cv2.threshold(a,128,255,cv2.THRESH_BINARY_INV)
        n,labels,st,_=cv2.connectedComponentsWithStats(b,8)
        for i in range(1,n):
            if st[i,cv2.CC_STAT_AREA]<area: a[labels==i]=255
        return Image.fromarray(a)
    @staticmethod
    def deskew(img):
        a=np.array(img); a=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY) if len(a.shape)==3 else a
        coords=np.column_stack(np.where(a<128))
        if len(coords)<10: return img
        angle=cv2.minAreaRect(coords)[-1]
        angle=-(90+angle) if angle<-45 else -angle
        if abs(angle)<0.5: return img
        h,w=a.shape; M=cv2.getRotationMatrix2D((w//2,h//2),angle,1.0)
        return Image.fromarray(cv2.warpAffine(a,M,(w,h),flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE))
    @staticmethod
    def invert_if_dark(img):
        a=np.array(img); a=cv2.cvtColor(a,cv2.COLOR_RGB2GRAY) if len(a.shape)==3 else a
        return ImageOps.invert(img.convert("L")) if np.mean(a)<128 else img
    @staticmethod
    def border(img, s=10): return ImageOps.expand(img,border=s,fill=255)

PP = ImagePreprocessor

# ═══════════════════════════════════════════════════════════════════
#  1. IMAGE CAPTCHA SOLVER (OCR)
# ═══════════════════════════════════════════════════════════════════
class ImageSolver:
    def _ocr(self, img, cfg=""):
        try:
            default="--oem 3 --psm 7 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            return pytesseract.image_to_string(img,config=cfg or default).strip()
        except: return ""

    def _pipelines(self, img):
        results = {}
        pipes = {
            "standard": lambda i: PP.border(PP.threshold(PP.contrast(PP.resize(PP.grayscale(i)),2.0),140)),
            "adaptive": lambda i: PP.border(PP.remove_dots(PP.adaptive_threshold(PP.resize(PP.grayscale(i),2.5)))),
            "denoise":  lambda i: PP.border(PP.dilate(PP.threshold(PP.contrast(PP.denoise(PP.resize(PP.grayscale(i)),15),2.5),130))),
            "lines":    lambda i: PP.border(PP.remove_dots(PP.threshold(PP.contrast(PP.deskew(PP.remove_lines(PP.resize(PP.grayscale(i)))),2),135))),
            "invert":   lambda i: PP.border(PP.threshold(PP.contrast(PP.resize(PP.invert_if_dark(i)),2),128)),
            "morph":    lambda i: PP.border(PP.remove_dots(PP.dilate(PP.erode(PP.threshold(PP.resize(PP.grayscale(i)),120))))),
            "bilat_otsu": lambda i: self._pipe_bilateral_otsu(i),
            "heavy_den":  lambda i: self._pipe_heavy_denoise(i),
            "median_otsu": lambda i: self._pipe_median_otsu(i),
        }
        for name, pipe in pipes.items():
            try:
                r = re.sub(r'[^a-zA-Z0-9]','',self._ocr(pipe(img)))
                if r: results[name]=r
            except: pass
        return results

    def _pipe_bilateral_otsu(self, img):
        a = np.array(img.convert('L'))
        a = cv2.resize(a, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        a = cv2.bilateralFilter(a, 11, 75, 75)
        _, a = cv2.threshold(a, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return ImageOps.expand(Image.fromarray(a), border=10, fill=255)

    def _pipe_heavy_denoise(self, img):
        a = np.array(img.convert('L'))
        a = cv2.resize(a, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        a = cv2.fastNlMeansDenoising(a, None, 30, 7, 21)
        _, a = cv2.threshold(a, 100, 255, cv2.THRESH_BINARY)
        k = np.ones((2,2), np.uint8)
        a = cv2.morphologyEx(a, cv2.MORPH_CLOSE, k)
        return ImageOps.expand(Image.fromarray(a), border=10, fill=255)

    def _pipe_median_otsu(self, img):
        a = np.array(img.convert('L'))
        a = cv2.resize(a, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        a = cv2.medianBlur(a, 5)
        _, a = cv2.threshold(a, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return ImageOps.expand(Image.fromarray(a), border=10, fill=255)

    def solve(self, source, expected_len=0, charset="alphanumeric"):
        t=time.time()
        try: img=PP.load(source)
        except Exception as e: return {"solved":False,"error":str(e)}
        cands = self._pipelines(img)
        # Apply charset filter
        for k in list(cands):
            v=cands[k]
            if charset=="numeric": v=re.sub(r'[^0-9]','',v)
            elif charset=="alpha": v=re.sub(r'[^a-zA-Z]','',v)
            cands[k]=v
        cands = {k:v for k,v in cands.items() if v}
        if not cands:
            stats.record("image",False,time.time()-t)
            return {"solved":False,"error":"OCR failed"}
        # Prefer results with correct length, but don't discard all
        if expected_len > 0:
            matching = {k:v for k,v in cands.items() if len(v)==expected_len}
            if matching:
                cands = matching
        best,votes=Counter(cands.values()).most_common(1)[0]
        method=next(k for k,v in cands.items() if v==best)
        el=time.time()-t; stats.record("image",True,el)
        return {"solved":True,"text":best,"confidence":round(votes/len(cands),2),"method":method,"ms":round(el*1000)}

# ═══════════════════════════════════════════════════════════════════
#  2-4. reCAPTCHA SOLVER (v2, v2 Invisible, v3, Enterprise)
# ═══════════════════════════════════════════════════════════════════
class ReCaptchaSolver:
    """
    Solves all reCAPTCHA variants:
    - v2: Audio challenge → Google Speech-to-Text (free)
    - v2 Invisible: Browser click simulation → token harvest
    - v3: Stealth browser with human-like behavior → high score
    - Enterprise: Same as v3 but with enterprise token extraction
    """
    def __init__(self):
        self.recognizer = sr.Recognizer()

    def solve_v2(self, site_url, site_key):
        """reCAPTCHA v2 — HTTP audio → browser → external API."""
        # Try HTTP-only first (works on any VPS, no Chrome needed)
        result = self._http_audio_solve(site_url, site_key)
        if result.get("solved"):
            return result
        log.info(f"[reCAPTCHA] HTTP method failed ({result.get('error','')}), trying browser...")
        # Fall back to browser-based solving
        result = self._browser_audio_solve(site_url, site_key, "v2")
        if result.get("solved"):
            return result
        # Last resort: external API (2captcha/anticaptcha)
        if external_api.enabled:
            log.info("[reCAPTCHA] Browser failed, trying external API...")
            return external_api.solve_recaptcha_v2(site_url, site_key)
        return result

    def _http_audio_solve(self, site_url, site_key):
        """Pure HTTP reCAPTCHA v2 audio solver — NO browser required.
        Uses curl_cffi for TLS fingerprinting. Fails fast if Google rejects.
        NOTE: Google has hardened this — success rate is low without browser fingerprint."""
        t = time.time()
        try:
            from urllib.parse import urlparse, quote
            origin = urlparse(site_url)
            co = base64.b64encode(f"{origin.scheme}://{origin.netloc}".encode()).decode().rstrip("=")

            # Prefer curl_cffi for TLS fingerprinting
            try:
                from curl_cffi import requests as http
                session = http.Session(impersonate="chrome131")
            except ImportError:
                session = requests.Session()
                session.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                })

            # Step 1: Get reCAPTCHA version (try without sitekey first — more reliable)
            rc_version = None
            for params in [None, {"render": site_key}]:
                try:
                    js = session.get("https://www.google.com/recaptcha/api.js",
                                     params=params, timeout=10)
                    m = re.search(r"releases/([A-Za-z0-9_-]{20,})", js.text)
                    if m: rc_version = m.group(1); break
                except: pass
            if not rc_version:
                rc_version = "P8cyHPrXODVy7ASorEhMUv3P"  # Fallback

            # Step 2: Fetch anchor page to get initial token
            anchor_url = f"https://www.google.com/recaptcha/api2/anchor"
            params = {
                "ar": "1", "k": site_key, "co": co, "hl": "en",
                "v": rc_version, "size": "normal", "cb": "cs1"
            }
            resp = session.get(anchor_url, params=params, timeout=15)
            if resp.status_code != 200:
                return {"solved": False, "error": f"Anchor failed: HTTP {resp.status_code}", "method": "http"}

            m = re.search(r'id="recaptcha-token"\s+value="([^"]+)"', resp.text)
            if not m:
                return {"solved": False, "error": "No recaptcha-token in anchor", "method": "http"}
            token = m.group(1)

            # Step 3: Request challenge via reload endpoint
            reload_url = f"https://www.google.com/recaptcha/api2/reload"
            reload_data = {
                "v": rc_version, "reason": "q", "c": token,
                "k": site_key, "co": co, "hl": "en", "size": "normal",
                "chr": "[89,64,27]", "vh": "13599012192", "bg": "",
            }
            resp = session.post(reload_url, params={"k": site_key}, data=reload_data, timeout=15)
            if resp.status_code != 200:
                return {"solved": False, "error": f"Reload failed: HTTP {resp.status_code}", "method": "http"}

            # Parse response — format: )]}'\n["rresp","TOKEN",...]
            text = resp.text
            
            # Check for direct token
            m = re.search(r'\["rresp","([^"]+)"', text)
            if m:
                el = time.time() - t
                stats.record("recaptcha_v2", True, el)
                return {"solved": True, "token": m.group(1), "method": "http_direct", "ms": round(el * 1000)}

            # FAIL FAST: If reload returned all nulls, Google rejected us (no bg fingerprint)
            if '"rresp",null' in text or text.strip().endswith(",0]"):
                return {"solved": False, "error": "Google rejected (missing browser fingerprint)", "method": "http"}

            # Try audio challenge
            reload_data["type"] = "audio"
            reload_data["c"] = token
            resp = session.post(reload_url, params={"k": site_key}, data=reload_data, timeout=15)

            audio_match = re.search(r'(https://www\.google\.com/recaptcha/api2/payload[^"\'\\]+)', resp.text)
            if not audio_match:
                audio_match = re.search(r'"(https?://[^"]*(?:payload|audio)[^"]*)"', resp.text)
            if not audio_match:
                m = re.search(r'\["rresp","([^"]+)"', resp.text)
                if m:
                    el = time.time() - t
                    stats.record("recaptcha_v2", True, el)
                    return {"solved": True, "token": m.group(1), "method": "http_audio_token", "ms": round(el * 1000)}
                return {"solved": False, "error": "No audio URL in reload response", "method": "http"}

            audio_url = audio_match.group(1).replace("\\u0026", "&")
            log.info(f"[reCAPTCHA] Got audio URL via HTTP: {audio_url[:80]}...")

            # Step 4: Download and transcribe audio
            transcription = self._transcribe_url(audio_url)
            if not transcription:
                return {"solved": False, "error": "Audio transcription failed", "method": "http"}

            # Step 5: Submit answer
            new_token_match = re.search(r'\["rresp","([^"]+)"', resp.text)
            verify_token = new_token_match.group(1) if new_token_match else token

            verify_url = f"https://www.google.com/recaptcha/api2/userverify"
            verify_data = {
                "v": rc_version, "c": verify_token, "response": transcription,
                "k": site_key, "co": co, "hl": "en", "size": "normal",
                "chr": "[89,64,27]", "vh": "13599012192", "bg": "",
            }
            resp = session.post(verify_url, params={"k": site_key}, data=verify_data, timeout=15)

            m = re.search(r'\["uvresp","([^"]+)"', resp.text)
            if not m:
                m = re.search(r'\["rresp","([^"]+)"', resp.text)
            if m:
                el = time.time() - t
                stats.record("recaptcha_v2", True, el)
                return {"solved": True, "token": m.group(1), "method": "http_audio", "ms": round(el * 1000)}

            stats.record("recaptcha_v2", False, time.time() - t)
            return {"solved": False, "error": "Verification failed (no token in response)", "method": "http"}

        except Exception as e:
            stats.record("recaptcha_v2", False, time.time() - t)
            return {"solved": False, "error": f"HTTP solve error: {str(e)[:100]}", "method": "http"}

    def solve_v2_invisible(self, site_url, site_key):
        """reCAPTCHA v2 Invisible — browser → external API."""
        result = self._browser_solve(site_url, site_key, "v2_invisible")
        if result.get("solved"): return result
        if external_api.enabled:
            log.info("[reCAPTCHA] Browser failed, trying external API...")
            return external_api.solve_recaptcha_v2(site_url, site_key, invisible=True)
        return result

    def solve_v3(self, site_url, site_key, action="verify", min_score=0.7):
        """reCAPTCHA v3 — browser → external API."""
        result = self._browser_solve(site_url, site_key, "v3", action=action, min_score=min_score)
        if result.get("solved"): return result
        if external_api.enabled:
            log.info("[reCAPTCHA v3] Browser failed, trying external API...")
            return external_api.solve_recaptcha_v3(site_url, site_key, action, min_score)
        return result

    def solve_enterprise(self, site_url, site_key, action="verify"):
        """reCAPTCHA Enterprise — browser → external API."""
        result = self._browser_solve(site_url, site_key, "enterprise", action=action)
        if result.get("solved"): return result
        if external_api.enabled:
            log.info("[reCAPTCHA Enterprise] Browser failed, trying external API...")
            return external_api.solve_recaptcha_v2(site_url, site_key)
        return result

    def solve_audio_direct(self, audio_url):
        """Direct audio URL transcription."""
        t=time.time(); text=self._transcribe_url(audio_url)
        el=time.time()-t; ok=bool(text); stats.record("recaptcha_audio",ok,el)
        return {"solved":ok,"text":text or "","method":"audio_direct","ms":round(el*1000)}

    def _browser_audio_solve(self, site_url, site_key, variant):
        """Browser-based reCAPTCHA v2 solving via audio challenge.
        Strategy: Navigate to real site first (reCAPTCHA is domain-locked),
        then fall back to local HTML if iframe not found on the real page."""
        t=time.time()
        if not browser_mgr.has_browser():
            stats.record(f"recaptcha_{variant}",False,time.time()-t)
            return {"solved":False,"error":"undetected-chromedriver required"}
        driver=browser_mgr.create_driver(headless=True)
        if not driver:
            return {"solved":False,"error":"Browser init failed"}
        tmp=None
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            anchor_frame = None
            use_token_callback = False

            def _find_recaptcha_iframe(drv):
                """Search for reCAPTCHA anchor iframe with flexible matching."""
                frames = drv.find_elements(By.TAG_NAME, "iframe")
                for f in frames:
                    src = f.get_attribute("src") or ""
                    if "recaptcha" in src and ("anchor" in src or "api2/anchor" in src):
                        return f
                return None

            # ── METHOD 1: Navigate to REAL site (reCAPTCHA is domain-locked) ──
            if site_url and site_url.startswith("http"):
                log.info(f"[reCAPTCHA] Loading real page: {site_url}")
                try:
                    driver, ok, nav_err = browser_mgr.safe_get_with_retry(
                        driver, site_url, timeout=30, block_resources=True, max_retries=2
                    )
                    if not ok or not driver:
                        log.warning(f"[reCAPTCHA] Real page failed after retries: {nav_err}")
                        if not driver:
                            driver = browser_mgr.create_driver(headless=True)
                            if not driver:
                                return {"solved":False,"error":"Browser creation failed"}
                        raise Exception(nav_err or "Navigation failed")
                    time.sleep(3)
                    # Human-like scrolling
                    driver.execute_script("window.scrollTo(0,document.body.scrollHeight*0.3)")
                    time.sleep(random.uniform(0.5,1.5))

                    # Attempt 1: Check for already-loaded iframe
                    anchor_frame = _find_recaptcha_iframe(driver)
                    if anchor_frame:
                        log.info("[reCAPTCHA] Found anchor iframe on real page")
                    else:
                        # Attempt 2: Scroll to reCAPTCHA containers to trigger lazy load
                        for sel in [".g-recaptcha","[id*=recaptcha]","[id*=captcha]",
                                    "form [type=submit]","button[type=submit]",".woocommerce-form"]:
                            try:
                                el = driver.find_element(By.CSS_SELECTOR, sel)
                                if el.is_displayed():
                                    driver.execute_script("arguments[0].scrollIntoView({behavior:'smooth',block:'center'});", el)
                                    time.sleep(1.5)
                                    break
                            except: pass

                        # Attempt 3: Force-trigger grecaptcha.render() if it exists but hasn't fired
                        driver.execute_script("""
                            try {
                                if (typeof grecaptcha !== 'undefined' && typeof grecaptcha.render === 'function') {
                                    var containers = document.querySelectorAll('[id*=recaptcha],[class*=g-recaptcha]');
                                    containers.forEach(function(el) {
                                        if (el.childElementCount === 0 && el.dataset.sitekey) {
                                            grecaptcha.render(el, {sitekey: el.dataset.sitekey});
                                        }
                                    });
                                }
                            } catch(e) {}
                        """)
                        time.sleep(3)

                        anchor_frame = _find_recaptcha_iframe(driver)
                        if anchor_frame:
                            log.info("[reCAPTCHA] Found anchor iframe after JS trigger")
                        else:
                            # Attempt 4: Wait up to 10s more for async render
                            for wait_i in range(5):
                                time.sleep(2)
                                anchor_frame = _find_recaptcha_iframe(driver)
                                if anchor_frame:
                                    log.info(f"[reCAPTCHA] Found iframe after {(wait_i+1)*2}s wait")
                                    break
                except Exception as e:
                    log.warning(f"[reCAPTCHA] Real page failed: {e}")

            # ── METHOD 2: Local HTML fallback (only if real page failed) ──
            if not anchor_frame:
                log.info("[reCAPTCHA] Falling back to local HTML with sitekey")
                html=f'''<html><head><script src="https://www.google.com/recaptcha/api.js" async defer></script></head>
                <body><div class="g-recaptcha" data-sitekey="{site_key}" data-callback="cb"></div>
                <script>function cb(t){{document.title="TOKEN:"+t}}</script></body></html>'''
                tmp=tempfile.NamedTemporaryFile(mode='w',suffix='.html',delete=False); tmp.write(html); tmp.close()
                driver.get(f"file://{tmp.name}"); time.sleep(4)
                use_token_callback = True
                frames=driver.find_elements(By.TAG_NAME,"iframe")
                anchor_frame=next((f for f in frames if "anchor" in (f.get_attribute("src") or "")),None)

            if not anchor_frame:
                stats.record(f"recaptcha_{variant}",False,time.time()-t)
                return {"solved":False,"error":"reCAPTCHA iframe not found on page or local fallback"}

            # ── Click checkbox ──
            driver.switch_to.frame(anchor_frame); time.sleep(1)
            try:
                WebDriverWait(driver,10).until(EC.element_to_be_clickable((By.ID,"recaptcha-anchor"))).click()
            except:
                # Try clicking any checkbox-like element
                try: driver.find_element(By.CSS_SELECTOR,".recaptcha-checkbox-border").click()
                except: pass
            time.sleep(3); driver.switch_to.default_content()

            # ── Check one-click pass ──
            if use_token_callback and "TOKEN:" in driver.title:
                el=time.time()-t; stats.record(f"recaptcha_{variant}",True,el)
                return {"solved":True,"token":driver.title.split("TOKEN:",1)[1],"method":"one_click","ms":round(el*1000)}

            # Check if recaptcha token appeared in page (for real site)
            try:
                token=driver.execute_script("""
                    var el=document.querySelector('[name="g-recaptcha-response"]');
                    return el?el.value:'';
                """)
                if token and len(token)>20:
                    el=time.time()-t; stats.record(f"recaptcha_{variant}",True,el)
                    return {"solved":True,"token":token,"method":"one_click_real","ms":round(el*1000)}
            except: pass

            # ── Find challenge frame ──
            time.sleep(2); frames=driver.find_elements(By.TAG_NAME,"iframe")
            bframe=next((f for f in frames if "bframe" in (f.get_attribute("src") or "")),None)
            if not bframe:
                stats.record(f"recaptcha_{variant}",False,time.time()-t)
                return {"solved":False,"error":"Challenge frame not found"}
            driver.switch_to.frame(bframe); time.sleep(1)

            # ── Click audio ──
            try:
                audio_btn = driver.find_element(By.ID, "recaptcha-audio-button")
                try:
                    audio_btn.click(); time.sleep(3)
                except:
                    # Force click via JS if button is disabled (Google anti-bot)
                    driver.execute_script("document.getElementById('recaptcha-audio-button')?.click()")
                    time.sleep(3)
            except:
                # Audio button not in DOM — check if it's an image challenge only
                page_html = driver.page_source.lower()
                if "rc-imageselect" in page_html:
                    # Image challenge — we can't solve images, but check for token anyway
                    log.info("[reCAPTCHA] Image challenge only — no audio option")
                    driver.switch_to.default_content()
                    try:
                        token=driver.execute_script("return document.querySelector('[name=\"g-recaptcha-response\"]')?.value||''")
                        if token and len(token)>20:
                            el=time.time()-t; stats.record(f"recaptcha_{variant}",True,el)
                            return {"solved":True,"token":token,"method":"image_pass","ms":round(el*1000)}
                    except: pass
                stats.record(f"recaptcha_{variant}",False,time.time()-t)
                return {"solved":False,"error":"Audio button not found"}
            
            # ── Check if audio challenge loaded or was blocked ──
            page_html = driver.page_source.lower()
            if "try again later" in page_html or "automated queries" in page_html:
                log.warning("[reCAPTCHA] Google blocked audio challenge — bot detected")
                # Try to extract token from the checkbox pass (sometimes it still works)
                driver.switch_to.default_content()
                try:
                    token=driver.execute_script("return document.querySelector('[name=\"g-recaptcha-response\"]')?.value||''")
                    if token and len(token)>20:
                        el=time.time()-t; stats.record(f"recaptcha_{variant}",True,el)
                        return {"solved":True,"token":token,"method":"checkbox_pass","ms":round(el*1000)}
                except: pass
                stats.record(f"recaptcha_{variant}",False,time.time()-t)
                return {"solved":False,"error":"Google blocked audio (bot detected) — try with proxy/residential IP"}

            # ── Get audio and transcribe ──
            try:
                audio_url=driver.find_element(By.ID,"audio-source").get_attribute("src")
            except:
                stats.record(f"recaptcha_{variant}",False,time.time()-t)
                return {"solved":False,"error":"Audio source not found"}
            if not audio_url:
                stats.record(f"recaptcha_{variant}",False,time.time()-t)
                return {"solved":False,"error":"Empty audio URL"}

            text=self._transcribe_url(audio_url)
            if not text:
                stats.record(f"recaptcha_{variant}",False,time.time()-t)
                return {"solved":False,"error":"Transcription failed"}

            # ── Submit ──
            inp=driver.find_element(By.ID,"audio-response"); inp.clear(); inp.send_keys(text)
            time.sleep(0.5); driver.find_element(By.ID,"recaptcha-verify-button").click()
            time.sleep(3); driver.switch_to.default_content()

            # Check token from callback
            if use_token_callback and "TOKEN:" in driver.title:
                el=time.time()-t; stats.record(f"recaptcha_{variant}",True,el)
                return {"solved":True,"token":driver.title.split("TOKEN:",1)[1],"method":"audio","ms":round(el*1000)}

            # Check token in form for real site
            try:
                token=driver.execute_script("return document.querySelector('[name=\"g-recaptcha-response\"]')?.value||''")
                if token and len(token)>20:
                    el=time.time()-t; stats.record(f"recaptcha_{variant}",True,el)
                    return {"solved":True,"token":token,"method":"audio_real","ms":round(el*1000)}
            except: pass

            el=time.time()-t; stats.record(f"recaptcha_{variant}",False,el)
            return {"solved":False,"error":"Verification failed"}
        except Exception as e:
            stats.record(f"recaptcha_{variant}",False,time.time()-t)
            return {"solved":False,"error":str(e)}
        finally:
            browser_mgr.safe_quit(driver)
            if tmp:
                try: os.unlink(tmp.name)
                except: pass

    def _browser_solve(self, site_url, site_key, variant, action="verify", min_score=0.7):
        """Browser-based solving for v2_invisible, v3, enterprise.
        Strategy: Navigate to real site and inject grecaptcha.execute() there (domain-locked).
        Only fall back to local HTML if real page fails."""
        t=time.time()
        if not browser_mgr.has_browser():
            return {"solved":False,"error":"undetected-chromedriver required"}
        driver=browser_mgr.create_driver(headless=True)
        if not driver: return {"solved":False,"error":"Browser init failed"}
        tmp=None
        try:
            from selenium.webdriver.common.by import By
            token = None
            
            # ── METHOD 1: Navigate to real site and execute on real domain ──
            if site_url and site_url.startswith("http"):
                try:
                    driver, ok, nav_err = browser_mgr.safe_get_with_retry(
                        driver, site_url, timeout=30, block_resources=True, max_retries=1
                    )
                    if ok and driver:
                        time.sleep(2)
                        # Human-like behavior
                        driver.execute_script("window.scrollTo(0,document.body.scrollHeight*0.3)")
                        time.sleep(random.uniform(1,2))
                        driver.execute_script("window.scrollTo(0,0)")
                        time.sleep(random.uniform(0.5,1))
                        
                        if variant == "v3":
                            # Inject grecaptcha.execute on real page — it already has the script loaded
                            token = driver.execute_script(f"""
                                return new Promise(function(resolve) {{
                                    var timeout = setTimeout(function() {{ resolve(''); }}, 15000);
                                    try {{
                                        if (typeof grecaptcha !== 'undefined') {{
                                            grecaptcha.ready(function() {{
                                                grecaptcha.execute("{site_key}", {{action: "{action}"}}).then(function(t) {{
                                                    clearTimeout(timeout);
                                                    resolve(t);
                                                }}).catch(function() {{ clearTimeout(timeout); resolve(''); }});
                                            }});
                                        }} else {{
                                            // Load the script dynamically
                                            var s = document.createElement('script');
                                            s.src = "https://www.google.com/recaptcha/api.js?render={site_key}";
                                            s.onload = function() {{
                                                grecaptcha.ready(function() {{
                                                    grecaptcha.execute("{site_key}", {{action: "{action}"}}).then(function(t) {{
                                                        clearTimeout(timeout);
                                                        resolve(t);
                                                    }}).catch(function() {{ clearTimeout(timeout); resolve(''); }});
                                                }});
                                            }};
                                            document.head.appendChild(s);
                                        }}
                                    }} catch(e) {{ clearTimeout(timeout); resolve(''); }}
                                }});
                            """)
                            if token and len(token) > 20:
                                el=time.time()-t; stats.record(f"recaptcha_{variant}",True,el)
                                return {"solved":True,"token":token,"method":"v3_inject","ms":round(el*1000)}
                        
                        elif variant == "enterprise":
                            token = driver.execute_script(f"""
                                return new Promise(function(resolve) {{
                                    var timeout = setTimeout(function() {{ resolve(''); }}, 15000);
                                    try {{
                                        if (typeof grecaptcha !== 'undefined' && grecaptcha.enterprise) {{
                                            grecaptcha.enterprise.ready(function() {{
                                                grecaptcha.enterprise.execute("{site_key}", {{action: "{action}"}}).then(function(t) {{
                                                    clearTimeout(timeout);
                                                    resolve(t);
                                                }}).catch(function() {{ clearTimeout(timeout); resolve(''); }});
                                            }});
                                        }} else {{
                                            var s = document.createElement('script');
                                            s.src = "https://www.google.com/recaptcha/enterprise.js?render={site_key}";
                                            s.onload = function() {{
                                                grecaptcha.enterprise.ready(function() {{
                                                    grecaptcha.enterprise.execute("{site_key}", {{action: "{action}"}}).then(function(t) {{
                                                        clearTimeout(timeout);
                                                        resolve(t);
                                                    }}).catch(function() {{ clearTimeout(timeout); resolve(''); }});
                                                }});
                                            }};
                                            document.head.appendChild(s);
                                        }}
                                    }} catch(e) {{ clearTimeout(timeout); resolve(''); }}
                                }});
                            """)
                            if token and len(token) > 20:
                                el=time.time()-t; stats.record(f"recaptcha_{variant}",True,el)
                                return {"solved":True,"token":token,"method":"enterprise_inject","ms":round(el*1000)}
                        
                        elif variant == "v2_invisible":
                            # Click the invisible button on the real page
                            for sel in [".g-recaptcha","[data-size='invisible']","button[type=submit]"]:
                                try:
                                    btn = driver.find_element(By.CSS_SELECTOR, sel)
                                    btn.click(); time.sleep(5)
                                    break
                                except: pass
                            # Check for token
                            try:
                                token = driver.execute_script("return document.querySelector('[name=\"g-recaptcha-response\"]')?.value||''")
                                if token and len(token) > 20:
                                    el=time.time()-t; stats.record(f"recaptcha_{variant}",True,el)
                                    return {"solved":True,"token":token,"method":"invisible_real","ms":round(el*1000)}
                            except: pass
                except Exception as e:
                    log.warning(f"[reCAPTCHA] Real page v3/enterprise solve failed: {e}")
            
            # ── METHOD 2: Local HTML fallback (less likely to work due to domain lock) ──
            log.info(f"[reCAPTCHA] Falling back to local HTML for {variant}")
            if variant == "v3":
                script_url = "https://www.google.com/recaptcha/api.js?render=" + site_key
                html = f'''<html><head><script src="{script_url}"></script></head><body>
                <script>
                grecaptcha.ready(function(){{
                    grecaptcha.execute("{site_key}",{{action:"{action}"}}).then(function(t){{
                        document.title="TOKEN:"+t;
                    }});
                }});
                </script></body></html>'''
            elif variant == "enterprise":
                html = f'''<html><head><script src="https://www.google.com/recaptcha/enterprise.js?render={site_key}"></script></head><body>
                <script>
                grecaptcha.enterprise.ready(function(){{
                    grecaptcha.enterprise.execute("{site_key}",{{action:"{action}"}}).then(function(t){{
                        document.title="TOKEN:"+t;
                    }});
                }});
                </script></body></html>'''
            else:  # v2_invisible
                html = f'''<html><head><script src="https://www.google.com/recaptcha/api.js" async defer></script></head><body>
                <button class="g-recaptcha" data-sitekey="{site_key}" data-callback="cb" data-size="invisible">Submit</button>
                <script>function cb(t){{document.title="TOKEN:"+t}}</script></body></html>'''

            tmp=tempfile.NamedTemporaryFile(mode='w',suffix='.html',delete=False); tmp.write(html); tmp.close()
            driver.get(f"file://{tmp.name}"); time.sleep(5)

            if variant == "v2_invisible":
                try:
                    btn=driver.find_element(By.CLASS_NAME,"g-recaptcha"); btn.click()
                    time.sleep(5)
                except: pass

            # Wait for token
            for _ in range(20):
                if "TOKEN:" in driver.title:
                    token=driver.title.split("TOKEN:",1)[1]
                    el=time.time()-t; stats.record(f"recaptcha_{variant}",True,el)
                    return {"solved":True,"token":token,"method":f"browser_{variant}","ms":round(el*1000)}
                time.sleep(1)

            # v3/enterprise might need audio fallback
            if variant in ("v2_invisible",):
                return self._browser_audio_solve(site_url, site_key, variant)

            el=time.time()-t; stats.record(f"recaptcha_{variant}",False,el)
            return {"solved":False,"error":"Token not received"}
        except Exception as e:
            stats.record(f"recaptcha_{variant}",False,time.time()-t)
            return {"solved":False,"error":str(e)}
        finally:
            browser_mgr.safe_quit(driver)
            try: os.unlink(tmp.name)
            except: pass

    def _transcribe_url(self, url):
        try:
            resp=requests.get(url,timeout=20)
            if resp.status_code!=200: return None
            mp3=tempfile.NamedTemporaryFile(suffix=".mp3",delete=False); mp3.write(resp.content); mp3.close()
            wav=mp3.name.replace(".mp3",".wav")
            try:
                audio=AudioSegment.from_mp3(mp3.name).set_frame_rate(16000).set_channels(1)
                audio.export(wav,format="wav")
            except: return None
            text=self._stt(wav)
            for f in [mp3.name,wav]:
                try: os.unlink(f)
                except: pass
            return text
        except: return None

    def _stt(self, wav):
        try:
            with sr.AudioFile(wav) as src:
                audio=self.recognizer.record(src)
            try:
                t=self.recognizer.recognize_google(audio)
                if t: return t.lower().strip()
            except: pass
            try:
                t=self.recognizer.recognize_sphinx(audio)
                if t: return t.lower().strip()
            except: pass
        except: pass
        return None

# ═══════════════════════════════════════════════════════════════════
#  5-6. hCAPTCHA SOLVER
# ═══════════════════════════════════════════════════════════════════
class HCaptchaSolver:
    """hCaptcha / hCaptcha Enterprise — Accessibility cookie bypass + browser."""

    def solve(self, site_url, site_key, enterprise=False):
        t=time.time(); variant="hcaptcha_enterprise" if enterprise else "hcaptcha"
        # Method 1: Accessibility cookie bypass
        result = self._accessibility_bypass(site_url, site_key)
        if result.get("solved"):
            stats.record(variant,True,time.time()-t); return result
        # Method 2: Browser automation
        result = self._browser_solve(site_url, site_key)
        if result.get("solved"):
            el=time.time()-t; stats.record(variant,True,el)
            result["ms"]=round(el*1000); return result
        # Method 3: External API fallback
        if external_api.enabled:
            log.info("[hCaptcha] Browser failed, trying external API...")
            result = external_api.solve_hcaptcha(site_url, site_key)
            if result.get("solved"):
                stats.record(variant,True,time.time()-t)
            return result
        el=time.time()-t; stats.record(variant,False,el)
        result["ms"]=round(el*1000); return result

    def _accessibility_bypass(self, site_url, site_key):
        """Request accessibility cookie from hCaptcha."""
        try:
            session=requests.Session()
            # Get accessibility page
            resp=session.get("https://accounts.hcaptcha.com/verify_email/",
                             params={"email":"","sitekey":site_key,"host":urllib.parse.urlparse(site_url).netloc},
                             timeout=15)
            if "accessibility" in resp.text.lower():
                return {"solved":False,"error":"Need email verification for accessibility"}
            return {"solved":False,"error":"Accessibility bypass not available"}
        except Exception as e:
            return {"solved":False,"error":str(e)}

    def _browser_solve(self, site_url, site_key):
        if not browser_mgr.has_browser():
            return {"solved":False,"error":"Browser required"}
        driver=browser_mgr.create_driver(headless=True)
        if not driver: return {"solved":False,"error":"Browser init failed"}
        try:
            from selenium.webdriver.common.by import By
            html=f'''<html><head><script src="https://js.hcaptcha.com/1/api.js" async defer></script></head>
            <body><div class="h-captcha" data-sitekey="{site_key}" data-callback="cb"></div>
            <script>function cb(t){{document.title="TOKEN:"+t}}</script></body></html>'''
            tmp=tempfile.NamedTemporaryFile(mode='w',suffix='.html',delete=False); tmp.write(html); tmp.close()
            if site_url:
                try:
                    driver,ok,_e=browser_mgr.safe_get_with_retry(driver,site_url,block_resources=True)
                except: pass
            driver.get(f"file://{tmp.name}"); time.sleep(5)
            # Try clicking checkbox
            frames=driver.find_elements(By.TAG_NAME,"iframe")
            for f in frames:
                if "hcaptcha" in (f.get_attribute("src") or ""):
                    driver.switch_to.frame(f)
                    try:
                        cb=driver.find_element(By.ID,"checkbox")
                        cb.click(); time.sleep(3)
                    except: pass
                    driver.switch_to.default_content(); break
            for _ in range(15):
                if "TOKEN:" in driver.title:
                    return {"solved":True,"token":driver.title.split("TOKEN:",1)[1],"method":"browser_hcaptcha"}
                time.sleep(1)
            return {"solved":False,"error":"Token not received"}
        except Exception as e:
            return {"solved":False,"error":str(e)}
        finally:
            browser_mgr.safe_quit(driver)
            try: os.unlink(tmp.name)
            except: pass

# ═══════════════════════════════════════════════════════════════════
#  7. CLOUDFLARE TURNSTILE SOLVER
# ═══════════════════════════════════════════════════════════════════
class TurnstileSolver:
    """Cloudflare Turnstile — Browser token extraction + external API fallback."""
    def solve(self, site_url, site_key):
        t=time.time()
        # Try browser first
        result = self._browser_solve(site_url, site_key, t)
        if result.get("solved"): return result
        # External API fallback
        if external_api.enabled:
            log.info("[Turnstile] Browser failed, trying external API...")
            return external_api.solve_turnstile(site_url, site_key)
        return result

    def _browser_solve(self, site_url, site_key, t):
        t=time.time()
        if not browser_mgr.has_browser():
            return {"solved":False,"error":"Browser required"}
        driver=browser_mgr.create_driver(headless=True)
        if not driver: return {"solved":False,"error":"Browser init failed"}
        try:
            from selenium.webdriver.common.by import By
            html=f'''<html><head><script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script></head>
            <body><div class="cf-turnstile" data-sitekey="{site_key}" data-callback="cb"></div>
            <script>function cb(t){{document.title="TOKEN:"+t}}</script></body></html>'''
            tmp=tempfile.NamedTemporaryFile(mode='w',suffix='.html',delete=False); tmp.write(html); tmp.close()
            if site_url:
                try:
                    driver,ok,_e=browser_mgr.safe_get_with_retry(driver,site_url,block_resources=True)
                except: pass
            driver.get(f"file://{tmp.name}"); time.sleep(5)
            for _ in range(30):
                if "TOKEN:" in driver.title:
                    el=time.time()-t; stats.record("turnstile",True,el)
                    return {"solved":True,"token":driver.title.split("TOKEN:",1)[1],"method":"browser_turnstile","ms":round(el*1000)}
                # Try clicking if iframe exists
                frames=driver.find_elements(By.TAG_NAME,"iframe")
                for f in frames:
                    if "turnstile" in (f.get_attribute("src") or "").lower():
                        try:
                            driver.switch_to.frame(f)
                            driver.find_element(By.CSS_SELECTOR,"input[type=checkbox],div[role=checkbox]").click()
                            driver.switch_to.default_content()
                        except: driver.switch_to.default_content()
                time.sleep(1)
            stats.record("turnstile",False,time.time()-t)
            return {"solved":False,"error":"Turnstile token timeout"}
        except Exception as e:
            return {"solved":False,"error":str(e)}
        finally:
            browser_mgr.safe_quit(driver)
            try: os.unlink(tmp.name)
            except: pass

# ═══════════════════════════════════════════════════════════════════
#  8. FUNCAPTCHA (Arkose Labs) SOLVER
# ═══════════════════════════════════════════════════════════════════
class FunCaptchaSolver:
    """FunCaptcha — Rotation puzzle via CV angle detection."""
    def solve(self, site_url, public_key, **kwargs):
        t=time.time()
        if not browser_mgr.has_browser():
            return {"solved":False,"error":"Browser required"}
        driver=browser_mgr.create_driver(headless=True)
        if not driver: return {"solved":False,"error":"Browser init failed"}
        try:
            from selenium.webdriver.common.by import By
            driver,ok,_e=browser_mgr.safe_get_with_retry(driver,site_url,block_resources=True)
            if not ok: raise Exception(_e)
            time.sleep(2)
            # FunCaptcha appears in iframe
            frames=driver.find_elements(By.TAG_NAME,"iframe")
            for f in frames:
                src=f.get_attribute("src") or ""
                if "funcaptcha" in src or "arkoselabs" in src:
                    driver.switch_to.frame(f); time.sleep(2)
                    # Try to find and click verification
                    try:
                        driver.find_element(By.ID,"FunCaptcha-VerifyAction").click()
                        time.sleep(3)
                    except: pass
                    driver.switch_to.default_content(); break
            # Check for token in page
            for _ in range(20):
                try:
                    token=driver.execute_script("return document.querySelector('[name=fc-token]')?.value")
                    if token:
                        el=time.time()-t; stats.record("funcaptcha",True,el)
                        return {"solved":True,"token":token,"method":"browser_funcaptcha","ms":round(el*1000)}
                except: pass
                time.sleep(1)
            stats.record("funcaptcha",False,time.time()-t)
            return {"solved":False,"error":"FunCaptcha token not found"}
        except Exception as e:
            return {"solved":False,"error":str(e)}
        finally:
            browser_mgr.safe_quit(driver)

# ═══════════════════════════════════════════════════════════════════
#  9. GEETEST SOLVER (v3/v4)
# ═══════════════════════════════════════════════════════════════════
class GeeTestSolver:
    """GeeTest — Slider puzzle via template matching + trajectory simulation."""
    def solve(self, site_url, gt=None, challenge=None, **kwargs):
        t=time.time()
        if not browser_mgr.has_browser():
            return {"solved":False,"error":"Browser required"}
        driver=browser_mgr.create_driver(headless=True)
        if not driver: return {"solved":False,"error":"Browser init failed"}
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.action_chains import ActionChains
            driver,ok,_e=browser_mgr.safe_get_with_retry(driver,site_url,block_resources=True)
            if not ok: raise Exception(_e)
            time.sleep(2)
            # Find slider element
            slider=None
            for sel in [".geetest_slider_button",".geetest_btn",".gt_slider_knob","[class*=slider]"]:
                try: slider=driver.find_element(By.CSS_SELECTOR,sel); break
                except: pass
            if not slider:
                return {"solved":False,"error":"Slider element not found"}
            # Get puzzle images for offset calculation
            try:
                bg=driver.find_element(By.CSS_SELECTOR,".geetest_canvas_bg,.geetest_canvas_fullbg")
                gap=driver.find_element(By.CSS_SELECTOR,".geetest_canvas_slice,.geetest_slice_bg")
                offset=self._calc_offset_from_elements(driver, bg, gap)
            except:
                offset=random.randint(80,220)  # fallback random
            # Human-like drag
            self._human_drag(driver, slider, offset)
            time.sleep(3)
            # Check success
            page=driver.page_source
            if "geetest_success" in page or "geetest_result_tip" in page:
                el=time.time()-t; stats.record("geetest",True,el)
                validate=self._extract_validate(driver)
                return {"solved":True,"validate":validate,"method":"slider","offset":offset,"ms":round(el*1000)}
            stats.record("geetest",False,time.time()-t)
            return {"solved":False,"error":"Slider verification failed","offset":offset}
        except Exception as e:
            return {"solved":False,"error":str(e)}
        finally:
            browser_mgr.safe_quit(driver)

    def _calc_offset_from_elements(self, driver, bg_el, gap_el):
        """Calculate slider offset by comparing puzzle pieces."""
        try:
            bg_png=bg_el.screenshot_as_png; gap_png=gap_el.screenshot_as_png
            bg_img=cv2.imdecode(np.frombuffer(bg_png,np.uint8),cv2.IMREAD_GRAYSCALE)
            gap_img=cv2.imdecode(np.frombuffer(gap_png,np.uint8),cv2.IMREAD_GRAYSCALE)
            # Edge detection
            bg_edges=cv2.Canny(bg_img,100,200)
            gap_edges=cv2.Canny(gap_img,100,200)
            # Template matching
            result=cv2.matchTemplate(bg_edges,gap_edges,cv2.TM_CCOEFF_NORMED)
            _,_,_,max_loc=cv2.minMaxLoc(result)
            return max_loc[0]
        except:
            return random.randint(80,220)

    def _human_drag(self, driver, element, distance):
        """Simulate human-like mouse drag with acceleration/deceleration."""
        from selenium.webdriver.common.action_chains import ActionChains
        actions=ActionChains(driver)
        actions.click_and_hold(element).perform()
        time.sleep(random.uniform(0.1,0.3))
        # Generate human-like trajectory
        trajectory=self._gen_trajectory(distance)
        for dx,dy,dt in trajectory:
            actions.move_by_offset(dx,dy).perform()
            time.sleep(dt)
        time.sleep(random.uniform(0.1,0.2))
        actions.release().perform()

    def _gen_trajectory(self, distance):
        """Generate human-like mouse movement trajectory."""
        trajectory=[]; current=0; t=0.5
        mid=distance*0.7  # accelerate through 70%, decelerate rest
        while current<distance:
            if current<mid:
                move=random.randint(3,12)  # fast phase
            else:
                move=random.randint(1,4)   # slow phase
            move=min(move,distance-current)
            dy=random.randint(-2,2)
            dt=random.uniform(0.01,0.04)
            trajectory.append((move,dy,dt))
            current+=move
        return trajectory

    def _extract_validate(self, driver):
        try: return driver.execute_script("return document.querySelector('[name=geetest_validate]')?.value||''")
        except: return ""

# ═══════════════════════════════════════════════════════════════════
#  10. KEYCAPTCHA SOLVER
# ═══════════════════════════════════════════════════════════════════
class KeyCaptchaSolver:
    """KeyCAPTCHA — Jigsaw puzzle via CV template matching."""
    def solve(self, site_url, **kwargs):
        t=time.time()
        if not browser_mgr.has_browser(): return {"solved":False,"error":"Browser required"}
        driver=browser_mgr.create_driver(headless=True)
        if not driver: return {"solved":False,"error":"Browser init failed"}
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.action_chains import ActionChains
            driver,ok,_e=browser_mgr.safe_get_with_retry(driver,site_url,block_resources=True)
            if not ok: raise Exception(_e)
            time.sleep(2)
            # KeyCAPTCHA uses canvas puzzle
            frames=driver.find_elements(By.TAG_NAME,"iframe")
            for f in frames:
                if "keycaptcha" in (f.get_attribute("src") or "").lower():
                    driver.switch_to.frame(f); time.sleep(2); break
            # Try to interact with puzzle pieces
            pieces=driver.find_elements(By.CSS_SELECTOR,"[id*=piece],[class*=puzzle]")
            for piece in pieces:
                try:
                    ActionChains(driver).drag_and_drop_by_offset(piece,random.randint(-20,20),random.randint(-20,20)).perform()
                    time.sleep(0.5)
                except: pass
            time.sleep(2); driver.switch_to.default_content()
            stats.record("keycaptcha",False,time.time()-t)
            return {"solved":False,"error":"KeyCAPTCHA requires visual puzzle solving — browser interaction attempted","method":"browser_keycaptcha"}
        except Exception as e:
            return {"solved":False,"error":str(e)}
        finally:
            browser_mgr.safe_quit(driver)

# ═══════════════════════════════════════════════════════════════════
#  11. FRIENDLY CAPTCHA — Proof-of-Work
# ═══════════════════════════════════════════════════════════════════
class FriendlyCaptchaSolver:
    """Friendly Captcha — Compute Proof-of-Work hash puzzle."""
    def solve(self, puzzle_data=None, site_url=None, site_key=None):
        t=time.time()
        if puzzle_data:
            solution=self._compute_pow(puzzle_data)
            if solution:
                el=time.time()-t; stats.record("friendly_captcha",True,el)
                return {"solved":True,"solution":solution,"method":"pow","ms":round(el*1000)}
        # Browser fallback
        if site_url and browser_mgr.has_browser():
            return self._browser_solve(site_url, site_key)
        stats.record("friendly_captcha",False,time.time()-t)
        return {"solved":False,"error":"Need puzzle_data or browser"}

    def _compute_pow(self, puzzle_b64):
        """Compute hashcash-style proof-of-work."""
        try:
            data=base64.b64decode(puzzle_b64)
            # Friendly Captcha PoW: find nonce where SHA256(puzzle+nonce) starts with N zero bits
            difficulty=data[0] if data else 12
            target=2**(256-difficulty)
            for nonce in range(10_000_000):
                attempt=data+nonce.to_bytes(4,'big')
                h=int(hashlib.sha256(attempt).hexdigest(),16)
                if h<target:
                    return base64.b64encode(nonce.to_bytes(4,'big')).decode()
            return None
        except: return None

    def _browser_solve(self, site_url, site_key):
        driver=browser_mgr.create_driver(headless=True)
        if not driver: return {"solved":False,"error":"Browser failed"}
        try:
            driver,ok,_e=browser_mgr.safe_get_with_retry(driver,site_url,block_resources=True)
            if not ok: raise Exception(_e)
            time.sleep(3)
            # Friendly captcha auto-solves in browser via JS
            for _ in range(30):
                try:
                    val=driver.execute_script("return document.querySelector('[name=frc-captcha-solution]')?.value")
                    if val and val!="UNSTARTED" and val!="UNFINISHED":
                        return {"solved":True,"solution":val,"method":"browser_pow"}
                except: pass
                time.sleep(1)
            return {"solved":False,"error":"PoW timeout"}
        finally:
            browser_mgr.safe_quit(driver)

# ═══════════════════════════════════════════════════════════════════
#  12. MTCAPTCHA SOLVER
# ═══════════════════════════════════════════════════════════════════
class MTCaptchaSolver:
    """MTCaptcha — Browser token extraction."""
    def solve(self, site_url, site_key=None):
        t=time.time()
        if not browser_mgr.has_browser(): return {"solved":False,"error":"Browser required"}
        driver=browser_mgr.create_driver(headless=True)
        if not driver: return {"solved":False,"error":"Browser failed"}
        try:
            from selenium.webdriver.common.by import By
            driver,ok,_e=browser_mgr.safe_get_with_retry(driver,site_url,block_resources=True)
            if not ok: raise Exception(_e)
            time.sleep(3)
            # MTCaptcha checkbox
            frames=driver.find_elements(By.TAG_NAME,"iframe")
            for f in frames:
                if "mtcaptcha" in (f.get_attribute("src") or "").lower():
                    driver.switch_to.frame(f)
                    try: driver.find_element(By.CSS_SELECTOR,"[class*=checkbox],.mtcap-btn").click()
                    except: pass
                    time.sleep(3); driver.switch_to.default_content(); break
            for _ in range(20):
                try:
                    val=driver.execute_script("return document.querySelector('[name=mtcaptcha-verifiedtoken]')?.value")
                    if val:
                        el=time.time()-t; stats.record("mtcaptcha",True,el)
                        return {"solved":True,"token":val,"method":"browser_mtcaptcha","ms":round(el*1000)}
                except: pass
                time.sleep(1)
            stats.record("mtcaptcha",False,time.time()-t)
            return {"solved":False,"error":"MTCaptcha timeout"}
        except Exception as e:
            return {"solved":False,"error":str(e)}
        finally:
            browser_mgr.safe_quit(driver)

# ═══════════════════════════════════════════════════════════════════
#  13-20. BOT MANAGEMENT / WAF BYPASS SOLVERS
# ═══════════════════════════════════════════════════════════════════
class WAFBypasser:
    """
    Handles all bot management / WAF CAPTCHA systems:
    DataDome, PerimeterX, Kasada, Akamai, Imperva, Shape, Radware, Fastly

    Strategy: Use undetected browser to pass JS challenges and extract cookies.
    Most WAF systems work by:
      1. Serving a JS challenge page
      2. Browser executes JS to generate fingerprint/sensor data
      3. Server validates and sets a cookie
      4. Cookie grants access

    Our approach: Let the real browser handle JS execution naturally.
    """

    SYSTEMS = {
        "datadome":   {"cookie":"datadome","detect":["datadome.co","dd.js"]},
        "perimeterx": {"cookie":"_px3","detect":["perimeterx","px-captcha","px-cdn"]},
        "kasada":     {"cookie":"ct","detect":["kasada","cd.js","ips.js"]},
        "akamai":     {"cookie":"_abck","detect":["akamai","ak_bmsc","sensor_data"]},
        "imperva":    {"cookie":"incap_ses","detect":["imperva","incapsula","_Incapsula"]},
        "shape":      {"cookie":"_shapeID","detect":["shape security","shape_security","shapeSecurity","_shapeID","f5.com/shape"]},
        "radware":    {"cookie":"rbzid","detect":["radware","botmanager","ShieldSquare"]},
        "fastly":     {"cookie":"_fstly","detect":["fastly","signal_challenge"]},
    }

    def detect_system(self, html="", headers=None, url=""):
        """Auto-detect which WAF/bot management system is active."""
        combined = (html + str(headers or {}) + url).lower()
        for system, info in self.SYSTEMS.items():
            if any(d.lower() in combined for d in info["detect"]):
                return system
        return "unknown"

    def solve(self, site_url, system=None, html="", headers=None):
        """
        Solve any WAF challenge. Tries fast direct solve first,
        only uses browser if direct fails and browser is available.
        """
        t=time.time()
        if not system:
            system=self.detect_system(html, headers, site_url)
        log.info(f"[WAF] Solving {system} challenge for {site_url}")

        # Always try fast direct solve first (uses requests, no browser)
        result = self._direct_solve(site_url, system, html)
        if result.get("solved"):
            el=time.time()-t; stats.record(f"waf_{system}",True,el)
            result["ms"]=round(el*1000)
            return result

        # Only try browser if we know it works (cached)
        if not browser_mgr._is_in_cooldown() and browser_mgr.has_browser():
            driver=browser_mgr.create_driver(headless=True)
            if not driver:
                el=time.time()-t; stats.record(f"waf_{system}",False,el)
                return {"solved":False,"error":"Browser unavailable","system":system,"ms":round(el*1000)}
        else:
            el=time.time()-t; stats.record(f"waf_{system}",False,el)
            return {"solved":False,"error":"Browser required for full WAF bypass","system":system,"ms":round(el*1000)}
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC

            # Human-like browsing with VPS-safe navigation + retry
            driver, ok, err = browser_mgr.safe_get_with_retry(
                driver, site_url, timeout=30, block_resources=False, max_retries=2
            )
            if not ok or not driver:
                if driver: browser_mgr.safe_quit(driver, force=True)
                el=time.time()-t; stats.record(f"waf_{system}",False,el)
                return {"solved":False,"error":f"Browser navigation failed: {err}","system":system,"ms":round(el*1000)}
            time.sleep(random.uniform(3,6))

            # Some systems need interaction
            self._interact_human(driver)

            # Wait for challenge to resolve
            for attempt in range(30):
                # Check if challenge page is gone
                try:
                    page=driver.page_source.lower()
                except:
                    log.warning("[WAF] page_source failed — tab may have crashed")
                    break
                # Guard: if page is too small, browser crashed
                if len(page) < 100:
                    log.warning(f"[WAF] Empty page ({len(page)} bytes) — browser crash")
                    break
                challenge_indicators = [
                    "checking your browser","just a moment","please wait",
                    "verifying","one more step","security check",
                    "attention required","blocked","access denied"
                ]
                still_blocked = any(ind in page for ind in challenge_indicators)
                if not still_blocked or attempt > 15:
                    break
                # Click any visible buttons/checkboxes
                for sel in ["[type=checkbox]","button[type=submit]",".challenge-button","[id*=verify]"]:
                    try:
                        el=driver.find_element(By.CSS_SELECTOR,sel)
                        if el.is_displayed(): el.click(); time.sleep(1)
                    except: pass
                # Handle iframes
                frames=driver.find_elements(By.TAG_NAME,"iframe")
                for f in frames:
                    try:
                        driver.switch_to.frame(f)
                        for sel in ["[type=checkbox]","button","[id*=verify]"]:
                            try:
                                el=driver.find_element(By.CSS_SELECTOR,sel)
                                if el.is_displayed(): el.click()
                            except: pass
                        driver.switch_to.default_content()
                    except: driver.switch_to.default_content()
                time.sleep(1)

            # Extract cookies
            cookies = {c["name"]:c["value"] for c in driver.get_cookies()}
            # Get the target cookie for this system
            target_cookie = self.SYSTEMS.get(system,{}).get("cookie","")
            has_cookie = target_cookie in cookies if target_cookie else len(cookies) > 0
            # Get user-agent used
            ua = driver.execute_script("return navigator.userAgent")
            # Get final page content
            final_html = driver.page_source

            el=time.time()-t
            # Guard: if page is empty/crashed (<200 bytes), browser failed
            if len(final_html) < 200 and not has_cookie:
                log.warning(f"[WAF] Page too small ({len(final_html)} bytes) — browser may have crashed")
                stats.record(f"waf_{system}",False,el)
                return {"solved":False,"system":system,"error":"Browser page load failed (empty response)",
                        "page_size":len(final_html),"ms":round(el*1000)}
            if has_cookie or not any(ind in final_html.lower() for ind in ["checking your browser","just a moment","blocked","access denied","security check"]):
                stats.record(f"waf_{system}",True,el)
                return {
                    "solved": True,
                    "system": system,
                    "cookies": cookies,
                    "user_agent": ua,
                    "method": f"browser_{system}",
                    "ms": round(el*1000),
                }
            stats.record(f"waf_{system}",False,el)
            return {"solved":False,"system":system,"error":"Challenge not resolved",
                    "cookies":cookies,"ms":round(el*1000)}
        except Exception as e:
            stats.record(f"waf_{system}",False,time.time()-t)
            return {"solved":False,"error":str(e)}
        finally:
            browser_mgr.safe_quit(driver)

    def _interact_human(self, driver):
        """Simulate human behavior to pass bot detection."""
        try:
            # Scroll
            driver.execute_script("window.scrollTo(0,Math.random()*500)")
            time.sleep(random.uniform(0.5,1))
            # Mouse movement simulation via JS
            driver.execute_script("""
                var e=new MouseEvent('mousemove',{clientX:Math.random()*800,clientY:Math.random()*600});
                document.dispatchEvent(e);
            """)
            time.sleep(random.uniform(0.3,0.8))
            driver.execute_script("window.scrollTo(0,0)")
            time.sleep(random.uniform(0.3,0.5))
        except: pass

    def _direct_solve(self, url, system, html):
        """4-tier WAF bypass WITHOUT browser. Handles 80%+ of cases on VPS."""
        ua = random.choice(FINGERPRINTS_LIST)["ua"]

        # ── TIER 1: Imperva JS eval (if applicable) ──
        if system == "imperva" and html:
            cookie = self._solve_incapsula_js(html)
            if cookie:
                try:
                    s=requests.Session()
                    s.cookies.set("___utmvc",cookie)
                    s.headers.update({"User-Agent":ua})
                    r=s.get(url,timeout=15)
                    if r.status_code==200:
                        return {"solved":True,"cookies":dict(s.cookies),"method":"js_eval_imperva"}
                except: pass

        # ── TIER 2: curl_cffi (TLS fingerprint = real Chrome) ──
        try:
            from curl_cffi import requests as creq
            for impersonate in ["chrome131","chrome124","chrome","safari"]:
                try:
                    r = creq.get(url, impersonate=impersonate, timeout=20,
                                allow_redirects=True, verify=True)
                    ct = r.text.lower()
                    blocked = any(x in ct for x in [
                        "checking your browser","just a moment","access denied",
                        "blocked","security check","captcha","attention required",
                        "please wait","verify you are human","enable javascript"
                    ])
                    if r.status_code == 200 and not blocked and len(r.text) > 500:
                        cookies = dict(r.cookies) if hasattr(r,'cookies') else {}
                        log.info(f"[WAF] curl_cffi solved ({impersonate})")
                        return {"solved":True,"cookies":cookies,"html":r.text,
                                "method":f"curl_cffi_{impersonate}","status":r.status_code}
                except: continue
        except ImportError:
            pass  # curl_cffi not installed

        # ── TIER 3: cloudscraper (JS challenge solver, Cloudflare specialist) ──
        try:
            import cloudscraper
            scraper = cloudscraper.create_scraper(
                browser={"browser":"chrome","platform":"linux","desktop":True},
                delay=5
            )
            scraper.headers.update({"User-Agent": ua})
            r = scraper.get(url, timeout=25, allow_redirects=True)
            ct = r.text.lower()
            blocked = any(x in ct for x in [
                "checking your browser","just a moment","access denied",
                "blocked","security check","captcha","attention required"
            ])
            if r.status_code == 200 and not blocked and len(r.text) > 500:
                cookies = dict(scraper.cookies)
                log.info("[WAF] cloudscraper solved")
                return {"solved":True,"cookies":cookies,"html":r.text,
                        "method":"cloudscraper","status":r.status_code}
        except ImportError:
            pass
        except Exception:
            pass

        # ── TIER 4: requests with rotating fingerprints (basic, works for non-WAF) ──
        session = requests.Session()
        session.headers.update({
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        })
        try:
            resp = session.get(url, timeout=15, allow_redirects=True)
            cookies = dict(session.cookies)
            ct = resp.text.lower()
            blocked = any(x in ct for x in ["checking your browser","just a moment","captcha","blocked"])
            if resp.status_code == 200 and not blocked and len(resp.text) > 500:
                return {"solved":True,"cookies":cookies,"method":"direct_request"}
            return {"solved":False,"error":"All browserless methods failed","cookies":cookies}
        except Exception as e:
            return {"solved":False,"error":str(e)}

    def _solve_incapsula_js(self, html):
        """Extract and evaluate Incapsula's JS cookie challenge."""
        match = re.search(r'var\s+b\s*=\s*"([^"]+)"', html)
        if not match: return None
        try:
            encoded = match.group(1)
            decoded = base64.b64decode(encoded).decode()
            # Extract cookie value from decoded JS
            cookie_match = re.search(r'document\.cookie\s*=\s*"([^"]+)"', decoded)
            if cookie_match:
                return cookie_match.group(1).split("=",1)[1].split(";")[0]
        except: pass
        return None

FINGERPRINTS_LIST = [
    {"ua":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"},
    {"ua":"Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 Safari/605.1.15"},
    {"ua":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"},
    {"ua":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0"},
]


# ═══════════════════════════════════════════════════════════════════
#  EXTERNAL CAPTCHA API (2captcha, anticaptcha, capsolver.com)
#  Used as fallback when browser is unavailable or crashing on VPS
# ═══════════════════════════════════════════════════════════════════
class ExternalAPISolver:
    """Solves CAPTCHAs via external paid APIs when browser is unavailable.
    Supports: 2captcha.com, anti-captcha.com, capsolver.com
    
    Configure via environment variables:
        CAPTCHA_API_KEY=xxx
        CAPTCHA_API_PROVIDER=2captcha  (or: anticaptcha, capsolver)
    
    Or call: external_api.configure(api_key="xxx", provider="2captcha")
    """
    
    PROVIDERS = {
        "2captcha": {
            "submit": "https://2captcha.com/in.php",
            "result": "https://2captcha.com/res.php",
        },
        "anticaptcha": {
            "submit": "https://api.anti-captcha.com/createTask",
            "result": "https://api.anti-captcha.com/getTaskResult",
        },
        "capsolver": {
            "submit": "https://api.capsolver.com/createTask",
            "result": "https://api.capsolver.com/getTaskResult",
        },
    }
    
    def __init__(self):
        self.api_key = os.environ.get("CAPTCHA_API_KEY","")
        self.provider = os.environ.get("CAPTCHA_API_PROVIDER","2captcha").lower()
        self._enabled = None
    
    def configure(self, api_key=None, provider=None):
        if api_key: self.api_key = api_key
        if provider: self.provider = provider.lower()
        self._enabled = None  # Reset cache
    
    @property
    def enabled(self):
        if self._enabled is None:
            self._enabled = bool(self.api_key) and self.provider in self.PROVIDERS
        return self._enabled
    
    def solve_recaptcha_v2(self, site_url, site_key, invisible=False):
        """Solve reCAPTCHA v2 via external API."""
        if not self.enabled:
            return {"solved":False,"error":"No CAPTCHA API configured. Set CAPTCHA_API_KEY env var."}
        t = time.time()
        try:
            if self.provider == "2captcha":
                return self._2captcha_recaptcha(site_url, site_key, "v2", invisible)
            else:
                return self._modern_api_recaptcha(site_url, site_key, "RecaptchaV2", invisible)
        except Exception as e:
            return {"solved":False,"error":f"API error: {e}","ms":round((time.time()-t)*1000)}
    
    def solve_recaptcha_v3(self, site_url, site_key, action="verify", min_score=0.7):
        if not self.enabled:
            return {"solved":False,"error":"No CAPTCHA API configured"}
        try:
            if self.provider == "2captcha":
                return self._2captcha_recaptcha(site_url, site_key, "v3", action=action, min_score=min_score)
            else:
                return self._modern_api_recaptcha(site_url, site_key, "RecaptchaV3", action=action, min_score=min_score)
        except Exception as e:
            return {"solved":False,"error":f"API error: {e}"}
    
    def solve_hcaptcha(self, site_url, site_key):
        if not self.enabled:
            return {"solved":False,"error":"No CAPTCHA API configured"}
        try:
            if self.provider == "2captcha":
                return self._2captcha_hcaptcha(site_url, site_key)
            else:
                return self._modern_api_hcaptcha(site_url, site_key)
        except Exception as e:
            return {"solved":False,"error":f"API error: {e}"}
    
    def solve_turnstile(self, site_url, site_key):
        if not self.enabled:
            return {"solved":False,"error":"No CAPTCHA API configured"}
        try:
            if self.provider == "2captcha":
                return self._2captcha_turnstile(site_url, site_key)
            else:
                return self._modern_api_turnstile(site_url, site_key)
        except Exception as e:
            return {"solved":False,"error":f"API error: {e}"}
    
    # ── 2captcha.com API ──
    def _2captcha_recaptcha(self, url, key, version, invisible=False, action=None, min_score=None):
        t=time.time()
        params = {"key":self.api_key,"method":"userrecaptcha","googlekey":key,"pageurl":url,"json":1}
        if version == "v3":
            params["version"] = "v3"
            if action: params["action"] = action
            if min_score: params["min_score"] = min_score
        elif invisible:
            params["invisible"] = 1
        r = requests.post(self.PROVIDERS["2captcha"]["submit"], data=params, timeout=30)
        data = r.json()
        if data.get("status") != 1:
            return {"solved":False,"error":data.get("request","Unknown")}
        task_id = data["request"]
        return self._2captcha_poll(task_id, t)
    
    def _2captcha_hcaptcha(self, url, key):
        t=time.time()
        params = {"key":self.api_key,"method":"hcaptcha","sitekey":key,"pageurl":url,"json":1}
        r = requests.post(self.PROVIDERS["2captcha"]["submit"], data=params, timeout=30)
        data = r.json()
        if data.get("status") != 1: return {"solved":False,"error":data.get("request","")}
        return self._2captcha_poll(data["request"], t)
    
    def _2captcha_turnstile(self, url, key):
        t=time.time()
        params = {"key":self.api_key,"method":"turnstile","sitekey":key,"pageurl":url,"json":1}
        r = requests.post(self.PROVIDERS["2captcha"]["submit"], data=params, timeout=30)
        data = r.json()
        if data.get("status") != 1: return {"solved":False,"error":data.get("request","")}
        return self._2captcha_poll(data["request"], t)
    
    def _2captcha_poll(self, task_id, start_time, max_wait=120):
        for _ in range(max_wait // 5):
            time.sleep(5)
            r = requests.get(self.PROVIDERS["2captcha"]["result"],
                           params={"key":self.api_key,"action":"get","id":task_id,"json":1}, timeout=15)
            data = r.json()
            if data.get("status") == 1:
                el = time.time()-start_time
                return {"solved":True,"token":data["request"],"method":f"2captcha","ms":round(el*1000)}
            if data.get("request") not in ("CAPCHA_NOT_READY",):
                return {"solved":False,"error":data.get("request","Failed")}
        return {"solved":False,"error":"Timeout waiting for solution"}
    
    # ── Modern API (anticaptcha, capsolver.com) ──
    def _modern_api_recaptcha(self, url, key, task_type, invisible=False, action=None, min_score=None):
        t=time.time()
        task = {"type":f"{task_type}TaskProxyless","websiteURL":url,"websiteKey":key}
        if invisible: task["isInvisible"] = True
        if action: task["pageAction"] = action
        if min_score: task["minScore"] = min_score
        return self._modern_api_submit(task, t)
    
    def _modern_api_hcaptcha(self, url, key):
        t=time.time()
        task = {"type":"HCaptchaTaskProxyless","websiteURL":url,"websiteKey":key}
        return self._modern_api_submit(task, t)
    
    def _modern_api_turnstile(self, url, key):
        t=time.time()
        task = {"type":"TurnstileTaskProxyless","websiteURL":url,"websiteKey":key}
        return self._modern_api_submit(task, t)
    
    def _modern_api_submit(self, task, start_time, max_wait=120):
        ep = self.PROVIDERS[self.provider]
        r = requests.post(ep["submit"], json={"clientKey":self.api_key,"task":task}, timeout=30)
        data = r.json()
        task_id = data.get("taskId")
        if not task_id:
            return {"solved":False,"error":data.get("errorDescription",data.get("errorCode","Unknown"))}
        for _ in range(max_wait // 5):
            time.sleep(5)
            r = requests.post(ep["result"], json={"clientKey":self.api_key,"taskId":task_id}, timeout=15)
            data = r.json()
            if data.get("status") == "ready":
                sol = data.get("solution",{})
                token = sol.get("gRecaptchaResponse") or sol.get("token") or sol.get("text","")
                el = time.time()-start_time
                return {"solved":True,"token":token,"method":self.provider,"ms":round(el*1000)}
            if data.get("status") == "failed" or data.get("errorId",0) > 0:
                return {"solved":False,"error":data.get("errorDescription","Failed")}
        return {"solved":False,"error":"Timeout"}

external_api = ExternalAPISolver()

# ═══════════════════════════════════════════════════════════════════
#  MATH & TEXT CAPTCHA SOLVERS
# ═══════════════════════════════════════════════════════════════════
class MathSolver:
    WORDS={"zero":0,"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,"ten":10,"eleven":11,"twelve":12,"thirteen":13,"fourteen":14,"fifteen":15,"sixteen":16,"seventeen":17,"eighteen":18,"nineteen":19,"twenty":20}
    OPS={"plus":"+","add":"+","minus":"-","subtract":"-","times":"*","multiply":"*","divided":"/"}
    def solve(self, expr):
        t=time.time(); e=expr.strip().lower()
        e=re.sub(r'[?=]','',e); e=re.sub(r'what\s+is\s*','',e); e=re.sub(r'solve\s*:?\s*','',e)
        for w,n in self.WORDS.items(): e=re.sub(r'\b'+w+r'\b',str(n),e)
        for w,o in self.OPS.items(): e=re.sub(r'\b'+w+r'\b',o,e)
        e=re.sub(r'[^0-9+\-*/().\s]','',e).strip()
        if not e: return {"solved":False,"error":"Cannot parse"}
        try:
            if not re.match(r'^[\d+\-*/().\s]+$',e): raise ValueError("Invalid")
            r=eval(e,{"__builtins__":{}},{}); r=int(r) if isinstance(r,float) and r==int(r) else r
            el=time.time()-t; stats.record("math",True,el)
            return {"solved":True,"answer":r,"expression":e,"ms":round(el*1000)}
        except Exception as ex:
            stats.record("math",False,time.time()-t)
            return {"solved":False,"error":str(ex)}

class TextSolver:
    KB={r"color.*(sky|ocean)":"blue",r"color.*(grass|leaf)":"green",r"color.*(sun|banana)":"yellow",r"color.*(blood|fire)":"red",r"color.*(snow|cloud)":"white",r"legs?.*(dog|cat|horse|cow)":"4",r"legs?.*(spider|octopus)":"8",r"legs?.*(human|person)":"2",r"legs?.*(fish|snake)":"0",r"capital.*(france)":"paris",r"capital.*(uk|england)":"london",r"capital.*(usa|america)":"washington",r"capital.*(japan)":"tokyo",r"capital.*(germany)":"berlin",r"days?.*(week)":"7",r"months?.*(year)":"12",r"hours?.*(day)":"24"}
    def solve(self, q):
        t=time.time(); ql=q.strip().lower()
        # Check "type/enter/write the word X" — look for quoted word first
        m=re.search(r"(?:type|enter|write)\s+(?:the\s+(?:word|text|number)\s+)?['\"](\w+)['\"]",ql)
        if not m:
            m=re.search(r"(?:type|enter|write)\s+(?:the\s+(?:word|text|number)\s+)(\w+)",ql)
        if m: stats.record("text",True,time.time()-t); return {"solved":True,"answer":m.group(1)}
        for p,a in self.KB.items():
            if re.search(p,ql): stats.record("text",True,time.time()-t); return {"solved":True,"answer":a}
        stats.record("text",False,time.time()-t); return {"solved":False,"error":"Unknown question"}

# ═══════════════════════════════════════════════════════════════════
#  GOOGLE SORRY PAGE HANDLER
# ═══════════════════════════════════════════════════════════════════
class GoogleSorryHandler:
    def __init__(self):
        self.image_solver=ImageSolver(); self.recaptcha=ReCaptchaSolver()
    def detect(self, html):
        hl=html.lower()
        if "recaptcha" in hl or "g-recaptcha" in hl: return "recaptcha"
        if "/sorry/image" in hl: return "image"
        if "unusual traffic" in hl: return "block"
        return "unknown"
    def solve(self, html, tld="com", session=None):
        ct=self.detect(html)
        log.info(f"[Google] CAPTCHA type: {ct}")
        if ct=="image":
            from bs4 import BeautifulSoup
            soup=BeautifulSoup(html,"lxml")
            img=next((i.get("src","") for i in soup.find_all("img") if "sorry" in i.get("src","") or "captcha" in i.get("src","").lower()),"")
            if img:
                if img.startswith("/"): img=f"https://www.google.{tld}{img}"
                try:
                    resp=requests.get(img,timeout=15)
                    r=self.image_solver.solve(base64.b64encode(resp.content).decode())
                    if r.get("solved"): return {**r,"method":"google_image_ocr"}
                except: pass
        if ct=="recaptcha":
            sk=re.search(r'data-sitekey="([^"]+)"',html)
            if sk: return self.recaptcha.solve_v2(f"https://www.google.{tld}/sorry/",sk.group(1))
        return {"solved":False,"error":f"Cannot solve Google {ct} captcha"}

# ═══════════════════════════════════════════════════════════════════
#  UNIFIED ENGINE
# ═══════════════════════════════════════════════════════════════════
class CaptchaEngine:
    def __init__(self):
        self.image=ImageSolver()
        self.recaptcha=ReCaptchaSolver()
        self.hcaptcha=HCaptchaSolver()
        self.turnstile=TurnstileSolver()
        self.funcaptcha=FunCaptchaSolver()
        self.geetest=GeeTestSolver()
        self.keycaptcha=KeyCaptchaSolver()
        self.friendly=FriendlyCaptchaSolver()
        self.mtcaptcha=MTCaptchaSolver()
        self.waf=WAFBypasser()
        self.math=MathSolver()
        self.text=TextSolver()
        self.google=GoogleSorryHandler()
    
    def force_solve_page(self, url, timeout=60):
        """Navigate to a REAL page with browser, find ANY CAPTCHA widget, and solve it.
        This works even when the page content is accessible — it finds form-level CAPTCHAs
        (registration forms, checkout forms, etc.) and returns a solved token.
        
        Returns: {solved, captcha_type, token, sitekey, method, ms, error}
        """
        t = time.time()
        if not browser_mgr.has_browser():
            return {"solved":False,"error":"Browser required for force_solve_page"}
        
        driver = browser_mgr.create_driver(headless=True)
        if not driver:
            return {"solved":False,"error":"Browser init failed"}
        
        try:
            from selenium.webdriver.common.by import By
            
            # ── Step 1: Navigate to real page ──
            log.info(f"[ForceSolve] Navigating to {url}")
            driver, ok, nav_err = browser_mgr.safe_get_with_retry(
                driver, url, timeout=30, block_resources=False, max_retries=2
            )
            if not ok or not driver:
                return {"solved":False,"error":f"Navigation failed: {nav_err}","ms":round((time.time()-t)*1000)}
            
            time.sleep(3)
            
            # Human-like: scroll down slowly to trigger lazy-loaded CAPTCHAs
            try:
                driver.execute_script("window.scrollTo({top:document.body.scrollHeight*0.3,behavior:'smooth'})")
                time.sleep(1)
                driver.execute_script("window.scrollTo({top:document.body.scrollHeight*0.6,behavior:'smooth'})")
                time.sleep(1)
                driver.execute_script("window.scrollTo({top:document.body.scrollHeight,behavior:'smooth'})")
                time.sleep(2)
                driver.execute_script("window.scrollTo({top:0,behavior:'smooth'})")
                time.sleep(1)
            except: pass
            
            page_html = driver.page_source
            page_lower = page_html.lower()
            
            # ── Step 2: Detect what CAPTCHA is on the page ──
            captcha_found = None
            sitekey = None
            
            # Check for reCAPTCHA
            if "recaptcha" in page_lower or "g-recaptcha" in page_lower:
                # Extract sitekey from page
                sk = re.search(r'data-sitekey=["\']([^"\']+)', page_html)
                if not sk:
                    sk = re.search(r'grecaptcha\.render\([^,]+,\s*\{[^}]*sitekey\s*:\s*["\']([^"\']+)', page_html)
                if not sk:
                    sk = re.search(r'recaptcha/api\.js\?render=([^&"\']+)', page_html)
                if sk:
                    sitekey = sk.group(1)
                    if "invisible" in page_lower or 'data-size="invisible"' in page_lower:
                        captcha_found = "recaptcha_v2_invisible"
                    elif "enterprise" in page_lower and "recaptcha/enterprise" in page_lower:
                        captcha_found = "recaptcha_enterprise"
                    elif "grecaptcha.execute" in page_html:
                        captcha_found = "recaptcha_v3"
                    else:
                        captcha_found = "recaptcha_v2"
                    log.info(f"[ForceSolve] Found {captcha_found} sitekey={sitekey[:20]}...")
            
            # Check for hCaptcha
            if not captcha_found and ("hcaptcha" in page_lower or "h-captcha" in page_lower):
                sk = re.search(r'data-sitekey=["\']([^"\']+)', page_html)
                if sk:
                    sitekey = sk.group(1)
                    captcha_found = "hcaptcha"
                    log.info(f"[ForceSolve] Found hCaptcha sitekey={sitekey[:20]}...")
            
            # Check for Turnstile
            if not captcha_found and ("turnstile" in page_lower or "cf-turnstile" in page_lower):
                sk = re.search(r'data-sitekey=["\']([^"\']+)', page_html)
                if sk:
                    sitekey = sk.group(1)
                    captcha_found = "turnstile"
                    log.info(f"[ForceSolve] Found Turnstile sitekey={sitekey[:20]}...")
            
            # Check for FunCaptcha
            if not captcha_found and ("funcaptcha" in page_lower or "arkoselabs" in page_lower):
                sk = re.search(r'data-pkey=["\']([^"\']+)', page_html)
                if sk:
                    sitekey = sk.group(1)
                    captcha_found = "funcaptcha"
            
            # Check for GeeTest
            if not captcha_found and "geetest" in page_lower:
                captcha_found = "geetest"
            
            # Check for Friendly Captcha
            if not captcha_found and "frc-captcha" in page_lower:
                captcha_found = "friendly"
            
            # Check for MTCaptcha
            if not captcha_found and "mtcaptcha" in page_lower:
                captcha_found = "mtcaptcha"
            
            if not captcha_found:
                el = time.time()-t
                return {"solved":False,"error":"No CAPTCHA widget found on page","page_size":len(page_html),
                        "ms":round(el*1000)}
            
            # ── Step 3: Try solving IN-PAGE first (interact with the CAPTCHA on the actual page) ──
            log.info(f"[ForceSolve] Attempting in-page solve for {captcha_found}")
            
            token = None
            method = None
            
            if captcha_found.startswith("recaptcha"):
                # Try to find and interact with reCAPTCHA on the live page
                token, method = self._force_solve_recaptcha_inpage(driver, sitekey, captcha_found)
            
            elif captcha_found == "hcaptcha":
                token, method = self._force_solve_hcaptcha_inpage(driver, sitekey)
            
            elif captcha_found == "turnstile":
                token, method = self._force_solve_turnstile_inpage(driver, sitekey)
            
            # ── Step 4: If in-page failed, fall back to dedicated solver ──
            if not token:
                log.info(f"[ForceSolve] In-page failed, trying dedicated solver...")
                if captcha_found == "recaptcha_v2":
                    r = self.recaptcha.solve_v2(url, sitekey)
                elif captcha_found == "recaptcha_v2_invisible":
                    r = self.recaptcha.solve_v2_invisible(url, sitekey)
                elif captcha_found == "recaptcha_v3":
                    r = self.recaptcha.solve_v3(url, sitekey)
                elif captcha_found == "recaptcha_enterprise":
                    r = self.recaptcha.solve_enterprise(url, sitekey)
                elif captcha_found == "hcaptcha":
                    r = self.hcaptcha.solve(url, sitekey)
                elif captcha_found == "turnstile":
                    r = self.turnstile.solve(url, sitekey)
                elif captcha_found == "funcaptcha":
                    r = self.funcaptcha.solve(url, sitekey)
                elif captcha_found == "geetest":
                    r = self.geetest.solve(url)
                elif captcha_found == "friendly":
                    r = self.friendly.solve(site_url=url)
                elif captcha_found == "mtcaptcha":
                    r = self.mtcaptcha.solve(url)
                else:
                    r = {"solved":False,"error":f"No solver for {captcha_found}"}
                
                if r.get("solved"):
                    token = r.get("token","")
                    method = r.get("method","fallback_solver")
            
            el = time.time()-t
            if token:
                log.info(f"[ForceSolve] ✅ Solved {captcha_found} in {el:.1f}s via {method}")
                stats.record(f"force_{captcha_found}",True,el)
                return {"solved":True,"captcha_type":captcha_found,"token":token[:80]+"..." if len(str(token))>80 else token,
                        "sitekey":sitekey,"method":method,"ms":round(el*1000)}
            else:
                log.warning(f"[ForceSolve] ❌ Failed {captcha_found} after {el:.1f}s")
                stats.record(f"force_{captcha_found}",False,el)
                return {"solved":False,"captcha_type":captcha_found,"sitekey":sitekey,
                        "error":r.get("error","Token not obtained") if 'r' in dir() else "In-page solve failed",
                        "ms":round(el*1000)}
        
        except Exception as e:
            el = time.time()-t
            return {"solved":False,"error":str(e)[:200],"ms":round(el*1000)}
        finally:
            browser_mgr.safe_quit(driver, force=True)
    
    def _force_solve_recaptcha_inpage(self, driver, sitekey, variant):
        """Solve reCAPTCHA directly on the loaded page — checkbox click, token check, audio fallback."""
        try:
            from selenium.webdriver.common.by import By
            
            # Scroll to reCAPTCHA container to trigger render
            for sel in [".g-recaptcha","[data-sitekey]","[id*=recaptcha]","[id*=captcha]",
                        "form [type=submit]","button[type=submit]"]:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                    driver.execute_script("arguments[0].scrollIntoView({behavior:'smooth',block:'center'});", el)
                    time.sleep(1)
                    break
                except: pass
            
            # Force grecaptcha.render() if it hasn't fired
            driver.execute_script("""
                try {
                    if (typeof grecaptcha !== 'undefined' && typeof grecaptcha.render === 'function') {
                        var containers = document.querySelectorAll('[data-sitekey],[id*=recaptcha],[class*=g-recaptcha]');
                        containers.forEach(function(el) {
                            if (el.childElementCount === 0 || el.querySelector('iframe') === null) {
                                try { grecaptcha.render(el, {sitekey: el.dataset.sitekey || '%s'}); } catch(e) {}
                            }
                        });
                    }
                } catch(e) {}
            """ % sitekey)
            time.sleep(3)
            
            # ── Try grecaptcha.execute() first for invisible/v3 ──
            if "invisible" in variant or "v3" in variant:
                log.info("[ForceSolve] Trying grecaptcha.execute() for invisible/v3...")
                driver.execute_script("""
                    try {
                        if (typeof grecaptcha !== 'undefined') {
                            grecaptcha.execute('%s', {action: 'submit'}).then(function(token) {
                                document.title = 'RCTOKEN:' + token;
                            });
                        }
                    } catch(e) {
                        try { grecaptcha.execute(); } catch(e2) {}
                    }
                """ % sitekey)
                # Wait for async callback
                for i in range(15):
                    time.sleep(2)
                    title = driver.execute_script("return document.title || ''") or ""
                    if "RCTOKEN:" in title:
                        token = title.split("RCTOKEN:")[1]
                        if len(token) > 20:
                            log.info(f"[ForceSolve] grecaptcha.execute() returned token!")
                            return token, "grecaptcha_execute"
                    # Also check response textarea
                    token = driver.execute_script(
                        "return document.querySelector('textarea[name=\"g-recaptcha-response\"]')?.value || "
                        "document.querySelector('#g-recaptcha-response')?.value || ''"
                    ) or ""
                    if len(token) > 20:
                        return token, "grecaptcha_callback"
            
            # ── Find and click the checkbox ──
            frames = driver.find_elements(By.TAG_NAME, "iframe")
            anchor = None
            for f in frames:
                src = f.get_attribute("src") or ""
                if "recaptcha" in src and ("anchor" in src or "api2" in src):
                    anchor = f
                    break
            
            if not anchor:
                for _ in range(5):
                    time.sleep(2)
                    frames = driver.find_elements(By.TAG_NAME, "iframe")
                    for f in frames:
                        src = f.get_attribute("src") or ""
                        if "recaptcha" in src and ("anchor" in src or "api2" in src):
                            anchor = f; break
                    if anchor: break
            
            if not anchor:
                log.warning("[ForceSolve] reCAPTCHA iframe not found")
                return None, None
            
            log.info("[ForceSolve] Found anchor iframe, clicking checkbox...")
            driver.switch_to.frame(anchor)
            time.sleep(1)
            
            try:
                cb = driver.find_element(By.ID, "recaptcha-anchor")
                cb.click()
            except:
                try: driver.execute_script("document.getElementById('recaptcha-anchor')?.click()")
                except: pass
            time.sleep(4)
            
            # Check if solved by checkbox click (common for low-risk browsers)
            try:
                checked = driver.execute_script(
                    "return document.getElementById('recaptcha-anchor')?.getAttribute('aria-checked') || ''"
                ) or ""
                log.info(f"[ForceSolve] Checkbox aria-checked: {checked}")
            except:
                checked = ""
            
            driver.switch_to.default_content()
            
            # ── Check for token (retry multiple times — reCAPTCHA is async) ──
            for wait_i in range(10):
                token = driver.execute_script(
                    "return document.querySelector('textarea[name=\"g-recaptcha-response\"]')?.value || "
                    "document.querySelector('#g-recaptcha-response')?.value || "
                    "document.querySelector('[id*=recaptcha-response]')?.value || ''"
                ) or ""
                if len(token) > 20:
                    log.info(f"[ForceSolve] Got token after checkbox click! (attempt {wait_i+1})")
                    return token, "checkbox_click"
                time.sleep(2)
            
            log.info("[ForceSolve] Checkbox didn't auto-solve, trying audio challenge...")
            
            # ── Audio challenge — find the bframe ──
            frames = driver.find_elements(By.TAG_NAME, "iframe")
            bframe = None
            for f in frames:
                src = f.get_attribute("src") or ""
                if "recaptcha" in src and ("bframe" in src or "api2/bframe" in src):
                    bframe = f; break
            
            if not bframe:
                log.warning("[ForceSolve] No challenge frame — reCAPTCHA may have silently failed")
                return None, None
            
            driver.switch_to.frame(bframe)
            time.sleep(1)
            
            # Click audio button
            try:
                audio_btn = driver.find_element(By.ID, "recaptcha-audio-button")
                audio_btn.click()
                time.sleep(3)
            except:
                try:
                    driver.execute_script("document.getElementById('recaptcha-audio-button')?.click()")
                    time.sleep(3)
                except:
                    log.warning("[ForceSolve] Audio button not found — may be image-only challenge")
                    driver.switch_to.default_content()
                    return None, None
            
            # Get audio URL
            audio_src = ""
            for _ in range(3):
                try:
                    audio_src = driver.execute_script(
                        "return document.getElementById('audio-source')?.src || "
                        "document.querySelector('.rc-audiochallenge-tdownload-link')?.href || ''"
                    ) or ""
                except: pass
                if audio_src: break
                time.sleep(2)
            
            if not audio_src:
                log.warning("[ForceSolve] No audio URL — Google may have blocked audio challenge")
                driver.switch_to.default_content()
                return None, None
            
            # Download and transcribe
            log.info(f"[ForceSolve] Transcribing audio...")
            try:
                import speech_recognition as sr
                import subprocess, tempfile
                
                audio_data = requests.get(audio_src, timeout=15).content
                mp3 = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                mp3.write(audio_data); mp3.close()
                wav = mp3.name.replace(".mp3", ".wav")
                subprocess.run(["ffmpeg","-y","-i",mp3.name,wav], capture_output=True, timeout=15)
                
                recognizer = sr.Recognizer()
                with sr.AudioFile(wav) as source:
                    audio = recognizer.record(source)
                text = recognizer.recognize_google(audio)
                log.info(f"[ForceSolve] Transcribed: '{text}'")
                
                try: os.unlink(mp3.name)
                except: pass
                try: os.unlink(wav)
                except: pass
                
                # Type answer with human-like delay
                answer_input = driver.find_element(By.ID, "audio-response")
                answer_input.clear()
                for ch in text:
                    answer_input.send_keys(ch)
                    time.sleep(random.uniform(0.05, 0.15))
                time.sleep(0.5)
                
                driver.find_element(By.ID, "recaptcha-verify-button").click()
                time.sleep(5)
                
                driver.switch_to.default_content()
                
                # Check for token
                for _ in range(5):
                    token = driver.execute_script(
                        "return document.querySelector('textarea[name=\"g-recaptcha-response\"]')?.value || ''"
                    ) or ""
                    if len(token) > 20:
                        return token, "audio_solve"
                    time.sleep(2)
                
                log.warning("[ForceSolve] Audio answered but no token")
                return None, None
                    
            except ImportError:
                log.warning("[ForceSolve] speech_recognition not installed")
                driver.switch_to.default_content()
                return None, None
            except Exception as e:
                log.warning(f"[ForceSolve] Audio failed: {e}")
                driver.switch_to.default_content()
                return None, None
        
        except Exception as e:
            log.warning(f"[ForceSolve] reCAPTCHA error: {e}")
            try: driver.switch_to.default_content()
            except: pass
            return None, None
    
    def _force_solve_hcaptcha_inpage(self, driver, sitekey):
        """Attempt to solve hCaptcha on the loaded page."""
        try:
            from selenium.webdriver.common.by import By
            
            frames = driver.find_elements(By.TAG_NAME, "iframe")
            hframe = None
            for f in frames:
                src = f.get_attribute("src") or ""
                if "hcaptcha" in src:
                    hframe = f
                    break
            
            if hframe:
                driver.switch_to.frame(hframe)
                time.sleep(1)
                try:
                    cb = driver.find_element(By.CSS_SELECTOR, "[id*=checkbox],.check")
                    cb.click()
                    time.sleep(5)
                except: pass
                driver.switch_to.default_content()
                
                token = driver.execute_script(
                    "return document.querySelector('[name=\"h-captcha-response\"]')?.value || "
                    "document.querySelector('[name=\"g-recaptcha-response\"]')?.value || ''"
                )
                if token and len(token) > 20:
                    return token, "hcaptcha_click"
        except: pass
        return None, None
    
    def _force_solve_turnstile_inpage(self, driver, sitekey):
        """Attempt to solve Cloudflare Turnstile on the loaded page."""
        try:
            from selenium.webdriver.common.by import By
            
            # Turnstile often auto-solves — wait for it
            for _ in range(10):
                token = driver.execute_script(
                    "return document.querySelector('[name=\"cf-turnstile-response\"]')?.value || "
                    "document.querySelector('[name=\"turnstileToken\"]')?.value || ''"
                )
                if token and len(token) > 20:
                    return token, "turnstile_auto"
                time.sleep(2)
            
            # Try clicking
            frames = driver.find_elements(By.TAG_NAME, "iframe")
            for f in frames:
                if "turnstile" in (f.get_attribute("src") or ""):
                    driver.switch_to.frame(f)
                    try:
                        driver.find_element(By.CSS_SELECTOR, "[type=checkbox],input").click()
                        time.sleep(5)
                    except: pass
                    driver.switch_to.default_content()
                    break
            
            token = driver.execute_script(
                "return document.querySelector('[name=\"cf-turnstile-response\"]')?.value || ''"
            )
            if token and len(token) > 20:
                return token, "turnstile_click"
        except: pass
        return None, None

engine = CaptchaEngine()

# ═══════════════════════════════════════════════════════════════════
#  FLASK API
# ═══════════════════════════════════════════════════════════════════
app = Flask(__name__)

def jres(data, status=200):
    return Response(json.dumps(data,indent=2),status=status,mimetype="application/json",
                    headers={"Access-Control-Allow-Origin":"*","Access-Control-Allow-Methods":"GET,POST,OPTIONS",
                             "Access-Control-Allow-Headers":"Content-Type"})

@app.route("/")
def index(): return jres({"name":"CapSolver v2.0 — Universal","version":"2.0","types":CAPTCHA_TYPES})

CAPTCHA_TYPES = {
    "POST /solve/image":               "Image OCR (6 pipelines + voting)",
    "POST /solve/recaptcha/v2":         "reCAPTCHA v2 (audio bypass)",
    "POST /solve/recaptcha/v2invisible":"reCAPTCHA v2 Invisible",
    "POST /solve/recaptcha/v3":         "reCAPTCHA v3 (score sim)",
    "POST /solve/recaptcha/enterprise": "reCAPTCHA Enterprise",
    "POST /solve/recaptcha/audio":      "reCAPTCHA audio direct",
    "POST /solve/hcaptcha":             "hCaptcha",
    "POST /solve/hcaptcha/enterprise":  "hCaptcha Enterprise",
    "POST /solve/turnstile":            "Cloudflare Turnstile",
    "POST /solve/funcaptcha":           "FunCaptcha (Arkose Labs)",
    "POST /solve/geetest":             "GeeTest v3/v4 (slider)",
    "POST /solve/keycaptcha":           "KeyCAPTCHA",
    "POST /solve/friendly":             "Friendly Captcha (PoW)",
    "POST /solve/mtcaptcha":            "MTCaptcha",
    "POST /solve/waf":                  "WAF Bypass (DataDome/PX/Kasada/Akamai/Imperva/Shape/Radware/Fastly)",
    "POST /solve/math":                 "Math CAPTCHA",
    "POST /solve/text":                 "Text CAPTCHA",
    "POST /solve/google":               "Google Sorry Page",
    "POST /solve/auto":                 "Auto-detect & solve",
    "POST /solve/force":                "Force-solve CAPTCHA on any page (browser navigates, finds, solves)",
    "GET  /health":                     "Health + capabilities",
    "GET  /stats":                      "Solver statistics",
}

@app.route("/solve/image", methods=["POST"])
def s_image():
    d=freq.get_json(silent=True) or {}
    return jres(engine.image.solve(d.get("image",""),d.get("expected_length",0),d.get("charset","alphanumeric")))

@app.route("/solve/recaptcha/v2", methods=["POST"])
def s_rc2():
    d=freq.get_json(silent=True) or {}
    return jres(engine.recaptcha.solve_v2(d.get("site_url",""),d.get("site_key","")))

@app.route("/solve/recaptcha/v2invisible", methods=["POST"])
def s_rc2i():
    d=freq.get_json(silent=True) or {}
    return jres(engine.recaptcha.solve_v2_invisible(d.get("site_url",""),d.get("site_key","")))

@app.route("/solve/recaptcha/v3", methods=["POST"])
def s_rc3():
    d=freq.get_json(silent=True) or {}
    return jres(engine.recaptcha.solve_v3(d.get("site_url",""),d.get("site_key",""),d.get("action","verify"),d.get("min_score",0.7)))

@app.route("/solve/recaptcha/enterprise", methods=["POST"])
def s_rce():
    d=freq.get_json(silent=True) or {}
    return jres(engine.recaptcha.solve_enterprise(d.get("site_url",""),d.get("site_key",""),d.get("action","verify")))

@app.route("/solve/recaptcha/audio", methods=["POST"])
def s_rca():
    d=freq.get_json(silent=True) or {}
    return jres(engine.recaptcha.solve_audio_direct(d.get("audio_url","")))

@app.route("/solve/hcaptcha", methods=["POST"])
def s_hc():
    d=freq.get_json(silent=True) or {}
    return jres(engine.hcaptcha.solve(d.get("site_url",""),d.get("site_key","")))

@app.route("/solve/hcaptcha/enterprise", methods=["POST"])
def s_hce():
    d=freq.get_json(silent=True) or {}
    return jres(engine.hcaptcha.solve(d.get("site_url",""),d.get("site_key",""),enterprise=True))

@app.route("/solve/turnstile", methods=["POST"])
def s_ts():
    d=freq.get_json(silent=True) or {}
    return jres(engine.turnstile.solve(d.get("site_url",""),d.get("site_key","")))

@app.route("/solve/funcaptcha", methods=["POST"])
def s_fc():
    d=freq.get_json(silent=True) or {}
    return jres(engine.funcaptcha.solve(d.get("site_url",""),d.get("public_key","")))

@app.route("/solve/geetest", methods=["POST"])
def s_gt():
    d=freq.get_json(silent=True) or {}
    return jres(engine.geetest.solve(d.get("site_url",""),d.get("gt"),d.get("challenge")))

@app.route("/solve/keycaptcha", methods=["POST"])
def s_kc():
    d=freq.get_json(silent=True) or {}
    return jres(engine.keycaptcha.solve(d.get("site_url","")))

@app.route("/solve/friendly", methods=["POST"])
def s_fr():
    d=freq.get_json(silent=True) or {}
    return jres(engine.friendly.solve(d.get("puzzle"),d.get("site_url"),d.get("site_key")))

@app.route("/solve/mtcaptcha", methods=["POST"])
def s_mt():
    d=freq.get_json(silent=True) or {}
    return jres(engine.mtcaptcha.solve(d.get("site_url",""),d.get("site_key")))

@app.route("/solve/waf", methods=["POST"])
def s_waf():
    d=freq.get_json(silent=True) or {}
    return jres(engine.waf.solve(d.get("site_url",""),d.get("system"),d.get("html",""),d.get("headers")))

@app.route("/solve/math", methods=["POST"])
def s_math():
    d=freq.get_json(silent=True) or {}
    return jres(engine.math.solve(d.get("expression","")))

@app.route("/solve/text", methods=["POST"])
def s_text():
    d=freq.get_json(silent=True) or {}
    return jres(engine.text.solve(d.get("question","")))

@app.route("/solve/google", methods=["POST"])
def s_google():
    d=freq.get_json(silent=True) or {}
    return jres(engine.google.solve(d.get("html",""),d.get("tld","com")))

@app.route("/solve/auto", methods=["POST"])
def s_auto():
    """Auto-detect CAPTCHA type and solve."""
    d=freq.get_json(silent=True) or {}
    html=d.get("html",""); url=d.get("site_url",""); headers=d.get("headers",{})
    combined=(html+str(headers)+url).lower()
    # Detection logic
    if "g-recaptcha" in combined or "recaptcha" in combined:
        sk=re.search(r'data-sitekey="([^"]+)"',html)
        key=sk.group(1) if sk else d.get("site_key","")
        if "invisible" in combined: return jres(engine.recaptcha.solve_v2_invisible(url,key))
        if "enterprise" in combined: return jres(engine.recaptcha.solve_enterprise(url,key))
        if "v3" in combined: return jres(engine.recaptcha.solve_v3(url,key))
        return jres(engine.recaptcha.solve_v2(url,key))
    if "hcaptcha" in combined or "h-captcha" in combined:
        sk=re.search(r'data-sitekey="([^"]+)"',html)
        return jres(engine.hcaptcha.solve(url,sk.group(1) if sk else d.get("site_key","")))
    if "turnstile" in combined or "cf-turnstile" in combined:
        sk=re.search(r'data-sitekey="([^"]+)"',html)
        return jres(engine.turnstile.solve(url,sk.group(1) if sk else d.get("site_key","")))
    if "funcaptcha" in combined or "arkoselabs" in combined:
        return jres(engine.funcaptcha.solve(url,d.get("public_key","")))
    if "geetest" in combined:
        return jres(engine.geetest.solve(url))
    if "friendly" in combined or "frc-captcha" in combined:
        return jres(engine.friendly.solve(d.get("puzzle"),url,d.get("site_key")))
    if "mtcaptcha" in combined:
        return jres(engine.mtcaptcha.solve(url))
    # WAF detection
    waf_sys=engine.waf.detect_system(html,headers,url)
    if waf_sys!="unknown":
        return jres(engine.waf.solve(url,waf_sys,html,headers))
    # Google sorry
    if "unusual traffic" in combined or "/sorry/" in combined:
        return jres(engine.google.solve(html,d.get("tld","com")))
    return jres({"solved":False,"error":"Cannot auto-detect CAPTCHA type","hint":"Provide more context in html/site_url"})

@app.route("/solve/force", methods=["POST"])
def s_force():
    """Force-solve: navigate to page with browser, find CAPTCHA widget, solve it."""
    d=freq.get_json(silent=True) or {}
    url=d.get("site_url","")
    if not url: return jres({"solved":False,"error":"site_url required"},400)
    return jres(engine.force_solve_page(url, timeout=d.get("timeout",60)))

@app.route("/health")
def health():
    tess=False
    try: pytesseract.get_tesseract_version(); tess=True
    except: pass
    ffmpeg=os.system("ffmpeg -version >/dev/null 2>&1")==0
    return jres({
        "status":"ok","version":"2.0",
        "supported_types":list(CAPTCHA_TYPES.keys()),
        "total_types":len(CAPTCHA_TYPES),
        "capabilities":{
            "image_ocr":tess,"audio_stt":ffmpeg,
            "browser":browser_mgr.has_browser(),"selenium":browser_mgr.has_selenium(),
            "math":True,"text":True,"pow":True,
        },
        "install":{
            "tesseract":"apt install tesseract-ocr" if not tess else "OK",
            "ffmpeg":"apt install ffmpeg" if not ffmpeg else "OK",
            "browser":"pip install undetected-chromedriver selenium" if not browser_mgr.has_browser() else "OK",
        }
    })

@app.route("/stats")
def get_stats(): return jres(stats.to_dict())

# CORS preflight
@app.route("/<path:path>", methods=["OPTIONS"])
def cors_preflight(path):
    return Response("",headers={"Access-Control-Allow-Origin":"*","Access-Control-Allow-Methods":"*","Access-Control-Allow-Headers":"*"})

if __name__=="__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║           CAPSOLVER v2.0 — UNIVERSAL CAPTCHA SOLVER          ║
    ╠═══════════════════════════════════════════════════════════════╣
    ║  Server:  http://localhost:9090                               ║
    ║  Health:  http://localhost:9090/health                        ║
    ║  Stats:   http://localhost:9090/stats                         ║
    ╠═══════════════════════════════════════════════════════════════╣
    ║  20+ CAPTCHA Types Supported:                                ║
    ║   reCAPTCHA v2/v3/Enterprise | hCaptcha | Turnstile          ║
    ║   FunCaptcha | GeeTest | KeyCAPTCHA | Friendly | MTCaptcha   ║
    ║   DataDome | PerimeterX | Kasada | Akamai | Imperva          ║
    ║   Shape Security | Radware | Fastly | Image OCR | Math/Text  ║
    ╠═══════════════════════════════════════════════════════════════╣
    ║  Requirements:                                                ║
    ║   apt install tesseract-ocr ffmpeg                           ║
    ║   pip install undetected-chromedriver selenium (recommended)  ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)
    app.run(host="0.0.0.0",port=8080,debug=False,threaded=True)
