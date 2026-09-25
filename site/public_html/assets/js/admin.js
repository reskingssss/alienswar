// MavelyLink admin v7: confirmation dialogs, copy buttons, unsaved-edit
// guard, and small live previews. Works without JavaScript too (every
// form still submits; confirmations fall back to the browser prompt).
(function () {
  'use strict';

  // ---- confirmation for sensitive actions -----------------------------
  var dlg = document.getElementById('confirm-dialog');
  function askConfirm(message, onYes) {
    if (!dlg || typeof dlg.showModal !== 'function') {
      if (window.confirm(message)) { onYes(); }
      return;
    }
    document.getElementById('confirm-text').textContent = message;
    dlg.returnValue = '';
    dlg.showModal();
    document.getElementById('confirm-ok').focus();
    dlg.addEventListener('close', function handler() {
      dlg.removeEventListener('close', handler);
      if (dlg.returnValue === 'ok') { onYes(); }
    });
  }
  document.addEventListener('click', function (e) {
    var el = e.target.closest('[data-confirm]');
    if (!el || el.dataset.confirmed === '1') { return; }
    var form = el.form || el.closest('form');
    if (!form) { return; }
    e.preventDefault();
    askConfirm(el.getAttribute('data-confirm'), function () {
      el.dataset.confirmed = '1';
      if (el.name) {
        var h = document.createElement('input');
        h.type = 'hidden'; h.name = el.name; h.value = el.value;
        form.appendChild(h);
      }
      form.submit();
    });
  });
  // select-driven actions (licence row menu) confirm the chosen option
  document.addEventListener('submit', function (e) {
    var form = e.target;
    var sel = form.querySelector('select[data-confirm-options]');
    if (!sel || form.dataset.confirmed === '1') { return; }
    var opt = sel.options[sel.selectedIndex];
    var msg = opt && opt.getAttribute('data-confirm');
    if (!msg) { return; }
    e.preventDefault();
    askConfirm(msg, function () { form.dataset.confirmed = '1'; form.submit(); });
  });

  // ---- copy to clipboard ---------------------------------------------
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-copy]');
    if (!b) { return; }
    e.preventDefault();
    var text = b.getAttribute('data-copy');
    var done = function () {
      var old = b.getAttribute('aria-label') || 'Copy';
      b.setAttribute('aria-label', 'Copied');
      b.title = 'Copied';
      setTimeout(function () { b.setAttribute('aria-label', old); b.title = old; }, 1500);
    };
    if (navigator.clipboard) { navigator.clipboard.writeText(text).then(done, function () {}); }
  });

  // ---- keep long edits from being lost ---------------------------------
  document.querySelectorAll('form[data-guard]').forEach(function (form) {
    var dirty = false;
    form.addEventListener('input', function () { dirty = true; });
    form.addEventListener('submit', function () { dirty = false; });
    window.addEventListener('beforeunload', function (e) {
      if (dirty) { e.preventDefault(); e.returnValue = ''; }
    });
  });
  // Tab inserts two spaces in code editors instead of leaving the field.
  document.querySelectorAll('textarea.code').forEach(function (ta) {
    ta.addEventListener('keydown', function (e) {
      if (e.key !== 'Tab' || e.shiftKey) { return; }
      e.preventDefault();
      var s = ta.selectionStart, t = ta.selectionEnd;
      ta.value = ta.value.slice(0, s) + '  ' + ta.value.slice(t);
      ta.selectionStart = ta.selectionEnd = s + 2;
    });
  });

  // ---- live price preview on the Pricing plans page --------------------
  document.querySelectorAll('[data-price-form]').forEach(function (form) {
    var out = form.querySelector('[data-price-preview]');
    if (!out) { return; }
    var render = function () {
      var cur = form.querySelector('[name=current_price]').value.trim();
      var prev = form.querySelector('[name=previous_price]').value.trim();
      var ccy = form.querySelector('[name=currency]').value.trim().toUpperCase() || 'USD';
      var days = form.querySelector('[name=period_days]').value.trim();
      var sym = ccy === 'USD' ? '$' : (ccy + ' ');
      out.querySelector('.was').textContent = prev ? sym + Number(prev).toFixed(2) : '';
      out.querySelector('.now').textContent = sym + (cur ? Number(cur).toFixed(2) : '0.00');
      out.querySelector('.per').textContent = Number(days) > 0 ? 'per ' + days + ' days' : 'no expiry';
    };
    form.addEventListener('input', render);
    render();
  });

  // ---- coupon form: suggested code follows the chosen percentage -------
  var pct = document.querySelectorAll('input[name=percent]');
  var codeBox = document.querySelector('input[name=code][data-suggest]');
  pct.forEach(function (r) {
    r.addEventListener('change', function () {
      if (codeBox && !codeBox.value) { codeBox.placeholder = 'Leave empty for SAVE' + r.value + '-XXXXXX'; }
    });
  });
})();
