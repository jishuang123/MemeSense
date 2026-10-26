"""按 SHA-256 分组划分，避免完全重复的图片跨集合泄漏。"""

import math
import random


def split_by_template(rows: list[dict[str, str]],
                      ratios: tuple[float, float, float] = (0.8, 0.1, 0.1),
                      seed: int = 42, uncertain: str = 'exclude'
                      ) -> tuple[dict[str, list[dict[str, str]]], list[dict[str, str]]]:
    """按模板组数近似分配；整组随机划分，不修改输入或进行类别分层。"""
    if len(ratios) != 3 or any(not math.isfinite(r) or r < 0 for r in ratios) or not math.isclose(sum(ratios), 1.0):
        raise ValueError('三个划分比例必须非负、有限且总和为 1')
    if uncertain not in {'exclude', 'include'}:
        raise ValueError('uncertain 策略只能是 exclude 或 include')
    groups: dict[str, list[dict[str, str]]] = {}
    excluded = []
    for row in rows:
        if uncertain == 'exclude' and row['intent_label'] == 'uncertain':
            excluded.append(row.copy())
        else:
            groups.setdefault(row['template_id'], []).append(row.copy())
    keys = sorted(groups)
    random.Random(seed).shuffle(keys)
    # 最大余数法：先向下取整，再按余数补足模板数量。
    quotas = [len(keys) * ratio for ratio in ratios]
    counts = [math.floor(quota) for quota in quotas]
    priority = sorted(range(3), key=lambda i: (-(quotas[i] - counts[i]), i))
    for i in priority[:len(keys) - sum(counts)]:
        counts[i] += 1
    active = [i for i, ratio in enumerate(ratios) if ratio > 0]
    # 数据足够时每个非零比例集合至少有一组；小样本比例必然有偏差。
    if len(keys) >= len(active):
        for i in active:
            if counts[i] == 0:
                donor = max(active, key=lambda j: counts[j])
                counts[donor] -= 1
                counts[i] += 1
    result = {}
    offset = 0
    for name, count in zip(('train', 'val', 'test'), counts):
        result[name] = sorted([row for key in keys[offset:offset + count] for row in groups[key]],
                              key=lambda row: int(row['sample_id'][1:]))
        offset += count
    excluded.sort(key=lambda row: int(row['sample_id'][1:]))
    return result, excluded


def split_records(rows: list[dict], ratios: tuple[float, float, float] = (0.8, 0.1, 0.1),
                  seed: int = 42) -> dict[str, list[dict]]:
    if len(ratios) != 3 or any(not math.isfinite(r) or r < 0 for r in ratios) or not math.isclose(sum(ratios), 1.0):
        raise ValueError("train / val / test 比例须非负且总和为 1")
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["sha256"], []).append(row)
    keys = sorted(groups)
    random.Random(seed).shuffle(keys)
    train_end = int(len(keys) * ratios[0])
    val_end = train_end + int(len(keys) * ratios[1])
    return {name: [row for key in selected for row in groups[key]]
            for name, selected in zip(("train", "val", "test"),
                                      (keys[:train_end], keys[train_end:val_end], keys[val_end:]))}
