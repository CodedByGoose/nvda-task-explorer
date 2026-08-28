# -*- coding: UTF-8 -*-
"""Turning numbers into text that is pleasant to hear.

Every string a screen reader user actually listens to is built here, kept apart
from the dialog so the test suite can check the wording without wxPython or
NVDA being present.

Written by CodedByGoose, with the help of Quill (Claude agent).
"""

try:
    import addonHandler

    addonHandler.initTranslation()
except ImportError:
    # Running outside NVDA, which is where the tests run. NVDA installs gettext's
    # _ as a builtin; standing in for it keeps this module importable on its own.
    import builtins

    if not hasattr(builtins, "_"):
        builtins._ = lambda text: text

#: Below this, an application is doing nothing worth putting a number on.
IDLE_CPU_THRESHOLD = 0.05

KILOBYTE = 1024
MEGABYTE = KILOBYTE * 1024
GIGABYTE = MEGABYTE * 1024


def formatCpu(percent):
    """Describe a CPU percentage, keeping the spoken form short."""
    if percent < IDLE_CPU_THRESHOLD:
        # Translators: Spoken instead of a CPU percentage when an application is using no processor time.
        return _("idle")
    if percent < 10:
        # Translators: A CPU usage figure with one decimal place, for example "3.4 percent CPU".
        return _("{value:.1f} percent CPU").format(value=percent)
    # Translators: A whole number CPU usage figure, for example "24 percent CPU".
    return _("{value:.0f} percent CPU").format(value=percent)


def formatMemory(numberOfBytes):
    """Describe a quantity of memory at a sensible scale."""
    if numberOfBytes >= GIGABYTE:
        # Translators: A memory figure in gigabytes, for example "1.2 GB".
        return _("{value:.1f} GB").format(value=numberOfBytes / GIGABYTE)
    if numberOfBytes >= MEGABYTE:
        # Translators: A memory figure in megabytes, for example "412 MB".
        return _("{value:.0f} MB").format(value=numberOfBytes / MEGABYTE)
    # Translators: A memory figure in kilobytes, for example "64 KB".
    return _("{value:.0f} KB").format(value=numberOfBytes / KILOBYTE)


def formatAppRow(app, isExpanded=False):
    """Compose the single line that represents one application in the list."""
    parts = [app.displayName, formatCpu(app.cpuPercent), formatMemory(app.memoryBytes)]
    if app.processCount > 1:
        # Translators: The number of processes belonging to one application in the list.
        parts.append(_("{count} processes").format(count=app.processCount))
        parts.append(
            # Translators: Indicates that an application's individual processes are currently shown.
            _("expanded")
            if isExpanded
            # Translators: Indicates that an application's individual processes are currently hidden.
            else _("collapsed")
        )
    return ", ".join(parts)


def formatProcessRow(process):
    """Compose the line for one individual process beneath its application."""
    return ", ".join(
        [
            process.displayName,
            # Translators: Identifies an individual process by its process ID.
            _("process {pid}").format(pid=process.pid),
            formatCpu(process.cpuPercent),
            formatMemory(process.memoryBytes),
        ]
    )


def formatTotals(snapshot):
    """Describe overall machine load, announced when the dialog opens."""
    # Translators: A summary of overall system load, spoken when the dialog opens.
    return _("Total {cpu:.0f} percent CPU, memory {memory:.0f} percent used").format(
        cpu=min(snapshot.totalCpuPercent, 100.0),
        memory=snapshot.memoryPercent,
    )


def formatSpokenSummary(apps, includeMemory=True, byMemory=False):
    """Compose the announcement made by the spoken shortcuts."""
    if not apps:
        if byMemory:
            # Translators: Spoken when no applications could be measured.
            return _("No applications to report")
        # Translators: Spoken when nothing is using a measurable amount of processor time.
        return _("Nothing is using the processor right now")

    entries = []
    for app in apps:
        if byMemory:
            detail = formatMemory(app.memoryBytes)
            if includeMemory:
                detail = f"{detail}, {formatCpu(app.cpuPercent)}"
        else:
            detail = formatCpu(app.cpuPercent)
            if includeMemory:
                detail = f"{detail}, {formatMemory(app.memoryBytes)}"
        entries.append(f"{app.displayName}, {detail}")

    if byMemory:
        # Translators: Introduces the list of applications using the most memory.
        heading = _("Top {count} by memory").format(count=len(apps))
    else:
        # Translators: Introduces the list of applications using the most processor time.
        heading = _("Top {count} by CPU").format(count=len(apps))
    return heading + ": " + "; ".join(entries)


def formatNotReadyMessage():
    # Translators: Spoken when a shortcut is used before the first measurement has finished.
    return _("Still measuring, try again in a moment")
