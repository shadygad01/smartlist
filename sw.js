const CACHE = 'egx-smc-v12';
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

// ── Fetch: network-first for page navigations + data.json, cache-first for rest ───────
self.addEventListener('fetch', e => {
    const url = new URL(e.request.url);
    // request.mode === 'navigate' catches every SPA route (/, /archive,
    // /portfolio, ...), not just paths ending in '.html' or '/'.
    const isNavigation = e.request.mode === 'navigate';
    const isData = url.pathname.endsWith('data.json');

    if (isNavigation || isData) {
        e.respondWith(
            fetch(e.request)
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
