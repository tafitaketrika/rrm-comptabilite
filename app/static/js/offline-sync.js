/**
 * RRM – Phase 2 offline : file d'attente IndexedDB + synchro brouillard
 */
(function (global) {
  const DB_NAME = 'rrm_offline';
  const DB_VER = 1;
  const STORE = 'pending_entries';
  const ACC_STORE = 'accounts_cache';

  function openDB() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VER);
      req.onupgradeneeded = function (e) {
        const db = e.target.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
        }
        if (!db.objectStoreNames.contains(ACC_STORE)) {
          db.createObjectStore(ACC_STORE, { keyPath: 'code' });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async function addPending(entry) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      const r = tx.objectStore(STORE).add({
        ...entry,
        createdAt: new Date().toISOString(),
        status: 'pending'
      });
      r.onsuccess = () => resolve(r.result);
      r.onerror = () => reject(r.error);
    });
  }

  async function listPending() {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly');
      const r = tx.objectStore(STORE).getAll();
      r.onsuccess = () => resolve(r.result || []);
      r.onerror = () => reject(r.error);
    });
  }

  async function removePending(id) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).delete(id);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async function cacheAccounts(list) {
    if (!list || !list.length) return;
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(ACC_STORE, 'readwrite');
      const store = tx.objectStore(ACC_STORE);
      list.forEach((a) => store.put(a));
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async function getCachedAccounts() {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const r = db.transaction(ACC_STORE, 'readonly').objectStore(ACC_STORE).getAll();
      r.onsuccess = () => resolve(r.result || []);
      r.onerror = () => reject(r.error);
    });
  }

  function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve({
        name: file.name,
        type: file.type,
        size: file.size,
        data: reader.result
      });
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  async function syncAll() {
    if (!navigator.onLine) return { ok: 0, fail: 0, skipped: true };
    const pending = await listPending();
    let ok = 0, fail = 0;
    for (const item of pending) {
      try {
        const res = await fetch('/journal/api/offline-sync', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
          },
          credentials: 'same-origin',
          body: JSON.stringify(item)
        });
        if (res.ok) {
          await removePending(item.id);
          ok++;
        } else {
          fail++;
          console.warn('[offline] sync fail', item.id, await res.text());
        }
      } catch (e) {
        fail++;
        console.warn('[offline] sync error', e);
      }
    }
    updateBadge();
    return { ok, fail };
  }

  async function updateBadge() {
    const el = document.getElementById('offlineQueueBadge');
    if (!el) return;
    try {
      const list = await listPending();
      if (list.length) {
        el.style.display = '';
        el.textContent = list.length;
        el.title = list.length + ' écriture(s) en attente de synchro';
      } else {
        el.style.display = 'none';
      }
    } catch (e) { /* ignore */ }
  }

  async function interceptJournalForm(form) {
    form.addEventListener('submit', async function (e) {
      if (navigator.onLine) {
        // laisser le POST normal ; tenter une synchro des anciennes en parallèle
        syncAll();
        return;
      }
      e.preventDefault();
      const fd = new FormData(form);
      const files = form.querySelector('input[type=file]');
      const attachments = [];
      if (files && files.files) {
        for (let i = 0; i < files.files.length; i++) {
          const f = files.files[i];
          if (f.size > 4 * 1024 * 1024) {
            alert('Fichier trop volumineux pour le mode hors ligne (max 4 Mo) : ' + f.name);
            continue;
          }
          attachments.push(await fileToBase64(f));
        }
      }
      const payload = {
        entry_date: fd.get('entry_date') || '',
        description: fd.get('description') || '',
        credit_account_code: fd.get('credit_account_code') || '',
        debit_account_code: fd.get('debit_account_code') || '',
        credit_account_id: fd.get('credit_account_id') || '',
        debit_account_id: fd.get('debit_account_id') || '',
        amount: fd.get('amount') || '',
        currency: fd.get('currency') || 'MGA',
        attachments: attachments
      };
      if (!payload.description || !payload.amount) {
        alert('Description et montant obligatoires.');
        return;
      }
      await addPending(payload);
      await updateBadge();
      alert('Hors ligne : écriture enregistrée localement. Elle sera envoyée automatiquement à la reconnexion.');
      form.reset();
      // date du jour si champ existe
      const de = document.getElementById('entry_date');
      if (de && !de.value) {
        const t = new Date();
        const dd = String(t.getDate()).padStart(2, '0');
        const mm = String(t.getMonth() + 1).padStart(2, '0');
        const yy = String(t.getFullYear()).slice(-2);
        de.value = dd + '/' + mm + '/' + yy;
      }
    });
  }

  // Auto-init
  document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('entry-form');
    if (form) interceptJournalForm(form);
    // cache accounts from page if present
    if (global.RRM_ACCOUNTS_CACHE) {
      cacheAccounts(global.RRM_ACCOUNTS_CACHE);
    }
    updateBadge();
    if (navigator.onLine) syncAll();
  });

  window.addEventListener('online', function () {
    syncAll().then(function (r) {
      if (r && r.ok) {
        const el = document.getElementById('netStatus');
        if (el) {
          el.className = 'net-status show online';
          el.innerHTML = '<i class="bi bi-cloud-upload"></i> ' + r.ok + ' écriture(s) synchronisée(s)';
          setTimeout(function () { el.classList.remove('show'); }, 4000);
        }
      }
    });
  });

  global.RRMOffline = {
    addPending, listPending, syncAll, updateBadge, cacheAccounts, getCachedAccounts
  };
})(window);
