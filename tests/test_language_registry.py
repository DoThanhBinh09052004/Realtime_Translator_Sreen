import pytest


def test_registry_preserves_distinct_config_ocr_and_translation_roles():
    from core.languages import source_languages, target_languages, language_by_id, language_by_config_name, language_by_ocr_code
    assert [(x.id, x.config_name, x.ocr_code, x.google_code, x.bundled) for x in source_languages()] == [
        ('en', 'English', 'en', 'en', True), ('ja', 'Japanese', 'japan', 'ja', True),
        ('zh-Hans', 'Chinese', 'ch', 'zh-CN', False), ('ko', 'Korean', 'korean', 'ko', False)]
    assert [x.config_name for x in target_languages()] == ['Vietnamese', 'English']
    assert language_by_id('ko').component_ids == ('det-ml', 'rec-ko', 'cls')
    assert language_by_config_name('Chinese').id == 'zh-Hans'
    assert language_by_ocr_code('japan').id == 'ja'
    for lookup in (language_by_id, language_by_config_name, language_by_ocr_code):
        with pytest.raises(ValueError):
            lookup('unknown')
