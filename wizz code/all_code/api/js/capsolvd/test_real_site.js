import fetch from 'node-fetch';
import { CookieJar } from 'tough-cookie';
import fetchCookie from 'fetch-cookie';

const jar = new CookieJar();
const fetchWithCookies = fetchCookie(fetch, jar);

// Try known working Shopify stores
const testSites = ['gymshark.com', 'allbirds.com', 'fashionnova.com', 'kylieco smetics.com'];

for (const site of testSites) {
  try {
    console.log('\n=== TESTING:', site, '===');
    const productsRes = await fetch(`https://${site}/products.json?limit=1`);
    const products = await productsRes.json();
    
    if (!products.products || products.products.length === 0) {
      console.log('No products found');
      continue;
    }
    
    const variantId = products.products[0].variants[0].id;
    console.log('Product:', products.products[0].title);
    console.log('Variant ID:', variantId);
    
    const res = await fetchWithCookies(`https://${site}/cart/${variantId}:1`, {
      redirect: 'follow',
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }
    });
    
    const html = await res.text();
    console.log('Final URL:', res.url);
    console.log('Status:', res.status);
    console.log('HTML length:', html.length);
    
    // Check for session token with multiple patterns
    const patterns = [
      { name: 'Meta tag', regex: /serialized-session-token['"\\s]+content=['"]&quot;([^&]+)&quot;/i },
      { name: 'JSON sessionToken', regex: /"sessionToken"\s*:\s*"([^"]+)"/i },
      { name: 'Any sessionToken', regex: /sessionToken[&:'"]+([\\w\\-\\.]+)/i },
      { name: 'Shopify.__st', regex: /Shopify\\.__st\\s*=\\s*\\{[^}]*sessionToken[&:'"]+([\\w\\-\\.]+)/i },
      { name: 'window.Shopify', regex: /window\\.Shopify[^}]*sessionToken[&:'"]+([\\w\\-\\.]+)/i }
    ];
    
    let found = false;
    for (const pattern of patterns) {
      const match = html.match(pattern.regex);
      if (match && match[1]) {
        console.log(`✓ ${pattern.name} FOUND: ${match[1].substring(0, 50)}...`);
        found = true;
        break;
      }
    }
    
    if (!found) {
      // Check if it contains sessionToken at all
      if (html.includes('sessionToken')) {
        console.log('✓ HTML contains "sessionToken" but patterns did not match');
        const lines = html.split('\n').filter(l => l.includes('sessionToken'));
        console.log(`Found ${lines.length} lines with sessionToken`);
        if (lines.length > 0) {
          console.log('Sample line:', lines[0].trim().substring(0, 300));
        }
      } else {
        console.log('✗ No sessionToken found in HTML at all');
      }
    }
    
    // Success - stop here
    if (found) break;
    
  } catch (e) {
    console.log('Error:', e.message);
  }
}
