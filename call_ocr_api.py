#!/usr/bin/env python3

from __future__ import annotations

import argparse
import glob
import json
import mimetypes
import uuid
from pathlib import Path
from urllib import error, request

from PIL import Image, ImageDraw


DEFAULT_API_BASE = "http://127.0.0.1:8100"
DEFAULT_TIMEOUT = 120
PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "tmp"


def build_multipart_body(
    image_path: Path,
    image_name: str,
    page_id: str,
) -> tuple[bytes, str]:
    boundary = f"----OCRBoundary{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(image_name)[0] or "application/octet-stream"
    image_bytes = image_path.read_bytes()

    parts = [
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image_name"\r\n\r\n'
            f"{image_name}\r\n"
        ).encode("utf-8"),
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="page_id"\r\n\r\n'
            f"{page_id}\r\n"
        ).encode("utf-8"),
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{image_name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8"),
        image_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]

    return b"".join(parts), boundary


def call_ocr_api(
    api_base: str,
    image_path: Path,
    image_name: str | None = None,
    page_id: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, object]:
    image_name = image_name or image_path.name
    page_id = page_id or image_path.stem
    body, boundary = build_multipart_body(image_path, image_name, page_id)

    req = request.Request(
        url=f"{api_base.rstrip('/')}/ocr",
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
    )

    try:
        with request.urlopen(req, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OCR request failed: HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OCR request failed: {exc.reason}") from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OCR response is not valid JSON: {payload}") from exc


def write_text_output(output_path: Path, rows: list[dict[str, object]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for index, row in enumerate(rows, start=1):
        lines.append(f"[{index}]")
        lines.append(f"text: {str(row.get('Content') or '').strip()}")
        lines.append(f"ocr_text: {str(row.get('OcrText') or '').strip()}")
        lines.append(f"score: {row.get('Score')}")
        lines.append(f"pos: {str(row.get('Pos') or '').strip()}")
        lines.append(
            "pos_rect: "
            + json.dumps(row.get("PosRect") or {}, ensure_ascii=False, sort_keys=True)
        )
        lines.append(
            "points: "
            + json.dumps(row.get("Points") or [], ensure_ascii=False)
        )
        if index != len(rows):
            lines.append("")
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def draw_boxes(image_path: Path, output_path: Path, rows: list[dict[str, object]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)

    for row in rows:
        rect = row.get("PosRect") or {}
        left = int(rect.get("left", 0))
        top = int(rect.get("top", 0))
        width = int(rect.get("width", 0))
        height = int(rect.get("height", 0))
        if width <= 0 or height <= 0:
            continue
        draw.rectangle(
            [(left, top), (left + width, top + height)],
            outline="red",
            width=3,
        )

    image.save(output_path)


def run(
    api_base: str,
    image_path: Path,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    image_name: str | None = None,
    page_id: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[Path, Path]:
    payload = call_ocr_api(
        api_base=api_base,
        image_path=image_path,
        image_name=image_name,
        page_id=page_id,
        timeout=timeout,
    )
    rows = payload.get("rows", [])
    if not isinstance(rows, list):
        raise RuntimeError("OCR response rows is not a list")

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(image_name or image_path.name).stem
    text_path = output_dir / f"{stem}_ocr.txt"
    preview_path = output_dir / f"{stem}_boxes.png"

    write_text_output(text_path, rows)
    draw_boxes(image_path, preview_path, rows)

    return text_path, preview_path


def run_many(
    api_base: str,
    image_paths: list[Path],
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[tuple[Path, Path]]:
    outputs = []
    for image_path in image_paths:
        outputs.append(
            run(
                api_base=api_base,
                image_path=image_path,
                output_dir=output_dir,
                timeout=timeout,
            )
        )
    return outputs


def expand_image_inputs(patterns: list[str]) -> list[Path]:
    resolved: list[Path] = []
    seen: set[Path] = set()

    for pattern in patterns:
        matches = sorted(Path(path).resolve() for path in glob.glob(pattern, recursive=True))
        if not matches:
            candidate = Path(pattern).expanduser().resolve()
            if candidate.exists():
                matches = [candidate]
        for match in matches:
            if match.is_file() and match not in seen:
                resolved.append(match)
                seen.add(match)

    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="调用 OCR 接口，保存识别文本和带框预览图到 tmp 目录。",
    )
    parser.add_argument("image", nargs="?", help="单张本地图片路径")
    parser.add_argument(
        "--images",
        nargs="+",
        help="批量图片路径或通配模式，例如 --images 'tmp/*.jpg' 'tmp/*.png'",
    )
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="OCR 接口地址")
    parser.add_argument("--image-name", help="传给后端的 image_name，默认使用图片文件名")
    parser.add_argument("--page-id", help="传给后端的 page_id，默认使用图片文件名 stem")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="输出目录，默认是 ./tmp")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="请求超时时间，单位秒")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()

    if args.images:
        image_paths = expand_image_inputs(args.images)
        if not image_paths:
            raise SystemExit("没有匹配到任何图片")
        outputs = run_many(
            api_base=args.api_base,
            image_paths=image_paths,
            output_dir=output_dir,
            timeout=args.timeout,
        )
        for text_path, preview_path in outputs:
            print(f"文本结果已保存: {text_path}")
            print(f"带框图片已保存: {preview_path}")
        return 0

    if not args.image:
        raise SystemExit("请传入 image，或者使用 --images 批量指定图片")

    image_path = Path(args.image).expanduser().resolve()
    if not image_path.exists():
        raise SystemExit(f"图片不存在: {image_path}")

    text_path, preview_path = run(
        api_base=args.api_base,
        image_path=image_path,
        output_dir=output_dir,
        image_name=args.image_name,
        page_id=args.page_id,
        timeout=args.timeout,
    )

    print(f"文本结果已保存: {text_path}")
    print(f"带框图片已保存: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
