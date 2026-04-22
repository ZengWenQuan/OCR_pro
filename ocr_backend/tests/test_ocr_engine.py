from io import BytesIO

import numpy as np
from PIL import Image

from ocr_backend.ocr_engine import OcrEngine


def test_recognize_converts_image_bytes_to_numpy_array():
    image = Image.new("RGB", (20, 10), "white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    seen = {}

    class StubModel:
        def ocr(self, img, cls=True):
            seen["img_type"] = type(img)
            seen["shape"] = getattr(img, "shape", None)
            return [[]]

    engine = OcrEngine.__new__(OcrEngine)
    engine._ocr = StubModel()

    result = engine.recognize(buffer.getvalue())

    assert result == []
    assert seen["img_type"] is np.ndarray
    assert seen["shape"] == (10, 20, 3)


def test_recognize_filters_results_below_configured_min_score():
    image = Image.new("RGB", (20, 10), "white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    class StubModel:
        def ocr(self, img, cls=True):
            return [
                [
                    (
                        [[1, 2], [11, 2], [11, 12], [1, 12]],
                        ("Keep me", 0.95),
                    ),
                    (
                        [[2, 3], [12, 3], [12, 13], [2, 13]],
                        ("Drop me", 0.49),
                    ),
                ]
            ]

    class StubOcrConfig:
        min_score = 0.5

    class StubConfig:
        ocr = StubOcrConfig()

    engine = OcrEngine.__new__(OcrEngine)
    engine._ocr = StubModel()
    engine._config = StubConfig()

    result = engine.recognize(buffer.getvalue())

    assert [item["text"] for item in result] == ["Keep me"]
