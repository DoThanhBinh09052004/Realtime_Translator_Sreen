"""Writable user data is separate from packaged, read-only resources."""
from dataclasses import dataclass
from pathlib import Path

from PyQt5.QtCore import QStandardPaths


@dataclass(frozen=True)
class AppPaths:
    config_dir: Path
    cache_dir: Path
    logs_dir: Path
    models_dir: Path


def get_app_paths() -> AppPaths:
    def location(kind):
        value = QStandardPaths.writableLocation(kind)
        if not value:
            raise OSError('Không tìm thấy thư mục dữ liệu người dùng.')
        return (Path(value) / 'TranslateHUD' / 'TranslateHUD').resolve()
    data = location(QStandardPaths.GenericDataLocation)
    cache = location(QStandardPaths.GenericCacheLocation)
    return AppPaths(data, cache, data / 'logs', cache / 'models')
