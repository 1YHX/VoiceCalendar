import asyncio
import base64
import os
import uuid

from tencentcloud.common import credential
from tencentcloud.common.common_client import CommonClient
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile


def _unwrap_tencent_response(response: dict) -> dict:
    return response.get("Response", response)


def _tencent_tts_request(text: str) -> dict:
    secret_id = os.getenv("TENCENT_SECRET_ID", "")
    secret_key = os.getenv("TENCENT_SECRET_KEY", "")
    if not secret_id or not secret_key:
        raise ValueError("缺少 TENCENT_SECRET_ID 或 TENCENT_SECRET_KEY")

    http_profile = HttpProfile()
    http_profile.endpoint = os.getenv("TENCENT_TTS_ENDPOINT", "tts.tencentcloudapi.com")
    client_profile = ClientProfile()
    client_profile.httpProfile = http_profile

    cred = credential.Credential(secret_id, secret_key)
    client = CommonClient(
        "tts",
        "2019-08-23",
        cred,
        os.getenv("TENCENT_TTS_REGION", "ap-shanghai"),
        profile=client_profile,
    )
    codec = os.getenv("TENCENT_TTS_CODEC", "wav")
    params = {
        "Text": text[:150],
        "SessionId": f"voice-calendar-{uuid.uuid4()}",
        "Volume": float(os.getenv("TENCENT_TTS_VOLUME", "0")),
        "Speed": float(os.getenv("TENCENT_TTS_SPEED", "0")),
        "ProjectId": 0,
        "ModelType": 1,
        "VoiceType": int(os.getenv("TENCENT_TTS_VOICE_TYPE", "101001")),
        "PrimaryLanguage": 1,
        "SampleRate": int(os.getenv("TENCENT_TTS_SAMPLE_RATE", "16000")),
        "Codec": codec,
    }

    try:
        response = client.call_json("TextToVoice", params)
    except TencentCloudSDKException as exc:
        raise ValueError(f"腾讯云 TTS 请求失败：{exc}") from exc

    payload = _unwrap_tencent_response(response)
    audio = payload.get("Audio", "")
    if not audio:
        request_id = payload.get("RequestId") or response.get("RequestId", "")
        raise ValueError(f"腾讯云 TTS 返回空音频，request_id={request_id}")

    return {
        "audio_base64": audio,
        "audio_mime": "audio/mpeg" if codec == "mp3" else "audio/wav",
    }


async def synthesize_speech(text: str) -> dict:
    if not text.strip():
        raise ValueError("TTS 文本为空")
    return await asyncio.to_thread(_tencent_tts_request, text.strip())
