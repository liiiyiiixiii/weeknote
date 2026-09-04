import asyncio

from app import asr


def test_audio_limit_counts_all_chunks_not_only_current_buffer(monkeypatch):
    monkeypatch.setattr(asr, "API_KEY", "fake")
    monkeypatch.setattr(asr, "MAX_AUDIO_BYTES", 10)
    monkeypatch.setattr(asr, "MAX_AUDIO_SECONDS", 1)

    created = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.closed = False
            created.append(self)

        async def connect(self, payload):
            return None

        async def send_audio(self, chunk, is_last=False):
            return None

        async def recv(self):
            while True:
                await asyncio.sleep(60)
                yield None

        async def close(self):
            self.closed = True

    class FakeWebSocket:
        def __init__(self):
            self.messages = [
                {"type": "websocket.receive", "bytes": b"12345678"},
                {"type": "websocket.receive", "bytes": b"1234"},
            ]
            self.sent = []

        async def accept(self):
            return None

        async def receive(self):
            return self.messages.pop(0)

        async def send_json(self, value):
            self.sent.append(value)

        async def close(self):
            return None

    monkeypatch.setattr(asr.sauc_protocol, "SaucLiveClient", FakeClient)
    websocket = FakeWebSocket()
    received = asyncio.run(asr.handle_asr(websocket))

    assert received == 8
    assert websocket.sent[-1]["type"] == "error"
    assert "最多 1 秒" in websocket.sent[-1]["message"]
    assert created[0].closed is True


def test_upstream_failure_stops_waiting_for_browser_and_hides_exception(monkeypatch):
    monkeypatch.setattr(asr, "API_KEY", "fake")

    class FakeClient:
        async def connect(self, payload):
            return None

        async def recv(self):
            raise RuntimeError("sensitive upstream detail")
            yield  # pragma: no cover

        async def close(self):
            return None

    class FakeWebSocket:
        def __init__(self):
            self.sent = []

        async def accept(self):
            return None

        async def receive(self):
            await asyncio.Event().wait()

        async def send_json(self, value):
            self.sent.append(value)

        async def close(self):
            return None

    monkeypatch.setattr(asr.sauc_protocol, "SaucLiveClient", lambda *args, **kwargs: FakeClient())
    websocket = FakeWebSocket()
    received = asyncio.run(asyncio.wait_for(asr.handle_asr(websocket), timeout=1))

    assert received == 0
    assert websocket.sent == [{"type": "error", "message": "转写中断，请稍后重试"}]
