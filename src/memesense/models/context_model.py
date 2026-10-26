"""结合群聊上下文解释表情包的模型接口。"""

from pathlib import Path
from typing import Sequence


class ContextModel:
    def predict(self, image_path: Path, text: str, context: Sequence[str]) -> dict[str, float]:
        raise NotImplementedError("上下文模型尚未实现或训练")
