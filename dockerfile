# 使用官方的 Python 3.11 輕量版 Image (原生支援 x86 與 ARM 架構)
FROM python:3.11-slim

# ==========================================
# 設定 Python 環境變數
# ==========================================
# 避免 Python 產生 .pyc 檔案，減少不必要的硬碟佔用
ENV PYTHONDONTWRITEBYTECODE=1
# 讓印出的 Log 不會被緩衝，直接顯示在終端機，方便 debug
ENV PYTHONUNBUFFERED=1

# 設定容器內的工作目錄
WORKDIR /app

# ==========================================
# 安裝系統層級的依賴與套件
# ==========================================
# 如果有使用 PostgreSQL，通常需要 gcc 與 libpq-dev 來編譯相關套件
# 安裝完畢後立刻清除 apt 暫存，讓 Image 保持最小體積
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ==========================================
# 安裝 Python 依賴套件
# ==========================================
# 先單獨複製 requirements.txt。
# 這樣做的目的是利用 Docker 的 Cache 機制：只要你的套件清單沒改，
# 下次打包時 Docker 就不會浪費時間重新下載套件。
COPY requirements.txt .

# 升級 pip 並安裝套件，不保留 pip 快取檔以節省空間
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ==========================================
# 複製專案原始碼與權限設定
# ==========================================
# 將本機的所有程式碼複製到容器的 /app 目錄中
COPY . .

# 建立一個沒有密碼的非 root 使用者 (提升安全性，防止駭客取得系統最高權限)
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app

# 切換成這個一般使用者
USER appuser

# ==========================================
# 執行設定
# ==========================================
# 宣告此容器預期會使用 8000 Port
EXPOSE 8000

# 啟動 FastAPI 伺服器 (假設你的進入點在 app/main.py 並且變數名叫 app)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]