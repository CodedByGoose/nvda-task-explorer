# -*- coding: UTF-8 -*-
"""Tests for the Resource Manager sampler.

The sampler imports nothing from NVDA, so these run under an ordinary Python
interpreter that has psutil installed:

    python -m unittest discover -s tests

Written by CodedByGoose, with the help of Quill (Claude agent).
"""

import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "addon", "globalPlugins", "resourceManager"),
)

import sampler  # noqa: E402
import winprocinfo  # noqa: E402


def makeProcess(name, exe, cpuSeconds, memoryBytes=1024, createTime=1000.0):
    return {
        "name": name,
        "exe": exe,
        "cpuSeconds": cpuSeconds,
        "memoryBytes": memoryBytes,
        "createTime": createTime,
    }


class TestCpuArithmetic(unittest.TestCase):
    """The core sum: CPU seconds burned, over wall clock time, over core count."""

    def test_oneFullCoreOfFourReadsAsTwentyFivePercent(self):
        previous = {100: makeProcess("app.exe", r"C:\fake\app.exe", 10.0)}
        current = {100: makeProcess("app.exe", r"C:\fake\app.exe", 11.0)}
        apps = sampler.buildSnapshot(previous, 0.0, current, 1.0, cpuCount=4)
        self.assertEqual(len(apps), 1)
        self.assertAlmostEqual(apps[0].cpuPercent, 25.0, places=4)

    def test_allFourCoresReadsAsOneHundredPercent(self):
        previous = {100: makeProcess("app.exe", r"C:\fake\app.exe", 0.0)}
        current = {100: makeProcess("app.exe", r"C:\fake\app.exe", 4.0)}
        apps = sampler.buildSnapshot(previous, 0.0, current, 1.0, cpuCount=4)
        self.assertAlmostEqual(apps[0].cpuPercent, 100.0, places=4)

    def test_idleProcessReadsAsZero(self):
        previous = {100: makeProcess("app.exe", r"C:\fake\app.exe", 5.0)}
        current = {100: makeProcess("app.exe", r"C:\fake\app.exe", 5.0)}
        apps = sampler.buildSnapshot(previous, 0.0, current, 2.0, cpuCount=4)
        self.assertEqual(apps[0].cpuPercent, 0.0)

    def test_resultIsClampedToOneHundredPercent(self):
        # A clock adjustment or a very short interval must not produce 900%.
        previous = {100: makeProcess("app.exe", r"C:\fake\app.exe", 0.0)}
        current = {100: makeProcess("app.exe", r"C:\fake\app.exe", 40.0)}
        apps = sampler.buildSnapshot(previous, 0.0, current, 1.0, cpuCount=4)
        self.assertEqual(apps[0].cpuPercent, 100.0)

    def test_zeroElapsedTimeDoesNotDivideByZero(self):
        previous = {100: makeProcess("app.exe", r"C:\fake\app.exe", 1.0)}
        current = {100: makeProcess("app.exe", r"C:\fake\app.exe", 1.0)}
        apps = sampler.buildSnapshot(previous, 5.0, current, 5.0, cpuCount=4)
        self.assertEqual(apps[0].cpuPercent, 0.0)

    def test_cpuCountOfZeroIsTreatedAsOne(self):
        previous = {100: makeProcess("app.exe", r"C:\fake\app.exe", 0.0)}
        current = {100: makeProcess("app.exe", r"C:\fake\app.exe", 0.5)}
        apps = sampler.buildSnapshot(previous, 0.0, current, 1.0, cpuCount=0)
        self.assertAlmostEqual(apps[0].cpuPercent, 50.0, places=4)


class TestProcessIdentity(unittest.TestCase):
    """Windows recycles process IDs, and new processes have no history."""

    def test_recycledProcessIdIsNotCreditedWithOldCpuTime(self):
        previous = {100: makeProcess("old.exe", r"C:\fake\old.exe", 500.0, createTime=1000.0)}
        # Same pid, different process: a naive delta would report a huge negative
        # or wildly wrong figure.
        current = {100: makeProcess("new.exe", r"C:\fake\new.exe", 2.0, createTime=9999.0)}
        apps = sampler.buildSnapshot(previous, 0.0, current, 1.0, cpuCount=4)
        self.assertEqual(apps[0].cpuPercent, 0.0)
        self.assertEqual(apps[0].processes[0].name, "new.exe")

    def test_processAbsentFromPreviousSnapshotReadsAsZero(self):
        apps = sampler.buildSnapshot({}, 0.0, {100: makeProcess("new.exe", r"C:\fake\new.exe", 3.0)}, 1.0, cpuCount=4)
        self.assertEqual(apps[0].cpuPercent, 0.0)

    def test_processThatEndedIsDropped(self):
        previous = {
            100: makeProcess("a.exe", r"C:\fake\a.exe", 1.0),
            200: makeProcess("b.exe", r"C:\fake\b.exe", 1.0),
        }
        current = {100: makeProcess("a.exe", r"C:\fake\a.exe", 1.5)}
        apps = sampler.buildSnapshot(previous, 0.0, current, 1.0, cpuCount=4)
        self.assertEqual([a.processes[0].pid for a in apps], [100])

    def test_backwardsCpuTimeDoesNotProduceNegativeUsage(self):
        previous = {100: makeProcess("a.exe", r"C:\fake\a.exe", 10.0)}
        current = {100: makeProcess("a.exe", r"C:\fake\a.exe", 9.0)}
        apps = sampler.buildSnapshot(previous, 0.0, current, 1.0, cpuCount=4)
        self.assertEqual(apps[0].cpuPercent, 0.0)


class TestGrouping(unittest.TestCase):
    def test_processesSharingAnExecutableBecomeOneApp(self):
        previous = {
            1: makeProcess("chrome.exe", r"C:\fake\chrome.exe", 0.0),
            2: makeProcess("chrome.exe", r"C:\fake\chrome.exe", 0.0),
            3: makeProcess("chrome.exe", r"C:\fake\chrome.exe", 0.0),
        }
        current = {
            1: makeProcess("chrome.exe", r"C:\fake\chrome.exe", 1.0, memoryBytes=100),
            2: makeProcess("chrome.exe", r"C:\fake\chrome.exe", 1.0, memoryBytes=200),
            3: makeProcess("chrome.exe", r"C:\fake\chrome.exe", 2.0, memoryBytes=300),
        }
        apps = sampler.buildSnapshot(previous, 0.0, current, 1.0, cpuCount=8)
        self.assertEqual(len(apps), 1)
        app = apps[0]
        self.assertEqual(app.processCount, 3)
        self.assertEqual(sorted(app.pids), [1, 2, 3])
        self.assertEqual(app.memoryBytes, 600)
        # 4 CPU seconds over 1 second on 8 cores.
        self.assertAlmostEqual(app.cpuPercent, 50.0, places=4)

    def test_sameNameDifferentPathsStaySeparate(self):
        current = {
            1: makeProcess("python.exe", r"C:\toolA\python.exe", 1.0),
            2: makeProcess("python.exe", r"C:\toolB\python.exe", 1.0),
        }
        apps = sampler.buildSnapshot({}, 0.0, current, 1.0, cpuCount=4)
        self.assertEqual(len(apps), 2)

    def test_childProcessesAreSortedBusiestFirst(self):
        previous = {n: makeProcess("app.exe", r"C:\fake\app.exe", 0.0) for n in (1, 2, 3)}
        current = {
            1: makeProcess("app.exe", r"C:\fake\app.exe", 0.5),
            2: makeProcess("app.exe", r"C:\fake\app.exe", 2.0),
            3: makeProcess("app.exe", r"C:\fake\app.exe", 1.0),
        }
        apps = sampler.buildSnapshot(previous, 0.0, current, 1.0, cpuCount=8)
        self.assertEqual([p.pid for p in apps[0].processes], [2, 3, 1])

    def test_appsAreSortedBusiestFirst(self):
        previous = {n: makeProcess(f"a{n}.exe", rf"C:\fake\a{n}.exe", 0.0) for n in (1, 2, 3)}
        current = {
            1: makeProcess("a1.exe", r"C:\fake\a1.exe", 0.5),
            2: makeProcess("a2.exe", r"C:\fake\a2.exe", 2.0),
            3: makeProcess("a3.exe", r"C:\fake\a3.exe", 1.0),
        }
        apps = sampler.buildSnapshot(previous, 0.0, current, 1.0, cpuCount=8)
        self.assertEqual([a.processes[0].name for a in apps], ["a2.exe", "a3.exe", "a1.exe"])


class TestNaming(unittest.TestCase):
    def test_ambiguousExecutableGainsItsWindowTitle(self):
        current = {1: makeProcess("python.exe", r"C:\fake\python.exe", 1.0)}
        apps = sampler.buildSnapshot({}, 0.0, current, 1.0, cpuCount=4, windowTitles={1: "My Script"})
        self.assertIn("My Script", apps[0].displayName)

    def test_ordinaryExecutableDoesNotGainItsWindowTitle(self):
        current = {1: makeProcess("notepad.exe", r"C:\fake\notepad.exe", 1.0)}
        apps = sampler.buildSnapshot({}, 0.0, current, 1.0, cpuCount=4, windowTitles={1: "Untitled"})
        self.assertNotIn("Untitled", apps[0].displayName)

    def test_executableSuffixIsStripped(self):
        self.assertEqual(sampler._prettifyProcessName("notepad.exe"), "notepad")
        self.assertEqual(sampler._prettifyProcessName("weird"), "weird")
        self.assertEqual(sampler._prettifyProcessName(""), "Unknown")


class TestProtectedProcesses(unittest.TestCase):
    def test_criticalSystemProcessesAreFlagged(self):
        current = {1: makeProcess("csrss.exe", r"C:\Windows\System32\csrss.exe", 1.0)}
        apps = sampler.buildSnapshot({}, 0.0, current, 1.0, cpuCount=4)
        self.assertTrue(apps[0].isProtected)

    def test_nvdaItselfIsProtected(self):
        # Ending NVDA would leave the user with no speech and no way back.
        current = {1: makeProcess("nvda.exe", r"C:\Program Files (x86)\NVDA\nvda.exe", 1.0)}
        apps = sampler.buildSnapshot({}, 0.0, current, 1.0, cpuCount=4)
        self.assertTrue(apps[0].isProtected)

    def test_ordinaryApplicationsAreNotFlagged(self):
        current = {1: makeProcess("notepad.exe", r"C:\Windows\notepad.exe", 1.0)}
        apps = sampler.buildSnapshot({}, 0.0, current, 1.0, cpuCount=4)
        self.assertFalse(apps[0].isProtected)

    def test_groupIsProtectedIfAnyMemberIs(self):
        current = {
            1: makeProcess("svchost.exe", r"C:\Windows\System32\svchost.exe", 1.0),
            2: makeProcess("svchost.exe", r"C:\Windows\System32\svchost.exe", 1.0),
        }
        apps = sampler.buildSnapshot({}, 0.0, current, 1.0, cpuCount=4)
        self.assertTrue(apps[0].isProtected)


class TestSnapshotRecord(unittest.TestCase):
    def test_memoryPercentHandlesEmptySnapshot(self):
        self.assertEqual(sampler.Snapshot().memoryPercent, 0.0)

    def test_memoryPercentIsComputedFromTotals(self):
        snapshot = sampler.Snapshot(usedMemoryBytes=4, totalMemoryBytes=16)
        self.assertEqual(snapshot.memoryPercent, 25.0)


class TestFastEnumeration(unittest.TestCase):
    """These touch the real system, since that is the point of them."""

    def test_fastPathAgreesWithPsutil(self):
        ok, reason = winprocinfo.verify()
        self.assertTrue(ok, f"fast enumeration failed its self check: {reason}")

    def test_ourOwnProcessIsPresentAndSane(self):
        processes = winprocinfo.getSystemProcessInfo()
        entry = processes[os.getpid()]
        self.assertTrue(entry["name"].lower().startswith("python"))
        self.assertGreater(entry["workingSetBytes"], 1024 * 1024)
        self.assertGreater(entry["threadCount"], 0)

    def test_enumerationFindsAPlausibleNumberOfProcesses(self):
        self.assertGreater(len(winprocinfo.getSystemProcessInfo()), 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
