"""Read-only selectable plain-text translation output monitor."""
from typing import Any
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextOption
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QApplication, QSizePolicy
from ui.icons import set_theme_icon
from ui.styles import TOKENS, set_style, apply_widget_theme, text_style, FONT_FAMILY, TEXT_SIZES


class TranslationOutputWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Placeholder label when no translated text is available
        self.placeholder_lbl = QLabel("Chưa có bản dịch được hiển thị")
        set_style(self.placeholder_lbl, text_style('body') + f"color:{TOKENS['muted']};padding:12px;")
        self.placeholder_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.placeholder_lbl)

        # Content container
        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)

        header_style = text_style('caption')
        edit_style = f"""
            QPlainTextEdit {{
                background-color: transparent;
                color: {TOKENS['text']};
                border: none;
                padding: 4px 0;
                font-family: '{FONT_FAMILY}';
                font-size: {TEXT_SIZES['reading']}px;
                font-weight: 400;
            }}
            QPlainTextEdit:focus {{
                border-color: {TOKENS['focus']};
            }}
        """

        self.source_header = QLabel('Văn bản gốc')
        set_style(self.source_header, header_style)
        header_row = QHBoxLayout()
        header_row.addWidget(self.source_header)
        header_row.addStretch()
        self.copy_btn = QPushButton()
        self.copy_btn.setToolTip('Sao chép bản dịch')
        self.copy_btn.setAccessibleName('Sao chép bản dịch')
        set_theme_icon(self.copy_btn, 'copy', size=16)
        self.copy_btn.clicked.connect(self.copy_translation)
        header_row.addWidget(self.copy_btn)
        content_layout.addLayout(header_row)

        self.source_edit = QPlainTextEdit()
        self.source_edit.document().setDocumentMargin(0)
        self.source_edit.setReadOnly(True)
        self.source_edit.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        set_style(self.source_edit, edit_style)
        self.source_edit.setFixedHeight(54)
        content_layout.addWidget(self.source_edit)

        self.target_header = QLabel('Bản dịch')
        set_style(self.target_header, header_style)
        content_layout.addWidget(self.target_header)

        self.target_edit = QPlainTextEdit()
        self.target_edit.document().setDocumentMargin(0)
        self.target_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.target_edit.setReadOnly(True)
        self.target_edit.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.target_edit.setMinimumHeight(90)
        set_style(self.target_edit, f'QPlainTextEdit {{background:transparent;color:{TOKENS["text"]};border:0;padding:4px 0;font-family:"{FONT_FAMILY}";font-size:{TEXT_SIZES["translation"]}px;font-weight:400;}}')
        content_layout.addWidget(self.target_edit, 1)
        for editor in (self.source_edit, self.target_edit):
            editor.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            editor.setLineWrapMode(QPlainTextEdit.WidgetWidth)
            editor.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)

        layout.addWidget(self.content_widget)
        self.clear()

    def apply_theme(self, theme):
        apply_widget_theme(self, theme)

    def copy_translation(self):
        QApplication.clipboard().setText(self.target_edit.toPlainText())

    def render(self, presentation: Any | None, region_labels: dict[str, str] | None = None) -> None:
        pairs = getattr(presentation, 'pairs', ()) if presentation is not None else ()
        if not pairs:
            self.clear()
            return

        self.placeholder_lbl.hide()
        self.content_widget.show()
        self.copy_btn.setEnabled(True)

        if len(pairs) == 1:
            pair = pairs[0]
            self.source_edit.setPlainText(pair.source_text)
            self.target_edit.setPlainText(pair.translated_text)
        else:
            source_parts: list[str] = []
            target_parts: list[str] = []
            for pair in pairs:
                lbl = None
                if region_labels and pair.region_id:
                    lbl = region_labels.get(pair.region_id, pair.region_id)
                elif pair.region_id:
                    lbl = pair.region_id

                prefix = f"[{lbl}]\n" if lbl else ""
                source_parts.append(f"{prefix}{pair.source_text}")
                target_parts.append(f"{prefix}{pair.translated_text}")

            self.source_edit.setPlainText("\n\n".join(source_parts))
            self.target_edit.setPlainText("\n\n".join(target_parts))

    def is_empty(self) -> bool:
        return self.placeholder_lbl.isVisible() or (not self.source_edit.toPlainText().strip() and not self.target_edit.toPlainText().strip())

    def clear(self) -> None:
        self.copy_btn.setEnabled(False)
        self.source_edit.clear()
        self.target_edit.clear()
        self.placeholder_lbl.show()
        self.content_widget.hide()
