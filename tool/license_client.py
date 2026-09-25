"""
license_client.py  -  talks to the MavelyLink licensing site.

Design notes that matter:
  * Pure standard library, so it survives a PyInstaller / Nuitka freeze.
  * Ed25519 verification of every server token, using an EMBEDDED public
    key. A fake server (hosts file, DNS) cannot mint a token this accepts.
  * Fails OPEN inside a grace window: if the server is unreachable the tool
    keeps working for GRACE_DAYS, so an outage does not lock out paying
    users. It fails CLOSED only once grace has genuinely elapsed.
  * The local state file is signed with an HMAC keyed on a stable
    per-machine value, so it cannot be copied to another PC or edited to
    extend a licence. On Windows the whole file is also encrypted with DPAPI.
  * Nothing here trusts the local clock to EXTEND anything. If the clock
    moves backwards the grace window is treated as expired.
"""

import base64
import calendar
import hashlib
import hmac
import json
import os
import platform
import re
import ssl
import tempfile
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# configuration - EDIT the public key below before you build
# ---------------------------------------------------------------------------

# The PUBLIC signing key for your server, base64.
#
# Get it from the admin dashboard: Settings -> Licence signing keys ->
# LICENSE_PUBLIC_KEY_B64, and use the copy button there. It is about 44
# characters and ends in "=".
#
# Only the public half. Never put the secret key in the client.
#
# THIS IS NOT THE SERVER ADDRESS. The address is _DEFAULT_API_BASE, below.
# In 6.2.0 the site URL had been pasted here, which broke every activation:
# base64 decoding "https://mavlink.click/" does not raise - the characters
# that are not in the base64 alphabet are simply dropped - it just yields 15
# bytes where Ed25519 needs 32, so every signature check failed and the tool
# refused activation responses from its own server. _license_public_key()
# below now rejects a wrong-sized key loudly instead of failing silently.
LICENSE_PUBLIC_KEY_B64 = "vhgVP+B6JCnatBDP1vdSpGZLvCCKPQ4JrEL8hvuB4M0="

APP_VERSION = "6.2.0"
HEARTBEAT_SECONDS = 3600          # background re-check once an hour
NETWORK_TIMEOUT = 20

# ---------------------------------------------------------------------------
# server address - ONE place, domain-independent.
#
# The website can be deployed to any domain, so the client must not be nailed
# to one forever. The address is resolved (first hit wins) from:
#   1) the MAVELYLINK_API_BASE environment variable
#   2) a "mavely_config.json" ({"api_base": "https://your-domain.com"}) placed
#      next to the executable OR in the per-user MavelyLink data folder
#   3) the built-in default below
# So moving the tool to a new domain is a one-line config change, no rebuild.
# API_BASE is resolved once at import (see the bottom of this module).
# ---------------------------------------------------------------------------
_DEFAULT_API_BASE = "https://mavlink.click/"


def _read_api_base_from_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            val = str(data.get("api_base") or data.get("API_BASE") or "").strip()
            if val:
                return val.rstrip("/")
    except Exception:
        pass
    return ""


def _resolve_api_base() -> str:
    env = (os.environ.get("MAVELYLINK_API_BASE") or "").strip()
    if env:
        return env.rstrip("/")

    candidates = []
    try:
        if getattr(sys, "frozen", False):
            candidates.append(os.path.join(os.path.dirname(sys.executable),
                                           "mavely_config.json"))
        candidates.append(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "mavely_config.json"))
    except Exception:
        pass
    try:
        candidates.append(os.path.join(_state_dir(), "mavely_config.json"))
    except Exception:
        pass
    for path in candidates:
        val = _read_api_base_from_file(path)
        if val:
            return val

    return _DEFAULT_API_BASE


# ---------------------------------------------------------------------------
# base64url helpers (JWT style, no padding)
# ---------------------------------------------------------------------------
def _b64u_decode(txt: str) -> bytes:
    pad = "=" * (-len(txt) % 4)
    return base64.urlsafe_b64decode(txt + pad)


# ---------------------------------------------------------------------------
# Ed25519 verify with no third-party dependency.
#   Uses cryptography if it happens to be present, otherwise a compact
#   pure-python implementation. Verify-only, so it is not performance
#   sensitive.
# ---------------------------------------------------------------------------
def _verify_ed25519(public_key: bytes, signature: bytes, message: bytes) -> bool:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
        from cryptography.exceptions import InvalidSignature
        try:
            Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
            return True
        except InvalidSignature:
            return False
    except Exception:
        pass
    try:
        return _ed25519_pure_verify(public_key, signature, message)
    except Exception:
        return False


# --- minimal pure-python Ed25519 verification (RFC 8032) -------------------
_p = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_d = (-121665 * pow(121666, _p - 2, _p)) % _p
_I = pow(2, (_p - 1) // 4, _p)


def _xrecover(y):
    xx = (y * y - 1) * pow(_d * y * y + 1, _p - 2, _p)
    x = pow(xx, (_p + 3) // 8, _p)
    if (x * x - xx) % _p != 0:
        x = (x * _I) % _p
    if x % 2 != 0:
        x = _p - x
    return x


_By = (4 * pow(5, _p - 2, _p)) % _p
_Bx = _xrecover(_By)
_B = (_Bx % _p, _By % _p, 1, (_Bx * _By) % _p)


def _edwards_add(P, Q):
    x1, y1, z1, t1 = P
    x2, y2, z2, t2 = Q
    a = ((y1 - x1) * (y2 - x2)) % _p
    b = ((y1 + x1) * (y2 + x2)) % _p
    c = (2 * t1 * t2 * _d) % _p
    dd = (2 * z1 * z2) % _p
    e = b - a
    f = dd - c
    g = dd + c
    h = b + a
    return (e * f % _p, g * h % _p, f * g % _p, e * h % _p)


def _scalarmult(P, e):
    if e == 0:
        return (0, 1, 1, 0)
    Q = _scalarmult(P, e // 2)
    Q = _edwards_add(Q, Q)
    if e & 1:
        Q = _edwards_add(Q, P)
    return Q


def _encode_point(P):
    x, y, z, _t = P
    zi = pow(z, _p - 2, _p)
    x = (x * zi) % _p
    y = (y * zi) % _p
    bits = [(y >> i) & 1 for i in range(255)] + [x & 1]
    return bytes(sum(bits[i * 8 + j] << j for j in range(8)) for i in range(32))


def _bit(h, i):
    return (h[i // 8] >> (i % 8)) & 1


def _decode_point(s):
    y = sum(2 ** i * _bit(s, i) for i in range(255))
    x = _xrecover(y)
    if x & 1 != _bit(s, 255):
        x = _p - x
    P = (x, y, 1, (x * y) % _p)
    if not _is_on_curve(P):
        raise ValueError("point not on curve")
    return P


def _is_on_curve(P):
    x, y, z, t = P
    return (
        z % _p != 0
        and x * y % _p == z * t % _p
        and (y * y - x * x - z * z - _d * t * t) % _p == 0
    )


def _ed25519_pure_verify(public_key, signature, message):
    if len(signature) != 64 or len(public_key) != 32:
        return False
    A = _decode_point(public_key)
    R = _decode_point(signature[:32])
    S = int.from_bytes(signature[32:], "little")
    if S >= _L:
        return False
    h = int.from_bytes(
        hashlib.sha512(signature[:32] + public_key + message).digest(), "little"
    ) % _L
    left = _scalarmult(_B, S)
    right = _edwards_add(R, _scalarmult(A, h))
    return _encode_point(left) == _encode_point(right)


# ---------------------------------------------------------------------------
# device identity: stable per machine, sent only as a hash
# ---------------------------------------------------------------------------
def _machine_raw() -> str:
    parts = [platform.node() or "", platform.machine() or ""]
    system = platform.system()
    try:
        if system == "Windows":
            out = subprocess.check_output(
                ["wmic", "csproduct", "get", "UUID"],
                stderr=subprocess.DEVNULL, timeout=10,
                creationflags=0x08000000,
            ).decode(errors="ignore")
            parts.append("".join(out.split("\n")[1:]).strip())
            vol = subprocess.check_output(
                ["cmd", "/c", "vol", "c:"],
                stderr=subprocess.DEVNULL, timeout=10,
                creationflags=0x08000000,
            ).decode(errors="ignore")
            parts.append(vol.strip())
        elif system == "Darwin":
            out = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                stderr=subprocess.DEVNULL, timeout=10,
            ).decode(errors="ignore")
            for line in out.split("\n"):
                if "IOPlatformUUID" in line:
                    parts.append(line.split('"')[-2])
                    break
        else:
            for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                if os.path.exists(path):
                    with open(path) as f:
                        parts.append(f.read().strip())
                    break
    except Exception:
        pass
    return "|".join(p for p in parts if p)


def device_hash() -> str:
    return hashlib.sha256(_machine_raw().encode("utf-8", "ignore")).hexdigest()


def device_label() -> str:
    return (platform.node() or "PC")[:120]


# ---------------------------------------------------------------------------
# local state, tamper-evident and machine-bound
# ---------------------------------------------------------------------------
def _state_dir() -> str:
    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    elif platform.system() == "Darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    d = os.path.join(base, "MavelyLink")
    os.makedirs(d, exist_ok=True)
    return d


def _state_path() -> str:
    return os.path.join(_state_dir(), "license.bin")


def _dpapi_available() -> bool:
    return platform.system() == "Windows"


def _dpapi(func_name: str, data: bytes) -> bytes:
    """Call CryptProtectData / CryptUnprotectData. Returns b'' on failure.

    Unlike the previous code, DPAPI is used to encrypt the STORED STATE, not
    to derive the HMAC key. CryptProtectData embeds a fresh random salt every
    call, so hashing its output produced a DIFFERENT key on every run and the
    saved licence never validated after a restart - the reported bug. Here the
    protect/unprotect pair round-trips correctly, so state written on this
    machine is read back on this machine, and cannot be read on another.
    """
    import ctypes
    import ctypes.wintypes as wt

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = BLOB()
    fn = getattr(ctypes.windll.crypt32, func_name)
    if not fn(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        return b""
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _state_key() -> bytes:
    """Deterministic HMAC key bound to this machine.

    Stable across runs (no DPAPI here), so the tamper tag verifies after a
    restart. Tied to the machine fingerprint so a state file copied to another
    computer fails the tag check and is ignored.
    """
    raw = ("mvl-state-v2|" + _machine_raw()).encode("utf-8", "ignore")
    return hashlib.sha256(raw).digest()


# a small fixed prefix marks a DPAPI-wrapped payload on disk
_STATE_MAGIC = b"MVL2"


def _save_state(data: dict) -> None:
    body = json.dumps(data, separators=(",", ":")).encode("utf-8")
    tag = hmac.new(_state_key(), body, hashlib.sha256).digest()
    blob = tag + body
    # On Windows, additionally wrap the whole thing with DPAPI so the licence
    # is not sitting in plain text. The HMAC tag still binds it to this machine
    # even where DPAPI is unavailable.
    if _dpapi_available():
        try:
            protected = _dpapi("CryptProtectData", blob)
            if protected:
                blob = _STATE_MAGIC + protected
        except Exception:
            pass
    try:
        path = _state_path()
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(blob)
        os.replace(tmp, path)   # atomic: never leaves a half-written state file
    except Exception:
        pass


def _load_state() -> dict:
    try:
        with open(_state_path(), "rb") as f:
            blob = f.read()
    except Exception:
        return {}
    wrapped = blob[:4] == _STATE_MAGIC
    if wrapped:
        if not _dpapi_available():
            return {}   # written on Windows, opened elsewhere: cannot read
        try:
            blob = _dpapi("CryptUnprotectData", blob[4:])
        except Exception:
            return {}
        if not blob:
            return {}
    if len(blob) < 33:
        return {}
    tag, body = blob[:32], blob[32:]
    if not hmac.compare_digest(tag, hmac.new(_state_key(), body, hashlib.sha256).digest()):
        # tampered, corrupt, copied from another machine - or written by a
        # build before v6.2, whose key changed on every run. Only the last
        # case can be rescued, and only through the signed token inside.
        return _legacy_state_import(body) if not wrapped else {}
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return {}


def _legacy_state_import(body: bytes) -> dict:
    """Recover a licence saved by a build before v6.2.

    Those builds derived the file key from DPAPI output, which changes on every
    call, so their state file never verified again - the "serial asked again
    after restart" bug. The file itself is therefore untrusted, but the session
    token inside is Ed25519-signed by the server. Only facts the signature
    vouches for are imported, and only when the token belongs to THIS computer.
    Everything else (switch, update policy, scripts) is re-learned at the next
    check-in, which also renews the token.
    """
    try:
        old = json.loads(body.decode("utf-8"))
    except Exception:
        return {}
    if not isinstance(old, dict):
        return {}
    token = str(old.get("token", "") or "")
    claims = _verify_token(token, TOKEN_LEEWAY_SECONDS) if token else {}
    if not claims or not hmac.compare_digest(str(claims.get("device", "")), device_hash()):
        return {}
    tier = str(claims.get("tier", "") or "")
    return {
        "token": token,
        "serial": str(claims.get("serial", "") or ""),
        "tier": tier if tier in ("pro", "team") else "free",
        "last_ok": time.time(),   # the grace window restarts from the import
        "legacy_imported": True,
    }


# ---------------------------------------------------------------------------
# v6.2.1: Free-plan profile baseline  (section 7, Option A)
#
# The Free plan allows 5 browser profiles, but the check used to compare that
# cap against EVERY profile folder on disk. Anyone who had used the tool
# before the Free/Pro model existed was therefore over the cap from the very
# first launch - 59 profiles against a cap of 5 - and "Generate New Profile"
# could never do anything again.
#
# The cap now applies only to profiles created from this version onwards.
# Whatever already existed the first time this code runs is recorded here as
# the baseline and permanently grandfathered: those profiles keep working,
# keep opening, and never count against the cap. A brand-new install records
# an empty baseline, so a fresh Free user gets exactly the 5 profiles the
# plan promises.
#
# This is a product limit, not a security boundary. It sits in a plain JSON
# file for the same reason the rest of the Free-plan enforcement is
# client-side: it exists to be honest with the user, not to resist them.
# Paid entitlements are the ones the server signs.
# ---------------------------------------------------------------------------
def _free_baseline_path() -> str:
    return os.path.join(_state_dir(), "free_profiles.json")


def _free_baseline_read() -> dict:
    try:
        with open(_free_baseline_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("grandfathered"), list):
            return data
    except Exception:
        pass
    return {}


def free_baseline_names(current_names=None) -> set:
    """The profile names that predate the Free cap and are exempt from it.

    Captured once, the first time this runs on a machine. `current_names` is
    what exists on disk right now; pass it so the very first call can record
    the baseline. Returns an empty set for a fresh install.
    """
    data = _free_baseline_read()
    if data:
        return set(str(n) for n in data.get("grandfathered", []))

    names = sorted(set(str(n) for n in (current_names or [])))
    try:
        tmp = _free_baseline_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({
                "grandfathered": names,
                "captured": int(time.time()),
                "note": ("Profiles that existed before the Free plan cap applied. "
                         "They are exempt from it and keep working. Delete this file "
                         "to make every profile on disk count against the cap again."),
            }, f, indent=2)
        os.replace(tmp, _free_baseline_path())
    except Exception:
        # if it cannot be written we still exempt what is there right now, so
        # a read-only data folder can never dead-end profile generation
        pass
    return set(names)


def free_new_profile_count(current_names) -> int:
    """How many profiles count against the Free cap: those created after the
    baseline was taken. Never negative."""
    current = set(str(n) for n in (current_names or []))
    return max(0, len(current - free_baseline_names(current)))


def app_marker_path() -> str:
    """Small file the per-profile launchers read before starting a browser."""
    return os.path.join(_state_dir(), "app_state.json")


def _write_app_marker(enabled: bool, message: str) -> None:
    """Record the master-switch state learned from a SIGNED check-in, so a
    desktop shortcut cannot open a profile while the administrator has the
    application turned off."""
    try:
        path = app_marker_path()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"app_enabled": bool(enabled), "message": str(message or ""),
                       "updated": int(time.time())}, f)
        os.replace(tmp, path)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# configuration derived from the server (safe defaults for older builds)
# ---------------------------------------------------------------------------
CHECKIN_SECONDS_DEFAULT = 180      # overridden by the server's next_checkin_seconds
CHECKIN_SECONDS_MIN = 60
CHECKIN_SECONDS_MAX = 3600
GRACE_DAYS = 7                     # offline tolerance for a paid licence
TOKEN_LEEWAY_SECONDS = 45 * 86400  # a genuine expired token may still be renewed


# ---------------------------------------------------------------------------
# token: decode + verify (Ed25519, embedded public key)
# ---------------------------------------------------------------------------
def _license_public_key() -> bytes:
    """The embedded public key as 32 raw bytes, or b'' if it is not usable.

    Validated strictly, because base64.b64decode() is far too forgiving to
    catch a mistake here on its own: it silently drops every character that
    is not in the base64 alphabet, so a pasted URL, a fingerprint or a
    truncated key all "decode" into something of the wrong length instead of
    raising. A key that is not exactly 32 bytes is no key at all.
    """
    raw_text = (LICENSE_PUBLIC_KEY_B64 or "").strip()
    if not raw_text or raw_text.startswith("PASTE_"):
        return b""
    try:
        # validate=True rejects stray characters outright rather than
        # quietly discarding them
        public = base64.b64decode(raw_text, validate=True)
    except Exception:
        return b""
    if len(public) != 32:
        return b""
    return public


def license_key_problem() -> str:
    """'' when the embedded key looks usable, else a sentence saying what is
    wrong. Used to explain an activation failure in plain language instead of
    letting it surface as a bare signature mismatch."""
    raw_text = (LICENSE_PUBLIC_KEY_B64 or "").strip()
    if not raw_text or raw_text.startswith("PASTE_"):
        return ("This build has no licence signing key. Rebuild the tool with "
                "LICENSE_PUBLIC_KEY_B64 set to the public key from the admin "
                "dashboard (Settings > Licence signing keys).")
    if "://" in raw_text or raw_text.startswith("http"):
        return ("LICENSE_PUBLIC_KEY_B64 in this build contains a web address, not a "
                "signing key. Rebuild the tool with the public key from the admin "
                "dashboard (Settings > Licence signing keys).")
    if not _license_public_key():
        return ("The licence signing key in this build is not valid. Rebuild the tool "
                "with the public key from the admin dashboard "
                "(Settings > Licence signing keys).")
    return ""


def _verify_token(token: str, leeway_seconds: int = 0) -> dict:
    """Verify an Ed25519-signed token. leeway_seconds lets a genuine token
    that expired recently still verify, so the app keeps working offline
    while the server (not the token) decides if the licence is still good."""
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except (ValueError, AttributeError):
        return {}
    public = _license_public_key()
    if not public:
        return {}
    message = (header_b64 + "." + payload_b64).encode("ascii")
    if not _verify_ed25519(public, _b64u_decode(sig_b64), message):
        return {}
    try:
        claims = json.loads(_b64u_decode(payload_b64))
    except Exception:
        return {}
    if not isinstance(claims, dict):
        return {}
    exp = int(claims.get("exp", 0))
    if exp and (exp + max(0, leeway_seconds)) < time.time():
        return {}
    return claims


# ---------------------------------------------------------------------------
# HTTP (standard library only, so it survives a PyInstaller freeze)
# ---------------------------------------------------------------------------
def _http(method: str, path: str, payload: dict = None, token: str = "") -> dict:
    url = API_BASE + path
    data = None
    headers = {"User-Agent": "MavelyLink/" + APP_VERSION, "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=NETWORK_TIMEOUT, context=ctx) as resp:
        raw = resp.read().decode("utf-8", "replace")
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


def _post(path: str, payload: dict) -> dict:
    return _http("POST", path, payload)


def _get(path: str, token: str) -> dict:
    return _http("GET", path, None, token)


# ---------------------------------------------------------------------------
# the client the GUI talks to
# ---------------------------------------------------------------------------
class LicenseClient:
    """Talks to the MavelyLink server and holds the current plan state.

    v6.2 model: FREE is the baseline. The tool runs whenever the master
    switch is on, even with no licence. A Pro or Team licence unlocks paid
    features while its signed token is valid (within an offline grace
    window). Everything decisive - the plan, the app on/off switch, the
    update policy and the script manifest - arrives on ONE signed check-in
    (see the server's /api/v1/checkin.php), so a random HTTP response cannot
    forge any of it. Scripts are held in memory, never written to disk.
    """

    def __init__(self):
        self.device = device_hash()
        self._lock = threading.RLock()
        self._hb_thread = None
        self._hb_stop = threading.Event()

        st = _load_state()
        self.token = st.get("token", "")
        self.serial = st.get("serial", "")
        self.tier = st.get("tier", "free")            # 'free' | 'pro' | 'team'
        self.expires_at = st.get("expires_at", "")
        self.last_ok = float(st.get("last_ok", 0) or 0)
        self.message = st.get("message", "")
        self.scripts = st.get("scripts", [])          # [{slug,name,version,min_tier,source,sha256}]
        # a decisive server "no" (blocked / revoked / expired paid licence)
        self.server_denied = bool(st.get("server_denied", False))
        # master switch + update policy, learned from the signed check-in
        self.app_enabled = bool(st.get("app_enabled", True))
        self.update_required = bool(st.get("update_required", False))
        self.update_available = bool(st.get("update_available", False))
        self.latest_version = st.get("latest_version", "")
        self.min_version = st.get("min_version", "")
        self.download_url = st.get("download_url", "")
        self.download_sha256 = st.get("download_sha256", "")
        self.release_notes = st.get("release_notes", "")
        self.blocked_message = st.get("blocked_message", "")
        self.plan_name_cached = st.get("plan_name", "Free")
        self.entitlements = st.get("entitlements", self._free_entitlements())
        self.license_public = st.get("license_public", None)
        self.checkin_seconds = int(st.get("checkin_seconds", CHECKIN_SECONDS_DEFAULT) or CHECKIN_SECONDS_DEFAULT)
        self._blocked_by_admin = bool(st.get("blocked_by_admin", False)) \
            or (self.server_denied and not self.app_enabled)
        # the device id an OLDER build used on this same machine, so a licence
        # bound under that identity can be migrated instead of taking a 2nd seat
        # v6.3: last referral state we saw, so the Invite tab works offline
        self.referral = st.get("referral", {}) or {}
        # v6.3.1 (TASK 2): last activation attempt/lockout state from the
        # server, mirrored so the UI is right offline. Server always wins.
        self.activation = st.get("activation", {}) or {}
        # v6.3.4: server-delivered feature definitions (the half of each
        # feature that does NOT ship inside the tool). Cached so the
        # feature keeps working offline, re-fetched when the version moves.
        self.features = st.get("features", {}) or {}
        # v7.0.0: server-controlled Python tabs. Two caches, both additive:
        #   tabs       - the last verified tab manifest (titles, order, locked
        #                flags). Lets the tab strip be complete before any
        #                network call, so the window never flickers.
        #   tab_blobs  - {slug: sealed envelope}. The payload is stored
        #                ENCRYPTED, exactly as the server sent it; the
        #                plaintext module is never written anywhere. It rides
        #                inside the existing state file, which is already
        #                DPAPI-protected on Windows.
        self.tabs = st.get("tabs", []) or []
        self.tab_blobs = st.get("tab_blobs", {}) or {}
        # v7.0.1: last remote-tab refresh error is diagnostic only. It never
        # changes entitlement, cached tabs, or any existing feature.
        self.tabs_last_error = str(st.get("tabs_last_error", "") or "")
        # v8.0.0: per-option gating (id -> [free, pro, team]) and the Control
        # ZIP Links rules. Both arrive ONLY inside the signed control block;
        # cached so they keep applying offline. Nothing received yet = every
        # option allowed (the behaviour before v8) and the built-in ZIP link
        # defaults, which match the server's own defaults.
        self.gates = st.get("gates", {}) or {}
        self.ziplinks = st.get("ziplinks", {}) or {}
        self.tool_control_version = str(st.get("tcv", "") or "")
        self.legacy_device = st.get("legacy_device", "")
        self.legacy_imported = bool(st.get("legacy_imported", False))
        if self.legacy_imported:
            self._persist()   # rewrite in the v6.2 format; verified from now on

    @staticmethod
    def _free_entitlements() -> dict:
        return {
            "plan": "free", "max_profiles": 5, "fingerprint": False,
            "languages": ["en-US", "fr-FR"], "resolutions": ["1920x1080"],
            "scripts": ["free"], "max_devices": 1,
        }

    # ---- persistence -------------------------------------------------
    def _persist(self):
        _save_state({
            "token": self.token, "serial": self.serial, "tier": self.tier,
            "expires_at": self.expires_at, "last_ok": self.last_ok,
            "message": self.message, "scripts": self.scripts,
            "server_denied": self.server_denied, "app_enabled": self.app_enabled,
            "update_required": self.update_required, "update_available": self.update_available,
            "latest_version": self.latest_version, "min_version": self.min_version,
            "download_url": self.download_url, "download_sha256": self.download_sha256,
            "release_notes": self.release_notes, "blocked_message": self.blocked_message,
            "plan_name": self.plan_name_cached, "entitlements": self.entitlements,
            "license_public": self.license_public, "checkin_seconds": self.checkin_seconds,
            "blocked_by_admin": getattr(self, "_blocked_by_admin", False),
            "legacy_device": self.legacy_device,
            "referral": self.referral,
            "activation": self.activation,
            "features": self.features,
            # v7.0.0 (additive: every key above is unchanged)
            "tabs": self.tabs,
            "tab_blobs": self.tab_blobs,
            "tabs_last_error": getattr(self, "tabs_last_error", ""),
            # v8.0.0 (additive)
            "gates": getattr(self, "gates", {}),
            "ziplinks": getattr(self, "ziplinks", {}),
            "tcv": getattr(self, "tool_control_version", ""),
        })

    # ---- state the GUI asks about ------------------------------------
    def is_activated(self) -> bool:
        """True when a paid licence is registered on this device (any state)."""
        return bool(self.serial)

    def paid_usable(self) -> bool:
        """True when the PAID licence is currently valid (within grace)."""
        if not self.token or self.server_denied:
            return False
        claims = _verify_token(self.token, TOKEN_LEEWAY_SECONDS)
        if not claims:
            return False
        lexp = float(claims.get("lexp", 0) or 0)
        if lexp and time.time() > lexp + 300:
            # the licence period itself is over; the server renews the token
            # (with a new lexp) at the next check-in if it was renewed
            return False
        if time.time() <= float(claims.get("grace_until", 0)):
            return True
        return self.grace_seconds_left() > 0

    def current_plan(self) -> str:
        """The plan in force right now: 'pro', 'team' or 'free'."""
        if self.paid_usable() and self.tier in ("pro", "team"):
            return self.tier
        return "free"

    def is_pro(self) -> bool:
        """True when paid features are unlocked (Pro OR Team). Name kept for
        the GUI's existing call sites."""
        return self.current_plan() in ("pro", "team")

    def is_team(self) -> bool:
        return self.current_plan() == "team"

    def app_allowed(self) -> bool:
        """True when the app may run at all (master switch)."""
        if getattr(self, "_blocked_by_admin", False):
            return False
        if self.server_denied and not self.app_enabled:
            return False
        return bool(self.app_enabled)

    def is_usable(self) -> bool:
        """Back-compat: the tool may run and do useful work now. True for FREE
        too, as long as the master switch is on."""
        return self.app_allowed()

    def plan_name(self) -> str:
        return {"free": "Free", "pro": "Pro", "team": "Unlimited for Team"}.get(
            self.current_plan(), self.plan_name_cached or "Free")

    def plan_entitlements(self) -> dict:
        """What the current plan unlocks. Falls back to Free limits."""
        if self.is_pro() and isinstance(self.entitlements, dict) \
                and self.entitlements.get("plan") in ("pro", "team"):
            return self.entitlements
        return self._free_entitlements()

    # ---- remote application-update + block, for the GUI --------------
    def is_blocked_by_admin(self) -> bool:
        if getattr(self, "_blocked_by_admin", False):
            return True
        return self.server_denied and not self.app_enabled

    def needs_update(self) -> bool:
        return bool(self.update_required)

    def has_update(self) -> bool:
        return bool(self.update_available)

    def update_download_url(self) -> str:
        return self.download_url or ""

    def blocked_reason(self) -> str:
        return self.blocked_message or (
            "The application is temporarily disabled by the administrator. "
            "Please try again later or contact support.")

    def grace_seconds_left(self) -> int:
        if not self.last_ok:
            return 0
        elapsed = time.time() - self.last_ok
        if elapsed < 0:                       # clock moved backwards
            return 0
        return max(0, int(GRACE_DAYS * 86400 - elapsed))

    def status_line(self) -> str:
        plan = self.current_plan()
        if not self.app_allowed():
            return "Disabled by administrator"
        if plan == "free":
            if self.serial and self.message:
                return self.message            # e.g. an expired paid licence note
            return "Free plan"
        label = "Pro" if plan == "pro" else "Unlimited for Team"
        tail = ("  -  " + self.expires_at.split(" ")[0]) if self.expires_at else ""
        return "%s active%s" % (label, tail)

    # ---- the one call that learns everything -------------------------
    def check_in(self) -> dict:
        """Ask the server for the plan, switch, update policy and scripts.

        Works with or without a licence, so a Free install is served too.
        Applies the signed result to local state. Never raises; on a network
        error it returns {} and the last good state (with its grace window)
        stays in force.
        """
        payload = {
            "device_hash": self.device,
            "app_version": APP_VERSION,
            "profile_count": _profile_count(),
            "protocol": 2,
        }
        if self.token:
            payload["token"] = self.token
        if self.legacy_device and self.legacy_device != self.device:
            payload["legacy_device_hash"] = self.legacy_device
        try:
            r = _post("/api/v1/checkin.php", payload)
        except urllib.error.HTTPError as e:
            try:
                r = json.loads(e.read().decode("utf-8"))
                if not isinstance(r, dict):
                    return {}
            except Exception:
                return {}
        except Exception:
            return {}   # offline: grace covers it
        if not r.get("ok"):
            return r

        # the reply's control block is signed; verify before trusting it
        control = _verify_token(str(r.get("control", "")))
        with self._lock:
            self.last_ok = time.time()
            if control and str(control.get("sub", "")) == self.device:
                self.app_enabled = bool(control.get("app_enabled", True))
                self.checkin_seconds = self._clamp_interval(control.get("next"))
                upd = control.get("update", {}) if isinstance(control.get("update"), dict) else {}
                self.update_required = bool(upd.get("mandatory", False))
                self.update_available = bool(upd.get("available", False))
                self.latest_version = str(upd.get("latest_version", "") or "")
                self.min_version = str(upd.get("min_version", "") or "")
                self.download_url = str(upd.get("url", "") or "")
                self.download_sha256 = str(upd.get("sha256", "") or "")
                self.release_notes = str(upd.get("notes", "") or "")
                plan = str(control.get("plan", "free") or "free")
                lic_state = str(control.get("license_state", "none") or "none")
                # v8.0.0: remote per-option gating + Control ZIP Links. Taken
                # from the SIGNED block only; an unsigned reply never changes them.
                if isinstance(control.get("gates"), dict):
                    self.gates = self._clean_gates(control.get("gates"))
                if isinstance(control.get("ziplinks"), dict):
                    self.ziplinks = control.get("ziplinks")
                self.tool_control_version = str(control.get("tcv", "") or "")
            else:
                # unsigned or mismatched control: fall back to the plain fields,
                # but they may only make things STRICTER. They can never turn a
                # switched-off app back on or unlock paid features.
                self.app_enabled = self.app_enabled and bool(r.get("enabled", True))
                self.checkin_seconds = self._clamp_interval(r.get("next_checkin_seconds"))
                self.update_required = bool(r.get("update_required", False))
                self.update_available = bool(r.get("update_available", False))
                self.latest_version = str(r.get("latest_version", "") or "")
                self.min_version = str(r.get("min_version", "") or "")
                self.download_url = str(r.get("download_url", "") or "")
                self.download_sha256 = str(r.get("download_sha256", "") or "")
                self.release_notes = str(r.get("release_notes", "") or "")
                plan = "free"
                lic_state = str(r.get("license_state", "none") or "none")

            self.blocked_message = str(r.get("message", "") or self.blocked_message)
            self.message = str(r.get("license_message", "") or "")
            self.plan_name_cached = str(r.get("plan_name", "") or self.plan_name_cached)
            if isinstance(r.get("entitlements"), dict):
                self.entitlements = r["entitlements"]
            if r.get("license") is not None:
                self.license_public = r.get("license")

            # a fresh signed session token keeps a paid licence alive offline
            new_token = str(r.get("token", "") or "")
            if new_token and _verify_token(new_token, TOKEN_LEEWAY_SECONDS):
                self.token = new_token
            lic_pub = r.get("license") if isinstance(r.get("license"), dict) else {}
            if lic_pub.get("expires_at"):
                self.expires_at = str(lic_pub["expires_at"])
            elif r.get("expires_at"):
                self.expires_at = str(r["expires_at"])

            # decide the effective tier and whether the server said "no"
            if lic_state == "active" and plan in ("pro", "team"):
                self.tier = plan
                self.server_denied = False
            else:
                # expired / revoked / blocked / device removed -> fall back to
                # Free WITHOUT deleting anything. Keep the serial for display.
                if lic_state in ("expired", "revoked", "blocked", "device_removed", "reauth"):
                    self.server_denied = True
                    if lic_state == "reauth":
                        # the saved session could not be verified; drop the token
                        # so the next activation re-establishes one, and drop
                        # the serial with it - a stale serial would make the
                        # tab IKM differ from the one the server seals with
                        # (server uses '' once no active licence exists), and
                        # every remote tab would fail its integrity check.
                        self.token = ""
                        self.serial = ""
                self.tier = "free"

            self._blocked_by_admin = (not self.app_enabled)
            self._persist()
        if control:
            _write_app_marker(self.app_enabled, self.blocked_message)

        # scripts: only re-download when a version actually changed
        manifest = r.get("scripts", [])
        # v6.3.1 (TASK 2): the server's attempt/lockout state wins.
        act = r.get("activation")
        if isinstance(act, dict):
            with self._lock:
                self.activation = act
                self._persist()
        if self.app_allowed() and self._scripts_need_refresh(manifest):
            self.refresh_scripts()
        elif not self.app_allowed():
            pass  # keep cached scripts; they simply are not injected while off
        return r

    @staticmethod
    def _clamp_interval(value) -> int:
        try:
            v = int(value)
        except (TypeError, ValueError):
            return CHECKIN_SECONDS_DEFAULT
        return max(CHECKIN_SECONDS_MIN, min(CHECKIN_SECONDS_MAX, v))

    # ---- v8.0.0: remote per-option gating ----------------------------
    _TIER_INDEX = {"free": 0, "pro": 1, "team": 2}

    @staticmethod
    def _clean_gates(raw) -> dict:
        out = {}
        for key, row in (raw or {}).items():
            try:
                vals = [bool(int(v)) for v in list(row)[:3]]
            except Exception:
                continue
            if len(vals) == 3:
                out[str(key)[:64]] = vals
        return out

    def feature_allowed(self, option_id: str, plan: str = None) -> bool:
        """True when the dashboard allows this option on this plan (the
        current plan by default). Unknown ids are allowed, so an option the
        server does not know about yet keeps working exactly as before."""
        row = (getattr(self, "gates", {}) or {}).get(option_id)
        if not row:
            return True
        idx = self._TIER_INDEX.get(plan or self.current_plan(), 0)
        try:
            return bool(row[idx])
        except Exception:
            return True

    def feature_min_plan(self, option_id: str) -> str:
        """The lowest plan that may use this option: 'free', 'pro', 'team',
        or '' when the dashboard has switched it off for every plan."""
        row = (getattr(self, "gates", {}) or {}).get(option_id)
        if not row:
            return "free"
        for name in ("free", "pro", "team"):
            try:
                if row[self._TIER_INDEX[name]]:
                    return name
            except Exception:
                return "free"
        return ""

    # ---- v8.0.0: Control ZIP Links -------------------------------------
    ZIPLINKS_DEFAULT_DOMAINS = ["usadealshub.shop", "mavelylink.com",
                                "martdeals.shop", "usathedeals.shop"]

    def ziplinks_rules(self, plan: str = None) -> dict:
        """The ZIP link rules for this plan (current plan by default):
        {'enforce', 'domains', 'check_description', 'apply_to_csv',
         'message', 'url', 'label', 'plan'}. 'enforce' False means every
        link is supported. Built-in defaults (same as the server's) apply
        until a signed check-in has delivered the dashboard's settings."""
        plan = plan or self.current_plan()
        cfg = getattr(self, "ziplinks", {}) or {}
        default_dom = list(self.ZIPLINKS_DEFAULT_DOMAINS)
        if not cfg:
            cfg = {"on": 1, "tiers": {"free": {"e": 1, "d": default_dom},
                                       "pro": {"e": 0, "d": default_dom},
                                       "team": {"e": 0, "d": default_dom}},
                   "desc": 0, "csv": 0,
                   "msg": "Your link is not supported in the {plan} version.",
                   "url": "https://mavelylink.com/", "label": "Get supported links"}
        tiers = cfg.get("tiers") if isinstance(cfg.get("tiers"), dict) else {}
        row = tiers.get(plan) if isinstance(tiers.get(plan), dict) else {}
        domains = []
        for d in row.get("d", []) or []:
            d = str(d or "").strip().lower()
            if d:
                domains.append(d)
        try:
            enforce = bool(int(cfg.get("on", 1))) and bool(int(row.get("e", 0)))
        except Exception:
            enforce = False
        url = str(cfg.get("url") or "")
        if not url.lower().startswith("https://"):
            url = "https://mavelylink.com/"
        return {
            "plan": plan,
            "enforce": enforce,
            "domains": domains,
            "check_description": bool(cfg.get("desc", 0)),
            "apply_to_csv": bool(cfg.get("csv", 0)),
            "message": str(cfg.get("msg") or "Your link is not supported in the {plan} version."),
            "url": url,
            "label": str(cfg.get("label") or "Get supported links"),
        }

    # ---- activation --------------------------------------------------
    def activate(self, serial: str) -> tuple:
        serial = (serial or "").strip().upper()
        if not serial:
            return False, "Enter a licence key."
        # v6.2.1: check OUR key before blaming the server. Without this, a
        # build with a bad LICENSE_PUBLIC_KEY_B64 reports the misleading
        # "the server response could not be verified" for every key anyone
        # ever pastes, and the real cause stays invisible.
        problem = license_key_problem()
        if problem:
            return False, problem
        # v6.3.1 (TASK 2): a key that fails the local format check is refused
        # HERE and never sent, so it cannot consume one of the three attempts
        # (spec 2.2). Only a key the server actually rejects counts.
        if not self.serial_looks_valid(serial):
            return False, ("That does not look like a licence key. They look like "
                           "MVL-XXXXX-XXXXX-XXXXX-XXXXX.")
        payload = {
            "serial": serial, "device_hash": self.device,
            "device_label": device_label(), "app_version": APP_VERSION,
            "protocol": 2,
        }
        if self.legacy_device and self.legacy_device != self.device:
            payload["legacy_device_hash"] = self.legacy_device
        try:
            r = _post("/api/v1/activate.php", payload)
        except urllib.error.HTTPError as e:
            # v6.3.1 (TASK 2): a rejected key comes back as 404/403/429 with
            # the new attempt state attached. Record it, so the UI can hide
            # the button and start the countdown straight away instead of
            # waiting for the next check-in.
            # NOTE: e.read() can only be consumed ONCE, so the body is read
            # here and the message is built from it directly rather than
            # calling _http_error(e), which would then see an empty body.
            body, msg = {}, "Server error %s" % e.code
            try:
                body = json.loads(e.read().decode("utf-8", "replace") or "{}")
                msg = body.get("error", msg)
            except Exception:
                pass
            act = body.get("activation") if isinstance(body, dict) else None
            if isinstance(act, dict):
                with self._lock:
                    self.activation = act              # server wins
                    self._persist()
            elif e.code in (400, 401, 403, 404, 409, 410, 422):
                # a real rejection from the server (not a 5xx outage and not
                # a network failure), so it counts. Mirrored locally so the
                # button hides immediately even on an older server build.
                self._record_local_rejection()
            return False, msg
        except Exception as e:
            # a network failure NEVER counts as an attempt (spec 2.2): the
            # request did not reach the server, so nothing was recorded there
            return False, "Could not reach the server. Check your internet connection. (%s)" % e

        if isinstance(r.get("activation"), dict):
            with self._lock:
                self.activation = r["activation"]      # server wins
                self._persist()
        if not r.get("ok"):
            # the SERVER rejected this key, so it counts (spec 1.3). Counted
            # locally too, so the button hides at once even on an older server.
            if not isinstance(r.get("activation"), dict):
                self._record_local_rejection()
            return False, r.get("error", "Activation failed.")
        token = r.get("token", "")
        if not _verify_token(token):
            return False, "The server response could not be verified. Activation refused."

        with self._lock:
            self.token = token
            self.serial = serial
            self.tier = r.get("plan", r.get("tier", "pro"))
            if self.tier not in ("pro", "team"):
                self.tier = "pro"
            self.expires_at = r.get("expires_at", "")
            self.last_ok = time.time()
            self.message = ""
            self.server_denied = False
            self._blocked_by_admin = False
            if isinstance(r.get("entitlements"), dict):
                self.entitlements = r["entitlements"]
            if r.get("license") is not None:
                self.license_public = r.get("license")
            self.plan_name_cached = r.get("plan_name", self.plan_name_cached)
            self._persist()

        self.refresh_scripts()
        self.start_background()
        return True, "Activated. " + r.get("remaining", "")

    def release_device(self) -> tuple:
        if not self.serial:
            return False, "Nothing to release."
        try:
            r = _post("/api/v1/release.php", {"serial": self.serial, "device_hash": self.device})
        except urllib.error.HTTPError as e:
            return self._http_error(e)
        except Exception as e:
            return False, "Could not reach the server. (%s)" % e
        if r.get("ok"):
            with self._lock:
                self.token = ""
                self.serial = ""
                self.tier = "free"
                self.server_denied = False
                self._persist()
            return True, r.get("message", "This computer was released. You can activate the key elsewhere now.")
        return False, r.get("error", "Could not release this computer.")

    def start_trial(self, email: str = "") -> tuple:
        """Kept for older builds. New installs never call this - Free needs no
        trial. If the server still offers a trial it is activated; otherwise
        the user is simply told they are already on the Free plan."""
        try:
            r = _post("/api/v1/trial.php", {
                "email": email, "device_hash": self.device, "app_version": APP_VERSION,
            })
        except urllib.error.HTTPError as e:
            return self._http_error(e)
        except Exception as e:
            return False, "Could not reach the server. (%s)" % e
        if r.get("ok") and r.get("serial"):
            return self.activate(r["serial"])
        return False, r.get("error", "You are already on the Free plan. Upgrade any time for Pro features.")

    # ---- scripts -----------------------------------------------------
    # ---- v6.3: referral programme ------------------------------------
    # All three calls reuse the EXISTING authentication: the signed licence
    # token when there is one, otherwise the device hash the check-in
    # already sends. Nothing new is invented, and none of them can block
    # the tool - every failure falls back to the last known state.
    def _referral_payload(self) -> dict:
        payload = {"device_hash": self.device, "app_version": APP_VERSION}
        if self.token:
            payload["token"] = self.token
        return payload

    def referral_state(self, refresh: bool = True) -> dict:
        """Referral code, link, counts and reward state.

        Offline is NOT an error here. The last state we saw is returned
        with offline=True, so the Invite tab still shows the user their
        own link with no network at all.
        """
        cached = dict(self.referral or {})
        if not refresh:
            cached.setdefault("offline", True)
            return cached
        try:
            r = _post("/api/v1/referral/me.php", self._referral_payload())
        except urllib.error.HTTPError as e:
            cached["offline"] = True
            cached["error"] = self._http_error(e)[1]
            return cached
        except Exception as e:
            cached["offline"] = True
            cached["error"] = "Could not reach the server. (%s)" % e
            return cached
        if not isinstance(r, dict) or not r.get("ok"):
            cached["offline"] = True
            cached["error"] = (r or {}).get("error", "The server did not answer.")
            return cached
        r["offline"] = False
        with self._lock:
            self.referral = r
            self._persist()
        return dict(r)

    def referral_register(self, email: str) -> tuple:
        """Attach an email to this installation so it can be rewarded.

        The only new thing a FREE user has to do. The site has no accounts,
        so the email IS the identity - the same one a licence would use.
        """
        email = (email or "").strip().lower()
        if len(email) > 190 or "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            return False, "Enter a valid email address."
        payload = self._referral_payload()
        payload["email"] = email
        try:
            r = _post("/api/v1/referral/register.php", payload)
        except urllib.error.HTTPError as e:
            return self._http_error(e)
        except Exception as e:
            return False, "Could not reach the server. Check your internet connection. (%s)" % e
        if not isinstance(r, dict) or not r.get("ok"):
            return False, (r or {}).get("error", "That email address could not be registered.")
        r["offline"] = False
        with self._lock:
            self.referral = r
            self._persist()
        return True, "Your invite link is ready."

    def referral_mark_seen(self, reward: bool = False) -> bool:
        """Tell the server the popup has been shown, so it does not repeat."""
        payload = self._referral_payload()
        if reward:
            payload["reward"] = True
        try:
            r = _post("/api/v1/referral/popup-seen.php", payload)
        except Exception:
            return False        # try again next launch; never bother the user
        if isinstance(r, dict) and r.get("ok"):
            r["offline"] = False
            with self._lock:
                self.referral = r
                self._persist()
            return True
        return False

    # ---- v6.3.1 activation attempts (TASK 2) --------------------------
    SERIAL_RE = re.compile(r"^MVL(-[0-9A-Z]{5}){4}$")

    @staticmethod
    def serial_looks_valid(serial: str) -> bool:
        """Local format check BEFORE anything is sent.

        Spec 2.2: an empty field or a key that fails local format validation
        must NOT consume one of the three attempts. Refusing it here is what
        makes that true - the request never reaches the server.
        """
        return bool(LicenseClient.SERIAL_RE.match((serial or "").strip().upper()))

    def _record_local_rejection(self) -> None:
        """Count a server rejection locally.

        The server is the authority and its value always wins at the next
        check-in. But the server only reports a count if the 6.3.1+ server
        files are deployed, and the UI must hide the button the moment the
        third key is rejected regardless. So the count is mirrored here too:
        whichever is higher is used, and the server overwrites it wholesale
        as soon as it sends one.
        """
        with self._lock:
            st = dict(self.activation or {})
            mx = int(st.get("max", 3) or 3)
            st["max"] = mx
            st["fails"] = int(st.get("fails", 0) or 0) + 1
            st["remaining"] = max(0, mx - st["fails"])
            if st["fails"] >= mx:
                until = time.time() + int(st.get("lockout_hours", 24) or 24) * 3600
                st["locked"] = True
                st["locked_until"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(until))
                st["retry_after_seconds"] = int(until - time.time())
            else:
                st["locked"] = False
                st["locked_until"] = None
                st["retry_after_seconds"] = 0
            self.activation = st
            self._persist()

    def activation_state(self) -> dict:
        """Attempts remaining and lockout, as last reported by the server.

        Counts down locally between check-ins so the UI stays honest offline,
        and never invents attempts it has not been told about.
        """
        st = dict(self.activation or {})
        if not st:
            return {"max": 3, "fails": 0, "remaining": 3, "locked": False,
                    "retry_after_seconds": 0}
        until = st.get("locked_until")
        if until:
            try:
                ts = calendar.timegm(time.strptime(
                    str(until).replace("Z", "+0000").split("+")[0], "%Y-%m-%dT%H:%M:%S"))
                left = int(ts - time.time())
                st["retry_after_seconds"] = max(0, left)
                st["locked"] = left > 0
                if left <= 0:
                    st["fails"] = 0
                    st["remaining"] = int(st.get("max", 3) or 3)
            except Exception:
                pass
        return st

    # ---- v6.3.4: split features ---------------------------------------
    def feature(self, feature_id, refresh=True):
        """The server-side half of a feature.

        Returns its `data` dict, or {} when this installation is not
        entitled or has never been able to fetch it.

        The tool ships only the renderer; the rules live on the server, so
        a cracked copy has nothing to render. Offline, the last verified
        copy is reused - the feature keeps working, it just cannot change.
        """
        cached = (self.features or {}).get(feature_id) or {}
        if not refresh:
            return cached.get("data", {}) or {}
        payload = {"id": feature_id, "device_hash": self.device,
                   "app_version": APP_VERSION}
        if self.token:
            payload["token"] = self.token
        try:
            r = _post("/api/v1/feature.php", payload)
        except urllib.error.HTTPError as e:
            if e.code == 403:
                # not entitled: drop any cached copy so a lapsed licence
                # cannot keep using it
                with self._lock:
                    self.features.pop(feature_id, None)
                    self._persist()
                return {}
            return cached.get("data", {}) or {}
        except Exception:
            return cached.get("data", {}) or {}
        if not isinstance(r, dict) or not r.get("ok") or not isinstance(r.get("data"), dict):
            return cached.get("data", {}) or {}
        with self._lock:
            self.features[feature_id] = {"version": r.get("version", 0),
                                         "data": r["data"]}
            self._persist()
        return r["data"]

    def referral_link(self) -> str:
        return str((self.referral or {}).get("referral_link", ""))

    def _scripts_need_refresh(self, manifest: list) -> bool:
        want = {}
        try:
            for s in manifest or []:
                if isinstance(s, dict):
                    slug = str(s.get("slug", ""))
                    if slug:
                        want[slug] = int(s.get("version", 0) or 0)
                elif isinstance(s, (list, tuple)) and len(s) >= 2:
                    want[str(s[0])] = int(s[1])
        except Exception:
            return True   # unrecognised shape: be safe and refetch
        have = {}
        for s in self.scripts:
            slug = str(s.get("slug", ""))
            if not slug or not s.get("source"):
                return True
            have[slug] = int(s.get("version", 0) or 0)
        return want != have

    def refresh_scripts(self) -> bool:
        """Fetch the full script sources this install is entitled to and cache
        them in memory, verifying each against its manifest SHA-256. Works for
        Free (no token) and paid (token) alike."""
        payload = {"device_hash": self.device, "protocol": 2}
        if self.token:
            payload["token"] = self.token
        try:
            r = _post("/api/v1/scripts.php", payload)
        except Exception:
            return False
        if not r.get("ok"):
            if r.get("state") in ("reauth", "revoked", "disabled"):
                # do not wipe the cache on a transient "no"; just skip
                return False
            return False
        incoming = r.get("scripts", [])
        verified = []
        for s in incoming:
            src = s.get("source", "")
            want = str(s.get("sha256", "") or "").lower()
            if want and hashlib.sha256(src.encode("utf-8")).hexdigest() != want:
                continue   # corrupt or tampered: drop this one, keep the rest
            verified.append(s)
        with self._lock:
            self.scripts = verified
            self._persist()
        return True

    def get_scripts(self) -> list:
        """Full server-script records to inject now, or [] when the app is off.

        The plan's entitlement is enforced by the SERVER (a Free install is
        never sent Script 2), so here we simply return what was delivered as
        long as the app is allowed to run."""
        if not self.app_allowed():
            return []
        # The server already sends only what the plan includes. This filter
        # covers the gap between a plan change and the next successful
        # refresh, so a script the current plan is not entitled to is never
        # injected from a stale cache.
        #
        # v6.3.1 (TASK 4): min_tier is a MINIMUM-TIER threshold and cannot
        # express "Free only", so an explicit per-plan list now takes
        # precedence when the server sends one. The old min_tier path is kept
        # untouched for any script that has no list.
        plan = self.current_plan()          # 'free' when unverified/offline
        paid = plan in ("pro", "team")
        out = []
        for s in self.scripts:
            plans = str(s.get("plans", "") or "").strip()
            if plans:
                allowed = [p.strip() for p in plans.split(",") if p.strip()]
                if plan not in allowed:
                    continue                # e.g. Script 1 on a Pro install
            elif not paid and str(s.get("min_tier", "free")) != "free":
                continue                    # original behaviour, unchanged
            if s.get("source"):
                out.append({
                    "slug": s.get("slug", ""),
                    "name": s.get("name", s.get("slug", "")),
                    "version": s.get("version", 0),
                    "min_tier": s.get("min_tier", "free"),
                    "plans": plans,
                    "source": s.get("source", ""),
                })
        return out

    def get_scripts_source(self) -> list:
        """[(name, source)] - back-compat for older callers."""
        return [(s["name"], s["source"]) for s in self.get_scripts()]

    # ---- v7.0.0: server-controlled Python tabs -------------------------
    #
    # Two calls, mirroring the script pipeline above:
    #   remote_tabs()  - the tab strip: titles, order, locked flags. No code.
    #   tab_payload()  - one sealed module, only for an entitled licence.
    #
    # The plan is decided by the SERVER from its own database. Nothing here
    # sends a plan, and nothing here would be believed if it did. Faking
    # anything on this side gains nothing, because the code for a tab this
    # installation is not entitled to is never delivered at all.
    #
    # Neither call ever writes a module to disk: tab_blobs holds the sealed
    # envelope, and mavely_tabs.py decrypts it into a buffer it zeroes.

    def remote_tabs(self, refresh: bool = True) -> list:
        """The tab manifest. Cached copy when refresh is False or offline."""
        if not refresh:
            return list(self.tabs or [])
        payload = {"device_hash": self.device, "app_version": APP_VERSION}
        if self.token:
            payload["token"] = self.token
        try:
            r = _post("/api/v1/tabs.php", payload)
        except Exception as exc:
            # Offline: the last verified manifest keeps the tabs on screen.
            # Record the reason so the desktop log can diagnose a stale list.
            with self._lock:
                self.tabs_last_error = "tabs manifest request failed: %r" % (exc,)
                self._persist()
            return list(self.tabs or [])
        if not isinstance(r, dict) or not r.get("ok"):
            with self._lock:
                self.tabs_last_error = "tabs manifest returned an invalid response: %r" % (r,)
                self._persist()
            return list(self.tabs or [])

        tabs = r.get("tabs", [])
        if not isinstance(tabs, list):
            with self._lock:
                self.tabs_last_error = "tabs manifest did not contain a list"
                self._persist()
            return list(self.tabs or [])

        with self._lock:
            self.tabs_last_error = ""
            self.tabs = tabs
            # Drop cached payloads for tabs that are gone, disabled, newly
            # locked, or superseded. A lapsed licence therefore cannot keep
            # running a module from a stale cache.
            live = {}
            for t in tabs:
                if isinstance(t, dict) and t.get("slug") and not t.get("locked"):
                    live[str(t["slug"])] = int(t.get("version", 0) or 0)
            for slug in list(self.tab_blobs.keys()):
                blob = self.tab_blobs.get(slug) or {}
                if slug not in live or int(blob.get("version", -1)) != live[slug]:
                    self.tab_blobs.pop(slug, None)
            self._persist()
        return tabs

    def tab_payload(self, slug: str, have_version: int = 0,
                    allow_network: bool = True) -> dict:
        # have_version is accepted for backward compatibility and ignored:
        # the held-version decision is made from the sealed cache below.
        """One sealed tab module, or {} when there is nothing to run.

        Returns the envelope mavely_tabs.unseal() expects. A dict with
        state='locked' means the server refused on plan grounds, which the
        caller renders as the locked state.

        allow_network=False serves the cache only, so the first paint at
        start-up is instant and the network refresh follows behind it.
        """
        slug = str(slug or "")
        if not slug:
            return {}
        cached = (self.tab_blobs or {}).get(slug) or {}

        # A cached module is only usable while its signed grant is still
        # valid AND the licence is. mavely_tabs re-verifies the signature
        # regardless; this just avoids a pointless decrypt.
        if cached and not allow_network:
            return dict(cached)
        if not allow_network:
            return {}

        # The server answers "current" (no payload) whenever have_version
        # equals its own row version. Callers pass the *manifest* version,
        # so on a first-time install -- sealed cache still empty -- the tool
        # was effectively asking "do I already hold vN?" and the server
        # truthfully answered "yes, current" with no code attached. The
        # result: {} and the tab renders as "not available offline" forever,
        # with no way to ever download the module. Only the sealed cache may
        # claim to hold a version; never trust the caller's number here.
        held = 0
        try:
            held = int(cached.get("version", 0) or 0)
        except Exception:
            held = 0
        payload = {"device_hash": self.device, "slug": slug,
                   "app_version": APP_VERSION,
                   "have_version": max(0, held)}
        if self.token:
            payload["token"] = self.token
        try:
            r = _post("/api/v1/tab_script.php", payload)
        except urllib.error.HTTPError as e:
            # The server explains itself in the JSON body; read it so the tab
            # can show the real reason instead of a generic "no connection".
            body_state = ""
            try:
                import json as _json
                _body = _json.loads(e.read().decode("utf-8", "replace"))
                if isinstance(_body, dict):
                    body_state = str(_body.get("state", ""))
            except Exception:
                pass
            if e.code == 403 or body_state == "locked":
                # not entitled: forget any cached copy, so a downgrade takes
                # effect at once rather than at the next successful fetch
                with self._lock:
                    self.tab_blobs.pop(slug, None)
                    self._persist()
                return {"state": "locked", "slug": slug}
            if e.code == 426 or body_state == "update_required":
                return {"state": "update_required", "slug": slug}
            if body_state in ("empty", "gone", "off", "disabled"):
                return {"state": body_state, "slug": slug}
            # 429 / 5xx / anything else: sealed cache or nothing
            return dict(cached) if cached else {}
        except Exception:
            # offline or a transient failure: retry once, then fall back to
            # the sealed cache if we have one
            try:
                import time as _time
                _time.sleep(1.0)
                r = _post("/api/v1/tab_script.php", payload)
            except Exception:
                return dict(cached) if cached else {}

        if not isinstance(r, dict):
            return dict(cached) if cached else {}

        state = str(r.get("state", ""))
        if state == "current" and cached:
            return dict(cached)          # the server says our copy is current
        if state in ("locked", "off", "disabled", "update_required"):
            if state == "locked":
                with self._lock:
                    self.tab_blobs.pop(slug, None)
                    self._persist()
            return {"state": state, "slug": slug,
                    "required_plan": r.get("required_plan", ""),
                    "title": r.get("title", "")}
        if not r.get("ok") or not r.get("ct") or not r.get("grant"):
            return dict(cached) if cached else {}

        with self._lock:
            self.tab_blobs[slug] = r
            self._persist()
        return r

    def forget_tabs(self) -> None:
        """Drop every cached tab and payload. Used when the app is switched
        off or a licence is released, so nothing survives that should not."""
        with self._lock:
            self.tabs = []
            self.tab_blobs = {}
            self._persist()

    # ---- application updates -------------------------------------------
    UPDATE_MAX_BYTES = 600 * 1024 * 1024

    def update_details(self) -> dict:
        """Everything the update dialog shows, in one place."""
        return {
            "current": APP_VERSION,
            "latest": self.latest_version,
            "minimum": self.min_version,
            "available": bool(self.update_available),
            "mandatory": bool(self.update_required),
            "url": self.download_url,
            "notes": self.release_notes,
            "verifiable": bool(_update_url_ok(self.download_url)
                               and re.fullmatch(r"[0-9a-f]{64}", (self.download_sha256 or "").lower())),
        }

    def download_update(self, progress=None, cancel=None) -> tuple:
        """Download the published installer and verify its SHA-256.

        Returns (True, path) only for a file whose checksum matches the one
        the server published inside the SIGNED check-in. Anything else is
        deleted and reported, so an unverified file is never left behind for
        the user to run. progress(done_bytes, total_bytes) may be called from
        this worker thread; cancel is an optional threading.Event.
        """
        url = (self.download_url or "").strip()
        want = (self.download_sha256 or "").strip().lower()
        if not _update_url_ok(url):
            return False, "The update link is missing or is not a secure (https) address."
        if not re.fullmatch(r"[0-9a-f]{64}", want):
            return False, ("This update has no published checksum, so it cannot be verified "
                           "automatically. Download it from the website instead.")
        folder = os.path.join(tempfile.gettempdir(), "MavelyLink-Updates")
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            return False, "Could not prepare a download folder (%s)." % e
        final = os.path.join(folder, _update_file_name(url, self.latest_version))
        part = final + ".part"
        if os.path.isfile(final) and _sha256_file(final) == want:
            return True, final            # already downloaded and still intact

        def _cleanup():
            for f in (part,):
                try:
                    os.remove(f)
                except Exception:
                    pass

        digest = hashlib.sha256()
        done = 0
        req = urllib.request.Request(url, headers={"User-Agent": "MavelyLink/" + APP_VERSION})
        try:
            with urllib.request.urlopen(req, timeout=NETWORK_TIMEOUT,
                                        context=ssl.create_default_context()) as resp, \
                    open(part, "wb") as out:
                total = int(resp.headers.get("Content-Length") or 0)
                if total > self.UPDATE_MAX_BYTES:
                    raise ValueError("the file is larger than expected")
                while True:
                    if cancel is not None and cancel.is_set():
                        raise InterruptedError()
                    chunk = resp.read(262144)
                    if not chunk:
                        break
                    done += len(chunk)
                    if done > self.UPDATE_MAX_BYTES:
                        raise ValueError("the file is larger than expected")
                    digest.update(chunk)
                    out.write(chunk)
                    if progress is not None:
                        try:
                            progress(done, total)
                        except Exception:
                            pass
        except InterruptedError:
            _cleanup()
            return False, "Download cancelled."
        except Exception as e:
            _cleanup()
            return False, "The download failed: %s" % e
        if total and done != total:
            _cleanup()
            return False, "The download was incomplete. Please try again."
        if not hmac.compare_digest(digest.hexdigest(), want):
            _cleanup()
            return False, ("The downloaded file failed its security check (checksum mismatch) "
                           "and was deleted. Please try again, or download it from the website.")
        try:
            os.replace(part, final)
        except Exception as e:
            _cleanup()
            return False, "Could not save the update (%s)." % e
        return True, final

    def launch_installer(self, path: str) -> tuple:
        """Start a verified installer. Re-checks the file first, because it sat
        on disk between download and launch."""
        want = (self.download_sha256 or "").strip().lower()
        if not path or not os.path.isfile(path):
            return False, "The downloaded update could not be found."
        if not re.fullmatch(r"[0-9a-f]{64}", want) or _sha256_file(path) != want:
            return False, "The update file changed after it was verified, so it was not started."
        try:
            if platform.system() == "Windows":
                os.startfile(path)            # the installer asks for elevation itself
            else:
                subprocess.Popen([path], close_fds=True)
        except Exception as e:
            return False, "Could not start the installer: %s" % e
        return True, "The installer has started."

    # ---- background check-in loop ------------------------------------
    def start_background(self):
        if self._hb_thread and self._hb_thread.is_alive():
            return
        self._hb_stop.clear()

        def loop():
            # one check-in at start-up, then every self.checkin_seconds, which
            # the server can change. About every 3 min by default, so a change
            # made in the dashboard reaches a running tool within minutes.
            if self._hb_stop.wait(1):
                return
            while True:
                try:
                    self.check_in()
                except Exception:
                    pass
                wait = max(CHECKIN_SECONDS_MIN, min(CHECKIN_SECONDS_MAX, self.checkin_seconds))
                if self._hb_stop.wait(wait):
                    break

        self._hb_thread = threading.Thread(target=loop, daemon=True)
        self._hb_thread.start()

    def stop_background(self):
        self._hb_stop.set()

    # legacy name some builds referenced
    def heartbeat(self) -> dict:
        return self.check_in()

    # ---- helpers -----------------------------------------------------
    def _http_error(self, e) -> tuple:
        try:
            body = json.loads(e.read().decode("utf-8"))
            return False, body.get("error", "Server error %s" % e.code)
        except Exception:
            return False, "Server error %s" % e.code


def _update_url_ok(url: str) -> bool:
    """https only. Plain http is accepted solely for a server on this machine
    (local testing); the SHA-256 check protects the file either way."""
    try:
        from urllib.parse import urlparse
        u = urlparse((url or "").strip())
    except Exception:
        return False
    if u.scheme == "https" and u.netloc:
        return True
    return u.scheme == "http" and (u.hostname or "") in ("127.0.0.1", "localhost")


def _update_file_name(url: str, version: str) -> str:
    """A safe local file name for the download."""
    try:
        from urllib.parse import urlparse, unquote
        base = os.path.basename(unquote(urlparse(url).path))
    except Exception:
        base = ""
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)[:80]
    if not base.lower().endswith((".exe", ".msi", ".zip")):
        ver = re.sub(r"[^0-9A-Za-z.]", "", version or "") or "latest"
        base = "MavelyLink-Setup-%s.exe" % ver
    return base


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(262144), b""):
                h.update(chunk)
    except Exception:
        return ""
    return h.hexdigest()


def _grace_days() -> int:
    """Kept for older callers; the offline grace window in days."""
    return GRACE_DAYS


def _version_cmp(a: str, b: str) -> int:
    """Compare two dotted versions numerically. -1/0/1 for a<b / a==b / a>b.

    Numeric-aware so 4.10 > 4.2, and missing segments count as 0 so
    "4.1" == "4.1.0". Matches the server's version_cmp() exactly.
    """
    pa = [p for p in re.split(r"[.\-+]", (a or "").strip()) if p != ""]
    pb = [p for p in re.split(r"[.\-+]", (b or "").strip()) if p != ""]

    def _int(x):
        try:
            return int(x)
        except Exception:
            return 0
    for i in range(max(len(pa), len(pb))):
        x = _int(pa[i]) if i < len(pa) else 0
        y = _int(pb[i]) if i < len(pb) else 0
        if x != y:
            return -1 if x < y else 1
    return 0


def _profile_count() -> int:
    try:
        base = os.path.join(os.path.expanduser("~"), "ChromeProfiles")
        return sum(
            1 for n in os.listdir(base)
            if n.startswith("Profile_") and os.path.isdir(os.path.join(base, n))
        )
    except Exception:
        return 0


# Resolve the server address exactly once, now that _state_dir() exists.
API_BASE = _resolve_api_base()
