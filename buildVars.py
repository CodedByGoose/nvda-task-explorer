# -*- coding: UTF-8 -*-
# Build customizations for the Task Explorer NVDA add-on.
# Written by CodedByGoose, with the help of Quill (Claude agent).


def _(arg):
    """Identity function so gettext can harvest strings from this file at build time."""
    return arg


# Add-on information. Used to generate addon/manifest.ini at build time.
addon_info = {
    # Internal add-on name. Must be unique and is used as the add-on's folder name.
    "addon_name": "taskExplorer",
    # Add-on summary, usually the user visible name of the add-on.
    # Translators: Summary for this add-on to be shown on installation and add-on information.
    "addon_summary": _("Task Explorer"),
    # Add-on description.
    # Translators: Long description to be shown for this add-on on add-on information from add-ons manager.
    "addon_description": _(
        """Shows which applications are using the most CPU, in a fast, fully keyboard
driven dialog designed to be explored with a screen reader.

Applications are grouped so that a browser's many helper processes appear as a
single row you can expand. You can sort by CPU, memory or name, and end a task
directly from the list. Spoken shortcuts announce the busiest applications
without opening any window."""
    ),
    "addon_version": "1.0.1",
    # Translators: The changelog shown on the add-on's information page.
    "addon_changelog": _(
        """Version 1.0.1

Tested with NVDA 2026.2. A single build now covers NVDA 2025.1 through 2026.2.

Version 1.0

First release."""
    ),
    "addon_author": "CodedByGoose <codedbygoose@gmail.com>",
    "addon_url": "https://github.com/CodedByGoose/nvda-task-explorer",
    "addon_sourceURL": "https://github.com/CodedByGoose/nvda-task-explorer",
    "addon_docFileName": "readme.html",
    # Minimum NVDA version supported.
    "addon_minimumNVDAVersion": "2025.1",
    # Last NVDA version tested against.
    "addon_lastTestedNVDAVersion": "2026.2",
    # Add-on update channel: None for stable, "dev" for development releases.
    "addon_updateChannel": None,
    "addon_license": "GPL v2",
    "addon_licenseURL": "https://www.gnu.org/licenses/old-licenses/gpl-2.0.html",
}

# Define the python files that are the sources of your add-on.
pythonSources = ["addon/globalPlugins/taskExplorer/*.py"]

# Files that contain strings for translation.
i18nSources = pythonSources + ["buildVars.py"]

# Files that will be ignored when building the add-on.
excludedFiles = []

# Base language of the add-on's source code.
baseLanguage = "en"

# Markdown extensions for add-on documentation.
markdownExtensions = []

# Custom braille translation tables.
brailleTables = {}

# Custom speech symbol dictionaries.
symbolDictionaries = {}
