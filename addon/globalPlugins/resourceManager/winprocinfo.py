# -*- coding: UTF-8 -*-
"""One-call enumeration of every running process on Windows.

Why this exists
---------------
psutil can give us everything in here, but not cheaply. On Windows, reading a
process's memory information always goes through NtQuerySystemInformation, and
reading its CPU times falls back to the same call whenever we lack permission to
open the process. That call enumerates the whole system every time it runs, so
asking psutil for 345 processes performs roughly 345 full system enumerations:
around 780 milliseconds of solid CPU work per sampling pass on a normal desktop.

A background thread in a screen reader add-on cannot cost that much. So we make
the same system call psutil makes, but once, and read every process out of the
single buffer it returns. That takes about 4 milliseconds for the same 345
processes, and it also covers processes a normal user cannot open, which means a
misbehaving system service stays visible instead of silently reading as zero.

The structure layout below is the long-documented SYSTEM_PROCESS_INFORMATION.
ctypes sizes HANDLE and SIZE_T to the running interpreter, so the same
definition is correct for NVDA's 32 bit build and for a 64 bit Python.

Written by CodedByGoose, with the help of Quill (Claude agent).
"""

import ctypes
from ctypes import wintypes

#: SystemProcessInformation, the SYSTEM_INFORMATION_CLASS value we query.
SYSTEM_PROCESS_INFORMATION_CLASS = 5

#: The buffer we offered was too small; grow it and ask again.
STATUS_INFO_LENGTH_MISMATCH = 0xC0000004

#: Windows file times count 100 nanosecond intervals.
HUNDRED_NANOSECONDS_PER_SECOND = 10_000_000

#: Offset between the Windows epoch (1601-01-01) and the Unix epoch, in seconds.
WINDOWS_TO_UNIX_EPOCH_SECONDS = 11644473600


class UNICODE_STRING(ctypes.Structure):
    _fields_ = [
        ("Length", wintypes.USHORT),
        ("MaximumLength", wintypes.USHORT),
        ("Buffer", ctypes.c_void_p),
    ]


class SYSTEM_PROCESS_INFORMATION(ctypes.Structure):
    """Truncated after the fields we actually read.

    Iteration follows NextEntryOffset rather than the size of this structure, so
    stopping early is safe: we only require that the offsets of the fields
    declared here are right, which they are as far as PrivatePageCount.
    """

    _fields_ = [
        ("NextEntryOffset", wintypes.ULONG),
        ("NumberOfThreads", wintypes.ULONG),
        ("WorkingSetPrivateSize", ctypes.c_longlong),
        ("HardFaultCount", wintypes.ULONG),
        ("NumberOfThreadsHighWatermark", wintypes.ULONG),
        ("CycleTime", ctypes.c_ulonglong),
        ("CreateTime", ctypes.c_longlong),
        ("UserTime", ctypes.c_longlong),
        ("KernelTime", ctypes.c_longlong),
        ("ImageName", UNICODE_STRING),
        ("BasePriority", ctypes.c_long),
        ("UniqueProcessId", ctypes.c_void_p),
        ("InheritedFromUniqueProcessId", ctypes.c_void_p),
        ("HandleCount", wintypes.ULONG),
        ("SessionId", wintypes.ULONG),
        ("UniqueProcessKey", ctypes.c_size_t),
        ("PeakVirtualSize", ctypes.c_size_t),
        ("VirtualSize", ctypes.c_size_t),
        ("PageFaultCount", wintypes.ULONG),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivatePageCount", ctypes.c_size_t),
    ]


_ntdll = None


def _getNtdll():
    global _ntdll
    if _ntdll is None:
        ntdll = ctypes.WinDLL("ntdll.dll")
        ntdll.NtQuerySystemInformation.argtypes = [
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
        ]
        ntdll.NtQuerySystemInformation.restype = ctypes.c_long
        _ntdll = ntdll
    return _ntdll


class ProcessSnapshotEntry(dict):
    """A plain dict; named for readability at the call site."""


def getSystemProcessInfo():
    """Return {pid: entry} for every process, from a single system call.

    Each entry holds: name, cpuSeconds, createTime (Unix epoch seconds),
    workingSetBytes, privateBytes, threadCount and parentPid.

    Raises OSError if the system call fails, so the caller can fall back.
    """
    ntdll = _getNtdll()
    size = ctypes.c_ulong(0x10000)
    returnLength = ctypes.c_ulong(0)

    # The process list changes between the sizing call and the reading call, so
    # grow generously and retry rather than trusting the reported length exactly.
    for _attempt in range(8):
        buffer = ctypes.create_string_buffer(size.value)
        status = ntdll.NtQuerySystemInformation(
            SYSTEM_PROCESS_INFORMATION_CLASS,
            buffer,
            size.value,
            ctypes.byref(returnLength),
        )
        if status == 0:
            break
        if (status & 0xFFFFFFFF) != STATUS_INFO_LENGTH_MISMATCH:
            raise OSError(f"NtQuerySystemInformation failed with status 0x{status & 0xFFFFFFFF:08X}")
        size.value = max(returnLength.value, size.value) * 2
    else:
        raise OSError("NtQuerySystemInformation would not settle on a buffer size")

    processes = {}
    address = ctypes.addressof(buffer)
    while True:
        entry = SYSTEM_PROCESS_INFORMATION.from_address(address)
        pid = entry.UniqueProcessId or 0

        if entry.ImageName.Buffer and entry.ImageName.Length:
            name = ctypes.wstring_at(entry.ImageName.Buffer, entry.ImageName.Length // 2)
        elif pid == 0:
            name = "System Idle Process"
        else:
            name = ""

        processes[pid] = {
            "name": name,
            "cpuSeconds": (entry.UserTime + entry.KernelTime) / HUNDRED_NANOSECONDS_PER_SECOND,
            "createTime": (
                entry.CreateTime / HUNDRED_NANOSECONDS_PER_SECOND - WINDOWS_TO_UNIX_EPOCH_SECONDS
                if entry.CreateTime
                else 0.0
            ),
            "workingSetBytes": entry.WorkingSetSize,
            "privateBytes": entry.PrivatePageCount,
            "threadCount": entry.NumberOfThreads,
            "parentPid": entry.InheritedFromUniqueProcessId or 0,
        }

        if not entry.NextEntryOffset:
            break
        address += entry.NextEntryOffset

    return processes


def verify():
    """Check the fast enumeration agrees with psutil before we rely on it.

    The structure above is laid out by ctypes using the running interpreter's
    pointer size and alignment. That is correct for NVDA's 32 bit build and for
    64 bit Python alike, but a wrong offset would not raise: it would quietly
    yield plausible looking nonsense. So rather than trust it, we compare our
    own process against psutil, which reads it by a completely different route.

    Returns (True, None) on success, or (False, reason) so the caller can fall
    back to the slower psutil path and log why.
    """
    try:
        import os

        import psutil

        processes = getSystemProcessInfo()
        if len(processes) < 5:
            return False, f"only {len(processes)} processes enumerated"

        ownPid = os.getpid()
        mine = processes.get(ownPid)
        if mine is None:
            return False, "our own process was missing from the enumeration"

        own = psutil.Process(ownPid)
        expectedName = own.name()
        if mine["name"].lower() != expectedName.lower():
            return False, f"name mismatch for our own process: {mine['name']!r} != {expectedName!r}"

        if abs(mine["createTime"] - own.create_time()) > 5.0:
            return False, "create time mismatch for our own process"

        expectedMemory = own.memory_info().rss
        if expectedMemory and not (0.5 <= mine["workingSetBytes"] / expectedMemory <= 2.0):
            return False, "working set size mismatch for our own process"

        return True, None
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
