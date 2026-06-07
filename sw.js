const CACHE = 'egx-smc-v4';
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

// ── Fetch: network-first for HTML + data.json, cache-first for rest ───────
self.addEventListener('fetch', e => {
    const url = new URL(e.request.url);
    const isHTML = url.pathname.endsWith('.html') || url.pathname.endsWith('/');
    const isData = url.pathname.endsWith('data.json');

    if (isHTML || isData) {
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
