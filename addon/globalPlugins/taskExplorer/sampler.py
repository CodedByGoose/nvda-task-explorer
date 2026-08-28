# -*- coding: UTF-8 -*-
"""Process sampling for the Task Explorer NVDA add-on.

This module deliberately imports nothing from NVDA, so it can be exercised by
the test suite with an ordinary Python interpreter.

CPU usage per process is worked out by hand rather than with
psutil.Process.cpu_percent(). That method either blocks for its measurement
interval or keeps per-object state, and neither behaves well when the caller is
walking several hundred short lived processes on a timer. Instead a background
thread takes two snapshots of every process's accumulated CPU time and divides
the difference by the wall clock time that elapsed between them.

Written by CodedByGoose, with the help of Quill (Claude agent).
"""

import ctypes
import os
import threading
import time
import traceback
from ctypes import wintypes
from dataclasses import dataclass, field

import psutil

try:
    from . import winprocinfo
except ImportError:  # Running from the test suite rather than inside NVDA.
    import winprocinfo

#: The idle process reports enormous CPU time because it accounts for unused
#: cycles. Task Manager hides it and so do we.
IDLE_PID = 0

#: Processes that should never be ended casually. Ending any of these either
#: bluescreens Windows or, in NVDA's case, leaves the user with no speech.
PROTECTED_PROCESS_NAMES = frozenset(
    {
        "system",
        "registry",
        "smss.exe",
        "csrss.exe",
        "wininit.exe",
        "winlogon.exe",
        "services.exe",
        "lsass.exe",
        "svchost.exe",
        "dwm.exe",
        "nvda.exe",
    }
)

#: Executable names that say nothing useful about which application they are,
#: so the window title is worth appending when we have one.
AMBIGUOUS_PROCESS_NAMES = frozenset(
    {
        "python.exe",
        "pythonw.exe",
        "java.exe",
        "javaw.exe",
        "node.exe",
        "electron.exe",
        "cmd.exe",
        "powershell.exe",
        "pwsh.exe",
        "conhost.exe",
        "wscript.exe",
        "cscript.exe",
        "rundll32.exe",
        "dllhost.exe",
        "svchost.exe",
        "wine.exe",
    }
)


@dataclass
class ProcessRecord:
    """A single running process."""

    pid: int
    name: str
    displayName: str
    cpuPercent: float
    memoryBytes: int
    isProtected: bool = False


@dataclass
class AppRecord:
    """One application, being every process sharing the same executable."""

    key: str
    displayName: str
    cpuPercent: float
    memoryBytes: int
    processes: list = field(default_factory=list)
    isProtected: bool = False

    @property
    def processCount(self):
        return len(self.processes)

    @property
    def pids(self):
        return [p.pid for p in self.processes]


@dataclass
class Snapshot:
    """Everything one sampling pass produced."""

    apps: list = field(default_factory=list)
    totalCpuPercent: float = 0.0
    usedMemoryBytes: int = 0
    totalMemoryBytes: int = 0
    timestamp: float = 0.0

    @property
    def memoryPercent(self):
        if not self.totalMemoryBytes:
            return 0.0
        return self.usedMemoryBytes / self.totalMemoryBytes * 100.0


# --- Friendly application names -------------------------------------------------

_friendlyNameCache = {}


def _readFileDescription(exePath):
    """Return the FileDescription recorded in an executable's version resource.

    This is where "Google Chrome" lives for chrome.exe, and it is what Task
    Manager displays. Returns None when the file has no version resource.
    """
    try:
        version = ctypes.WinDLL("version.dll")
        size = version.GetFileVersionInfoSizeW(ctypes.c_wchar_p(exePath), None)
        if not size:
            return None
        buffer = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(ctypes.c_wchar_p(exePath), 0, size, buffer):
            return None

        pointer = ctypes.c_void_p()
        length = wintypes.UINT()
        # Find which language and code page this file's strings are stored under.
        if not version.VerQueryValueW(
            buffer,
            ctypes.c_wchar_p("\\VarFileInfo\\Translation"),
            ctypes.byref(pointer),
            ctypes.byref(length),
        ):
            return None
        if length.value < 4:
            return None
        langCodepage = ctypes.cast(pointer, ctypes.POINTER(wintypes.WORD))
        language, codepage = langCodepage[0], langCodepage[1]

        subBlock = f"\\StringFileInfo\\{language:04x}{codepage:04x}\\FileDescription"
        if not version.VerQueryValueW(
            buffer,
            ctypes.c_wchar_p(subBlock),
            ctypes.byref(pointer),
            ctypes.byref(length),
        ):
            return None
        if not length.value:
            return None
        description = ctypes.wstring_at(pointer, length.value - 1).strip()
        return description or None
    except Exception:
        # Version resources are optional and occasionally malformed. A missing
        # friendly name is never worth failing a sampling pass over.
        return None


def getFriendlyName(exePath, fallbackName):
    """Return a human readable application name, cached per executable path."""
    if not exePath:
        return _prettifyProcessName(fallbackName)
    cached = _friendlyNameCache.get(exePath)
    if cached is not None:
        return cached
    description = _readFileDescription(exePath)
    name = description or _prettifyProcessName(fallbackName or os.path.basename(exePath))
    _friendlyNameCache[exePath] = name
    return name


def _prettifyProcessName(name):
    """Turn an executable file name into something reasonable to hear."""
    if not name:
        return "Unknown"
    stem = name[:-4] if name.lower().endswith(".exe") else name
    return stem or name


# --- Window titles --------------------------------------------------------------

_EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def getWindowTitlesByPid():
    """Map process IDs to the title of their most prominent visible window.

    Used only to tell apart processes whose executable name says nothing, such
    as several unrelated tools all running as python.exe.
    """
    titles = {}
    try:
        user32 = ctypes.WinDLL("user32.dll")

        def callback(hwnd, _lParam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if not length:
                    return True
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                title = buffer.value.strip()
                if not title:
                    return True
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                # Keep the first visible window we meet for each process; the
                # enumeration order puts foreground windows first.
                titles.setdefault(pid.value, title)
            except Exception:
                pass
            return True

        user32.EnumWindows(_EnumWindowsProc(callback), 0)
    except Exception:
        return {}
    return titles


# --- Sampling -------------------------------------------------------------------

_SNAPSHOT_ATTRS = ["pid", "name", "exe", "cpu_times", "memory_info", "create_time"]

#: Executable paths keyed by process ID, as {pid: (createTime, exePath)}.
#: Resolving an executable path is the one genuinely slow thing left in a pass,
#: and a live process never changes its own, so it is looked up once per process.
_exePathCache = {}
_EXE_CACHE_LIMIT = 4000


def _getExePath(pid, createTime):
    cached = _exePathCache.get(pid)
    # The create time guards against Windows recycling a process ID.
    if cached is not None and cached[0] == createTime:
        return cached[1]
    try:
        exe = psutil.Process(pid).exe() or ""
    except Exception:
        # Protected and already dead processes have no path we may read. The
        # executable name still identifies them well enough to group by.
        exe = ""
    _exePathCache[pid] = (createTime, exe)
    return exe


def _pruneExePathCache(livePids):
    if len(_exePathCache) <= _EXE_CACHE_LIMIT:
        return
    for pid in [p for p in _exePathCache if p not in livePids]:
        del _exePathCache[pid]


def _takeFastSnapshot():
    """Collect per process figures using a single system call."""
    processes = {}
    for pid, entry in winprocinfo.getSystemProcessInfo().items():
        if pid == IDLE_PID:
            continue
        name = entry["name"]
        createTime = entry["createTime"]
        processes[pid] = {
            "name": name,
            "exe": _getExePath(pid, createTime),
            "cpuSeconds": entry["cpuSeconds"],
            "memoryBytes": entry["workingSetBytes"],
            "createTime": createTime,
        }
    _pruneExePathCache(processes.keys())
    return processes


def _takePsutilSnapshot():
    """Fallback collection using psutil alone.

    Correct everywhere, but performs a full system enumeration per process, so
    it costs the better part of a second on a busy machine. Only used when the
    fast path fails to verify itself.
    """
    processes = {}
    for process in psutil.process_iter(attrs=_SNAPSHOT_ATTRS, ad_value=None):
        info = process.info
        pid = info["pid"]
        if pid == IDLE_PID:
            continue
        cpuTimes = info["cpu_times"]
        # A process we cannot read CPU times for is one we can say nothing about.
        cpuSeconds = (cpuTimes.user + cpuTimes.system) if cpuTimes else None
        memoryInfo = info["memory_info"]
        processes[pid] = {
            "name": info["name"] or "",
            "exe": info["exe"] or "",
            "cpuSeconds": cpuSeconds,
            "memoryBytes": memoryInfo.rss if memoryInfo else 0,
            "createTime": info["create_time"],
        }
    return processes


def _takeRawSnapshot(useFastPath=True):
    """Collect the raw per process figures needed to compute a CPU delta."""
    if useFastPath:
        return _takeFastSnapshot(), time.monotonic()
    return _takePsutilSnapshot(), time.monotonic()


def buildSnapshot(previous, previousTime, current, currentTime, cpuCount, windowTitles=None):
    """Turn two raw snapshots into grouped application records.

    Separated from the sampling thread so the test suite can feed it fabricated
    snapshots and assert on the arithmetic.
    """
    elapsed = max(currentTime - previousTime, 1e-6)
    cpuCount = max(cpuCount or 1, 1)
    windowTitles = windowTitles or {}

    groups = {}
    for pid, info in current.items():
        before = previous.get(pid)
        cpuSeconds = info["cpuSeconds"]
        # Only count processes that existed in both snapshots and are the same
        # process: process IDs are recycled by Windows.
        if (
            before is None
            or cpuSeconds is None
            or before["cpuSeconds"] is None
            or before["createTime"] != info["createTime"]
        ):
            cpuPercent = 0.0
        else:
            deltaSeconds = max(cpuSeconds - before["cpuSeconds"], 0.0)
            cpuPercent = deltaSeconds / elapsed / cpuCount * 100.0
            cpuPercent = min(cpuPercent, 100.0)

        name = info["name"]
        exe = info["exe"]
        key = (exe or name or str(pid)).lower()
        lowerName = name.lower()
        isProtected = lowerName in PROTECTED_PROCESS_NAMES

        group = groups.get(key)
        if group is None:
            displayName = getFriendlyName(exe, name)
            title = windowTitles.get(pid)
            # Only lean on the window title when the executable name alone
            # would leave several unrelated apps sounding identical.
            if title and lowerName in AMBIGUOUS_PROCESS_NAMES:
                displayName = f"{displayName} ({title})"
            group = AppRecord(
                key=key,
                displayName=displayName,
                cpuPercent=0.0,
                memoryBytes=0,
                isProtected=isProtected,
            )
            groups[key] = group

        group.cpuPercent += cpuPercent
        group.memoryBytes += info["memoryBytes"]
        group.isProtected = group.isProtected or isProtected
        group.processes.append(
            ProcessRecord(
                pid=pid,
                name=name,
                displayName=windowTitles.get(pid) or _prettifyProcessName(name),
                cpuPercent=cpuPercent,
                memoryBytes=info["memoryBytes"],
                isProtected=isProtected,
            )
        )

    apps = list(groups.values())
    for app in apps:
        # Grouped CPU can exceed a full machine only through rounding.
        app.cpuPercent = min(app.cpuPercent, 100.0)
        app.processes.sort(key=lambda p: (-p.cpuPercent, -p.memoryBytes))
    apps.sort(key=lambda a: (-a.cpuPercent, -a.memoryBytes))
    return apps


class Sampler:
    """Samples running processes on a background thread.

    The thread is a daemon and holds no NVDA locks, so a slow sampling pass can
    never stall speech.
    """

    def __init__(self, interval=2.0, onError=None):
        self._interval = max(float(interval), 0.5)
        self._snapshot = Snapshot()
        self._lock = threading.Lock()
        self._stopEvent = threading.Event()
        self._thread = None
        self._cpuCount = psutil.cpu_count() or 1
        #: Called with a message when a sampling pass fails. The plugin points
        #: this at NVDA's log; without it failures would be invisible.
        self.onError = onError
        #: Decided on first start by checking the fast enumeration against
        #: psutil, so a bad structure layout degrades to slow but correct.
        self._useFastPath = True
        self._fastPathChecked = False

    @property
    def usingFastPath(self):
        return self._useFastPath

    def _chooseSamplingPath(self):
        if self._fastPathChecked:
            return
        self._fastPathChecked = True
        ok, reason = winprocinfo.verify()
        self._useFastPath = ok
        if not ok and self.onError:
            try:
                self.onError(
                    "Task Explorer: fast process enumeration failed its self check "
                    f"({reason}). Falling back to the slower psutil path."
                )
            except Exception:
                pass

    @property
    def interval(self):
        return self._interval

    def setInterval(self, interval):
        """Change the sampling interval. Takes effect from the next pass."""
        self._interval = max(float(interval), 0.5)

    @property
    def isPrimed(self):
        """True once at least one pair of snapshots has produced real figures."""
        with self._lock:
            return self._snapshot.timestamp > 0.0

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stopEvent.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="taskExplorerSampler",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout=3.0):
        self._stopEvent.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout)
        self._thread = None

    def getSnapshot(self):
        """Return the most recent snapshot. Safe to call from any thread."""
        with self._lock:
            return self._snapshot

    def getApps(self):
        return self.getSnapshot().apps

    def getTopApps(self, count=3, key="cpu"):
        """Return the busiest applications, ignoring ones that are idle."""
        apps = self.getApps()
        if key == "memory":
            ranked = sorted(apps, key=lambda a: -a.memoryBytes)
        else:
            ranked = [a for a in apps if a.cpuPercent > 0.05]
        return ranked[: max(count, 0)]

    def _run(self):
        self._chooseSamplingPath()
        previous, previousTime = _takeRawSnapshot(self._useFastPath)
        while not self._stopEvent.wait(self._interval):
            try:
                current, currentTime = _takeRawSnapshot(self._useFastPath)
                apps = buildSnapshot(
                    previous,
                    previousTime,
                    current,
                    currentTime,
                    self._cpuCount,
                    getWindowTitlesByPid(),
                )
                memory = psutil.virtual_memory()
                snapshot = Snapshot(
                    apps=apps,
                    totalCpuPercent=sum(a.cpuPercent for a in apps),
                    usedMemoryBytes=memory.total - memory.available,
                    totalMemoryBytes=memory.total,
                    timestamp=time.time(),
                )
                with self._lock:
                    self._snapshot = snapshot
                previous, previousTime = current, currentTime
            except Exception:
                # A failed pass must not kill the thread; the next one may work.
                if self.onError:
                    try:
                        self.onError("Task Explorer sampling pass failed:\n" + traceback.format_exc())
                    except Exception:
                        pass
                try:
                    previous, previousTime = _takeRawSnapshot(self._useFastPath)
                except Exception:
                    pass
