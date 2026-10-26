# 助手预标审核：批次校验与独立导入

适用于当前 batch01 至 batch07。审核页面不需要改动或刷新。你完成一批后，保留浏览器下载的CSV并交回即可。

## 命令

从项目根目录使用已配置环境运行。先检查（允许未完成备份，不写文件）：

```powershell
.venv/Scripts/python.exe scripts/import_assisted_review.py --batch batch02 --input "下载文件的完整路径.csv" --check-only
```

全部完成后导入，输出目录必须不存在：

```powershell
.venv/Scripts/python.exe scripts/import_assisted_review.py --batch batch02 --input "下载文件的完整路径.csv" --output-dir outputs/human_review_imports/batch02_first
```

batch01对应首批24张；batch02–batch07对应剩余127张的六个页面。校验必须匹配所选批次的完整样本集合；不能将不同批次随意拼接或只导出部分行。

## 校验与来源

- 样本集合、唯一性、列名、行宽、模板、路径、优先级、标签版本均按交付材料核对。
- 助手建议、理由、预标来源、审核模式及规则标识必须保持原样。助手参考查看标记必须为true，因为页面直接展示建议。
- 人工标签须合法，标签和非空依据齐全才算reviewed；未完成只允许检查，不能导入。
- 实际审核者必填；MSAIRS查看标记只能是true或false，不将自报记录当作独立性证明。
- 批次1与批次2–7的原有导出字段不同，由程序分别识别，不要求用户手工改CSV。

## 输出

新目录内包含 reviewed_batch.csv、original_export.csv、import_audit.json。原始导出按字节保存，审计记录文件哈希和采用的批次资料。

reviewed_batch.csv保留原助手索引的全部列为baseline_*（包括旧标签与intent-draft-v1版本），保持新助手预标及其理由，再保留人工标签、依据、参考记录与intent-calibration-v2版本。不会伪改旧基线版本，也不会用新人工标签覆盖助手原标签。

这是人工审核助手预标的记录，不是独立盲标。当前输出尚不是训练用标准索引，不直接运行旧adopt_human_labels.py或划分脚本；下一步在真实审核结果核验后，显式采用human_label、汇总覆盖率并保留所有来源，再生成新的标准索引。

没有修改审核页面、原图、既有索引或已下载答案。所有测试使用临时TEST_ONLY填写，七个页面实际导出的空白备份已验证可通过检查，未保存为真实人工结果。
