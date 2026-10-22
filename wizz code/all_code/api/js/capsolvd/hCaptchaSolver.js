import crypto from 'crypto';
import https from 'https';
import http from 'http';
import { URL, URLSearchParams } from 'url';
import EventEmitter from 'events';

const CONFIG = {
  VERSION: '5.0.0',
  TIMEOUT: 30000,
  HCAPTCHA: {
    SITE_CONFIG: 'https://hcaptcha.com/checksiteconfig'
  }
};

const timestamp = () => Date.now();

class HttpClient {
  static async fetch(url, options = {}) {
    return new Promise((resolve, reject) => {
      const urlObj = new URL(url);
      const isHttps = urlObj.protocol === 'https:';
      const client = isHttps ? https : http;
      const reqOptions = {
        hostname: urlObj.hostname,
        port: urlObj.port || (isHttps ? 443 : 80),
        path: urlObj.pathname + urlObj.search,
        method: options.method || 'GET',
        headers: options.headers || {},
        timeout: CONFIG.TIMEOUT
      };
      const req = client.request(reqOptions, res => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            resolve({ status: res.statusCode, data: JSON.parse(data) });
          } catch {
            resolve({ status: res.statusCode, data });
          }
        });
      });
      req.on('error', reject);
      req.end();
    });
  }
  static get(url, options) { return this.fetch(url, options); }
}

class HCaptchaSolver extends EventEmitter {
  constructor(options = {}) {
    super();
    this.siteKey = options.sitekey || options.siteKey;
    this.siteUrl = options.url || options.siteUrl || `https://${options.host || 'checkout.shopify.com'}`;
    this.host = options.host || 'checkout.shopify.com';
  }

  async getSiteConfig() {
    const params = new URLSearchParams({ v: 'b1129dc', host: this.host, sitekey: this.siteKey });
    const res = await HttpClient.get(`${CONFIG.HCAPTCHA.SITE_CONFIG}?${params}`);
    return res.data;
  }

  async solve() {
    const start = timestamp();
    this.emit('status', 'Starting REAL Captcha solve via Browser...');
    
    try {
        const { default: BrowserCaptchaSolver } = await import('./browserCaptchaSolver.js');
        
        const browserSolver = new BrowserCaptchaSolver({
            domain: this.host,
            headless: true
        });

        const result = await browserSolver.run();
        
        if (result.success && result.token) {
            return {
                success: true,
                token: result.token,
                time: timestamp() - start,
                method: 'puppeteer-browser'
            };
        } else {
            return {
                success: false,
                error: result.error || 'Browser solver failed to find token',
                time: timestamp() - start
            };
        }
    } catch (e) {
        return {
            success: false,
            error: e.message,
            time: timestamp() - start
        };
    }
  }
}

export default HCaptchaSolver;
export { HCaptchaSolver, HttpClient };