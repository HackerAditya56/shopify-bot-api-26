"""
proxy_classify.py — classify proxies: residential vs datacenter, rotating vs static.

Exit IP via ipify.
Classification via ipwho.is (genuinely free, no documented rate limit, HTTPS).
Datacenter signal: connection.domain present (hosting providers advertise a PTR/domain)
or org/isp matching a hosting keyword. Residential: consumer ISP, empty domain.
Rotating detection via two exit-IP samples.
"""
import asyncio
import aiohttp

IPIFY = "http://api.ipify.org?format=json"
IPWHOIS = "https://ipwho.is/{ip}"

_UA = {"User-Agent": "Mozilla/5.0 (proxy-classifier)"}

# hosting / datacenter keywords in org|isp|domain
_HOSTING_KW = (
    "amazon", "aws", "google", "gcp", "azure", "microsoft", "digitalocean",
    "linode", "vultr", "ovh", "hetzner", "contabo", "hostinger", "godaddy",
    "cloudflare", "fastly", "akamai", "equinix", "leaseweb", "colocrossing",
    "psychz", "interserver", "24shells", "dana", "orion", "b2 net",
    "thunderbox", "host", "server", "datacenter", "dc ", "vps", "colo",
    "dedicated", "corporaci", "internet services", "network limited",
    "data center", "cloud", "digital", "fiber", "telemedia", "telecom",
)

_RESIDENTIAL_HINTS = ("rotating", "residential", "isp", "premium", "real")


def _to_url(p):
    return p if p.startswith("http") else "http://" + p


def _host_hint(p):
    h = (p or "").lower()
    for hint in _RESIDENTIAL_HINTS:
        if hint in h:
            return "residential"
    return None


async def _exit_ip(session, proxy):
    try:
        async with session.get(IPIFY, proxy=_to_url(proxy), ssl=False,
                               timeout=aiohttp.ClientTimeout(total=10, connect=5)) as r:
            if r.status == 200:
                d = await r.json()
                ip = (d.get("ip") or "").strip()
                return ip or None
    except Exception:
        pass
    return None


async def _lookup_ipwhois(session, sem, ip):
    async with sem:
        try:
            async with session.get(IPWHOIS.format(ip=ip), headers=_UA,
                                   timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    return ip, await r.json()
        except Exception:
            pass
    return ip, None


def _classify(data):
    """residential | datacenter | unknown from an ipwho.is payload."""
    if not data or not data.get("success", False):
        return "unknown", None, None
    conn = data.get("connection") or {}
    org = (conn.get("org") or "").lower()
    isp = (conn.get("isp") or "").lower()
    domain = (conn.get("domain") or "").lower()
    text = f"{org} {isp} {domain}"
    if domain or any(k in text for k in _HOSTING_KW):
        kind = "datacenter"
    else:
        kind = "residential"
    label = conn.get("org") or conn.get("isp") or f"AS{conn.get('asn', '')}"
    return kind, label, data.get("country_code")


async def classify_proxies(proxies, concurrency=50):
    """Classify proxies. Returns dict: proxy -> {ip, type, rotating, isp, as}.

    type: 'residential' | 'datacenter' | 'unknown' | 'dead'
    rotating: bool (exit IP changed across two samples)
    """
    sem = asyncio.Semaphore(concurrency)
    out = {p: {"ip": None, "type": "dead", "rotating": False, "isp": None, "as": None}
           for p in proxies}

    async with aiohttp.ClientSession() as session:
        # 1) exit IP per proxy
        async def _ip_one(p):
            async with sem:
                return p, await _exit_ip(session, p)
        pairs = await asyncio.gather(*[_ip_one(p) for p in proxies])
        live = [(p, ip) for p, ip in pairs if ip]

        # 2) classify each exit IP via ipwho.is (concurrent, no rate-limit churn)
        uniq_ips = list({ip for _, ip in live})
        lookups = await asyncio.gather(*[_lookup_ipwhois(session, sem, ip) for ip in uniq_ips])
        info_map = {ip: data for ip, data in lookups}

        # 3) rotating detection: second exit-IP sample
        async def _rot_one(p, first_ip):
            async with sem:
                ip2 = await _exit_ip(session, p)
                return p, (ip2 is not None and ip2 != first_ip)
        rots = await asyncio.gather(*[_rot_one(p, ip) for p, ip in live])
        rot_map = dict(rots)

        for p, ip in live:
            data = info_map.get(ip)
            kind, label, country = _classify(data)
            if kind == "unknown":
                hint = _host_hint(p)
                if hint:
                    kind = hint
            out[p] = {"ip": ip, "type": kind, "rotating": rot_map.get(p, False),
                      "isp": label, "as": country}

    return out


def is_residential(info):
    return info.get("type") == "residential" and info.get("ip")


def summarize(info):
    """Short human label for a classified proxy."""
    if info["type"] == "dead":
        return "DEAD"
    t = info["type"].upper()
    r = "ROTATING" if info["rotating"] else "static"
    return f"{t} · {r} · {info.get('isp') or info['ip']}"
