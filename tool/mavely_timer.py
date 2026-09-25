#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MavelyLink — USA Timer panel.

Ported from USA_Timer_Post.py. The scheduling logic (golden/good hours, day
ranking, GOLD/GOOD/OK/LOW) is reproduced exactly; everything that made the
original unsafe to embed has been fixed:

  * no tk.Tk() and no mainloop() - this is a Frame that takes a parent, so
    it runs on the tool's existing event loop
  * the 1-second tick is cancelled on destroy and paused while the tab is
    not visible, so no timer leaks and profile generation is never slowed
  * notifications are drawn IN the tab. No messagebox, no '-topmost', so
    the tool can never be seized or pushed in front of what you were doing.
    Only the sound runs on a worker thread; every UI call is on the main
    thread
  * colours come from theme tokens, so it follows light/dark
  * all text comes from the language file, including AM/PM, state names,
    day names and tips
  * zoneinfo (stdlib, 3.9+) with an automatic pytz fallback, so nothing
    extra has to be bundled on a modern build
  * get_local_ip() is gone - it returned a LAN address, blocked the UI, and
    served no purpose here
  * the 'if mins:' bug is fixed, so 0 minutes is a real answer
  * seen-notification keys are trimmed, so the set cannot grow forever
  * no bare 'except:' - failures go to the tool's logger
"""

import threading
from datetime import datetime, timedelta

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:                                    # pragma: no cover
    tk = None
    ttk = None

# ---------------------------------------------------------------- zones
# Three backends, tried in order, so this works on Python 3.7.7 with NO
# third-party dependency to bundle:
#
#   1. zoneinfo   - stdlib on 3.9+
#   2. pytz       - if the build already ships it
#   3. built-in   - the four US zones these 11 states actually use, with the
#                   current US DST rule. Pure stdlib, works on 3.7.
#
# The built-in table is deliberately narrow: it covers only the zones this
# feature needs and does not pretend to be a general tz database.
from datetime import tzinfo

_TZ_BACKEND = 'builtin'
_tz = None

try:
    from zoneinfo import ZoneInfo

    def _tz(name):                                   # noqa: F811
        return ZoneInfo(name)

    _TZ_BACKEND = 'zoneinfo'
except ImportError:
    try:
        import pytz

        def _tz(name):                               # noqa: F811
            return pytz.timezone(name)

        _TZ_BACKEND = 'pytz'
    except ImportError:
        _tz = None


# (standard offset hours, observes US DST)
_US_ZONES = {
    "America/New_York":    (-5, True),
    "America/Chicago":     (-6, True),
    "America/Denver":      (-7, True),
    "America/Los_Angeles": (-8, True),
    "America/Phoenix":     (-7, False),    # Arizona does not observe DST
}
_US_ABBR = {
    "America/New_York":    ("EST", "EDT"),
    "America/Chicago":     ("CST", "CDT"),
    "America/Denver":      ("MST", "MDT"),
    "America/Los_Angeles": ("PST", "PDT"),
    "America/Phoenix":     ("MST", "MST"),
}


def _nth_weekday(year, month, weekday, n):
    """Date of the nth <weekday> of a month (weekday: Mon=0)."""
    d = datetime(year, month, 1)
    shift = (weekday - d.weekday()) % 7
    return d + timedelta(days=shift + (n - 1) * 7)


def _us_dst_active(dt_utc, std_offset):
    """US DST: 02:00 local on the 2nd Sunday of March until 02:00 local on
    the 1st Sunday of November. Compared in local standard time."""
    local_std = dt_utc + timedelta(hours=std_offset)
    year = local_std.year
    start = _nth_weekday(year, 3, 6, 2) + timedelta(hours=2)    # Sun = 6
    end = _nth_weekday(year, 11, 6, 1) + timedelta(hours=2)
    return start <= local_std.replace(tzinfo=None) < end


class _UsFixedZone(tzinfo):
    """Minimal tzinfo for the US zones this feature uses."""

    def __init__(self, name):
        self._name = name
        self._std, self._dst = _US_ZONES.get(name, (-5, True))

    def _is_dst(self, dt):
        if not self._dst or dt is None:
            return False
        naive = dt.replace(tzinfo=None)
        return _us_dst_active(naive - timedelta(hours=self._std), self._std)

    def utcoffset(self, dt):
        return timedelta(hours=self._std) + self.dst(dt)

    def dst(self, dt):
        return timedelta(hours=1) if self._is_dst(dt) else timedelta(0)

    def tzname(self, dt):
        std, dst = _US_ABBR.get(self._name, ("", ""))
        return dst if self._is_dst(dt) else std


if _tz is None:
    def _tz(name):                                   # noqa: F811
        return _UsFixedZone(name)

    _TZ_BACKEND = 'builtin'


ZONES_FALLBACK = [
    ("Arkansas", "America/Chicago"),
    ("New York", "America/New_York"),
    ("Texas", "America/Chicago"),
    ("Florida", "America/New_York"),
    ("California", "America/Los_Angeles"),
    ("Tennessee", "America/Chicago"),
    ("Ohio", "America/New_York"),
    ("Oklahoma", "America/Chicago"),
    ("Missouri", "America/Chicago"),
    ("Pennsylvania", "America/New_York"),
    ("Arizona", "America/Phoenix"),
]

GOLDEN_HOURS = [9, 10, 11, 13, 14, 15, 20, 21]
GOOD_HOURS = [6, 7, 8, 12, 18, 19]
BEST_DAYS = {1, 2, 3}          # Tue, Wed, Thu
GOOD_DAYS = {0, 4}             # Mon, Fri
AVOID_DAYS = {5, 6}            # Sat, Sun

US_REFERENCE_TZ = "America/New_York"   # fallback only; the server sends this


def apply_rules(rules, hour, weekday):
    """Walk the ladder the SERVER sent and return a status key.

    The tool has no built-in opinion about what makes an hour good. It
    only knows how to walk a list of conditions - the conditions
    themselves arrive from the website. Hand it nothing and it returns
    nothing, which is exactly what a cracked copy gets.
    """
    if not rules:
        return None
    golden = hour in (rules.get('golden_hours') or [])
    good = hour in (rules.get('good_hours') or [])
    best_days = set(rules.get('best_days') or [])
    good_days = set(rules.get('good_days') or [])
    avoid_days = set(rules.get('avoid_days') or [])

    for rule in (rules.get('ladder') or []):
        cond = rule.get('if') or {}
        ok = True
        if 'golden' in cond and bool(cond['golden']) != golden:
            ok = False
        if ok and 'good' in cond and bool(cond['good']) != good:
            ok = False
        if ok and 'hour_between' in cond:
            lo, hi = cond['hour_between']
            if not (lo <= hour < hi):
                ok = False
        if ok and 'day' in cond:
            want = cond['day']
            if want == 'best' and weekday not in best_days:
                ok = False
            elif want == 'good' and weekday not in good_days:
                ok = False
            elif want == 'not_avoid' and weekday in avoid_days:
                ok = False
        if ok:
            return rule.get('status', 'LOW')
    return 'LOW'


def apply_tips(rules, hour, weekday):
    """Pick the tip key, again from the server's list."""
    for entry in (rules.get('tips') or []):
        if 'hours' in entry and hour not in entry['hours']:
            continue
        if 'weekday' in entry and weekday != entry['weekday']:
            continue
        if 'weekdays' in entry and weekday not in entry['weekdays']:
            continue
        return entry.get('key', 'tip.default')
    return 'tip.default'


def get_fb_status(hour, weekday):
    """Exactly the original ladder, returning a status key only.

    The colour is resolved from the theme by the panel, so the same status
    looks right in both light and dark.
    """
    is_golden = hour in GOLDEN_HOURS
    is_good = hour in GOOD_HOURS
    is_best_day = weekday in BEST_DAYS
    is_good_day = weekday in GOOD_DAYS
    is_avoid = weekday in AVOID_DAYS

    if is_golden and is_best_day:
        return "GOLD"
    if is_golden and (is_good_day or not is_avoid):
        return "GOOD"
    if is_good and not is_avoid:
        return "OK"
    if 8 <= hour < 18 and not is_avoid:
        return "OK"
    return "LOW"


def tip_key(hour, weekday):
    if hour in (9, 10, 11):
        return "tip.morning"
    if hour in (13, 14, 15):
        return "tip.lunch"
    if hour in (20, 21):
        return "tip.evening"
    if weekday == 2:
        return "tip.wednesday"
    if weekday in AVOID_DAYS:
        return "tip.weekend"
    return "tip.default"


def next_golden_minutes(now_by_zone, golden_hours=None):
    """Minutes until the soonest upcoming golden hour anywhere.

    Returns (minutes, state) or (None, None).

    Wall-clock arithmetic on purpose. Adding a timedelta to an aware
    datetime does NOT re-normalise the offset under pytz, so doing the
    maths on instants would drift by an hour across a DST change. The
    question here is "what will the clock on the wall say", so the wall
    clock is what is compared - which is also what the original script did.

    Unlike the original, 0 is a real answer (its `if mins:` treated it as
    no result) and it looks into tomorrow, so late at night it still gives
    a number instead of giving up.
    """
    best = None
    for state, now in now_by_zone.items():
        minutes_now = now.hour * 60 + now.minute
        for day_offset in (0, 1):
            for h in (golden_hours or GOLDEN_HOURS):
                target = day_offset * 24 * 60 + h * 60
                mins = target - minutes_now
                if mins < 0:
                    continue
                if best is None or mins < best[0]:
                    best = (mins, state)
    return best if best else (None, None)


def play_sound():
    """Sound only. The ONLY thing allowed on a worker thread."""
    try:
        import platform
        system = platform.system()
        if system == "Windows":
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        elif system == "Darwin":
            import subprocess
            subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], check=False)
        else:
            import subprocess
            subprocess.run(
                ["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"], check=False)
    except Exception:
        pass


class UsaTimerPanel(object):
    """The USA Timer, as a panel inside an existing window.

    host must provide: t(key, **kw), theme colours, log(msg) and a Tk
    widget to draw into. It never creates a root and never starts a loop.
    """

    TICK_MS = 1000

    def __init__(self, parent, host, rules=None):
        self.parent = parent
        self.host = host
        # The rules arrive from the website (see includes/features.php).
        # With none, the panel renders its chrome and NO schedule: the list
        # of states, the hours and the ladder all live on the server, so a
        # copy that cannot reach it has nothing to show. That is the point.
        self.rules = rules or {}
        self.zones = []
        for z in (self.rules.get('zones') or []):
            if isinstance(z, dict):
                self.zones.append((z.get('state'), z.get('tz')))
            elif isinstance(z, (list, tuple)) and len(z) == 2:
                self.zones.append((z[0], z[1]))
        self._job = None
        self._destroyed = False
        self._notified = {}
        self._rows = {}
        self._last_status = {}
        self.frame = tk.Frame(parent, bg=self._c('BG'))
        self.frame.pack(fill=tk.BOTH, expand=True)
        self._build()
        self.frame.bind('<Destroy>', self._on_destroy)
        self.tick()

    # ---------------------------------------------------------- helpers
    def _c(self, name, default='#ffffff'):
        return getattr(self.host, name, default)

    def _t(self, key, **kw):
        try:
            return self.host.t(key, **kw)
        except Exception:
            return key

    def _log(self, msg):
        try:
            self.host.log('[usa-timer] %s' % msg)
        except Exception:
            pass

    def status_colour(self, status):
        """Status colours that stay legible on light AND dark backgrounds."""
        dark = str(self._c('BG', '#ffffff')).lower() not in ('#ffffff', 'white', '#f7f9fc')
        table = {
            'GOLD': '#d4a017' if not dark else '#ffd700',
            'GOOD': '#1e8e3e' if not dark else '#7ee787',
            'OK':   '#b26a00' if not dark else '#d29922',
            'LOW':  '#8a9099' if not dark else '#484f58',
        }
        return table.get(status, self._c('FG_MUTED', '#888888'))

    # ------------------------------------------------------------- UI
    def _golden_caption(self):
        """Render the server's golden hours as compact ranges."""
        hours = sorted(self.rules.get('golden_hours') or GOLDEN_HOURS)
        if not hours:
            return '--'
        spans, start, prev = [], hours[0], hours[0]
        for h in hours[1:]:
            if h == prev + 1:
                prev = h
                continue
            spans.append((start, prev))
            start = prev = h
        spans.append((start, prev))
        return '  \u00b7  '.join('%02d\u2013%02d' % sp if sp[0] != sp[1] else '%02d' % sp[0]
                                 for sp in spans)

    def _build(self):
        host = self.host
        rtl = getattr(host, '_is_rtl', lambda: False)()
        anchor = tk.E if rtl else tk.W
        justify = tk.RIGHT if rtl else tk.LEFT

        head = tk.Frame(self.frame, bg=self._c('BG_CARD'), highlightthickness=1,
                        highlightbackground=self._c('BORDER'))
        head.pack(fill=tk.X, padx=6, pady=(6, 4))
        self.title_lbl = tk.Label(head, text=self._t('timer.title'), bg=self._c('BG_CARD'),
                                  fg=self._c('ACCENT'), font=('Segoe UI', 16, 'bold'),
                                  anchor=anchor, justify=justify)
        self.title_lbl.pack(fill=tk.X, padx=16, pady=(12, 0))
        self.sub_lbl = tk.Label(head, text=self._t('timer.subtitle'), bg=self._c('BG_CARD'),
                                fg=self._c('FG_MUTED'), font=('Segoe UI', 9),
                                anchor=anchor, justify=justify)
        self.sub_lbl.pack(fill=tk.X, padx=16, pady=(2, 10))

        # your own local time, detected from the OS - not hard-coded
        mine = tk.Frame(head, bg=self._c('BG_CARD_2'))
        mine.pack(fill=tk.X, padx=16, pady=(0, 12))
        self.mine_cap = tk.Label(mine, text=self._t('timer.your_time'), bg=self._c('BG_CARD_2'),
                                 fg=self._c('FG_MUTED'), font=('Segoe UI', 8), anchor=anchor)
        self.mine_cap.pack(fill=tk.X, padx=10, pady=(6, 0))
        row = tk.Frame(mine, bg=self._c('BG_CARD_2'))
        row.pack(fill=tk.X, padx=10, pady=(0, 6))
        self.my_time = tk.Label(row, text='--:--:--', bg=self._c('BG_CARD_2'),
                                fg=self._c('FG'), font=('Consolas', 15, 'bold'))
        self.my_time.pack(side=tk.LEFT)
        self.my_period = tk.Label(row, text='', bg=self._c('BG_CARD_2'),
                                  fg=self._c('FG_MUTED'), font=('Segoe UI', 10, 'bold'))
        self.my_period.pack(side=tk.LEFT, padx=(8, 0))
        self.my_zone = tk.Label(row, text='', bg=self._c('BG_CARD_2'),
                                fg=self._c('FG_MUTED'), font=('Segoe UI', 8))
        self.my_zone.pack(side=tk.LEFT, padx=(10, 0))

        # in-tab alert banner: replaces the original blocking messagebox
        self.alert = tk.Label(self.frame, text='', bg=self._c('BG_CARD'), fg='#ffffff',
                              font=('Segoe UI', 10, 'bold'), anchor=tk.CENTER, pady=7)

        # two columns so it does not look like a stretched phone app
        cols = tk.Frame(self.frame, bg=self._c('BG'))
        cols.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 4))
        left = tk.Frame(cols, bg=self._c('BG_CARD'), highlightthickness=1,
                        highlightbackground=self._c('BORDER'))
        right = tk.Frame(cols, bg=self._c('BG_CARD'), highlightthickness=1,
                         highlightbackground=self._c('BORDER'))
        # mirrored for Arabic
        (right if rtl else left).pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3))
        (left if rtl else right).pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(3, 0))

        hdr = tk.Frame(left, bg=self._c('BG_CARD_2'))
        hdr.pack(fill=tk.X)
        self.h_state = tk.Label(hdr, text=self._t('timer.state'), bg=self._c('BG_CARD_2'),
                                fg=self._c('FG_MUTED'), font=('Segoe UI', 8, 'bold'),
                                width=14, anchor=anchor)
        self.h_state.pack(side=tk.LEFT, padx=(10, 0), pady=4)
        self.h_time = tk.Label(hdr, text=self._t('timer.time'), bg=self._c('BG_CARD_2'),
                               fg=self._c('FG_MUTED'), font=('Segoe UI', 8, 'bold'), anchor=tk.W)
        self.h_time.pack(side=tk.LEFT)
        self.h_status = tk.Label(hdr, text=self._t('timer.status'), bg=self._c('BG_CARD_2'),
                                 fg=self._c('FG_MUTED'), font=('Segoe UI', 8, 'bold'), anchor=tk.E)
        self.h_status.pack(side=tk.RIGHT, padx=(0, 10))

        for state, tzname in self.zones:
            r = tk.Frame(left, bg=self._c('BG_CARD'))
            r.pack(fill=tk.X, padx=10, pady=1)
            name = tk.Label(r, text=self._t('state.' + state), bg=self._c('BG_CARD'),
                            fg=self._c('FG'), font=('Segoe UI', 9), width=14, anchor=anchor)
            name.pack(side=tk.LEFT)
            clock = tk.Label(r, text='--:--:--', bg=self._c('BG_CARD'), fg=self._c('FG'),
                             font=('Consolas', 10))
            clock.pack(side=tk.LEFT)
            period = tk.Label(r, text='', bg=self._c('BG_CARD'), fg=self._c('FG_MUTED'),
                              font=('Segoe UI', 8))
            period.pack(side=tk.LEFT, padx=(6, 0))
            badge = tk.Label(r, text='', bg=self._c('BG_CARD'), fg=self._c('FG_MUTED'),
                             font=('Segoe UI', 8, 'bold'), anchor=tk.E)
            badge.pack(side=tk.RIGHT)
            self._rows[state] = (name, clock, period, badge, tzname)

        # right column: countdown, golden hours, days, legend, tip
        self.cd_cap = tk.Label(right, text=self._t('timer.next_golden'), bg=self._c('BG_CARD'),
                               fg=self._c('FG_MUTED'), font=('Segoe UI', 8), anchor=anchor)
        self.cd_cap.pack(fill=tk.X, padx=12, pady=(10, 0))
        self.countdown = tk.Label(right, text='--', bg=self._c('BG_CARD'), fg=self._c('ACCENT'),
                                  font=('Segoe UI', 18, 'bold'), anchor=anchor)
        self.countdown.pack(fill=tk.X, padx=12)

        self.gh_cap = tk.Label(right, text=self._t('timer.golden_hours'), bg=self._c('BG_CARD'),
                               fg=self._c('FG_MUTED'), font=('Segoe UI', 8, 'bold'), anchor=anchor)
        self.gh_cap.pack(fill=tk.X, padx=12, pady=(10, 0))
        tk.Label(right, text=self._golden_caption(), bg=self._c('BG_CARD'),
                 fg=self._c('FG'), font=('Consolas', 10), anchor=anchor
                 ).pack(fill=tk.X, padx=12)

        self.day_cap = tk.Label(right, text=self._t('timer.day_ranking'), bg=self._c('BG_CARD'),
                                fg=self._c('FG_MUTED'), font=('Segoe UI', 8, 'bold'), anchor=anchor)
        self.day_cap.pack(fill=tk.X, padx=12, pady=(10, 0))
        self.day_rank = tk.Label(right, text='', bg=self._c('BG_CARD'), fg=self._c('FG'),
                                 font=('Segoe UI', 9), anchor=anchor)
        self.day_rank.pack(fill=tk.X, padx=12)
        self.day_status = tk.Label(right, text='', bg=self._c('BG_CARD'), fg=self._c('FG_MUTED'),
                                   font=('Segoe UI', 9, 'bold'), anchor=anchor)
        self.day_status.pack(fill=tk.X, padx=12, pady=(2, 0))

        self.leg_cap = tk.Label(right, text=self._t('timer.legend'), bg=self._c('BG_CARD'),
                                fg=self._c('FG_MUTED'), font=('Segoe UI', 8, 'bold'), anchor=anchor)
        self.leg_cap.pack(fill=tk.X, padx=12, pady=(10, 0))
        self.legend_box = tk.Frame(right, bg=self._c('BG_CARD'))
        self.legend_box.pack(fill=tk.X, padx=12)
        self._legend_labels = []
        for key in ('GOLD', 'GOOD', 'OK', 'LOW'):
            lr = tk.Frame(self.legend_box, bg=self._c('BG_CARD'))
            lr.pack(fill=tk.X)
            dot = tk.Label(lr, text='\u25cf', bg=self._c('BG_CARD'),
                           fg=self.status_colour(key), font=('Segoe UI', 9))
            dot.pack(side=tk.LEFT)
            txt = tk.Label(lr, text='', bg=self._c('BG_CARD'), fg=self._c('FG_MUTED'),
                           font=('Segoe UI', 8), anchor=tk.W)
            txt.pack(side=tk.LEFT, padx=(5, 0))
            self._legend_labels.append((key, dot, txt))

        self.tip = tk.Label(right, text='', bg=self._c('BG_CARD'), fg=self._c('FG'),
                            font=('Segoe UI', 9), wraplength=260, justify=justify, anchor=anchor)
        self.tip.pack(fill=tk.X, padx=12, pady=(12, 0))

        self.notify_var = tk.BooleanVar(value=True)
        self.notify_chk = tk.Checkbutton(
            right, text=self._t('timer.notify'), variable=self.notify_var,
            bg=self._c('BG_CARD'), fg=self._c('FG_MUTED'), selectcolor=self._c('BG_CARD_2'),
            activebackground=self._c('BG_CARD'), activeforeground=self._c('FG'),
            font=('Segoe UI', 8), anchor=anchor, bd=0, highlightthickness=0)
        self.notify_chk.pack(fill=tk.X, padx=10, pady=(10, 12))

        if not self.zones:
            tk.Label(self.frame, text=self._t('timer.no_rules'),
                     bg=self._c('BG'), fg=self._c('FG_MUTED'),
                     font=('Segoe UI', 10), wraplength=520, justify=tk.CENTER
                     ).pack(pady=24)
        if _TZ_BACKEND == 'none':
            tk.Label(self.frame, text='Time zone data is unavailable on this system.',
                     bg=self._c('BG'), fg=self._c('FG_MUTED'), font=('Segoe UI', 9)
                     ).pack(pady=8)
        self._retranslate_legend()

    def _retranslate_legend(self):
        for key, _dot, txt in getattr(self, '_legend_labels', []):
            try:
                txt.configure(text='%s — %s' % (self._t('st.' + key), self._t('st.' + key + '.help')))
            except Exception:
                pass

    def retranslate(self):
        """Apply a language change in place, with no rebuild."""
        pairs = [(getattr(self, 'title_lbl', None), 'timer.title'),
                 (getattr(self, 'sub_lbl', None), 'timer.subtitle'),
                 (getattr(self, 'mine_cap', None), 'timer.your_time'),
                 (getattr(self, 'cd_cap', None), 'timer.next_golden'),
                 (getattr(self, 'gh_cap', None), 'timer.golden_hours'),
                 (getattr(self, 'day_cap', None), 'timer.day_ranking'),
                 (getattr(self, 'leg_cap', None), 'timer.legend'),
                 (getattr(self, 'h_state', None), 'timer.state'),
                 (getattr(self, 'h_time', None), 'timer.time'),
                 (getattr(self, 'h_status', None), 'timer.status'),
                 (getattr(self, 'notify_chk', None), 'timer.notify')]
        for widget, key in pairs:
            try:
                if widget is not None:
                    widget.configure(text=self._t(key))
            except Exception:
                pass
        for state, (name, _c, _p, _b, _tz) in self._rows.items():
            try:
                name.configure(text=self._t('state.' + state))
            except Exception:
                pass
        self._retranslate_legend()

    # --------------------------------------------------------- lifecycle
    def _on_destroy(self, event=None):
        if event is not None and event.widget is not self.frame:
            return
        self.stop()

    def stop(self):
        """Cancel the tick. Called on tab destroy and on app close, so no
        timer and no thread is left running."""
        self._destroyed = True
        job, self._job = self._job, None
        if job:
            try:
                self.parent.after_cancel(job)
            except Exception:
                pass

    def _visible(self):
        """Is this tab actually on screen? If not, the tick is throttled so
        it cannot compete with profile generation."""
        try:
            nb = getattr(self.host, 'notebook', None)
            tab = getattr(self.host, 'timer_tab', None)
            if nb is None or tab is None:
                return True
            return str(nb.select()) == str(tab)
        except Exception:
            return True

    def tick(self):
        if self._destroyed:
            return
        delay = self.TICK_MS
        try:
            if self._visible():
                self.update_once()
            else:
                delay = 15000        # hidden: idle, do almost nothing
        except Exception as exc:
            self._log('update failed: %r' % (exc,))
            delay = 5000
        if not self._destroyed:
            try:
                self._job = self.parent.after(delay, self.tick)
            except Exception:
                self._job = None

    # ------------------------------------------------------------ update
    def _period(self, hour):
        return self._t('timer.am') if hour < 12 else self._t('timer.pm')

    def update_once(self):
        if _tz is None:
            return
        golden, good = [], []
        now_by_zone = {}

        # your own time, from the OS
        try:
            local = datetime.now().astimezone()
            self.my_time.configure(text=local.strftime('%H:%M:%S'))
            self.my_period.configure(text=self._period(local.hour))
            self.my_zone.configure(text=str(local.tzname() or ''))
        except Exception as exc:
            self._log('local clock: %r' % (exc,))

        try:
            ref = datetime.now(_tz(self.rules.get('reference_tz') or US_REFERENCE_TZ))
        except Exception as exc:
            self._log('reference zone: %r' % (exc,))
            return
        ref_weekday, ref_hour = ref.weekday(), ref.hour

        for state, (name, clock, period, badge, tzname) in self._rows.items():
            try:
                now = datetime.now(_tz(tzname))
            except Exception as exc:
                self._log('zone %s: %r' % (tzname, exc))
                continue
            now_by_zone[state] = now
            status = apply_rules(self.rules, now.hour, now.weekday()) \
                if self.rules else get_fb_status(now.hour, now.weekday())
            colour = self.status_colour(status)
            try:
                clock.configure(text=now.strftime('%H:%M:%S'))
                period.configure(text=self._period(now.hour))
                badge.configure(text='\u25cf %s' % self._t('st.' + status), fg=colour)
            except Exception:
                continue
            if status == 'GOLD':
                golden.append(state)
            elif status == 'GOOD':
                good.append(state)

        # day status, against the US reference
        try:
            self.day_rank.configure(text='%s  >  %s  >  %s' % (
                self._t('day.2'), self._t('day.1'), self._t('day.3')))
            if ref_weekday in BEST_DAYS or ref_weekday in GOOD_DAYS:
                self.day_status.configure(
                    text=self._t('day.%d' % ref_weekday),
                    fg=self.status_colour('GOOD' if ref_weekday in BEST_DAYS else 'OK'))
            else:
                self.day_status.configure(text=self._t('timer.weekend'),
                                          fg=self.status_colour('LOW'))
            self.tip.configure(text=self._t(
                apply_tips(self.rules, ref_hour, ref_weekday) if self.rules
                else tip_key(ref_hour, ref_weekday)))
        except Exception as exc:
            self._log('day status: %r' % (exc,))

        # in-tab banner - never a modal, never topmost
        try:
            if golden:
                names = ', '.join(self._t('state.' + s) for s in golden[:3])
                self.alert.configure(text='%s — %s' % (self._t('timer.golden_now'), names),
                                     bg=self.status_colour('GOLD'), fg='#1a1a1a')
                self.alert.pack(fill=tk.X, padx=6, pady=(0, 4))
            elif good:
                names = ', '.join(self._t('state.' + s) for s in good[:3])
                self.alert.configure(text='%s — %s' % (self._t('timer.good_now'), names),
                                     bg=self.status_colour('GOOD'), fg='#ffffff')
                self.alert.pack(fill=tk.X, padx=6, pady=(0, 4))
            else:
                self.alert.pack_forget()
        except Exception as exc:
            self._log('banner: %r' % (exc,))

        # countdown - 0 minutes is a real answer, not a falsy one
        try:
            mins, _state = next_golden_minutes(
                now_by_zone, self.rules.get('golden_hours'))
            if mins is None:
                self.countdown.configure(text=self._t('timer.tomorrow'))
            elif mins < 60:
                self.countdown.configure(text='%dm' % mins)
            else:
                self.countdown.configure(text='%dh %02dm' % (mins // 60, mins % 60))
        except Exception as exc:
            self._log('countdown: %r' % (exc,))

        self._maybe_notify(golden, good)

    def _maybe_notify(self, golden, good):
        if not golden and not good:
            return
        try:
            if not self.notify_var.get():
                return
        except Exception:
            return
        now = datetime.now()
        if now.minute != 0:
            return
        key = now.strftime('%Y%m%d%H')
        if key in self._notified:
            return
        self._notified[key] = now
        # trim: the original set grew forever
        cutoff = now - timedelta(hours=24)
        for k in [k for k, v in self._notified.items() if v < cutoff]:
            self._notified.pop(k, None)
        # sound off the UI thread; everything visual is already on it
        threading.Thread(target=play_sound, daemon=True).start()
        try:
            self.host.notify_tab_badge()
        except Exception:
            pass
