import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def speech_wav(tmp_path_factory):
    """A real spoken sentence (espeak-ng), for the voice-activity and engine tests."""
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        pytest.skip("espeak-ng is not installed")
    path = tmp_path_factory.mktemp("speech") / "hello.wav"
    subprocess.run([exe, "-v", "en-us", "-s", "160", "-w", str(path),
                    "Hey Jarvis, open notepad and write a note for me please."], check=True)
    return str(path)
