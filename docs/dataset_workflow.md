# MemeSense 数据集构建操作指南

适用范围：当前 CSV 数据集流水线，从原图入库到统计审计。本文不涉及 OCR、模型训练、QQ Bot 或 LLM。`ocr_text` 保留为空，不需要配置 API Key。

## 1. 执行顺序与职责

```text
人工收集并放入原图
  → prepare_data.py：增量索引
  → 固定本批索引与标签配置快照
  → deduplicate.py：候选模板分组
  → build_review_page.py：生成模板复核页
  → 人工检查、修正 template_id、标记、下载 CSV
  → import_reviewed.py：校验、导入已复核索引
  → build_annotation_page.py：生成交流意图标注页
  → 人工选择意图、填写备注、下载 CSV
  → import_annotations.py：校验、导入已标注索引
  → split_dataset.py：按模板整组划分
  → dataset_report.py：统计与独立审计
```

| 阶段 | 输入 | 输出 | 是否需要人工操作 |
| --- | --- | --- | --- |
| 原图入库 | 收集的图片 | 原图目录 | 是：筛选、放置、维护来源 |
| 索引 | 原图目录、已有累计索引（若有） | meme_index.csv | 检查 warning 和异常文件 |
| 候选模板 | 固定的批次索引 | meme_index_with_templates.csv、near_duplicate_pairs.csv | 暂不确认模板 |
| 模板复核 | 候选 CSV、原图 | HTML、浏览器下载的复核 CSV | 是：查看图片、拆组/合组、标记 |
| 复核导入 | 下载 CSV、候选 baseline | meme_index_reviewed.csv | 处理校验错误或未决项 |
| 意图标注 | 已复核索引、标签 YAML、原图 | HTML、浏览器下载的标注 CSV | 是：逐样本选择标签、备注 |
| 标注导入 | 下载 CSV、已复核 baseline、标签 YAML | meme_index_annotated.csv | 处理校验错误或未完成项 |
| 划分 | 已标注索引、标签 YAML | train/val/test.csv、排除清单、划分报告 | 决定比例、种子与 uncertain 策略 |
| 统计审计 | 已标注索引、完整划分目录 | dataset_report.html/json | 阅读错误、警告和分布 |

## 2. 环境准备

在项目根目录打开 PowerShell。需要 Python 3.11+，项目已有 `.venv` 时不要重复创建：

```powershell
# 仅首次没有虚拟环境时执行
python -m venv .venv

# 每次打开新终端后激活
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
```

如果 PowerShell 不允许执行激活脚本，可把下文的 `python` 替换为 `.\.venv\Scripts\python.exe -X utf8`，无需更改系统执行策略。命令行工具可用 `--help` 查看参数。

按阶段逐条执行，不要一次粘贴整篇指南。PowerShell 中某条 Python 命令失败后，下一条命令不一定自动停止；看到 ERROR 或非零退出码时先处理，不继续复制或导入旧结果。编写批处理时，每条 Python 命令之后添加：

```powershell
if ($LASTEXITCODE -ne 0) { throw "上一条 Python 命令失败：$LASTEXITCODE" }
```

## 3. 正式数据与测试数据隔离

| 数据类型 | 位置与规则 |
| --- | --- |
| 正式原图 | `data/raw/images/`，采集放入后只读使用；不在此目录保存 CSV、页面或缩略图 |
| 正式累计索引 | `data/interim/meme_index.csv`，重复扫描更新它，保留稳定 sample_id |
| 正式批次快照/候选 | `data/interim/<批次>/`，保留生成复核页时的 baseline |
| 正式人工下载 | `data/annotations/<批次>/`，保存浏览器下载的新 CSV，不能覆盖 baseline |
| 正式确认结果 | `data/processed/<批次>/`，存放已复核、已标注索引和划分 |
| 正式页面/报告 | `outputs/formal/<批次>/`，不把它当作原数据目录 |
| 独立测试 | `outputs/<独立测试目录>/` 下存放测试原图、索引、人工下载、划分、页面及报告；所有相关参数显式指定 |

测试与正式数据即使 sample_id 同为 M0001，也属于不同数据集，不能合并。已有合成图片、故意损坏图、故意泄漏划分以及全部 uncertain 的验收结果都只供功能测试，不是正式数据。

`data/`、`outputs/` 默认被 Git 忽略。请自行备份原图、CSV、标签配置快照和报告，不能依赖代码提交保存这些文件。

### 正式运行：设置路径

先人工将 jpg/jpeg/png/webp 图片放入 `data/raw/images/`。支持子目录和大写扩展名；本流水线不扫描 GIF。不要移动或重命名已有图片来整理顺序，路径变化会被视为新样本。

选择尚未使用的批次名，然后设置以下变量。后续第 4～11 节共用这些变量：

```powershell
$Batch = 'v001'
$Images = 'data/raw/images'
$MasterIndex = 'data/interim/meme_index.csv'
$Interim = "data/interim/$Batch"
$Annotations = "data/annotations/$Batch"
$Processed = "data/processed/$Batch"
$Views = "outputs/formal/$Batch"
```

### 独立测试：改用这一组路径

测试时**不要运行上一组正式路径设置**。使用新的测试目录，人工将少量测试图片放入下面的 `$Images`。如果参考此前测试图片，复制到新测试目录或只读引用原 fixtures，不改动原文件。

```powershell
$Sandbox = 'outputs/manual_dataset_test_v001'
$Images = "$Sandbox/images"
$MasterIndex = "$Sandbox/meme_index.csv"
$Interim = "$Sandbox/interim"
$Annotations = "$Sandbox/annotations"
$Processed = "$Sandbox/processed"
$Views = "$Sandbox/pages"
if (Test-Path -LiteralPath $Sandbox) { throw "测试目录已存在，请换一个全新的名称：$Sandbox" }
New-Item -ItemType Directory -Path $Images
```

### 为本批创建新目录并固定标签配置

完成上述二选一设置后执行：

```powershell
foreach ($Directory in @($Interim, $Annotations, $Processed, $Views)) {
    if (Test-Path -LiteralPath $Directory) { throw "目录已存在，请使用新批次：$Directory" }
}
New-Item -ItemType Directory -Path $Interim, $Annotations, $Processed, $Views
$Labels = "$Interim/labels.yaml"
Copy-Item -LiteralPath 'configs/labels.yaml' -Destination $Labels
```

先确认标签初稿，再复制快照。修改标签集合或含义时更新 YAML 的 `version`，另开批次；不要在同一标注批次中途改版本。当前初稿为 `intent-draft-v1`，不是最终学术分类标准。

## 4. 生成索引并固定批次输入

```powershell
python scripts/prepare_data.py --input "$Images" --output "$MasterIndex"
if ($LASTEXITCODE -ne 0) { throw '索引生成失败，不创建批次快照' }
if (Test-Path -LiteralPath "$Interim/meme_index.csv") { throw '批次索引快照已存在，请勿覆盖' }
Copy-Item -LiteralPath $MasterIndex -Destination "$Interim/meme_index.csv"
```

复制命令仅在刚创建的新批次执行一次，不用它覆盖已有批次快照。后续均以 `$Interim/meme_index.csv` 为本批固定输入，累计索引可在下一批继续扫描。

输出包含 sample_id、原始文件名、相对 image_path、width、height、file_size、64 位 phash，以及初始为空的 template_id、ocr_text 和默认 unknown 的 source。

人工检查日志：

- 每张可读图片一条记录；同路径重跑保持编号，新路径从历史最大编号续号。不要删除累计索引后重扫，否则无法沿用历史编号。
- 损坏图片会 warning 并跳过。已有记录对应的图片丢失或变坏时会保留历史记录，不代表当前图片仍可用。
- 原图目录为空时会生成只有表头的 CSV；后续人工导入不能把它当成有效数据集。
- 保持输入根目录和相对路径规则不变。正式批次开始后固定原图内容，避免 CSV 中的旧 pHash 与后来替换的图片不一致。

若需修复历史异常记录，先备份累计索引并人工处理，再重新生成新批次；不要在复核 CSV 中删行，导入会检查遗漏样本。

## 5. pHash 候选模板分组

```powershell
python scripts/deduplicate.py --input "$Interim/meme_index.csv" --output "$Interim/meme_index_with_templates.csv" --pairs "$Interim/near_duplicate_pairs.csv" --threshold 6
```

程序仅计算 CSV 中 pHash 的汉明距离，不删除原图。距离 ≤ 6 的图片建立联系，再按连通关系分组；T0001 等候选编号取自组内最小 sample_id。单张也有模板编号，无效 pHash 保留行但模板留空。

阈值 6 是初始参数，需要人工复核后再决定是否调整。A 类似 B、B 类似 C，并不保证 A 类似 C。不同图片的 pHash 相同也不能证明原文件相同。

这两个输出会被同路径重跑替换，因此**开始人工复核后不得重跑覆盖该 baseline**。要改阈值或加入新图片，另开批次。

## 6. 人工模板复核及 CSV 下载

```powershell
python scripts/build_review_page.py --input "$Interim/meme_index_with_templates.csv" --images "$Images" --output "$Views/template_review.html" --threshold 6
Invoke-Item "$Views/template_review.html"
```

在浏览器中逐组操作：

1. 查看缩略图、sample_id、路径和与参照图的距离；切换参照图检查传递分组，必要时自行只读打开原图查看细节。页面放大的是缩略图。
2. 对不确定组标记“疑似误分组”，不要为通过导入而直接确认。
3. 按图片修改 template_id：分配未使用的合法编号以拆组，使用现有编号以合组。例如 T0100；不得为 T0000、任意文字或带空格的编号。
4. 页面仍按原候选组排列，修改编号会将该展示组重置为“未复核”。确认最终编号后，再点击“分组正确”。需要确认合组后的整体时，先导出并重新生成页面再检查。
5. 点击“导出复核 CSV”，确认浏览器已保存文件。将下载的新文件保存到 `$Annotations/review_export.csv`（不要覆盖之前的下载；后续用 `_v2` 等新文件名）。

这里的 `$Annotations/...` 是前文变量对应的实际目录，浏览器另存对话框不会展开 PowerShell 变量。可以在终端执行 `Write-Output $Annotations` 查看目录。

如果浏览器自动下载到“下载”目录而没有询问保存位置，可在文件管理器中**复制**该新下载文件到本批 annotations 目录并重命名为 `review_export.csv`；不要选择替换已有文件。先确认实际下载完成，再执行第 7 节。`intent_export.csv` 同理。系统可能隐藏 `.csv` 扩展名，重命名后应核对实际文件名，避免变成 `.csv.csv`。

浏览器编辑只存在内存中，刷新或关闭会丢失尚未导出的修改。筛选隐藏不会限制导出范围，下载始终包括全部样本。

继续复核的命令：

```powershell
python scripts/build_review_page.py --input "$Annotations/review_export.csv" --images "$Images" --output "$Views/template_review_v2.html" --threshold 6
```

下次下载改用新文件名，并在后续命令中选最新版本。原始候选 baseline 保留不动，`review_original_template_id` 也不要手改。

例如最新下载为 `review_export_v2.csv`，第 7 节两条命令的 `--input` 都改成该文件，`--baseline` 仍指向本批最初候选 CSV。不要继续导入较早的 `review_export.csv`。意图标注的 `_v2` 下载同样需要更新第 9 节 `--input`。

## 7. 校验并导入模板复核结果

```powershell
python scripts/import_reviewed.py --input "$Annotations/review_export.csv" --baseline "$Interim/meme_index_with_templates.csv" --check-only
python scripts/import_reviewed.py --input "$Annotations/review_export.csv" --baseline "$Interim/meme_index_with_templates.csv" --output "$Processed/meme_index_reviewed.csv"
```

先执行第一条，确认没有错误，再执行第二条。`--check-only` 可接受合法的 pending/suspected 状态，不等于复核完成。正式导入要求全部 `review_status=correct` 且 template_id 非空、合法。

导入同时检查 sample_id 集合、重复、原模板来源以及所有应保留字段。不要在下载文件中改图片路径、pHash、source 或删除记录。出现遗漏、额外样本、来源不一致时，确认使用的是**本批原始候选 baseline**，不要换成其他批次绕过检查。

## 8. 交流意图人工标注及 CSV 下载

```powershell
python scripts/build_annotation_page.py --input "$Processed/meme_index_reviewed.csv" --images "$Images" --labels "$Labels" --output "$Views/intent_annotation.html"
Invoke-Item "$Views/intent_annotation.html"
```

人工操作：

1. 展开标签定义，按每张图片的主要交流目的选择一个标签，不把“看起来开心”等情绪直接当作交流意图。
2. 同一模板不自动共用意图标签，应逐样本检查。
3. 缺少语境或存在多个合理解读时选“无法判断”（uncertain），填写缺少什么信息；意图明确但不属于标签体系时选“其他”（other）并说明。
4. 备注可记录判断依据或疑问，不需要填写 OCR 内容。未标注可保留空标签作为阶段性进度，但不能作为完成数据导入。
5. 点击“导出标注 CSV”，确认下载并保存到 `$Annotations/intent_export.csv`，不覆盖任何输入文件。

标注新增字段：

| 字段 | 含义 |
| --- | --- |
| intent_label | YAML 中的英文标签编号；空为未标注 |
| annotation_notes | 人工备注，支持中文、逗号、引号和换行 |
| annotation_status | 有标签为 annotated，无标签为 pending；不是标注质量审核结论 |
| label_schema_version | 当前标签版本，必须与固定配置一致 |

继续标注时使用下载 CSV 和同一标签快照，输出新的 HTML：

```powershell
python scripts/build_annotation_page.py --input "$Annotations/intent_export.csv" --images "$Images" --labels "$Labels" --output "$Views/intent_annotation_v2.html"
```

## 9. 校验并导入意图标注

```powershell
python scripts/import_annotations.py --input "$Annotations/intent_export.csv" --baseline "$Processed/meme_index_reviewed.csv" --labels "$Labels" --check-only
python scripts/import_annotations.py --input "$Annotations/intent_export.csv" --baseline "$Processed/meme_index_reviewed.csv" --labels "$Labels" --output "$Processed/meme_index_annotated.csv"
```

只有标签合法、版本一致、状态匹配且全部为 annotated 才能导入。`uncertain` 是有效的已填写标签，与 pending 不同。导入不判断人工标签语义正确与否。

本阶段仅四个标注字段可改变，模板编号和模板复核状态不能再次编辑；如发现模板问题，应返回模板复核阶段另存新结果，然后重新生成后续产物。

## 10. 按模板划分

```powershell
python scripts/split_dataset.py --input "$Processed/meme_index_annotated.csv" --labels "$Labels" --output-dir "$Processed/splits" --ratios 0.8 0.1 0.1 --seed 42 --uncertain exclude
```

**不要预先创建 `$Processed/splits`**。脚本要求新目录，生成：

- train.csv、val.csv、test.csv：保留完整原字段，仅分配记录，不复制或修改原图。
- excluded_uncertain.csv：默认排除的“无法判断”样本，保留原标签与备注。
- split_report.json：输入散列、策略、种子、模板清单、数量及警告；最后写入，存在才表示所有输出已写完。

规则：

- template_id 整组进入一个集合，比例近似作用于有效模板组数，不是图片数；组大小不均时图片比例会偏离。
- 固定种子、相同数据可复现。模板数足够时非零比例集合至少有一组；不足时允许空集合并警告。不进行类别分层。
- 默认按样本排除 uncertain；同模板中的明确标签样本仍保留并整组分配。排除清单不属于 train/val/test。
- 若明确需要保留无法判断类别，另用新目录并指定 `--uncertain include`，在实验记录中说明。不要为了凑数量改写 uncertain 标签。
- 全部为 uncertain 时默认得到三个空清单和完整排除清单，这是可审计的结果，不是可用的训练数据。
- 命令行比例与种子生效，当前不会读取 `configs/model.yaml` 中的对应值。

后续增删样本、修改模板或标签后，应另开批次并重新划分。不要手动搬动 CSV 行来达到比例；这样可能让模板跨集合。

仅在明确选择保留 uncertain，或在独立测试中验证非空整组划分时，使用以下完整命令；不要覆盖默认 exclude 结果：

```powershell
python scripts/split_dataset.py --input "$Processed/meme_index_annotated.csv" --labels "$Labels" --output-dir "$Processed/splits_include" --ratios 0.8 0.1 0.1 --seed 42 --uncertain include
python scripts/dataset_report.py --input "$Processed/meme_index_annotated.csv" --splits-dir "$Processed/splits_include" --labels "$Labels" --output-dir "$Views/dataset_report_include"
```

下一节仍检查默认 exclude 的 splits。两个报告属于两种策略，不要交叉使用划分目录或用 include 报告替代 exclude 报告。

## 11. 统计报告与验收

```powershell
python scripts/dataset_report.py --input "$Processed/meme_index_annotated.csv" --splits-dir "$Processed/splits" --labels "$Labels" --output-dir "$Views/dataset_report"
Invoke-Item "$Views/dataset_report/dataset_report.html"
```

同样不要预先创建报告目录。生成 HTML 和 JSON，读取 CSV 重新统计，不直接相信 split_report.json 的“无泄漏”结论。

人工核对：

1. 原索引样本数等于 train + val + test + 排除清单的记录数，且无重复、遗漏或未知样本。
2. 模板跨集合检查 train/val、train/test、val/test 均无交叉。排除清单可能与已纳入样本共享模板，模板计数不一定可相加。
3. 标签分布、无法判断数量、空集合和缺失类别警告是否符合预期。表中占比以原索引样本数为分母。
4. 显示“审计通过”仅意味着一致性检查无错误，不能替代标签质量评估，也不保证已有足够数据开展训练。

统计命令退出码：0 为无审计错误（仍可能有警告）；1 为输入/格式/输出路径错误；2 为发现模板泄漏或数据不一致，**仍会留下错误报告供检查**。PowerShell 可用 `$LASTEXITCODE` 查看上一条 Python 命令退出码。错误未修复前不要继续使用该划分。

## 12. 重跑、失败与保存规则

| 工具 | 同路径重跑行为 | 操作要求 |
| --- | --- | --- |
| prepare_data.py | 更新累计索引，保留原编号和人工字段 | 同时只运行一个扫描进程；保留主索引 |
| deduplicate.py | 替换候选 CSV 和 pairs CSV | 开始复核后冻结 baseline；新批次用新路径 |
| build_review_page.py | 可替换同名 HTML | 不覆盖正在编辑的页面；先导出，再生成 v2 |
| build_annotation_page.py | 拒绝已有 HTML | 使用新文件名 |
| 两个 import 脚本 | 拒绝已有输出 CSV | 使用新版本输出，不删除已确认结果来强制重跑 |
| split_dataset.py、dataset_report.py | 拒绝已存在的输出目录 | 使用新目录；写入失败可能留下部分产物，不当作完成结果 |
| 浏览器导出 | 下载新文件，名称带时间戳 | 确认实际保存成功，别手动选中原索引覆盖 |

常见问题：

- **页面修改丢失**：刷新前未导出；当前无自动保存。只有已下载 CSV 能恢复。
- **导入报告 sample_id 不一致**：选错 baseline、混入其他批次或手动删行。返回本批来源核对，不通过重编号修复。
- **标签版本错误**：使用了不匹配的 YAML。恢复本批快照；确需更改体系时另开版本并重新人工处理，不能只改版本字段。
- **图片缺失或无法显示**：确认 `--images` 指向索引相对路径的根目录。页面显示占位符时不要凭空确认；先处理原始数据批次问题。
- **没有划分样本**：检查是否全为 uncertain，查看排除清单。不要为了让三个文件非空而伪造明确标签。
- **审计失败**：查看 JSON 错误、模板交叉编号，返回复核/导入或重新划分；保留错误报告作为排查记录。

一批数据完成后，应一并保留：原图、累计索引备份、批次索引快照、标签 YAML、候选及相似对 CSV、两次人工下载、已复核/已标注索引、划分 CSV 和报告。HTML 可重建，CSV 和来源快照才是继续操作的依据。

## 13. 独立测试与现有验收脚本

按本指南从全新数据跑完整流程（不依赖历史测试目录）：

```powershell
python tests/workflow_guide_smoke.py
```

需已有项目环境、可选 Playwright、本机 Edge 和 pwsh。它从本文抽取 PowerShell 命令，改用全新 `outputs/guide_e2e_*/dataset` 路径和当前 Python 解释器，并在每条 Python 命令后检查退出码。`Invoke-Item` 的打开操作由独立 Edge 会话完成。合成图片从头生成，实际操作两类页面、阶段性下载与重新载入，再进行校验导入、exclude/include 划分和统计。`commands/` 保留实际执行的 PowerShell 脚本，另有日志、截图及 `report.json`。测试结果不进入正式数据集。

常规测试：

```powershell
python -m unittest discover -s tests -v
```

需要实际浏览器验收时，额外安装可选 Playwright，并确保本机有 Microsoft Edge：

```powershell
python -m pip install playwright
python tests/browser_review_smoke.py
```

浏览器脚本使用独立的无界面 Edge 会话，不使用个人浏览器配置。截图和下载产物都留在 `outputs/` 新目录。

| 测试脚本 | 作用与前提 |
| --- | --- |
| browser_review_smoke.py | 自建合成图片，跑索引、分组、模板编辑和下载；可独立启动 |
| browser_review_import_smoke.py --fixture-run <目录> | 使用上一步生成的特定合成数据完成复核及导入 |
| browser_annotation_smoke.py | 意图选择、备注、阶段性下载；引用此前已复核测试目录 |
| annotation_import_smoke.py | 新建明确的合成完成副本验证导入，不等于浏览器续标 |
| browser_annotation_import_smoke.py | 在浏览器中完成余下 uncertain 标注、下载及导入 |
| template_split_smoke.py | 默认排除、显式 include、模板隔离及拒绝覆盖 |
| dataset_report_smoke.py | 正常、全排除及故意泄漏统计报告 |
| browser_dataset_report_smoke.py | 实际打开三份报告并逐格核对与截图 |

除前两个可独立或指定来源的入口外，多数验收脚本当前引用工作区已有的具体测试目录，并不是通用批量工具。在干净克隆中这些被 Git 忽略的历史产物不存在；不要把脚本默认测试路径改成正式目录。可先按本文“独立测试路径”手动跑通完整流程，或为验收脚本更新测试来源后再运行。合成数据验收只证明功能链路，不证明真实表情包识别准确率。
