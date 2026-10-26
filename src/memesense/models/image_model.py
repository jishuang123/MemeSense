"""图像分类模型接口。"""

from pathlib import Path


class ImageModel:
    def predict(self, image_path: Path) -> dict[str, float]:
        """返回标签概率；模型实现待补充。"""
        raise NotImplementedError("图像模型尚未实现或训练")
