"""환경 변수 설정. 값은 .env 파일이나 시스템 환경 변수에서 읽는다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """의존성을 늘리지 않으려고 만든 아주 단순한 .env 로더. 이미 설정된 값은 덮어쓰지 않는다."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    provider: str
    model: str | None
    effort: str
    max_image_side: int
    max_upload_mb: int
    # 이 서버를 부를 수 있는 다른 사이트 주소 (예: Vercel에 올린 화면). 비우면 같은 주소에서만.
    cors_origins: tuple[str, ...] = ()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "problems.db"

    @property
    def figures_dir(self) -> Path:
        return self.data_dir / "figures"

    @property
    def sources_dir(self) -> Path:
        return self.data_dir / "sources"


def load_settings() -> Settings:
    _load_dotenv(Path.cwd() / ".env")
    return Settings(
        data_dir=Path(os.environ.get("PX_DATA_DIR", "data")).resolve(),
        provider=os.environ.get("PX_PROVIDER", "gemini").strip().lower(),
        model=os.environ.get("PX_MODEL", "").strip() or None,  # 비우면 제공사별 기본 모델
        effort=os.environ.get("PX_EFFORT", "medium"),
        max_image_side=int(os.environ.get("PX_MAX_IMAGE_SIDE", "2000")),
        max_upload_mb=int(os.environ.get("PX_MAX_UPLOAD_MB", "15")),
        cors_origins=tuple(
            o.strip().rstrip("/") for o in os.environ.get("PX_CORS_ORIGINS", "").split(",") if o.strip()
        ),
    )
