# -*- coding: utf-8 -*-
"""Sample tab module for the "Chrome Profile Generator" desktop tool.

This is a COMPLETE, WORKING example of the tab-module contract. Paste it into
the "Script" field of a tab in the admin dashboard (ADD Tabs *Py in Your Tool)
to see a real remote tab render inside the tool. It also serves as the
reference the AI converter prompt describes.

What it shows off, all inside the contract:
  * TAB_META plus build(parent, ctx), on_show, on_hide, teardown
  * every colour and font taken from ctx["style"], so it follows light/dark
  * slow work on a worker thread, results marshalled back with parent.after()
  * ctx["log"], ctx["toast"], ctx["open_url"] and ctx["plan"]
  * grid() layout that fits the advised 960x340 canvas
  * a teardown() that cancels timers and stops threads

It is deliberately Python 3.7.7 / standard-library only: no walrus, no
builtin generics, no f-string "{x=}", no third-party import.
"""

import threading
import time

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:                                    # pragma: no cover
    tk = None
    ttk = None


TAB_META = {
    "name": "Sample Tab",
    "version": 1,
    "min_width": 960,
    "min_height": 340,
}


# Module-level state. teardown() clears it so nothing leaks when the tool
# closes or the tab is reloaded after a version bump.
_STATE = {
    "after_id": None,
    "parent": None,
    "ticks": 0,
    "stop": False,
    "clock_var": None,
}


def build(parent, ctx):
    """Called once when the tab is created. Builds everything into `parent`.

    `parent` already exists, is sized, DPI-scaled and scrollable — this only
    fills it. Returns quickly and never blocks.
    """
    try:
        _build(parent, ctx)
    except Exception as exc:
        # Re-raise so the host shows its inline error state; log first so the
        # reason reaches the tool's log panel and the dashboard.
        ctx["log"]("[sample] build failed: %r" % (exc,))
        raise


def _build(parent, ctx):
    style = ctx["style"]
    _STATE["parent"] = parent
    _STATE["stop"] = False
    _STATE["ticks"] = 0

    bg = style["BG"]
    card_bg = style["BG_CARD"]
    fg = style["FG"]
    muted = style["FG_MUTED"]
    pad = int(style.get("pad", 8))
    gap = int(style.get("gap", 6))

    parent.configure(bg=bg)
    # a single content column that stretches with the window
    parent.columnconfigure(0, weight=1)

    # ---- header ------------------------------------------------------
    header = tk.Frame(parent, bg=bg)
    header.grid(row=0, column=0, sticky="we", padx=pad, pady=(pad, 0))
    tk.Label(header, text="Sample Tab", bg=bg, fg=fg,
             font=style.get("font_title", ("Segoe UI", 11))).pack(side=tk.LEFT)
    plan = str(ctx.get("plan", "free"))
    tk.Label(header, text="  plan: %s" % (plan,), bg=bg, fg=muted,
             font=style.get("font", ("Segoe UI", 9))).pack(side=tk.LEFT)

    # ---- a card with live content ------------------------------------
    card = tk.Frame(parent, bg=card_bg, highlightbackground=style["BORDER"],
                    highlightthickness=1)
    card.grid(row=1, column=0, sticky="we", padx=pad, pady=pad)
    card.columnconfigure(1, weight=1)

    tk.Label(card, text="This tab is served from your dashboard.",
             bg=card_bg, fg=fg, font=style.get("font", ("Segoe UI", 9)),
             anchor="w", justify=tk.LEFT).grid(
        row=0, column=0, columnspan=3, sticky="we", padx=pad, pady=(pad, gap))

    # a 1-second clock, to show the after()-driven update pattern
    _STATE["clock_var"] = tk.StringVar(value="--:--:--")
    tk.Label(card, text="Local time:", bg=card_bg, fg=muted,
             font=style.get("font", ("Segoe UI", 9))).grid(
        row=1, column=0, sticky="w", padx=(pad, gap), pady=gap)
    tk.Label(card, textvariable=_STATE["clock_var"], bg=card_bg, fg=fg,
             font=style.get("font_mono", ("Consolas", 9))).grid(
        row=1, column=1, sticky="w", pady=gap)

    # ---- a row of buttons using the tool's own styles ----------------
    row = tk.Frame(parent, bg=bg)
    row.grid(row=2, column=0, sticky="we", padx=pad, pady=(0, pad))

    def say_hello():
        ctx["toast"]("Hello from the sample tab!")
        ctx["log"]("[sample] toast shown")

    def do_work():
        # slow work OFF the UI thread; result comes back through after()
        status.configure(text="Working\u2026")

        def worker():
            time.sleep(1.0)                       # pretend this is real work
            answer = sum(i * i for i in range(1000))

            def done():
                if not _STATE["stop"]:
                    status.configure(text="Worker finished: %d" % (answer,))
            _after(parent, 0, done)

        threading.Thread(target=worker, daemon=True).start()

    def open_site():
        ctx["open_url"]("https://mavlink.click/")

    ttk.Button(row, text="Say hello", style="Accent.TButton",
               command=say_hello).pack(side=tk.LEFT)
    ttk.Button(row, text="Do work", style="Go.TButton",
               command=do_work).pack(side=tk.LEFT, padx=(gap, 0))
    ttk.Button(row, text="Open site", style="Ghost.TButton",
               command=open_site).pack(side=tk.LEFT, padx=(gap, 0))

    status = tk.Label(parent, text="Ready.", bg=bg, fg=muted,
                      font=style.get("font", ("Segoe UI", 9)), anchor="w")
    status.grid(row=3, column=0, sticky="we", padx=pad, pady=(0, pad))

    ctx["log"]("[sample] built at scale %.2f" % float(ctx.get("scale", 1.0)))
    _tick(parent)


def _tick(parent):
    """One-second clock tick, rescheduled with after(). Cancelled in teardown."""
    if _STATE["stop"]:
        return
    var = _STATE.get("clock_var")
    if var is not None:
        try:
            var.set(time.strftime("%H:%M:%S"))
        except Exception:
            pass
    _STATE["ticks"] += 1
    _STATE["after_id"] = _after(parent, 1000, lambda: _tick(parent))


def _after(parent, ms, fn):
    """parent.after() that never raises if the widget is gone."""
    try:
        return parent.after(ms, fn)
    except Exception:
        return None


def on_show():
    """Called when the tab gains focus. Safe to call more than once."""
    # nothing heavy here; the clock keeps running regardless
    pass


def on_hide():
    """Called when the tab loses focus."""
    pass


def teardown():
    """Called when the tool closes or the tab is reloaded. Free everything."""
    _STATE["stop"] = True
    parent = _STATE.get("parent")
    after_id = _STATE.get("after_id")
    if parent is not None and after_id is not None:
        try:
            parent.after_cancel(after_id)
        except Exception:
            pass
    _STATE["after_id"] = None
    _STATE["parent"] = None
    _STATE["clock_var"] = None
