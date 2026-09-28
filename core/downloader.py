"""
Fetching model files once, safely.

Downloads go to a .part file and are renamed only when complete, so a network
drop never leaves a truncated model that then fails to load forever. Several
mirrors can be given; the first that works wins.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable, Iterable

import requests


def fetch(urls: Iterable[str] | str, dest: Path, min_bytes: int = 1024,
          progress: Callable[[str], None] | None = None, timeout: float = 60.0) -> Path:
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size >= min_bytes:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(urls, str):
        urls = [urls]
    errors = []
    for url in urls:
        part = dest.with_name(dest.name + ".part")
        try:
            with requests.get(url, stream=True, timeout=(15, timeout),
                              headers={"User-Agent": "JARVIS-assistant"}) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length") or 0)
                got, last = 0, 0.0
                with open(part, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        if not chunk:
                            continue
                        f.write(chunk)
                        got += len(chunk)
                        now = time.monotonic()
                        if progress and now - last > 2.0:
                            last = now
                            pct = f"{got * 100 // total}%" if total else f"{got >> 20} MB"
                            progress(f"Downloading {dest.name}: {pct}")
            if got < min_bytes:
                raise RuntimeError(f"only {got} bytes received")
            os.replace(part, dest)
            if progress:
                progress(f"Downloaded {dest.name} ({got >> 20} MB)")
            return dest
        except Exception as e:
            errors.append(f"{url.split('?')[0]}: {e}")
            try:
                part.unlink()
            except Exception:
                pass
    raise RuntimeError("download failed — " + " | ".join(errors))
