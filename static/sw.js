// Service Worker for MelkID PWA
const CACHE_NAME = 'melkid-v1.0.0';
const OFFLINE_URL = '/offline/';

// Files to cache for offline functionality
const STATIC_CACHE_URLS = [
  '/',
  '/static/css/bootstrap.min.css',
  '/static/css/modern-ui.css',
  '/static/css/mobile-enhancements.css',
  '/static/js/bootstrap.bundle.min.js',
  '/static/js/modern-interactions.js',
  '/static/fonts/vazirmatn-webfont.woff2',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png',
  OFFLINE_URL
];

// API endpoints to cache
const API_CACHE_URLS = [
  '/api/user/profile/',
  '/api/services/',
  '/api/notifications/'
];

// Install event - cache static resources
self.addEventListener('install', (event) => {
  console.log('🔧 Service Worker installing...');
  
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('📦 Caching static resources');
        return cache.addAll(STATIC_CACHE_URLS);
      })
      .then(() => {
        console.log('✅ Service Worker installed successfully');
        return self.skipWaiting();
      })
      .catch((error) => {
        console.error('❌ Service Worker installation failed:', error);
      })
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  console.log('🚀 Service Worker activating...');
  
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames.map((cacheName) => {
            if (cacheName !== CACHE_NAME) {
              console.log('🗑️ Deleting old cache:', cacheName);
              return caches.delete(cacheName);
            }
          })
        );
      })
      .then(() => {
        console.log('✅ Service Worker activated');
        return self.clients.claim();
      })
  );
});

// Fetch event - serve cached content when offline
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') {
    return;
  }

  // Skip chrome-extension and other non-http requests
  if (!url.protocol.startsWith('http')) {
    return;
  }

  // Handle different types of requests
  if (url.pathname.startsWith('/api/')) {
    // API requests - network first, then cache
    event.respondWith(handleApiRequest(request));
  } else if (url.pathname.startsWith('/static/')) {
    // Static files - cache first, then network
    event.respondWith(handleStaticRequest(request));
  } else {
    // HTML pages - network first, then cache, then offline page
    event.respondWith(handlePageRequest(request));
  }
});

// Handle API requests with network-first strategy
async function handleApiRequest(request) {
  try {
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      // Cache successful API responses
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    console.log('🌐 Network failed, trying cache for API:', request.url);
    
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // Return offline API response
    return new Response(
      JSON.stringify({
        error: 'اتصال اینترنت برقرار نیست',
        offline: true,
        timestamp: new Date().toISOString()
      }),
      {
        status: 503,
        statusText: 'Service Unavailable',
        headers: {
          'Content-Type': 'application/json; charset=utf-8'
        }
      }
    );
  }
}

// Handle static files with cache-first strategy
async function handleStaticRequest(request) {
  const cachedResponse = await caches.match(request);
  
  if (cachedResponse) {
    return cachedResponse;
  }
  
  try {
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    console.log('❌ Failed to fetch static resource:', request.url);
    return new Response('Resource not available offline', { status: 404 });
  }
}

// Handle page requests with network-first strategy
async function handlePageRequest(request) {
  try {
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      // Cache successful page responses
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    console.log('🌐 Network failed, trying cache for page:', request.url);
    
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // Return offline page
    const offlineResponse = await caches.match(OFFLINE_URL);
    if (offlineResponse) {
      return offlineResponse;
    }
    
    // Fallback offline HTML
    return new Response(`
      <!DOCTYPE html>
      <html lang="fa" dir="rtl">
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>آفلاین - MelkID</title>
        <style>
          body {
            font-family: 'Vazirmatn', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-align: center;
            padding: 2rem;
            margin: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-direction: column;
          }
          .offline-icon {
            font-size: 4rem;
            margin-bottom: 1rem;
          }
          .offline-title {
            font-size: 2rem;
            margin-bottom: 1rem;
          }
          .offline-message {
            font-size: 1.2rem;
            margin-bottom: 2rem;
            opacity: 0.9;
          }
          .retry-button {
            background: rgba(255, 255, 255, 0.2);
            border: 2px solid rgba(255, 255, 255, 0.3);
            color: white;
            padding: 1rem 2rem;
            border-radius: 50px;
            font-size: 1.1rem;
            cursor: pointer;
            transition: all 0.3s ease;
          }
          .retry-button:hover {
            background: rgba(255, 255, 255, 0.3);
            transform: translateY(-2px);
          }
        </style>
      </head>
      <body>
        <div class="offline-icon">🌐</div>
        <h1 class="offline-title">اتصال اینترنت برقرار نیست</h1>
        <p class="offline-message">
          لطفاً اتصال اینترنت خود را بررسی کنید و دوباره تلاش کنید
        </p>
        <button class="retry-button" onclick="window.location.reload()">
          تلاش مجدد
        </button>
        
        <script>
          // Auto-retry when online
          window.addEventListener('online', () => {
            window.location.reload();
          });
          
          // Show online/offline status
          window.addEventListener('offline', () => {
            document.body.style.filter = 'grayscale(100%)';
          });
          
          window.addEventListener('online', () => {
            document.body.style.filter = 'none';
          });
        </script>
      </body>
      </html>
    `, {
      status: 200,
      headers: {
        'Content-Type': 'text/html; charset=utf-8'
      }
    });
  }
}

// Background sync for form submissions
self.addEventListener('sync', (event) => {
  console.log('🔄 Background sync triggered:', event.tag);
  
  if (event.tag === 'background-sync-forms') {
    event.waitUntil(syncPendingForms());
  }
});

// Sync pending form submissions when back online
async function syncPendingForms() {
  try {
    const cache = await caches.open(CACHE_NAME);
    const pendingRequests = await cache.match('/pending-forms');
    
    if (pendingRequests) {
      const forms = await pendingRequests.json();
      
      for (const form of forms) {
        try {
          await fetch(form.url, {
            method: form.method,
            headers: form.headers,
            body: form.body
          });
          
          console.log('✅ Synced pending form:', form.url);
        } catch (error) {
          console.log('❌ Failed to sync form:', form.url, error);
        }
      }
      
      // Clear pending forms after sync
      await cache.delete('/pending-forms');
    }
  } catch (error) {
    console.error('❌ Background sync failed:', error);
  }
}

// Push notification handling
self.addEventListener('push', (event) => {
  console.log('📱 Push notification received');
  
  const options = {
    body: 'شما پیام جدیدی دارید',
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/badge-72x72.png',
    vibrate: [100, 50, 100],
    data: {
      dateOfArrival: Date.now(),
      primaryKey: 1
    },
    actions: [
      {
        action: 'explore',
        title: 'مشاهده',
        icon: '/static/icons/checkmark.png'
      },
      {
        action: 'close',
        title: 'بستن',
        icon: '/static/icons/xmark.png'
      }
    ],
    requireInteraction: true,
    silent: false,
    dir: 'rtl',
    lang: 'fa'
  };

  if (event.data) {
    const data = event.data.json();
    options.body = data.body || options.body;
    options.title = data.title || 'MelkID';
  }

  event.waitUntil(
    self.registration.showNotification('MelkID', options)
  );
});

// Handle notification clicks
self.addEventListener('notificationclick', (event) => {
  console.log('🔔 Notification clicked:', event.action);
  
  event.notification.close();

  if (event.action === 'explore') {
    event.waitUntil(
      clients.openWindow('/dashboard/')
    );
  } else if (event.action === 'close') {
    // Just close the notification
    return;
  } else {
    // Default action - open the app
    event.waitUntil(
      clients.openWindow('/')
    );
  }
});

// Handle notification close
self.addEventListener('notificationclose', (event) => {
  console.log('🔕 Notification closed');
});

// Periodic background sync (if supported)
self.addEventListener('periodicsync', (event) => {
  console.log('⏰ Periodic sync triggered:', event.tag);
  
  if (event.tag === 'update-notifications') {
    event.waitUntil(updateNotifications());
  }
});

async function updateNotifications() {
  try {
    const response = await fetch('/api/notifications/unread/');
    const data = await response.json();
    
    if (data.count > 0) {
      await self.registration.showNotification('MelkID', {
        body: `شما ${data.count} پیام خوانده نشده دارید`,
        icon: '/static/icons/icon-192x192.png',
        badge: '/static/icons/badge-72x72.png',
        tag: 'unread-notifications',
        renotify: true,
        silent: true
      });
    }
  } catch (error) {
    console.log('❌ Failed to update notifications:', error);
  }
}

// Share target handling (if the app is registered as a share target)
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SHARE_TARGET') {
    console.log('📤 Share target activated:', event.data);
    
    // Handle shared content
    event.waitUntil(
      clients.openWindow('/share/?data=' + encodeURIComponent(JSON.stringify(event.data)))
    );
  }
});

console.log('🎉 MelkID Service Worker loaded successfully');