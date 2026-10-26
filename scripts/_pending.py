"""尚未实现的实验入口：支持帮助信息，但绝不伪装训练成功。"""

import argparse


def pending(task: str) -> None:
    parser = argparse.ArgumentParser(description=f"MemeSense {task}（待实现）")
    parser.add_argument("--config", default="configs/model.yaml", help="未来实验配置路径")
    parser.parse_args()
    parser.exit(2, f"{task}尚未实现。请先确定标签、数据集和模型架构；当前不会生成权重或指标。\n")
