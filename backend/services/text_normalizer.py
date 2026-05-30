COMMON_ASR_CORRECTIONS = {
    "开主会": "开组会",
    "主会": "组会",
}


def normalize_asr_text(text: str) -> str:
    normalized = text.strip()
    for source, target in COMMON_ASR_CORRECTIONS.items():
        normalized = normalized.replace(source, target)
    return normalized

