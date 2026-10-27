"""Language identities shared by OCR, translation, configuration and UI."""
from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageDefinition:
    id: str
    config_name: str
    ocr_code: str | None
    google_code: str
    source_enabled: bool
    target_enabled: bool
    bundled: bool
    component_ids: tuple[str, ...]
    dictionary_resource: str | None


_LANGUAGES = (
    LanguageDefinition('en', 'English', 'en', 'en', True, True, True, ('det-en', 'rec-en', 'cls'), 'dict-en'),
    LanguageDefinition('ja', 'Japanese', 'japan', 'ja', True, False, True, ('det-ml', 'rec-ja', 'cls'), 'dict-ja'),
    LanguageDefinition('zh-Hans', 'Chinese', 'ch', 'zh-CN', True, False, False, ('det-ch', 'rec-ch', 'cls'), 'dict-ch'),
    LanguageDefinition('ko', 'Korean', 'korean', 'ko', True, False, False, ('det-ml', 'rec-ko', 'cls'), 'dict-ko'),
    LanguageDefinition('vi', 'Vietnamese', None, 'vi', False, True, False, (), None),
)


def source_languages() -> tuple[LanguageDefinition, ...]:
    return tuple(x for x in _LANGUAGES if x.source_enabled)


def target_languages() -> tuple[LanguageDefinition, ...]:
    return (language_by_id('vi'), language_by_id('en'))


def _lookup(field: str, value: str) -> LanguageDefinition:
    for language in _LANGUAGES:
        if value is not None and getattr(language, field) == value:
            return language
    raise ValueError('Unknown language')


def language_by_id(id: str) -> LanguageDefinition:
    return _lookup('id', id)


def language_by_config_name(name: str) -> LanguageDefinition:
    return _lookup('config_name', name)


def language_by_ocr_code(code: str) -> LanguageDefinition:
    return _lookup('ocr_code', code)
