from core.blocks.models import Rect


def test_columns_and_lines_are_grouped_deterministically(span_factory):
    from core.blocks.grouping import group_spans
    spans = (span_factory('Left one', width=120), span_factory('Left two', y=36, width=120),
             span_factory('Right', x=320), span_factory('• Item', y=90))
    blocks = group_spans(spans, (800, 600))
    assert [(b.source_text, b.source_rect) for b in blocks] == [
        ('Left one Left two', Rect(10, 10, 120, 46)), ('Right', Rect(320, 10, 100, 20)),
        ('• Item', Rect(10, 90, 100, 20))]
    assert group_spans(tuple(reversed(spans)), (800, 600)) == blocks


def test_title_size_and_confidence_boundaries(span_factory):
    from core.blocks.grouping import group_spans
    assert not group_spans((span_factory(confidence=.49),), (800, 600))
    assert len(group_spans((span_factory(confidence=.50),), (800, 600))) == 1
    assert group_spans((span_factory(x=-10, width=30),), (800, 600))[0].source_rect == Rect(0, 10, 20, 20)
    for ratio, count in [(1.2, 1), (1.21, 2)]:
        spans = (span_factory('title', height=20*ratio), span_factory('body', y=40))
        assert len(group_spans(spans, (800, 600))) == count
    assert len(group_spans(tuple(span_factory(str(i)+'.', y=i*50) for i in range(40)), (800, 3000))) == 32


def test_sentence_and_list_boundaries(span_factory):
    from core.blocks.grouping import group_spans
    for first, second in [('Done.', 'next'), ('line', '1. item'), ('line', '• item')]:
        assert len(group_spans((span_factory(first), span_factory(second, y=36)), (800, 600))) == 2


def test_paragraph_with_three_lines_uses_line_height(span_factory):
    from core.blocks.grouping import group_spans
    blocks = group_spans(tuple(span_factory(t, y=10+i*26) for i, t in enumerate(('one', 'two', 'three'))), (800, 600))
    assert [b.source_text for b in blocks] == ['one two three']
