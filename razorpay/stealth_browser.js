// stealth_browser.js — KAKU DEV headless-Chrome stealth layer for Razorpay checkout.
// Spoofs headless-Chrome leaks (platform, webdriver, deviceMemory, plugins, Client Hints)
// to real Windows Chrome values so ThreatMetrix/Sardine can't flag the headless runtime.
// Usage: await page.add_init_script(open('stealth_browser.js').read()) before goto().
// NOTE: also disable WebRTC (--disable-webrtc) so TM can't see the LAN IP behind the proxy.


(() => {
  const log = (k,v) => { try { window.__stealth = window.__stealth||{}; window.__stealth[k]=v; } catch(e){} };
  Object.defineProperty(Navigator.prototype, 'platform', { get: () => 'Win32', configurable: true });
  Object.defineProperty(Navigator.prototype, 'webdriver', { get: () => undefined, configurable: true });
  Object.defineProperty(Navigator.prototype, 'deviceMemory', { get: () => 8, configurable: true });
  Object.defineProperty(Navigator.prototype, 'hardwareConcurrency', { get: () => 8, configurable: true });
  const realPlugins = [
    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
    { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
  ];
  const mkPlugin = (p) => ({
    name: p.name, filename: p.filename, description: p.description, length: 1,
    item: (i) => (i === 0 ? { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' } : null),
    namedItem: (n) => (n === 'application/pdf' ? { type: 'application/pdf', suffixes: 'pdf', description: '' } : null),
  });
  Object.defineProperty(Navigator.prototype, 'plugins', {
    get: () => {
      const arr = Object.create(PluginArray.prototype);
      const pl = realPlugins.map(mkPlugin);
      Object.defineProperty(arr, 'length', { value: pl.length });
      pl.forEach((p, i) => Object.defineProperty(arr, i, { value: p, enumerable: true }));
      return arr;
    }, configurable: true
  });
  Object.defineProperty(Navigator.prototype, 'maxTouchPoints', { get: () => 0, configurable: true });
  Object.defineProperty(Navigator.prototype, 'languages', { get: () => ['en-IN', 'en'], configurable: true });
  Object.defineProperty(Navigator.prototype, 'language', { get: () => 'en-IN', configurable: true });
  Object.defineProperty(Navigator.prototype, 'userAgentData', {
    get: () => ({
      brands: [{brand:'Google Chrome',version:'131'},{brand:'Chromium',version:'131'},{brand:'Not_A Brand',version:'24'}],
      mobile: false, platform: 'Windows',
      getHighEntropyValues: async () => ({ architecture: 'x86', bitness: '64', model: '', platformVersion: '10.0.0', uaFullVersion: '131.0.0.0' }),
    }), configurable: true
  });
  Object.defineProperty(Navigator.prototype, 'connection', { get: () => ({ effectiveType: '4g', rtt: 50, downlink: 10, saveData: false }), configurable: true });
  Object.defineProperty(Navigator.prototype, 'appVersion', { get: () => '5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36', configurable: true });
  window.chrome = window.chrome || { runtime: {}, loadTimes: () => ({}), csi: () => ({}), app: {} };
  log('stealth.applied', true);
})();
