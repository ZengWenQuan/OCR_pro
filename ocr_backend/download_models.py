from paddleocr import PaddleOCR

from ocr_backend.config import get_config


def main() -> None:
    ocr_config = get_config().ocr
    PaddleOCR(
        use_angle_cls=ocr_config.use_angle_cls,
        lang=ocr_config.lang,
        show_log=ocr_config.show_log,
        cls_model_dir=str(ocr_config.cls_model_dir),
        det_model_dir=str(ocr_config.det_model_dir),
        rec_model_dir=str(ocr_config.rec_model_dir),
    )


if __name__ == "__main__":
    main()
