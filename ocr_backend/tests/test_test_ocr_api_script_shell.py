from pathlib import Path
import subprocess


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "test_ocr_api.sh"


def test_shell_script_exists_and_shows_usage_without_args():
    assert SCRIPT_PATH.exists()

    completed = subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
        cwd=str(SCRIPT_PATH.parent),
    )

    assert completed.returncode == 1
    assert "Usage:" in completed.stderr
    assert "bash test_ocr_api.sh <image_path>" in completed.stderr
