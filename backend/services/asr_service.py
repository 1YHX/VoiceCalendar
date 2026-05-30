import os


def mock_asr() -> dict:
    return {
        "success": True,
        "text": "今天晚上八点提醒我提交代码",
        "mock": True,
    }


async def qiniu_asr_placeholder(file_bytes: bytes, filename: str) -> dict:
    return {
        "success": False,
        "text": "",
        "mock": False,
        "message": "七牛云 ASR 接口已预留，当前 MVP 请使用 ASR_MOCK=true。",
    }


async def recognize_audio(file_bytes: bytes, filename: str) -> dict:
    if os.getenv("ASR_MOCK", "true").lower() == "true":
        return mock_asr()
    return await qiniu_asr_placeholder(file_bytes, filename)

