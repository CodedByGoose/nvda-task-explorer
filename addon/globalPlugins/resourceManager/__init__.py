# -*- coding: UTF-8 -*-
"""Resource Manager, an NVDA add-on.

Shows which applications are using the most CPU, in a dialog built to be
explored by ear rather than by eye.

Written by CodedByGoose, with the help of Quill (Claude agent).
"""

import globalPluginHandler
import gui
import ui
import wx
from logHandler import log
from scriptHandler import script

import addonHandler

from . import dialog, formatting, sampler, settings

addonHandler.initTranslation()


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    # Translators: The category these commands appear under in NVDA's Input Gestures dialog.
    scriptCategory = _("Resource Manager")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        settings.initialiseConfig()
        gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(settings.ResourceManagerSettingsPanel)

        self.sampler = sampler.Sampler(
            interval=settings.getSetting("refreshInterval"),
            onError=log.debugWarning,
        )
        # Started now rather than when first asked for, so that the first
        # measurement is already waiting when a shortcut is pressed. A pass
        # costs a few milliseconds, so leaving it running is cheap.
        self.sampler.start()

    def terminate(self):
        try:
            existing = dialog.ResourceManagerDialog._instance
            if existing is not None:
                wx.CallAfter(existing.Close)
        except Exception:
            log.debugWarning("Resource Manager: could not close the dialog", exc_info=True)
        try:
            self.sampler.stop()
        except Exception:
            log.debugWarning("Resource Manager: could not stop the sampler", exc_info=True)
        try:
            gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(settings.ResourceManagerSettingsPanel)
        except ValueError:
            pass
        super().terminate()

    def _syncSamplerInterval(self):
        self.sampler.setInterval(settings.getSetting("refreshInterval"))

    def _announceTop(self, byMemory):
        if not self.sampler.isPrimed:
            ui.message(formatting.formatNotReadyMessage())
            return
        apps = self.sampler.getTopApps(
            count=settings.getSetting("topAppCount"),
            key="memory" if byMemory else "cpu",
        )
        ui.message(
            formatting.formatSpokenSummary(
                apps,
                includeMemory=settings.getSetting("includeMemoryInSpokenSummary"),
                byMemory=byMemory,
            )
        )

    @script(
        # Translators: The description of a command, shown in NVDA's Input Gestures dialog.
        description=_("Shows the Resource Manager, listing applications by how much they are using"),
        gesture="kb:NVDA+alt+r",
    )
    def script_showResourceManager(self, gesture):
        self._syncSamplerInterval()
        if not self.sampler.isPrimed:
            ui.message(formatting.formatNotReadyMessage())
            return
        try:
            dialog.ResourceManagerDialog.open(self.sampler)
        except Exception:
            log.error("Resource Manager: the dialog could not be shown", exc_info=True)
            # Translators: Spoken when the dialog fails to open.
            ui.message(_("Resource Manager could not open. See the NVDA log for details."))

    @script(
        # Translators: The description of a command, shown in NVDA's Input Gestures dialog.
        description=_("Announces the applications using the most processor time"),
        speakOnDemand=True,
    )
    def script_announceTopByCpu(self, gesture):
        self._syncSamplerInterval()
        self._announceTop(byMemory=False)

    @script(
        # Translators: The description of a command, shown in NVDA's Input Gestures dialog.
        description=_("Announces the applications using the most memory"),
        speakOnDemand=True,
    )
    def script_announceTopByMemory(self, gesture):
        self._syncSamplerInterval()
        self._announceTop(byMemory=True)

    @script(
        # Translators: The description of a command, shown in NVDA's Input Gestures dialog.
        description=_("Announces total processor and memory use"),
        speakOnDemand=True,
    )
    def script_announceTotalUtilisation(self, gesture):
        self._syncSamplerInterval()
        if not self.sampler.isPrimed:
            ui.message(formatting.formatNotReadyMessage())
            return
        ui.message(formatting.formatTotals(self.sampler.getSnapshot()))
