// Service worker d'adLyn (application Android installable, PWABuilder / TWA).
// Rôle unique : quand l'ouverture d'une page échoue faute d'Internet, afficher la page
// « Pas de connexion » (offline.html) au lieu de l'erreur du navigateur.
// RIEN d'autre n'est mis en cache : le site reste toujours à jour (aucune ancienne version servie).
const CACHE_HORS_LIGNE = "adlyn-hors-ligne-1";

// Installation : on garde de côté la seule page hors ligne
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE_HORS_LIGNE).then((c) => c.add("/offline.html")).catch(() => {}));
  self.skipWaiting();
});

// Activation : prise de contrôle immédiate des pages ouvertes
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

// Ouverture d'une page (navigation) : réseau d'abord ; en cas d'échec, page hors ligne.
// Les appels à l'API et les images ne passent pas par ici (rien n'est intercepté).
self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate") return;
  event.respondWith(
    fetch(event.request).catch(() => caches.match("/offline.html").then((r) => r || Response.error())),
  );
});
