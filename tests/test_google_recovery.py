from dataclasses import replace
from threading import Thread
from core.contracts import TranslationResult, EngineError


def failure(code='network', delay=None, retryable=True):
    return TranslationResult(error=EngineError(code,'failure',retryable,delay))


def test_four_consecutive_failures_pause_globally():
    from core.google_recovery import GoogleRecoveryGate
    g = GoogleRecoveryGate()
    generation = g.snapshot(now_s=0).generation
    for now, due in [(0,1),(1,3),(3,7),(7,7)]:
        g.record_result(failure(),generation=generation,now_s=now)
        if now != 7:
            assert g.snapshot(now_s=now).not_before_s == due
            assert not g.can_dispatch(now_s=due-.01)
            assert g.can_dispatch(now_s=due)
    assert g.snapshot(now_s=10000).phase == 'paused'
    assert not g.can_dispatch(now_s=10000)


def test_cache_and_input_do_not_heal_but_network_success_resets_budget():
    from core.google_recovery import GoogleRecoveryGate
    g = GoogleRecoveryGate()
    generation = g.snapshot(now_s=0).generation
    g.record_result(failure(),generation=generation,now_s=0)
    for result in (TranslationResult('cached',from_cache=True), failure('invalid_input',retryable=False)):
        g.record_result(result,generation=generation,now_s=1)
        assert g.snapshot(now_s=1).retries_issued == 1
    g.record_result(TranslationResult('fresh'),generation=generation,now_s=1)
    assert g.snapshot(now_s=1).retries_issued == 0


def test_rate_limit_deadline_survives_pause_retry_and_new_session():
    from core.google_recovery import GoogleRecoveryGate
    for header, due in [(None,30),(12,12),(90,90)]:
        g = GoogleRecoveryGate()
        generation = g.snapshot(now_s=0).generation
        g.record_result(failure('rate_limit',header),generation=generation,now_s=0)
        assert g.snapshot(now_s=0).not_before_s == due
    g = GoogleRecoveryGate()
    generation = g.snapshot(now_s=0).generation
    for now in (0,30,60,90):
        g.record_result(failure('rate_limit'),generation=generation,now_s=now)
    assert g.snapshot(now_s=90).phase == 'paused'
    next_generation = g.manual_retry(now_s=91)
    assert next_generation != generation
    assert g.manual_retry(now_s=91) == next_generation
    assert not g.can_dispatch(now_s=119.99)
    assert g.can_dispatch(now_s=120)
    g.record_result(failure('invalid_response',retryable=False),generation=next_generation,now_s=92)
    assert g.snapshot(now_s=92).phase == 'paused'
    g.begin_session(now_s=93)
    assert g.snapshot(now_s=93).phase == 'retry_wait'
    assert not g.can_dispatch(now_s=119)


def test_old_generation_and_concurrent_snapshots_are_safe():
    from core.google_recovery import GoogleRecoveryGate
    g = GoogleRecoveryGate()
    old = g.snapshot(now_s=0).generation
    g.invalidate_requests()
    g.record_result(failure('invalid_response',retryable=False),generation=old,now_s=1)
    assert g.can_dispatch(now_s=1)
    errors = []
    def read():
        try:
            for _ in range(200):
                snap = g.snapshot(now_s=5)
                assert 0 <= snap.retries_issued <= 3
        except Exception as e: errors.append(e)
    t=Thread(target=read); t.start()
    for _ in range(200): g.begin_session(now_s=5)
    t.join()
    assert not errors
