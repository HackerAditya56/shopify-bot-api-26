"""
proxy_classify.py — classify proxies: residential vs datacenter, rotating vs static.

Exit IP via ipify, classification via ip-api.com/batch (100 IPs per request,
no per-IP rate-limit churn), rotating detection via two exit-IP samples.
"""
import asyncio
import aiohttp

IPIFY = "http://api.ipify.org?format=json"
# ip-api.com batch: free, 100 IPs/request, 15 req/min — the highest-throughput free option
IPAPI_BATCH = "http://ip-api.com/batch?fields=status,query,proxy,hosting,mobile,isp,as"

_RESIDENTIAL_HINTS = ("rotating", "residential", "isp", "premium", "real")
_DATACENTER_HINTS = ("datacenter", "dc", "server", "vps", "hosting")


def _to_url(p):
    return p if p.startswith("http") else "http://" + p


def _host_hint(p):
    h = (p or "").lower()
    for hint in _RESIDENTIAL_HINTS:
        if hint in h:
            return "residential"
    for hint in _DATACENTER_HINTS:
        if hint in h:
            return "datacenter"
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

        # 2) batch classify via ip-api.com (100 per request)
        type_map = {}
        ips = list({ip for _, ip in live})
        for i in range(0, len(ips), 100):
            chunk = ips[i:i + 100]
            try:
                async with session.post(IPAPI_BATCH, json=chunk,
                                        timeout=aiohttp.ClientTimeout(total=15)) as r:
                    data = await r.json()
                for item in data:
                    q = item.get("query")
                    if not q:
                        continue
                    hosting = item.get("hosting") or item.get("proxy")
                    t = "datacenter" if hosting else "residential"
                    type_map[q] = (t, item.get("isp"), item.get("as"))
            except Exception:
                pass

        # 3) rotating detection: second exit-IP sample
        async def _rot_one(p, first_ip):
            async with sem:
                ip2 = await _exit_ip(session, p)
                return p, (ip2 is not None and ip2 != first_ip)
        rots = await asyncio.gather(*[_rot_one(p, ip) for p, ip in live])
        rot_map = dict(rots)

        for p, ip in live:
            t, isp, asn = type_map.get(ip, ("unknown", None, None))
            host_hint = _host_hint(p)
            if t == "unknown" and host_hint:
                t = host_hint
            out[p] = {"ip": ip, "type": t, "rotating": rot_map.get(p, False),
                      "isp": isp, "as": asn}

    return out


def is_residential(info):
    return info.get("type") in ("residential",) and info.get("ip")


def summarize(info):
    """Short human label for a classified proxy."""
    if info["type"] == "dead":
        return "DEAD"
    t = info["type"].upper()
    r = "ROTATING" if info["rotating"] else "static"
    return f"{t} · {r} · {info.get('isp') or info.get('as') or info['ip']}"
