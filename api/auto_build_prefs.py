"""Settings > App tools > App update: what happens by itself around an update and a build.

  build_after_update      after "Update project" changed the repo, start the APK build
  download_after_build    when the build is done, download the APK to Download/Yt-bridge/APK
  install_after_download  when it is saved, open Android's installer

Saved on the phone, so the choice stays after the app is closed. Installing needs the download,
so the two are kept consistent: install on -> download on; download off -> install off.
"""
from api.github.auth import _settings_store

_KEY = "auto_build"
_DEFAULTS = {"build_after_update": False, "download_after_build": False,
             "install_after_download": False}


def _load() -> dict:
    out = dict(_DEFAULTS)
    try:
        if _settings_store.exists(_KEY):
            out.update(dict(_settings_store.get(_KEY)))
    except Exception:
        pass
    return out


def _save(**changes) -> None:
    data = _load()
    data.update(changes)
    _settings_store.put(_KEY, **data)


def build_after_update() -> bool:
    return bool(_load().get("build_after_update"))


def download_after_build() -> bool:
    data = _load()
    return bool(data.get("download_after_build") or data.get("install_after_download"))


def install_after_download() -> bool:
    return bool(_load().get("install_after_download"))


def set_build_after_update(value) -> None:
    _save(build_after_update=bool(value))


def set_download_after_build(value) -> None:
    if value:
        _save(download_after_build=True)
    else:
        _save(download_after_build=False, install_after_download=False)


def set_install_after_download(value) -> None:
    if value:
        _save(install_after_download=True, download_after_build=True)
    else:
        _save(install_after_download=False)
