from core.dialogue.context_models import *

def make_turn(source_id=1,text='A: Hello',version=1):
    return SourceTurn(source_id,version,text,OcrEvidence((OcrLine(text),)),0.,.6)

def make_view(*,epoch=1,scope_id='r1',turns=()):
    return MemoryView(epoch,scope_id,turns)

def stable(text='A: Hello',turn=1,version=1,revision=1):
    return StableTurn(revision,0,turn,version,text,OcrEvidence((OcrLine(text),)),0.,.6)

class ContextRuntimeHarness:
    """Real GUI/session/queue/service/overlay; only OCR input and SDK transport fake."""
    def __init__(self,qtbot,settings,responses,*,clock):
        from types import SimpleNamespace
        from unittest.mock import patch
        from PyQt5.QtCore import Qt
        from core.dialogue.coordinator import DialogueCoordinator
        from core.blocks.translation_worker import BlockTranslationWorker
        from ui.overlay import Overlay
        self.qtbot,self.settings,self.clock=qtbot,settings,clock
        self.responses=iter(responses);self.calls=[];self.events=[];self.presented=[];self.scan_id=0
        def create(**kwargs):
            self.calls.append(kwargs)
            value=next(self.responses)
            if callable(value):value=value(kwargs)
            if isinstance(value,Exception):raise value
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=value),finish_reason='stop')],usage=None)
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),close=lambda:None)
        self.patch=patch('engines.translator.OpenAI',lambda **kwargs:client);self.patch.start()
        self.coordinator=DialogueCoordinator(clock=clock)
        self.worker=BlockTranslationWorker(clock=clock)
        self.worker.diagnostic_event.connect(self.events.append)
        self.overlay=Overlay();qtbot.addWidget(self.overlay);self.overlay.set_mode('subtitle',1)
        self.overlay.translation_presented.connect(self.presented.append)
        self.coordinator.diagnostic_event.connect(self.events.append)
        self.coordinator.subtitle_updated.connect(self.overlay.update_subtitle)
        self.coordinator.jobs_changed.connect(self.worker.replace_pending)
        self.worker.job_started.connect(self.coordinator.on_job_started,Qt.QueuedConnection)
        self.worker.result_ready.connect(self.coordinator.on_result,Qt.QueuedConnection)
        self.coordinator.reset(settings,revision=1,session_id=1,running=True,memory_source=SourceKey('window',(1,)),memory_scopes=(ScopeSpec('legacy-subtitle'),))
        self.worker.start()

    def observe(self,ocr,*,at_s,scope_id='legacy-subtitle'):
        from core.dialogue.models import DialogueObservation
        self.scan_id+=1
        self.coordinator.observe(DialogueObservation(self.coordinator.revision,self.scan_id,at_s,at_s,self.settings,ocr,None))

    def close(self):
        self.coordinator._timer.stop();self.worker.request_stop()
        assert self.worker.wait(3000)
        self.patch.stop();self.overlay.close()
