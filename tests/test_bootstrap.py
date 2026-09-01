from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_preview_make_target_bootstraps_pinned_runtime() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    bootstrap = (ROOT / "scripts/bootstrap_env.sh").read_text(encoding="utf-8")

    assert "preview: preview-bootstrap" in makefile
    assert "preview-start: preview-bootstrap" in makefile
    assert "oracle: preview-start" in makefile
    assert "audit: preview-bootstrap" in makefile
    assert 'requirements_file="${repo_root}/requirements.txt"' in bootstrap
    assert 'probe="import yaml"' in bootstrap


def test_codespaces_starts_a_valid_sam_feature_and_live_preview() -> None:
    devcontainer = (ROOT / ".devcontainer/devcontainer.json").read_text(encoding="utf-8")

    assert "bash scripts/bootstrap_env.sh dev" in devcontainer
    assert "codespaces-features/sam-cli:1.2.0" in devcontainer
    assert "codespaces-features/aws-sam-cli" not in devcontainer
    assert "bash scripts/preview_server.sh start" in devcontainer
    assert '"onAutoForward": "openBrowser"' in devcontainer


def test_preview_bootstrap_repairs_a_venv_with_python_but_no_pip(tmp_path: Path) -> None:
    broken_venv = tmp_path / "broken-venv"
    subprocess.run(  # noqa: S603 - fixed interpreter and isolated temporary target
        [sys.executable, "-m", "venv", "--without-pip", str(broken_venv)],
        check=True,
        capture_output=True,
        text=True,
    )
    broken_python = broken_venv / "bin" / "python"
    purelib_result = subprocess.run(  # noqa: S603 - fixed temporary interpreter
        [
            str(broken_python),
            "-c",
            "import sysconfig; print(sysconfig.get_path('purelib'))",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    purelib = Path(purelib_result.stdout.strip())
    (purelib / "yaml.py").write_text("__version__ = 'test'\n", encoding="utf-8")
    missing_pip = subprocess.run(  # noqa: S603 - fixed temporary interpreter
        [str(broken_python), "-m", "pip", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert missing_pip.returncode != 0

    environment = os.environ.copy()
    environment["VENV_DIR"] = str(broken_venv)
    repaired = subprocess.run(  # noqa: S603 - repository-owned script with fixed arguments
        ["/bin/bash", str(ROOT / "scripts" / "bootstrap_env.sh"), "preview"],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Repairing pip in incomplete isolated environment" in repaired.stdout
    subprocess.run(  # noqa: S603 - fixed temporary interpreter
        [str(broken_python), "-m", "pip", "--version"],
        check=True,
        capture_output=True,
        text=True,
    )

    repeated = subprocess.run(  # noqa: S603 - repository-owned script with fixed arguments
        ["/bin/bash", str(ROOT / "scripts" / "bootstrap_env.sh"), "preview"],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Repairing pip in incomplete isolated environment" not in repeated.stdout
    assert "Installing pinned preview dependencies" not in repeated.stdout
