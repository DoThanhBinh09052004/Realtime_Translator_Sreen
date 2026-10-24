from pathlib import Path
import json
import pytest


@pytest.mark.parametrize('latency',[0,700,2000])
def test_transcript_preserves_progressive_dialogue(qtbot,tmp_path,latency):
    from tools.replay_dialogue_video import run_replay
    summary=run_replay(Path('tests/fixtures/dialogue/progressive_game.json'),latency_ms=latency,mode='both',out_dir=tmp_path)
    assert summary['clears_within_active_turn']==0
    assert summary['shown_closed_turn_results']==0
    assert summary['peak_inflight']==1 and summary['peak_pending']<=32
    assert summary['nonempty_shows']>0
    assert (tmp_path/'events.jsonl').exists()
    assert json.loads((tmp_path/'summary.json').read_text(encoding='utf-8'))==summary


def test_live_requires_explicit_provider_and_network_flag(tmp_path):
    from tools.replay_dialogue_video import main
    common=['live','--video','missing.mp4','--out',str(tmp_path)]
    assert main(common)==2
    assert main(common+['--provider','OpenAI'])==2
    assert main(common+['--allow-network'])==2
    assert not list(tmp_path.iterdir())


def test_live_keeps_owner_alive_until_backend_drained(qtbot,monkeypatch,tmp_path):
    from PyQt5.QtCore import QObject, pyqtSignal, QTimer
    from PyQt5.QtWidgets import QApplication
    from threading import Event
    from types import SimpleNamespace
    import core.worker as module
    from tools import replay_dialogue_video as tool
    drained=Event()
    class Worker(QObject):
        revision_changed=pyqtSignal(int)
        subtitle_updated=pyqtSignal(object)
        blocks_updated=pyqtSignal(object)
        diagnostic_event=pyqtSignal(object)
        error_occurred=pyqtSignal(object)
        shutdown_finished=pyqtSignal()
        def __init__(self,*args):
            super().__init__();self._coordinator=self;self.running=False;self.stopping=False
            self._block_translator=SimpleNamespace(isRunning=lambda:self.running,wait=lambda *a:not self.running)
        def configure(self,*a):pass
        def set_capture_geometry(self,*a):pass
        def start_worker(self):
            self.running=True
            QTimer.singleShot(10,QApplication.instance().quit)  # external early close
        def stop_worker(self):
            if not self.stopping:
                self.stopping=True
                QTimer.singleShot(50,self.finish)
        def finish(self):self.running=False;drained.set();self.shutdown_finished.emit()
        def isRunning(self):return self.running
        def wait(self,*a):return not self.running
    monkeypatch.setattr(module,'TranslationWorker',Worker)
    monkeypatch.setattr(tool,'clip_info',lambda p:dict(decoded_duration_s=.01))
    tool.run_live(Path('not-opened.mp4'),provider='OpenAI',mode='subtitle',crop=[0,0,1,1],size=[100,40],out_dir=tmp_path)
    assert drained.is_set()
