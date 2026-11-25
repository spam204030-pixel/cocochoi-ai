"""네이버 검색광고 키워드 도구(공식 API)로 키워드별 월간 검색량·경쟁도를 조회한다.

사용법:
    python scripts/naver_keyword.py 키워드1 키워드2 ...

- API 키는 프로젝트 맨 위 폴더의 .env 파일에서 읽는다 (Git에 올리지 않음).
  NAVER_AD_API_KEY, NAVER_AD_SECRET, NAVER_AD_CUSTOMER_ID
- 결과는 화면에 표로 보여주고, reports/keywords_YYYY-MM-DD.csv 로도 저장한다.
"""
import base64
import csv
import hashlib
import hmac
import os
import sys
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

API_KEY = os.getenv("NAVER_AD_API_KEY")
SECRET = os.getenv("NAVER_AD_SECRET")
CUSTOMER_ID = os.getenv("NAVER_AD_CUSTOMER_ID")
BASE_URL = "https://api.searchad.naver.com"
URI = "/keywordstool"


def headers(method: str, uri: str) -> dict:
    ts = str(int(time.time() * 1000))
    msg = f"{ts}.{method}.{uri}".encode()
    sig = base64.b64encode(hmac.new(SECRET.encode(), msg, hashlib.sha256).digest()).decode()
    return {
        "X-Timestamp": ts,
        "X-API-KEY": API_KEY,
        "X-Customer": str(CUSTOMER_ID),
        "X-Signature": sig,
    }


def to_int(v) -> int:
    # 검색량이 아주 적으면 "< 10" 문자열로 온다
    if isinstance(v, (int, float)):
        return int(v)
    return 5 if "<" in str(v) else int(str(v).replace(",", "") or 0)


def fetch(keywords: list[str]) -> list[dict]:
    """키워드는 한 번에 5개까지만 요청 가능 → 5개씩 나눠서 요청."""
    rows = {}
    for i in range(0, len(keywords), 5):
        chunk = [k.replace(" ", "") for k in keywords[i:i + 5]]
        r = requests.get(
            BASE_URL + URI,
            params={"hintKeywords": ",".join(chunk), "showDetail": "1"},
            headers=headers("GET", URI),
            timeout=20,
        )
        if r.status_code != 200:
            sys.exit(f"[오류] {r.status_code} {r.text[:300]}")
        for item in r.json().get("keywordList", []):
            rows[item["relKeyword"]] = item
        time.sleep(0.5)
    return list(rows.values())


def main():
    keywords = sys.argv[1:]
    if not keywords:
        sys.exit("사용법: python scripts/naver_keyword.py 키워드1 키워드2 ...")
    if not (API_KEY and SECRET and CUSTOMER_ID):
        sys.exit("[오류] .env 파일에 NAVER_AD_API_KEY / NAVER_AD_SECRET / NAVER_AD_CUSTOMER_ID 가 필요합니다.")

    items = fetch(keywords)
    asked = {k.replace(" ", "") for k in keywords}
    result = []
    for it in items:
        pc, mo = to_int(it["monthlyPcQcCnt"]), to_int(it["monthlyMobileQcCnt"])
        result.append({
            "키워드": it["relKeyword"],
            "입력키워드": "O" if it["relKeyword"] in asked else "",
            "PC검색량": pc,
            "모바일검색량": mo,
            "총검색량": pc + mo,
            "모바일클릭수": it.get("monthlyAveMobileClkCnt", 0),
            "경쟁도": it.get("compIdx", ""),
        })
    result.sort(key=lambda x: (x["입력키워드"] != "O", -x["총검색량"]))

    out = ROOT / "reports" / f"keywords_{date.today().isoformat()}.csv"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(result[0].keys()))
        w.writeheader()
        w.writerows(result)

    print(f"\n[입력 키워드] (출처: 네이버 검색광고 키워드도구, 조회일 {date.today()})")
    for r in result:
        if r["입력키워드"]:
            print(f"  {r['키워드']:<16} 총 {r['총검색량']:>7,}  (PC {r['PC검색량']:,} / 모바일 {r['모바일검색량']:,})  경쟁도 {r['경쟁도']}")
    missing = asked - {r["키워드"] for r in result}
    if missing:
        print("  ※ 검색량 데이터 없음:", ", ".join(sorted(missing)))
    print(f"\n연관 키워드 포함 전체 {len(result)}개 → {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
