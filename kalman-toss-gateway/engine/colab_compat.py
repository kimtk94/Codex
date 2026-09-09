from __future__ import annotations

import os
import sys
import types
from pathlib import Path


class _UserData:
    @staticmethod
    def get(key: str):
        return os.environ.get(key)


class _Drive:
    @staticmethod
    def mount(path: str, *_, **__):
        _ensure_drive_alias(Path(path))
        print(f"[server] Drive compatibility path ready: {path}/MyDrive")


class _Auth:
    @staticmethod
    def authenticate_user(*_, **__):
        # On a server, google.auth.default() uses ADC / GOOGLE_APPLICATION_CREDENTIALS.
        if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            print("[server] Google auth: relying on Application Default Credentials")


def _ensure_drive_alias(mount_path: Path = Path("/content/drive")) -> Path:
    data_root = Path(os.environ.get("KALMAN_DATA_ROOT", "/opt/kalman/data")).expanduser().resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    mount_path.mkdir(parents=True, exist_ok=True)
    alias = mount_path / "MyDrive"
    if alias.is_symlink():
        if alias.resolve() != data_root:
            alias.unlink()
        else:
            return alias
    if alias.exists() and not alias.is_symlink():
        raise RuntimeError(
            f"{alias} already exists and is not a symlink. "
            f"Move it aside, then link it to KALMAN_DATA_ROOT={data_root}."
        )
    alias.symlink_to(data_root, target_is_directory=True)
    return alias


def install_colab_compat() -> None:
    _ensure_drive_alias()
    colab = types.ModuleType("google.colab")
    colab.userdata = _UserData()
    colab.drive = _Drive()
    colab.auth = _Auth()
    sys.modules["google.colab"] = colab

    try:
        import google  # namespace package from google-auth, if installed
    except Exception:
        google = types.ModuleType("google")
        sys.modules["google"] = google
    setattr(google, "colab", colab)
