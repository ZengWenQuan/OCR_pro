from __future__ import annotations

"""OCR 服务的 FastAPI 入口文件。"""

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ocr_backend.cache_loader import format_pos
from ocr_backend.config import get_config
from ocr_backend.storage import ensure_data_layout, read_result_txt, write_result_txt

if TYPE_CHECKING:
    from ocr_backend.ocr_engine import OcrEngine

BASE_DIR = Path(__file__).resolve().parent
BOOK_DIR = BASE_DIR.parent.parent

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ensure_data_layout()


@lru_cache(maxsize=1)
def get_ocr_engine() -> "OcrEngine":
    """创建并缓存 PaddleOCR 封装对象。"""

    from ocr_backend.ocr_engine import OcrEngine

    return OcrEngine()


def build_row(
    stem: str,
    index: int,
    ocr_item: dict[str, object],
) -> dict[str, object]:
    """把一条 OCR 结果转换成前端和结果 txt 共用的行结构。"""

    rect = ocr_item["rect"]

    return {
        "SoundName": f"{stem}_audio{index}",
        "Content": ocr_item["text"],
        "Chinese": "",
        "Pos": format_pos(rect),
        "Line": 1,
        "OSDAudio": "",
        "Score": round(float(ocr_item["score"]), 4),
        "Points": ocr_item["points"],
        "PosRect": rect,
        "OcrText": ocr_item["text"],
    }


def _rect_to_points(rect: dict[str, int]) -> list[dict[str, int]]:
    left = int(rect["left"])
    top = int(rect["top"])
    width = int(rect["width"])
    height = int(rect["height"])
    return [
        {"x": left, "y": top},
        {"x": left + width, "y": top},
        {"x": left + width, "y": top + height},
        {"x": left, "y": top + height},
    ]


def build_aliyun_result(row: dict[str, object]) -> dict[str, object]:
    rect = row["PosRect"]
    raw_points = row.get("Points") or []

    if raw_points:
        points = [
            {"x": int(point[0]), "y": int(point[1])}
            for point in raw_points
            if isinstance(point, list) and len(point) >= 2
        ]
    else:
        points = _rect_to_points(rect)

    return {
        "Txt": row["Content"],
        "Pos": {
            "Top": int(rect["top"]),
            "Left": int(rect["left"]),
            "Width": int(rect["width"]),
            "Height": int(rect["height"]),
            "Points": points,
        },
    }


@app.get("/health")
def health() -> dict[str, str]:
    """轻量级健康检查接口。"""

    return {"status": "ok"}


@app.post("/ocr", response_model=None)
async def ocr(
    file: UploadFile | None = File(default=None),
    image_name: str = Form(default=""),
    page_id: str = Form(default=""),
) -> Any:
    """识别一张上传的页面图片，并返回标准化后的 OCR 行数据。"""

    image_name = image_name.strip()
    page_id = page_id.strip()

    if not image_name and file is not None:
        image_name = Path(file.filename or "").name
    if not image_name:
        return JSONResponse({"error": "missing image_name"}, status_code=400)

    filename = Path(image_name).name
    image_stem = Path(filename).stem

    if not page_id:
        page_id = image_stem

    cached_rows = read_result_txt(image_stem)
    if cached_rows is not None:
        return {
            "page_id": page_id,
            "count": len(cached_rows),
            "txt_path": str(get_config().paths.data_dir / "txt" / f"{image_stem}.txt"),
            "cached": True,
            "rows": cached_rows,
            "results": [build_aliyun_result(row) for row in cached_rows],
        }

    if file is None:
        return JSONResponse({"error": "missing file"}, status_code=400)

    image_bytes = await file.read()

    try:
        ocr_results = get_ocr_engine().recognize(image_bytes)
    except Exception as exc:
        return JSONResponse({"error": "ocr_failed", "message": str(exc)}, status_code=500)

    rows = []
    for idx, item in enumerate(ocr_results, start=1):
        rows.append(build_row(image_stem, idx, item))

    txt_path = write_result_txt(image_stem, rows)

    return {
        "page_id": page_id,
        "count": len(rows),
        "txt_path": str(txt_path),
        "cached": False,
        "rows": rows,
        "results": [build_aliyun_result(row) for row in rows],
    }
