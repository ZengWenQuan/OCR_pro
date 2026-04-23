from io import BytesIO

from fastapi.testclient import TestClient

from ocr_backend.app import app


def test_ocr_endpoint_returns_json_error_when_engine_fails(monkeypatch):
    monkeypatch.setattr("ocr_backend.app.read_result_txt", lambda stem: None)
    monkeypatch.setattr(
        "ocr_backend.app.get_ocr_engine",
        lambda: type(
            "StubEngine",
            (),
            {"recognize": lambda self, image_bytes: (_ for _ in ()).throw(RuntimeError("boom"))},
        )(),
    )
    client = TestClient(app)

    response = client.post(
        "/ocr",
        data={"page_id": "appendices_page14", "image_name": "page14.png"},
        files={"file": ("page14.png", BytesIO(b"fake-image"), "image/png")},
    )

    body = response.json()
    assert response.status_code == 500
    assert body["error"] == "ocr_failed"
    assert "boom" in body["message"]


def test_ocr_endpoint_writes_txt_without_caching_image(monkeypatch):
    monkeypatch.setattr("ocr_backend.app.read_result_txt", lambda stem: None)
    monkeypatch.setattr(
        "ocr_backend.app.save_uploaded_image",
        lambda filename, image_bytes: (_ for _ in ()).throw(RuntimeError("should not cache image")),
        raising=False,
    )
    monkeypatch.setattr(
        "ocr_backend.app.get_ocr_engine",
        lambda: type(
            "StubEngine",
            (),
            {
                "recognize": lambda self, image_bytes: [
                    {
                        "text": "Where is Mum?",
                        "score": 0.99,
                        "points": [[231, 309], [669, 309], [669, 395], [231, 395]],
                        "rect": {"left": 231, "top": 309, "width": 438, "height": 86},
                    }
                ]
            },
        )(),
    )
    client = TestClient(app)

    response = client.post(
        "/ocr",
        data={"page_id": "appendices_page14", "image_name": "appendices_page14.jpg"},
        files={"file": ("appendices_page14.jpg", BytesIO(b"fake-image"), "image/jpeg")},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["cached"] is False
    assert body["rows"][0]["SoundName"] == "appendices_page14_audio1"
    assert body["rows"][0]["Content"] == "Where is Mum?"
    assert body["rows"][0]["Chinese"] == ""
    assert body["rows"][0]["OSDAudio"] == ""
    assert body["results"] == [
        {
            "Txt": "Where is Mum?",
            "Pos": {
                "Top": 309,
                "Left": 231,
                "Width": 438,
                "Height": 86,
                "Points": [
                    {"x": 231, "y": 309},
                    {"x": 669, "y": 309},
                    {"x": 669, "y": 395},
                    {"x": 231, "y": 395},
                ],
            },
        }
    ]
    assert "image_path" not in body
    assert "image_url" not in body


def test_ocr_endpoint_reads_cached_txt_without_engine(monkeypatch):
    monkeypatch.setattr(
        "ocr_backend.app.read_result_txt",
        lambda stem: [
            {
                "SoundName": "appendices_page14_audio1",
                "Content": "Where is Mum?",
                "Chinese": "",
                "Pos": "1,2,3,4",
                "Line": 1,
                "OSDAudio": "",
                "Score": None,
                "Points": [],
                "PosRect": {"left": 1, "top": 2, "width": 3, "height": 4},
                "OcrText": "Where is Mum?",
                "Cached": True,
            }
        ],
    )
    monkeypatch.setattr(
        "ocr_backend.app.get_ocr_engine",
        lambda: (_ for _ in ()).throw(RuntimeError("should not be called")),
    )
    client = TestClient(app)

    response = client.post(
        "/ocr",
        data={"image_name": "appendices_page14.jpg", "page_id": "appendices_page14"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["cached"] is True
    assert body["rows"][0]["SoundName"] == "appendices_page14_audio1"
    assert body["results"] == [
        {
            "Txt": "Where is Mum?",
            "Pos": {
                "Top": 2,
                "Left": 1,
                "Width": 3,
                "Height": 4,
                "Points": [
                    {"x": 1, "y": 2},
                    {"x": 4, "y": 2},
                    {"x": 4, "y": 6},
                    {"x": 1, "y": 6},
                ],
            },
        }
    ]
    assert "image_path" not in body
    assert "image_url" not in body


def test_ocr_endpoint_keeps_uploaded_preview_on_cache_miss(monkeypatch):
    monkeypatch.setattr("ocr_backend.app.read_result_txt", lambda stem: None)
    monkeypatch.setattr(
        "ocr_backend.app.get_ocr_engine",
        lambda: type(
            "StubEngine",
            (),
            {
                "recognize": lambda self, image_bytes: [
                    {
                        "text": "Where is Mum?",
                        "score": 0.99,
                        "points": [[231, 309], [669, 309], [669, 395], [231, 395]],
                        "rect": {"left": 231, "top": 309, "width": 438, "height": 86},
                    }
                ]
            },
        )(),
    )
    client = TestClient(app)

    response = client.post(
        "/ocr",
        data={"image_name": "appendices_page14.jpg", "page_id": "appendices_page14"},
        files={"file": ("appendices_page14.jpg", BytesIO(b"fake-image"), "image/jpeg")},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["cached"] is False
    assert body["rows"][0]["SoundName"] == "appendices_page14_audio1"
    assert body["rows"][0]["Content"] == "Where is Mum?"
    assert "image_path" not in body
    assert "image_url" not in body


def test_source_image_route_is_removed():
    client = TestClient(app)

    response = client.get("/source-image/appendices_page14.jpg")

    assert response.status_code == 404


def test_ocr_endpoint_requires_file_when_cache_misses(monkeypatch):
    monkeypatch.setattr("ocr_backend.app.read_result_txt", lambda stem: None)
    client = TestClient(app)

    response = client.post(
        "/ocr",
        data={"image_name": "appendices_page18.jpg", "page_id": "appendices_page18"},
    )

    body = response.json()
    assert response.status_code == 400
    assert body["error"] == "missing file"


def test_ocr_endpoint_falls_back_to_uploaded_filename_when_image_name_missing(monkeypatch):
    monkeypatch.setattr("ocr_backend.app.read_result_txt", lambda stem: None)
    monkeypatch.setattr(
        "ocr_backend.app.get_ocr_engine",
        lambda: type(
            "StubEngine",
            (),
            {
                "recognize": lambda self, image_bytes: [
                    {
                        "text": "Hello",
                        "score": 0.99,
                        "points": [[1, 2], [11, 2], [11, 12], [1, 12]],
                        "rect": {"left": 1, "top": 2, "width": 10, "height": 10},
                    }
                ]
            },
        )(),
    )
    client = TestClient(app)

    response = client.post(
        "/ocr",
        data={"page_id": "appendices_page18"},
        files={"file": ("appendices_page18.jpg", BytesIO(b"fake-image"), "image/jpeg")},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["rows"][0]["SoundName"] == "appendices_page18_audio1"
    assert body["results"] == [
        {
            "Txt": "Hello",
            "Pos": {
                "Top": 2,
                "Left": 1,
                "Width": 10,
                "Height": 10,
                "Points": [
                    {"x": 1, "y": 2},
                    {"x": 11, "y": 2},
                    {"x": 11, "y": 12},
                    {"x": 1, "y": 12},
                ],
            },
        }
    ]
