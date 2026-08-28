# -*- coding: UTF-8 -*-
"""Tests for what the user actually hears, and for the row and sort model.

Neither module under test imports wxPython or NVDA, so these run under an
ordinary Python interpreter:

    python -m unittest discover -s tests

Written by CodedByGoose, with the help of Quill (Claude agent).
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "addon", "globalPlugins", "taskExplorer"),
)

import formatting  # noqa: E402
import rowmodel  # noqa: E402
from sampler import AppRecord, ProcessRecord, Snapshot  # noqa: E402

MB = 1024 * 1024
GB = MB * 1024


def makeApp(name, cpu=0.0, memory=MB, processCount=1, key=None, isProtected=False):
    app = AppRecord(
        key=key or name.lower(),
        displayName=name,
        cpuPercent=cpu,
        memoryBytes=memory,
        isProtected=isProtected,
    )
    for index in range(processCount):
        app.processes.append(
            ProcessRecord(
                pid=1000 + index,
                name=f"{name.lower()}.exe",
                displayName=f"{name} {index}",
                cpuPercent=cpu / max(processCount, 1),
                memoryBytes=memory // max(processCount, 1),
            )
        )
    return app


class TestNumberWording(unittest.TestCase):
    def test_idleIsWordsNotZeroPercent(self):
        self.assertEqual(formatting.formatCpu(0.0), "idle")
        self.assertEqual(formatting.formatCpu(0.001), "idle")

    def test_smallFiguresKeepOneDecimal(self):
        self.assertEqual(formatting.formatCpu(3.44), "3.4 percent CPU")

    def test_largeFiguresAreRounded(self):
        # "24 percent CPU" is quicker to hear than "24.3 percent CPU".
        self.assertEqual(formatting.formatCpu(24.3), "24 percent CPU")

    def test_memoryScalesToGigabytes(self):
        self.assertEqual(formatting.formatMemory(int(2.5 * GB)), "2.5 GB")

    def test_memoryScalesToMegabytes(self):
        self.assertEqual(formatting.formatMemory(412 * MB), "412 MB")

    def test_smallMemoryScalesToKilobytes(self):
        self.assertEqual(formatting.formatMemory(64 * 1024), "64 KB")


class TestRowWording(unittest.TestCase):
    def test_singleProcessAppOmitsCountAndExpansionState(self):
        label = formatting.formatAppRow(makeApp("Notepad", cpu=1.5, memory=40 * MB))
        self.assertEqual(label, "Notepad, 1.5 percent CPU, 40 MB")

    def test_multiProcessAppStatesCountAndCollapsedState(self):
        label = formatting.formatAppRow(makeApp("Chrome", cpu=12.0, memory=GB, processCount=40))
        self.assertEqual(label, "Chrome, 12 percent CPU, 1.0 GB, 40 processes, collapsed")

    def test_expandedStateIsAnnouncedInTheRow(self):
        label = formatting.formatAppRow(makeApp("Chrome", cpu=12.0, memory=GB, processCount=40), isExpanded=True)
        self.assertTrue(label.endswith("expanded"))

    def test_processRowIdentifiesItselfByProcessId(self):
        process = ProcessRecord(pid=4321, name="chrome.exe", displayName="Gmail", cpuPercent=3.0, memoryBytes=210 * MB)
        self.assertEqual(formatting.formatProcessRow(process), "Gmail, process 4321, 3.0 percent CPU, 210 MB")


class TestSpokenSummary(unittest.TestCase):
    def test_summaryListsAppsWithCpuAndMemory(self):
        apps = [makeApp("Chrome", cpu=12.0, memory=GB), makeApp("Code", cpu=4.0, memory=512 * MB)]
        summary = formatting.formatSpokenSummary(apps)
        self.assertEqual(summary, "Top 2 by CPU: Chrome, 12 percent CPU, 1.0 GB; Code, 4.0 percent CPU, 512 MB")

    def test_memoryCanBeLeftOut(self):
        apps = [makeApp("Chrome", cpu=12.0, memory=GB)]
        self.assertEqual(formatting.formatSpokenSummary(apps, includeMemory=False), "Top 1 by CPU: Chrome, 12 percent CPU")

    def test_memorySummaryLeadsWithMemory(self):
        apps = [makeApp("Chrome", cpu=12.0, memory=GB)]
        summary = formatting.formatSpokenSummary(apps, byMemory=True)
        self.assertTrue(summary.startswith("Top 1 by memory: Chrome, 1.0 GB"))

    def test_anIdleMachineSaysSoPlainly(self):
        self.assertEqual(formatting.formatSpokenSummary([]), "Nothing is using the processor right now")

    def test_totalsMentionBothCpuAndMemory(self):
        snapshot = Snapshot(totalCpuPercent=21.4, usedMemoryBytes=8 * GB, totalMemoryBytes=16 * GB)
        self.assertEqual(formatting.formatTotals(snapshot), "Total 21 percent CPU, memory 50 percent used")


class TestSorting(unittest.TestCase):
    def setUp(self):
        self.apps = [
            makeApp("Beta", cpu=1.0, memory=900 * MB),
            makeApp("Alpha", cpu=9.0, memory=100 * MB),
            makeApp("Gamma", cpu=5.0, memory=500 * MB),
        ]

    def test_defaultOrderIsBusiestCpuFirst(self):
        names = [a.displayName for a in rowmodel.sortApps(self.apps, rowmodel.SORT_CPU)]
        self.assertEqual(names, ["Alpha", "Gamma", "Beta"])

    def test_memoryOrderIsLargestFirst(self):
        names = [a.displayName for a in rowmodel.sortApps(self.apps, rowmodel.SORT_MEMORY)]
        self.assertEqual(names, ["Beta", "Gamma", "Alpha"])

    def test_nameOrderIsAlphabeticalAndCaseInsensitive(self):
        apps = self.apps + [makeApp("alpha two", cpu=0.0)]
        names = [a.displayName for a in rowmodel.sortApps(apps, rowmodel.SORT_NAME)]
        self.assertEqual(names, ["Alpha", "alpha two", "Beta", "Gamma"])

    def test_equalAppsKeepAStableOrderBetweenRefreshes(self):
        # Rows that swap places for no reason would move the list under the user.
        tied = [makeApp("Zulu", cpu=5.0, memory=MB), makeApp("Alpha", cpu=5.0, memory=MB)]
        first = [a.displayName for a in rowmodel.sortApps(tied, rowmodel.SORT_CPU)]
        second = [a.displayName for a in rowmodel.sortApps(list(reversed(tied)), rowmodel.SORT_CPU)]
        self.assertEqual(first, second)


class TestRowBuilding(unittest.TestCase):
    def test_collapsedAppContributesOneRow(self):
        rows = rowmodel.buildRows([makeApp("Chrome", processCount=40)], expandedKeys=set())
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].isApp)
        self.assertTrue(rows[0].isExpandable)

    def test_expandedAppContributesItsChildren(self):
        app = makeApp("Chrome", processCount=3)
        rows = rowmodel.buildRows([app], expandedKeys={app.key})
        self.assertEqual(len(rows), 4)
        self.assertTrue(rows[0].isApp)
        self.assertFalse(any(r.isApp for r in rows[1:]))

    def test_singleProcessAppNeverExpands(self):
        app = makeApp("Notepad", processCount=1)
        rows = rowmodel.buildRows([app], expandedKeys={app.key})
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0].isExpandable)

    def test_expandingOneAppLeavesOthersCollapsed(self):
        chrome = makeApp("Chrome", cpu=9.0, processCount=3)
        code = makeApp("Code", cpu=1.0, processCount=5)
        rows = rowmodel.buildRows([chrome, code], expandedKeys={chrome.key})
        self.assertEqual([r.isApp for r in rows], [True, False, False, False, True])

    def test_rowKeysAreUniqueAndStable(self):
        app = makeApp("Chrome", processCount=3)
        keys = [r.key for r in rowmodel.buildRows([app], expandedKeys={app.key})]
        self.assertEqual(len(keys), len(set(keys)))
        again = [r.key for r in rowmodel.buildRows([app], expandedKeys={app.key})]
        self.assertEqual(keys, again)

    def test_expansionSurvivesReordering(self):
        # The user expands an app, then it drops down the list as usage changes.
        # It must still be expanded, and still findable by key.
        chrome = makeApp("Chrome", cpu=9.0, processCount=3)
        code = makeApp("Code", cpu=1.0, processCount=2)
        before = rowmodel.buildRows([chrome, code], expandedKeys={chrome.key})
        chrome.cpuPercent = 0.1
        after = rowmodel.buildRows([chrome, code], expandedKeys={chrome.key})
        self.assertEqual(rowmodel.findRowIndex(before, rowmodel.appRowKey(chrome)), 0)
        self.assertEqual(rowmodel.findRowIndex(after, rowmodel.appRowKey(chrome)), 1)
        self.assertEqual(sum(1 for r in after if not r.isApp), 3)

    def test_findRowIndexReturnsNoneForAVanishedApp(self):
        rows = rowmodel.buildRows([makeApp("Chrome")], expandedKeys=set())
        self.assertIsNone(rowmodel.findRowIndex(rows, "app:gone"))

    def test_sortComboOrderMatchesSortKeys(self):
        # The dialog maps the combo box selection straight onto this tuple.
        self.assertEqual(rowmodel.SORT_KEYS, ("cpu", "memory", "name"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
