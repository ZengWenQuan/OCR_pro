from pathlib import Path
import importlib.util

from PIL import Image


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "call_ocr_api.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("call_ocr_api", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_write_text_output_creates_txt_file(tmp_path):
    module = load_script_module()
    rows = [
        {
            "Content": "Hello",
            "OcrText": "Hello",
            "Score": 0.98,
            "Pos": "1,2,3,4",
            "PosRect": {"left": 1, "top": 2, "width": 3, "height": 4},
            "Points": [[1, 2], [4, 2], [4, 6], [1, 6]],
        },
        {
            "Content": "World",
            "OcrText": "World",
            "Score": 0.87,
            "Pos": "5,6,7,8",
            "PosRect": {"left": 5, "top": 6, "width": 7, "height": 8},
            "Points": [[5, 6], [12, 6], [12, 14], [5, 14]],
        },
    ]

    output_path = tmp_path / "result.txt"
    module.write_text_output(output_path, rows)

    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == (
        "[1]\n"
        "text: Hello\n"
        "ocr_text: Hello\n"
        "score: 0.98\n"
        "pos: 1,2,3,4\n"
        "pos_rect: {\"height\": 4, \"left\": 1, \"top\": 2, \"width\": 3}\n"
        "points: [[1, 2], [4, 2], [4, 6], [1, 6]]\n"
        "\n"
        "[2]\n"
        "text: World\n"
        "ocr_text: World\n"
        "score: 0.87\n"
        "pos: 5,6,7,8\n"
        "pos_rect: {\"height\": 8, \"left\": 5, \"top\": 6, \"width\": 7}\n"
        "points: [[5, 6], [12, 6], [12, 14], [5, 14]]\n"
    )


def test_draw_boxes_saves_annotated_image(tmp_path):
    module = load_script_module()
    image_path = tmp_path / "input.png"
    Image.new("RGB", (80, 60), color="white").save(image_path)

    output_path = tmp_path / "boxed.png"
    rows = [
        {
            "PosRect": {"left": 10, "top": 10, "width": 30, "height": 20},
            "Content": "Hello",
        }
    ]

    module.draw_boxes(image_path, output_path, rows)

    assert output_path.exists()
    image = Image.open(output_path)
    assert image.size == (80, 60)
    # 矩形边框应改变原本的纯白像素
    assert image.getpixel((10, 10)) != (255, 255, 255)


def test_run_creates_text_and_preview_outputs(tmp_path, monkeypatch):
    module = load_script_module()
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (100, 80), color="white").save(image_path)
    output_dir = tmp_path / "tmp"

    monkeypatch.setattr(
        module,
        "call_ocr_api",
        lambda api_base, image_path, image_name=None, page_id=None, timeout=120: {
            "rows": [
                {
                    "Content": "Hello",
                    "OcrText": "Hello",
                    "Score": 0.99,
                    "Pos": "5,6,20,10",
                    "PosRect": {"left": 5, "top": 6, "width": 20, "height": 10},
                    "Points": [[5, 6], [25, 6], [25, 16], [5, 16]],
                },
                {
                    "Content": "World",
                    "OcrText": "World",
                    "Score": 0.88,
                    "Pos": "30,20,25,12",
                    "PosRect": {"left": 30, "top": 20, "width": 25, "height": 12},
                    "Points": [[30, 20], [55, 20], [55, 32], [30, 32]],
                },
            ]
        },
    )

    text_path, preview_path = module.run(
        api_base="http://127.0.0.1:8100",
        image_path=image_path,
        output_dir=output_dir,
    )

    assert text_path == output_dir / "sample_ocr.txt"
    assert preview_path == output_dir / "sample_boxes.png"
    assert text_path.exists()
    assert preview_path.exists()
    content = text_path.read_text(encoding="utf-8")
    assert "text: Hello" in content
    assert "score: 0.99" in content
    assert "pos: 5,6,20,10" in content
    assert "points: [[30, 20], [55, 20], [55, 32], [30, 32]]" in content


def test_expand_image_inputs_supports_glob_patterns(tmp_path):
    module = load_script_module()
    (tmp_path / "a.jpg").write_bytes(b"a")
    (tmp_path / "b.png").write_bytes(b"b")
    (tmp_path / "c.txt").write_bytes(b"c")

    paths = module.expand_image_inputs(
        [str(tmp_path / "*.jpg"), str(tmp_path / "*.png")],
    )

    assert paths == [tmp_path / "a.jpg", tmp_path / "b.png"]


def test_run_many_creates_outputs_for_multiple_images(tmp_path, monkeypatch):
    module = load_script_module()
    image_a = tmp_path / "sample_a.png"
    image_b = tmp_path / "sample_b.png"
    Image.new("RGB", (60, 40), color="white").save(image_a)
    Image.new("RGB", (70, 50), color="white").save(image_b)
    output_dir = tmp_path / "tmp"

    monkeypatch.setattr(
        module,
        "call_ocr_api",
        lambda api_base, image_path, image_name=None, page_id=None, timeout=120: {
            "rows": [
                {
                    "Content": image_path.stem,
                    "OcrText": image_path.stem,
                    "Score": 0.95,
                    "Pos": "5,5,20,10",
                    "PosRect": {"left": 5, "top": 5, "width": 20, "height": 10},
                    "Points": [[5, 5], [25, 5], [25, 15], [5, 15]],
                }
            ]
        },
    )

    outputs = module.run_many(
        api_base="http://127.0.0.1:8100",
        image_paths=[image_a, image_b],
        output_dir=output_dir,
    )

    assert outputs == [
        (output_dir / "sample_a_ocr.txt", output_dir / "sample_a_boxes.png"),
        (output_dir / "sample_b_ocr.txt", output_dir / "sample_b_boxes.png"),
    ]
    assert "text: sample_a" in (output_dir / "sample_a_ocr.txt").read_text(encoding="utf-8")
    assert "text: sample_b" in (output_dir / "sample_b_ocr.txt").read_text(encoding="utf-8")
