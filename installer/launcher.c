/*
 * JARVIS.exe — starts the bundled Python on app\main.py.
 *
 * Layout next to this exe:
 *     python\pythonw.exe   python\python.exe   app\main.py
 *
 * Built twice: as a GUI program (no console window) and, with -DCONSOLE_BUILD,
 * as JARVIS-Console.exe which keeps a console open with the live log — the
 * first thing to run when something does not work.
 */
#define WIN32_LEAN_AND_MEAN
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <stdio.h>
#include <wchar.h>

#define BIG 4096

static const wchar_t *skip_program_name(const wchar_t *cmd) {
    if (!cmd) return L"";
    if (*cmd == L'"') {
        cmd++;
        while (*cmd && *cmd != L'"') cmd++;
        if (*cmd == L'"') cmd++;
    } else {
        while (*cmd && *cmd != L' ' && *cmd != L'\t') cmd++;
    }
    while (*cmd == L' ' || *cmd == L'\t') cmd++;
    return cmd;
}

static void fail(const wchar_t *what, const wchar_t *path) {
    wchar_t msg[BIG];
    DWORD err = GetLastError();
    _snwprintf(msg, BIG, L"JARVIS could not start.\n\n%ls\n%ls\n\nWindows error %lu.\n"
               L"Reinstalling JARVIS usually fixes this.", what, path, err);
    MessageBoxW(NULL, msg, L"JARVIS", MB_OK | MB_ICONERROR);
}

#ifdef CONSOLE_BUILD
int wmain(void)
#else
int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, PWSTR lpCmd, int nShow)
#endif
{
    wchar_t exe[BIG], dir[BIG], py[BIG], app[BIG], script[BIG], cmdline[BIG * 2], path[BIG * 4];
    if (!GetModuleFileNameW(NULL, exe, BIG)) return 1;
    wcscpy(dir, exe);
    wchar_t *slash = wcsrchr(dir, L'\\');
    if (slash) *slash = 0;

#ifdef CONSOLE_BUILD
    _snwprintf(py, BIG, L"%ls\\python\\python.exe", dir);
#else
    _snwprintf(py, BIG, L"%ls\\python\\pythonw.exe", dir);
#endif
    _snwprintf(app, BIG, L"%ls\\app", dir);
    _snwprintf(script, BIG, L"%ls\\main.py", app);

    if (GetFileAttributesW(py) == INVALID_FILE_ATTRIBUTES) { fail(L"The bundled Python is missing:", py); return 2; }
    if (GetFileAttributesW(script) == INVALID_FILE_ATTRIBUTES) { fail(L"The application files are missing:", script); return 3; }

    /* A clean, predictable environment: ignore any Python the user installed. */
    SetEnvironmentVariableW(L"PYTHONHOME", NULL);
    SetEnvironmentVariableW(L"PYTHONPATH", NULL);
    SetEnvironmentVariableW(L"PYTHONNOUSERSITE", L"1");
    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");
    SetEnvironmentVariableW(L"PYTHONIOENCODING", L"utf-8");
    SetEnvironmentVariableW(L"JARVIS_HOME", dir);
    SetEnvironmentVariableW(L"HF_HUB_DISABLE_SYMLINKS_WARNING", L"1");
    {
        wchar_t old[BIG * 3];
        DWORD n = GetEnvironmentVariableW(L"PATH", old, BIG * 3);
        if (n == 0 || n >= BIG * 3) old[0] = 0;
        _snwprintf(path, BIG * 4, L"%ls\\python;%ls\\python\\Scripts;%ls", dir, dir, old);
        SetEnvironmentVariableW(L"PATH", path);
    }

    const wchar_t *extra = skip_program_name(GetCommandLineW());
    _snwprintf(cmdline, BIG * 2, L"\"%ls\" -X utf8 \"%ls\" %ls", py, script, extra);

    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));
    if (!CreateProcessW(py, cmdline, NULL, NULL, FALSE, 0, NULL, app, &si, &pi)) {
        fail(L"Could not launch:", py);
        return 4;
    }
#ifdef CONSOLE_BUILD
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 0;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return (int)code;
#else
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
#endif
}
