from __future__ import annotations

import asyncio
import time
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from .client import TGClient


class DownloadStatus(Enum):
    QUEUED = "Queued"
    DOWNLOADING = "Downloading"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"
    SKIPPED = "Skipped (exists)"


@dataclass
class DownloadItem:
    chat_title: str
    message: object
    save_dir: str
    filename: str
    file_size: int = 0
    duration: int = 0
    status: DownloadStatus = DownloadStatus.QUEUED
    progress: float = 0.0
    downloaded: int = 0
    speed: float = 0.0
    eta: float = 0.0
    error: Optional[str] = None

    @property
    def full_path(self) -> Path:
        return Path(self.save_dir) / self._sanitize(self.chat_title) / self.filename

    @staticmethod
    def _sanitize(name: str) -> str:
        for ch in '<>:"/\\|?*':
            name = name.replace(ch, "_")
        return name.strip()


class DownloadQueue:
    def __init__(self, client: TGClient, max_concurrent: int = 3):
        self.client = client
        self.max_concurrent = max_concurrent
        self._queue: asyncio.Queue[DownloadItem] = asyncio.Queue()
        self._items: list[DownloadItem] = []
        self._cancelled: set[int] = set()
        self._paused = False
        self._on_update: Optional[Callable[[Optional[DownloadItem]], None]] = None
        self._running = False

    @property
    def items(self) -> list[DownloadItem]:
        return self._items

    def set_on_update(self, callback: Callable[[Optional[DownloadItem]], None]):
        self._on_update = callback

    def _notify(self, item: Optional[DownloadItem] = None):
        if self._on_update:
            self._on_update(item)

    def add_items(self, items: list[DownloadItem]):
        for it in items:
            self._items.append(it)
            self._queue.put_nowait(it)
        self._notify()

    def remove_item(self, item: DownloadItem):
        if item in self._items:
            self._items.remove(item)
        self._notify()

    def cancel(self, item: DownloadItem):
        if item.status in (DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING):
            item.status = DownloadStatus.CANCELLED
            self._cancelled.add(id(item))
            self._notify(item)

    def cancel_all(self):
        for item in self._items:
            if item.status in (DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING):
                item.status = DownloadStatus.CANCELLED
                self._cancelled.add(id(item))
        self._notify()

    def toggle_pause(self):
        self._paused = not self._paused
        return self._paused

    async def process(self):
        self._running = True
        workers = [asyncio.create_task(self._worker(f"w{i}")) for i in range(self.max_concurrent)]
        try:
            await asyncio.gather(*workers)
        finally:
            self._running = False

    async def _worker(self, name: str):
        while self._running:
            if self._paused:
                await asyncio.sleep(0.3)
                continue
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if id(item) in self._cancelled:
                self._queue.task_done()
                continue

            final_path = item.full_path
            part_path = final_path.with_suffix(final_path.suffix + ".part")
            existing_size = 0

            if final_path.exists():
                item.status = DownloadStatus.SKIPPED
                item.progress = 100.0
                self._notify(item)
                self._queue.task_done()
                continue

            if part_path.exists():
                existing_size = part_path.stat().st_size
                if existing_size >= item.file_size > 0:
                    part_path.rename(final_path)
                    item.status = DownloadStatus.SKIPPED
                    item.progress = 100.0
                    self._notify(item)
                    self._queue.task_done()
                    continue

            item.status = DownloadStatus.DOWNLOADING
            if existing_size > 0:
                item.downloaded = existing_size
                item.file_size = max(item.file_size, 1)
                item.progress = (existing_size / item.file_size) * 100
            self._notify(item)
            try:
                item.full_path.parent.mkdir(parents=True, exist_ok=True)
                last_notify = 0.0
                _speed_last_bytes = existing_size
                _speed_last_time = time.monotonic()

                def _progress(curr, total):
                    nonlocal last_notify, _speed_last_bytes, _speed_last_time
                    if id(item) in self._cancelled:
                        raise asyncio.CancelledError()
                    now = time.monotonic()
                    elapsed = now - _speed_last_time
                    if elapsed >= 1.0:
                        chunk = curr - _speed_last_bytes
                        item.speed = chunk / elapsed if elapsed > 0 else 0
                        if item.speed > 0:
                            item.eta = (total - curr) / item.speed
                        _speed_last_bytes = curr
                        _speed_last_time = now
                    item.downloaded = curr
                    item.file_size = total
                    item.progress = (curr / total * 100) if total > 0 else 0
                    if now - last_notify > 0.15:
                        last_notify = now
                        self._notify(item)

                await self.client.download_media_resumable(
                    item.message, str(part_path),
                    existing_size=existing_size,
                    progress_callback=_progress,
                )

                part_path.rename(final_path)
                if id(item) not in self._cancelled:
                    item.status = DownloadStatus.COMPLETED
                    item.progress = 100.0
                else:
                    item.status = DownloadStatus.CANCELLED
            except asyncio.CancelledError:
                item.status = DownloadStatus.CANCELLED
            except Exception as e:
                item.status = DownloadStatus.FAILED
                item.error = str(e)
            self._notify(item)
            self._queue.task_done()
