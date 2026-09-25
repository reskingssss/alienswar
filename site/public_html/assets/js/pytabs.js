/* MavelyLink admin — ADD Tabs *Py in Your Tool (v7.0.0)
 *
 * A separate file so assets/js/admin.js is not touched. Nothing here is
 * required for the page to work: with JavaScript off you still get a plain
 * code box, the numeric Order field, a server-rendered size verdict and a
 * selectable prompt. This only makes those four things nicer.
 *
 * No dependencies, no CDN — the rest of this dashboard ships its own assets
 * and this follows that.
 */
(function () {
  'use strict';

  // =====================================================================
  // 1. Python syntax highlighting
  //
  // A small hand-written tokenizer rather than a highlighting library: the
  // whole job is one language in one textarea, and pulling in a 200 KB
  // editor for it would be the wrong trade. It is deliberately conservative
  // — anything it is not sure about is left in the default colour, which is
  // readable, so a tokenizer gap shows up as "not coloured" and never as
  // "wrong text".
  // =====================================================================

  var KEYWORDS = ('False None True and as assert async await break class continue def del '
    + 'elif else except finally for from global if import in is lambda nonlocal not or pass '
    + 'raise return try while with yield').split(' ');
  var BUILTINS = ('abs all any bool bytes callable chr dict dir enumerate filter float format '
    + 'getattr hasattr hash hex id input int isinstance issubclass len list map max min next '
    + 'object open ord print range repr reversed round set setattr sorted str sum super tuple '
    + 'type zip self cls Exception ValueError TypeError KeyError IndexError RuntimeError '
    + 'AttributeError OSError ImportError').split(' ');

  var KW = {}, BI = {};
  KEYWORDS.forEach(function (k) { KW[k] = 1; });
  BUILTINS.forEach(function (k) { BI[k] = 1; });

  function esc(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function span(cls, text) {
    return '<span class="' + cls + '">' + esc(text) + '</span>';
  }

  /* Walks the source once, character by character, emitting HTML. Handles
     triple-quoted strings, single-quoted strings with escapes and prefixes
     (r, b, f, u and pairs of them), comments, numbers, decorators and
     identifiers. Anything else falls through as plain text. */
  function highlight(src) {
    var out = '';
    var i = 0;
    var n = src.length;
    var atLineStart = true;

    while (i < n) {
      var c = src[i];

      // --- comment ---------------------------------------------------
      if (c === '#') {
        var end = src.indexOf('\n', i);
        if (end === -1) { end = n; }
        out += span('t-com', src.slice(i, end));
        i = end;
        continue;
      }

      // --- string (with optional prefix) -----------------------------
      var prefixMatch = /^(?:[rRbBuUfF]{0,2})('''|"""|'|")/.exec(src.slice(i, i + 5));
      if (prefixMatch && (c === '"' || c === "'" || /[rRbBuUfF]/.test(c))) {
        // make sure a prefix letter is really a prefix and not an identifier
        var pfxLen = prefixMatch[0].length - prefixMatch[1].length;
        var before = i > 0 ? src[i - 1] : '';
        if (pfxLen === 0 || !/[A-Za-z0-9_]/.test(before)) {
          var quote = prefixMatch[1];
          var start = i;
          var j = i + prefixMatch[0].length;
          var raw = /[rR]/.test(prefixMatch[0].slice(0, pfxLen));
          while (j < n) {
            if (!raw && src[j] === '\\') { j += 2; continue; }
            if (src.substr(j, quote.length) === quote) { j += quote.length; break; }
            // a single-quoted string cannot span a newline
            if (quote.length === 1 && src[j] === '\n') { break; }
            j++;
          }
          out += span('t-str', src.slice(start, Math.min(j, n)));
          i = Math.min(j, n);
          atLineStart = false;
          continue;
        }
      }

      // --- decorator -------------------------------------------------
      if (c === '@' && atLineStart) {
        var dEnd = i + 1;
        while (dEnd < n && /[A-Za-z0-9_.]/.test(src[dEnd])) { dEnd++; }
        out += span('t-dec', src.slice(i, dEnd));
        i = dEnd;
        atLineStart = false;
        continue;
      }

      // --- number ----------------------------------------------------
      if (/[0-9]/.test(c) && !/[A-Za-z0-9_.]/.test(i > 0 ? src[i - 1] : ' ')) {
        var numMatch = /^(?:0[xXbBoO][0-9a-fA-F_]+|[0-9][0-9_]*(?:\.[0-9_]*)?(?:[eE][+-]?[0-9]+)?j?)/
          .exec(src.slice(i));
        if (numMatch) {
          out += span('t-num', numMatch[0]);
          i += numMatch[0].length;
          atLineStart = false;
          continue;
        }
      }

      // --- identifier / keyword --------------------------------------
      if (/[A-Za-z_]/.test(c)) {
        var wEnd = i;
        while (wEnd < n && /[A-Za-z0-9_]/.test(src[wEnd])) { wEnd++; }
        var word = src.slice(i, wEnd);
        if (KW[word]) {
          out += span('t-kw', word);
          // the name right after def/class is the definition itself
          if (word === 'def' || word === 'class') {
            var rest = /^(\s+)([A-Za-z_]\w*)/.exec(src.slice(wEnd));
            if (rest) {
              out += esc(rest[1]) + span('t-def', rest[2]);
              wEnd += rest[0].length;
            }
          }
        } else if (BI[word]) {
          out += span('t-bi', word);
        } else {
          out += esc(word);
        }
        i = wEnd;
        atLineStart = false;
        continue;
      }

      // --- anything else ---------------------------------------------
      out += esc(c);
      atLineStart = (c === '\n');
      i++;
    }
    return out;
  }

  document.querySelectorAll('[data-pytabs-editor]').forEach(function (wrap) {
    var ta = wrap.querySelector('textarea.code');
    var pre = wrap.querySelector('.code-underlay');
    if (!ta || !pre) { return; }
    wrap.classList.add('is-lit');

    var paint = function () {
      // the trailing newline keeps the last line visible while typing at the
      // very end of the file
      pre.innerHTML = highlight(ta.value + '\n');
      pre.scrollTop = ta.scrollTop;
      pre.scrollLeft = ta.scrollLeft;
    };
    var sync = function () {
      pre.scrollTop = ta.scrollTop;
      pre.scrollLeft = ta.scrollLeft;
    };

    ta.addEventListener('input', paint);
    ta.addEventListener('scroll', sync);
    window.addEventListener('resize', sync);

    // Tab inserts four spaces. admin.js already does two for textarea.code
    // generally; Python wants four, and this listener runs on the same
    // element, so preventDefault here settles it. Shift+Tab outdents.
    ta.addEventListener('keydown', function (e) {
      if (e.key !== 'Tab') { return; }
      e.preventDefault();
      e.stopPropagation();
      var s = ta.selectionStart, t = ta.selectionEnd, v = ta.value;
      if (e.shiftKey) {
        var lineStart = v.lastIndexOf('\n', s - 1) + 1;
        if (v.slice(lineStart, lineStart + 4) === '    ') {
          ta.value = v.slice(0, lineStart) + v.slice(lineStart + 4);
          ta.selectionStart = ta.selectionEnd = Math.max(lineStart, s - 4);
        }
      } else {
        ta.value = v.slice(0, s) + '    ' + v.slice(t);
        ta.selectionStart = ta.selectionEnd = s + 4;
      }
      paint();
    }, true);

    paint();
  });

  // =====================================================================
  // 2. Drag-to-reorder
  //
  // Writes the resulting id order into the hidden field the form already
  // posts, so the server handler is the same one the numeric Order field
  // uses. Nothing is saved until the button is pressed.
  // =====================================================================
  var table = document.getElementById('tab-table');
  var idsField = document.getElementById('order-ids');
  if (table && idsField) {
    var body = table.tBodies[0];
    var dragged = null;

    var writeOrder = function () {
      var ids = [];
      Array.prototype.forEach.call(body.rows, function (r) {
        if (r.dataset.id) { ids.push(r.dataset.id); }
      });
      idsField.value = ids.join(',');
    };

    var clearMarks = function () {
      Array.prototype.forEach.call(body.rows, function (r) {
        r.classList.remove('drop-before', 'drop-after');
      });
    };

    body.addEventListener('dragstart', function (e) {
      var row = e.target.closest('tr');
      if (!row) { return; }
      dragged = row;
      row.classList.add('dragging');
      try {
        e.dataTransfer.effectAllowed = 'move';
        // Firefox refuses to start a drag without payload
        e.dataTransfer.setData('text/plain', row.dataset.id || '');
      } catch (err) { /* older browsers: the drag still works */ }
    });

    body.addEventListener('dragover', function (e) {
      if (!dragged) { return; }
      var row = e.target.closest('tr');
      if (!row || row === dragged) { return; }
      e.preventDefault();
      var box = row.getBoundingClientRect();
      var after = (e.clientY - box.top) > box.height / 2;
      clearMarks();
      row.classList.add(after ? 'drop-after' : 'drop-before');
    });

    body.addEventListener('drop', function (e) {
      if (!dragged) { return; }
      var row = e.target.closest('tr');
      if (!row || row === dragged) { return; }
      e.preventDefault();
      var box = row.getBoundingClientRect();
      var after = (e.clientY - box.top) > box.height / 2;
      row.parentNode.insertBefore(dragged, after ? row.nextSibling : row);
      clearMarks();
      writeOrder();
    });

    body.addEventListener('dragend', function () {
      if (dragged) { dragged.classList.remove('dragging'); }
      dragged = null;
      clearMarks();
      writeOrder();
    });

    writeOrder();
  }

  // =====================================================================
  // 3. Live size fitter
  //
  // Draws the declared ui_width/ui_height against the tool's real tab
  // canvas. The server renders the same verdict on load, so this only keeps
  // it live while the numbers are being typed.
  // =====================================================================
  var fitter = document.getElementById('fitter');
  var wIn = document.getElementById('ui-w');
  var hIn = document.getElementById('ui-h');
  if (fitter && wIn && hIn) {
    var canvasW = parseInt(fitter.dataset.canvasW, 10);
    var canvasH = parseInt(fitter.dataset.canvasH, 10);
    var minW = parseInt(fitter.dataset.minW, 10);
    var minH = parseInt(fitter.dataset.minH, 10);
    var advW = parseInt(fitter.dataset.advisedW, 10);
    var advH = parseInt(fitter.dataset.advisedH, 10);
    var minBox = fitter.querySelector('.fitter-min');
    var scriptBox = fitter.querySelector('.fitter-script');
    var note = document.getElementById('fitter-note');

    var pct = function (v, of) { return Math.max(2, Math.min(100, (v / of) * 100)) + '%'; };

    var render = function () {
      var w = parseInt(wIn.value, 10) || advW;
      var h = parseInt(hIn.value, 10) || advH;

      minBox.style.width = pct(minW, canvasW);
      minBox.style.height = pct(minH, canvasH);
      scriptBox.style.width = pct(w, canvasW);
      scriptBox.style.height = pct(h, canvasH);

      var problems = [];
      if (w > canvasW) {
        problems.push('Width ' + w + ' px is wider than the tab canvas (' + canvasW
          + ' px at the default window). The tab will scroll sideways.');
      } else if (w > minW) {
        problems.push('Width ' + w + ' px fits the default window but not the smallest allowed one ('
          + minW + ' px).');
      }
      if (h > canvasH) {
        problems.push('Height ' + h + ' px is taller than the tab canvas (' + canvasH
          + ' px at the default window). The tab will scroll vertically.');
      } else if (h > minH) {
        problems.push('Height ' + h + ' px fits the default window but not the smallest allowed one ('
          + minH + ' px).');
      }

      scriptBox.classList.toggle('is-over', w > canvasW || h > canvasH);

      var html = '';
      if (!problems.length) {
        html = '<p class="chip chip-good"><span aria-hidden="true">●</span> '
          + 'Fits the tab canvas at every supported window size.</p>';
      } else {
        problems.forEach(function (p) {
          html += '<p class="chip chip-warn"><span aria-hidden="true">▲</span> ' + esc(p) + '</p>';
        });
        html += '<p class="muted small">Recommended: <b>' + advW + ' × ' + advH + '</b>. '
          + 'Larger still works — the container scrolls — but the user has to scroll to reach it. '
          + '<button type="button" class="btn btn-sm" id="use-advised">Use recommended</button></p>';
      }
      note.innerHTML = html;

      var use = document.getElementById('use-advised');
      if (use) {
        use.addEventListener('click', function () {
          wIn.value = advW;
          hIn.value = advH;
          render();
        });
      }
    };

    wIn.addEventListener('input', render);
    hIn.addEventListener('input', render);
    render();
  }

  // =====================================================================
  // 4. Copy the AI prompt
  //
  // admin.js copies from a data-copy attribute; the prompt is several KB and
  // does not belong in an attribute, so this copies from an element instead.
  // =====================================================================
  document.querySelectorAll('[data-copy-target]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var el = document.querySelector(btn.getAttribute('data-copy-target'));
      if (!el) { return; }
      var text = el.textContent;
      var done = function () {
        var label = btn.textContent;
        btn.textContent = 'Copied';
        btn.classList.add('is-copied');
        setTimeout(function () {
          btn.textContent = label;
          btn.classList.remove('is-copied');
        }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () { select(el); });
      } else {
        select(el);
      }
    });
  });

  /* Clipboard API unavailable or refused (it needs HTTPS): select the text
     so Ctrl+C still works rather than failing silently. */
  function select(el) {
    try {
      var range = document.createRange();
      range.selectNodeContents(el);
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    } catch (err) { /* nothing more we can do */ }
  }
})();
