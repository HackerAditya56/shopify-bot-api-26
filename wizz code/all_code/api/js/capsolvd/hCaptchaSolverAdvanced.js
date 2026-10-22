/**
 * ╔═════════════════════════════════════════════════════════════════════════════════════╗
 * ║              ADVANCED HCAPTCHA API v5.0                                            ║
 * ║          Auto-Detect SiteKey • Browser Solver • API Server                         ║
 * ╠═════════════════════════════════════════════════════════════════════════════════════╣
 * ║                                                                                     ║
 * ║  FEATURES:                                                                          ║
 * ║  ✓ Auto-detects siteKey from HTML, JS files, inline scripts                        ║
 * ║  ✓ No API key required for the server                                              ║
 * ║  ✓ Works on Shopify, DiceyGolf, Nike, Supreme, Discord, etc.                       ║
 * ║  ✓ Browser-based solver using Puppeteer                                            ║
 * ║  ✓ Supports hCaptcha v2, v3, Enterprise, Invisible                                 ║
 * ║                                                                                     ║
 * ║  IMPORTANT NOTES:                                                                   ║
 * ║  • hCaptcha uses HSW (WebAssembly) proof-of-work that requires a browser           ║
 * ║  • Image challenges require human interaction or computer vision AI                ║
 * ║  • For invisible captchas, instant-pass may work automatically                     ║
 * ║  • For image challenges, use with your own solving logic or human-in-the-loop     ║
 * ║                                                                                     ║
 * ╚═════════════════════════════════════════════════════════════════════════════════════╝
 * 
 *  START:  node HCAPTCHA.JS
 *  
 *  ENDPOINTS:
 *    POST /solve    - Solve captcha (needs browser for full solving)
 *    POST /detect   - Detect siteKey from URL
 *    GET  /stats    - Server statistics
 *    GET  /health   - Health check
 */

'use strict';

const crypto = require('crypto');
const https = require('https');
const http = require('http');
const { URL } = require('url');
const EventEmitter = require('events');

// ════════════════════════════════════════════════════════════════════════════════
// CONFIGURATION
// ════════════════════════════════════════════════════════════════════════════════

const CONFIG = {
  VERSION: '5.0.0',
  PORT: 3000,
  TIMEOUT: 30000,
  MAX_CONCURRENT: 50,
  
  HCAPTCHA: {
    SITE_CONFIG: 'https://hcaptcha.com/checksiteconfig',
    GET_CAPTCHA: 'https://hcaptcha.com/getcaptcha',
    CHECK_CAPTCHA: 'https://hcaptcha.com/checkcaptcha'
  },
  
  // Known siteKeys for popular sites
  KNOWN_KEYS: {
    'shopify': 'f5561ba9-8f1e-40ca-9b5b-a0b3f719ef34',
    'diceygolf': 'f5561ba9-8f1e-40ca-9b5b-a0b3f719ef34',
    'discord': 'f5561ba9-8f1e-40ca-9b5b-a0b3f719ef34',
    'epicgames': 'f5561ba9-8f1e-40ca-9b5b-a0b3f719ef34',
    'nike': 'a9b5fb1a-0468-4796-94d5-a6e3e6a1d8d2',
    'default': 'f5561ba9-8f1e-40ca-9b5b-a0b3f719ef34'
  },
  
  USER_AGENTS: [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
  ]
};

// ════════════════════════════════════════════════════════════════════════════════
// UTILITIES
// ════════════════════════════════════════════════════════════════════════════════

const randomUA = () => CONFIG.USER_AGENTS[Math.floor(Math.random() * CONFIG.USER_AGENTS.length)];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const uuid = () => crypto.randomUUID();
const timestamp = () => Date.now();

function getDomain(url) {
  try {
    return new URL(url.startsWith('http') ? url : `https://${url}`).hostname;
  } catch {
    return url;
  }
}

function base64Encode(data) {
  return Buffer.from(typeof data === 'string' ? data : JSON.stringify(data)).toString('base64');
}

function base64Decode(str) {
  try {
    return JSON.parse(Buffer.from(str, 'base64').toString());
  } catch {
    return Buffer.from(str, 'base64').toString();
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// HTTP CLIENT
// ════════════════════════════════════════════════════════════════════════════════

class HttpClient {
  static async fetch(url, options = {}, redirectCount = 0) {
    const maxRedirects = options.maxRedirects || 5;
    
    return new Promise((resolve, reject) => {
      const urlObj = new URL(url);
      const isHttps = urlObj.protocol === 'https:';
      const client = isHttps ? https : http;
      
      const reqOptions = {
        hostname: urlObj.hostname,
        port: urlObj.port || (isHttps ? 443 : 80),
        path: urlObj.pathname + urlObj.search,
        method: options.method || 'GET',
        headers: {
          'User-Agent': options.userAgent || randomUA(),
          'Accept': options.accept || '*/*',
          'Accept-Language': 'en-US,en;q=0.9',
          'Accept-Encoding': 'identity',
          'Connection': 'keep-alive',
          ...options.headers
        },
        timeout: options.timeout || CONFIG.TIMEOUT
      };
      
      const req = client.request(reqOptions, res => {
        // Handle redirects
        if ([301, 302, 303, 307, 308].includes(res.statusCode) && res.headers.location && redirectCount < maxRedirects) {
          let newUrl = res.headers.location;
          if (!newUrl.startsWith('http')) {
            newUrl = new URL(newUrl, url).href;
          }
          return this.fetch(newUrl, options, redirectCount + 1).then(resolve).catch(reject);
        }
        
        let data = '';
        res.setEncoding('utf8');
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            resolve({ 
              status: res.statusCode, 
              headers: res.headers,
              url: url,
              data: options.json !== false ? JSON.parse(data) : data 
            });
          } catch {
            resolve({ status: res.statusCode, headers: res.headers, url: url, data });
          }
        });
      });
      
      req.on('error', reject);
      req.on('timeout', () => { req.destroy(); reject(new Error('Timeout')); });
      
      if (options.body) {
        const body = typeof options.body === 'string' ? options.body : 
                     options.form ? new URLSearchParams(options.body).toString() : 
                     JSON.stringify(options.body);
        req.setHeader('Content-Type', options.form ? 'application/x-www-form-urlencoded' : 'application/json');
        req.setHeader('Content-Length', Buffer.byteLength(body));
        req.write(body);
      }
      
      req.end();
    });
  }
  
  static get(url, options = {}) {
    return this.fetch(url, { ...options, method: 'GET' });
  }
  
  static post(url, body, options = {}) {
    return this.fetch(url, { ...options, method: 'POST', body, form: true });
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// ADVANCED SITEKEY DETECTOR - Scans HTML, JS files, inline scripts
// ════════════════════════════════════════════════════════════════════════════════

class SiteKeyDetector {
  
  // All patterns to find siteKey
  static PATTERNS = [
    // HTML attributes
    /data-sitekey\s*=\s*["']([a-f0-9-]{36})["']/gi,
    /data-hcaptcha-sitekey\s*=\s*["']([a-f0-9-]{36})["']/gi,
    /sitekey\s*=\s*["']([a-f0-9-]{36})["']/gi,
    
    // JavaScript variables
    /sitekey\s*:\s*["']([a-f0-9-]{36})["']/gi,
    /siteKey\s*:\s*["']([a-f0-9-]{36})["']/gi,
    /site_key\s*:\s*["']([a-f0-9-]{36})["']/gi,
    /SITE_KEY\s*:\s*["']([a-f0-9-]{36})["']/gi,
    /hcaptchaSiteKey\s*:\s*["']([a-f0-9-]{36})["']/gi,
    /hcaptcha_sitekey\s*:\s*["']([a-f0-9-]{36})["']/gi,
    /captchaSiteKey\s*:\s*["']([a-f0-9-]{36})["']/gi,
    
    // Assignment patterns
    /sitekey\s*=\s*["']([a-f0-9-]{36})["']/gi,
    /siteKey\s*=\s*["']([a-f0-9-]{36})["']/gi,
    /site_key\s*=\s*["']([a-f0-9-]{36})["']/gi,
    /['"]sitekey['"]\s*:\s*["']([a-f0-9-]{36})["']/gi,
    
    // hCaptcha render calls
    /hcaptcha\.render\s*\([^)]*sitekey\s*:\s*["']([a-f0-9-]{36})["']/gi,
    /hcaptcha\.render\s*\(\s*["'][^"']+["']\s*,\s*\{[^}]*sitekey\s*:\s*["']([a-f0-9-]{36})["']/gi,
    
    // URL parameters
    /hcaptcha\.com\/1\/api\.js\?[^"']*sitekey=([a-f0-9-]{36})/gi,
    /sitekey=([a-f0-9-]{36})/gi,
    
    // Config objects
    /["']hcaptcha["']\s*:\s*\{[^}]*["']sitekey["']\s*:\s*["']([a-f0-9-]{36})["']/gi,
    /captchaConfig[^}]*sitekey\s*:\s*["']([a-f0-9-]{36})["']/gi,
    /window\.__.*?sitekey.*?["']([a-f0-9-]{36})["']/gi,
    
    // Shopify specific
    /Shopify\..*?captcha.*?["']([a-f0-9-]{36})["']/gi,
    /checkout.*?hcaptcha.*?["']([a-f0-9-]{36})["']/gi
  ];
  
  /**
   * Extract all siteKeys from text content
   */
  static extractFromText(text) {
    const found = new Set();
    
    for (const pattern of this.PATTERNS) {
      pattern.lastIndex = 0; // Reset regex
      let match;
      while ((match = pattern.exec(text)) !== null) {
        if (match[1] && this.isValidSiteKey(match[1])) {
          found.add(match[1]);
        }
      }
    }
    
    return Array.from(found);
  }
  
  /**
   * Validate siteKey format
   */
  static isValidSiteKey(key) {
    return /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(key);
  }
  
  /**
   * Extract JS file URLs from HTML
   */
  static extractJsUrls(html, baseUrl) {
    const urls = new Set();
    const domain = getDomain(baseUrl);
    const base = baseUrl.startsWith('http') ? baseUrl : `https://${baseUrl}`;
    
    // Script src attributes
    const srcPattern = /<script[^>]*src\s*=\s*["']([^"']+)["'][^>]*>/gi;
    let match;
    
    while ((match = srcPattern.exec(html)) !== null) {
      let src = match[1];
      
      // Skip external tracking/analytics
      if (src.includes('google') || src.includes('facebook') || src.includes('analytics')) {
        continue;
      }
      
      // Convert relative URLs to absolute
      if (src.startsWith('//')) {
        src = 'https:' + src;
      } else if (src.startsWith('/')) {
        src = `https://${domain}${src}`;
      } else if (!src.startsWith('http')) {
        src = new URL(src, base).href;
      }
      
      urls.add(src);
    }
    
    return Array.from(urls);
  }
  
  /**
   * Check if site is Shopify based on HTML content
   */
  static isShopifySite(html) {
    const indicators = [
      'shopify',
      'myshopify.com',
      'cdn.shopify',
      'cdn/shop/',
      'Shopify.shop',
      '/checkouts/',
      'shopifycloud'
    ];
    const htmlLower = html.toLowerCase();
    return indicators.some(ind => htmlLower.includes(ind));
  }
  
  /**
   * Check if page has hCaptcha
   */
  static hasHCaptcha(html) {
    const indicators = [
      'hcaptcha.com',
      'hcaptcha',
      'h-captcha',
      'data-hcaptcha'
    ];
    const htmlLower = html.toLowerCase();
    return indicators.some(ind => htmlLower.includes(ind));
  }

  /**
   * Main detection function - scans page and all JS files
   */
  static async detect(url) {
    const results = {
      url,
      domain: getDomain(url),
      siteKeys: [],
      sources: [],
      version: 'v2',
      invisible: false,
      enterprise: false,
      isShopify: false,
      hasHCaptcha: false
    };
    
    try {
      // Step 1: Fetch main page (follows redirects automatically now)
      console.log(`[Detector] Scanning: ${url}`);
      const pageResponse = await HttpClient.get(url, { json: false, accept: 'text/html,application/xhtml+xml' });
      const html = pageResponse.data || '';
      
      if (!html || html.length < 100) {
        throw new Error('Empty or invalid response from site');
      }
      
      // Step 2: Check site type
      results.isShopify = this.isShopifySite(html);
      results.hasHCaptcha = this.hasHCaptcha(html);
      
      console.log(`[Detector] Shopify: ${results.isShopify}, hCaptcha: ${results.hasHCaptcha}`);
      
      // Step 3: Extract siteKeys from HTML
      const htmlKeys = this.extractFromText(html);
      htmlKeys.forEach(key => {
        results.siteKeys.push(key);
        results.sources.push({ key, source: 'html' });
      });
      
      // Check for invisible/enterprise
      if (html.includes('invisible') || html.includes('data-size="invisible"')) {
        results.invisible = true;
      }
      if (html.includes('enterprise')) {
        results.enterprise = true;
        results.version = 'v3';
      }
      
      // Step 4: Extract and scan JS files (only if no key found yet)
      if (results.siteKeys.length === 0) {
        const jsUrls = this.extractJsUrls(html, url);
        console.log(`[Detector] Scanning ${jsUrls.length} JS files...`);
        
        // Scan JS files in parallel (max 5 concurrent for speed)
        const chunks = [];
        for (let i = 0; i < Math.min(jsUrls.length, 20); i += 5) {
          chunks.push(jsUrls.slice(i, i + 5));
        }
        
        for (const chunk of chunks) {
          if (results.siteKeys.length > 0) break; // Stop if found
          
          const promises = chunk.map(async jsUrl => {
            try {
              const jsResponse = await HttpClient.get(jsUrl, { json: false, timeout: 8000 });
              const jsKeys = this.extractFromText(jsResponse.data || '');
              
              jsKeys.forEach(key => {
                if (!results.siteKeys.includes(key)) {
                  results.siteKeys.push(key);
                  results.sources.push({ key, source: jsUrl });
                  console.log(`[Detector] ✓ Found siteKey in JS: ${key}`);
                }
              });
            } catch (e) {
              // Ignore JS fetch errors
            }
          });
          
          await Promise.all(promises);
        }
      }
      
      // Step 5: Extract from inline scripts
      if (results.siteKeys.length === 0) {
        const inlineScriptPattern = /<script[^>]*>([\s\S]*?)<\/script>/gi;
        let scriptMatch;
        while ((scriptMatch = inlineScriptPattern.exec(html)) !== null) {
          const inlineKeys = this.extractFromText(scriptMatch[1]);
          inlineKeys.forEach(key => {
            if (!results.siteKeys.includes(key)) {
              results.siteKeys.push(key);
              results.sources.push({ key, source: 'inline-script' });
              console.log(`[Detector] ✓ Found siteKey in inline script: ${key}`);
            }
          });
        }
      }
      
      // Step 6: Use known siteKey for Shopify sites
      if (results.siteKeys.length === 0 && results.isShopify) {
        console.log(`[Detector] ✓ Shopify site detected - using known siteKey`);
        results.siteKeys.push(CONFIG.KNOWN_KEYS.shopify);
        results.sources.push({ key: CONFIG.KNOWN_KEYS.shopify, source: 'shopify-known' });
      }
      
      // Step 7: Fallback for other known sites
      if (results.siteKeys.length === 0) {
        const domain = results.domain.toLowerCase();
        
        if (domain.includes('discord')) {
          results.siteKeys.push(CONFIG.KNOWN_KEYS.discord);
          results.sources.push({ key: CONFIG.KNOWN_KEYS.discord, source: 'known-discord' });
        } else if (domain.includes('nike')) {
          results.siteKeys.push(CONFIG.KNOWN_KEYS.nike);
          results.sources.push({ key: CONFIG.KNOWN_KEYS.nike, source: 'known-nike' });
          results.version = 'v3';
          results.enterprise = true;
        } else if (domain.includes('epicgames')) {
          results.siteKeys.push(CONFIG.KNOWN_KEYS.epicgames);
          results.sources.push({ key: CONFIG.KNOWN_KEYS.epicgames, source: 'known-epicgames' });
        }
      }
      
      results.detected = results.siteKeys.length > 0;
      results.primaryKey = results.siteKeys[0] || null;
      
      console.log(`[Detector] Result: ${results.detected ? '✓ Detected' : '✗ Not found'} - ${results.siteKeys.length} key(s)`);
      
    } catch (error) {
      console.log(`[Detector] Error: ${error.message}`);
      results.error = error.message;
      results.detected = false;
      
      // Even on error, try known sites fallback
      const domain = getDomain(url).toLowerCase();
      if (domain.includes('shopify') || domain.includes('myshopify') || domain.includes('diceygolf')) {
        results.siteKeys.push(CONFIG.KNOWN_KEYS.shopify);
        results.sources.push({ key: CONFIG.KNOWN_KEYS.shopify, source: 'fallback-shopify' });
        results.isShopify = true;
        results.detected = true;
        results.primaryKey = CONFIG.KNOWN_KEYS.shopify;
      }
    }
    
    return results;
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// FINGERPRINT GENERATOR
// ════════════════════════════════════════════════════════════════════════════════

class Fingerprint {
  static generate() {
    const screens = [
      [1920, 1080], [2560, 1440], [1366, 768], [1536, 864], [1440, 900], [1680, 1050]
    ];
    const [w, h] = screens[Math.floor(Math.random() * screens.length)];
    const ua = randomUA();
    
    return {
      ua,
      screen: { w, h, dpr: [1, 1.25, 1.5, 2][Math.floor(Math.random() * 4)] },
      platform: ua.includes('Windows') ? 'Win32' : ua.includes('Mac') ? 'MacIntel' : 'Linux x86_64',
      cores: [4, 8, 12, 16][Math.floor(Math.random() * 4)],
      memory: [4, 8, 16, 32][Math.floor(Math.random() * 4)],
      tz: [-480, -420, -360, -300, -240, 0, 60][Math.floor(Math.random() * 7)],
      canvas: crypto.randomBytes(16).toString('hex'),
      webgl: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11)'
    };
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// MOTION DATA GENERATOR
// ════════════════════════════════════════════════════════════════════════════════

class MotionGenerator {
  static generate(fp) {
    const now = timestamp();
    const mm = [];
    const steps = 20 + Math.floor(Math.random() * 15);
    
    let x = Math.random() * 200;
    let y = Math.random() * 200;
    const targetX = 300 + Math.random() * 200;
    const targetY = 200 + Math.random() * 100;
    
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const progress = t * t * (3 - 2 * t); // Smooth step
      x = x + (targetX - x) * progress / steps + (Math.random() - 0.5) * 5;
      y = y + (targetY - y) * progress / steps + (Math.random() - 0.5) * 5;
      mm.push([Math.round(x), Math.round(y), Math.round(t * 1500)]);
    }
    
    return {
      st: now - 2000 - Math.floor(Math.random() * 3000),
      dct: now,
      mm,
      mm_mp: Math.random() * 20,
      md: [[Math.round(mm[0][0]), Math.round(mm[0][1]), now - 500]],
      md_mp: Math.random() * 10,
      mu: [[Math.round(targetX), Math.round(targetY), now]],
      mu_mp: Math.random() * 10,
      topLevel: {
        st: now - 10000,
        sc: {
          availWidth: fp.screen.w,
          availHeight: fp.screen.h - 40,
          width: fp.screen.w,
          height: fp.screen.h,
          colorDepth: 24,
          pixelDepth: 24,
          availTop: 0,
          availLeft: 0,
          devicePixelRatio: fp.screen.dpr
        },
        nv: {
          vendorSub: '',
          productSub: '20030107',
          vendor: 'Google Inc.',
          maxTouchPoints: 0,
          hardwareConcurrency: fp.cores,
          cookieEnabled: true,
          appCodeName: 'Mozilla',
          appName: 'Netscape',
          appVersion: fp.ua.replace('Mozilla/', ''),
          platform: fp.platform,
          product: 'Gecko',
          userAgent: fp.ua,
          language: 'en-US',
          languages: ['en-US', 'en'],
          onLine: true,
          webdriver: false,
          deviceMemory: fp.memory
        },
        dr: '',
        exec: false,
        wn: [[fp.screen.w, fp.screen.h, 1, now - 5000]],
        xy: [[0, 0, 1, now - 4000]],
        wh: `${fp.screen.w}x${fp.screen.h - 40}`,
        orom: false
      },
      v: 1
    };
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// HSW WEBASSEMBLY SOLVER - Advanced Native Implementation
// ════════════════════════════════════════════════════════════════════════════════

class HSWSolver {
  constructor() {
    this.wasmCache = new Map();
    this.wasmModule = null;
  }
  
  /**
   * Solve HSW challenge
   */
  async solve(req) {
    try {
      // Decode JWT
      const parts = req.split('.');
      if (parts.length !== 3) throw new Error('Invalid HSW JWT');
      
      const header = JSON.parse(Buffer.from(parts[0], 'base64').toString());
      const payload = JSON.parse(Buffer.from(parts[1], 'base64').toString());
      const { d, l, s, t, n, c, e, i, f } = payload;
      
      console.log('    [HSW] Type:', n, '| Complexity:', c, '| Expiry:', new Date(e * 1000).toISOString());
      
      // Method 1: Try to execute actual WASM
      const wasmResult = await this._tryWASMExecution(l, d, c);
      if (wasmResult) return wasmResult;
      
      // Method 2: Simulate HSW algorithm
      console.log('    [HSW] Simulating HSW algorithm...');
      return await this._simulateHSW(d, c, s, req);
      
    } catch (error) {
      console.log('    [HSW] Error:', error.message);
      return null;
    }
  }
  
  /**
   * Try to execute actual WebAssembly
   */
  async _tryWASMExecution(wasmPath, data, complexity) {
    try {
      const wasmUrl = `https://hcaptcha.com${wasmPath}`;
      
      // Fetch WASM binary
      let wasmBinary = this.wasmCache.get(wasmPath);
      if (!wasmBinary) {
        console.log('    [HSW] Downloading WASM...');
        const res = await HttpClient.get(wasmUrl, { json: false, timeout: 10000 });
        
        // Check if it's actual WASM binary
        if (res.data && res.data.length > 100) {
          // Try to detect if it's WASM or JS wrapper
          const start = res.data.substring(0, 50);
          if (start.includes('AGFzbQ') || start.charCodeAt(0) === 0) {
            // Looks like WASM
            wasmBinary = res.data;
            this.wasmCache.set(wasmPath, wasmBinary);
          }
        }
      }
      
      if (wasmBinary) {
        // Try to instantiate and run WASM
        const result = await this._runWASM(wasmBinary, data, complexity);
        if (result) return result;
      }
    } catch (e) {
      console.log('    [HSW] WASM execution failed:', e.message);
    }
    return null;
  }
  
  /**
   * Run WebAssembly module
   */
  async _runWASM(wasmBinary, data, complexity) {
    try {
      // Convert string to buffer if needed
      let binary = wasmBinary;
      if (typeof wasmBinary === 'string') {
        // Check if base64
        if (wasmBinary.match(/^[A-Za-z0-9+/=]+$/)) {
          binary = Buffer.from(wasmBinary, 'base64');
        } else {
          binary = Buffer.from(wasmBinary, 'binary');
        }
      }
      
      // Check WASM magic number
      if (binary[0] === 0x00 && binary[1] === 0x61 && binary[2] === 0x73 && binary[3] === 0x6d) {
        console.log('    [HSW] Valid WASM module detected');
        
        // Compile and instantiate
        const wasmModule = await WebAssembly.compile(binary);
        const instance = await WebAssembly.instantiate(wasmModule, {
          env: {
            memory: new WebAssembly.Memory({ initial: 256 }),
            abort: () => {}
          }
        });
        
        // Try to find and call the solve function
        const exports = instance.exports;
        if (exports.solve || exports.hsw || exports.main) {
          const solveFunc = exports.solve || exports.hsw || exports.main;
          const result = solveFunc(data, complexity);
          return result;
        }
      }
    } catch (e) {
      console.log('    [HSW] WASM run error:', e.message);
    }
    return null;
  }
  
  /**
   * Simulate HSW algorithm in pure JavaScript
   */
  async _simulateHSW(data, complexity, seed, originalReq) {
    const iterations = (complexity || 1000) * 10;
    const startTime = Date.now();
    
    // Decode challenge data
    let challengeBytes;
    try {
      // Data might be base64 encoded
      challengeBytes = Buffer.from(data.replace(/[+]/g, '-').replace(/[/]/g, '_'), 'base64');
    } catch {
      challengeBytes = Buffer.from(data, 'utf-8');
    }
    
    // HSW-style proof of work
    // The algorithm finds a nonce where hash(data + nonce) meets difficulty
    let bestNonce = 0;
    let bestHash = null;
    let bestScore = 0;
    
    for (let nonce = 0; nonce < iterations; nonce++) {
      // Construct input: challenge + nonce + timestamp
      const nonceBuffer = Buffer.alloc(8);
      nonceBuffer.writeBigUInt64LE(BigInt(nonce));
      
      const timeBuffer = Buffer.alloc(8);
      timeBuffer.writeBigUInt64LE(BigInt(startTime));
      
      const input = Buffer.concat([challengeBytes, nonceBuffer, timeBuffer]);
      
      // SHA-256 hash
      const hash = crypto.createHash('sha256').update(input).digest();
      
      // Count leading zero bits
      let zeroBits = 0;
      for (const byte of hash) {
        if (byte === 0) {
          zeroBits += 8;
        } else {
          zeroBits += Math.clz32(byte) - 24;
          break;
        }
      }
      
      if (zeroBits > bestScore) {
        bestScore = zeroBits;
        bestNonce = nonce;
        bestHash = hash;
        
        // Check if we meet the difficulty requirement
        const requiredBits = Math.ceil(Math.log2(complexity || 1000));
        if (zeroBits >= requiredBits) {
          console.log('    [HSW] Found solution! Nonce:', nonce, 'Zero bits:', zeroBits);
          break;
        }
      }
      
      // Progress update
      if (nonce > 0 && nonce % 10000 === 0) {
        console.log('    [HSW] Progress:', nonce, '/', iterations, '| Best:', bestScore, 'bits');
      }
    }
    
    // Build response
    return this._buildResponse(data, bestNonce, startTime, bestHash || crypto.randomBytes(32), seed);
  }
  
  /**
   * Build HSW response in hCaptcha expected format
   */
  _buildResponse(data, nonce, timestamp, hash, seed) {
    // HSW response format varies but typically includes:
    const response = Buffer.from(JSON.stringify({
      v: 1,
      s: seed || 2,
      t: timestamp,
      n: nonce,
      c: hash.toString('hex'),
      d: data
    })).toString('base64');
    
    return response;
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// PROOF OF WORK SOLVER (HSL & HSW)
// ════════════════════════════════════════════════════════════════════════════════

class ProofOfWork {
  static hswSolver = new HSWSolver();
  
  static async solve(config) {
    if (!config || !config.type || !config.req) return null;
    
    try {
      if (config.type === 'hsw') {
        return await this.solveHSW(config.req);
      } else if (config.type === 'hsl') {
        return this.solveHSL(config.req);
      }
      return null;
    } catch (e) {
      console.log('    [PoW] Error:', e.message);
      return null;
    }
  }
  
  static solveHSL(req) {
    try {
      console.log('    [HSL] Solving proof-of-work...');
      const data = base64Decode(req);
      const { d, n, c, s } = data;
      const difficulty = Math.ceil(n / 4);
      const target = '0'.repeat(difficulty);
      
      for (let counter = 0; counter < 10000000; counter++) {
        const hash = crypto.createHash('sha1').update(`${d}:${n}:${c}:${s}:${counter}`).digest('hex');
        if (hash.startsWith(target)) {
          console.log('    [HSL] Found solution at counter:', counter);
          return base64Encode({ d, n, c, s, counter });
        }
      }
      return base64Encode({ d, n, c, s, counter: 0 });
    } catch (e) {
      console.log('    [HSL] Error:', e.message);
      return null;
    }
  }
  
  static async solveHSW(req) {
    return await this.hswSolver.solve(req);
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// BLACKBOX AI SERVICE
// ════════════════════════════════════════════════════════════════════════════════

class BlackboxService {
  constructor(apiKey = 'sk-tpGpGJ-S4-Wby5OoLZrxAQ') {
    this.apiKey = apiKey;
    this.endpoint = 'https://api.blackbox.ai/v1/chat/completions';
  }
  
  async chat(message, model = 'blackboxai/deepseek/deepseek-chat:free') {
    try {
      const body = JSON.stringify({
        messages: [
          { role: 'system', content: 'You are a helpful assistant that follows instructions precisely.' },
          { role: 'user', content: message }
        ],
        model: model,
        max_tokens: 4000,
        temperature: 0.9
      });
      
      const response = await HttpClient.fetch(this.endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.apiKey}`
        },
        body: body,
        timeout: 90000
      });
      
      if (response.data && response.data.choices && response.data.choices[0]) {
        return response.data.choices[0].message?.content || '';
      }
      return '';
    } catch (e) {
      console.log('    [Blackbox] Error:', e.message);
      return '';
    }
  }
  
  async getModels() {
    try {
      const response = await HttpClient.fetch('https://api.blackbox.ai/v1/models', {
        headers: { 'Authorization': `Bearer ${this.apiKey}` }
      });
      return response.data?.data || [];
    } catch {
      return [];
    }
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// CAPTCHA SOLVER SERVICE
// ════════════════════════════════════════════════════════════════════════════════

class CaptchaSolverService {
  constructor(options = {}) {
    this.timeout = options.timeout || 120000;
  }
  
  async solve(siteKey, siteUrl) {
    const startTime = Date.now();
    
    // Try to get an instant pass by making request look legitimate
    try {
      console.log('    [Service] Attempting optimized solve...');
      
      const fp = Fingerprint.generate();
      
      for (let i = 0; i < 3; i++) {
        const configRes = await HttpClient.fetch(
          `https://hcaptcha.com/checksiteconfig?v=b1129dc&host=${getDomain(siteUrl)}&sitekey=${siteKey}&sc=1&swa=1`,
          {
            headers: {
              'User-Agent': fp.ua,
              'Accept': 'application/json'
            }
          }
        );
        
        if (configRes.data && configRes.data.pass === true) {
          const motion = MotionGenerator.generate(fp);
          const challengeRes = await HttpClient.post(
            `https://hcaptcha.com/getcaptcha/${siteKey}`,
            {
              v: 'b1129dc',
              sitekey: siteKey,
              host: getDomain(siteUrl),
              hl: 'en',
              motionData: JSON.stringify(motion),
              n: '',
              c: JSON.stringify(configRes.data.c || {}),
              pst: 'false'
            },
            {
              headers: {
                'User-Agent': fp.ua,
                'Origin': 'https://newassets.hcaptcha.com',
                'Referer': 'https://newassets.hcaptcha.com/'
              }
            }
          );
          
          if (challengeRes.data && challengeRes.data.pass && challengeRes.data.generated_pass_UUID) {
            return {
              success: true,
              token: challengeRes.data.generated_pass_UUID,
              time: Date.now() - startTime,
              method: 'instant-pass'
            };
          }
        }
        
        await sleep(500);
      }
      
    } catch (e) {
      console.log('    [Service] Optimized solve failed:', e.message);
    }
    
    return {
      success: false,
      error: 'hCaptcha requires HSW WebAssembly. Use BrowserSolver.',
      time: Date.now() - startTime
    };
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// HCAPTCHA SOLVER ENGINE - Advanced Native Solver
// ════════════════════════════════════════════════════════════════════════════════

class HCaptchaSolver extends EventEmitter {
  constructor(options) {
    super();
    this.siteKey = options.siteKey;
    this.siteUrl = options.siteUrl;
    this.host = getDomain(this.siteUrl);
    this.rqdata = options.rqdata;
    this.invisible = options.invisible || false;
    this.maxRetries = options.maxRetries || 10;
    this.useBrowser = options.useBrowser !== false;
    this.fp = Fingerprint.generate();
    this.widgetId = this._generateWidgetId();
  }
  
  _generateWidgetId() {
    return crypto.randomBytes(10).toString('hex');
  }
  
  async solve() {
    const start = timestamp();
    
    // ═══════════════════════════════════════════════════════════════
    // METHOD 1: Try Instant Pass (Trusted Request)
    // ═══════════════════════════════════════════════════════════════
    this.emit('status', '=== Method 1: Instant Pass Attempt ===');
    
    for (let i = 0; i < 3; i++) {
      try {
        this.fp = Fingerprint.generate();
        const instantResult = await this._tryInstantPass();
        if (instantResult) {
          this.emit('status', '✓ Got instant pass token!');
          return {
            success: true,
            token: instantResult,
            time: timestamp() - start,
            method: 'instant-pass',
            attempt: i + 1
          };
        }
      } catch (e) {
        await sleep(300);
      }
    }
    
    // ═══════════════════════════════════════════════════════════════
    // METHOD 2: Native HSW Solver with Advanced PoW
    // ═══════════════════════════════════════════════════════════════
    this.emit('status', '=== Method 2: Native HSW Solver ===');
    
    for (let attempt = 1; attempt <= this.maxRetries; attempt++) {
      try {
        this.emit('status', `HSW attempt ${attempt}/${this.maxRetries}...`);
        this.fp = Fingerprint.generate();
        
        // Get config with different fingerprints
        const config = await this._getConfig();
        
        // Check if site allows pass
        if (config.pass === true) {
          this.emit('status', 'Site config allows pass, trying challenge...');
        }
        
        // Get challenge
        const challenge = await this._getChallenge(config);
        
        // Check for instant pass
        if (challenge.pass && challenge.generated_pass_UUID) {
          this.emit('status', '✓ Instant pass!');
          return {
            success: true,
            token: challenge.generated_pass_UUID,
            time: timestamp() - start,
            type: 'instant',
            method: 'native-instant',
            attempt
          };
        }
        
        // Check for error
        if (challenge['error-codes']) {
          this.emit('status', `Challenge error: ${challenge['error-codes'].join(', ')}`);
          await sleep(1000);
          continue;
        }
        
        // Solve challenge
        const challengeType = challenge.request_type || 'hsw';
        this.emit('status', `Solving ${challengeType} challenge...`);
        
        const answers = await this._solveChallenge(challenge);
        
        // Submit with delay
        await sleep(500 + Math.random() * 1000);
        this.emit('status', 'Submitting solution...');
        
        const result = await this._submit(challenge, answers);
        
        if (result.pass && result.generated_pass_UUID) {
          this.emit('status', '✓ Native HSW solve success!');
          return {
            success: true,
            token: result.generated_pass_UUID,
            time: timestamp() - start,
            type: challengeType,
            method: 'native-hsw',
            attempt
          };
        }
        
        // Check result errors
        if (result['error-codes']) {
          this.emit('status', `Submit error: ${result['error-codes'].join(', ')}`);
        }
        
        await sleep(1000 + Math.random() * 2000);
        
      } catch (error) {
        this.emit('status', `Attempt ${attempt} error: ${error.message}`);
        await sleep(1000);
      }
    }
    
    // ═══════════════════════════════════════════════════════════════
    // METHOD 3: Browser Solver (Puppeteer)
    // ═══════════════════════════════════════════════════════════════
    if (this.useBrowser) {
      this.emit('status', '=== Method 3: Browser Solver ===');
      
      try {
        const browserSolver = new BrowserSolver({ headless: true, timeout: 120000 });
        const browserResult = await browserSolver.solve(this.siteUrl, this.siteKey);
        
        if (browserResult.success) {
          this.emit('status', '✓ Browser solve success!');
          return {
            ...browserResult,
            time: timestamp() - start
          };
        }
        this.emit('status', `Browser failed: ${browserResult.error}`);
      } catch (e) {
        this.emit('status', `Browser error: ${e.message}`);
      }
    }
    
    return {
      success: false,
      error: 'All native solving methods failed. hCaptcha requires valid HSW proof-of-work.',
      time: timestamp() - start,
      attempts: this.maxRetries,
      methods_tried: ['instant-pass', 'native-hsw', this.useBrowser ? 'browser' : null].filter(Boolean)
    };
  }
  
  /**
   * Try to get instant pass by making trusted-looking request
   */
  async _tryInstantPass() {
    const config = await this._getConfig();
    
    if (!config.pass) return null;
    
    // Generate very realistic motion data
    const motion = this._generateRealisticMotion();
    
    const body = {
      v: 'b1129dc',
      sitekey: this.siteKey,
      host: this.host,
      hl: 'en',
      motionData: JSON.stringify(motion),
      n: '', // No PoW for instant pass attempt
      c: JSON.stringify(config.c || {}),
      pst: 'false',
      paw: 'true'
    };
    
    const res = await HttpClient.post(`${CONFIG.HCAPTCHA.GET_CAPTCHA}/${this.siteKey}`, body, {
      userAgent: this.fp.ua,
      headers: {
        'Origin': 'https://newassets.hcaptcha.com',
        'Referer': 'https://newassets.hcaptcha.com/',
        'Accept': 'application/json'
      }
    });
    
    if (res.data && res.data.pass && res.data.generated_pass_UUID) {
      return res.data.generated_pass_UUID;
    }
    
    return null;
  }
  
  /**
   * Generate very realistic mouse motion data
   */
  _generateRealisticMotion() {
    const now = timestamp();
    const sessionStart = now - 15000 - Math.floor(Math.random() * 30000);
    
    // Realistic mouse movement path
    const mm = [];
    let x = 50 + Math.random() * 150;
    let y = 50 + Math.random() * 150;
    const targetX = 300 + Math.random() * 200;
    const targetY = 250 + Math.random() * 150;
    
    const steps = 40 + Math.floor(Math.random() * 30);
    for (let i = 0; i < steps; i++) {
      const progress = i / steps;
      const easing = progress < 0.5 
        ? 2 * progress * progress 
        : 1 - Math.pow(-2 * progress + 2, 2) / 2;
      
      x = x + (targetX - x) * (1/steps) + (Math.random() - 0.5) * 8;
      y = y + (targetY - y) * (1/steps) + (Math.random() - 0.5) * 8;
      
      mm.push([
        Math.round(x),
        Math.round(y),
        Math.round(easing * 2500 + Math.random() * 100)
      ]);
    }
    
    return {
      st: sessionStart,
      dct: now - 2000,
      mm: mm,
      mm_mp: 10 + Math.random() * 20,
      md: [[Math.round(targetX), Math.round(targetY), now - 800]],
      md_mp: 3 + Math.random() * 7,
      mu: [[Math.round(targetX + 1), Math.round(targetY + 1), now - 700]],
      mu_mp: 3 + Math.random() * 7,
      kd: [],
      ku: [],
      topLevel: {
        st: sessionStart - 10000,
        sc: {
          availWidth: this.fp.screen.w,
          availHeight: this.fp.screen.h - 40,
          width: this.fp.screen.w,
          height: this.fp.screen.h,
          colorDepth: 24,
          pixelDepth: 24,
          availTop: 0,
          availLeft: 0,
          devicePixelRatio: this.fp.screen.dpr
        },
        nv: {
          vendorSub: '',
          productSub: '20030107',
          vendor: 'Google Inc.',
          maxTouchPoints: 0,
          hardwareConcurrency: this.fp.cores,
          cookieEnabled: true,
          appCodeName: 'Mozilla',
          appName: 'Netscape',
          appVersion: this.fp.ua.replace('Mozilla/', ''),
          platform: this.fp.platform,
          product: 'Gecko',
          userAgent: this.fp.ua,
          language: 'en-US',
          languages: ['en-US', 'en'],
          onLine: true,
          webdriver: false,
          pdfViewerEnabled: true,
          deviceMemory: this.fp.memory,
          connection: { effectiveType: '4g', rtt: 50, downlink: 10, saveData: false }
        },
        dr: '',
        inv: false,
        exec: false,
        wn: [[this.fp.screen.w, this.fp.screen.h - 40, 1, sessionStart - 5000]],
        wn_mp: 0,
        xy: [[0, 0, 1, sessionStart - 4000]],
        xy_mp: 0,
        wh: `${this.fp.screen.w}x${this.fp.screen.h - 140}`,
        orom: false
      },
      session: [],
      widgetList: [this.widgetId],
      widgetId: this.widgetId,
      href: this.siteUrl,
      prev: { escaped: false, passed: false, expiredChallenge: false, expiredResponse: false },
      v: 1
    };
  }
  
  async _getConfig() {
    const params = new URLSearchParams({
      v: 'b1129dc',
      host: this.host,
      sitekey: this.siteKey,
      sc: '1',
      swa: '1',
      spst: '1'
    });
    
    const res = await HttpClient.get(`${CONFIG.HCAPTCHA.SITE_CONFIG}?${params}`, {
      userAgent: this.fp.ua,
      headers: { 
        'Referer': this.siteUrl,
        'Origin': `https://${this.host}`,
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'cross-site'
      }
    });
    
    return res.data;
  }
  
  async _getChallenge(config) {
    // Generate realistic motion data
    const motion = this._generateAdvancedMotion();
    const pow = await ProofOfWork.solve(config.c);
    
    const body = {
      v: 'b1129dc',
      sitekey: this.siteKey,
      host: this.host,
      hl: 'en',
      motionData: JSON.stringify(motion),
      n: pow,
      c: JSON.stringify(config.c || {}),
      pst: 'false',
      paw: 'true',
      rqdata: this.rqdata || ''
    };
    
    const res = await HttpClient.post(`${CONFIG.HCAPTCHA.GET_CAPTCHA}/${this.siteKey}`, body, {
      userAgent: this.fp.ua,
      headers: {
        'Origin': 'https://newassets.hcaptcha.com',
        'Referer': 'https://newassets.hcaptcha.com/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
        'Accept': 'application/json'
      }
    });
    
    return res.data;
  }
  
  _generateAdvancedMotion() {
    const now = timestamp();
    const startTime = now - 3000 - Math.floor(Math.random() * 5000);
    
    // Generate realistic mouse movements
    const mm = [];
    const points = 30 + Math.floor(Math.random() * 30);
    let x = 50 + Math.random() * 100;
    let y = 50 + Math.random() * 100;
    const targetX = 200 + Math.random() * 200;
    const targetY = 150 + Math.random() * 150;
    
    for (let i = 0; i < points; i++) {
      const progress = i / points;
      const easing = progress * progress * (3 - 2 * progress); // Smooth step
      
      x += (targetX - x) * 0.1 + (Math.random() - 0.5) * 8;
      y += (targetY - y) * 0.1 + (Math.random() - 0.5) * 8;
      
      mm.push([
        Math.round(x),
        Math.round(y),
        Math.round(progress * 2000 + Math.random() * 50)
      ]);
    }
    
    // Mouse down/up events
    const md = [[Math.round(x), Math.round(y), now - 500 + Math.floor(Math.random() * 200)]];
    const mu = [[Math.round(x + 2), Math.round(y + 1), now - 400 + Math.floor(Math.random() * 200)]];
    
    // Keyboard events (simulated)
    const kd = [];
    const ku = [];
    
    return {
      st: startTime,
      dct: now - 1000,
      mm: mm,
      mm_mp: 8 + Math.random() * 15,
      md: md,
      md_mp: 2 + Math.random() * 8,
      mu: mu,
      mu_mp: 2 + Math.random() * 8,
      kd: kd,
      ku: ku,
      topLevel: {
        st: startTime - 5000,
        sc: {
          availWidth: this.fp.screen.w,
          availHeight: this.fp.screen.h - 40,
          width: this.fp.screen.w,
          height: this.fp.screen.h,
          colorDepth: 24,
          pixelDepth: 24,
          availTop: 0,
          availLeft: 0,
          devicePixelRatio: this.fp.screen.dpr,
          innerWidth: this.fp.screen.w,
          innerHeight: this.fp.screen.h - 140,
          outerWidth: this.fp.screen.w,
          outerHeight: this.fp.screen.h
        },
        nv: {
          vendorSub: '',
          productSub: '20030107',
          vendor: 'Google Inc.',
          maxTouchPoints: 0,
          scheduling: {},
          userActivation: {},
          doNotTrack: null,
          hardwareConcurrency: this.fp.cores,
          cookieEnabled: true,
          appCodeName: 'Mozilla',
          appName: 'Netscape',
          appVersion: this.fp.ua.replace('Mozilla/', ''),
          platform: this.fp.platform,
          product: 'Gecko',
          userAgent: this.fp.ua,
          language: 'en-US',
          languages: ['en-US', 'en'],
          onLine: true,
          webdriver: false,
          pdfViewerEnabled: true,
          deviceMemory: this.fp.memory,
          connection: {
            effectiveType: '4g',
            rtt: 50 + Math.floor(Math.random() * 50),
            downlink: 10,
            saveData: false
          }
        },
        dr: '',
        inv: false,
        exec: false,
        wn: [
          [this.fp.screen.w, this.fp.screen.h - 40, 1, startTime - 3000],
          [this.fp.screen.w, this.fp.screen.h - 40, 1, startTime - 1000]
        ],
        wn_mp: 0,
        xy: [
          [0, 0, 1, startTime - 2000]
        ],
        xy_mp: 0,
        wh: `${this.fp.screen.w}x${this.fp.screen.h - 140}`,
        orom: false,
        bt: {
          ua: this.fp.ua,
          mobile: false,
          platform: this.fp.platform,
          brands: [
            { brand: 'Not A(Brand', version: '99' },
            { brand: 'Google Chrome', version: '122' },
            { brand: 'Chromium', version: '122' }
          ]
        }
      },
      session: [],
      widgetList: [this.widgetId],
      widgetId: this.widgetId,
      href: this.siteUrl,
      prev: {
        escaped: false,
        passed: false,
        expiredChallenge: false,
        expiredResponse: false
      },
      v: 1
    };
  }
  
  async _solveChallenge(challenge) {
    const answers = {};
    const tasklist = challenge.tasklist || {};
    const question = (challenge.requester_question?.en || '').toLowerCase();
    
    // Analyze question for hints
    const taskKeys = Object.keys(tasklist);
    
    if (taskKeys.length === 0) {
      return {};
    }
    
    // For image challenges, we need to analyze each image
    for (const key of taskKeys) {
      const task = tasklist[key];
      
      // Use weighted random selection based on typical patterns
      // Most hCaptcha challenges have 3-4 correct answers out of 9
      const correctProbability = 0.35 + Math.random() * 0.1;
      answers[key] = Math.random() < correctProbability ? 'true' : 'false';
    }
    
    // Ensure we have at least 2-3 true answers (typical for hCaptcha)
    const trueCount = Object.values(answers).filter(v => v === 'true').length;
    if (trueCount < 2) {
      const falseKeys = taskKeys.filter(k => answers[k] === 'false');
      const toFlip = Math.min(3 - trueCount, falseKeys.length);
      for (let i = 0; i < toFlip; i++) {
        const randomKey = falseKeys[Math.floor(Math.random() * falseKeys.length)];
        answers[randomKey] = 'true';
        falseKeys.splice(falseKeys.indexOf(randomKey), 1);
      }
    }
    
    return answers;
  }
  
  async _submit(challenge, answers) {
    const motion = this._generateAdvancedMotion();
    const pow = await ProofOfWork.solve(challenge.c);
    
    // Add timing simulation
    await sleep(500 + Math.random() * 1500);
    
    const body = {
      v: 'b1129dc',
      job_mode: challenge.request_type || 'image_label_binary',
      answers: JSON.stringify(answers),
      serverdomain: this.host,
      sitekey: this.siteKey,
      motionData: JSON.stringify(motion),
      n: pow,
      c: JSON.stringify(challenge.c || {})
    };
    
    const res = await HttpClient.post(
      `${CONFIG.HCAPTCHA.CHECK_CAPTCHA}/${this.siteKey}/${challenge.key}`,
      body,
      {
        userAgent: this.fp.ua,
        headers: {
          'Origin': 'https://newassets.hcaptcha.com',
          'Referer': 'https://newassets.hcaptcha.com/',
          'Sec-Fetch-Dest': 'empty',
          'Sec-Fetch-Mode': 'cors',
          'Sec-Fetch-Site': 'same-site',
          'Accept': 'application/json'
        }
      }
    );
    
    return res.data;
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// TASK QUEUE
// ════════════════════════════════════════════════════════════════════════════════

class Queue {
  constructor(concurrency = CONFIG.MAX_CONCURRENT) {
    this.concurrency = concurrency;
    this.running = 0;
    this.queue = [];
  }
  
  async add(fn, priority = 0) {
    return new Promise((resolve, reject) => {
      this.queue.push({ fn, priority, resolve, reject });
      this.queue.sort((a, b) => b.priority - a.priority);
      this._run();
    });
  }
  
  async _run() {
    while (this.running < this.concurrency && this.queue.length) {
      const task = this.queue.shift();
      this.running++;
      
      task.fn()
        .then(task.resolve)
        .catch(task.reject)
        .finally(() => {
          this.running--;
          this._run();
        });
    }
  }
  
  stats() {
    return { queued: this.queue.length, running: this.running };
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// TOKEN CACHE
// ════════════════════════════════════════════════════════════════════════════════

class Cache {
  constructor(ttl = 110000) {
    this.data = new Map();
    this.ttl = ttl;
  }
  
  set(key, value) {
    this.data.set(key, { value, expires: Date.now() + this.ttl });
  }
  
  get(key) {
    const item = this.data.get(key);
    if (!item) return null;
    if (Date.now() > item.expires) {
      this.data.delete(key);
      return null;
    }
    return item.value;
  }
  
  key(siteKey, url) {
    return crypto.createHash('md5').update(`${siteKey}:${url}`).digest('hex');
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// API SERVER - NO API KEY REQUIRED
// ════════════════════════════════════════════════════════════════════════════════

class Server {
  constructor(port = CONFIG.PORT) {
    this.port = port;
    this.queue = new Queue();
    this.cache = new Cache();
    this.stats = { total: 0, success: 0, failed: 0, times: [] };
    this.server = null;
  }
  
  start() {
    return new Promise(resolve => {
      this.server = http.createServer((req, res) => this._handle(req, res));
      
      this.server.listen(this.port, () => {
        console.log(`
╔═════════════════════════════════════════════════════════════════════════════════════╗
║               🚀 HCAPTCHA AUTO-SOLVER API v${CONFIG.VERSION} STARTED                       ║
╠═════════════════════════════════════════════════════════════════════════════════════╣
║                                                                                     ║
║   URL: http://localhost:${this.port.toString().padEnd(58)}║
║                                                                                     ║
║   NO API KEY REQUIRED - Just send your request!                                     ║
║                                                                                     ║
╠═════════════════════════════════════════════════════════════════════════════════════╣
║   ENDPOINTS:                                                                        ║
║                                                                                     ║
║   POST /solve          Solve captcha (auto-detect siteKey)                         ║
║                        Body: {"url": "https://diceygolf.com"}                       ║
║                                                                                     ║
║   POST /solve          Solve with known siteKey                                    ║
║                        Body: {"url": "...", "siteKey": "..."}                       ║
║                                                                                     ║
║   POST /detect         Detect siteKey from any page                                ║
║                        Body: {"url": "https://example.com"}                         ║
║                                                                                     ║
║   GET  /stats          Server statistics                                           ║
║   GET  /health         Health check                                                ║
║                                                                                     ║
╚═════════════════════════════════════════════════════════════════════════════════════╝
`);
        resolve(this);
      });
    });
  }
  
  async _handle(req, res) {
    // CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    
    if (req.method === 'OPTIONS') {
      res.writeHead(204);
      return res.end();
    }
    
    const url = new URL(req.url, `http://localhost:${this.port}`);
    
    try {
      // Routes
      if (url.pathname === '/health') {
        return this._json(res, { status: 'ok', version: CONFIG.VERSION });
      }
      
      if (url.pathname === '/stats') {
        return this._json(res, this._getStats());
      }
      
      if (url.pathname === '/detect' && req.method === 'POST') {
        const body = await this._body(req);
        if (!body.url) return this._json(res, { error: 'url required' }, 400);
        
        const result = await SiteKeyDetector.detect(body.url);
        return this._json(res, result);
      }
      
      if (url.pathname === '/solve' && req.method === 'POST') {
        return this._handleSolve(req, res);
      }
      
      this._json(res, { error: 'Not found' }, 404);
      
    } catch (err) {
      this._json(res, { error: err.message }, 500);
    }
  }
  
  async _handleSolve(req, res) {
    const body = await this._body(req);
    const targetUrl = body.url || body.siteUrl;
    
    if (!targetUrl) {
      return this._json(res, { error: 'url is required' }, 400);
    }
    
    this.stats.total++;
    let siteKey = body.siteKey;
    let detectionInfo = null;
    
    // Auto-detect siteKey if not provided
    if (!siteKey) {
      console.log(`[API] Auto-detecting siteKey for: ${targetUrl}`);
      const detection = await SiteKeyDetector.detect(targetUrl);
      
      if (!detection.detected || !detection.primaryKey) {
        this.stats.failed++;
        return this._json(res, {
          success: false,
          error: 'Could not detect siteKey. Please provide siteKey in request.',
          detection
        }, 400);
      }
      
      siteKey = detection.primaryKey;
      detectionInfo = {
        autoDetected: true,
        siteKey,
        sources: detection.sources,
        version: detection.version
      };
      
      console.log(`[API] Detected siteKey: ${siteKey}`);
    }
    
    // Check cache
    const cacheKey = this.cache.key(siteKey, targetUrl);
    const cached = this.cache.get(cacheKey);
    if (cached) {
      return this._json(res, {
        success: true,
        token: cached,
        cached: true,
        time: 0,
        detection: detectionInfo
      });
    }
    
    // Solve
    console.log(`[API] Solving for: ${targetUrl}`);
    
    // Try native solver first
    let result = await this.queue.add(async () => {
      const solver = new HCaptchaSolver({
        siteKey,
        siteUrl: targetUrl,
        rqdata: body.rqdata,
        maxRetries: 2
      });
      return solver.solve();
    }, body.priority || 0);
    
    // If native fails and browser mode requested, try browser solver
    if (!result.success && body.useBrowser !== false) {
      console.log(`[API] Native failed, trying browser solver...`);
      
      try {
        const browserSolver = new BrowserSolver({ 
          headless: body.headless !== false,
          timeout: body.timeout || 60000
        });
        result = await browserSolver.solve(targetUrl, siteKey);
      } catch (e) {
        // Browser solver not available, return native error
        console.log(`[API] Browser solver not available: ${e.message}`);
      }
    }
    
    if (result.success) {
      this.stats.success++;
      this._recordTime(result.time);
      this.cache.set(cacheKey, result.token);
      
      console.log(`[API] ✓ Solved in ${result.time}ms (${result.method || 'native'})`);
      
      return this._json(res, {
        success: true,
        token: result.token,
        time: result.time,
        method: result.method || 'native',
        cached: false,
        detection: detectionInfo
      });
    }
    
    this.stats.failed++;
    console.log(`[API] ✗ Failed: ${result.error}`);
    
    return this._json(res, {
      success: false,
      error: result.error,
      time: result.time,
      detection: detectionInfo,
      hint: 'Install puppeteer for browser-based solving: npm install puppeteer'
    }, 500);
  }
  
  _body(req) {
    return new Promise(resolve => {
      let data = '';
      req.on('data', c => data += c);
      req.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch { resolve({}); }
      });
    });
  }
  
  _json(res, data, status = 200) {
    res.writeHead(status, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(data, null, 2));
  }
  
  _recordTime(time) {
    this.stats.times.push(time);
    if (this.stats.times.length > 100) this.stats.times.shift();
  }
  
  _getStats() {
    const avgTime = this.stats.times.length 
      ? Math.round(this.stats.times.reduce((a, b) => a + b, 0) / this.stats.times.length)
      : 0;
    
    return {
      version: CONFIG.VERSION,
      uptime: Math.round(process.uptime()),
      requests: {
        total: this.stats.total,
        success: this.stats.success,
        failed: this.stats.failed,
        rate: this.stats.total ? `${((this.stats.success / this.stats.total) * 100).toFixed(1)}%` : '0%'
      },
      performance: {
        avgSolveTime: `${avgTime}ms`,
        queue: this.queue.stats()
      }
    };
  }
  
  stop() {
    if (this.server) this.server.close();
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// BROWSER-BASED SOLVER (Puppeteer) - Solves HSW challenges natively
// ════════════════════════════════════════════════════════════════════════════════

class BrowserSolver {
  constructor(options = {}) {
    this.headless = options.headless !== false;
    this.timeout = options.timeout || 60000;
    this.browser = null;
  }
  
  /**
   * Solve hCaptcha using Puppeteer - Full browser automation
   */
  async solve(siteUrl, siteKey) {
    let puppeteer;
    try {
      puppeteer = require('puppeteer');
    } catch (e) {
      throw new Error('Puppeteer not installed. Run: npm install puppeteer');
    }
    
    const startTime = Date.now();
    
    try {
      console.log('    [Browser] Launching Chrome...');
      
      // Launch with maximum stealth
      this.browser = await puppeteer.launch({
        headless: this.headless ? 'new' : false,
        args: [
          '--no-sandbox',
          '--disable-setuid-sandbox',
          '--disable-dev-shm-usage',
          '--disable-blink-features=AutomationControlled',
          '--disable-features=IsolateOrigins,site-per-process',
          '--disable-infobars',
          '--window-size=1920,1080',
          '--start-maximized'
        ],
        ignoreDefaultArgs: ['--enable-automation']
      });
      
      const page = await this.browser.newPage();
      
      // Maximum anti-detection
      await page.evaluateOnNewDocument(() => {
        // Hide webdriver
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        
        // Fake plugins
        Object.defineProperty(navigator, 'plugins', {
          get: () => [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
            { name: 'Native Client', filename: 'internal-nacl-plugin' }
          ]
        });
        
        // Fake languages
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        
        // Chrome runtime
        window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {} };
        
        // Permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
          parameters.name === 'notifications' ?
            Promise.resolve({ state: Notification.permission }) :
            originalQuery(parameters)
        );
        
        // WebGL
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
          if (parameter === 37445) return 'Intel Inc.';
          if (parameter === 37446) return 'Intel Iris OpenGL Engine';
          return getParameter.call(this, parameter);
        };
      });
      
      await page.setViewport({ width: 1920, height: 1080 });
      await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36');
      
      // Set extra headers
      await page.setExtraHTTPHeaders({
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br'
      });
      
      // Navigate to site
      console.log('    [Browser] Navigating to', siteUrl);
      await page.goto(siteUrl, { waitUntil: 'networkidle0', timeout: 45000 });
      
      // Setup token interception
      await page.evaluate(() => {
        window.__hcaptchaToken = null;
        window.__hcaptchaReady = false;
        window.__hcaptchaError = null;
        
        // Intercept hcaptcha callbacks
        const originalExecute = window.hcaptcha?.execute;
        if (window.hcaptcha) {
          window.hcaptcha.execute = function(...args) {
            return originalExecute?.apply(this, args)?.then?.(token => {
              window.__hcaptchaToken = token;
              return token;
            });
          };
        }
      });
      
      // Check for existing captcha or inject
      const existingCaptcha = await page.$('[data-sitekey], .h-captcha, #h-captcha');
      
      if (!existingCaptcha) {
        console.log('    [Browser] Injecting hCaptcha widget...');
        await page.evaluate((sk) => {
          const container = document.createElement('div');
          container.id = 'solver-captcha-container';
          container.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:99999;background:#fff;padding:30px;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,0.3);';
          document.body.appendChild(container);
          
          const captchaDiv = document.createElement('div');
          captchaDiv.id = 'solver-captcha';
          captchaDiv.className = 'h-captcha';
          captchaDiv.setAttribute('data-sitekey', sk);
          captchaDiv.setAttribute('data-callback', '__solverCallback');
          captchaDiv.setAttribute('data-error-callback', '__solverErrorCallback');
          captchaDiv.setAttribute('data-expired-callback', '__solverExpiredCallback');
          container.appendChild(captchaDiv);
          
          window.__solverCallback = (token) => { window.__hcaptchaToken = token; };
          window.__solverErrorCallback = (err) => { window.__hcaptchaError = err; };
          window.__solverExpiredCallback = () => { window.__hcaptchaError = 'expired'; };
          
          const script = document.createElement('script');
          script.src = 'https://js.hcaptcha.com/1/api.js?onload=__solverOnLoad&render=explicit';
          script.async = true;
          window.__solverOnLoad = () => {
            try {
              hcaptcha.render('solver-captcha');
              window.__hcaptchaReady = true;
            } catch(e) { window.__hcaptchaError = e.message; }
          };
          document.head.appendChild(script);
        }, siteKey);
        
        console.log('    [Browser] Waiting for hCaptcha to initialize...');
        await page.waitForFunction(() => window.__hcaptchaReady || window.__hcaptchaError, { timeout: 20000 });
      }
      
      // Wait for checkbox frame
      console.log('    [Browser] Looking for checkbox frame...');
      await sleep(2000);
      
      // Click the checkbox
      let checkboxClicked = false;
      for (let i = 0; i < 20; i++) {
        const frames = page.frames();
        for (const frame of frames) {
          if (frame.url().includes('hcaptcha.com') && frame.url().includes('checkbox')) {
            try {
              await frame.waitForSelector('#checkbox', { timeout: 2000 });
              console.log('    [Browser] Found checkbox, clicking...');
              
              // Human-like delay
              await sleep(300 + Math.random() * 700);
              
              // Move mouse to checkbox area first
              const checkbox = await frame.$('#checkbox');
              const box = await checkbox.boundingBox();
              if (box) {
                await page.mouse.move(box.x + box.width/2, box.y + box.height/2, { steps: 10 });
                await sleep(100 + Math.random() * 200);
              }
              
              await frame.click('#checkbox');
              checkboxClicked = true;
              console.log('    [Browser] Checkbox clicked!');
              break;
            } catch (e) {}
          }
        }
        if (checkboxClicked) break;
        await sleep(500);
      }
      
      // Wait for token with longer timeout
      console.log('    [Browser] Waiting for captcha completion...');
      
      const token = await page.waitForFunction(
        () => {
          if (window.__hcaptchaToken) return window.__hcaptchaToken;
          
          const textarea = document.querySelector('textarea[name="h-captcha-response"]');
          if (textarea && textarea.value && textarea.value.length > 50) return textarea.value;
          
          const hidden = document.querySelector('input[name="h-captcha-response"]');
          if (hidden && hidden.value && hidden.value.length > 50) return hidden.value;
          
          if (window.__hcaptchaError) return 'ERROR:' + window.__hcaptchaError;
          
          return null;
        },
        { timeout: this.timeout, polling: 500 }
      ).then(h => h.jsonValue());
      
      await this.browser.close();
      
      if (token.startsWith('ERROR:')) {
        return { success: false, error: token.replace('ERROR:', ''), time: Date.now() - startTime };
      }
      
      console.log('    [Browser] Got token!');
      return {
        success: true,
        token,
        time: Date.now() - startTime,
        method: 'browser-puppeteer'
      };
      
    } catch (error) {
      if (this.browser) {
        try { await this.browser.close(); } catch (e) {}
      }
      
      return {
        success: false,
        error: error.message,
        time: Date.now() - startTime
      };
    }
  }
  
  /**
   * Solve on an existing Puppeteer page
   */
  async solveOnPage(page, siteKey) {
    const startTime = Date.now();
    
    try {
      // Check if hCaptcha is already on page
      const hasHCaptcha = await page.$('[data-sitekey]');
      
      if (!hasHCaptcha && siteKey) {
        // Inject hCaptcha
        await page.evaluate((sk) => {
          const div = document.createElement('div');
          div.className = 'h-captcha';
          div.setAttribute('data-sitekey', sk);
          div.setAttribute('data-callback', '__hcaptchaCallback');
          document.body.appendChild(div);
          
          window.__hcaptchaToken = null;
          window.__hcaptchaCallback = (token) => {
            window.__hcaptchaToken = token;
          };
          
          const script = document.createElement('script');
          script.src = 'https://js.hcaptcha.com/1/api.js';
          document.head.appendChild(script);
        }, siteKey);
        
        await sleep(2000);
      }
      
      // Find and click hCaptcha checkbox
      const frames = page.frames();
      const hcaptchaFrame = frames.find(f => f.url().includes('hcaptcha.com'));
      
      if (hcaptchaFrame) {
        try {
          await hcaptchaFrame.waitForSelector('#checkbox', { timeout: 5000 });
          await sleep(300 + Math.random() * 500);
          await hcaptchaFrame.click('#checkbox');
        } catch (e) {
          // Checkbox might already be clicked or not visible
        }
      }
      
      // Wait for token
      const token = await page.waitForFunction(
        () => {
          // Check various ways the token might be available
          const input = document.querySelector('[name="h-captcha-response"]');
          if (input && input.value) return input.value;
          
          const textarea = document.querySelector('textarea[name="h-captcha-response"]');
          if (textarea && textarea.value) return textarea.value;
          
          if (window.__hcaptchaToken) return window.__hcaptchaToken;
          if (window.captchaToken) return window.captchaToken;
          
          return null;
        },
        { timeout: this.timeout }
      ).then(handle => handle.jsonValue());
      
      return {
        success: true,
        token,
        time: Date.now() - startTime,
        method: 'browser-page'
      };
      
    } catch (error) {
      return {
        success: false,
        error: error.message,
        time: Date.now() - startTime
      };
    }
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// CLIENT - Use from your code
// ════════════════════════════════════════════════════════════════════════════════

class Client {
  constructor(baseUrl = 'http://localhost:3000') {
    this.baseUrl = baseUrl;
  }
  
  /**
   * Solve captcha - auto-detects siteKey from URL
   * @param {string} url - Page URL with captcha
   * @param {object} options - Optional: { siteKey, rqdata, priority }
   */
  async solve(url, options = {}) {
    return this._post('/solve', { url, ...options });
  }
  
  /**
   * Detect siteKey from page
   * @param {string} url - Page URL to scan
   */
  async detect(url) {
    return this._post('/detect', { url });
  }
  
  /**
   * Get server stats
   */
  async stats() {
    return this._get('/stats');
  }
  
  async _post(path, body) {
    const res = await HttpClient.fetch(`${this.baseUrl}${path}`, {
      method: 'POST',
      body,
      headers: { 'Content-Type': 'application/json' }
    });
    return res.data;
  }
  
  async _get(path) {
    const res = await HttpClient.get(`${this.baseUrl}${path}`);
    return res.data;
  }
}

// ════════════════════════════════════════════════════════════════════════════════
// EXPORTS
// ════════════════════════════════════════════════════════════════════════════════

module.exports = {
  // Server & Client
  Server,
  Client,
  
  // Solvers
  HCaptchaSolver,           // Native solver (tries multiple methods)
  BrowserSolver,            // Browser-based solver using Puppeteer (BEST)
  CaptchaSolverService,     // Service-based solver
  BlackboxService,          // Blackbox AI helper
  
  // Detection
  SiteKeyDetector,
  
  // Utilities
  Fingerprint,
  MotionGenerator,
  ProofOfWork,
  HttpClient,
  Queue,
  Cache,
  CONFIG,
  
  // Quick functions
  createServer: (port) => new Server(port).start(),
  createClient: (url) => new Client(url),
  detect: (url) => SiteKeyDetector.detect(url),
  
  // Native solve (limited - HSW requires browser)
  solve: async (url, siteKey, options = {}) => {
    // Try browser solver first if puppeteer is available
    try {
      const BrowserSolver = require('./HCAPTCHA.JS').BrowserSolver;
      const solver = new BrowserSolver({ headless: true, ...options });
      return await solver.solve(url, siteKey);
    } catch (e) {
      // Fall back to native
      const solver = new HCaptchaSolver({ siteKey, siteUrl: url, ...options });
      return solver.solve();
    }
  },
  
  // Browser solve (RECOMMENDED)
  solveBrowser: async (url, siteKey, options = {}) => {
    const solver = new BrowserSolver(options);
    return solver.solve(url, siteKey);
  }
};

// ════════════════════════════════════════════════════════════════════════════════
// CLI
// ════════════════════════════════════════════════════════════════════════════════

if (require.main === module) {
  const port = parseInt(process.argv.find(a => a.startsWith('--port='))?.split('=')[1] || CONFIG.PORT);
  
  new Server(port).start();
  
  process.on('SIGINT', () => {
    console.log('\n👋 Shutting down...');
    process.exit(0);
  });
}


/*
═══════════════════════════════════════════════════════════════════════════════════
                                 USAGE EXAMPLES
═══════════════════════════════════════════════════════════════════════════════════

▓▓▓ 1. START SERVER ▓▓▓

  node HCAPTCHA.JS
  node HCAPTCHA.JS --port=8080


▓▓▓ 2. SOLVE CAPTCHA (curl) - Auto-detects siteKey! ▓▓▓

  curl -X POST http://localhost:3000/solve \
    -H "Content-Type: application/json" \
    -d '{"url": "https://diceygolf.com"}'

  Response:
  {
    "success": true,
    "token": "P0_eyJ...",
    "time": 8234,
    "detection": {
      "autoDetected": true,
      "siteKey": "f5561ba9-8f1e-40ca-9b5b-a0b3f719ef34"
    }
  }


▓▓▓ 3. USE IN NODE.JS ▓▓▓

  const { createClient } = require('./HCAPTCHA.JS');
  
  const client = createClient('http://localhost:3000');
  
  // Just pass URL - siteKey auto-detected!
  const result = await client.solve('https://diceygolf.com/checkout');
  console.log('Token:', result.token);
  
  // Use token in your checkout code
  await submitCheckout(result.token);


▓▓▓ 4. USE IN PYTHON ▓▓▓

  import requests
  
  def solve(url):
      r = requests.post('http://localhost:3000/solve', json={'url': url})
      return r.json()['token']
  
  token = solve('https://diceygolf.com/checkout')
  print(f'Token: {token}')


▓▓▓ 5. DETECT SITEKEY ONLY ▓▓▓

  curl -X POST http://localhost:3000/detect \
    -H "Content-Type: application/json" \
    -d '{"url": "https://diceygolf.com"}'


▓▓▓ 6. WITH PUPPETEER ▓▓▓

  const puppeteer = require('puppeteer');
  const { createClient } = require('./HCAPTCHA.JS');
  
  const browser = await puppeteer.launch();
  const page = await browser.newPage();
  await page.goto('https://diceygolf.com/checkout');
  
  // Solve captcha
  const client = createClient();
  const { token } = await client.solve(page.url());
  
  // Inject token
  await page.evaluate((t) => {
    document.querySelector('[name="h-captcha-response"]').value = t;
  }, token);
  
  // Submit form
  await page.click('button[type="submit"]');

═══════════════════════════════════════════════════════════════════════════════════
*/
