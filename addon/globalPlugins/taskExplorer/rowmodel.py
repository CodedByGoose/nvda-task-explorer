# -*- coding: UTF-8 -*-
"""Turning applications into the flat list of rows the dialog displays.

Kept free of wxPython and NVDA imports so the expansion and sorting rules, which
are the fiddliest part of the dialog, can be tested directly.

Written by CodedByGoose, with the help of Quill (Claude agent).
"""

try:
    from . import formatting
except ImportError:  # Running from the test suite rather than inside NVDA.
    import formatting

SORT_CPU = "cpu"
SORT_MEMORY = "memory"
SORT_NAME = "name"

#: Order matters: it matches the entries in the dialog's sort combo box.
SORT_KEYS = (SORT_CPU, SORT_MEMORY, SORT_NAME)


class Row:
    """One line in the list: either an application, or a process within one."""

    __slots__ = ("key", "label", "app", "process")

    def __init__(self, key, label, app, process=None):
        self.key = key
        self.label = label
        self.app = app
        self.process = process

    @property
    def isApp(self):
        return self.process is None

    @property
    def isExpandable(self):
        return self.process is None and self.app.processCount > 1

    def __repr__(self):
        return f"<Row {self.key}>"


def sortApps(apps, sortKey):
    """Order applications for display.

    Ties are broken by a stable secondary key so that rows do not swap places
    between refreshes for no reason, which would move the list under the user.
    """
    if sortKey == SORT_MEMORY:
        return sorted(apps, key=lambda a: (-a.memoryBytes, a.displayName.lower()))
    if sortKey == SORT_NAME:
        return sorted(apps, key=lambda a: (a.displayName.lower(), -a.cpuPercent))
    return sorted(apps, key=lambda a: (-a.cpuPercent, -a.memoryBytes, a.displayName.lower()))


def appRowKey(app):
    return f"app:{app.key}"


def processRowKey(app, process):
    return f"proc:{app.key}:{process.pid}"


def buildRows(apps, expandedKeys, sortKey=SORT_CPU):
    """Flatten applications, and the children of expanded ones, into rows."""
    rows = []
    for app in sortApps(apps, sortKey):
        # An application with a single process has nothing to expand into, so it
        # never claims to be collapsed.
        isExpanded = app.key in expandedKeys and app.processCount > 1
        rows.append(Row(appRowKey(app), formatting.formatAppRow(app, isExpanded), app))
        if isExpanded:
            for process in app.processes:
                rows.append(
                    Row(
                        processRowKey(app, process),
                        formatting.formatProcessRow(process),
                        app,
                        process,
                    )
                )
    return rows


def findRowIndex(rows, key):
    """Locate a row by identity. Returns None when it is no longer present."""
    for index, row in enumerate(rows):
        if row.key == key:
            return index
    return None
