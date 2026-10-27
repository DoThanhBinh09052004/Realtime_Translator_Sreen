import main


def test_shutdown_waits_for_translation_and_pack_worker_in_either_order():
    for order in (('translation', 'language_packs'), ('language_packs', 'translation')):
        ready = []
        barrier = main.ShutdownBarrier(lambda: ready.append(True))
        assert barrier.begin() is True
        barrier.finish(order[0])
        assert ready == []
        barrier.finish(order[1])
        assert ready == [True]
        barrier.finish(order[1])
        assert barrier.begin() is False
        assert ready == [True]


def test_stop_signal_before_quit_cannot_finish_a_later_shutdown():
    ready = []
    barrier = main.ShutdownBarrier(lambda: ready.append(True))
    barrier.finish('translation')
    barrier.begin()
    barrier.finish('language_packs')
    assert ready == []
    barrier.finish('translation')
    assert ready == [True]
