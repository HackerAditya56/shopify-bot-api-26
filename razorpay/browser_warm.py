"""
browser_warm.py — KAKU DEV minimal ThreatMetrix warm-up for Razorpay.

The browser check that curl can't fake is ThreatMetrix (h.online-metrix.net,
org_id=k8vif92e). TM's tags.js runs its own fingerprint engine (canvas/webgl/
audio/fonts) and beacons it to online-metrix.net with session_id=razorpay<checkout_id>.
Razorpay's server then queries TM by that session_id at the create/ajax step.

KEY FACT (proven live): TM fires on a BARE page with just tags.js injected — no
checkout form, no card, no button-clicking. So we can warm TM in ~8 seconds with
ZERO form interaction. Stripe Radar is already handled in curl (real rse_ session);
this module closes the TM gap.

Flow:
  1. curl creates the order -> checkout_id
  2. browser (stealth, same proxy) loads razorpay.com + injects TM tags.js with
     session_id=razorpay<checkout_id> -> TM beacons its fingerprint
  3. curl submits the card (create/ajax) -> server sees TM has a live profile
"""
import asyncio, json, time, random, re

PROFILES = [
    {"name":"win-chrome146","ua":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36","platform":"Win32","ua_platform":"Windows","brands":"146","full":"146.0.0.0","screen":(1920,1080),"dpr":1,"mem":8,"hc":8,"touch":0,"lang":"en-IN"},
    {"name":"win-chrome124","ua":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36","platform":"Win32","ua_platform":"Windows","brands":"124","full":"124.0.0.0","screen":(1366,768),"dpr":1,"mem":8,"hc":4,"touch":0,"lang":"en-US"},
    {"name":"mac-chrome142","ua":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36","platform":"MacIntel","ua_platform":"macOS","brands":"142","full":"142.0.0.0","screen":(1728,1117),"dpr":2,"mem":8,"hc":10,"touch":0,"lang":"en-GB"},
    {"name":"linux-chrome136","ua":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36","platform":"Linux x86_64","ua_platform":"Linux","brands":"136","full":"136.0.0.0","screen":(1920,1080),"dpr":1,"mem":16,"hc":12,"touch":0,"lang":"en-IN"},
]
_USED = set()

def _pick_profile():
    avail = [p for p in PROFILES if p["name"] not in _USED]
    if not avail:
        avail = list(PROFILES); _USED.clear()
    p = random.choice(avail); _USED.add(p["name"]); return p

def _stealth_init(p):
    ua=p["ua"]; plat=p["platform"]; uaplat=p["ua_platform"]; brand=p["brands"]; full=p["full"]
    return f"""
(() => {{
  const d = Object.defineProperty;
  d(Navigator.prototype,'platform',{{get:()=>'{plat}'}});
  d(Navigator.prototype,'webdriver',{{get:()=>undefined}});
  d(Navigator.prototype,'deviceMemory',{{get:()=>{p['mem']}}});
  d(Navigator.prototype,'hardwareConcurrency',{{get:()=>{p['hc']}}});
  d(Navigator.prototype,'maxTouchPoints',{{get:()=>{p['touch']}}});
  d(Navigator.prototype,'languages',{{get:()=>['{p['lang']}','en']}});
  d(Navigator.prototype,'language',{{get:()=>'{p['lang']}'}});
  d(Navigator.prototype,'appVersion',{{get:()=>'{ua}'}});
  d(Navigator.prototype,'userAgentData',{{get:()=>({{
    brands:[{{brand:'Google Chrome',version:'{brand}'}},{{brand:'Chromium',version:'{brand}'}},{{brand:'Not_A Brand',version:'24'}}],
    mobile:false,platform:'{uaplat}',
    getHighEntropyValues:async()=>({{architecture:'x86',bitness:'64',model:'',platformVersion:'10.0.0',uaFullVersion:'{full}'}})}})}});
  d(Navigator.prototype,'connection',{{get:()=>({{effectiveType:'4g',rtt:50,downlink:10,saveData:false}})}});
  const rp=[{{name:'Chrome PDF Plugin',filename:'internal-pdf-viewer',description:'Portable Document Format'}},
            {{name:'Chrome PDF Viewer',filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai',description:''}},
            {{name:'Native Client',filename:'internal-nacl-plugin',description:''}}];
  d(Navigator.prototype,'plugins',{{get:()=>{{const a=Object.create(PluginArray.prototype);const pl=rp.map(x=>({{name:x.name,filename:x.filename,description:x.description,length:1,item:i=>null,namedItem:n=>null}}));Object.defineProperty(a,'length',{{value:pl.length}});pl.forEach((x,i)=>Object.defineProperty(a,i,{{value:x,enumerable:true}}));return a;}}}});
  window.chrome=window.chrome||{{runtime:{{}},loadTimes:()=>({{}}),csi:()=>({{}}),app:{{}}}};
}})();"""

def _parse_proxy(proxy):
    if not proxy: return {}
    p = proxy.strip()
    m = re.match(r'^(?:https?://)?(?:([^:@/]+):([^@/]+)@)?([^:/@]+):(\d+)(?::([^:]+):([^\s]+))?$', p)
    if m:
        u,pw,h,port,u2,p2 = m.groups()
        if u is None and u2: u,pw = u2,p2
        return {"server":f"{h}:{port}","username":u or "","password":pw or ""}
    parts = p.split()
    if len(parts)>=4: return {"server":f"{parts[2]}:{parts[3]}","username":parts[0],"password":parts[1]}
    return {"server":p}

async def warm_threatmetrix(checkout_id: str, proxy: str, wait_s: float = 9.0) -> dict:
    """Standalone TM warm. Returns {fired, cis3sid, nonce, profile, beacons}."""
    from playwright.async_api import async_playwright
    profile = _pick_profile()
    px = _parse_proxy(proxy)
    session_id = f"razorpay{checkout_id}"
    out = {"fired": False, "cis3sid": "", "nonce": "", "profile": profile["name"], "beacons": 0}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            "--disable-blink-features=AutomationControlled","--no-sandbox","--disable-webrtc","--use-gl=swiftshader"])
        kw = dict(viewport={"width":profile["screen"][0],"height":profile["screen"][1]},
                  user_agent=profile["ua"], locale=profile["lang"], device_scale_factor=profile["dpr"])
        if px.get("server"):
            kw["proxy"] = {"server":"http://"+px["server"],"username":px.get("username",""),"password":px.get("password","")}
        ctx = await browser.new_context(**kw)
        page = await ctx.new_page()
        await page.add_init_script(_stealth_init(profile))

        # load the real razorpay origin so TM's referrer/origin look right,
        # then inject tags.js with the correct session_id.
        try:
            await page.goto("https://api.razorpay.com/", wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass
        await page.evaluate(f"""
        (() => {{
          const s = document.createElement('script');
          s.src = 'https://h.online-metrix.net/fp/tags.js?org_id=k8vif92e&session_id={session_id}';
          s.async = true;
          document.head.appendChild(s);
        }})()""")

        def on_req(req):
            u = req.url
            if "online-metrix" in u:
                out["beacons"] += 1
                out["fired"] = True
                if "check.js" in u:
                    m = re.search(r"CIS3SID=([A-F0-9]+)", u)
                    if m: out["cis3sid"] = m.group(1)
                m2 = re.search(r"nonce=([a-f0-9]+)", u)
                if m2 and not out["nonce"]: out["nonce"] = m2.group(1)
        page.on("request", on_req)

        for _ in range(int(wait_s)):
            await page.wait_for_timeout(1000)
            if out["fired"] and out["beacons"] >= 3:
                break
        await browser.close()
    return out


if __name__ == "__main__":
    async def main():
        proxy = None
        for l in open("/home/zirconium/Desktop/shopify/proxy.txt").read().splitlines():
            if "pvdata" in l: proxy = l; break
        r = await warm_threatmetrix("TESTCHECKOUT123", proxy)
        print(json.dumps(r, indent=2, default=str))
    asyncio.run(main())
