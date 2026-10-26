"""OCR 契约；后续接入选定引擎，不以空字符串伪装成功。"""

from pathlib import Path
from typing import Protocol


class OCREngine(Protocol):
    def recognize(self, image_path: Path) -> str:
        """返回图片中的文字；无文字可返回空字符串，失败应抛异常。"""
        ...


def extract_text(image_path: Path, engine: OCREngine | None = None) -> str:
    if engine is None:
        raise NotImplementedError("尚未配置 OCR 引擎")
    return engine.recognize(image_path)
