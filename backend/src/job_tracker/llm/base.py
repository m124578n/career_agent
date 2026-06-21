"""LLM provider 介面。所有 provider 都實作 complete() 與 parse()。"""

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    async def complete(
        self, prompt: str, *, system: str = "", max_tokens: int = 2048, client=None
    ) -> str:
        """自由文字產生（如求職信）。"""
        ...

    async def parse(
        self,
        prompt: str,
        schema: type[T],
        *,
        system: str = "",
        max_tokens: int = 4096,
        client=None,
    ) -> T:
        """結構化輸出，回傳依 schema 驗證的物件。"""
        ...


_DEFAULT_SYSTEM = "你是一位專業的求職顧問。"
