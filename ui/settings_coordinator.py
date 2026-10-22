"""Persist settings before applying them to runtime services."""
from typing import Callable
from PyQt5.QtCore import QObject, pyqtSignal
from core.config import (
    State, ConfigError, PROVIDERS, load_config, save_config, load_region, save_region,
    load_active_provider, save_active_provider, load_provider_model_id,
    save_provider_model_id, load_provider_api_key, save_provider_api_key,
    load_runtime_settings, load_custom_api_base_url, save_custom_api_base_url,
)
from ui.controller_state import AiPageState, OcrPageState, SubtitlePageState, ControllerSnapshot


class SettingsCoordinator(QObject):
    settings_changed = pyqtSignal(object, str)
    save_failed = pyqtSignal(str)
    drag_mode_changed = pyqtSignal(bool)

    def __init__(self, state: State, worker=None, overlay=None, parent=None):
        super().__init__(parent)
        self.state = state
        self.worker = worker
        self.overlay = overlay
        self._interval_initialized = False

    def snapshot(self) -> ControllerSnapshot:
        provider = load_active_provider()
        model = load_provider_model_id(provider)
        models = tuple(PROVIDERS[provider]['models'])
        if model not in models:
            models += (model,)
        region = load_region()
        return ControllerSnapshot(
            AiPageState(provider, model, models, load_provider_api_key(provider),
                        PROVIDERS[provider]['placeholder'],
                        load_custom_api_base_url() if provider == 'Custom API' else ''),
            OcrPageState(self.state.source, self.state.target, load_config()['interval_ms'],
                         tuple(region[key] for key in ('left', 'top', 'width', 'height')) if region else None),
            SubtitlePageState(self.state.bg_color, self.state.text_color, self.state.bg_opacity,
                              self.state.font_size, self.state.overlay_preset, self.state.overlay_x, self.state.overlay_y))

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
        if self.worker is not None:
            self.worker.configure(load_runtime_settings(self.state, load_config()['interval_ms']))

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
        if not model_id.strip():
            return False
        return self._commit(lambda: save_provider_model_id(load_active_provider(), model_id.strip()),
                            field='model', after_commit=self._configure_worker)

    def set_api_key(self, key: str) -> bool:
        return self._commit(lambda: save_provider_api_key(load_active_provider(), key.strip()),
                            field='api_key', after_commit=self._configure_worker)

    def set_custom_base_url(self, base_url: str) -> bool:
        if load_active_provider() != 'Custom API':
            return False
        return self._commit(lambda: save_custom_api_base_url(base_url),
                            field='base_url', after_commit=self._configure_worker)

    def set_source(self, language: str) -> bool:
        return self._commit(lambda: self.state.update(source=language), field='source', after_commit=self._configure_worker)

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
        if self.overlay is None:
            return False
        enabled = not self.overlay.is_drag_mode
        self.overlay.set_drag_mode(enabled)
        self.drag_mode_changed.emit(enabled)
        return enabled

    def apply_region_selection(self, region: dict) -> bool:
        def apply():
            if self.worker is not None:
                self.worker.set_region(load_region())
        return self._commit(lambda: save_region(region), field='region', after_commit=apply)
