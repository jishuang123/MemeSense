"""推理结果结构与待实现入口。"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Prediction:
    label: str
    confidence: float
    ocr_text: str


class Predictor:
    def predict(self, image_path: Path, context: tuple[str, ...] = ()) -> Prediction:
        raise NotImplementedError("请先实现 OCR、加载模型权重及标签映射")
