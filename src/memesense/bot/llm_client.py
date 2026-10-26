"""DeepSeek 客户端边界；网络调用将在后续接入。"""

from typing import Sequence


class LLMClient:
    async def reply(self, messages: Sequence[dict[str, str]]) -> str:
        raise NotImplementedError("DeepSeek 客户端尚未接入；请勿在代码中硬编码密钥")
