"""火山引擎 SAUC 大模型语音识别 WebSocket 协议（基于官方 sauc_python SDK 适配）。

相对官方 SDK 的改动：
- 移除导入时的 logging.basicConfig（避免每次导入都写 run.log 的副作用）。
- 新增 SaucLiveClient：支持实时推流（浏览器麦克风 PCM → 豆包 ASR），而非读文件。
- 新增 extract_text()：从响应 payload 中提取转写文本。
"""

import gzip
import json
import logging
import ssl
import struct
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import aiohttp
import certifi

logger = logging.getLogger("sauc")


class ProtocolVersion:
    V1 = 0b0001


class MessageType:
    CLIENT_FULL_REQUEST = 0b0001
    CLIENT_AUDIO_ONLY_REQUEST = 0b0010
    SERVER_FULL_RESPONSE = 0b1001
    SERVER_ERROR_RESPONSE = 0b1111


class MessageTypeSpecificFlags:
    NO_SEQUENCE = 0b0000
    POS_SEQUENCE = 0b0001
    NEG_SEQUENCE = 0b0010
    NEG_WITH_SEQUENCE = 0b0011


class SerializationType:
    NO_SERIALIZATION = 0b0000
    JSON = 0b0001


class CompressionType:
    GZIP = 0b0001


class Config:
    def __init__(
        self, api_key: str = "", app_key: str = "", access_key: str = "", resource_id: str = "volc.bigasr.sauc.duration"
    ):
        # 新版控制台鉴权: 设置 api_key；老版控制台鉴权: 设置 app_key + access_key
        self.api_key = api_key
        self.app_key = app_key
        self.access_key = access_key
        self.resource_id = resource_id


class CommonUtils:
    @staticmethod
    def gzip_compress(data: bytes) -> bytes:
        return gzip.compress(data)

    @staticmethod
    def gzip_decompress(data: bytes) -> bytes:
        return gzip.decompress(data)


class AsrRequestHeader:
    def __init__(self):
        self.message_type = MessageType.CLIENT_FULL_REQUEST
        self.message_type_specific_flags = MessageTypeSpecificFlags.POS_SEQUENCE
        self.serialization_type = SerializationType.JSON
        self.compression_type = CompressionType.GZIP
        self.reserved_data = bytes([0x00])

    def with_message_type(self, message_type: int) -> "AsrRequestHeader":
        self.message_type = message_type
        return self

    def with_message_type_specific_flags(self, flags: int) -> "AsrRequestHeader":
        self.message_type_specific_flags = flags
        return self

    def with_serialization_type(self, serialization_type: int) -> "AsrRequestHeader":
        self.serialization_type = serialization_type
        return self

    def with_compression_type(self, compression_type: int) -> "AsrRequestHeader":
        self.compression_type = compression_type
        return self

    def with_reserved_data(self, reserved_data: bytes) -> "AsrRequestHeader":
        self.reserved_data = reserved_data
        return self

    def to_bytes(self) -> bytes:
        header = bytearray()
        header.append((ProtocolVersion.V1 << 4) | 1)
        header.append((self.message_type << 4) | self.message_type_specific_flags)
        header.append((self.serialization_type << 4) | self.compression_type)
        header.extend(self.reserved_data)
        return bytes(header)

    @staticmethod
    def default_header() -> "AsrRequestHeader":
        return AsrRequestHeader()


class RequestBuilder:
    @staticmethod
    def new_auth_headers(config: Config) -> dict[str, str]:
        reqid = str(uuid.uuid4())
        headers = {
            "X-Api-Resource-Id": config.resource_id,
            "X-Api-Request-Id": reqid,
        }
        # 新版控制台鉴权: X-Api-Key；老版控制台鉴权: X-Api-App-Key + X-Api-Access-Key
        if config.api_key:
            headers["X-Api-Key"] = config.api_key
        else:
            headers["X-Api-App-Key"] = config.app_key
            headers["X-Api-Access-Key"] = config.access_key
        return headers

    @staticmethod
    def new_full_client_request(seq: int, payload) -> bytes:
        header = AsrRequestHeader.default_header().with_message_type_specific_flags(
            MessageTypeSpecificFlags.POS_SEQUENCE
        )

        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        compressed_payload = CommonUtils.gzip_compress(payload_bytes)
        payload_size = len(compressed_payload)

        request = bytearray()
        request.extend(header.to_bytes())
        request.extend(struct.pack(">i", seq))
        request.extend(struct.pack(">I", payload_size))
        request.extend(compressed_payload)

        return bytes(request)

    @staticmethod
    def new_audio_only_request(seq: int, segment: bytes, is_last: bool = False) -> bytes:
        header = AsrRequestHeader.default_header()
        if is_last:  # 最后一个包特殊处理
            header.with_message_type_specific_flags(MessageTypeSpecificFlags.NEG_WITH_SEQUENCE)
            seq = -seq  # 设为负值
        else:
            header.with_message_type_specific_flags(MessageTypeSpecificFlags.POS_SEQUENCE)
        header.with_message_type(MessageType.CLIENT_AUDIO_ONLY_REQUEST)

        request = bytearray()
        request.extend(header.to_bytes())
        request.extend(struct.pack(">i", seq))

        compressed_segment = CommonUtils.gzip_compress(segment)
        request.extend(struct.pack(">I", len(compressed_segment)))
        request.extend(compressed_segment)

        return bytes(request)


class AsrResponse:
    def __init__(self):
        self.code = 0
        self.event = 0
        self.is_last_package = False
        self.payload_sequence = 0
        self.payload_size = 0
        self.payload_msg = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "event": self.event,
            "is_last_package": self.is_last_package,
            "payload_sequence": self.payload_sequence,
            "payload_size": self.payload_size,
            "payload_msg": self.payload_msg,
        }


class ResponseParser:
    @staticmethod
    def parse_response(msg: bytes) -> AsrResponse:
        response = AsrResponse()

        header_size = msg[0] & 0x0F
        message_type = msg[1] >> 4
        message_type_specific_flags = msg[1] & 0x0F
        serialization_method = msg[2] >> 4
        message_compression = msg[2] & 0x0F

        payload = msg[header_size * 4 :]

        # 解析 message_type_specific_flags
        if message_type_specific_flags & 0x01:
            response.payload_sequence = struct.unpack(">i", payload[:4])[0]
            payload = payload[4:]
        if message_type_specific_flags & 0x02:
            response.is_last_package = True
        if message_type_specific_flags & 0x04:
            response.event = struct.unpack(">i", payload[:4])[0]
            payload = payload[4:]

        # 解析 message_type
        if message_type == MessageType.SERVER_FULL_RESPONSE:
            response.payload_size = struct.unpack(">I", payload[:4])[0]
            payload = payload[4:]
        elif message_type == MessageType.SERVER_ERROR_RESPONSE:
            response.code = struct.unpack(">i", payload[:4])[0]
            response.payload_size = struct.unpack(">I", payload[4:8])[0]
            payload = payload[8:]

        if not payload:
            return response

        # 解压缩
        if message_compression == CompressionType.GZIP:
            try:
                payload = CommonUtils.gzip_decompress(payload)
            except Exception as e:
                logger.error("Failed to decompress payload: %s", e)
                return response

        # 解析 payload
        try:
            if serialization_method == SerializationType.JSON:
                response.payload_msg = json.loads(payload.decode("utf-8"))
        except Exception as e:
            logger.error("Failed to parse payload: %s", e)

        return response


def extract_text(payload_msg) -> str:
    """从响应 payload 中提取转写文本。"""
    if not payload_msg:
        return ""
    result = payload_msg.get("result") or {}
    return (result.get("text") or "").strip()


class SaucLiveClient:
    """实时双向流式客户端：建立连接、推流 PCM 音频、接收转写结果。"""

    def __init__(self, url: str, config: Config):
        self.url = url
        self.config = config
        self.seq = 1
        self.session = None
        self.conn = None

    async def connect(self, payload: dict) -> None:
        self.session = aiohttp.ClientSession(trust_env=False)
        headers = RequestBuilder.new_auth_headers(self.config)
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        try:
            self.conn = await self.session.ws_connect(self.url, headers=headers, ssl=ssl_context, timeout=10)
            request = RequestBuilder.new_full_client_request(self.seq, payload)
            self.seq += 1
            await self.conn.send_bytes(request)
        except BaseException:
            await self.close()
            raise

    async def send_audio(self, segment: bytes, is_last: bool = False) -> None:
        request = RequestBuilder.new_audio_only_request(self.seq, segment, is_last=is_last)
        if not is_last:
            self.seq += 1
        await self.conn.send_bytes(request)

    async def recv(self) -> AsyncGenerator[AsrResponse, None]:
        async for msg in self.conn:
            if msg.type == aiohttp.WSMsgType.BINARY:
                response = ResponseParser.parse_response(msg.data)
                yield response
                if response.is_last_package or response.code != 0:
                    break
            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                break

    async def close(self) -> None:
        if self.conn and not self.conn.closed:
            await self.conn.close()
        if self.session and not self.session.closed:
            await self.session.close()
