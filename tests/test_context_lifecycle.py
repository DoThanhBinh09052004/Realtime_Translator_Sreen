from dataclasses import replace
import pytest
from core import config
from core.worker import TranslationWorker
from core.dialogue.context_models import *
from tests.context_helpers import stable

@pytest.mark.parametrize('change,reset',[({'interval_ms':900},False),({'ocr_threads':2},False),({'target_lang':'English'},True),({'context_enabled':False},True)])
def test_runtime_revision_has_independent_memory_epoch(qtbot,change,reset):
    w=TranslationWorker(config.State(),config.DEFAULT_REGION)
    w.configure(replace(w._settings,context_enabled=True))
    memory=w._coordinator.context_memory
    memory.observe('legacy-subtitle',stable())
    epoch=memory.view('legacy-subtitle',now_s=0).epoch
    w.configure(replace(w._settings,**change))
    assert (memory.view('legacy-subtitle',now_s=0).epoch!=epoch)==reset

def test_reset_context_changes_revision_and_invalidates_memory(qtbot):
    w=TranslationWorker(config.State(),config.DEFAULT_REGION)
    memory=w._coordinator.context_memory
    memory.observe('legacy-subtitle',stable())
    revision=w.revision
    assert w.reset_dialogue_context()>revision
    assert not memory.view('legacy-subtitle',now_s=0).turns

def test_old_source_terminal_signal_cannot_clear_new_source(qtbot):
    w=TranslationWorker(config.State(),config.DEFAULT_REGION)
    revision=w.revision
    w.invalidate_context_source(999)
    assert w.revision==revision
