import json
from pathlib import Path

CONFIG_FILE = Path("config.json")


class Config:
    def __init__(self):
        self.api_id: int = 0
        self.api_hash: str = ""
        self.phone: str = ""
        self.download_dir: str = "downloads"
        self.max_concurrent: int = 3
        self.max_messages_per_group: int = 200
        self.dark_mode: bool = True
        self.load()

    def load(self):
        if not CONFIG_FILE.exists():
            return
        try:
            data = json.loads(CONFIG_FILE.read_text("utf-8"))
            self.api_id = data.get("api_id", 0)
            self.api_hash = data.get("api_hash", "")
            self.phone = data.get("phone", "")
            self.download_dir = data.get("download_dir", "downloads")
            self.max_concurrent = data.get("max_concurrent", 3)
            self.max_messages_per_group = data.get("max_messages_per_group", 200)
            self.dark_mode = data.get("dark_mode", True)
        except (json.JSONDecodeError, OSError):
            pass

    def save(self):
        data = {
            "api_id": self.api_id,
            "api_hash": self.api_hash,
            "phone": self.phone,
            "download_dir": self.download_dir,
            "max_concurrent": self.max_concurrent,
            "max_messages_per_group": self.max_messages_per_group,
            "dark_mode": self.dark_mode,
        }
        CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
