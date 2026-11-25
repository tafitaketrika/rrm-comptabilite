/**
 * RRM – Phase 2 offline stabilisé v8
 * Anti-doublons : un seul enregistrement local + une seule synchro à la fois
 */
(function (global) {
  const DB_NAME = 'rrm_offline';
  const DB_VER = 2;
  const STORE = 'pending_entries';
  const ACC_STORE = 'accounts_cache';

  let appOffline = (typeof navigator !== 'undefined' && navigator.onLine === false);
  let saveInProgress = false;
  let syncInProgress = false;
  let lastSaveFingerprint = '';
  let lastSaveAt = 0;

  function openDB() {
    return new Promise(function (resolve, reject) {
      var req = indexedDB.open(DB_NAME, DB_VER);
      req.onupgradeneeded = function (e) {
        var db = e.target.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
        }
        if (!db.objectStoreNames.contains(ACC_STORE)) {
          db.createObjectStore(ACC_STORE, { keyPath: 'code' });
        }
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error || new Error('IndexedDB open failed')); };
    });
  }

  function withTimeout(promise, ms, label) {
    return Promise.race([
      promise,
      new Promise(function (_, reject) {
        setTimeout(function () {
          reject(new Error((label || 'Opération') + ' trop longue (' + ms + ' ms)'));
        }, ms);
      })
    ]);
  }

  async function addPending(entry) {
    var db = await withTimeout(openDB(), 5000, 'Ouverture IndexedDB');
    return new Promise(function (resolve, reject) {
      var tx = db.transaction(STORE, 'readwrite');
      var payload = {
        kind: entry.kind,
        entry_date: entry.entry_date,
        description: entry.description,
        credit_account_code: entry.credit_account_code,
        debit_account_code: entry.debit_account_code,
        credit_account_id: entry.credit_account_id,
        debit_account_id: entry.debit_account_id,
        amount: entry.amount,
        currency: entry.currency,
        attachments: entry.attachments,
        name: entry.name,
        start_date: entry.start_date,
        end_date: entry.end_date,
        assigned_to: entry.assigned_to,
        cc_to: entry.cc_to,
        cost_center_id: entry.cost_center_id,
        lines: entry.lines,
        budget_id: entry.budget_id,
        fingerprint: entry.fingerprint || '',
        createdAt: new Date().toISOString(),
        status: 'pending'
      };
      var r = tx.objectStore(STORE).add(payload);
      r.onsuccess = function () { resolve(r.result); };
      r.onerror = function () { reject(r.error || new Error('IndexedDB add failed')); };
      tx.onerror = function () { reject(tx.error || new Error('IndexedDB tx failed')); };
    });
  }

  async function listPending() {
    var db = await openDB();
    return new Promise(function (resolve, reject) {
      var r = db.transaction(STORE, 'readonly').objectStore(STORE).getAll();
      r.onsuccess = function () { resolve(r.result || []); };
      r.onerror = function () { reject(r.error); };
    });
  }

  async function removePending(id) {
    var db = await openDB();
    return new Promise(function (resolve, reject) {
      var tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).delete(id);
      tx.oncomplete = function () { resolve(); };
      tx.onerror = function () { reject(tx.error); };
    });
  }

  async function cacheAccounts(list) {
    if (!list || !list.length) return;
    var db = await openDB();
    return new Promise(function (resolve, reject) {
      var tx = db.transaction(ACC_STORE, 'readwrite');
      var store = tx.objectStore(ACC_STORE);
      list.forEach(function (a) { store.put(a); });
      tx.oncomplete = function () { resolve(); };
      tx.onerror = function () { reject(tx.error); };
    });
  }

  async function getCachedAccounts() {
    var db = await openDB();
    return new Promise(function (resolve, reject) {
      var r = db.transaction(ACC_STORE, 'readonly').objectStore(ACC_STORE).getAll();
      r.onsuccess = function () { resolve(r.result || []); };
      r.onerror = function () { reject(r.error); };
    });
  }

  function fileToBase64(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        resolve({
          name: file.name,
          type: file.type,
          size: file.size,
          data: reader.result
        });
      };
      reader.onerror = function () { reject(reader.error || new Error('Lecture fichier')); };
      reader.readAsDataURL(file);
    });
  }

  function todayJjMmAa() {
    var t = new Date();
    var dd = String(t.getDate()).padStart(2, '0');
    var mm = String(t.getMonth() + 1).padStart(2, '0');
    var yy = String(t.getFullYear()).slice(-2);
    return dd + '/' + mm + '/' + yy;
  }

  function unformatAmount(val) {
    if (val == null) return '';
    return String(val).replace(/\s/g, '').replace(/,/g, '.').replace(/[^\d.-]/g, '');
  }

  function isOffline() {
    return appOffline || (typeof navigator !== 'undefined' && navigator.onLine === false);
  }

  function fingerprintPayload(payload) {
    try {
      var key = {
        kind: payload.kind,
        description: payload.description || '',
        amount: payload.amount || '',
        name: payload.name || '',
        credit_account_id: payload.credit_account_id || '',
        debit_account_id: payload.debit_account_id || '',
        lines: (payload.lines || []).map(function (l) {
          return [l.account_id, l.description, l.quantity, l.occurrence, l.unit_cost].join('|');
        }).join(';')
      };
      return JSON.stringify(key);
    } catch (e) {
      return String(Date.now());
    }
  }

  function ensureToastEl() {
    var el = document.getElementById('rrmOfflineToast');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'rrmOfflineToast';
    el.setAttribute('role', 'status');
    el.style.cssText = [
      'position:fixed', 'left:50%', 'bottom:72px', 'transform:translateX(-50%)',
      'z-index:99999', 'max-width:92vw', 'width:420px',
      'background:#111', 'color:#fff', 'padding:14px 18px', 'border-radius:10px',
      'font:14px/1.4 system-ui,sans-serif', 'box-shadow:0 8px 24px rgba(0,0,0,.25)',
      'display:none', 'text-align:center'
    ].join(';');
    document.body.appendChild(el);
    return el;
  }

  function showToast(msg, kind) {
    var el = ensureToastEl();
    el.style.background = kind === 'error' ? '#c0392b' : (kind === 'ok' ? '#1e7e34' : '#111');
    el.textContent = msg;
    el.style.display = 'block';
    clearTimeout(el._hideTimer);
    if (kind !== 'progress') {
      el._hideTimer = setTimeout(function () { el.style.display = 'none'; }, 5000);
    }
    try { console.log('[offline]', kind || 'info', msg); } catch (e) {}
  }

  function hideToast() {
    var el = document.getElementById('rrmOfflineToast');
    if (el) el.style.display = 'none';
  }

  async function syncAll() {
    if (isOffline()) return { ok: 0, fail: 0, skipped: true };
    if (syncInProgress) return { ok: 0, fail: 0, skipped: true };
    syncInProgress = true;
    try {
      var pending;
      try {
        pending = await listPending();
      } catch (e) {
        console.warn('[offline] listPending', e);
        return { ok: 0, fail: 0 };
      }
      // Dédupliquer la file par fingerprint avant envoi
      var seen = {};
      var unique = [];
      for (var i = 0; i < pending.length; i++) {
        var item = pending[i];
        var fp = item.fingerprint || ('id:' + item.id);
        if (seen[fp]) {
          try { await removePending(item.id); } catch (e) {}
          continue;
        }
        seen[fp] = true;
        unique.push(item);
      }
      var ok = 0, fail = 0;
      for (var j = 0; j < unique.length; j++) {
        var it = unique[j];
        try {
          var kind = it.kind || 'journal';
          var url = kind === 'budget' ? '/budgets/api/offline-sync' : '/journal/api/offline-sync';
          var res = await fetch(url, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin',
            body: JSON.stringify(it)
          });
          if (res.ok) {
            await removePending(it.id);
            ok++;
          } else {
            fail++;
            console.warn('[offline] sync fail', kind, it.id, await res.text());
          }
        } catch (e) {
          fail++;
          console.warn('[offline] sync error', e);
        }
      }
      updateBadge();
      return { ok: ok, fail: fail };
    } finally {
      syncInProgress = false;
    }
  }

  async function updateBadge() {
    var el = document.getElementById('offlineQueueBadge');
    if (!el) return;
    try {
      var list = await listPending();
      if (list.length) {
        el.style.display = '';
        el.textContent = String(list.length);
        el.title = list.length + ' élément(s) en attente de synchro';
      } else {
        el.style.display = 'none';
      }
    } catch (e) { /* ignore */ }
  }

  async function saveJournalOffline(form) {
    showToast('Enregistrement local en cours…', 'progress');
    var fd = new FormData(form);
    var files = form.querySelector('input[type=file]');
    var attachments = [];
    if (files && files.files && files.files.length) {
      for (var i = 0; i < files.files.length; i++) {
        var f = files.files[i];
        if (f.size > 4 * 1024 * 1024) {
          showToast('Fichier trop volumineux (max 4 Mo) : ' + f.name, 'error');
          continue;
        }
        try {
          attachments.push(await withTimeout(fileToBase64(f), 15000, 'Lecture ' + f.name));
        } catch (err) {
          showToast('Impossible de lire le fichier : ' + f.name, 'error');
        }
      }
    }
    var amount = unformatAmount(fd.get('amount') || '');
    var payload = {
      kind: 'journal',
      entry_date: (fd.get('entry_date') || '').trim() || todayJjMmAa(),
      description: (fd.get('description') || '').trim(),
      credit_account_code: fd.get('credit_account_code') || '',
      debit_account_code: fd.get('debit_account_code') || '',
      credit_account_id: fd.get('credit_account_id') || '',
      debit_account_id: fd.get('debit_account_id') || '',
      amount: amount,
      currency: fd.get('currency') || 'MGA',
      attachments: attachments
    };
    if (!payload.description || !payload.amount) {
      showToast('Description et montant obligatoires.', 'error');
      return false;
    }
    if (!payload.credit_account_id && !payload.credit_account_code) {
      showToast('Compte crédit obligatoire.', 'error');
      return false;
    }
    if (!payload.debit_account_id && !payload.debit_account_code) {
      showToast('Compte débit obligatoire.', 'error');
      return false;
    }
    payload.fingerprint = fingerprintPayload(payload);
    // Anti-doublon local (même contenu dans les 15 s)
    if (payload.fingerprint === lastSaveFingerprint && (Date.now() - lastSaveAt) < 15000) {
      showToast('Déjà enregistré localement (doublon ignoré).', 'ok');
      return true;
    }
    await withTimeout(addPending(payload), 8000, 'Sauvegarde locale');
    lastSaveFingerprint = payload.fingerprint;
    lastSaveAt = Date.now();
    await updateBadge();
    showToast('Écriture enregistrée localement. Synchronisation à la reconnexion.', 'ok');
    try {
      form.reset();
      var de = document.getElementById('entry_date');
      if (de) de.value = todayJjMmAa();
      var aw = document.getElementById('amount_words');
      if (aw) aw.textContent = '';
      var cd = document.getElementById('credit_desc');
      if (cd) cd.textContent = '';
      var dd = document.getElementById('debit_desc');
      if (dd) dd.textContent = '';
    } catch (e) {}
    return true;
  }

  async function saveBudgetOffline(form) {
    showToast('Enregistrement local en cours…', 'progress');
    var fd = new FormData(form);
    var descs = fd.getAll('line_description');
    var qtys = fd.getAll('line_quantity');
    var qtyUnits = fd.getAll('line_quantity_unit');
    var occs = fd.getAll('line_occurrence');
    var occUnits = fd.getAll('line_occurrence_unit');
    var costs = fd.getAll('line_unit_cost');
    var accIds = fd.getAll('line_account_id');
    var lines = [];
    for (var i = 0; i < descs.length; i++) {
      var desc = (descs[i] || '').trim();
      if (!desc) continue;
      var aid = accIds[i] || '';
      if (!aid) continue;
      lines.push({
        description: desc,
        quantity: qtys[i] || '1',
        quantity_unit: qtyUnits[i] || '',
        occurrence: occs[i] || '1',
        occurrence_unit: occUnits[i] || '',
        unit_cost: costs[i] || '0',
        account_id: aid
      });
    }
    var name = (fd.get('name') || '').trim();
    if (!name) {
      var bt = document.getElementById('budget_title');
      if (bt) name = (bt.value || '').trim();
    }
    if (!name) {
      var lt = document.getElementById('lines-title');
      if (lt) name = (lt.textContent || '').trim();
    }
    if (!name || name === 'Budget' || name === 'Nouveau budget') {
      showToast('Le titre du budget est obligatoire (ouvrez En-tête).', 'error');
      return false;
    }
    if (!lines.length) {
      showToast('Au moins une ligne avec compte et description est requise.', 'error');
      return false;
    }
    var payload = {
      kind: 'budget',
      name: name,
      start_date: fd.get('start_date') || '',
      end_date: fd.get('end_date') || '',
      currency: fd.get('currency') || 'MGA',
      assigned_to: fd.getAll('assigned_to'),
      cc_to: fd.getAll('cc_to'),
      cost_center_id: fd.get('cost_center_id') || '',
      lines: lines,
      budget_id: form.dataset.budgetId || null
    };
    payload.fingerprint = fingerprintPayload(payload);
    if (payload.fingerprint === lastSaveFingerprint && (Date.now() - lastSaveAt) < 15000) {
      showToast('Déjà enregistré localement (doublon ignoré).', 'ok');
      return true;
    }
    await withTimeout(addPending(payload), 8000, 'Sauvegarde locale');
    lastSaveFingerprint = payload.fingerprint;
    lastSaveAt = Date.now();
    await updateBadge();
    showToast('Budget enregistré localement. Synchronisation à la reconnexion.', 'ok');
    return true;
  }

  function blockEvent(e) {
    if (!e) return;
    e.preventDefault();
    e.stopPropagation();
    if (typeof e.stopImmediatePropagation === 'function') e.stopImmediatePropagation();
  }

  function handleOfflineSubmit(form, kind, e) {
    blockEvent(e);
    if (saveInProgress) {
      showToast('Enregistrement déjà en cours…', 'progress');
      return false;
    }
    form.noValidate = true;
    saveInProgress = true;
    showToast('Enregistrement local en cours…', 'progress');
    var p = kind === 'budget' ? saveBudgetOffline(form) : saveJournalOffline(form);
    p.then(function () {
      saveInProgress = false;
    }).catch(function (err) {
      saveInProgress = false;
      console.error('[offline]', kind, err);
      showToast('Erreur enregistrement local : ' + (err && err.message ? err.message : String(err)), 'error');
    });
    return false;
  }

  function attachJournal(form) {
    if (!form || form.dataset.offlineBound === '1') return;
    form.dataset.offlineBound = '1';
    form.setAttribute('novalidate', 'novalidate');

    // Un seul point d'entrée : submit (novalidate hors ligne => toujours déclenché)
    form.addEventListener('submit', function (e) {
      if (!isOffline()) {
        syncAll();
        return;
      }
      handleOfflineSubmit(form, 'journal', e);
    }, true);
  }

  function attachBudget(form) {
    if (!form || form.dataset.offlineBound === '1') return;
    form.dataset.offlineBound = '1';
    form.setAttribute('novalidate', 'novalidate');

    form.addEventListener('submit', function (e) {
      if (!isOffline()) {
        syncAll();
        return;
      }
      handleOfflineSubmit(form, 'budget', e);
    }, true);
  }

  function applyOfflineFormFlags() {
    var offline = isOffline();
    ['entry-form', 'budget-form'].forEach(function (id) {
      var f = document.getElementById(id);
      if (!f) return;
      if (offline) {
        f.setAttribute('novalidate', 'novalidate');
        f.noValidate = true;
      }
    });
  }

  function initForms() {
    var j = document.getElementById('entry-form');
    if (j) attachJournal(j);
    var b = document.getElementById('budget-form');
    if (b) attachBudget(b);
    applyOfflineFormFlags();
  }

  function boot() {
    appOffline = (typeof navigator !== 'undefined' && navigator.onLine === false);
    initForms();
    if (global.RRM_ACCOUNTS_CACHE) {
      cacheAccounts(global.RRM_ACCOUNTS_CACHE).catch(function () {});
    }
    updateBadge();
    if (!isOffline()) syncAll();
    try { console.log('[offline] v8 ready, offline=', isOffline()); } catch (e) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  setTimeout(initForms, 400);
  setTimeout(initForms, 1200);

  // Pas de délégation document : elle doublonnait avec le submit

  window.addEventListener('online', function () {
    appOffline = false;
    applyOfflineFormFlags();
    hideToast();
    // Une seule synchro, légère temporisation pour laisser le réseau se stabiliser
    setTimeout(function () {
      syncAll().then(function (r) {
        if (r && r.ok) {
          showToast(r.ok + ' élément(s) synchronisé(s)', 'ok');
          var el = document.getElementById('netStatus');
          if (el) {
            el.className = 'net-status show online';
            el.innerHTML = '<i class="bi bi-cloud-upload"></i> ' + r.ok + ' élément(s) synchronisé(s)';
            setTimeout(function () { el.classList.remove('show'); }, 4000);
          }
        }
      });
    }, 400);
  });

  window.addEventListener('offline', function () {
    appOffline = true;
    applyOfflineFormFlags();
  });

  global.RRMOffline = {
    addPending: addPending,
    listPending: listPending,
    syncAll: syncAll,
    updateBadge: updateBadge,
    cacheAccounts: cacheAccounts,
    getCachedAccounts: getCachedAccounts,
    saveJournalOffline: saveJournalOffline,
    saveBudgetOffline: saveBudgetOffline,
    isOffline: isOffline,
    showToast: showToast
  };
})(window);
