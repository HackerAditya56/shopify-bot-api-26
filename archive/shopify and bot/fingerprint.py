"""
Fingerprint Generation for Stealth Browser
Generates realistic browser fingerprints for anti-detection
"""

import random
import hashlib
import json
from typing import Dict, Optional


# Common screen resolutions (weighted towards popular ones)
RESOLUTIONS = [
    {"w": 1920, "h": 1080, "weight": 35},
    {"w": 1366, "h": 768, "weight": 20},
    {"w": 1536, "h": 864, "weight": 15},
    {"w": 1440, "h": 900, "weight": 10},
    {"w": 2560, "h": 1440, "weight": 8},
    {"w": 1680, "h": 1050, "weight": 5},
    {"w": 1280, "h": 720, "weight": 4},
    {"w": 1600, "h": 900, "weight": 3},
]

# WebGL renderers (realistic GPU info)
WEBGL_RENDERERS = [
    {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Intel(R) Iris Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Intel(R) HD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD, AMD Radeon RX 580 Series Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 2060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
]

# Chrome versions (recent stable)
CHROME_VERSIONS = [
    "120.0.6099.109",
    "120.0.6099.130",
    "121.0.6167.85",
    "121.0.6167.139",
    "122.0.6261.57",
    "122.0.6261.94",
    "123.0.6312.58",
    "123.0.6312.86",
]

# Timezones
TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Phoenix",
    "America/Anchorage",
    "America/Toronto",
    "Europe/London",
    "Europe/Berlin",
    "Australia/Sydney",
]


def _weighted_choice(items):
    """Choose from weighted items"""
    total = sum(item.get("weight", 1) for item in items)
    r = random.uniform(0, total)
    cumulative = 0
    for item in items:
        cumulative += item.get("weight", 1)
        if r <= cumulative:
            return item
    return items[-1]


def generate_fingerprint(
    timezone: str = None,
    language: str = "en-US",
    screen_width: int = None,
    screen_height: int = None,
) -> Dict:
    """
    Generate a randomized browser fingerprint.
    
    Args:
        timezone: IANA timezone string (auto-selected if None)
        language: Browser language
        screen_width: Custom screen width (random if None)
        screen_height: Custom screen height (random if None)
    
    Returns:
        dict: Complete fingerprint data
    """
    # Resolution
    if screen_width and screen_height:
        res = {"w": screen_width, "h": screen_height}
    else:
        res = _weighted_choice(RESOLUTIONS)
    
    # Timezone
    tz = timezone or random.choice(TIMEZONES)
    
    # Chrome version
    chrome_version = random.choice(CHROME_VERSIONS)
    
    # WebGL
    webgl = random.choice(WEBGL_RENDERERS)
    
    # Languages
    lang_base = language.split("-")[0] if "-" in language else language
    languages = [language, lang_base]
    
    # Canvas noise (subtle)
    canvas_noise = {
        "r": random.randint(-3, 3),
        "g": random.randint(-3, 3),
        "b": random.randint(-3, 3),
        "a": random.randint(-2, 2),
    }
    
    # User agent
    user_agent = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} Safari/537.36"
    
    return {
        "userAgent": user_agent,
        "chromeVersion": chrome_version,
        "platform": "Win32",
        "screen": {"width": res["w"], "height": res["h"]},
        "languages": languages,
        "language": language,
        "hardwareConcurrency": random.choice([4, 8, 12, 16]),
        "deviceMemory": random.choice([4, 8, 16]),
        "canvasNoise": canvas_noise,
        "audioNoise": random.random() * 0.000001,
        "noiseSeed": random.randint(0, 9999999),
        "timezone": tz,
        "webgl": {
            "vendor": webgl["vendor"],
            "renderer": webgl["renderer"],
        },
        "colorDepth": random.choice([24, 32]),
        "maxTouchPoints": 0,
        "doNotTrack": random.choice([None, "1"]),
    }


def get_stealth_script(fingerprint: Dict) -> str:
    """
    Generate JavaScript injection script for fingerprint spoofing.
    Covers: navigator, screen, WebGL, canvas, audio, timezone, WebRTC
    
    Args:
        fingerprint: Fingerprint dict from generate_fingerprint()
    
    Returns:
        str: JavaScript code to inject
    """
    fp_json = json.dumps(fingerprint)
    
    return f'''
(function() {{
    try {{
        const fp = {fp_json};
        
        // === Helper: Make functions appear native ===
        const makeNative = (func, name) => {{
            const nativeStr = 'function ' + name + '() {{ [native code] }}';
            Object.defineProperty(func, 'toString', {{
                value: function() {{ return nativeStr; }},
                configurable: true, writable: true
            }});
            return func;
        }};

        // === 1. Remove WebDriver Detection ===
        Object.defineProperty(navigator, 'webdriver', {{ get: () => false }});
        
        // Remove automation markers
        const cdcRegex = /cdc_[a-zA-Z0-9]+/;
        for (const key in window) {{
            if (cdcRegex.test(key)) delete window[key];
        }}
        ['$cdc_asdjflasutopfhvcZLmcfl_', '$chrome_asyncScriptInfo', 'callPhantom'].forEach(k => {{
            if (window[k]) delete window[k];
        }});

        // === 2. Chrome Object ===
        Object.defineProperty(window, 'chrome', {{
            writable: true, enumerable: true, configurable: false,
            value: {{
                app: {{ isInstalled: false, InstallState: {{ DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' }} }},
                runtime: {{
                    OnInstalledReason: {{ CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' }},
                    OnRestartRequiredReason: {{ APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' }},
                    PlatformArch: {{ ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' }},
                    PlatformOs: {{ ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' }},
                    RequestUpdateCheckStatus: {{ NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' }}
                }}
            }}
        }});

        // === 3. Navigator Properties ===
        Object.defineProperty(navigator, 'platform', {{ get: makeNative(() => fp.platform, 'platform') }});
        Object.defineProperty(navigator, 'vendor', {{ get: makeNative(() => 'Google Inc.', 'vendor') }});
        Object.defineProperty(navigator, 'languages', {{ get: makeNative(() => fp.languages, 'languages') }});
        Object.defineProperty(navigator, 'language', {{ get: makeNative(() => fp.language, 'language') }});
        Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: makeNative(() => fp.hardwareConcurrency, 'hardwareConcurrency') }});
        Object.defineProperty(navigator, 'deviceMemory', {{ get: makeNative(() => fp.deviceMemory, 'deviceMemory') }});
        Object.defineProperty(navigator, 'maxTouchPoints', {{ get: makeNative(() => fp.maxTouchPoints, 'maxTouchPoints') }});
        
        // Plugins
        Object.defineProperty(navigator, 'plugins', {{
            get: makeNative(() => {{
                const plugins = [
                    {{name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'}},
                    {{name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''}},
                    {{name: 'Native Client', filename: 'internal-nacl-plugin', description: ''}}
                ];
                plugins.item = (i) => plugins[i];
                plugins.namedItem = (name) => plugins.find(p => p.name === name);
                plugins.refresh = () => {{}};
                return plugins;
            }}, 'plugins')
        }});

        // Permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({{ state: Notification.permission }}) :
                originalQuery(parameters)
        );

        // Connection
        Object.defineProperty(navigator, 'connection', {{
            get: makeNative(() => ({{
                effectiveType: '4g', rtt: 50, downlink: 10, saveData: false
            }}), 'connection')
        }});

        // === 4. Screen Properties ===
        if (fp.screen) {{
            const sw = fp.screen.width, sh = fp.screen.height;
            Object.defineProperty(screen, 'width', {{ get: makeNative(() => sw, 'width') }});
            Object.defineProperty(screen, 'height', {{ get: makeNative(() => sh, 'height') }});
            Object.defineProperty(screen, 'availWidth', {{ get: makeNative(() => sw, 'availWidth') }});
            Object.defineProperty(screen, 'availHeight', {{ get: makeNative(() => sh - 40, 'availHeight') }});
            Object.defineProperty(screen, 'colorDepth', {{ get: makeNative(() => fp.colorDepth || 24, 'colorDepth') }});
            Object.defineProperty(screen, 'pixelDepth', {{ get: makeNative(() => fp.colorDepth || 24, 'pixelDepth') }});
        }}

        // === 5. Canvas Fingerprint Noise ===
        if (fp.canvasNoise) {{
            const origGetContext = HTMLCanvasElement.prototype.getContext;
            HTMLCanvasElement.prototype.getContext = function(type, attrs) {{
                const ctx = origGetContext.call(this, type, attrs);
                if (type === '2d' && ctx) {{
                    const origGetImageData = ctx.getImageData;
                    ctx.getImageData = function(x, y, w, h) {{
                        const data = origGetImageData.call(this, x, y, w, h);
                        const noise = fp.canvasNoise;
                        for (let i = 0; i < data.data.length; i += 4) {{
                            data.data[i] = Math.max(0, Math.min(255, data.data[i] + noise.r));
                            data.data[i+1] = Math.max(0, Math.min(255, data.data[i+1] + noise.g));
                            data.data[i+2] = Math.max(0, Math.min(255, data.data[i+2] + noise.b));
                        }}
                        return data;
                    }};
                    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
                    this.toDataURL = function() {{
                        return origToDataURL.apply(this, arguments);
                    }};
                }}
                return ctx;
            }};
        }}

        // === 6. WebGL Fingerprint ===
        if (fp.webgl) {{
            const handler = {{
                apply: function(target, thisArg, args) {{
                    const param = args[0];
                    if (param === 37445) return fp.webgl.vendor;
                    if (param === 37446) return fp.webgl.renderer;
                    return Reflect.apply(target, thisArg, args);
                }}
            }};
            if (WebGLRenderingContext.prototype.getParameter) {{
                WebGLRenderingContext.prototype.getParameter = new Proxy(WebGLRenderingContext.prototype.getParameter, handler);
            }}
            try {{
                if (WebGL2RenderingContext && WebGL2RenderingContext.prototype.getParameter) {{
                    WebGL2RenderingContext.prototype.getParameter = new Proxy(WebGL2RenderingContext.prototype.getParameter, handler);
                }}
            }} catch(e) {{}}
        }}

        // === 7. Audio Fingerprint Noise ===
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (AudioCtx) {{
            const origCreateAnalyser = AudioCtx.prototype.createAnalyser;
            AudioCtx.prototype.createAnalyser = function() {{
                const analyser = origCreateAnalyser.call(this);
                const origGetFloat = analyser.getFloatFrequencyData;
                analyser.getFloatFrequencyData = function(array) {{
                    origGetFloat.call(this, array);
                    for (let i = 0; i < array.length; i++) {{
                        array[i] = array[i] + (fp.audioNoise || 0);
                    }}
                }};
                return analyser;
            }};
        }}

        // === 8. Timezone Spoofing ===
        if (fp.timezone) {{
            const targetTZ = fp.timezone;
            const getOffset = (tz) => {{
                try {{
                    const now = new Date();
                    const utc = new Date(now.toLocaleString('en-US', {{ timeZone: 'UTC' }}));
                    const local = new Date(now.toLocaleString('en-US', {{ timeZone: tz }}));
                    return Math.round((utc - local) / 60000);
                }} catch(e) {{ return new Date().getTimezoneOffset(); }}
            }};
            const offset = getOffset(targetTZ);
            
            Date.prototype.getTimezoneOffset = makeNative(function() {{ return offset; }}, 'getTimezoneOffset');
            
            const origResolved = Intl.DateTimeFormat.prototype.resolvedOptions;
            Intl.DateTimeFormat.prototype.resolvedOptions = makeNative(function() {{
                const r = origResolved.call(this);
                r.timeZone = targetTZ;
                return r;
            }}, 'resolvedOptions');
        }}

        // === 9. WebRTC Leak Prevention ===
        if (window.RTCPeerConnection) {{
            const origRTC = window.RTCPeerConnection;
            window.RTCPeerConnection = function(config) {{
                if (config && config.iceServers) {{
                    config.iceServers = [];
                }}
                return new origRTC(config);
            }};
            window.RTCPeerConnection.prototype = origRTC.prototype;
        }}

    }} catch(e) {{
        // Silent fail - don't break the page
    }}
}})();
'''
