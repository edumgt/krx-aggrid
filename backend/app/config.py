from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException


KRX_ENDPOINTS = {
    "production": "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd",
    "sample": "https://data-dbg.krx.co.kr/svc/sample/apis/sto/stk_bydd_trd",
}
KRX_API_MODE = os.getenv("KRX_API_MODE", "production").strip().lower()
if KRX_API_MODE not in KRX_ENDPOINTS:
    raise RuntimeError("KRX_API_MODE는 production 또는 sample이어야 합니다.")
KRX_ENDPOINT = KRX_ENDPOINTS[KRX_API_MODE]
MAX_DAYS = 366
MAX_WORKERS = 5
KEY_FILE = Path(os.getenv("KRX_KEY_FILE", Path.cwd() / ".key"))


def get_krx_key() -> str:
    """Load a KRX key without embedding it in an image or tracked source."""
    for variable in ("KRX_KEY", "KRX_AUTH_KEY", "KRX-KEY"):
        key = os.getenv(variable, "").strip()
        if key:
            return key

    try:
        for line in KEY_FILE.read_text(encoding="utf-8").splitlines():
            normalized = line.strip()
            if normalized.startswith(("KRX-KEY=", "KRX_KEY=", "KRX_AUTH_KEY=")):
                key = normalized.partition("=")[2].strip().strip("\"'")
                if key:
                    return key
    except (FileNotFoundError, IsADirectoryError):
        pass

    raise HTTPException(
        status_code=500,
        detail="KRX API 키가 없습니다. KRX_KEY/KRX_AUTH_KEY 환경변수 또는 .key의 KRX-KEY를 설정하세요.",
    )
