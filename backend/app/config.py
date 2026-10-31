from __future__ import annotations

MAX_DAYS = 1100
MAX_WORKERS = 8

DEFAULT_SYMBOLS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "GOOGL",
    "AMZN",
    "TSLA",
    "META",
]

TICKER_NAMES: dict[str, str] = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "NVIDIA",
    "GOOGL": "Alphabet (Google)",
    "AMZN": "Amazon",
    "TSLA": "Tesla",
    "META": "Meta",
    "005930.KS": "삼성전자",
    "000660.KS": "SK하이닉스",
    "035420.KS": "NAVER",
    "035720.KS": "카카오",
    "005380.KS": "현대차",
    "068270.KS": "셀트리온",
    "000270.KS": "기아",
}
