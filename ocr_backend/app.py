from __future__ import annotations

"""OCR 测试服务的 Flask 入口文件。

这个模块主要串起三件事：
- 对静态前端暴露 HTTP 接口；
- 在进程内缓存初始化成本高的 OCR 引擎；
- 当本地没有结果缓存时，对上传的页面图片执行 OCR，并把结果写回 data/txt。

当前请求链路是同步处理的：一次 POST /ocr 请求要么直接返回 data/txt
中已有的识别结果，要么立刻运行 PaddleOCR，并把新生成的结果写回缓存，
供后续请求复用。
"""

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from flask import Flask, jsonify, request
from flask_cors import CORS

from ocr_backend.cache_loader import format_pos
from ocr_backend.config import get_config
from ocr_backend.storage import (
    ensure_data_layout,
    read_result_txt,
    write_result_txt,
)

if TYPE_CHECKING:
    # 这里只给类型检查器使用。真正运行时的导入放在 get_ocr_engine() 里延迟执行，
    # 因为 PaddleOCR 的导入和模型初始化都比较重。
    from ocr_backend.ocr_engine import OcrEngine

# 目录结构说明：
# - BASE_DIR 指向 OCR_pro/ocr_backend
# - BOOK_DIR 指向 OCR_pro 的上级目录，保留给历史路径兼容场景使用
BASE_DIR = Path(__file__).resolve().parent
BOOK_DIR = BASE_DIR.parent.parent

# 前端是单独的静态服务，端口通常和后端不同，所以这里开启 CORS，
# 允许浏览器从前端端口请求这个 Flask 后端端口。
app = Flask(__name__)
CORS(app)

# 服务启动时创建 data/txt 和结果模板文件。
# 这样请求处理函数里就不用反复关心目录是否存在，后续读写路径也更稳定。
ensure_data_layout()


@lru_cache(maxsize=1)
def get_ocr_engine() -> "OcrEngine":
    """创建并缓存 PaddleOCR 封装对象。

    PaddleOCR 模型加载是最慢、最占内存的初始化步骤。
    lru_cache(maxsize=1) 会把这个工厂函数变成“进程内单例”：
    第一次 /ocr 请求初始化引擎，后续请求复用同一个实例。
    """

    from ocr_backend.ocr_engine import OcrEngine

    return OcrEngine()


def build_row(
    stem: str,
    index: int,
    ocr_item: dict[str, object],
) -> dict[str, object]:
    """把一条 OCR 结果转换成前端和结果 txt 共用的行结构。"""

    rect = ocr_item["rect"]

    # Pos 用 "left,top,width,height" 字符串格式保存，兼容现有 txt 配置。
    # PosRect 和 Points 保留结构化数据，方便前端画框和排查坐标问题。
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


@app.get("/health")
def health():
    """轻量级健康检查接口。"""

    return jsonify({"status": "ok"})


@app.post("/ocr")
def ocr():
    """识别一张上传的页面图片，并返回标准化后的 OCR 行数据。

    期望的 multipart/form-data 字段：
    - file：图片文件内容；
    - image_name：图片文件名，用于查缓存和生成结果文件名；
    - page_id：逻辑页面标识，例如 appendices_page14。

    处理流程会先检查 data/txt/{image_stem}.txt。如果存在，就把这个文件视为
    权威缓存结果，直接跳过 OCR。否则会把上传图片读成内存 bytes、执行 OCR，
    然后写入 data/txt 并以 JSON 返回。
    """

    # 浏览器 FormData 会把上传图片放在 request.files，把普通文本字段放在 request.form。
    file = request.files.get("file")
    image_name = request.form.get("image_name", "").strip()
    page_id = request.form.get("page_id", "").strip()

    # 正常情况下前端会显式传 image_name。如果没有传，就退回使用上传文件自带的文件名，
    # 这样直接调用接口时也能工作。
    if not image_name and file is not None:
        image_name = Path(file.filename or "").name
    if not image_name:
        return jsonify({"error": "missing image_name"}), 400

    # Path(...).name 会去掉用户输入里的目录部分，避免把缓存或保存路径写到服务目录外。
    filename = Path(image_name).name
    image_stem = Path(filename).stem

    # 如果没有传 page_id，就假设图片文件名 stem 本身符合页面命名规则，
    # 例如 appendices_page14.jpg -> appendices_page14。
    if not page_id:
        page_id = image_stem

    # 快路径：如果结果 txt 已经存在，就直接返回缓存。
    # 所以前端用同一个图片名重复点击时，不会重新跑 OCR。
    cached_rows = read_result_txt(image_stem)
    if cached_rows is not None:
        return jsonify(
            {
                "page_id": page_id,
                "count": len(cached_rows),
                "txt_path": str(get_config().paths.data_dir / "txt" / f"{image_stem}.txt"),
                "cached": True,
                "rows": cached_rows,
            }
        )

    # 只有缓存未命中时才必须上传 file。缓存命中时只需要 image_name，
    # 因为结果 txt 里已经有文本框和文字内容。
    if file is None:
        return jsonify({"error": "missing file"}), 400

    # 后端不缓存上传图片，只把本次请求中的文件读成内存 bytes 给 OCR 使用。
    # 前端预览继续使用浏览器本地的 URL.createObjectURL(file)。
    image_bytes = file.read()

    try:
        ocr_results = get_ocr_engine().recognize(image_bytes)
    except Exception as exc:
        # 即使 OCR 或模型执行失败，也保持 JSON 响应格式，方便前端展示错误信息。
        return jsonify({"error": "ocr_failed", "message": str(exc)}), 500

    rows = []
    for idx, item in enumerate(ocr_results, start=1):
        rows.append(build_row(image_stem, idx, item))

    # 把生成结果保存成 tab 分隔的 txt。之后同一个 image_stem 的请求会读取这个文件，
    # 并跳过 OCR。
    txt_path = write_result_txt(image_stem, rows)

    return jsonify(
        {
            "page_id": page_id,
            "count": len(rows),
            "txt_path": str(txt_path),
            "cached": False,
            "rows": rows,
        }
    )


if __name__ == "__main__":
    # 本地开发入口。生产环境或脚本启动通常会通过 start-ocr 脚本执行：
    # "python -m flask --app ocr_backend.app run ..."
    server_config = get_config().server
    app.run(host=server_config.host, port=server_config.port, debug=server_config.debug)
