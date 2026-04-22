from __future__ import annotations

import csv
from pathlib import Path


def derive_page_id(sound_name: str) -> str:
    parts = sound_name.split("_")
    return "_".join(parts[:2])


def parse_pos(raw_pos: str) -> dict[str, int]:
    left, top, width, height = [int(part.strip()) for part in raw_pos.split(",")]
    return {
        "left": left,
        "top": top,
        "width": width,
        "height": height,
    }


def format_pos(rect: dict[str, int]) -> str:
    return f'{rect["left"]},{rect["top"]},{rect["width"]},{rect["height"]}'


def load_audio_index(path: Path) -> dict[str, list[dict[str, object]]]:
    page_index: dict[str, list[dict[str, object]]] = {}
    with path.open("r", encoding="utf-8") as handle:
        next(handle, None)
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            sound_name = row["SoundName"]
            item = {
                "SoundName": sound_name,
                "Content": row["Content"],
                "Chinese": row["Chinese"],
                "Pos": parse_pos(row["Pos"]),
                "Line": int(row["Line"]),
                "OSDAudio": row["OSDAudio"],
            }
            page_index.setdefault(derive_page_id(sound_name), []).append(item)
    return page_index
