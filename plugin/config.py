from dataclasses import fields
from pathlib import Path

from calibre.constants import config_dir
from calibre.utils.config import JSONConfig
from qt.core import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTextOption, QVBoxLayout, QWidget

from .core.markdown import MarkdownOptions
from .core.models import SyncDestination, stable_id
from .core.sync import validate_destination

DEFAULTS = {
    'vault': '', 'folder': 'Books/Highlights', 'filename': '{title}', 'manual_folder': '', 'author_folders': False,
    'clippings': True, 'recovery': True, 'preview': True, 'prefer_calibre': True,
    **{f.name: getattr(MarkdownOptions(), f.name) for f in fields(MarkdownOptions)},
}

PREFERENCE_HELP = {
    'vault': 'Existing Obsidian vault directory to write book notes into. All exported notes and backups stay inside this vault.',
    'folder': 'Folder inside the vault, for example Books/Highlights. Created when needed. Changing it starts a separate export destination and leaves old notes intact; use a relative path without .. .',
    'filename': 'Name for new book notes, without .md (added automatically). Fields: {title}, {author}, {id}. Example: {author} - {title}. Unsafe filename characters are replaced. Existing notes keep their paths.',
    'manual_folder': 'Copied Kindle source folder used when no device is connected, and the starting folder for Import folder. Leave empty to choose a folder when needed. Sources are read only.',
    'date_format': 'Format for available highlight dates when Show highlight dates is enabled. Examples: %Y-%m-%d → 2026-11-01; %d %B %Y → 01 November 2026; %H:%M adds time. Month names follow the runtime locale. This does not change stored dates.',
    'author_folders': 'Place new notes in an author subfolder beneath the destination folder. Multiple authors share one folder with comma-separated names; missing authors use Unknown author. Existing notes are not moved.',
    'clippings': 'Read highlights and notes from My Clippings.txt during future imports. Does not remove previously imported records. At least one importer must remain enabled.',
    'recovery': 'Recover annotation text from supported DRM-free KFX books and their matching .sdr/YJR sidecars during future imports. Requires both sources; does not extract highlights directly from EPUB or ksdk_annotation_v1.db. Previously imported records remain available.',
    'preview': 'Show proposed note changes, duplicate merges and conflicts before writing. Uncheck books to skip them for this run. Turning this off applies eligible changes immediately; conflict checks and backups remain enabled. Cancelling the preview does not undo the local import.',
    'prefer_calibre': 'Use matched Calibre book metadata, such as title, authors and series, on future imports. Turn off to prefer source metadata while keeping library matching. This does not change highlight text or rewrite existing YAML properties.',
    'blockquotes': 'Render highlight passages and personal-note text as Markdown blockquotes (>). Turn off for ordinary paragraphs. Does not change stored annotation text.',
    'numbering': 'Add numbered Highlight/Note headings in book order. Middle insertions renumber headings; turning this off hides these headings without affecting sorting or stable highlight identities.',
    'positions': 'Show available page, Kindle location and chapter metadata. Unmapped KFX coordinates are explicitly labeled KFX position. Missing information is omitted. Hiding these labels does not change book ordering or the separate chapter-grouping option.',
    'dates': 'Show each annotation’s available creation date using Date format. Missing or unparseable dates are omitted. Does not show export time or change sorting.',
    'yaml': 'Add Obsidian YAML properties above the managed section when creating a note: title, author, book ID, tags, and available series, publication date and identifiers. Existing properties are user-owned: this option neither adds to nor removes them in existing notes.',
    'notes': 'Include standalone personal notes and notes attached to highlights. Turn off to omit these from generated output while retaining them in local state. Edited blocks that would be removed may require conflict review.',
    'compact': 'Put visible page/location/chapter/date metadata on one line separated by · instead of separate lines. Does not shorten highlight passages or enable metadata that is otherwise hidden.',
    'group_chapters': 'Insert chapter headings as chapter names change in book order. Does not rearrange highlights to collect equal chapter names. Missing chapters use Other highlights. Works independently of position labels and numbering.',
}


def preferences():
    prefs = JSONConfig('plugins/kindle_highlights_sync')
    prefs.defaults.update(DEFAULTS)
    return prefs


def settings():
    prefs = preferences()
    return {key: prefs[key] for key in DEFAULTS}


def destination(values):
    return SyncDestination(values['vault'], values['folder'], values['filename'], values['author_folders'])


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
        presets = QComboBox()
        presets.addItems(['Choose a filename preset…', '{title}', '{author} - {title}', '{title} - {author}', '{title} [{id}]'])
        presets.setToolTip('Copy a common pattern into Filename convention, then edit it if needed. Choosing a preset does not rename existing notes. The first entry makes no change.')
        form.addRow('Filename presets', presets)
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
                button.setToolTip('Choose an existing directory for ' + label.lower() + '.')
                button.clicked.connect(lambda checked=False, control=edit: self.browse(control))
                row_layout.addWidget(button)
                form.addRow(label, row)
            else:
                form.addRow(label, edit)
        presets.textActivated.connect(lambda text: self.controls['filename'].setText(text) if text.startswith('{') else None)
        labels = {'author_folders': 'Create a folder for each author',
                  'clippings': 'Import My Clippings.txt', 'recovery': 'Recover highlights from KFX/YJR',
                  'preview': 'Preview changes before writing', 'prefer_calibre': 'Prefer Calibre metadata',
                  'blockquotes': 'Use blockquotes', 'numbering': 'Number highlights',
                  'positions': 'Show page, location, and chapter when available', 'dates': 'Show highlight dates',
                  'yaml': 'Add YAML properties to new notes', 'notes': 'Include personal notes',
                  'compact': 'Compact highlight metadata onto one line', 'group_chapters': 'Group highlights by chapter (in book order)'}
        for key, label in labels.items():
            checkbox = QCheckBox(label)
            checkbox.setChecked(bool(values[key]))
            form.addRow(checkbox)
            self.controls[key] = checkbox
        for key, control in self.controls.items():
            control.setToolTip(PREFERENCE_HELP[key])
            control.setWhatsThis(PREFERENCE_HELP[key])
            control.setAccessibleDescription(PREFERENCE_HELP[key])
        self.path_preview = QPlainTextEdit()
        self.path_preview.setReadOnly(True)
        self.path_preview.setToolTip('Illustrative path relative to the vault using Example Book and Example Author, not a real library record. Updates as naming settings change. Select text to copy it.')
        self.path_preview.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
        self.path_preview.setFixedHeight(self.path_preview.fontMetrics().lineSpacing() * 3 + 12)
        form.addRow(QLabel('Example path'))
        form.addRow(self.path_preview)
        for key in ('filename', 'folder'):
            self.controls[key].textChanged.connect(self.update_preview)
        self.controls['author_folders'].toggled.connect(self.update_preview)
        self.update_preview()
        help_label = QLabel('Hover over any option for help.\nFilename fields: {title}, {author}, {id}.\nExisting notes keep their paths; these path settings apply to new books.\nNew highlights are merged in book order; manual edits are preserved.\nConfirmed duplicate notes are merged and archived in the backup folder.\nManage exclusions from the toolbar menu → Manage highlights.')
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        layout.addStretch()

    def update_preview(self, *args):
        from .core.sync import safe_filename
        try:
            name = safe_filename(self.controls['filename'].text().format(title='Example Book', author='Example Author', id='example-id'))
            folder = self.controls['folder'].text().replace('\\', '/').rstrip('/')
            if self.controls['author_folders'].isChecked():
                folder += '/Example Author'
            self.path_preview.setPlainText(folder + '/' + name + '.md')
        except (ValueError, KeyError, IndexError, AttributeError):
            self.path_preview.setPlainText('Invalid filename pattern')

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
        self.resize(720, 850)
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
