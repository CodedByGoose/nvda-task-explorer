# -*- coding: UTF-8 -*-
"""The Task Explorer dialog.

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

from . import formatting, rowmodel, settings, winprocinfo
from .rowmodel import SORT_KEYS, buildRows

addonHandler.initTranslation()

#: How long the list holds still after a key press, in "pause while I am moving
#: through the list" mode.
FREEZE_SECONDS = 2.0

#: How long to give a process to close politely before offering to force it.
GRACEFUL_TIMEOUT_SECONDS = 4.0

#: How long a typed search stays open. Another letter within this time carries on
#: the same search, so "s", "l" finds Slack. After it, the next letter starts
#: afresh. A little longer than the Windows default, which is unkindly short if
#: you are listening to each row as you go.
TYPE_AHEAD_SECONDS = 1.5

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
        # Translators: The title of the Task Explorer dialog.
        super().__init__(parent, title=_("Task Explorer"))
        ResourceManagerDialog._instance = self
        self._sampler = sampler
        self._expandedKeys = set()
        self._rows = []
        self._lastNavigation = 0.0
        self._sortKey = rowmodel.SORT_CPU
        self._searchText = ""
        self._lastTypedAt = 0.0

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
        # Overall totals are on alt+T, spoken only when asked for.

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
            char = self._typedCharacter(evt)
            if char is not None:
                # Deliberately not passed on to the list box. Its own search only
                # ever looks at the first letter, so leaving it to do the work is
                # what makes "s", "l" jump to the first L rather than to Slack.
                self._typeAhead(char)
                return
            # Any other key ends the search in progress, so the next letter typed
            # starts a new one rather than continuing a half typed word.
            self._searchText = ""
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

    # --- Typing to find a row -------------------------------------------------

    def _typedCharacter(self, evt):
        """The printable character a key press stands for, or None if it is not one."""
        if evt.HasAnyModifiers():
            # alt and control belong to the shortcuts, not to the search.
            return None
        code = evt.GetUnicodeKey()
        if code == wx.WXK_NONE or code < ord(" ") or code == wx.WXK_DELETE:
            return None
        return chr(code).lower()

    def _typeAhead(self, char):
        """Move to the next row on screen matching everything typed so far."""
        now = time.monotonic()
        if now - self._lastTypedAt > TYPE_AHEAD_SECONDS:
            self._searchText = ""
        self._lastTypedAt = now

        if char == " " and not self._searchText:
            # No name begins with a space, and space on its own should sit still.
            return

        selected = self.list.GetSelection()
        if selected == wx.NOT_FOUND:
            selected = -1
        query = self._searchText + char

        index = None
        if self._searchText:
            # The row already found is still a candidate, so typing more of the
            # name it matched narrows the search instead of skipping past it.
            index = rowmodel.findTypeAheadMatch(self._rows, query, selected)
        if index is None and query == char * len(query):
            # A fresh letter, or the same letter pressed again with nothing
            # longer to match: step on to the next row starting with it, which is
            # how lists have always been walked and is worth keeping.
            query = char
            index = rowmodel.findTypeAheadMatch(self._rows, query, selected + 1)

        self._searchText = query
        if index is not None:
            # NVDA announces the row itself as the selection moves, so nothing is
            # spoken here. Nothing is spoken for no match either: silence is the
            # answer every other Windows list gives, and a message on every
            # keystroke would talk over the name being typed.
            self.list.SetSelection(index)

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
                    "Task Explorer will not end NVDA, because doing so would leave you "
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
                "End {name}?\n\nIts {count} processes will be asked to close. You may be "
                "prompted to save your work."
            ).format(name=name, count=len(targets))
        else:
            # Translators: Confirmation before ending a single process.
            question = _(
                "End {name}?\n\nIt will be asked to close, and may prompt you to save your work."
            ).format(name=name)

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
        """Ask the application to close, then follow up if it does not.

        The polite stage posts WM_CLOSE to the application's windows, which is
        what clicking their close button does, so it can run its own shutdown
        and prompt to save. psutil's terminate() is deliberately not used here:
        on Windows it is an alias for kill() and destroys unsaved work outright.
        """
        processes = []
        for pid in pids:
            try:
                processes.append(psutil.Process(pid))
            except psutil.NoSuchProcess:
                continue
            except Exception:
                log.debugWarning(f"Task Explorer: could not open process {pid}", exc_info=True)

        if not processes:
            # Translators: Spoken when the chosen application had already closed.
            ui.message(_("{name} is no longer running").format(name=name))
            self._refresh(force=True)
            return

        asked = winprocinfo.askWindowsToClose([p.pid for p in processes])
        if not asked:
            # Nothing to ask: a background service or a hung window that no
            # longer accepts messages. Forcing is the only remaining option, so
            # say so rather than pretending we tried something gentler.
            self._offerForceKill(processes, name, politeAttemptFailed=True)
            return

        # Translators: Spoken immediately after asking an application to close.
        ui.message(_("Asked {name} to close").format(name=name))
        self._refresh(force=True)

        # Waiting happens off the main thread so speech and the dialog stay responsive.
        threading.Thread(
            target=self._awaitTermination,
            args=(processes, name),
            name="taskExplorerTerminate",
            daemon=True,
        ).start()

    def _awaitTermination(self, processes, name):
        try:
            _gone, alive = psutil.wait_procs(processes, timeout=GRACEFUL_TIMEOUT_SECONDS)
        except Exception:
            log.debugWarning("Task Explorer: waiting for termination failed", exc_info=True)
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

    def _offerForceKill(self, processes, name, politeAttemptFailed=False):
        if not self:
            return
        if politeAttemptFailed:
            # Translators: Offered when an application has no window that could be asked to close.
            question = _(
                "{name} has no window that can be asked to close, so it cannot be closed "
                "politely. This is usual for background services.\n\n"
                "Force it to close? This is immediate and any unsaved work will be lost."
            ).format(name=name)
        else:
            # Translators: Offered when an application ignored a polite request to close.
            question = _(
                "{name} has not closed. {count} of its processes are still running.\n\n"
                "Force them to close? This is immediate and unsaved work will definitely "
                "be lost."
            ).format(name=name, count=len(processes))

        if (
            gui.messageBox(
                question,
                # Translators: The title of the dialog offering to force an application to close.
                _("Force {name} to close?").format(name=name),
                wx.YES | wx.NO | wx.NO_DEFAULT | wx.ICON_WARNING,
                self,
            )
            != wx.YES
        ):
            return

        denied = failed = 0
        for process in processes:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                continue
            except psutil.AccessDenied:
                denied += 1
            except Exception:
                log.debugWarning(f"Task Explorer: could not kill process {process.pid}", exc_info=True)
                failed += 1

        if denied:
            ui.message(
                # Translators: Spoken when the user lacks permission to end an application.
                _(
                    "Could not close {name}. It is running with higher privileges than NVDA, "
                    "so Windows will not let this add-on close it."
                ).format(name=name)
            )
        elif failed:
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
