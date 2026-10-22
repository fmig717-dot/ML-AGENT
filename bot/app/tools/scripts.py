"""
Запуск готовых Python-скриптов из skill'ов (kp_number.py, record_draft.py,
build_buyers_xlsx.py, append_row.py) как subprocess. Разрешён только фиксированный
список скриптов — никакого произвольного кода.

Все скрипты запускаются с cwd=DATA_DIR, поэтому относительные пути внутри них
(например "output/kp_state.json" в kp_number.py) падают прямо в рабочую директорию.
"""
from __future__ import annotations

import os
import subprocess
import sys

from app.config import DATA_DIR, SKILLS_DIR

ALLOWED_SCRIPTS = {
    "kp_number": "offer-drafter/scripts/kp_number.py",
    "record_draft": "offer-drafter/scripts/record_draft.py",
    "build_buyers_xlsx": "buyer-finder/scripts/build_buyers_xlsx.py",
    "append_row": "market-supervisor/scripts/append_row.py",
}

TIMEOUT_SECONDS = 30


def list_available_scripts() -> dict:
    return {"scripts": list(ALLOWED_SCRIPTS.keys())}


def run_script(script: str, args: list[str] | None = None) -> dict:
    """
    Запускает один из разрешённых скриптов (см. list_available_scripts) с
    переданными аргументами командной строки (как в документации самого
    скрипта, см. read_skill_file на его путь).
    """
    if script not in ALLOWED_SCRIPTS:
        return {"error": f"Скрипт '{script}' не в списке разрешённых: {list(ALLOWED_SCRIPTS)}"}
    rel = ALLOWED_SCRIPTS[script]
    full_path = os.path.join(SKILLS_DIR, rel)
    if not os.path.isfile(full_path):
        return {"error": f"Файл скрипта не найден на диске: {rel}"}

    os.makedirs(DATA_DIR, exist_ok=True)
    cmd = [sys.executable, full_path] + [str(a) for a in (args or [])]
    try:
        proc = subprocess.run(
            cmd,
            cwd=DATA_DIR,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"Скрипт не завершился за {TIMEOUT_SECONDS}с"}

    return {
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-8000:],
        "stderr": proc.stderr[-4000:],
    }
