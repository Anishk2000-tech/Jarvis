"""
Build the Windows installer:  installer/dist/JARVIS-Setup-<version>.exe

Works on Linux (cross-build — this is how CI does it) and on Windows.

What it assembles, in installer/build/stage/:
    python/     Python 3.12 for Windows, from the official NuGet package, with
                every library pre-installed into Lib/site-packages. The
                libraries are resolved by uv FOR WINDOWS, so dependencies that
                are only needed on Windows (pywin32, colorama…) are included
                even when this runs on Linux — plain `pip --platform` would get
                that wrong, because it evaluates environment markers for the
                machine it runs on.
    app/        the assistant (main.py, ui.py, core/, actions/, plugins/ …),
                plus the face-recognition models so face ID works offline.
    JARVIS.exe, JARVIS-Console.exe   small native launchers (installer/launcher.c)

Then NSIS compresses it into one installer (installer/jarvis.nsi).

Requirements on the build machine:
    Python 3.12 (for pre-compiling the libraries), uv (pip install uv),
    NSIS 3 (makensis), and on Linux the MinGW cross compiler
    (apt install nsis gcc-mingw-w64-x86-64).

Usage:
    python installer/build_windows.py [--version 56.0.1] [--skip-installer]
"""
from __future__ import annotations

import argparse
import compileall
import os
import platform
import py_compile
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / "installer"
BUILD = HERE / "build"
CACHE = BUILD / "cache"
STAGE = BUILD / "stage"
DIST = HERE / "dist"

PY_VERSION = "3.12.10"
NUGET_URL = f"https://api.nuget.org/v3-flatcontainer/python/{PY_VERSION}/python.{PY_VERSION}.nupkg"

APP_FILES = ["main.py", "ui.py", "ui_brain.py", "selftest.py", "readme.md", "LICENSE", "requirements.txt"]
APP_DIRS = ["core", "actions", "plugins", "memory", "config", "dashboard", "firmware"]
EXCLUDE_NAMES = {"__pycache__", "api_keys.json", "api_keys.json.tmp", "long_term.json", "schedule.json",
                 "smart_home.json", "hardware.json", "routines.json", "journal", "faces", "certs",
                 "whatsapp_web", "mcp_servers.json", "tuya_devices.json", "logs", "uploads"}
FACE_MODELS = ["face_detection_yunet_2023mar.onnx", "face_recognition_sface_2021dec.onnx"]


def log(msg: str) -> None:
    print(f"▶ {msg}", flush=True)


def run(cmd: list[str], **kw) -> None:
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def fetch(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    log(f"downloading {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    tmp.replace(dest)
    return dest


def stage_python() -> Path:
    pkg = fetch(NUGET_URL, CACHE / f"python.{PY_VERSION}.nupkg")
    target = STAGE / "python"
    if target.exists():
        shutil.rmtree(target)
    log("extracting Windows Python")
    with zipfile.ZipFile(pkg) as z:
        for m in z.infolist():
            if not m.filename.startswith("tools/") or m.is_dir():
                continue
            rel = m.filename[len("tools/"):]
            out = target / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            with z.open(m) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
    assert (target / "pythonw.exe").exists(), "pythonw.exe missing from the NuGet package"
    return target


def uv_cmd() -> list[str]:
    exe = shutil.which("uv")
    if exe:
        return [exe]
    return [sys.executable, "-m", "uv"]


def install_libraries(py_dir: Path) -> Path:
    site = py_dir / "Lib" / "site-packages"
    site.mkdir(parents=True, exist_ok=True)
    log("installing Windows libraries with uv (resolved for win_amd64 / CPython 3.12)")
    run(uv_cmd() + ["pip", "install", "--python-platform", "x86_64-pc-windows-msvc",
                    "--python-version", "3.12", "--target", str(site),
                    "--link-mode", "copy", "-r", str(HERE / "requirements-windows.txt")])
    # pywin32 needs its DLLs findable; its .pth + pywin32_bootstrap handle that
    # at start-up, but only when the .pth sits in site-packages — check it does.
    assert (site / "pywin32.pth").exists(), "pywin32.pth missing — pywin32 would not load"
    return site


_MSVC_RUNTIME = ("msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "msvcp140_atomic_wait.dll",
                 "msvcp140_codecvt_ids.dll", "concrt140.dll", "vcruntime140.dll", "vcruntime140_1.dll",
                 "vcruntime140_threads.dll")


def bundle_msvc_runtime(py_dir: Path, site: Path) -> None:
    """Put the Microsoft C++ runtime next to python.exe.

    onnxruntime, OpenCV, CTranslate2 and others need msvcp140.dll, which a
    fresh Windows only has if some program installed the Visual C++
    redistributable. The directory of the executable is always on the DLL
    search path, so app-local copies make every library load on any Windows
    10/11 — no redistributable to install. PyQt6 ships a complete,
    redistributable set of these DLLs; that set is used."""
    src = site / "PyQt6" / "Qt6" / "bin"
    copied = []
    for name in _MSVC_RUNTIME:
        if (src / name).exists():
            shutil.copy2(src / name, py_dir / name)
            copied.append(name)
    missing = {"msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"} - set(copied)
    if missing:
        raise SystemExit(f"MSVC runtime DLLs not found in PyQt6: {missing}")
    log(f"bundled the MSVC runtime next to python.exe ({len(copied)} DLLs)")


def precompile(site: Path) -> None:
    """Pre-compile the libraries so the first launch is not spent compiling.

    Only done when this interpreter IS 3.12 (bytecode is version-specific but
    OS-independent). Unchecked-hash .pyc files are used, so file timestamps
    changed by extraction do not invalidate them. The app itself is left as
    source: plugins and skills there are meant to be edited."""
    if sys.version_info[:2] != (3, 12):
        log(f"skipping pre-compilation (build Python is {sys.version_info[0]}.{sys.version_info[1]}, not 3.12)")
        return
    log("pre-compiling libraries")
    compileall.compile_dir(str(site), quiet=2, workers=0,
                           invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)


def _ignore(dirpath: str, names: list[str]) -> set[str]:
    out = {n for n in names if n in EXCLUDE_NAMES or n.endswith((".pyc", ".log", ".part", ".tmp"))}
    return out


def stage_app() -> Path:
    app = STAGE / "app"
    if app.exists():
        shutil.rmtree(app)
    app.mkdir(parents=True)
    log("copying the application")
    for f in APP_FILES:
        if (ROOT / f).exists():
            shutil.copy2(ROOT / f, app / f)
    for d in APP_DIRS:
        shutil.copytree(ROOT / d, app / d, ignore=_ignore)
    # Face-recognition models: bundled so face ID works without a download.
    faces = app / "models" / "faces"
    faces.mkdir(parents=True, exist_ok=True)
    local = ROOT / "models" / "faces"
    for name in FACE_MODELS:
        if (local / name).exists():
            shutil.copy2(local / name, faces / name)
    missing = [n for n in FACE_MODELS if not (faces / n).exists()]
    for name in missing:
        sub = "face_detection_yunet" if "yunet" in name else "face_recognition_sface"
        for base in ("https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/",
                     "https://github.com/opencv/opencv_zoo/raw/main/models/"):
            try:
                fetch(f"{base}{sub}/{name}", faces / name)
                if (faces / name).stat().st_size > 100_000:
                    break
                (faces / name).unlink()
            except Exception as e:
                log(f"face model mirror failed: {e}")
        if not (faces / name).exists():
            log(f"WARNING: {name} not bundled; it will download on first use")
    return app


def build_launchers() -> None:
    log("building JARVIS.exe launchers")
    tmp = BUILD / "launcher"
    tmp.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "config" / "jarvis.ico", tmp / "jarvis.ico")
    shutil.copy2(HERE / "launcher.rc", tmp / "launcher.rc")
    if platform.system() == "Windows":
        gcc, windres = shutil.which("gcc"), shutil.which("windres")
    else:
        gcc, windres = shutil.which("x86_64-w64-mingw32-gcc"), shutil.which("x86_64-w64-mingw32-windres")
    if not gcc or not windres:
        raise SystemExit("MinGW (gcc + windres) is needed to build the launcher "
                         "(Linux: apt install gcc-mingw-w64-x86-64)")
    run([windres, "launcher.rc", "-O", "coff", "-o", "launcher.res"], cwd=tmp)
    src = str(HERE / "launcher.c")
    run([gcc, "-O2", "-s", "-municode", "-mwindows", "-o", str(STAGE / "JARVIS.exe"), src, "launcher.res"], cwd=tmp)
    run([gcc, "-O2", "-s", "-municode", "-DCONSOLE_BUILD", "-o", str(STAGE / "JARVIS-Console.exe"), src,
         "launcher.res"], cwd=tmp)


def makensis() -> str:
    exe = shutil.which("makensis")
    if not exe and platform.system() == "Windows":
        for cand in (r"C:\Program Files (x86)\NSIS\makensis.exe", r"C:\Program Files\NSIS\makensis.exe"):
            if os.path.exists(cand):
                exe = cand
    if not exe:
        raise SystemExit("NSIS (makensis) is needed (Linux: apt install nsis; Windows: nsis.sourceforge.io)")
    return exe


def build_installer(version: str) -> Path:
    DIST.mkdir(parents=True, exist_ok=True)
    out = DIST / f"JARVIS-Setup-{version}.exe"
    log("compressing the installer with NSIS (LZMA, several minutes)")
    run([makensis(), "-V2", f"-DVERSION={version}", f"-DSTAGE={STAGE}", f"-DOUTFILE={out}",
         str(HERE / "jarvis.nsi")])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default=f"56.0.{os.environ.get('GITHUB_RUN_NUMBER', '0')}")
    ap.add_argument("--skip-installer", action="store_true", help="stage only, do not run NSIS")
    ap.add_argument("--reuse-python", action="store_true", help="keep an already staged python/")
    args = ap.parse_args()

    STAGE.mkdir(parents=True, exist_ok=True)
    py_dir = STAGE / "python"
    if not (args.reuse_python and (py_dir / "Lib" / "site-packages" / "PyQt6").exists()):
        py_dir = stage_python()
        site = install_libraries(py_dir)
        bundle_msvc_runtime(py_dir, site)
        precompile(site)
    stage_app()
    shutil.copy2(ROOT / "LICENSE", STAGE / "LICENSE.txt")
    shutil.copy2(HERE / "README-FIRST.txt", STAGE / "README-FIRST.txt")
    build_launchers()
    if args.skip_installer:
        log(f"staged in {STAGE}")
        return
    out = build_installer(args.version)
    size = out.stat().st_size / 2**20
    log(f"done: {out}  ({size:.0f} MB)")


if __name__ == "__main__":
    main()
