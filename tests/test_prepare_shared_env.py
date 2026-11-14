"""La génération d'une clé ne doit ni l'afficher ni écraser un fichier existant."""

import os
import re
import stat
import subprocess
import sys
from pathlib import Path


def test_private_key_file_is_created_once_without_disclosing_key(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/prepare_shared_env.py"
    destination = tmp_path / "private.env"
    command = [sys.executable, str(script), "--file", str(destination)]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    content = destination.read_text()
    assert re.fullmatch(r"SBC_API_KEY=[A-Za-z0-9_-]{43}\n", content)
    key = content.strip().split("=", 1)[1]
    assert key not in result.stdout + result.stderr
    if os.name == "posix":
        assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode != 0
    assert destination.read_text() == content
    assert key not in result.stdout + result.stderr
