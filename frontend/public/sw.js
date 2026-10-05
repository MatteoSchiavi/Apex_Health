const CACHE_NAME = "apex-static-v1";
const SHELL_FILES = [
  "/offline.html",
  "/manifest.webmanifest",
  "/icons/apex.svg",
  "/icons/apex-192.png",
  "/icons/apex-512.png",
  "/icons/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES)));
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter((name) => name.startsWith("apex-static-") && name !== CACHE_NAME).map((name) => caches.delete(name)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(async () => {
      const cache = await caches.open(CACHE_NAME);
      return (await cache.match("/offline.html")) || Response.error();
    }));
    return;
  }

  // Cache only build output and explicit public PWA assets. All API calls,
  // HTML pages, auth responses, and user data remain network-only.
  const isPublicAsset = url.pathname.startsWith("/assets/") ||
    url.pathname.startsWith("/fonts/") ||
    SHELL_FILES.includes(url.pathname);
  if (!isPublicAsset) return;

  const cachePromise = caches.open(CACHE_NAME);
  const network = fetch(request).then(async (response) => {
    if (response.ok && response.type === "basic") {
      const cache = await cachePromise;
      await cache.put(request, response.clone());
      // Keep updates from accumulating an unbounded history of hashed bundles.
      const keys = (await cache.keys()).filter((key) => !SHELL_FILES.includes(new URL(key.url).pathname));
      await Promise.all(keys.slice(0, Math.max(0, keys.length - 64)).map((key) => cache.delete(key)));
    }
    return response;
  });
  event.waitUntil(network.then(() => undefined).catch(() => undefined));
  event.respondWith(cachePromise.then(async (cache) => (await cache.match(request)) || network));
});
