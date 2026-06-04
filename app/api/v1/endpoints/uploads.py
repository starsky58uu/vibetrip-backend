"""圖片上傳端點 — 供 AR 足跡儲存使用。"""
from pathlib import Path
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.models.user import User

router = APIRouter()

_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
_MAX_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


@router.post("/image")
async def upload_image(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    _user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """
    上傳單張圖片（multipart/form-data），回傳可公開存取的 image_url。

    - 支援格式：JPEG / PNG / WebP / HEIC
    - 大小上限：MAX_UPLOAD_SIZE_MB（預設 10MB）
    - 認證：需要 Bearer token
    """
    # ── 格式檢查 ─────────────────────────────────────────────────────────────
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in _ALLOWED_MIME:
        raise HTTPException(status_code=415, detail=f"不支援的格式：{content_type}")

    # ── 存檔 ─────────────────────────────────────────────────────────────────
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename or "img.jpg").suffix.lower() or ".jpg"
    # heic → jpg 外掛副檔名（不做轉檔，只存原檔）
    filename = f"{uuid.uuid4()}{ext}"
    dest = upload_dir / filename

    size = 0
    try:
        with open(dest, "wb") as f:
            while chunk := await file.read(64 * 1024):
                size += len(chunk)
                if size > _MAX_BYTES:
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"圖片不得超過 {settings.MAX_UPLOAD_SIZE_MB} MB",
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="儲存圖片失敗") from exc

    # ── 產生 URL ──────────────────────────────────────────────────────────────
    # 優先使用 config 中設定的 PUBLIC_CDN_BASE；
    # 若仍是預設值 localhost，則改用請求實際來源，方便手機直接存取
    base = settings.PUBLIC_CDN_BASE.rstrip("/")
    if "localhost" in base or "127.0.0.1" in base:
        # 動態從請求取得 scheme+host（例如 http://10.56.60.215:8000）
        base = f"{request.url.scheme}://{request.url.netloc}/static/uploads"

    image_url = f"{base}/{filename}"
    return {"image_url": image_url}
