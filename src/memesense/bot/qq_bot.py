"""群聊上下文工具及 QQ 接入边界，不自动启动机器人。"""

from collections import OrderedDict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class ChatMessage:
    sender: str
    text: str
    timestamp: str


class GroupContext:
    """按群隔离且限制单条、条数和群数；暂不持久化。"""

    def __init__(self, max_messages: int = 12, max_chars: int = 500, max_groups: int = 100):
        if min(max_messages, max_chars, max_groups) < 1:
            raise ValueError("上下文限制必须为正整数")
        self.max_messages, self.max_chars, self.max_groups = max_messages, max_chars, max_groups
        self._groups: OrderedDict[str, deque[ChatMessage]] = OrderedDict()

    def add(self, group_id: str, sender: str, text: str, timestamp: str) -> None:
        if not text.strip():
            return
        if group_id not in self._groups:
            if len(self._groups) >= self.max_groups:
                self._groups.popitem(last=False)
            self._groups[group_id] = deque(maxlen=self.max_messages)
        self._groups.move_to_end(group_id)
        self._groups[group_id].append(ChatMessage(sender[:100], text.strip()[:self.max_chars], timestamp[:64]))

    def get(self, group_id: str) -> tuple[ChatMessage, ...]:
        return tuple(self._groups.get(group_id, ()))

    def reset(self, group_id: str) -> None:
        self._groups.pop(group_id, None)


def run() -> None:
    raise NotImplementedError("QQ 传输层尚未接入；后续连接 NapCatQQ / OneBot v11")
