def test_google_subtitle_overlay_rejects_queued_old_frame(qtbot):
    from core.contracts import SubtitleFrame
    from ui.overlay import Overlay
    o=Overlay(); qtbot.addWidget(o)
    o.set_mode('subtitle',2)
    o.update_subtitle(SubtitleFrame(2,3,'new','New'))
    o.update_subtitle(SubtitleFrame(1,4,'old','Old'))
    o.update_subtitle(SubtitleFrame(2,2,'old','Old'))
    assert o.text()=='New'
    o.update_subtitle(SubtitleFrame(2,4,'',''))
    assert o._last_subtitle_candidate_id==4
    o.set_mode('blocks',3)
    o.update_subtitle(SubtitleFrame(3,5,'wrong','Wrong'))
    assert not o.isVisible()


def test_invalidation_clears_label_before_queued_refresh(qtbot):
    from ui.overlay import Overlay
    o=Overlay(); qtbot.addWidget(o)
    o.update_text('old provider')
    o.set_mode('subtitle',2)
    o.refresh()
    assert not o.isVisible() and not o.text()
