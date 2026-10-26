# 显式采用人工二次复核标签

先通过 import_second_review.py 生成独立人工复核索引，再运行本转换。转换只创建新的标准已标注索引，不修改助手索引、人工导出或图片。不因类别数量自动调整任何标签。

字段关系：

| 新标准字段 | 取值 |
|---|---|
| intent_label | human_label |
| annotation_notes | human_note |
| annotation_status | annotated（要求全部 human_review_status=reviewed） |
| label_schema_version | 保留已校验版本，不自动升级 |
| assistant_intent_label | 原 intent_label |
| assistant_annotation_notes | 原 annotation_notes |
| assistant_annotation_status | 原 annotation_status |
| assistant_label_schema_version | 原 label_schema_version |
| effective_label_source | human_second_review |

human_label、human_note、human_review_status、reviewer_id、两种 reference_viewed、annotation_origin 及全部其他原字段保留。annotation_origin 仍表示起点为助手视觉试标，effective_label_source 表示当前采用人工结果；不能把二者混为同一含义。转换不证明多人独立复核或金标准质量。

命令示例（项目根目录，须先有真实完成的人工复核索引）：

```powershell
$Batch = 'outputs/msairs_pilot_20261016'
$New = "$Batch/human_adopted_v1"
.\.venv\Scripts\python.exe scripts/adopt_human_labels.py --input "$Batch/human_second_review_v1/meme_index_human_reviewed.csv" --baseline "$Batch/intent_trial_v1/meme_index_annotated.csv" --labels "$Batch/intent_annotation_v1/labels.yaml" --output "$New/meme_index_annotated.csv"
if ($LASTEXITCODE -ne 0) { throw '转换失败' }
.\.venv\Scripts\python.exe scripts/split_dataset.py --input "$New/meme_index_annotated.csv" --labels "$Batch/intent_annotation_v1/labels.yaml" --output-dir "$New/splits" --uncertain exclude --seed 42 --ratios 0.8 0.1 0.1
if ($LASTEXITCODE -ne 0) { throw '划分失败' }
.\.venv\Scripts\python.exe scripts/dataset_report.py --input "$New/meme_index_annotated.csv" --labels "$Batch/intent_annotation_v1/labels.yaml" --splits-dir "$New/splits" --output-dir "$New/report"
if ($LASTEXITCODE -ne 0) { throw '统计失败' }
```

不要预建 splits/report，命令要求新输出目录。原助手 baseline 必须与二次复核时相同。转换检查所有助手原字段均未变化，人工状态完整、标签有效、版本一致、来源及参考标志合法；缺失/重复/未知样本、重复转换或已存在输出均拒绝。

下游现有脚本无需改动：转换后 intent_label 已采用人工结果，uncertain 排除也按人工结果进行。同模板可有不同意图，仍按 template_id 整组划分；所有附加来源字段原样传递到分区 CSV。统计报告只表示数据一致性与模板隔离情况，不证明语义质量。

验证命令：`python -m unittest discover -s tests -p test_adopt_human_labels.py -v`。独立合成测试故意设置助手与人工标签冲突，并包括人工 uncertain、同模板多图、备注引号与换行，核验转换、归档、错误拒绝、禁止覆盖、划分及统计全过程。合成 human_label 不是真实人工标注，不混入正式数据或 MSAIRS 批次。
