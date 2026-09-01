from __future__ import annotations

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
