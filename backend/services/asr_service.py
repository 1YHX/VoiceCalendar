import os
import asyncio
import base64

import qiniu
import requests
from qiniu import QiniuMacAuth, config, http


def mock_asr() -> dict:
    return {
        "success": True,
        "text": "今天晚上八点提醒我提交代码",
        "mock": True,
    }


def _post_with_qiniu_auth(url: str, body: dict, auth: QiniuMacAuth):
    qiniu_auth = qiniu.auth.QiniuMacRequestsAuth(auth)
    timeout = config.get_default("connection_timeout")
    try:
        response = requests.post(url, json=body, auth=qiniu_auth, timeout=timeout)
    except Exception as exc:
        return None, http.ResponseInfo(None, exc)
    return http.__return_wrapper(response)


def _qiniu_asr_request(file_bytes: bytes) -> dict:
    access_key = os.getenv("QINIU_ACCESS_KEY", "")
    secret_key = os.getenv("QINIU_SECRET_KEY", "")
    if not access_key or not secret_key:
        raise ValueError("缺少 QINIU_ACCESS_KEY 或 QINIU_SECRET_KEY")

    url = os.getenv("QINIU_ASR_URL", "http://yitu-audio.qiniuapi.com/v2/asr")
    audio_base64 = base64.b64encode(file_bytes).decode("utf-8")
    body = {
        "audioDataBase64": audio_base64,
        "lang": "MANDARIN",
        "scene": "GENERAL",
    }
    auth = QiniuMacAuth(access_key, secret_key)
    ret, response_info = _post_with_qiniu_auth(url, body, auth)

    if response_info.status_code != 200:
        error_text = getattr(response_info, "text_body", "") or response_info.error or "七牛 ASR 请求失败"
        raise ValueError(f"七牛 ASR 请求失败：{error_text}")
    if not ret:
        raise ValueError("七牛 ASR 返回为空")
    if ret.get("rtn") != 0:
        raise ValueError(f"七牛 ASR 识别失败：{ret.get('message', '未知错误')}")

    text = ret.get("resultText", "")
    if not text:
        raise ValueError("七牛 ASR 返回空识别文本，请确认音频有声音且格式受支持")

    return {
        "success": True,
        "text": text,
        "mock": False,
    }


async def qiniu_asr(file_bytes: bytes, filename: str) -> dict:
    if not file_bytes:
        raise ValueError("上传音频为空")
    return await asyncio.to_thread(_qiniu_asr_request, file_bytes)


async def recognize_audio(file_bytes: bytes, filename: str) -> dict:
    if os.getenv("ASR_MOCK", "true").lower() == "true":
        return mock_asr()
    return await qiniu_asr(file_bytes, filename)
