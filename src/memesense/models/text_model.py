"""OCR 文本分类模型接口。"""


class TextModel:
    def predict(self, text: str) -> dict[str, float]:
        raise NotImplementedError("文本模型尚未实现或训练")
