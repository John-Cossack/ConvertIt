"""Extract application files from a signed MSI without running Windows Installer."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import sys
import tempfile

msi = ctypes.WinDLL("msi")
Handle = wintypes.UINT
msi.MsiOpenDatabaseW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.POINTER(Handle)]
msi.MsiDatabaseOpenViewW.argtypes = [Handle, wintypes.LPCWSTR, ctypes.POINTER(Handle)]
msi.MsiRecordGetStringW.argtypes = [Handle, wintypes.UINT, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
msi.MsiRecordReadStream.argtypes = [Handle, wintypes.UINT, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]


def check(code):
    if code:
        raise OSError(f"Windows MSI API error {code}")


def field(record, number):
    size = wintypes.DWORD(0)
    status = msi.MsiRecordGetStringW(record, number, None, ctypes.byref(size))
    if status not in (0, 234):
        check(status)
    size.value += 1
    buffer = ctypes.create_unicode_buffer(size.value)
    check(msi.MsiRecordGetStringW(record, number, buffer, ctypes.byref(size)))
    return buffer.value


def records(database, sql):
    view = Handle()
    check(msi.MsiDatabaseOpenViewW(database, sql, ctypes.byref(view)))
    check(msi.MsiViewExecute(view, 0))
    try:
        while True:
            record = Handle()
            status = msi.MsiViewFetch(view, ctypes.byref(record))
            if status == 259:
                break
            check(status)
            try:
                yield record
            finally:
                msi.MsiCloseHandle(record)
    finally:
        msi.MsiCloseHandle(view)


def extract(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    workspace = Path(__file__).resolve().parent.parent
    if not destination.is_relative_to(workspace / "third-party"):
        raise ValueError("Extraction must stay inside this workspace's third-party directory")
    database = Handle()
    check(msi.MsiOpenDatabaseW(str(source), None, ctypes.byref(database)))
    try:
        directories = {field(r, 1): (field(r, 2), field(r, 3)) for r in records(database, "SELECT `Directory`, `Directory_Parent`, `DefaultDir` FROM `Directory`")}
        components = {field(r, 1): field(r, 2) for r in records(database, "SELECT `Component`, `Directory_` FROM `Component`")}
        files = [(field(r, 1), field(r, 2), field(r, 3)) for r in records(database, "SELECT `File`, `Component_`, `FileName` FROM `File`")]
        cabinets = [field(r, 1).lstrip("#") for r in records(database, "SELECT `Cabinet` FROM `Media`") if field(r, 1)]
        root_id = "INSTALLLOCATION" if "INSTALLLOCATION" in directories else "TARGETDIR"
        def folder(key, seen=None):
            if key == root_id:
                return destination
            seen = set() if seen is None else seen
            if not key or key not in directories or key in seen:
                return None
            seen.add(key)
            parent, name = directories[key]
            base = folder(parent, seen)
            if base is None:
                return None
            name = name.split(":", 1)[0].split("|")[-1]
            result = (base / name).resolve() if name != "." else base
            if not result.is_relative_to(destination):
                raise ValueError("Invalid MSI directory")
            return result
        destination.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="msi-extract-", dir=workspace / "third-party") as temporary:
            temporary = Path(temporary)
            raw = temporary / "raw"
            raw.mkdir()
            for name in cabinets:
                cabinet = temporary / Path(name).name
                sql_name = name.replace("'", "''")
                for record in records(database, f"SELECT `Name`, `Data` FROM `_Streams` WHERE `Name`='{sql_name}'"):
                    with cabinet.open("wb") as file:
                        buffer = ctypes.create_string_buffer(65536)
                        while True:
                            size = wintypes.DWORD(len(buffer))
                            check(msi.MsiRecordReadStream(record, 2, buffer, ctypes.byref(size)))
                            if not size.value:
                                break
                            file.write(buffer.raw[:size.value])
                subprocess.run([str(Path('C:/Windows/System32/expand.exe')), "-F:*", str(cabinet), str(raw)], check=True, stdout=subprocess.DEVNULL)
            count = 0
            for key, component, name in files:
                base = folder(components[component])
                if base is None:
                    continue
                target = (base / name.split("|")[-1]).resolve()
                origin = (raw / key).resolve()
                if not target.is_relative_to(destination) or not origin.is_relative_to(raw):
                    raise ValueError("Invalid MSI file")
                target.parent.mkdir(parents=True, exist_ok=True)
                origin.replace(target)
                count += 1
        print(f"Extracted {count} application files to {destination}")
    finally:
        msi.MsiCloseHandle(database)


if __name__ == "__main__":
    extract(sys.argv[1], sys.argv[2])
