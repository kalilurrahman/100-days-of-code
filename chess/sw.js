/*
 * sw.js — service worker for offline play.
 * Precaches the app shell and serves it cache-first so the game works
 * with no network (e.g. installed to a phone's home screen).
 */

const CACHE = "chess-v2";
const ASSETS = [
  "./",
  "./index.html",
  "./style.css",
  "./chess.js",
  "./ai.js",
  "./app.js",
  "./manifest.webmanifest",
  "./icon.svg",
  "./icon-maskable.svg",
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
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req)
        .then((resp) => {
          // Cache successful same-origin responses for next time.
          if (resp && resp.ok && new URL(req.url).origin === self.location.origin) {
            const copy = resp.clone();
            caches.open(CACHE).then((cache) => cache.put(req, copy));
          }
          return resp;
        })
        .catch(() => {
          // Offline navigation fallback to the app shell.
          if (req.mode === "navigate") return caches.match("./index.html");
          return Response.error();
        });
    })
  );
});
