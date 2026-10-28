"""Kindle Highlights Sync, GPL-3.0-or-later."""
try:
    from calibre.customize import InterfaceActionBase
except ImportError:
    InterfaceActionBase = object  # Core tests do not require Calibre.


class KindleHighlightsSync(InterfaceActionBase):
    name = 'Kindle Highlights Sync'
    description = 'Import Kindle annotations and safely synchronize an Obsidian vault'
    author = 'Kindle Highlights Sync contributors'
    version = (0, 1, 0)
    minimum_calibre_version = (9, 17, 0)
    supported_platforms = ['windows', 'linux']
    actual_plugin = 'calibre_plugins.kindle_highlights_sync.action:KindleHighlightsAction'

    def is_customizable(self):
        return True

    def config_widget(self):
        from .config import SettingsWidget
        return SettingsWidget()

    def save_settings(self, widget):
        widget.save()
