#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""

"""

import os
import sys
import json
import random
import string
import shutil
import sqlite3
import subprocess
import threading
import time
import hashlib
import re
from pathlib import Path
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import platform

# Optional dependency for colored icon variants. Falls back gracefully.
try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


# ---------------------------------------------------------------------------
# v6.0  MavelyLink licensing.  Additive: the import is optional so the tool
# still starts if the module is missing, and every call site below is guarded.
# ---------------------------------------------------------------------------
try:
    import license_client as _license
except Exception:
    _license = None


# ---------------------------------------------------------------------------
# v7.0.0  Server-controlled Python tabs. Additive and optional in exactly the
# same way as the licensing import above: if the module is missing the tool
# starts with its existing tabs and nothing else changes.
# ---------------------------------------------------------------------------
try:
    import mavely_tabs as _tabs
except Exception:
    _tabs = None


def _enable_dpi_awareness():
    """Tell Windows this process scales its own UI.

    Without this the window is bitmap-stretched at 125% and 150%, which is
    blurry AND shrinks the usable logical desktop - on a 1366x768 screen at
    150% the app is handed a 911x512 workspace, which is what made the
    Generate button impossible to reach. With it, the app sees real pixels
    and scales the layout itself (see _apply_adaptive_geometry).

    Must run before the first Tk window exists, so main() calls it.
    Silent and harmless anywhere that is not Windows.
    """
    if not sys.platform.startswith('win'):
        return
    try:
        import ctypes
    except Exception:
        return
    try:
        # 1 = system DPI aware. Deliberately not 2 (per-monitor): Tk cannot
        # re-scale a live window when it is dragged between monitors, so
        # per-monitor awareness would look worse, not better.
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()      # Windows 7 / 8
    except Exception:
        pass


class AppDisabledError(RuntimeError):
    """Raised when the administrator has switched the application off.

    Kept distinct from other launch errors so no fallback path (such as the
    plain browser open used for an already-running profile) can bypass it.
    """

class ChromeProfileGenerator:
    """Generate unique Chrome profiles with hardened fingerprints"""

    # TLS cipher suites for per-profile ordering variation
    # These are real cipher suites Chrome supports; reordering changes JA3 fingerprint
    TLS_CIPHERS = [
        "TLS_AES_128_GCM_SHA256",
        "TLS_AES_256_GCM_SHA384",
        "TLS_CHACHA20_POLY1305_SHA256",
        "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256",
        "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
        "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384",
        "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",
        "TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256",
        "TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256",
        "TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA",
        "TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA",
        "TLS_RSA_WITH_AES_128_GCM_SHA256",
        "TLS_RSA_WITH_AES_256_GCM_SHA384",
        "TLS_RSA_WITH_AES_128_CBC_SHA",
        "TLS_RSA_WITH_AES_256_CBC_SHA",
    ]

    # Realistic WebGPU adapter info per GPU vendor
    WEBGPU_ADAPTERS = {
        "nvidia": {
            "vendor": "0x10de",
            "architecture": "ampere",
            "description": "NVIDIA GeForce RTX 3060",
            "device": "0x2503",
        },
        "intel": {
            "vendor": "0x8086",
            "architecture": "xe",
            "description": "Intel Iris Xe Graphics",
            "device": "0x9a49",
        },
        "amd": {
            "vendor": "0x1002",
            "architecture": "rdna2",
            "description": "AMD Radeon RX 6600",
            "device": "0x73ff",
        },
        "apple": {
            "vendor": "0x106b",
            "architecture": "apple-gpu",
            "description": "Apple M2 GPU",
            "device": "0x0000",
        },
    }

    # Realistic performance.memory values per deviceMemory tier
    MEMORY_PRESETS = {
        4: {"jsHeapSizeLimit": 2197815296, "totalJSHeapSize": 12000000, "usedJSHeapSize": 8000000},
        8: {"jsHeapSizeLimit": 4294705152, "totalJSHeapSize": 24000000, "usedJSHeapSize": 16000000},
        16: {"jsHeapSizeLimit": 8589934592, "totalJSHeapSize": 48000000, "usedJSHeapSize": 32000000},
        32: {"jsHeapSizeLimit": 17179869184, "totalJSHeapSize": 96000000, "usedJSHeapSize": 64000000},
    }

    # Font pools for realistic per-profile subsets
    FONT_POOLS = {
        "windows": [
            "Arial", "Arial Black", "Calibri", "Cambria", "Cambria Math",
            "Comic Sans MS", "Consolas", "Constantia", "Corbel", "Courier New",
            "Ebrima", "Franklin Gothic Medium", "Gabriola", "Gadugi",
            "Georgia", "Impact", "Javanese Text", "Leelawadee UI",
            "Lucida Console", "Lucida Sans Unicode", "Malgun Gothic",
            "Microsoft Himalaya", "Microsoft JhengHei", "Microsoft New Tai Lue",
            "Microsoft PhagsPa", "Microsoft Sans Serif", "Microsoft Tai Le",
            "Microsoft YaHei", "Microsoft Yi Baiti", "Mongolian Baiti",
            "MV Boli", "Myanmar Text", "Nirmala UI", "Palatino Linotype",
            "Segoe MDL2 Assets", "Segoe Print", "Segoe Script", "Segoe UI",
            "Segoe UI Emoji", "Segoe UI Historic", "Segoe UI Symbol",
            "SimSun", "Sitka Banner", "Sitka Display", "Sitka Heading",
            "Sitka Small", "Sitka Subheading", "Sitka Text", "Sylfaen",
            "Tahoma", "Times New Roman", "Trebuchet MS", "Verdana",
            "Webdings", "Wingdings", "Yu Gothic",
        ],
        "mac": [
            "American Typewriter", "Andale Mono", "Arial", "Arial Black",
            "Comic Sans MS", "Courier", "Courier New", "Georgia",
            "Helvetica", "Helvetica Neue", "Impact", "Lucida Grande",
            "Menlo", "Monaco", "Tahoma", "Times", "Times New Roman",
            "Trebuchet MS", "Verdana", "Geneva", "Futura", "Baskerville",
            "Apple Chancery", "Hoefler Text", "Optima", "Palatino",
            "Marker Felt", "Papyrus", "Herculanum", "Didot",
            "Bradley Hand", "Arial Narrow", "Big Caslon", "DIN Alternate",
            "Charter", "Copperplate", "Noteworthy", "Savoye LET",
            "SF Pro Display", "SF Pro Text", "SF Mono", "New York",
        ],
        "linux": [
            "Arial", "Arial Black", "DejaVu Sans", "DejaVu Sans Mono",
            "DejaVu Serif", "Droid Sans", "Droid Sans Mono", "Droid Serif",
            "FreeMono", "FreeSans", "FreeSerif", "Liberation Mono",
            "Liberation Sans", "Liberation Serif", "Noto Mono", "Noto Sans",
            "Noto Serif", "Ubuntu", "Ubuntu Condensed", "Ubuntu Light",
            "Ubuntu Mono", "Cantarell", "Fira Sans", "Fira Mono",
            "Hack", "Inter", "Open Sans", "Roboto", "Roboto Mono",
            "Source Sans Pro", "Source Serif Pro", "Poppins", "Oxygen",
            "Bitstream Charter", "URW Gothic", "Nimbus Sans",
            "Nimbus Roman No9 L", "Nimbus Mono PS", "Standard Symbols PS",
        ],
    }

    # v3.1: canonical pools, used to restore defaults when nothing is checked
    DEFAULT_RESOLUTIONS = [
        (1920, 1080), (1366, 768), (1536, 864), (1440, 900),
        (1280, 720), (1600, 900), (1280, 1024),
    ]
    DEFAULT_LANGUAGES = [
        'en-US', 'en-GB', 'fr-FR', 'ar-SA',
    ]

    def __init__(self):
        self.profiles_dir = self._get_profiles_directory()
        self.desktop_dir = self._get_desktop_directory()
        self.assets_dir = self._get_assets_directory()
        self.icon_path = self._get_icon_path()
        self.icons_cache_dir = self._get_icons_cache_dir()
        self.user_agents = self._get_user_agents()
        # v3.2: shared user-script library + download cache
        self.userscripts_dir = self._get_userscripts_directory()
        self.userscripts_cache_dir = self._get_userscripts_cache_directory()
        # v3.6: pools restricted to the sizes and locales actually wanted
        self.screen_resolutions = list(self.DEFAULT_RESOLUTIONS)
        self.languages = list(self.DEFAULT_LANGUAGES)
        self.timezones = [
            'America/New_York', 'America/Los_Angeles', 'America/Chicago',
            'America/Denver', 'America/Detroit', 'America/Phoenix',
            'America/Toronto', 'America/Vancouver', 'America/Mexico_City',
            'Europe/London', 'Europe/Paris', 'Europe/Berlin',
            'Europe/Madrid', 'Europe/Rome', 'Europe/Amsterdam',
            'Europe/Vienna', 'Europe/Warsaw', 'Europe/Stockholm',
            'Asia/Tokyo', 'Asia/Seoul', 'Asia/Shanghai',
            'Asia/Singapore', 'Asia/Hong_Kong', 'Asia/Bangkok',
            'Asia/Dubai', 'Asia/Mumbai', 'Asia/Jakarta',
            'Australia/Sydney', 'Australia/Melbourne',
            'Pacific/Auckland', 'America/Sao_Paulo',
        ]
        self.color_schemes = ["light", "dark"]
        self.motion_preferences = ["no-preference", "reduce"]
        self.icon_color_palette = [
            ("Classic",  [(234, 67, 53),  (251, 188, 5),  (52, 168, 83)],   (66, 133, 244)),
            ("Sunset",   [(255, 94, 77),  (255, 165, 0),  (255, 209, 102)], (220, 20, 60)),
            ("Ocean",    [(0, 119, 190),  (0, 180, 216),  (144, 224, 239)], (3, 4, 94)),
            ("Forest",   [(46, 125, 50),  (104, 159, 56), (174, 213, 129)], (27, 94, 32)),
            ("Berry",    [(136, 14, 79),  (194, 24, 91),  (236, 64, 122)],  (74, 20, 140)),
            ("MonoBlue", [(33, 150, 243), (66, 165, 245), (100, 181, 246)], (13, 71, 161)),
            ("MonoRed",  [(244, 67, 54),  (239, 83, 80),  (229, 115, 115)], (183, 28, 28)),
            ("MonoGreen",[(76, 175, 80),  (102, 187, 106), (129, 199, 132)], (27, 94, 32)),
            ("Cyber",    [(255, 0, 255),  (0, 255, 255),  (255, 255, 0)],   (138, 43, 226)),
            ("Pastel",   [(255, 179, 186), (186, 255, 201), (186, 225, 255)], (255, 218, 185)),
            ("Earth",    [(141, 110, 99), (215, 204, 200), (188, 170, 164)], (62, 39, 35)),
            ("Royal",    [(94, 53, 177),  (149, 117, 205), (179, 157, 219)], (255, 193, 7)),
            ("Mint",     [(77, 182, 172), (128, 203, 196), (178, 223, 219)], (0, 121, 107)),
            ("Coral",    [(255, 87, 34),  (255, 138, 101), (255, 171, 145)], (191, 54, 12)),
            ("Rose",     [(216, 27, 96),  (240, 98, 146), (244, 143, 177)], (136, 14, 79)),
            ("Slate",    [(96, 125, 139), (144, 164, 174), (176, 190, 197)], (38, 50, 56)),
        ]
        # v4.10: cheap insurance for the everyday browser, taken once per
        # run. Wrapped so a failure here can never stop the tool starting.
        try:
            self.backup_default_browser_state()
        except Exception:
            pass

    def _get_profiles_directory(self):
        home = str(Path.home())
        profiles_dir = os.path.join(home, 'ChromeProfiles')
        os.makedirs(profiles_dir, exist_ok=True)
        return profiles_dir

    # ------------------------------------------------------------------
    # v4.10: hard isolation. Every method that writes into, launches or
    # deletes a profile asks _assert_own_profile() first. A path that is
    # not strictly inside profiles_dir - or that lands anywhere near a
    # real browser's User Data folder - is refused and logged. This is a
    # structural block, not a convention: there is no code path that
    # writes to a profile directory without passing through here.
    # ------------------------------------------------------------------
    def real_browser_data_dirs(self):
        """Every well-known everyday-browser data directory on this machine."""
        home = str(Path.home())
        out = []
        if platform.system() == 'Windows':
            local = os.environ.get('LOCALAPPDATA') or os.path.join(
                home, 'AppData', 'Local')
            roaming = os.environ.get('APPDATA') or os.path.join(
                home, 'AppData', 'Roaming')
            for parts in (
                    ('Google', 'Chrome', 'User Data'),
                    ('Google', 'Chrome Beta', 'User Data'),
                    ('Google', 'Chrome SxS', 'User Data'),
                    ('Microsoft', 'Edge', 'User Data'),
                    ('BraveSoftware', 'Brave-Browser', 'User Data'),
                    ('Chromium', 'User Data'),
                    ('Vivaldi', 'User Data'),
                    ('Opera Software', 'Opera Stable')):
                out.append(os.path.join(local, *parts))
                out.append(os.path.join(roaming, *parts))
        elif platform.system() == 'Darwin':
            base = os.path.join(home, 'Library', 'Application Support')
            for parts in (('Google', 'Chrome'),
                          ('Microsoft Edge',),
                          ('BraveSoftware', 'Brave-Browser'),
                          ('Chromium',)):
                out.append(os.path.join(base, *parts))
        else:
            for parts in (('.config', 'google-chrome'),
                          ('.config', 'microsoft-edge'),
                          ('.config', 'BraveSoftware', 'Brave-Browser'),
                          ('.config', 'chromium')):
                out.append(os.path.join(home, *parts))
        return out

    def is_protected_path(self, path):
        """True when `path` is anywhere inside a real browser's data folder."""
        try:
            target = os.path.normcase(os.path.abspath(path))
        except Exception:
            return True
        for guarded in self.real_browser_data_dirs():
            g = os.path.normcase(os.path.abspath(guarded))
            if target == g or target.startswith(g + os.sep):
                return True
        return False

    def _assert_own_profile(self, profile_path, what='operate on'):
        """True only for a directory this tool owns. Refusals are logged.

        Two independent tests have to pass: the path must sit strictly
        inside profiles_dir, AND it must not be inside any real browser
        data directory. Either one alone would be enough in practice;
        both are used because the cost of being wrong is somebody's
        everyday browser.
        """
        try:
            target = os.path.normcase(os.path.abspath(profile_path or ''))
            root = os.path.normcase(os.path.abspath(self.profiles_dir))
        except Exception:
            return False
        if not target or target == root or not target.startswith(root + os.sep):
            self._isolation_refusal(what, profile_path,
                                    'outside %s' % self.profiles_dir)
            return False
        if self.is_protected_path(profile_path):
            self._isolation_refusal(what, profile_path,
                                    'inside a real browser data folder')
            return False
        return True

    def _isolation_refusal(self, what, path, why):
        line = ('ISOLATION: refused to %s %r - %s' % (what, path, why))
        try:
            with open(os.path.join(self.profiles_dir, '_isolation.log'),
                      'a', encoding='utf-8') as handle:
                handle.write('%s  %s\n' % (
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'), line))
        except Exception:
            pass
        try:
            print('[isolation] ' + line)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # v4.10: a small, cheap safety net for the everyday browser. Only the
    # few small files that decide whether Chrome starts cleanly are
    # copied - not the whole profile, which would be gigabytes and would
    # be unsafe to restore wholesale. Runs once at startup, keeps the
    # last few snapshots, and can never raise.
    # ------------------------------------------------------------------
    BACKUP_FILES = ('Local State',
                    os.path.join('Default', 'Preferences'),
                    os.path.join('Default', 'Secure Preferences'),
                    os.path.join('Default', 'Bookmarks'))
    BACKUP_KEEP = 5

    def default_browser_backup_dir(self):
        d = os.path.join(self.profiles_dir, '_default_browser_backup')
        os.makedirs(d, exist_ok=True)
        return d

    def backup_default_browser_state(self):
        """Snapshot the everyday browser's small startup files. Never raises."""
        saved = []
        try:
            root = self.default_browser_backup_dir()
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            for data_dir in self.real_browser_data_dirs():
                if not os.path.isdir(data_dir):
                    continue
                label = os.path.basename(os.path.dirname(data_dir)) or 'browser'
                for rel in self.BACKUP_FILES:
                    src = os.path.join(data_dir, rel)
                    if not os.path.isfile(src):
                        continue
                    dst = os.path.join(root, stamp, label, rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    try:
                        shutil.copy2(src, dst)
                        saved.append(dst)
                    except Exception:
                        pass
            snaps = sorted(d for d in os.listdir(root)
                           if os.path.isdir(os.path.join(root, d)))
            for old in snaps[:-self.BACKUP_KEEP]:
                shutil.rmtree(os.path.join(root, old), ignore_errors=True)
        except Exception:
            pass
        return saved

    def list_default_browser_backups(self):
        """Newest-first list of available snapshots."""
        try:
            root = self.default_browser_backup_dir()
            return sorted((d for d in os.listdir(root)
                           if os.path.isdir(os.path.join(root, d))),
                          reverse=True)
        except Exception:
            return []

    def restore_default_browser_state(self, stamp=None):
        """Put a snapshot back. Close every browser window first.

        Returns (restored, [paths]). The live file is renamed to
        <name>.broken before being replaced, so nothing is lost either way.
        """
        done = []
        try:
            snaps = self.list_default_browser_backups()
            if not snaps:
                return False, []
            stamp = stamp or snaps[0]
            root = os.path.join(self.default_browser_backup_dir(), stamp)
            for data_dir in self.real_browser_data_dirs():
                if not os.path.isdir(data_dir):
                    continue
                label = os.path.basename(os.path.dirname(data_dir)) or 'browser'
                for rel in self.BACKUP_FILES:
                    src = os.path.join(root, label, rel)
                    dst = os.path.join(data_dir, rel)
                    if not os.path.isfile(src):
                        continue
                    try:
                        if os.path.isfile(dst):
                            broken = dst + '.broken'
                            if os.path.exists(broken):
                                os.remove(broken)
                            os.replace(dst, broken)
                        shutil.copy2(src, dst)
                        done.append(dst)
                    except Exception:
                        pass
        except Exception:
            return False, done
        return bool(done), done

    def _get_desktop_directory(self):
        system = platform.system()
        home = str(Path.home())
        if system == 'Windows':
            desktop = os.path.join(home, 'Desktop')
        elif system == 'Darwin':
            desktop = os.path.join(home, 'Desktop')
        else:
            desktop = os.path.join(home, 'Desktop')
            if not os.path.exists(desktop):
                desktop = os.path.join(home, 'Bureau')
            if not os.path.exists(desktop):
                desktop = os.path.join(home, 'Escritorio')
        os.makedirs(desktop, exist_ok=True)
        return desktop

    def _get_assets_directory(self):
        assets_dir = os.path.join(self.profiles_dir, '_app')
        os.makedirs(assets_dir, exist_ok=True)
        return assets_dir

    def _get_icon_path(self):
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        src_icon = os.path.join(base_path, 'icon.ico')
        persistent_icon = os.path.join(self.assets_dir, 'icon.ico')
        if os.path.exists(src_icon):
            try:
                if (not os.path.exists(persistent_icon) or
                        os.path.getmtime(src_icon) > os.path.getmtime(persistent_icon)):
                    shutil.copy2(src_icon, persistent_icon)
            except Exception:
                pass
        if os.path.exists(persistent_icon):
            return persistent_icon
        if os.path.exists(src_icon):
            return src_icon
        return None

    def _get_icons_cache_dir(self):
        cache_dir = os.path.join(self.profiles_dir, '_icons')
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir

    def _get_user_agents(self):
        return [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
        ]

    def _generate_random_id(self, length=8):
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

    def _find_chrome_path(self):
        # v3.4: an explicitly chosen browser always wins
        try:
            chosen = self.browser_override()
            if chosen and os.path.exists(chosen):
                return chosen
        except Exception:
            pass
        system = platform.system()
        chrome_paths = {
            'Windows': [
                r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
                # v3.2: Chromium-family fallbacks - these still honour
                # --load-extension, which branded Chrome 142+ does not
                os.path.expandvars(r'%LOCALAPPDATA%\Chromium\Application\chrome.exe'),
                r'C:\Program Files\Chromium\Application\chrome.exe',
                r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',
                r'C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe',
                r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
            ],
            'Darwin': [
                '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                '/Applications/Chromium.app/Contents/MacOS/Chromium',
                '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
                '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
            ],
            'Linux': [
                '/usr/bin/google-chrome',
                '/usr/bin/google-chrome-stable',
                '/usr/bin/chromium',
                '/usr/bin/chromium-browser',
                '/usr/bin/brave-browser',
                '/usr/bin/microsoft-edge',
                '/snap/bin/chromium',
            ]
        }
        if system in chrome_paths:
            for path in chrome_paths[system]:
                if os.path.exists(path):
                    return path
        return None

    def _find_firefox_path(self):
        # Firefox removed: never report one so nothing can generate or
        # launch a Firefox profile by accident
        return ''

    def _find_firefox_path_disabled(self):
        """First Firefox-family executable found on this system, or ''."""
        system = platform.system()
        firefox_paths = {
            'Windows': [
                r'C:\Program Files\Mozilla Firefox\firefox.exe',
                r'C:\Program Files (x86)\Mozilla Firefox\firefox.exe',
                os.path.expandvars(r'%LOCALAPPDATA%\Mozilla Firefox\firefox.exe'),
                r'C:\Program Files\Firefox Developer Edition\firefox.exe',
                r'C:\Program Files\Firefox Nightly\firefox.exe',
                r'C:\Program Files\Mozilla Firefox ESR\firefox.exe',
            ],
            'Darwin': [
                '/Applications/Firefox.app/Contents/MacOS/firefox',
                '/Applications/Firefox Developer Edition.app/Contents/MacOS/firefox',
                '/Applications/Firefox Nightly.app/Contents/MacOS/firefox',
            ],
            'Linux': [
                '/usr/bin/firefox', '/usr/bin/firefox-esr',
                '/snap/bin/firefox', '/usr/lib/firefox/firefox',
                '/usr/lib/firefox-esr/firefox-esr',
            ],
        }.get(system, [])
        for path in firefox_paths:
            if path and os.path.exists(path):
                return path
        for name in ('firefox', 'firefox-esr'):
            found = shutil.which(name)
            if found:
                return found
        return ''

    # ------------------------------------------------------------------
    # v4.4: which engine the "Generate" switch is currently set to
    # ------------------------------------------------------------------
    def active_browser_kind(self):
        """Always 'chrome'.

        Firefox has been removed: it cannot run the user scripts,
        because injection needs Chrome's DevTools Protocol. The helper
        methods stay so nothing breaks, but Firefox can never be chosen.
        """
        return 'chrome'

    def purge_firefox_bindings(self):
        """Remove every Firefox pin an earlier build left behind."""
        removed = 0
        try:
            reg = self._load_userscript_registry()
            table = reg['settings'].get('profile_browsers', {}) or {}
            for key in list(table.keys()):
                if self.browser_engine(table[key]) == 'gecko':
                    del table[key]
                    removed += 1
            current = reg['settings'].get('browser_path', '')
            if current and self.browser_engine(current) == 'gecko':
                reg['settings']['browser_path'] = ''
                removed += 1
            reg['settings']['active_browser_kind'] = 'chrome'
            self._save_userscript_registry(reg)
            self._browser_info_cache = {}
        except Exception:
            pass
        return removed

    def reconcile_browser_kind(self):
        """Make the saved browser match the Chrome/Firefox switch.

        The switch and the browser path were stored separately, so a Firefox
        path could survive a switch back to Chrome. New profiles then followed
        the stale path and came out as Firefox.
        """
        self.purge_firefox_bindings()
        kind = 'chrome'
        current = self.browser_override()
        engine = self.browser_engine(current) if current else ''
        wanted = 'chromium'
        if current and os.path.exists(current) and engine == wanted:
            return current
        path = (self._find_firefox_path() if kind == 'firefox'
                else self._find_chrome_path())
        if path and os.path.exists(path):
            self.set_browser_override(path)
            self._browser_info_cache = {}
        return path

    def pin_profile_to_active_browser(self, profile_path, fingerprint=None):
        """Lock a new profile to the browser it was generated for.

        Pinning at creation means a later switch of the global browser can
        never turn an existing Chrome profile into a Firefox one.
        """
        key = self.profile_key(profile_path)
        path = self._find_chrome_path()
        if not path or not os.path.exists(path):
            return ''
        self.set_profile_browser(key, path)
        return path

    def set_active_browser_kind(self, kind):
        """Pick Chrome or Firefox and point the global browser at it."""
        kind = 'chrome'   # Chrome is the only engine now
        reg = self._load_userscript_registry()
        reg['settings']['active_browser_kind'] = kind
        self._save_userscript_registry(reg)
        path = self._find_firefox_path() if kind == 'firefox' else self._find_chrome_path()
        # only override when we actually found the requested engine, so an
        # accidental toggle never blanks out a working browser choice
        if path and os.path.exists(path):
            self.set_browser_override(path)
        self._browser_info_cache = {}
        return path

    # ------------------------------------------------------------------
    # Per-profile colored icon variant generation
    # ------------------------------------------------------------------
    def _pick_color_for_profile(self, profile_name):
        if not self.icon_color_palette:
            return ("Classic",
                    [(234, 67, 53), (251, 188, 5), (52, 168, 83)],
                    (66, 133, 244))
        h = 0
        for c in profile_name:
            h = (h * 131 + ord(c)) & 0xFFFFFFFF
        idx = h % len(self.icon_color_palette)
        return self.icon_color_palette[idx]

    def _draw_chrome_logo(self, size, sector_colors, center_color):
        from PIL import Image, ImageDraw
        scale = 4
        s = size * scale
        img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        box = (0, 0, s - 1, s - 1)
        sectors = [
            (-30, 90,  sector_colors[0]),
            (90,  210, sector_colors[1]),
            (210, 330, sector_colors[2]),
        ]
        for start, end, color in sectors:
            d.pieslice(box, start, end, fill=color)
        cx, cy = s // 2, s // 2
        outer_r = int(s * 0.36)
        inner_r = int(s * 0.31)
        d.ellipse((cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r),
                  fill=(255, 255, 255, 255))
        d.ellipse((cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r),
                  fill=center_color)
        return img.resize((size, size), Image.LANCZOS)

    def _generate_colored_icon(self, profile_name):
        if not _PIL_AVAILABLE:
            return None
        try:
            theme_name, sector_colors, center_color = self._pick_color_for_profile(profile_name)
            out_path = os.path.join(
                self.icons_cache_dir,
                f"{profile_name}_{theme_name}.ico"
            )
            if os.path.exists(out_path):
                return out_path
            target_sizes = [(256, 256), (128, 128), (64, 64),
                            (48, 48), (32, 32), (16, 16)]
            frames = []
            for w, h in target_sizes:
                frames.append(self._draw_chrome_logo(w, sector_colors, center_color))
            frames[0].save(out_path, format='ICO', sizes=target_sizes,
                           append_images=frames[1:])
            return out_path
        except Exception as e:
            print(f"[icon] Failed to generate Chrome-logo icon for {profile_name}: {e}")
            return None

    # ------------------------------------------------------------------
    # v3: Enhanced fingerprint generator with all new vectors
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # v3.1: user-selectable pools (languages / screen resolutions)
    # ------------------------------------------------------------------
    def set_language_pool(self, languages):
        """Restrict fingerprint generation to the given language tags.

        Pass an empty list / None to restore the full built-in pool.
        """
        if languages:
            cleaned = [l for l in languages if l]
            self.allowed_languages = list(cleaned)
            self.languages = list(cleaned)
        else:
            self.allowed_languages = None
            self.languages = list(self.DEFAULT_LANGUAGES)
        return self.languages

    def set_resolution_pool(self, resolutions):
        """Restrict fingerprint generation to the given (width, height) sizes.

        Pass an empty list / None to restore the full built-in pool.
        """
        if resolutions:
            cleaned = [(int(w), int(h)) for (w, h) in resolutions]
            self.allowed_resolutions = list(cleaned)
            self.screen_resolutions = list(cleaned)
        else:
            self.allowed_resolutions = None
            self.screen_resolutions = list(self.DEFAULT_RESOLUTIONS)
        return self.screen_resolutions

    def get_language_pool(self):
        return list(getattr(self, "allowed_languages", None) or self.languages)

    def get_resolution_pool(self):
        return list(getattr(self, "allowed_resolutions", None) or self.screen_resolutions)

    def _enforce_selection(self, fingerprint):
        """Safety net: force a generated fingerprint inside the selected pools.

        Nothing is changed when no restriction is active, so default
        behaviour is byte-for-byte identical to before.
        """
        allowed_langs = getattr(self, "allowed_languages", None)
        if allowed_langs:
            primary = fingerprint.get("language")
            if primary not in allowed_langs:
                primary = random.choice(allowed_langs)
                fingerprint["language"] = primary

            # Secondary languages may only come from the checked set.
            primary_base = primary.split("-")[0]
            bases = []
            for tag in allowed_langs:
                base = tag.split("-")[0]
                if base != primary_base and base not in bases:
                    bases.append(base)
            random.shuffle(bases)
            langs = [primary] + bases[:2]
            fingerprint["languages"] = langs

        allowed_res = getattr(self, "allowed_resolutions", None)
        if allowed_res:
            res = fingerprint.get("screen_resolution", {})
            current = (res.get("width"), res.get("height"))
            if current not in allowed_res:
                width, height = random.choice(allowed_res)
                fingerprint["screen_resolution"] = {"width": width, "height": height}
                # keep devicePixelRatio plausible for the forced resolution
                if width >= 2560:
                    fingerprint["device_pixel_ratio"] = random.choice([1.0, 1.25, 1.5, 2.0])
                elif width >= 1920:
                    fingerprint["device_pixel_ratio"] = random.choice([1.0, 1.125, 1.25])
                else:
                    fingerprint["device_pixel_ratio"] = random.choice([1.0, 1.0, 1.0, 1.25])
        return fingerprint

    # ------------------------------------------------------------------
    # v3.2: guaranteed-unique per-profile desktop icons
    # ------------------------------------------------------------------
    # Flat geometric badge vocabulary. Deliberately contains no
    # pie-sliced colour wheel and no white-ring-around-a-dot, i.e.
    # nothing that reads as the stock Chrome logo.
    ICON_SHAPES = [
        "tile", "squircle", "disc", "pill", "hex", "diamond", "triangle",
        "star", "shield", "cross", "chevron", "cutcorner", "arch", "banner",
    ]
    ICON_MARKS = [
        "letters", "letters_boxed", "bars", "dots3", "chevron_mark",
        "triangle_mark", "square_mark", "none",
    ]
    ICON_PATTERNS = [
        "none", "none", "stripes", "checker", "dots", "split",
        "corner", "rays", "band",
    ]
    ICON_SCHEMES = ["analogous", "triadic", "complementary", "split", "mono", "wide"]

    # ------------------------------------------------------------------
    # Icon look. "orb" reproduces the reference icon: a coloured disc,
    # a white ring, and a deep contrasting core - one design, a different
    # colour for every profile. Set to "badge" for the flat geometric set.
    # ------------------------------------------------------------------
    # "recolor" = take your own icon.ico / icon.png and hue-shift it so every
    #             profile gets the same artwork in its own colour (needs the
    #             file next to this script; falls back to "orb" if missing).
    # "orb"     = draw a coloured disc + white ring + dark core.
    # "badge"   = draw flat geometric badges.
    ICON_STYLE = "recolor"
    ICON_ORB_MONOGRAM = False   # True -> print the profile initials in the core

    # Extra separation knobs used when many profiles exist and hues get close.
    RECOLOR_SAT_TIERS = [1.00, 0.72, 1.25, 0.88]
    RECOLOR_VAL_TIERS = [1.00, 0.84, 0.92, 1.08]

    # Radii as a fraction of the icon radius, measured off the reference.
    ORB_RING_RANGE = (0.70, 0.78)   # outer edge of the white ring
    ORB_CORE_RANGE = (0.56, 0.64)   # the dark centre disc

    # kept for backward compatibility with any external caller
    ICON_CENTERS = ICON_MARKS

    def _base_icon_candidates(self):
        """Where a user-supplied template icon may live, best first."""
        if getattr(sys, "frozen", False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        names = ["icon.ico", "icon.png", "template.ico", "template.png"]
        paths = []
        for folder in (base_path, self.assets_dir, self.profiles_dir):
            for n in names:
                paths.append(os.path.join(folder, n))
        return paths

    def _load_base_icon(self):
        """Largest frame of the user's template icon as RGBA, or None."""
        cached = getattr(self, "_base_icon_cache", "missing")
        if cached != "missing":
            return cached
        result = None
        if _PIL_AVAILABLE:
            from PIL import Image
            for path in self._base_icon_candidates():
                if not os.path.exists(path):
                    continue
                try:
                    img = Image.open(path)
                    # .ico files hold several frames - take the biggest
                    try:
                        sizes = sorted(img.ico.sizes())
                        if sizes:
                            img = img.ico.getimage(sizes[-1])
                    except Exception:
                        pass
                    img = img.convert("RGBA")
                    if img.width < 32:
                        img = img.resize((256, 256), Image.LANCZOS)
                    if self._icon_is_colourable(img):
                        result = img
                        self._base_icon_source = path
                        break
                except Exception:
                    continue
        self._base_icon_cache = result
        return result

    @staticmethod
    def _icon_is_colourable(img):
        """True if the artwork has enough colour for a hue shift to show."""
        try:
            small = img.resize((48, 48))
            px = small.load()
            coloured = 0
            for y in range(48):
                for x in range(48):
                    r, g, b, a = px[x, y]
                    if a > 128 and (max(r, g, b) - min(r, g, b)) > 40:
                        coloured += 1
            return coloured >= 60
        except Exception:
            return False

    def _base_icon_hue(self):
        """Dominant hue of the template, so shifts are measured from it."""
        cached = getattr(self, "_base_hue_cache", None)
        if cached is not None:
            return cached
        import colorsys
        img = self._load_base_icon()
        hue = 30
        if img is not None:
            try:
                small = img.resize((64, 64))
                px = small.load()
                buckets = {}
                for y in range(64):
                    for x in range(64):
                        r, g, b, a = px[x, y]
                        if a < 160:
                            continue
                        hh, ss, vv = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
                        if ss > 0.30 and vv > 0.15:
                            key = int(hh * 360) // 5 * 5
                            buckets[key] = buckets.get(key, 0) + 1
                if buckets:
                    hue = max(buckets.items(), key=lambda kv: kv[1])[0]
            except Exception:
                pass
        self._base_hue_cache = hue
        return hue

    @staticmethod
    def _recolor_image(img, hue_shift, sat_scale=1.0, val_scale=1.0):
        """Rotate hue while keeping shape, shading, white areas and alpha.

        White / grey pixels have zero saturation, so they are untouched -
        only the coloured parts of the artwork change.
        """
        from PIL import Image
        alpha = img.split()[3]
        hsv = img.convert("RGB").convert("HSV")
        h, s, v = hsv.split()
        shift = int(round((hue_shift % 360) * 255.0 / 360.0)) % 256
        if shift:
            h = h.point(lambda p, sh=shift: (p + sh) % 256)
        if abs(sat_scale - 1.0) > 0.01:
            s = s.point(lambda p, k=sat_scale: max(0, min(255, int(p * k))))
        if abs(val_scale - 1.0) > 0.01:
            v = v.point(lambda p, k=val_scale: max(0, min(255, int(p * k))))
        out = Image.merge("HSV", (h, s, v)).convert("RGB").convert("RGBA")
        out.putalpha(alpha)
        return out

    def _recolored_icon_frames(self, spec, target_sizes):
        """Recoloured copies of the template at every requested size."""
        from PIL import Image
        base = self._load_base_icon()
        if base is None:
            return None
        seq = spec.get("seq") or 0
        sat = self.RECOLOR_SAT_TIERS[seq % len(self.RECOLOR_SAT_TIERS)]
        val = self.RECOLOR_VAL_TIERS[(seq // 2) % len(self.RECOLOR_VAL_TIERS)]
        shift = (spec["hue"] - self._base_icon_hue()) % 360
        tinted = self._recolor_image(base, shift, sat, val)
        return [tinted.resize((w, h), Image.LANCZOS) for w, h in target_sizes]

    def _icon_registry_path(self):
        return os.path.join(self.icons_cache_dir, "_icon_registry.json")

    def _load_icon_registry(self):
        """Registry of every icon design + colour already handed out.

        Shape: {"designs": {key: profile}, "meta": {"seq": n, "hues": {...}}}
        Older flat {key: profile} files are migrated automatically.
        """
        blank = {"designs": {}, "meta": {"seq": 0, "hues": {}}}
        try:
            with open(self._icon_registry_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return blank
            if "designs" not in data:  # migrate old flat format
                data = {"designs": dict(data),
                        "meta": {"seq": len(data), "hues": {}}}
            data.setdefault("designs", {})
            meta = data.setdefault("meta", {})
            meta.setdefault("seq", len(data["designs"]))
            meta.setdefault("hues", {})
            return data
        except Exception:
            return blank

    @staticmethod
    def _allocate_hue(used_hues, jitter=0):
        """Return the hue furthest away from every hue already in use.

        Picks the midpoint of the widest gap on the colour wheel, so 2
        profiles are 180 deg apart, 3 are 120 apart, 4 are 90 apart, and
        so on - adjacent icons can never end up as two similar greens.
        """
        used = sorted(set(int(h) % 360 for h in used_hues))
        if not used:
            return random.randrange(0, 360)
        if len(used) == 1:
            return (used[0] + 180 + jitter) % 360
        best_gap, best_hue = -1, used[0]
        for i in range(len(used)):
            a = used[i]
            b = used[(i + 1) % len(used)]
            gap = (b - a) % 360
            if gap == 0:
                gap = 360
            if gap > best_gap:
                best_gap, best_hue = gap, (a + gap / 2.0) % 360
        return int((best_hue + jitter) % 360)

    def _save_icon_registry(self, registry):
        try:
            with open(self._icon_registry_path(), "w", encoding="utf-8") as f:
                json.dump(registry, f, indent=1)
        except Exception:
            pass

    @staticmethod
    def _hsv_rgb(h, s, v):
        import colorsys
        r, g, b = colorsys.hsv_to_rgb((h % 360) / 360.0, max(0.0, min(1.0, s)),
                                      max(0.0, min(1.0, v)))
        return (int(r * 255), int(g * 255), int(b * 255))

    def _icon_spec_for_profile(self, profile_name, salt=0, hue=None, seq=None):
        """Deterministic visual design for one profile.

        hue : pre-allocated base hue (keeps every profile a different colour)
        seq : allocation index, used to walk shapes / brightness tiers so
              consecutive icons never look like the same badge twice.
        """
        digest = hashlib.sha256(("%s|%d" % (profile_name, salt)).encode("utf-8")).hexdigest()
        rng = random.Random(int(digest[:16], 16))

        if hue is None:
            hue = rng.randrange(0, 360)
        hue = int(hue) % 360
        scheme = rng.choice(self.ICON_SCHEMES)
        if scheme == "analogous":
            offsets = [0, rng.choice([25, 30, 35]), rng.choice([50, 60, 70])]
        elif scheme == "triadic":
            offsets = [0, 120, 240]
        elif scheme == "complementary":
            offsets = [0, 180, rng.choice([150, 200, 210])]
        elif scheme == "split":
            offsets = [0, 150, 210]
        elif scheme == "wide":
            offsets = [0, rng.randrange(80, 140), rng.randrange(180, 300)]
        else:  # mono
            offsets = [0, 0, 0]

        # Brightness / saturation tiers walk with the allocation index so
        # even close hues read as clearly different icons.
        if seq is None:
            sat = round(rng.uniform(0.45, 0.95), 2)
            val = round(rng.uniform(0.62, 0.98), 2)
        else:
            sat_tiers = [0.92, 0.62, 0.99, 0.75]
            val_tiers = [0.97, 0.78, 0.62, 0.88]
            sat = round(min(1.0, sat_tiers[seq % len(sat_tiers)]
                            + rng.uniform(-0.04, 0.04)), 2)
            val = round(min(1.0, val_tiers[(seq // 2) % len(val_tiers)]
                            + rng.uniform(-0.04, 0.04)), 2)
        colors = []
        for i, off in enumerate(offsets):
            s_adj = max(0.2, min(1.0, sat + (0.10 * i if scheme == "mono" else 0)))
            v_adj = max(0.25, min(1.0, val - (0.14 * i if scheme == "mono" else 0)))
            colors.append(self._hsv_rgb(hue + off, s_adj, v_adj))

        center_hue = (hue + rng.choice([180, 200, 160, 90, 270])) % 360
        center_color = self._hsv_rgb(center_hue, min(1.0, sat + 0.05),
                                     max(0.22, val - rng.uniform(0.20, 0.45)))
        accent_color = self._hsv_rgb((hue + rng.randrange(30, 330)) % 360,
                                     0.9, min(1.0, val + 0.05))

        alnum = [ch for ch in profile_name if ch.isalnum()]
        tail = ""
        for ch in reversed(profile_name):
            if ch.isdigit():
                tail = ch + tail
            else:
                break
        tail = tail[-2:]
        if tail and alnum:
            letters = (alnum[0] + tail).upper()      # FB_16 -> F16, FB_6 -> F6
        elif len(alnum) >= 2:
            letters = (alnum[0] + alnum[-1]).upper()
        elif alnum:
            letters = alnum[0].upper()
        else:
            letters = "P"

        # Shape / mark / pattern each walk their own shuffled permutation,
        # so every shape is used before any repeat and neighbours differ.
        if seq is None:
            shape = rng.choice(self.ICON_SHAPES)
            mark = rng.choice(self.ICON_MARKS)
            pattern = rng.choice(self.ICON_PATTERNS)
        else:
            shapes = list(self.ICON_SHAPES)
            random.Random(1000 + seq // len(shapes)).shuffle(shapes)
            shape = shapes[seq % len(shapes)]
            marks = list(self.ICON_MARKS)
            random.Random(2000 + seq // len(marks)).shuffle(marks)
            mark = marks[seq % len(marks)]
            pats = list(self.ICON_PATTERNS)
            random.Random(3000 + seq // len(pats)).shuffle(pats)
            pattern = pats[seq % len(pats)]

        # Orb style: one silhouette for every profile, colour does the work.
        if getattr(self, "ICON_STYLE", "orb") in ("orb", "recolor"):
            shape = "orb"
            # Keep every orb vivid like the reference - no washed-out or
            # muddy discs, so the colour difference stays obvious at 48px.
            sat = round(max(0.78, min(0.98, sat)), 2)
            val = round(max(0.74, min(0.96, val)), 2)
            mark = "letters" if getattr(self, "ICON_ORB_MONOGRAM", False) else "none"
            pattern = "none"

        lo, hi = self.ORB_RING_RANGE
        ring_outer = round(rng.uniform(lo, hi), 3)
        lo, hi = self.ORB_CORE_RANGE
        core = round(rng.uniform(lo, min(hi, ring_outer - 0.09)), 3)

        spec = {
            "shape": shape,
            "mark": mark,
            "center": mark,
            "pattern": pattern,
            "ring_outer": ring_outer,
            "core": core,
            "core_shift": rng.choice([-68, -95, -120, -45, 40, 70, 150, 180]),
            "core_val": round(rng.uniform(0.42, 0.60), 2),
            "grad_angle": rng.randrange(0, 360, 15),
            "grad": rng.random() < 0.72,
            "rotation": rng.randrange(0, 360, 5),
            "wedges": rng.choice([3, 4, 5, 6, 8]),
            "ring_ratio": round(rng.uniform(0.26, 0.42), 2),
            "badge": rng.random() < 0.55,
            "badge_corner": rng.choice(["se", "ne", "sw", "nw"]),
            "outline": rng.random() < 0.5,
            "colors": colors,
            "center_color": center_color,
            "accent_color": accent_color,
            "letters": letters,
            "hue": hue,
            "scheme": scheme,
            "sat": sat,
            "val": val,
            "seq": seq,
        }
        spec["key"] = "-".join(str(x) for x in (
            spec["shape"], spec["mark"], spec["pattern"], spec["rotation"],
            spec["wedges"], spec["grad_angle"], int(spec["grad"]),
            int(spec["badge"]), spec["badge_corner"], int(spec["outline"]),
            spec["hue"], spec["scheme"], sat, val,
            spec["ring_outer"], spec["core"], spec["core_shift"], spec["core_val"],
        ))
        return spec

    def _unique_icon_spec(self, profile_name):
        """Allocate a design no other profile owns, in a fresh colour.

        The hue is taken from the widest free slot on the colour wheel, so
        two profiles can never come out as, say, two similar greens.
        """
        registry = self._load_icon_registry()
        designs = registry["designs"]
        meta = registry["meta"]
        hues = meta["hues"]

        # Already allocated? keep the same icon for this profile.
        if profile_name in hues:
            seq = int(meta.get("seq_of", {}).get(profile_name, meta.get("seq", 0)))
            spec = self._icon_spec_for_profile(profile_name, seq,
                                               hue=hues[profile_name], seq=seq)
            if designs.get(spec["key"]) in (None, profile_name):
                designs[spec["key"]] = profile_name
                self._save_icon_registry(registry)
                return spec

        other_hues = [v for k, v in hues.items() if k != profile_name]
        seq = int(meta.get("seq", 0))

        spec = None
        for attempt in range(0, 240):
            hue = self._allocate_hue(other_hues, jitter=(attempt * 11) % 360 if attempt else 0)
            candidate = self._icon_spec_for_profile(profile_name,
                                                    seq * 977 + attempt,
                                                    hue=hue, seq=seq + attempt)
            owner = designs.get(candidate["key"])
            if owner is None or owner == profile_name:
                spec = candidate
                break
        if spec is None:
            spec = self._icon_spec_for_profile(
                profile_name, int(time.time() * 1000) % 1000000,
                hue=self._allocate_hue(other_hues), seq=seq)

        designs[spec["key"]] = profile_name
        hues[profile_name] = spec["hue"]
        meta.setdefault("seq_of", {})[profile_name] = seq
        meta["seq"] = seq + 1
        self._save_icon_registry(registry)
        return spec

    @staticmethod
    def _icon_polygon(cx, cy, r, rotation, sides=6):
        import math
        pts = []
        for i in range(sides):
            ang = math.radians(rotation + i * (360.0 / sides))
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
        return pts

    @staticmethod
    def _star_polygon(cx, cy, r, rotation, points=5, inner=0.46):
        import math
        pts = []
        for i in range(points * 2):
            rad = r if i % 2 == 0 else r * inner
            ang = math.radians(rotation - 90 + i * (180.0 / points))
            pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        return pts

    def _shape_mask(self, s, shape, rot):
        """Silhouette of the badge as an L-mode mask."""
        import math
        from PIL import Image, ImageDraw
        mask = Image.new("L", (s, s), 0)
        md = ImageDraw.Draw(mask)
        m = s * 0.035
        cx = cy = s / 2.0
        r = s * 0.47

        def rrect(bbox, radius):
            try:
                md.rounded_rectangle(bbox, radius=int(radius), fill=255)
            except Exception:
                md.rectangle(bbox, fill=255)

        if shape == "tile":
            rrect((m, m, s - m, s - m), s * 0.20)
        elif shape == "squircle":
            rrect((m, m, s - m, s - m), s * 0.40)
        elif shape == "disc":
            md.ellipse((m, m, s - m, s - m), fill=255)
        elif shape == "pill":
            rrect((m, s * 0.15, s - m, s * 0.85), s * 0.35)
        elif shape == "hex":
            md.polygon(self._icon_polygon(cx, cy, r, rot, 6), fill=255)
        elif shape == "diamond":
            md.polygon(self._icon_polygon(cx, cy, r, rot + 45, 4), fill=255)
        elif shape == "triangle":
            md.polygon(self._icon_polygon(cx, cy * 1.08, r, rot - 90, 3), fill=255)
        elif shape == "star":
            md.polygon(self._star_polygon(cx, cy, r, rot, 6, 0.62), fill=255)
        elif shape == "shield":
            md.polygon([(cx, m), (s - m, s * 0.24), (s - m, s * 0.58),
                        (cx, s - m), (m, s * 0.58), (m, s * 0.24)], fill=255)
        elif shape == "cross":
            t = s * 0.34
            rrect((cx - t, m, cx + t, s - m), s * 0.10)
            rrect((m, cy - t, s - m, cy + t), s * 0.10)
        elif shape == "chevron":
            md.polygon([(m, s * 0.10), (cx, s * 0.34), (s - m, s * 0.10),
                        (s - m, s * 0.62), (cx, s - m), (m, s * 0.62)], fill=255)
        elif shape == "cutcorner":
            k = s * 0.34
            md.polygon([(m, m), (s - m - k, m), (s - m, m + k),
                        (s - m, s - m), (m, s - m)], fill=255)
        elif shape == "arch":
            md.pieslice((m, m, s - m, s * 0.92), 180, 360, fill=255)
            rrect((m, cy * 0.92, s - m, s - m), s * 0.10)
        else:  # banner
            md.polygon([(s * 0.14, m), (s - s * 0.14, m), (s - s * 0.14, s - m),
                        (cx, s * 0.80), (s * 0.14, s - m)], fill=255)
        return mask

    def _plate_image(self, s, spec):
        """The coloured fill placed behind the silhouette."""
        import math
        from PIL import Image, ImageDraw
        c0, c1, c2 = spec["colors"]

        if spec.get("grad", True):
            g = 72
            small = Image.new("RGB", (g, g))
            px = small.load()
            ang = math.radians(spec.get("grad_angle", 45))
            dx, dy = math.cos(ang), math.sin(ang)
            span = abs(dx) + abs(dy)
            for y in range(g):
                for x in range(g):
                    t = ((x / (g - 1.0)) * dx + (y / (g - 1.0)) * dy)
                    t = (t + (1 if dx < 0 else 0) + (1 if dy < 0 else 0)) / span
                    t = max(0.0, min(1.0, t))
                    px[x, y] = (int(c0[0] + (c1[0] - c0[0]) * t),
                                int(c0[1] + (c1[1] - c0[1]) * t),
                                int(c0[2] + (c1[2] - c0[2]) * t))
            plate = small.resize((s, s), Image.BILINEAR).convert("RGBA")
        else:
            plate = Image.new("RGBA", (s, s), c0 + (255,))

        d = ImageDraw.Draw(plate, "RGBA")
        pat = spec.get("pattern", "none")
        acc = c2 + (215,)

        if pat == "stripes":
            w = s * 0.085
            step = int(w * 2.4)
            for x in range(-s, s * 2, max(4, step)):
                d.polygon([(x, 0), (x + w, 0), (x + w - s, s), (x - s, s)], fill=acc)
        elif pat == "checker":
            n = 5
            cell = s / float(n)
            for iy in range(n):
                for ix in range(n):
                    if (ix + iy) % 2 == 0:
                        d.rectangle((ix * cell, iy * cell,
                                     (ix + 1) * cell, (iy + 1) * cell), fill=acc)
        elif pat == "dots":
            n = 4
            cell = s / float(n)
            rr = cell * 0.24
            for iy in range(n):
                for ix in range(n):
                    px_, py_ = (ix + 0.5) * cell, (iy + 0.5) * cell
                    d.ellipse((px_ - rr, py_ - rr, px_ + rr, py_ + rr), fill=acc)
        elif pat == "split":
            d.polygon([(0, s), (s, 0), (s, s)], fill=acc)
        elif pat == "corner":
            d.polygon([(0, 0), (s * 0.62, 0), (0, s * 0.62)], fill=acc)
        elif pat == "rays":
            n = max(4, spec.get("wedges", 5))
            for i in range(n):
                a0 = spec["rotation"] + i * (360.0 / n)
                d.pieslice((-s * 0.2, -s * 0.2, s * 1.2, s * 1.2),
                           a0, a0 + (180.0 / n), fill=acc)
        elif pat == "band":
            d.rectangle((0, s * 0.40, s, s * 0.62), fill=acc)
        return plate

    @staticmethod
    def _ink_for(color):
        """Readable foreground colour for a given background."""
        lum = (0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]) / 255.0
        return (16, 18, 24, 255) if lum > 0.62 else (255, 255, 255, 255)

    def _draw_mark(self, img, s, spec):
        """Foreground glyph: monogram, bars, dots, chevron..."""
        from PIL import ImageDraw
        d = ImageDraw.Draw(img, "RGBA")
        cx = cy = s / 2.0
        mark = spec.get("mark", "letters")
        avg = tuple(sum(c[i] for c in spec["colors"]) // 3 for i in range(3))
        ink = self._ink_for(avg)

        if mark == "letters":
            self._draw_icon_letters(d, s, cx, cy, s * 0.30, spec, ink)
        elif mark == "letters_boxed":
            bw, bh = s * 0.40, s * 0.26
            plate_col = self._ink_for(avg)
            try:
                d.rounded_rectangle((cx - bw, cy - bh, cx + bw, cy + bh),
                                    radius=int(s * 0.08), fill=plate_col)
            except Exception:
                d.rectangle((cx - bw, cy - bh, cx + bw, cy + bh), fill=plate_col)
            inv = (255, 255, 255, 255) if plate_col[0] < 128 else (20, 20, 26, 255)
            self._draw_icon_letters(d, s, cx, cy, s * 0.22, spec, inv)
        elif mark == "bars":
            bw, bh = s * 0.30, s * 0.055
            for i, gap in enumerate((-1, 0, 1)):
                w = bw * (1.0 if i != 2 else 0.62)
                d.rectangle((cx - w, cy + gap * s * 0.14 - bh,
                             cx + w, cy + gap * s * 0.14 + bh), fill=ink)
        elif mark == "dots3":
            rr = s * 0.058
            for gap in (-1, 0, 1):
                x = cx + gap * s * 0.19
                d.ellipse((x - rr, cy - rr, x + rr, cy + rr), fill=ink)
        elif mark == "chevron_mark":
            t = s * 0.075
            for off in (-s * 0.10, s * 0.10):
                d.line([(cx - s * 0.16 + off, cy - s * 0.17),
                        (cx + s * 0.04 + off, cy),
                        (cx - s * 0.16 + off, cy + s * 0.17)],
                       fill=ink, width=int(t), joint="curve")
        elif mark == "triangle_mark":
            r = s * 0.21
            d.polygon(self._icon_polygon(cx + s * 0.02, cy, r, 0, 3), fill=ink)
        elif mark == "square_mark":
            r = s * 0.16
            try:
                d.rounded_rectangle((cx - r, cy - r, cx + r, cy + r),
                                    radius=int(s * 0.05), fill=ink)
            except Exception:
                d.rectangle((cx - r, cy - r, cx + r, cy + r), fill=ink)
        return img

    @staticmethod
    def _linear_gradient(s, c_from, c_to, angle):
        """Cheap smooth gradient: build small, upscale."""
        import math
        from PIL import Image
        g = 72
        small = Image.new("RGB", (g, g))
        px = small.load()
        rad = math.radians(angle)
        dx, dy = math.cos(rad), math.sin(rad)
        span = abs(dx) + abs(dy)
        for y in range(g):
            for x in range(g):
                t = (x / (g - 1.0)) * dx + (y / (g - 1.0)) * dy
                t = (t + (1 if dx < 0 else 0) + (1 if dy < 0 else 0)) / span
                t = max(0.0, min(1.0, t))
                px[x, y] = (int(c_from[0] + (c_to[0] - c_from[0]) * t),
                            int(c_from[1] + (c_to[1] - c_from[1]) * t),
                            int(c_from[2] + (c_to[2] - c_from[2]) * t))
        return small.resize((s, s), Image.BILINEAR).convert("RGBA")

    def _draw_orb(self, size, spec):
        """The reference look: colour disc + white ring + dark core."""
        from PIL import Image, ImageDraw
        scale = 4
        s = size * scale
        hue = spec.get("hue", 330)
        sat = spec.get("sat", 0.85)
        val = spec.get("val", 0.85)

        c_light = self._hsv_rgb(hue, max(0.35, sat * 0.90), min(1.0, val + 0.12))
        c_dark = self._hsv_rgb((hue + 10) % 360, min(1.0, sat + 0.06),
                               max(0.28, val - 0.28))
        core_col = self._hsv_rgb((hue + spec.get("core_shift", -68)) % 360,
                                 min(1.0, sat + 0.02), spec.get("core_val", 0.52))

        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        plate = self._linear_gradient(s, c_light, c_dark,
                                      spec.get("grad_angle", 60))
        mask = Image.new("L", (s, s), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, s - 1, s - 1), fill=255)
        img.paste(plate, (0, 0), mask)

        d = ImageDraw.Draw(img)
        c = s / 2.0
        r = s / 2.0
        ro = r * spec.get("ring_outer", 0.73)
        d.ellipse((c - ro, c - ro, c + ro, c + ro), fill=(255, 255, 255, 255))
        rc = r * spec.get("core", 0.60)
        d.ellipse((c - rc, c - rc, c + rc, c + rc), fill=core_col)

        if spec.get("mark") == "letters":
            self._draw_icon_letters(d, s, c, c, rc * 0.62, spec,
                                    (255, 255, 255, 255))
        return img.resize((size, size), Image.LANCZOS)

    def _draw_unique_logo(self, size, spec):
        """Render one frame: coloured plate -> silhouette -> glyph -> badge."""
        from PIL import Image, ImageDraw
        if spec.get("shape") == "orb":
            return self._draw_orb(size, spec)
        scale = 4
        s = size * scale
        mask = self._shape_mask(s, spec["shape"], spec["rotation"])
        plate = self._plate_image(s, spec)

        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        img.paste(plate, (0, 0), mask)

        if spec.get("outline"):
            edge = Image.new("RGBA", (s, s), (0, 0, 0, 0))
            ed = ImageDraw.Draw(edge)
            ed.rectangle((0, 0, s - 1, s - 1), fill=(255, 255, 255, 235))
            inner = mask.resize((int(s * 0.90), int(s * 0.90)), Image.LANCZOS)
            ring = mask.copy()
            ring.paste(0, (int(s * 0.05), int(s * 0.05)), inner)
            img.paste(edge, (0, 0), ring)

        self._draw_mark(img, s, spec)

        if spec.get("badge"):
            d = ImageDraw.Draw(img, "RGBA")
            br = s * 0.135
            pos = {"se": (s * 0.79, s * 0.79), "ne": (s * 0.79, s * 0.21),
                   "sw": (s * 0.21, s * 0.79), "nw": (s * 0.21, s * 0.21)}
            bx, by = pos.get(spec.get("badge_corner", "se"), (s * 0.79, s * 0.79))
            d.ellipse((bx - br * 1.3, by - br * 1.3, bx + br * 1.3, by + br * 1.3),
                      fill=(255, 255, 255, 245))
            d.ellipse((bx - br, by - br, bx + br, by + br), fill=spec["accent_color"])

        return img.resize((size, size), Image.LANCZOS)

    @staticmethod
    def _draw_icon_letters(draw, s, cx, cy, target, spec, ink=(255, 255, 255, 255)):
        """Best-effort monogram; silently skipped when no font is available."""
        try:
            from PIL import ImageFont
            font = None
            for candidate in ("arialbd.ttf", "seguisb.ttf", "segoeuib.ttf",
                              "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf",
                              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                              "/System/Library/Fonts/Supplemental/Arial Bold.ttf"):
                try:
                    fit = {1: 1.95, 2: 1.55, 3: 1.12}.get(len(spec["letters"]), 0.95)
                    font = ImageFont.truetype(candidate, max(8, int(target * fit)))
                    break
                except Exception:
                    continue
            if font is None:
                return
            txt = spec["letters"]
            try:
                l, t, r_, b = draw.textbbox((0, 0), txt, font=font)
                tw, th, ox, oy = r_ - l, b - t, l, t
            except Exception:
                tw, th = draw.textsize(txt, font=font)
                ox = oy = 0
            draw.text((cx - tw / 2.0 - ox, cy - th / 2.0 - oy), txt, font=font, fill=ink)
        except Exception:
            pass

    def _generate_unique_icon(self, profile_name):
        """Build a .ico that no other profile shares. None on failure."""
        if not _PIL_AVAILABLE:
            return None
        try:
            spec = self._unique_icon_spec(profile_name)
            safe_key = hashlib.md5(spec["key"].encode("utf-8")).hexdigest()[:10]
            out_path = os.path.join(self.icons_cache_dir,
                                    "%s__%s.ico" % (profile_name, safe_key))
            if os.path.exists(out_path):
                return out_path
            target_sizes = [(256, 256), (128, 128), (64, 64),
                            (48, 48), (32, 32), (16, 16)]
            frames = None
            if getattr(self, "ICON_STYLE", "recolor") == "recolor":
                frames = self._recolored_icon_frames(spec, target_sizes)
            if not frames:
                frames = [self._draw_unique_logo(w, spec) for w, h in target_sizes]
            frames[0].save(out_path, format="ICO", sizes=target_sizes,
                           append_images=frames[1:])
            try:
                frames[0].save(out_path[:-4] + ".png", format="PNG")
            except Exception:
                pass
            return out_path
        except Exception as e:
            print("[icon] unique icon failed for %s: %s" % (profile_name, e))
            return None

    def _release_unique_icon(self, profile_name):
        """Drop a profile's icon files + registry entries (called on delete)."""
        try:
            registry = self._load_icon_registry()
            designs = registry["designs"]
            meta = registry["meta"]
            for key in [k for k, v in designs.items() if v == profile_name]:
                del designs[key]
            meta.get("hues", {}).pop(profile_name, None)
            meta.get("seq_of", {}).pop(profile_name, None)
            self._save_icon_registry(registry)
            prefix = profile_name + "__"
            for fname in os.listdir(self.icons_cache_dir):
                if fname.startswith(prefix):
                    try:
                        os.remove(os.path.join(self.icons_cache_dir, fname))
                    except Exception:
                        pass
        except Exception:
            pass

    def icon_preview_path(self, profile_name):
        """Public helper: path of the profile's unique icon (built on demand)."""
        return self._generate_unique_icon(profile_name)

    def _generate_fingerprint(self):
        """Generate unique browser fingerprint with v3 hardening"""
        resolution = random.choice(self.screen_resolutions)
        ua = random.choice(self.user_agents)

        # Derive platform + renderer pool from UA (ensures consistency)
        if 'Mac OS X' in ua:
            platform_str = 'MacIntel'
            renderer_pool = [
                'ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)',
                'ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)',
                'ANGLE (Apple, ANGLE Metal Renderer: Apple M3, Unspecified Version)',
                'ANGLE (Intel Inc., Intel(R) Iris(TM) Plus Graphics, OpenGL 4.1)',
            ]
            font_platform = "mac"
            webgpu_vendor = "apple"
        elif 'Linux' in ua and 'Android' not in ua:
            platform_str = 'Linux x86_64'
            renderer_pool = [
                'ANGLE (Mesa, llvmpipe (LLVM 15.0.7, 256 bits), OpenGL 4.5)',
                'ANGLE (Intel, Mesa Intel(R) UHD Graphics 620, OpenGL 4.6)',
                'ANGLE (NVIDIA, NVIDIA GeForce GTX 1060, OpenGL 4.6)',
                'ANGLE (AMD, AMD Radeon RX 580, OpenGL 4.6)',
            ]
            font_platform = "linux"
            webgpu_vendor = random.choice(["intel", "nvidia", "amd"])
        else:
            platform_str = 'Win32'
            renderer_pool = [
                'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)',
                'ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)',
                'ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Direct3D11 vs_5_0 ps_5_0, D3D11)',
                'ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)',
                'ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)',
                'ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)',
                'ANGLE (AMD, AMD Radeon RX 6600 Direct3D11 vs_5_0 ps_5_0, D3D11)',
            ]
            font_platform = "windows"
            webgpu_vendor = random.choice(["nvidia", "intel", "amd"])

        webgl_renderer = random.choice(renderer_pool)
        webgl_vendor = f"Google Inc. ({webgpu_vendor.upper()})"

        # Language selection
        primary_lang = random.choice(self.languages)
        # Build realistic secondary languages
        lang_base = primary_lang.split('-')[0]
        languages = [primary_lang]
        if lang_base != 'en':
            languages.append('en')
        if random.random() < 0.3:
            languages.append(random.choice(['fr', 'de', 'es', 'pt', 'zh']))

        # Device memory + hardware concurrency (must correlate)
        device_memory = random.choice([4, 8, 16, 32])
        if device_memory <= 4:
            hw_concurrency = random.choice([2, 4])
        elif device_memory <= 8:
            hw_concurrency = random.choice([4, 8])
        elif device_memory <= 16:
            hw_concurrency = random.choice([8, 12, 16])
        else:
            hw_concurrency = random.choice([16, 24, 32])

        # Color depth and pixel ratio (correlate with resolution)
        color_depth = random.choice([24, 30, 48])
        if resolution[0] >= 2560:
            device_pixel_ratio = random.choice([1.0, 1.25, 1.5, 2.0])
        elif resolution[0] >= 1920:
            device_pixel_ratio = random.choice([1.0, 1.125, 1.25])
        else:
            device_pixel_ratio = random.choice([1.0, 1.0, 1.0, 1.25])

        # Per-profile font subset (realistic for chosen platform)
        platform_fonts = self.FONT_POOLS.get(font_platform, self.FONT_POOLS["windows"])
        num_fonts = random.randint(12, min(28, len(platform_fonts)))
        chosen_fonts = sorted(random.sample(platform_fonts, k=num_fonts))

        # Plugins (Windows has more than Mac/Linux)
        plugin_pool = [
            'PDF Viewer', 'Chrome PDF Viewer', 'Chromium PDF Viewer',
            'Microsoft Edge PDF Viewer', 'WebKit built-in PDF',
        ]
        if font_platform == "windows":
            plugin_pool.extend(['Native Client', 'Widevine Content Decryption Module'])
        chosen_plugins = random.sample(plugin_pool, k=random.randint(2, min(4, len(plugin_pool))))

        # Battery
        battery = {
            "charging": random.choice([True, False]),
            "chargingTime": random.choice([0, random.randint(600, 7200)]),
            "dischargingTime": random.choice([float('inf'), random.randint(1800, 28800)]),
            "level": round(random.uniform(0.2, 1.0), 2),
        }

        # Connection
        connection = {
            "effectiveType": random.choice(['4g', '4g', '4g', '4g', '3g']),
            "rtt": random.choice([25, 50, 75, 100, 150]),
            "downlink": round(random.uniform(2.0, 20.0), 1),
            "saveData": False,
            "type": random.choice(["wifi", "ethernet", "wifi", "wifi"]),
        }

        # Timezone
        tz = random.choice(self.timezones)

        # Color scheme + motion preference
        color_scheme = random.choice(self.color_schemes)
        motion_pref = random.choice(self.motion_preferences)

        # v3: TLS cipher ordering for JA3 variation
        tls_order = random.sample(self.TLS_CIPHERS, k=len(self.TLS_CIPHERS))

        # v3: WebGPU adapter
        webgpu_info = self.WEBGPU_ADAPTERS[webgpu_vendor].copy()

        # v3: Memory info (correlated with deviceMemory)
        mem_info = self.MEMORY_PRESETS.get(device_memory, self.MEMORY_PRESETS[8]).copy()
        # Add realistic jitter
        mem_info["totalJSHeapSize"] += random.randint(0, 5000000)
        mem_info["usedJSHeapSize"] += random.randint(0, 3000000)

        # v3: Speech synthesis voices per platform
        speech_voices = self._generate_speech_voices(font_platform)

        fingerprint = {
            'user_agent': ua,
            'screen_resolution': {
                'width': resolution[0],
                'height': resolution[1]
            },
            'language': primary_lang,
            'languages': languages,
            'timezone': tz,
            'platform': platform_str,
            'hardware_concurrency': hw_concurrency,
            'device_memory': device_memory,
            'color_depth': color_depth,
            'device_pixel_ratio': device_pixel_ratio,
            'canvas_hash': self._generate_random_id(16),
            'audio_noise': round(random.uniform(0.00001, 0.0005), 6),
            'webgl_vendor': webgl_vendor,
            'webgl_renderer': webgl_renderer,
            'webgpu': webgpu_info,
            'fonts': chosen_fonts,
            'plugins': chosen_plugins,
            'battery': battery,
            'connection': connection,
            'do_not_track': random.choice(['1', None]),
            'color_scheme': color_scheme,
            'motion_preference': motion_pref,
            'tls_cipher_order': tls_order,
            'memory': mem_info,
            'speech_voices': speech_voices,
            'font_platform': font_platform,
        }
        return fingerprint

    def _generate_speech_voices(self, platform):
        """Generate realistic SpeechSynthesisVoice list per platform"""
        base_voices = [
            {"name": "Microsoft David - English (United States)", "lang": "en-US", "local": True, "default": True},
            {"name": "Microsoft Zira - English (United States)", "lang": "en-US", "local": True, "default": False},
        ]
        if platform == "mac":
            base_voices = [
                {"name": "Samantha", "lang": "en-US", "local": True, "default": True},
                {"name": "Alex", "lang": "en-US", "local": True, "default": False},
                {"name": "Victoria", "lang": "en-GB", "local": True, "default": False},
            ]
        elif platform == "linux":
            base_voices = [
                {"name": "English (America)", "lang": "en-US", "local": True, "default": True},
                {"name": "English (Great Britain)", "lang": "en-GB", "local": True, "default": False},
            ]
        # Add Google voices (present on all platforms with Chrome)
        google_voices = [
            {"name": "Google US English", "lang": "en-US", "local": False, "default": False},
            {"name": "Google UK English Female", "lang": "en-GB", "local": False, "default": False},
            {"name": "Google UK English Male", "lang": "en-GB", "local": False, "default": False},
        ]
        return base_voices + google_voices


    # ------------------------------------------------------------------
    # v3: Enhanced fingerprint extension builder
    # ------------------------------------------------------------------
    def _build_fingerprint_extension(self, profile_path, fingerprint):
        """Generate a Chrome MV3 extension with v3 hardening."""
        if not self._assert_own_profile(profile_path, 'write an extension into'):
            return None
        try:
            ext_dir = os.path.join(profile_path, '_fingerprint_extension')
            os.makedirs(ext_dir, exist_ok=True)

            manifest = {
                "manifest_version": 3,
                "name": "Profile Environment",
                "version": "1.0",
                "description": "Browser environment normalization.",
                "content_scripts": [{
                    "matches": ["<all_urls>"],
                    "js": ["loader.js"],
                    "run_at": "document_start",
                    "all_frames": True,
                    "match_about_blank": True,
                    "world": "ISOLATED"
                }],
                "web_accessible_resources": [{
                    "resources": ["inject.js"],
                    "matches": ["<all_urls>"]
                }],
                "host_permissions": ["<all_urls>"]
            }
            with open(os.path.join(ext_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2)

            loader_js = (
                "(() => {\n"
                "  try {\n"
                "    const url = chrome.runtime.getURL('inject.js');\n"
                "    const xhr = new XMLHttpRequest();\n"
                "    xhr.open('GET', url, false);\n"
                "    xhr.send();\n"
                "    const code = xhr.responseText;\n"
                "    const s = document.createElement('script');\n"
                "    s.textContent = code;\n"
                "    (document.head || document.documentElement).prepend(s);\n"
                "    s.remove();\n"
                "  } catch (e) {}\n"
                "})();\n"
            )
            with open(os.path.join(ext_dir, 'loader.js'), 'w', encoding='utf-8') as f:
                f.write(loader_js)

            # Extract Chrome version from UA
            ua_string = fingerprint['user_agent']
            import re as _re
            m = _re.search(r'Chrome/(\d+)\.(\d+)\.(\d+)\.(\d+)', ua_string)
            if m:
                chrome_full = f"{m.group(1)}.{m.group(2)}.{m.group(3)}.{m.group(4)}"
                chrome_major = m.group(1)
            else:
                chrome_full = "135.0.0.0"
                chrome_major = "135"

            if 'Mac OS X' in ua_string:
                ch_platform = 'macOS'
                ch_mobile = False
            elif 'Linux' in ua_string and 'Android' not in ua_string:
                ch_platform = 'Linux'
                ch_mobile = False
            elif 'Android' in ua_string:
                ch_platform = 'Android'
                ch_mobile = True
            else:
                ch_platform = 'Windows'
                ch_mobile = False

            data = {
                "userAgent": ua_string,
                "language": fingerprint['language'],
                "languages": fingerprint.get('languages', [fingerprint['language'], 'en']),
                "platform": fingerprint['platform'],
                "hardwareConcurrency": fingerprint['hardware_concurrency'],
                "deviceMemory": fingerprint['device_memory'],
                "devicePixelRatio": fingerprint['device_pixel_ratio'],
                "screen": {
                    "width": fingerprint['screen_resolution']['width'],
                    "height": fingerprint['screen_resolution']['height'],
                    "availWidth": fingerprint['screen_resolution']['width'],
                    "availHeight": fingerprint['screen_resolution']['height'] - 40,
                    "colorDepth": fingerprint['color_depth'],
                    "pixelDepth": fingerprint['color_depth'],
                },
                "timezone": fingerprint['timezone'],
                "webglVendor": fingerprint['webgl_vendor'],
                "webglRenderer": fingerprint.get('webgl_renderer', 'ANGLE (Generic)'),
                "webgpu": fingerprint.get('webgpu', {}),
                "canvasNoise": fingerprint['canvas_hash'],
                "audioNoise": fingerprint.get('audio_noise', 0.0001),
                "doNotTrack": fingerprint.get('do_not_track'),
                "colorScheme": fingerprint.get('color_scheme', 'light'),
                "motionPreference": fingerprint.get('motion_preference', 'no-preference'),
                "fonts": fingerprint.get('fonts', []),
                "plugins": fingerprint.get('plugins', []),
                "battery": fingerprint.get('battery', {
                    "charging": True, "chargingTime": 0,
                    "dischargingTime": float('inf'), "level": 1.0
                }),
                "connection": fingerprint.get('connection', {
                    "effectiveType": "4g", "rtt": 50,
                    "downlink": 10.0, "saveData": False, "type": "wifi"
                }),
                "memory": fingerprint.get('memory', {
                    "jsHeapSizeLimit": 4294705152,
                    "totalJSHeapSize": 24000000,
                    "usedJSHeapSize": 16000000,
                }),
                "speechVoices": fingerprint.get('speech_voices', []),
                "vendor": "Google Inc.",
                "userAgentData": {
                    "brands": [
                        {"brand": "Google Chrome", "version": chrome_major},
                        {"brand": "Chromium", "version": chrome_major},
                        {"brand": "Not_A Brand", "version": "24"},
                    ],
                    "fullVersionList": [
                        {"brand": "Google Chrome", "version": chrome_full},
                        {"brand": "Chromium", "version": chrome_full},
                        {"brand": "Not_A Brand", "version": "24.0.0.0"},
                    ],
                    "mobile": ch_mobile,
                    "platform": ch_platform,
                    "platformVersion": "15.0.0" if ch_platform == "Windows" else "10.15.7",
                    "architecture": "x86",
                    "bitness": "64",
                    "model": "",
                    "wow64": False,
                },
            }
            if data['battery'].get('dischargingTime') == float('inf'):
                data['battery']['dischargingTime'] = -1

            # v3.3: guarded so the extension copy and the CDP copy of this
            # same script never both apply in one document
            inject_js = self._guard_once(self._fingerprint_inject_js(data),
                                         self._fp_guard_key(profile_path))
            with open(os.path.join(ext_dir, 'inject.js'), 'w', encoding='utf-8') as f:
                f.write(inject_js)
            return ext_dir
        except Exception as e:
            print(f"[ext] Failed to build fingerprint extension: {e}")
            return None

    def _fingerprint_inject_js(self, data):
        """Return the v3 enhanced JS source for fingerprint override."""
        embedded = json.dumps(data)
        return r"""
(function () {
  'use strict';
  try {
    const FP = """ + embedded + r""";
    if (FP.battery && FP.battery.dischargingTime === -1) {
      FP.battery.dischargingTime = Infinity;
    }

    // Seeded RNG for deterministic noise
    const seedFrom = (str) => {
      let h = 2166136261 >>> 0;
      for (let i = 0; i < str.length; i++) {
        h ^= str.charCodeAt(i);
        h = Math.imul(h, 16777619);
      }
      return h >>> 0;
    };
    const mulberry32 = (seed) => {
      let s = seed >>> 0;
      return () => {
        s = (s + 0x6D2B79F5) >>> 0;
        let t = s;
        t = Math.imul(t ^ (t >>> 15), t | 1);
        t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
        return (((t ^ (t >>> 14)) >>> 0) / 4294967296);
      };
    };

    const define = (obj, key, value) => {
      try {
        Object.defineProperty(obj, key, {
          get: () => value, configurable: true, enumerable: true,
        });
      } catch (e) {}
    };

    const replaceMethod = (proto, name, replacement) => {
      try {
        const original = proto[name];
        if (typeof original !== 'function') return null;
        const origStr = Function.prototype.toString.call(original);
        Object.defineProperty(replacement, 'toString', {
          value: () => origStr, configurable: true,
        });
        Object.defineProperty(replacement, 'name', {
          value: original.name, configurable: true,
        });
        proto[name] = replacement;
        return original;
      } catch (e) { return null; }
    };

    // ===== navigator overrides =====
    try {
      define(navigator, 'userAgent', FP.userAgent);
      define(navigator, 'appVersion', FP.userAgent.replace(/^Mozilla\//, ''));
      define(navigator, 'platform', FP.platform);
      define(navigator, 'language', FP.language);
      define(navigator, 'languages', Object.freeze(FP.languages.slice()));
      define(navigator, 'hardwareConcurrency', FP.hardwareConcurrency);
      define(navigator, 'deviceMemory', FP.deviceMemory);
      define(navigator, 'vendor', FP.vendor);
      define(navigator, 'doNotTrack', FP.doNotTrack);
      define(navigator, 'deviceMemory', FP.deviceMemory);
      try {
        Object.defineProperty(navigator, 'webdriver', {
          get: () => undefined, configurable: true,
        });
      } catch (e) {}
      // Wipe CDP/Selenium globals
      const wipeList = [
        'cdc_adoQpoasnfa76pfcZLmcfl_Array',
        'cdc_adoQpoasnfa76pfcZLmcfl_Promise',
        'cdc_adoQpoasnfa76pfcZLmcfl_Symbol',
        'cdc_adoQpoasnfa76pfcZLmcfl_JSON',
        'cdc_adoQpoasnfa76pfcZLmcfl_Object',
        'cdc_adoQpoasnfa76pfcZLmcfl_Proxy',
        '$cdc_asdjflasutopfhvcZLmcfl_',
        '$chrome_asyncScriptInfo',
        '__webdriver_evaluate', '__selenium_evaluate',
        '__webdriver_script_function', '__webdriver_script_func',
        '__webdriver_script_fn', '__fxdriver_evaluate',
        '__driver_unwrapped', '__webdriver_unwrapped',
        '__driver_evaluate', '__selenium_unwrapped',
        '__fxdriver_unwrapped', '__webdriver_script_result',
        '__lastWatirAlert', '__lastWatirConfirm', '__lastWatirPrompt',
        'callPhantom', '_phantom', 'callSelenium', '_selenium',
      ];
      wipeList.forEach(k => {
        try { delete window[k]; } catch (e) {}
      });
      // Hide automation from Navigator prototype chain
      try {
        if (Navigator.prototype.webdriver !== undefined) {
          Object.defineProperty(Navigator.prototype, 'webdriver', {
            get: () => undefined, configurable: true,
          });
        }
      } catch (e) {}
    } catch (e) {}

    // ===== navigator.keyboard =====
    try {
      if (!navigator.keyboard) {
        define(navigator, 'keyboard', {
          getLayoutMap: () => Promise.resolve({
            has: (k) => true,
            get: (k) => k,
            entries: () => [].entries(),
            keys: () => [].keys(),
            values: () => [].values(),
            forEach: () => {},
            size: 0,
          }),
          addEventListener: () => {},
          removeEventListener: () => {},
          dispatchEvent: () => false,
        });
      }
    } catch (e) {}

    // ===== navigator.mediaCapabilities =====
    try {
      if (!navigator.mediaCapabilities) {
        define(navigator, 'mediaCapabilities', {
          decodingInfo: (c) => Promise.resolve({
            supported: true, smooth: true, powerEfficient: true,
          }),
          encodingInfo: (c) => Promise.resolve({
            supported: true, smooth: true, powerEfficient: false,
          }),
        });
      }
    } catch (e) {}

    // ===== Bluetooth / USB / Serial / HID nulling =====
    try {
      if (!navigator.bluetooth) define(navigator, 'bluetooth', undefined);
      if (!navigator.usb) define(navigator, 'usb', undefined);
      if (!navigator.serial) define(navigator, 'serial', undefined);
      if (!navigator.hid) define(navigator, 'hid', undefined);
    } catch (e) {}

    // ===== User-Agent Client Hints =====
    try {
      if (FP.userAgentData) {
        const uad = {
          brands: FP.userAgentData.brands,
          mobile: FP.userAgentData.mobile,
          platform: FP.userAgentData.platform,
          getHighEntropyValues: function (hints) {
            const result = {
              brands: FP.userAgentData.brands,
              mobile: FP.userAgentData.mobile,
              platform: FP.userAgentData.platform,
            };
            (hints || []).forEach((h) => {
              if (h === 'architecture') result.architecture = FP.userAgentData.architecture;
              else if (h === 'bitness') result.bitness = FP.userAgentData.bitness;
              else if (h === 'model') result.model = FP.userAgentData.model;
              else if (h === 'platformVersion') result.platformVersion = FP.userAgentData.platformVersion;
              else if (h === 'uaFullVersion') result.uaFullVersion = FP.userAgentData.fullVersionList[0].version;
              else if (h === 'fullVersionList') result.fullVersionList = FP.userAgentData.fullVersionList;
              else if (h === 'wow64') result.wow64 = FP.userAgentData.wow64;
            });
            return Promise.resolve(result);
          },
          toJSON: function () {
            return {
              brands: FP.userAgentData.brands,
              mobile: FP.userAgentData.mobile,
              platform: FP.userAgentData.platform,
            };
          },
        };
        Object.defineProperty(navigator, 'userAgentData', {
          get: () => uad, configurable: true,
        });
      }
    } catch (e) {}

    // ===== screen overrides =====
    try {
      define(screen, 'width', FP.screen.width);
      define(screen, 'height', FP.screen.height);
      define(screen, 'availWidth', FP.screen.availWidth);
      define(screen, 'availHeight', FP.screen.availHeight);
      define(screen, 'colorDepth', FP.screen.colorDepth);
      define(screen, 'pixelDepth', FP.screen.pixelDepth);
      define(window, 'outerWidth', FP.screen.width);
      define(window, 'outerHeight', FP.screen.height);
      define(window, 'devicePixelRatio', FP.devicePixelRatio);
      define(window, 'screenLeft', 0);
      define(window, 'screenTop', 0);
      define(window, 'screenX', 0);
      define(window, 'screenY', 0);
    } catch (e) {}

    // ===== Timezone =====
    try {
      const _origRO = Intl.DateTimeFormat.prototype.resolvedOptions;
      replaceMethod(Intl.DateTimeFormat.prototype, 'resolvedOptions', function () {
        const r = _origRO.call(this);
        r.timeZone = FP.timezone;
        return r;
      });
      const tzOffsets = {
        'America/New_York': 300, 'America/Los_Angeles': 480,
        'America/Chicago': 360, 'America/Denver': 420,
        'America/Detroit': 300, 'America/Phoenix': 420,
        'America/Toronto': 300, 'America/Vancouver': 480,
        'America/Mexico_City': 360, 'America/Sao_Paulo': 180,
        'Europe/London': 0, 'Europe/Paris': -60,
        'Europe/Berlin': -60, 'Europe/Madrid': -60,
        'Europe/Rome': -60, 'Europe/Amsterdam': -60,
        'Europe/Vienna': -60, 'Europe/Warsaw': -60,
        'Europe/Stockholm': -60,
        'Asia/Tokyo': -540, 'Asia/Seoul': -540,
        'Asia/Shanghai': -480, 'Asia/Singapore': -480,
        'Asia/Hong_Kong': -480, 'Asia/Bangkok': -420,
        'Asia/Dubai': -240, 'Asia/Mumbai': -330,
        'Asia/Jakarta': -420,
        'Australia/Sydney': -660, 'Australia/Melbourne': -660,
        'Pacific/Auckland': -780,
      };
      const off = (FP.timezone in tzOffsets) ? tzOffsets[FP.timezone] : 0;
      replaceMethod(Date.prototype, 'getTimezoneOffset', function () {
        return off;
      });
    } catch (e) {}

    // ===== Intl.* locale overrides =====
    try {
      const origDN = Intl.DisplayNames;
      if (origDN) {
        const PatchedDN = function(locales, options) {
          return new origDN(FP.language, options);
        };
        PatchedDN.prototype = origDN.prototype;
        PatchedDN.supportedLocalesOf = origDN.supportedLocalesOf;
        Intl.DisplayNames = PatchedDN;
      }
      const origNF = Intl.NumberFormat;
      const PatchedNF = function(locales, options) {
        return new origNF(FP.language, options);
      };
      PatchedNF.prototype = origNF.prototype;
      PatchedNF.supportedLocalesOf = origNF.supportedLocalesOf;
      Intl.NumberFormat = PatchedNF;
      const origDF = Intl.DateTimeFormat;
      const PatchedDF = function(locales, options) {
        return new origDF(FP.language, options);
      };
      PatchedDF.prototype = origDF.prototype;
      PatchedDF.supportedLocalesOf = origDF.supportedLocalesOf;
      Intl.DateTimeFormat = PatchedDF;
      const origLF = Intl.ListFormat;
      if (origLF) {
        const PatchedLF = function(locales, options) {
          return new origLF(FP.language, options);
        };
        PatchedLF.prototype = origLF.prototype;
        PatchedLF.supportedLocalesOf = origLF.supportedLocalesOf;
        Intl.ListFormat = PatchedLF;
      }
      const origRTF = Intl.RelativeTimeFormat;
      if (origRTF) {
        const PatchedRTF = function(locales, options) {
          return new origRTF(FP.language, options);
        };
        PatchedRTF.prototype = origRTF.prototype;
        PatchedRTF.supportedLocalesOf = origRTF.supportedLocalesOf;
        Intl.RelativeTimeFormat = PatchedRTF;
      }
    } catch (e) {}

    // ===== WebGL vendor/renderer =====
    try {
      const patchGL = (proto) => {
        const origGetParameter = proto.getParameter;
        replaceMethod(proto, 'getParameter', function (p) {
          if (p === 37445) return FP.webglVendor;
          if (p === 37446) return FP.webglRenderer;
          if (p === 7936)  return FP.webglVendor;
          if (p === 7937)  return FP.webglRenderer;
          return origGetParameter.apply(this, arguments);
        });
      };
      if (window.WebGLRenderingContext) patchGL(WebGLRenderingContext.prototype);
      if (window.WebGL2RenderingContext) patchGL(WebGL2RenderingContext.prototype);
    } catch (e) {}

    // ===== WebGPU spoofing =====
    try {
      if (navigator.gpu && FP.webgpu) {
        const origRequestAdapter = navigator.gpu.requestAdapter;
        replaceMethod(navigator.gpu, 'requestAdapter', async function (options) {
          const adapter = await origRequestAdapter.apply(this, arguments);
          if (!adapter) return null;
          const origRequestDevice = adapter.requestDevice;
          adapter.requestDevice = async function (desc) {
            const device = await origRequestDevice.apply(this, arguments);
            return device;
          };
          adapter.info = {
            vendor: FP.webgpu.vendor || '',
            architecture: FP.webgpu.architecture || '',
            device: FP.webgpu.device || '',
            description: FP.webgpu.description || '',
          };
          return adapter;
        });
      }
    } catch (e) {}

    // ===== Canvas — stable deterministic noise =====
    try {
      const baseSeed = seedFrom(FP.canvasNoise);
      const noiseCanvas = (canvas) => {
        try {
          const ctx = canvas.getContext('2d');
          if (!ctx || !canvas.width || !canvas.height) return;
          const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
          const rng = mulberry32(baseSeed ^ canvas.width ^ (canvas.height << 16));
          for (let i = 0; i < img.data.length; i += 4) {
            if (rng() < 0.002) img.data[i]   = (img.data[i]   ^ 1) & 0xff;
            if (rng() < 0.002) img.data[i+1] = (img.data[i+1] ^ 1) & 0xff;
            if (rng() < 0.002) img.data[i+2] = (img.data[i+2] ^ 1) & 0xff;
          }
          ctx.putImageData(img, 0, 0);
        } catch (e) {}
      };
      const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
      replaceMethod(HTMLCanvasElement.prototype, 'toDataURL', function () {
        noiseCanvas(this);
        return origToDataURL.apply(this, arguments);
      });
      const origToBlob = HTMLCanvasElement.prototype.toBlob;
      replaceMethod(HTMLCanvasElement.prototype, 'toBlob', function () {
        noiseCanvas(this);
        return origToBlob.apply(this, arguments);
      });
      const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
      replaceMethod(CanvasRenderingContext2D.prototype, 'getImageData', function () {
        const result = origGetImageData.apply(this, arguments);
        try {
          const rng = mulberry32(baseSeed ^ result.width ^ (result.height << 16));
          for (let i = 0; i < result.data.length; i += 4) {
            if (rng() < 0.002) result.data[i]   = (result.data[i]   ^ 1) & 0xff;
            if (rng() < 0.002) result.data[i+1] = (result.data[i+1] ^ 1) & 0xff;
            if (rng() < 0.002) result.data[i+2] = (result.data[i+2] ^ 1) & 0xff;
          }
        } catch (e) {}
        return result;
      });
    } catch (e) {}

    // ===== Audio — stable per-profile noise =====
    try {
      const audioSeed = seedFrom(String(FP.audioNoise) + FP.canvasNoise);
      const origGCD = AudioBuffer.prototype.getChannelData;
      replaceMethod(AudioBuffer.prototype, 'getChannelData', function (channel) {
        const data = origGCD.apply(this, arguments);
        try {
          const rng = mulberry32(audioSeed ^ (channel || 0));
          for (let i = 0; i < data.length; i += 1000) {
            data[i] = data[i] + (rng() - 0.5) * 1e-7;
          }
        } catch (e) {}
        return data;
      });
      const origCFD = OfflineAudioContext.prototype.createDynamicsCompressor;
      if (origCFD) {
        replaceMethod(OfflineAudioContext.prototype, 'createDynamicsCompressor', function () {
          const compressor = origCFD.apply(this, arguments);
          const origGT = compressor.getFloatTimeDomainData || compressor.getTimeDomainData;
          if (origGT) {
            replaceMethod(compressor, origGT.name, function () {
              const data = origGT.apply(this, arguments);
              try {
                const rng = mulberry32(audioSeed ^ 0x42);
                for (let i = 0; i < data.length; i += 100) {
                  data[i] = data[i] + (rng() - 0.5) * 1e-8;
                }
              } catch (e) {}
              return data;
            });
          }
          return compressor;
        });
      }
    } catch (e) {}

    // ===== Battery =====
    try {
      if (navigator.getBattery) {
        const fake = {
          charging: FP.battery.charging,
          chargingTime: FP.battery.chargingTime,
          dischargingTime: FP.battery.dischargingTime,
          level: FP.battery.level,
          addEventListener: function () {},
          removeEventListener: function () {},
          dispatchEvent: function () { return false; },
          onchargingchange: null,
          onchargingtimechange: null,
          ondischargingtimechange: null,
          onlevelchange: null,
        };
        replaceMethod(navigator, 'getBattery', function () {
          return Promise.resolve(fake);
        });
      }
    } catch (e) {}

    // ===== Network connection info =====
    try {
      if (navigator.connection) {
        define(navigator.connection, 'effectiveType', FP.connection.effectiveType);
        define(navigator.connection, 'rtt', FP.connection.rtt);
        define(navigator.connection, 'downlink', FP.connection.downlink);
        define(navigator.connection, 'saveData', FP.connection.saveData);
        define(navigator.connection, 'type', FP.connection.type);
        // Round downlinkMax to realistic value
        define(navigator.connection, 'downlinkMax', Math.ceil(FP.connection.downlink));
      }
    } catch (e) {}

    // ===== Plugins =====
    try {
      const makePlugin = (name) => {
        const plugin = Object.create(Plugin.prototype);
        Object.defineProperty(plugin, 'name', { value: name });
        Object.defineProperty(plugin, 'filename', {
          value: name.toLowerCase().replace(/\s+/g, '-') + '.dll'
        });
        Object.defineProperty(plugin, 'description', { value: 'Portable Document Format' });
        Object.defineProperty(plugin, 'length', { value: 1 });
        return plugin;
      };
      const pluginArray = Object.create(PluginArray.prototype);
      const items = FP.plugins.map(makePlugin);
      items.forEach((p, i) => { pluginArray[i] = p; pluginArray[p.name] = p; });
      Object.defineProperty(pluginArray, 'length', { value: items.length });
      pluginArray.item = function (i) { return items[i] || null; };
      pluginArray.namedItem = function (n) { return items.find(p => p.name === n) || null; };
      pluginArray.refresh = function () {};
      Object.defineProperty(navigator, 'plugins', {
        get: () => pluginArray, configurable: true,
      });
      try {
        const origMimeTypes = Object.getOwnPropertyDescriptor(Navigator.prototype, 'mimeTypes');
        if (!origMimeTypes || (navigator.mimeTypes && navigator.mimeTypes.length === 0)) {
          const mtArray = Object.create(MimeTypeArray.prototype);
          Object.defineProperty(mtArray, 'length', { value: 3 });
          mtArray[0] = { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: items[0] || makePlugin('PDF Viewer') };
          mtArray[1] = { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: items[0] || makePlugin('PDF Viewer') };
          mtArray[2] = { type: 'application/x-nacl', suffixes: '', description: 'Native Client', enabledPlugin: null };
          mtArray.item = function(i) { return this[i] || null; };
          mtArray.namedItem = function(n) {
            for (let i = 0; i < this.length; i++) if (this[i] && this[i].type === n) return this[i];
            return null;
          };
          mtArray.refresh = function() {};
          Object.defineProperty(navigator, 'mimeTypes', { get: () => mtArray, configurable: true });
        }
      } catch (e) {}
    } catch (e) {}

    // ===== Permissions API =====
    try {
      const origQuery = navigator.permissions && navigator.permissions.query;
      if (origQuery) {
        replaceMethod(navigator.permissions, 'query', function (params) {
          if (params && params.name) {
            const name = params.name;
            // Consistent permission states per profile
            const states = {};
            states[name] = (name === 'notifications') ? Notification.permission : 'prompt';
            if (name === 'camera' || name === 'microphone' || name === 'camera-microphone') {
              states[name] = 'prompt';
            }
            if (name === 'geolocation') states[name] = 'prompt';
            if (name === 'clipboard-read' || name === 'clipboard-write') states[name] = 'prompt';
            if (name === 'payment-handler') states[name] = 'prompt';
            if (name === 'midi' || name === 'midi-sysex') states[name] = 'prompt';
            return Promise.resolve({
              state: states[name] || 'prompt',
              onchange: null,
              addEventListener: function(){},
              removeEventListener: function(){},
              dispatchEvent: function(){ return false; },
            });
          }
          return origQuery.call(navigator.permissions, params);
        });
      }
      // Override Notification.permission consistency
      try {
        Object.defineProperty(Notification, 'permission', {
          get: () => 'default', configurable: true,
        });
      } catch (e) {}
    } catch (e) {}

    // ===== CSS Media Queries =====
    try {
      const origMatchMedia = window.matchMedia;
      window.matchMedia = function (query) {
        const result = origMatchMedia.call(window, query);
        if (query === '(prefers-color-scheme: dark)') {
          return {
            matches: FP.colorScheme === 'dark',
            media: query,
            onchange: null,
            addListener: function(){},
            removeListener: function(){},
            addEventListener: function(){},
            removeEventListener: function(){},
            dispatchEvent: function(){ return false; },
          };
        }
        if (query === '(prefers-color-scheme: light)') {
          return {
            matches: FP.colorScheme === 'light',
            media: query,
            onchange: null,
            addListener: function(){},
            removeListener: function(){},
            addEventListener: function(){},
            removeEventListener: function(){},
            dispatchEvent: function(){ return false; },
          };
        }
        if (query === '(prefers-reduced-motion: reduce)') {
          return {
            matches: FP.motionPreference === 'reduce',
            media: query,
            onchange: null,
            addListener: function(){},
            removeListener: function(){},
            addEventListener: function(){},
            removeEventListener: function(){},
            dispatchEvent: function(){ return false; },
          };
        }
        if (query === '(prefers-reduced-motion: no-preference)') {
          return {
            matches: FP.motionPreference === 'no-preference',
            media: query,
            onchange: null,
            addListener: function(){},
            removeListener: function(){},
            addEventListener: function(){},
            removeEventListener: function(){},
            dispatchEvent: function(){ return false; },
          };
        }
        return result;
      };
    } catch (e) {}

    // ===== performance.memory spoofing =====
    try {
      if (performance && FP.memory) {
        define(performance, 'memory', {
          jsHeapSizeLimit: FP.memory.jsHeapSizeLimit,
          totalJSHeapSize: FP.memory.totalJSHeapSize,
          usedJSHeapSize: FP.memory.usedJSHeapSize,
        });
      }
    } catch (e) {}

    // ===== Performance & Navigation timing sanitization =====
    try {
      const origGetEntries = Performance.prototype.getEntries;
      replaceMethod(Performance.prototype, 'getEntries', function () {
        const entries = origGetEntries.apply(this, arguments);
        return entries.filter(e => {
          // Remove entries that reveal automation/CDP
          if (e.name && e.name.includes('devtools')) return false;
          if (e.name && e.name.includes('debugger')) return false;
          return true;
        });
      });
      const origGetEntriesByType = Performance.prototype.getEntriesByType;
      replaceMethod(Performance.prototype, 'getEntriesByType', function (type) {
        const entries = origGetEntriesByType.apply(this, arguments);
        if (type === 'navigation') {
          return entries.map(e => {
            const clone = {};
            for (const k in e) {
              if (k === 'nextHopProtocol' && e[k] === '') {
                clone[k] = 'h2'; // Realistic default
              } else {
                clone[k] = e[k];
              }
            }
            return clone;
          });
        }
        return entries;
      });
    } catch (e) {}

    // ===== chrome.runtime stub =====
    try {
      if (!window.chrome) window.chrome = {};
      if (!window.chrome.runtime) {
        window.chrome.runtime = {
          OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
          OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
          PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
          PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
          PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
          RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' },
          OnConnectEvent: {},
          OnMessageEvent: {},
          // Methods that exist but throw outside extension context
          getManifest: function() { throw new Error('chrome.runtime.getManifest is not available'); },
          getURL: function(p) { return 'chrome-extension://invalid/' + p; },
          reload: function() {},
          requestUpdateCheck: function(cb) { if(cb) cb('no_update'); },
          restart: function() {},
          restartAfterDelay: function() {},
          connect: function() { return { postMessage: function(){}, disconnect: function(){}, onMessage: { addListener: function(){} } }; },
          sendMessage: function() { if (arguments.length > 0 && typeof arguments[arguments.length-1] === 'function') arguments[arguments.length-1](); },
          onStartup: { addListener: function(){} },
          onInstalled: { addListener: function(){} },
          onSuspend: { addListener: function(){} },
          onSuspendCanceled: { addListener: function(){} },
          onUpdateAvailable: { addListener: function(){} },
          onBrowserUpdateAvailable: { addListener: function(){} },
          onConnect: { addListener: function(){}, removeListener: function(){}, hasListeners: function(){ return false; } },
          onMessage: { addListener: function(){}, removeListener: function(){}, hasListeners: function(){ return false; } },
          onConnectExternal: { addListener: function(){} },
          onMessageExternal: { addListener: function(){} },
        };
      }
      if (!window.chrome.app) {
        window.chrome.app = {
          isInstalled: false,
          InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
          RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
        };
      }
      if (!window.chrome.csi) window.chrome.csi = function () { return { onloadT: Date.now(), startE: Date.now(), pageT: Date.now() }; };
      if (!window.chrome.loadTimes) {
        window.chrome.loadTimes = function () {
          const now = Date.now() / 1000;
          return {
            commitLoadTime: now - 1,
            connectionInfo: 'h2',
            finishDocumentLoadTime: now - 0.5,
            finishLoadTime: now - 0.3,
            firstPaintAfterLoadTime: 0,
            firstPaintTime: now - 0.6,
            navigationType: 'Other',
            npnNegotiatedProtocol: 'h2',
            requestTime: now - 1.2,
            startLoadTime: now - 1.2,
            wasAlternateProtocolAvailable: false,
            wasFetchedViaSpdy: true,
            wasNpnNegotiated: true,
          };
        };
      }
      // chrome.system (partial stub)
      if (!window.chrome.system) {
        window.chrome.system = {
          cpu: {
            getInfo: function(cb) {
              if (cb) cb({
                archName: FP.platform === 'MacIntel' ? 'x86_64' : 'x86_64',
                features: ['mmx', 'sse', 'sse2', 'sse3', 'ssse3', 'sse4_1', 'sse4_2', 'avx'],
                modelName: 'Unknown',
                numOfProcessors: FP.hardwareConcurrency,
                processors: Array(FP.hardwareConcurrency).fill({ usage: { idle: 0, kernel: 0, total: 0, user: 0 } }),
                temperatures: [],
              });
            }
          },
          memory: {
            getInfo: function(cb) {
              if (cb) cb({
                availableCapacity: FP.deviceMemory * 1024 * 1024 * 1024 * 0.6,
                capacity: FP.deviceMemory * 1024 * 1024 * 1024,
              });
            }
          },
          storage: {
            getInfo: function(cb) { if(cb) cb([]); },
            ejectDevice: function() {},
            getAvailableCapacity: function(cb) { if(cb) cb({ availableCapacity: 100000000000 }); },
            onAttached: { addListener: function(){} },
            onDetached: { addListener: function(){} },
          },
        };
      }
    } catch (e) {}

    // ===== Speech Synthesis voice spoofing =====
    try {
      if (window.speechSynthesis && FP.speechVoices) {
        const origGetVoices = window.speechSynthesis.getVoices;
        const fakeVoices = FP.speechVoices.map((v, i) => {
          const voice = new SpeechSynthesisVoice();
          Object.defineProperty(voice, 'name', { value: v.name });
          Object.defineProperty(voice, 'lang', { value: v.lang });
          Object.defineProperty(voice, 'localService', { value: !!v.local });
          Object.defineProperty(voice, 'default', { value: !!v.default });
          Object.defineProperty(voice, 'voiceURI', { value: 'urn:moz-tts:sync?rate=1.0&name=' + encodeURIComponent(v.name) });
          return voice;
        });
        replaceMethod(window.speechSynthesis, 'getVoices', function () {
          return fakeVoices;
        });
        // Also handle the voiceschanged event for async voice loading
        setTimeout(() => {
          try {
            const evt = new Event('voiceschanged');
            window.speechSynthesis.dispatchEvent(evt);
          } catch (e) {}
        }, 100);
      }
    } catch (e) {}

    // ===== WebRTC — block local IP leaks =====
    try {
      if (window.RTCPeerConnection) {
        const OrigRTC = window.RTCPeerConnection;
        const PatchedRTC = function (config, ...rest) {
          const pc = new OrigRTC(config, ...rest);
          const origCreateOffer = pc.createOffer.bind(pc);
          pc.createOffer = function (...a) {
            return origCreateOffer(...a).then((offer) => {
              if (offer && offer.sdp) {
                offer.sdp = offer.sdp.replace(/^a=candidate:.*typ host.*$/gm, '');
                offer.sdp = offer.sdp.replace(/^a=candidate:.*typ srflx.*$/gm, '');
              }
              return offer;
            });
          };
          return pc;
        };
        PatchedRTC.prototype = OrigRTC.prototype;
        window.RTCPeerConnection = PatchedRTC;
        if (window.webkitRTCPeerConnection) window.webkitRTCPeerConnection = PatchedRTC;
        // Also patch RTCSessionDescription to appear native
        if (window.RTCSessionDescription) {
          const origStr = Function.prototype.toString.call(window.RTCSessionDescription);
          Object.defineProperty(window.RTCSessionDescription, 'toString', {
            value: () => origStr, configurable: true,
          });
        }
      }
    } catch (e) {}

    // ===== Font enumeration evasion =====
    try {
      if (document && document.fonts) {
        const origCheck = document.fonts.check;
        replaceMethod(document.fonts, 'check', function (font, text) {
          // If checking a font we claim to have, return true
          const fontName = (font || '').replace(/['"]/g, '').split(' ')[0];
          if (FP.fonts.some(f => f.toLowerCase() === fontName.toLowerCase())) {
            return true;
          }
          return origCheck.apply(this, arguments);
        });
        const origReady = document.fonts.ready;
        if (origReady && origReady.then) {
          // Already a promise-like; leave it
        }
      }
    } catch (e) {}

    // ===== Misc telltales =====
    try {
      // iFrame creation timing (some detectors check this)
      const origCreateElement = Document.prototype.createElement;
      replaceMethod(Document.prototype, 'createElement', function(tag) {
        if (tag && tag.toLowerCase() === 'iframe') {
          // Add small delay to iframe creation to look more human
          const start = performance.now();
          while (performance.now() - start < 0.5) { /* micro-delay */ }
        }
        return origCreateElement.apply(this, arguments);
      });
    } catch (e) {}

    // ===== document.$wpt (WebPageTest) wipe =====
    try { delete document.$wpt; } catch (e) {}
    try { delete window.$wpt; } catch (e) {}

    // Fonts list
    try { window.__FP_FONTS__ = FP.fonts; } catch (e) {}
  } catch (err) {
    /* swallow - never break the page */
  }
})();
"""


    # ------------------------------------------------------------------
    # Chrome timestamp helper
    # ------------------------------------------------------------------
    @staticmethod
    def _chrome_timestamp(dt):
        epoch_start = datetime(1601, 1, 1)
        delta = dt - epoch_start
        return int(delta.total_seconds() * 1_000_000)

    def _aged_site_catalog(self):
        return [
            {"host": "google.com", "wildcard": True, "secure": True, "cookies": [
                ("NID", "rand:64"),
                ("1P_JAR", "date:%Y-%m-%d-%H"),
                ("AEC", "rand:48"),
                ("CONSENT", "static:YES+cb.20210418-17-p0.en+FX+{rand:3}"),
                ("DV", "rand:40"),
            ]},
            {"host": "youtube.com", "wildcard": True, "secure": True, "cookies": [
                ("VISITOR_INFO1_LIVE", "rand:11"),
                ("YSC", "rand:11"),
                ("PREF", "static:f6=40000000&tz={tz_offset}"),
                ("GPS", "static:1"),
            ]},
            {"host": "gstatic.com", "wildcard": True, "secure": True, "cookies": [
                ("__Secure-ENID", "rand:80"),
            ]},
            {"host": "facebook.com", "wildcard": True, "secure": True, "cookies": [
                ("datr", "rand:24"),
                ("sb",   "rand:24"),
                ("fr",   "rand:60"),
                ("wd",   "static:{w}x{h}"),
                ("c_user", "rand-digits:15"),
                ("locale", "lang"),
            ]},
            {"host": "instagram.com", "wildcard": True, "secure": True, "cookies": [
                ("ig_did", "uuid"),
                ("mid",    "rand:28"),
                ("csrftoken", "rand:32"),
                ("ds_user_id", "rand-digits:10"),
            ]},
            {"host": "microsoft.com", "wildcard": True, "secure": True, "cookies": [
                ("MUID", "hex:32"),
                ("MC1",  "static:GUID={uuid_no_dashes}&HASH={hex:8}&LV={date:%Y%m%d}&V=4"),
            ]},
            {"host": "bing.com", "wildcard": True, "secure": True, "cookies": [
                ("MUID", "hex:32"),
                ("SRCHD", "static:AF=NOFORM"),
                ("SRCHUID", "static:V=2&GUID={uuid_no_dashes}&dmnchg=1"),
                ("_EDGE_S", "static:F=1&SID={hex:32}"),
            ]},
            {"host": "linkedin.com", "wildcard": True, "secure": True, "cookies": [
                ("bcookie",  'static:"v=2&{uuid}"'),
                ("bscookie", 'static:"v=1&{rand:60}"'),
                ("lidc",     'static:"b=VB97:s=V:r=V:a=V:p=V:g=2932:u=1:x=1:i={ts}:t={ts2}:v=2:sig={hex:32}"'),
                ("li_gc",    "rand:40"),
            ]},
            {"host": "x.com", "wildcard": True, "secure": True, "cookies": [
                ("guest_id", "static:v1%3A{ts_digits}"),
                ("personalization_id", 'static:"v1_{rand:24}"'),
                ("kdt", "rand:24"),
            ]},
            {"host": "twitter.com", "wildcard": True, "secure": True, "cookies": [
                ("guest_id", "static:v1%3A{ts_digits}"),
                ("personalization_id", 'static:"v1_{rand:24}"'),
            ]},
            {"host": "reddit.com", "wildcard": True, "secure": True, "cookies": [
                ("loid", "rand:48"),
                ("session_tracker", "rand:40"),
                ("edgebucket", "rand:21"),
                ("reddit_session", "rand:36"),
            ]},
            {"host": "amazon.com", "wildcard": True, "secure": True, "cookies": [
                ("session-id", "static:{rand-digits:3}-{rand-digits:7}-{rand-digits:7}"),
                ("session-id-time", "ts"),
                ("ubid-main", "static:{rand-digits:3}-{rand-digits:7}-{rand-digits:7}"),
                ("i18n-prefs", "static:USD"),
                ("sp-cdn", "static:L5Z9:US"),
            ]},
            {"host": "ebay.com", "wildcard": True, "secure": True, "cookies": [
                ("dp1", "static:bbl/US{hex:6}^"),
                ("nonsession", "static:CgADKACBskUlkY2I0NWFmNDIxOTBhZ{rand:10}"),
            ]},
            {"host": "nytimes.com", "wildcard": True, "secure": True, "cookies": [
                ("nyt-a", "rand:32"),
                ("nyt-gdpr", "static:0"),
            ]},
            {"host": "bbc.com", "wildcard": True, "secure": True, "cookies": [
                ("ckns_explicit", "static:1"),
                ("ckns_policy", "static:111"),
                ("ckns_atkn", "rand:64"),
            ]},
            {"host": "cnn.com", "wildcard": True, "secure": True, "cookies": [
                ("countryCode", "static:US"),
                ("geoData", "static:atlanta|GA|30303|US|NA|-400|broadband|33.7490|-84.3880"),
            ]},
            {"host": "cloudflare.com", "wildcard": True, "secure": True, "cookies": [
                ("__cf_bm", "rand:43"),
            ]},
            {"host": "doubleclick.net", "wildcard": True, "secure": True, "cookies": [
                ("IDE", "rand:64"),
                ("test_cookie", "static:CheckForPermission"),
            ]},
            {"host": "googlesyndication.com", "wildcard": True, "secure": True, "cookies": [
                ("__gads", "static:ID={hex:16}-1:T={ts_digits}:RT={ts_digits}:S=ALNI_M{rand:20}"),
            ]},
            {"host": "github.com", "wildcard": True, "secure": True, "cookies": [
                ("_octo", "static:GH1.1.{rand-digits:10}.{ts_digits}"),
                ("logged_in", "static:no"),
                ("preferred_color_mode", "static:dark"),
                ("tz", "tz_name"),
            ]},
            {"host": "stackoverflow.com", "wildcard": True, "secure": True, "cookies": [
                ("prov", "uuid"),
                ("acct", "static:t=Lq{rand:18}&s={rand:24}"),
            ]},
            {"host": "netflix.com", "wildcard": True, "secure": True, "cookies": [
                ("nfvdid", "static:BQFmAAEBE{rand:50}"),
                ("OptanonConsent", "static:isGpcEnabled=0&datestamp={date:%a+%b+%d+%Y}"),
            ]},
            {"host": "spotify.com", "wildcard": True, "secure": True, "cookies": [
                ("sp_t",  "uuid"),
                ("sp_landing", "static:https%3A%2F%2Fopen.spotify.com%2F"),
            ]},
            {"host": "wikipedia.org", "wildcard": True, "secure": True, "cookies": [
                ("WMF-Last-Access", "date:%d-%b-%Y"),
                ("WMF-Last-Access-Global", "date:%d-%b-%Y"),
                ("GeoIP", "static:US:NY:New_York:40.71:-74.00:v4"),
            ]},
            {"host": "pinterest.com", "wildcard": True, "secure": True, "cookies": [
                ("_pinterest_sess", "rand:80"),
                ("_routing_id", "uuid"),
                ("csrftoken", "hex:32"),
            ]},
        ]

    def _render_cookie_value(self, template, ctx):
        import uuid as _uuid

        def gen(directive):
            if directive == 'uuid':
                return str(_uuid.uuid4())
            if directive == 'uuid_no_dashes':
                return _uuid.uuid4().hex
            if directive == 'ts':
                return str(ctx['chrome_ts'])
            if directive == 'ts2':
                return str(ctx['chrome_ts'] + random.randint(1000, 100000))
            if directive == 'ts_digits':
                return str(ctx['chrome_ts'])
            if directive == 'tz_offset':
                return str(ctx['tz_offset'])
            if directive == 'tz_name':
                return ctx['tz_name']
            if directive == 'lang':
                return ctx['lang']
            if directive.startswith('rand-digits:'):
                n = int(directive.split(':', 1)[1])
                return ''.join(random.choices(string.digits, k=n))
            if directive.startswith('rand:'):
                n = int(directive.split(':', 1)[1])
                alphabet = string.ascii_letters + string.digits
                return ''.join(random.choices(alphabet, k=n))
            if directive.startswith('hex:'):
                n = int(directive.split(':', 1)[1])
                return ''.join(random.choices('0123456789abcdef', k=n))
            if directive.startswith('date:'):
                fmt = directive.split(':', 1)[1]
                offset = timedelta(days=random.randint(0, 30),
                                   hours=random.randint(0, 23))
                d = ctx['now'] - offset
                return d.strftime(fmt)
            return ''

        if template.startswith('static:'):
            literal = template[len('static:'):]
            out, i = [], 0
            while i < len(literal):
                if literal[i] == '{':
                    j = literal.find('}', i)
                    if j != -1:
                        out.append(gen(literal[i+1:j]))
                        i = j + 1
                        continue
                out.append(literal[i])
                i += 1
            return ''.join(out)
        return gen(template)

    def _seed_profile_cookies(self, profile_path, fingerprint, num_sites=None):
        if not self._assert_own_profile(profile_path, 'seed cookies into'):
            return None
        try:
            net_dir = os.path.join(profile_path, 'Network')
            os.makedirs(net_dir, exist_ok=True)
            cookies_db = os.path.join(net_dir, 'Cookies')

            catalog = self._aged_site_catalog()
            if num_sites is None:
                num_sites = random.randint(12, 20)
            chosen = random.sample(catalog, k=min(num_sites, len(catalog)))

            now = datetime.utcnow()
            tz_name = fingerprint.get('timezone', 'UTC')
            tz_offsets = {
                'America/New_York': -300, 'America/Los_Angeles': -480,
                'America/Chicago': -360, 'America/Denver': -420,
                'America/Detroit': -300, 'America/Phoenix': -420,
                'America/Toronto': -300, 'America/Vancouver': -480,
                'America/Mexico_City': -360, 'America/Sao_Paulo': 180,
                'Europe/London': 0, 'Europe/Paris': 60,
                'Europe/Berlin': 60, 'Europe/Madrid': 60,
                'Europe/Rome': 60, 'Europe/Amsterdam': 60,
                'Europe/Vienna': 60, 'Europe/Warsaw': 60,
                'Europe/Stockholm': 60,
                'Asia/Tokyo': 540, 'Asia/Seoul': 540,
                'Asia/Shanghai': 480, 'Asia/Singapore': 480,
                'Asia/Hong_Kong': 480, 'Asia/Bangkok': 420,
                'Asia/Dubai': 240, 'Asia/Mumbai': 330,
                'Asia/Jakarta': 420,
                'Australia/Sydney': 660, 'Australia/Melbourne': 660,
                'Pacific/Auckland': 780,
            }

            ctx_base = {
                'now': now,
                'lang': fingerprint.get('language', 'en-US'),
                'tz_name': tz_name,
                'tz_offset': tz_offsets.get(tz_name, 0),
                'w': fingerprint['screen_resolution']['width'],
                'h': fingerprint['screen_resolution']['height'],
            }

            for suffix in ('-journal', '-wal', '-shm'):
                p = cookies_db + suffix
                if os.path.exists(p):
                    try: os.remove(p)
                    except Exception: pass

            conn = sqlite3.connect(cookies_db)
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=DELETE")
            cur.execute("PRAGMA synchronous=FULL")
            cur.execute("PRAGMA secure_delete=OFF")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS cookies (
                    creation_utc      INTEGER NOT NULL,
                    host_key          TEXT NOT NULL,
                    top_frame_site_key TEXT NOT NULL DEFAULT '',
                    name              TEXT NOT NULL,
                    value             TEXT NOT NULL,
                    encrypted_value   BLOB DEFAULT '',
                    path              TEXT NOT NULL,
                    expires_utc       INTEGER NOT NULL,
                    is_secure         INTEGER NOT NULL,
                    is_httponly       INTEGER NOT NULL,
                    last_access_utc   INTEGER NOT NULL,
                    has_expires       INTEGER NOT NULL DEFAULT 1,
                    is_persistent     INTEGER NOT NULL DEFAULT 1,
                    priority          INTEGER NOT NULL DEFAULT 1,
                    samesite          INTEGER NOT NULL DEFAULT -1,
                    source_scheme     INTEGER NOT NULL DEFAULT 0,
                    source_port       INTEGER NOT NULL DEFAULT -1,
                    last_update_utc   INTEGER NOT NULL DEFAULT 0,
                    source_type       INTEGER NOT NULL DEFAULT 0,
                    has_cross_site_ancestor INTEGER NOT NULL DEFAULT 0,
                    UNIQUE (host_key, top_frame_site_key, name, path)
                )
            """)
            cur.execute("CREATE TABLE IF NOT EXISTS meta (key LONGVARCHAR NOT NULL UNIQUE PRIMARY KEY, value LONGVARCHAR)")
            cur.execute("INSERT OR REPLACE INTO meta VALUES ('version', '18')")
            cur.execute("INSERT OR REPLACE INTO meta VALUES ('last_compatible_version', '18')")
            cur.execute("CREATE INDEX IF NOT EXISTS cookies_host_key ON cookies(host_key)")
            cur.execute("CREATE INDEX IF NOT EXISTS cookies_top_frame_site_key ON cookies(top_frame_site_key)")

            cookie_count = 0
            site_summaries = []

            for site in chosen:
                first_visit = now - timedelta(
                    days=random.randint(2, 30),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59)
                )
                last_visit_offset = random.expovariate(1 / 3.0)
                last_visit_offset = min(last_visit_offset, 30)
                last_visit = now - timedelta(
                    days=last_visit_offset,
                    hours=random.randint(0, 23),
                )
                if last_visit < first_visit:
                    last_visit = first_visit + timedelta(hours=1)

                creation_ts = self._chrome_timestamp(first_visit)
                last_access_ts = self._chrome_timestamp(last_visit)
                expires_ts = self._chrome_timestamp(now + timedelta(days=random.randint(180, 400)))

                ctx = dict(ctx_base, chrome_ts=creation_ts)

                host_key = site['host']
                if site.get('wildcard'):
                    host_key = '.' + host_key

                site_cookie_count = 0
                for cname, ctemplate in site['cookies']:
                    try:
                        cvalue = self._render_cookie_value(ctemplate, ctx)
                        cur.execute("""
                            INSERT OR IGNORE INTO cookies (
                                creation_utc, host_key, top_frame_site_key,
                                name, value, encrypted_value, path,
                                expires_utc, is_secure, is_httponly,
                                last_access_utc, has_expires, is_persistent,
                                priority, samesite, source_scheme, source_port,
                                last_update_utc, source_type, has_cross_site_ancestor
                            ) VALUES (?, ?, '', ?, ?, ?, '/', ?, ?, ?, ?, 1, 1, 1, -1, 2, 443, ?, 0, 0)
                        """, (
                            creation_ts + site_cookie_count,
                            host_key,
                            cname,
                            cvalue,
                            b'',
                            expires_ts,
                            1 if site.get('secure') else 0,
                            1 if cname.startswith('__Secure-') or cname.startswith('__Host-') else 0,
                            last_access_ts,
                            last_access_ts,
                        ))
                        site_cookie_count += 1
                        cookie_count += 1
                    except sqlite3.Error:
                        continue

                site_summaries.append({
                    'host': site['host'],
                    'cookies': site_cookie_count,
                    'first_visit': first_visit.isoformat(timespec='seconds'),
                    'last_visit': last_visit.isoformat(timespec='seconds'),
                })

            conn.commit()
            conn.close()

            summary = {
                'cookie_count': cookie_count,
                'site_count': len(site_summaries),
                'simulated_age_days': 30,
                'sites': site_summaries,
            }
            with open(os.path.join(profile_path, '_cookies_summary.json'),
                      'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2)
            return summary
        except Exception as e:
            print(f"[cookies] Failed to seed cookies: {e}")
            return None

    def _seed_profile_history(self, profile_path, cookie_summary):
        if not self._assert_own_profile(profile_path, 'seed history into'):
            return None
        if not cookie_summary or not cookie_summary.get('sites'):
            return None
        try:
            history_db = os.path.join(profile_path, 'History')
            for suffix in ('-journal', '-wal', '-shm'):
                p = history_db + suffix
                if os.path.exists(p):
                    try: os.remove(p)
                    except Exception: pass

            conn = sqlite3.connect(history_db)
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=DELETE")
            cur.execute("PRAGMA synchronous=FULL")

            cur.executescript("""
                CREATE TABLE IF NOT EXISTS urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url LONGVARCHAR, title LONGVARCHAR,
                    visit_count INTEGER DEFAULT 0 NOT NULL,
                    typed_count INTEGER DEFAULT 0 NOT NULL,
                    last_visit_time INTEGER NOT NULL,
                    hidden INTEGER DEFAULT 0 NOT NULL
                );
                CREATE TABLE IF NOT EXISTS visits (
                    id INTEGER PRIMARY KEY, url INTEGER NOT NULL,
                    visit_time INTEGER NOT NULL, from_visit INTEGER,
                    transition INTEGER DEFAULT 0 NOT NULL, segment_id INTEGER,
                    visit_duration INTEGER DEFAULT 0 NOT NULL,
                    incremented_omnibox_typed_score BOOLEAN DEFAULT FALSE NOT NULL,
                    opener_visit INTEGER, originator_cache_guid TEXT,
                    originator_visit_id INTEGER, originator_from_visit INTEGER,
                    originator_opener_visit INTEGER,
                    is_known_to_sync BOOLEAN DEFAULT FALSE NOT NULL,
                    consider_for_ntp_most_visited BOOLEAN DEFAULT FALSE NOT NULL
                );
                CREATE TABLE IF NOT EXISTS visit_source (id INTEGER PRIMARY KEY, source INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS keyword_search_terms (
                    keyword_id INTEGER NOT NULL, url_id INTEGER NOT NULL,
                    term LONGVARCHAR NOT NULL, normalized_term LONGVARCHAR NOT NULL
                );
                CREATE TABLE IF NOT EXISTS segments (id INTEGER PRIMARY KEY, name VARCHAR, url_id INTEGER NON NULL);
                CREATE TABLE IF NOT EXISTS segment_usage (
                    id INTEGER PRIMARY KEY, segment_id INTEGER NOT NULL,
                    time_slot INTEGER NOT NULL, visit_count INTEGER DEFAULT 0 NOT NULL
                );
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY, guid VARCHAR NOT NULL,
                    current_path LONGVARCHAR NOT NULL, target_path LONGVARCHAR NOT NULL,
                    start_time INTEGER NOT NULL, received_bytes INTEGER NOT NULL,
                    total_bytes INTEGER NOT NULL, state INTEGER NOT NULL,
                    danger_type INTEGER NOT NULL, interrupt_reason INTEGER NOT NULL,
                    hash BLOB NOT NULL, end_time INTEGER NOT NULL,
                    opened INTEGER NOT NULL, last_access_time INTEGER NOT NULL,
                    transient INTEGER NOT NULL, referrer VARCHAR NOT NULL,
                    site_url VARCHAR NOT NULL, embedder_download_data VARCHAR NOT NULL,
                    tab_url VARCHAR NOT NULL, tab_referrer_url VARCHAR NOT NULL,
                    http_method VARCHAR NOT NULL, by_ext_id VARCHAR NOT NULL,
                    by_ext_name VARCHAR NOT NULL, by_web_app_id VARCHAR NOT NULL,
                    etag VARCHAR NOT NULL, last_modified VARCHAR NOT NULL,
                    mime_type VARCHAR(255) NOT NULL, original_mime_type VARCHAR(255) NOT NULL
                );
                CREATE TABLE IF NOT EXISTS downloads_url_chains (
                    id INTEGER NOT NULL, chain_index INTEGER NOT NULL,
                    url LONGVARCHAR NOT NULL, PRIMARY KEY (id, chain_index)
                );
                CREATE TABLE IF NOT EXISTS meta (key LONGVARCHAR NOT NULL UNIQUE PRIMARY KEY, value LONGVARCHAR);
                CREATE INDEX IF NOT EXISTS urls_url_index ON urls (url);
                CREATE INDEX IF NOT EXISTS visits_url_index ON visits (url);
                CREATE INDEX IF NOT EXISTS visits_from_index ON visits (from_visit);
                CREATE INDEX IF NOT EXISTS visits_time_index ON visits (visit_time);
                CREATE INDEX IF NOT EXISTS segments_name ON segments (name);
                CREATE INDEX IF NOT EXISTS segments_url_id ON segments (url_id);
            """)
            cur.execute("INSERT OR REPLACE INTO meta VALUES ('version', '50')")
            cur.execute("INSERT OR REPLACE INTO meta VALUES ('last_compatible_version', '40')")
            cur.execute("INSERT OR REPLACE INTO meta VALUES ('early_expiration_threshold', '0')")

            url_id = 0
            visit_id = 0
            segment_id = 0
            for site in cookie_summary['sites']:
                url_id += 1
                host = site['host']
                url = f"https://www.{host}/"
                title = host.split('.')[0].capitalize()
                visit_count = random.randint(5, 40)
                last_visit_dt = datetime.fromisoformat(site['last_visit'])
                last_visit_ts = self._chrome_timestamp(last_visit_dt)

                cur.execute("""
                    INSERT INTO urls (id, url, title, visit_count, typed_count, last_visit_time, hidden)
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                """, (url_id, url, title, visit_count,
                      random.randint(0, max(1, visit_count // 4)),
                      last_visit_ts))

                segment_id += 1
                cur.execute("""
                    INSERT INTO segments (id, name, url_id) VALUES (?, ?, ?)
                """, (segment_id, f"http://{host}/", url_id))

                first_visit_dt = datetime.fromisoformat(site['first_visit'])
                span_seconds = max(60, (last_visit_dt - first_visit_dt).total_seconds())
                for _ in range(visit_count):
                    visit_id += 1
                    offset = random.uniform(0, span_seconds)
                    vt = first_visit_dt + timedelta(seconds=offset)
                    transition = random.choice([
                        0x00000001, 0x00000001, 0x00000001,
                        0x00000002, 0x00000005,
                    ]) | 0x10000000 | 0x20000000
                    visit_ts = self._chrome_timestamp(vt)
                    cur.execute("""
                        INSERT INTO visits (id, url, visit_time, from_visit, transition, segment_id, visit_duration, consider_for_ntp_most_visited)
                        VALUES (?, ?, ?, 0, ?, ?, ?, 1)
                    """, (visit_id, url_id, visit_ts, transition, segment_id,
                          random.randint(5_000_000, 600_000_000)))

                cur.execute("""
                    INSERT INTO segment_usage (segment_id, time_slot, visit_count)
                    VALUES (?, ?, ?)
                """, (segment_id, last_visit_ts, visit_count))

            conn.commit()
            conn.close()
            return {'urls': url_id, 'visits': visit_id}
        except Exception as e:
            print(f"[history] Failed to seed history: {e}")
            return None

    # ------------------------------------------------------------------
    # v3: Enhanced launcher with TLS cipher flags and automation evasion
    # ------------------------------------------------------------------
    def _build_launcher_script(self, profile_name, profile_path, fingerprint, extension_path):
        # v4.2: this profile's own browser wins over the global choice
        chrome_exe = self.browser_for_profile(profile_name)
        if not chrome_exe:
            return None

        system = platform.system()
        ext = '.pyw' if system == 'Windows' else '.py'
        launcher_path = os.path.join(profile_path, f'launch{ext}')

        ua = fingerprint['user_agent'].replace('"', '')
        lang = fingerprint['language']
        langs = fingerprint.get('languages', [lang, 'en'])
        accept_lang_parts = []
        for i, l in enumerate(langs):
            q = max(0.1, round(1.0 - 0.1 * i, 1))
            accept_lang_parts.append(l if i == 0 else f"{l};q={q}")
        accept_lang = ','.join(accept_lang_parts)

        win_w = fingerprint['screen_resolution']['width']
        win_h = fingerprint['screen_resolution']['height']
        tz = fingerprint['timezone']
        color_scheme = fingerprint.get('color_scheme', 'light')

        # v3.2: make sure the user-script extension exists, then collect all
        self._build_userscript_extension(profile_path)
        ext_joined = ','.join(
            self._collect_extension_dirs(profile_path, extension_path))
        disabled_features = self._disabled_features()
        enabled_features = self._enabled_features()
        injector_path = self._build_cdp_injector(profile_path) or ''
        verbose = self.verbose_diagnostics()
        lean_flags = repr(self.lean_memory_flags())
        keepalive_flags = repr(self.background_keepalive_flags())
        _rt, _pfx = self._runtime_and_prefix()
        run_prefix = repr(_pfx)
        auth_token = self.launch_token(profile_name)
        app_marker = ''
        try:
            if _license is not None:
                app_marker = _license.app_marker_path()
        except Exception:
            app_marker = ''
        engine = 'chromium'   # Chrome only: never a Firefox command line
        tool_name = self.TOOL_NAME
        if not self._extensions_usable():
            ext_joined = ''

        # v4.4: the page this profile opens on (Facebook by default). Passed
        # straight to the browser so the tab loads even if injection can't.
        start_url = self.normalize_url(self.start_url_for(profile_name)) \
            or self.DEFAULT_START_URL

        # v4.4: Firefox needs its own extension and its own installer, because
        # it does not speak Chrome's DevTools protocol. Both are best-effort:
        # if Firefox refuses the remote-debugging server the browser still
        # opens, it just runs without the injected scripts.
        ff_ext_path = ''
        ff_injector = ''
        ff_debug_port = 0
        if engine == 'gecko':
            try:
                ff_ext_path = self._build_firefox_extension(profile_path) or ''
            except Exception:
                ff_ext_path = ''
            try:
                ff_debug_port = self._firefox_debug_port(profile_name)
                self._prepare_firefox_profile(profile_path, ff_debug_port)
            except Exception:
                ff_debug_port = 0
            try:
                if ff_ext_path and ff_debug_port:
                    ff_injector = self._build_firefox_injector(
                        profile_path, ff_ext_path, ff_debug_port) or ''
            except Exception:
                ff_injector = ''

        # v3: TLS cipher suite ordering flag
        tls_ciphers = fingerprint.get('tls_cipher_order', [])
        cipher_flag = ''
        if tls_ciphers:
            # Chrome doesn't have a direct "set cipher order" flag, but we can
            # disable specific ciphers via --cipher-suite-blacklist to force
            # different handshake patterns per profile
            cipher_flag = self.cipher_blacklist_flag(tls_ciphers)

        launcher_src = f"""#!/usr/bin/env python3
# -*- coding: utf-8 -*-
\"\"\"Auto-generated launcher for Chrome profile: {profile_name}

Starts Chrome with this profile's flags, then (when DevTools injection is
enabled) starts the injector that pushes user scripts into every page.

Anything that goes wrong is written to launch.log next to this file, and
Chrome is started anyway with a minimal command line, so a bad flag can
never stop the browser from opening.
\"\"\"
import os, sys, subprocess, traceback, time

CHROME_EXE   = r\"\"\"{chrome_exe}\"\"\"
PROFILE_PATH = r\"\"\"{profile_path}\"\"\"
EXT_PATH     = r\"\"\"{ext_joined}\"\"\"
INJECTOR     = r\"\"\"{injector_path}\"\"\"
CIPHER_FLAG  = r\"\"\"{cipher_flag}\"\"\"
AUTH_TOKEN   = r\"\"\"{auth_token}\"\"\"
APP_MARKER   = r\"\"\"{app_marker}\"\"\"
TOOL_NAME    = r\"\"\"{tool_name}\"\"\"
ENGINE       = r\"\"\"{engine}\"\"\"
START_URL    = r\"\"\"{start_url}\"\"\"
FF_EXT_PATH  = r\"\"\"{ff_ext_path}\"\"\"
FF_INJECTOR  = r\"\"\"{ff_injector}\"\"\"
FF_DEBUG_PORT = {ff_debug_port}
VERBOSE      = {verbose}
LEAN_FLAGS   = {lean_flags}
KEEPALIVE_FLAGS = {keepalive_flags}
RUN_PREFIX = {run_prefix}
LOG_FILE     = os.path.join(PROFILE_PATH, "launch.log")


def log(message):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as handle:
            handle.write(message + "\\n")
    except Exception:
        pass


def build_args():
    if ENGINE == "gecko":
        # Firefox takes none of Chrome's flags. Open the profile, turn on the
        # remote-debugging server (the injector installs the extension through
        # it) and load the start page.
        args = [CHROME_EXE, "-profile", PROFILE_PATH, "-no-remote"]
        if FF_DEBUG_PORT:
            args += ["-start-debugger-server", str(FF_DEBUG_PORT)]
        if START_URL:
            args.append(START_URL)
        return [a for a in args if a]
    args = [
        CHROME_EXE,
        "--user-data-dir=" + PROFILE_PATH,
        "--user-agent={ua}",
        "--lang={lang}",
        "--accept-lang={accept_lang}",
        "--window-size={win_w},{win_h}",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-service-autorun",
        "--password-store=basic",
        "--use-mock-keychain",
        "--disable-features={disabled_features}",
        "--enable-features={enabled_features}",
        "--disable-blink-features=AutomationControlled",
        "--disable-component-update",
        "--disable-domain-reliability",
        "--disable-background-networking",
        "--disable-sync",
        "--disable-breakpad",
        "--force-color-profile={self.color_profile_flag(color_scheme)}",
        "--disable-ipc-flooding-protection",
        "--disable-dev-shm-usage",
    ]
    if sys.platform.startswith("linux"):
        args.append("--no-sandbox")
    if CIPHER_FLAG:
        args.append(CIPHER_FLAG)
    if EXT_PATH:
        args.append("--load-extension=" + EXT_PATH)
    if INJECTOR:
        # bind to a random loopback port; Chrome writes the port it chose
        # into DevToolsActivePort and the injector reads it from there
        args.append("--remote-debugging-port=0")
        args.append("--remote-debugging-address=127.0.0.1")
    if VERBOSE:
        # chrome_debug.log in the profile records extension load failures
        args.append("--enable-logging")
        args.append("--v=1")
    # v4.6: every generated profile is a WHOLE extra Chrome - its own browser,
    # GPU, network service and one renderer per site. Several open at once
    # exhaust the Windows commit limit, and the first thing Windows refuses is
    # a new renderer - in ANY Chrome, including the user's own. These flags cap
    # what each profile costs. Purely additive: nothing above is changed.
    for _lean in LEAN_FLAGS:
        if _lean and _lean not in args:
            args.append(_lean)
    # v5.0: background execution reliability. Appended last so a duplicate
    # is skipped and nothing above can be overwritten.
    for _ka in KEEPALIVE_FLAGS:
        if _ka and _ka not in args:
            args.append(_ka)
    # v4.4: hand the page straight to Chrome as the last argument so it loads
    # even when the DevTools port is blocked and injection cannot happen
    if START_URL:
        args.append(START_URL)
    return [a for a in args if a]


def build_env():
    env = os.environ.copy()
    # v4.8: the injector uses this to tell a DevToolsActivePort written by
    # THIS launch from one left behind by a previous run that was killed.
    env["MVL_LAUNCH_EPOCH"] = str(time.time())
    env["TZ"] = "{tz}"
    env["GOOGLE_API_KEY"] = "no"
    env["GOOGLE_DEFAULT_CLIENT_ID"] = "no"
    env["GOOGLE_DEFAULT_CLIENT_SECRET"] = "no"
    return env


def start_injector(env):
    if ENGINE == "gecko":
        # Firefox: install the temporary add-on through the remote-debugging
        # server so the fingerprint patch and user scripts run in it too.
        if FF_INJECTOR and os.path.isfile(FF_INJECTOR) and FF_DEBUG_PORT:
            runtime = sys.executable
            if os.name == "nt":
                quiet = os.path.join(os.path.dirname(runtime), "pythonw.exe")
                if os.path.exists(quiet):
                    runtime = quiet
            try:
                if os.name == "nt":
                    subprocess.Popen([runtime, FF_INJECTOR], env=env,
                                     close_fds=True, creationflags=0x08000000)
                else:
                    subprocess.Popen([runtime, FF_INJECTOR], env=env,
                                     close_fds=True)
                log("firefox: add-on installer started on port %d" % FF_DEBUG_PORT)
            except Exception:
                log("firefox: could not start the add-on installer:\\n"
                    + traceback.format_exc())
        else:
            log("firefox: no add-on installer, scripts will not run")
        return
    if not INJECTOR or not os.path.isfile(INJECTOR):
        return
    runtime = sys.executable
    if os.name == "nt":
        quiet = os.path.join(os.path.dirname(runtime), "pythonw.exe")
        if os.path.exists(quiet):
            runtime = quiet
    if not runtime:
        log("no python runtime to start the injector")
        return
    _pfx = RUN_PREFIX
    if os.name == "nt":
        subprocess.Popen([runtime] + _pfx + [INJECTOR], env=env,
                         close_fds=True, creationflags=0x08000000)
    else:
        subprocess.Popen([runtime] + _pfx + [INJECTOR], env=env, close_fds=True)
    # v5.3: the CDP heartbeat runs as its own process so a failure in it
    # can never affect injection
    heartbeat = os.path.join(os.path.dirname(INJECTOR), "keepalive_heartbeat.py")
    if os.path.isfile(heartbeat):
        try:
            _pfx = RUN_PREFIX
            if os.name == "nt":
                subprocess.Popen([runtime] + _pfx + [heartbeat], env=env,
                                 close_fds=True, creationflags=0x08000000)
            else:
                subprocess.Popen([runtime] + _pfx + [heartbeat], env=env,
                                 close_fds=True)
        except Exception as exc:
            log("heartbeat did not start: %s" % exc)


def live_port():
    \"\"\"Port of a Chrome already running on this profile, else 0.\"\"\"
    import socket
    try:
        with open(os.path.join(PROFILE_PATH, "DevToolsActivePort"),
                  "r", encoding="utf-8") as handle:
            port = int(handle.read().split(chr(10))[0].strip())
    except Exception:
        return 0
    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=1)
        sock.close()
        return port
    except Exception:
        return 0


def started_by_tool():
    return bool(AUTH_TOKEN) and AUTH_TOKEN in sys.argv[1:]


def warn_direct_open():
    # tell whoever double-clicked the icon that they need the tool
    try:
        import tkinter
        from tkinter import messagebox
        window = tkinter.Tk()
        window.withdraw()
        window.attributes("-topmost", True)
        messagebox.showwarning(
            TOOL_NAME + " required",
            "This browser was created with " + TOOL_NAME + ".\\n\\n"
            "It can only be opened from " + TOOL_NAME + ".\\n\\n"
            "Please start " + TOOL_NAME + " and open it from there.")
        window.destroy()
    except Exception:
        pass


def minimal_args():
    # last-ditch command line if building the full one failed
    if ENGINE == "gecko":
        base = [CHROME_EXE, "-profile", PROFILE_PATH, "-no-remote"]
    else:
        base = [CHROME_EXE, "--user-data-dir=" + PROFILE_PATH]
    if START_URL:
        base.append(START_URL)
    return base


def open_plain():
    # no token, so no scripts: just the profile in a normal browser
    try:
        subprocess.Popen(minimal_args(), close_fds=True)
    except Exception:
        log("plain open failed:\\n" + traceback.format_exc())


def app_switched_off():
    # written by the app from a SIGNED check-in; absent = no decision yet
    if not APP_MARKER:
        return ""
    try:
        import json as _json
        with open(APP_MARKER, "r", encoding="utf-8") as handle:
            state = _json.load(handle)
    except Exception:
        return ""
    if state.get("app_enabled", True) is False:
        return state.get("message") or "The application is turned off by the administrator."
    return ""


def main():
    log("launcher start")
    if not started_by_tool():
        log("opened directly from the desktop - refused")
        warn_direct_open()
        return 0
    off = app_switched_off()
    if off:
        log("application switched off by the administrator - refused")
        return 0
    running = live_port()
    if running:
        # Chrome hands the request to the existing process and exits, so
        # every flag below is discarded. The injector can still attach to
        # the port that instance already opened.
        log("ALREADY RUNNING on port %d - new flags will be IGNORED by "
            "Chrome; close every window of this profile first" % running)
    else:
        try:
            os.remove(os.path.join(PROFILE_PATH, "DevToolsActivePort"))
        except Exception:
            pass

    try:
        args = build_args()
        env = build_env()
    except Exception:
        log("could not build the command line:\\n" + traceback.format_exc())
        args = minimal_args()
        env = os.environ.copy()

    proc = None
    try:
        if VERBOSE or ENGINE == "gecko":
            sink = open(os.path.join(PROFILE_PATH, "browser_stderr.log"), "wb")
            proc = subprocess.Popen(args, env=env, close_fds=True,
                                    stdout=sink, stderr=subprocess.STDOUT)
        else:
            proc = subprocess.Popen(args, env=env, close_fds=True)
    except Exception:
        log("chrome failed to start:\\n" + traceback.format_exc())
        try:
            subprocess.Popen(minimal_args())
        except Exception:
            log("minimal fallback also failed:\\n" + traceback.format_exc())
            return 1

    log("browser: " + CHROME_EXE + "  engine=" + ENGINE)
    log("chrome started with %d flags, injector=%s"
        % (len(args), "yes" if INJECTOR else "no"))

    try:
        start_injector(env)
    except Exception:
        log("injector failed to start:\\n" + traceback.format_exc())

    if ENGINE == "gecko":
        # Firefox exits straight away if another copy already owns the
        # profile, so say so instead of leaving a window that vanishes
        try:
            import time as _t
            _t.sleep(4)
            if proc is not None and proc.poll() is not None:
                log("firefox exited immediately with code %s - another copy "
                    "is probably already running, or the profile is in use"
                    % proc.returncode)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        log("fatal:\\n" + traceback.format_exc())
        try:
            subprocess.Popen(minimal_args())
        except Exception:
            pass
        sys.exit(1)
"""

        with open(launcher_path, 'w', encoding='utf-8') as f:
            f.write(launcher_src)
        try:
            os.chmod(launcher_path, 0o755)
        except Exception:
            pass
        return launcher_path

    # ------------------------------------------------------------------
    # v4.4: in-page guard against DevTools / extension tampering
    # ------------------------------------------------------------------
    #  This is the user-facing half: it shows the "developer tools are
    #  disabled" message and blocks the F12 / Ctrl+Shift+I shortcuts. The
    #  actual closing of the whole browser is done by the injector, which
    #  sees the devtools:// target over CDP. Wrapped so a throw here can
    #  never break the page it runs on.
    # ------------------------------------------------------------------
    GUARD_JS = r'''
(function () {
  'use strict';
  try {
    if (window.__mvl_guard__) { return; }
    Object.defineProperty(window, '__mvl_guard__', {
      value: 1, enumerable: false, configurable: true });

    var TOOL = "__GUARD_TOOL__";
    var shown = false;

    function overlay() {
      if (shown) { return; }
      shown = true;
      try {
        var html =
          '<div id="__mvl_block" style="position:fixed;inset:0;z-index:2147483647;'
          + 'background:#081733;color:#e8f0ff;display:flex;align-items:center;'
          + 'justify-content:center;flex-direction:column;font-family:Segoe UI,'
          + 'Arial,sans-serif;text-align:center;padding:40px">'
          + '<div style="font-size:56px;margin-bottom:14px">&#128274;</div>'
          + '<div style="font-size:22px;font-weight:700;margin-bottom:10px">'
          + 'Developer tools are disabled</div>'
          + '<div style="font-size:14px;color:#8fa8cc;max-width:460px;line-height:1.5">'
          + 'You can\u2019t open the developer tools in this browser.<br>'
          + 'It is closing now.</div></div>';
        var host = document.body || document.documentElement;
        if (host) {
          var d = document.createElement('div');
          d.innerHTML = html;
          host.appendChild(d);
        }
        try { document.title = 'Developer tools disabled'; } catch (e) {}
      } catch (e) {}
      // last-resort attempt to close this tab; the injector closes the rest
      try { window.close(); } catch (e) {}
      try { window.stop(); } catch (e) {}
    }

    // block the usual shortcuts so the guard is the normal outcome, not a race
    window.addEventListener('keydown', function (ev) {
      try {
        var k = (ev.key || '').toLowerCase();
        var block =
          ev.keyCode === 123 /* F12 */ ||
          (ev.ctrlKey && ev.shiftKey && (k === 'i' || k === 'j' || k === 'c')) ||
          (ev.metaKey && ev.altKey && (k === 'i' || k === 'j' || k === 'c')) ||
          (ev.ctrlKey && k === 'u');
        if (block) {
          ev.preventDefault();
          ev.stopPropagation();
          overlay();
        }
      } catch (e) {}
    }, true);

    window.addEventListener('contextmenu', function (ev) {
      try { ev.preventDefault(); } catch (e) {}
    }, true);

    // Note: no window-size / console-timing heuristics here. Those give false
    // positives (a docked bookmarks bar, a short window) and would blank a
    // page for no reason. The actual DevTools detection is done reliably
    // outside the page - by the CDP injector on Chrome (it sees the
    // devtools:// target and closes the whole browser) and by the extension's
    // own detector on Firefox.
  } catch (e) {}
})();
'''

    def _guard_js(self):
        """The in-page guard script, or '' when the guard is turned off."""
        if not self.guard_devtools():
            return ''
        return self.GUARD_JS.replace('__GUARD_TOOL__', self.TOOL_NAME)

    # ------------------------------------------------------------------
    # Userscript engine sources (written into each profile's extension)
    # ------------------------------------------------------------------
    USERSCRIPT_RUNTIME_JS = r'''/* Userscript runtime - Tampermonkey-compatible subset */
(function () {
  var KEY = '__USKEY__';
  var TOKEN = '__USTOKEN__';
  var PROFILE = '__USPROFILE__';
  var RESOURCES = __USRESOURCES__;
  var BRIDGED = __USBRIDGED__;   /* false => no extension worker, use page fallbacks */

  try { if (window[KEY]) { return; } } catch (e) { return; }

  /* ---------------- pattern matching ---------------- */
  function esc(s) { return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  function globToRegExp(p) {
    return new RegExp('^' + esc(p).replace(/\\\*/g, '[\\s\\S]*') + '$');
  }

  function patternToRegExp(p, isMatch) {
    try {
      if (!p) { return null; }
      p = String(p).trim();
      if (p === '<all_urls>' || p === '*' || p === '*://*/*') { return /^[\s\S]*$/; }
      if (p.length > 2 && p.charAt(0) === '/' && p.charAt(p.length - 1) === '/') {
        return new RegExp(p.slice(1, -1));
      }
      if (!isMatch) { return globToRegExp(p); }
      var m = /^(\*|[a-zA-Z][a-zA-Z0-9+.-]*):\/\/([^\/]*)(\/[\s\S]*)?$/.exec(p);
      if (!m) { return globToRegExp(p); }
      var scheme = m[1] === '*' ? '(?:https?)' : esc(m[1]);
      var host = m[2] || '*';
      var path = m[3] || '/*';
      var hostRe;
      if (host === '*') {
        hostRe = '[^/]*';
      } else if (host.slice(0, 2) === '*.') {
        hostRe = '(?:[^/]*\\.)?' + esc(host.slice(2)).replace(/\\\*/g, '[^/]*');
      } else {
        hostRe = esc(host).replace(/\\\*/g, '[^/]*');
      }
      var pathRe = esc(path).replace(/\\\*/g, '[\\s\\S]*');
      return new RegExp('^' + scheme + '://' + hostRe + pathRe + '$');
    } catch (e) { return null; }
  }

  function anyMatch(list, url, isMatch) {
    for (var i = 0; i < list.length; i++) {
      var re = patternToRegExp(list[i], isMatch);
      if (re && re.test(url)) { return true; }
    }
    return false;
  }

  function urlMatches(meta, url, isTop) {
    if (meta.noframes && !isTop) { return false; }
    var matches = meta.matches || [];
    var includes = meta.includes || [];
    var hasPositive = matches.length > 0 || includes.length > 0;
    if (hasPositive) {
      if (!anyMatch(matches, url, true) && !anyMatch(includes, url, false)) { return false; }
    }
    if (anyMatch(meta.excludeMatches || [], url, true)) { return false; }
    if (anyMatch(meta.excludes || [], url, false)) { return false; }
    return true;
  }

  /* ---------------- bridge to the extension worker ---------------- */
  var pending = {};
  var seq = 0;

  try {
    window.addEventListener('message', function (ev) {
      if (ev.source !== window) { return; }
      var d = ev.data;
      if (!d || d.__usreply !== TOKEN) { return; }
      var cb = pending[d.id];
      if (!cb) { return; }
      delete pending[d.id];
      try { cb(!!d.ok, d.data); } catch (e) {}
    }, false);
  } catch (e) {}

  function call(action, payload, cb) {
    if (!BRIDGED) {
      localCall(action, payload || {}, cb || function () {});
      return 'local';
    }
    var id = (++seq) + '.' + Math.random().toString(36).slice(2);
    if (cb) { pending[id] = cb; }
    try {
      window.postMessage({ __usreq: TOKEN, id: id, action: action, payload: payload }, '*');
    } catch (e) {
      if (cb) { delete pending[id]; cb(false, String(e)); }
    }
    return id;
  }

  function promised(action, payload) {
    return new Promise(function (resolve, reject) {
      call(action, payload, function (ok, data) {
        if (ok) { resolve(data); } else { reject(new Error(String(data))); }
      });
    });
  }

  /* ---------------- fallbacks when injected without an extension ------- */
  function localCall(action, p, cb) {
    try {
      if (action === 'xhr') {
        var init = {
          method: p.method || 'GET',
          headers: p.headers || {},
          credentials: p.anonymous ? 'omit' : 'include',
          redirect: 'follow'
        };
        if (p.data !== null && p.data !== undefined &&
            init.method !== 'GET' && init.method !== 'HEAD') { init.body = p.data; }
        var bin = (p.responseType === 'arraybuffer' || p.responseType === 'blob');
        fetch(p.url, init).then(function (r) {
          var hdrs = [];
          try { r.headers.forEach(function (v, k) { hdrs.push(k + ': ' + v); }); } catch (e) {}
          return (bin ? r.arrayBuffer() : r.text()).then(function (body) {
            var out = {
              status: r.status, statusText: r.statusText, finalUrl: r.url,
              headers: hdrs.join('\r\n'), body: '', b64: ''
            };
            if (bin) {
              var u8 = new Uint8Array(body), str = '';
              for (var i = 0; i < u8.length; i++) { str += String.fromCharCode(u8[i]); }
              out.b64 = btoa(str);
            } else { out.body = body; }
            cb(true, out);
          });
        }).catch(function (e) { cb(false, String(e)); });
        return;
      }
      if (action === 'store_get') { cb(true, lsGet(p.id, p.key)); return; }
      if (action === 'store_set' || action === 'store_del') { cb(true, true); return; }
      if (action === 'store_get_all') { cb(true, {}); return; }
      if (action === 'open_tab') {
        try { window.open(p.url, '_blank'); } catch (e) {}
        cb(true, {}); return;
      }
      if (action === 'notify') {
        try {
          if (window.Notification && Notification.permission === 'granted') {
            new Notification(p.title || '', { body: p.text || '', icon: p.image || undefined });
          } else { console.log('[notification] ' + (p.title || '') + ': ' + (p.text || '')); }
        } catch (e) {}
        cb(true, ''); return;
      }
      if (action === 'download') {
        try {
          var a = document.createElement('a');
          a.href = p.url; a.download = p.name || '';
          a.style.display = 'none';
          (document.body || document.documentElement).appendChild(a);
          a.click(); a.remove();
        } catch (e) {}
        cb(true, {}); return;
      }
      if (action === 'cookie_list') {
        var out2 = [];
        try {
          String(document.cookie || '').split(';').forEach(function (pair) {
            var idx = pair.indexOf('=');
            if (idx < 0) { return; }
            var nm = pair.slice(0, idx).trim();
            if (p.name && nm !== p.name) { return; }
            out2.push({ name: nm, value: pair.slice(idx + 1), domain: location.hostname, path: '/' });
          });
        } catch (e) {}
        cb(true, out2); return;
      }
      if (action === 'cookie_set') {
        try {
          var c = encodeURIComponent(p.name) + '=' + String(p.value === undefined ? '' : p.value);
          c += '; path=' + (p.path || '/');
          if (p.expirationDate) { c += '; expires=' + new Date(p.expirationDate * 1000).toUTCString(); }
          if (p.secure) { c += '; secure'; }
          document.cookie = c;
        } catch (e) {}
        cb(true, true); return;
      }
      if (action === 'cookie_del') {
        try {
          document.cookie = encodeURIComponent(p.name) +
            '=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
        } catch (e) {}
        cb(true, true); return;
      }
      cb(false, 'unsupported without extension: ' + action);
    } catch (e) { cb(false, String(e)); }
  }

  /* ---------------- value storage ---------------- */
  var memStore = {};

  function lsKey(id, k) { return 'us$' + PROFILE + '$' + id + '$' + k; }

  function lsGet(id, k) {
    try {
      var v = window.localStorage.getItem(lsKey(id, k));
      if (v !== null && v !== undefined) { return v; }
    } catch (e) {}
    var mk = lsKey(id, k);
    return Object.prototype.hasOwnProperty.call(memStore, mk) ? memStore[mk] : null;
  }

  function lsSet(id, k, raw) {
    memStore[lsKey(id, k)] = raw;
    try { window.localStorage.setItem(lsKey(id, k), raw); } catch (e) {}
  }

  function lsDel(id, k) {
    delete memStore[lsKey(id, k)];
    try { window.localStorage.removeItem(lsKey(id, k)); } catch (e) {}
  }

  function lsKeys(id) {
    var prefix = lsKey(id, '');
    var out = {};
    var i, k;
    for (k in memStore) {
      if (k.indexOf(prefix) === 0) { out[k.slice(prefix.length)] = 1; }
    }
    try {
      for (i = 0; i < window.localStorage.length; i++) {
        k = window.localStorage.key(i);
        if (k && k.indexOf(prefix) === 0) { out[k.slice(prefix.length)] = 1; }
      }
    } catch (e) {}
    return Object.keys(out);
  }

  var listeners = {};
  var listenerSeq = 0;

  function fireChange(id, name, oldVal, newVal, remote) {
    var reg = listeners[id];
    if (!reg) { return; }
    for (var lid in reg) {
      if (reg[lid].name === name) {
        try { reg[lid].fn(name, oldVal, newVal, !!remote); } catch (e) {}
      }
    }
  }

  /* seed the synchronous cache from the profile-wide store */
  function hydrate(id) {
    call('store_get_all', { id: id }, function (ok, data) {
      if (!ok || !data) { return; }
      for (var k in data) {
        try {
          var mk = lsKey(id, k);
          if (memStore[mk] === undefined) {
            memStore[mk] = data[k];
            try {
              if (window.localStorage.getItem(mk) === null) {
                window.localStorage.setItem(mk, data[k]);
              }
            } catch (e) {}
          }
        } catch (e) {}
      }
    });
  }

  /* ---------------- misc helpers ---------------- */
  function b64ToBytes(b64) {
    var bin = atob(b64);
    var out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) { out[i] = bin.charCodeAt(i); }
    return out;
  }

  function addStyle(css) {
    try {
      var el = document.createElement('style');
      el.setAttribute('type', 'text/css');
      el.textContent = String(css);
      (document.head || document.documentElement).appendChild(el);
      return el;
    } catch (e) { return null; }
  }

  function addElement(a, b, c) {
    var parent, tag, attrs;
    if (typeof a === 'string') { parent = null; tag = a; attrs = b || {}; }
    else { parent = a; tag = b; attrs = c || {}; }
    var el = document.createElement(tag);
    for (var k in attrs) {
      if (k === 'textContent') { el.textContent = attrs[k]; }
      else if (k === 'innerHTML') { el.innerHTML = attrs[k]; }
      else { try { el.setAttribute(k, attrs[k]); } catch (e) {} }
    }
    (parent || document.head || document.documentElement).appendChild(el);
    return el;
  }

  function setClipboard(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(String(text));
        return;
      }
    } catch (e) {}
    try {
      var ta = document.createElement('textarea');
      ta.value = String(text);
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      (document.body || document.documentElement).appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
    } catch (e) {}
  }

  /* ---------------- per-script API factory ---------------- */
  function makeApi(meta) {
    var id = meta.id;
    hydrate(id);

    var info = {
      script: {
        name: meta.name,
        namespace: meta.namespace || '',
        version: meta.version || '',
        description: meta.description || '',
        author: meta.author || '',
        matches: meta.matches || [],
        includes: meta.includes || [],
        excludes: meta.excludes || [],
        grant: meta.grants || [],
        runAt: meta.runAt || 'document-idle',
        resources: meta.resourceList || [],
        uuid: id
      },
      scriptMetaStr: meta.metaStr || '',
      scriptHandler: 'ChromeProfileGenerator',
      version: '1.0',
      injectInto: meta.world === 'ISOLATED' ? 'content' : 'page',
      isIncognito: false,
      downloadMode: 'browser',
      profile: PROFILE,
      uuid: id
    };

    function GM_setValue(name, value) {
      var raw;
      try { raw = JSON.stringify(value); } catch (e) { raw = 'null'; }
      var oldRaw = lsGet(id, name);
      lsSet(id, name, raw);
      call('store_set', { id: id, key: String(name), value: raw });
      var oldVal;
      try { oldVal = oldRaw === null ? undefined : JSON.parse(oldRaw); } catch (e) { oldVal = undefined; }
      fireChange(id, String(name), oldVal, value, false);
      return undefined;
    }

    function GM_getValue(name, dflt) {
      var raw = lsGet(id, name);
      if (raw === null || raw === undefined) { return dflt; }
      try { return JSON.parse(raw); } catch (e) { return dflt; }
    }

    function GM_deleteValue(name) {
      var oldRaw = lsGet(id, name);
      lsDel(id, name);
      call('store_del', { id: id, key: String(name) });
      var oldVal;
      try { oldVal = oldRaw === null ? undefined : JSON.parse(oldRaw); } catch (e) { oldVal = undefined; }
      fireChange(id, String(name), oldVal, undefined, false);
    }

    function GM_listValues() { return lsKeys(id); }

    function GM_setValues(obj) {
      for (var k in obj) { GM_setValue(k, obj[k]); }
    }

    function GM_getValues(arg) {
      var out = {};
      var k;
      if (Array.isArray(arg)) {
        for (var i = 0; i < arg.length; i++) { out[arg[i]] = GM_getValue(arg[i]); }
      } else if (arg && typeof arg === 'object') {
        for (k in arg) { out[k] = GM_getValue(k, arg[k]); }
      } else {
        var keys = GM_listValues();
        for (var j = 0; j < keys.length; j++) { out[keys[j]] = GM_getValue(keys[j]); }
      }
      return out;
    }

    function GM_addValueChangeListener(name, fn) {
      var lid = 'l' + (++listenerSeq);
      if (!listeners[id]) { listeners[id] = {}; }
      listeners[id][lid] = { name: String(name), fn: fn };
      return lid;
    }

    function GM_removeValueChangeListener(lid) {
      if (listeners[id]) { delete listeners[id][lid]; }
    }

    function GM_xmlhttpRequest(details) {
      details = details || {};
      var aborted = false;
      var rt = String(details.responseType || '').toLowerCase();
      var payload = {
        method: String(details.method || 'GET').toUpperCase(),
        url: details.url,
        headers: details.headers || {},
        data: (details.data !== undefined && details.data !== null) ? String(details.data) : null,
        responseType: rt,
        timeout: details.timeout || 0,
        anonymous: !!details.anonymous
      };
      if (details.onloadstart) {
        try { details.onloadstart({ readyState: 1, status: 0, context: details.context }); } catch (e) {}
      }
      call('xhr', payload, function (ok, res) {
        if (aborted) { return; }
        if (!ok) {
          if (details.onerror) {
            try { details.onerror({ readyState: 4, status: 0, error: String(res), context: details.context }); } catch (e) {}
          }
          return;
        }
        var resp = {
          readyState: 4,
          status: res.status,
          statusText: res.statusText || '',
          responseHeaders: res.headers || '',
          finalUrl: res.finalUrl || payload.url,
          responseText: res.body || '',
          response: res.body || '',
          context: details.context
        };
        try {
          if (rt === 'json') { resp.response = JSON.parse(res.body); }
          else if (rt === 'arraybuffer') { resp.response = b64ToBytes(res.b64 || '').buffer; }
          else if (rt === 'blob') { resp.response = new Blob([b64ToBytes(res.b64 || '')]); }
          else if (rt === 'document') {
            resp.response = new DOMParser().parseFromString(res.body || '', 'text/html');
            resp.responseXML = resp.response;
          }
        } catch (e) {}
        if (details.onreadystatechange) { try { details.onreadystatechange(resp); } catch (e) {} }
        if (res.status >= 200 && res.status < 400) {
          if (details.onload) { try { details.onload(resp); } catch (e) {} }
        } else if (details.onerror) {
          try { details.onerror(resp); } catch (e) {}
        }
      });
      return { abort: function () { aborted = true; } };
    }

    function GM_openInTab(url, options) {
      var active = true;
      if (typeof options === 'boolean') { active = !options; }
      else if (options && typeof options === 'object') { active = options.active !== false; }
      var handle = { closed: false, close: function () {}, onclose: null };
      call('open_tab', { url: url, active: active });
      return handle;
    }

    function GM_notification(a, b, c, d) {
      var o;
      if (typeof a === 'object' && a !== null) { o = a; }
      else { o = { text: a, title: b, image: c, onclick: d }; }
      call('notify', {
        title: o.title || meta.name,
        text: o.text || '',
        image: o.image || '',
        silent: !!o.silent
      }, function (ok) {
        if (ok && o.ondone) { try { o.ondone(); } catch (e) {} }
      });
    }

    function GM_download(a, name) {
      var o = (typeof a === 'object' && a !== null) ? a : { url: a, name: name };
      call('download', { url: o.url, name: o.name || '' }, function (ok, data) {
        if (ok) { if (o.onload) { try { o.onload(); } catch (e) {} } }
        else if (o.onerror) { try { o.onerror({ error: String(data) }); } catch (e) {} }
      });
    }

    function GM_getResourceText(name) {
      var r = RESOURCES[name];
      if (!r) { return undefined; }
      return r.text !== undefined ? r.text : '';
    }

    function GM_getResourceURL(name) {
      var r = RESOURCES[name];
      if (!r) { return undefined; }
      if (r.url) { return r.url; }
      if (r.text !== undefined) {
        try { return 'data:text/plain;base64,' + btoa(unescape(encodeURIComponent(r.text))); } catch (e) { return ''; }
      }
      return '';
    }

    var menuCommands = {};
    var menuSeq = 0;

    function GM_registerMenuCommand(caption, fn, accessKey) {
      var mid = 'm' + (++menuSeq);
      menuCommands[mid] = { caption: caption, fn: fn, accessKey: accessKey };
      try {
        if (!window.__userscriptMenu) { window.__userscriptMenu = []; }
        window.__userscriptMenu.push({ script: meta.name, caption: caption, run: fn });
      } catch (e) {}
      return mid;
    }

    function GM_unregisterMenuCommand(mid) { delete menuCommands[mid]; }

    function GM_log() {
      try { console.log.apply(console, ['[' + meta.name + ']'].concat([].slice.call(arguments))); } catch (e) {}
    }

    var GM_cookie = {
      list: function (details, cb) {
        call('cookie_list', details || {}, function (ok, data) {
          if (cb) { cb(ok ? data : [], ok ? undefined : String(data)); }
        });
      },
      set: function (details, cb) {
        call('cookie_set', details || {}, function (ok, data) {
          if (cb) { cb(ok ? undefined : String(data)); }
        });
      },
      delete: function (details, cb) {
        call('cookie_del', details || {}, function (ok, data) {
          if (cb) { cb(ok ? undefined : String(data)); }
        });
      }
    };

    function GM_webRequest() { /* not supported */ }
    function GM_getTab(cb) { if (cb) { cb(GM_getValue('__tab__', {})); } }
    function GM_saveTab(obj) { GM_setValue('__tab__', obj); }
    function GM_getTabs(cb) { if (cb) { cb({ 0: GM_getValue('__tab__', {}) }); } }

    var GM = {
      info: info,
      setValue: function (n, v) { GM_setValue(n, v); return Promise.resolve(); },
      getValue: function (n, d) {
        return promised('store_get', { id: id, key: String(n) }).then(function (raw) {
          if (raw === null || raw === undefined) { return GM_getValue(n, d); }
          try { return JSON.parse(raw); } catch (e) { return d; }
        }).catch(function () { return GM_getValue(n, d); });
      },
      deleteValue: function (n) { GM_deleteValue(n); return Promise.resolve(); },
      listValues: function () {
        return promised('store_get_all', { id: id }).then(function (data) {
          return Object.keys(data || {});
        }).catch(function () { return GM_listValues(); });
      },
      setValues: function (o) { GM_setValues(o); return Promise.resolve(); },
      getValues: function (o) { return Promise.resolve(GM_getValues(o)); },
      addStyle: function (css) { return Promise.resolve(addStyle(css)); },
      addElement: function (a, b, c) { return Promise.resolve(addElement(a, b, c)); },
      setClipboard: function (t) { setClipboard(t); return Promise.resolve(); },
      openInTab: function (u, o) { return Promise.resolve(GM_openInTab(u, o)); },
      notification: function (o) { GM_notification(o); return Promise.resolve(); },
      download: function (o) { GM_download(o); return Promise.resolve(); },
      getResourceText: function (n) { return Promise.resolve(GM_getResourceText(n)); },
      getResourceUrl: function (n) { return Promise.resolve(GM_getResourceURL(n)); },
      registerMenuCommand: function (c, f, a) { return Promise.resolve(GM_registerMenuCommand(c, f, a)); },
      unregisterMenuCommand: function (m) { return Promise.resolve(GM_unregisterMenuCommand(m)); },
      xmlHttpRequest: GM_xmlhttpRequest,
      cookie: GM_cookie
    };

    return {
      unsafeWindow: window,
      GM: GM,
      GM_info: info,
      GM_setValue: GM_setValue,
      GM_getValue: GM_getValue,
      GM_deleteValue: GM_deleteValue,
      GM_listValues: GM_listValues,
      GM_setValues: GM_setValues,
      GM_getValues: GM_getValues,
      GM_addValueChangeListener: GM_addValueChangeListener,
      GM_removeValueChangeListener: GM_removeValueChangeListener,
      GM_addStyle: addStyle,
      GM_addElement: addElement,
      GM_xmlhttpRequest: GM_xmlhttpRequest,
      GM_openInTab: GM_openInTab,
      GM_setClipboard: setClipboard,
      GM_log: GM_log,
      GM_notification: GM_notification,
      GM_download: GM_download,
      GM_registerMenuCommand: GM_registerMenuCommand,
      GM_unregisterMenuCommand: GM_unregisterMenuCommand,
      GM_getResourceText: GM_getResourceText,
      GM_getResourceURL: GM_getResourceURL,
      GM_getResourceUrl: GM_getResourceURL,
      GM_getTab: GM_getTab,
      GM_saveTab: GM_saveTab,
      GM_getTabs: GM_getTabs,
      GM_cookie: GM_cookie,
      GM_webRequest: GM_webRequest
    };
  }

  /* ---------------- runner ---------------- */
  var done = {};
  var status = { profile: PROFILE, bridged: BRIDGED, scripts: [] };

  function note(meta, matched, ran, error) {
    try {
      status.url = location.href;
      status.scripts.push({
        name: meta.name, runAt: meta.runAt, matched: !!matched,
        ran: !!ran, error: error ? String(error).split('\n')[0].slice(0, 200) : ''
      });
    } catch (e) {}
  }

  function run(meta, names, fn) {
    try {
      var url = '';
      try { url = location.href; } catch (e) { url = ''; }
      var isTop = true;
      try { isTop = (window.top === window.self); } catch (e) { isTop = false; }
      if (!urlMatches(meta, url, isTop)) { note(meta, false, false, ''); return; }
      if (done[meta.id]) { return; }
      done[meta.id] = 1;

      var go = function () {
        var api, args, i;
        try {
          api = makeApi(meta);
          args = [];
          for (i = 0; i < names.length; i++) { args.push(api[names[i]]); }
        } catch (e) {
          note(meta, true, false, 'api: ' + ((e && e.message) || e));
          try { console.error('[userscript] ' + meta.name + ' api error:', e); } catch (e2) {}
          return;
        }
        try {
          fn.apply(window, args);
          note(meta, true, true, '');
        } catch (e) {
          note(meta, true, false, (e && e.stack) || e);
          try { console.error('[userscript] ' + meta.name + ':', e); } catch (e2) {}
        }
      };

      var phase = meta.runAt || 'document-idle';
      if (phase === 'document-start') {
        go();
      } else if (phase === 'document-body') {
        if (document.body) { go(); }
        else {
          var tries = 0;
          var iv = setInterval(function () {
            tries++;
            if (document.body) { clearInterval(iv); go(); }
            else if (tries > 20000) { clearInterval(iv); }
          }, 1);
        }
      } else if (phase === 'document-end') {
        if (document.readyState === 'loading') {
          document.addEventListener('DOMContentLoaded', go, { once: true });
        } else { go(); }
      } else {
        if (document.readyState === 'complete') { setTimeout(go, 0); }
        else { window.addEventListener('load', function () { setTimeout(go, 0); }, { once: true }); }
      }
    } catch (e) {}
  }

  var host = { run: run, matches: urlMatches, call: call, token: TOKEN, status: status };
  try {
    Object.defineProperty(window, KEY, {
      value: host, enumerable: false, configurable: true, writable: false
    });
  } catch (e) {
    try { window[KEY] = host; } catch (e2) {}
  }
})();
'''

    USERSCRIPT_BRIDGE_JS = r'''/* Userscript bridge: page/isolated world  <->  extension service worker */
(function () {
  var TOKEN = '__USTOKEN__';

  function reply(id, ok, data) {
    try {
      window.postMessage({ __usreply: TOKEN, id: id, ok: !!ok, data: data }, '*');
    } catch (e) {}
  }

  window.addEventListener('message', function (ev) {
    if (ev.source !== window) { return; }
    var d = ev.data;
    if (!d || d.__usreq !== TOKEN || !d.id || !d.action) { return; }
    try {
      chrome.runtime.sendMessage(
        { __us: true, action: d.action, payload: d.payload || {} },
        function (res) {
          if (chrome.runtime.lastError) {
            reply(d.id, false, chrome.runtime.lastError.message);
            return;
          }
          if (!res) { reply(d.id, false, 'no response'); return; }
          reply(d.id, !!res.ok, res.data);
        }
      );
    } catch (e) {
      reply(d.id, false, String(e));
    }
  }, false);
})();
'''

    USERSCRIPT_SW_JS = r'''/* Userscript service worker: privileged operations for the GM_* API */

function nsKey(id, key) { return 'us|' + id + '|' + key; }

function bufToB64(buf) {
  var bytes = new Uint8Array(buf);
  var chunk = 0x8000;
  var parts = [];
  for (var i = 0; i < bytes.length; i += chunk) {
    parts.push(String.fromCharCode.apply(null, bytes.subarray(i, i + chunk)));
  }
  return btoa(parts.join(''));
}

async function doFetch(p) {
  var ctrl = new AbortController();
  var timer = null;
  if (p.timeout && p.timeout > 0) {
    timer = setTimeout(function () { ctrl.abort(); }, p.timeout);
  }
  try {
    var init = {
      method: p.method || 'GET',
      headers: p.headers || {},
      signal: ctrl.signal,
      redirect: 'follow',
      credentials: p.anonymous ? 'omit' : 'include'
    };
    if (p.data !== null && p.data !== undefined && init.method !== 'GET' && init.method !== 'HEAD') {
      init.body = p.data;
    }
    var r = await fetch(p.url, init);
    var hdrs = [];
    r.headers.forEach(function (v, k) { hdrs.push(k + ': ' + v); });
    var wantBin = (p.responseType === 'arraybuffer' || p.responseType === 'blob');
    var body = '';
    var b64 = '';
    if (wantBin) {
      b64 = bufToB64(await r.arrayBuffer());
    } else {
      body = await r.text();
    }
    return {
      status: r.status,
      statusText: r.statusText,
      finalUrl: r.url,
      headers: hdrs.join('\r\n'),
      body: body,
      b64: b64
    };
  } finally {
    if (timer) { clearTimeout(timer); }
  }
}

async function handle(action, p) {
  if (action === 'xhr') {
    return await doFetch(p);
  }

  if (action === 'store_get') {
    var k = nsKey(p.id, p.key);
    var got = await chrome.storage.local.get(k);
    return got[k] === undefined ? null : got[k];
  }

  if (action === 'store_set') {
    var obj = {};
    obj[nsKey(p.id, p.key)] = p.value;
    await chrome.storage.local.set(obj);
    return true;
  }

  if (action === 'store_del') {
    await chrome.storage.local.remove(nsKey(p.id, p.key));
    return true;
  }

  if (action === 'store_get_all') {
    var all = await chrome.storage.local.get(null);
    var prefix = 'us|' + p.id + '|';
    var out = {};
    for (var key in all) {
      if (key.indexOf(prefix) === 0) { out[key.slice(prefix.length)] = all[key]; }
    }
    return out;
  }

  if (action === 'open_tab') {
    var tab = await chrome.tabs.create({ url: p.url, active: p.active !== false });
    return { id: tab.id };
  }

  if (action === 'notify') {
    var opts = {
      type: 'basic',
      title: String(p.title || 'Userscript'),
      message: String(p.text || ''),
      iconUrl: p.image || 'icon.png',
      silent: !!p.silent
    };
    try {
      return await chrome.notifications.create('', opts);
    } catch (e) {
      delete opts.iconUrl;
      opts.iconUrl = 'icon.png';
      return await chrome.notifications.create('', opts);
    }
  }

  if (action === 'download') {
    var d = { url: p.url };
    if (p.name) { d.filename = p.name; }
    var dlId = await chrome.downloads.download(d);
    return { id: dlId };
  }

  if (action === 'cookie_list') {
    var q = {};
    if (p.url) { q.url = p.url; }
    if (p.domain) { q.domain = p.domain; }
    if (p.name) { q.name = p.name; }
    if (p.path) { q.path = p.path; }
    return await chrome.cookies.getAll(q);
  }

  if (action === 'cookie_set') {
    var c = {
      url: p.url,
      name: p.name,
      value: String(p.value === undefined ? '' : p.value)
    };
    if (p.domain) { c.domain = p.domain; }
    if (p.path) { c.path = p.path; }
    if (p.secure !== undefined) { c.secure = !!p.secure; }
    if (p.httpOnly !== undefined) { c.httpOnly = !!p.httpOnly; }
    if (p.expirationDate) { c.expirationDate = p.expirationDate; }
    if (p.sameSite) { c.sameSite = p.sameSite; }
    return await chrome.cookies.set(c);
  }

  if (action === 'cookie_del') {
    return await chrome.cookies.remove({ url: p.url, name: p.name });
  }

  throw new Error('unknown action: ' + action);
}

chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
  if (!msg || msg.__us !== true) { return false; }
  handle(msg.action, msg.payload || {}).then(
    function (data) { sendResponse({ ok: true, data: data }); },
    function (err) { sendResponse({ ok: false, data: String((err && err.message) || err) }); }
  );
  return true;
});
'''

    USERSCRIPT_ICON_B64 = (
        "iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAYAAABXAvmHAAAB60lEQVR4nO2aTyhEQRzHP9am"
        "Vi0Oilw5uDk6SU5ctEdSDnLlhlJydHIjRyUlcXJQKPKnJNkif07YgyOlFpHYdZiW9ezbndk3"
        "b9/ss5967TS9N9/vd34z07ZvoYS3lOkcLDKdTMrctzZSpk3X8UCypu1wGibvh50at5JvEOWH"
        "dBu3ohokoHKz2+bz0ZAOUAjz+WhJBSikeVXNnAG8MK+inTWAl+ZlPdgGMMF8imxeMgYwyXwK"
        "O09Kx6iJ/Alg4uynyOTNXxUwefZTWD0G3RBZGoK+WdFurIP+NggG4DMBM5vw8KRPy/UlNNwp"
        "TE+swMYZDLTrHf87gFvLp7oSKspF+/gG1k+dj5nu1ZUllM7iAUz1QjQGe1dwfqd3fNcD7FyK"
        "mW9tgsEOOLqG5UN942vbA1M9f/uqQtDcAM9vsH0Bk6vQ1aJLUaAtQDgEtWGor4HHl5/+0W7R"
        "DyLQfVyXokDbElrYh/GIaM/vis/4K8xtwVg3vH9AIilOJJ1oC3ByKy4r0Zi43MJfXyWKEf8E"
        "0Plzn9uke/VPBYqVXwGKYRlZPfqrAmB2FTJ5818FwMwq2HmyrYBJIbJ5ybqETAiRy0POPeBl"
        "CBltqU3sRQhZTelTqJAhVLSUjtFChFDV+H+vWa0U7YvuTHjxV4MSXvMFlgSqXrfE5eoAAAAA"
        "SUVORK5CYII="
    )

    # ==================================================================
    #  USERSCRIPTS  (Tampermonkey-style JS injection)
    # ==================================================================
    #  Scripts live once in  <profiles_dir>/_userscripts/*.user.js  and are
    #  compiled into a per-profile MV3 extension
    #  (<profile>/_userscripts_extension) that is passed to Chrome through
    #  --load-extension alongside the fingerprint extension.
    # ------------------------------------------------------------------

    USERSCRIPT_EXT_DIRNAME = '_userscripts_extension'

    # Names handed to every userscript as function parameters, in this order.
    USERSCRIPT_API_NAMES = [
        "unsafeWindow", "GM", "GM_info",
        "GM_setValue", "GM_getValue", "GM_deleteValue", "GM_listValues",
        "GM_setValues", "GM_getValues",
        "GM_addValueChangeListener", "GM_removeValueChangeListener",
        "GM_addStyle", "GM_addElement", "GM_xmlhttpRequest",
        "GM_openInTab", "GM_setClipboard", "GM_log", "GM_notification",
        "GM_download", "GM_registerMenuCommand", "GM_unregisterMenuCommand",
        "GM_getResourceText", "GM_getResourceURL", "GM_getResourceUrl",
        "GM_getTab", "GM_saveTab", "GM_getTabs",
        "GM_cookie", "GM_webRequest",
    ]

    USERSCRIPT_RUN_AT = {
        'document-start': 'document_start',
        'document_start': 'document_start',
        'document-body': 'document_start',
        'document_body': 'document_start',
        'document-end': 'document_end',
        'document_end': 'document_end',
        'document-idle': 'document_idle',
        'document_idle': 'document_idle',
        'context-menu': 'document_idle',
        'context_menu': 'document_idle',
    }

    USERSCRIPT_TEMPLATE = """// ==UserScript==
// @name         %(name)s
// @namespace    chrome-profile-generator
// @version      1.0
// @description  Injected into every profile created by this tool
// @author       you
// @match        *://*/*
// @run-at       document-idle
// @grant        GM_addStyle
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_xmlhttpRequest
// ==/UserScript==

(function () {
    'use strict';

    console.log('[%(name)s] running on', location.href);

    // Example: your code goes here.
    // GM_addStyle('body { outline: 2px solid #4f8cff; }');

})();
"""

    # ------------------------------------------------------------------
    # storage layout
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # v3.2: Chrome feature flags
    # ------------------------------------------------------------------
    #  Chrome honours only the LAST --disable-features on the command line,
    #  so every value has to travel in one flag. Before v3.2 the args list
    #  carried seven separate --disable-features switches and six of them
    #  (including AutomationControlled and UserAgentClientHint) were being
    #  silently dropped.
    # ------------------------------------------------------------------
    DISABLED_FEATURES = [
        "UserAgentClientHint",
        "UserAgentClientHintFullVersionList",
        "PrivacySandboxSettings4",
        "InterestFeedContentSuggestions",
        "IsolateOrigins",
        "site-per-process",
        "AutomationControlled",
        "ChromeCleanup",
        "TranslateUI",
        "CalculateNativeWinOcclusion",
        # v5.0: Chrome 88+ drops a hidden page to one timer wake per minute.
        # Must live here: a second --disable-features switch would REPLACE
        # this list instead of adding to it.
        "IntensiveWakeUpThrottling",
        "WinRetrieveSuggestionsOnlyOnDemand",
        "AvoidUnnecessaryBeforeUnloadCheckSync",
        "SubresourceWebBundles",
        # Chrome 137-141 refuse --load-extension unless this is disabled.
        # Harmless on older builds and on Chromium forks.
        "DisableLoadExtensionCommandLineSwitch",
    ]

    ENABLED_FEATURES = [
        "NetworkService",
        "NetworkServiceInProcess",
    ]

    def _disabled_features(self):
        return ','.join(self.DISABLED_FEATURES)

    def _enabled_features(self):
        return ','.join(self.ENABLED_FEATURES)

    # ------------------------------------------------------------------
    # v3.2: which browser are we driving, and will it load our extensions?
    # ------------------------------------------------------------------
    BROWSER_BRANDS = [
        ('chrome for testing', 'Chrome for Testing'),
        ('firefox', 'Firefox'),
        ('librewolf', 'LibreWolf'),
        ('waterfox', 'Waterfox'),
        ('chrome-for-testing', 'Chrome for Testing'),
        ('brave', 'Brave'),
        ('msedge', 'Edge'),
        ('microsoft edge', 'Edge'),
        ('chromium', 'Chromium'),
        ('chrome', 'Google Chrome'),
    ]

    def detect_browser_info(self, exe=None):
        """Identify the browser and whether --load-extension still works.

        Google removed --load-extension from branded Chrome in 137 (the
        DisableLoadExtensionCommandLineSwitch escape hatch covered 137-141)
        and removed the escape hatch too in 142. Chromium, Brave, Edge and
        Chrome for Testing are unaffected.
        """
        exe = exe or self._find_chrome_path()
        cache = getattr(self, '_browser_info_cache', None)
        if cache is None:
            cache = self._browser_info_cache = {}
        if exe in cache:
            return dict(cache[exe])
        info = {
            'path': exe or '',
            'brand': 'Unknown',
            'version': '',
            'major': 0,
            'load_extension': True,
            'note': '',
        }
        if not exe:
            info['load_extension'] = False
            info['note'] = 'No Chrome/Chromium build was found on this system.'
            return info

        low = exe.replace('\\', '/').lower()
        for needle, brand in self.BROWSER_BRANDS:
            if needle in low:
                info['brand'] = brand
                break

        version = ''
        try:
            if platform.system() == 'Windows':
                app_dir = os.path.dirname(exe)
                for name in sorted(os.listdir(app_dir), reverse=True):
                    if re.match(r'^\d+\.\d+\.\d+\.\d+$', name):
                        version = name
                        break
        except Exception:
            version = ''
        if not version:
            try:
                out = subprocess.run([exe, '--version'], capture_output=True,
                                     timeout=8, text=True).stdout or ''
                m = re.search(r'(\d+\.\d+\.\d+\.\d+)', out)
                if m:
                    version = m.group(1)
                if 'chromium' in out.lower() and info['brand'] == 'Unknown':
                    info['brand'] = 'Chromium'
            except Exception:
                pass

        info['version'] = version
        try:
            info['major'] = int(version.split('.')[0]) if version else 0
        except Exception:
            info['major'] = 0

        branded = info['brand'] == 'Google Chrome'
        if branded and info['major'] >= 142:
            info['load_extension'] = False
            info['note'] = (
                'Google Chrome %s removed --load-extension (and its override) '
                'in 142. Fingerprint + user-script extensions will NOT load. '
                'Use Chromium, Brave, Edge or Chrome for Testing instead.'
                % info['version'])
        elif branded and info['major'] >= 137:
            info['note'] = (
                'Google Chrome %s needs the DisableLoadExtensionCommandLineSwitch '
                'override, which this tool now adds automatically.' % info['version'])
        elif info['major'] == 0:
            info['note'] = 'Could not read the browser version; assuming extensions load.'
        cache[exe] = dict(info)
        return info

    def browser_warning(self):
        """Short human-readable warning, or '' when everything is fine."""
        info = self.detect_browser_info()
        mode = self.injection_mode()
        if info['load_extension']:
            return ''
        if mode in ('cdp', 'both'):
            return ('NOTE  %s cannot load extensions, so scripts are injected '
                    'over the DevTools Protocol instead. Nothing to enable - '
                    'just launch the profile from its desktop shortcut.'
                    % (info['brand'] + ' ' + info['version']).strip())
        return 'WARNING  ' + info['note']

    # ------------------------------------------------------------------
    # v3.3: extension-free injection over the DevTools Protocol
    # ------------------------------------------------------------------
    USERSCRIPT_CDP_PY = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Injects JavaScript into every page of one Chrome profile.

Runs next to Chrome and talks the DevTools Protocol over a loopback
WebSocket. Nothing is installed in the browser: no extension, no
developer-mode prompt, nothing to allow. Works on Chrome 137+ / 142+
where --load-extension no longer functions.

Pure standard library, so it runs under whatever Python launched it.
Every decision is written to inject.log next to this file.
"""
import base64
import json
import os
import socket
import struct
import sys
import threading
import time
import urllib.request
from urllib.parse import urlparse

PROFILE_DIR = r"""__PROFILE_DIR__"""
PAYLOAD_FILE = r"""__PAYLOAD_FILE__"""
INDEX_FILE = r"""__INDEX_FILE__"""
HOST_KEY = r"""__USHOSTKEY__"""
SELFTEST_URL = r"""__USSELFTEST__"""
# v4.4: open SELFTEST_URL as an extra tab? No - the browser already opens the
# start page on the command line, so a second tab would just be a duplicate.
OPEN_SELFTEST = False
# v4.4: guard the generated browser. When on, opening DevTools or the
# extensions page closes the whole browser.
GUARD_DEVTOOLS = __USGUARD__
# v4.5: site lock. Registrable domains this profile is allowed to open.
# An empty tuple means no restriction at all (pre-4.5 behaviour).
SITE_LOCK = __USSITELOCK__
# v4.5: close the whole browser as soon as a second tab exists.
LOCK_SINGLE_TAB = __USSINGLETAB__
VERBOSE = __USVERBOSE__
LOG_FILE = os.path.join(PROFILE_DIR, '_inject', 'inject.log')

SKIP_PREFIXES = ('devtools://', 'chrome-untrusted://')
WEBUI_PREFIXES = ('chrome://', 'edge://', 'brave://', 'about:')
# v4.4: pages that mean "the user is trying to manage extensions" - opening
# any of these trips the guard just like DevTools does
GUARD_URL_MARKERS = ('chrome://extensions', 'edge://extensions',
                     'brave://extensions', 'about:addons',
                     'chrome://inspect', 'edge://inspect')
PAGE_TYPES = ('page', 'iframe', 'webview')
# v4.5: what a tab shows before it has actually navigated anywhere. These
# must never trip the site lock or the browser would close on startup.
NEUTRAL_URLS = ('about:blank', 'about:newtab', 'chrome://newtab',
                'chrome://new-tab-page', 'edge://newtab')
MAX_LOG_BYTES = 256 * 1024
# v4.8: when this launcher started. A DevToolsActivePort older than this is
# left over from a previous run and its port may now belong to anything.
try:
    LAUNCH_EPOCH = float(os.environ.get('MVL_LAUNCH_EPOCH', '') or 0)
except Exception:
    LAUNCH_EPOCH = 0.0
AUTO_ATTACH = {'autoAttach': True, 'waitForDebuggerOnStart': True, 'flatten': True}

# localhost must never be sent through a system or corporate proxy
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        try:
            if os.path.getsize(LOG_FILE) > MAX_LOG_BYTES:
                os.remove(LOG_FILE)
        except OSError:
            pass
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write('%s  %s\n' % (time.strftime('%H:%M:%S'), msg))
    except Exception:
        pass


# ----------------------------------------------------------------------
# minimal RFC6455 client
# ----------------------------------------------------------------------
class WebSocket(object):
    def __init__(self, url, timeout=15):
        u = urlparse(url)
        port = u.port or 80
        self.sock = socket.create_connection((u.hostname, port), timeout=timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        path = u.path or '/'
        if u.query:
            path += '?' + u.query
        key = base64.b64encode(os.urandom(16)).decode('ascii')
        req = (
            'GET %s HTTP/1.1\r\n'
            'Host: %s:%d\r\n'
            'Upgrade: websocket\r\n'
            'Connection: Upgrade\r\n'
            'Sec-WebSocket-Key: %s\r\n'
            'Sec-WebSocket-Version: 13\r\n'
            '\r\n' % (path, u.hostname, port, key)
        )
        self.sock.sendall(req.encode('ascii'))
        buf = b''
        while b'\r\n\r\n' not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise IOError('handshake closed')
            buf += chunk
        head, rest = buf.split(b'\r\n\r\n', 1)
        if b' 101' not in head.split(b'\r\n')[0]:
            raise IOError('no websocket upgrade: %r' % head[:80])
        self._rest = rest
        self.sock.settimeout(None)
        self._send_lock = threading.Lock()

    def _read(self, n):
        out = b''
        if self._rest:
            out = self._rest[:n]
            self._rest = self._rest[n:]
        while len(out) < n:
            chunk = self.sock.recv(min(65536, n - len(out)))
            if not chunk:
                raise IOError('connection closed')
            out += chunk
        return out

    def recv(self):
        data = b''
        while True:
            b1, b2 = self._read(2)
            fin = b1 & 0x80
            opcode = b1 & 0x0F
            masked = b2 & 0x80
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack('>H', self._read(2))[0]
            elif length == 127:
                length = struct.unpack('>Q', self._read(8))[0]
            mask = self._read(4) if masked else None
            payload = self._read(length) if length else b''
            if mask:
                payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
            if opcode == 0x8:
                raise IOError('peer closed')
            if opcode == 0x9:
                self._frame(payload, 0xA)
                continue
            if opcode == 0xA:
                continue
            data += payload
            if fin:
                return data.decode('utf-8', 'replace')

    def _frame(self, payload, opcode):
        if isinstance(payload, str):
            payload = payload.encode('utf-8')
        header = bytearray([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack('>H', n)
        else:
            header.append(0x80 | 127)
            header += struct.pack('>Q', n)
        mask = os.urandom(4)
        header += mask
        body = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
        with self._send_lock:
            self.sock.sendall(bytes(header) + body)

    def send(self, text):
        self._frame(text, 0x1)

    def close(self):
        try:
            self._frame(b'', 0x8)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


# ----------------------------------------------------------------------
# discovery
# ----------------------------------------------------------------------
def _pid_on_port(port):
    """PID listening on a local TCP port, or 0 if it cannot be determined."""
    if os.name != 'nt':
        return 0
    import subprocess as _sp
    try:
        out = _sp.check_output(['netstat', '-ano', '-p', 'TCP'],
                               stderr=_sp.DEVNULL, timeout=20,
                               creationflags=0x08000000).decode('utf-8', 'ignore')
    except Exception:
        return 0
    tail = ':%d' % port
    for line in out.splitlines():
        parts = line.split()
        if (len(parts) >= 5 and parts[3].upper() == 'LISTENING'
                and parts[1].endswith(tail)):
            try:
                return int(parts[-1])
            except ValueError:
                return 0
    return 0


def _cmdline_of(pid):
    """Full command line of a PID, or '' if it cannot be read.

    v4.9: WMIC was removed in Windows 11 24H2, so it can no longer be
    the primary source - on a current machine it simply is not there,
    this function returned '' and port_owner_is_ours then waved the
    injector through onto whatever browser held the port. Windows
    PowerShell 5.1 ships with every supported Windows and answers this
    reliably, so it goes first; pwsh covers boxes where 5.1 was removed;
    wmic stays last for old Windows 10 builds with PowerShell locked
    down. -ExecutionPolicy Bypass matters: a Restricted policy is the
    other common way the old PowerShell attempt returned nothing.
    """
    import subprocess as _sp
    _ps = ("$p = Get-CimInstance Win32_Process -Filter 'ProcessId=%d' "
           "-ErrorAction SilentlyContinue; if ($p) { $p.CommandLine }" % pid)
    for argv, prefix in (
            (['powershell', '-NoProfile', '-NonInteractive',
              '-ExecutionPolicy', 'Bypass', '-Command', _ps], ''),
            (['pwsh', '-NoProfile', '-NonInteractive',
              '-ExecutionPolicy', 'Bypass', '-Command', _ps], ''),
            (['wmic', 'process', 'where', 'ProcessId=%d' % pid,
              'get', 'CommandLine', '/FORMAT:LIST'], 'CommandLine=')):
        try:
            out = _sp.check_output(argv, stderr=_sp.DEVNULL, timeout=20,
                                   creationflags=0x08000000
                                   ).decode('utf-8', 'ignore')
        except Exception:
            continue
        if prefix:
            for line in out.splitlines():
                if line.strip().startswith(prefix):
                    return line.split('=', 1)[1]
        elif out.strip():
            return out
    return ''


def port_owner_is_ours(port):
    """True when the browser listening on `port` is THIS profile's Chrome.

    Windows recycles ephemeral ports, and a hard kill (taskkill /F) never
    lets Chrome delete DevToolsActivePort. So the port in that file can
    easily belong to a different browser by the time we read it -
    including the user's own everyday Chrome. Attaching there would push
    the DevTools guard and the site lock into a browser we do not own:
    F12, right-click Inspect and Save image would stop working there, and
    the first navigation outside the allowed sites would close it.

    v4.9: this now FAILS CLOSED. The old version returned True whenever
    ownership could not be determined, and since _cmdline_of depended on
    WMIC - gone from Windows 11 24H2 - "could not be determined" became
    the normal answer rather than the rare one. That is exactly how the
    DevTools guard and the site lock ended up inside the user's own
    everyday Chrome. Losing injection on a locked-down box is a far
    smaller problem than breaking the browser the person actually uses,
    so a port whose owner cannot be proven is now treated as somebody
    else's and left alone. Every refusal is logged with its reason.

    v4.10: the identity proof now comes first and settles it on every OS.
    DevToolsActivePort line 2 is the browser target UUID of the process
    that owns THIS profile directory; /json/version reports the UUID of
    whatever is really on the port. Equal means ours, different means
    somebody else's, and neither answer needs netstat, PowerShell or
    WMIC. The command-line check below is kept only for the case where
    the UUID cannot be read at all, and it still fails closed.
    """
    verdict = identity_verdict(port)
    if verdict == 'ours':
        return True
    if verdict == 'theirs':
        log('ownership: port %d is served by a DIFFERENT browser instance '
            '(target UUID does not match this profile) - NOT attaching'
            % port)
        return False

    # verdict == 'unknown': fall back to the command line, fail closed.
    if os.name != 'nt':
        log('ownership: could not read the browser target UUID on port %d '
            'and there is no command-line check off Windows - NOT attaching'
            % port)
        return False
    want = os.path.normcase(os.path.abspath(PROFILE_DIR))
    pid = _pid_on_port(port)
    if not pid:
        log('ownership: nothing is listening on port %d - not attaching'
            % port)
        return False
    cmd = _cmdline_of(pid)
    if not cmd.strip():
        log('ownership: could not read the command line of PID %d '
            '(PowerShell and WMIC both failed) - NOT attaching, because '
            'this port may belong to another Chrome' % pid)
        return False
    if want in os.path.normcase(cmd):
        return True
    log('ownership: PID %d on port %d is not this profile - not attaching'
        % (pid, port))
    return False


def wait_for_port(timeout=60):
    """Chrome writes the port it actually bound to into DevToolsActivePort.

    v4.8: a file older than this launch is ignored. Chrome needs a second
    or two to bind and rewrite it, and reading the previous run's value in
    that window is exactly how the injector used to end up on the wrong
    browser.
    """
    path = os.path.join(PROFILE_DIR, 'DevToolsActivePort')
    deadline = time.time() + timeout
    warned = False
    while time.time() < deadline:
        try:
            if LAUNCH_EPOCH:
                if os.path.getmtime(path) < LAUNCH_EPOCH - 3:
                    if not warned:
                        log('ignoring a DevToolsActivePort left by an earlier '
                            'run; waiting for Chrome to write a fresh one')
                        warned = True
                    time.sleep(0.15)
                    continue
            with open(path, 'r', encoding='utf-8') as f:
                first = f.read().split('\n')[0].strip()
            port = int(first)
            if port > 0:
                return port
        except Exception:
            pass
        time.sleep(0.15)
    return 0


def browser_socket(port, timeout=30):
    deadline = time.time() + timeout
    url = 'http://127.0.0.1:%d/json/version' % port
    last = ''
    while time.time() < deadline:
        try:
            with OPENER.open(url, timeout=3) as resp:
                return json.load(resp).get('webSocketDebuggerUrl')
        except Exception as exc:
            last = str(exc)
            time.sleep(0.25)
    log('could not reach %s (%s)' % (url, last))
    return None


def our_browser_token():
    """Line 2 of this profile's DevToolsActivePort: /devtools/browser/<uuid>.

    Written by the Chrome instance that owns this profile directory, and
    rewritten every launch. It is the strongest ownership evidence we can
    get and it costs nothing - no netstat, no PowerShell, no WMIC.
    """
    try:
        path = os.path.join(PROFILE_DIR, 'DevToolsActivePort')
        with open(path, 'r', encoding='utf-8') as handle:
            lines = handle.read().split(chr(10))
        if len(lines) > 1 and lines[1].strip():
            return lines[1].strip()
    except Exception:
        pass
    return ''


def live_browser_token(port):
    """The browser target path actually served on `port`, or ''."""
    try:
        with OPENER.open('http://127.0.0.1:%d/json/version' % port,
                         timeout=3) as resp:
            ws = json.load(resp).get('webSocketDebuggerUrl') or ''
    except Exception:
        return ''
    try:
        parsed = urlparse(ws)
        return parsed.path or ''
    except Exception:
        return ''


def identity_verdict(port):
    """'ours', 'theirs', or 'unknown' for the browser on `port`."""
    mine = our_browser_token()
    theirs = live_browser_token(port)
    if not mine or not theirs:
        return 'unknown'
    return 'ours' if mine == theirs else 'theirs'


def load_payloads():
    """Each script is sent separately so one bad script cannot kill the rest."""
    parts = []
    try:
        with open(INDEX_FILE, 'r', encoding='utf-8') as f:
            names = json.load(f)
        base = os.path.dirname(INDEX_FILE)
        for name in names:
            try:
                with open(os.path.join(base, name), 'r', encoding='utf-8') as f:
                    parts.append((name, f.read()))
            except Exception as exc:
                log('cannot read %s: %s' % (name, exc))
    except Exception as exc:
        log('no index (%s), falling back to the single payload file' % exc)
        try:
            with open(PAYLOAD_FILE, 'r', encoding='utf-8') as f:
                parts = [('payload.js', f.read())]
        except Exception as exc2:
            log('no payload at all: %s' % exc2)
    return [(n, src) for n, src in parts if src.strip()]


def _host_of(url):
    """Host of a URL, lower case, without a leading www."""
    try:
        host = (urlparse(url).hostname or '').lower()
    except Exception:
        return ''
    return host[4:] if host.startswith('www.') else host


def host_allowed(host):
    """True when host is in SITE_LOCK or is a subdomain of an entry."""
    if not SITE_LOCK:
        return True
    if not host:
        return False
    for allowed in SITE_LOCK:
        if host == allowed or host.endswith('.' + allowed):
            return True
    return False


def port_alive(port):
    try:
        socket.create_connection(('127.0.0.1', port), timeout=1).close()
        return True
    except Exception:
        return False


def _hard_kill_browser():
    """Backup for Browser.close: kill the browser bound to this profile.

    Matched by the --user-data-dir / -profile flag on its command line so
    only this profile's browser is affected, never the user's own.
    """
    needle = os.path.normcase(os.path.abspath(PROFILE_DIR))
    import subprocess as _sp
    try:
        if os.name == 'nt':
            # WMIC gives the full command line; taskkill by PID
            out = _sp.check_output(
                ['wmic', 'process', 'where',
                 "name like '%chrome%' or name like '%firefox%' "
                 "or name like '%brave%' or name like '%msedge%'",
                 'get', 'ProcessId,CommandLine', '/FORMAT:LIST'],
                stderr=_sp.DEVNULL, timeout=8).decode('utf-8', 'ignore')
            block = {}
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    if block.get('CommandLine') and block.get('ProcessId'):
                        cmd = os.path.normcase(block['CommandLine'])
                        if needle in cmd:
                            # v4.5: /T takes the child processes too. Chrome's
                            # renderers and GPU process do NOT carry
                            # --user-data-dir, so without /T they are orphaned
                            # by every hard kill and pile up until Windows
                            # cannot start a new renderer at all.
                            _sp.call(['taskkill', '/F', '/T', '/PID',
                                      block['ProcessId']],
                                     stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
                    block = {}
                    continue
                if '=' in line:
                    k, v = line.split('=', 1)
                    block[k.strip()] = v.strip()
        else:
            out = _sp.check_output(['ps', 'ax', '-o', 'pid=,command='],
                                   stderr=_sp.DEVNULL, timeout=8
                                   ).decode('utf-8', 'ignore')
            import signal as _sig
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    pid_str, cmd = line.split(None, 1)
                    pid = int(pid_str)
                except Exception:
                    continue
                if needle in os.path.normcase(cmd):
                    try:
                        os.kill(pid, _sig.SIGTERM)
                    except Exception:
                        pass
    except Exception as exc:
        log('hard kill failed: %s' % exc)


# ----------------------------------------------------------------------
class Session(object):
    """One DevTools connection: injects into every page it can reach."""

    def __init__(self, ws, payloads):
        self.ws = ws
        self.payloads = payloads
        self.counter = 0
        self.lock = threading.Lock()
        self.pending = {}
        self.attached = set()
        self.injected = 0
        self.guard_tripped = False
        # v4.5: page targets currently open, for the single-tab lock
        self.pages = set()

    def guard_trip(self, reason):
        """Developer tools / the extensions page were opened - shut the whole
        browser down. Called from the CDP event loop, so it is safe to send."""
        if self.guard_tripped:
            return
        self.guard_tripped = True
        log('GUARD tripped: %s -> closing the browser' % reason)
        # let any page that is still open flash the warning banner first
        try:
            self.send('Runtime.evaluate',
                      {'expression': 'void 0'})
        except Exception:
            pass
        def shut():
            try:
                self.send('Browser.close')
            except Exception:
                pass
            # Browser.close is usually enough; if it is refused, take the
            # process down the hard way so DevTools cannot stay open
            time.sleep(1.2)
            try:
                _hard_kill_browser()
            except Exception:
                pass
        t = threading.Timer(0.35, shut)
        t.daemon = True
        t.start()

    def send(self, method, params=None, session=None, on_result=None):
        with self.lock:
            self.counter += 1
            mid = self.counter
            if on_result:
                self.pending[mid] = on_result
        msg = {'id': mid, 'method': method, 'params': params or {}}
        if session:
            msg['sessionId'] = session
        try:
            self.ws.send(json.dumps(msg))
        except Exception as exc:
            log('send %s failed: %s' % (method, exc))
        return mid

    def attach(self, target_id):
        if not target_id or target_id in self.attached:
            return
        self.attached.add(target_id)
        self.send('Target.attachToTarget', {'targetId': target_id, 'flatten': True})

    def _report(self, label):
        def handler(msg):
            err = msg.get('error')
            if err:
                log('  FAILED %s: %s' % (label, str(err)[:200]))
                return
            details = (msg.get('result') or {}).get('exceptionDetails')
            if details:
                exc = details.get('exception') or {}
                text = exc.get('description') or details.get('text') or str(details)
                first = str(text).split('\n')[0][:200]
                log('  ERROR  %s: %s' % (label, first))
        return handler

    def inject(self, session, info, waiting):
        url = info.get('url') or ''
        kind = info.get('type') or '?'
        if kind not in PAGE_TYPES or url.startswith(SKIP_PREFIXES):
            log('skip   %-8s %s' % (kind, url[:70]))
            return False

        # one call per script: a syntax error in one cannot stop the others
        for name, source in self.payloads:
            self.send('Page.addScriptToEvaluateOnNewDocument',
                      {'source': source, 'runImmediately': True}, session,
                      on_result=self._report('register ' + name))

        evaluable = (url and not url.startswith(WEBUI_PREFIXES)
                     and not url.startswith('about:'))
        if not waiting and evaluable:
            # tab was already open and loaded before we attached, so also run
            # the scripts in the document that is on screen right now
            for name, source in self.payloads:
                self.send('Runtime.evaluate',
                          {'expression': source, 'awaitPromise': False,
                           'returnByValue': False}, session,
                          on_result=self._report('run ' + name))

        # follow popups and out-of-process iframes opened from here
        self.send('Target.setAutoAttach', AUTO_ATTACH, session)
        if VERBOSE:
            # report on every page this tab navigates to from now on
            self.send('Page.enable', {}, session)
        self.injected += 1
        log('inject %-8s %s' % (kind, url[:70]))
        if VERBOSE:
            self.schedule_probe(session)
        return True

    def schedule_probe(self, session, delay=4.0):
        """Ask the page itself what the runtime did. This is the only way to
        see a script that loaded but never matched or threw."""
        expression = (
            '(function(){try{var h=window[' + json.dumps(HOST_KEY) + '];'
            'if(!h){return "RUNTIME NOT PRESENT";}'
            'return JSON.stringify(h.status);}catch(e){return "probe error: "+e;}})()'
        )

        def fire():
            self.send('Runtime.evaluate',
                      {'expression': expression, 'returnByValue': True},
                      session, on_result=self._probed)

        timer = threading.Timer(delay, fire)
        timer.daemon = True
        timer.start()

    def _probed(self, msg):
        if msg.get('error'):
            log('  probe failed: %s' % str(msg['error'])[:150])
            return
        value = ((msg.get('result') or {}).get('result') or {}).get('value')
        if not value:
            log('  probe: no answer')
            return
        if not str(value).startswith('{'):
            log('  probe: %s' % value)
            return
        try:
            data = json.loads(value)
        except Exception:
            log('  probe: %s' % str(value)[:200])
            return
        log('  page says: url=%s bridged=%s' % (
            str(data.get('url'))[:60], data.get('bridged')))
        scripts = data.get('scripts') or []
        if not scripts:
            log('    no scripts evaluated on this page')
        for item in scripts:
            if item.get('ran'):
                state = 'RAN'
            elif not item.get('matched'):
                state = 'did not match this URL'
            else:
                state = 'THREW: ' + (item.get('error') or '?')
            log('    %-28s %s' % (str(item.get('name'))[:28], state))

    def guard_check(self, info):
        """Trip the guard if a target is DevTools or the extensions page."""
        if not GUARD_DEVTOOLS or self.guard_tripped:
            return False
        kind = (info.get('type') or '').lower()
        url = (info.get('url') or '').lower()
        title = (info.get('title') or '').lower()
        if url.startswith('devtools://') or kind == 'devtools':
            self.guard_trip('DevTools opened')
            return True
        for marker in GUARD_URL_MARKERS:
            if url.startswith(marker):
                self.guard_trip('opened %s' % marker)
                return True
        if 'devtools' in title:
            self.guard_trip('DevTools window')
            return True
        return False

    def tab_check(self, info):
        """Trip the guard when a second tab is opened.

        Only real top-level pages count: iframes, workers and the browser
        target itself are not tabs.
        """
        if not LOCK_SINGLE_TAB or self.guard_tripped:
            return False
        if (info.get('type') or '').lower() != 'page':
            return False
        url = (info.get('url') or '')
        if url.startswith(SKIP_PREFIXES):
            return False
        target_id = info.get('targetId')
        if not target_id:
            return False
        if target_id in self.pages:
            return False
        self.pages.add(target_id)
        if len(self.pages) > 1:
            self.guard_trip('a second tab was opened')
            return True
        return False

    def site_check(self, info):
        """Trip the guard on a top-level page outside SITE_LOCK."""
        if not SITE_LOCK or self.guard_tripped:
            return False
        if (info.get('type') or '').lower() != 'page':
            return False
        url = info.get('url') or ''
        if not url or url.startswith(NEUTRAL_URLS):
            return False
        if url.startswith(SKIP_PREFIXES) or url.startswith(WEBUI_PREFIXES):
            # chrome:// pages are handled by guard_check; the rest of them
            # (settings, history) are harmless and must not close the browser
            return False
        host = _host_of(url)
        if host_allowed(host):
            return False
        self.guard_trip('blocked site: %s' % (host or url[:60]))
        return True

    def run(self):
        self.send('Target.setDiscoverTargets', {'discover': True})
        self.send('Target.setAutoAttach', AUTO_ATTACH)

        # setAutoAttach only fires for targets created from now on, so the tab
        # Chrome already opened at startup has to be picked up explicitly
        def got_targets(msg):
            infos = ((msg or {}).get('result') or {}).get('targetInfos') or []
            pages = [i for i in infos if i.get('type') in PAGE_TYPES]
            log('%d existing target(s), %d injectable' % (len(infos), len(pages)))
            if VERBOSE:
                for info in infos:
                    log('  target %-16s %s' % (info.get('type'),
                                               (info.get('url') or '')[:78]))
                exts = [i for i in infos
                        if (i.get('url') or '').startswith('chrome-extension://')]
                log('  extensions loaded: %d%s' % (
                    len(exts),
                    '' if exts else '  <-- none; --load-extension did nothing'))
            for info in infos:
                if self.guard_check(info) or self.tab_check(info):
                    continue
                self.site_check(info)
            for info in pages:
                self.attach(info.get('targetId'))

        self.send('Target.getTargets', {}, on_result=got_targets)

        if OPEN_SELFTEST and SELFTEST_URL:
            # the browser already opens the start page on the command line, so
            # this is off by default; kept for diagnostics only
            log('self-test: opening %s' % SELFTEST_URL)
            self.send('Target.createTarget', {'url': SELFTEST_URL})

        while True:
            try:
                raw = self.ws.recv()
            except Exception:
                break
            try:
                msg = json.loads(raw)
            except Exception:
                continue

            mid = msg.get('id')
            if mid is not None:
                handler = self.pending.pop(mid, None)
                if handler:
                    try:
                        handler(msg)
                    except Exception as exc:
                        log('result handler failed: %s' % exc)
                elif msg.get('error'):
                    log('cdp error: %s' % str(msg['error'])[:160])
                continue

            method = msg.get('method')
            params = msg.get('params') or {}

            if method == 'Target.attachedToTarget':
                session = params.get('sessionId')
                info = params.get('targetInfo') or {}
                waiting = bool(params.get('waitingForDebugger'))
                self.attached.add(info.get('targetId'))
                blocked = (self.guard_check(info) or self.tab_check(info)
                           or self.site_check(info))
                if blocked:
                    # v4.5: resume even while shutting down. A target left
                    # paused by waitForDebuggerOnStart renders an empty
                    # window with no error and stays that way after the
                    # injector exits.
                    if waiting and session:
                        self.send('Runtime.runIfWaitingForDebugger', {}, session)
                    continue
                if session:
                    try:
                        self.inject(session, info, waiting)
                    finally:
                        if waiting:
                            self.send('Runtime.runIfWaitingForDebugger', {}, session)
                elif waiting:
                    # v4.5: no session id, so nothing can be injected - but the
                    # target still has to be released or that tab stays blank
                    self.send('Runtime.runIfWaitingForDebugger', {})

            elif method == 'Page.loadEventFired' and VERBOSE:
                sid = msg.get('sessionId')
                if sid:
                    self.schedule_probe(sid, delay=2.5)

            elif method == 'Page.frameNavigated':
                frame = params.get('frame') or {}
                if not frame.get('parentId'):
                    url = frame.get('url') or ''
                    if VERBOSE:
                        log('navigated to %s' % url[:78])
                    moved = {'type': 'page', 'url': url}
                    if not self.guard_check(moved):
                        self.site_check(moved)

            elif method == 'Target.targetCreated':
                info = params.get('targetInfo') or {}
                if self.guard_check(info) or self.tab_check(info):
                    continue
                if self.site_check(info):
                    continue
                if info.get('type') in PAGE_TYPES:
                    self.attach(info.get('targetId'))

            elif method == 'Target.targetInfoChanged':
                info = params.get('targetInfo') or {}
                if not self.guard_check(info):
                    self.site_check(info)

            elif method == 'Target.detachedFromTarget':
                self.attached.discard(params.get('targetId'))

            elif method == 'Target.targetDestroyed':
                # v4.5: closing a tab frees its slot, so the single-tab lock
                # means "one tab at a time", not "one tab ever"
                gone = params.get('targetId')
                self.attached.discard(gone)
                self.pages.discard(gone)

        return self.injected


def main():
    payloads = load_payloads()
    lock_active = bool(SITE_LOCK) or LOCK_SINGLE_TAB
    if not payloads and not lock_active:
        log('payload is empty, nothing to inject')
        return 0
    if not payloads:
        log('payload is empty; staying up to enforce the site lock')
    if SITE_LOCK:
        log('site lock: %s' % ', '.join(SITE_LOCK))
    if LOCK_SINGLE_TAB:
        log('single-tab lock: on')

    port = wait_for_port()
    if not port:
        log('DevToolsActivePort never appeared - is --remote-debugging-port set?')
        return 2
    # v4.8: never inject into a browser that is not ours. Everything this
    # injector does - the DevTools guard, the site lock, Browser.close -
    # would otherwise land on somebody else's window.
    if not port_owner_is_ours(port):
        log('REFUSED: port %d is owned by another browser, not %s. '
            'Nothing was injected and nothing was closed.'
            % (port, PROFILE_DIR))
        return 3
    log('devtools port %d, %d script(s), %d bytes total' % (
        port, len(payloads), sum(len(p[1]) for p in payloads)))
    for name, src in payloads:
        log('  part %-28s %8d bytes' % (name, len(src)))

    total = 0
    while True:
        # v4.10: the first check above only covered the first connection.
        # A profile can exit and Windows can hand the same ephemeral port
        # to another Chrome before this loop notices, so ownership is
        # re-proved before every single attach.
        if not port_owner_is_ours(port):
            log('REFUSED on reconnect: port %d is no longer this profile. '
                'Nothing further was injected and nothing was closed.' % port)
            break
        ws_url = browser_socket(port)
        if not ws_url:
            break
        try:
            ws = WebSocket(ws_url)
        except Exception as exc:
            log('websocket failed: %s' % exc)
            break
        log('connected')
        try:
            total += Session(ws, payloads).run()
        except Exception as exc:
            log('session ended: %s' % exc)
        ws.close()
        if not port_alive(port):
            break
        log('reconnecting')
        time.sleep(0.5)

    log('finished, %d injection(s)' % total)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as exc:
        log('fatal: %s' % exc)
        sys.exit(9)
'''

    INJECTION_MODES = ('extension', 'cdp', 'both')

    def injection_mode(self):
        """'extension' | 'cdp' | 'both'  (default 'both')."""
        mode = self._load_userscript_registry()['settings'].get('injection_mode', 'both')
        return mode if mode in self.INJECTION_MODES else 'both'

    def set_injection_mode(self, mode):
        reg = self._load_userscript_registry()
        reg['settings']['injection_mode'] = mode if mode in self.INJECTION_MODES else 'both'
        self._save_userscript_registry(reg)

    def cdp_include_fingerprint(self):
        return bool(self._load_userscript_registry()['settings']
                    .get('cdp_include_fingerprint', True))

    def set_cdp_include_fingerprint(self, value):
        reg = self._load_userscript_registry()
        reg['settings']['cdp_include_fingerprint'] = bool(value)
        self._save_userscript_registry(reg)

    def guard_devtools(self):
        """v4.4: close the generated browser when DevTools / extensions open.

        v4.10: ON by default again, as originally designed. It was turned
        off in v4.9 only because the injector could not prove which
        browser it was attached to, so the guard could land in the user's
        own Chrome and kill F12 and "Save image as" there. That hole is
        closed: the injector now verifies the browser target UUID before
        it sends anything, so this guard can only ever reach a profile
        this tool created. It still has a switch on the User Scripts tab
        for anyone who wants it off.
        """
        try:
            return bool(self._load_userscript_registry()['settings']
                        .get('guard_devtools', True))
        except Exception:
            return True

    def set_guard_devtools(self, value):
        reg = self._load_userscript_registry()
        reg['settings']['guard_devtools'] = bool(value)
        self._save_userscript_registry(reg)

    # ------------------------------------------------------------------
    # v4.5: site lock - the only sites a generated profile may open
    # ------------------------------------------------------------------
    # v4.9: was ('facebook.com', 'mavlink.click'). With a non-empty
    # default, site_check() called guard_trip() - which closes the whole
    # browser - the moment a profile opened any custom URL outside those
    # two domains. An empty default means no restriction, so custom URLs
    # work. Re-enable per install with set_site_lock(['example.com']).
    SITE_LOCK_DEFAULT = ()

    @staticmethod
    def _clean_lock_host(value):
        """'https://www.Facebook.com/x' -> 'facebook.com'."""
        host = str(value or '').strip().lower()
        host = re.sub(r'^[a-z0-9+.-]+://', '', host)
        for sep in ('/', '?', '#'):
            host = host.split(sep)[0]
        host = host.split(':')[0].strip('.')
        if host.startswith('www.'):
            host = host[4:]
        return host

    def site_lock(self):
        """Domains a generated profile may visit. [] means no restriction."""
        try:
            stored = self._load_userscript_registry()['settings'].get('site_lock')
        except Exception:
            stored = None
        if stored is None:
            return list(self.SITE_LOCK_DEFAULT)
        cleaned = []
        for item in stored:
            host = self._clean_lock_host(item)
            if host and host not in cleaned:
                cleaned.append(host)
        return cleaned

    def set_site_lock(self, domains):
        """Replace the allowed-domain list. Pass [] to switch the lock off."""
        cleaned = []
        for item in domains or []:
            host = self._clean_lock_host(item)
            if host and host not in cleaned:
                cleaned.append(host)
        reg = self._load_userscript_registry()
        reg['settings']['site_lock'] = cleaned
        self._save_userscript_registry(reg)

    # ------------------------------------------------------------------
    # v4.11: per-profile site lock.
    #
    # site_lock() above is one fixed list shared by every profile, which
    # is why a profile generated with a custom start URL used to trip a
    # lock meant for a different site. These methods derive the allowed
    # domain from each profile's OWN start URL instead, so a profile
    # generated for facebook.com is locked to facebook.com, one generated
    # for example.com is locked to example.com, and changing the URL in
    # the same tab to anything else closes that profile's browser.
    #
    # Enforcement is NOT new code: Session.site_check() in the injector
    # already trips guard_trip() on any top-level page outside the lock,
    # and host_allowed() already accepts subdomains. All that changes is
    # which list gets baked in.
    # ------------------------------------------------------------------
    def auto_site_lock(self):
        """Lock every generated profile to the site it was generated for."""
        try:
            return bool(self._load_userscript_registry()['settings']
                        .get('auto_site_lock', True))
        except Exception:
            return True

    def set_auto_site_lock(self, value):
        reg = self._load_userscript_registry()
        reg['settings']['auto_site_lock'] = bool(value)
        self._save_userscript_registry(reg)

    def profile_site_lock(self, profile_name):
        """Domains THIS profile may visit. [] means no restriction.

        With auto_site_lock off, this is exactly site_lock() - the old
        behaviour, unchanged. With it on, the profile's own start domain
        is added to whatever site_lock() holds, so an explicit list still
        works and is treated as extra domains rather than a replacement.
        That matters for sites that bounce through a second domain: put
        it in site_lock() and both stay allowed.
        """
        explicit = self.site_lock()
        if not self.auto_site_lock():
            return explicit
        hosts = list(explicit)
        try:
            own = self._clean_lock_host(self.start_url_for(profile_name))
        except Exception:
            own = ''
        if own and own not in hosts:
            hosts.append(own)
        return hosts

    def single_tab_lock(self):
        """Close the generated browser as soon as a second tab is opened."""
        try:
            return bool(self._load_userscript_registry()['settings']
                        .get('single_tab_lock', True))
        except Exception:
            return True

    def set_ui_setting(self, key, value):
        """v6.3.3: store one UI preference (language, theme, flags) in the
        registry the tool already uses. Additive - no existing setter is
        replaced, and unknown keys are simply carried alongside."""
        reg = self._load_userscript_registry()
        reg['settings'][str(key)] = value
        self._save_userscript_registry(reg)

    def set_single_tab_lock(self, value):
        reg = self._load_userscript_registry()
        reg['settings']['single_tab_lock'] = bool(value)
        self._save_userscript_registry(reg)

    # ------------------------------------------------------------------
    # v4.6: lean memory - stop generated profiles starving the machine
    # ------------------------------------------------------------------
    RENDERER_LIMIT_DEFAULT = 2

    def lean_memory(self):
        """Cap what each generated profile costs in RAM. On by default."""
        try:
            return bool(self._load_userscript_registry()['settings']
                        .get('lean_memory', True))
        except Exception:
            return True

    def set_lean_memory(self, value):
        reg = self._load_userscript_registry()
        reg['settings']['lean_memory'] = bool(value)
        self._save_userscript_registry(reg)

    def renderer_process_limit(self):
        """Renderer processes allowed per generated profile."""
        try:
            value = int(self._load_userscript_registry()['settings']
                        .get('renderer_process_limit',
                             self.RENDERER_LIMIT_DEFAULT))
        except Exception:
            value = self.RENDERER_LIMIT_DEFAULT
        return max(1, min(value, 16))

    def set_renderer_process_limit(self, count):
        try:
            value = max(1, min(int(count), 16))
        except Exception:
            value = self.RENDERER_LIMIT_DEFAULT
        reg = self._load_userscript_registry()
        reg['settings']['renderer_process_limit'] = value
        self._save_userscript_registry(reg)

    def lean_memory_flags(self):
        """Chrome flags that shrink a generated profile's footprint.

        None of these touch the fingerprint surface: they only change how
        many processes Chrome spawns and how big its JS heap may grow.
        """
        if not self.lean_memory():
            return []
        return [
            # the big one: without it Chrome spawns a renderer per site
            '--renderer-process-limit=%d' % self.renderer_process_limit(),
            # all tabs of one site share a renderer
            '--process-per-site',
            # cap the V8 heap so one runaway page cannot eat the machine
            '--js-flags=--max-old-space-size=512',
            # no fallback software GL: it is slow and memory hungry
            '--disable-software-rasterizer',
            # a generated profile does not need an on-disk cache that big
            '--disk-cache-size=52428800',
        ]

    # ==================================================================
    # v5.3  BACKGROUND EXECUTION RELIABILITY   (additive - nothing above
    # this block is touched).
    #
    # v5.2 made every page timer go through the Worker. On a busy page
    # that is thousands of postMessage round trips a second, which made
    # the browser feel slow and bought nothing: a 0 ms timer is not what
    # an automation script depends on across a minimise. v5.3 only adopts
    # delays >= KEEPALIVE_ADOPT_MIN_MS.
    #
    # v5.3 also adds the one clock Chrome cannot touch: a heartbeat
    # driven from Python over CDP. Runtime.evaluate is not a timer, not a
    # frame and not a task the page scheduled, so hiding, minimising,
    # occluding and freezing all have no effect on it.
    # ==================================================================
    KEEPALIVE_SWITCHES = [
        '--disable-background-timer-throttling',
        '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding',
    ]
    KEEPALIVE_AUTOPLAY_SWITCH = '--autoplay-policy=no-user-gesture-required'

    # Reference-proven audio levels: (2000/32767)*0.02 = -58 dBFS.
    # Inaudible at 40 Hz but well above the noise floor, so Chrome still
    # counts the tab as playing audio. Do NOT lower these.
    KEEPALIVE_AUDIO_HZ = 40
    KEEPALIVE_AUDIO_AMPLITUDE = 2000
    KEEPALIVE_AUDIO_VOLUME = 0.02
    KEEPALIVE_SKEW_MS = 25
    KEEPALIVE_RAF_MS = 32
    # Delays shorter than this stay on the native timer. 400 ms keeps the
    # high-volume scheduler traffic off the Worker while still covering
    # every wait an automation script realistically uses.
    KEEPALIVE_ADOPT_MIN_MS = 400
    KEEPALIVE_HEARTBEAT_SECONDS = 5

    KEEPALIVE_JS = r'''
/* Background execution reliability - additive, isolated, best effort.
   Never throws into the page.

   v5.2 - four layers, because timers alone were not enough:
     1. native refs captured FIRST, so nothing below can recurse
     2. visibility spoof: the page never learns it is hidden
     3. worker clock adopted into window.setTimeout / setInterval, so
        scripts already written against the plain globals benefit
     4. rAF shim + audio keep-alive                                   */
(function () {
  'use strict';

  var CFG = __KA_CONFIG__;
  var NS = '__KA_NS__';

  try { if (window[NS]) { return; } } catch (e) { return; }

  /* ==================================================================
     0. Native references. Captured before anything is patched, and used
        for every internal timer. Without this, adopting the globals
        makes the module's own backstop call itself forever.
     ================================================================== */
  var NATIVE = {};
  try {
    NATIVE.setTimeout = window.setTimeout.bind(window);
    NATIVE.clearTimeout = window.clearTimeout.bind(window);
    NATIVE.setInterval = window.setInterval.bind(window);
    NATIVE.clearInterval = window.clearInterval.bind(window);
    NATIVE.raf = window.requestAnimationFrame
      ? window.requestAnimationFrame.bind(window) : null;
    NATIVE.caf = window.cancelAnimationFrame
      ? window.cancelAnimationFrame.bind(window) : null;
    NATIVE.hasFocus = document.hasFocus ? document.hasFocus.bind(document) : null;
  } catch (e) { return; }

  /* original visibility getters, so the module can still see the truth
     after the page-facing ones are replaced */
  var REAL_VIS = null, REAL_HIDDEN = null;
  function findGetter(obj, prop) {
    /* walk the prototype chain rather than assuming window.Document:
       if this returns null the module would fall back to the property it
       is about to spoof and could never see the real state again. */
    var o = obj;
    while (o) {
      var d = Object.getOwnPropertyDescriptor(o, prop);
      if (d && d.get) { return d.get; }
      o = Object.getPrototypeOf(o);
    }
    return null;
  }
  try {
    REAL_VIS = findGetter(document, 'visibilityState');
    REAL_HIDDEN = findGetter(document, 'hidden');
  } catch (e) {}

  var lastRealVis = 'visible';
  try { lastRealVis = REAL_VIS ? REAL_VIS.call(document) : document.visibilityState; }
  catch (e) {}

  function realVisibility() {
    if (REAL_VIS) {
      try { return REAL_VIS.call(document); } catch (e) {}
    }
    /* no real getter available: use the value tracked from the events we
       intercept, NOT the spoofed property */
    return lastRealVis;
  }
  function reallyHidden() {
    if (REAL_HIDDEN) {
      try { return !!REAL_HIDDEN.call(document); } catch (e) {}
    }
    return realVisibility() === 'hidden';
  }

  var S = {
    worker: null, workerOk: false, seq: 0, pending: Object.create(null),
    tasks: Object.create(null), taskSeq: 0,
    rafSeq: 0, rafMap: Object.create(null),
    audio: null, audioUrl: null, audioOn: false, gestureArmed: false,
    probes: 0, throttled: false, stopped: false, errors: 0,
    adopted: false, spoofed: false, frozenSeen: 0, beats: 0,
    lastReal: 'visible'
  };

  function now() { try { return Date.now(); } catch (e) { return 0; } }
  function swallow(fn) { try { return fn(); } catch (e) { S.errors++; return null; } }
  function pageTimeout(cb, ms) {
    return swallow(function () { return NATIVE.setTimeout(cb, ms); });
  }

  /* make a replacement function report itself as native, matching the
     approach the fingerprint patch already uses */
  function masquerade(replacement, original) {
    swallow(function () {
      var src = 'function ' + (original.name || '') + '() { [native code] }';
      Object.defineProperty(replacement, 'name',
        { value: original.name, configurable: true });
      Object.defineProperty(replacement, 'length',
        { value: original.length, configurable: true });
      Object.defineProperty(replacement, 'toString',
        { value: function () { return src; }, configurable: true, writable: true });
    });
  }

  /* ==================================================================
     1. Worker clock  (reference: apBGTimer)
     ================================================================== */
  var WORKER_SRC =
    'var t={};onmessage=function(e){var d=e.data||{};' +
    'if(d.cmd==="set"){t[d.id]=setTimeout(function(){' +
    'delete t[d.id];postMessage({id:d.id});},d.ms);}' +
    'else if(d.cmd==="rep"){t[d.id]=setInterval(function(){' +
    'postMessage({id:d.id,rep:1});},d.ms);}' +
    'else if(d.cmd==="clear"){var h=t[d.id];if(h!==undefined){' +
    'clearTimeout(h);clearInterval(h);delete t[d.id];}}' +
    'else if(d.cmd==="ping"){postMessage({pong:1});}};';

  function startWorker() {
    if (S.worker || !CFG.worker || S.stopped) { return; }
    swallow(function () {
      if (typeof Worker !== 'function' || typeof Blob !== 'function') { return; }
      if (!window.URL || !URL.createObjectURL) { return; }
      var url = URL.createObjectURL(
        new Blob([WORKER_SRC], { type: 'application/javascript' }));
      var w = new Worker(url);
      swallow(function () { URL.revokeObjectURL(url); });
      w.onmessage = function (ev) {
        var d = (ev && ev.data) || {};
        if (d.pong) { S.workerOk = true; return; }
        if (d.rep) { tick(d.id, 'worker'); return; }
        var cb = S.pending[d.id];
        if (cb) { delete S.pending[d.id]; swallow(cb); }
        else { tick(d.id, 'worker'); }
      };
      w.onerror = function () { S.workerOk = false; };
      w.onmessageerror = function () { S.workerOk = false; };
      S.worker = w;
      w.postMessage({ cmd: 'ping' });
    });
  }

  var BG = {
    get available() { return !!S.worker; },
    setTimeout: function (cb, ms) {
      startWorker();
      if (!S.worker) { return { page: pageTimeout(cb, ms) }; }
      var id = ++S.seq;
      S.pending[id] = cb;
      var sent = swallow(function () {
        S.worker.postMessage({ cmd: 'set', id: id, ms: ms });
        return true;
      });
      if (sent !== true) {
        delete S.pending[id];
        return { page: pageTimeout(cb, ms) };
      }
      return { id: id };
    },
    setInterval: function (id, ms) {
      if (!S.worker) { return false; }
      return swallow(function () {
        S.worker.postMessage({ cmd: 'rep', id: id, ms: ms });
        return true;
      }) === true;
    },
    clear: function (h) {
      if (!h) { return; }
      if (h.page !== undefined && h.page !== null) {
        swallow(function () { NATIVE.clearTimeout(h.page); });
      }
      if (h.id !== undefined) { BG.clearId(h.id); }
    },
    clearId: function (id) {
      delete S.pending[id];
      if (S.worker) {
        swallow(function () { S.worker.postMessage({ cmd: 'clear', id: id }); });
      }
    }
  };

  /* ==================================================================
     2. sleep()  (reference: apSleep)
     ================================================================== */
  function sleep(ms) {
    ms = Math.max(0, (+ms) || 0);
    return new Promise(function (resolve) {
      var done = false, handle = null, backstop = null;
      var finish = function () {
        if (done) { return; }
        done = true;
        BG.clear(handle);
        if (backstop !== null && backstop !== undefined) {
          swallow(function () { NATIVE.clearTimeout(backstop); });
        }
        resolve();
      };
      handle = BG.setTimeout(finish, ms);
      backstop = pageTimeout(finish, ms + CFG.skewMs);
    });
  }

  /* ==================================================================
     3. Callback timers
     ================================================================== */
  function tick(id, source) {
    var t = S.tasks[id];
    if (!t || t.done) { return; }
    var stamp = now();
    if (t.repeat) {
      var floor = Math.min(t.ms / 2, 250);
      if (t.last && (stamp - t.last) < floor) { return; }
      t.last = stamp;
      t.source = source;
    } else {
      t.done = true;
      clearTask(id, true);
    }
    swallow(function () { t.fn.apply(window, t.args); });
  }

  function clearTask(id, drop) {
    var t = S.tasks[id];
    if (!t) { return; }
    if (t.handle) { BG.clear(t.handle); t.handle = null; }
    if (t.workerRep) { BG.clearId(id); t.workerRep = false; }
    if (t.pageId !== null && t.pageId !== undefined) {
      swallow(function () {
        if (t.repeat) { NATIVE.clearInterval(t.pageId); }
        else { NATIVE.clearTimeout(t.pageId); }
      });
      t.pageId = null;
    }
    if (t.watchId !== null && t.watchId !== undefined) {
      swallow(function () { NATIVE.clearInterval(t.watchId); });
      t.watchId = null;
    }
    if (drop) { delete S.tasks[id]; }
  }

  /* ids are offset so they can never collide with a native timer id the
     page may still be holding */
  var ID_BASE = 800000000;

  function schedule(fn, ms, repeat, args) {
    if (typeof fn !== 'function') { return 0; }
    ms = Math.max(0, (+ms) || 0);
    var id = ++S.taskSeq;
    var t = {
      fn: fn, ms: ms, args: args || [], repeat: !!repeat, done: false,
      last: 0, handle: null, pageId: null, watchId: null,
      workerRep: false, source: 'page'
    };
    S.tasks[id] = t;
    startWorker();

    if (!repeat) {
      t.handle = BG.setTimeout(function () { tick(id, 'worker'); }, ms);
      t.pageId = pageTimeout(function () { tick(id, 'page'); }, ms + CFG.skewMs);
      return ID_BASE + id;
    }

    t.workerRep = BG.setInterval(id, ms);
    if (!t.workerRep) {
      t.pageId = swallow(function () {
        return NATIVE.setInterval(function () { tick(id, 'page'); }, ms);
      });
      return ID_BASE + id;
    }
    var period = Math.max(ms * 2, 2000);
    t.watchId = swallow(function () {
      return NATIVE.setInterval(function () {
        var task = S.tasks[id];
        if (!task || task.pageId) { return; }
        if (task.last && (now() - task.last) <= (task.ms * 2.5 + 1000)) { return; }
        S.workerOk = false;
        BG.clearId(id);
        task.workerRep = false;
        task.pageId = swallow(function () {
          return NATIVE.setInterval(function () { tick(id, 'page'); }, task.ms);
        });
      }, period);
    });
    return ID_BASE + id;
  }

  function cancel(handle) {
    var id = (typeof handle === 'number' && handle >= ID_BASE)
      ? handle - ID_BASE : handle;
    var t = S.tasks[id];
    if (!t) { return false; }
    t.done = true;
    clearTask(id, true);
    return true;
  }

  /* ==================================================================
     4. Visibility spoof. The single biggest reason a script stops when
        the window is minimised is not the timer - it is the script, or
        the page it drives, reacting to hidden/blur. The page is told it
        is visible and focused; the module keeps reading the truth
        through the captured getters.
     ================================================================== */
  function installSpoof() {
    if (!CFG.spoofVisibility || S.spoofed) { return; }
    S.spoofed = true;

    swallow(function () {
      Object.defineProperty(document, 'hidden',
        { get: function () { return false; }, configurable: true });
    });
    swallow(function () {
      Object.defineProperty(document, 'visibilityState',
        { get: function () { return 'visible'; }, configurable: true });
    });
    swallow(function () {
      Object.defineProperty(document, 'webkitHidden',
        { get: function () { return false; }, configurable: true });
    });
    swallow(function () {
      Object.defineProperty(document, 'webkitVisibilityState',
        { get: function () { return 'visible'; }, configurable: true });
    });
    if (NATIVE.hasFocus) {
      swallow(function () {
        var rep = function () { return true; };
        masquerade(rep, document.hasFocus);
        document.hasFocus = rep;
      });
    }

    /* swallow the events before any page listener sees them. Capture on
       window runs before the document target phase, so this wins. */
    var eat = function (e) {
      if (!REAL_VIS) { lastRealVis = (lastRealVis === 'hidden') ? 'visible' : 'hidden'; }
      S.lastReal = realVisibility();
      swallow(function () { e.stopImmediatePropagation(); });
      if (typeof e.stopPropagation === 'function') { swallow(function () { e.stopPropagation(); }); }
    };
    ['visibilitychange', 'webkitvisibilitychange'].forEach(function (evt) {
      swallow(function () { window.addEventListener(evt, eat, true); });
      swallow(function () { document.addEventListener(evt, eat, true); });
    });
    if (CFG.spoofFocus) {
      swallow(function () {
        window.addEventListener('blur', function (e) {
          swallow(function () { e.stopImmediatePropagation(); });
        }, true);
      });
    }
  }

  /* ==================================================================
     5. rAF shim. requestAnimationFrame does not fire at all when the
        window is not being composited, so anything driven by it stops
        dead. While really hidden, callbacks are serviced from the
        worker clock instead.
     ================================================================== */
  var RAF_BASE = 900000000;

  function installRaf() {
    if (!CFG.shimRaf || !NATIVE.raf) { return; }
    swallow(function () {
      var rep = function (cb) {
        if (typeof cb !== 'function') { return NATIVE.raf(cb); }
        if (!reallyHidden()) { return NATIVE.raf(cb); }
        var id = ++S.rafSeq;
        S.rafMap[id] = cb;
        BG.setTimeout(function () {
          var fn = S.rafMap[id];
          delete S.rafMap[id];
          if (!fn) { return; }
          var ts = 0;
          swallow(function () { ts = (window.performance && performance.now()) || now(); });
          swallow(function () { fn(ts); });
        }, CFG.rafMs);
        return RAF_BASE + id;
      };
      masquerade(rep, window.requestAnimationFrame);
      window.requestAnimationFrame = rep;

      if (NATIVE.caf) {
        var crep = function (id) {
          if (typeof id === 'number' && id >= RAF_BASE) {
            delete S.rafMap[id - RAF_BASE];
            return;
          }
          return NATIVE.caf(id);
        };
        masquerade(crep, window.cancelAnimationFrame);
        window.cancelAnimationFrame = crep;
      }
    });
  }

  /* ==================================================================
     6. Adopt the global timers. This is what makes scripts that were
        written against plain setTimeout / setInterval benefit without
        being edited. Internals use NATIVE, so there is no recursion.
     ================================================================== */
  function adopt() {
    if (S.adopted) { return; }
    S.adopted = true;
    swallow(function () {
      /* Only delays >= adoptMinMs are routed through the worker. A page
         like Facebook schedules thousands of 0-50 ms timers a second for
         its own scheduler; sending every one of those through a
         postMessage round trip made the whole page measurably slower and
         bought nothing, because a short timer is not what an automation
         script depends on across a minimise. Short timers stay native. */
      var MIN = CFG.adoptMinMs;
      var rST = function (fn, ms) {
        /* fast path first and WITHOUT touching `arguments`: materialising
           the arguments object and going through .apply costs far more
           than the call it replaces, and this runs thousands of times a
           second on a busy page. */
        if (typeof fn !== 'function' || ((+ms) || 0) < MIN) {
          if (arguments.length <= 2) { return NATIVE.setTimeout(fn, ms); }
          return NATIVE.setTimeout.apply(null, arguments);
        }
        return schedule(fn, ms, false,
          arguments.length > 2 ? Array.prototype.slice.call(arguments, 2) : null);
      };
      var rSI = function (fn, ms) {
        if (typeof fn !== 'function' || ((+ms) || 0) < MIN) {
          if (arguments.length <= 2) { return NATIVE.setInterval(fn, ms); }
          return NATIVE.setInterval.apply(null, arguments);
        }
        return schedule(fn, ms, true,
          arguments.length > 2 ? Array.prototype.slice.call(arguments, 2) : null);
      };
      var rCT = function (id) {
        if (cancel(id)) { return; }
        return NATIVE.clearTimeout(id);
      };
      var rCI = function (id) {
        if (cancel(id)) { return; }
        return NATIVE.clearInterval(id);
      };
      masquerade(rST, window.setTimeout);
      masquerade(rSI, window.setInterval);
      masquerade(rCT, window.clearTimeout);
      masquerade(rCI, window.clearInterval);
      window.setTimeout = rST;
      window.setInterval = rSI;
      window.clearTimeout = rCT;
      window.clearInterval = rCI;
    });
  }

  /* ==================================================================
     7. Audio keep-alive. Proven levels: 40 Hz, amplitude 2000/32767,
        volume 0.02. A tab genuinely producing audio is exempt from
        intensive throttling and is not frozen or discarded. Digital
        silence does not count.
     ================================================================== */
  function buildWavUrl() {
    return swallow(function () {
      var rate = 8000, n = rate;
      var buf = new ArrayBuffer(44 + n * 2);
      var dv = new DataView(buf);
      var wr = function (o, s) {
        for (var i = 0; i < s.length; i++) { dv.setUint8(o + i, s.charCodeAt(i)); }
      };
      wr(0, 'RIFF'); dv.setUint32(4, 36 + n * 2, true); wr(8, 'WAVE');
      wr(12, 'fmt '); dv.setUint32(16, 16, true); dv.setUint16(20, 1, true);
      dv.setUint16(22, 1, true); dv.setUint32(24, rate, true);
      dv.setUint32(28, rate * 2, true); dv.setUint16(32, 2, true);
      dv.setUint16(34, 16, true); wr(36, 'data'); dv.setUint32(40, n * 2, true);
      var amp = CFG.amplitude;
      /* exact 2*pi*hz/rate so a 1 s buffer holds a whole number of cycles
         and the loop point has no step */
      var omega = 2 * Math.PI * CFG.hz / rate;
      for (var i = 0; i < n; i++) {
        dv.setInt16(44 + i * 2, Math.round(Math.sin(i * omega) * amp), true);
      }
      return URL.createObjectURL(new Blob([buf], { type: 'audio/wav' }));
    });
  }

  function attach(audio) {
    if (!CFG.attachToDom) { return; }
    var host = document.body || document.documentElement;
    if (host) { swallow(function () { host.appendChild(audio); }); return; }
    swallow(function () {
      document.addEventListener('DOMContentLoaded', function () {
        var h = document.body || document.documentElement;
        if (h && S.audio) { swallow(function () { h.appendChild(S.audio); }); }
      }, { once: true });
    });
  }

  function armGesture() {
    if (S.gestureArmed || S.stopped) { return; }
    S.gestureArmed = true;
    var opts = { capture: true, passive: true, once: true };
    var retry = function () { S.gestureArmed = false; startAudio(); };
    ['pointerdown', 'keydown', 'touchstart'].forEach(function (evt) {
      swallow(function () { window.addEventListener(evt, retry, opts); });
    });
  }

  function startAudio() {
    if (!CFG.audio || S.stopped) { return; }
    if (S.audio && S.audioOn) { return; }
    swallow(function () {
      if (S.audio) {
        var rp = S.audio.play();
        if (rp && rp.then) {
          rp.then(function () { S.audioOn = true; },
                  function () { S.audioOn = false; armGesture(); });
        }
        return;
      }
      if (!S.audioUrl) { S.audioUrl = buildWavUrl(); }
      if (!S.audioUrl) { return; }
      var audio = document.createElement('audio');
      audio.loop = true;
      audio.volume = CFG.volume;
      audio.preload = 'auto';
      audio.setAttribute('playsinline', '');
      if (CFG.marker) { audio.setAttribute(CFG.marker, '1'); }
      audio.src = S.audioUrl;
      S.audio = audio;
      attach(audio);
      var p = audio.play();
      if (p && p.then) {
        p.then(function () { S.audioOn = true; },
               function () { S.audioOn = false; armGesture(); });
      } else {
        S.audioOn = true;
      }
    });
  }

  function stopAudio() {
    if (!S.audio) { return; }
    var a = S.audio;
    swallow(function () { a.pause(); });
    swallow(function () { if (a.parentNode) { a.parentNode.removeChild(a); } });
    swallow(function () { a.removeAttribute('src'); a.load(); });
    if (S.audioUrl) { swallow(function () { URL.revokeObjectURL(S.audioUrl); }); }
    S.audio = null; S.audioUrl = null; S.audioOn = false;
  }

  /* ==================================================================
     8. Drift measurement + teardown
     ================================================================== */
  function measure(samples, cb) {
    var n = Math.max(1, samples | 0), worst = 0, i = 0;
    var step = function () {
      var t0 = now();
      pageTimeout(function () {
        var drift = now() - t0 - 1000;
        if (drift > worst) { worst = drift; }
        i++;
        if (i >= n) { cb(worst); } else { step(); }
      }, 1000);
    };
    step();
  }

  function stop() {
    S.stopped = true;
    Object.keys(S.tasks).forEach(function (id) { clearTask(id, true); });
    S.tasks = Object.create(null);
    S.pending = Object.create(null);
    S.rafMap = Object.create(null);
    if (S.worker) { swallow(function () { S.worker.terminate(); }); S.worker = null; }
    stopAudio();
  }

  var API = {
    sleep: sleep,
    setTimeout: function (fn, ms) {
      return schedule(fn, ms, false, Array.prototype.slice.call(arguments, 2));
    },
    setInterval: function (fn, ms) {
      return schedule(fn, ms, true, Array.prototype.slice.call(arguments, 2));
    },
    clearTimeout: cancel,
    clearInterval: cancel,
    startKeepAlive: function () { startAudio(); },
    stopKeepAlive: function () { stopAudio(); },
    keepAudio: function (on) { if (on) { startAudio(); } else { stopAudio(); } },
    adopt: adopt,
    bgTimer: BG,
    /* Called from outside the page by _inject/keepalive_heartbeat.py via
       Runtime.evaluate. A CDP evaluation is not a timer, not a frame and
       not a task the page scheduled, so nothing Chrome does to hidden
       pages can throttle it. This is the only clock here that cannot be
       slowed down. Attach work with:  api.onHeartbeat = function(n){...} */
    onHeartbeat: null,
    heartbeat: function () {
      S.beats++;
      if (CFG.audioMode !== 'off' && !S.audioOn) { startAudio(); }
      var h = API.onHeartbeat;
      if (typeof h === 'function') { swallow(function () { h(S.beats); }); }
      return S.beats;
    },
    realVisibility: realVisibility,
    status: function () {
      return {
        worker: !!S.worker, workerOk: S.workerOk,
        adopted: S.adopted, spoofed: S.spoofed,
        rafShimmed: CFG.shimRaf && !!NATIVE.raf,
        tasks: Object.keys(S.tasks).length,
        pending: Object.keys(S.pending).length,
        audio: S.audioOn, audioMode: CFG.audioMode,
        realVisibility: realVisibility(),
        pageSeesVisibility: document.visibilityState,
        freezeEvents: S.frozenSeen, beats: S.beats,
        throttled: S.throttled, errors: S.errors, stopped: S.stopped
      };
    },
    /* one call that tells you which layer is failing */
    diagnose: function (cb) {
      var out = API.status();
      out.nativeTimersPatched =
        String(window.setTimeout).indexOf('[native code]') >= 0 && S.adopted;
      measure(3, function (worstDrift) {
        out.worstDriftMs = worstDrift;
        out.timersThrottled = worstDrift > 700;
        out.verdict = out.timersThrottled
          ? (S.audioOn ? 'still throttled WITH audio - check chrome://version flags'
                       : 'throttled and audio off - flags missing; try audioMode always')
          : 'timers healthy';
        if (typeof cb === 'function') { cb(out); }
        else { swallow(function () { console.log('[keepalive]', out); }); }
      });
      return 'measuring for 3s...';
    },
    stop: stop,
    installLegacyGlobals: function () {
      swallow(function () {
        window.apBGTimer = {
          available: BG.available,
          setTimeout: function (cb, ms) { BG.setTimeout(cb, ms); }
        };
        window.apSleep = sleep;
        window.apStartKeepAlive = startAudio;
        window.apStopKeepAlive = stopAudio;
      });
    }
  };

  swallow(function () {
    Object.defineProperty(window, NS, {
      value: API, enumerable: false, configurable: true, writable: false
    });
  });

  /* real-visibility tracking + freeze reporting, on the captured truth */
  swallow(function () {
    document.addEventListener('freeze', function () { S.frozenSeen++; }, true);
    document.addEventListener('resume', function () { S.frozenSeen++; }, true);
    window.addEventListener('pagehide', stop, true);
  });

  /* order matters: spoof first so nothing downstream sees a hidden page,
     then rAF, then adopt the globals */
  installSpoof();
  installRaf();
  if (CFG.worker) { startWorker(); }
  if (CFG.adoptTimers) { adopt(); }
  if (CFG.audioMode === 'always') { startAudio(); }
  else if (CFG.audioMode === 'auto' && reallyHidden()) { startAudio(); }
})();
'''

    KEEPALIVE_HEARTBEAT_PY = r'''
# Keep-alive heartbeat - runs beside cdp_inject.py, never inside it.
# A Runtime.evaluate driven from here is not a timer, not a frame and not
# a task the page scheduled, so no amount of hiding, minimising, occluding
# or freezing can slow it down. This is the only clock in the feature that
# Chrome cannot throttle.
import os
import sys
import json
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
LOG = os.path.join(HERE, 'heartbeat.log')
INTERVAL = __INTERVAL__
NS = r"""__NS__"""


def log(msg):
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write('%s  %s\n' % (time.strftime('%H:%M:%S'), msg))
    except Exception:
        pass


try:
    import cdp_inject as CI          # reuse the proven WebSocket + port logic
except Exception as exc:
    log('cannot import cdp_inject (%s) - heartbeat disabled' % exc)
    raise SystemExit(0)

EXPR = ('(function(){try{var a=window["' + NS + '"];'
        'if(a&&a.heartbeat){return a.heartbeat();}return -1;}catch(e){return -2;}})()')


def main():
    port = CI.wait_for_port()
    if not port:
        log('no devtools port; nothing to do')
        return 0
    if not CI.port_owner_is_ours(port):
        log('REFUSED: port %d is not this profile' % port)
        return 3

    beats = 0
    while True:
        ws_url = CI.browser_socket(port)
        if not ws_url:
            break
        try:
            ws = CI.WebSocket(ws_url)
        except Exception as exc:
            log('websocket failed: %s' % exc)
            break
        log('connected, every %ss' % INTERVAL)
        mid = [0]
        sessions = {}

        def send(method, params=None, session=None):
            mid[0] += 1
            msg = {'id': mid[0], 'method': method, 'params': params or {}}
            if session:
                msg['sessionId'] = session
            try:
                ws.send(json.dumps(msg))
            except Exception:
                return False
            return True

        try:
            ws.settimeout(INTERVAL)
        except Exception:
            pass

        send('Target.setDiscoverTargets', {'discover': True})
        send('Target.getTargets', {})
        last = 0.0
        while True:
            try:
                raw = ws.recv()
            except Exception:
                raw = None                      # timeout is normal, not an error
            if raw:
                try:
                    msg = json.loads(raw)
                except Exception:
                    msg = {}
                method = msg.get('method')
                result = msg.get('result') or {}
                if method == 'Target.attachedToTarget':
                    p = msg.get('params') or {}
                    info = p.get('targetInfo') or {}
                    if info.get('type') == 'page':
                        sessions[info.get('targetId')] = p.get('sessionId')
                elif method == 'Target.detachedFromTarget':
                    sid = (msg.get('params') or {}).get('sessionId')
                    for k, v in list(sessions.items()):
                        if v == sid:
                            sessions.pop(k, None)
                elif 'targetInfos' in result:
                    for info in result['targetInfos']:
                        if info.get('type') == 'page':
                            send('Target.attachToTarget',
                                 {'targetId': info['targetId'], 'flatten': True})
                elif 'sessionId' in result:
                    sessions[result['sessionId']] = result['sessionId']

            now = time.time()
            if now - last >= INTERVAL:
                last = now
                if not sessions:
                    send('Target.getTargets', {})
                for sid in list(sessions.values()):
                    if not send('Runtime.evaluate',
                                {'expression': EXPR, 'returnByValue': True,
                                 'awaitPromise': False}, sid):
                        sessions.clear()
                        break
                beats += 1
                if beats % 60 == 0:
                    log('%d beats, %d page session(s)' % (beats, len(sessions)))
            if not CI.port_alive(port):
                break
        try:
            ws.close()
        except Exception:
            pass
        if not CI.port_alive(port):
            break
        time.sleep(1.0)

    log('finished after %d beats' % beats)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as exc:
        log('fatal: %s' % exc)
        sys.exit(9)
'''

    def _ka_setting(self, key, default):
        try:
            return self._load_userscript_registry()['settings'].get(key, default)
        except Exception:
            return default

    def _set_ka_setting(self, key, value):
        registry = self._load_userscript_registry()
        registry['settings'][key] = value
        self._save_userscript_registry(registry)

    def background_keepalive(self):
        return bool(self._ka_setting('background_keepalive', True))

    def set_background_keepalive(self, value):
        self._set_ka_setting('background_keepalive', bool(value))

    def keepalive_adopt_timers(self):
        """Route long window.setTimeout / setInterval through the Worker."""
        return bool(self._ka_setting('keepalive_adopt_timers', True))

    def set_keepalive_adopt_timers(self, value):
        self._set_ka_setting('keepalive_adopt_timers', bool(value))

    def keepalive_adopt_min_ms(self):
        """Shortest delay that is worth sending through the Worker.

        Below this the native timer is used untouched. Lowering it toward
        0 restores the v5.2 behaviour and the slowdown that came with it.
        """
        try:
            return int(self._ka_setting('keepalive_adopt_min_ms',
                                        self.KEEPALIVE_ADOPT_MIN_MS))
        except Exception:
            return self.KEEPALIVE_ADOPT_MIN_MS

    def set_keepalive_adopt_min_ms(self, value):
        self._set_ka_setting('keepalive_adopt_min_ms', max(0, int(value)))

    def keepalive_spoof_visibility(self):
        """Tell the page it is visible and focused even when it is not.

        Note the cost: a page that never learns it is hidden also never
        idles, so it keeps polling, prefetching and animating in the
        background. Across several open profiles that is real CPU and
        bandwidth. Turn this off first if the browser feels slow.
        """
        return bool(self._ka_setting('keepalive_spoof_visibility', True))

    def set_keepalive_spoof_visibility(self, value):
        self._set_ka_setting('keepalive_spoof_visibility', bool(value))

    def keepalive_shim_raf(self):
        """Service requestAnimationFrame from the Worker while hidden."""
        return bool(self._ka_setting('keepalive_shim_raf', True))

    def set_keepalive_shim_raf(self, value):
        self._set_ka_setting('keepalive_shim_raf', bool(value))

    def keepalive_heartbeat(self):
        """Drive a heartbeat into the page from Python over CDP.

        This is the only mechanism here that Chrome cannot throttle. Needs
        DevTools injection, so it does nothing in 'extension' mode.
        """
        return bool(self._ka_setting('keepalive_heartbeat', True))

    def set_keepalive_heartbeat(self, value):
        self._set_ka_setting('keepalive_heartbeat', bool(value))

    def keepalive_heartbeat_seconds(self):
        try:
            return max(1, int(self._ka_setting('keepalive_heartbeat_seconds',
                                               self.KEEPALIVE_HEARTBEAT_SECONDS)))
        except Exception:
            return self.KEEPALIVE_HEARTBEAT_SECONDS

    def set_keepalive_heartbeat_seconds(self, value):
        self._set_ka_setting('keepalive_heartbeat_seconds', max(1, int(value)))

    def background_keepalive_audio(self):
        return self.keepalive_audio_mode() != 'off'

    def set_background_keepalive_audio(self, value):
        self.set_keepalive_audio_mode('always' if value else 'off')

    def keepalive_audio_mode(self):
        """'always' | 'auto' | 'off'.  Default 'always'."""
        mode = self._ka_setting('keepalive_audio_mode', 'always')
        return mode if mode in ('auto', 'always', 'off') else 'always'

    def set_keepalive_audio_mode(self, mode):
        if mode not in ('auto', 'always', 'off'):
            raise ValueError("mode must be 'auto', 'always' or 'off'")
        self._set_ka_setting('keepalive_audio_mode', mode)

    def background_keepalive_flags(self):
        """Chrome switches for background reliability, or [] when off.

        IntensiveWakeUpThrottling is deliberately NOT here - it is a
        feature name and lives in DISABLED_FEATURES, because a second
        --disable-features switch replaces the first instead of adding.
        """
        if not self.background_keepalive():
            return []
        flags = list(self.KEEPALIVE_SWITCHES)
        if self.keepalive_audio_mode() != 'off':
            flags.append(self.KEEPALIVE_AUTOPLAY_SWITCH)
        return flags

    def _keepalive_guard_key(self, profile_path):
        name = os.path.basename(profile_path.rstrip(os.sep))
        return '__ka_' + hashlib.sha1(('ka:' + name).encode('utf-8')).hexdigest()[:10]

    def _keepalive_namespace(self, profile_path):
        return self._keepalive_guard_key(profile_path) + '_api'

    def keepalive_config(self):
        mode = self.keepalive_audio_mode()
        return {
            'worker': True,
            'audio': mode != 'off',
            'audioMode': mode,
            'adoptTimers': bool(self.keepalive_adopt_timers()),
            'adoptMinMs': int(self.keepalive_adopt_min_ms()),
            'spoofVisibility': bool(self.keepalive_spoof_visibility()),
            'spoofFocus': bool(self.keepalive_spoof_visibility()),
            'shimRaf': bool(self.keepalive_shim_raf()),
            'rafMs': self.KEEPALIVE_RAF_MS,
            'skewMs': self.KEEPALIVE_SKEW_MS,
            'volume': self.KEEPALIVE_AUDIO_VOLUME,
            'amplitude': self.KEEPALIVE_AUDIO_AMPLITUDE,
            'hz': self.KEEPALIVE_AUDIO_HZ,
            'attachToDom': True,
            'marker': 'data-ka-keepalive',
            'maxProbes': 4,
            'driftMs': 1700,
            'stopAudioWhenVisible': False,
        }

    # ==================================================================
    # v6.0  licensing hooks
    # ==================================================================
    def license(self):
        """The shared LicenseClient, or None if the module is absent."""
        if _license is None:
            return None
        client = getattr(self, '_license_client', None)
        if client is None:
            try:
                client = _license.LicenseClient()
            except Exception:
                client = None
            self._license_client = client
        return client

    def license_usable(self):
        """True when the tool is allowed to run. Absent module = allowed,
        so a developer checkout without the licensing file still works.
        """
        client = self.license()
        if client is None:
            return True
        return client.is_usable()

    def license_is_pro(self):
        client = self.license()
        return client.is_pro() if client else True

    # ==================================================================
    # v6.3  FEATURE 1: unrestricted browsing + new tabs on the paid plans
    # ==================================================================
    def browsing_unlocked(self):
        """True when generated profiles may open new tabs and browse anywhere.

        Pro and Unlimited ('team') only. This reuses the plan the app has
        ALREADY resolved from the Ed25519-signed licence token via
        LicenseClient.current_plan() - there is no second licensing check
        here, and nothing is asked of the network.

        Fail-safe by design (spec 1.3): every uncertain case returns False,
        which leaves the original Free restrictions exactly as they are.
        That covers a missing licensing module, a client that would not
        construct, a corrupt or expired token, an unknown plan name and any
        exception at all. It can never unlock by accident.

        Note this deliberately differs from license_is_pro() above, which
        returns True when the licensing module is absent (developer
        checkout). For a *restriction* the safe default is the opposite
        one, so an absent module keeps the locks on - which is also
        precisely how the tool behaves today.
        """
        client = self.license()
        if client is None:
            return False
        try:
            return client.current_plan() in ('pro', 'team')
        except Exception:
            return False

    def server_scripts(self):
        """Scripts delivered by the site as [(name, source)].

        These are held only in memory by the client and never written
        to the profile, so a cracked binary has no scripts to run.
        Kept for callers that only want name/source pairs.
        """
        client = self.license()
        if client is None:
            return []
        try:
            return client.get_scripts_source()
        except Exception:
            return []

    def server_script_entries(self):
        """Server scripts as full userscript ENTRIES, ready to inject.

        v6.2 fix: the server scripts (Script 1 / Script 2) are real
        Tampermonkey-style userscripts that call GM_addStyle, GM_setValue and
        the rest. Injecting their raw source ran them OUTSIDE the userscript
        runtime, so those helpers were undefined and nothing worked. Here each
        source is parsed the same way a local script is, so the shared runtime
        wraps it and every GM_* function exists. The entry mirrors the shape
        list_userscripts() used to return, so _userscript_wrapper() and the
        MV3 extension builder accept it unchanged.
        """
        client = self.license()
        if client is None:
            return []
        try:
            records = client.get_scripts() if hasattr(client, 'get_scripts') else []
        except Exception:
            records = []
        if not records:
            # older client: fall back to name/source pairs
            try:
                records = [{'slug': n, 'name': n, 'source': s, 'version': ''}
                           for (n, s) in self.server_scripts()]
            except Exception:
                records = []

        entries = []
        for rec in records:
            source = rec.get('source') or ''
            if not source:
                continue
            slug = rec.get('slug') or 'script'
            try:
                meta = self.parse_userscript_metadata(source)
            except Exception:
                meta = {}
            entry = dict(meta) if isinstance(meta, dict) else {}
            entry['file'] = 'server_' + str(slug) + '.user.js'
            entry['source'] = source
            entry['enabled'] = True
            entry['server'] = True
            entry['id'] = hashlib.sha1(('srv:' + str(slug)).encode('utf-8')).hexdigest()[:16]
            entry.setdefault('run_at', 'document-idle')
            entry.setdefault('world', 'MAIN')
            entry.setdefault('grants', [])
            entry.setdefault('matches', [])
            entry.setdefault('includes', [])
            entry.setdefault('excludes', [])
            entry.setdefault('exclude_matches', [])
            entry.setdefault('requires', [])
            entry.setdefault('resources', [])
            entry.setdefault('connects', [])
            entry.setdefault('meta_str', '')
            entry.setdefault('namespace', '')
            entry.setdefault('version', str(rec.get('version', '')))
            entry.setdefault('description', '')
            entry.setdefault('author', '')
            entry.setdefault('noframes', False)
            # a script with no @match/@include should run everywhere, which is
            # what the tool's users expect from the two managed scripts
            if not entry['matches'] and not entry['includes']:
                entry['includes'] = ['*']
            display = (meta.get('name') if isinstance(meta, dict) else '') \
                or rec.get('name') or str(slug)
            entry['display_name'] = display
            entries.append(entry)
        return entries

    def _keepalive_js(self, profile_path):
        if not self.background_keepalive():
            return ''
        try:
            key = self._keepalive_guard_key(profile_path)
            source = (self.KEEPALIVE_JS
                      .replace('__KA_CONFIG__',
                               json.dumps(self.keepalive_config()))
                      .replace('__KA_NS__', self._keepalive_namespace(profile_path)))
            return self._guard_once(source, key)
        except Exception:
            return ''

    def _build_keepalive_heartbeat(self, profile_path):
        """Write <profile>/_inject/keepalive_heartbeat.py, or remove it.

        Returns the path, or None when the heartbeat is off or CDP
        injection is not in use.
        """
        inject_dir = os.path.join(profile_path, '_inject')
        target = os.path.join(inject_dir, 'keepalive_heartbeat.py')
        try:
            on = (self.background_keepalive() and self.keepalive_heartbeat()
                  and self.injection_mode() in ('cdp', 'both'))
            if not on:
                if os.path.isfile(target):
                    os.remove(target)
                return None
            if not os.path.isdir(inject_dir):
                return None
            source = (self.KEEPALIVE_HEARTBEAT_PY
                      .replace('__INTERVAL__',
                               str(self.keepalive_heartbeat_seconds()))
                      .replace('__NS__', self._keepalive_namespace(profile_path)))
            with open(target, 'w', encoding='utf-8') as f:
                f.write(source)
            return target
        except Exception:
            return None

    def keepalive_selftest(self, profile_name):
        """What is ACTUALLY on disk for this profile, versus the settings.

        Reads the generated files rather than trusting the configuration,
        so a stale launcher shows up as stale.
        """
        path = profile_name
        if not os.path.isabs(path):
            path = os.path.join(self.profiles_dir, profile_name)
        report = {'profile': os.path.basename(path.rstrip(os.sep)),
                  'exists': os.path.isdir(path), 'problems': []}
        if not report['exists']:
            report['problems'].append('profile folder not found')
            return report

        report['settings'] = {
            'keepalive': self.background_keepalive(),
            'audio_mode': self.keepalive_audio_mode(),
            'adopt_timers': self.keepalive_adopt_timers(),
            'adopt_min_ms': self.keepalive_adopt_min_ms(),
            'spoof_visibility': self.keepalive_spoof_visibility(),
            'shim_raf': self.keepalive_shim_raf(),
            'heartbeat': self.keepalive_heartbeat(),
            'injection_mode': self.injection_mode(),
        }

        launcher = os.path.join(path, 'launch.pyw')
        if not os.path.isfile(launcher):
            launcher = os.path.join(path, 'launch.py')
        report['launcher'] = launcher if os.path.isfile(launcher) else None
        if report['launcher']:
            try:
                with open(launcher, encoding='utf-8') as f:
                    text = f.read()
            except Exception:
                text = ''
            missing = [s for s in self.KEEPALIVE_SWITCHES if s not in text]
            report['launcher_flags_missing'] = missing
            if missing and self.background_keepalive():
                report['problems'].append(
                    'launcher is STALE - run apply_keepalive_to_all_profiles()')
        else:
            report['problems'].append('no launcher on disk')

        inject_dir = os.path.join(path, '_inject')
        payload = os.path.join(inject_dir, 'payload.js')
        report['payload_has_keepalive'] = False
        if os.path.isfile(payload):
            try:
                with open(payload, encoding='utf-8') as f:
                    report['payload_has_keepalive'] = '__ka_' in f.read()
            except Exception:
                pass
        if self.background_keepalive() and not report['payload_has_keepalive']:
            report['problems'].append(
                'injected payload has no keep-alive module')

        hb = os.path.join(inject_dir, 'keepalive_heartbeat.py')
        report['heartbeat_script'] = os.path.isfile(hb)
        if self.keepalive_heartbeat() and not report['heartbeat_script'] \
                and self.injection_mode() in ('cdp', 'both'):
            report['problems'].append(
                'heartbeat script missing - run apply_keepalive_to_all_profiles()')

        report['namespace'] = self._keepalive_namespace(path)
        report['console_snippet'] = (
            'window["%s"].diagnose()' % report['namespace'])
        report['ok'] = not report['problems']
        return report

    def apply_keepalive_to_all_profiles(self, progress=None):
        """Push the current keep-alive settings into EXISTING profiles.

        A profile's launch.pyw is written once, when the profile is
        created, and the desktop shortcut runs that same file. A profile
        made before this feature existed therefore keeps its old command
        line - no flags, no injected module - until its launcher is
        rewritten. Close any open profile first. Returns (updated, total).
        """
        profiles = self.get_all_profiles()
        done = 0
        total = len(profiles)
        for index, profile in enumerate(profiles):
            name, path = profile['name'], profile['path']
            try:
                self._build_userscript_extension(path)
                self._build_cdp_injector(path)
                self._build_keepalive_heartbeat(path)
                if self._profile_launcher(self.profile_key(path), path):
                    done += 1
                try:
                    self.create_desktop_shortcut(name, path)
                except Exception:
                    pass
            except Exception:
                pass
            if progress:
                try:
                    progress(index + 1, total, name)
                except Exception:
                    pass
        return done, total

    def _fp_guard_key(self, profile_path):
        name = os.path.basename(profile_path.rstrip(os.sep))
        return '__fp_' + hashlib.sha1(('fp:' + name).encode('utf-8')).hexdigest()[:10]

    @staticmethod
    def _guard_once(source, key):
        """Run `source` at most once per document, whichever path delivers it."""
        return (
            "(function(){var k=%s;try{if(window[k]){return;}"
            "Object.defineProperty(window,k,{value:1,enumerable:false,configurable:true});}"
            "catch(e){}\n%s\n})();\n" % (json.dumps(key), source)
        )

    def _build_cdp_parts(self, profile_path, entries=None):
        """Injectable units, in order: fingerprint, runtime, then one per script.

        Kept separate so a syntax error in one user script cannot stop the
        fingerprint patch or the other scripts from running.
        """
        if entries is None:
            entries = self.list_userscripts()
        if not self.userscripts_enabled():
            entries = []
        entries = [e for e in entries if e.get('enabled')]
        # v6.2: server-delivered scripts (Script 1 / Script 2) are wrapped in
        # the SAME runtime as local scripts, so their GM_* helpers exist. They
        # are added to the list the runtime serves rather than pasted raw.
        entries = list(entries) + self.server_script_entries()

        parts = []
        profile_name = os.path.basename(profile_path.rstrip(os.sep))
        guard = self._guard_js()
        if guard:
            parts.append(('00_guard.js', guard))
        keepalive = self._keepalive_js(profile_path)
        if keepalive:
            parts.append(('00_keepalive.js', keepalive))
        if self.cdp_include_fingerprint() and self.profile_fingerprint(profile_name):
            fp_js = os.path.join(profile_path, '_fingerprint_extension', 'inject.js')
            if os.path.isfile(fp_js):
                try:
                    with open(fp_js, 'r', encoding='utf-8') as f:
                        parts.append(('01_fingerprint.js', f.read()))
                except Exception:
                    pass

        if entries:
            seed = hashlib.sha1(('us:' + profile_name).encode('utf-8')).hexdigest()
            host_key = '__us_' + seed[:12]
            resources = self._userscript_resource_map(entries)
            parts.append(('01_runtime.js', self.USERSCRIPT_RUNTIME_JS
                          .replace('__USKEY__', host_key)
                          .replace('__USTOKEN__', 'us_' + seed[12:28])
                          .replace('__USPROFILE__', profile_name)
                          .replace('__USBRIDGED__', 'false')
                          .replace('__USRESOURCES__',
                                   json.dumps(resources, ensure_ascii=False))))
            for index, entry in enumerate(entries):
                name = '%02d_%s.js' % (
                    index + 2,
                    self._slugify_userscript_name(entry['display_name'])[:28] or 'script')
                parts.append((name, self._userscript_wrapper(entry, host_key)))

        return parts

    def _build_cdp_payload(self, profile_path, entries=None):
        """One self-contained JS blob: fingerprint patch + runtime + scripts."""
        if entries is None:
            entries = self.list_userscripts()
        if not self.userscripts_enabled():
            entries = []
        entries = [e for e in entries if e.get('enabled')]
        # v6.2: same as _build_cdp_parts - server scripts ride the runtime
        entries = list(entries) + self.server_script_entries()

        parts = []
        guard = self._guard_js()
        if guard:
            parts.append(guard)
        keepalive = self._keepalive_js(profile_path)
        if keepalive:
            parts.append(keepalive)
        if self.cdp_include_fingerprint():
            fp_js = os.path.join(profile_path, '_fingerprint_extension', 'inject.js')
            if os.path.isfile(fp_js):
                try:
                    with open(fp_js, 'r', encoding='utf-8') as f:
                        parts.append(f.read())
                except Exception:
                    pass

        if entries:
            profile_name = os.path.basename(profile_path.rstrip(os.sep))
            seed = hashlib.sha1(('us:' + profile_name).encode('utf-8')).hexdigest()
            host_key = '__us_' + seed[:12]
            resources = self._userscript_resource_map(entries)
            parts.append(self.USERSCRIPT_RUNTIME_JS
                         .replace('__USKEY__', host_key)
                         .replace('__USTOKEN__', 'us_' + seed[12:28])
                         .replace('__USPROFILE__', profile_name)
                         .replace('__USBRIDGED__', 'false')
                         .replace('__USRESOURCES__',
                                  json.dumps(resources, ensure_ascii=False)))
            for entry in entries:
                parts.append(self._userscript_wrapper(entry, host_key))

        return '\n'.join(parts)

    def _build_cdp_injector(self, profile_path, entries=None):
        """Write the payload + injector into <profile>/_inject.

        Returns the injector path, or None when CDP injection is off or
        there is nothing to inject.
        """
        inject_dir = os.path.join(profile_path, '_inject')
        try:
            # v4.11: the lock is resolved per profile now, so a profile
            # generated with a custom URL locks to that URL's domain.
            lock_hosts = self.profile_site_lock(
                os.path.basename(profile_path.rstrip(os.sep)))
            single_tab = self.single_tab_lock()
            # ----------------------------------------------------------
            # v6.3 FEATURE 1. Nothing above or below is removed: the two
            # lock resolvers still run exactly as they did, and the FREE
            # branch here is the original v4.5/v4.11 behaviour, untouched.
            # On a paid plan the two values are simply replaced with the
            # ones the injector already treats as "no restriction at all":
            # an empty SITE_LOCK (host_allowed() then returns True for
            # every host) and LOCK_SINGLE_TAB False (tab_check() returns
            # early). No enforcement code is edited - only what gets baked
            # into it. GUARD_DEVTOOLS is deliberately NOT touched, so the
            # DevTools / extensions guard stays on for every plan.
            # ----------------------------------------------------------
            if not self.browsing_unlocked():
                pass          # FREE, or plan unknown: original restrictions
            else:
                lock_hosts = []      # PRO / UNLIMITED: browse to any URL
                single_tab = False   # PRO / UNLIMITED: new tabs allowed
            # v4.5: the locks live in the injector, so 'extension' mode can
            # only skip it while no lock is active.
            #
            # v6.3: this existence test deliberately still uses the
            # CONFIGURED locks, not the plan-gated ones above. Unlocking a
            # paid plan must not make the injector disappear in 'extension'
            # mode, because the injector also carries the keepalive
            # heartbeat and the CDP payload. So a paid profile keeps exactly
            # the same injector it has today - only SITE_LOCK and
            # LOCK_SINGLE_TAB inside it change.
            lock_on = (bool(self.profile_site_lock(
                           os.path.basename(profile_path.rstrip(os.sep))))
                       or self.single_tab_lock())
            if self.injection_mode() == 'extension' and not lock_on:
                if os.path.isdir(inject_dir):
                    shutil.rmtree(inject_dir, ignore_errors=True)
                return None

            payload = self._build_cdp_payload(profile_path, entries)
            if not payload.strip() and not lock_on:
                if os.path.isdir(inject_dir):
                    shutil.rmtree(inject_dir, ignore_errors=True)
                return None

            os.makedirs(inject_dir, exist_ok=True)
            payload_file = os.path.join(inject_dir, 'payload.js')
            with open(payload_file, 'w', encoding='utf-8') as f:
                f.write(payload)

            # one file per injectable unit, plus the index the injector reads
            for stale in os.listdir(inject_dir):
                if re.match(r'^\d\d_.*\.js$', stale):
                    try:
                        os.remove(os.path.join(inject_dir, stale))
                    except Exception:
                        pass
            names = []
            for name, source in self._build_cdp_parts(profile_path, entries):
                with open(os.path.join(inject_dir, name), 'w', encoding='utf-8') as f:
                    f.write(source)
                names.append(name)
            index_file = os.path.join(inject_dir, 'payload_index.json')
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(names, f, indent=1)

            profile_name = os.path.basename(profile_path.rstrip(os.sep))
            seed = hashlib.sha1(('us:' + profile_name).encode('utf-8')).hexdigest()
            injector = os.path.join(inject_dir, 'cdp_inject.py')
            self._build_keepalive_heartbeat(profile_path)
            src = (self.USERSCRIPT_CDP_PY
                   .replace('__PROFILE_DIR__', profile_path)
                   .replace('__INDEX_FILE__', index_file)
                   .replace('__PAYLOAD_FILE__', payload_file)
                   .replace('__USHOSTKEY__', '__us_' + seed[:12])
                   .replace('__USSELFTEST__',
                            self.start_url_for(os.path.basename(
                                profile_path.rstrip(os.sep))))
                   .replace('__USGUARD__',
                            'True' if self.guard_devtools() else 'False')
                   .replace('__USSITELOCK__', repr(tuple(lock_hosts)))
                   # v6.3: the plan-resolved value from above, not the raw
                   # setting, so a paid plan really does get no tab lock
                   .replace('__USSINGLETAB__',
                            'True' if single_tab else 'False')
                   # always on: this is what made injection reliable
                   .replace('__USVERBOSE__', 'True'))
            with open(injector, 'w', encoding='utf-8') as f:
                f.write(src)
            try:
                os.chmod(injector, 0o755)
            except Exception:
                pass
            return injector
        except Exception as e:
            print(f"[inject] Failed to build CDP injector: {e}")
            return None

    # ==================================================================
    # v4.4: Firefox support - a WebExtension plus an RDP installer, so the
    # fingerprint patch and user scripts run in Firefox too. Firefox does
    # not speak Chrome's DevTools protocol, so none of the CDP path applies.
    # ==================================================================
    FIREFOX_EXT_DIRNAME = '_firefox_extension'

    def _firefox_extension_id(self, profile_name):
        seed = hashlib.sha1(('ffid:' + profile_name).encode('utf-8')).hexdigest()[:12]
        return 'mvl-%s@mavelylink' % seed

    def _firefox_debug_port(self, profile_name):
        """A stable loopback port in the private range for this profile."""
        h = int(hashlib.sha1(('ffport:' + profile_name).encode('utf-8')
                             ).hexdigest()[:6], 16)
        return 49200 + (h % 700)

    def _prepare_firefox_profile(self, profile_path, port):
        """Write the prefs Firefox needs to accept the temporary add-on.

        The remote-debugging server is off by default and normally shows a
        connection prompt; both are turned off here, bound to loopback only.
        """
        prefs = {
            'devtools.debugger.remote-enabled': 'true',
            'devtools.debugger.prompt-connection': 'false',
            'devtools.debugger.force-local': 'true',
            'devtools.chrome.enabled': 'true',
            'devtools.debugger.remote-port': str(int(port)),
            'browser.shell.checkDefaultBrowser': 'false',
            'browser.startup.homepage_override.mstone': '"ignore"',
            'startup.homepage_welcome_url': '""',
            'startup.homepage_welcome_url.additional': '""',
            'datareporting.policy.dataSubmissionEnabled': 'false',
            'datareporting.policy.firstRunURL': '""',
            'toolkit.telemetry.reportingpolicy.firstRun': 'false',
            'trailhead.firstrun.didSeeAboutWelcome': 'true',
            'browser.aboutwelcome.enabled': 'false',
            'xpinstall.signatures.required': 'false',
            'extensions.autoDisableScopes': '0',
            'browser.tabs.warnOnClose': 'false',
        }
        lines = ['// Written by %s - do not edit' % self.TOOL_NAME]
        for key, value in prefs.items():
            lines.append('user_pref("%s", %s);' % (key, value))
        body = '\n'.join(lines) + '\n'
        # only user.js: Firefox rewrites prefs.js itself and treats a
        # hand-edited one as damaged, which is why it closed immediately
        for name in ('user.js',):
            try:
                target = os.path.join(profile_path, name)
                existing = ''
                if name == 'prefs.js' and os.path.isfile(target):
                    with open(target, 'r', encoding='utf-8', errors='ignore') as f:
                        existing = f.read()
                    if '// Written by %s' % self.TOOL_NAME in existing:
                        continue
                    body_to_write = existing.rstrip('\n') + '\n' + body
                else:
                    body_to_write = body
                with open(target, 'w', encoding='utf-8') as f:
                    f.write(body_to_write)
            except Exception:
                pass
        return True

    def _build_firefox_extension(self, profile_path, entries=None):
        """Build the unpacked Firefox WebExtension for this profile.

        The page-world payload is exactly the CDP payload (guard +
        fingerprint + user-script runtime + scripts); a content script
        injects it into the page at document-start.
        """
        profile_name = os.path.basename(profile_path.rstrip(os.sep))
        ext_dir = os.path.join(profile_path, self.FIREFOX_EXT_DIRNAME)
        os.makedirs(ext_dir, exist_ok=True)

        payload = self._build_cdp_payload(profile_path, entries) or ''
        guard_on = self.guard_devtools()

        ext_id = self._firefox_extension_id(profile_name)
        manifest = {
            'manifest_version': 2,
            'name': 'MavelyLink Profile Runtime',
            'version': '1.0',
            'description': 'Injects the profile fingerprint and user scripts.',
            'browser_specific_settings': {'gecko': {'id': ext_id}},
            'permissions': ['<all_urls>', 'tabs', 'webNavigation'],
            'content_scripts': [{
                'matches': ['<all_urls>'],
                'match_about_blank': True,
                'all_frames': True,
                'run_at': 'document_start',
                'js': ['bootstrap.js'],
            }],
            'background': {'scripts': ['background.js'], 'persistent': True},
        }
        with open(os.path.join(ext_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)

        # payload.js holds the page-world code as a plain file we read back
        with open(os.path.join(ext_dir, 'payload.js'), 'w', encoding='utf-8') as f:
            f.write(payload)

        # bootstrap runs in the isolated content-script world. It injects the
        # payload into the page world, and (when the guard is on) blocks the
        # DevTools shortcuts and tells the background to close the browser.
        bootstrap = (
            "(function(){\n"
            "  var CODE = %s;\n"
            "  var GUARD = %s;\n"
            "  try {\n"
            "    var s = document.createElement('script');\n"
            "    s.textContent = CODE;\n"
            "    (document.head || document.documentElement).appendChild(s);\n"
            "    s.remove();\n"
            "  } catch (e) {}\n"
            "  if (GUARD) {\n"
            "    function trip(){ try { browser.runtime.sendMessage({type:'mvl-guard-close'}); } catch(e){}\n"
            "      try { chrome.runtime.sendMessage({type:'mvl-guard-close'}); } catch(e){} }\n"
            "    window.addEventListener('keydown', function(ev){\n"
            "      try { var k=(ev.key||'').toLowerCase();\n"
            "        if (ev.keyCode===123 || (ev.ctrlKey&&ev.shiftKey&&(k==='i'||k==='j'||k==='c')) ||\n"
            "            (ev.metaKey&&ev.altKey&&(k==='i'||k==='j'||k==='c')) || (ev.ctrlKey&&k==='u')) {\n"
            "          ev.preventDefault(); ev.stopPropagation(); trip(); } } catch(e){}\n"
            "    }, true);\n"
            "    setInterval(function(){ try {\n"
            "      if ((window.outerWidth-window.innerWidth)>300 || (window.outerHeight-window.innerHeight)>320) trip();\n"
            "    } catch(e){} }, 1000);\n"
            "  }\n"
            "})();\n"
            % (json.dumps(payload), 'true' if guard_on else 'false'))
        with open(os.path.join(ext_dir, 'bootstrap.js'), 'w', encoding='utf-8') as f:
            f.write(bootstrap)

        # background closes every window when the guard trips, and also when a
        # tab tries to open the add-ons / debugging pages
        background = (
            "var GUARD = %s;\n"
            "function shutAll(){ try { browser.windows.getAll().then(function(ws){\n"
            "  ws.forEach(function(w){ try { browser.windows.remove(w.id); } catch(e){} }); }); } catch(e){}\n"
            "  try { chrome.windows.getAll(function(ws){ ws.forEach(function(w){ try{ chrome.windows.remove(w.id);}catch(e){} }); }); } catch(e){} }\n"
            "try { browser.runtime.onMessage.addListener(function(m){ if(m&&m.type==='mvl-guard-close'&&GUARD) shutAll(); }); } catch(e){}\n"
            "try { chrome.runtime.onMessage.addListener(function(m){ if(m&&m.type==='mvl-guard-close'&&GUARD) shutAll(); }); } catch(e){}\n"
            "var BAD = ['about:addons','about:debugging','about:devtools'];\n"
            "function watch(details){ try { if(!GUARD) return; var u=(details.url||'').toLowerCase();\n"
            "  for (var i=0;i<BAD.length;i++){ if(u.indexOf(BAD[i])===0){ shutAll(); return; } } } catch(e){} }\n"
            "try { browser.webNavigation.onBeforeNavigate.addListener(watch); } catch(e){}\n"
            "try { browser.webNavigation.onCommitted.addListener(watch); } catch(e){}\n"
            % ('true' if guard_on else 'false'))
        with open(os.path.join(ext_dir, 'background.js'), 'w', encoding='utf-8') as f:
            f.write(background)

        return ext_dir

    FIREFOX_RDP_PY = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Installs a temporary Firefox add-on over the Remote Debugging Protocol.

Firefox does not speak Chrome's DevTools protocol, so this is the Firefox
equivalent of the CDP injector: it connects to the debugger server that the
launcher started with -start-debugger-server and asks the addons actor to
install the unpacked extension. Pure standard library.
"""
import json
import os
import socket
import sys
import time

PROFILE_DIR = r"""__PROFILE_DIR__"""
EXT_PATH = r"""__FF_EXT_PATH__"""
PORT = __FF_PORT__
LOG_FILE = os.path.join(PROFILE_DIR, '_inject', 'firefox_inject.log')


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write('%s  %s\n' % (time.strftime('%H:%M:%S'), msg))
    except Exception:
        pass


class RDP(object):
    """Minimal Firefox Remote Debugging Protocol client (length:json frames)."""

    def __init__(self, sock):
        self.sock = sock
        self.buf = b''

    def _fill(self):
        chunk = self.sock.recv(65536)
        if not chunk:
            raise IOError('connection closed')
        self.buf += chunk

    def read_packet(self, timeout=20):
        self.sock.settimeout(timeout)
        while True:
            colon = self.buf.find(b':')
            if colon != -1:
                try:
                    length = int(self.buf[:colon])
                except ValueError:
                    # not a JSON packet (bulk data); drop the delimiter
                    self.buf = self.buf[colon + 1:]
                    continue
                start = colon + 1
                if len(self.buf) >= start + length:
                    body = self.buf[start:start + length]
                    self.buf = self.buf[start + length:]
                    try:
                        return json.loads(body.decode('utf-8'))
                    except Exception as exc:
                        log('bad packet: %s' % exc)
                        continue
            self._fill()

    def send(self, obj):
        data = json.dumps(obj).encode('utf-8')
        frame = str(len(data)).encode('ascii') + b':' + data
        self.sock.sendall(frame)

    def request(self, obj, timeout=20):
        self.send(obj)
        return self.read_packet(timeout)


def connect(timeout=45):
    deadline = time.time() + timeout
    last = ''
    while time.time() < deadline:
        try:
            s = socket.create_connection(('127.0.0.1', PORT), timeout=3)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            return s
        except Exception as exc:
            last = str(exc)
            time.sleep(0.4)
    log('could not reach the debugger server on port %d (%s)' % (PORT, last))
    return None


def main():
    if not EXT_PATH or not os.path.isdir(EXT_PATH):
        log('no extension directory to install: %s' % EXT_PATH)
        return 2
    sock = connect()
    if not sock:
        return 3
    rdp = RDP(sock)
    try:
        greeting = rdp.read_packet()
        log('connected; applicationType=%s' % greeting.get('applicationType'))
        root = rdp.request({'to': 'root', 'type': 'getRoot'})
        addons_actor = root.get('addonsActor')
        if not addons_actor:
            # older Firefox exposes it only after getRoot; try again
            root = rdp.request({'to': 'root', 'type': 'getRoot'})
            addons_actor = root.get('addonsActor')
        if not addons_actor:
            log('this Firefox has no addons actor; cannot install. Root keys: %s'
                % ', '.join(sorted(root.keys())))
            return 4
        reply = rdp.request({'to': addons_actor,
                             'type': 'installTemporaryAddon',
                             'addonPath': os.path.abspath(EXT_PATH)}, timeout=30)
        if reply.get('error'):
            log('install refused: %s %s' % (reply.get('error'),
                                            reply.get('message', '')))
            return 5
        addon = reply.get('addon') or {}
        log('installed temporary add-on: %s' % (addon.get('id') or addon))
        return 0
    except Exception as exc:
        log('install failed: %s' % exc)
        return 6
    finally:
        try:
            sock.close()
        except Exception:
            pass


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        log('fatal: %s' % exc)
        sys.exit(9)
'''

    def _build_firefox_injector(self, profile_path, ext_path, port):
        """Write the RDP add-on installer into <profile>/_inject."""
        inject_dir = os.path.join(profile_path, '_inject')
        os.makedirs(inject_dir, exist_ok=True)
        injector = os.path.join(inject_dir, 'firefox_inject.py')
        src = (self.FIREFOX_RDP_PY
               .replace('__PROFILE_DIR__', profile_path)
               .replace('__FF_EXT_PATH__', ext_path)
               .replace('__FF_PORT__', str(int(port))))
        with open(injector, 'w', encoding='utf-8') as f:
            f.write(src)
        try:
            os.chmod(injector, 0o755)
        except Exception:
            pass
        return injector

    def _extensions_usable(self):
        """False when the browser ignores --load-extension anyway."""
        if self.injection_mode() == 'cdp':
            return False
        try:
            return bool(self.detect_browser_info().get('load_extension', True))
        except Exception:
            return True

    def _runtime_and_prefix(self):
        """(interpreter, argv_prefix) for running a helper script.

        Frozen: the app EXE plus --run-script. Source: the python
        interpreter with no prefix. Callers that build a command line
        for the injector / launcher / heartbeat use this so a compiled
        build keeps injecting instead of launching a second GUI.
        """
        if getattr(sys, 'frozen', False):
            return sys.executable, ['--run-script']
        return self._python_runtime(), []

    def _python_runtime(self):
        """Interpreter used to run the per-profile injector / launcher."""
        exe = sys.executable or ''
        if not exe or not os.path.exists(exe):
            return None
        if platform.system() == 'Windows':
            quiet = os.path.join(os.path.dirname(exe), 'pythonw.exe')
            if os.path.exists(quiet):
                return quiet
        return exe

    def _shortcut_target(self, name, profile_path, fingerprint, ext_dir, chrome_exe):
        """(target, arguments, working_dir) for this profile's shortcut.

        With DevTools injection enabled the shortcut has to start the
        launcher rather than chrome.exe, because something must stay
        attached to the browser to inject into new tabs.
        """
        if self.injection_mode() in ('cdp', 'both'):
            if getattr(sys, 'frozen', False):
                return (sys.executable, '--launch-profile "%s"' % name,
                        os.path.dirname(sys.executable))
            launcher = self._build_launcher_script(name, profile_path,
                                                   fingerprint, ext_dir)
            runtime = self._python_runtime()
            if launcher and runtime:
                return (runtime, '"%s"' % launcher, profile_path)
        return (chrome_exe,
                self._chrome_args_for_profile(profile_path, fingerprint, ext_dir),
                os.path.dirname(chrome_exe))

    # ------------------------------------------------------------------
    # v3.4: pick the browser yourself
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # v3.5: bundle a real extension (Tampermonkey, uBlock, ...) into profiles
    # ------------------------------------------------------------------
    def extensions_dir(self):
        path = os.path.join(self.profiles_dir, '_extensions')
        os.makedirs(path, exist_ok=True)
        return path

    def _find_manifest_dir(self, root):
        """Web Store downloads nest the manifest under a version folder."""
        best = None
        for current, dirs, files in os.walk(root):
            if 'manifest.json' in files:
                depth = current[len(root):].count(os.sep)
                if best is None or depth < best[0]:
                    best = (depth, current)
            if best and best[0] == 0:
                break
        return best[1] if best else None

    def import_extension(self, source, name=None):
        """Copy an unpacked extension (folder or .zip) into _extensions.

        Returns (folder_name, warnings). Fixes the things that make Chrome
        refuse a Web Store folder loaded unpacked.
        """
        import tempfile
        import zipfile

        warnings = []
        temp = None
        try:
            if os.path.isfile(source) and source.lower().endswith('.zip'):
                temp = tempfile.mkdtemp(prefix='ext_')
                with zipfile.ZipFile(source) as zf:
                    zf.extractall(temp)
                root = temp
            elif os.path.isdir(source):
                root = source
            else:
                raise ValueError('Pick a folder or a .zip file')

            manifest_dir = self._find_manifest_dir(root)
            if not manifest_dir:
                raise ValueError('No manifest.json anywhere in that folder')

            with open(os.path.join(manifest_dir, 'manifest.json'),
                      'r', encoding='utf-8-sig') as f:
                manifest = json.load(f)

            label = name or manifest.get('short_name') or manifest.get('name') or 'extension'
            if label.startswith('__MSG_'):
                label = os.path.basename(source).rsplit('.', 1)[0]
            folder = self._slugify_userscript_name(label)[:40] or 'extension'
            dest = os.path.join(self.extensions_dir(), folder)
            if os.path.isdir(dest):
                shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(manifest_dir, dest)

            if os.path.normpath(manifest_dir) != os.path.normpath(root):
                warnings.append(
                    'manifest was nested in %s - used that folder'
                    % os.path.basename(manifest_dir))

            # Chrome refuses unpacked extensions containing _metadata
            meta = os.path.join(dest, '_metadata')
            if os.path.isdir(meta):
                shutil.rmtree(meta, ignore_errors=True)
                warnings.append('removed _metadata (Chrome rejects it when unpacked)')

            changed = False
            perms = manifest.get('permissions')
            if isinstance(perms, list) and manifest.get('manifest_version', 2) >= 3:
                blocked = [p for p in perms if p in ('webRequestBlocking',)]
                if blocked:
                    manifest['permissions'] = [p for p in perms if p not in blocked]
                    warnings.append('removed %s (not allowed for unpacked MV3)'
                                    % ', '.join(blocked))
                    changed = True
            if manifest.pop('update_url', None):
                warnings.append('removed update_url so Chrome will not swap it out')
                changed = True
            if manifest.pop('differential_fingerprint', None):
                changed = True
            if changed:
                with open(os.path.join(dest, 'manifest.json'), 'w', encoding='utf-8') as f:
                    json.dump(manifest, f, indent=2)

            return folder, warnings
        finally:
            if temp:
                shutil.rmtree(temp, ignore_errors=True)

    def remove_extension(self, folder):
        path = os.path.join(self.extensions_dir(), os.path.basename(folder))
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            return True
        return False

    def describe_extensions(self):
        out = []
        for path in sorted(self.list_extra_extensions()):
            info = {'folder': os.path.basename(path), 'path': path,
                    'name': os.path.basename(path), 'version': ''}
            try:
                with open(os.path.join(path, 'manifest.json'),
                          'r', encoding='utf-8-sig') as f:
                    manifest = json.load(f)
                label = manifest.get('name') or ''
                if label.startswith('__MSG_'):
                    label = os.path.basename(path)
                info['name'] = label
                info['version'] = manifest.get('version', '')
            except Exception:
                pass
            out.append(info)
        return out

    # ------------------------------------------------------------------
    # v3.7: two flags Chrome was rejecting on every launch
    # ------------------------------------------------------------------
    #  chrome_debug.log showed:
    #    Invalid forced color profile: "hdr10-hlg"
    #    Ignoring unrecognized or unparsable cipher suite: TLS_RSA_WITH_...
    #  --force-color-profile only accepts a fixed set of names, and
    #  --cipher-suite-blacklist only accepts hex ids. Both were no-ops.
    # ------------------------------------------------------------------
    VALID_COLOR_PROFILES = ('srgb', 'display-p3-d65', 'scrgb-linear',
                            'hdr10', 'extended-srgb', 'generic-rgb')

    CIPHER_IDS = {
        'TLS_AES_128_GCM_SHA256': '0x1301',
        'TLS_AES_256_GCM_SHA384': '0x1302',
        'TLS_CHACHA20_POLY1305_SHA256': '0x1303',
        'TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256': '0xc02b',
        'TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256': '0xc02f',
        'TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384': '0xc02c',
        'TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384': '0xc030',
        'TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256': '0xcca9',
        'TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256': '0xcca8',
        'TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA': '0xc013',
        'TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA': '0xc014',
        'TLS_ECDHE_ECDSA_WITH_AES_128_CBC_SHA': '0xc009',
        'TLS_ECDHE_ECDSA_WITH_AES_256_CBC_SHA': '0xc00a',
        'TLS_RSA_WITH_AES_128_GCM_SHA256': '0x009c',
        'TLS_RSA_WITH_AES_256_GCM_SHA384': '0x009d',
        'TLS_RSA_WITH_AES_128_CBC_SHA': '0x002f',
        'TLS_RSA_WITH_AES_256_CBC_SHA': '0x0035',
        'TLS_RSA_WITH_3DES_EDE_CBC_SHA': '0x000a',
    }

    # never disable these or TLS 1.3 handshakes break
    CIPHER_ESSENTIAL = {'0x1301', '0x1302', '0x1303', '0xc02b', '0xc02f'}

    def color_profile_flag(self, color_scheme):
        value = 'srgb' if color_scheme == 'light' else 'display-p3-d65'
        return value if value in self.VALID_COLOR_PROFILES else 'srgb'

    def cipher_blacklist_flag(self, tls_ciphers):
        """Hex ids for the tail of this profile's cipher order, or ''."""
        ids = []
        for name in tls_ciphers:
            hex_id = self.CIPHER_IDS.get(str(name).strip().upper())
            if hex_id and hex_id not in self.CIPHER_ESSENTIAL and hex_id not in ids:
                ids.append(hex_id)
        ids = ids[-3:]
        return '--cipher-suite-blacklist=' + ','.join(ids) if ids else ''

    # ------------------------------------------------------------------
    # v3.7: fetch a browser that can actually load extensions
    # ------------------------------------------------------------------
    CFT_ENDPOINT = ('https://googlechromelabs.github.io/chrome-for-testing/'
                    'last-known-good-versions-with-downloads.json')

    def _cft_platform(self):
        system = platform.system()
        if system == 'Windows':
            return 'win64' if sys.maxsize > 2 ** 32 else 'win32'
        if system == 'Darwin':
            return 'mac-arm64' if platform.machine() in ('arm64',) else 'mac-x64'
        return 'linux64'

    def download_chrome_for_testing(self, progress=None, channel='Stable'):
        """Download + unpack Chrome for Testing and select it.

        Chrome for Testing still honours --load-extension, so bundled
        extensions (Tampermonkey included) load with no prompt.
        Returns (exe_path, version).
        """
        import urllib.request
        import zipfile

        def say(msg):
            if progress:
                try:
                    progress(msg)
                except Exception:
                    pass

        say('Looking up the latest build...')
        opener = urllib.request.build_opener()
        with opener.open(self.CFT_ENDPOINT, timeout=30) as resp:
            catalogue = json.load(resp)

        entry = catalogue['channels'][channel]
        version = entry['version']
        want = self._cft_platform()
        url = None
        for item in entry['downloads']['chrome']:
            if item['platform'] == want:
                url = item['url']
                break
        if not url:
            raise RuntimeError('No Chrome for Testing build for %s' % want)

        target_root = os.path.join(self.profiles_dir, '_browser')
        os.makedirs(target_root, exist_ok=True)
        archive = os.path.join(target_root, 'cft.zip')

        say('Downloading Chrome for Testing %s ...' % version)
        with opener.open(url, timeout=120) as resp, open(archive, 'wb') as out:
            total = int(resp.headers.get('Content-Length') or 0)
            done = 0
            while True:
                chunk = resp.read(262144)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if total:
                    say('Downloading %d%%  (%.0f of %.0f MB)'
                        % (done * 100 // total, done / 1048576.0, total / 1048576.0))

        say('Unpacking...')
        extract_to = os.path.join(target_root, 'chrome-for-testing')
        if os.path.isdir(extract_to):
            shutil.rmtree(extract_to, ignore_errors=True)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extract_to)
        try:
            os.remove(archive)
        except Exception:
            pass

        names = ('chrome.exe' if platform.system() == 'Windows'
                 else 'Google Chrome for Testing' if platform.system() == 'Darwin'
                 else 'chrome')
        exe = None
        for current, dirs, files in os.walk(extract_to):
            if names in files:
                exe = os.path.join(current, names)
                break
        if not exe:
            raise RuntimeError('Downloaded archive did not contain the browser')
        try:
            os.chmod(exe, 0o755)
        except Exception:
            pass

        self.set_browser_override(exe)
        say('Ready: %s' % exe)
        return exe, version

    def selftest_url(self):
        """A real page the first enabled script claims to run on."""
        for entry in self.list_userscripts():
            if not entry.get('enabled'):
                continue
            for pattern in (entry.get('matches') or []) + (entry.get('includes') or []):
                match = re.match(r'^(https?|\*)://([^/*][^/]*)/', str(pattern))
                if match:
                    scheme = 'http' if match.group(1) == 'http' else 'https'
                    return '%s://%s/' % (scheme, match.group(2))
        return 'https://example.com/'

    def profile_is_running(self, profile_path):
        """(port, True) when a Chrome is live on this profile with debugging."""
        import socket
        port_file = os.path.join(profile_path, 'DevToolsActivePort')
        try:
            with open(port_file, 'r', encoding='utf-8') as f:
                port = int(f.read().split('\n')[0].strip())
        except Exception:
            port = 0
        alive = False
        if port:
            try:
                sock = socket.create_connection(('127.0.0.1', port), timeout=1)
                sock.close()
                alive = True
            except Exception:
                alive = False
        locked = any(os.path.exists(os.path.join(profile_path, n))
                     for n in ('lockfile', 'SingletonLock', 'SingletonCookie'))
        return {'port': port, 'alive': alive, 'locked': locked}

    # ------------------------------------------------------------------
    # v4: every launch injects, with no dialogs
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # v4.2: each profile can use its own browser, and can opt out of
    # fingerprint spoofing entirely
    # ------------------------------------------------------------------
    GECKO_NAMES = ('firefox', 'librewolf', 'waterfox', 'palemoon',
                   'seamonkey', 'tor browser', 'basilisk')

    def browser_engine(self, path):
        """'chromium', 'gecko' or 'unknown' for an executable path."""
        low = os.path.basename(path or '').lower()
        if any(n in low for n in self.GECKO_NAMES):
            return 'gecko'
        if any(n in low for n in ('chrome', 'chromium', 'msedge', 'brave',
                                  'vivaldi', 'opera', 'thorium')):
            return 'chromium'
        return 'unknown'

    TOOL_NAME = 'MavelyLink Tool'

    # v4.4: page every freshly generated profile opens on
    DEFAULT_START_URL = 'https://www.facebook.com/'
    # v4.4: opened in the user's own default browser when the tool starts
    TOOL_HOME_URL = 'https://mavlink.click'

    @staticmethod
    def normalize_url(url):
        """Make a user-typed address safe to hand to a browser.

        Adds https:// when no scheme is present so 'facebook.com' and
        'www.facebook.com' open a real page instead of a blank tab or a
        search. Returns '' for empty input.
        """
        url = (url or '').strip()
        if not url:
            return ''
        low = url.lower()
        if low.startswith(('http://', 'https://', 'file://', 'about:',
                           'chrome://', 'edge://', 'brave://', 'ftp://')):
            return url
        # strip a stray leading '//' then prefix https
        url = url.lstrip('/')
        return 'https://' + url

    def profile_shortcut_path(self, profile_name):
        """The desktop shortcut for a profile, or '' when it has none."""
        for ext in ('.lnk', '.desktop', '.command'):
            candidate = os.path.join(self.desktop_dir, profile_name + ext)
            if os.path.exists(candidate):
                return candidate
        return ''

    def _desktop_dirs(self):
        seen, out = set(), []
        home = os.path.expanduser('~')
        for folder in (self.desktop_dir,
                       os.path.join(home, 'Desktop'),
                       os.path.join(home, 'OneDrive', 'Desktop'),
                       os.path.join(os.environ.get('PUBLIC', ''), 'Desktop')):
            if folder and os.path.isdir(folder):
                key = os.path.normcase(os.path.abspath(folder))
                if key not in seen:
                    seen.add(key)
                    out.append(folder)
        return out

    def _resolve_lnk_batch(self, files):
        """{shortcut: (target, arguments)} for Windows .lnk files."""
        found = {}
        if not files or platform.system() != 'Windows':
            return found
        for start in range(0, len(files), 25):
            chunk = files[start:start + 25]
            parts = ["$ws = New-Object -ComObject WScript.Shell", "$out = @()"]
            for full in chunk:
                q = json.dumps(full.replace('/', '\\'))
                parts.append(
                    "try { $s = $ws.CreateShortcut(%s); $out += "
                    "[PSCustomObject]@{ F=%s; T=$s.TargetPath; A=$s.Arguments } } catch {}"
                    % (q, q))
            parts.append("$out | ConvertTo-Json -Compress")
            try:
                proc = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive",
                     "-Command", "; ".join(parts)],
                    capture_output=True, text=True, timeout=60)
                data = json.loads(proc.stdout.strip() or "[]")
            except Exception:
                continue
            if isinstance(data, dict):
                data = [data]
            for item in data:
                try:
                    found[item.get("F", "")] = (item.get("T") or "",
                                                item.get("A") or "")
                except AttributeError:
                    continue
        return found

    def _profile_dir_from_command(self, target, args):
        """Work out which profile a shortcut opens, or ''."""
        blob = '%s %s' % (target or '', args or '')
        match = re.search(r'--user-data-dir="?([^"]+?)"?(?:\s|$)', blob)
        if match and os.path.isdir(match.group(1)):
            return os.path.abspath(match.group(1))
        match = re.search(r'"?([A-Za-z]:\\[^"]+?launch\.pyw?|/[^"]+?launch\.pyw?)"?',
                          blob)
        if match:
            script = match.group(1)
            if os.path.isfile(script):
                return os.path.dirname(os.path.abspath(script))
        return ''

    def scan_desktop_browsers(self):
        """Every desktop icon that opens one of our profiles.

        Matching on file name alone missed shortcuts whose name differs from
        the folder, so the shortcut itself is resolved instead.
        """
        shortcuts = []
        for folder in self._desktop_dirs():
            try:
                names = sorted(os.listdir(folder))
            except Exception:
                continue
            for entry in names:
                if entry.lower().endswith(('.lnk', '.desktop', '.command')):
                    shortcuts.append(os.path.join(folder, entry))

        resolved = self._resolve_lnk_batch(
            [f for f in shortcuts if f.lower().endswith('.lnk')])

        results, seen = [], set()
        for full in shortcuts:
            label = os.path.splitext(os.path.basename(full))[0]
            if full.lower().endswith('.lnk'):
                target, args = resolved.get(full, ('', ''))
            else:
                target, args = '', ''
                try:
                    with open(full, 'r', encoding='utf-8', errors='ignore') as f:
                        for line in f:
                            if line.startswith('Exec='):
                                target, args = '', line[5:].strip()
                                break
                            if line.startswith('"') or 'chrome' in line.lower():
                                args = line.strip()
                except Exception:
                    pass
            path = self._profile_dir_from_command(target, args)
            if not path:
                guess = os.path.join(self.profiles_dir, label)
                if os.path.isdir(guess):
                    path = guess
            if not path or not os.path.isdir(path):
                continue
            key = os.path.normcase(path)
            if key in seen:
                continue
            seen.add(key)
            created = ''
            try:
                created = datetime.fromtimestamp(
                    os.path.getctime(path)).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass
            results.append({'name': label, 'path': path, 'created': created,
                            'shortcut': full})
        return results

    def get_desktop_profiles(self):
        """Only profiles that really exist and really have a desktop icon.

        get_all_profiles() can still list folders left behind by a half
        finished delete, which is why those turn up in the list as browsers
        that are not there any more.
        """
        real = []
        for profile in self.get_all_profiles():
            path = profile.get('path', '')
            if not os.path.isdir(path):
                continue
            looks_real = (os.path.isfile(os.path.join(path, '_fingerprint.json'))
                          or os.path.isdir(os.path.join(path, 'Default'))
                          or os.path.isfile(os.path.join(path, 'launch.pyw'))
                          or os.path.isfile(os.path.join(path, 'launch.py')))
            if looks_real:
                real.append(profile)
        # resolve the shortcuts themselves: names on the desktop do not
        # always match the folder name
        by_path = {os.path.normcase(p['path']): p for p in real}
        found = []
        seen = set()
        try:
            for item in self.scan_desktop_browsers():
                key = os.path.normcase(item['path'])
                if key in seen:
                    continue
                seen.add(key)
                base = dict(by_path.get(key, item))
                base['name'] = item['name']
                base['path'] = item['path']
                base.setdefault('created', item.get('created', ''))
                found.append(base)
        except Exception:
            found = []
        for profile in real:
            if os.path.normcase(profile['path']) not in seen:
                if self.profile_shortcut_path(profile['name']):
                    found.append(profile)
        return found if found else real

    @staticmethod
    def profile_key(profile_path):
        """Folder name: the stable id, whatever the desktop icon is called."""
        return os.path.basename(str(profile_path).rstrip(os.sep))

    def profile_browser_family(self, profile_name, profile_path=None):
        """'Chrome' | 'Edge' | 'Brave' | 'Firefox' | 'Other' for the tabs."""
        if profile_path:
            profile_name = self.profile_key(profile_path)
        try:
            info = self.detect_browser_info(self.browser_for_profile(profile_name))
        except Exception:
            return 'Other'
        brand = (info.get('brand') or '').lower()
        for key, label in (('brave', 'Brave'), ('edge', 'Edge'),
                           ('firefox', 'Firefox'), ('librewolf', 'Firefox'),
                           ('waterfox', 'Firefox'), ('chromium', 'Chrome'),
                           ('chrome', 'Chrome')):
            if key in brand:
                return label
        return 'Other'

    def launch_token(self, profile_name):
        """Secret the tool passes so a launcher knows the tool started it."""
        return 'mvl-' + hashlib.sha1(
            ('mavely:' + profile_name).encode('utf-8')).hexdigest()[:16]

    def profile_browser(self, profile_name):
        try:
            table = self._load_userscript_registry()['settings'].get(
                'profile_browsers', {})
            return table.get(profile_name, '')
        except Exception:
            return ''

    def set_profile_browser(self, profile_name, path):
        reg = self._load_userscript_registry()
        table = reg['settings'].setdefault('profile_browsers', {})
        if path:
            table[profile_name] = path
        else:
            table.pop(profile_name, None)
        self._save_userscript_registry(reg)

    def browser_for_profile(self, profile_name):
        """This profile's own browser if it has one, else the global choice."""
        own = self.profile_browser(profile_name)
        # drop Firefox pins written by the old build, or those profiles
        # would keep opening Firefox for ever
        if own and os.path.exists(own) and self.browser_engine(own) != 'gecko':
            return own
        return self._find_chrome_path()

    def profile_fingerprint(self, profile_name):
        try:
            table = self._load_userscript_registry()['settings'].get(
                'profile_fingerprint', {})
            return bool(table.get(profile_name, True))
        except Exception:
            return True

    def set_profile_fingerprint(self, profile_name, enabled):
        reg = self._load_userscript_registry()
        table = reg['settings'].setdefault('profile_fingerprint', {})
        table[profile_name] = bool(enabled)
        self._save_userscript_registry(reg)

    def apply_profile_fingerprint(self, profile_name, profile_path, enabled):
        """Turn fingerprint spoofing on or off for one profile, for real.

        Off means the patch is neither loaded as an extension nor injected
        over DevTools, so the browser reports its own values.
        """
        self.set_profile_fingerprint(profile_name, enabled)
        ext = os.path.join(profile_path, '_fingerprint_extension')
        if not enabled:
            if os.path.isdir(ext):
                shutil.rmtree(ext, ignore_errors=True)
        elif not os.path.isfile(os.path.join(ext, 'manifest.json')):
            try:
                with open(os.path.join(profile_path, '_fingerprint.json'),
                          'r', encoding='utf-8') as f:
                    self._build_fingerprint_extension(profile_path, json.load(f))
            except Exception:
                pass
        try:
            self._build_cdp_injector(profile_path)
        except Exception:
            pass
        return enabled

    def get_profile_url(self, profile_name):
        try:
            urls = self._load_userscript_registry()['settings'].get('profile_urls', {})
            return urls.get(profile_name, '')
        except Exception:
            return ''

    def set_profile_url(self, profile_name, url):
        reg = self._load_userscript_registry()
        urls = reg['settings'].setdefault('profile_urls', {})
        if url:
            urls[profile_name] = url
        else:
            urls.pop(profile_name, None)
        self._save_userscript_registry(reg)

    def start_url_for(self, profile_name):
        """Page a profile opens on: its own if set, else Facebook."""
        return self.normalize_url(self.get_profile_url(profile_name)) or self.DEFAULT_START_URL

    def rebuild_all_launchers(self, progress=None):
        """Point every profile's launcher at the currently chosen browser.

        The browser path is baked into each launch.pyw, so a profile made
        before the switch would otherwise keep opening the old browser -
        including from its desktop shortcut, which runs the same launcher.
        """
        profiles = self.get_all_profiles()
        done = 0
        for index, profile in enumerate(profiles):
            try:
                if self._profile_launcher(profile['name'], profile['path']):
                    done += 1
            except Exception:
                pass
            if progress:
                try:
                    progress(index + 1, len(profiles), profile['name'])
                except Exception:
                    pass
        return done, len(profiles)

    def launch_profile(self, profile_name, profile_path=None, url=None):
        """Open a profile with its scripts already injected.

        This is the whole 'Report' launch path minus the dialogs: rebuild
        the payload, bake in the page to open, write the launcher, run it.
        """
        if profile_path is None:
            profile_path = os.path.join(self.profiles_dir, profile_name)
        if not self._assert_own_profile(profile_path, 'launch'):
            return False, ('Refused: %s is not a profile this tool owns.'
                           % profile_path)
        if not os.path.isdir(profile_path):
            raise RuntimeError('profile folder is missing: %s' % profile_path)
        # v6.2: the master switch applies to every launch path (window button,
        # desktop shortcut, command line), not only to the main window
        client = self.license()
        if client is not None and not client.app_allowed():
            raise AppDisabledError(client.blocked_reason())

        key = self.profile_key(profile_path)
        if url is not None:
            self.set_profile_url(key, url)

        state = self.profile_is_running(profile_path)
        profile_name = profile_name or key
        if state['alive'] or state['locked']:
            raise RuntimeError(
                "'%s' is already open.\n\nChrome hands a second launch to the "
                "running window and throws away every flag, so nothing can be "
                "injected. Close all of its windows first." % profile_name)

        self._build_userscript_extension(profile_path)
        self._build_cdp_injector(profile_path)

        launcher = self._profile_launcher(key, profile_path)
        runtime = self._python_runtime()
        if not launcher or not runtime:
            raise RuntimeError('No launcher for this profile. Check that '
                               'injection mode is not set to Extension only.')
        try:
            os.remove(os.path.join(profile_path, '_inject', 'inject.log'))
        except Exception:
            pass
        token = self.launch_token(key)
        if os.name == 'nt':
            subprocess.Popen([runtime, launcher, token], close_fds=True,
                             creationflags=0x08000000)
        else:
            subprocess.Popen([runtime, launcher, token], close_fds=True)
        return launcher

    def verbose_diagnostics(self):
        try:
            return bool(self._load_userscript_registry()['settings']
                        .get('verbose', False))
        except Exception:
            return False

    def set_verbose_diagnostics(self, value):
        reg = self._load_userscript_registry()
        reg['settings']['verbose'] = bool(value)
        self._save_userscript_registry(reg)

    def browser_override(self):
        """Explicit browser executable chosen in the UI, or ''."""
        try:
            return self._load_userscript_registry()['settings'].get('browser_path', '')
        except Exception:
            return ''

    def set_browser_override(self, path):
        reg = self._load_userscript_registry()
        reg['settings']['browser_path'] = path or ''
        self._save_userscript_registry(reg)
        self._browser_info_cache = {}

    def browser_candidates(self):
        """Every browser executable we can find, best first."""
        system = platform.system()
        paths = {
            'Windows': [
                r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
                os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
                os.path.expandvars(r'%LOCALAPPDATA%\Chromium\Application\chrome.exe'),
                r'C:\Program Files\Chromium\Application\chrome.exe',
                r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',
                r'C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe',
                os.path.expandvars(r'%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe'),
                r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
                os.path.expandvars(r'%LOCALAPPDATA%\Chrome for Testing\chrome.exe'),
                os.path.expandvars(r'%LOCALAPPDATA%\ms-playwright\chromium\chrome-win\chrome.exe'),
            ],
            'Darwin': [
                '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                '/Applications/Chromium.app/Contents/MacOS/Chromium',
                '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
                '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
                '/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
            ],
            'Linux': [
                '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable',
                '/usr/bin/chromium', '/usr/bin/chromium-browser',
                '/usr/bin/brave-browser', '/usr/bin/microsoft-edge',
                '/snap/bin/chromium',
            ],
        }.get(system, [])

        found = []
        seen = set()
        override = self.browser_override()
        if override and os.path.exists(override):
            found.append(self.detect_browser_info(override))
            seen.add(os.path.normcase(override))
        for path in paths:
            if not path or not os.path.exists(path):
                continue
            key = os.path.normcase(path)
            if key in seen:
                continue
            seen.add(key)
            found.append(self.detect_browser_info(path))
        # browsers that can still load our extension sort first
        found.sort(key=lambda b: (not b['load_extension'], b['brand']))
        return found

    def remote_debugging_policy(self):
        """True/False if an enterprise policy pins it, else None.

        Chrome's RemoteDebuggingAllowed policy silently disables
        --remote-debugging-port. AV suites and corporate images set it, and
        when it is off no DevTools injection can ever work.
        """
        if platform.system() != 'Windows':
            return None
        try:
            import winreg
        except Exception:
            return None
        keys = [
            r'SOFTWARE\Policies\Google\Chrome',
            r'SOFTWARE\Policies\Chromium',
            r'SOFTWARE\Policies\Microsoft\Edge',
            r'SOFTWARE\Policies\BraveSoftware\Brave',
        ]
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub_key in keys:
                try:
                    with winreg.OpenKey(root, sub_key) as handle:
                        value, _ = winreg.QueryValueEx(handle, 'RemoteDebuggingAllowed')
                        return bool(value)
                except OSError:
                    continue
                except Exception:
                    continue
        return None

    def injection_blockers(self):
        """Reasons injection cannot work right now, most important first."""
        problems = []
        info = self.detect_browser_info()
        mode = self.injection_mode()
        if not info['path']:
            problems.append("No browser found. Use 'Change' to pick one.")
            return problems
        if mode in ('cdp', 'both'):
            if self.remote_debugging_policy() is False:
                problems.append(
                    "Your machine's RemoteDebuggingAllowed policy is set to "
                    "Disabled, so Chrome ignores the debug port and DevTools "
                    "injection cannot work. Switch to a browser that loads "
                    "extensions (Brave, Chromium, Chrome for Testing) and set "
                    "'Inject via: Extension'.")
            if not self._python_runtime():
                problems.append(
                    "No Python interpreter was found to run the injector.")
        if mode == 'extension' and not info['load_extension']:
            problems.append(
                "%s %s ignores --load-extension, so Extension mode does "
                "nothing here. Pick another browser or use DevTools mode."
                % (info['brand'], info['version']))
        return problems

    # ------------------------------------------------------------------
    # v3.6: one file that explains exactly why nothing happened
    # ------------------------------------------------------------------
    @staticmethod
    def _tail(path, limit=6000, keep=None):
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
        except Exception:
            return None
        if keep:
            lines = [l for l in text.splitlines()
                     if any(k.lower() in l.lower() for k in keep)]
            text = '\n'.join(lines)
        return text[-limit:] if len(text) > limit else text

    def build_diagnostic_report(self, profile_name=None):
        """Everything needed to understand an injection failure, as text."""
        out = []
        add = out.append

        add('=' * 68)
        add('CHROME PROFILE GENERATOR - DIAGNOSTIC REPORT')
        add(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        add('=' * 68)

        add('')
        add('[ENVIRONMENT]')
        add('  python         : %s' % sys.version.split()[0])
        add('  executable     : %s' % (sys.executable or '-'))
        add('  runtime picked : %s' % (self._python_runtime() or 'NONE'))
        add('  platform       : %s %s' % (platform.system(), platform.release()))
        add('  frozen         : %s' % bool(getattr(sys, 'frozen', False)))
        add('  profiles dir   : %s' % self.profiles_dir)

        info = self.detect_browser_info()
        policy = self.remote_debugging_policy()
        add('')
        add('[BROWSER]')
        add('  path           : %s' % (info['path'] or 'NONE FOUND'))
        add('  brand/version  : %s %s' % (info['brand'], info['version'] or '?'))
        add('  loads exts     : %s' % info['load_extension'])
        add('  debug policy   : %s' % {True: 'allowed', False: 'BLOCKED BY POLICY',
                                       None: 'not set'}[policy])
        add('  override set   : %s' % (self.browser_override() or '(auto-detect)'))
        if info['note']:
            add('  note           : %s' % info['note'])

        add('')
        add('[SETTINGS]')
        add('  inject mode    : %s' % self.injection_mode())
        add('  scripts on     : %s' % self.userscripts_enabled())
        add('  verbose        : %s' % self.verbose_diagnostics())
        add('  fingerprint js : %s' % self.cdp_include_fingerprint())
        for problem in self.injection_blockers():
            add('  BLOCKER        : %s' % problem)

        add('')
        add('[USER SCRIPTS]')
        entries = self.list_userscripts()
        if not entries:
            add('  (none)')
        for entry in entries:
            add('  %-28s %s' % (entry['display_name'][:28],
                                'enabled' if entry['enabled'] else 'disabled'))
            add('      file    : %s (%d bytes)'
                % (entry['file'], len(entry['source'])))
            add('      match   : %s' % (', '.join(
                entry['matches'] or entry['includes']) or 'ALL URLS'))
            add('      run-at  : %s   world: %s   grants: %d'
                % (entry['run_at'], entry['world'], len(entry['grants'])))
            if not entry['matches'] and not entry['includes']:
                add('      WARNING : no @match/@include')

        add('')
        add('[BUNDLED EXTENSIONS]')
        extensions = self.describe_extensions()
        if not extensions:
            add('  (none)')
        for item in extensions:
            add('  %s %s' % (item['name'], item['version']))
            manifest = os.path.join(item['path'], 'manifest.json')
            try:
                with open(manifest, 'r', encoding='utf-8-sig') as f:
                    data = json.load(f)
                add('      manifest: OK (mv%s)' % data.get('manifest_version'))
                bad = [n for n in os.listdir(item['path'])
                       if n.startswith('_') and n != '_locales']
                if bad:
                    add('      PROBLEM : reserved folder(s) %s' % ', '.join(bad))
            except Exception as exc:
                add('      PROBLEM : manifest unreadable - %s' % exc)
            if not info['load_extension']:
                add('      NOTE    : this browser ignores --load-extension')

        profiles = self.get_all_profiles()
        add('')
        add('[PROFILES] %d total' % len(profiles))
        target = None
        if profile_name:
            for item in profiles:
                if item['name'] == profile_name:
                    target = item
                    break
        if target is None and profiles:
            target = max(profiles, key=lambda p: p['created'])
        if target is None:
            add('  (none)')
            return '\n'.join(out)

        path = target['path']
        add('  inspecting     : %s' % target['name'])
        add('  path           : %s' % path)

        add('')
        add('[FILES]')
        for label, rel in (('launcher .pyw', 'launch.pyw'),
                           ('launcher .py', 'launch.py'),
                           ('fingerprint', '_fingerprint.json'),
                           ('fp extension', '_fingerprint_extension/manifest.json'),
                           ('us extension', '_userscripts_extension/manifest.json'),
                           ('injector', '_inject/cdp_inject.py'),
                           ('payload index', '_inject/payload_index.json')):
            full = os.path.join(path, rel.replace('/', os.sep))
            add('  %-14s %s' % (label, ('%d bytes' % os.path.getsize(full))
                                if os.path.exists(full) else 'MISSING'))

        inject_dir = os.path.join(path, '_inject')
        try:
            parts = json.load(open(os.path.join(inject_dir, 'payload_index.json'),
                                   encoding='utf-8'))
            add('')
            add('[PAYLOAD PARTS]')
            for name in parts:
                add('  %-30s %8d bytes'
                    % (name, os.path.getsize(os.path.join(inject_dir, name))))
        except Exception:
            pass

        state = self.profile_is_running(path)
        add('')
        add('[PROFILE STATE]')
        add('  devtools port  : %s' % (state['port'] or 'none recorded'))
        add('  port responding: %s' % state['alive'])
        add('  lock files     : %s' % state['locked'])
        if state['alive'] or state['locked']:
            add('  WARNING        : Chrome is already running on this profile.')
            add('                   Chrome hands new launches to the existing')
            add('                   process and DISCARDS every new flag,')
            add('                   including --remote-debugging-port.')
            add('                   Close all windows of this profile first.')

        add('')
        add('[LAUNCHER]')
        why = []
        built = self._profile_launcher(target['name'], path, why)
        add('  path           : %s' % (built or 'NOT BUILT'))
        for reason in why:
            add('  reason         : %s' % reason)

        add('')
        add('[SHORTCUT]')
        try:
            chrome_exe = self._find_chrome_path() or ''
            fingerprint = json.load(open(os.path.join(path, '_fingerprint.json'),
                                         encoding='utf-8'))
            ext_dir = os.path.join(path, '_fingerprint_extension')
            tgt, args, _ = self._shortcut_target(target['name'], path,
                                                 fingerprint, ext_dir, chrome_exe)
            add('  target         : %s' % tgt)
            add('  arguments      : %s' % args[:300])
        except Exception as exc:
            add('  could not compute: %s' % exc)

        for label, rel, keep in (
                ('LAUNCHER LOG', 'launch.log', None),
                ('INJECTOR LOG', os.path.join('_inject', 'inject.log'), None),
                ('CHROME STDERR', 'chrome_stderr.log',
                 ('extension', 'error', 'fail')),
                ('CHROME DEBUG LOG', 'chrome_debug.log',
                 ('extension', 'error', 'fail', 'manifest'))):
            text = self._tail(os.path.join(path, rel))
            add('')
            add('[%s]' % label)
            if text is None:
                add('  (file not present)')
            elif not text.strip():
                add('  (empty)')
            else:
                if keep:
                    filtered = self._tail(os.path.join(path, rel), keep=keep)
                    text = filtered if (filtered or '').strip() else text[-2000:]
                for line in text.strip().splitlines()[-80:]:
                    add('  ' + line)

        return '\n'.join(out)

    def save_diagnostic_report(self, profile_name=None):
        text = self.build_diagnostic_report(profile_name)
        name = 'chrome_profile_report_%s.txt' % datetime.now().strftime('%H%M%S')
        for folder in (self.desktop_dir, self.profiles_dir):
            try:
                path = os.path.join(folder, name)
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(text)
                return path, text
            except Exception:
                continue
        return None, text

    # ------------------------------------------------------------------
    # v3.6: pull old profiles onto the current language / size pools
    # ------------------------------------------------------------------
    def profile_pool_violations(self):
        """Profiles whose saved fingerprint uses a language or size no longer allowed."""
        langs = set(self.get_language_pool())
        sizes = {tuple(s) for s in self.get_resolution_pool()}
        bad = []
        for profile in self.get_all_profiles():
            fp_path = os.path.join(profile['path'], '_fingerprint.json')
            try:
                with open(fp_path, 'r', encoding='utf-8') as f:
                    fingerprint = json.load(f)
            except Exception:
                continue
            res = fingerprint.get('screen_resolution') or {}
            size = (res.get('width'), res.get('height'))
            if fingerprint.get('language') not in langs or size not in sizes:
                bad.append({'name': profile['name'], 'path': profile['path'],
                            'language': fingerprint.get('language'), 'size': size})
        return bad

    def migrate_profile_pools(self, profile_path):
        """Rewrite one profile's language / screen size into the allowed pools."""
        if not self._assert_own_profile(profile_path, 'migrate'):
            return False
        fp_path = os.path.join(profile_path, '_fingerprint.json')
        try:
            with open(fp_path, 'r', encoding='utf-8') as f:
                fingerprint = json.load(f)
        except Exception:
            return False

        langs = self.get_language_pool()
        sizes = [tuple(s) for s in self.get_resolution_pool()]
        changed = False

        if langs and fingerprint.get('language') not in langs:
            fingerprint['language'] = random.choice(langs)
            changed = True
        if langs:
            kept = [l for l in fingerprint.get('languages', []) if l in langs
                    or '-' not in l]
            if not kept or kept[0] != fingerprint['language']:
                base = fingerprint['language'].split('-')[0]
                kept = [fingerprint['language']]
                if base != fingerprint['language']:
                    kept.append(base)
                if 'en' not in kept:
                    kept.append('en')
                changed = True
            if kept != fingerprint.get('languages'):
                fingerprint['languages'] = kept
                changed = True

        res = fingerprint.get('screen_resolution') or {}
        if sizes and (res.get('width'), res.get('height')) not in sizes:
            width, height = random.choice(sizes)
            res['width'] = width
            res['height'] = height
            for key, value in (('avail_width', width), ('availWidth', width)):
                if key in res:
                    res[key] = value
            for key in ('avail_height', 'availHeight'):
                if key in res:
                    res[key] = height - 40
            fingerprint['screen_resolution'] = res
            changed = True

        if not changed:
            return False

        fingerprint = self._enforce_selection(fingerprint)
        try:
            with open(fp_path, 'w', encoding='utf-8') as f:
                json.dump(fingerprint, f, indent=2)
        except Exception:
            return False

        # everything derived from the fingerprint has to be rebuilt
        try:
            self._build_fingerprint_extension(profile_path, fingerprint)
        except Exception:
            pass
        try:
            self._build_userscript_extension(profile_path)
            self._build_cdp_injector(profile_path)
        except Exception:
            pass
        return True

    def migrate_all_profiles(self, rebuild_shortcuts=True, progress=None):
        profiles = self.get_all_profiles()
        fixed = 0
        for index, profile in enumerate(profiles):
            if self.migrate_profile_pools(profile['path']):
                fixed += 1
                if rebuild_shortcuts:
                    try:
                        self.create_desktop_shortcut(profile['name'], profile['path'])
                    except Exception:
                        pass
            if progress:
                try:
                    progress(index + 1, len(profiles), profile['name'])
                except Exception:
                    pass
        return fixed, len(profiles)

    def _get_userscripts_directory(self):
        d = os.path.join(self.profiles_dir, '_userscripts')
        os.makedirs(d, exist_ok=True)
        return d

    def _get_userscripts_cache_directory(self):
        d = os.path.join(self._get_userscripts_directory(), '_cache')
        os.makedirs(d, exist_ok=True)
        return d

    def _userscript_registry_path(self):
        return os.path.join(self.userscripts_dir, 'registry.json')

    def _load_userscript_registry(self):
        path = self._userscript_registry_path()
        data = {}
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault('version', 1)
        data.setdefault('scripts', {})
        data.setdefault('settings', {})
        data['settings'].setdefault('download_requires', True)
        data['settings'].setdefault('enabled', True)
        return data

    def _save_userscript_registry(self, registry):
        try:
            with open(self._userscript_registry_path(), 'w', encoding='utf-8') as f:
                json.dump(registry, f, indent=2)
        except Exception as e:
            print(f"[userscripts] Failed to save registry: {e}")

    def userscripts_enabled(self):
        return bool(self._load_userscript_registry()['settings'].get('enabled', True))

    def set_userscripts_enabled(self, value):
        reg = self._load_userscript_registry()
        reg['settings']['enabled'] = bool(value)
        self._save_userscript_registry(reg)

    def userscript_download_requires(self):
        return bool(self._load_userscript_registry()['settings'].get('download_requires', True))

    def set_userscript_download_requires(self, value):
        reg = self._load_userscript_registry()
        reg['settings']['download_requires'] = bool(value)
        self._save_userscript_registry(reg)

    # ------------------------------------------------------------------
    # metadata parsing  (// ==UserScript== ... // ==/UserScript==)
    # ------------------------------------------------------------------
    @staticmethod
    def parse_userscript_metadata(source):
        """Parse a Tampermonkey/Greasemonkey metadata block."""
        meta = {
            'name': '', 'namespace': '', 'version': '', 'description': '',
            'author': '', 'icon': '', 'run_at': 'document-idle',
            'matches': [], 'includes': [], 'excludes': [], 'exclude_matches': [],
            'grants': [], 'requires': [], 'resources': [], 'connects': [],
            'noframes': False, 'world': 'MAIN', 'meta_str': '', 'priority': 0,
        }
        lines = source.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        in_block = False
        block_lines = []
        raw = {}
        for line in lines:
            stripped = line.strip()
            if not in_block:
                if re.match(r'^//\s*==UserScript==\s*$', stripped):
                    in_block = True
                    block_lines.append(stripped)
                continue
            block_lines.append(stripped)
            if re.match(r'^//\s*==/UserScript==\s*$', stripped):
                break
            m = re.match(r'^//\s*@([A-Za-z0-9_:\-]+)\s*(.*)$', stripped)
            if m:
                raw.setdefault(m.group(1).lower(), []).append(m.group(2).strip())
        meta['meta_str'] = '\n'.join(block_lines)

        def first(key, default=''):
            vals = raw.get(key)
            return vals[0] if vals else default

        meta['name'] = first('name')
        meta['namespace'] = first('namespace')
        meta['version'] = first('version')
        meta['description'] = first('description')
        meta['author'] = first('author')
        meta['icon'] = first('icon') or first('iconurl')
        meta['matches'] = [v for v in raw.get('match', []) if v]
        meta['includes'] = [v for v in raw.get('include', []) if v]
        meta['excludes'] = [v for v in raw.get('exclude', []) if v]
        meta['exclude_matches'] = [v for v in (raw.get('exclude-match', []) +
                                               raw.get('exclude_match', [])) if v]
        meta['grants'] = [v for v in raw.get('grant', []) if v]
        meta['requires'] = [v for v in raw.get('require', []) if v]
        meta['connects'] = [v for v in raw.get('connect', []) if v]
        meta['noframes'] = ('noframes' in raw)

        run_at = (first('run-at') or first('run_at') or 'document-idle').strip().lower()
        run_at = run_at.replace('_', '-')
        if run_at not in ('document-start', 'document-body',
                          'document-end', 'document-idle', 'context-menu'):
            run_at = 'document-idle'
        meta['run_at'] = run_at

        inject = (first('inject-into') or first('sandbox') or '').strip().lower()
        if inject in ('content', 'isolated', 'js'):
            meta['world'] = 'ISOLATED'
        else:
            meta['world'] = 'MAIN'

        try:
            meta['priority'] = int(first('priority', '0') or 0)
        except Exception:
            meta['priority'] = 0

        for entry in raw.get('resource', []):
            parts = entry.split(None, 1)
            if len(parts) == 2:
                meta['resources'].append({'name': parts[0], 'url': parts[1].strip()})
        return meta

    @staticmethod
    def _slugify_userscript_name(name):
        slug = re.sub(r'[^A-Za-z0-9._-]+', '-', (name or '').strip()).strip('-.')
        return (slug[:60] or 'script').lower()

    def userscript_template(self, name='My Script'):
        return self.USERSCRIPT_TEMPLATE % {'name': name}

    # ------------------------------------------------------------------
    # CRUD over the shared script folder
    # ------------------------------------------------------------------
    def list_userscripts(self):
        """Local user scripts are no longer managed on the desktop.

        v6.0: script management moved entirely to the website dashboard. The
        desktop only injects the scripts the licensing server authorises for
        this tier (see server_scripts()), so the local library is always
        empty. Returning [] here means every local-compile path below
        (_build_cdp_parts, _build_userscript_extension, the diagnostics)
        naturally produces nothing local, while the server-script branch is
        untouched. The original file-scanning body is kept beneath the return
        so nothing that inspects it breaks, but it never executes.
        """
        return []

    def _list_userscripts_local_DISABLED(self):
        """Return every *.user.js / *.js in the userscripts folder."""
        registry = self._load_userscript_registry()
        entries = []
        try:
            names = sorted(os.listdir(self.userscripts_dir))
        except Exception:
            names = []
        dirty = False
        for fname in names:
            if not fname.lower().endswith('.js'):
                continue
            full = os.path.join(self.userscripts_dir, fname)
            if not os.path.isfile(full):
                continue
            try:
                with open(full, 'r', encoding='utf-8', errors='replace') as f:
                    source = f.read()
            except Exception:
                continue
            meta = self.parse_userscript_metadata(source)
            rec = registry['scripts'].get(fname)
            if rec is None:
                rec = {'enabled': True, 'added': datetime.now().isoformat()}
                registry['scripts'][fname] = rec
                dirty = True
            entry = dict(meta)
            entry['file'] = fname
            entry['path'] = full
            entry['source'] = source
            entry['enabled'] = bool(rec.get('enabled', True))
            entry['id'] = hashlib.sha1(fname.encode('utf-8')).hexdigest()[:16]
            entry['display_name'] = meta['name'] or os.path.splitext(fname)[0]
            entries.append(entry)
        # forget registry rows whose file is gone
        for key in list(registry['scripts'].keys()):
            if key not in names:
                del registry['scripts'][key]
                dirty = True
        if dirty:
            self._save_userscript_registry(registry)
        entries.sort(key=lambda e: (-e.get('priority', 0), e['display_name'].lower()))
        return entries

    def get_userscript_source(self, file_name):
        full = os.path.join(self.userscripts_dir, os.path.basename(file_name))
        if not os.path.exists(full):
            return ''
        with open(full, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()

    def save_userscript(self, source, file_name=None, enabled=None):
        """Write a userscript; returns the file name it was stored under."""
        meta = self.parse_userscript_metadata(source)
        if not file_name:
            base = self._slugify_userscript_name(meta['name'] or 'script')
            file_name = base + '.user.js'
            candidate = os.path.join(self.userscripts_dir, file_name)
            n = 2
            while os.path.exists(candidate):
                file_name = '%s-%d.user.js' % (base, n)
                candidate = os.path.join(self.userscripts_dir, file_name)
                n += 1
        file_name = os.path.basename(file_name)
        if not file_name.lower().endswith('.js'):
            file_name += '.user.js'
        full = os.path.join(self.userscripts_dir, file_name)
        with open(full, 'w', encoding='utf-8') as f:
            f.write(source)
        registry = self._load_userscript_registry()
        rec = registry['scripts'].setdefault(
            file_name, {'enabled': True, 'added': datetime.now().isoformat()})
        if enabled is not None:
            rec['enabled'] = bool(enabled)
        rec['updated'] = datetime.now().isoformat()
        self._save_userscript_registry(registry)
        return file_name

    def delete_userscript(self, file_name):
        file_name = os.path.basename(file_name)
        full = os.path.join(self.userscripts_dir, file_name)
        removed = False
        if os.path.exists(full):
            try:
                os.remove(full)
                removed = True
            except Exception as e:
                print(f"[userscripts] Failed to delete {file_name}: {e}")
        registry = self._load_userscript_registry()
        if file_name in registry['scripts']:
            del registry['scripts'][file_name]
            self._save_userscript_registry(registry)
        return removed

    def set_userscript_enabled(self, file_name, enabled):
        file_name = os.path.basename(file_name)
        registry = self._load_userscript_registry()
        rec = registry['scripts'].setdefault(
            file_name, {'enabled': True, 'added': datetime.now().isoformat()})
        rec['enabled'] = bool(enabled)
        self._save_userscript_registry(registry)
        return rec['enabled']

    def import_userscript(self, path):
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            source = f.read()
        base = os.path.basename(path)
        meta = self.parse_userscript_metadata(source)
        if not meta['name']:
            base = self._slugify_userscript_name(os.path.splitext(base)[0]) + '.user.js'
            return self.save_userscript(source, base)
        return self.save_userscript(source)

    def rename_userscript(self, old_name, new_name):
        old_name = os.path.basename(old_name)
        new_name = os.path.basename(new_name)
        if not new_name.lower().endswith('.js'):
            new_name += '.user.js'
        src = os.path.join(self.userscripts_dir, old_name)
        dst = os.path.join(self.userscripts_dir, new_name)
        if not os.path.exists(src) or os.path.exists(dst):
            return False
        os.rename(src, dst)
        registry = self._load_userscript_registry()
        registry['scripts'][new_name] = registry['scripts'].pop(
            old_name, {'enabled': True})
        self._save_userscript_registry(registry)
        return True

    # ------------------------------------------------------------------
    # @require / @resource fetching (cached on disk)
    # ------------------------------------------------------------------
    def _userscript_cache_file(self, url):
        digest = hashlib.sha1(url.encode('utf-8')).hexdigest()
        return os.path.join(self.userscripts_cache_dir, digest + '.txt')

    def _fetch_userscript_asset(self, url, timeout=12):
        """Download @require / @resource content, using an on-disk cache."""
        cache_file = self._userscript_cache_file(url)
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8', errors='replace') as f:
                    return f.read()
            except Exception:
                pass
        if not self.userscript_download_requires():
            return None
        if not url.lower().startswith(('http://', 'https://')):
            return None
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={
                'User-Agent': self.user_agents[0],
                'Accept': '*/*',
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = resp.read()
            text = payload.decode('utf-8', errors='replace')
            try:
                with open(cache_file, 'w', encoding='utf-8') as f:
                    f.write(text)
            except Exception:
                pass
            return text
        except Exception as e:
            print(f"[userscripts] Could not fetch {url}: {e}")
            return None

    def clear_userscript_cache(self):
        n = 0
        try:
            for f in os.listdir(self.userscripts_cache_dir):
                try:
                    os.remove(os.path.join(self.userscripts_cache_dir, f))
                    n += 1
                except Exception:
                    pass
        except Exception:
            pass
        return n

    # ------------------------------------------------------------------
    # extension compilation
    # ------------------------------------------------------------------
    def _userscript_wrapper(self, entry, host_key):
        """Wrap one userscript into a standalone content-script file."""
        api_names = self.USERSCRIPT_API_NAMES
        meta_js = json.dumps({
            'id': entry['id'],
            'name': entry['display_name'],
            'namespace': entry.get('namespace', ''),
            'version': entry.get('version', ''),
            'description': entry.get('description', ''),
            'author': entry.get('author', ''),
            'matches': entry.get('matches', []),
            'includes': entry.get('includes', []),
            'excludes': entry.get('excludes', []),
            'excludeMatches': entry.get('exclude_matches', []),
            'grants': entry.get('grants', []),
            'runAt': entry.get('run_at', 'document-idle'),
            'noframes': bool(entry.get('noframes')),
            'world': entry.get('world', 'MAIN'),
            'metaStr': entry.get('meta_str', ''),
            'resourceList': [r['name'] for r in entry.get('resources', [])],
        }, ensure_ascii=False)

        prelude = []
        for url in entry.get('requires', []):
            lib = self._fetch_userscript_asset(url)
            if lib:
                prelude.append('/* @require %s */\n%s\n' % (url, lib))
            else:
                prelude.append('/* @require %s -- unavailable */\n' % url)

        parts = [
            '/* ==== %s (%s) ==== */\n' % (entry['display_name'], entry['file']),
            '(function () {\n',
            'var H = window[%s];\n' % json.dumps(host_key),
            'if (!H) { return; }\n',
            'H.run(%s, %s, function (%s) {\n' % (
                meta_js, json.dumps(api_names), ', '.join(api_names)),
            ''.join(prelude),
            entry['source'],
            '\n;\n});\n})();\n',
        ]
        return ''.join(parts)

    def _userscript_resource_map(self, entries):
        resources = {}
        for entry in entries:
            for res in entry.get('resources', []):
                if res['name'] in resources:
                    continue
                text = self._fetch_userscript_asset(res['url'])
                if text is None:
                    resources[res['name']] = {'url': res['url']}
                else:
                    resources[res['name']] = {'text': text, 'url': res['url']}
        return resources

    def _build_userscript_extension(self, profile_path, entries=None):
        """Compile the enabled userscripts into an MV3 extension for one profile.

        Returns the extension directory, or None when there is nothing to load.
        """
        if not self._assert_own_profile(profile_path, 'write userscripts into'):
            return None
        ext_dir = os.path.join(profile_path, self.USERSCRIPT_EXT_DIRNAME)
        try:
            if entries is None:
                entries = self.list_userscripts()
            if not self.userscripts_enabled():
                entries = []
            entries = [e for e in entries if e.get('enabled')]
            # v6.2: server scripts are compiled into the extension too, so
            # 'extension' and 'both' injection modes deliver them as well
            entries = list(entries) + self.server_script_entries()

            if not entries:
                if os.path.isdir(ext_dir):
                    shutil.rmtree(ext_dir, ignore_errors=True)
                return None

            if os.path.isdir(ext_dir):
                shutil.rmtree(ext_dir, ignore_errors=True)
            os.makedirs(ext_dir, exist_ok=True)

            profile_name = os.path.basename(profile_path.rstrip(os.sep))
            seed = hashlib.sha1(('us:' + profile_name).encode('utf-8')).hexdigest()
            host_key = '__us_' + seed[:12]
            token = 'us_' + seed[12:28]

            resources = self._userscript_resource_map(entries)

            runtime = (self.USERSCRIPT_RUNTIME_JS
                       .replace('__USKEY__', host_key)
                       .replace('__USTOKEN__', token)
                       .replace('__USPROFILE__', profile_name)
                       .replace('__USBRIDGED__', 'true')
                       .replace('__USRESOURCES__', json.dumps(resources, ensure_ascii=False)))
            bridge = self.USERSCRIPT_BRIDGE_JS.replace('__USTOKEN__', token)

            with open(os.path.join(ext_dir, 'gm_runtime.js'), 'w', encoding='utf-8') as f:
                f.write(runtime)
            with open(os.path.join(ext_dir, 'bridge.js'), 'w', encoding='utf-8') as f:
                f.write(bridge)
            with open(os.path.join(ext_dir, 'sw.js'), 'w', encoding='utf-8') as f:
                f.write(self.USERSCRIPT_SW_JS)
            keepalive = self._keepalive_js(profile_path)
            if keepalive:
                with open(os.path.join(ext_dir, 'keepalive.js'), 'w', encoding='utf-8') as f:
                    f.write(keepalive)
            try:
                import base64 as _b64
                with open(os.path.join(ext_dir, 'icon.png'), 'wb') as f:
                    f.write(_b64.b64decode(self.USERSCRIPT_ICON_B64))
            except Exception:
                pass

            # group scripts by (world, chrome run_at) so each combination
            # becomes one content_scripts entry
            groups = {}
            listing = []
            for index, entry in enumerate(entries):
                world = 'ISOLATED' if entry.get('world') == 'ISOLATED' else 'MAIN'
                run_at = self.USERSCRIPT_RUN_AT.get(
                    entry.get('run_at', 'document-idle'), 'document_idle')
                fname = 'us_%02d_%s.js' % (index, self._slugify_userscript_name(
                    entry['display_name'])[:24] or 'script')
                with open(os.path.join(ext_dir, fname), 'w', encoding='utf-8') as f:
                    f.write(self._userscript_wrapper(entry, host_key))
                groups.setdefault((world, run_at), []).append(fname)
                listing.append({
                    'file': entry['file'],
                    'name': entry['display_name'],
                    'version': entry.get('version', ''),
                    'run_at': entry.get('run_at'),
                    'world': world,
                    'matches': entry.get('matches', []) or entry.get('includes', []),
                })

            content_scripts = [{
                "matches": ["<all_urls>"],
                "js": ["bridge.js"],
                "run_at": "document_start",
                "all_frames": True,
                "match_about_blank": True,
                "world": "ISOLATED",
            }]
            if keepalive:
                # both worlds: a MAIN-world patch is invisible to an
                # ISOLATED-world user script, which has its own window
                for _ka_world in ("MAIN", "ISOLATED"):
                    content_scripts.append({
                        "matches": ["<all_urls>"],
                        "js": ["keepalive.js"],
                        "run_at": "document_start",
                        "all_frames": False,
                        "match_about_blank": False,
                        "world": _ka_world,
                    })
            order = ['document_start', 'document_end', 'document_idle']
            for world in ('MAIN', 'ISOLATED'):
                for run_at in order:
                    files = groups.get((world, run_at))
                    if not files:
                        continue
                    content_scripts.append({
                        "matches": ["<all_urls>"],
                        "js": ["gm_runtime.js"] + files,
                        "run_at": run_at,
                        "all_frames": True,
                        "match_about_blank": True,
                        "world": world,
                    })

            manifest = {
                "manifest_version": 3,
                "name": "Profile User Scripts",
                "version": "1.0",
                "description": "User script injection for this profile.",
                "background": {"service_worker": "sw.js"},
                "content_scripts": content_scripts,
                "host_permissions": ["<all_urls>"],
                "permissions": ["storage", "tabs", "notifications",
                                "downloads", "cookies"],
                "icons": {"48": "icon.png"},
            }
            with open(os.path.join(ext_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2)
            with open(os.path.join(ext_dir, '_scripts.json'), 'w', encoding='utf-8') as f:
                json.dump({'built': datetime.now().isoformat(),
                           'scripts': listing}, f, indent=2)
            return ext_dir
        except Exception as e:
            print(f"[userscripts] Failed to build extension: {e}")
            return None

    def _collect_extension_dirs(self, profile_path, primary_ext=None):
        """Every extension directory Chrome should load for this profile."""
        dirs = []
        candidates = []
        if primary_ext:
            candidates.append(primary_ext)
        candidates.append(os.path.join(profile_path, '_fingerprint_extension'))
        candidates.append(os.path.join(profile_path, self.USERSCRIPT_EXT_DIRNAME))
        for extra in sorted(self.list_extra_extensions()):
            candidates.append(extra)
        for path in candidates:
            if not path:
                continue
            norm = os.path.normpath(path)
            if norm in dirs:
                continue
            if os.path.isfile(os.path.join(norm, 'manifest.json')):
                dirs.append(norm)
        return dirs

    def _profile_launcher(self, name, profile_path, why=None):
        """Launcher script path when DevTools injection is active, else None.

        Pass a list as `why` to collect the reason it could not be built.
        """
        def fail(reason):
            if why is not None:
                why.append(reason)
            return None

        if self.injection_mode() == 'extension':
            return fail("injection mode is 'extension', so no launcher is used")
        if not os.path.isdir(profile_path):
            return fail('profile folder does not exist: %s' % profile_path)
        fp_path = os.path.join(profile_path, '_fingerprint.json')
        try:
            with open(fp_path, 'r', encoding='utf-8') as f:
                fingerprint = json.load(f)
        except Exception as exc:
            return fail('_fingerprint.json unreadable: %s' % exc)
        if not self._find_chrome_path():
            return fail('no browser executable found')
        ext_dir = os.path.join(profile_path, '_fingerprint_extension')
        try:
            path = self._build_launcher_script(name, profile_path,
                                               fingerprint, ext_dir)
        except Exception as exc:
            return fail('launcher build raised %s: %s'
                        % (type(exc).__name__, exc))
        if not path:
            return fail('launcher builder returned nothing')
        return path

    def _shortcut_arg_string(self, profile_path):
        """Full Chrome flag string for a profile, extensions included.

        Used by the macOS / Linux shortcut writers so they match the
        Windows .lnk behaviour instead of only passing --user-data-dir.
        """
        fp_path = os.path.join(profile_path, '_fingerprint.json')
        fingerprint = None
        if os.path.exists(fp_path):
            try:
                with open(fp_path, 'r', encoding='utf-8') as f:
                    fingerprint = json.load(f)
            except Exception:
                fingerprint = None
        if fingerprint is None:
            fingerprint = self._enforce_selection(self._generate_fingerprint())
            try:
                with open(fp_path, 'w', encoding='utf-8') as f:
                    json.dump(fingerprint, f, indent=2)
            except Exception:
                pass

        ext_dir = os.path.join(profile_path, '_fingerprint_extension')
        if not os.path.exists(os.path.join(ext_dir, 'manifest.json')):
            ext_dir = self._build_fingerprint_extension(profile_path, fingerprint) or ''
        self._build_userscript_extension(profile_path)
        return self._chrome_args_for_profile(profile_path, fingerprint, ext_dir)

    def list_extra_extensions(self):
        """Unpacked extensions dropped in <profiles_dir>/_extensions/<name>/."""
        root = os.path.join(self.profiles_dir, '_extensions')
        found = []
        if not os.path.isdir(root):
            return found
        for name in os.listdir(root):
            path = os.path.join(root, name)
            if os.path.isfile(os.path.join(path, 'manifest.json')):
                found.append(path)
        return found

    # ------------------------------------------------------------------
    # pushing script changes into existing profiles
    # ------------------------------------------------------------------
    def sync_userscripts_to_profile(self, profile_name, entries=None,
                                    rebuild_shortcut=False):
        profile_path = profile_name
        if not os.path.isabs(profile_path):
            profile_path = os.path.join(self.profiles_dir, profile_name)
        if not os.path.isdir(profile_path):
            return False
        self._build_userscript_extension(profile_path, entries)
        self._build_cdp_injector(profile_path, entries)
        if rebuild_shortcut:
            try:
                self.create_desktop_shortcut(
                    os.path.basename(profile_path.rstrip(os.sep)), profile_path)
            except Exception:
                pass
        return True

    def sync_userscripts_to_all_profiles(self, rebuild_shortcuts=True,
                                         progress=None):
        entries = self.list_userscripts()
        profiles = self.get_all_profiles()
        done = 0
        for i, profile in enumerate(profiles):
            if self.sync_userscripts_to_profile(profile['path'], entries,
                                                rebuild_shortcuts):
                done += 1
            if progress:
                try:
                    progress(i + 1, len(profiles), profile['name'])
                except Exception:
                    pass
        return done, len(profiles)

    def userscript_report(self):
        entries = self.list_userscripts()
        on = [e for e in entries if e['enabled']]
        return {
            'total': len(entries),
            'enabled': len(on),
            'names': [e['display_name'] for e in on],
        }

    def create_desktop_shortcut(self, profile_name, profile_path):
        chrome_exe = self._find_chrome_path()
        if not chrome_exe:
            return False

        system = platform.system()
        shortcut_name = profile_name
        profile_icon = (self._generate_unique_icon(profile_name)
                        or self._generate_colored_icon(profile_name)
                        or self.icon_path)

        if system == 'Windows':
            return self._create_windows_shortcut(shortcut_name, chrome_exe, profile_path, profile_icon)
        elif system == 'Darwin':
            return self._create_macos_shortcut(shortcut_name, chrome_exe, profile_path)
        else:
            return self._create_linux_shortcut(shortcut_name, chrome_exe, profile_path, profile_icon)

    def _create_windows_shortcut(self, name, chrome_exe, profile_path, icon_for_shortcut=None):
        try:
            if icon_for_shortcut is None:
                icon_for_shortcut = self.icon_path

            fp_path = os.path.join(profile_path, '_fingerprint.json')
            if os.path.exists(fp_path):
                with open(fp_path, 'r', encoding='utf-8') as f:
                    fingerprint = json.load(f)
            else:
                fingerprint = self._generate_fingerprint()
                with open(fp_path, 'w', encoding='utf-8') as f:
                    json.dump(fingerprint, f, indent=2)

            ext_dir = os.path.join(profile_path, '_fingerprint_extension')
            if not os.path.exists(os.path.join(ext_dir, 'manifest.json')):
                ext_dir = self._build_fingerprint_extension(profile_path, fingerprint) or ''

            self._build_userscript_extension(profile_path)
            self._build_cdp_injector(profile_path)

            try:
                self._build_launcher_script(name, profile_path, fingerprint, ext_dir)
            except Exception:
                pass

            def winpath(p):
                if not p: return p
                return os.path.normpath(p).replace('/', '\\')

            lnk_file = winpath(os.path.join(self.desktop_dir, f"{name}.lnk"))
            # v3.3: with DevTools injection the shortcut launches the
            # per-profile launcher, which starts Chrome *and* the injector
            target, arguments, workdir = self._shortcut_target(
                name, profile_path, fingerprint, ext_dir, chrome_exe)
            target_path = winpath(target)
            working_dir = winpath(workdir)

            chosen_icon = icon_for_shortcut if (icon_for_shortcut and os.path.exists(icon_for_shortcut)) else chrome_exe
            icon_loc = winpath(chosen_icon) + ",0"
            description = f"Chrome Profile - {name}"

            if self._make_lnk_via_powershell(
                lnk_file=lnk_file, target=target_path,
                arguments=arguments, working_dir=working_dir,
                icon=icon_loc, description=description,
            ) and self._verify_lnk_icon(lnk_file, chosen_icon):
                self._invalidate_icon_cache_for(lnk_file)
                return True

            if self._make_lnk_via_pywin32(
                lnk_file=lnk_file, target=target_path,
                arguments=arguments, working_dir=working_dir,
                icon=icon_loc, description=description,
            ) and self._verify_lnk_icon(lnk_file, chosen_icon):
                self._invalidate_icon_cache_for(lnk_file)
                return True

            if self._make_lnk_via_vbs(
                lnk_file=lnk_file, target=target_path,
                arguments=arguments, working_dir=working_dir,
                icon=icon_loc, description=description,
            ) and self._verify_lnk_icon(lnk_file, chosen_icon):
                self._invalidate_icon_cache_for(lnk_file)
                return True

            if os.path.exists(lnk_file):
                print(f"[shortcut] Created '{name}' but icon embedding failed; using fallback icon")
                return True

            print(f"[shortcut] All three methods failed for '{name}'")
            return False

        except Exception as e:
            print(f"Error creating Windows shortcut: {e}")
            return False

    def _verify_lnk_icon(self, lnk_file, expected_icon_path):
        try:
            if not os.path.exists(lnk_file):
                return False
            if not expected_icon_path:
                return True
            basename = os.path.basename(expected_icon_path)
            if not basename:
                return True
            with open(lnk_file, 'rb') as f:
                data = f.read()
            needle_utf16 = basename.encode('utf-16le')
            needle_ascii = basename.encode('latin-1', errors='ignore')
            return needle_utf16 in data or needle_ascii in data
        except Exception as e:
            print(f"[lnk-verify] {e}")
            return True

    def _invalidate_icon_cache_for(self, lnk_file):
        try:
            if os.path.exists(lnk_file):
                now = time.time()
                os.utime(lnk_file, (now, now))
        except Exception:
            pass

    def _make_lnk_via_vbs(self, lnk_file, target, arguments, working_dir, icon, description):
        if platform.system() != 'Windows':
            return False
        vbs_file = lnk_file + ".tmp.vbs"
        try:
            args_vbs = arguments.replace('"', '""')
            vbs_content = (
                'Set oWS = WScript.CreateObject("WScript.Shell")\r\n'
                f'Set oLink = oWS.CreateShortcut("{lnk_file}")\r\n'
                f'oLink.TargetPath = "{target}"\r\n'
                f'oLink.Arguments = "{args_vbs}"\r\n'
                f'oLink.WorkingDirectory = "{working_dir}"\r\n'
                f'oLink.IconLocation = "{icon}"\r\n'
                f'oLink.Description = "{description}"\r\n'
                'oLink.Save\r\n'
            )
            with open(vbs_file, 'w', encoding='utf-8') as f:
                f.write(vbs_content)
            res = subprocess.run(
                ['cscript', '//nologo', vbs_file],
                capture_output=True, text=True, timeout=15
            )
            return res.returncode == 0 and os.path.exists(lnk_file)
        except Exception as e:
            print(f"[lnk] VBS shortcut creation failed: {e}")
            return False
        finally:
            try:
                if os.path.exists(vbs_file):
                    os.remove(vbs_file)
            except Exception:
                pass

    def _make_lnk_via_pywin32(self, lnk_file, target, arguments, working_dir, icon, description):
        if platform.system() != 'Windows':
            return False
        try:
            from win32com.client import Dispatch
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(lnk_file)
            shortcut.Targetpath = target
            shortcut.Arguments = arguments
            shortcut.WorkingDirectory = working_dir
            shortcut.IconLocation = icon
            shortcut.Description = description
            shortcut.save()
            return os.path.exists(lnk_file)
        except ImportError:
            return False
        except Exception as e:
            print(f"[lnk] pywin32 shortcut creation failed: {e}")
            return False

    # ------------------------------------------------------------------
    # v3: Enhanced Chrome args with TLS ciphers and automation evasion
    # ------------------------------------------------------------------
    def _chrome_args_for_profile(self, profile_path, fingerprint, ext_dir):
        ua = fingerprint['user_agent'].replace('"', '')
        langs = fingerprint.get('languages', [fingerprint['language'], 'en'])
        accept_lang_parts = []
        for i, l in enumerate(langs):
            q = max(0.1, round(1.0 - 0.1 * i, 1))
            accept_lang_parts.append(l if i == 0 else f"{l};q={q}")
        accept_lang = ','.join(accept_lang_parts)
        color_scheme = fingerprint.get('color_scheme', 'light')

        # v3: Build cipher blacklist from the tail of the cipher order
        tls_ciphers = fingerprint.get('tls_cipher_order', [])
        cipher_blacklist = ''
        if tls_ciphers:
            cipher_blacklist = self.cipher_blacklist_flag(tls_ciphers)

        parts = [
            f'--user-data-dir="{profile_path}"',
            f'--user-agent="{ua}"',
            f'--lang={fingerprint["language"]}',
            f'--accept-lang="{accept_lang}"',
            f'--window-size={fingerprint["screen_resolution"]["width"]},{fingerprint["screen_resolution"]["height"]}',
            '--no-first-run',
            '--no-default-browser-check',
            # v3.2: ONE merged --disable-features (see DISABLED_FEATURES)
            f'--disable-features={self._disabled_features()}',
            f'--enable-features={self._enabled_features()}',
            '--disable-blink-features=AutomationControlled',
            '--password-store=basic',
            '--use-mock-keychain',
            '--disable-component-update',
            '--disable-domain-reliability',
            '--disable-background-networking',
            '--disable-sync',
            '--disable-breakpad',
            f'--force-color-profile={self.color_profile_flag(color_scheme)}',
            '--disable-ipc-flooding-protection',
            # v3: Additional automation evasion flags
            '--disable-renderer-backgrounding',
            '--disable-backgrounding-occluded-windows',
            '--disable-background-timer-throttling',
        ]
        if cipher_blacklist:
            parts.append(cipher_blacklist)
        # v3.2: fingerprint ext + user-script ext + extras, comma separated
        ext_dirs = self._collect_extension_dirs(profile_path, ext_dir)
        if ext_dirs and self._extensions_usable():
            parts.append('--load-extension="%s"' % ','.join(ext_dirs))
        return ' '.join(p for p in parts if p)

    def _make_lnk_via_powershell(self, lnk_file, target, arguments, working_dir, icon, description):
        if platform.system() != 'Windows':
            return False
        try:
            import base64
            def ps_quote(s):
                if s is None: return ''
                return s.replace("'", "''")

            ps_script = (
                "$ErrorActionPreference = 'Stop'; "
                "$WshShell = New-Object -ComObject WScript.Shell; "
                f"$s = $WshShell.CreateShortcut('{ps_quote(lnk_file)}'); "
                f"$s.TargetPath = '{ps_quote(target)}'; "
                f"$s.Arguments = '{ps_quote(arguments)}'; "
                f"$s.WorkingDirectory = '{ps_quote(working_dir)}'; "
                f"$s.IconLocation = '{ps_quote(icon)}'; "
                f"$s.Description = '{ps_quote(description)}'; "
                "$s.Save();"
            )
            encoded = base64.b64encode(ps_script.encode('utf-16-le')).decode('ascii')
            res = subprocess.run(
                ['powershell', '-NoProfile', '-NonInteractive',
                 '-ExecutionPolicy', 'Bypass', '-EncodedCommand', encoded],
                capture_output=True, text=True, timeout=20
            )
            if res.returncode != 0:
                err = (res.stderr or res.stdout or '').strip()[:300]
                if err:
                    print(f"[lnk] PowerShell error: {err}")
                return False
            return os.path.exists(lnk_file)
        except Exception as e:
            print(f"[lnk] PowerShell shortcut creation failed: {e}")
            return False

    def _create_macos_shortcut(self, name, chrome_exe, profile_path):
        try:
            script_file = os.path.join(self.desktop_dir, f"{name}.command")
            # v3.3: run the launcher when DevTools injection is on
            launcher = self._profile_launcher(name, profile_path)
            with open(script_file, 'w') as f:
                f.write('#!/bin/bash\n')
                if launcher:
                    f.write(f'"{sys.executable}" "{launcher}" &\n')
                else:
                    args = self._shortcut_arg_string(profile_path)
                    f.write(f'"{chrome_exe}" {args} &\n')
            os.chmod(script_file, 0o755)
            return True
        except Exception as e:
            print(f"Error creating macOS shortcut: {e}")
            return False

    def _create_linux_shortcut(self, name, chrome_exe, profile_path, profile_icon=None):
        try:
            desktop_file = os.path.join(self.desktop_dir, f"{name}.desktop")
            chosen_icon = profile_icon or self.icon_path
            icon_line = 'Icon=google-chrome\n'
            if chosen_icon and os.path.exists(chosen_icon):
                icon_line = f'Icon={chosen_icon}\n'
            # v3.3: run the launcher when DevTools injection is on
            launcher = self._profile_launcher(name, profile_path)
            if launcher:
                exec_line = f'Exec="{sys.executable}" "{launcher}"\n'
            else:
                exec_line = f'Exec="{chrome_exe}" {self._shortcut_arg_string(profile_path)}\n'
            with open(desktop_file, 'w') as f:
                f.write('[Desktop Entry]\n')
                f.write('Version=1.0\n')
                f.write('Type=Application\n')
                f.write(f'Name={name}\n')
                f.write(exec_line)
                f.write(icon_line)
                f.write('Terminal=false\n')
                f.write('Categories=Network;WebBrowser;\n')
            os.chmod(desktop_file, 0o755)
            return True
        except Exception as e:
            print(f"Error creating Linux shortcut: {e}")
            return False

    # ------------------------------------------------------------------
    # Profile creation (uses v3 enhanced fingerprint)
    # ------------------------------------------------------------------
    def create_profile(self, profile_name=None, create_shortcut=True):
        if profile_name is None:
            profile_name = f"Profile_{self._generate_random_id()}"

        profile_path = os.path.join(self.profiles_dir, profile_name)
        if os.path.exists(profile_path):
            raise ValueError(f"Profile '{profile_name}' already exists")

        os.makedirs(profile_path, exist_ok=True)

        # Generate v3 enhanced fingerprint
        fingerprint = self._generate_fingerprint()
        # v3.1: clamp to the language / resolution pools selected in the GUI
        fingerprint = self._enforce_selection(fingerprint)

        with open(os.path.join(profile_path, '_fingerprint.json'), 'w', encoding='utf-8') as f:
            json.dump(fingerprint, f, indent=2)

        preferences = self._create_preferences(fingerprint)
        prefs_path = os.path.join(profile_path, 'Preferences')
        with open(prefs_path, 'w', encoding='utf-8') as f:
            json.dump(preferences, f, indent=2)

        local_state = self._create_local_state(profile_name)
        local_state_path = os.path.join(profile_path, 'Local State')
        with open(local_state_path, 'w', encoding='utf-8') as f:
            json.dump(local_state, f, indent=2)

        first_run_path = os.path.join(profile_path, 'First Run')
        Path(first_run_path).touch()

        subdirs = ['Cache', 'Code Cache', 'GPUCache', 'Service Worker', 'Session Storage']
        for subdir in subdirs:
            os.makedirs(os.path.join(profile_path, subdir), exist_ok=True)

        self._build_fingerprint_extension(profile_path, fingerprint)
        # v3.2: compile the shared user scripts into this new profile
        self._build_userscript_extension(profile_path)
        # v3.3: and the extension-free DevTools injector
        self._build_cdp_injector(profile_path)
        cookie_summary = self._seed_profile_cookies(profile_path, fingerprint)
        self._seed_profile_history(profile_path, cookie_summary)

        shortcut_created = False
        if create_shortcut:
            shortcut_created = self.create_desktop_shortcut(profile_name, profile_path)

        return {
            'profile_name': profile_name,
            'profile_path': profile_path,
            'fingerprint': fingerprint,
            'created_at': datetime.now().isoformat(),
            'shortcut_created': shortcut_created
        }

    def _create_preferences(self, fingerprint):
        preferences = {
            "profile": {
                "name": f"User_{self._generate_random_id()}",
                "managed_user_id": "",
                "content_settings": {
                    "exceptions": {}
                }
            },
            "browser": {
                "check_default_browser": False,
                "has_seen_welcome_page": True,
                "show_home_button": True
            },
            "session": {
                "restore_on_startup": 1
            },
            "translate": {
                "enabled": False
            },
            "safebrowsing": {
                "enabled": True,
                "enhanced": False
            },
            "autofill": {
                "enabled": True
            },
            "password_manager": {
                "auto_sign_in": False
            },
            "download": {
                "prompt_for_download": False
            },
            "extensions": {
                "ui": {
                    "developer_mode": False
                }
            },
            "intl": {
                "accept_languages": fingerprint['language']
            },
            "webkit": {
                "webprefs": {
                    "default_font_size": 16,
                    "default_fixed_font_size": 13,
                    "minimum_font_size": 0
                }
            }
        }
        return preferences

    def _create_local_state(self, profile_name):
        local_state = {
            "profile": {
                "info_cache": {
                    profile_name: {
                        "name": profile_name,
                        "user_name": f"User_{self._generate_random_id()}",
                        "is_using_default_name": False,
                        "background_apps": False
                    }
                },
                "last_used": profile_name,
                "last_active_profiles": [profile_name],
                "metrics": {
                    "next_id": 1
                }
            },
            "browser": {
                "enabled_labs_experiments": []
            }
        }
        return local_state

    def get_all_profiles(self):
        profiles = []
        if os.path.exists(self.profiles_dir):
            for item in os.listdir(self.profiles_dir):
                item_path = os.path.join(self.profiles_dir, item)
                if item.startswith('_'):
                    continue
                if os.path.isdir(item_path):
                    prefs_path = os.path.join(item_path, 'Preferences')
                    if os.path.exists(prefs_path):
                        profiles.append({
                            'name': item,
                            'path': item_path,
                            'created': datetime.fromtimestamp(
                                os.path.getctime(item_path)
                            ).strftime('%Y-%m-%d %H:%M:%S')
                        })
        return profiles

    def delete_profile(self, profile_name):
        profile_path = os.path.join(self.profiles_dir, profile_name)
        if not self._assert_own_profile(profile_path, 'DELETE'):
            return False
        if os.path.exists(profile_path):
            shutil.rmtree(profile_path)
            self._delete_desktop_shortcut(profile_name)
            self._release_unique_icon(profile_name)
            try:
                theme_name = self._pick_color_for_profile(profile_name)[0]
                icon_variant = os.path.join(self.icons_cache_dir, f"{profile_name}_{theme_name}.ico")
                if os.path.exists(icon_variant):
                    os.remove(icon_variant)
            except Exception:
                pass
            return True
        return False

    def _delete_desktop_shortcut(self, profile_name):
        system = platform.system()
        shortcut_names = [profile_name, f"Chrome - {profile_name}"]
        extensions = []
        if system == 'Windows':
            extensions = ['.bat', '.lnk', '.vbs']
        elif system == 'Darwin':
            extensions = ['.command', '.app']
        else:
            extensions = ['.desktop']
        for shortcut_name in shortcut_names:
            for ext in extensions:
                shortcut_path = os.path.join(self.desktop_dir, f"{shortcut_name}{ext}")
                if os.path.exists(shortcut_path):
                    try:
                        if os.path.isdir(shortcut_path):
                            shutil.rmtree(shortcut_path)
                        else:
                            os.remove(shortcut_path)
                    except Exception:
                        pass

    def get_launch_command(self, profile_name):
        profile_path = os.path.join(self.profiles_dir, profile_name)
        chrome_exe = self._find_chrome_path()
        if chrome_exe:
            return f'"{chrome_exe}" --user-data-dir="{profile_path}"'
        else:
            return f'chrome --user-data-dir="{profile_path}"'

    # ==================================================================
    # v4.7: memory guard
    #
    # Every generated profile is a whole extra Chrome. Enough of them and
    # Windows hits its commit limit, and the first thing it refuses is a
    # new renderer process - in ANY Chrome, including the user's own. That
    # shows up as a sad-face tab on a blank page with no crash dump,
    # because a denied process never crashed.
    #
    # This keeps a slice of commit reserved for the user's own browsing.
    # Nothing here touches the default Chrome; it only limits what the
    # tool itself starts.
    # ==================================================================
    MEM_RESERVE_DEFAULT = 1536      # MB of commit kept free for the user
    MEM_PROFILE_COST_DEFAULT = 450  # MB assumed per profile until measured
    MEM_WARN_PCT = 80               # commit % that earns a warning
    MEM_SAMPLE_DELAY = 12.0         # seconds to wait before costing a launch

    @staticmethod
    def _memory_snapshot():
        """Physical and commit memory in MB, or None.

        Windows: GlobalMemoryStatusEx. ullTotalPageFile is the commit
        LIMIT (RAM + page file) and ullAvailPageFile is what is left of
        it - the number that actually decides whether a new process can
        be created. Costs microseconds, so it is safe to poll.
        """
        try:
            if os.name == 'nt':
                import ctypes

                class _MemStatusEx(ctypes.Structure):
                    _fields_ = [('dwLength', ctypes.c_ulong),
                                ('dwMemoryLoad', ctypes.c_ulong),
                                ('ullTotalPhys', ctypes.c_ulonglong),
                                ('ullAvailPhys', ctypes.c_ulonglong),
                                ('ullTotalPageFile', ctypes.c_ulonglong),
                                ('ullAvailPageFile', ctypes.c_ulonglong),
                                ('ullTotalVirtual', ctypes.c_ulonglong),
                                ('ullAvailVirtual', ctypes.c_ulonglong),
                                ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]

                status = _MemStatusEx()
                status.dwLength = ctypes.sizeof(_MemStatusEx)
                if not ctypes.windll.kernel32.GlobalMemoryStatusEx(
                        ctypes.byref(status)):
                    return None
                mb = 1024.0 * 1024.0
                return {'total_mb': int(status.ullTotalPhys / mb),
                        'avail_mb': int(status.ullAvailPhys / mb),
                        'commit_limit_mb': int(status.ullTotalPageFile / mb),
                        'commit_avail_mb': int(status.ullAvailPageFile / mb)}

            info = {}
            with open('/proc/meminfo', 'r') as handle:
                for line in handle:
                    bits = line.split(':')
                    if len(bits) == 2:
                        try:
                            info[bits[0].strip()] = int(bits[1].split()[0])
                        except (ValueError, IndexError):
                            pass
            total = info.get('MemTotal', 0) // 1024
            avail = info.get('MemAvailable', info.get('MemFree', 0)) // 1024
            limit = info.get('CommitLimit', total * 2) // 1024
            used = info.get('Committed_AS', 0) // 1024
            return {'total_mb': total, 'avail_mb': avail,
                    'commit_limit_mb': limit,
                    'commit_avail_mb': max(0, limit - used)}
        except Exception:
            return None

    # ------------------------------------------------------------------
    # settings
    # ------------------------------------------------------------------
    def memory_guard_enabled(self):
        try:
            return bool(self._load_userscript_registry()['settings']
                        .get('memory_guard', True))
        except Exception:
            return True

    def set_memory_guard_enabled(self, value):
        reg = self._load_userscript_registry()
        reg['settings']['memory_guard'] = bool(value)
        self._save_userscript_registry(reg)

    def memory_reserve_mb(self):
        """Commit held back so the user's own Chrome keeps working.

        With nothing configured this scales to the machine. A flat 1.5 GB
        would block every launch on a 4 GB box, so the default is a fifth
        of the commit limit, clamped to a sane range.
        """
        try:
            stored = self._load_userscript_registry()['settings'].get(
                'memory_reserve_mb')
        except Exception:
            stored = None
        if stored is not None:
            try:
                return max(256, min(int(stored), 16384))
            except Exception:
                pass
        snap = self._memory_snapshot()
        if snap and snap.get('commit_limit_mb'):
            return int(max(512, min(self.MEM_RESERVE_DEFAULT,
                                    snap['commit_limit_mb'] * 0.20)))
        return self.MEM_RESERVE_DEFAULT

    def set_memory_reserve_mb(self, megabytes):
        try:
            value = max(256, min(int(megabytes), 16384))
        except Exception:
            value = self.MEM_RESERVE_DEFAULT
        reg = self._load_userscript_registry()
        reg['settings']['memory_reserve_mb'] = value
        self._save_userscript_registry(reg)

    def memory_autoclose(self):
        """Close the newest generated profile when commit runs out."""
        try:
            return bool(self._load_userscript_registry()['settings']
                        .get('memory_autoclose', False))
        except Exception:
            return False

    def set_memory_autoclose(self, value):
        reg = self._load_userscript_registry()
        reg['settings']['memory_autoclose'] = bool(value)
        self._save_userscript_registry(reg)

    def profile_cost_estimate(self):
        """Measured MB a generated profile costs, or the default."""
        try:
            value = int(self._load_userscript_registry()['settings']
                        .get('profile_cost_mb', self.MEM_PROFILE_COST_DEFAULT))
        except Exception:
            value = self.MEM_PROFILE_COST_DEFAULT
        return max(120, min(value, 4096))

    def _record_profile_cost(self, megabytes):
        """Roll the measured cost into a running average."""
        try:
            cost = int(megabytes)
        except Exception:
            return
        if cost < 120 or cost > 4096:
            return          # a background process moved, not our launch
        blended = int(0.7 * self.profile_cost_estimate() + 0.3 * cost)
        try:
            reg = self._load_userscript_registry()
            reg['settings']['profile_cost_mb'] = blended
            self._save_userscript_registry(reg)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # the picture
    # ------------------------------------------------------------------
    def memory_status(self):
        """Snapshot plus what it means for opening more profiles."""
        snap = self._memory_snapshot()
        if not snap:
            return None
        limit = max(1, snap['commit_limit_mb'])
        snap['commit_used_mb'] = limit - snap['commit_avail_mb']
        snap['commit_pct'] = round(100.0 * snap['commit_used_mb'] / limit, 1)
        # a commit limit barely above RAM means little or no page file
        snap['pagefile_small'] = (
            snap['commit_limit_mb'] < snap['total_mb'] * 1.15)
        snap['profile_cost_mb'] = self.profile_cost_estimate()
        snap['reserve_mb'] = self.memory_reserve_mb()
        snap['room_for_profiles'] = max(0, int(
            (snap['commit_avail_mb'] - snap['reserve_mb'])
            / max(1, snap['profile_cost_mb'])))
        return snap

    def memory_precheck(self):
        """(ok, level, message) before starting another profile.

        level is 'ok', 'warn' or 'block'.
        """
        if not self.memory_guard_enabled():
            return True, 'ok', ''
        snap = self.memory_status()
        if not snap:
            return True, 'ok', ''

        needed = snap['profile_cost_mb'] + snap['reserve_mb']
        if snap['commit_avail_mb'] < needed:
            lines = [
                "Not enough memory to open another profile safely.",
                "",
                "free commit      : %d MB" % snap['commit_avail_mb'],
                "this profile needs about %d MB" % snap['profile_cost_mb'],
                "reserved for your own Chrome: %d MB" % snap['reserve_mb'],
                "",
                "Opening it now would push Windows past its commit limit.",
                "Windows would then refuse new renderer processes, and your",
                "own Chrome would start showing blank tabs with a sad face.",
                "",
                "Close a profile or two and try again.",
            ]
            if snap['pagefile_small']:
                lines += [
                    "",
                    "Your commit limit (%d MB) is barely above your RAM"
                    % snap['commit_limit_mb'],
                    "(%d MB), so the page file is off or very small."
                    % snap['total_mb'],
                    "Turning it back on would raise this ceiling a lot:",
                    "  sysdm.cpl > Advanced > Performance Settings >",
                    "  Advanced > Virtual memory > Change >",
                    "  tick 'Automatically manage', then reboot.",
                ]
            return False, 'block', '\n'.join(lines)

        if snap['commit_pct'] >= self.MEM_WARN_PCT:
            return True, 'warn', (
                "Memory is tight: %.0f%% of the commit limit is in use and "
                "there is room for about %d more profile(s)."
                % (snap['commit_pct'], snap['room_for_profiles']))
        return True, 'ok', ''

    # ------------------------------------------------------------------
    # alerts
    # ------------------------------------------------------------------
    def set_memory_alert_handler(self, handler):
        """handler(level, message). Called from a BACKGROUND thread.

        From Tkinter, marshal it back to the UI thread:
            gen.set_memory_alert_handler(
                lambda lvl, msg: root.after(0, show_it, lvl, msg))
        """
        self._mem_handler = handler

    def pending_memory_alert(self):
        """Newest unread alert as (level, message), or None. Poll-friendly."""
        alert = getattr(self, '_mem_pending', None)
        self._mem_pending = None
        return alert

    def _memory_alert(self, level, message):
        self._mem_pending = (level, message)
        try:
            path = os.path.join(self.profiles_dir, '_memory_guard.log')
            with open(path, 'a', encoding='utf-8') as handle:
                handle.write('%s  [%s] %s\n' % (
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    level, message.replace('\n', ' | ')))
        except Exception:
            pass
        handler = getattr(self, '_mem_handler', None)
        if handler:
            try:
                handler(level, message)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # closing a profile the tool started (never the user's own Chrome)
    # ------------------------------------------------------------------
    def close_profile(self, profile_name, profile_path=None):
        """Kill the browser for one generated profile, children included.

        Matched on --user-data-dir, so only a profile inside profiles_dir
        can ever be hit. The user's own Chrome has no such flag.
        """
        if profile_path is None:
            profile_path = os.path.join(self.profiles_dir, profile_name)
        needle = os.path.normcase(os.path.abspath(profile_path))
        root = os.path.normcase(os.path.abspath(self.profiles_dir))
        if not needle.startswith(root):
            raise RuntimeError('refusing to close something outside %s'
                               % self.profiles_dir)
        killed = 0
        try:
            if os.name == 'nt':
                script = ("Get-CimInstance Win32_Process -Filter "
                          "\"Name='chrome.exe'\" | ForEach-Object "
                          "{ \"$($_.ProcessId)`t$($_.CommandLine)\" }")
                out = subprocess.check_output(
                    ['powershell', '-NoProfile', '-Command', script],
                    stderr=subprocess.DEVNULL, timeout=25,
                    creationflags=0x08000000).decode('utf-8', 'ignore')
                for line in out.splitlines():
                    if '\t' not in line:
                        continue
                    pid, _, cmd = line.partition('\t')
                    if needle in os.path.normcase(cmd):
                        subprocess.call(
                            ['taskkill', '/F', '/T', '/PID', pid.strip()],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=0x08000000)
                        killed += 1
            else:
                import signal
                out = subprocess.check_output(
                    ['ps', 'ax', '-o', 'pid=,command='],
                    stderr=subprocess.DEVNULL, timeout=25
                ).decode('utf-8', 'ignore')
                for line in out.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        pid_text, cmd = line.split(None, 1)
                        pid_num = int(pid_text)
                    except (ValueError, IndexError):
                        continue
                    if needle in os.path.normcase(cmd):
                        try:
                            os.kill(pid_num, signal.SIGTERM)
                            killed += 1
                        except Exception:
                            pass
        except Exception:
            pass
        return killed

    def _note_launch(self, profile_name, profile_path):
        history = getattr(self, '_mem_launched', None)
        if history is None:
            history = []
            self._mem_launched = history
        history.append((time.time(), profile_name, profile_path))
        del history[:-64]

    def _close_newest_profile(self):
        """Last resort for the watchdog. Returns the name closed, or ''."""
        history = getattr(self, '_mem_launched', None) or []
        while history:
            _when, name, path = history.pop()
            try:
                if not self.profile_is_running(path)['alive']:
                    continue
            except Exception:
                pass
            if self.close_profile(name, path):
                return name
        return ''

    # ------------------------------------------------------------------
    # watchdog
    # ------------------------------------------------------------------
    def start_memory_watchdog(self, interval=6.0):
        """Start the background sampler once. Safe to call repeatedly."""
        if not self.memory_guard_enabled():
            return
        thread = getattr(self, '_mem_thread', None)
        if thread is not None and thread.is_alive():
            return
        import threading
        self._mem_stop = threading.Event()
        self._mem_last_level = 'ok'

        def loop():
            stop = self._mem_stop
            while not stop.is_set():
                try:
                    self._watchdog_tick()
                except Exception:
                    pass
                stop.wait(interval)

        thread = threading.Thread(target=loop, name='memory-guard')
        thread.daemon = True
        self._mem_thread = thread
        thread.start()

    def stop_memory_watchdog(self):
        stop = getattr(self, '_mem_stop', None)
        if stop is not None:
            stop.set()

    def _watchdog_tick(self):
        snap = self.memory_status()
        if not snap:
            return
        previous = getattr(self, '_mem_last_level', 'ok')

        if snap['commit_avail_mb'] < snap['reserve_mb']:
            level = 'critical'
        elif snap['commit_pct'] >= self.MEM_WARN_PCT:
            level = 'warn'
        else:
            level = 'ok'
        self._mem_last_level = level

        if level == 'ok':
            return
        if level == previous:
            return              # already told them, do not spam

        if level == 'critical':
            message = ("Memory critical: only %d MB of commit left, below the "
                       "%d MB reserved for your own browsing. Close a profile "
                       "or your normal Chrome will start showing blank tabs."
                       % (snap['commit_avail_mb'], snap['reserve_mb']))
            if self.memory_autoclose():
                closed = self._close_newest_profile()
                if closed:
                    message += "  Closed '%s' to free memory." % closed
            self._memory_alert('critical', message)
        else:
            self._memory_alert('warn',
                               "Memory tight: %.0f%% of the commit limit used, "
                               "room for about %d more profile(s)."
                               % (snap['commit_pct'], snap['room_for_profiles']))

    def _schedule_cost_sample(self, before):
        """Measure what a launch actually cost, once Chrome has settled."""
        if not before:
            return
        import threading

        def sample():
            after = self._memory_snapshot()
            if after:
                self._record_profile_cost(
                    before['commit_avail_mb'] - after['commit_avail_mb'])

        timer = threading.Timer(self.MEM_SAMPLE_DELAY, sample)
        timer.daemon = True
        timer.start()

    # ------------------------------------------------------------------
    # the report, so the standalone script is no longer needed
    # ------------------------------------------------------------------
    def memory_report(self):
        """Everything check_chrome_resources.py printed, as one string."""
        snap = self.memory_status()
        if not snap:
            return 'Memory information is not available on this system.'
        bar = '-' * 58
        out = [bar, 'Memory guard', bar,
               'physical RAM      : %d MB' % snap['total_mb'],
               'free physical RAM : %d MB' % snap['avail_mb'],
               'commit limit      : %d MB' % snap['commit_limit_mb'],
               'commit in use     : %d MB (%.0f%%)' % (snap['commit_used_mb'],
                                                       snap['commit_pct']),
               'commit free       : %d MB' % snap['commit_avail_mb'],
               '',
               'reserved for you  : %d MB' % snap['reserve_mb'],
               'cost per profile  : %d MB%s' % (
                   snap['profile_cost_mb'],
                   ' (measured)' if snap['profile_cost_mb']
                   != self.MEM_PROFILE_COST_DEFAULT else ' (estimate)'),
               'room for          : about %d more profile(s)'
               % snap['room_for_profiles'],
               '',
               'guard             : %s' % (
                   'on' if self.memory_guard_enabled() else 'OFF'),
               'auto-close        : %s' % (
                   'on' if self.memory_autoclose() else 'off'),
               bar]

        if snap['pagefile_small']:
            out += [
                'PAGE FILE',
                '  Commit limit %d MB vs %d MB of RAM - the page file is'
                % (snap['commit_limit_mb'], snap['total_mb']),
                '  off or very small. That is what caps how many profiles',
                '  you can open before Windows starts refusing renderers.',
                '',
                '  sysdm.cpl > Advanced > Performance Settings > Advanced',
                '  > Virtual memory > Change > tick "Automatically manage"',
                '  then reboot.',
                bar]

        if snap['commit_pct'] >= 90:
            out += ['Commit is nearly exhausted. Close some profiles now.', bar]
        elif snap['room_for_profiles'] == 0:
            out += ['No headroom for another profile.', bar]
        return '\n'.join(out)

    def save_memory_report(self, path=None):
        if path is None:
            path = os.path.join(self.profiles_dir, 'memory_report.txt')
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(self.memory_report())
        return path



# ----------------------------------------------------------------------
# v4.7: put the memory guard in front of launch_profile.
#
# The original method is captured below and called unchanged - nothing in
# ChromeProfileGenerator.launch_profile is edited or removed. Set
# gen.set_memory_guard_enabled(False) to go back to the old behaviour.
# ----------------------------------------------------------------------
_unguarded_launch_profile = ChromeProfileGenerator.launch_profile


def _guarded_launch_profile(self, profile_name, profile_path=None, url=None):
    # v6.2: a switched-off application is reported before anything else
    client = self.license() if hasattr(self, 'license') else None
    if client is not None and not client.app_allowed():
        raise AppDisabledError(client.blocked_reason())
    ok, level, message = self.memory_precheck()
    if not ok:
        # refuse BEFORE spending the memory, so the user's own Chrome keeps
        # the renderers it needs
        raise RuntimeError(message)
    if level == 'warn':
        self._memory_alert('warn', message)

    before = self._memory_snapshot()
    result = _unguarded_launch_profile(self, profile_name, profile_path, url)

    if profile_path is None:
        profile_path = os.path.join(self.profiles_dir, profile_name)
    try:
        self._note_launch(profile_name, profile_path)
        self._schedule_cost_sample(before)
        self.start_memory_watchdog()
    except Exception:
        pass
    return result


_guarded_launch_profile.__doc__ = _unguarded_launch_profile.__doc__
_guarded_launch_profile.__name__ = 'launch_profile'
ChromeProfileGenerator.launch_profile = _guarded_launch_profile

# ----------------------------------------------------------------------
# v4.4: iOS-style on/off switch used everywhere instead of check boxes
# ----------------------------------------------------------------------
class ToggleSwitch(tk.Canvas):
    """A small rounded on/off switch backed by a tk.BooleanVar.

    Green with the knob on the right when ON, grey with the knob on the
    left when OFF, mirroring the reference switch art. Clicking it (or its
    label) flips the variable and fires the optional command.
    """

    def __init__(self, master, variable=None, command=None,
                 width=48, height=26, bg=None,
                 on_color="#22c55e", off_color="#8794a6",
                 knob_color="#ffffff", locked_command=None, **kw):
        try:
            bg = bg or master.cget('bg')
        except Exception:
            bg = bg or "#0d2347"
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bd=0, bg=bg, **kw)
        self._var = variable if variable is not None else tk.BooleanVar(value=False)
        self._command = command
        # v6.2.1: what to do when a DISABLED switch is clicked. Default None
        # keeps the original behaviour exactly (the click is ignored).
        self._locked_command = locked_command
        self._sw = int(width)
        self._sh = int(height)
        self._on_color = on_color
        self._off_color = off_color
        self._knob_color = knob_color
        self._enabled = True
        self.bind('<Button-1>', self._on_click)
        try:
            self._trace = self._var.trace_add('write', lambda *a: self._redraw())
        except Exception:
            try:
                self._var.trace('w', lambda *a: self._redraw())
            except Exception:
                pass
        self._redraw()

    def _pill(self, x0, y0, x1, y1, r, fill):
        self.create_oval(x0, y0, x0 + 2 * r, y1, fill=fill, outline=fill)
        self.create_oval(x1 - 2 * r, y0, x1, y1, fill=fill, outline=fill)
        self.create_rectangle(x0 + r, y0, x1 - r, y1, fill=fill, outline=fill)

    def _redraw(self):
        try:
            self.delete('all')
        except Exception:
            return
        on = bool(self._var.get())
        pad = 2
        r = (self._sh - 2 * pad) // 2
        track = self._on_color if on else self._off_color
        if not self._enabled:
            track = "#5a6470"
        self._pill(pad, pad, self._sw - pad, self._sh - pad, r, track)
        kd = self._sh - 2 * pad - 4
        ky = pad + 2
        if on:
            kx = self._sw - pad - 2 - kd
        else:
            kx = pad + 2
        # soft drop shadow then the white knob
        self.create_oval(kx + 1, ky + 2, kx + kd + 1, ky + kd + 2,
                         fill="#6b7280", outline="")
        self.create_oval(kx, ky, kx + kd, ky + kd,
                         fill=self._knob_color, outline="#d0d5dd")

    def _on_click(self, event=None):
        if not self._enabled:
            # v6.2.1: a locked switch used to swallow the click silently, so a
            # Free user clicking a paid-only option got no answer at all. Say
            # why instead. The switch itself still does NOT change state, so
            # this stays non-destructive.
            if self._locked_command:
                try:
                    self._locked_command()
                except Exception:
                    pass
            return
        try:
            self._var.set(not bool(self._var.get()))
        except Exception:
            return
        self._redraw()
        if self._command:
            try:
                self._command()
            except Exception:
                pass

    def set_locked_command(self, fn):
        """v6.2.1: set (or clear) what happens when this switch is clicked
        while locked. Safe to call at any time."""
        self._locked_command = fn

    def set_enabled(self, flag):
        self._enabled = bool(flag)
        try:
            self.configure(cursor='' if flag else 'arrow')
        except Exception:
            pass
        self._redraw()


class LabeledSwitch(tk.Frame):
    """A ToggleSwitch with a caption to its right; a drop-in for a check box."""

    def __init__(self, master, text='', variable=None, command=None,
                 bg=None, fg="#e8f0ff", font=('Segoe UI', 9),
                 on_color="#22c55e", off_color="#8794a6",
                 switch_width=48, switch_height=26, gap=8,
                 locked_command=None, **kw):
        try:
            bg = bg or master.cget('bg')
        except Exception:
            bg = bg or "#0d2347"
        super().__init__(master, bg=bg, **kw)
        self.var = variable if variable is not None else tk.BooleanVar(value=False)
        self.switch = ToggleSwitch(self, variable=self.var, command=command,
                                   bg=bg, on_color=on_color, off_color=off_color,
                                   width=switch_width, height=switch_height,
                                   locked_command=locked_command)
        self.switch.pack(side=tk.LEFT)
        self.label = None
        if text:
            self.label = tk.Label(self, text=text, bg=bg, fg=fg, font=font)
            self.label.pack(side=tk.LEFT, padx=(gap, 0))
            self.label.bind('<Button-1>', lambda e: self.switch._on_click())

    def set_enabled(self, flag):
        self.switch.set_enabled(flag)

    def set_locked_command(self, fn):
        """v6.2.1: forwarded to the inner switch, so clicking either the
        switch or its caption while locked gives the same answer."""
        self.switch.set_locked_command(fn)


# ----------------------------------------------------------------------
# GUI: Modern dark-themed interface for profile management
# ----------------------------------------------------------------------
class ChromeProfileGeneratorGUI:
    """GUI for Chrome Profile Generator v3"""

    BG        = "#1e1f24"
    BG_CARD   = "#272930"
    BG_CARD_2 = "#2f323a"
    FG        = "#e6e6e6"
    FG_MUTED  = "#9aa0a6"
    ACCENT    = "#4f8cff"
    ACCENT_HV = "#3b78ee"
    DANGER    = "#e85d5d"
    DANGER_HV = "#c94747"
    OK        = "#3ecf8e"
    BORDER    = "#3a3d46"

    def __init__(self, root):
        self.root = root
        self.root.title("Chrome Profile Generator")
        self.root.geometry("1060x680")
        self.root.minsize(960, 600)
        self.root.configure(bg=self.BG)
        # v7.0.0 (bug fix): the two lines above are kept exactly as they were
        # so nothing that reads them changes, and then re-applied for the
        # real screen and DPI. On a 1366x768 display at 150% scaling the
        # literal 960x600 minimum is larger than the workspace, which is how
        # the Generate button ended up off-screen with no way to resize back.
        self._dpi_scale = 1.0
        try:
            self._measure_dpi()
            self._apply_adaptive_geometry()
        except Exception:
            pass                       # keep the original geometry on failure

        self.generator = ChromeProfileGenerator()
        # v7.0.1: always initialize the remote-tab host attribute before any
        # widget/theme rebuild can inspect it. This is additive and does not
        # change the existing Profiles / Invite / USA Timer behaviour.
        self.tab_host = None
        self.theme_name = self._load_theme_name()
        try:
            # heal profiles an earlier build pinned to Firefox
            self.generator.purge_firefox_bindings()
            self.generator.reconcile_browser_kind()
        except Exception:
            pass
        if self.generator.icon_path:
            try:
                self.root.iconbitmap(self.generator.icon_path)
            except Exception:
                pass

        self._configure_style()
        self._create_widgets()
        self._refresh_profiles()
        # v6.2: reflect the current plan (theme, badge, feature locks) and start
        # the background check-in. Free is fully usable from the first launch;
        # there is no activation gate and no trial popup.
        try:
            self._build_license_buttons()
            self._refresh_license_banner()
            self._apply_plan_theme()
            self._sync_feature_locks()
            client = self.generator.license()
            if client is not None:
                client.start_background()
                # after the first check-in the plan/theme/locks may change
                # (e.g. a paid licence validated, or the app turned off)
                self.root.after(2500, self._on_plan_maybe_changed)
                # watch for a remote block or a mandatory update; both arrive
                # on the signed check-in and are polled so a dashboard change
                # reaches a running tool within a few minutes.
                self._app_control_shown = False
                self.root.after(1500, self._check_app_control)
                # v6.3: one referral check at launch. Runs on a worker
                # thread and shows at most one popup; silent when offline.
                self.root.after(3500, self._referral_launch_check)
        except Exception:
            pass
        # v7.0.0: server-defined tabs. Built from the cache immediately so the
        # tab strip is complete at once, then refreshed in the background.
        # Wrapped twice over: a failure here can never stop the tool.
        try:
            self._build_remote_tabs()
        except Exception as exc:
            self.tab_host = None
            try:
                self.log('[tabs] could not start: %r' % (exc,))
            except Exception:
                pass
        try:
            self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        except Exception:
            pass

    def _refresh_plan_ui(self):
        """Re-apply the plan badge, theme and feature locks once."""
        try:
            self._build_license_buttons()
            self._refresh_license_banner()
            self._apply_plan_theme()
            self._sync_feature_locks()
        except Exception:
            pass

    def _on_plan_maybe_changed(self):
        """Track the server: refresh the plan UI, keep existing profiles'
        scripts in step with the plan and the switch, and poll again."""
        self._refresh_plan_ui()
        # v6.3.3: add or drop the USA Timer tab when the plan changes,
        # with no restart
        try:
            self._sync_timer_tab()
        except Exception:
            pass
        # v7.0.0: a plan change unlocks or re-locks server-defined tabs, so
        # ask the server again. Cheap (one request), silent when offline, and
        # it means an upgrade takes effect without restarting the tool.
        try:
            host = getattr(self, 'tab_host', None)
            if host is not None:
                host.refresh_async()
        except Exception:
            pass
        try:
            self._maybe_resync_profiles()
        except Exception:
            pass
        try:
            self.root.after(15000, self._on_plan_maybe_changed)
        except Exception:
            pass

    def _script_signature(self):
        """What the profiles should currently contain, as plain JSON data."""
        client = self.generator.license() if hasattr(self.generator, 'license') else None
        if client is None:
            return None
        try:
            scripts = sorted([str(s.get('slug', '')), int(s.get('version', 0) or 0)]
                             for s in client.get_scripts())
            return {'on': bool(client.app_allowed()), 'plan': client.current_plan(),
                    'scripts': scripts}
        except Exception:
            return None

    def _maybe_resync_profiles(self):
        """Rebuild every profile's injected scripts when the effective set
        changes - a plan change, a new script version, or the master switch.

        Profiles keep their script payload on disk, so without this a profile
        opened later could still carry Script 2 after a downgrade, an old
        script version, or scripts while the application is switched off.
        The last synced state is remembered next to the profiles, so a change
        that happened while the tool was closed is caught at the next start.
        """
        if getattr(self, '_resync_running', False):
            return
        sig = self._script_signature()
        if sig is None:
            return
        marker = os.path.join(self.generator.profiles_dir, '_script_sync.json')
        try:
            with open(marker, 'r', encoding='utf-8') as handle:
                last = json.load(handle)
        except Exception:
            last = None
        if last == sig:
            return
        try:
            profiles = list(self.generator.get_all_profiles())
        except Exception:
            profiles = []
        self._resync_running = True

        def work():
            done = 0
            try:
                for p in profiles:
                    try:
                        if self.generator.sync_userscripts_to_profile(p['path']):
                            done += 1
                    except Exception:
                        pass
                try:
                    os.makedirs(os.path.dirname(marker), exist_ok=True)
                    tmp = marker + '.tmp'
                    with open(tmp, 'w', encoding='utf-8') as handle:
                        json.dump(sig, handle)
                    os.replace(tmp, marker)
                except Exception:
                    pass
            finally:
                self._resync_last_count = done
                self._resync_running = False
        threading.Thread(target=work, daemon=True).start()

    # layout of the language / screen-size pickers
    BROWSER_TABS = ('All', 'Chrome', 'Edge', 'Brave', 'Firefox', 'Other')

    @property
    def tree(self):
        # whichever list is on screen, so Open / Delete act on what you see
        trees = getattr(self, 'browser_trees', None)
        if not trees:
            return getattr(self, '_fallback_tree', None)
        try:
            name = self.browser_tabs.tab(self.browser_tabs.select(), 'text')
            return trees.get(name.strip(), trees['All'])
        except Exception:
            return trees['All']

    @tree.setter
    def tree(self, value):
        self._fallback_tree = value

    LANG_COLS = 2
    RES_COLS = 2
    LANG_LABELS = {
        'en-US': 'English (US)', 'en-GB': 'English (UK)',
        'fr-FR': 'French', 'ar-SA': 'Arabic',
    }

    THEMES = {
        'dark': {
            'BG': '#0a1526', 'BG_CARD': '#111f38', 'BG_CARD_2': '#16294a',
            'BORDER': '#23406e', 'FG': '#e9f1ff', 'FG_MUTED': '#93a7c6',
            'ACCENT': '#2f74e0', 'ACCENT_2': '#2864c8', 'GREEN': '#2f9e54',
            'DANGER': '#e5534b', 'BANNER': '#12305c', 'HEADER': '#0c1d3a',
            'ENTRY': '#0d1d38', 'SELECT': '#2864c8',
        },
        'light': {
            'BG': '#eef2f7', 'BG_CARD': '#ffffff', 'BG_CARD_2': '#f5f8fc',
            'BORDER': '#cdd8e6', 'FG': '#0f2340', 'FG_MUTED': '#5a6b80',
            'ACCENT': '#1a5fb4', 'ACCENT_2': '#14508f', 'GREEN': '#2f9e54',
            'DANGER': '#d13d34', 'BANNER': '#16365e', 'HEADER': '#ffffff',
            'ENTRY': '#ffffff', 'SELECT': '#1a5fb4',
        },
    }

    def _load_theme_name(self):
        # v6.0: light is the default theme. A user who has picked dark before
        # keeps it (the saved preference wins); only the first-run default
        # changed from dark to light.
        try:
            return self.generator._load_userscript_registry()['settings'].get(
                'theme', 'light')
        except Exception:
            return 'light'

    def _save_theme_name(self, name):
        try:
            reg = self.generator._load_userscript_registry()
            reg['settings']['theme'] = name
            self.generator._save_userscript_registry(reg)
        except Exception:
            pass

    def _apply_palette(self):
        palette = self.THEMES.get(getattr(self, 'theme_name', 'dark'),
                                  self.THEMES['dark'])
        for key, value in palette.items():
            setattr(self, key, value)

    def _toggle_theme(self, name):
        if name == getattr(self, 'theme_name', 'dark'):
            return
        self.theme_name = name
        self._save_theme_name(name)
        self._apply_palette()
        for child in list(self.root.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        self._configure_style()
        self._create_widgets()
        self._refresh_profiles()

    def _show_about(self):
        messagebox.showinfo(
            "About",
            "Chrome Profile Generator  \u00b7  version "
            + (getattr(_license, 'APP_VERSION', '') if _license is not None else 'dev')
            + "\n\n"
            "Creates isolated Chrome profiles, each with its own fingerprint,\n"
            "icon and desktop shortcut, and injects your user scripts into\n"
            "every page they open.\n\n"
            "Scripts are delivered from your dashboard and injected at runtime,\n"
            "so they update centrally with nothing to reinstall.\n\n"
            "Languages: en-US, en-GB, fr-FR, ar-SA\n"
            "Screen sizes: 1920x1080, 1366x768, 1536x864, 1440x900,\n"
            "1280x720, 1600x900, 1280x1024")

    def _configure_style(self):
        self._apply_palette()
        self.root.configure(bg=self.BG)
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass

        style.configure('TFrame', background=self.BG)
        style.configure('Card.TFrame', background=self.BG_CARD)
        style.configure('TLabel', background=self.BG, foreground=self.FG,
                        font=('Segoe UI', 9))
        style.configure('Muted.TLabel', background=self.BG,
                        foreground=self.FG_MUTED, font=('Segoe UI', 8))
        style.configure('Card.TLabel', background=self.BG_CARD,
                        foreground=self.FG, font=('Segoe UI', 9))
        style.configure('CardMuted.TLabel', background=self.BG_CARD,
                        foreground=self.FG_MUTED, font=('Segoe UI', 8))
        style.configure('Title.TLabel', background=self.HEADER,
                        foreground=self.FG, font=('Segoe UI', 17, 'bold'))
        style.configure('Subtitle.TLabel', background=self.HEADER,
                        foreground=self.FG_MUTED, font=('Segoe UI', 8))
        style.configure('Section.TLabel', background=self.BG,
                        foreground=self.FG, font=('Segoe UI', 11))

        style.configure('TButton', background=self.BG_CARD_2,
                        foreground=self.FG, borderwidth=0, focusthickness=0,
                        padding=(12, 6), font=('Segoe UI', 9))
        style.map('TButton', background=[('active', self.BORDER)])
        style.configure('Accent.TButton', background=self.ACCENT,
                        foreground='#ffffff', font=('Segoe UI', 9, 'bold'),
                        padding=(14, 7), borderwidth=0)
        style.map('Accent.TButton', background=[('active', self.ACCENT_2)])
        style.configure('Go.TButton', background=self.GREEN,
                        foreground='#ffffff', font=('Segoe UI', 10, 'bold'),
                        padding=(12, 8), borderwidth=0)
        style.map('Go.TButton', background=[('active', self.ACCENT_2)])
        style.configure('Pick.TButton', background=self.ACCENT_2,
                        foreground='#ffffff', font=('Segoe UI', 10, 'bold'),
                        padding=(12, 8), borderwidth=0)
        style.map('Pick.TButton', background=[('active', self.ACCENT)])
        style.configure('Ghost.TButton', background=self.BG_CARD_2,
                        foreground=self.FG, borderwidth=0, padding=(10, 5))
        style.map('Ghost.TButton', background=[('active', self.BORDER)])
        style.configure('Mini.TButton', background=self.BG_CARD_2,
                        foreground=self.FG_MUTED, borderwidth=0,
                        padding=(8, 3), font=('Segoe UI', 8))
        style.map('Mini.TButton', background=[('active', self.BORDER)])
        style.configure('Danger.TButton', background=self.DANGER,
                        foreground='#ffffff', borderwidth=0, padding=(10, 5))
        style.configure('Icon.TButton', background=self.HEADER,
                        foreground=self.FG, borderwidth=0,
                        padding=(8, 4), font=('Segoe UI', 13))
        style.map('Icon.TButton', background=[('active', self.BORDER)])

        style.configure('TCheckbutton', background=self.BG_CARD,
                        foreground=self.FG, font=('Segoe UI', 9))
        style.map('TCheckbutton', background=[('active', self.BG_CARD)])
        style.configure('Pool.TCheckbutton', background=self.BG_CARD,
                        foreground=self.FG, font=('Segoe UI', 9))
        style.map('Pool.TCheckbutton', background=[('active', self.BG_CARD)])
        style.configure('TRadiobutton', background=self.BG_CARD,
                        foreground=self.FG, font=('Segoe UI', 9))
        style.map('TRadiobutton', background=[('active', self.BG_CARD)])

        style.configure('TEntry', fieldbackground=self.ENTRY,
                        foreground=self.FG, bordercolor=self.BORDER,
                        insertcolor=self.FG, borderwidth=1, padding=5)
        style.configure('TSpinbox', fieldbackground=self.ENTRY,
                        foreground=self.FG, bordercolor=self.BORDER,
                        arrowcolor=self.FG, borderwidth=1, padding=4)

        style.configure('Treeview', background=self.BG_CARD,
                        fieldbackground=self.BG_CARD, foreground=self.FG,
                        borderwidth=0, rowheight=24, font=('Segoe UI', 9))
        style.configure('Treeview.Heading', background=self.BG_CARD_2,
                        foreground=self.FG_MUTED, borderwidth=0,
                        font=('Segoe UI', 9, 'bold'))
        style.map('Treeview', background=[('selected', self.SELECT)],
                  foreground=[('selected', '#ffffff')])
        style.configure('Vertical.TScrollbar', background=self.BG_CARD_2,
                        troughcolor=self.BG, bordercolor=self.BG,
                        arrowcolor=self.FG_MUTED, borderwidth=0)

        style.configure('TLabelframe', background=self.BG_CARD,
                        bordercolor=self.BORDER)
        style.configure('TLabelframe.Label', background=self.BG_CARD,
                        foreground=self.FG, font=('Segoe UI', 9, 'bold'))

        style.configure('TNotebook', background=self.BG,
                        bordercolor=self.BORDER, tabmargins=(2, 4, 2, 0))
        style.configure('TNotebook.Tab', background=self.BG_CARD_2,
                        foreground=self.FG_MUTED, borderwidth=0,
                        padding=(18, 7), font=('Segoe UI', 9, 'bold'))
        style.map('TNotebook.Tab',
                  background=[('selected', self.BG_CARD), ('active', self.BORDER)],
                  foreground=[('selected', self.FG)])

    # ==================================================================
    # v6.2  licensing UI - Free is the baseline; paid plans add features
    # ==================================================================
    PLAN_TEXT = {'free': 'Free', 'pro': 'Pro', 'team': 'Unlimited for Team'}

    def _current_plan(self):
        client = self.generator.license() if hasattr(self.generator, 'license') else None
        if client is None:
            return 'pro'   # developer checkout without the licensing module
        try:
            return client.current_plan()
        except Exception:
            return 'free'

    def _build_license_buttons(self):
        """Header shows the current plan and, on Free, a clear Upgrade button.

        Nothing here blocks the tool: a Free user has full Free features and
        an obvious, non-blocking way to upgrade or register a key.
        """
        frame = getattr(self, '_license_btns', None)
        if frame is None:
            return
        for child in frame.winfo_children():
            child.destroy()
        gen = self.generator
        client = gen.license() if hasattr(gen, 'license') else None
        if client is None:
            return   # developer checkout: show nothing

        plan = self._current_plan()

        # a small plan pill, coloured per plan (never colour alone: it says the word)
        colours = {'free': (self.FG_MUTED, self.BG_CARD_2),
                   'pro': ('#ffffff', self.ACCENT),
                   'team': ('#ffffff', '#0b766e')}
        fg, bg = colours.get(plan, colours['free'])
        pill = tk.Label(frame, text='  ' + self.PLAN_TEXT.get(plan, 'Free') + ' plan  ',
                        bg=bg, fg=fg, font=('Segoe UI', 9, 'bold'))
        pill.pack(side=tk.LEFT, padx=(0, 8), pady=2)

        if plan == 'free':
            ttk.Button(frame, text='\u2b50  Upgrade', style='Accent.TButton',
                       command=self._open_upgrade).pack(side=tk.LEFT, padx=(0, 6))
            # v6.3.1 (TASK 2): the button is replaced by a countdown notice
            # once three keys have been rejected. The state comes from the
            # SERVER at check-in, so restarting the tool or clearing local
            # data does not give anyone a fresh set of attempts.
            lock = self._activation_lock_state()
            if lock.get('locked'):
                # v6.3.2 (TASK 1.3): the button is simply NOT THERE. No
                # countdown, no notice, no explanation - the round-2
                # countdown was explicitly withdrawn. A cheap timer re-checks
                # so the button reappears by itself when the window closes.
                if not self._silent_registration():
                    tk.Label(frame, text='Too many attempts. You can try again in '
                                         + self._format_lock_remaining(lock),
                             bg=self.HEADER, fg='#ffd479', font=('Segoe UI', 9)
                             ).pack(side=tk.LEFT, padx=(0, 6))
                self._schedule_lock_countdown()
            else:
                ttk.Button(frame, text='Register licence', style='Ghost.TButton',
                           command=self._register_serial_dialog).pack(side=tk.LEFT, padx=(0, 6))
                # v6.3.2: "N attempts remaining" is gone too - it is an
                # explanation, and section 1.3 allows none.
                left = lock.get('remaining')
                if not self._silent_registration() and isinstance(left, int) \
                        and 0 < left < lock.get('max', 3):
                    tk.Label(frame, text='%d attempt%s remaining'
                                         % (left, '' if left == 1 else 's'),
                             bg=self.HEADER, fg=self.FG_MUTED, font=('Segoe UI', 9)
                             ).pack(side=tk.LEFT, padx=(0, 6))
        else:
            # v6.3.1 (TASK 2): a valid licence is active, so Register licence
            # is removed from the top bar. My plan stays and remains where the
            # user sees status, expiry and plan. The button comes back by
            # itself if the licence expires, is revoked or is refunded,
            # because this runs again on every plan change.
            ttk.Button(frame, text='My plan', style='Ghost.TButton',
                       command=self._show_plan_dialog).pack(side=tk.LEFT, padx=(0, 6))

    def _activation_lock_state(self):
        """Attempt/lockout state for the Register licence button (TASK 2).

        The SERVER value always wins. It arrives on every check-in and is
        mirrored locally by license_client, so the UI is instantly correct at
        start-up and still correct with no network - and a restart cannot
        hand anyone a fresh set of attempts.
        """
        client = self._referral_client()
        if client is None:
            return {}
        try:
            state = client.activation_state() or {}
        except Exception:
            return {}
        return state if isinstance(state, dict) else {}

    def _format_lock_remaining(self, lock):
        try:
            secs = int(lock.get('retry_after_seconds', 0) or 0)
        except Exception:
            secs = 0
        secs = max(0, secs)
        hours, rem = divmod(secs, 3600)
        mins = rem // 60
        if hours:
            return '%dh %02dm' % (hours, mins)
        if mins:
            return '%dm' % mins
        return 'less than a minute'

    def _schedule_lock_countdown(self):
        """Tick the countdown once a minute, and put the button back the
        moment the window expires - without hammering the server."""
        if getattr(self, '_lock_tick_job', None):
            try:
                self.root.after_cancel(self._lock_tick_job)
            except Exception:
                pass
            self._lock_tick_job = None

        def tick():
            self._lock_tick_job = None
            try:
                lock = self._activation_lock_state()
                self._build_license_buttons()
                if not lock.get('locked'):
                    # window closed: re-check in so the server agrees
                    self._refresh_plan_after_reward()
            except Exception:
                pass

        try:
            self._lock_tick_job = self.root.after(60000, tick)
        except Exception:
            pass

    # ==================================================================
    # v6.3.3  LANGUAGE (English / العربية / Español / Français)
    #
    # Strings live in mavely_lang.py, an external resource file, so a
    # wording fix never touches logic. Any key a translation is missing
    # falls back to English, so a partial translation cannot break the
    # window. Nothing existing is removed: untranslated widgets keep the
    # literal text they always had.
    # ==================================================================
    def _lang_code(self):
        code = getattr(self, '_ui_lang', None)
        if code:
            return code
        try:
            code = self.generator._load_userscript_registry()['settings'].get('ui_language')
        except Exception:
            code = None
        if not code:
            code = self._detect_os_language()
        self._ui_lang = code
        return code

    @staticmethod
    def _detect_os_language():
        """Follow the operating system, falling back to English (spec 3)."""
        try:
            import locale
            raw = ''
            try:
                raw = (locale.getlocale()[0] or '')
            except Exception:
                raw = ''
            if not raw:
                raw = os.environ.get('LANG', '') or os.environ.get('LANGUAGE', '')
            raw = raw.replace('-', '_').lower()
            for code in ('ar', 'es', 'fr', 'en'):
                if raw.startswith(code) or ('_' + code) in raw:
                    return code
        except Exception:
            pass
        return 'en'

    def t(self, key, **kw):
        """Translate. Never raises: a bad key returns the key itself."""
        try:
            import mavely_lang
            text = mavely_lang.lookup(self._lang_code(), key)
        except Exception:
            return key
        if kw:
            try:
                return text.format(**kw)
            except Exception:
                return text
        return text

    def _is_rtl(self):
        try:
            import mavely_lang
            return mavely_lang.is_rtl(self._lang_code())
        except Exception:
            return False

    def _anchor(self):
        """Text anchor for the active direction: RTL text hangs right."""
        return tk.E if self._is_rtl() else tk.W

    def _justify(self):
        return tk.RIGHT if self._is_rtl() else tk.LEFT

    def _side_start(self):
        """'Start' edge: right in Arabic, left otherwise, so panels mirror."""
        return tk.RIGHT if self._is_rtl() else tk.LEFT

    def _side_end(self):
        return tk.LEFT if self._is_rtl() else tk.RIGHT

    @staticmethod
    def ltr(text):
        """Keep numbers, clocks, URLs and licence keys left-to-right when
        they sit inside Arabic text (spec 3). U+2066/U+2069 isolate them."""
        return '\u2066' + str(text) + '\u2069'

    def _set_language(self, code):
        """Switch language immediately - no restart (spec 3)."""
        if code == getattr(self, '_ui_lang', None):
            return
        self._ui_lang = code
        try:
            self.generator.set_ui_setting('ui_language', code)
        except Exception:
            pass
        try:
            self._retranslate()
        except Exception:
            pass

    def _register_text(self, widget, key, attr='text', **kw):
        """Remember a widget so _retranslate() can update it in place."""
        if not hasattr(self, '_i18n_widgets'):
            self._i18n_widgets = []
        self._i18n_widgets.append((widget, key, attr, kw))
        try:
            widget.configure(**{attr: self.t(key, **kw)})
        except Exception:
            pass
        return widget

    def _retranslate(self):
        """Re-apply every registered string, then rebuild what is rebuilt."""
        for entry in list(getattr(self, '_i18n_widgets', [])):
            widget, key, attr, kw = entry
            try:
                if not widget.winfo_exists():
                    self._i18n_widgets.remove(entry)
                    continue
                widget.configure(**{attr: self.t(key, **kw)})
            except Exception:
                pass
        # tabs
        try:
            self.notebook.tab(self.profiles_tab, text='   %s   ' % self.t('tab.profiles'))
            if getattr(self, 'invite_tab', None) is not None:
                self.notebook.tab(self.invite_tab, text='   %s   ' % self.t('tab.invite'))
            if getattr(self, 'timer_tab', None) is not None:
                self.notebook.tab(self.timer_tab, text='   %s   ' % self.t('tab.timer'))
        except Exception:
            pass
        for fn in ('_build_license_buttons', '_build_language_buttons',
                   '_refresh_invite_tab', '_timer_retranslate'):
            try:
                f = getattr(self, fn, None)
                if f:
                    f() if fn != '_refresh_invite_tab' else f(False)
            except Exception:
                pass

    def _build_language_buttons(self):
        """The language selector in the top bar, beside the plan controls."""
        frame = getattr(self, '_lang_btns', None)
        if frame is None:
            return
        for child in frame.winfo_children():
            child.destroy()
        try:
            import mavely_lang
            langs = mavely_lang.language_labels()
        except Exception:
            return
        active = self._lang_code()
        for code, label in langs:
            on = (code == active)
            b = tk.Label(frame, text=' %s ' % label, cursor='hand2',
                         bg=self.ACCENT if on else self.BG_CARD_2,
                         fg='#ffffff' if on else self.FG,
                         font=('Segoe UI', 9, 'bold' if on else 'normal'),
                         padx=6, pady=2)
            b.pack(side=tk.LEFT, padx=(0, 3))
            b.bind('<Button-1>', lambda e, c=code: self._set_language(c))

    # ==================================================================
    # v6.3.3  USA TIMER TAB
    # ==================================================================
    def _build_timer_tab(self):
        """The USA Timer, beside Profiles and Invite.

        Pro and Unlimited for Team only - it is a paid feature, so on Free
        the tab is not created at all rather than shown and blocked.
        """
        self.timer_tab = None
        self._timer_panel = None
        if self._current_plan() not in ('pro', 'team'):
            return
        try:
            import mavely_timer
        except Exception as exc:
            self.log('[usa-timer] not available: %r' % (exc,))
            return
        try:
            self.timer_tab = ttk.Frame(self.notebook, style='TFrame', padding=0)
            self.notebook.add(self.timer_tab, text='   %s   ' % self.t('tab.timer'))
            rules = self._timer_rules(refresh=False) or self._timer_rules(refresh=True)
            self._timer_panel = mavely_timer.UsaTimerPanel(self.timer_tab, self, rules)
        except Exception as exc:
            self.log('[usa-timer] could not start: %r' % (exc,))
            self.timer_tab = None
            self._timer_panel = None

    def _timer_retranslate(self):
        panel = getattr(self, '_timer_panel', None)
        if panel is not None:
            try:
                panel.retranslate()
            except Exception:
                pass

    def notify_tab_badge(self):
        """Golden hour started. A quiet mark on the tab - never a modal and
        never topmost, so the tool is not seized while you are working."""
        try:
            if getattr(self, 'timer_tab', None) is not None:
                self.notebook.tab(self.timer_tab, text='  \u25cf %s   ' % self.t('tab.timer'))
                self.root.after(60000, lambda: self.notebook.tab(
                    self.timer_tab, text='   %s   ' % self.t('tab.timer')))
        except Exception:
            pass

    def _sync_timer_tab(self):
        """Add or remove the tab when the plan changes, with no restart."""
        paid = self._current_plan() in ('pro', 'team')
        have = getattr(self, 'timer_tab', None) is not None
        if paid and not have:
            self._build_timer_tab()
            try:
                if getattr(self, '_timer_banner', None) is None:
                    self._build_timer_banner()
            except Exception:
                pass
        elif not paid and have:
            self._drop_timer_banner()
            panel = getattr(self, '_timer_panel', None)
            if panel is not None:
                try:
                    panel.stop()
                except Exception:
                    pass
            try:
                self.notebook.forget(self.timer_tab)
            except Exception:
                pass
            self.timer_tab = None
            self._timer_panel = None

    def log(self, message):
        """v6.3.3: one place for a panel to report a failure.

        Goes to stderr always, and to the server's Audit & error logs when
        the licensing client can reach it - the same path the rest of the
        tool already uses. Never raises, so a logging problem can never
        take down whatever was being logged.
        """
        try:
            sys.stderr.write('%s\n' % (message,))
        except Exception:
            pass
        try:
            client = self.generator.license()
            reporter = getattr(client, 'report_error', None) if client else None
            if reporter:
                threading.Thread(target=lambda: reporter(str(message)),
                                 daemon=True).start()
        except Exception:
            pass

    # ==================================================================
    # v6.3.4  USA TIMER BANNER (across the top of the window)
    # ==================================================================
    def _timer_rules(self, refresh=False):
        """The schedule, from the website. {} when not entitled/unknown."""
        client = self.generator.license() if hasattr(self.generator, 'license') else None
        if client is None or not hasattr(client, 'feature'):
            return {}
        try:
            return client.feature('usa_timer', refresh=refresh) or {}
        except Exception:
            return {}

    def _build_timer_banner(self):
        """A live strip at the top: title, the states that are prime right
        now, and the countdown to the next one. Clicking it opens the tab.

        It is only built when the website has actually sent a schedule, so
        a copy that cannot reach the server shows nothing at all rather
        than an empty frame."""
        self._timer_banner = None
        self._timer_banner_rules = self._timer_rules(refresh=False)
        if self._current_plan() not in ('pro', 'team'):
            return
        if not self._timer_banner_rules:
            # ask the website once, in the background, then build if it answers
            def fetch():
                rules = self._timer_rules(refresh=True)
                if rules:
                    try:
                        self.root.after(0, self._build_timer_banner)
                    except Exception:
                        pass
            threading.Thread(target=fetch, daemon=True).start()
            return

        bar = tk.Frame(self.root, bg=self.BG_CARD, highlightthickness=1,
                       highlightbackground=self.BORDER, cursor='hand2')
        bar.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=10, pady=(0, 6))
        self._timer_banner = bar

        title = tk.Label(bar, text=self.t('timer.title'), bg=self.BG_CARD,
                         fg=self.ACCENT, font=('Segoe UI', 15, 'bold'))
        title.pack(side=self._side_start(), padx=(14, 16), pady=6)
        self._timer_banner_title = title

        self._timer_banner_states = tk.Label(
            bar, text='', bg=self.BG_CARD, fg=self.FG, font=('Segoe UI', 10))
        self._timer_banner_states.pack(side=self._side_start(), pady=6)

        self._timer_banner_next = tk.Label(
            bar, text='', bg=self.BG_CARD, fg=self.FG_MUTED,
            font=('Segoe UI', 10, 'bold'))
        self._timer_banner_next.pack(side=self._side_end(), padx=(0, 14), pady=6)

        for w in (bar, title, self._timer_banner_states, self._timer_banner_next):
            w.bind('<Button-1>', lambda e: self._show_timer_tab())

        self._tick_timer_banner()

    def _tick_timer_banner(self):
        """Refresh the banner once a second. Cheap: a handful of clock
        reads, no layout churn, and it stops itself if the bar is gone."""
        bar = getattr(self, '_timer_banner', None)
        if bar is None:
            return
        try:
            if not bar.winfo_exists():
                self._timer_banner = None
                return
        except Exception:
            self._timer_banner = None
            return
        try:
            import mavely_timer
            rules = self._timer_banner_rules or {}
            now_by_zone, prime = {}, []
            zones = [(z.get('state'), z.get('tz')) for z in (rules.get('zones') or [])]
            for state, tzname in zones:
                try:
                    now = mavely_timer.datetime.now(mavely_timer._tz(tzname))
                except Exception:
                    continue
                now_by_zone[state] = now
                status = mavely_timer.apply_rules(rules, now.hour, now.weekday())
                if status in ('GOLD', 'GOOD'):
                    prime.append((status, state, now))
            prime.sort(key=lambda p: 0 if p[0] == 'GOLD' else 1)
            if prime:
                status, state, now = prime[0]
                extra = len(prime) - 1
                text = '%s  %s  %s' % (self.t('state.' + state),
                                       self.ltr(now.strftime('%H:%M')),
                                       self.t('st.' + status))
                if extra > 0:
                    text += '   (+%d)' % extra
                colour = ('#d4a017' if status == 'GOLD' else '#1e8e3e')
            else:
                text = self.t('timer.subtitle')
                colour = self.FG_MUTED
            self._timer_banner_states.configure(text=text, fg=colour)

            mins, _s = mavely_timer.next_golden_minutes(now_by_zone,
                                                        rules.get('golden_hours'))
            if mins is None:
                nxt = self.t('timer.tomorrow')
            elif mins < 60:
                nxt = self.ltr('%dm' % mins)
            else:
                nxt = self.ltr('%dh %02dm' % (mins // 60, mins % 60))
            self._timer_banner_next.configure(
                text='%s: %s' % (self.t('timer.next_golden'), nxt))
        except Exception as exc:
            self.log('[usa-timer-banner] %r' % (exc,))
        try:
            self._timer_banner_job = self.root.after(1000, self._tick_timer_banner)
        except Exception:
            pass

    def _drop_timer_banner(self):
        job = getattr(self, '_timer_banner_job', None)
        if job:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
            self._timer_banner_job = None
        bar = getattr(self, '_timer_banner', None)
        if bar is not None:
            try:
                bar.destroy()
            except Exception:
                pass
        self._timer_banner = None

    def _api_base(self):
        base = 'https://mavlink.click'
        if _license is not None:
            base = getattr(_license, 'API_BASE', base) or base
        return base

    def _open_buy_page(self):
        import webbrowser
        try:
            webbrowser.open_new_tab(self._api_base() + '/pricing.php?ref=app')
        except Exception:
            pass

    def _open_upgrade(self):
        """Non-blocking upgrade dialog: explains the paid plans and opens the
        website to buy, or lets the user paste a key they already have."""
        client = self.generator.license()
        if client is None:
            return
        win = tk.Toplevel(self.root)
        win.title('Upgrade')
        win.configure(bg=self.BG_CARD)
        win.transient(self.root)
        win.resizable(False, False)
        tk.Label(win, text='Upgrade for more', bg=self.BG_CARD, fg=self.FG,
                 font=('Segoe UI', 15, 'bold')).pack(padx=26, pady=(20, 4))
        tk.Label(win, bg=self.BG_CARD, fg=self.FG_MUTED, font=('Segoe UI', 10),
                 justify=tk.LEFT, wraplength=420, text=(
                     'You are on the Free plan: up to 5 profiles, English and French, '
                     '1920\u00d71080, and Script 1.\n\n'
                     'Pro unlocks unlimited profiles, the full fingerprint engine, every '
                     'language and screen size, and Script 2, on one computer.\n\n'
                     'Unlimited for Team adds activation on up to three computers.')
                 ).pack(padx=26, pady=(0, 12))
        btns = tk.Frame(win, bg=self.BG_CARD)
        btns.pack(padx=26, pady=(0, 20))
        ttk.Button(btns, text='See plans and buy', style='Accent.TButton',
                   command=lambda: (self._open_buy_page(), win.destroy())).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btns, text='I have a licence key', style='Ghost.TButton',
                   command=lambda: (win.destroy(), self._register_serial_dialog())).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btns, text='Not now', style='Ghost.TButton',
                   command=win.destroy).pack(side=tk.LEFT)
        self._center_popup(win)

    def _start_trial_dialog(self):
        """Kept for older call sites. v6.2 has no trial: the Free plan works
        from the first launch, so this simply shows the upgrade options."""
        self._open_upgrade()

    def _show_plan_dialog(self):
        """A read-only summary of the active paid plan and its licence."""
        client = self.generator.license()
        if client is None:
            return
        pub = getattr(client, 'license_public', None) or {}
        plan = self._current_plan()
        lines = ['Plan: ' + self.PLAN_TEXT.get(plan, plan)]
        if pub.get('serial_masked'):
            lines.append('Licence: ' + str(pub.get('serial_masked')))
        if client.expires_at:
            lines.append('Renews / expires: ' + client.expires_at.split(' ')[0])
        if pub.get('devices_used') is not None and pub.get('max_devices') is not None:
            lines.append('Computers: %s of %s in use' % (pub.get('devices_used'), pub.get('max_devices')))
        ent = {}
        try:
            ent = client.plan_entitlements()
        except Exception:
            ent = {}
        if ent:
            prof = 'Unlimited' if int(ent.get('max_profiles', 0)) == 0 else str(ent.get('max_profiles'))
            lines.append('Profiles: ' + prof)
            lines.append('Script 2: ' + ('yes' if 'pro' in ent.get('scripts', []) else 'no'))
        from tkinter import messagebox
        messagebox.showinfo('My plan', '\n'.join(lines))

    def _silent_registration(self):
        """v6.3.2 (TASK 1): registration failures are silent.

        A stored setting, so the original popup flow is never deleted - it
        is one value away. Default ON, exactly as specified.
        """
        try:
            return bool(self.generator._load_userscript_registry()['settings']
                        .get('silent_registration', True))
        except Exception:
            return True

    def _registration_flash(self):
        """Optional single border flash on a rejected key.

        Default OFF, because the specification says show nothing at all.
        It exists because with zero feedback a customer with a typo cannot
        tell a wrong key from broken software, and a flash leaks nothing an
        attacker could use. Flip 'registration_flash' to switch it on.
        """
        try:
            return bool(self.generator._load_userscript_registry()['settings']
                        .get('registration_flash', False))
        except Exception:
            return False

    def _open_registration_window(self):
        """The registration window (TASK 1.1).

        simpledialog.askstring() closes the moment OK is pressed, so by the
        time a key is known to be bad there is no field left to clear. This
        window stays open instead, which is what makes 'clear the input and
        show nothing' possible at all.

        On ANY failure: the field is cleared, focus stays in it, and nothing
        else happens - no dialog, no message, no status text, no sound, no
        colour. On success the original success path runs unchanged.
        """
        client = self.generator.license()
        if client is None:
            return
        existing = getattr(self, '_reg_win', None)
        if existing is not None:
            try:
                existing.lift()
                existing.focus_force()
                return
            except Exception:
                self._reg_win = None

        win = tk.Toplevel(self.root)
        self._reg_win = win
        win.title('Register licence')
        win.configure(bg=self.BG_CARD)
        win.resizable(False, False)
        try:
            win.transient(self.root)
        except Exception:
            pass

        body = tk.Frame(win, bg=self.BG_CARD)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=(18, 0))
        tk.Label(body, text='Register licence', bg=self.BG_CARD, fg=self.FG,
                 font=('Segoe UI', 12, 'bold'), anchor=tk.W).pack(fill=tk.X)
        tk.Label(body, text='Paste your licence key:', bg=self.BG_CARD,
                 fg=self.FG_MUTED, font=('Segoe UI', 9), anchor=tk.W
                 ).pack(fill=tk.X, pady=(6, 4))

        var = tk.StringVar(value='')
        entry = tk.Entry(body, textvariable=var, width=34, font=('Consolas', 11),
                         bg=self.BG_CARD_2, fg=self.FG, insertbackground=self.FG,
                         relief=tk.FLAT, highlightthickness=1,
                         highlightbackground=self.BORDER, highlightcolor=self.ACCENT)
        entry.pack(fill=tk.X, ipady=4)

        btns = tk.Frame(win, bg=self.BG_CARD)
        btns.pack(fill=tk.X, padx=20, pady=(14, 18))

        state = {'busy': False}

        def close():
            self._reg_win = None
            try:
                win.destroy()
            except Exception:
                pass

        def fail_silently():
            """Clear the field. Show nothing. Change nothing else."""
            try:
                var.set('')
                entry.focus_set()
            except Exception:
                pass
            if self._registration_flash():
                try:
                    entry.configure(highlightbackground='#c0392b', highlightcolor='#c0392b')
                    self.root.after(450, lambda: entry.configure(
                        highlightbackground=self.BORDER, highlightcolor=self.ACCENT))
                except Exception:
                    pass

        def submit(_evt=None):
            if state['busy']:
                return
            raw = ''
            try:
                raw = var.get().strip()
            except Exception:
                pass
            if not raw:
                fail_silently()          # empty field never reaches the server
                return
            state['busy'] = True

            def work():
                try:
                    ok, msg = client.activate(raw)
                except Exception:
                    ok, msg = False, ''
                def done():
                    state['busy'] = False
                    if ok:
                        close()
                        # success path unchanged: plan applied, buttons
                        # rebuilt, the normal confirmation still shown
                        self._after_license_change(True, msg)
                    else:
                        fail_silently()
                        # the top bar may need to lose the button now, but
                        # nothing is announced
                        try:
                            self._build_license_buttons()
                        except Exception:
                            pass
                try:
                    self.root.after(0, done)
                except Exception:
                    pass

            threading.Thread(target=work, daemon=True).start()

        ttk.Button(btns, text='Register', style='Accent.TButton', width=10,
                   command=submit).pack(side=tk.RIGHT)
        ttk.Button(btns, text='Cancel', style='Ghost.TButton', width=9,
                   command=close).pack(side=tk.RIGHT, padx=(0, 6))

        win.protocol('WM_DELETE_WINDOW', close)
        win.bind('<Return>', submit)
        win.bind('<Escape>', lambda e: close())
        try:
            win.geometry('380x180')
            win.minsize(380, 180)
        except Exception:
            pass
        try:
            self._center_popup(win)
        except Exception:
            pass
        try:
            entry.focus_set()
        except Exception:
            pass

    def _register_serial_dialog(self):
        # v6.3.2 (TASK 1): silent registration. The original ask-then-popup
        # path below is NOT removed - it still runs whenever silent mode is
        # switched off in settings.
        if self._silent_registration():
            self._open_registration_window()
            return
        client = self.generator.license()
        if client is None:
            return
        serial = self._ask_text('Register licence',
                                'Paste your licence key (MVL-XXXXX-XXXXX-XXXXX-XXXXX):')
        if not serial:
            return
        self.status_var.set('Activating licence...')
        self.root.update_idletasks()
        ok, msg = client.activate(serial.strip())
        self._after_license_change(ok, msg)

    def _after_license_change(self, ok, msg):
        from tkinter import messagebox
        self._build_license_buttons()
        self._refresh_license_banner()
        try:
            self._apply_plan_theme()
        except Exception:
            pass
        try:
            self.status_var.set(self.generator.license().status_line())
        except Exception:
            pass
        # reflect any newly locked/unlocked features in the config panel
        try:
            self._sync_feature_locks()
        except Exception:
            pass
        if ok:
            messagebox.showinfo('MavelyLink', msg or 'Your licence is active.')
        elif not self._silent_registration():
            # v6.3.2 (TASK 1): THIS is the dialog in licence.png. It is not
            # deleted - it still runs when silent registration is switched
            # off - but in the default silent mode a rejected key produces
            # no modal, no message, no sound and no colour anywhere.
            messagebox.showerror('MavelyLink', msg or 'Something went wrong.')

    def _ask_text(self, title, prompt):
        from tkinter import simpledialog
        try:
            return simpledialog.askstring(title, prompt, parent=self.root)
        except Exception:
            return None

    def _refresh_license_banner(self):
        client = self.generator.license()
        if client is None or not hasattr(self, '_license_status_lbl'):
            return
        try:
            self._license_status_lbl.config(text=client.status_line())
        except Exception:
            pass

    def _enforce_license_gate(self):
        """v6.2: the tool is usable on Free, so this NO LONGER blocks an
        unlicensed user. It only stops the tool when the administrator has
        turned the application off (the master switch). Paid-only features are
        gated individually where they are used, with an upgrade prompt.
        """
        client = self.generator.license()
        if client is None:
            return True
        try:
            if client.app_allowed():
                return True
        except Exception:
            return True
        # master switch is OFF: the dedicated popup handles this
        return False

    def _free_counted_profiles(self):
        """v6.2.1: how many profiles count against the Free cap.

        Only profiles created since this version was installed. Whatever
        already existed is grandfathered by free_baseline_names() in
        license_client and never counted, which is what unblocks an existing
        user who is far over the old cap.

        Falls back to the plain total if the licensing module is absent, so
        a developer checkout behaves exactly as before.
        """
        try:
            names = [p['name'] for p in self.generator.get_all_profiles()]
        except Exception:
            return 0
        if _license is None or not hasattr(_license, 'free_new_profile_count'):
            return len(names)
        try:
            return int(_license.free_new_profile_count(names))
        except Exception:
            return len(names)

    def _free_grandfathered_count(self):
        """How many existing profiles are exempt from the cap. 0 on a fresh
        install. Used only to explain the numbers to the user."""
        try:
            total = len(self.generator.get_all_profiles())
        except Exception:
            return 0
        return max(0, total - self._free_counted_profiles())

    def _free_plan_limit_dialog(self, cap, counted, allowed, total=None):
        """The original 'Free plan limit' dialog, kept as it was.

        v6.2.1 moved it into a method of its own so the generation path can
        still reach it, and so its wording is in one place. The text is the
        original text; the only addition is one line explaining that older
        profiles do not count, shown only when there are some.
        """
        from tkinter import messagebox
        msg = ('The Free plan allows up to %d browser profiles, and you have %d.\n\n'
               '%s\n\nUpgrade to Pro or Unlimited for Team for unlimited profiles. '
               'Your Free profiles keep working.'
               % (cap, counted,
                  ('You can create %d more.' % allowed) if allowed
                  else 'Delete one first, or upgrade to add more.'))
        grandfathered = 0
        try:
            if total is None:
                total = len(self.generator.get_all_profiles())
            grandfathered = max(0, int(total) - int(counted))
        except Exception:
            grandfathered = 0
        if grandfathered:
            msg += ('\n\nThe %d profile%s you already had do not count towards this '
                    'limit and keep working.'
                    % (grandfathered, '' if grandfathered == 1 else 's'))
        messagebox.showinfo('Free plan limit', msg)

    def _free_feature_popup(self, message='', title=None, offer_upgrade=True):
        # v6.3.4: the title and the default body now come from the language
        # file, so this popup is no longer English while the UI is Arabic.
        title = title or self.t('free.title')
        """v6.2.1 (task 4): the small 'not in the Free version' dialog.

        Deliberately tiny - roughly 320x130 - with a short title, one
        sentence and an OK button, plus an optional Upgrade button that
        opens the existing full upgrade dialog.

        Non-destructive by construction: it only reports. It never changes a
        setting, never cancels what the user was doing, and the control that
        triggered it keeps the state it already had. The app stays fully
        usable behind it.

        This is for the LOCKED FEATURE case. The bigger 'Free plan limit'
        and 'Upgrade for more' dialogs are untouched and still used
        elsewhere.
        """
        message = message or self.t('free.generic')
        try:
            win = tk.Toplevel(self.root)
        except Exception:
            # no usable window (headless / shutting down): never let the
            # absence of a popup stop the caller
            return
        win.title(title)
        win.configure(bg=self.BG_CARD)
        win.resizable(False, False)
        try:
            win.transient(self.root)
        except Exception:
            pass

        body = tk.Frame(win, bg=self.BG_CARD)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(14, 0))
        tk.Label(body, text=title, bg=self.BG_CARD, fg=self.FG,
                 font=('Segoe UI', 10, 'bold'), anchor=tk.W).pack(fill=tk.X)
        tk.Label(body, text=message, bg=self.BG_CARD, fg=self.FG_MUTED,
                 font=('Segoe UI', 9), justify=tk.LEFT, wraplength=286,
                 anchor=tk.W).pack(fill=tk.X, pady=(6, 0))

        btns = tk.Frame(win, bg=self.BG_CARD)
        btns.pack(fill=tk.X, padx=16, pady=(10, 14))

        def _close():
            try:
                win.grab_release()
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass

        ok = ttk.Button(btns, text='OK', style='Accent.TButton', width=8, command=_close)
        ok.pack(side=tk.RIGHT)
        if offer_upgrade:
            ttk.Button(btns, text='Upgrade', style='Ghost.TButton', width=9,
                       command=lambda: (_close(), self._open_upgrade())).pack(side=tk.RIGHT, padx=(0, 6))

        win.protocol('WM_DELETE_WINDOW', _close)
        win.bind('<Return>', lambda e: _close())
        win.bind('<Escape>', lambda e: _close())
        try:
            win.geometry('320x130')
            win.minsize(320, 130)
        except Exception:
            pass
        try:
            self._center_popup(win)
        except Exception:
            pass
        try:
            ok.focus_set()
            win.grab_set()
        except Exception:
            pass

    def _free_locked(self, feature=''):
        """One-liner for any paid-only control: report, then carry on.

        Always returns True, so a caller can write
            if not self._plan_allows(x): return self._free_locked('X')
        and read naturally. Use this for every new paid-only control.
        """
        if feature:
            message = self.t('free.feature', feature=feature)
        else:
            message = self.t('free.generic')
        self._free_feature_popup(message)
        return True

    def _needs_pro(self, feature='', small=True):
        """True if a paid-only feature was blocked; shows an upgrade prompt.

        Returns False when the current plan already includes it (so the
        caller proceeds). Never raises.

        v6.2.1: `small` (new, defaults to True) shows the compact task-4
        dialog instead of the old question box. Pass small=False for the
        original behaviour, which is preserved below unchanged. The return
        value means the same thing either way, so no existing caller needs
        to change.
        """
        try:
            if self._current_plan() in ('pro', 'team'):
                return False
        except Exception:
            return False
        if small:
            self._free_locked(feature or 'That feature')
            return True
        from tkinter import messagebox
        msg = (feature or 'That feature') + ' is a Pro feature.\n\n' \
            + 'Upgrade to Pro or Unlimited for Team to use it. Your Free plan keeps working in the meantime.'
        if messagebox.askyesno('Pro feature', msg + '\n\nSee the plans now?'):
            self._open_upgrade()
        return True

    # ==================================================================
    # v6.3  REFERRAL PROGRAMME - Invite tab + the two launch popups
    #
    # Additive throughout. The header bar is left exactly as it was
    # (About / plan pill / Upgrade / Register licence / theme buttons);
    # everything here lives on its own notebook tab beside Profiles.
    #
    # Works on EVERY plan, Free included. Every network call runs on a
    # worker thread and every failure is silent, so the tool behaves
    # identically with no connection.
    # ==================================================================
    REFERRAL_OFFER_LINE1 = 'Earn an extra $15 or get a Pro License*'
    REFERRAL_OFFER_LINE2 = 'Invite 5 people'

    def _referral_client(self):
        """The LicenseClient, or None when the module is absent."""
        try:
            gen = self.generator
            return gen.license() if hasattr(gen, 'license') else None
        except Exception:
            return None

    def _build_invite_tab(self):
        """The Invite tab. Built once, populated from cache, then refreshed
        from the server in the background."""
        try:
            self.invite_tab = ttk.Frame(self.notebook, style='TFrame', padding=8)
            self.notebook.add(self.invite_tab, text='   Invite   ')
        except Exception:
            return
        if self._referral_client() is None:
            # developer checkout without the licensing module: show nothing
            # rather than a tab that cannot work
            try:
                self.notebook.forget(self.invite_tab)
            except Exception:
                pass
            self.invite_tab = None
            return

        self._ref_link_var = tk.StringVar(value='')
        self._ref_progress_var = tk.StringVar(value='0 of 5 referrals')
        self._ref_status_var = tk.StringVar(value='Loading your invite link...')
        self._ref_email_var = tk.StringVar(value='')
        self._ref_state = {}

        outer = tk.Frame(self.invite_tab, bg=self.BG)
        outer.pack(fill=tk.BOTH, expand=True)

        card = tk.Frame(outer, bg=self.BG_CARD, highlightbackground=self.BORDER,
                        highlightthickness=1, bd=0)
        card.pack(fill=tk.X, padx=6, pady=6)

        tk.Label(card, text=self.REFERRAL_OFFER_LINE1, bg=self.BG_CARD, fg=self.FG,
                 font=('Segoe UI', 15, 'bold'), anchor=tk.W
                 ).pack(fill=tk.X, padx=18, pady=(16, 2))
        tk.Label(card, text=self.REFERRAL_OFFER_LINE2, bg=self.BG_CARD, fg=self.FG,
                 font=('Segoe UI', 11), anchor=tk.W
                 ).pack(fill=tk.X, padx=18, pady=(0, 2))

        terms = tk.Label(card, text='* See the referral terms', bg=self.BG_CARD,
                         fg=self.ACCENT, font=('Segoe UI', 9, 'underline'),
                         cursor='hand2', anchor=tk.W)
        terms.pack(fill=tk.X, padx=18, pady=(0, 12))
        terms.bind('<Button-1>', lambda e: self._open_referral_terms())

        # ---- the link ------------------------------------------------
        self._ref_link_frame = tk.Frame(card, bg=self.BG_CARD)
        self._ref_link_frame.pack(fill=tk.X, padx=18, pady=(0, 4))
        tk.Label(self._ref_link_frame, text='Your invite link', bg=self.BG_CARD,
                 fg=self.FG_MUTED, font=('Segoe UI', 9), anchor=tk.W).pack(fill=tk.X)
        row = tk.Frame(self._ref_link_frame, bg=self.BG_CARD)
        row.pack(fill=tk.X, pady=(4, 0))
        self._ref_link_entry = ttk.Entry(row, textvariable=self._ref_link_var,
                                         state='readonly', width=48)
        self._ref_link_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._ref_copy_btn = ttk.Button(row, text='Copy link', style='Accent.TButton',
                                        command=self._copy_referral_link)
        self._ref_copy_btn.pack(side=tk.LEFT, padx=(8, 0))

        # ---- the "no account yet" path -------------------------------
        # A Free user has no licence, no serial and no email on record, so
        # there is nothing to attach a code to until they give one. Shown
        # instead of a broken link (spec 2.2).
        self._ref_email_frame = tk.Frame(card, bg=self.BG_CARD)
        tk.Label(self._ref_email_frame,
                 text='Add your email address to get your personal invite link.\n'
                      'It is also where a reward would be sent.',
                 bg=self.BG_CARD, fg=self.FG_MUTED, font=('Segoe UI', 9),
                 justify=tk.LEFT, anchor=tk.W).pack(fill=tk.X)
        erow = tk.Frame(self._ref_email_frame, bg=self.BG_CARD)
        erow.pack(fill=tk.X, pady=(6, 0))
        ttk.Entry(erow, textvariable=self._ref_email_var, width=34).pack(side=tk.LEFT)
        ttk.Button(erow, text='Get my invite link', style='Accent.TButton',
                   command=self._register_referral_email).pack(side=tk.LEFT, padx=(8, 0))

        # ---- progress -------------------------------------------------
        prog = tk.Frame(card, bg=self.BG_CARD)
        prog.pack(fill=tk.X, padx=18, pady=(14, 0))
        tk.Label(prog, textvariable=self._ref_progress_var, bg=self.BG_CARD,
                 fg=self.FG, font=('Segoe UI', 11, 'bold'), anchor=tk.W).pack(fill=tk.X)
        self._ref_bar = ttk.Progressbar(prog, orient='horizontal', mode='determinate',
                                        maximum=5, value=0)
        self._ref_bar.pack(fill=tk.X, pady=(6, 0))

        tk.Label(card,
                 text='A referral counts when someone you invited buys a licence through '
                      'your link. Clicks, downloads and Free installs do not count.',
                 bg=self.BG_CARD, fg=self.FG_MUTED, font=('Segoe UI', 9),
                 justify=tk.LEFT, wraplength=640, anchor=tk.W
                 ).pack(fill=tk.X, padx=18, pady=(10, 0))

        bar = tk.Frame(card, bg=self.BG_CARD)
        bar.pack(fill=tk.X, padx=18, pady=(12, 16))
        ttk.Button(bar, text='Refresh', style='Ghost.TButton',
                   command=lambda: self._refresh_invite_tab(True)).pack(side=tk.LEFT)
        tk.Label(bar, textvariable=self._ref_status_var, bg=self.BG_CARD,
                 fg=self.FG_MUTED, font=('Segoe UI', 9), anchor=tk.W
                 ).pack(side=tk.LEFT, padx=(12, 0))

        # paint from the cached state straight away, then ask the server
        self._apply_referral_state(self._referral_cached_state(), from_cache=True)
        self._refresh_invite_tab(True)

    def _referral_cached_state(self):
        client = self._referral_client()
        if client is None:
            return {}
        try:
            return client.referral_state(refresh=False)
        except Exception:
            return {}

    def _open_referral_terms(self):
        import webbrowser
        url = str((self._ref_state or {}).get('terms_url') or '')
        if not url:
            url = self._api_base() + '/referral-terms.php'
        try:
            webbrowser.open_new_tab(url)
        except Exception:
            pass

    def _refresh_invite_tab(self, from_server=False):
        """Fetch the referral state off the UI thread, then apply it."""
        if getattr(self, 'invite_tab', None) is None:
            return
        client = self._referral_client()
        if client is None:
            return
        if not from_server:
            self._apply_referral_state(self._referral_cached_state(), from_cache=True)
            return
        try:
            self._ref_status_var.set('Checking...')
        except Exception:
            pass

        def work():
            try:
                state = client.referral_state(refresh=True)
            except Exception:
                state = {}
            try:
                self.root.after(0, lambda: self._apply_referral_state(state))
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _apply_referral_state(self, state, from_cache=False):
        """Paint the Invite tab. Never raises."""
        if getattr(self, 'invite_tab', None) is None:
            return
        state = state or {}
        self._ref_state = state
        try:
            threshold = int(state.get('threshold', 5) or 5)
        except Exception:
            threshold = 5
        try:
            count = int(state.get('confirmed_count', 0) or 0)
        except Exception:
            count = 0
        identified = bool(state.get('identified')) and bool(state.get('referral_link'))

        try:
            if identified:
                self._ref_link_var.set(str(state.get('referral_link', '')))
                self._ref_email_frame.pack_forget()
                self._ref_link_frame.pack(fill=tk.X, padx=18, pady=(0, 4))
                self._ref_copy_btn.state(['!disabled'])
            else:
                self._ref_link_var.set('')
                self._ref_link_frame.pack_forget()
                self._ref_email_frame.pack(fill=tk.X, padx=18, pady=(0, 4))
        except Exception:
            pass

        try:
            self._ref_progress_var.set('%d of %d referrals' % (count, threshold))
            self._ref_bar.configure(maximum=max(1, threshold),
                                    value=max(0, min(count, threshold)))
        except Exception:
            pass

        # status line
        msg = ''
        if state.get('enabled') is False:
            msg = 'The referral programme is not running at the moment.'
        elif state.get('offline'):
            msg = 'Offline - showing the last known numbers.' if identified \
                else 'Offline - connect to get your invite link.'
        elif state.get('reward_status') == 'pro_granted':
            msg = 'Reward granted: your Pro licence is active.'
        elif identified:
            remaining = max(0, threshold - count)
            msg = 'Share your link. %d more to go.' % remaining if remaining \
                else 'You have reached the goal.'
        elif from_cache:
            msg = ''
        try:
            self._ref_status_var.set(msg)
        except Exception:
            pass

    def _copy_referral_link(self):
        link = ''
        try:
            link = self._ref_link_var.get().strip()
        except Exception:
            pass
        if not link:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(link)
            self.root.update_idletasks()
        except Exception:
            self._ref_status_var.set('Could not reach the clipboard. Select the link and copy it.')
            return
        # visible confirmation on the button itself, then back after 2 s
        try:
            self._ref_copy_btn.configure(text='Copied!')
            self._ref_status_var.set('Invite link copied to the clipboard.')
            self.root.after(2000, lambda: self._ref_copy_btn.configure(text='Copy link'))
        except Exception:
            pass

    def _register_referral_email(self):
        client = self._referral_client()
        if client is None:
            return
        email = ''
        try:
            email = self._ref_email_var.get().strip()
        except Exception:
            pass
        if not email:
            self._ref_status_var.set('Enter your email address first.')
            return
        self._ref_status_var.set('Setting up your invite link...')

        def work():
            try:
                ok, msg = client.referral_register(email)
            except Exception as exc:
                ok, msg = False, str(exc)
            state = {}
            if ok:
                try:
                    state = client.referral_state(refresh=False)
                except Exception:
                    state = {}

            def done():
                if ok:
                    self._apply_referral_state(state)
                    self._ref_status_var.set(msg or 'Your invite link is ready.')
                else:
                    self._ref_status_var.set(msg or 'That did not work.')

            try:
                self.root.after(0, done)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    # ---- launch popups ------------------------------------------------
    def _referral_launch_check(self):
        """At startup: ask the server once, then show at most one popup.

        Offline is skipped silently (spec 2.5) - the popup simply appears
        the next time the server can be reached.
        """
        client = self._referral_client()
        if client is None:
            return

        def work():
            try:
                state = client.referral_state(refresh=True)
            except Exception:
                return
            try:
                self.root.after(0, lambda: self._referral_popups_for(state))
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _referral_popups_for(self, state):
        state = state or {}
        if state.get('offline') or not state.get('identified'):
            return
        try:
            self._apply_referral_state(state)
        except Exception:
            pass
        # the reward popup wins: it is the bigger news, and its "seen" call
        # marks the new-referral popup as seen at the same time
        if state.get('reward_popup_pending'):
            self._referral_reward_popup(state)
            return
        try:
            unseen = int(state.get('new_unseen_count', 0) or 0)
        except Exception:
            unseen = 0
        if unseen > 0:
            self._referral_new_popup(state)

    def _referral_mark_seen_async(self, reward=False):
        client = self._referral_client()
        if client is None:
            return

        def work():
            try:
                client.referral_mark_seen(reward=reward)
            except Exception:
                pass
            try:
                self.root.after(0, lambda: self._refresh_invite_tab(False))
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _referral_new_popup(self, state):
        """Popup 1: one popup for the whole batch, never one per referral."""
        try:
            count = int(state.get('confirmed_count', 0) or 0)
            threshold = int(state.get('threshold', 5) or 5)
        except Exception:
            count, threshold = 0, 5
        remaining = max(0, threshold - count)
        cash = str(state.get('cash_amount', '15'))
        body = ('Someone registered with your referral link.\n\n'
                'You have %d of %d. You need %d more to get $%s or a Pro License.'
                % (count, threshold, remaining, cash))
        self._referral_popup('Congratulations!', body,
                             on_close=lambda: self._referral_mark_seen_async(False))

    def _referral_reward_popup(self, state):
        """Popup 2: the reward was granted server-side. Shown once."""
        try:
            threshold = int(state.get('threshold', 5) or 5)
        except Exception:
            threshold = 5
        body = ('You invited %d people. Your Pro License has been activated '
                'automatically.\n\nThere is no key to enter - it is already on your '
                'account. The new plan takes effect right away.' % threshold)

        def after():
            self._referral_mark_seen_async(True)
            # pick the new plan up now, so the unlocked features are live
            # without a restart
            self._refresh_plan_after_reward()

        self._referral_popup('Congratulations!', body, on_close=after)

    def _refresh_plan_after_reward(self):
        """Re-check in, then repaint the plan UI. The next profile launch
        picks up the new plan on its own, because the injector is rebuilt
        every time a profile starts."""
        client = self._referral_client()
        if client is None:
            return

        def work():
            try:
                client.check_in()
            except Exception:
                pass
            try:
                self.root.after(0, self._refresh_plan_ui)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _referral_popup(self, title, message, on_close=None):
        """The referral popup. Same shape as the Free-feature dialog, so it
        looks like the rest of the tool."""
        try:
            win = tk.Toplevel(self.root)
        except Exception:
            if on_close:
                on_close()
            return
        win.title(title)
        win.configure(bg=self.BG_CARD)
        win.resizable(False, False)
        try:
            win.transient(self.root)
        except Exception:
            pass

        body = tk.Frame(win, bg=self.BG_CARD)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=(18, 0))
        tk.Label(body, text=title, bg=self.BG_CARD, fg=self.FG,
                 font=('Segoe UI', 13, 'bold'), anchor=tk.W).pack(fill=tk.X)
        tk.Label(body, text=message, bg=self.BG_CARD, fg=self.FG_MUTED,
                 font=('Segoe UI', 10), justify=tk.LEFT, wraplength=360,
                 anchor=tk.W).pack(fill=tk.X, pady=(8, 0))

        btns = tk.Frame(win, bg=self.BG_CARD)
        btns.pack(fill=tk.X, padx=20, pady=(14, 18))

        done = {'called': False}

        def _close():
            if not done['called']:
                done['called'] = True
                try:
                    if on_close:
                        on_close()
                except Exception:
                    pass
            try:
                win.grab_release()
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass

        ttk.Button(btns, text='OK', style='Accent.TButton', width=9,
                   command=_close).pack(side=tk.RIGHT)
        ttk.Button(btns, text='Open Invite tab', style='Ghost.TButton',
                   command=lambda: (_close(), self._show_invite_tab())
                   ).pack(side=tk.RIGHT, padx=(0, 6))

        win.protocol('WM_DELETE_WINDOW', _close)
        win.bind('<Return>', lambda e: _close())
        win.bind('<Escape>', lambda e: _close())
        try:
            win.geometry('420x200')
            win.minsize(420, 200)
        except Exception:
            pass
        try:
            self._center_popup(win)
        except Exception:
            pass

    def _show_invite_tab(self):
        try:
            if getattr(self, 'invite_tab', None) is not None:
                self.notebook.select(self.invite_tab)
                self._refresh_invite_tab(True)
        except Exception:
            pass

    # ==================================================================
    # v6.1  remote application control: mandatory update + block popups
    # ==================================================================
    def _check_app_control(self):
        """Watch the signed check-in state and react to it.

        Priority: a required update, then the master switch, then an optional
        update (offered once per version per session). Polls for the life of
        the window, so a switched-off app recovers on its own when the
        administrator switches it back on - no restart needed.
        """
        client = None
        try:
            client = self.generator.license()
        except Exception:
            client = None
        if client is None:
            return  # developer build without the licensing module: do nothing
        try:
            if not getattr(self, '_app_control_shown', False):
                if client.needs_update():
                    self._app_control_shown = True
                    self._show_update_dialog(client, mandatory=True)
                elif client.is_blocked_by_admin():
                    self._app_control_shown = True
                    self._show_application_disabled(client)
                elif (client.has_update()
                      and not getattr(self, '_update_dialog_open', False)
                      and getattr(self, '_update_snoozed', None) != client.latest_version):
                    self._show_update_dialog(client, mandatory=False)
        except Exception:
            pass
        try:
            self.root.after(15000, self._check_app_control)
        except Exception:
            pass

    def _show_update_required(self, client):
        """Older call sites: the mandatory form of the update dialog."""
        self._show_update_dialog(client, mandatory=True)

    def _ui_pump(self, win, q):
        """Run callables queued by worker threads, on the Tk thread."""
        try:
            while True:
                fn = q.get_nowait()
                try:
                    fn()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if win.winfo_exists():
                win.after(120, lambda: self._ui_pump(win, q))
        except Exception:
            pass

    def _show_update_dialog(self, client, mandatory=False):
        """Optional or required update, with release notes and a verified
        in-app download.

        'Update now' downloads the installer, checks its SHA-256 against the
        checksum published in the signed check-in, then starts it and closes
        the tool. If no checksum was published the file cannot be verified, so
        the dialog opens the download page instead of fetching it.
        """
        import queue as _queue
        try:
            info = client.update_details()
        except Exception:
            info = {'current': '', 'latest': getattr(client, 'latest_version', ''),
                    'notes': '', 'verifiable': False, 'url': client.update_download_url()}
        self._update_dialog_open = True
        q = _queue.Queue()
        cancel = threading.Event()
        busy = {'on': False}

        win = tk.Toplevel(self.root)
        win.title('Update required' if mandatory else 'Update available')
        win.configure(bg=self.BG_CARD)
        win.resizable(False, False)
        win.transient(self.root)
        if mandatory:
            try:
                win.grab_set()   # the tool cannot be used behind a required update
            except Exception:
                pass

        def later():
            cancel.set()
            self._update_dialog_open = False
            self._update_snoozed = info.get('latest', '')
            try:
                win.destroy()
            except Exception:
                pass

        def quit_app():
            cancel.set()
            try:
                win.destroy()
            finally:
                self._hard_exit()

        win.protocol('WM_DELETE_WINDOW', quit_app if mandatory else later)

        tk.Label(win, text=('\u26A0  Update required' if mandatory
                            else '\u2B06  A new version is available'),
                 bg=self.BG_CARD, fg=self.FG, font=('Segoe UI', 15, 'bold')
                 ).pack(padx=28, pady=(22, 4), anchor=tk.W)
        tk.Label(win, bg=self.BG_CARD, fg=self.FG_MUTED, font=('Segoe UI', 10),
                 wraplength=440, justify=tk.LEFT,
                 text=('This version can no longer be used. Install the update to continue.'
                       if mandatory else
                       'Install it now, or keep working and update later.')
                 ).pack(padx=28, anchor=tk.W)
        tk.Label(win, bg=self.BG_CARD, fg=self.FG, font=('Segoe UI', 9, 'bold'),
                 text='Installed: %s     Latest: %s' % (info.get('current') or '?',
                                                        info.get('latest') or '?')
                 ).pack(padx=28, pady=(10, 2), anchor=tk.W)

        notes = (info.get('notes') or '').strip()
        if notes:
            box = tk.Frame(win, bg=self.BG_CARD)
            box.pack(padx=28, pady=(6, 2), fill=tk.X)
            txt = tk.Text(box, height=min(10, max(3, notes.count('\n') + 2)), width=58,
                          wrap=tk.WORD, relief=tk.FLAT, bg=self.BG_CARD_2, fg=self.FG,
                          font=('Segoe UI', 9), padx=8, pady=6)
            bar_y = ttk.Scrollbar(box, orient=tk.VERTICAL, command=txt.yview)
            txt.configure(yscrollcommand=bar_y.set)
            txt.insert('1.0', "What's new\n\n" + notes)
            txt.configure(state=tk.DISABLED)
            txt.pack(side=tk.LEFT, fill=tk.X, expand=True)
            bar_y.pack(side=tk.RIGHT, fill=tk.Y)

        bar = ttk.Progressbar(win, mode='determinate', maximum=100, length=440)
        status = tk.StringVar(value='' if info.get('verifiable') else
                              'This update is downloaded from the website.')
        status_lbl = tk.Label(win, textvariable=status, bg=self.BG_CARD,
                              fg=self.FG_MUTED, font=('Segoe UI', 9),
                              wraplength=440, justify=tk.LEFT)
        status_lbl.pack(padx=28, pady=(8, 0), anchor=tk.W)
        btns = tk.Frame(win, bg=self.BG_CARD)
        btns.pack(padx=28, pady=(14, 22), anchor=tk.E)

        def open_page():
            url = info.get('url') or (self._api_base() + '/docs.php#install')
            try:
                import webbrowser
                webbrowser.open_new_tab(url)
            except Exception:
                pass
            if mandatory:
                quit_app()
            else:
                later()

        def progress(done, total):          # worker thread
            def ui():
                if total:
                    bar['value'] = int(done * 100 / total)
                    status.set('Downloading\u2026 %d%%  (%.1f of %.1f MB)'
                               % (bar['value'], done / 1048576.0, total / 1048576.0))
                else:
                    status.set('Downloading\u2026 %.1f MB' % (done / 1048576.0))
            q.put(ui)

        def finished(ok, result):           # Tk thread
            busy['on'] = False
            if not win.winfo_exists():
                return
            if ok:
                bar['value'] = 100
                status.set('Verified. Starting the installer\u2026')
                started, msg = client.launch_installer(result)
                if started:
                    status.set('The installer is running. '
                               + self.generator.TOOL_NAME + ' will close now.')
                    self.root.after(1500, self._hard_exit)
                    return
                result = msg
            status_lbl.configure(fg=self.DANGER)
            status.set(result)
            update_btn.configure(state=tk.NORMAL, text='Try again')
            if not page_btn.winfo_ismapped():
                page_btn.pack(side=tk.LEFT, padx=(8, 0), before=second_btn)

        def start_download():
            if busy['on']:
                return
            busy['on'] = True
            cancel.clear()
            status_lbl.configure(fg=self.FG_MUTED)
            status.set('Starting the download\u2026')
            bar['value'] = 0
            if not bar.winfo_ismapped():
                bar.pack(padx=28, pady=(10, 0), anchor=tk.W, before=status_lbl)
            update_btn.configure(state=tk.DISABLED)

            def work():
                ok, result = client.download_update(progress=progress, cancel=cancel)
                q.put(lambda: finished(ok, result))
            threading.Thread(target=work, daemon=True).start()

        if info.get('verifiable'):
            update_btn = ttk.Button(btns, text='Update now', style='Accent.TButton',
                                    command=start_download)
        else:
            update_btn = ttk.Button(btns, text='Open download page',
                                    style='Accent.TButton', command=open_page)
        update_btn.pack(side=tk.LEFT)
        page_btn = ttk.Button(btns, text='Download from website',
                              style='Ghost.TButton', command=open_page)
        second_btn = ttk.Button(btns, text='Quit' if mandatory else 'Later',
                                style='Ghost.TButton',
                                command=quit_app if mandatory else later)
        second_btn.pack(side=tk.LEFT, padx=(8, 0))
        self._ui_pump(win, q)
        self._center_popup(win)

    def _show_application_disabled(self, client):
        """Modal while the administrator has the application switched off.

        Nothing can be used behind it. It closes by itself as soon as the
        application is switched back on (the background check-in learns that),
        and 'Check again' asks the server immediately. 'Close app' exits.
        """
        import queue as _queue
        msg = 'The application is temporarily disabled by the administrator.'
        try:
            msg = client.blocked_reason() or msg
        except Exception:
            pass
        q = _queue.Queue()
        win = tk.Toplevel(self.root)
        win.title('Application disabled')
        win.configure(bg=self.BG_CARD)
        win.resizable(False, False)
        win.transient(self.root)
        try:
            win.grab_set()
        except Exception:
            pass

        def quit_app():
            try:
                win.destroy()
            finally:
                self._hard_exit()
        win.protocol('WM_DELETE_WINDOW', quit_app)

        tk.Label(win, text='\u26D4  Application disabled', bg=self.BG_CARD,
                 fg=self.FG, font=('Segoe UI', 15, 'bold')
                 ).pack(padx=28, pady=(22, 8), anchor=tk.W)
        tk.Label(win, bg=self.BG_CARD, fg=self.FG, font=('Segoe UI', 10),
                 justify=tk.LEFT, wraplength=400, text=msg
                 ).pack(padx=28, pady=(0, 8), anchor=tk.W)
        status = tk.StringVar(value='This window closes by itself when the '
                                    'application is switched back on.')
        tk.Label(win, textvariable=status, bg=self.BG_CARD, fg=self.FG_MUTED,
                 font=('Segoe UI', 9), justify=tk.LEFT, wraplength=400
                 ).pack(padx=28, anchor=tk.W)
        btns = tk.Frame(win, bg=self.BG_CARD)
        btns.pack(padx=28, pady=(14, 22), anchor=tk.E)

        def back_on():
            try:
                win.grab_release()
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass
            self._app_control_shown = False
            self._refresh_plan_ui()
            try:
                self.status_var.set('The application is available again.')
            except Exception:
                pass

        def watch():
            if not win.winfo_exists():
                return
            try:
                if client.app_allowed():
                    back_on()
                    return
            except Exception:
                pass
            win.after(3000, watch)

        def checked():
            if not win.winfo_exists():
                return
            check_btn.configure(state=tk.NORMAL)
            try:
                if client.app_allowed():
                    back_on()
                    return
            except Exception:
                pass
            status.set('Still switched off. This window keeps checking automatically.')

        def check_now():
            check_btn.configure(state=tk.DISABLED)
            status.set('Checking with the server\u2026')

            def work():
                try:
                    client.check_in()
                except Exception:
                    pass
                q.put(checked)
            threading.Thread(target=work, daemon=True).start()

        check_btn = ttk.Button(btns, text='Check again', style='Accent.TButton',
                               command=check_now)
        check_btn.pack(side=tk.LEFT)
        ttk.Button(btns, text='Close app', style='Ghost.TButton',
                   command=quit_app).pack(side=tk.LEFT, padx=(8, 0))
        self._ui_pump(win, q)
        watch()
        self._center_popup(win)

    def _center_popup(self, win):
        try:
            win.update_idletasks()
            rx = self.root.winfo_rootx(); ry = self.root.winfo_rooty()
            rw = self.root.winfo_width(); rh = self.root.winfo_height()
            w = win.winfo_reqwidth(); h = win.winfo_reqheight()
            x = rx + max(0, (rw - w) // 2); y = ry + max(0, (rh - h) // 3)
            win.geometry('+%d+%d' % (x, y))
            win.lift(); win.focus_force()
        except Exception:
            pass

    def _hard_exit(self):
        """Stop normal operation: halt the heartbeat and close the window."""
        try:
            client = self.generator.license()
            if client is not None:
                client.stop_background()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    # ==================================================================
    # v7.0.0  DPI AWARENESS AND WINDOW GEOMETRY
    #
    # Everything here is new. No existing method was changed to add it; the
    # two original geometry() / minsize() calls in __init__ are still there
    # and still run first, and these only re-apply the same intent in terms
    # of the real screen.
    # ==================================================================
    def _measure_dpi(self):
        """Work out the display scale and tell Tk about it.

        winfo_fpixels('1i') reports how many pixels Tk thinks an inch is:
        96 at 100%, 120 at 125%, 144 at 150%. `tk scaling` is points to
        pixels, so it is that figure over 72. At 100% this computes Tk's own
        Windows default, so nothing moves on a normal display.
        """
        scale = 1.0
        try:
            dpi = float(self.root.winfo_fpixels('1i'))
            if dpi > 0:
                scale = max(1.0, min(3.0, dpi / 96.0))
                self.root.tk.call('tk', 'scaling', dpi / 72.0)
        except Exception:
            scale = 1.0
        self._dpi_scale = scale
        return scale

    def _px(self, value):
        """A logical pixel count scaled for the current display.

        Used for the few hard-coded pixel sizes in the layout. Without it a
        minsize of 330 px stays 330 px at 150% while the text inside it grows
        by half, which is what made the Desktop icon / Fingerprint row
        collide.
        """
        try:
            return int(round(float(value) * float(getattr(self, '_dpi_scale', 1.0) or 1.0)))
        except Exception:
            return int(value)

    def _apply_adaptive_geometry(self):
        """Size the window for this screen, at this scaling.

        The preferred size is the original 1060x680 scaled up, and the
        minimum is a size the layout is known to survive - but BOTH are
        clamped to what the screen can actually show, so the window can
        never open larger than the desktop and can never be given a minimum
        the user is unable to satisfy.
        """
        root = self.root
        try:
            screen_w = int(root.winfo_screenwidth())
            screen_h = int(root.winfo_screenheight())
        except Exception:
            return
        # leave room for the taskbar and the window border
        avail_w = max(640, screen_w - 40)
        avail_h = max(480, screen_h - 80)

        want_w = min(self._px(1060), avail_w)
        want_h = min(self._px(680), avail_h)
        # 1000x660 logical is the smallest size at which the Profiles tab
        # still shows the configuration panel and the browser list side by
        # side without either becoming unusable.
        min_w = min(self._px(1000), avail_w)
        min_h = min(self._px(660), avail_h)

        try:
            root.minsize(min_w, min_h)
            root.geometry('%dx%d' % (max(want_w, min_w), max(want_h, min_h)))
        except Exception:
            pass

    def _on_close(self):
        """Window close: stop remote tab modules, then behave as before.

        The root window had no close handler before, so the default was a
        plain destroy; that is preserved at the end.
        """
        try:
            host = getattr(self, 'tab_host', None)
            if host is not None:
                host.shutdown()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    # ==================================================================
    # v7.0.0  SERVER-CONTROLLED TABS
    #
    # The tool hosts them; the website defines them. All of this is
    # additive: the Profiles, Invite and USA Timer tabs are untouched, and
    # every path here fails soft.
    # ==================================================================
    def _build_remote_tabs(self):
        """Create the tab host and let it populate the notebook."""
        self.tab_host = None
        if _tabs is None:
            return
        if getattr(self, 'notebook', None) is None:
            return
        host = _tabs.TabHost(self)
        self.tab_host = host
        host.build()
        try:
            self.notebook.bind('<<NotebookTabChanged>>',
                               self._on_notebook_tab_changed, add='+')
        except Exception:
            pass
        # v7.0.1: do one guaranteed post-start refresh after the Tk event loop
        # is alive. The host already performs its normal async refresh; this
        # delayed call is only a recovery path for a first request that raced
        # application startup or failed before the window became responsive.
        try:
            self.root.after(1200, self._refresh_remote_tabs)
        except Exception:
            pass

    def _on_notebook_tab_changed(self, _event=None):
        """Drive on_show() / on_hide() for remote modules.

        Bound with add='+', so any handler the notebook already had keeps
        working.
        """
        host = getattr(self, 'tab_host', None)
        if host is None:
            return
        try:
            current = self.notebook.nametowidget(self.notebook.select())
        except Exception:
            return
        try:
            host.on_tab_changed(current)
        except Exception:
            pass

    def _refresh_remote_tabs(self):
        """The manual "Refresh tabs" action.

        Picks up a rename, a new tab, a removed tab or a plan change without
        restarting the tool.
        """
        host = getattr(self, 'tab_host', None)
        if host is None:
            return
        try:
            host.refresh_async()
        except Exception as exc:
            self.log('[tabs] refresh failed: %r' % (exc,))

    def _ensure_tabs_refresh_button(self):
        """Show the Refresh tabs control, but only once there is a remote tab.

        The header bar is already busy, so nothing is added to it for an
        installation that has no server-defined tabs at all.
        """
        holder = getattr(self, '_tabs_btns', None)
        if holder is None:
            return
        if getattr(self, '_tabs_refresh_btn', None) is not None:
            return
        try:
            btn = ttk.Button(holder, text='\u27f3', style='Icon.TButton', width=3,
                             command=self._refresh_remote_tabs)
            btn.pack(side=tk.LEFT)
            self._tabs_refresh_btn = btn
        except Exception:
            self._tabs_refresh_btn = None

    def _create_widgets(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        # ---------- header -------------------------------------------
        header = tk.Frame(self.root, bg=self.HEADER)
        header.grid(row=0, column=0, sticky=(tk.W, tk.E))
        header.columnconfigure(1, weight=1)

        tk.Label(header, text="Chrome Profile Generator", bg=self.HEADER,
                 fg=self.FG, font=('Segoe UI', 17, 'bold')
                 ).grid(row=0, column=0, sticky=tk.W, padx=16, pady=(12, 10))

        tools = tk.Frame(header, bg=self.HEADER)
        tools.grid(row=0, column=2, sticky=tk.E, padx=14)
        ttk.Button(tools, text="About", style='Ghost.TButton',
                   command=self._show_about).pack(side=tk.LEFT, padx=(0, 8))
        # v7.0.0: holder for the "Refresh tabs" control. Stays empty - and so
        # invisible - unless this installation actually has server-defined
        # tabs, so nothing is added to the header for anyone who does not.
        self._tabs_btns = tk.Frame(tools, bg=self.HEADER)
        self._tabs_btns.pack(side=tk.LEFT, padx=(0, 8))
        self._tabs_refresh_btn = None
        # v6.0 licensing buttons - shown before About
        # v6.3.3: language selector, beside the plan controls
        self._lang_btns = tk.Frame(tools, bg=self.HEADER)
        self._lang_btns.pack(side=tk.LEFT, padx=(0, 10))
        self._build_language_buttons()
        self._license_btns = tk.Frame(tools, bg=self.HEADER)
        self._license_btns.pack(side=tk.LEFT, padx=(0, 8))
        self._build_license_buttons()
        ttk.Button(tools, text="\u2600", style='Icon.TButton', width=3,
                   command=lambda: self._toggle_theme('light')).pack(side=tk.LEFT)
        ttk.Button(tools, text="\u263D", style='Icon.TButton', width=3,
                   command=lambda: self._toggle_theme('dark')).pack(side=tk.LEFT,
                                                                    padx=(6, 0))

        # ---------- USA Timer banner (v6.3.4) ------------------------
        # Sits above the isolated-profiles banner, across the top of the
        # window. Built only when the plan is entitled AND the website has
        # sent the schedule - the tool alone does not know what to show.
        try:
            self._build_timer_banner()
        except Exception:
            self._timer_banner = None

        # ---------- banner -------------------------------------------
        banner = tk.Frame(self.root, bg=self.BANNER)
        self._banner_frame = banner
        banner.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=10, pady=(0, 8))
        self._register_text(
            tk.Label(banner, bg=self.BANNER, fg='#9fc2f0',
                     font=('Segoe UI', 10, 'bold')), 'banner.isolated'
        ).pack(side=self._side_start(), padx=(12, 8), pady=8)
        self._register_text(
            tk.Label(banner, bg=self.BANNER, fg='#ffffff',
                     font=('Segoe UI', 10, 'bold')), 'banner.isolated_text'
        ).pack(side=self._side_start(), pady=8)

        # ---------- tabs ---------------------------------------------
        # v6.0: user-script MANAGEMENT now lives on the website dashboard,
        # so the local "User Scripts" editor tab is gone. The desktop still
        # RECEIVES, caches and injects the scripts the server authorises for
        # this licence tier - only the create/edit/delete UI was removed.
        self.notebook = ttk.Notebook(self.root, style='TNotebook')
        self.notebook.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S),
                           padx=10)
        self.profiles_tab = ttk.Frame(self.notebook, style='TFrame', padding=8)
        self.notebook.add(self.profiles_tab, text='   Profiles   ')
        # v6.3: the referral programme gets its own tab beside Profiles.
        # The header bar is already full (About / plan pill / Upgrade /
        # Register licence / two theme buttons), so nothing is added there.
        # Built for EVERY plan, Free included.
        try:
            self._build_invite_tab()
        except Exception:
            self.invite_tab = None
        # v6.3.3: the USA Timer tab (Pro and Unlimited for Team)
        try:
            self._build_timer_tab()
        except Exception:
            self.timer_tab = None
        # v7.0.0: the widget tree is destroyed and rebuilt on a theme switch,
        # so the remote tabs have to be rebuilt with it. On the first call
        # __init__ has not reached _build_remote_tabs yet and there is no
        # host, which is why this is guarded rather than unconditional.
        if getattr(self, 'tab_host', None) is not None:
            try:
                self.tab_host.shutdown()
                self._build_remote_tabs()
            except Exception:
                self.tab_host = None

        tab = self.profiles_tab
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)

        columns = tk.Frame(tab, bg=self.BG)
        columns.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        # v7.0.0 (bug fix): these minimums were fixed pixel counts, so at 125%
        # and 150% DPI the text inside them grew while the columns did not -
        # which is what made the "Desktop icon" and "Fingerprint" switches
        # collide. Scaled, they hold their proportions at every DPI.
        columns.columnconfigure(0, weight=0, minsize=self._px(330))
        columns.columnconfigure(1, weight=1, minsize=self._px(420))
        columns.rowconfigure(0, weight=1)

        self._build_config_column(columns)
        self._build_browser_column(columns)
        # v4.4: the "All Desktop Browser" list column has been removed; a
        # hidden tree keeps the code that used to feed it from crashing.
        self._build_hidden_profile_store()

        # kept so the existing fingerprint panel still has a home
        self.fp_frame = tk.Frame(tab, bg=self.BG_CARD,
                                 highlightbackground=self.BORDER,
                                 highlightthickness=1, bd=0)


        # ---------- fingerprint summary ------------------------------
        summary = tk.Frame(self.root, bg=self.BG)
        summary.grid(row=3, column=0, sticky=(tk.W, tk.E), padx=10, pady=(8, 0))
        summary.columnconfigure(0, weight=1)
        self.summary_text = tk.Text(summary, height=3, bg=self.BG_CARD_2,
                                    fg=self.FG, font=('Consolas', 9),
                                    highlightthickness=1,
                                    highlightbackground=self.BORDER,
                                    borderwidth=0, wrap=tk.WORD)
        self.summary_text.grid(row=0, column=0, sticky=(tk.W, tk.E))
        self.summary_text.insert('1.0', '=== Fingerprint Summary ===\n'
                                        'Generate a profile to see its details here.')
        self.summary_text.configure(state=tk.DISABLED)

        # ---------- footer -------------------------------------------
        footer = tk.Frame(self.root, bg=self.BG)
        footer.grid(row=4, column=0, sticky=(tk.W, tk.E), padx=12, pady=8)
        footer.columnconfigure(1, weight=1)
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(footer, textvariable=self.status_var, bg=self.BG,
                 fg=self.FG_MUTED, font=('Segoe UI', 8)
                 ).grid(row=0, column=0, sticky=tk.W)
        # v6.0 licence status in the footer
        self._license_status_lbl = tk.Label(footer, text='',
                 bg=self.BG, fg=self.ACCENT, font=('Segoe UI', 8, 'bold'))
        self._license_status_lbl.grid(row=1, column=0, sticky=tk.W)
        tk.Label(footer, text=self.generator.profiles_dir, bg=self.BG,
                 fg=self.FG_MUTED, font=('Segoe UI', 8)
                 ).grid(row=0, column=1, sticky=tk.E)

    # ------------------------------------------------------------------
    def _build_config_column(self, parent):
        # ==============================================================
        # v7.0.0 BUG FIX — "Generate new profile" was cut off.
        #
        # WHAT WAS WRONG
        # The whole panel was one grid inside `card`, rows 0..12, with the
        # green action button on row 12. A Tk grid does not scroll: when the
        # contents are taller than the cell, the LAST rows are simply not
        # drawn. Opening the Language / screen size pools adds roughly 150 px,
        # which pushed row 12 past the bottom edge - so the button vanished
        # and the only way back was to zoom out or resize the window.
        #
        # WHAT CHANGED
        # `card` is now two rows: a scrolling viewport on row 0 and a fixed
        # action bar on row 1. Everything that used to be in `card` is now in
        # `body` INSIDE the viewport, at exactly the same row numbers, with
        # the same widgets, the same variables and the same attribute names -
        # so every other method that reaches into this panel still works
        # unchanged. The action bar is outside the scroll region, which is
        # what makes it impossible to clip: it is laid out before the
        # viewport is given whatever height is left over.
        #
        # The method keeps its name and its signature, and creates every
        # attribute it created before.
        # ==============================================================
        shell = tk.Frame(parent, bg=self.BG_CARD,
                         highlightbackground=self.BORDER, highlightthickness=1)
        shell.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 8))
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)      # viewport takes the slack
        shell.rowconfigure(1, weight=0)      # action bar keeps its height
        self._cfg_shell = shell

        # ---- scrolling viewport --------------------------------------
        view = tk.Canvas(shell, bg=self.BG_CARD, highlightthickness=0, bd=0)
        view.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        cfg_bar = ttk.Scrollbar(shell, orient=tk.VERTICAL, command=view.yview,
                                style='Vertical.TScrollbar')
        view.configure(yscrollcommand=lambda first, last:
                       self._cfg_scroll_sync(cfg_bar, first, last))
        self._cfg_view = view
        self._cfg_bar = cfg_bar

        body = tk.Frame(view, bg=self.BG_CARD)
        self._cfg_body = body
        body_window = view.create_window((0, 0), window=body, anchor='nw')
        body.columnconfigure(0, weight=1)
        body.rowconfigure(11, weight=1)

        def _body_resized(_event=None):
            try:
                view.configure(scrollregion=view.bbox('all'))
            except Exception:
                pass

        def _view_resized(event):
            # keep the inner frame as wide as the viewport, so widgets that
            # stretch with sticky=(W, E) fill the panel instead of hugging
            # the left edge
            try:
                view.itemconfigure(body_window, width=event.width)
            except Exception:
                pass

        body.bind('<Configure>', _body_resized)
        view.bind('<Configure>', _view_resized)
        # The wheel is bound on enter and released on leave, so scrolling
        # over the Browser Profiles list next door is never stolen.
        view.bind('<Enter>', lambda e: self._cfg_wheel_bind(True))
        view.bind('<Leave>', lambda e: self._cfg_wheel_bind(False))
        self._cfg_wheel_on = False

        self._register_text(
            tk.Label(body, bg=self.BG_CARD, fg=self.FG, font=('Segoe UI', 11)),
            'cfg.title').grid(row=0, column=0, sticky=self._anchor(),
                              padx=12, pady=(8, 6))

        card = body          # everything below builds into the scrolling body
        box = tk.Frame(card, bg=self.BG_CARD_2,
                       highlightbackground=self.BORDER, highlightthickness=1)
        box.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=14)
        box.columnconfigure(1, weight=1)
        self._register_text(
            tk.Label(box, bg=self.BG_CARD_2, fg=self.FG, font=('Segoe UI', 9)),
            'cfg.name').grid(row=0, column=0, padx=(10, 8), pady=10)
        self.profile_name_var = tk.StringVar()
        ttk.Entry(box, textvariable=self.profile_name_var
                  ).grid(row=0, column=1, sticky=(tk.W, tk.E), pady=10)
        tk.Label(box, text="Count", bg=self.BG_CARD_2, fg=self.FG,
                 font=('Segoe UI', 9)).grid(row=0, column=2, padx=(10, 6))
        self.num_profiles_var = tk.StringVar(value="1")
        self.profile_count_var = self.num_profiles_var   # old alias
        ttk.Spinbox(box, from_=1, to=100, width=4,
                    textvariable=self.num_profiles_var
                    ).grid(row=0, column=3, padx=(0, 10))

        # v4.4: choose which browser new profiles are generated for
        engine = tk.Frame(card, bg=self.BG_CARD_2,
                          highlightbackground=self.BORDER, highlightthickness=1)
        engine.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=12, pady=(8, 0))
        tk.Label(engine, text="Generate with", bg=self.BG_CARD_2,
                 fg=self.FG_MUTED, font=('Segoe UI', 8, 'bold')
                 ).pack(side=tk.LEFT, padx=(10, 10), pady=9)
        # Firefox removed: profiles are always generated for Chrome
        self.browser_kind_chrome = tk.BooleanVar(value=True)
        self.browser_kind_firefox = tk.BooleanVar(value=False)
        tk.Label(engine, text="Google Chrome",
                 bg=self.BG_CARD_2, fg=self.FG,
                 font=('Segoe UI', 9, 'bold')).pack(side=tk.LEFT, pady=9)
        tk.Label(engine, text="   (user scripts need Chrome)",
                 bg=self.BG_CARD_2, fg=self.FG_MUTED,
                 font=('Segoe UI', 8)).pack(side=tk.LEFT, pady=9)

        # v7.0.0 (bug fix): these two switches were packed side by side with
        # side=tk.LEFT. Pack gives each child its requested width and simply
        # runs off the end when the frame is too narrow, so at 125% and 150%
        # DPI - where the captions grow but the 330 px column did not - the
        # "Fingerprint" switch was drawn over the "Desktop icon" caption.
        #
        # Grid cannot overlap: two equal columns, and a Configure handler
        # that stacks them vertically when there genuinely is not room for
        # both. Same widgets, same variables, same attribute names.
        toggles = tk.Frame(card, bg=self.BG_CARD_2,
                           highlightbackground=self.BORDER, highlightthickness=1)
        toggles.grid(row=3, column=0, sticky=(tk.W, tk.E), padx=12, pady=7)
        toggles.columnconfigure(0, weight=1, uniform='cfgtoggle')
        toggles.columnconfigure(1, weight=1, uniform='cfgtoggle')
        self.create_shortcut_var = tk.BooleanVar(value=True)
        self.show_fp_var = tk.BooleanVar(value=False)
        self.show_fingerprint_var = self.show_fp_var        # old alias
        self._shortcut_switch = LabeledSwitch(
            toggles, text="Desktop icon",
            variable=self.create_shortcut_var, bg=self.BG_CARD_2,
            fg=self.FG, switch_width=42, switch_height=22)
        self._shortcut_switch.grid(row=0, column=0, sticky=tk.W,
                                   padx=(12, 6), pady=9)
        self._fp_switch = LabeledSwitch(toggles, text="Fingerprint",
                      variable=self.show_fp_var, bg=self.BG_CARD_2,
                      fg=self.FG, switch_width=42, switch_height=22)
        self._fp_switch.grid(row=0, column=1, sticky=tk.W, padx=(6, 12), pady=9)
        self._toggles_frame = toggles
        self._toggles_stacked = False
        toggles.bind('<Configure>', self._reflow_toggles)

        tk.Label(card, text="Language / Screen Size", bg=self.BG_CARD, fg=self.FG,
                 font=('Segoe UI', 11)).grid(row=4, column=0, sticky=tk.W,
                                             padx=12, pady=(2, 4))
        self._build_selection_card(card, 5)
        try:
            if not getattr(self, 'pools_open', False):
                self._toggle_pools()
        except Exception:
            pass

        self.browser_label_var = tk.StringVar(value="")
        self.browser_caption = tk.Label(
            card, textvariable=self.browser_label_var, bg=self.BG_CARD,
            fg=self.FG_MUTED, font=('Segoe UI', 8), anchor=tk.W,
            justify=tk.LEFT, wraplength=300)
        self.browser_caption.grid(row=11, column=0, sticky=(tk.W, tk.S), padx=14)
        self._refresh_browser_caption()

        # ---- the action bar: PINNED, never clipped --------------------
        # Note the parent: `shell`, not `card`/`body`. It sits on shell's
        # row 1, outside the scrolling viewport, so the grid gives it its
        # full requested height first and the viewport takes what is left.
        # There is no arrangement of the panel above that can push it off
        # the bottom - which was the whole bug.
        actions = tk.Frame(shell, bg=self.BG_CARD)
        actions.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=12, pady=(6, 10))
        actions.columnconfigure(0, weight=1)
        self._generate_btn = ttk.Button(
            actions, text="Generate New Profile", style='Go.TButton',
            command=self._generate_profiles)
        self._generate_btn.grid(row=0, column=0, sticky=(tk.W, tk.E))

    # ------------------------------------------------------------------
    # v7.0.0: helpers for the scrolling configuration panel (all new)
    # ------------------------------------------------------------------
    def _cfg_scroll_sync(self, bar, first, last):
        """Show the scrollbar only when the panel actually overflows.

        Without this the bar is always present and steals ~16 px from an
        already narrow column even when everything fits.
        """
        try:
            if float(first) <= 0.0 and float(last) >= 1.0:
                bar.grid_remove()
            else:
                bar.grid(row=0, column=1, sticky=(tk.N, tk.S))
            bar.set(first, last)
        except Exception:
            pass

    def _cfg_wheel_bind(self, on):
        """Bind the mouse wheel only while the pointer is over the panel."""
        view = getattr(self, '_cfg_view', None)
        if view is None:
            return
        if on and not getattr(self, '_cfg_wheel_on', False):
            self._cfg_wheel_on = True
            for seq, fn in (('<MouseWheel>', self._cfg_wheel),
                            ('<Button-4>', self._cfg_wheel_x11),
                            ('<Button-5>', self._cfg_wheel_x11)):
                try:
                    view.bind_all(seq, fn)
                except Exception:
                    pass
        elif not on and getattr(self, '_cfg_wheel_on', False):
            self._cfg_wheel_on = False
            for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                try:
                    view.unbind_all(seq)
                except Exception:
                    pass

    def _cfg_wheel(self, event):
        try:
            self._cfg_view.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        except Exception:
            pass

    def _cfg_wheel_x11(self, event):
        try:
            self._cfg_view.yview_scroll(-1 if event.num == 4 else 1, 'units')
        except Exception:
            pass

    def _reflow_toggles(self, event=None):
        """Stack the Desktop icon / Fingerprint switches when they will not
        fit side by side, instead of letting them collide.

        Measured, not guessed: the two switches report what they actually
        need at the current font size and DPI, so this behaves correctly at
        100%, 125% and 150% without a hard-coded breakpoint.
        """
        toggles = getattr(self, '_toggles_frame', None)
        first = getattr(self, '_shortcut_switch', None)
        second = getattr(self, '_fp_switch', None)
        if toggles is None or first is None or second is None:
            return
        try:
            width = event.width if event is not None else toggles.winfo_width()
            needed = first.winfo_reqwidth() + second.winfo_reqwidth() + self._px(36)
            stack = width > 1 and width < needed
            if stack == getattr(self, '_toggles_stacked', False):
                return
            self._toggles_stacked = stack
            if stack:
                first.grid_configure(row=0, column=0, columnspan=2,
                                     padx=(12, 12), pady=(9, 2))
                second.grid_configure(row=1, column=0, columnspan=2,
                                      padx=(12, 12), pady=(0, 9))
            else:
                first.grid_configure(row=0, column=0, columnspan=1,
                                     padx=(12, 6), pady=9)
                second.grid_configure(row=0, column=1, columnspan=1,
                                      padx=(6, 12), pady=9)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # v4.4: Chrome / Firefox chooser (radio-style switches)
    # ------------------------------------------------------------------
    def _sync_browser_switches(self, kind):
        self._suppress_browser_cmd = True
        try:
            self.browser_kind_chrome.set(kind == 'chrome')
            self.browser_kind_firefox.set(kind == 'firefox')
        finally:
            self._suppress_browser_cmd = False

    def _apply_browser_kind(self, kind):
        kind = 'firefox' if kind == 'firefox' else 'chrome'
        path = (self.generator._find_firefox_path() if kind == 'firefox'
                else self.generator._find_chrome_path())
        if not path:
            want = 'Firefox' if kind == 'firefox' else 'Google Chrome'
            messagebox.showwarning(
                "%s not found" % want,
                "%s was not found on this system.\n\n"
                "Install it first, or pick its program file from the "
                "User Scripts tab using 'Change'." % want)
            self._sync_browser_switches(self.generator.active_browser_kind())
            return
        self.generator.set_active_browser_kind(kind)
        self._sync_browser_switches(kind)
        try:
            info = self.generator.detect_browser_info(path)
            brand = info['brand']
        except Exception:
            brand = 'Firefox' if kind == 'firefox' else 'Google Chrome'
        self.status_var.set("New profiles will be generated with %s" % brand)
        try:
            self.generator.rebuild_all_launchers()
        except Exception:
            pass
        try:
            self._refresh_browser_caption()
            self._refresh_browser_label()
        except Exception:
            pass
        self._refresh_profiles()

    def _on_toggle_chrome(self):
        if getattr(self, '_suppress_browser_cmd', False):
            return
        self._apply_browser_kind('chrome')

    def _on_toggle_firefox(self):
        if getattr(self, '_suppress_browser_cmd', False):
            return
        self._apply_browser_kind('firefox')

    # ------------------------------------------------------------------
    # kept from the original file: the window no longer shows this list,
    # but the method is left intact and callable
    def _build_created_column(self, parent):
        card = tk.Frame(parent, bg=self.BG_CARD,
                        highlightbackground=self.BORDER, highlightthickness=1)
        card.grid(row=0, column=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)

        tk.Label(card, text="All Desktop Browser", bg=self.BG_CARD, fg=self.FG,
                 font=('Segoe UI', 12)).grid(row=0, column=0, sticky=tk.W,
                                             padx=12, pady=(12, 8))

        wrap = tk.Frame(card, bg=self.BG_CARD)
        wrap.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S),
                  padx=12, pady=(0, 8))
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)

        # one tab per browser family, each with its own list
        self.browser_tabs = ttk.Notebook(wrap, style='TNotebook')
        self.browser_tabs.grid(row=0, column=0, columnspan=2,
                               sticky=(tk.W, tk.E, tk.N, tk.S))
        self.browser_trees = {}
        for family in self.BROWSER_TABS:
            page = ttk.Frame(self.browser_tabs, style='TFrame')
            page.columnconfigure(0, weight=1)
            page.rowconfigure(0, weight=1)
            self.browser_tabs.add(page, text=' %s ' % family)
            tree = ttk.Treeview(page, columns=('name', 'created', 'path'),
                                displaycolumns=('name',),
                                show='headings', selectmode='browse')
            tree.heading('name', text='Profile')
            tree.column('name', width=170, anchor=tk.W)
            tree.column('created', width=0, stretch=False)
            tree.column('path', width=0, stretch=False)
            tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
            bar = ttk.Scrollbar(page, orient=tk.VERTICAL, command=tree.yview,
                                style='Vertical.TScrollbar')
            tree.configure(yscrollcommand=bar.set)
            bar.grid(row=0, column=1, sticky=(tk.N, tk.S))
            self.browser_trees[family] = tree

        buttons = tk.Frame(card, bg=self.BG_CARD)
        buttons.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=12, pady=(0, 12))
        ttk.Button(buttons, text="Open", style='Accent.TButton',
                   command=self._launch_selected).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Add", style='Ghost.TButton',
                   command=self._add_selected_card).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Refresh", style='Ghost.TButton',
                   command=self._refresh_profiles).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(buttons, text="Delete", style='Danger.TButton',
                   command=self._delete_profile).pack(side=tk.LEFT)

    def _build_browser_column(self, parent):
        card = tk.Frame(parent, bg=self.BG)
        card.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 8))
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)

        tk.Label(card, text="Browser Profiles", bg=self.BG, fg=self.FG,
                 font=('Segoe UI', 12)).grid(row=0, column=0, sticky=tk.W,
                                             pady=(2, 8))

        holder = tk.Frame(card, bg=self.BG_CARD,
                          highlightbackground=self.BORDER, highlightthickness=1)
        holder.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)

        self.cards_canvas = tk.Canvas(holder, bg=self.BG_CARD,
                                      highlightthickness=0, borderwidth=0)
        self.cards_canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        bar = ttk.Scrollbar(holder, orient=tk.VERTICAL,
                            command=self.cards_canvas.yview,
                            style='Vertical.TScrollbar')
        bar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.cards_canvas.configure(yscrollcommand=bar.set)

        self.cards_holder = tk.Frame(self.cards_canvas, bg=self.BG_CARD)
        self.cards_window = self.cards_canvas.create_window(
            (0, 0), window=self.cards_holder, anchor='nw')

        def on_config(event=None):
            self.cards_canvas.configure(
                scrollregion=self.cards_canvas.bbox('all'))
            self.cards_canvas.itemconfigure(
                self.cards_window, width=self.cards_canvas.winfo_width())

        self.cards_holder.bind('<Configure>', on_config)
        self.cards_canvas.bind('<Configure>', on_config)

    # ------------------------------------------------------------------
    def _build_hidden_profile_store(self):
        """v4.4: the 'All Desktop Browser' column is gone. The Browser
        Profiles cards are now the only list. Several helpers still read a
        Treeview via self.tree, so keep one alive but never shown."""
        holder = tk.Frame(self.root, bg=self.BG)
        # deliberately not gridded/packed, so it never appears on screen
        self.browser_trees = {}
        tree = ttk.Treeview(holder, columns=('name', 'created', 'path'),
                            displaycolumns=('name',),
                            show='headings', selectmode='browse')
        for family in self.BROWSER_TABS:
            self.browser_trees[family] = tree
        self._fallback_tree = tree

    # ------------------------------------------------------------------
    # profile cards
    # ------------------------------------------------------------------
    def _rebuild_cards(self, profiles):
        for child in list(self.cards_holder.winfo_children()):
            child.destroy()
        self.card_urls = {}
        for index, profile in enumerate(profiles):
            self._make_card(profile, index)
        self.cards_holder.update_idletasks()
        self.cards_canvas.configure(scrollregion=self.cards_canvas.bbox('all'))

    def _make_card(self, profile, index):
        name = profile['name']
        path = profile['path']
        key = self.generator.profile_key(path)
        language = ''
        try:
            with open(os.path.join(path, '_fingerprint.json'),
                      encoding='utf-8') as f:
                language = json.load(f).get('language', '')
        except Exception:
            language = ''

        card = tk.Frame(self.cards_holder, bg=self.BG_CARD_2,
                        highlightbackground=self.BORDER, highlightthickness=1)
        card.pack(fill=tk.X, padx=10, pady=6)
        card.columnconfigure(1, weight=1)

        tk.Label(card, text="\u25CF", bg=self.BG_CARD_2, fg=self.ACCENT,
                 font=('Segoe UI', 22)).grid(row=0, column=0, rowspan=2,
                                             padx=(12, 10), pady=8)
        tk.Label(card, text=name, bg=self.BG_CARD_2, fg=self.FG,
                 font=('Segoe UI', 12, 'bold')).grid(row=0, column=1,
                                                     sticky=tk.W, pady=(10, 0))

        badges = tk.Frame(card, bg=self.BG_CARD_2)
        badges.grid(row=1, column=1, sticky=tk.W, pady=(2, 6))
        tk.Label(badges, text=" Language: %s " % (language or '?'),
                 bg=self.BG_CARD, fg=self.FG_MUTED, font=('Segoe UI', 8)
                 ).pack(side=tk.LEFT)
        has_fp = (os.path.isfile(os.path.join(path, '_fingerprint.json'))
                  and self.generator.profile_fingerprint(key))
        tk.Label(badges, text=" Fingerprint ", bg=self.BG_CARD,
                 fg=self.FG_MUTED, font=('Segoe UI', 8)).pack(side=tk.LEFT, padx=(6, 0))
        tk.Label(badges, text=" YES " if has_fp else " NO ",
                 bg=self.GREEN if has_fp else self.DANGER, fg='#ffffff',
                 font=('Segoe UI', 8, 'bold')).pack(side=tk.LEFT)

        # v4.4: X now removes the profile itself (with a confirm), since the
        # separate delete list has been removed
        ttk.Button(card, text="\u2715", style='Mini.TButton', width=3,
                   command=lambda n=name, p=path: self._delete_card_profile(n, p)
                   ).grid(row=0, column=2, sticky=tk.NE, padx=8, pady=8)

        row = tk.Frame(card, bg=self.BG_CARD_2)
        row.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E),
                 padx=12, pady=(0, 10))
        row.columnconfigure(0, weight=1)

        browser_line = tk.Frame(row, bg=self.BG_CARD_2)
        browser_line.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        shown = self.generator.detect_browser_info(
            self.generator.browser_for_profile(key))
        tk.Label(browser_line,
                 text="Browser: %s" % shown['brand'],
                 bg=self.BG_CARD_2, fg=self.FG_MUTED, font=('Segoe UI', 8)
                 ).pack(side=tk.LEFT)
        created = str(profile.get('created') or '')
        if created:
            tk.Label(browser_line, text="   Created: %s" % created,
                     bg=self.BG_CARD_2, fg=self.FG_MUTED,
                     font=('Segoe UI', 8)).pack(side=tk.LEFT)

        url_line = tk.Frame(row, bg=self.BG_CARD_2)
        url_line.grid(row=1, column=0, sticky=(tk.W, tk.E))
        url_line.columnconfigure(1, weight=1)
        tk.Label(url_line, text="Open at", bg=self.BG_CARD_2, fg=self.FG_MUTED,
                 font=('Segoe UI', 8, 'bold')).grid(row=0, column=0, padx=(0, 6))
        var = tk.StringVar(value=self.generator.start_url_for(key))
        self.card_urls[name] = var
        ttk.Entry(url_line, textvariable=var).grid(row=0, column=1,
                                                  sticky=(tk.W, tk.E))

        btn_line = tk.Frame(row, bg=self.BG_CARD_2)
        btn_line.grid(row=2, column=0, sticky=tk.E, pady=(7, 0))
        ttk.Button(btn_line, text="SAVE", style='Ghost.TButton',
                   command=lambda n=name, k=key: self._save_card_url(n, k)
                   ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_line, text="Open browser", style='Accent.TButton',
                   command=lambda n=name, p=path: self._launch_card(n, p)
                   ).pack(side=tk.LEFT)

    # ------------------------------------------------------------------
    # v4.1: browser choice, and cards you curate yourself
    # ------------------------------------------------------------------
    def _check_engine(self, path):
        """Warn about browsers that need the best-effort Firefox path."""
        engine = self.generator.browser_engine(path)
        if engine == 'gecko':
            return messagebox.askyesno(
                "Firefox support is best-effort",
                "%s is a Firefox-family browser.\n\n"
                "This tool installs a temporary add-on over Firefox's "
                "remote-debugging server so the fingerprint patch and your "
                "user scripts run in it too. This works on current Firefox, "
                "but is less battle-tested than the Chrome path, and some "
                "sites with a strict content-security-policy may block the "
                "injected code.\n\nUse Firefox?" % os.path.basename(path))
        if engine == 'unknown':
            return messagebox.askyesno(
                "Not a known browser",
                "%s is not a browser this tool recognises.\n\n"
                "If it is not Chromium-based it will not work. Use it anyway?"
                % os.path.basename(path))
        return True

    def _browser_file_dialog(self, title):
        if platform.system() == 'Windows':
            types = [("Browser program", "*.exe"), ("All files", "*.*")]
            start = os.environ.get('ProgramFiles', r'C:\\Program Files')
        elif platform.system() == 'Darwin':
            types = [("All files", "*.*")]
            start = '/Applications'
        else:
            types = [("All files", "*.*")]
            start = '/usr/bin'
        return filedialog.askopenfilename(title=title, initialdir=start,
                                          filetypes=types)

    def _pick_card_browser(self, name):
        """Give one profile its own browser, leaving the others alone."""
        path = self._browser_file_dialog("Browser for '%s'" % name)
        if not path or not self._check_engine(path):
            return
        self.generator.set_profile_browser(name, path)
        try:
            self.generator._profile_launcher(
                name, os.path.join(self.generator.profiles_dir, name))
        except Exception:
            pass
        self._refresh_profiles()
        info = self.generator.detect_browser_info(path)
        self.status_var.set("%s will now open in %s" % (name, info['brand']))

    def _clear_card_browser(self, name):
        self.generator.set_profile_browser(name, '')
        try:
            self.generator._profile_launcher(
                name, os.path.join(self.generator.profiles_dir, name))
        except Exception:
            pass
        self._refresh_profiles()
        self.status_var.set("%s follows the default browser again" % name)

    def _generate_profiles(self):
        if not self._enforce_license_gate():
            return
        """Create profiles, then honour the Fingerprint checkbox for real.

        v6.2: Free-plan limits are enforced HERE (not just hidden in the UI):
        at most 5 profiles, no fingerprint engine, and only the Free language
        and screen-size sets. The server signs these same entitlements, so a
        Free user who edits local settings still cannot exceed them - the
        generated profiles are clamped to the plan.
        """
        client = self.generator.license() if hasattr(self.generator, 'license') else None
        ent = None
        if client is not None:
            try:
                ent = client.plan_entitlements()
            except Exception:
                ent = None
        is_paid = self._current_plan() in ('pro', 'team')

        try:
            want_count = max(1, int(self.num_profiles_var.get()))
        except Exception:
            want_count = 1

        if ent and not is_paid:
            cap = int(ent.get('max_profiles', 5) or 5)
            try:
                have = len(self.generator.get_all_profiles())
            except Exception:
                have = 0
            # v6.2.1 (section 7, Option A): the cap counts only profiles made
            # since this version was installed. Everything that already
            # existed is grandfathered and keeps working, so an existing user
            # is never locked out of generation by profiles they made before
            # the plan model existed.
            counted = self._free_counted_profiles()
            if counted + want_count > cap:
                allowed = max(0, cap - counted)
                if allowed <= 0:
                    # at the cap: the small task-4 dialog, not a dead end
                    # dressed up as two big ones
                    self._free_feature_popup(
                        'The Free version includes %d browser profiles. '
                        'Delete one to make room, or upgrade.' % cap,
                        title='Free version limit')
                    return
                # room for some but not all: keep the original, more
                # detailed dialog, then clamp and carry on generating
                self._free_plan_limit_dialog(cap, counted, allowed, have)
                self.num_profiles_var.set(str(allowed))
                want_count = allowed

            if bool(self.show_fp_var.get()) and not ent.get('fingerprint', False):
                if self._needs_pro('The fingerprint engine'):
                    self.show_fp_var.set(False)

            self._clamp_pools_to_entitlement(ent)

        try:
            before = {p['name'] for p in self.generator.get_all_profiles()}
        except Exception:
            before = set()
        want_fp = bool(self.show_fp_var.get())
        self._create_profiles()
        try:
            fresh = [p for p in self.generator.get_all_profiles()
                     if p['name'] not in before]
        except Exception:
            fresh = []
        kind = self.generator.active_browser_kind()
        for profile in fresh:
            try:
                fingerprint = None
                fp_file = os.path.join(profile['path'], '_fingerprint.json')
                if os.path.isfile(fp_file):
                    with open(fp_file, encoding='utf-8') as handle:
                        fingerprint = json.load(handle)
                # pin first: a later switch of the global browser must never
                # turn this profile into the other engine
                self.generator.pin_profile_to_active_browser(
                    profile['path'], fingerprint)
                self.generator.apply_profile_fingerprint(
                    profile['name'], profile['path'], want_fp)
                self.generator._profile_launcher(
                    self.generator.profile_key(profile['path']),
                    profile['path'])
            except Exception:
                pass
        if fresh:
            self.status_var.set(
                "%d profile(s) created with %s - fingerprint %s"
                % (len(fresh),
                   "Firefox" if kind == 'firefox' else "Google Chrome",
                   "applied" if want_fp else "OFF"))
            self._refresh_profiles()

    def _flash_browser_caption(self, message):
        try:
            self.browser_label_var.set(message)
            self.browser_caption.configure(fg='#4ade80')
            self.root.after(6000, self._refresh_browser_caption)
        except Exception:
            pass

    def _refresh_browser_caption(self):
        try:
            info = self.generator.detect_browser_info()
            label = "%s %s" % (info['brand'], info['version'] or '')
            path = info['path'] or 'none found'
        except Exception:
            label, path = 'unknown', ''
        try:
            self.browser_caption.configure(fg=self.FG_MUTED)
        except Exception:
            pass
        self.browser_label_var.set("Browser: %s\n%s" % (label.strip(), path))

    def _pick_browser_file(self):
        """Pick the browser executable straight from disk - no chooser box."""
        if platform.system() == 'Windows':
            types = [("Browser program", "*.exe"), ("All files", "*.*")]
            start = os.environ.get('ProgramFiles', r'C:\\Program Files')
        elif platform.system() == 'Darwin':
            types = [("All files", "*.*")]
            start = '/Applications'
        else:
            types = [("All files", "*.*")]
            start = '/usr/bin'
        path = filedialog.askopenfilename(
            title="Select the browser this tool should launch",
            initialdir=start, filetypes=types)
        if not path:
            return
        if not self._check_engine(path):
            return
        self.generator.set_browser_override(path)
        self._refresh_browser_caption()

        info = self.generator.detect_browser_info(path)
        self.status_var.set("Rebuilding launchers for %s ..." % info['brand'])
        self.root.update_idletasks()

        def progress(done, total, name):
            if done % 5 == 0 or done == total:
                self.status_var.set("Rebuilding %d/%d ..." % (done, total))
                self.root.update_idletasks()

        try:
            done, total = self.generator.rebuild_all_launchers(progress)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return
        self.status_var.set(
            "%s is now the default browser - %d/%d launcher(s) updated"
            % (info['brand'], done, total))
        # no popup: it was being read as an error. The caption under the
        # pools turns green instead, which is impossible to miss.
        self._flash_browser_caption(
            "%s is now the default browser (%d/%d launchers updated). "
            "Press 'Open browser' on a card to start one."
            % (info['brand'], done, total))
        self._refresh_profiles()

    # ---- which profiles appear as cards ----
    def _card_names(self):
        try:
            reg = self.generator._load_userscript_registry()
            return list(reg['settings'].get('card_profiles', []))
        except Exception:
            return []

    def _set_card_names(self, names):
        try:
            reg = self.generator._load_userscript_registry()
            reg['settings']['card_profiles'] = list(names)
            self.generator._save_userscript_registry(reg)
        except Exception:
            pass

    def _add_card_name(self, name, front=False):
        names = self._card_names()
        if name in names:
            if not front:
                return
            names.remove(name)
        if front:
            names.insert(0, name)   # newest profile sits at the top
        else:
            names.append(name)
        self._set_card_names(names)

    def _remove_card_name(self, name):
        names = [n for n in self._card_names() if n != name]
        self._set_card_names(names)

    def _add_selected_card(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Select a profile first")
            return
        name = str(self.tree.item(selection[0])['values'][0])
        self._add_card_name(name)
        self._refresh_profiles()
        self.status_var.set("%s added to Browser Profiles" % name)

    def _save_card_url(self, name, key=None):
        url = self.card_urls[name].get().strip()
        self.generator.set_profile_url(key or name, url)
        self.status_var.set("Saved start page for %s" % name)

    def _launch_card(self, name, path):
        url = ''
        if name in getattr(self, 'card_urls', {}):
            url = self.card_urls[name].get().strip()
        self._launch(name, path, url)

    def _launch_selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Select a profile first")
            return
        values = self.tree.item(selection[0])['values']
        self._launch(str(values[0]), str(values[2]), '')

    def _launch(self, name, path, url):
        self.status_var.set("Starting %s ..." % name)
        self.root.update_idletasks()
        try:
            self.generator.launch_profile(name, path, url or None)
        except AppDisabledError as e:
            self.status_var.set("The application is turned off by the administrator")
            messagebox.showwarning("Application disabled", str(e))
            return
        except Exception as e:
            self.status_var.set("Could not start %s" % name)
            messagebox.showerror("Could not open", str(e))
            return
        report = self.generator.userscript_report()
        self.status_var.set(
            "%s started - %d script(s) injecting" % (name, report['enabled']))

    def _hide_card(self, name):
        self._remove_card_name(name)
        self._refresh_profiles()
        self.status_var.set("%s removed from Browser Profiles "
                            "(the profile itself is untouched)" % name)

    def _delete_card_profile(self, name, path=None):
        """v4.4: the card's X deletes the profile after a confirmation."""
        if not messagebox.askyesno(
                "Delete profile",
                "Delete profile '%s'?\n\n"
                "This removes its folder and desktop shortcut and cannot be "
                "undone." % name):
            return
        state = None
        try:
            ppath = path or os.path.join(self.generator.profiles_dir, name)
            state = self.generator.profile_is_running(ppath)
        except Exception:
            state = None
        if state and (state.get('alive') or state.get('locked')):
            messagebox.showwarning(
                "Profile is open",
                "'%s' is currently open. Close all of its browser windows "
                "first, then delete it." % name)
            return
        try:
            self.generator.delete_profile(name)
        except Exception as e:
            messagebox.showerror("Could not delete", str(e))
            return
        self._remove_card_name(name)
        try:
            self._known_profiles = None  # force a fresh recount
        except Exception:
            pass
        self._refresh_profiles()
        self.status_var.set("Deleted profile %s" % name)

    def _delete_named(self, name):
        for item in self.tree.get_children():
            values = self.tree.item(item)['values']
            if values and str(values[0]) == name:
                self.tree.selection_set(item)
                break
        self._delete_profile()

    def _build_selection_card(self, parent, row):
        """Compact, collapsible language / screen-size pools."""
        try:
            ttk.Style().configure('Pool.TCheckbutton', background=self.BG_CARD,
                                  foreground=self.FG, focuscolor=self.BG_CARD,
                                  font=('Segoe UI', 8))
            ttk.Style().map('Pool.TCheckbutton',
                            background=[('active', self.BG_CARD)])
            ttk.Style().configure('Accent.TButton', padding=(9, 5))
            ttk.Style().configure('Ghost.TButton', padding=(8, 4))
            ttk.Style().configure('Danger.TButton', padding=(8, 4))
            ttk.Style().configure('Mini.TButton', background=self.BG_CARD_2,
                                  foreground=self.FG, borderwidth=0,
                                  padding=(6, 2), font=('Segoe UI', 8))
            ttk.Style().map('Mini.TButton',
                            background=[('active', self.BORDER)])
        except Exception:
            pass

        head = tk.Frame(parent, bg=self.BG_CARD)
        head.grid(row=row, column=0, columnspan=4, sticky=(tk.W, tk.E),
                  padx=10, pady=(0, 4))
        head.columnconfigure(1, weight=1)

        self.pools_open = False
        self.pool_toggle_text = tk.StringVar(value="\u25b8  Language / screen size")
        ttk.Button(head, textvariable=self.pool_toggle_text, style='Mini.TButton',
                   command=self._toggle_pools).grid(row=0, column=0, sticky=tk.W)

        self.pool_summary_var = tk.StringVar(value="")
        ttk.Label(head, textvariable=self.pool_summary_var,
                  style='CardMuted.TLabel').grid(row=0, column=1, sticky=tk.W,
                                                 padx=(8, 0))

        self.pool_body = tk.Frame(parent, bg=self.BG_CARD)
        self._pool_body_row = row + 1
        self.pool_body.columnconfigure(0, weight=1)
        self.pool_body.columnconfigure(1, weight=1)

        # ---- languages (tag only, 5 per row) ----
        lang_box = ttk.LabelFrame(self.pool_body, text=" Languages ",
                                  padding=(6, 2, 6, 5))
        lang_box.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N), padx=(0, 6))

        lang_tools = tk.Frame(lang_box, bg=self.BG_CARD)
        lang_tools.grid(row=0, column=0, columnspan=self.LANG_COLS,
                        sticky=tk.W, pady=(0, 2))
        for label, val in (("All", True), ("None", False), ("Inv", None)):
            ttk.Button(lang_tools, text=label, style='Mini.TButton', width=4,
                       command=lambda v=val: self._set_pool(self.lang_vars, v)
                       ).pack(side=tk.LEFT, padx=(0, 3))

        self.lang_vars = {}
        self._lang_switches = {}
        for i, tag in enumerate(self.generator.DEFAULT_LANGUAGES):
            var = tk.BooleanVar(value=True)
            self.lang_vars[tag] = var
            _ls = LabeledSwitch(lang_box, text=tag, variable=var,
                          command=self._update_pool_summary, bg=self.BG_CARD,
                          fg=self.FG, font=('Segoe UI', 8),
                          switch_width=34, switch_height=18, gap=5)
            _ls.grid(row=1 + i // self.LANG_COLS,
                     column=i % self.LANG_COLS,
                     sticky=tk.W, padx=(0, 8), pady=1)
            self._lang_switches[tag] = _ls

        # ---- screen sizes (3 per row) ----
        res_box = ttk.LabelFrame(self.pool_body, text=" Screen size ",
                                 padding=(6, 2, 6, 5))
        res_box.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N))

        res_tools = tk.Frame(res_box, bg=self.BG_CARD)
        res_tools.grid(row=0, column=0, columnspan=self.RES_COLS,
                       sticky=tk.W, pady=(0, 2))
        for label, val in (("All", True), ("None", False), ("Inv", None)):
            ttk.Button(res_tools, text=label, style='Mini.TButton', width=4,
                       command=lambda v=val: self._set_pool(self.res_vars, v)
                       ).pack(side=tk.LEFT, padx=(0, 3))

        self.res_vars = {}
        self._res_switches = {}
        for i, (w, h) in enumerate(self.generator.DEFAULT_RESOLUTIONS):
            var = tk.BooleanVar(value=True)
            self.res_vars[(w, h)] = var
            _rs = LabeledSwitch(res_box, text="%dx%d" % (w, h), variable=var,
                          command=self._update_pool_summary, bg=self.BG_CARD,
                          fg=self.FG, font=('Segoe UI', 8),
                          switch_width=34, switch_height=18, gap=5)
            _rs.grid(row=1 + i // self.RES_COLS,
                     column=i % self.RES_COLS,
                     sticky=tk.W, padx=(0, 8), pady=1)
            self._res_switches[(w, h)] = _rs

        self._update_pool_summary()

    def _toggle_pools(self):
        """Show / hide the pool checkboxes so the window stays small."""
        self.pools_open = not getattr(self, "pools_open", False)
        if self.pools_open:
            self.pool_body.grid(row=self._pool_body_row, column=0, columnspan=4,
                                sticky=(tk.W, tk.E), padx=10, pady=(0, 8))
            self.pool_toggle_text.set("\u25be  Language / screen size")
        else:
            self.pool_body.grid_forget()
            self.pool_toggle_text.set("\u25b8  Language / screen size")

    def _set_pool(self, var_map, value):
        """value True = check all, False = uncheck all, None = invert.

        v6.2.1: on Free, All/Invert could tick options the plan does not
        include; they were silently un-ticked again a moment later, which
        looked like a broken button. The selection is now clamped straight
        away and the small task-4 dialog explains it once. Un-ticking
        (value False) is never restricted.
        """
        for var in var_map.values():
            var.set((not var.get()) if value is None else bool(value))
        blocked = 0
        if value is not False:
            try:
                blocked = self._clamp_pool_map(var_map)
            except Exception:
                blocked = 0
        self._update_pool_summary()
        if blocked:
            self._free_feature_popup(
                'Some of those options are not available in the Free version, '
                'so they were left off.')

    def _clamp_pool_map(self, var_map):
        """Un-tick anything in this pool the current plan does not include.
        Returns how many were un-ticked. Paid plans clamp nothing."""
        if self._current_plan() in ('pro', 'team'):
            return 0
        client = self.generator.license() if hasattr(self.generator, 'license') else None
        ent = None
        if client is not None:
            try:
                ent = client.plan_entitlements()
            except Exception:
                ent = None
        if not ent:
            return 0
        allow_langs = ent.get('languages', ['*'])
        allow_res = ent.get('resolutions', ['*'])
        blocked = 0
        for key, var in var_map.items():
            if not var.get():
                continue
            if isinstance(key, tuple):
                ok = '*' in allow_res or ('%dx%d' % key) in allow_res
            else:
                ok = '*' in allow_langs or key in allow_langs
            if not ok:
                var.set(False)
                blocked += 1
        return blocked

    def _selected_languages(self):
        return [tag for tag, var in self.lang_vars.items() if var.get()]

    def _selected_resolutions(self):
        return [size for size, var in self.res_vars.items() if var.get()]

    def _update_pool_summary(self):
        langs = self._selected_languages()
        sizes = self._selected_resolutions()
        parts = []
        parts.append(langs[0] if len(langs) == 1
                     else "%d/%d lang" % (len(langs), len(self.lang_vars)))
        parts.append("%dx%d" % sizes[0] if len(sizes) == 1
                     else "%d/%d sizes" % (len(sizes), len(self.res_vars)))
        self.pool_summary_var.set(" · ".join(parts))

    def _apply_pool_selection(self):
        """Push the checked pools into the generator. False = invalid state.

        v6.2: on the Free plan the selection is clamped to the languages and
        screen sizes Free is entitled to, so a manual edit cannot widen it.
        """
        langs = self._selected_languages()
        sizes = self._selected_resolutions()
        if not langs:
            messagebox.showerror("Error", "Select at least one language.")
            return False
        if not sizes:
            messagebox.showerror("Error", "Select at least one screen resolution.")
            return False
        # Free clamp
        if self._current_plan() not in ('pro', 'team'):
            ent = None
            client = self.generator.license() if hasattr(self.generator, 'license') else None
            if client is not None:
                try:
                    ent = client.plan_entitlements()
                except Exception:
                    ent = None
            if ent:
                allow_langs = ent.get('languages', [])
                if '*' not in allow_langs:
                    langs = [l for l in langs if l in allow_langs] or list(allow_langs)
                allow_res = ent.get('resolutions', [])
                if '*' not in allow_res:
                    def _res_ok(wh):
                        return ('%dx%d' % (wh[0], wh[1])) in allow_res
                    sizes = [s for s in sizes if _res_ok(s)] or \
                        [tuple(int(x) for x in r.split('x')) for r in allow_res]
        self.generator.set_language_pool(langs)
        self.generator.set_resolution_pool(sizes)
        return True

    def _clamp_pools_to_entitlement(self, ent):
        """Tick only the language/screen-size switches the plan allows, and
        disable the rest so a Free user sees exactly what Free includes."""
        try:
            allow_langs = ent.get('languages', [])
            allow_res = ent.get('resolutions', [])
            star_l = '*' in allow_langs
            star_r = '*' in allow_res
            for tag, var in getattr(self, 'lang_vars', {}).items():
                ok = star_l or tag in allow_langs
                if not ok and var.get():
                    var.set(False)
            for (w, h), var in getattr(self, 'res_vars', {}).items():
                ok = star_r or ('%dx%d' % (w, h)) in allow_res
                if not ok and var.get():
                    var.set(False)
            # make sure at least the Free defaults are on
            if not self._selected_languages():
                for tag, var in self.lang_vars.items():
                    if star_l or tag in allow_langs:
                        var.set(True)
            if not self._selected_resolutions():
                for (w, h), var in self.res_vars.items():
                    if star_r or ('%dx%d' % (w, h)) in allow_res:
                        var.set(True)
            self._update_pool_summary()
        except Exception:
            pass

    def _sync_feature_locks(self):
        """Reflect the current plan in the config panel: on Free, lock the
        Pro-only language/screen switches and the fingerprint toggle so they
        read as paid features rather than silently doing nothing."""
        plan = self._current_plan()
        paid = plan in ('pro', 'team')
        ent = None
        client = self.generator.license() if hasattr(self.generator, 'license') else None
        if client is not None:
            try:
                ent = client.plan_entitlements()
            except Exception:
                ent = None
        allow_langs = (ent or {}).get('languages', ['*'])
        allow_res = (ent or {}).get('resolutions', ['*'])
        star_l = paid or '*' in allow_langs
        star_r = paid or '*' in allow_res

        # language switches
        for tag, ls in getattr(self, '_lang_switches', {}).items():
            locked = not (star_l or tag in allow_langs)
            try:
                ls.set_enabled(not locked)
                # v6.2.1: clicking a locked switch now says why (task 4)
                ls.set_locked_command(
                    (lambda t=tag: self._free_locked('The %s language' % t)) if locked else None)
                if locked and tag in self.lang_vars:
                    self.lang_vars[tag].set(False)
            except Exception:
                pass
        for (w, h), ls in getattr(self, '_res_switches', {}).items():
            locked = not (star_r or ('%dx%d' % (w, h)) in allow_res)
            try:
                ls.set_enabled(not locked)
                ls.set_locked_command(
                    (lambda ww=w, hh=h: self._free_locked('The %dx%d screen size' % (ww, hh)))
                    if locked else None)
                if locked and (w, h) in self.res_vars:
                    self.res_vars[(w, h)].set(False)
            except Exception:
                pass
        # fingerprint toggle
        fp_locked = not (paid or (ent or {}).get('fingerprint', True))
        fps = getattr(self, '_fp_switch', None)
        if fps is not None:
            try:
                fps.set_enabled(not fp_locked)
                fps.set_locked_command(
                    (lambda: self._free_locked('The fingerprint engine')) if fp_locked else None)
                if fp_locked:
                    self.show_fp_var.set(False)
            except Exception:
                pass
        try:
            self._update_pool_summary()
        except Exception:
            pass

    def _apply_plan_theme(self):
        """Tint the header/banner accent by plan: Free (blue), Pro (indigo),
        Team (teal), so the active plan is obvious at a glance. Falls back
        silently if the widgets are not built yet."""
        plan = self._current_plan()
        accents = {'free': self.ACCENT, 'pro': '#5b35c9', 'team': '#0b766e'}
        banners = {'free': self.BANNER, 'pro': '#2a1e63', 'team': '#0b3b38'}
        accent = accents.get(plan, self.ACCENT)
        banner = banners.get(plan, self.BANNER)
        self._plan_accent = accent
        try:
            ttk.Style().configure('Accent.TButton', background=accent)
            ttk.Style().map('Accent.TButton', background=[('active', accent)])
        except Exception:
            pass
        try:
            if getattr(self, '_banner_frame', None) is not None:
                self._banner_frame.configure(bg=banner)
                for ch in self._banner_frame.winfo_children():
                    try:
                        ch.configure(bg=banner)
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            self._build_license_buttons()
        except Exception:
            pass


    @staticmethod
    def _short(path, limit=42):
        if len(path) <= limit:
            return path
        return "…" + path[-(limit - 1):]

    def _show_fingerprint_panel(self, fingerprint=None):
        try:
            self._update_summary(fingerprint)
        except Exception:
            pass
        """Show or hide the fingerprint details panel."""
        if fingerprint and self.show_fp_var.get():
            self.fp_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(0, 8))
            self.fp_text.configure(state=tk.NORMAL)
            self.fp_text.delete(1.0, tk.END)
            # Pretty-print key fingerprint values
            lines = [
                "=== Fingerprint Summary ===",
                f"UA: {fingerprint.get('user_agent', 'N/A')[:80]}...",
                f"Screen: {fingerprint.get('screen_resolution', {})}",
                f"Platform: {fingerprint.get('platform')} | Lang: {fingerprint.get('language')}",
                f"Accept-Languages: {', '.join(fingerprint.get('languages', []))}",
                f"HW Concurrency: {fingerprint.get('hardware_concurrency')} | Device Memory: {fingerprint.get('device_memory')}GB",
                f"WebGL: {fingerprint.get('webgl_renderer', 'N/A')[:60]}...",
                f"WebGPU: {fingerprint.get('webgpu', {}).get('description', 'N/A')}",
                f"Color Scheme: {fingerprint.get('color_scheme')} | Motion: {fingerprint.get('motion_preference')}",
                f"Timezone: {fingerprint.get('timezone')}",
                f"Fonts: {len(fingerprint.get('fonts', []))} fonts | Plugins: {len(fingerprint.get('plugins', []))} plugins",
                f"Device Pixel Ratio: {fingerprint.get('device_pixel_ratio')} | Color Depth: {fingerprint.get('color_depth')}",
                f"TLS Cipher Blacklist: {len(fingerprint.get('tls_cipher_order', []))} ciphers",
                f"Speech Voices: {len(fingerprint.get('speech_voices', []))} voices",
                "",
            ]
            self.fp_text.insert(tk.END, '\n'.join(lines))
            self.fp_text.configure(state=tk.DISABLED)
        else:
            self.fp_frame.grid_forget()

    def _update_summary(self, fingerprint):
        """Mirror the fingerprint into the panel under the window."""
        box = getattr(self, 'summary_text', None)
        if box is None or not fingerprint:
            return
        res = fingerprint.get('screen_resolution') or {}
        lines = [
            "=== Fingerprint Summary ===",
            "UA: %s" % fingerprint.get('user_agent', ''),
            "Screen: %sx%s   Lang: %s" % (res.get('width'), res.get('height'),
                                          fingerprint.get('language')),
            "Accept-Language: %s" % ', '.join(fingerprint.get('languages', [])),
            "Timezone: %s" % fingerprint.get('timezone', ''),
            "HW Concurrency: %s | Device Memory: %sGB" % (
                fingerprint.get('hardware_concurrency'),
                fingerprint.get('device_memory')),
        ]
        box.configure(state=tk.NORMAL)
        box.delete('1.0', tk.END)
        box.insert('1.0', '\n'.join(str(l) for l in lines))
        box.configure(state=tk.DISABLED)

    def _create_profiles(self):
        try:
            num_profiles = int(self.num_profiles_var.get())
            if num_profiles < 1 or num_profiles > 100:
                messagebox.showerror("Error", "Number of profiles must be between 1 and 100")
                return

            profile_name = self.profile_name_var.get().strip()
            create_shortcut = self.create_shortcut_var.get()

            # v3.1: only the checked languages / screen sizes may be used
            if not self._apply_pool_selection():
                return

            created_profiles = []
            shortcuts_created = 0
            last_fingerprint = None

            for i in range(num_profiles):
                if num_profiles == 1 and profile_name:
                    name = profile_name
                elif num_profiles > 1 and profile_name:
                    name = f"{profile_name}_{i+1}"
                else:
                    name = None

                try:
                    result = self.generator.create_profile(name, create_shortcut)
                    created_profiles.append(result['profile_name'])
                    last_fingerprint = result['fingerprint']
                    if result['shortcut_created']:
                        shortcuts_created += 1
                except ValueError as e:
                    messagebox.showerror("Error", str(e))
                    break

            if created_profiles:
                self.status_var.set(
                    f"Created {len(created_profiles)} profile(s) · "
                    f"{shortcuts_created} shortcut(s) · "
                    f"{len(self._selected_languages())} lang / "
                    f"{len(self._selected_resolutions())} size pool"
                )
                self._refresh_profiles()
                self._show_fingerprint_panel(last_fingerprint)
                self.profile_name_var.set("")

                msg = f"Successfully created {len(created_profiles)} v3-enhanced profile(s):\n\n"
                msg += '\n'.join(created_profiles)
                if shortcuts_created > 0:
                    msg += f"\n\n✅ {shortcuts_created} desktop shortcut(s) created"
                    if self.generator.icon_path:
                        msg += " with a unique colored icon!"
                    msg += f"\n\nCheck your Desktop folder to launch profiles."
                if not _PIL_AVAILABLE:
                    msg += ("\n\n[!] Pillow is not installed, so the shortcuts use the "
                            "default Chrome icon.\nInstall it with:  pip install pillow")
                us = self.generator.userscript_report()
                if us['enabled']:
                    msg += "\n\n\U0001f4dc %d user script(s) injected: %s" % (
                        us['enabled'], ', '.join(us['names'][:4]))
                    if len(us['names']) > 4:
                        msg += ', …'
                msg += "\n\nv3 hardening includes: WebGPU, MediaQueries, Memory, "
                msg += "Permissions, Speech, TLS ciphers, Font evasion."

                messagebox.showinfo("Success", msg)
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid number of profiles")

    def _create_shortcut_for_selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a profile")
            return

        item = self.tree.item(selection[0])
        profile_name = item['values'][0]
        profile_path = item['values'][2]

        if self.generator.create_desktop_shortcut(profile_name, profile_path):
            icon_msg = " with custom colored icon" if self.generator.icon_path else ""
            messagebox.showinfo(
                "Success",
                f"Desktop shortcut created for '{profile_name}'{icon_msg}!\n\n"
                f"Check your Desktop folder."
            )
        else:
            messagebox.showerror(
                "Error",
                "Failed to create desktop shortcut.\n\n"
                "Make sure Chrome is installed."
            )

    def _refresh_profiles(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        profiles = self.generator.get_desktop_profiles()
        for profile in profiles:
            self.tree.insert('', tk.END, values=(
                profile['name'],
                profile['created'],
                profile['path']
            ))
        us = self.generator.userscript_report()
        self.status_var.set('%s: %s \u00b7 %s/%s %s' % (
            self.t('status.total'), self.ltr(len(profiles)),
            self.ltr(us['enabled']), self.ltr(us['total']),
            self.t('status.scripts_active')))
        self._show_fingerprint_panel(None)

    # ==================================================================
    #  Tab 2: User Scripts (Tampermonkey-style editor)
    # ==================================================================
        try:
            for family, widget in getattr(self, 'browser_trees', {}).items():
                for item in widget.get_children():
                    widget.delete(item)
                for profile in profiles:
                    if family != 'All':
                        try:
                            if self.generator.profile_browser_family(
                                    profile['name'],
                                    profile['path']) != family:
                                continue
                        except Exception:
                            continue
                    widget.insert('', tk.END, values=(
                        profile['name'], profile.get('created', ''),
                        profile['path']))
        except Exception:
            pass

        try:
            names = [p['name'] for p in profiles]
            known = getattr(self, '_known_profiles', None)
            if known is None:
                # v4.4: cards are the only profile list now, so show every
                # existing profile as a card the first time we look
                self._known_profiles = set(names)
                for n in names:
                    self._add_card_name(n)
            else:
                fresh = [n for n in names if n not in known]
                if fresh:
                    for n in fresh:
                        self._add_card_name(n, front=True)
                    self._known_profiles = set(names)
            wanted = self._card_names()
            chosen = [p for p in profiles if p['name'] in wanted]
            chosen.sort(key=lambda p: wanted.index(p['name']))
            self._rebuild_cards(chosen)
        except Exception:
            pass

    def _build_userscripts_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(1, weight=1)

        # ---- top bar -------------------------------------------------
        top = tk.Frame(parent, bg=self.BG_CARD,
                       highlightbackground=self.BORDER,
                       highlightthickness=1, bd=0)
        top.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 7))
        top.columnconfigure(3, weight=1)

        self.us_enabled_var = tk.BooleanVar(
            value=self.generator.userscripts_enabled())
        LabeledSwitch(top, text="Inject user scripts",
                      variable=self.us_enabled_var,
                      command=self._toggle_userscripts_master, bg=self.BG_CARD,
                      fg=self.FG, switch_width=42, switch_height=22
                      ).grid(row=0, column=0, sticky=tk.W, padx=(10, 10), pady=8)

        self.us_requires_var = tk.BooleanVar(
            value=self.generator.userscript_download_requires())
        LabeledSwitch(top, text="Download @require libs",
                      variable=self.us_requires_var,
                      command=self._toggle_userscript_requires, bg=self.BG_CARD,
                      fg=self.FG, switch_width=42, switch_height=22
                      ).grid(row=0, column=1, sticky=tk.W, padx=(0, 10), pady=8)

        ttk.Button(top, text="Apply to all profiles", style='Accent.TButton',
                   command=self._apply_userscripts_to_profiles
                   ).grid(row=0, column=2, padx=(0, 8), pady=6)

        self.us_status_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.us_status_var, style='CardMuted.TLabel'
                  ).grid(row=0, column=3, sticky=tk.W, padx=(4, 10))


        # v3.3: how the script actually gets into the page
        mode_row = tk.Frame(top, bg=self.BG_CARD)
        mode_row.grid(row=1, column=0, columnspan=7, sticky=tk.W,
                      padx=10, pady=(0, 8))
        mode_row.grid_configure(columnspan=7)
        ttk.Label(mode_row, text="Inject via:", style='Card.TLabel'
                  ).pack(side=tk.LEFT, padx=(0, 8))
        self.us_mode_var = tk.StringVar(value=self.generator.injection_mode())
        for label, value, hint in (
                ("DevTools (no permission needed)", 'cdp', ''),
                ("Extension", 'extension', ''),
                ("Both", 'both', '')):
            ttk.Radiobutton(mode_row, text=label, value=value,
                            variable=self.us_mode_var,
                            style='Pool.TCheckbutton',
                            command=self._change_injection_mode
                            ).pack(side=tk.LEFT, padx=(0, 14))

        # v4.9: the DevTools guard used to be an invisible default-on
        # setting with no control anywhere in the UI. It is the reason
        # F12, Inspect and "Save image as" stopped working, so it gets a
        # switch and the caption says plainly what turning it on costs.
        guard_row = tk.Frame(top, bg=self.BG_CARD)
        guard_row.grid(row=3, column=0, columnspan=7, sticky=tk.W,
                       padx=10, pady=(0, 8))
        self.us_guard_var = tk.BooleanVar(
            value=self.generator.guard_devtools())
        LabeledSwitch(guard_row, text="Block DevTools in generated profiles",
                      variable=self.us_guard_var,
                      command=self._toggle_devtools_guard, bg=self.BG_CARD,
                      fg=self.FG, switch_width=42, switch_height=22
                      ).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(guard_row,
                  text="generated profiles only - never your own Chrome",
                  style='CardMuted.TLabel').pack(side=tk.LEFT)

        # v4.11: leaving the profile's own site closes that profile.
        lock_row = tk.Frame(top, bg=self.BG_CARD)
        lock_row.grid(row=4, column=0, columnspan=7, sticky=tk.W,
                      padx=10, pady=(0, 8))
        self.us_autolock_var = tk.BooleanVar(
            value=self.generator.auto_site_lock())
        LabeledSwitch(lock_row,
                      text="Close profile if it leaves its start site",
                      variable=self.us_autolock_var,
                      command=self._toggle_auto_site_lock, bg=self.BG_CARD,
                      fg=self.FG, switch_width=42, switch_height=22
                      ).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(lock_row,
                  text="each profile is locked to its own start URL",
                  style='CardMuted.TLabel').pack(side=tk.LEFT)

        # ---- left: script list --------------------------------------
        left = tk.Frame(parent, bg=self.BG_CARD,
                        highlightbackground=self.BORDER,
                        highlightthickness=1, bd=0)
        left.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 7))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        ttk.Label(left, text="Scripts", style='Card.TLabel',
                  font=('Segoe UI', 10, 'bold')
                  ).grid(row=0, column=0, sticky=tk.W, padx=10, pady=(7, 4))

        list_wrap = tk.Frame(left, bg=self.BG_CARD)
        list_wrap.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S),
                       padx=10, pady=(0, 6))
        list_wrap.columnconfigure(0, weight=1)
        list_wrap.rowconfigure(0, weight=1)

        self.us_tree = ttk.Treeview(list_wrap, columns=('on', 'name', 'run'),
                                    show='headings', height=11, selectmode='browse')
        self.us_tree.heading('on', text='On')
        self.us_tree.heading('name', text='Script')
        self.us_tree.heading('run', text='Run at')
        self.us_tree.column('on', width=34, minwidth=30, anchor=tk.CENTER, stretch=False)
        self.us_tree.column('name', width=185, minwidth=110, anchor=tk.W)
        self.us_tree.column('run', width=95, minwidth=70, anchor=tk.W, stretch=False)
        us_scroll = ttk.Scrollbar(list_wrap, orient=tk.VERTICAL,
                                  command=self.us_tree.yview,
                                  style='Vertical.TScrollbar')
        self.us_tree.configure(yscroll=us_scroll.set)
        self.us_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        us_scroll.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.us_tree.bind('<<TreeviewSelect>>', self._on_userscript_select)
        self.us_tree.bind('<Double-1>', self._toggle_userscript)
        self.us_tree.tag_configure('off', foreground=self.FG_MUTED)

        list_btns = tk.Frame(left, bg=self.BG_CARD)
        list_btns.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=10, pady=(0, 9))
        ttk.Button(list_btns, text="New", style='Accent.TButton',
                   command=self._new_userscript).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(list_btns, text="Import", style='Ghost.TButton',
                   command=self._import_userscript).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(list_btns, text="On/Off", style='Ghost.TButton',
                   command=self._toggle_userscript).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(list_btns, text="Delete", style='Danger.TButton',
                   command=self._delete_userscript).pack(side=tk.LEFT)

        # ---- right: editor ------------------------------------------
        right = tk.Frame(parent, bg=self.BG_CARD,
                         highlightbackground=self.BORDER,
                         highlightthickness=1, bd=0)
        right.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        head = tk.Frame(right, bg=self.BG_CARD)
        head.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=10, pady=(7, 4))
        head.columnconfigure(0, weight=1)
        self.us_title_var = tk.StringVar(value="No script selected")
        ttk.Label(head, textvariable=self.us_title_var, style='Card.TLabel',
                  font=('Segoe UI', 10, 'bold')).grid(row=0, column=0, sticky=tk.W)
        self.us_meta_var = tk.StringVar(value="")
        ttk.Label(head, textvariable=self.us_meta_var, style='CardMuted.TLabel'
                  ).grid(row=1, column=0, sticky=tk.W, pady=(1, 0))

        self.us_editor = scrolledtext.ScrolledText(
            right, bg=self.BG_CARD_2, fg=self.FG,
            insertbackground=self.FG, selectbackground=self.ACCENT,
            font=('Consolas', 9), height=18, wrap=tk.NONE,
            highlightthickness=0, borderwidth=0, undo=True,
        )
        self.us_editor.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S),
                            padx=10, pady=(0, 6))
        self.us_editor.bind('<Tab>', self._editor_tab)
        self.us_editor.bind('<Control-s>', self._editor_ctrl_s)

        edit_btns = tk.Frame(right, bg=self.BG_CARD)
        edit_btns.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=10, pady=(0, 9))
        ttk.Button(edit_btns, text="Save", style='Accent.TButton',
                   command=self._save_userscript).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(edit_btns, text="Save + Apply", style='Ghost.TButton',
                   command=self._save_and_apply_userscript).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(edit_btns, text="Revert", style='Ghost.TButton',
                   command=self._revert_userscript).pack(side=tk.LEFT)
        ttk.Label(edit_btns,
                  text="Ctrl+S saves   ·   every profile injects these on launch",
                  style='CardMuted.TLabel').pack(side=tk.RIGHT)

        # v3.2: warn when the detected browser cannot load extensions at all
        self.us_warn_frame = tk.Frame(parent, bg='#4a2c2c',
                                      highlightbackground=self.DANGER,
                                      highlightthickness=1, bd=0)
        self.us_warn_var = tk.StringVar(value='')
        tk.Label(self.us_warn_frame, textvariable=self.us_warn_var,
                 bg='#4a2c2c', fg='#ffd9d9', font=('Segoe UI', 8),
                 justify=tk.LEFT, wraplength=820, anchor=tk.W
                 ).pack(fill=tk.X, padx=10, pady=6)
        try:
            warning = self.generator.browser_warning()
        except Exception:
            warning = ''
        if warning:
            self.us_warn_var.set(warning)
            self.us_warn_frame.grid(row=2, column=0, columnspan=2,
                                    sticky=(tk.W, tk.E), pady=(7, 0))

        # v3.4: which browser these profiles actually run in
        browser_row = tk.Frame(top, bg=self.BG_CARD)
        browser_row.grid(row=2, column=0, columnspan=7, sticky=(tk.W, tk.E),
                         padx=10, pady=(0, 8))
        ttk.Label(browser_row, text="Browser:", style='Card.TLabel'
                  ).pack(side=tk.LEFT, padx=(0, 8))
        self.us_browser_var = tk.StringVar(value='')
        ttk.Label(browser_row, textvariable=self.us_browser_var,
                  style='CardMuted.TLabel').pack(side=tk.LEFT)
        ttk.Button(browser_row, text="Change", style='Mini.TButton',
                   command=self._choose_browser).pack(side=tk.LEFT, padx=(10, 0))

        self.us_current_file = None
        self._refresh_browser_label()
        self._refresh_userscripts()

    # ------------------------------------------------------------------
    def _editor_tab(self, event):
        self.us_editor.insert(tk.INSERT, '    ')
        return 'break'

    def _editor_ctrl_s(self, event):
        self._save_userscript()
        return 'break'

    # ------------------------------------------------------------------
    # v3.3: launch one profile and report what the injector actually did
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # v3.4: browser chooser
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # v3.5: bundled extensions (Tampermonkey and friends)
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # v3.6: launch with full logging, then collect one file to send
    # ------------------------------------------------------------------
    def _refresh_browser_label(self):
        try:
            info = self.generator.detect_browser_info()
        except Exception:
            self.us_browser_var.set('(detection failed)')
            return
        if not info['path']:
            self.us_browser_var.set('none found - press Change')
        else:
            self.us_browser_var.set(
                '%s %s   %s' % (info['brand'], info['version'] or '?',
                                'loads extensions' if info['load_extension']
                                else 'no extension support'))
        self._refresh_blockers()

    def _refresh_blockers(self):
        try:
            problems = self.generator.injection_blockers()
        except Exception:
            problems = []
        if not problems:
            try:
                note = self.generator.browser_warning()
            except Exception:
                note = ''
            problems = [note] if note else []
        text = '\n'.join(problems)
        self.us_warn_var.set(text)
        if text:
            self.us_warn_frame.grid(row=2, column=0, columnspan=2,
                                    sticky=(tk.W, tk.E), pady=(7, 0))
        else:
            self.us_warn_frame.grid_forget()

    def _download_browser(self):
        if not messagebox.askyesno(
                "Download Chrome for Testing",
                "Google Chrome 142+ ignores --load-extension, so bundled\n"
                "extensions such as Tampermonkey can never load in it.\n\n"
                "Chrome for Testing is the same engine, published by Google,\n"
                "and still loads them. It downloads to your profiles folder\n"
                "(about 150 MB) and does not touch your normal Chrome.\n\n"
                "Download it now?"):
            return

        win = tk.Toplevel(self.root)
        win.title("Downloading")
        win.geometry("460x150")
        win.configure(bg=self.BG)
        message = tk.StringVar(value="Starting...")
        tk.Label(win, textvariable=message, bg=self.BG, fg=self.FG,
                 font=('Segoe UI', 9), wraplength=420, justify=tk.LEFT
                 ).pack(padx=16, pady=28)
        win.update()

        state = {}

        def progress(text):
            message.set(text)
            try:
                win.update()
            except Exception:
                pass

        try:
            exe, version = self.generator.download_chrome_for_testing(progress)
            state['exe'] = exe
            state['version'] = version
        except Exception as e:
            win.destroy()
            messagebox.showerror(
                "Download failed",
                "%s\n\nYou can also install Brave or Chromium and pick it "
                "with Browse..." % e)
            return

        win.destroy()
        self._refresh_browser_label()
        self.us_status_var.set("Chrome for Testing %s selected" % state['version'])
        messagebox.showinfo(
            "Ready",
            "Chrome for Testing %s is installed and selected:\n%s\n\n"
            "Now press 'Apply to all profiles' so every shortcut uses it.\n"
            "Extensions and scripts will load with no prompt."
            % (state['version'], state['exe']))

    def _choose_browser(self):
        win = tk.Toplevel(self.root)
        win.title("Choose browser")
        win.geometry("720x360")
        win.configure(bg=self.BG)
        win.columnconfigure(0, weight=1)
        win.rowconfigure(1, weight=1)

        tk.Label(win, bg=self.BG, fg=self.FG_MUTED, justify=tk.LEFT, anchor=tk.W,
                 font=('Segoe UI', 8), wraplength=680,
                 text=("Every profile is launched with the browser you pick here.\n"
                       "Chromium, Brave and Chrome for Testing still honour "
                       "--load-extension, so scripts load with no prompt and no "
                       "debug port. Google Chrome 142+ does not.")
                 ).grid(row=0, column=0, sticky=(tk.W, tk.E), padx=12, pady=(12, 8))

        cols = ('brand', 'version', 'ext', 'path')
        tree = ttk.Treeview(win, columns=cols, show='headings', selectmode='browse')
        for col, title, width in (('brand', 'Browser', 130), ('version', 'Version', 110),
                                  ('ext', 'Extensions', 110), ('path', 'Path', 340)):
            tree.heading(col, text=title)
            tree.column(col, width=width, anchor=tk.W)
        tree.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=12)

        found = []
        try:
            found = self.generator.browser_candidates()
        except Exception as e:
            messagebox.showerror("Error", str(e))
        current = self.generator.browser_override()
        for item in found:
            iid = item['path']
            tree.insert('', tk.END, iid=iid, values=(
                item['brand'], item['version'] or '?',
                'yes' if item['load_extension'] else 'no', item['path']))
            if os.path.normcase(iid) == os.path.normcase(current or ''):
                tree.selection_set(iid)
        if not tree.selection() and found:
            tree.selection_set(found[0]['path'])

        def use_selected():
            sel = tree.selection()
            if not sel:
                return
            apply_path(sel[0])

        def browse():
            types = [("Browser", "*.exe"), ("All files", "*.*")] \
                if platform.system() == 'Windows' else [("All files", "*.*")]
            path = filedialog.askopenfilename(title="Select a browser executable",
                                              filetypes=types)
            if path and self._check_engine(path):
                apply_path(path)

        def apply_path(path):
            self.generator.set_browser_override(path)
            win.destroy()
            self._refresh_browser_label()
            self.us_status_var.set(
                "Browser set - press Apply to all profiles to rebuild shortcuts")

        def use_default():
            self.generator.set_browser_override('')
            win.destroy()
            self._refresh_browser_label()

        bar = tk.Frame(win, bg=self.BG)
        bar.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=12, pady=10)
        def download():
            win.destroy()
            self._download_browser()

        ttk.Button(bar, text="Download Chrome for Testing",
                   style='Accent.TButton',
                   command=download).pack(side=tk.LEFT)
        ttk.Button(bar, text="Browse...", style='Ghost.TButton',
                   command=browse).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(bar, text="Auto-detect", style='Ghost.TButton',
                   command=use_default).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(bar, text="Use selected", style='Accent.TButton',
                   command=use_selected).pack(side=tk.RIGHT)
        tree.bind('<Double-1>', lambda e: use_selected())

    def _show_report(self, name, verdict, body):
        """One window, one block of text. The caller decides what goes in it."""
        win = tk.Toplevel(self.root)
        win.title("Injection report - %s" % name)
        win.geometry("820x560")
        win.configure(bg=self.BG)
        win.columnconfigure(0, weight=1)
        win.rowconfigure(1, weight=1)

        tk.Label(win, text=verdict, bg=self.BG, fg=self.FG,
                 font=('Segoe UI', 9, 'bold'), justify=tk.LEFT,
                 anchor=tk.W, wraplength=780
                 ).grid(row=0, column=0, sticky=(tk.W, tk.E), padx=12, pady=(12, 6))

        box = scrolledtext.ScrolledText(
            win, bg=self.BG_CARD_2, fg=self.FG, font=('Consolas', 9),
            highlightthickness=0, borderwidth=0, wrap=tk.NONE)
        box.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=12)
        box.insert('1.0', body)
        box.configure(state=tk.DISABLED)

        bar = tk.Frame(win, bg=self.BG)
        bar.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=12, pady=10)

        def copy_all():
            self.root.clipboard_clear()
            self.root.clipboard_append(body)
            self.us_status_var.set("Report copied to clipboard")

        ttk.Button(bar, text="Copy all", style='Accent.TButton',
                   command=copy_all).pack(side=tk.LEFT)
        ttk.Button(bar, text="Close", style='Ghost.TButton',
                   command=win.destroy).pack(side=tk.RIGHT)
        win.lift()
        win.focus_force()

    def _change_injection_mode(self):
        self.generator.set_injection_mode(self.us_mode_var.get())
        warning = ''
        try:
            warning = self.generator.browser_warning()
        except Exception:
            pass
        self.us_warn_var.set(warning)
        if warning:
            self.us_warn_frame.grid(row=2, column=0, columnspan=2,
                                    sticky=(tk.W, tk.E), pady=(7, 0))
        else:
            self.us_warn_frame.grid_forget()
        self.us_status_var.set(
            "Injection mode: %s - press Apply to all profiles"
            % self.us_mode_var.get())

    def _toggle_devtools_guard(self):
        """v4.9: turn the in-page DevTools guard on or off."""
        self.generator.set_guard_devtools(self.us_guard_var.get())
        self.us_status_var.set(
            "DevTools guard %s - press Apply to all profiles"
            % ('ON' if self.us_guard_var.get() else 'OFF'))

    def _toggle_auto_site_lock(self):
        """v4.11: lock each generated profile to its own start URL."""
        self.generator.set_auto_site_lock(self.us_autolock_var.get())
        self.us_status_var.set(
            "Leave-site lock %s - press Apply to all profiles"
            % ('ON' if self.us_autolock_var.get() else 'OFF'))

    def _toggle_userscripts_master(self):
        self.generator.set_userscripts_enabled(self.us_enabled_var.get())
        self._refresh_userscripts()

    def _toggle_userscript_requires(self):
        self.generator.set_userscript_download_requires(self.us_requires_var.get())

    def _refresh_userscripts(self, select_file=None):
        for item in self.us_tree.get_children():
            self.us_tree.delete(item)
        entries = self.generator.list_userscripts()
        self._us_entries = {e['file']: e for e in entries}
        target = None
        for entry in entries:
            iid = entry['file']
            tags = () if entry['enabled'] else ('off',)
            self.us_tree.insert('', tk.END, iid=iid, tags=tags, values=(
                '✓' if entry['enabled'] else '·',
                entry['display_name'],
                entry.get('run_at', 'document-idle').replace('document-', ''),
            ))
            if select_file and iid == select_file:
                target = iid
        report = self.generator.userscript_report()
        master = "" if self.generator.userscripts_enabled() else "  ·  injection OFF"
        self.us_status_var.set(
            "%d script(s), %d active%s" % (report['total'], report['enabled'], master))
        if target:
            self.us_tree.selection_set(target)
            self.us_tree.focus(target)
        elif self.us_current_file in self._us_entries:
            self.us_tree.selection_set(self.us_current_file)
        elif entries:
            self.us_tree.selection_set(entries[0]['file'])
        else:
            self.us_current_file = None
            self.us_title_var.set("No script selected")
            self.us_meta_var.set("Press New to create one")
            self.us_editor.delete('1.0', tk.END)

    def _current_userscript(self):
        selection = self.us_tree.selection()
        if not selection:
            return None
        return getattr(self, '_us_entries', {}).get(selection[0])

    def _on_userscript_select(self, event=None):
        entry = self._current_userscript()
        if not entry:
            return
        self.us_current_file = entry['file']
        self.us_editor.delete('1.0', tk.END)
        self.us_editor.insert('1.0', entry['source'])
        self.us_editor.edit_reset()
        self.us_title_var.set("%s  ·  %s" % (entry['display_name'], entry['file']))
        patterns = entry.get('matches') or entry.get('includes') or ['(all sites)']
        shown = ', '.join(patterns[:3])
        if len(patterns) > 3:
            shown += ' +%d more' % (len(patterns) - 3)
        self.us_meta_var.set("%s  ·  %s  ·  world %s  ·  %s" % (
            shown, entry.get('run_at', 'document-idle'),
            entry.get('world', 'MAIN'),
            'enabled' if entry['enabled'] else 'disabled'))

    def _new_userscript(self):
        base = "My Script"
        existing = {e['display_name'] for e in self.generator.list_userscripts()}
        name = base
        n = 2
        while name in existing:
            name = "%s %d" % (base, n)
            n += 1
        file_name = self.generator.save_userscript(
            self.generator.userscript_template(name))
        self.us_current_file = file_name
        self._refresh_userscripts(select_file=file_name)
        try:
            self.us_editor.focus_set()
        except Exception:
            pass

    def _import_userscript(self):
        paths = filedialog.askopenfilenames(
            title="Import user script(s)",
            filetypes=[("User scripts", "*.user.js"),
                       ("JavaScript", "*.js"),
                       ("All files", "*.*")])
        if not paths:
            return
        last = None
        for path in paths:
            try:
                last = self.generator.import_userscript(path)
            except Exception as e:
                messagebox.showerror("Import failed", f"{os.path.basename(path)}\n\n{e}")
        self._refresh_userscripts(select_file=last)

    def _save_userscript(self):
        source = self.us_editor.get('1.0', tk.END)
        if source.endswith('\n'):
            source = source[:-1]
        if not self.us_current_file:
            if not source.strip():
                return
            self.us_current_file = self.generator.save_userscript(source)
        else:
            self.generator.save_userscript(source, self.us_current_file)
        meta = self.generator.parse_userscript_metadata(source)
        if not meta['matches'] and not meta['includes']:
            self.us_status_var.set(
                "Saved · no @match/@include, so it runs on every page")
        else:
            self.us_status_var.set("Saved " + self.us_current_file)
        self._refresh_userscripts(select_file=self.us_current_file)

    def _save_and_apply_userscript(self):
        self._save_userscript()
        self._apply_userscripts_to_profiles()

    def _revert_userscript(self):
        if not self.us_current_file:
            return
        source = self.generator.get_userscript_source(self.us_current_file)
        self.us_editor.delete('1.0', tk.END)
        self.us_editor.insert('1.0', source)

    def _toggle_userscript(self, event=None):
        entry = self._current_userscript()
        if not entry:
            return 'break'
        self.generator.set_userscript_enabled(entry['file'], not entry['enabled'])
        self._refresh_userscripts(select_file=entry['file'])
        return 'break'

    def _delete_userscript(self):
        entry = self._current_userscript()
        if not entry:
            messagebox.showwarning("Warning", "Select a script first")
            return
        if not messagebox.askyesno(
                "Confirm delete",
                f"Delete '{entry['display_name']}'?\n\n"
                f"File: {entry['file']}\nThis cannot be undone."):
            return
        self.generator.delete_userscript(entry['file'])
        if self.us_current_file == entry['file']:
            self.us_current_file = None
            self.us_editor.delete('1.0', tk.END)
        self._refresh_userscripts()

    def _apply_userscripts_to_profiles(self):
        profiles = self.generator.get_all_profiles()
        if not profiles:
            messagebox.showinfo(
                "No profiles yet",
                "There are no profiles to update.\n\n"
                "Scripts are compiled into every profile you create from now on.")
            return
        try:
            stale = self.generator.profile_pool_violations()
        except Exception:
            stale = []
        if stale:
            sample = ', '.join(
                '%s (%s %sx%s)' % (s['name'], s['language'],
                                   s['size'][0], s['size'][1])
                for s in stale[:3])
            if messagebox.askyesno(
                    "Update languages and screen sizes?",
                    f"{len(stale)} profile(s) still use a language or screen size\n"
                    f"that is no longer in your allowed list, for example:\n\n"
                    f"  {sample}\n\n"
                    "Rewrite them to the allowed values now?"):
                fixed, total = self.generator.migrate_all_profiles(
                    rebuild_shortcuts=False)
                self.us_status_var.set("Updated %d/%d profile(s)" % (fixed, total))
                self.root.update_idletasks()

        self.us_status_var.set("Rebuilding %d profile(s)…" % len(profiles))
        self.root.update_idletasks()

        def progress(done, total, name):
            self.us_status_var.set("Rebuilding %d/%d · %s" % (done, total, name))
            self.root.update_idletasks()

        try:
            done, total = self.generator.sync_userscripts_to_all_profiles(
                rebuild_shortcuts=True, progress=progress)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to apply scripts:\n{e}")
            self._refresh_userscripts()
            return

        report = self.generator.userscript_report()
        self._refresh_userscripts()
        names = '\n'.join('  • ' + n for n in report['names'][:12]) or '  (none)'
        if len(report['names']) > 12:
            names += '\n  …'
        messagebox.showinfo(
            "Applied",
            f"{report['enabled']} active script(s) written into {done}/{total} profile(s).\n\n"
            f"{names}\n\n"
            "Desktop shortcuts were refreshed so Chrome loads the script\n"
            "extension. Close and reopen any profile that is already running.")

    def _delete_profile(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a profile to delete")
            return

        item = self.tree.item(selection[0])
        profile_name = item['values'][0]

        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete profile '{profile_name}'?\n\n"
            "This will also delete the desktop shortcut.\n"
            "This action cannot be undone."
        )

        if confirm:
            if self.generator.delete_profile(profile_name):
                messagebox.showinfo("Success", f"Profile '{profile_name}' and shortcut deleted successfully")
                self._refresh_profiles()
            else:
                messagebox.showerror("Error", "Failed to delete profile")


def _self_launch_profile(profile_name):
    """Legacy '--launch-profile NAME' entry point.

    v4.4: delegates to the unified launcher so it honours this profile's
    browser (Chrome or Firefox), its Facebook-by-default start page and the
    DevTools guard, instead of duplicating the command line.
    """
    gen = ChromeProfileGenerator()
    profile_path = os.path.join(gen.profiles_dir, profile_name)
    if not os.path.exists(profile_path):
        return 1

    # v6.2: a shortcut launch learns the current switch, plan and scripts
    # first. The check-in is bounded so an offline PC is not held up; the
    # last signed state (with its grace window) applies meanwhile.
    client = gen.license()
    if client is not None:
        try:
            import threading as _th
            _t = _th.Thread(target=client.check_in, daemon=True)
            _t.start()
            _t.join(6)
        except Exception:
            pass
        blocked = None
        try:
            if not client.app_allowed():
                blocked = ('Application disabled', client.blocked_reason())
            elif client.needs_update():
                blocked = ('Update required',
                           'A required update is available. Open '
                           + gen.TOOL_NAME + ' to install it, then try again.')
        except Exception:
            blocked = None
        if blocked:
            try:
                import tkinter.messagebox as _mb
                _root = tk.Tk(); _root.withdraw()
                _mb.showwarning(blocked[0], blocked[1])
            except Exception:
                pass
            return 4

    if not gen.browser_for_profile(profile_name):
        try:
            import tkinter.messagebox as _mb
            _root = tk.Tk(); _root.withdraw()
            _mb.showerror("Browser not found",
                          "Could not find a browser on this system.\n"
                          "Please install Chrome or Firefox to use this profile.")
        except Exception:
            pass
        return 2

    try:
        gen.launch_profile(profile_name, profile_path)
        return 0
    except AppDisabledError as e:
        try:
            import tkinter.messagebox as _mb
            _root = tk.Tk(); _root.withdraw()
            _mb.showwarning('Application disabled', str(e))
        except Exception:
            pass
        return 4
    except Exception as e:
        # already-open or a build error: fall back to a plain, script-free open
        import subprocess as _sp
        exe = gen.browser_for_profile(profile_name)
        start_url = gen.normalize_url(gen.start_url_for(profile_name)) \
            or gen.DEFAULT_START_URL
        if gen.browser_engine(exe) == 'gecko':
            args = [exe, '-profile', profile_path, '-no-remote', start_url]
        else:
            args = [exe, '--user-data-dir=' + profile_path, start_url]
        try:
            _sp.Popen([a for a in args if a], close_fds=True)
            return 0
        except Exception as e2:
            try:
                import tkinter.messagebox as _mb
                _root = tk.Tk(); _root.withdraw()
                _mb.showerror("Launch failed",
                              "Could not launch the browser:\n%s" % (e2 or e))
            except Exception:
                pass
            return 3


def _open_tool_home():
    """v4.4: open the tool's home page in the user's OWN default browser.

    Runs once each time the tool starts, in a background thread so a slow
    browser launch never delays the window from appearing. Never raises.
    """
    def go():
        try:
            import webbrowser
            # v6.0: domain-independent. Prefer the licence client's configured
            # API base (env / sidecar config), so moving the site to another
            # domain needs no rebuild; fall back to the built-in default.
            url = ChromeProfileGenerator.TOOL_HOME_URL
            try:
                if _license is not None:
                    base = getattr(_license, 'API_BASE', '')
                    if base:
                        url = base
            except Exception:
                pass
            webbrowser.open_new_tab(url)
        except Exception:
            pass
    try:
        import threading as _th
        _th.Thread(target=go, daemon=True).start()
    except Exception:
        go()


def main():
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == '--launch-profile':
        sys.exit(_self_launch_profile(args[1]))
    # v6.0: when frozen, run a helper script in-process. The launcher,
    # injector and heartbeat are started with this flag because a frozen
    # sys.executable is the app EXE, not a python interpreter.
    if len(args) >= 2 and args[0] == '--run-script':
        import runpy
        script = args[1]
        sys.argv = [script] + args[2:]
        try:
            runpy.run_path(script, run_name='__main__')
        except SystemExit:
            raise
        except Exception as exc:
            print('run-script failed:', exc)
        return 0

    # v4.4: always open mavlink.click in the default browser on start-up
    _open_tool_home()

    # v7.0.0: must happen before the first Tk window exists, or Windows has
    # already decided to bitmap-stretch the app and the choice cannot be
    # taken back. See _enable_dpi_awareness() for why this matters.
    _enable_dpi_awareness()

    root = tk.Tk()
    app = ChromeProfileGeneratorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()