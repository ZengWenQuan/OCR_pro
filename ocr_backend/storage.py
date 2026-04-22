from __future__ import annotations

import csv
from pathlib import Path

from ocr_backend.config import get_config

HEADER_ZH = ["音乐标示", "英文内容", "中文翻译", "位置", "行数", "原生音频"]
HEADER_EN = ["SoundName", "Content", "Chinese", "Pos", "Line", "OSDAudio"]

PROJECT_DIR = Path(__file__).resolve().parent.parent
BOOK_DIR = PROJECT_DIR.parent

# 这些常量保留给现有测试和外部调用方使用。实际函数内部会通过配置动态读取，
# 因此后续修改 config.yaml 后，只要重启进程即可改变运行路径。
DATA_DIR = get_config().paths.data_dir
TXT_DIR = DATA_DIR / "txt"
TEMPLATE_FILE = DATA_DIR / "ocr_result_template.txt"


def get_data_dir() -> Path:
    return get_config().paths.data_dir


def get_txt_dir() -> Path:
    return get_data_dir() / "txt"


def get_template_file() -> Path:
    return get_data_dir() / "ocr_result_template.txt"


def ensure_data_layout() -> None:
    get_txt_dir().mkdir(parents=True, exist_ok=True)
    template_file = get_template_file()
    if not template_file.exists():
        write_header_file(template_file)


def write_header_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(HEADER_ZH)
        writer.writerow(HEADER_EN)


def write_result_txt(stem: str, rows: list[dict[str, object]]) -> Path:
    ensure_data_layout()
    txt_path = get_txt_dir() / f"{stem}.txt"
    with txt_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(HEADER_ZH)
        writer.writerow(HEADER_EN)
        for row in rows:
            writer.writerow(
                [
                    row["SoundName"],
                    row["Content"],
                    row["Chinese"],
                    row["Pos"],
                    row["Line"],
                    row["OSDAudio"] or "null",
                ]
            )
    return txt_path


def parse_pos_text(raw_pos: str) -> dict[str, int]:
    left, top, width, height = [int(part.strip()) for part in raw_pos.split(",")]
    return {
        "left": left,
        "top": top,
        "width": width,
        "height": height,
    }


def read_result_txt(stem: str) -> list[dict[str, object]] | None:
    txt_path = get_txt_dir() / f"{stem}.txt"
    if not txt_path.exists():
        return None

    with txt_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        rows = list(reader)

    parsed_rows: list[dict[str, object]] = []
    for row in rows[2:]:
        if len(row) < 6:
            continue
        pos_rect = parse_pos_text(row[3])
        parsed_rows.append(
            {
                "SoundName": row[0],
                "Content": row[1],
                "Chinese": row[2],
                "Pos": row[3],
                "Line": int(row[4]),
                "OSDAudio": "" if row[5] == "null" else row[5],
                "Score": None,
                "Points": [],
                "PosRect": pos_rect,
                "OcrText": row[1],
                "Cached": True,
            }
        )
    return parsed_rows
