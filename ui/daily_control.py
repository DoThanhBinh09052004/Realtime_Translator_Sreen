"""Daily control screen coordinator and state computation."""
from PyQt5.QtCore import QObject, pyqtSignal

from core.config import (
    load_capture_setup_complete, load_active_provider, get_provider_capabilities,
    load_provider_api_key, load_provider_model_id, load_custom_api_base_url,
)
from core.endpoint_policy import normalize_custom_api_endpoint, EndpointPolicyError
from ui.controller_state import DailyReadiness, DailyRunState


class DailyControlCoordinator(QObject):
    state_changed = pyqtSignal(object, object)

    def __init__(self, settings_coordinator, worker, controller, parent=None):
        super().__init__(parent)
        self.settings_coordinator = settings_coordinator
        self.worker = worker
        self.controller = controller
        self.binding = None
        self.lifecycle = None

        if hasattr(self.settings_coordinator, "settings_changed"):
            self.settings_coordinator.settings_changed.connect(lambda *args: self.refresh())
        if hasattr(self.settings_coordinator, "save_failed"):
            self.settings_coordinator.save_failed.connect(lambda *args: self.refresh())
        if hasattr(self.controller, "daily_state_changed"):
            self.controller.daily_state_changed.connect(self.refresh)
        if hasattr(self.worker, "finished") and hasattr(self.worker.finished, "connect"):
            self.worker.finished.connect(self.refresh)

    def attach_capture(self, binding, lifecycle) -> None:
        self.binding = binding
        self.lifecycle = lifecycle
        if hasattr(binding, "binding_state_changed"):
            binding.binding_state_changed.connect(self.refresh)
        if hasattr(lifecycle, "activity_changed"):
            lifecycle.activity_changed.connect(self.refresh)
        self.refresh()

    def readiness(self) -> DailyReadiness:
        # 1. Source / binding check
        if self.binding is not None:
            is_bound = getattr(self.binding, "is_bound", False)
            profile = getattr(self.binding, "profile", None)
            if not is_bound or profile is None:
                return DailyReadiness(ready=False, reason="Chưa chọn nguồn chụp.", action="select_source")

            # 2. Region setup check
            if not load_capture_setup_complete():
                return DailyReadiness(ready=False, reason="Chưa chọn vùng đọc chữ.", action="select_regions")

            regions = getattr(profile, "regions", ())
            if not any(getattr(r, "enabled", False) for r in regions):
                return DailyReadiness(ready=False, reason="Chưa bật vùng đọc chữ nào.", action="select_regions")
        else:
            is_bound = getattr(self.controller, "_capture_bound", False)
            profile = getattr(self.controller, "_capture_profile", None)
            if not is_bound:
                return DailyReadiness(ready=False, reason="Chưa chọn nguồn chụp.", action="select_source")

            # 2. Region setup check for standalone/legacy controller
            if profile is not None:
                regions = getattr(profile, "regions", ())
                if not load_capture_setup_complete() and not any(getattr(r, "enabled", False) for r in regions):
                    return DailyReadiness(ready=False, reason="Chưa chọn vùng đọc chữ.", action="select_regions")
                if not any(getattr(r, "enabled", False) for r in regions):
                    return DailyReadiness(ready=False, reason="Chưa bật vùng đọc chữ nào.", action="select_regions")
            else:
                if not load_capture_setup_complete():
                    return DailyReadiness(ready=False, reason="Chưa chọn vùng đọc chữ.", action="select_regions")

        # 3. Language pack check
        if hasattr(self.settings_coordinator, "source_ready") and not self.settings_coordinator.source_ready():
            source_lang = getattr(getattr(self.settings_coordinator, "state", None), "source", "nguồn")
            return DailyReadiness(ready=False, reason=f"Gói OCR {source_lang} chưa sẵn sàng.", action="manage_packs")

        # 4. Provider configuration check
        provider = load_active_provider()
        caps = get_provider_capabilities(provider)
        if caps.requires_api_key:
            key = load_provider_api_key(provider)
            if not key or not key.strip():
                return DailyReadiness(ready=False, reason=f"Chưa cấu hình API key cho {provider}.", action="configure_provider")
        if caps.supports_models:
            model = load_provider_model_id(provider)
            if not model or not model.strip():
                return DailyReadiness(ready=False, reason=f"Chưa chọn mô hình cho {provider}.", action="configure_provider")
        if caps.supports_base_url:
            url = load_custom_api_base_url()
            if not url or not url.strip():
                return DailyReadiness(ready=False, reason="Chưa cấu hình URL API tùy chỉnh.", action="configure_provider")
            try:
                normalize_custom_api_endpoint(url)
            except EndpointPolicyError as exc:
                return DailyReadiness(ready=False, reason=str(exc), action="configure_provider")

        return DailyReadiness(ready=True, reason="Sẵn sàng dịch", action=None)

    def run_state(self) -> DailyRunState:
        is_drained = getattr(self.worker, "is_drained", True) is not False
        run_requested = getattr(self.controller, "capture_run_requested", False) is True
        is_running_fn = getattr(self.worker, "is_running", None)
        is_running = is_running_fn() is True if callable(is_running_fn) else False
        is_qthread_fn = getattr(self.worker, "isRunning", None)
        is_qthread = is_qthread_fn() is True if callable(is_qthread_fn) else False
        restart_pending = getattr(self.worker, "restart_pending", False) is True

        if self.binding is not None:
            is_waiting = getattr(self.binding, "is_waiting", False) or not getattr(self.binding, "is_bound", False)
        else:
            is_waiting = not getattr(self.controller, "_capture_bound", True)

        # 1. Stopping / draining
        if not is_drained and not run_requested:
            return DailyRunState(phase="stopping", message="Đang dừng...", can_toggle=False, preview_enabled=False)

        # 2. Waiting for source
        if run_requested and is_waiting:
            return DailyRunState(phase="waiting_source", message="Đang chờ nguồn chụp...", can_toggle=True, preview_enabled=False)

        # 3. Starting / restart pending
        if run_requested and restart_pending:
            return DailyRunState(phase="starting", message="Đang khởi động...", can_toggle=True, preview_enabled=False)

        # 4. Running
        if is_running or is_qthread or (run_requested and not is_waiting):
            return DailyRunState(phase="running", message="Đang dịch", can_toggle=True, preview_enabled=False)

        # 5. Stopped
        r = self.readiness()
        if self.binding is not None:
            bound = getattr(self.binding, "is_bound", False)
        else:
            bound = getattr(self.controller, "_capture_bound", False)
        is_editor_active = getattr(self.lifecycle, "is_active", False)
        preview_enabled = bool(bound and not is_editor_active)
        return DailyRunState(phase="stopped", message=r.reason, can_toggle=r.ready, preview_enabled=preview_enabled)

    def toggle_translation(self) -> None:
        current_run = self.run_state()
        if current_run.phase in ("running", "waiting_source", "starting"):
            if self.lifecycle is not None and hasattr(self.lifecycle, "cancel_dashboard_preview"):
                self.lifecycle.cancel_dashboard_preview()
            if hasattr(self.controller, "stop_ocr"):
                self.controller.stop_ocr()
        elif current_run.phase == "stopped":
            if self.readiness().ready:
                if self.lifecycle is not None and not getattr(self.lifecycle, "preview_is_drained", True):
                    if hasattr(self.lifecycle, "queue_start_intent"):
                        self.lifecycle.queue_start_intent()
                    return
                if hasattr(self.controller, "start_ocr"):
                    self.controller.start_ocr()

    def request_preview(self) -> bool:
        if self.lifecycle is not None and hasattr(self.lifecycle, "request_dashboard_preview"):
            return self.lifecycle.request_dashboard_preview()
        return False

    def refresh(self) -> None:
        self.state_changed.emit(self.readiness(), self.run_state())
