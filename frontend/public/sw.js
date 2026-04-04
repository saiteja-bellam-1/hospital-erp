// Minimal service worker for PWA install support.
// No offline caching — the app requires a live server connection.

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  // Pass through all requests to the network (no caching)
  return;
});
