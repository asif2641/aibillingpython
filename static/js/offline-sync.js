/**
 * static/js/offline-sync.js
 * =========================
 * Client-Side IndexedDB Storage & Auto-Sync Engine for aibilling PWA.
 *
 * Responsibilities:
 * 1. Manages IndexedDB 'aibilling_pwa_db' (v1) with object stores:
 *    - sync_queue: offline mutation queue
 *    - cached_parties, cached_categories, cached_units: reference data
 * 2. Caches reference data from /sync/pull/ when online.
 * 3. Monitors network connectivity (online/offline events) and renders
 *    a floating status indicator (#offline-sync-indicator).
 * 4. Intercepts manual bill form submissions when offline, stores to IndexedDB
 *    queue, and displays confirmation modal.
 * 5. Automatically pushes pending items to /sync/push/ when back online.
 */

(function () {
  'use strict';

  const DB_NAME = 'aibilling_pwa_db';
  const DB_VERSION = 1;

  // ───────────────────────────────────────────────────────────────────────────
  // 1. IndexedDB Helper Functions
  // ───────────────────────────────────────────────────────────────────────────

  function openDB() {
    return new Promise((resolve, reject) => {
      if (!window.indexedDB) {
        return reject(new Error('IndexedDB not supported in this browser.'));
      }
      const request = window.indexedDB.open(DB_NAME, DB_VERSION);

      request.onupgradeneeded = (event) => {
        const db = event.target.result;

        // Object store: sync_queue (offline mutations)
        if (!db.objectStoreNames.contains('sync_queue')) {
          const syncStore = db.createObjectStore('sync_queue', { keyPath: 'client_id' });
          syncStore.createIndex('status', 'status', { unique: false });
          syncStore.createIndex('timestamp', 'client_timestamp', { unique: false });
        }

        // Object store: cached_parties
        if (!db.objectStoreNames.contains('cached_parties')) {
          const partiesStore = db.createObjectStore('cached_parties', { keyPath: 'id' });
          partiesStore.createIndex('name', 'name', { unique: false });
        }

        // Object store: cached_categories
        if (!db.objectStoreNames.contains('cached_categories')) {
          db.createObjectStore('cached_categories', { keyPath: 'id' });
        }

        // Object store: cached_units
        if (!db.objectStoreNames.contains('cached_units')) {
          db.createObjectStore('cached_units', { keyPath: 'code' });
        }
      };

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async function saveSyncQueueItem(item) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('sync_queue', 'readwrite');
      const store = tx.objectStore('sync_queue');
      const req = store.put(item);
      req.onsuccess = () => resolve(item);
      req.onerror = () => reject(req.error);
    });
  }

  async function getPendingSyncItems() {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('sync_queue', 'readonly');
      const store = tx.objectStore('sync_queue');
      let req;
      if (store.indexNames.contains('status')) {
        const index = store.index('status');
        req = index.getAll('pending');
      } else {
        req = store.getAll();
      }
      req.onsuccess = () => {
        const items = (req.result || []).filter((i) => i.status === 'pending');
        resolve(items);
      };
      req.onerror = () => reject(req.error);
    });
  }

  async function updateSyncItemStatus(clientId, status, errorMsg = '') {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('sync_queue', 'readwrite');
      const store = tx.objectStore('sync_queue');
      const req = store.get(clientId);
      req.onsuccess = () => {
        const item = req.result;
        if (item) {
          item.status = status;
          if (errorMsg) item.error = errorMsg;
          item.synced_at = new Date().toISOString();
          store.put(item);
        }
        resolve();
      };
      req.onerror = () => reject(req.error);
    });
  }

  // ───────────────────────────────────────────────────────────────────────────
  // 2. Reference Data Caching (/sync/pull/)
  // ───────────────────────────────────────────────────────────────────────────

  async function cacheReferenceData() {
    if (!navigator.onLine) return;
    try {
      const langPrefix = document.documentElement.lang === 'ur' ? '/ur' : '/en';
      const endpoints = ['/sync/pull/', `${langPrefix}/sync/pull/`];
      let response = null;

      for (const ep of endpoints) {
        try {
          const res = await fetch(ep, {
            headers: { Accept: 'application/json' },
          });
          if (res.ok) {
            response = res;
            break;
          }
        } catch (_) {}
      }

      if (!response) return;
      const data = await response.json();
      const db = await openDB();

      if (Array.isArray(data.parties) && data.parties.length > 0) {
        const tx = db.transaction('cached_parties', 'readwrite');
        const store = tx.objectStore('cached_parties');
        data.parties.forEach((p) => store.put(p));
      }

      if (Array.isArray(data.categories) && data.categories.length > 0) {
        const tx = db.transaction('cached_categories', 'readwrite');
        const store = tx.objectStore('cached_categories');
        data.categories.forEach((c) => store.put(c));
      }

      if (Array.isArray(data.units) && data.units.length > 0) {
        const tx = db.transaction('cached_units', 'readwrite');
        const store = tx.objectStore('cached_units');
        data.units.forEach((u) => store.put(u));
      }

      console.log('[OfflineSync] Reference data cached in IndexedDB.');
    } catch (err) {
      console.warn('[OfflineSync] Failed to cache reference data:', err);
    }
  }

  // ───────────────────────────────────────────────────────────────────────────
  // 3. UI Status Indicator & Toast Notifications
  // ───────────────────────────────────────────────────────────────────────────

  let hideTimeout = null;

  function updateIndicator(state, count = 0) {
    const el = document.getElementById('offline-sync-indicator');
    if (!el) return;

    if (hideTimeout) {
      clearTimeout(hideTimeout);
      hideTimeout = null;
    }

    const isUrdu =
      document.documentElement.lang === 'ur' ||
      document.documentElement.dir === 'rtl';

    if (state === 'offline') {
      el.classList.remove('hidden');
      const pendingBadge = count > 0
        ? ` <span class="bg-amber-200 dark:bg-amber-900 px-1.5 py-0.5 rounded-full text-[11px] font-bold">(${count})</span>`
        : '';
      const textEn = `⚠️ Offline Mode — Bills saved locally will sync when online${pendingBadge}`;
      const textUr = `⚠️ آف لائن موڈ — بلز محفوظ ہیں، آن لائن ہونے پر سنک ہوں گے${pendingBadge}`;

      el.innerHTML = `
        <div class="flex items-center gap-2 px-4 py-2.5 rounded-2xl bg-amber-50 dark:bg-amber-950 border border-amber-300 dark:border-amber-800 text-amber-900 dark:text-amber-200 shadow-xl text-xs sm:text-sm font-semibold transition-all">
          <span class="relative flex h-2.5 w-2.5">
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
            <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500"></span>
          </span>
          <span>${isUrdu ? textUr : textEn}</span>
        </div>
      `;
    } else if (state === 'syncing') {
      el.classList.remove('hidden');
      const textEn = `🔄 Syncing (${count} bill${count === 1 ? '' : 's'})...`;
      const textUr = `🔄 سنک ہو رہا ہے (${count} بلز)...`;

      el.innerHTML = `
        <div class="flex items-center gap-2 px-4 py-2.5 rounded-2xl bg-indigo-50 dark:bg-indigo-950 border border-indigo-300 dark:border-indigo-800 text-indigo-900 dark:text-indigo-200 shadow-xl text-xs sm:text-sm font-semibold transition-all">
          <svg class="animate-spin w-4 h-4 text-indigo-600 dark:text-indigo-400" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
          </svg>
          <span>${isUrdu ? textUr : textEn}</span>
        </div>
      `;
    } else if (state === 'synced') {
      el.classList.remove('hidden');
      const textEn = `✅ Synced${count > 0 ? ` (${count} bill${count === 1 ? '' : 's'})` : ''}`;
      const textUr = `✅ سنک ہو گیا${count > 0 ? ` (${count} بلز)` : ''}`;

      el.innerHTML = `
        <div class="flex items-center gap-2 px-4 py-2.5 rounded-2xl bg-emerald-50 dark:bg-emerald-950 border border-emerald-300 dark:border-emerald-800 text-emerald-900 dark:text-emerald-200 shadow-xl text-xs sm:text-sm font-semibold transition-all">
          <span>${isUrdu ? textUr : textEn}</span>
        </div>
      `;

      hideTimeout = setTimeout(() => {
        el.classList.add('hidden');
      }, 3000);
    } else if (state === 'hidden') {
      el.classList.add('hidden');
    }
  }

  function showOfflineSavedModal(isUrdu) {
    const title = isUrdu ? 'بل کامیابی سے محفوظ ہو گیا!' : 'Bill Saved Offline!';
    const message = isUrdu
      ? 'انٹرنیٹ بحال ہوتے ہی یہ خودکار طور پر سرور پر منتقل ہو جائے گا۔'
      : 'It will automatically sync as soon as you reconnect to the internet.';
    const closeBtn = isUrdu ? 'ٹھیک ہے' : 'Got it';

    const modalId = 'offline-saved-modal';
    const existing = document.getElementById(modalId);
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = modalId;
    modal.className =
      'fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in';
    modal.innerHTML = `
      <div class="bg-white dark:bg-slate-800 rounded-3xl p-6 sm:p-8 max-w-md w-full shadow-2xl border border-slate-200 dark:border-slate-700 text-center space-y-4" dir="${isUrdu ? 'rtl' : 'ltr'}">
        <div class="w-16 h-16 mx-auto rounded-2xl bg-amber-100 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 flex items-center justify-center text-3xl shadow-inner">
          💾
        </div>
        <h3 class="text-lg sm:text-xl font-bold text-slate-900 dark:text-white">
          ${title}
        </h3>
        <p class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
          ${message}
        </p>
        <div class="pt-2">
          <button type="button" id="close-offline-modal" class="w-full py-3 min-h-[44px] rounded-xl bg-primary-600 hover:bg-primary-500 text-white font-semibold text-sm shadow-md transition-all focus:outline-none focus:ring-2 focus:ring-primary-500">
            ${closeBtn}
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    const btn = document.getElementById('close-offline-modal');
    if (btn) {
      btn.focus();
      btn.addEventListener('click', () => modal.remove());
    }
  }

  function getCsrfToken() {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    if (match) return decodeURIComponent(match[1]);
    const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (csrfInput) return csrfInput.value;
    return '';
  }

  function generateUUID() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  // ───────────────────────────────────────────────────────────────────────────
  // 4. Automatic Background Sync on Reconnect (/sync/push/)
  // ───────────────────────────────────────────────────────────────────────────

  let isSyncing = false;

  async function triggerSync() {
    if (!navigator.onLine || isSyncing) return;

    let pending = [];
    try {
      pending = await getPendingSyncItems();
    } catch (e) {
      console.warn('[OfflineSync] Could not read sync queue:', e);
      return;
    }

    if (pending.length === 0) {
      return;
    }

    isSyncing = true;
    updateIndicator('syncing', pending.length);

    try {
      const langPrefix = document.documentElement.lang === 'ur' ? '/ur' : '/en';
      const endpoints = ['/sync/push/', `${langPrefix}/sync/push/`];
      let response = null;

      const payload = { items: pending };
      const csrfToken = getCsrfToken();

      for (const ep of endpoints) {
        try {
          const res = await fetch(ep, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': csrfToken,
              Accept: 'application/json',
            },
            body: JSON.stringify(payload),
          });
          if (res.ok) {
            response = res;
            break;
          }
        } catch (_) {}
      }

      if (response && response.ok) {
        const result = await response.json();

        // Mark processed items
        if (Array.isArray(result.processed)) {
          for (const item of result.processed) {
            const clientId = typeof item === 'object' ? item.client_id : item;
            if (clientId) {
              await updateSyncItemStatus(clientId, 'processed');
            }
          }
        }

        // Mark failed items
        if (Array.isArray(result.failed)) {
          for (const item of result.failed) {
            if (typeof item === 'object' && item.client_id) {
              await updateSyncItemStatus(
                item.client_id,
                'failed',
                item.error || 'Server rejected item'
              );
            }
          }
        }

        const count = Array.isArray(result.processed) ? result.processed.length : pending.length;
        updateIndicator('synced', count);

        // If on the bills list page, refresh table to show synced bills
        if (
          window.location.pathname.includes('/bills') &&
          !window.location.pathname.includes('/add') &&
          !window.location.pathname.includes('/edit')
        ) {
          setTimeout(() => window.location.reload(), 1500);
        }
      } else {
        console.warn('[OfflineSync] Push endpoint returned non-200');
        const remaining = await getPendingSyncItems();
        updateIndicator(navigator.onLine ? 'hidden' : 'offline', remaining.length);
      }
    } catch (err) {
      console.error('[OfflineSync] Sync failed:', err);
      const remaining = await getPendingSyncItems();
      updateIndicator(navigator.onLine ? 'hidden' : 'offline', remaining.length);
    } finally {
      isSyncing = false;
    }
  }

  // ───────────────────────────────────────────────────────────────────────────
  // 5. Offline Manual Bill Form Interception
  // ───────────────────────────────────────────────────────────────────────────

  function attachBillFormInterception() {
    const form =
      document.getElementById('bill-form') ||
      document.querySelector('form[action*="/bills/add/"]');
    if (!form) return;

    form.addEventListener('submit', async function (e) {
      if (navigator.onLine) {
        // Normal online submission proceeds to server
        return;
      }

      e.preventDefault();

      const formData = new FormData(form);
      const invoiceNo = (formData.get('invoice_no') || '').trim();
      const billDate = (
        formData.get('bill_date') || new Date().toISOString().split('T')[0]
      ).trim();
      const billType = (formData.get('bill_type') || 'purchase').trim();

      const rawParty = formData.get('party');
      const partyId = rawParty && !isNaN(parseInt(rawParty, 10)) ? parseInt(rawParty, 10) : null;
      const partySelect = form.querySelector('[name="party"]');
      let partyName = '';
      if (partySelect && partySelect.selectedIndex >= 0) {
        partyName = partySelect.options[partySelect.selectedIndex].text.trim();
        if (partyName.startsWith('---------')) partyName = '';
      }
      if (!partyName && formData.get('party_name')) {
        partyName = String(formData.get('party_name')).trim();
      }

      const rawCategory = formData.get('category');
      const categoryId =
        rawCategory && !isNaN(parseInt(rawCategory, 10))
          ? parseInt(rawCategory, 10)
          : null;

      const discount = parseFloat(formData.get('discount')) || 0;
      const tax = parseFloat(formData.get('tax')) || 0;
      const amountPaid = parseFloat(formData.get('amount_paid')) || 0;
      const notes = (formData.get('notes') || '').trim();

      // Extract line items from formset rows
      const items = [];
      const itemNameInputs = form.querySelectorAll('input[name*="item_name"]');

      itemNameInputs.forEach((input) => {
        const nameAttr = input.name;
        // Determine prefix for sibling inputs (e.g., 'items-0-')
        const prefix = nameAttr.replace(/item_name$/, '');
        const deleteCheckbox = form.querySelector(`input[name="${prefix}DELETE"]`);
        if (deleteCheckbox && deleteCheckbox.checked) {
          return;
        }

        const itemName = (input.value || '').trim();
        if (!itemName) return;

        const urduNameInput = form.querySelector(`input[name="${prefix}urdu_item_name"]`);
        const qtyInput = form.querySelector(`input[name="${prefix}quantity"]`);
        const unitInput =
          form.querySelector(`select[name="${prefix}unit"]`) ||
          form.querySelector(`input[name="${prefix}unit"]`);
        const priceInput = form.querySelector(`input[name="${prefix}unit_price"]`);

        const qty = parseFloat(qtyInput ? qtyInput.value : 1) || 1;
        const unitVal = (unitInput ? unitInput.value : 'pcs').trim() || 'pcs';
        const price = parseFloat(priceInput ? priceInput.value : 0) || 0;
        const lineTotal = +(qty * price).toFixed(2);

        items.push({
          item_name: itemName,
          urdu_item_name: urduNameInput ? urduNameInput.value.trim() : '',
          quantity: qty,
          unit: unitVal,
          unit_price: price,
          line_total: lineTotal,
        });
      });

      const isUrdu =
        document.documentElement.lang === 'ur' ||
        document.documentElement.dir === 'rtl';

      if (!partyName && !partyId) {
        alert(
          isUrdu
            ? 'براہ کرم وینڈر یا کسٹمر منتخب کریں'
            : 'Please select or enter a vendor / customer.'
        );
        return;
      }

      if (items.length === 0) {
        alert(
          isUrdu
            ? 'براہ کرم کم از کم ایک آئٹم درج کریں'
            : 'Please enter at least one bill line item.'
        );
        return;
      }

      const clientId = generateUUID();
      const syncItem = {
        client_id: clientId,
        record_type: 'bill',
        action: 'create',
        client_timestamp: new Date().toISOString(),
        status: 'pending',
        payload: {
          invoice_no: invoiceNo,
          bill_date: billDate,
          bill_type: billType,
          party_id: partyId,
          party_name: partyName,
          category_id: categoryId,
          discount: discount,
          tax: tax,
          amount_paid: amountPaid,
          notes: notes,
          items: items,
        },
      };

      try {
        await saveSyncQueueItem(syncItem);
        showOfflineSavedModal(isUrdu);
        form.reset();

        const pending = await getPendingSyncItems();
        updateIndicator('offline', pending.length);
      } catch (err) {
        console.error('[OfflineSync] Failed to save offline bill:', err);
        alert(
          isUrdu
            ? 'خرابی: بل محفوظ نہیں ہو سکا'
            : 'Error: Failed to save bill offline.'
        );
      }
    });
  }

  // ───────────────────────────────────────────────────────────────────────────
  // 6. Initialization & Connectivity Event Listeners
  // ───────────────────────────────────────────────────────────────────────────

  async function checkInitialQueueState() {
    try {
      const pending = await getPendingSyncItems();
      if (!navigator.onLine) {
        updateIndicator('offline', pending.length);
      } else if (pending.length > 0) {
        triggerSync();
      }
    } catch (_) {}
  }

  function init() {
    window.addEventListener('online', () => {
      console.log('[OfflineSync] Network connected (online). Triggering sync...');
      triggerSync();
    });

    window.addEventListener('offline', async () => {
      console.log('[OfflineSync] Network disconnected (offline).');
      try {
        const pending = await getPendingSyncItems();
        updateIndicator('offline', pending.length);
      } catch (_) {
        updateIndicator('offline', 0);
      }
    });

    // Cache reference data on load if online
    if (navigator.onLine) {
      cacheReferenceData();
    }

    // Check offline queue and attach form interception
    checkInitialQueueState();
    attachBillFormInterception();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expose API for testing / debugging
  window.AIBillingSync = {
    openDB,
    saveSyncQueueItem,
    getPendingSyncItems,
    updateSyncItemStatus,
    cacheReferenceData,
    triggerSync,
    updateIndicator,
  };
})();
