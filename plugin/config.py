from dataclasses import fields
from pathlib import Path

from calibre.constants import config_dir
from calibre.utils.config import JSONConfig
from qt.core import QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from .core.markdown import MarkdownOptions
from .core.models import SyncDestination, stable_id
from .core.sync import validate_destination

DEFAULTS = {
    'vault': '', 'folder': 'Books/Highlights', 'filename': '{title}', 'manual_folder': '',
    'clippings': True, 'recovery': True, 'preview': True, 'prefer_calibre': True,
    **{f.name: getattr(MarkdownOptions(), f.name) for f in fields(MarkdownOptions)},
}


def preferences():
    prefs = JSONConfig('plugins/kindle_highlights_sync')
    prefs.defaults.update(DEFAULTS)
    return prefs


def settings():
    prefs = preferences()
    return {key: prefs[key] for key in DEFAULTS}


def destination(values):
    return SyncDestination(values['vault'], values['folder'], values['filename'])


def markdown_options(values):
    return MarkdownOptions(**{f.name: values[f.name] for f in fields(MarkdownOptions)})


def state_path(gui):
    library_id = str(gui.current_db.new_api.library_id)
    return Path(config_dir) / 'plugins' / 'kindle_highlights_sync' / stable_id(library_id) / 'state.sqlite'


class SettingsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        values = settings()
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        self.controls = {}
        for key, label, browse in [('vault', 'Obsidian vault', True), ('folder', 'Destination folder', False),
                                   ('filename', 'Filename convention', False), ('manual_folder', 'Fallback import folder', True),
                                   ('date_format', 'Date format (strftime)', False)]:
            edit = QLineEdit(str(values[key]))
            self.controls[key] = edit
            if browse:
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.addWidget(edit)
                button = QPushButton('Browse…')
                button.clicked.connect(lambda checked=False, control=edit: self.browse(control))
                row_layout.addWidget(button)
                form.addRow(label, row)
            else:
                form.addRow(label, edit)
        labels = {'clippings': 'Import My Clippings.txt', 'recovery': 'Recover highlights from KFX/YJR',
                  'preview': 'Preview changes before writing', 'prefer_calibre': 'Prefer Calibre metadata',
                  'blockquotes': 'Use blockquotes', 'numbering': 'Number highlights',
                  'positions': 'Show page, location, and chapter when available', 'dates': 'Show highlight dates',
                  'yaml': 'Add YAML properties to new notes', 'notes': 'Include personal notes'}
        for key, label in labels.items():
            checkbox = QCheckBox(label)
            checkbox.setChecked(bool(values[key]))
            form.addRow(checkbox)
            self.controls[key] = checkbox
        help_label = QLabel('Filename fields: {title}, {author}, {id}.\nBackups and preservation of user edits are always enabled.\nMissing books and excluded books never cause note deletion.\nManage exclusions from the toolbar menu → Manage highlights.')
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        layout.addStretch()

    def browse(self, control):
        path = QFileDialog.getExistingDirectory(self, 'Select directory', control.text())
        if path:
            control.setText(path)

    def values(self):
        return {key: control.isChecked() if isinstance(control, QCheckBox) else control.text().strip()
                for key, control in self.controls.items()}

    def validate(self):
        from calibre.gui2 import error_dialog
        try:
            values = self.values()
            validate_destination(destination(values))
            if not values['clippings'] and not values['recovery']:
                raise ValueError('Enable at least one importer.')
            return True
        except ValueError as error:
            error_dialog(self, 'Invalid settings', str(error), show=True)
            return False

    def save(self):
        prefs = preferences()
        with prefs:
            for key, value in self.values().items():
                prefs[key] = value


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('Kindle Highlights Sync settings')
        self.resize(650, 650)
        layout = QVBoxLayout(self)
        self.widget = SettingsWidget(self)
        layout.addWidget(self.widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        if self.widget.validate():
            self.widget.save()
            self.accept()
