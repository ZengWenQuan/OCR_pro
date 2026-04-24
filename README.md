# OCR_pro

基于 PaddleOCR 的图片 OCR 识别与调试服务。

## 功能

- **OCR 识别** — 上传图片，返回文本内容、坐标、置信度等结构化结果
- **结果缓存** — 同一图片的 OCR 结果自动缓存，重复请求直接命中
- **可视化调试** — 浏览器端选择图片、发起请求、绘制文本框、查看详细 JSON

## 项目结构

```
OCR_pro/
├── ocr_backend/          # FastAPI 后端：OCR 接口、缓存、配置
│   ├── app.py            # 入口，暴露 /health 和 /ocr
│   ├── ocr_engine.py     # PaddleOCR 封装
│   ├── storage.py        # OCR 结果读写
│   ├── config.py         # YAML 配置加载
│   ├── config.yaml       # 运行配置（端口、模型路径、语言等）
│   └── download_models.py
├── ocr_frontend/         # 前端调试页面（纯静态，无需构建）
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   ├── server.py         # 本地静态文件服务
│   └── config.js         # 启动时自动生成
├── data/
│   └── txt/              # OCR 结果缓存目录
├── checkpoints/          # PaddleOCR 模型目录（不入 Git）
├── pyproject.toml
├── script/
│   ├── setup-uv-env.sh   # 一键配置环境
│   ├── start-backend.sh  # 启动后端
│   ├── start-frontend.sh # 启动前端
│   ├── start-ocr.sh      # 一键启动前后端
│   ├── start-ocr.ps1     # Windows PowerShell 启动脚本
│   └── start-ocr.bat     # Windows CMD 启动脚本
```

## 环境要求

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)
- GPU 可选（需要 NVIDIA 驱动 + CUDA）

## 快速开始

### 1. 配置环境

```bash
chmod +x script/setup-uv-env.sh && ./script/setup-uv-env.sh
```

脚本会自动检查并创建 `.venv`，已有则跳过。

### 2. 准备模型

```bash
PYTHONPATH=. .venv/bin/python ocr_backend/download_models.py
```

> 首次部署必须先下载模型。模型保存在 `checkpoints/`，不入 Git。

### 3. 启动服务

**一键启动（推荐）：**

```bash
chmod +x script/start-ocr.sh && ./script/start-ocr.sh
```

**分开启动：**

```bash
# 终端 1 — 后端（默认端口 8100）
./script/start-backend.sh

# 终端 2 — 前端（默认端口 8080）
./script/start-frontend.sh
```

自定义端口：

```bash
./script/start-ocr.sh --backend-port 8101 --frontend-port 8081
# 或分开启动时：
./script/start-backend.sh --port 8101
./script/start-frontend.sh --backend-port 8101 --port 8081
```

启动后访问：**http://127.0.0.1:8080/index.html**

## 配置

编辑 `ocr_backend/config.yaml`：

| 配置项                    | 说明               | 默认值                 |
| ------------------------- | ------------------ | ---------------------- |
| `server.host/port`      | 后端监听地址和端口 | `0.0.0.0:8100`       |
| `paths.data_dir`        | OCR 结果缓存目录   | `data/`              |
| `paths.checkpoints_dir` | 模型根目录         | `checkpoints/`       |
| `ocr.lang`              | PaddleOCR 语言     | `ch`（支持中英混排） |
| `ocr.*_model_dir`       | 三个模型子目录     | 中文模型               |

> 项目默认使用中文模型，适合中英混排教材场景。纯英文页面可切换为英文模型，参见 `config.yaml` 中的注释。

## 接口

| 方法 | 路径        | 说明                                                                             |
| ---- | ----------- | -------------------------------------------------------------------------------- |
| GET  | `/health` | 健康检查                                                                         |
| POST | `/ocr`    | OCR 识别（`multipart/form-data`，字段：`file`、`image_name`、`page_id`） |

### 接口实现位置

- 后端入口代码：[`ocr_backend/app.py`](/home/irving/workspace/myPartjob/book1811/OCR_pro/ocr_backend/app.py)
- OCR 路由函数：`ocr_backend.app.ocr()`
- OCR 推理封装：[`ocr_backend/ocr_engine.py`](/home/irving/workspace/myPartjob/book1811/OCR_pro/ocr_backend/ocr_engine.py) 里的 `OcrEngine.recognize()`

### `/ocr` 接收参数

- `file`：上传的图片文件，`multipart/form-data`
- `image_name`：图片文件名，字符串，可选；不传时回退到上传文件名
- `page_id`：页面标识，字符串，可选；不传时默认使用图片文件名 stem

### `/ocr` 返回值

- `page_id`：本次请求对应的页面标识
- `count`：识别出的文本块数量
- `txt_path`：缓存结果 txt 路径
- `cached`：是否命中缓存
- `rows`：当前项目内部使用的 OCR 结果格式，主要字段包括 `Content`、`Pos`、`Score`、`Points`、`PosRect`
- `results`：阿里云兼容格式，主要字段为 `Txt` 和 `Pos	`

其中 `results` 的单项结构为：

```json
{
  "Txt": "Listen and repeat",
  "Pos": {
    "Top": 120,
    "Left": 50,
    "Width": 300,
    "Height": 40,
    "Points": [
      {"x": 50, "y": 120},
      {"x": 350, "y": 120},
      {"x": 350, "y": 160},
      {"x": 50, "y": 160}
    ]
  }
}
```

`/ocr` 的处理逻辑很简单：

1. 先检查 `data/txt/{image_stem}.txt` 是否存在。
2. 如果存在，直接读取这个缓存文件并返回。
3. 如果不存在，就读取上传图片做 OCR。
4. 把 OCR 结果写入 `data/txt/{image_stem}.txt`，供下次直接复用。

## 常见问题

- **GPU warning** — 无可用 GPU 时 Paddle 自动回退 CPU，不影响使用
- **模型目录缺失** — 检查 `config.yaml` 中模型路径和 `checkpoints/` 是否一致
- **端口占用** — 使用 `--port` 参数更换端口
