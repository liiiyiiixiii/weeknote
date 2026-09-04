"""豆包（火山引擎）SAUC 实时语音识别桥接：浏览器 WebSocket ↔ 豆包 WebSocket。"""

import asyncio
import json
import logging
import struct

from fastapi import WebSocket

from app import sauc_protocol
from app.core.config import AppSettings

SETTINGS = AppSettings.from_env()

logger = logging.getLogger(__name__)

ASR_URL = SETTINGS.volc_asr_url
RESOURCE_ID = SETTINGS.volc_resource_id
API_KEY = SETTINGS.volc_api_key
APP_KEY = SETTINGS.volc_app_key
ACCESS_KEY = SETTINGS.volc_access_key

SEG_MS = 200  # 每包音频时长（毫秒）
AUDIO_BYTES_PER_SECOND = 16000 * 2  # 16kHz * 16bit 单声道
SEG_BYTES = AUDIO_BYTES_PER_SECOND * SEG_MS // 1000
MAX_AUDIO_SECONDS = SETTINGS.asr_max_seconds
MAX_AUDIO_BYTES = AUDIO_BYTES_PER_SECOND * MAX_AUDIO_SECONDS


def make_wav_header(data_size: int = 0xFFFFFFFF) -> bytes:
    """16kHz / 16bit / 单声道 PCM 的 44 字节 WAV 头（流式模式 data 长度未知，填最大值）。"""
    riff_size = (36 + data_size) & 0xFFFFFFFF
    return (
        b"RIFF"
        + struct.pack("<I", riff_size)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
        + b"data"
        + struct.pack("<I", data_size)
    )


WAV_HEADER = make_wav_header()


def build_payload() -> dict:
    return {
        "user": {"uid": "zhoubao-assistant"},
        "audio": {"format": "wav", "codec": "raw", "rate": 16000, "bits": 16, "channel": 1},
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
            "enable_ddc": True,
            "show_utterances": True,
            "enable_nonstream": False,
        },
    }


async def handle_asr(websocket: WebSocket) -> int:
    """浏览器音频 → 豆包 ASR → 转写文本回传，返回实际接收的 PCM 字节数。"""
    await websocket.accept()
    total_audio_bytes = 0

    if not API_KEY and not (APP_KEY and ACCESS_KEY):
        await websocket.send_json(
            {
                "type": "error",
                "message": "未配置火山引擎 ASR 凭据，请在 backend/.env 填写 VOLC_API_KEY（或 VOLC_APP_KEY + VOLC_ACCESS_KEY）",
            }
        )
        await websocket.close()
        return 0

    config = sauc_protocol.Config(api_key=API_KEY, app_key=APP_KEY, access_key=ACCESS_KEY, resource_id=RESOURCE_ID)
    client = sauc_protocol.SaucLiveClient(ASR_URL, config)
    try:
        await client.connect(build_payload())
    except Exception as e:
        logger.warning("SAUC 连接失败: %s", e)
        await client.close()
        await websocket.send_json({"type": "error", "message": "语音服务暂时不可用，请稍后重试"})
        await websocket.close()
        return 0

    buffer = bytearray()
    state = {"finalized": False, "cancelled": False}
    header_sent = False

    async def browser_to_asr():
        nonlocal header_sent, total_audio_bytes
        try:
            while True:
                msg = await websocket.receive()
                mtype = msg.get("type")
                if mtype == "websocket.disconnect":
                    break
                if mtype != "websocket.receive":
                    continue
                if msg.get("bytes"):
                    incoming = msg["bytes"]
                    if total_audio_bytes + len(incoming) > MAX_AUDIO_BYTES:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": f"单次录音最多 {MAX_AUDIO_SECONDS} 秒",
                            }
                        )
                        state["cancelled"] = True
                        return
                    total_audio_bytes += len(incoming)
                    buffer.extend(incoming)
                    while len(buffer) >= SEG_BYTES:
                        chunk = bytes(buffer[:SEG_BYTES])
                        del buffer[:SEG_BYTES]
                        if not header_sent:
                            chunk = WAV_HEADER + chunk
                            header_sent = True
                        await client.send_audio(chunk)
                elif msg.get("text"):
                    try:
                        data = json.loads(msg["text"])
                    except Exception:
                        continue
                    kind = data.get("type")
                    if kind == "end":
                        remaining = bytes(buffer)
                        buffer.clear()
                        if not header_sent:
                            remaining = WAV_HEADER + remaining
                            header_sent = True
                        await client.send_audio(remaining, is_last=True)
                        state["finalized"] = True
                        return
                    if kind == "cancel":
                        state["cancelled"] = True
                        return
        except Exception as e:
            logger.warning("浏览器上行中断: %s", e)

    async def asr_to_browser():
        try:
            async for resp in client.recv():
                if resp.code != 0:
                    logger.warning("SAUC 返回错误 code=%s payload=%r", resp.code, resp.payload_msg)
                    await websocket.send_json({"type": "error", "message": "语音识别失败，请稍后重试"})
                    return
                text = sauc_protocol.extract_text(resp.payload_msg)
                if resp.is_last_package:
                    await websocket.send_json({"type": "final", "text": text})
                    return
                if text:
                    await websocket.send_json({"type": "partial", "text": text})
        except Exception as e:
            logger.warning("ASR 下行中断: %s", e)
            try:
                await websocket.send_json({"type": "error", "message": "转写中断，请稍后重试"})
            except Exception:
                pass

    t1 = asyncio.create_task(browser_to_asr())
    t2 = asyncio.create_task(asr_to_browser())

    try:
        done, _ = await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
        if t2 in done and not t1.done():
            # 上游识别服务已经结束或报错时，不再无限等待浏览器继续上行。
            t1.cancel()
            await asyncio.gather(t1, return_exceptions=True)
        elif t1 in done:
            await asyncio.gather(t1, return_exceptions=True)

        if state["finalized"] and not t2.done():
            try:
                await asyncio.wait_for(asyncio.shield(t2), timeout=15)
            except TimeoutError:
                t2.cancel()
        elif not t2.done():
            t2.cancel()
    finally:
        if not t1.done():
            t1.cancel()
        if not t2.done():
            t2.cancel()
        await asyncio.gather(t1, t2, return_exceptions=True)
        await client.close()
        try:
            await websocket.close()
        except Exception:
            pass
    return total_audio_bytes
