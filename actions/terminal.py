"""
terminal — run PowerShell, cmd, bash or Python on this machine.

This is what turns "operate my computer" from a list of canned actions into
anything a person at a keyboard could do: install software with winget, find
large files, kill a frozen process, check the IP address, batch-rename photos,
query the battery, schedule a backup, write and run a quick script.

Safety
------
Commands are classified before they run. Anything destructive or hard to
reverse — formatting, recursive deletes, registry deletes, shadow-copy removal,
disabling security, user-account changes, download-and-execute — is NOT run
directly: it goes through core/confirm.py, which puts a banner on the HUD and
waits for the user to press CONFIRM or say "confirm". The model cannot confirm
on the user's behalf. Everything else runs at once, like any other tool.
"""
from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from core import confirm as confirm_gate

_IS_WIN = platform.system() == "Windows"
_MAX_OUT = 6000

_DANGER = [
    (r"\bformat(-volume)?\b\s+[a-z]:?", "formats a drive"),
    (r"\bdiskpart\b", "edits disk partitions"),
    (r"\b(remove|clear|initialize)-(partition|disk)\b", "edits disk partitions"),
    (r"\brm\s+(-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r)\b", "deletes recursively"),
    (r"\brm\s+-r\b", "deletes recursively"),
    (r"\b(rd|rmdir)\s+/s\b", "deletes a folder tree"),
    (r"\bdel\s+(/[a-z]\s+)*/s\b", "deletes files recursively"),
    (r"\bremove-item\b.*-recurse", "deletes a folder tree"),
    (r"\b(reg|reg\.exe)\s+delete\b", "deletes registry keys"),
    (r"\bremove-item(property)?\b.*\bhk(lm|cu|cr|u|cc):", "deletes registry keys"),
    (r"\bbcdedit\b", "changes the boot configuration"),
    (r"\bvssadmin\b.*\bdelete\b|\bwmic\b.*shadowcopy.*delete", "deletes backups (shadow copies)"),
    (r"\bcipher\s+/w\b", "wipes free disk space"),
    (r"\bset-mppreference\b.*disable|\bdisable-windowsoptionalfeature\b", "disables security features"),
    (r"\bnetsh\s+advfirewall\s+set\b.*\boff\b", "turns off the firewall"),
    (r"\bnet\s+user\b.*\s/(add|delete)\b|\bnet\s+localgroup\s+administrators\b",
     "changes user accounts"),
    (r"\b(new|remove)-localuser\b", "changes user accounts"),
    (r"\btakeown\b|\bicacls\b.*\b(grant|reset)\b", "changes file ownership / permissions"),
    (r"\b(shutdown|stop-computer|restart-computer)\b", "shuts down or restarts the computer"),
    (r"\b(iwr|irm|invoke-webrequest|invoke-restmethod|curl|wget)\b.*\|\s*(iex|invoke-expression|sh|bash|python)",
     "downloads and runs code from the internet"),
    (r"\bset-executionpolicy\b\s+(unrestricted|bypass)", "lowers script security"),
    (r"\bclear-recyclebin\b|\brd\s+/s\s+.*\$recycle", "empties the recycle bin"),
    (r"\bmkfs\b|\bdd\s+if=", "overwrites a disk"),
    (r":\(\)\s*\{\s*:\|:&\s*\};:", "fork bomb"),
    (r"\bschtasks\b.*\s/delete\b", "deletes scheduled tasks"),
    (r"\bsc(\.exe)?\s+(delete|config)\b", "changes Windows services"),
    (r"\bstop-process\b.*\b(csrss|winlogon|lsass|svchost|explorer)\b|\btaskkill\b.*\b(csrss|winlogon|lsass|svchost)\b",
     "kills a critical system process"),
]
_PY_DANGER = [
    (r"shutil\.rmtree\(", "deletes a folder tree"),
    (r"os\.(remove|unlink|rmdir)\(|Path\([^)]*\)\.unlink\(", "deletes files"),
    (r"subprocess|os\.system|os\.popen", "runs shell commands"),
    (r"winreg\.(Delete|Set)", "edits the registry"),
]


def classify(command: str, shell: str) -> str:
    """'' when safe to run directly, else a short reason it needs confirmation."""
    text = (command or "").lower()
    rules = _PY_DANGER if shell == "python" else _DANGER
    for pat, why in rules:
        if re.search(pat, text, re.I):
            return why
    if shell != "python":
        # Deleting inside Windows / Program Files / a drive root is never casual.
        if re.search(r"\b(del|erase|remove-item|rm|rmdir|rd)\b", text) and re.search(
                r"([a-z]:\\(windows|program files|programdata)\b|[a-z]:\\\s*$|[a-z]:\\\*|\s/\s*$|system32)",
                text):
            return "deletes system files"
    return ""


def _default_shell() -> str:
    return "powershell" if _IS_WIN else "bash"


def _argv(command: str, shell: str) -> tuple[list[str], str | None]:
    tmp = None
    if shell == "python":
        fd, tmp = tempfile.mkstemp(suffix=".py", prefix="jarvis_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(command)
        return [sys.executable, "-X", "utf8", tmp], tmp
    if shell == "cmd":
        return ["cmd.exe", "/d", "/s", "/c", "chcp 65001>nul & " + command], None
    if shell in ("powershell", "pwsh"):
        exe = "powershell.exe" if shell == "powershell" else "pwsh.exe"
        pre = ("$ProgressPreference='SilentlyContinue';"
               "[Console]::OutputEncoding=[Text.Encoding]::UTF8;$OutputEncoding=[Text.Encoding]::UTF8;")
        return [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-Command", pre + command], None
    return ["/bin/bash", "-lc", command], None


def run_command(command: str, shell: str = "", timeout: float = 60, cwd: str = "",
                background: bool = False) -> str:
    shell = (shell or _default_shell()).lower()
    if not _IS_WIN and shell in ("powershell", "cmd"):
        shell = "bash"
    workdir = Path(os.path.expandvars(os.path.expanduser(cwd))) if cwd else Path.home()
    if not workdir.is_dir():
        return f"The folder '{cwd}' does not exist."
    argv, tmp = _argv(command, shell)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    kw: dict = {"cwd": str(workdir), "env": env}
    if _IS_WIN:
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        if background:
            p = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 stdin=subprocess.DEVNULL, **kw)
            return f"Started in the background (process id {p.pid})."
        r = subprocess.run(argv, capture_output=True, timeout=max(1, min(900, float(timeout or 60))),
                           stdin=subprocess.DEVNULL, **kw)
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", errors="replace")
        return f"Timed out after {timeout}s. Partial output:\n{out[-_MAX_OUT:]}"
    except FileNotFoundError as e:
        return f"The shell could not be started: {e}"
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except Exception:
                pass
    out = r.stdout.decode("utf-8", errors="replace").strip()
    err = r.stderr.decode("utf-8", errors="replace").strip()
    text = out
    if err:
        text += ("\n" if text else "") + "[stderr]\n" + err
    if len(text) > _MAX_OUT:
        text = text[:_MAX_OUT // 3] + "\n…[output truncated]…\n" + text[-(_MAX_OUT * 2 // 3):]
    status = "OK" if r.returncode == 0 else f"exit code {r.returncode}"
    return f"[{status}]\n{text or '(no output)'}"


def terminal(parameters: dict, player=None) -> str:
    p = parameters or {}
    command = str(p.get("command") or p.get("code") or "").strip()
    if not command:
        return "No command given."
    shell = str(p.get("shell") or "").lower().strip() or _default_shell()
    if shell in ("ps", "pwsh7"):
        shell = "pwsh"
    try:
        timeout = float(p.get("timeout") or 60)
    except (TypeError, ValueError):
        timeout = 60
    cwd = str(p.get("cwd") or "")
    background = bool(p.get("background"))
    if player:
        try:
            player.write_log(f"[Terminal] {shell}> {command[:160]}")
        except Exception:
            pass

    why = classify(command, shell)
    if why:
        def run_confirmed() -> str:
            result = run_command(command, shell, timeout, cwd, background)
            try:
                from core import runtime
                runtime.inject(f"[TOOL_RESULT] The confirmed command finished. Tell the user the "
                               f"outcome in one or two sentences:\n{result[:1500]}")
            except Exception:
                pass
            return result[:200]
        return confirm_gate.request(
            key="terminal", title=f"Run a command that {why}?",
            detail=command[:280], run=run_confirmed)
    return run_command(command, shell, timeout, cwd, background)


TOOL = {
    "name": "terminal",
    "description": (
        "Run a command on this computer and get its output: PowerShell (default on Windows), "
        "cmd, bash, or a Python script. Use for anything scriptable — system information, "
        "installing apps (winget install …), processes (Get-Process / Stop-Process), network "
        "(ipconfig, ping), disk usage, finding files, bulk file operations, services, "
        "environment, running programs or scripts. Destructive commands ask the user to "
        "confirm first. Prefer specific tools (open_app, file_controller) for simple tasks."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "command": {"type": "STRING", "description": "The command line, or Python source when shell=python"},
            "shell": {"type": "STRING", "description": "powershell | cmd | pwsh | bash | python"},
            "cwd": {"type": "STRING", "description": "Working folder (default: home)"},
            "timeout": {"type": "INTEGER", "description": "Seconds to wait (default 60, max 900)"},
            "background": {"type": "BOOLEAN", "description": "Start it and return immediately"},
        },
        "required": ["command"],
    },
    "handler": terminal,
}
