from pathlib import Path


def test_load_config_resolves_relative_paths_from_config_file(tmp_path):
    from ocr_backend.config import load_config

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 9001
  debug: false
paths:
  data_dir: "runtime-data"
  checkpoints_dir: "models"
ocr:
  lang: "en"
  use_angle_cls: false
  show_log: true
  min_score: 0.75
  cls_model_dir: "models/cls"
  det_model_dir: "models/det"
  rec_model_dir: "models/rec"
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.server.host == "127.0.0.1"
    assert config.server.port == 9001
    assert config.server.debug is False
    assert config.paths.data_dir == tmp_path / "runtime-data"
    assert config.paths.checkpoints_dir == tmp_path / "models"
    assert not hasattr(config.paths, "source_images_dir")
    assert config.ocr.use_angle_cls is False
    assert config.ocr.show_log is True
    assert config.ocr.min_score == 0.75
    assert config.ocr.cls_model_dir == tmp_path / "models" / "cls"
    assert config.ocr.det_model_dir == tmp_path / "models" / "det"
    assert config.ocr.rec_model_dir == tmp_path / "models" / "rec"
    assert not hasattr(config, "matching")


def test_default_config_keeps_existing_project_paths():
    from ocr_backend.config import DEFAULT_CONFIG_FILE, load_config

    project_dir = Path(__file__).resolve().parents[2]

    config = load_config(DEFAULT_CONFIG_FILE)

    assert config.paths.data_dir == project_dir / "data"
    assert config.paths.checkpoints_dir == project_dir / "checkpoints"
    assert not hasattr(config.paths, "source_images_dir")
    assert not hasattr(config, "matching")
