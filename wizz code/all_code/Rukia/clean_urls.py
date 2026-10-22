path = r'administator\Rukia\mass_gates\sites.txt'

with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

urls = []
for line in lines:
    raw = line.rstrip('\n').rstrip('\r').strip()
    if not raw:
        continue
    url = raw.split('|')[0].strip()
    # Keep only lines that look like URLs (start with http)
    if url.startswith('http'):
        urls.append(url)

with open(path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(urls))

print(f'Kept {len(urls)} URLs')
