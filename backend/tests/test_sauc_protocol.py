import gzip
import json
import struct

from app import sauc_protocol as sp


def _build_server_response(payload_msg, seq=42, is_last=True):
    header = bytearray()
    header.append((sp.ProtocolVersion.V1 << 4) | 1)
    flags = sp.MessageTypeSpecificFlags.POS_SEQUENCE | (0b0010 if is_last else 0)
    header.append((sp.MessageType.SERVER_FULL_RESPONSE << 4) | flags)
    header.append((sp.SerializationType.JSON << 4) | sp.CompressionType.GZIP)
    header.append(0x00)
    body = gzip.compress(json.dumps(payload_msg, ensure_ascii=False).encode("utf-8"))
    msg = bytearray(header)
    msg.extend(struct.pack(">i", seq))
    msg.extend(struct.pack(">I", len(body)))
    msg.extend(body)
    return bytes(msg)


def test_parse_response_roundtrip():
    payload_msg = {
        "audio_info": {"duration": 8040},
        "result": {"text": "您好，我是您的 AI 助手。", "utterances": []},
    }
    resp = sp.ResponseParser.parse_response(_build_server_response(payload_msg))
    assert resp.code == 0
    assert resp.is_last_package is True
    assert resp.payload_sequence == 42
    assert resp.payload_msg["result"]["text"] == "您好，我是您的 AI 助手。"


def test_extract_text():
    assert sp.extract_text({"result": {"text": " 你好 "}}) == "你好"
    assert sp.extract_text(None) == ""
    assert sp.extract_text({"foo": 1}) == ""


def test_full_request_roundtrip():
    payload = {"request": {"model_name": "bigmodel"}, "audio": {"rate": 16000}}
    req = sp.RequestBuilder.new_full_client_request(1, payload)
    assert req[0] == (sp.ProtocolVersion.V1 << 4) | 1
    assert req[1] == (sp.MessageType.CLIENT_FULL_REQUEST << 4) | sp.MessageTypeSpecificFlags.POS_SEQUENCE
    assert struct.unpack(">i", req[4:8])[0] == 1
    size = struct.unpack(">I", req[8:12])[0]
    body = gzip.decompress(req[12 : 12 + size])
    assert json.loads(body)["audio"]["rate"] == 16000


def test_last_audio_request_has_negative_seq():
    req = sp.RequestBuilder.new_audio_only_request(7, b"\x00" * 16, is_last=True)
    assert req[1] == (sp.MessageType.CLIENT_AUDIO_ONLY_REQUEST << 4) | sp.MessageTypeSpecificFlags.NEG_WITH_SEQUENCE
    assert struct.unpack(">i", req[4:8])[0] == -7


def test_mid_audio_request_has_positive_seq():
    req = sp.RequestBuilder.new_audio_only_request(7, b"\x00" * 16, is_last=False)
    assert req[1] == (sp.MessageType.CLIENT_AUDIO_ONLY_REQUEST << 4) | sp.MessageTypeSpecificFlags.POS_SEQUENCE
    assert struct.unpack(">i", req[4:8])[0] == 7
