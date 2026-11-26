import os
import time


class APIKeyManager:
    def __init__(self):
        # Mỗi phần tử: {"key": str, "store_id": str | None, "label": str}
        self.entries: list[dict[str, str | None]] = []
        self.keys: list[str] = []
        self.current_index: int = 0
        self.cooldowns: dict[str, float] = {}
        self._load_keys_and_stores()

    def _load_keys_and_stores(self):
        """Nạp API Keys và ghép đúng STORE_ID theo từng Project."""
        store_a = (os.getenv("GEMINI_STORE_ID_A") or "").strip() or None
        store_b = (os.getenv("GEMINI_STORE_ID_B") or "").strip() or None
        default_store = (os.getenv("GEMINI_STORE_ID") or "").strip() or None

        entries: list[dict[str, str | None]] = []

        # 1. Nạp theo từng Project nếu có cấu hình GEMINI_API_KEY_A_* / GEMINI_API_KEY_B_*
        for prefix, store_id, label_prefix in [
            ("GEMINI_API_KEY_A", store_a or default_store, "Project_A"),
            ("GEMINI_API_KEY_B", store_b or default_store, "Project_B"),
        ]:
            # Dạng đánh số _1, _2, ...
            idx = 1
            while True:
                k = (os.getenv(f"{prefix}_{idx}") or "").strip()
                if not k:
                    break
                entries.append({
                    "key": k,
                    "store_id": store_id,
                    "label": f"{label_prefix}_Key_{idx}",
                })
                idx += 1

            # Dạng không đánh số (ví dụ GEMINI_API_KEY_A)
            single_proj_key = (os.getenv(prefix) or "").strip()
            if single_proj_key and all(e["key"] != single_proj_key for e in entries):
                entries.append({
                    "key": single_proj_key,
                    "store_id": store_id,
                    "label": f"{label_prefix}_Key",
                })

        # 2. Nếu chưa dùng cấu hình theo Project, nạp từ GEMINI_API_KEYS hoặc GEMINI_API_KEY_1..N
        if not entries:
            raw_keys_str = os.getenv("GEMINI_API_KEYS", "")
            if raw_keys_str.strip():
                for i, k in enumerate(
                    [x.strip() for x in raw_keys_str.split(",") if x.strip()], start=1
                ):
                    entries.append({
                        "key": k,
                        "store_id": default_store,
                        "label": f"Pool_Key_{i}",
                    })

        if not entries:
            idx = 1
            while True:
                k = (os.getenv(f"GEMINI_API_KEY_{idx}") or "").strip()
                if not k:
                    break
                entries.append({
                    "key": k,
                    "store_id": default_store,
                    "label": f"Key_{idx}",
                })
                idx += 1

        # 3. Fallback 1 key đơn lẻ
        if not entries:
            single_key = (os.getenv("GEMINI_API_KEY") or "").strip()
            if single_key:
                entries.append({
                    "key": single_key,
                    "store_id": default_store,
                    "label": "Default_Key",
                })

        self.entries = entries
        self.keys = [e["key"] for e in entries if e["key"]]

    def get_next_key_and_store(self) -> tuple[str, str | None, str]:
        """Lấy (api_key, store_id, label) tiếp theo chưa bị cooldown."""
        if not self.entries:
            raise ValueError(
                "Chưa cấu hình GEMINI_API_KEYS / GEMINI_API_KEY_A_1 / GEMINI_API_KEY trên môi trường!"
            )

        now = time.time()
        n = len(self.entries)

        for _ in range(n):
            entry = self.entries[self.current_index]
            self.current_index = (self.current_index + 1) % n

            key = entry["key"] or ""
            cool_until = self.cooldowns.get(key, 0)
            if now >= cool_until:
                return key, entry["store_id"], entry["label"] or "Key"

        best_entry = min(self.entries, key=lambda e: self.cooldowns.get(e["key"] or "", 0))
        return (
            best_entry["key"] or "",
            best_entry["store_id"],
            best_entry["label"] or "Key",
        )

    def get_next_key(self) -> str:
        """Giữ tương thích ngược nếu nơi khác chỉ cần lấy key."""
        key, _, _ = self.get_next_key_and_store()
        return key

    def mark_key_quota_exceeded(self, key: str, cooldown_seconds: int = 60):
        """Đánh dấu Key bị dính lỗi 429 / Quota Exceeded và tạm nghỉ trong cooldown_seconds."""
        self.cooldowns[key] = time.time() + cooldown_seconds
        print(
            f"⚠️ Key [***{key[-6:]}] bị vượt quá quota 429. Đang tạm dừng sử"
            f" dụng key này trong {cooldown_seconds}s."
        )


# Export singleton instance
key_manager = APIKeyManager()