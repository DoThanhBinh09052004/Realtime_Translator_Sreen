"""Persist settings before applying them to runtime services."""
from typing import Callable
from PyQt5.QtCore import QObject, pyqtSignal
from core.config import (
    State, ConfigError, PROVIDERS, load_config, save_config, load_region, save_region,
    load_active_provider, save_active_provider, load_provider_model_id,
    save_provider_model_id, load_provider_api_key, save_provider_api_key,
    load_runtime_settings, load_custom_api_base_url, save_custom_api_base_url,
    get_provider_capabilities,
    provider_key_storage, import_legacy_provider_key, remove_legacy_provider_key,
)
from core.languages import language_by_config_name, language_by_id
from ui.controller_state import (AiPageState, OcrPageState, SubtitlePageState, ControllerSnapshot,
                                 LanguageChoice, LanguagePacksState, PackageRowState)


class SettingsCoordinator(QObject):
    settings_changed = pyqtSignal(object, str)
    save_failed = pyqtSignal(str)
    drag_mode_changed = pyqtSignal(bool)
    pack_state_changed = pyqtSignal(object)

    def __init__(self, state: State, worker=None, overlay=None, parent=None, *, pack_manager=None):
        super().__init__(parent)
        self.state = state
        self.worker = worker
        self.overlay = overlay
        self._interval_initialized = False
        self.pack_manager = pack_manager
        self._pack_snapshot = None
        if pack_manager is not None:
            pack_manager.set_selected_language(language_by_config_name(state.source).id)
            self._pack_snapshot = pack_manager.snapshot()
            pack_manager.snapshot_changed.connect(self._on_pack_snapshot)

    def snapshot(self) -> ControllerSnapshot:
        provider = load_active_provider()
        model = load_provider_model_id(provider)
        models = tuple(PROVIDERS[provider]['models'])
        if model not in models:
            models += (model,)
        region = load_region()
        capabilities = get_provider_capabilities(provider)
        return ControllerSnapshot(
            AiPageState(provider, model, models, load_provider_api_key(provider),
                        PROVIDERS[provider]['placeholder'],
                        load_custom_api_base_url() if provider == 'Custom API' else '',
                        capabilities.requires_api_key, capabilities.supports_models, capabilities.supports_base_url,
                        provider_key_storage(provider)),
            OcrPageState(self.state.source, self.state.target, load_config()['interval_ms'],
                         tuple(region[key] for key in ('left', 'top', 'width', 'height')) if region else None,
                         self._source_choices(), self._source_notice()),
            SubtitlePageState(self.state.bg_color, self.state.text_color, self.state.bg_opacity,
                              self.state.font_size, self.state.overlay_preset, self.state.overlay_x, self.state.overlay_y,
                              self.state.overlay_mode))

    def _source_choices(self):
        if self._pack_snapshot is None:
            return None
        return tuple(LanguageChoice(row.language_id, language_by_id(row.language_id).config_name,
                                    language_by_id(row.language_id).config_name)
                     for row in self._pack_snapshot.rows if row.state == 'installed')

    def source_ready(self) -> bool:
        choices = self._source_choices()
        return choices is None or any(choice.config_name == self.state.source for choice in choices)

    def _source_notice(self) -> str:
        if self.source_ready():
            return ''
        return f'Gói OCR {self.state.source} chưa sẵn sàng. Mở Quản lý gói ngôn ngữ để cài hoặc sửa gói.'

    def _on_pack_snapshot(self, snapshot) -> None:
        self._pack_snapshot = snapshot
        self.settings_changed.emit(self.snapshot(), 'language_packs')
        self.pack_state_changed.emit(self.pack_dialog_state())

    def pack_dialog_state(self) -> LanguagePacksState:
        if self._pack_snapshot is None:
            return LanguagePacksState((), False, 'Trình quản lý gói ngôn ngữ chưa được kết nối.')
        snapshot = self._pack_snapshot
        rows = []
        statuses = {'not_installed': 'Chưa cài', 'installed': 'Đã cài', 'downloading': 'Đang tải',
                    'verifying': 'Đang xác thực', 'installing': 'Đang cài đặt',
                    'removing': 'Đang xóa gói', 'error': 'Cần xử lý'}
        for row in snapshot.rows:
            language = language_by_id(row.language_id)
            selected = language.config_name == self.state.source
            action, reason, detail = None, '', ''
            status = statuses.get(row.state, row.state)
            enabled = not snapshot.busy
            if row.origin == 'bundled' and row.state == 'installed':
                status = 'Có sẵn trong ứng dụng'
                detail = f'Dung lượng: {row.installed_bytes:,} byte.'
            elif language.bundled and row.state not in ('downloading', 'verifying', 'installing', 'removing'):
                reason = 'Gói có sẵn chưa sẵn sàng. Kiểm tra bản cài đặt và cài lại ứng dụng nếu cần.'
                detail = row.error.user_message if row.error else ''
            elif row.state == 'installed':
                detail = f'Dung lượng: {row.installed_bytes:,} byte.'
                action = 'remove'
                enabled = enabled and row.removable and not row.in_use and not selected
                if selected:
                    reason = 'Chọn ngôn ngữ khác trước khi xóa.'
                elif row.in_use:
                    reason = 'Gói đang được OCR sử dụng. Dừng hoặc đổi ngôn ngữ rồi thử lại.'
                elif snapshot.busy:
                    reason = 'Chờ thao tác gói hiện tại hoàn tất.'
                elif not row.removable:
                    reason = 'Gói này được bảo vệ và không thể xóa.'
            elif row.state in ('downloading', 'verifying', 'installing'):
                action, enabled = 'cancel', True
            elif row.state == 'not_installed':
                action = 'install'
                detail = 'Tải gói để nhận diện ngôn ngữ này.'
            elif row.state == 'error':
                detail = row.error.user_message if row.error else 'Gói chưa sẵn sàng. Hãy thử lại.'
                # Bundled files require repairing the app, never a write to its assets.
                if row.origin != 'bundled' and (row.error is None or row.error.retryable):
                    action = 'retry'
                else:
                    reason = 'Kiểm tra bản cài đặt ứng dụng và cài lại nếu cần.'
            if selected and row.state == 'installed':
                status += ' · Đang chọn'
            if snapshot.busy and action in ('install', 'retry'):
                reason = 'Chờ thao tác gói hiện tại hoàn tất.'
            rows.append(PackageRowState(row.language_id, language.config_name, row.state, status, detail,
                                        row.downloaded_bytes, row.total_bytes, row.reclaimable_bytes,
                                        action, enabled, reason))
        return LanguagePacksState(tuple(rows), snapshot.busy)

    def _commit(self, action: Callable[[], None], *, field: str,
                after_commit: Callable[[], None] | None = None) -> bool:
        try:
            action()
        except ConfigError as exc:
            self.settings_changed.emit(self.snapshot(), 'rollback')
            self.save_failed.emit(str(exc))
            return False
        if after_commit is not None:
            after_commit()
        self.settings_changed.emit(self.snapshot(), field)
        return True

    def _configure_worker(self):
        revision = 0
        if self.worker is not None:
            revision = self.worker.configure(load_runtime_settings(self.state, load_config()['interval_ms']))
        if self.overlay is not None:
            self.overlay.set_mode(self.state.overlay_mode, revision)

    def set_overlay_mode(self, mode):
        if mode not in ('subtitle', 'blocks'):
            return False
        return self._commit(lambda: self.state.update(overlay_mode=mode), field='overlay_mode', after_commit=self._configure_worker)

    def initialize_worker_interval(self) -> None:
        if not self._interval_initialized:
            if self.worker is not None:
                self.worker.setInterval(load_config()['interval_ms'])
            self._interval_initialized = True

    def set_overlay(self, overlay) -> None:
        self.overlay = overlay

    def set_provider(self, name: str) -> bool:
        if name not in PROVIDERS:
            return False
        return self._commit(lambda: save_active_provider(name), field='provider', after_commit=self._configure_worker)

    def set_model(self, model_id: str) -> bool:
        if not get_provider_capabilities().supports_models:
            return False
        if not model_id.strip():
            return False
        return self._commit(lambda: save_provider_model_id(load_active_provider(), model_id.strip()),
                            field='model', after_commit=self._configure_worker)

    def set_api_key(self, key: str, persist: bool = True) -> bool:
        if not get_provider_capabilities().requires_api_key:
            return False
        try:
            save_provider_api_key(load_active_provider(), key.strip(), persist=persist)
        except ConfigError as error:
            # Preserve the draft so a failed DPAPI save can be retried in RAM.
            self.save_failed.emit(str(error))
            return False
        self._configure_worker()
        self.settings_changed.emit(self.snapshot(), 'api_key')
        return True

    def delete_api_key(self) -> bool:
        if not get_provider_capabilities().requires_api_key:
            return False
        return self._commit(lambda: save_provider_api_key(load_active_provider(), ''),
                            field='api_key_deleted', after_commit=self._configure_worker)

    def import_legacy_key(self, persist: bool) -> bool:
        if not get_provider_capabilities().requires_api_key:
            return False
        return self._commit(lambda: import_legacy_provider_key(load_active_provider(), persist=persist),
                            field='api_key_import', after_commit=self._configure_worker)

    def remove_legacy_key(self) -> bool:
        return self._commit(lambda: remove_legacy_provider_key(load_active_provider()), field='api_key')

    def set_custom_base_url(self, base_url: str) -> bool:
        if load_active_provider() != 'Custom API':
            return False
        return self._commit(lambda: save_custom_api_base_url(base_url),
                            field='base_url', after_commit=self._configure_worker)

    def set_source(self, language: str) -> bool:
        choices = self._source_choices()
        if choices is not None and not any(choice.config_name == language for choice in choices):
            self.settings_changed.emit(self.snapshot(), 'rollback')
            self.save_failed.emit(f'Gói OCR {language} chưa sẵn sàng. Mở Quản lý gói ngôn ngữ để cài hoặc sửa gói.')
            return False
        def apply():
            if self.pack_manager is not None:
                self.pack_manager.set_selected_language(language_by_config_name(language).id)
                self._pack_snapshot = self.pack_manager.snapshot()
                self.pack_state_changed.emit(self.pack_dialog_state())
            self._configure_worker()
        return self._commit(lambda: self.state.update(source=language), field='source', after_commit=apply)

    def set_target(self, language: str) -> bool:
        return self._commit(lambda: self.state.update(target=language), field='target', after_commit=self._configure_worker)

    def set_interval(self, interval_ms: int) -> bool:
        return self._commit(lambda: save_config('interval_ms', interval_ms), field='interval', after_commit=self._configure_worker)

    def set_subtitle_style(self, changes: dict) -> bool:
        if changes.keys() - {'bg_color', 'text_color', 'bg_opacity', 'font_size'}:
            raise ValueError('Unsupported subtitle style field')
        return self._commit(lambda: self.state.update(**changes), field='subtitle_style', after_commit=self._apply_style)

    def _apply_style(self):
        if self.overlay is not None:
            self.overlay.apply_style(bg_hex=self.state.bg_color, opacity_pct=self.state.bg_opacity,
                                     text_hex=self.state.text_color, font_size=self.state.font_size)

    def set_overlay_preset(self, preset: str) -> bool:
        def apply():
            if self.overlay is not None and self.state.overlay_preset != 'custom':
                self.overlay.apply_preset(self.state.overlay_preset)
        return self._commit(lambda: self.state.update(overlay_preset=preset), field='preset', after_commit=apply)

    def save_overlay_position(self, x: int, y: int) -> bool:
        success = self._commit(lambda: self.state.update(overlay_x=x, overlay_y=y, overlay_preset='custom'),
                               field='overlay_position')
        if not success and self.overlay is not None:
            if self.state.overlay_preset == 'custom' and self.state.overlay_x is not None and self.state.overlay_y is not None:
                self.overlay.move(self.state.overlay_x, self.state.overlay_y)
                self.overlay.current_preset = 'custom'
            else:
                self.overlay.apply_preset(self.state.overlay_preset)
        return success

    def toggle_overlay_drag(self) -> bool:
        if self.overlay is None or self.state.overlay_mode == 'blocks':
            return False
        enabled = not self.overlay.is_drag_mode
        self.overlay.set_drag_mode(enabled)
        self.drag_mode_changed.emit(enabled)
        return enabled

    def apply_region_selection(self, region: dict) -> bool:
        def apply():
            if self.worker is not None:
                revision = self.worker.set_region(load_region())
                if self.overlay is not None:
                    self.overlay.set_mode(self.state.overlay_mode, revision)
        return self._commit(lambda: save_region(region), field='region', after_commit=apply)
