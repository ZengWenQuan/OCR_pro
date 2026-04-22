from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image
from paddleocr import PaddleOCR

from ocr_backend.config import AppConfig, get_config


def normalize_ocr_line(points: list[list[float]], text: str, score: float) -> dict[str, object]:
    int_points = [[int(point[0]), int(point[1])] for point in points]
    xs = [point[0] for point in int_points]
    ys = [point[1] for point in int_points]
    return {
        "text": text,
        "score": float(score),
        "points": int_points,
        "rect": {
            "left": min(xs),
            "top": min(ys),
            "width": max(xs) - min(xs),
            "height": max(ys) - min(ys),
        },
    }


class OcrEngine:
    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or get_config()
        ocr_config = self._config.ocr
        self._ocr = PaddleOCR(
            use_angle_cls=ocr_config.use_angle_cls,
            lang=ocr_config.lang,
            show_log=ocr_config.show_log,
            cls_model_dir=str(ocr_config.cls_model_dir),
            det_model_dir=str(ocr_config.det_model_dir),
            rec_model_dir=str(ocr_config.rec_model_dir),
        )

    def recognize(self, image_bytes: bytes) -> list[dict[str, object]]:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        image_array = np.array(image)
        result = self._ocr.ocr(image_array, cls=True)
        normalized: list[dict[str, object]] = []
        lines = result[0] if result else []
        for line in lines:
            if len(line) != 2:
                continue
            points, payload = line
            if len(payload) != 2:
                continue
            text, score = payload
            if float(score) < self._config.ocr.min_score:
                continue
            normalized.append(normalize_ocr_line(points, text, score))
        return normalized
