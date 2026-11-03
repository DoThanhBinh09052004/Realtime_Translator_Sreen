"""Output policy contracts exercised through the public worker signals."""
from dataclasses import replace

from core import config
from core.contracts import SubtitleFrame, TranslationStatus
from core.translation.google_recovery import GoogleRecoverySnapshot
from core.runtime.worker import TranslationWorker


def test_subtitle_empty_duplicate_stale_and_revision_reset(qtbot, runtime_settings):
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    worker.configure(runtime_settings)
    worker._is_running = True
    frames, texts = [], []
    worker.subtitle_updated.connect(frames.append)
    worker.text_translated.connect(texts.append)
    revision = worker.revision
    for rev, text in [(revision - 1, 'stale'), (revision, 'hello'),
                      (revision, ''), (revision, 'hello')]:
        worker._publish_dialogue_subtitle(SubtitleFrame(rev, 1, '', text))
    assert [frame.text for frame in frames] == ['hello', '', 'hello']
    assert texts == ['hello']
    worker.configure(replace(runtime_settings, interval_ms=600))
    worker._publish_dialogue_subtitle(SubtitleFrame(worker.revision, 2, '', 'hello'))
    assert texts == ['hello', 'hello']
    worker._is_running = False


def test_rejected_status_does_not_poison_next_current_publication(qtbot, runtime_settings):
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    worker.configure(runtime_settings)
    statuses = []
    worker.translation_status_updated.connect(statuses.append)
    worker._publish_translation_status(runtime_settings, worker.revision)
    assert statuses == []
    worker._is_running = True
    worker._publish_translation_status(runtime_settings, worker.revision)
    assert len(statuses) == 1
    worker._is_running = False


def test_rejected_subtitle_does_not_suppress_same_current_text(qtbot):
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    texts = []
    worker.text_translated.connect(texts.append)
    worker._is_running = True
    worker._publish_dialogue_subtitle(SubtitleFrame(worker.revision - 1, 1, '', 'hello'))
    worker._publish_dialogue_subtitle(SubtitleFrame(worker.revision, 1, '', 'hello'))
    assert texts == ['hello']
    worker._is_running = False


def test_subtitle_listener_reconfigure_cannot_fill_new_revision_cache(qtbot, runtime_settings):
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    worker._is_running = True
    texts = []
    worker.text_translated.connect(texts.append)
    worker.subtitle_updated.connect(lambda frame: worker.configure(runtime_settings))
    worker._publish_dialogue_subtitle(SubtitleFrame(worker.revision, 1, '', 'hello'))
    worker.subtitle_updated.disconnect()
    assert texts == []
    worker._publish_dialogue_subtitle(SubtitleFrame(worker.revision, 2, '', 'hello'))
    assert texts == ['hello']
    worker._is_running = False


def test_google_and_ai_status_synthesis_and_dedup(qtbot, monkeypatch, runtime_settings):
    worker = TranslationWorker(config.State(), config.DEFAULT_REGION)
    settings = replace(runtime_settings, provider=replace(runtime_settings.provider, name='Google Translate'))
    worker.configure(settings)
    worker._is_running = True
    statuses = []
    worker.translation_status_updated.connect(statuses.append)
    for recovery, expected in [('ready', ('active', None)), ('retry_wait', ('retry_wait', 20.)),
                               ('paused', ('paused', None))]:
        monkeypatch.setattr(worker._google_recovery, 'snapshot',
            lambda **kw: GoogleRecoverySnapshot(1, recovery, 2, 20., None))
        worker._publish_translation_status(settings, worker.revision)
        worker._publish_translation_status(settings, worker.revision)
        assert (statuses[-1].phase, statuses[-1].retry_at_s) == expected
        assert statuses[-1].retries_issued == 2
    assert len(statuses) == 3
    worker._publish_translation_status(runtime_settings, worker.revision)
    assert statuses[-1] == TranslationStatus(runtime_settings.provider.name, worker.revision,
        worker.translation_session_id, 'active')
    worker._is_running = False
