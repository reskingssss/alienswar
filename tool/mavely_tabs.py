#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MavelyLink 7.0.0 — server-controlled Python tabs for the desktop tool.

WHAT THIS MODULE IS
-------------------
The tool ships a tab HOST. The tab CONTENT is a Python module that lives on
the website, is delivered at runtime to installations whose plan is entitled
to it, and is executed from memory. Nothing executable for these tabs is in
the distributed build, so reading the local files of a cracked copy yields a
host with nothing to host.

PYTHON 3.7.7
------------
Everything here parses and runs on 3.7.7 with the standard library only:
no walrus, no positional-only parameters, no match, no builtin generics, no
`X | Y` unions, no f-string `{x=}`. `%`-formatting is used throughout to
match the rest of this codebase.

FAIL-SOFT IS THE RULE
---------------------
This module must never be able to stop the tool starting or stop a profile
being generated. Every entry point is wrapped, every failure degrades to
"fewer tabs" rather than "no tool", and a server that cannot be reached
simply means the remote tabs come from the last verified cache or are absent
for this session. The existing Profiles and Invite tabs are never touched.

HOW A MODULE IS TRUSTED
-----------------------
Three independent checks, all of which must pass before anything runs:

  1. The Ed25519 GRANT. The server signs (slug, version, sha256, device,
     plan) with the licence signing key. We verify it against the public key
     already embedded in license_client. A fake server (hosts file, DNS,
     proxy) cannot mint one, and neither can someone holding only a stolen
     copy of the database.
  2. The HMAC TAG over the ciphertext (encrypt-then-MAC). Detects any
     modification of the payload in flight or in the cache.
  3. The SHA-256 of the decrypted bytes against the value inside the signed
     grant. Ties the bytes we are about to compile to the bytes the server
     signed.

Any mismatch and the module is discarded and the tab shows an error state.
We never "try anyway".

WHAT THE ENCRYPTION IS AND IS NOT
---------------------------------
The envelope is HKDF-SHA256 for key derivation, HMAC-SHA256 in counter mode
for the keystream, and encrypt-then-MAC. AES-GCM would be the usual choice,
but Python 3.7's standard library has no AES at all and bundling a crypto
library is out of scope here, so this construction — which is standard, and
expressible in both PHP and stdlib Python — is used instead.

It keeps the cached payload unreadable by anything that is not this tool on
this machine, and it makes tampering detectable. It does NOT hide the module
from someone who attaches a debugger to their own copy after decryption.
Nothing running on someone else's computer can do that. The protection that
actually holds is that the server never sends the module at all to an
installation whose plan is not entitled to it.
"""

import base64
import hashlib
import hmac
import os
import sys
import threading
import types

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:                                    # pragma: no cover
    tk = None
    ttk = None

try:
    import license_client as _license
except Exception:                                    # pragma: no cover
    _license = None


# The container the host guarantees. These match includes/tabs.php exactly;
# the admin size-fitter draws the same numbers, so the dashboard preview and
# the tool cannot drift apart.
TAB_CANVAS_W = 1024
TAB_CANVAS_H = 425
TAB_CANVAS_MIN_W = 964
TAB_CANVAS_MIN_H = 360
TAB_ADVISED_W = 960
TAB_ADVISED_H = 340


# ----------------------------------------------------------------------
# key derivation and the sealed envelope
# ----------------------------------------------------------------------
def _hkdf_extract(salt, ikm):
    """RFC 5869 extract. hashlib has no HKDF on 3.7, so it is spelled out."""
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def _hkdf_expand(prk, info, length):
    """RFC 5869 expand, SHA-256."""
    out = b''
    block = b''
    counter = 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        out += block
        counter += 1
    return out[:length]


def _hkdf(ikm, salt, info, length=32):
    return _hkdf_expand(_hkdf_extract(salt, ikm), info, length)


def _ctr_xor(key, data):
    """HMAC-SHA256 counter-mode keystream XORed over `data`.

    Returns a bytearray so the caller can zero it after use. The counter is
    a big-endian 32-bit block index, matching tab_ctr_xor() in tabs.php.
    """
    out = bytearray(data)
    n = len(out)
    pos = 0
    block = 0
    while pos < n:
        ks = hmac.new(key, block.to_bytes(4, 'big'), hashlib.sha256).digest()
        take = min(32, n - pos)
        for i in range(take):
            out[pos + i] ^= ks[i]
        pos += take
        block += 1
    return out


def _ikm(device, serial, slug, version):
    """Must match tab_ikm() in includes/tabs.php byte for byte."""
    parts = [device, serial, slug, str(int(version)), 'mvl-tab/v1']
    return '\x1f'.join(parts).encode('utf-8')


def unseal(envelope, device, serial):
    """Verify and decrypt one sealed module.

    Returns (source_bytes_bytearray, meta_dict) on success, or (None, reason)
    on any failure. The caller must zero the bytearray when it is done.
    """
    if not isinstance(envelope, dict):
        return None, 'malformed payload'

    slug = str(envelope.get('slug', ''))
    version = int(envelope.get('version', 0) or 0)
    grant = str(envelope.get('grant', ''))
    if not slug or not grant:
        return None, 'payload is missing its signature'

    # ---- 1. the Ed25519 grant ----------------------------------------
    # _verify_token checks the signature against the public key compiled
    # into the build, and checks `exp`. A little leeway is allowed so a
    # payload cached minutes before a clock adjustment still verifies.
    if _license is None:
        return None, 'licensing module unavailable'
    try:
        claims = _license._verify_token(grant, 300)
    except Exception:
        claims = {}
    if not claims:
        return None, 'signature did not verify (expired, or not from this server)'
    if str(claims.get('typ', '')) != 'tab':
        return None, 'signature is not for a tab'
    if str(claims.get('slug', '')) != slug:
        return None, 'signature is for a different tab'
    if int(claims.get('ver', -1)) != version:
        return None, 'signature is for a different version'
    if str(claims.get('sub', '')) != str(device):
        return None, 'signature is for a different computer'

    # ---- 2. the HMAC tag ---------------------------------------------
    try:
        nonce = base64.b64decode(str(envelope.get('nonce', '')))
        ct = base64.b64decode(str(envelope.get('ct', '')))
        tag = base64.b64decode(str(envelope.get('tag', '')))
    except Exception:
        return None, 'payload is not valid base64'
    if len(nonce) != 16 or not ct or len(tag) != 32:
        return None, 'payload is the wrong shape'

    plan = str(envelope.get('plan', claims.get('plan', 'free')))

    # The IKM binds the licence serial. The server seals with the serial it
    # has on record, which is '' for an installation with no ACTIVE licence,
    # while a client whose licence expired or was deleted may still hold the
    # old serial locally. Deriving a different IKM than the server used is
    # exactly what produced the 'payload failed its integrity check' state,
    # so the serial the server used must come from the SIGNED grant when the
    # server provides it. Older payloads have no 'ser' claim; for those we
    # try the local serial and then the empty serial a free installation is
    # sealed with.
    if 'ser' in claims:
        serial_candidates = [str(claims.get('ser', ''))]
    else:
        serial_candidates = []
        if str(serial) != '':
            serial_candidates.append(str(serial))
        serial_candidates.append('')

    aad = ('%s|%d|%s|%s' % (slug, version, device, plan)).encode('utf-8')

    source = None
    for candidate in serial_candidates:
        ikm = _ikm(device, candidate, slug, version)
        k_enc = _hkdf(ikm, nonce, b'mvl-tab-enc/v1')
        k_mac = _hkdf(ikm, nonce, b'mvl-tab-mac/v1')
        expect = hmac.new(k_mac, aad + b'|' + nonce + b'|' + ct,
                          hashlib.sha256).digest()
        # compare_digest, not ==, so a mismatch cannot be found a byte at a time
        if hmac.compare_digest(expect, tag):
            source = _ctr_xor(k_enc, ct)
            break

    if source is None:
        return None, 'payload failed its integrity check'

    # ---- 3. the hash inside the signed grant --------------------------
    want = str(claims.get('sha256', '')).lower()
    got = hashlib.sha256(bytes(source)).hexdigest()
    if not want or not hmac.compare_digest(want, got):
        _zero(source)
        return None, 'decrypted code does not match the signed hash'

    meta = {
        'slug': slug,
        'version': version,
        'title': str(envelope.get('title', slug)),
        'plan': plan,
        'ui_width': int(envelope.get('ui_width', TAB_ADVISED_W) or TAB_ADVISED_W),
        'ui_height': int(envelope.get('ui_height', TAB_ADVISED_H) or TAB_ADVISED_H),
        'expires': int(claims.get('exp', 0) or 0),
    }
    return source, meta


def _zero(buf):
    """Overwrite a bytearray in place.

    Best effort, and worth being honest about what it achieves: it clears
    THIS buffer, which is the one that held the decrypted module. It cannot
    clear the immutable bytes object compile() is handed, nor anything the
    interpreter copied internally. It shortens the window, it does not
    close it.
    """
    try:
        for i in range(len(buf)):
            buf[i] = 0
    except Exception:
        pass


# ----------------------------------------------------------------------
# the in-memory executor
# ----------------------------------------------------------------------
def load_module(source_bytes, slug):
    """Compile and execute a module from memory. Never touches the disk.

    Returns the module object. Raises whatever the module raises, so the
    caller can show the real reason in the tab.
    """
    name = 'mavely_tab_%s' % (slug,)
    module = types.ModuleType(name)
    module.__dict__['__name__'] = name
    module.__dict__['__file__'] = '<mavelylink-tab:%s>' % (slug,)
    # No __loader__ and no entry in sys.modules on purpose: the module is not
    # importable by name, so nothing else in the tool can reach it by an
    # `import`, and a second load replaces it cleanly.
    code = compile(source_bytes, '<mavelylink-tab:%s>' % (slug,), 'exec')
    exec(code, module.__dict__)                                  # noqa: S102
    return module


# ----------------------------------------------------------------------
# the container: DPI-aware and scrollable
# ----------------------------------------------------------------------
class TabCanvas(object):
    """The frame a remote module builds into.

    Guarantees, all of which the AI converter prompt documents:
      * it already exists, is sized and is packed - the module only fills it
      * it scrolls in both directions, so a module designed for a bigger
        canvas still works in a small window
      * the inner frame tracks the viewport width, so a module that uses
        sticky='we' fills the tab instead of hugging the left edge
      * mouse-wheel scrolling is bound on enter and released on leave, so it
        never steals the wheel from the Browser Profiles list next door
    """

    def __init__(self, parent, host, min_width=TAB_ADVISED_W, min_height=TAB_ADVISED_H):
        self.host = host
        self.outer = tk.Frame(parent, bg=self._c('BG'))
        self.outer.pack(fill=tk.BOTH, expand=True)
        self.outer.rowconfigure(0, weight=1)
        self.outer.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.outer, bg=self._c('BG'), highlightthickness=0, bd=0)
        self.canvas.grid(row=0, column=0, sticky='nsew')

        self.vbar = ttk.Scrollbar(self.outer, orient='vertical',
                                  command=self.canvas.yview, style='Vertical.TScrollbar')
        self.hbar = ttk.Scrollbar(self.outer, orient='horizontal',
                                  command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self._on_y, xscrollcommand=self._on_x)

        self.inner = tk.Frame(self.canvas, bg=self._c('BG'))
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor='nw')

        self._min_w = max(1, int(min_width))
        self._min_h = max(1, int(min_height))

        self.inner.bind('<Configure>', self._on_inner)
        self.canvas.bind('<Configure>', self._on_canvas)
        self.canvas.bind('<Enter>', self._wheel_on)
        self.canvas.bind('<Leave>', self._wheel_off)
        self._wheel_bound = False

    # ---- theme -------------------------------------------------------
    def _c(self, name, default='#111111'):
        return getattr(self.host, name, default)

    # ---- scrolling ---------------------------------------------------
    def _on_y(self, first, last):
        """Show the vertical bar only when there is something to scroll."""
        try:
            if float(first) <= 0.0 and float(last) >= 1.0:
                self.vbar.grid_remove()
            else:
                self.vbar.grid(row=0, column=1, sticky='ns')
            self.vbar.set(first, last)
        except Exception:
            pass

    def _on_x(self, first, last):
        try:
            if float(first) <= 0.0 and float(last) >= 1.0:
                self.hbar.grid_remove()
            else:
                self.hbar.grid(row=1, column=0, sticky='we')
            self.hbar.set(first, last)
        except Exception:
            pass

    def _on_inner(self, _event=None):
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        except Exception:
            pass

    def _on_canvas(self, event):
        """Stretch the inner frame to the viewport, but never below the size
        the module declared - that is what makes the scrollbars appear
        instead of the content being squashed."""
        try:
            width = max(event.width, self._min_w)
            height = max(event.height, self._min_h)
            self.canvas.itemconfigure(self._window, width=width, height=height)
        except Exception:
            pass

    def _wheel_on(self, _event=None):
        if self._wheel_bound:
            return
        self._wheel_bound = True
        try:
            self.canvas.bind_all('<MouseWheel>', self._wheel)          # Windows / macOS
            self.canvas.bind_all('<Button-4>', self._wheel_linux)      # X11 up
            self.canvas.bind_all('<Button-5>', self._wheel_linux)      # X11 down
        except Exception:
            pass

    def _wheel_off(self, _event=None):
        if not self._wheel_bound:
            return
        self._wheel_bound = False
        for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            try:
                self.canvas.unbind_all(seq)
            except Exception:
                pass

    def _wheel(self, event):
        try:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        except Exception:
            pass

    def _wheel_linux(self, event):
        try:
            self.canvas.yview_scroll(-1 if event.num == 4 else 1, 'units')
        except Exception:
            pass

    def destroy(self):
        self._wheel_off()
        try:
            self.outer.destroy()
        except Exception:
            pass


# ----------------------------------------------------------------------
# one remote tab
# ----------------------------------------------------------------------
class RemoteTab(object):
    """A single server-defined tab: its notebook frame, state and module."""

    STATE_LOADING = 'loading'
    STATE_READY = 'ready'
    STATE_LOCKED = 'locked'
    STATE_ERROR = 'error'
    STATE_OFFLINE = 'offline'

    def __init__(self, host, meta):
        self.host = host                      # the TabHost
        self.gui = host.gui
        self.slug = str(meta.get('slug', ''))
        self.title = str(meta.get('title', self.slug))
        self.order = int(meta.get('order', 0) or 0)
        self.version = int(meta.get('version', 0) or 0)
        self.required_plan = str(meta.get('required_plan', 'free'))
        self.locked = bool(meta.get('locked', False))
        self.too_old = bool(meta.get('too_old', False))
        self.min_tool_version = str(meta.get('min_tool_version', ''))
        self.ui_width = int(meta.get('ui_width', TAB_ADVISED_W) or TAB_ADVISED_W)
        self.ui_height = int(meta.get('ui_height', TAB_ADVISED_H) or TAB_ADVISED_H)

        self.frame = None
        self.canvas = None
        self.module = None
        self.state = self.STATE_LOADING
        self._message = ''
        self._built = False

    # ---- notebook ----------------------------------------------------
    def attach(self, notebook):
        """Create the notebook page. Matches the existing tabs' padding and
        label spacing exactly, so the tab strip stays visually uniform."""
        self.frame = ttk.Frame(notebook, style='TFrame', padding=8)
        notebook.add(self.frame, text='   %s   ' % (self.title,))
        return self.frame

    def set_title(self, title):
        """A rename in the dashboard, applied here."""
        if title == self.title:
            return
        self.title = title
        try:
            self.gui.notebook.tab(self.frame, text='   %s   ' % (title,))
        except Exception:
            pass

    # ---- content -----------------------------------------------------
    def clear(self):
        if self.canvas is not None:
            self.canvas.destroy()
            self.canvas = None
        for child in list(self.frame.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass

    def show_message(self, state, title, body, action=None, action_label=None):
        """The inline state panel: locked, offline, error, empty.

        Drawn IN the tab rather than as a dialog, so the tool is never seized.
        The small popup is separate and only appears on a click.
        """
        self.state = state
        self._message = body
        self.clear()
        gui = self.gui
        wrap = tk.Frame(self.frame, bg=gui.BG)
        wrap.pack(fill=tk.BOTH, expand=True)

        card = tk.Frame(wrap, bg=gui.BG_CARD, highlightbackground=gui.BORDER,
                        highlightthickness=1)
        card.place(relx=0.5, rely=0.42, anchor='center')

        glyph = {'locked': '\u25cf', 'offline': '\u25cb',
                 'error': '\u25a0'}.get(state, '\u25cb')
        colour = {'locked': gui.ACCENT, 'offline': gui.FG_MUTED,
                  'error': gui.DANGER}.get(state, gui.FG_MUTED)

        head = tk.Frame(card, bg=gui.BG_CARD)
        head.pack(fill=tk.X, padx=26, pady=(22, 0))
        tk.Label(head, text=glyph, bg=gui.BG_CARD, fg=colour,
                 font=('Segoe UI', 12)).pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(head, text=title, bg=gui.BG_CARD, fg=gui.FG,
                 font=('Segoe UI', 11, 'bold')).pack(side=tk.LEFT)

        tk.Label(card, text=body, bg=gui.BG_CARD, fg=gui.FG_MUTED,
                 font=('Segoe UI', 9), justify=tk.LEFT, wraplength=420,
                 anchor='w').pack(fill=tk.X, padx=26, pady=(8, 0))

        row = tk.Frame(card, bg=gui.BG_CARD)
        row.pack(fill=tk.X, padx=26, pady=(16, 22))
        if action is not None:
            ttk.Button(row, text=action_label or 'Continue', style='Accent.TButton',
                       command=action).pack(side=tk.LEFT)
        ttk.Button(row, text='Refresh tabs', style='Ghost.TButton',
                   command=self.host.refresh_async).pack(side=tk.LEFT, padx=(8, 0))

        # Clicking anywhere in a locked tab explains why, as the brief asks.
        if state == self.STATE_LOCKED:
            for widget in (wrap, card, head):
                try:
                    widget.bind('<Button-1>', lambda e: self.host.locked_popup(self))
                except Exception:
                    pass

    def show_locked(self):
        plan_word = {'pro': 'Pro', 'team': 'Unlimited for Team'}.get(
            self.required_plan, 'a paid plan')
        self.show_message(
            self.STATE_LOCKED,
            '%s is locked' % (self.title,),
            'This feature requires %s. Your Free plan keeps working as it is — '
            'upgrade to unlock this tab.\n\n'
            'The code for this tab is never sent to an installation that is not '
            'entitled to it, so there is nothing to unlock locally.' % (plan_word,),
            action=lambda: self.host.locked_popup(self),
            action_label='Why is this locked?')

    def mount(self, module, ctx):
        """Hand the container to the module and let it build."""
        self.clear()
        self.module = module
        self.canvas = TabCanvas(self.frame, self.gui,
                                min_width=self.ui_width, min_height=self.ui_height)
        build = getattr(module, 'build', None)
        if not callable(build):
            raise RuntimeError('the module has no build(parent, ctx) function')
        build(self.canvas.inner, ctx)
        self.state = self.STATE_READY
        self._built = True

    # ---- lifecycle hooks ---------------------------------------------
    def _hook(self, name):
        fn = getattr(self.module, name, None) if self.module is not None else None
        if not callable(fn):
            return
        try:
            fn()
        except Exception as exc:
            self.host.log('[tabs] %s.%s failed: %r' % (self.slug, name, exc))

    def on_show(self):
        self._hook('on_show')

    def on_hide(self):
        self._hook('on_hide')

    def teardown(self):
        self._hook('teardown')
        self.module = None


# ----------------------------------------------------------------------
# the host
# ----------------------------------------------------------------------
class TabHost(object):
    """Owns every remote tab: fetching, unsealing, mounting and refreshing.

    One instance lives on the GUI. Everything public here is safe to call
    from the Tk thread and never raises.
    """

    def __init__(self, gui):
        self.gui = gui
        self.tabs = []                  # [RemoteTab] in notebook order
        self._by_slug = {}
        self._busy = False
        self._current = None
        self._lock = threading.RLock()
        # Worker threads never touch Tk directly. They drop a callable on this
        # queue; a poller that runs ON the Tk thread drains it. This is the
        # same pattern the rest of the tool uses (see _ui_pump), and it is
        # safe under both mainloop() and a manual update() loop, unlike a
        # cross-thread after() which raises "main thread is not in main loop".
        try:
            import queue as _queue
            self._ui_q = _queue.Queue()
        except Exception:
            self._ui_q = None
        self._pump_started = False
        self._pump_after = None
        self._refresh_after = None
        self._refresh_interval_ms = 15000   # dashboard poll: new tabs appear live

    # ---- helpers ------------------------------------------------------
    def log(self, message):
        try:
            self.gui.log(message)
        except Exception:
            try:
                sys.stderr.write('%s\n' % (message,))
            except Exception:
                pass

    def _client(self):
        try:
            gen = self.gui.generator
            return gen.license() if hasattr(gen, 'license') else None
        except Exception:
            return None

    def _plan(self):
        try:
            return self.gui._current_plan()
        except Exception:
            return 'free'

    # ---- building -----------------------------------------------------
    def build(self):
        """Create every remote tab. Called once, at start-up.

        Uses the cached manifest first so the tab strip is complete before
        any network call, then refreshes in the background. With no cache and
        no connection, no remote tab is created and the tool is otherwise
        exactly as it was.
        """
        client = self._client()
        if client is None:
            return
        self._start_pump()
        try:
            manifest = client.remote_tabs(refresh=False)
        except Exception as exc:
            self.log('[tabs] cached manifest unreadable: %r' % (exc,))
            manifest = []
        if manifest:
            self._apply_manifest(manifest, from_cache=True)
        self.refresh_async(first=True)
        self.start_auto_refresh()

    def _apply_manifest(self, manifest, from_cache=False):
        """Create, rename, reorder and remove tabs to match the manifest."""
        try:
            notebook = self.gui.notebook
        except Exception:
            return
        wanted = []
        for meta in manifest:
            if isinstance(meta, dict) and meta.get('slug'):
                wanted.append(meta)
        wanted.sort(key=lambda m: (int(m.get('order', 0) or 0), str(m.get('slug', ''))))

        # v7.0.1: the dashboard explicitly promises a Refresh control. The
        # original host defined that control but never called it, which made a
        # newly-created server tab depend entirely on the background poll.
        # Keep the method intact and simply activate it once a manifest has at
        # least one real tab.
        if wanted:
            try:
                self.gui._ensure_tabs_refresh_button()
            except Exception:
                pass

        seen = set()
        for meta in wanted:
            slug = str(meta['slug'])
            seen.add(slug)
            tab = self._by_slug.get(slug)
            if tab is None:
                tab = RemoteTab(self, meta)
                try:
                    tab.attach(notebook)
                except Exception as exc:
                    self.log('[tabs] could not add %s: %r' % (slug, exc))
                    continue
                self._by_slug[slug] = tab
                self.tabs.append(tab)
                self._load_tab(tab, from_cache=from_cache)
            else:
                # A rename in the dashboard lands here, with no restart.
                tab.set_title(str(meta.get('title', tab.title)))
                new_version = int(meta.get('version', 0) or 0)
                new_locked = bool(meta.get('locked', False))
                changed = (new_version != tab.version or new_locked != tab.locked)
                tab.version = new_version
                tab.locked = new_locked
                tab.too_old = bool(meta.get('too_old', False))
                tab.ui_width = int(meta.get('ui_width', tab.ui_width) or tab.ui_width)
                tab.ui_height = int(meta.get('ui_height', tab.ui_height) or tab.ui_height)
                # Reload when something changed, OR when the tab has not yet
                # managed to show real content. The second case is the normal
                # first run: the cached manifest paints the strip with
                # from_cache=True (which only reads the local blob, so a tab
                # with no cached payload lands on the offline/loading state),
                # and the network refresh that follows must then actually
                # fetch it. Without this the tab would sit on "offline"
                # forever once the strip existed.
                unfinished = tab.state in (RemoteTab.STATE_OFFLINE,
                                           RemoteTab.STATE_LOADING,
                                           RemoteTab.STATE_ERROR)
                if changed or (not from_cache and not tab.locked and unfinished):
                    self._load_tab(tab, from_cache=from_cache)

        # Keep the notebook order identical to the server manifest. ttk.Notebook
        # appends new pages by default, so an added tab could otherwise land in
        # an unexpected position. Re-inserting existing pages is safe and does
        # not rebuild or edit the tab module itself.
        try:
            for index, meta in enumerate(wanted):
                slug = str(meta.get('slug', ''))
                tab = self._by_slug.get(slug)
                if tab is not None and tab.frame is not None:
                    self.gui.notebook.insert(index, tab.frame)
        except Exception as exc:
            self.log('[tabs] could not apply notebook order: %r' % (exc,))

        # tabs that disappeared from the dashboard, or were disabled
        for slug in list(self._by_slug.keys()):
            if slug in seen:
                continue
            tab = self._by_slug.pop(slug)
            try:
                tab.teardown()
                self.gui.notebook.forget(tab.frame)
            except Exception:
                pass
            if tab in self.tabs:
                self.tabs.remove(tab)

    def _load_tab(self, tab, from_cache=False):
        """Put the right content in one tab."""
        if tab.too_old:
            tab.show_message(
                RemoteTab.STATE_ERROR, '%s needs a newer version' % (tab.title,),
                'This tab needs version %s of the tool or newer. Everything else keeps '
                'working; update when convenient.' % (tab.min_tool_version or 'a newer',),
                action=self._open_update, action_label='Get the update')
            return
        if tab.locked:
            tab.show_locked()
            return
        tab.show_message(
            RemoteTab.STATE_LOADING, tab.title,
            'Loading this tab from MavelyLink…')
        self._fetch_and_mount_async(tab, from_cache=from_cache)

    def _open_update(self):
        try:
            self.gui._open_upgrade()
        except Exception:
            pass

    # ---- fetching -----------------------------------------------------
    def _fetch_and_mount_async(self, tab, from_cache=False):
        """Network on a worker thread, Tk only on the main thread.

        Every widget call goes back through root.after(), because touching a
        Tk widget from a worker thread is undefined behaviour and shows up
        later as a random crash that is very hard to trace.
        """
        def work():
            payload = None
            reason = ''
            client = self._client()
            if client is None:
                reason = 'the licensing module is not available'
            else:
                try:
                    payload = client.tab_payload(tab.slug, tab.version,
                                                 allow_network=not from_cache)
                except Exception as exc:
                    reason = 'could not reach MavelyLink (%r)' % (exc,)
            self._post(lambda: self._mount(tab, payload, reason))

        try:
            threading.Thread(target=work, daemon=True).start()
        except Exception as exc:
            self.log('[tabs] worker thread refused to start: %r' % (exc,))
            self._mount(tab, None, 'could not start a worker thread')

    def _post(self, fn):
        """Hand a callable to the Tk thread. Safe from any thread."""
        if self._ui_q is not None:
            try:
                self._ui_q.put(fn)
                return
            except Exception:
                pass
        # last resort if the queue could not be created
        try:
            self.gui.root.after(0, fn)
        except Exception:
            pass

    def _start_pump(self):
        """Begin draining the UI queue on the Tk thread. Idempotent."""
        if self._pump_started or self._ui_q is None:
            return
        self._pump_started = True
        self._pump()

    def _pump(self):
        if self._ui_q is not None:
            try:
                while True:
                    fn = self._ui_q.get_nowait()
                    try:
                        fn()
                    except Exception as exc:
                        self.log('[tabs] UI callback failed: %r' % (exc,))
            except Exception:
                pass                     # queue empty
        if not self._pump_started:
            return                       # shutdown() asked us to stop
        try:
            root = self.gui.root
            if root.winfo_exists():
                self._pump_after = root.after(80, self._pump)
            else:
                self._pump_started = False
        except Exception:
            self._pump_started = False

    def _mount(self, tab, payload, reason):
        """Unseal, compile, run. Main thread only."""
        if tab.frame is None or not tab.frame.winfo_exists():
            return

        if payload is None or not payload:
            # None or {} both mean "nothing to run": offline with no cache, a
            # tab with no source yet, or a fetch that returned nothing. Show
            # the calm offline state, never the scary verification error.
            # A module that is already running is NEVER torn down by one
            # failed fetch - a transient blip must not destroy a working tab.
            if tab._built and tab.module is not None:
                tab.state = RemoteTab.STATE_READY
                return
            tab.show_message(
                RemoteTab.STATE_OFFLINE, '%s is not available offline' % (tab.title,),
                'This tab could not be loaded: %s.\n\nThe rest of the tool is unaffected. '
                'It loads automatically as soon as the connection is back.'
                % (reason or 'no cached copy and no connection',))
            return

        state = str(payload.get('state', ''))
        if state == 'locked':
            tab.locked = True
            tab.show_locked()
            return
        if state in ('off', 'disabled'):
            tab.show_message(
                RemoteTab.STATE_OFFLINE, '%s is switched off' % (tab.title,),
                'The administrator has switched this tab off. Nothing is wrong with your '
                'installation and the rest of the tool is unaffected.')
            return
        if state in ('gone', 'empty'):
            tab.show_message(
                RemoteTab.STATE_OFFLINE, '%s is not published yet' % (tab.title,),
                'There is no code published for this tab yet (or it was removed). '
                'It will appear automatically once the administrator saves it.')
            return
        if state == 'update_required':
            tab.show_message(
                RemoteTab.STATE_ERROR, '%s needs a newer version' % (tab.title,),
                'This tab needs a newer version of the tool. Everything else keeps '
                'working; update when convenient.',
                action=self._open_update, action_label='Get the update')
            return

        client = self._client()
        device = getattr(client, 'device', '') if client else ''
        serial = getattr(client, 'serial', '') if client else ''

        source, meta = unseal(payload, device, serial)
        if source is None:
            # meta is the failure reason here
            self.log('[tabs] %s rejected: %s' % (tab.slug, meta))
            tab.show_message(
                RemoteTab.STATE_ERROR, '%s could not be verified' % (tab.title,),
                'The code for this tab did not pass its security checks (%s), so it was '
                'not run. This is deliberate: an unverified module is never executed.\n\n'
                'Press Refresh tabs to fetch a fresh copy.' % (meta,))
            return

        try:
            module = load_module(bytes(source), tab.slug)
            ctx = self.make_ctx(tab)
            tab.mount(module, ctx)
        except Exception as exc:
            self.log('[tabs] %s failed to start: %r' % (tab.slug, exc))
            tab.show_message(
                RemoteTab.STATE_ERROR, '%s could not start' % (tab.title,),
                'This tab reported an error while starting:\n\n%r\n\n'
                'The rest of the tool is unaffected.' % (exc,))
        finally:
            # zero the decrypted buffer as soon as it has been compiled
            _zero(source)
            del source

    # ---- the ctx handed to every module --------------------------------
    def make_ctx(self, tab):
        """Host services. Exactly what the AI converter prompt documents."""
        gui = self.gui
        client = self._client()

        licence = {'serial_masked': '', 'plan_name': 'Free', 'expires_at': '', 'state': 'free'}
        if client is not None:
            try:
                licence = {
                    'serial_masked': _mask(getattr(client, 'serial', '')),
                    'plan_name': client.plan_name(),
                    'expires_at': str(getattr(client, 'expires_at', '')),
                    'state': client.current_plan(),
                }
            except Exception:
                pass

        work = _tab_work_dir(tab.slug)

        def _log(message):
            self.log('[tab:%s] %s' % (tab.slug, message))

        def _toast(message):
            self._post(lambda: self.toast(str(message)))

        def _open_url(url):
            try:
                import webbrowser
                if str(url).lower().startswith(('http://', 'https://')):
                    webbrowser.open(str(url))
            except Exception:
                pass

        return {
            'plan': self._plan(),
            'licence': licence,
            'license': licence,          # both spellings, so neither trips anyone up
            'paths': {'work': work, 'downloads': work},
            'log': _log,
            'toast': _toast,
            'style': self.style_tokens(),
            'scale': self.scale(),
            'tab': {'slug': tab.slug, 'title': tab.title, 'version': tab.version},
            'open_url': _open_url,
            'host_version': getattr(_license, 'APP_VERSION', '') if _license else '',
        }

    def style_tokens(self):
        """The tool's live theme, so a remote tab follows light/dark."""
        gui = self.gui
        out = {}
        for key in ('BG', 'BG_CARD', 'BG_CARD_2', 'BORDER', 'FG', 'FG_MUTED',
                    'ACCENT', 'ACCENT_2', 'GREEN', 'DANGER', 'BANNER', 'HEADER',
                    'ENTRY', 'SELECT'):
            out[key] = getattr(gui, key, '#000000')
        out['font'] = ('Segoe UI', 9)
        out['font_bold'] = ('Segoe UI', 9, 'bold')
        out['font_title'] = ('Segoe UI', 11)
        out['font_mono'] = ('Consolas', 9)
        out['pad'] = 8
        out['gap'] = 6
        return out

    def scale(self):
        try:
            return float(getattr(self.gui, '_dpi_scale', 1.0) or 1.0)
        except Exception:
            return 1.0

    # ---- small popups --------------------------------------------------
    def locked_popup(self, tab):
        """The compact locked dialog: about 320x140, tool style, Upgrade + Close.

        Deliberately tiny and non-destructive. It only reports; nothing the
        user was doing is cancelled and the tool stays usable behind it.
        """
        gui = self.gui
        plan_word = {'pro': 'Pro', 'team': 'Unlimited for Team'}.get(
            tab.required_plan, 'a paid plan')
        try:
            win = tk.Toplevel(gui.root)
        except Exception:
            return
        win.title('Locked')
        win.configure(bg=gui.BG_CARD)
        win.resizable(False, False)
        try:
            win.transient(gui.root)
        except Exception:
            pass

        body = tk.Frame(win, bg=gui.BG_CARD)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(14, 0))
        tk.Label(body, text=tab.title, bg=gui.BG_CARD, fg=gui.FG,
                 font=('Segoe UI', 10, 'bold'), anchor='w').pack(fill=tk.X)
        tk.Label(body, text='This feature requires %s.' % (plan_word,),
                 bg=gui.BG_CARD, fg=gui.FG_MUTED, font=('Segoe UI', 9),
                 justify=tk.LEFT, wraplength=286, anchor='w').pack(fill=tk.X, pady=(6, 0))

        btns = tk.Frame(win, bg=gui.BG_CARD)
        btns.pack(fill=tk.X, padx=16, pady=(12, 14))

        def close():
            try:
                win.grab_release()
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass

        def upgrade():
            close()
            try:
                gui._open_upgrade()
            except Exception:
                pass

        shut = ttk.Button(btns, text='Close', style='Ghost.TButton', width=8, command=close)
        shut.pack(side=tk.RIGHT)
        ttk.Button(btns, text='Upgrade', style='Accent.TButton', width=9,
                   command=upgrade).pack(side=tk.RIGHT, padx=(0, 6))

        win.protocol('WM_DELETE_WINDOW', close)
        win.bind('<Return>', lambda e: close())
        win.bind('<Escape>', lambda e: close())
        try:
            win.geometry('320x140')
            win.minsize(320, 140)
        except Exception:
            pass
        try:
            gui._center_popup(win)
        except Exception:
            pass
        try:
            shut.focus_set()
            win.grab_set()
        except Exception:
            pass

    def toast(self, message):
        """ctx["toast"]: a small auto-dismissing note, never modal."""
        gui = self.gui
        try:
            win = tk.Toplevel(gui.root)
        except Exception:
            return
        win.overrideredirect(True)
        win.configure(bg=gui.BG_CARD_2)
        try:
            win.transient(gui.root)
            win.attributes('-alpha', 0.97)
        except Exception:
            pass
        tk.Label(win, text=str(message)[:200], bg=gui.BG_CARD_2, fg=gui.FG,
                 font=('Segoe UI', 9), justify=tk.LEFT, wraplength=300,
                 padx=14, pady=10).pack()
        try:
            gui.root.update_idletasks()
            x = gui.root.winfo_rootx() + gui.root.winfo_width() - win.winfo_reqwidth() - 28
            y = gui.root.winfo_rooty() + gui.root.winfo_height() - win.winfo_reqheight() - 60
            win.geometry('+%d+%d' % (max(0, x), max(0, y)))
        except Exception:
            pass
        try:
            win.after(3200, win.destroy)
        except Exception:
            pass

    # ---- refresh -------------------------------------------------------
    def refresh_async(self, first=False, silent=False):
        """The "Refresh tabs" action, the launch refresh, and the
        background poll. `silent` suppresses toasts for the auto poll.

        Guarded so repeated clicks cannot pile up worker threads.
        """
        with self._lock:
            if self._busy:
                return
            self._busy = True

        def work():
            manifest = []
            error = ''
            client = self._client()
            if client is None:
                error = 'licensing module unavailable'
            else:
                try:
                    manifest = client.remote_tabs(refresh=True)
                except Exception as exc:
                    error = repr(exc)
            self._post(lambda: self._refresh_done(manifest, error, first, silent))

        try:
            threading.Thread(target=work, daemon=True).start()
        except Exception:
            with self._lock:
                self._busy = False

    def _refresh_done(self, manifest, error, first, silent=False):
        with self._lock:
            self._busy = False
        if error:
            self.log('[tabs] refresh failed: %s' % (error,))
            if not first and not silent:
                self.toast('Could not reach MavelyLink. Tabs are unchanged.')
            return
        try:
            self._apply_manifest(manifest, from_cache=False)
        except Exception as exc:
            self.log('[tabs] could not apply the manifest: %r' % (exc,))
            return
        # v7.0.1: leave a useful diagnostic in the existing log path. This
        # makes it clear that the server answered and how many tabs were
        # actually received, without changing any tab/module behaviour.
        try:
            self.log('[tabs] manifest refreshed: %d tab(s)' % len(manifest or []))
        except Exception:
            pass
        if not first and not silent:
            self.toast('Tabs refreshed.')

    # ---- automatic background refresh --------------------------------
    def start_auto_refresh(self, interval_ms=90000):
        """Poll the dashboard so a tab added in 'ADD Tabs *Py in Your Tool'
        appears in an open tool without a restart. Idempotent."""
        self._refresh_interval_ms = max(15000, int(interval_ms))
        self._schedule_refresh()

    def _schedule_refresh(self):
        if self._refresh_after is not None:
            try:
                self.gui.root.after_cancel(self._refresh_after)
            except Exception:
                pass
            self._refresh_after = None
        try:
            if self.gui.root.winfo_exists():
                self._refresh_after = self.gui.root.after(
                    self._refresh_interval_ms, self._auto_refresh)
        except Exception:
            self._refresh_after = None

    def _auto_refresh(self):
        self._refresh_after = None
        self.refresh_async(silent=True)     # silent: no toasts from the poll
        self._schedule_refresh()

    # ---- notebook focus -------------------------------------------------
    def on_tab_changed(self, widget):
        """Called by the GUI when the selected notebook page changes."""
        nxt = None
        for tab in self.tabs:
            if tab.frame is widget:
                nxt = tab
                break
        if nxt is self._current:
            return
        if self._current is not None:
            self._current.on_hide()
        self._current = nxt
        if nxt is not None:
            nxt.on_show()
            # A tab stuck on loading/offline/error gets another fetch the
            # moment the user clicks it - no restart, no waiting for the poll.
            try:
                if (not nxt.locked and not self._busy and
                        nxt.state in (RemoteTab.STATE_OFFLINE,
                                      RemoteTab.STATE_LOADING,
                                      RemoteTab.STATE_ERROR)):
                    self._load_tab(nxt, from_cache=False)
            except Exception:
                pass

    def shutdown(self):
        """Stop every module cleanly when the tool closes."""
        self._pump_started = False       # stop the poller rescheduling itself
        if self._pump_after is not None:
            try:
                self.gui.root.after_cancel(self._pump_after)
            except Exception:
                pass
            self._pump_after = None
        if self._refresh_after is not None:
            try:
                self.gui.root.after_cancel(self._refresh_after)
            except Exception:
                pass
            self._refresh_after = None
        for tab in list(self.tabs):
            try:
                tab.teardown()
            except Exception:
                pass


# ----------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------
def _mask(serial):
    serial = str(serial or '')
    if len(serial) < 12:
        return serial
    return serial[:10] + '*****-*****-' + serial[-5:]


def _tab_work_dir(slug):
    """A per-tab scratch folder. The ONLY place a module may write.

    Deliberately outside the profiles directory and outside the licensing
    state folder, so a misbehaving module cannot damage either.
    """
    safe = ''.join(ch for ch in str(slug) if ch.isalnum() or ch == '_')[:64] or 'tab'
    try:
        if _license is not None and hasattr(_license, '_state_dir'):
            base = _license._state_dir()
        else:
            base = os.path.join(os.path.expanduser('~'), '.mavelylink')
        path = os.path.join(base, 'tabwork', safe)
        if not os.path.isdir(path):
            os.makedirs(path)
        return path
    except Exception:
        try:
            import tempfile
            return tempfile.gettempdir()
        except Exception:
            return '.'
