const apiBase = document.getElementById("apiBase");
const pageId = document.getElementById("pageId");
const imageInput = document.getElementById("imageInput");
const submitBtn = document.getElementById("submitBtn");
const statusText = document.getElementById("statusText");
const previewImage = document.getElementById("previewImage");
const overlay = document.getElementById("overlay");
const detailBox = document.getElementById("detailBox");

const configuredApiBase =
  window.OCR_APP_CONFIG?.apiBaseUrl || `http://${window.location.hostname}:8100`;
apiBase.value = configuredApiBase;

function clearBoxes() {
  overlay.innerHTML = "";
}

function setStatus(text) {
  statusText.textContent = text;
}

function renderRows(rows) {
  clearBoxes();
  const naturalWidth = previewImage.naturalWidth || 1;
  const naturalHeight = previewImage.naturalHeight || 1;
  const displayWidth = previewImage.clientWidth || naturalWidth;
  const displayHeight = previewImage.clientHeight || naturalHeight;
  const scaleX = displayWidth / naturalWidth;
  const scaleY = displayHeight / naturalHeight;

  rows.forEach((row) => {
    const box = document.createElement("button");
    box.type = "button";
    box.className = "ocr-box unmatched";
    box.style.left = `${row.PosRect.left * scaleX}px`;
    box.style.top = `${row.PosRect.top * scaleY}px`;
    box.style.width = `${row.PosRect.width * scaleX}px`;
    box.style.height = `${row.PosRect.height * scaleY}px`;
    box.title = row.Content || row.OcrText;
    box.addEventListener("click", () => {
      detailBox.textContent = JSON.stringify(row, null, 2);
    });
    overlay.appendChild(box);
  });
}

async function submitImage() {
  const file = imageInput.files[0];
  if (!file) {
    setStatus("请先上传图片");
    return;
  }
  const currentImageName = file.name;

  const base = apiBase.value.trim().replace(/\/$/, "");
  const formData = new FormData();
  formData.append("image_name", currentImageName);
  formData.append("page_id", pageId.value.trim());
  formData.append("file", file);

  previewImage.src = URL.createObjectURL(file);
  await previewImage.decode().catch(() => {});

  setStatus("识别中...");
  clearBoxes();
  detailBox.textContent = "暂无结果";

  try {
    const response = await fetch(`${base}/ocr`, {
      method: "POST",
      body: formData,
    });
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : { error: await response.text() };
    if (!response.ok) {
      throw new Error(payload.message || payload.error || "请求失败");
    }
    renderRows(payload.rows || []);
    setStatus(`${payload.cached ? "命中缓存" : "识别完成"}，共 ${payload.count || 0} 条`);
  } catch (error) {
    setStatus(`识别失败：${error.message}`);
  }
}

submitBtn.addEventListener("click", submitImage);
