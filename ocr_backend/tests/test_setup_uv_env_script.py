from pathlib import Path
import subprocess


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "script" / "setup-uv-env.sh"


def test_setup_uv_env_skips_when_venv_exists(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / ".venv" / "bin").mkdir(parents=True)
    (project_dir / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    (project_dir / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        cwd=project_dir,
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Virtual environment already exists" in result.stdout


def test_setup_uv_env_runs_uv_sync_when_venv_missing(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text("[project]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv_stub = bin_dir / "uv"
    marker_file = tmp_path / "uv-sync-called.txt"
    uv_stub.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "$*" > "{marker_file}"
mkdir -p .venv/bin
touch .venv/bin/python
""",
        encoding="utf-8",
    )
    uv_stub.chmod(0o755)

    result = subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        cwd=project_dir,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert marker_file.read_text(encoding="utf-8").strip() == "sync"
    assert (project_dir / ".venv" / "bin" / "python").exists()
    assert "Creating virtual environment with uv sync" in result.stdout
