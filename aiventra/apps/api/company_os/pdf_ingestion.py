"""No PDF parsing in API/worker threads: bounded fixed-code subprocess, never document execution."""

import asyncio
import ctypes
import json
import os
import subprocess
import sys
import sysconfig
import threading
from pathlib import Path

from fastapi import HTTPException

from .config import settings

_parse_slots = threading.BoundedSemaphore(2)


def windows_limit(process):
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_longlong),
            ("job_time", ctypes.c_longlong),
            ("flags", wintypes.DWORD),
            ("min_working", ctypes.c_size_t),
            ("max_working", ctypes.c_size_t),
            ("active", wintypes.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority", wintypes.DWORD),
            ("scheduling", wintypes.DWORD),
        ]

    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in ("r", "w", "o", "rb", "wb", "ob")]

    class Limits(ctypes.Structure):
        _fields_ = [
            ("basic", Basic),
            ("io", IO),
            ("process_memory", ctypes.c_size_t),
            ("job_memory", ctypes.c_size_t),
            ("peak_process", ctypes.c_size_t),
            ("peak_job", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateJobObjectW(None, None)
    limits = Limits()
    limits.basic.flags, limits.basic.process_time, limits.basic.active = 0x210A, 30_000_000, 1
    limits.process_memory = 268435456
    if (
        not handle
        or not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits))
        or not kernel.AssignProcessToJobObject(handle, int(process._handle))
    ):
        if handle:
            kernel.CloseHandle(handle)
        raise RuntimeError("PDF process isolation unavailable")
    return lambda: kernel.CloseHandle(handle)


def posix_limit():
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (268435456, 268435456))
    resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))


def extract_pdf(raw):
    if not _parse_slots.acquire(blocking=False):
        raise HTTPException(429, "PDF parser capacity reached; retry after the current uploads")
    try:
        return bounded_extract(raw)
    finally:
        _parse_slots.release()


def bounded_extract(raw):
    config = settings()
    command = [
        sys._base_executable,
        "-I",
        str(Path(__file__).with_name("pdf_parser.py")),
        str(config.pdf_page_limit),
        sysconfig.get_paths()["purelib"],
    ]
    # No inherited provider/cloud credentials; no input filename, URL or shell command.
    environment = {name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR") if name in os.environ}
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
            cwd=str(Path(__file__).parent),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            preexec_fn=posix_limit if os.name != "nt" else None,
        )
    except OSError:
        raise HTTPException(422, "Bounded PDF parser unavailable") from None

    def release():
        pass

    try:
        if os.name == "nt":
            release = windows_limit(process)
        output, _ = process.communicate(raw, timeout=config.pdf_timeout_seconds)
        if len(output) > 400000:
            raise ValueError()
        result = json.loads(output)
        if process.returncode or result.get("error"):
            raise HTTPException(422, result.get("error", "PDF resource limit exceeded"))
        return result
    except HTTPException:
        raise
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
        raise HTTPException(422, "PDF parsing failed or exceeded resource limits") from None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        release()


async def parse_pdf(raw):
    return await asyncio.to_thread(extract_pdf, raw)
