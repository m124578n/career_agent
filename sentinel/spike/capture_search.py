"""Spike：探 104 公開職缺搜尋 API，抓一筆 payload 釘死結構（SP-Search 用）。

用法：uv run python spike/capture_search.py
curl_cffi（Chrome TLS 指紋，像 SP4 抓 JD）——公開資料、不需登入、不彈 Chrome。
輸出 spike/captured/search__*.json（已 gitignore）。
"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "captured"
OUT.mkdir(parents=True, exist_ok=True)

KW = "Python"
CANDIDATES = [
    ("api_jobs", f"https://www.104.com.tw/jobs/search/api/jobs?keyword={KW}&page=1&pagesize=20&jobsource=2018indexpoc&order=15&asc=0&mode=s"),
    ("api_jobs_min", f"https://www.104.com.tw/jobs/search/api/jobs?keyword={KW}&page=1&pagesize=20"),
]
REFERER = f"https://www.104.com.tw/jobs/search/?keyword={KW}"
WARMUP = "https://www.104.com.tw/jobs/search/"


def main() -> None:
    from curl_cffi import requests as creq

    sess = creq.Session(impersonate="chrome", timeout=30)
    try:
        sess.get(WARMUP)  # 暖身取 cookie
    except Exception as exc:  # noqa: BLE001
        print(f"warmup note: {type(exc).__name__}: {exc}")

    for name, url in CANDIDATES:
        try:
            r = sess.get(url, headers={"Referer": REFERER})
            print(f"[{name}] status={r.status_code} len={len(r.text)}")
            if r.status_code == 200:
                try:
                    body = r.json()
                except Exception:  # noqa: BLE001
                    print(f"[{name}] 非 JSON，前 200 字：{r.text[:200]}")
                    continue
                (OUT / f"search__{name}.json").write_text(
                    json.dumps({"url": url, "body": body}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"[{name}] 存 search__{name}.json")
        except Exception as exc:  # noqa: BLE001
            print(f"[{name}] error: {type(exc).__name__}: {exc}")
    sess.close()


if __name__ == "__main__":
    main()
