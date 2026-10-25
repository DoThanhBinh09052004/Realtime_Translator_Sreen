"""Current-user Windows DPAPI credentials, with an explicit RAM-only mode."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys
import tempfile
import threading


PROVIDER_IDS = {'Google Gemini': 'gemini', 'OpenAI': 'openai',
                'DeepSeek': 'deepseek', 'Custom API': 'custom-api'}


class SecretStoreError(Exception):
    """A credential operation failed; messages never include credential data."""


class _Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


class DpapiProtector:
    def _crypt(self, value: bytes, *, decrypt: bool) -> bytes:
        if sys.platform != 'win32':
            raise SecretStoreError('Lưu key mã hóa chỉ khả dụng trên Windows.')
        crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        buffer = ctypes.create_string_buffer(value)
        source = _Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
        output = _Blob()
        function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
        function.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p,
                             ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                             wintypes.DWORD, ctypes.POINTER(_Blob)]
        function.restype = wintypes.BOOL
        try:
            # UI_FORBIDDEN only: never use CRYPTPROTECT_LOCAL_MACHINE.
            if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
                raise SecretStoreError('Không thể bảo vệ hoặc đọc API key bằng tài khoản Windows này.')
            return ctypes.string_at(output.data, output.size)
        finally:
            if output.data:
                kernel32.LocalFree(ctypes.cast(output.data, ctypes.c_void_p))

    def protect(self, value: bytes) -> bytes:
        return self._crypt(value, decrypt=False)

    def unprotect(self, value: bytes) -> bytes:
        return self._crypt(value, decrypt=True)


class SecretStore:
    def __init__(self, directory: Path, *, protector=None):
        self._directory = Path(directory)
        self._protector = protector if protector is not None else DpapiProtector()
        self._session = {}
        self._lock = threading.RLock()

    def _path(self, provider):
        if provider not in PROVIDER_IDS:
            raise SecretStoreError('Công cụ dịch không hỗ trợ lưu API key.')
        return self._directory / (PROVIDER_IDS[provider] + '.bin')

    def get(self, provider: str) -> str | None:
        with self._lock:
            path = self._path(provider)
            if provider in self._session:
                return self._session[provider]
            try:
                with path.open('rb') as stream:
                    value = stream.read(65537)
                if len(value) > 65536:
                    raise ValueError()
                return self._protector.unprotect(value).decode('utf-8')
            except FileNotFoundError:
                return None
            except Exception:
                raise SecretStoreError('Không thể đọc API key đã lưu. Bạn có thể nhập key chỉ dùng trong phiên.') from None

    def storage(self, provider: str) -> str:
        with self._lock:
            if provider in self._session:
                return 'session'
            return 'saved' if self.get(provider) is not None else 'none'

    def set(self, provider: str, key: str, *, persist: bool) -> None:
        with self._lock:
            path = self._path(provider)
            if not isinstance(key, str) or not key.strip() or len(key) > 16384 or any(c in key for c in '\r\n\0'):
                raise SecretStoreError('API key không hợp lệ.')
            key = key.strip()
            try:
                encoded = key.encode('utf-8')
            except UnicodeError:
                raise SecretStoreError('API key không hợp lệ.') from None
            if len(encoded) > 16384:
                raise SecretStoreError('API key vượt quá kích thước cho phép.')
            if not persist:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    raise SecretStoreError('Không thể xóa key đã lưu để chuyển sang chỉ dùng trong phiên.') from None
                self._session[provider] = key
                return
            temporary = None
            try:
                encrypted = self._protector.protect(encoded)
                if not encrypted or len(encrypted) > 65536:
                    raise ValueError()
                self._directory.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=self._directory, prefix='.credential-', delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(encrypted)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
                self._session.pop(provider, None)
            except Exception:
                raise SecretStoreError('Không thể lưu API key mã hóa. Hãy chọn chỉ dùng trong phiên hoặc kiểm tra quyền ghi.') from None
            finally:
                if temporary is not None:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass

    def delete(self, provider: str) -> None:
        with self._lock:
            try:
                self._path(provider).unlink(missing_ok=True)
            except OSError:
                raise SecretStoreError('Không thể xóa API key đã lưu.') from None
            self._session.pop(provider, None)
