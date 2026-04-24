from __future__ import annotations

"""OCR 服务的 FastAPI 入口文件。

这个文件只负责 HTTP 层的事情：
1. 接收图片上传请求；
2. 调用 `OcrEngine` 做识别；
3. 把识别结果整理成项目内部格式和阿里云兼容格式；
4. 把结果写回缓存目录，供下次请求直接复用。
"""

import inspect
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

# `BASE_DIR` 是 `ocr_backend/` 目录。
# `BOOK_DIR` 保留给一些历史路径兼容场景，当前主要用于调试和排查。
BASE_DIR = Path(__file__).resolve().parent
BOOK_DIR = BASE_DIR.parent.parent

# FastAPI 应用实例。
# 这里用它对外提供 `/health` 和 `/ocr` 两个接口。
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 启动时先把缓存目录准备好，避免第一个请求进来时才临时建目录。
ensure_data_layout()


@lru_cache(maxsize=1)
def get_ocr_engine() -> "OcrEngine":
    """创建并缓存 PaddleOCR 封装对象。

    `PaddleOCR` 初始化很重，模型加载和内存占用都不低。
    这里用 `lru_cache(maxsize=1)` 做成进程内单例，第一次请求创建，
    后续请求复用同一个引擎对象。
    """

    from ocr_backend.ocr_engine import OcrEngine

    return OcrEngine()


def build_row(
    stem: str,
    index: int,
    ocr_item: dict[str, object],
) -> dict[str, object]:
    """把一条 OCR 结果转换成项目内部统一的行结构。

    这个结构主要给两类地方使用：
    1. 写入 `data/txt/*.txt` 缓存文件；
    2. 前端调试页和测试脚本直接展示。

    其中：
    - `Content` 是文本内容；
    - `Pos` 是 `left,top,width,height` 字符串；
    - `PosRect` 和 `Points` 保留结构化坐标，方便画框和做兼容转换。
    """

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
    # 缓存命中时，`read_result_txt()` 只恢复矩形框，不一定有四角点。
    # 这里把矩形框补成四个点，方便下游继续按阿里云格式使用。
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
    # 下游原来是按阿里云 OCR 的返回格式取数据，所以这里做一个兼容层。
    # 兼容后的结构是：
    # {
    #   "Txt": "xxx",
    #   "Pos": {
    #       "Top": ...,
    #       "Left": ...,
    #       "Width": ...,
    #       "Height": ...,
    #       "Points": [...]
    #   }
    # }
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
    """轻量级健康检查接口。

    这个接口只返回 `{"status": "ok"}`，用于确认服务是否启动成功。
    """

    return {"status": "ok"}


@app.post("/ocr", response_model=None)
async def ocr(
    file: UploadFile | None = File(default=None),
    image_name: str = Form(default=""),
    page_id: str = Form(default=""),
) -> Any:
    """识别一张上传的页面图片，并返回标准化后的 OCR 行数据。

    接收参数：
    - `file`：图片文件，必填于缓存未命中时；
    - `image_name`：图片文件名，可选，不传时回退到上传文件名；
    - `page_id`：页面标识，可选，不传时默认使用图片 stem。

    返回值：
    - `cached`：是否命中本地 txt 缓存；
    - `count`：识别到的文本块数量；
    - `txt_path`：缓存 txt 文件路径；
    - `rows`：项目内部使用的 OCR 行数据；
    - `results`：阿里云兼容的 OCR 结果。
    """

    image_name = image_name.strip()
    page_id = page_id.strip()
    image_bytes: bytes | None = None

    local_path: Path | None = None
    upload_file: Any | None = None
    if isinstance(file, (str, Path)):
        local_path = Path(file).expanduser()
    elif file is not None and callable(getattr(file, "read", None)):
        upload_file = file

    if not image_name and upload_file is not None:
        upload_name = getattr(upload_file, "filename", "") or getattr(upload_file, "name", "")
        image_name = Path(str(upload_name)).name
    if not image_name and local_path is not None:
        image_name = local_path.name
    if not image_name:
        # 没有图片名时，没法确定缓存文件名，也没法继续处理。
        return JSONResponse({"error": "missing image_name"}, status_code=400)

    filename = Path(image_name).name
    image_stem = Path(filename).stem

    if not page_id:
        # 没传 page_id 时，直接用文件名 stem 作为页面标识。
        page_id = image_stem

    # 优先读缓存：如果 `data/txt/{stem}.txt` 已经存在，就直接返回，
    # 不再跑 PaddleOCR。
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

    if upload_file is None and local_path is None:
        # 缓存未命中时，必须有图片本体才能做 OCR。
        return JSONResponse({"error": "missing file"}, status_code=400)

    if local_path is not None:
        # 允许直接传本地图片路径，内部仍统一转成 bytes 走后续 OCR 流程。
        try:
            image_bytes = local_path.read_bytes()
        except OSError as exc:
            return JSONResponse(
                {"error": "missing file", "message": str(exc)},
                status_code=400,
            )
    elif upload_file is not None:
        # 只在缓存未命中时读取上传图片的 bytes，传给 PaddleOCR 引擎。
        maybe_image_bytes = upload_file.read()
        if inspect.isawaitable(maybe_image_bytes):
            image_bytes = await maybe_image_bytes
        else:
            image_bytes = maybe_image_bytes

    try:
        # 真正的 OCR 推理在 `OcrEngine.recognize()` 里。
        ocr_results = get_ocr_engine().recognize(image_bytes)
    except Exception as exc:
        # OCR 失败时保持 JSON 错误格式，方便前端和测试脚本统一处理。
        return JSONResponse({"error": "ocr_failed", "message": str(exc)}, status_code=500)

    # 把 PaddleOCR 的原始结果转成项目内部行结构。
    rows = []
    for idx, item in enumerate(ocr_results, start=1):
        rows.append(build_row(image_stem, idx, item))

    # 写入 `data/txt/{stem}.txt`，下一次相同图片名可直接命中缓存。
    txt_path = write_result_txt(image_stem, rows)

    # 同时返回内部格式 `rows` 和下游兼容格式 `results`。
    return {
        "page_id": page_id,
        "count": len(rows),
        "txt_path": str(txt_path),
        "cached": False,
        "rows": rows,
        "results": [build_aliyun_result(row) for row in rows],
    }
