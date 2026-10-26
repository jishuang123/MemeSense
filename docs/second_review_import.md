# 人工二次复核 CSV 校验与独立导入

使用 `scripts/import_second_review.py`，输入为二次复核页面导出的完整 CSV。来源仍是“助手视觉试标”，实际人工是否独立、是否经过仲裁不能仅靠文件校验证明。

在项目根目录执行；先把真实人工导出另存到以下 input 路径，不要用页面功能测试 CSV 冒充真实复核：

```powershell
$Batch = 'outputs/msairs_pilot_20261016'
$Export = "$Batch/human_second_review_v1/human_export.csv"
$Output = "$Batch/human_second_review_v1/meme_index_human_reviewed.csv"
$Arguments = @(
  '--input', $Export,
  '--baseline', "$Batch/intent_trial_v1/meme_index_annotated.csv",
  '--queue', "$Batch/collection_review_plan_v1/review_queue.json",
  '--labels', "$Batch/intent_annotation_v1/labels.yaml",
  '--output', $Output
)
.\.venv\Scripts\python.exe scripts/import_second_review.py @Arguments --check-only
if ($LASTEXITCODE -ne 0) { throw '校验失败' }
# 仅校验可接受 pending，实际导入必须全部 reviewed。
.\.venv\Scripts\python.exe scripts/import_second_review.py @Arguments
if ($LASTEXITCODE -ne 0) { throw '导入失败' }
```

输出必须尚不存在，拒绝覆盖输入或 data/raw 内输出。所有样本必须与 baseline 和 queue 完全对应；禁止重复、未知、遗漏或无效 sample_id。模板、图片路径、优先级及来源不能改变。标签版本须与快照严格一致；human_label 必须属于标签配置，reviewed 必须有标签，pending 必须为空。uncertain 是有效已填写标签，不是 pending。

assistant_reference_viewed、msairs_reference_viewed 必须为小写 true/false，并原样保留；它们是浏览器自报记录，不能验证用户在外部是否看过参考。reviewer_id 允许为空，以兼容已有页面“建议填写”的规则；建议真实人工复核填写代号。

输出保留 baseline 的所有字段，包括原 intent_label、annotation_notes、annotation_status、source、模板复核状态；人工结果使用独立 human_label、human_note、human_review_status 字段，并附 priority、annotation_origin、两种参考查看标志及 reviewer_id。不把助手结果伪装成人工结果，不自动覆盖或合并冲突标签。

**下游注意：现有 split_dataset.py 使用 intent_label，所以不要直接把此输出当作采用人工标签的划分输入。** 现在可用 `scripts/adopt_human_labels.py` 显式采用人工结果并保留助手字段，具体见 [采用人工标签说明](adopt_human_labels.md)。reviewed 不等于多人仲裁完成。

验证：`python -m unittest discover -s tests -p test_second_review_import.py -v`。测试覆盖合法及 uncertain 导入、未完成限制、编号/字段/版本/查看标志异常、清单过期、原字段保留和拒绝覆盖，全部使用 outputs 下独立合成数据。没有代填本批次真实人工结果。
