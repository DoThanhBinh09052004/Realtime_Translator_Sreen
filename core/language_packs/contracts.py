"""Immutable messages exchanged between the package store, workers and GUI."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactFile:
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ArtifactDefinition:
    id: str
    revision: str
    url: str
    archive_size_bytes: int
    archive_sha256: str
    archive_root: str
    files: tuple[ArtifactFile, ...]


@dataclass(frozen=True)
class ResourceDefinition:
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class PackCatalog:
    schema: int
    paddleocr_version: str
    ocr_version: str
    components: dict[str, ArtifactDefinition]
    resources: dict[str, ResourceDefinition]


@dataclass(frozen=True)
class PackError:
    code: str
    user_message: str
    retryable: bool


class PackOperationError(Exception):
    def __init__(self, error: PackError):
        self.error = error
        super().__init__(error.user_message)


def pack_error(code: str) -> PackOperationError:
    messages = {
        'busy': 'Một thao tác gói ngôn ngữ đang chạy. Hãy thử lại sau.',
        'network': 'Không tải được gói ngôn ngữ. Kiểm tra kết nối rồi thử lại.',
        'disk_space': 'Không đủ dung lượng để cài gói ngôn ngữ.',
        'permission': 'Không thể ghi dữ liệu gói ngôn ngữ. Kiểm tra quyền truy cập.',
        'integrity': 'Gói ngôn ngữ không hợp lệ. Hãy thử tải lại.',
        'incompatible': 'Gói ngôn ngữ không tương thích với phiên bản OCR này.',
        'cancelled': 'Đã hủy tải gói ngôn ngữ.',
        'in_use': 'Gói ngôn ngữ đang được sử dụng. Chọn ngôn ngữ khác trước khi xóa.',
        'protected': 'Gói có sẵn trong ứng dụng không thể xóa.',
        'invalid_catalog': 'Danh mục gói ngôn ngữ không hợp lệ. Hãy cài lại ứng dụng.',
        'missing': 'Gói ngôn ngữ chưa được cài hoặc bị hỏng. Mở quản lý gói để cài lại.',
    }
    return PackOperationError(PackError(code, messages[code], code not in ('protected', 'incompatible', 'invalid_catalog')))


@dataclass(frozen=True)
class PackState:
    language_id: str
    state: str
    origin: str
    revision: str | None
    removable: bool
    in_use: bool
    installed_bytes: int
    reclaimable_bytes: int
    downloaded_bytes: int = 0
    total_bytes: int = 0
    error: PackError | None = None


@dataclass(frozen=True)
class PackSnapshot:
    rows: tuple[PackState, ...]
    operation_id: str | None = None
    busy: bool = False


@dataclass(frozen=True)
class InstallPlan:
    language_id: str
    components: tuple[ArtifactDefinition, ...]
    resources: tuple[ResourceDefinition, ...]
    network_bytes: int
    required_disk_bytes: int


@dataclass(frozen=True)
class RemovalResult:
    reclaimed_bytes: int
    pending_cleanup: bool


@dataclass(frozen=True)
class PackProgress:
    operation_id: str
    language_id: str
    state: str
    downloaded_bytes: int
    total_bytes: int
