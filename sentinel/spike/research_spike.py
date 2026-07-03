"""SP9 spike：驗證 LLM provider 的 web search 能力。

跑法：cd sentinel && uv run python spike/research_spike.py
判準：回覆內容包含「近期真實網路資訊」（非模型記憶）且最好附來源網址。
"""
import httpx

from career_sentinel.config import foundry_settings, llm_settings

PROMPT = (
    "請用網路搜尋查「台積電 面試 評價」，用繁體中文回覆一句你查到的重點，"
    "並附上一個實際來源網址。"
)


def try_openai_online() -> None:
    cfg = llm_settings()
    if not cfg.api_key:
        print("[openai] 無 LLM_API_KEY，略過")
        return
    variants = [
        ("model:online 後綴", {"model": cfg.model + ":online"}),
        ("plugins web", {"model": cfg.model, "plugins": [{"id": "web"}]}),
    ]
    for name, extra in variants:
        try:
            r = httpx.post(
                f"{cfg.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {cfg.api_key}"},
                json={**extra, "messages": [{"role": "user", "content": PROMPT}]},
                timeout=120,
            )
            print(f"[openai/{name}] status={r.status_code}")
            if r.status_code == 200:
                print("  content:", r.json()["choices"][0]["message"]["content"][:300])
        except Exception as exc:
            print(f"[openai/{name}] error: {exc}")


def try_foundry_web_search() -> None:
    fs = foundry_settings()
    if not fs.api_key:
        print("[foundry] 無 FOUNDRY_API_KEY，略過")
        return
    from anthropic import AnthropicFoundry

    client = AnthropicFoundry(api_key=fs.api_key, base_url=fs.base_url)
    try:
        resp = client.messages.create(
            model=fs.model,
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
            messages=[{"role": "user", "content": PROMPT}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        print("[foundry/web_search_20250305] ok:", text[:300])
    except Exception as exc:
        print(f"[foundry/web_search_20250305] error: {exc}")


if __name__ == "__main__":
    try_openai_online()
    try_foundry_web_search()
