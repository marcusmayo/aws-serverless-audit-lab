from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_preview_make_target_bootstraps_pinned_runtime() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    bootstrap = (ROOT / "scripts/bootstrap_env.sh").read_text(encoding="utf-8")

    assert "preview: preview-bootstrap" in makefile
    assert "oracle: preview-bootstrap" in makefile
    assert "audit: preview-bootstrap" in makefile
    assert 'requirements_file="${repo_root}/requirements.txt"' in bootstrap
    assert 'probe="import yaml"' in bootstrap


def test_codespaces_post_create_uses_the_same_bootstrap() -> None:
    devcontainer = (ROOT / ".devcontainer/devcontainer.json").read_text(encoding="utf-8")

    assert "bash scripts/bootstrap_env.sh dev" in devcontainer
