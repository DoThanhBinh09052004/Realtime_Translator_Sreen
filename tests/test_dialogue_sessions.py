from core.blocks.models import TextBlock, Rect


def setup_subtitle(settings, factory):
    from core.dialogue.subtitle_session import SubtitleDialogueSession
    s=SubtitleDialogueSession();s.reset(1,settings)
    s.observe('Hello',now_s=0);s.observe('Hello',now_s=.25)
    j,=s.translation_jobs(now_s=.5)
    s.mark_dispatched(j,now_s=.5);s.apply_result(factory(j),now_s=.6)
    return s,j


def test_subtitle_empty_confirmation_and_three_second_tail(runtime_settings,dialogue_result):
    s,j=setup_subtitle(runtime_settings,dialogue_result)
    s.observe('',now_s=1);assert s.active_turns
    s.observe('',now_s=2);assert not s.active_turns
    s.observe('',now_s=3)
    s.tick(now_s=4.999);assert s.current_frame().text=='Xin chào'
    s.tick(now_s=5);assert s.current_frame().text==''
    assert not s.apply_result(dialogue_result(j,'old'),now_s=5.1)


def test_reappearing_same_text_is_new_turn(runtime_settings,dialogue_result):
    s,j=setup_subtitle(runtime_settings,dialogue_result)
    s.observe('',now_s=1);s.observe('',now_s=1.5)
    s.observe('Hello',now_s=2);s.observe('Hello',now_s=2.25)
    new,=s.translation_jobs(now_s=2.5)
    assert new.turn_id!=j.turn_id
    assert not s.apply_result(dialogue_result(j),now_s=2.5)
    s.mark_dispatched(new,now_s=2.5)
    assert s.apply_result(dialogue_result(new,'new'),now_s=2.6)
    assert s.current_frame().text=='new'


def test_freshness_and_new_observation(runtime_settings,dialogue_result):
    s,j=setup_subtitle(runtime_settings,dialogue_result)
    s.tick(now_s=6.25);assert s.current_frame().text==''
    assert s.active_turns
    s.observe('Hello',now_s=6.5);assert s.current_frame().text=='Xin chào'


def test_append_multiple_sentences_never_clears(runtime_settings,dialogue_result):
    s,j=setup_subtitle(runtime_settings,dialogue_result)
    s.observe('Hello world. Next sentence.',now_s=1)
    assert s.current_frame().text=='Xin chào'
    assert s.active_turns==frozenset({(1,0,j.turn_id)})


def test_oversized_subtitle_reports_once(runtime_settings):
    from core.dialogue.subtitle_session import SubtitleDialogueSession
    s=SubtitleDialogueSession();s.reset(1,runtime_settings)
    s.observe('x'*2001,now_s=0);s.observe('x'*2001,now_s=1)
    assert not s.translation_jobs(now_s=2)
    assert [e.code for e in s.drain_errors()]==['invalid_input']
    assert not s.drain_errors()


def test_missing_one_block_keeps_other_and_resets_counter(runtime_settings,capture_geometry,dialogue_result):
    from core.blocks.session import BlockSession
    s=BlockSession()
    a=TextBlock(0,'A',Rect(10,10,100,20));b=TextBlock(1,'B',Rect(400,10,100,20))
    def obs(blocks,t):
        s.observe(blocks,settings=runtime_settings,revision=1,frame_id=int(t*100),geometry=capture_geometry,now_s=t)
    obs((a,b),0);obs((a,b),.5)
    for j in s.translation_jobs(now_s=.5):
        s.mark_dispatched(j,now_s=.5);s.apply_result(dialogue_result(j),now_s=.6)
    obs((b,),1);obs((a,b),1.2);obs((b,),1.4)
    assert len(s.current_frame().blocks)==2
    obs((b,),1.6)
    assert [v.source_text for v in s.current_frame().blocks]==['B']


def test_block_freshness_and_geometry_during_read_hold(runtime_settings,capture_geometry,dialogue_result):
    from core.blocks.session import BlockSession
    s=BlockSession()
    def obs(text,x,t):
        s.observe((TextBlock(0,text,Rect(x,10,100,20)),),settings=runtime_settings,
                  revision=1,frame_id=int(t*100),geometry=capture_geometry,now_s=t)
    obs('Hello',10,0);obs('Hello',10,.5)
    j,=s.translation_jobs(now_s=.5);s.mark_dispatched(j,now_s=.5);s.apply_result(dialogue_result(j),now_s=.6)
    obs('Hello world',40,.7)
    assert s.current_frame().blocks[0].source_rect.x==40
    s.tick(now_s=3.7);assert not s.current_frame().blocks
    obs('Hello world',40,4);assert s.current_frame().blocks


def test_two_nearby_blocks_do_not_swap_and_track_bound(runtime_settings,capture_geometry,dialogue_result):
    from core.blocks.session import BlockSession
    s=BlockSession()
    def obs(blocks,t):
        s.observe(blocks,settings=runtime_settings,revision=1,frame_id=int(t*100),geometry=capture_geometry,now_s=t)
    a=TextBlock(0,'left',Rect(10,100,40,10));b=TextBlock(1,'right',Rect(60,100,40,10))
    obs((a,b),0);obs((b,a),.5)
    for j in s.translation_jobs(now_s=.5):
        s.mark_dispatched(j,now_s=.5);s.apply_result(dialogue_result(j,j.source_text),now_s=.6)
    obs((b,a),.75)
    assert [(v.source_rect.x,v.translated_text) for v in s.current_frame().blocks]==[(10,'left'),(60,'right')]
    s.reset()
    many=tuple(TextBlock(i,str(i),Rect(10+(i%8)*80,100+(i//8)*40,40,10)) for i in range(32))
    obs(many,0)
    obs((TextBlock(40,'new',Rect(10,10,40,10)),many[-1]),.5)
    assert len(s.active_turns)<=32
