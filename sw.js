const CACHE = 'egx-smc-v20';
const STATIC = ['manifest.json', 'icon.svg'];

// ── Install: cache only non-HTML static assets ────────────────────────────
self.addEventListener('install', e => {
    e.waitUntil(
        caches.open(CACHE)
            .then(c => c.addAll(STATIC))
            .then(() => self.skipWaiting())
    );
});

// ── Activate: clear old caches ────────────────────────────────────────────
self.addEventListener('activate', e => {
    e.waitUntil(
        caches.keys()
            .then(keys => Promise.all(
                keys.filter(k => k !== CACHE).map(k => caches.delete(k))
            ))
            .then(() => self.clients.claim())
    );
});

// ── Fetch: network-first for page navigations + live data files, cache-first for rest ───────
self.addEventListener('fetch', e => {
    const url = new URL(e.request.url);
    // request.mode === 'navigate' catches every SPA route (/, /archive,
    // /portfolio, ...), not just paths ending in '.html' or '/'.
    const isNavigation = e.request.mode === 'navigate';
    // presentation_snapshot.json carries the live prices the Portfolio
    // Tracker's Current Price / Unrealized P&L columns are computed from
    // (see SnapshotProvider.tsx); data.json is a legacy scan-status file
    // kept here for back-compat. Both must always go to the network —
    // Safari has been observed serving a stale snapshot from its HTTP/SW
    // cache when a data file falls through to the cache-first branch below.
    const isData = url.pathname.endsWith('data.json') || url.pathname.endsWith('presentation_snapshot.json');

    if (isNavigation || isData) {
        e.respondWith(
            fetch(e.request, { cache: 'no-store' })
                .then(res => {
                    const clone = res.clone();
                    caches.open(CACHE).then(c => c.put(e.request, clone));
                    return res;
                })
                .catch(() => caches.match(e.request))
        );
        return;
    }

    e.respondWith(
        caches.match(e.request).then(r => r || fetch(e.request))
    );
});
