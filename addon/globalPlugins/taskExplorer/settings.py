# -*- coding: UTF-8 -*-
"""Configuration and the NVDA settings panel for Task Explorer.

The panel is registered into NVDA's own Settings dialog, so it appears in the
category list alongside every other add-on rather than behind a separate menu
item of its own.

Written by CodedByGoose, with the help of Quill (Claude agent).
"""

import config
import gui
import wx
from gui import guiHelper, nvdaControls

import addonHandler

addonHandler.initTranslation()

CONFIG_SECTION = "taskExplorer"

#: Rebuild the list on every timer tick, whatever the user is doing.
REFRESH_ALWAYS = "always"
#: Hold the list still while the user is arrowing through it.
REFRESH_FREEZE_WHILE_NAVIGATING = "freeze"

REFRESH_MODES = (REFRESH_ALWAYS, REFRESH_FREEZE_WHILE_NAVIGATING)

MIN_INTERVAL = 1
MAX_INTERVAL = 30
MIN_TOP_COUNT = 1
MAX_TOP_COUNT = 10

confspec = {
    "refreshMode": f'option("{REFRESH_ALWAYS}", "{REFRESH_FREEZE_WHILE_NAVIGATING}", default="{REFRESH_ALWAYS}")',
    "refreshInterval": f"integer(default=2, min={MIN_INTERVAL}, max={MAX_INTERVAL})",
    "topAppCount": f"integer(default=3, min={MIN_TOP_COUNT}, max={MAX_TOP_COUNT})",
    "includeMemoryInSpokenSummary": "boolean(default=true)",
}


def initialiseConfig():
    """Register our section in NVDA's configuration."""
    config.conf.spec[CONFIG_SECTION] = confspec


def getSetting(key):
    return config.conf[CONFIG_SECTION][key]


class ResourceManagerSettingsPanel(gui.settingsDialogs.SettingsPanel):
    # Translators: The label for the Task Explorer category in NVDA's settings dialog.
    title = _("Task Explorer")

    def makeSettings(self, settingsSizer):
        helper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)

        # Translators: The label for a combo box choosing when the resource list updates.
        refreshModeLabel = _("&Update the list:")
        self.refreshModeChoices = [
            # Translators: A refresh option: the list updates continuously.
            _("Continuously"),
            # Translators: A refresh option: updates pause while the user moves through the list.
            _("Continuously, but pause while I am moving through the list"),
        ]
        self.refreshModeCombo = helper.addLabeledControl(
            refreshModeLabel, wx.Choice, choices=self.refreshModeChoices
        )
        self.refreshModeCombo.SetSelection(REFRESH_MODES.index(getSetting("refreshMode")))

        # Translators: The label for the setting controlling how often the list updates.
        intervalLabel = _("Update &every (seconds)")
        self.intervalEdit = helper.addLabeledControl(
            intervalLabel,
            nvdaControls.SelectOnFocusSpinCtrl,
            min=MIN_INTERVAL,
            max=MAX_INTERVAL,
            initial=getSetting("refreshInterval"),
        )

        # Translators: The label for the setting controlling how many applications the spoken shortcuts announce.
        topCountLabel = _("&Number of applications announced by the spoken shortcuts")
        self.topCountEdit = helper.addLabeledControl(
            topCountLabel,
            nvdaControls.SelectOnFocusSpinCtrl,
            min=MIN_TOP_COUNT,
            max=MAX_TOP_COUNT,
            initial=getSetting("topAppCount"),
        )

        # Translators: The label for a checkbox controlling whether spoken summaries mention memory use.
        self.includeMemoryCheckBox = helper.addItem(
            wx.CheckBox(self, label=_("Include &memory use in spoken summaries"))
        )
        self.includeMemoryCheckBox.SetValue(getSetting("includeMemoryInSpokenSummary"))

    def onSave(self):
        config.conf[CONFIG_SECTION]["refreshMode"] = REFRESH_MODES[self.refreshModeCombo.GetSelection()]
        config.conf[CONFIG_SECTION]["refreshInterval"] = self.intervalEdit.GetValue()
        config.conf[CONFIG_SECTION]["topAppCount"] = self.topCountEdit.GetValue()
        config.conf[CONFIG_SECTION]["includeMemoryInSpokenSummary"] = self.includeMemoryCheckBox.GetValue()
