"""Best-effort process memory compaction, independent of worker lifecycle."""
import ctypes
from ctypes import wintypes
import gc
import sys


def compact_memory():
    """Collect garbage and return unused Windows working-set pages to the OS."""
    try:
        gc.collect()
        if sys.platform == 'win32':
            kernel32 = ctypes.windll.kernel32
            psapi = ctypes.windll.psapi
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
            psapi.EmptyWorkingSet(kernel32.GetCurrentProcess())
    except Exception:
        pass
