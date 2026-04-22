from ocr_backend.storage import (
    DATA_DIR,
    HEADER_EN,
    HEADER_ZH,
    ensure_data_layout,
    read_result_txt,
    write_result_txt,
)


def test_ensure_data_layout_creates_template():
    ensure_data_layout()

    template_path = DATA_DIR / "ocr_result_template.txt"
    content = template_path.read_text(encoding="utf-8").splitlines()

    assert content[0].split("\t") == HEADER_ZH
    assert content[1].split("\t") == HEADER_EN


def test_write_result_txt_uses_allaudio_shape():
    txt_path = write_result_txt(
        "appendices_page15",
        [
            {
                "SoundName": "appendices_page15_audio1",
                "Content": "Please help",
                "Chinese": "",
                "Pos": "127,199,162,33",
                "Line": 1,
                "OSDAudio": "",
            }
        ],
    )

    content = txt_path.read_text(encoding="utf-8").splitlines()
    assert content[0].split("\t") == HEADER_ZH
    assert content[1].split("\t") == HEADER_EN
    assert content[2].split("\t")[0] == "appendices_page15_audio1"
    assert content[2].split("\t")[5] == "null"


def test_read_result_txt_returns_cached_rows():
    write_result_txt(
        "appendices_page16",
        [
            {
                "SoundName": "appendices_page16_audio1",
                "Content": "Look!",
                "Chinese": "",
                "Pos": "1,2,3,4",
                "Line": 1,
                "OSDAudio": "",
            }
        ],
    )

    rows = read_result_txt("appendices_page16")

    assert rows is not None
    assert rows[0]["SoundName"] == "appendices_page16_audio1"
    assert rows[0]["PosRect"] == {"left": 1, "top": 2, "width": 3, "height": 4}
    assert rows[0]["Cached"] is True
