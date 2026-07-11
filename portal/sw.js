/*
 * sw.js — service worker for the KR portal.
 * Network-first for navigations (content stays fresh), cache-first for
 * static assets. Only caches prefixed with "krportal-" are managed here so
 * the chess app's caches (same origin, /chess/ scope) are left alone.
 */

const CACHE = "krportal-v1";
const ASSETS = [
  "./",
  "./index.html",
  "./style.css",
  "./data.js",
  "./app.js",
  "./manifest.webmanifest",
  "./icon.svg",
  "./icon-192.png",
  "./icon-512.png",
  "./icon-maskable-512.png",
  "./apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k.startsWith("krportal-") && k !== CACHE)
            .map((k) => caches.delete(k))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  // Leave the chess app (its own service worker scope) alone.
  if (url.pathname.includes("/chess/")) return;

  if (req.mode === "navigate") {
    // Network-first so a redeploy shows up on next visit.
    event.respondWith(
      fetch(req)
        .then((resp) => {
          const copy = resp.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy));
          return resp;
        })
        .catch(() =>
          caches.open(CACHE).then((cache) => cache.match(req).then((hit) => hit || cache.match("./index.html")))
        )
    );
    return;
  }

  // Static assets: cache-first, refill from network.
  event.respondWith(
    caches.open(CACHE).then((cache) =>
      cache.match(req).then((cached) => {
        if (cached) return cached;
        return fetch(req).then((resp) => {
          if (resp && resp.ok && url.origin === self.location.origin) {
            cache.put(req, resp.clone());
          }
          return resp;
        });
      })
    )
  );
});
