# -*- coding: UTF-8 -*-
"""The Resource Manager dialog.

A single column list box was chosen over a multi column list control on purpose.
Each row is composed into one sentence, so a single arrow key press tells you
everything about an application without moving across columns.

Written by CodedByGoose, with the help of Quill (Claude agent).
"""

import threading
import time

import gui
import psutil
import ui
import wx
from logHandler import log

import addonHandler

from . import formatting, rowmodel, settings
from .rowmodel import SORT_KEYS, buildRows

addonHandler.initTranslation()

#: How long the list holds still after a key press, in "pause while I am moving
#: through the list" mode.
FREEZE_SECONDS = 2.0

#: How long to give a process to close politely before offering to force it.
GRACEFUL_TIMEOUT_SECONDS = 4.0

#: alt plus a number picks a sort order, indexing into rowmodel.SORT_KEYS.
#: The number row and the numeric keypad both work.
SORT_SHORTCUT_KEYS = {
    ord("1"): 0,
    ord("2"): 1,
    ord("3"): 2,
    wx.WXK_NUMPAD1: 0,
    wx.WXK_NUMPAD2: 1,
    wx.WXK_NUMPAD3: 2,
}


class ResourceManagerDialog(wx.Dialog):
    """Shows running applications ordered by how much they are using."""

    _instance = None

    @classmethod
    def open(cls, sampler):
        """Show the dialog, or bring the existing one back to the front."""
        if cls._instance is not None:
            try:
                cls._instance.Raise()
                cls._instance.SetFocus()
                return cls._instance
            except RuntimeError:
                # The window was destroyed without us noticing.
                cls._instance = None
        gui.mainFrame.prePopup()
        try:
            dialog = cls(gui.mainFrame, sampler)
            dialog.Show()
        finally:
            gui.mainFrame.postPopup()
        return dialog

    def __init__(self, parent, sampler):
        # Translators: The title of the Resource Manager dialog.
        super().__init__(parent, title=_("Resource Manager"))
        ResourceManagerDialog._instance = self
        self._sampler = sampler
        self._expandedKeys = set()
        self._rows = []
        self._lastNavigation = 0.0
        self._sortKey = rowmodel.SORT_CPU

        self._buildUi()
        self._refresh(force=True)

        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._onTimer, self._timer)
        self._timer.Start(max(settings.getSetting("refreshInterval"), 1) * 1000)

        self.Bind(wx.EVT_CLOSE, self._onClose)
        self.Bind(wx.EVT_CHAR_HOOK, self._onCharHook)

        self.list.SetFocus()
        if self.list.GetCount():
            self.list.SetSelection(0)
        # Nothing is announced here on purpose. Any message spoken while the
        # dialog is being built is immediately cancelled by NVDA's own focus
        # announcement for the dialog and the list, and delaying it instead
        # would cut off whichever list item the user had already arrowed to.
        # Overall totals are on control+T, spoken only when asked for.

    # --- Construction ---------------------------------------------------------

    def _buildUi(self):
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        contentSizer = gui.guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)

        # Order must match rowmodel.SORT_KEYS, and the alt+number shortcuts.
        self.sortChoices = [
            # Translators: A sort order for the application list.
            _("Processor use"),
            # Translators: A sort order for the application list.
            _("Memory use"),
            # Translators: A sort order for the application list.
            _("Name"),
        ]
        # Translators: The label of the combo box choosing how the list is ordered.
        self.sortCombo = contentSizer.addLabeledControl(_("&Sort by:"), wx.Choice, choices=self.sortChoices)
        self.sortCombo.SetSelection(0)
        self.sortCombo.Bind(wx.EVT_CHOICE, self._onSortChanged)

        # Translators: The label of the list of running applications.
        self.list = contentSizer.addLabeledControl(
            _("&Applications:"),
            wx.ListBox,
            style=wx.LB_SINGLE,
            size=(680, 380),
        )
        self.list.Bind(wx.EVT_LISTBOX, self._onSelectionChanged)
        self.list.Bind(wx.EVT_LISTBOX_DCLICK, self._onToggleExpand)

        buttonHelper = gui.guiHelper.ButtonHelper(wx.HORIZONTAL)
        # Translators: The label of a button that updates the list immediately.
        self.refreshButton = buttonHelper.addButton(self, label=_("&Refresh"))
        self.refreshButton.Bind(wx.EVT_BUTTON, self._onRefreshButton)
        # Translators: The label of a button that closes the selected application.
        self.endTaskButton = buttonHelper.addButton(self, label=_("&End task"))
        self.endTaskButton.Bind(wx.EVT_BUTTON, self._onEndTask)
        # Translators: The label of a button that closes the dialog.
        self.closeButton = buttonHelper.addButton(self, label=_("&Close"))
        self.closeButton.Bind(wx.EVT_BUTTON, lambda evt: self.Close())
        contentSizer.addItem(buttonHelper.sizer)

        mainSizer.Add(contentSizer.sizer, border=gui.guiHelper.BORDER_FOR_DIALOGS, flag=wx.ALL | wx.EXPAND)
        mainSizer.Fit(self)
        self.SetSizer(mainSizer)
        self.CentreOnScreen()
        self.SetEscapeId(wx.ID_CANCEL)

    # --- Refreshing -----------------------------------------------------------

    def _shouldHoldStill(self):
        """True when the user is moving about and the list must not shift."""
        if settings.getSetting("refreshMode") != settings.REFRESH_FREEZE_WHILE_NAVIGATING:
            return False
        return (time.monotonic() - self._lastNavigation) < FREEZE_SECONDS

    def _onTimer(self, evt):
        if self._shouldHoldStill():
            return
        self._refresh()

    def _onRefreshButton(self, evt):
        self._refresh(force=True)
        # Translators: Spoken after the list has been updated on request.
        ui.message(_("Updated"))

    def _refresh(self, force=False):
        snapshot = self._sampler.getSnapshot()
        newRows = buildRows(snapshot.apps, self._expandedKeys, self._sortKey)

        oldKeys = [row.key for row in self._rows]
        newKeys = [row.key for row in newRows]

        if not force and oldKeys == newKeys:
            # Same applications in the same order, so only the numbers moved.
            # Rewriting individual strings avoids the selection churn that a
            # full rebuild causes, which a screen reader would announce.
            self._updateChangedLabels(newRows)
            self._rows = newRows
            return

        selectedKey = self._selectedKey()
        self._rows = newRows
        self.list.Set([row.label for row in newRows])
        self._restoreSelection(selectedKey)

    def _updateChangedLabels(self, newRows):
        # The row the user is sitting on is left alone while the list has focus.
        # Rewriting it would make the screen reader announce it again every time
        # the numbers twitch, which makes the list impossible to read.
        protectedIndex = self.list.GetSelection() if self.list.HasFocus() else wx.NOT_FOUND
        for index, row in enumerate(newRows):
            if index == protectedIndex:
                continue
            if index < len(self._rows) and self._rows[index].label == row.label:
                continue
            self.list.SetString(index, row.label)

    def _selectedKey(self):
        index = self.list.GetSelection()
        if index == wx.NOT_FOUND or index >= len(self._rows):
            return None
        return self._rows[index].key

    def _restoreSelection(self, key, fallbackIndex=0):
        """Reselect the same row by identity, not by position.

        Applications reorder as their usage changes, so an index would silently
        move the user onto a different application.
        """
        if not self._rows:
            return
        if key is not None:
            for index, row in enumerate(self._rows):
                if row.key == key:
                    self.list.SetSelection(index)
                    return
        self.list.SetSelection(min(max(fallbackIndex, 0), len(self._rows) - 1))

    # --- Interaction ----------------------------------------------------------

    def _onSelectionChanged(self, evt):
        self._lastNavigation = time.monotonic()
        evt.Skip()

    def _onSortChanged(self, evt):
        # NVDA already announces the combo box's new value, so saying it again
        # here would only repeat what the user just heard.
        self._applySort(self.sortCombo.GetSelection(), announce=False)

    def _applySort(self, index, announce=True):
        """Reorder the list, keeping the combo box and shortcuts in step."""
        if not 0 <= index < len(SORT_KEYS):
            return
        self.sortCombo.SetSelection(index)
        self._sortKey = SORT_KEYS[index]
        self._refresh(force=True)
        if self._rows:
            self.list.SetSelection(0)
        if announce:
            # Translators: Spoken when the list order is changed by a shortcut.
            ui.message(_("Sorted by {order}").format(order=self.sortChoices[index]))

    def _onCharHook(self, evt):
        key = evt.GetKeyCode()
        if self.list.HasFocus():
            self._lastNavigation = time.monotonic()
            if key == wx.WXK_RIGHT:
                self._setExpanded(True)
                return
            if key == wx.WXK_LEFT:
                self._setExpanded(False)
                return
            if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
                self._onToggleExpand(evt)
                return
        if key == wx.WXK_F5:
            self._onRefreshButton(evt)
            return
        if evt.AltDown():
            if key == ord("T"):
                # Spoken only on request. Announcing totals as the dialog opens
                # does not work: NVDA's focus announcement cancels it every time.
                ui.message(formatting.formatTotals(self._sampler.getSnapshot()))
                return
            sortIndex = SORT_SHORTCUT_KEYS.get(key)
            if sortIndex is not None:
                self._applySort(sortIndex)
                return
        if key == wx.WXK_ESCAPE:
            # The dialog has no Cancel button, so wx would not close it for us.
            self.Close()
            return
        evt.Skip()

    def _currentRow(self):
        index = self.list.GetSelection()
        if index == wx.NOT_FOUND or index >= len(self._rows):
            return None
        return self._rows[index]

    def _onToggleExpand(self, evt):
        row = self._currentRow()
        if row is None:
            return
        self._setExpanded(row.app.key not in self._expandedKeys)

    def _setExpanded(self, expand):
        row = self._currentRow()
        if row is None:
            return
        app = row.app
        if not row.isApp:
            # Left arrow on a child jumps back to its application.
            if not expand:
                self._expandedKeys.discard(app.key)
                self._refresh(force=True)
                self._restoreSelection(rowmodel.appRowKey(app))
                # Translators: Spoken when an application's processes are hidden again.
                ui.message(_("collapsed"))
            return
        if app.processCount <= 1:
            return
        if expand:
            if app.key in self._expandedKeys:
                return
            self._expandedKeys.add(app.key)
            # Translators: Spoken when an application's individual processes are shown.
            message = _("expanded, {count} processes").format(count=app.processCount)
        else:
            if app.key not in self._expandedKeys:
                return
            self._expandedKeys.discard(app.key)
            # Translators: Spoken when an application's processes are hidden again.
            message = _("collapsed")
        self._refresh(force=True)
        self._restoreSelection(rowmodel.appRowKey(app))
        ui.message(message)

    # --- Ending tasks ---------------------------------------------------------

    def _onEndTask(self, evt):
        row = self._currentRow()
        if row is None:
            # Translators: Spoken when End task is used with nothing selected.
            ui.message(_("Nothing is selected"))
            return

        if row.isApp:
            targets = list(row.app.pids)
            name = row.app.displayName
            names = [p.name.lower() for p in row.app.processes]
            isProtected = row.app.isProtected
        else:
            targets = [row.process.pid]
            name = row.process.displayName
            names = [row.process.name.lower()]
            # Judge the individual process, not the whole group it belongs to.
            isProtected = row.process.isProtected

        if "nvda.exe" in names:
            gui.messageBox(
                # Translators: Shown when the user tries to end NVDA itself.
                _(
                    "Resource Manager will not end NVDA, because doing so would leave you "
                    "with no speech and no way to get it back. Exit NVDA from its own menu "
                    "if that is what you want."
                ),
                # Translators: The title of a message refusing to end a process.
                _("Cannot end this task"),
                wx.OK | wx.ICON_ERROR,
                self,
            )
            return

        if isProtected:
            if (
                gui.messageBox(
                    # Translators: A warning shown before ending a critical Windows process.
                    _(
                        "{name} is a critical Windows process. Ending it will very likely "
                        "make Windows unstable or restart your computer without warning, and "
                        "you will lose unsaved work.\n\n"
                        "Are you certain you want to continue?"
                    ).format(name=name),
                    # Translators: The title of a warning about ending a critical process.
                    _("Critical system process"),
                    wx.YES | wx.NO | wx.NO_DEFAULT | wx.ICON_WARNING,
                    self,
                )
                != wx.YES
            ):
                return

        if len(targets) > 1:
            # Translators: Confirmation before ending an application that has several processes.
            question = _(
                "End {name}?\n\nThis will close {count} processes. Any unsaved work in that "
                "application will be lost."
            ).format(name=name, count=len(targets))
        else:
            # Translators: Confirmation before ending a single process.
            question = _("End {name}?\n\nAny unsaved work in it will be lost.").format(name=name)

        if (
            gui.messageBox(
                question,
                # Translators: The title of the confirmation shown before ending a task.
                _("End task"),
                wx.YES | wx.NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
                self,
            )
            != wx.YES
        ):
            return

        self._terminate(targets, name)

    def _terminate(self, pids, name):
        """Ask each process to close, then follow up on any that refuse."""
        processes = []
        denied = 0
        for pid in pids:
            try:
                process = psutil.Process(pid)
                process.terminate()
                processes.append(process)
            except psutil.NoSuchProcess:
                continue
            except psutil.AccessDenied:
                denied += 1
            except Exception:
                log.debugWarning(f"Resource Manager: could not end process {pid}", exc_info=True)
                denied += 1

        if denied and not processes:
            ui.message(
                # Translators: Spoken when the user lacks permission to end an application.
                _(
                    "Could not end {name}. It is running with higher privileges than NVDA, "
                    "so Windows will not let this add-on close it."
                ).format(name=name)
            )
            return

        # Translators: Spoken immediately after asking an application to close.
        ui.message(_("Asked {name} to close").format(name=name))
        self._refresh(force=True)

        # Waiting happens off the main thread so speech and the dialog stay responsive.
        threading.Thread(
            target=self._awaitTermination,
            args=(processes, name),
            name="resourceManagerTerminate",
            daemon=True,
        ).start()

    def _awaitTermination(self, processes, name):
        try:
            _gone, alive = psutil.wait_procs(processes, timeout=GRACEFUL_TIMEOUT_SECONDS)
        except Exception:
            log.debugWarning("Resource Manager: waiting for termination failed", exc_info=True)
            return
        if alive:
            wx.CallAfter(self._offerForceKill, alive, name)
        else:
            wx.CallAfter(self._afterTermination, name)

    def _afterTermination(self, name):
        if not self:
            return
        # Translators: Spoken once an application has actually closed.
        ui.message(_("{name} has closed").format(name=name))
        self._refresh(force=True)

    def _offerForceKill(self, processes, name):
        if not self:
            return
        if (
            gui.messageBox(
                # Translators: Offered when an application ignored a polite request to close.
                _(
                    "{name} has not closed. {count} of its processes are still running.\n\n"
                    "Force them to close? This is immediate and unsaved work will definitely "
                    "be lost."
                ).format(name=name, count=len(processes)),
                # Translators: The title of the dialog offering to force an application to close.
                _("Force {name} to close?").format(name=name),
                wx.YES | wx.NO | wx.NO_DEFAULT | wx.ICON_WARNING,
                self,
            )
            != wx.YES
        ):
            return
        failed = 0
        for process in processes:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                continue
            except Exception:
                failed += 1
        if failed:
            # Translators: Spoken when forcing an application to close did not work.
            ui.message(_("Could not force {name} to close").format(name=name))
        else:
            # Translators: Spoken after an application has been forced to close.
            ui.message(_("Forced {name} to close").format(name=name))
        self._refresh(force=True)

    # --- Teardown -------------------------------------------------------------

    def _onClose(self, evt):
        if self._timer.IsRunning():
            self._timer.Stop()
        ResourceManagerDialog._instance = None
        self.Destroy()
