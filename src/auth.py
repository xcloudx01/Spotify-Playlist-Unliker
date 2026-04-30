from __future__ import annotations

import os
from pathlib import Path
import ctypes
from ctypes import wintypes
from typing import Final

from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

SPOTIPY_CLIENT_ID: Final[str] = "SPOTIPY_CLIENT_ID"
SPOTIPY_CLIENT_SECRET: Final[str] = "SPOTIPY_CLIENT_SECRET"
TARGET_NAME_CLIENT_ID: Final[str] = "SpotifyPlaylistUnliker:client_id"
TARGET_NAME_CLIENT_SECRET: Final[str] = "SpotifyPlaylistUnliker:client_secret"

DEFAULT_REDIRECT_URI: Final[str] = "http://127.0.0.1:8888/callback"
CONFIG_DIR_NAME: Final[str] = ".spotify-playlist-unliker"
CONFIG_FILE_NAME: Final[str] = "config.env"

_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", ctypes.c_byte * 8),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", wintypes.LPVOID),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


_advapi32 = ctypes.WinDLL("Advapi32", use_last_error=True)
_CredWriteW = _advapi32.CredWriteW
_CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
_CredWriteW.restype = wintypes.BOOL

_CredReadW = _advapi32.CredReadW
_CredReadW.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_CREDENTIALW))]
_CredReadW.restype = wintypes.BOOL

_CredDeleteW = _advapi32.CredDeleteW
_CredDeleteW.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
_CredDeleteW.restype = wintypes.BOOL

_CredFree = _advapi32.CredFree
_CredFree.argtypes = [wintypes.LPVOID]
_CredFree.restype = None


def _config_file_path() -> Path:
    return Path.home() / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def clear_saved_credentials() -> tuple[bool, str]:
    _delete_windows_credential(TARGET_NAME_CLIENT_ID)
    _delete_windows_credential(TARGET_NAME_CLIENT_SECRET)

    # Cleanup legacy local config if it exists.
    path = _config_file_path()
    removed_file = False
    if path.exists():
        path.unlink()
        removed_file = True

    if removed_file:
        return True, f"Cleared saved credentials and removed legacy file: {path}"
    return True, "Cleared saved credentials."


def _load_saved_env_values() -> None:
    path = _config_file_path()
    if not path.exists():
        return

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Warning: could not read saved credentials file ({exc}).")
        return

    loaded_any = False
    malformed = False
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            if line and not line.startswith("#") and "=" not in line:
                malformed = True
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value and not os.getenv(key):
            os.environ[key] = value
            loaded_any = True

    if malformed and not loaded_any:
        backup = path.with_suffix(".corrupt.bak")
        path.replace(backup)
        print(f"Warning: saved credentials file looked corrupted and was moved to: {backup}")
        print("You will be prompted to re-enter credentials.")


def _load_saved_credentials() -> tuple[str, str]:
    client_id = _read_windows_credential(TARGET_NAME_CLIENT_ID) or ""
    client_secret = _read_windows_credential(TARGET_NAME_CLIENT_SECRET) or ""
    return client_id.strip(), client_secret.strip()


def _save_credentials(client_id: str, client_secret: str) -> None:
    _write_windows_credential(TARGET_NAME_CLIENT_ID, client_id)
    _write_windows_credential(TARGET_NAME_CLIENT_SECRET, client_secret)


def _write_windows_credential(target_name: str, secret: str) -> None:
    payload = secret.encode("utf-16-le")
    blob = (ctypes.c_ubyte * len(payload)).from_buffer_copy(payload)
    cred = _CREDENTIALW()
    cred.Type = _CRED_TYPE_GENERIC
    cred.TargetName = target_name
    cred.CredentialBlobSize = len(payload)
    cred.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
    cred.Persist = _CRED_PERSIST_LOCAL_MACHINE
    cred.UserName = "SpotifyPlaylistUnliker"
    if not _CredWriteW(ctypes.byref(cred), 0):
        raise OSError(ctypes.get_last_error(), f"CredWriteW failed for {target_name}")


def _read_windows_credential(target_name: str) -> str | None:
    pcred = ctypes.POINTER(_CREDENTIALW)()
    ok = _CredReadW(target_name, _CRED_TYPE_GENERIC, 0, ctypes.byref(pcred))
    if not ok:
        err = ctypes.get_last_error()
        # 1168 == ERROR_NOT_FOUND
        if err == 1168:
            return None
        raise OSError(err, f"CredReadW failed for {target_name}")
    try:
        cred = pcred.contents
        if not cred.CredentialBlob or cred.CredentialBlobSize <= 0:
            return None
        raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
        return raw.decode("utf-16-le")
    finally:
        _CredFree(pcred)


def _delete_windows_credential(target_name: str) -> None:
    ok = _CredDeleteW(target_name, _CRED_TYPE_GENERIC, 0)
    if not ok:
        err = ctypes.get_last_error()
        # 1168 == ERROR_NOT_FOUND
        if err != 1168:
            raise OSError(err, f"CredDeleteW failed for {target_name}")


def _validate_saved_credentials(client_id: str, client_secret: str) -> bool:
    client_id = client_id.strip()
    client_secret = client_secret.strip()
    if not client_id or not client_secret:
        return False
    if any(ch.isspace() for ch in client_id) or any(ch.isspace() for ch in client_secret):
        return False
    if len(client_id) < 8 or len(client_secret) < 16:
        return False
    return True


def _prompt_if_missing(value: str, label: str) -> tuple[str, bool]:
    value = value.strip()
    if value:
        return value, False

    while True:
        prompt = f"Enter {label} (or type 'exit' to quit): "
        entered = input(prompt)
        entered = entered.strip()
        if entered.lower() == "exit":
            raise KeyboardInterrupt
        if entered:
            return entered, True
        print("Value cannot be empty. Paste the value from Spotify Developer Dashboard app settings.")


def _prompt_save_credentials() -> bool:
    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")

    while True:
        choice = input("Save login details for later? (Windows Credential Manager) Y/N: ").strip().lower()
        if choice in {"y", "yes"}:
            return True
        if choice in {"n", "no", ""}:
            return False
        print("Please enter Y or N.")


def build_auth_manager(scope: str, cache_path: str = ".spotify_cache") -> SpotifyOAuth:
    load_dotenv()
    _load_saved_env_values()

    if cache_path == ".spotify_cache":
        cache_dir = os.path.join(os.path.expanduser("~"), ".spotify-playlist-unliker")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, "spotify_cache")

    print(
        "Sign in to Spotify Developer Dashboard: https://developer.spotify.com/dashboard\n"
        "Open your app (or create one), then copy its Client ID and Client Secret when prompted.\n"
    )

    saved_client_id, saved_client_secret = _load_saved_credentials()
    client_id, entered_client_id = _prompt_if_missing(saved_client_id, "App Client ID")
    client_secret, entered_client_secret = _prompt_if_missing(saved_client_secret, "App Client Secret")

    if entered_client_secret:
        if os.name == "nt":
            os.system("cls")
        else:
            os.system("clear")

    if not _validate_saved_credentials(client_id, client_secret):
        raise ValueError(
            "Saved Spotify credentials are invalid. Clear them and re-enter correct values."
        )

    if entered_client_id or entered_client_secret:
        if _prompt_save_credentials():
            try:
                _save_credentials(client_id, client_secret)
                print("Saved login details for future runs.")
            except Exception as exc:
                print(f"Warning: could not save credentials ({exc}).")
                print("Continuing with this run only.")
        else:
            print("Login details will only be used for this run.")
    return SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=DEFAULT_REDIRECT_URI,
        scope=scope,
        open_browser=False,
        cache_path=cache_path,
    )

