const https = require('https');
const querystring = require('querystring');

const cookies = {
    'cookieyes-consent': 'consentid:Vzd3aFdxcUJKUzlrOTlXeEtZU1YwZE9ia0Z2TFRhNkM,consent:yes,action:yes,necessary:yes,functional:yes,analytics:yes,performance:yes,advertisement:yes,other:yes',
    'wp_consent_preferences': 'allow',
    'wp_consent_statistics': 'allow',
    'wp_consent_statistics-anonymous': 'allow',
    'wp_consent_functional': 'allow',
    'wp_consent_marketing': 'allow',
    '_ga': 'GA1.1.920092262.1775823431',
    '_ga_08WQY34W4S': 'GS2.1.s1775823431$o1$g0$t1775823431$j60$l0$h0'
};

const commonHeaders = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8',
    'cache-control': 'no-cache',
    'pragma': 'no-cache',
    'priority': 'u=0, i',
    'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Mobile Safari/537.36',
    'cookie': Object.entries(cookies).map(([k, v]) => `${k}=${v}`).join('; ')
};

// Form data for ladnehistorie.pl
const formData = querystring.stringify({
    'flexible_donation[first_name]': 'Rocky',
    'flexible_donation[last_name]': 'og',
    'flexible_donation[email]': 'malcviusstorm@gmail.com',
    'flexible_donation[amount]': '1',
    'flexible_donation[comment]': '',
    'flexible_donation[payment_method]': 'payu',
    'flexible_donation[terms]': ['no', 'yes'],
    'flexible_donation[form_id]': '5827',
    'flexible_donation[send_donation]': 'Send donation',
    'trp-form-language': 'en'
});

const postHeaders = {
    ...commonHeaders,
    'content-type': 'application/x-www-form-urlencoded',
    'origin': 'https://ladnehistorie.pl',
    'referer': 'https://ladnehistorie.pl/en/support-us/'
};

const postOptions = {
    hostname: 'ladnehistorie.pl',
    path: '/en/support-us/',
    method: 'POST',
    headers: {
        ...postHeaders,
        'content-length': Buffer.byteLength(formData)
    }
};

const postReq = https.request(postOptions, (postRes) => {
    let postBody = '';
    postRes.on('data', (chunk) => postBody += chunk);
    postRes.on('end', () => {
        const location = postRes.headers.location;
        if (location) {
            console.log(location);
        } else {
            // If no redirect, output status and part of response for debugging
            console.log('Status:', postRes.statusCode);
            console.log('Response (first 500 chars):', postBody.substring(0, 500));
        }
    });
});

postReq.on('error', (err) => {
    console.error('Error:', err.message);
    process.exit(1);
});

postReq.write(formData);
postReq.end();
