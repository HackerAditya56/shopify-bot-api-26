import puppeteer from 'puppeteer-extra';
import StealthPlugin from 'puppeteer-extra-plugin-stealth';
import { executablePath } from 'puppeteer';

puppeteer.use(StealthPlugin());

class BrowserCaptchaSolver {
    constructor(options = {}) {
        this.domain = options.domain || 'checkout.shopify.com';
        this.headless = options.headless !== false;
        this.timeout = options.timeout || 60000;
        this.variantId = options.variantId || null;
        this.browser = null;
        this.page = null;
    }

    async fastDelay(ms = 50) { await new Promise(r => setTimeout(r, ms)); }

    async initBrowser() {
        const args = [
            '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
            '--disable-gpu', '--window-size=1366,768', '--disable-blink-features=AutomationControlled'
        ];

        this.browser = await puppeteer.launch({
            headless: 'new',
            executablePath: executablePath(),
            args,
            defaultViewport: { width: 1366, height: 768 }
        });

        this.page = await this.browser.newPage();
        
        await this.page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
        await this.page.evaluateOnNewDocument(() => {
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        });
    }

    async run() {
        const startTime = Date.now();
        
        try {
            await this.initBrowser();
            
            const targetUrl = this.variantId 
                ? `https://${this.domain}/cart/${this.variantId}:1` 
                : `https://${this.domain}`;

            console.log(`[Browser] Navigating to ${targetUrl}`);
            await this.page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });

            console.log('[Browser] Looking for hCaptcha checkbox...');
            await this.fastDelay(3000);

            let checkboxClicked = false;
            for (let i = 0; i < 15; i++) {
                const frames = this.page.frames();
                for (const frame of frames) {
                    if (frame.url().includes('hcaptcha.com') && frame.url().includes('checkbox')) {
                        try {
                            await frame.waitForSelector('#checkbox', { timeout: 2000 });
                            await frame.click('#checkbox');
                            checkboxClicked = true;
                            console.log('[Browser] Clicked checkbox!');
                            break;
                        } catch (e) {}
                    }
                }
                if (checkboxClicked) break;
                await this.fastDelay(1000);
            }

            if (!checkboxClicked) {
                throw new Error('Could not find hCaptcha checkbox on the page.');
            }

            console.log('[Browser] Waiting for token...');
            const token = await this.page.waitForFunction(
                () => {
                    const textarea = document.querySelector('textarea[name="h-captcha-response"]');
                    if (textarea && textarea.value && textarea.value.length > 50) return textarea.value;
                    
                    const hidden = document.querySelector('input[name="h-captcha-response"]');
                    if (hidden && hidden.value && hidden.value.length > 50) return hidden.value;
                    
                    return null;
                },
                { timeout: this.timeout, polling: 500 }
            ).then(h => h.jsonValue());

            await this.browser.close();
            
            console.log('[Browser] Got Token!');
            return {
                success: true,
                token: token,
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
}

export default BrowserCaptchaSolver;