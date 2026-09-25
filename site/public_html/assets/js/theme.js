/* MavelyLink v8: light / dark theme. Loaded in <head> (tiny, same origin) so
   the saved choice is applied before the first paint. Without a saved choice
   the page follows the system setting. */
(function () {
  var root = document.documentElement, KEY = 'mvl-theme';
  function saved() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function current() {
    var t = root.getAttribute('data-theme');
    if (t === 'dark' || t === 'light') { return t; }
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  var s = saved();
  if (s === 'dark' || s === 'light') { root.setAttribute('data-theme', s); }
  function sync() {
    var dark = current() === 'dark', btns = document.querySelectorAll('[data-theme-toggle]');
    for (var i = 0; i < btns.length; i++) {
      btns[i].setAttribute('aria-pressed', dark ? 'true' : 'false');
      btns[i].setAttribute('title', dark ? 'Switch to light mode' : 'Switch to dark mode');
    }
  }
  document.addEventListener('click', function (ev) {
    var b = ev.target && ev.target.closest ? ev.target.closest('[data-theme-toggle]') : null;
    if (!b) { return; }
    var next = current() === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem(KEY, next); } catch (e) { /* private mode */ }
    sync();
  });
  document.addEventListener('DOMContentLoaded', sync);
})();
