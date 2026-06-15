import os
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    AuthRestartError,
)
from telethon.tl.types import DocumentAttributeFilename

SESSION_DIR = "sessions"


class TGClient:
    def __init__(self, session_name: str, api_id: int, api_hash: str, loop=None):
        self._loop = loop
        Path(SESSION_DIR).mkdir(parents=True, exist_ok=True)
        session_path = os.path.join(SESSION_DIR, session_name)
        self.client = TelegramClient(session_path, api_id, api_hash, loop=loop)

    async def connect(self):
        await self.client.connect()

    async def disconnect(self):
        await self.client.disconnect()

    async def is_authorized(self) -> bool:
        return await self.client.is_user_authorized()

    async def send_code_request(self, phone: str):
        try:
            return await self.client.send_code_request(phone)
        except AuthRestartError:
            # Telegram requires restarting the auth process
            await self.client.disconnect()
            await self.client.connect()
            return await self.client.send_code_request(phone)

    async def sign_in(self, phone: str, code: str, password: str = None):
        try:
            await self.client.sign_in(phone, code)
        except SessionPasswordNeededError:
            if password:
                await self.client.sign_in(password=password)
            else:
                raise

    async def get_dialogs(self):
        dialogs = await self.client.get_dialogs(archived=False)
        result = []
        for d in dialogs:
            entity = d.entity
            chat_type = "Private"
            if hasattr(entity, 'broadcast') and entity.broadcast:
                chat_type = "Channel"
            elif hasattr(entity, 'megagroup') and entity.megagroup:
                chat_type = "Group"
            elif hasattr(entity, 'gigagroup') and entity.gigagroup:
                chat_type = "GigaGroup"
            elif hasattr(entity, 'title'):
                chat_type = "Chat"
            protected = getattr(entity, 'has_protected_content', False)
            result.append({
                "id": d.id,
                "title": d.name or "Unknown",
                "entity": entity,
                "type": chat_type,
                "protected": protected,
                "unread": d.unread_count,
            })
        return result

    async def get_video_messages(self, chat_id, limit=200):
        messages = []
        async for msg in self.client.iter_messages(chat_id, limit=limit):
            if self._is_video(msg):
                messages.append(msg)
        messages.reverse()
        return messages

    async def download_media(self, message, file_path, progress_callback=None):
        return await self.client.download_media(
            message,
            file=file_path,
            progress_callback=progress_callback,
        )

    async def download_media_resumable(self, message, file_path, existing_size=0,
                                        progress_callback=None):
        total_size = 0
        if message.video:
            total_size = message.video.size
        elif message.document:
            total_size = message.document.size
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "ab" if existing_size > 0 else "wb"
        written = existing_size
        try:
            with open(file_path, mode) as f:
                async for chunk in self.client.iter_download(message, offset=existing_size):
                    f.write(chunk)
                    written += len(chunk)
                    if progress_callback and total_size > 0:
                        progress_callback(written, total_size)
        except Exception:
            raise
        return file_path

    async def get_message_from_link(self, link: str):
        import re
        link = link.strip()
        # https://t.me/c/CHANNEL_ID/MSG_ID (private channel)
        m = re.match(r'https?://t\.me/c/(\d+)/(\d+)', link)
        if m:
            chat_id, msg_id = int(m.group(1)), int(m.group(2))
            try:
                msg = await self.client.get_messages(int(f"-100{chat_id}"), ids=msg_id)
                return msg
            except Exception:
                return None
        # https://t.me/USERNAME/MSG_ID (public)
        m = re.match(r'https?://t\.me/([a-zA-Z0-9_]+)/(\d+)', link)
        if m:
            username, msg_id = m.group(1), int(m.group(2))
            try:
                msg = await self.client.get_messages(username, ids=msg_id)
                return msg
            except Exception:
                return None
        return None

    @staticmethod
    def _is_video(msg) -> bool:
        if msg.video:
            return True
        if msg.document and msg.document.mime_type:
            return msg.document.mime_type.startswith("video/")
        return False

    async def download_thumbnail(self, message, save_path):
        try:
            return await self.client.download_media(message, file=save_path, thumb=-1)
        except Exception:
            return None

    @staticmethod
    def get_video_duration(msg) -> int:
        if msg.video:
            return getattr(msg.video, 'duration', 0)
        if msg.document:
            from telethon.tl.types import DocumentAttributeVideo
            for attr in msg.document.attributes:
                if isinstance(attr, DocumentAttributeVideo):
                    return attr.duration
        return 0

    @staticmethod
    def get_video_filename(msg) -> str:
        if msg.file and msg.file.name:
            return msg.file.name
        if msg.document:
            for attr in msg.document.attributes:
                if isinstance(attr, DocumentAttributeFilename) and attr.file_name:
                    return attr.file_name
        ext = ".mp4"
        mime_map = {
            "video/mp4": ".mp4",
            "video/quicktime": ".mov",
            "video/x-matroska": ".mkv",
            "video/webm": ".webm",
            "video/avi": ".avi",
            "video/x-msvideo": ".avi",
            "video/mpeg": ".mpeg",
            "video/3gpp": ".3gp",
        }
        if msg.video and msg.video.mime_type:
            ext = mime_map.get(msg.video.mime_type, ".mp4")
        elif msg.document and msg.document.mime_type:
            ext = mime_map.get(msg.document.mime_type, ".mp4")
        date_str = msg.date.strftime("%Y%m%d_%H%M%S") if msg.date else "unknown"
        return f"video_{msg.id}_{date_str}{ext}"
