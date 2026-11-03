"""GUI-owned lifecycle intent, independent of Qt and native/SDK resources."""
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class LifecycleAction:
    kind: Literal['restart', 'shutdown']
    preserve_session: bool = False


@dataclass
class WorkerLifecycle:
    restart_pending: bool = False
    restart_preserve_session: bool = False
    shutdown_pending: bool = False

    def request_restart(self, *, preserve_session):
        self.restart_pending = True
        self.restart_preserve_session = preserve_session

    def request_start(self, *, capture_running, translation_running, running, preserve_session):
        if self.restart_pending:
            return False
        if ((self.shutdown_pending and capture_running)
                or (translation_running and not running)):
            self.request_restart(preserve_session=preserve_session)
            return False
        return not capture_running and not translation_running

    def request_direct_start(self, *, capture_running, translation_running, preserve_session):
        if capture_running:
            return False
        if translation_running:
            self.request_restart(preserve_session=preserve_session)
            return False
        return True

    def request_stop(self):
        self.restart_pending = False
        self.shutdown_pending = True

    def started(self):
        # Any actual start consumes the intent, including the public start() API.
        self.restart_pending = False
        self.shutdown_pending = False

    def threads_finished(self, *, capture_running, translation_running):
        if capture_running or translation_running:
            return None
        if self.restart_pending:
            self.restart_pending = False
            return LifecycleAction('restart', self.restart_preserve_session)
        if self.shutdown_pending:
            self.shutdown_pending = False
            return LifecycleAction('shutdown')
        return None
