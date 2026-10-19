"""Read-only Windows Restart Manager query; does not stop apps or delete files."""
import ctypes
from ctypes import wintypes
import json
import sys
import uuid


class UniqueProcess(ctypes.Structure):
    _fields_ = [("pid", wintypes.DWORD), ("started", wintypes.FILETIME)]


class ProcessInfo(ctypes.Structure):
    _fields_ = [
        ("process", UniqueProcess),
        ("app_name", wintypes.WCHAR * 256),
        ("service_name", wintypes.WCHAR * 64),
        ("app_type", ctypes.c_int),
        ("status", wintypes.ULONG),
        ("session_id", wintypes.DWORD),
        ("restartable", wintypes.BOOL),
    ]


def find_locking_processes(path):
    api = ctypes.WinDLL("rstrtmgr.dll")
    api.RmStartSession.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, wintypes.LPWSTR]
    api.RmRegisterResources.argtypes = [
        wintypes.DWORD, ctypes.c_uint, ctypes.POINTER(wintypes.LPCWSTR),
        ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p,
    ]
    api.RmGetList.argtypes = [
        wintypes.DWORD, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ProcessInfo), ctypes.POINTER(wintypes.DWORD),
    ]
    api.RmEndSession.argtypes = [wintypes.DWORD]
    for name in ("RmStartSession", "RmRegisterResources", "RmGetList", "RmEndSession"):
        getattr(api, name).restype = wintypes.DWORD

    session = wintypes.DWORD()
    key = ctypes.create_unicode_buffer(uuid.uuid4().hex, 33)
    result = api.RmStartSession(ctypes.byref(session), 0, key)
    if result:
        raise ctypes.WinError(result)
    try:
        paths = (wintypes.LPCWSTR * 1)(path)
        result = api.RmRegisterResources(session, 1, paths, 0, None, 0, None)
        if result:
            raise ctypes.WinError(result)
        needed = ctypes.c_uint()
        count = ctypes.c_uint()
        reboot = wintypes.DWORD()
        result = api.RmGetList(session, ctypes.byref(needed), ctypes.byref(count), None, ctypes.byref(reboot))
        for _ in range(3):
            if result == 0 and needed.value == 0:
                return []
            if result not in (0, 234):  # ERROR_MORE_DATA
                raise ctypes.WinError(result)
            count.value = needed.value
            processes = (ProcessInfo * count.value)()
            result = api.RmGetList(session, ctypes.byref(needed), ctypes.byref(count), processes, ctypes.byref(reboot))
            if result == 0:
                return [{"pid": item.process.pid, "application": item.app_name,
                         "service": item.service_name}
                        for item in processes[:count.value]]
        raise RuntimeError("Locking processes changed repeatedly; run the query again.")
    finally:
        api.RmEndSession(session)


if __name__ == "__main__":
    print(json.dumps(find_locking_processes(sys.argv[1]), indent=2))
