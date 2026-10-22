import re

# Approximate conversion rates to USD (as of recent rates)
CONVERSION_RATES = {
    '$':   1.0,       # USD
    '£':   1.27,      # GBP to USD
    '€':   1.08,      # EUR to USD
    'A$':  0.63,      # AUD to USD
    'C$':  0.73,      # CAD to USD
    'NZ$': 0.60,      # NZD to USD
    'S$':  0.75,      # SGD to USD
}

def parse_price(price_str):
    """Parse price string like 18.05£, 1.00$, 36.40€, 190.00A$"""
    price_str = price_str.strip()
    
    # Try multi-char currencies first (A$, C$, NZ$, S$)
    for symbol in ['NZ$', 'A$', 'C$', 'S$']:
        if symbol in price_str:
            amount = float(price_str.replace(symbol, '').strip())
            return amount, symbol
    
    # Single char currencies ($, £, €)
    for symbol in ['$', '£', '€']:
        if symbol in price_str:
            amount = float(price_str.replace(symbol, '').strip())
            return amount, symbol
    
    return None, None

def to_usd(amount, symbol):
    rate = CONVERSION_RATES.get(symbol, 1.0)
    return amount * rate

input_file  = r'administrator\Rukia\mass_gates\sites.txt'
output_file = r'administrator\Rukia\mass_gates\sites.txt'
backup_file = r'administrator\Rukia\mass_gates\sites_backup.txt'

# Read original
with open(input_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Backup
with open(backup_file, 'w', encoding='utf-8') as f:
    f.writelines(lines)

kept = []
removed = 0
kept_count = 0

for line in lines:
    stripped = line.strip()
    
    # Skip empty lines and header lines (---, ✅, 💸, etc.)
    if not stripped or stripped.startswith('---') or stripped.startswith('<tg-emoji emoji-id="5310296284874159738">✅</tg-emoji>') or stripped.startswith('<tg-emoji emoji-id="5922478782689579227">💸</tg-emoji>') or stripped.startswith('<tg-emoji emoji-id="5397890704062038337">❌</tg-emoji>') or stripped.startswith('⚠') or stripped.startswith('🔁') or stripped.startswith('#'):
        continue  # Skip headers/separators
    
    # Check if it's a URL line
    if '|' not in stripped:
        continue
    
    parts = stripped.split('|')
    if len(parts) < 3:
        continue
    
    price_str = parts[2].strip()
    amount, symbol = parse_price(price_str)
    
    if amount is None:
        # Can't parse price, skip
        removed += 1
        continue
    
    usd = to_usd(amount, symbol)
    
    if usd < 9.0:
        kept.append(stripped + '\n')
        kept_count += 1
    else:
        removed += 1

print(f"Kept: {kept_count} URLs (under $9)")
print(f"Removed: {removed} URLs")

# Write filtered output
with open(output_file, 'w', encoding='utf-8') as f:
    f.writelines(kept)

print(f"\nDone! sites.txt updated with {kept_count} entries.")
print(f"Backup saved to: sites_backup.txt")
