// Saju Destiny Service Worker v1.0
const CACHE_NAME = 'saju-destiny-v20260526-nocache';
const STATIC_ASSETS = ['/', '/index.html', '/manifest.json'];

// 설치
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS).catch(()=>{}))
  );
  self.skipWaiting();
});

// 활성화
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// 네트워크 요청 처리 (네트워크 우선, 캐시 폴백)
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});

// 푸시 알림 수신
self.addEventListener('push', event => {
  let data = { title: '🌟 Saju Destiny', body: 'ជោគជតាប្រចាំថ្ងៃរបស់អ្នក', url: '/' };
  if (event.data) {
    try { data = { ...data, ...event.data.json() }; } catch(e) {}
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/icon-192.png',
      badge: '/icon-192.png',
      tag: 'daily-fortune',
      renotify: true,
      requireInteraction: false,
      data: { url: data.url || '/' },
      actions: [
        { action: 'open', title: '📖 ការអានបន្ថែម' },
        { action: 'dismiss', title: '✕' }
      ]
    })
  );
});

// 알림 클릭
self.addEventListener('notificationclick', event => {
  event.notification.close();
  if (event.action === 'dismiss') return;
  const url = event.notification.data?.url || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});

// 백그라운드 동기화 (매일 아침 7시 알림 스케줄)
self.addEventListener('periodicsync', event => {
  if (event.tag === 'daily-fortune') {
    event.waitUntil(sendDailyFortune());
  }
});

async function sendDailyFortune() {
  const hour = new Date().getHours();
  if (hour < 6 || hour > 9) return; // 6~9시 사이에만 발송
  try {
    const r = await fetch('/api/v2/today');
    const d = await r.json();
    await self.registration.showNotification('🌅 ជោគជតាប្រចាំថ្ងៃ — Saju Destiny', {
      body: `សសរស្ដម្ភថ្ងៃ: ${d.day_pillar || '—'} · ចុចដើម្បីអានបន្ថែម`,
      icon: '/icon-192.png',
      tag: 'daily-fortune',
      data: { url: '/?mode=daily' }
    });
  } catch(e) {}
}
