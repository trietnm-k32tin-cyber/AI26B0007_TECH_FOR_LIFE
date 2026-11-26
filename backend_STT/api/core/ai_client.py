import asyncio
import random
from typing import Any
from google import genai
from google.genai import types
from api.core.key_manager import key_manager


def _build_tools_with_store(
    tools: list[Any] | None, store_id: str | None
) -> list[Any] | None:
    """Ghép FileSearch của store_id tương ứng với key hiện tại vào danh sách tools."""
    merged_tools: list[Any] = list(tools) if tools else []
    has_file_search = any(
        getattr(t, "file_search", None) is not None for t in merged_tools
    )

    if store_id and not has_file_search:
        merged_tools.append(
            types.Tool(
                file_search=types.FileSearch(
                    file_search_store_names=[store_id]
                )
            )
        )

    return merged_tools or None


async def generate_gemini_content_with_retry(
    prompt: str,
    response_schema=None,
    model: str = "gemini-3.8-flash",
    tools: list[Any] | None = None,
    max_retries: int = 5,
    base_delay: float = 2.0,
) -> str:
    """Thực hiện gọi Gemini API có kèm File Search Store (nếu có), xoay Key và Retry Backoff."""
    last_exception = None

    for attempt in range(max_retries):
        api_key, store_id, key_label = key_manager.get_next_key_and_store()
        client = genai.Client(api_key=api_key)

        config_kwargs: dict[str, Any] = {}
        if response_schema:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = response_schema
            config_kwargs["temperature"] = 0.6

        effective_tools = _build_tools_with_store(tools=tools, store_id=store_id)
        if effective_tools:
            config_kwargs["tools"] = effective_tools

        config = (
            types.GenerateContentConfig(**config_kwargs) if config_kwargs else None
        )

        try:
            response = await client.aio.models.generate_content(
                model=model, contents=prompt, config=config
            )
            return (response.text or "").strip()

        except Exception as err:
            last_exception = err
            err_str = str(err).lower()

            # Case 1: Lỗi Rate Limit (HTTP 429 / RESOURCE_EXHAUSTED) -> Đổi Key ngay lập tức
            if (
                "429" in err_str
                or "resource_exhausted" in err_str
                or "quota" in err_str
            ):
                key_manager.mark_key_quota_exceeded(api_key, cooldown_seconds=60)
                print(
                    f"🔄 [Lần thử {attempt + 1}/{max_retries}] ({key_label}) Đã tự"
                    " động chuyển API Key mới..."
                )
                await asyncio.sleep(0.3)
                continue

            # Case 2: Lỗi Server tạm thời (HTTP 500 / 503 / Timeout / Overloaded) -> Exponential Backoff
            elif (
                "500" in err_str
                or "503" in err_str
                or "unavailable" in err_str
                or "overloaded" in err_str
            ):
                sleep_time = (base_delay * (2**attempt)) + random.uniform(0.1, 0.8)
                print(
                    f"⏳ [Lần thử {attempt + 1}/{max_retries}] ({key_label}) Lỗi"
                    f" máy chủ Gemini ({err}). Đang chờ {sleep_time:.2f}s..."
                )
                await asyncio.sleep(sleep_time)
                continue

            # Case 3: Các lỗi khác -> Báo lỗi ra ngoài
            else:
                print(f"❌ Lỗi không thể retry ({key_label}): {err}")
                raise err

    raise Exception(
        f"Thất bại sau {max_retries} lần thử với Gemini API. Lỗi nguyên nhân:"
        f" {str(last_exception)}"
    )