import asyncio
import base64
import os
import uuid

from tencentcloud.common import credential
from tencentcloud.common.common_client import CommonClient
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile


def mock_asr() -> dict:
    return {
        "success": True,
        "text": "今天晚上八点提醒我提交代码",
        "mock": True,
    }


def _detect_voice_format(filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "wav"
    if suffix in {"wav", "mp3", "m4a", "ogg", "amr"}:
        return suffix
    return "wav"


def _unwrap_tencent_response(response: dict) -> dict:
    return response.get("Response", response)


def _tencent_asr_request(file_bytes: bytes, filename: str) -> dict:
    secret_id = os.getenv("TENCENT_SECRET_ID", "")
    secret_key = os.getenv("TENCENT_SECRET_KEY", "")
    if not secret_id or not secret_key:
        raise ValueError("缺少 TENCENT_SECRET_ID 或 TENCENT_SECRET_KEY")

    http_profile = HttpProfile()
    http_profile.endpoint = os.getenv("TENCENT_ASR_ENDPOINT", "asr.tencentcloudapi.com")
    client_profile = ClientProfile()
    client_profile.httpProfile = http_profile

    # 腾讯云一句话识别 SourceType=1 支持直接上传本地音频 base64。
    cred = credential.Credential(secret_id, secret_key)
    client = CommonClient(
        "asr",
        "2019-06-14",
        cred,
        os.getenv("TENCENT_ASR_REGION", "ap-shanghai"),
        profile=client_profile,
    )
    params = {
        "ProjectId": 0,
        "SubServiceType": 2,
        "EngSerViceType": os.getenv("TENCENT_ASR_ENGINE", "16k_zh"),
        "SourceType": 1,
        "VoiceFormat": _detect_voice_format(filename),
        "UsrAudioKey": f"voice-calendar-{uuid.uuid4()}",
        "Data": base64.b64encode(file_bytes).decode("utf-8"),
        "DataLen": len(file_bytes),
    }

    try:
        response = client.call_json("SentenceRecognition", params)
    except TencentCloudSDKException as exc:
        raise ValueError(f"腾讯云 ASR 请求失败：{exc}") from exc

    payload = _unwrap_tencent_response(response)
    result = payload.get("Result", "")
    if not result:
        request_id = payload.get("RequestId") or response.get("RequestId", "")
        raise ValueError(f"腾讯云 ASR 返回空识别文本，request_id={request_id}")

    return {
        "success": True,
        "text": result,
        "mock": False,
    }


async def tencent_asr(file_bytes: bytes, filename: str) -> dict:
    if not file_bytes:
        raise ValueError("上传音频为空")
    # 腾讯云 SDK 是同步调用，放到线程里执行，避免阻塞 FastAPI 事件循环。
    return await asyncio.to_thread(_tencent_asr_request, file_bytes, filename)


async def recognize_audio(file_bytes: bytes, filename: str) -> dict:
    if os.getenv("ASR_MOCK", "true").lower() == "true":
        return mock_asr()
    return await tencent_asr(file_bytes, filename)
