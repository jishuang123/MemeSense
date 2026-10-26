"""图像与 OCR 文本融合模型接口。"""

from pathlib import Path


class MultimodalModel:
    def predict(self, image_path: Path, text: str) -> dict[str, float]:
        raise NotImplementedError("多模态模型尚未实现或训练")
