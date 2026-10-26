# MemeSense

面向中文表情包的语义理解与 QQ 群聊应用项目。按数据准备 → 人工标注 → 图像 / 文本 / 多模态实验 → 推理 → 群聊应用组织代码。

## 当前状态

当前已实现原图索引、pHash 候选分组、模板人工复核、交流意图标注、CSV 校验导入、按模板划分及统计审计。OCR、模型训练、模型推理、DeepSeek 和 QQ 接入仍为未实现接口，不属于当前数据集流程。

完整操作指南：[数据集构建操作指南](docs/dataset_workflow.md)。首次操作请按指南顺序执行，包含正式/测试路径配置、人工下载步骤、每一步输入输出、重跑规则和错误处理。

## 仓库内容

本仓库包含源码、脚本、配置示例、文档和测试。原始图片、人工标注结果、实验输出、模型权重、虚拟环境以及真实 `.env` 配置仅保存在本机，不随 Git 上传。克隆后请按数据集构建操作指南准备数据；`data/`、`outputs/` 和 `checkpoints/` 中仅保留目录占位文件。

补充流程说明：[二次复核导入](docs/second_review_import.md)、[辅助复核导入](docs/assisted_review_import.md)、[采纳人工标签](docs/adopt_human_labels.md)。

机器人设计参考本机 Codex 聊天「qq机器人大肥鱼提示词」：DeepSeek + NapCatQQ / OneBot v11，默认仅被 @ 时回复，按群隔离上下文，后续支持白名单、冷却、管理命令和并发限制。详见 [机器人设计](docs/bot_design.md)。

## 安装与检查

需要 Python 3.11+。在项目根目录执行（PowerShell）：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
python -m unittest discover -s tests -v
```

## 数据流程

当前阶段覆盖数据集构建至划分和统计审计，不执行 OCR、训练、QQ Bot 或 LLM 调用。以下各节为功能速查，完整执行顺序见上方操作指南。

将图片放入 `data/raw/images/`，支持 jpg、jpeg、png、webp（含大写扩展名和子目录），运行：

```powershell
python scripts/prepare_data.py
# 可选：显式指定路径，相对路径以当前工作目录为基准
python scripts/prepare_data.py --input data/raw/images --output data/interim/meme_index.csv
```

输出 `data/interim/meme_index.csv`，包含：

`sample_id, original_filename, image_path, width, height, file_size, phash, template_id, ocr_text, source`

- `image_path` 相对于输入目录，采用 `/` 分隔；同一相对路径复用 sample_id。重跑同一索引时请保持输入根目录不变。
- 首次排序后编号 M0001、M0002……，新文件从历史最大编号继续递增，不复用旧编号。改名或移动视为新文件；不同路径的相同图片仍各有一条记录。
- 每次刷新宽高、字节数及 64 位 pHash；template_id、ocr_text 初始为空，source 初始为 unknown，后续人工填写内容保留。
- pHash 仅为后续近重复检测准备，不自动合并图片或分配模板。多帧 WebP 使用第一帧，宽高为文件解码尺寸。
- 原图仅以只读方式打开；禁止将输出放在输入目录或 `data/raw/`。损坏图片输出 warning 并跳过。已入库后丢失或损坏的文件保留历史记录及编号，需人工复核。
- 空目录生成仅含表头的 CSV。旧 CSV 编号重复或缺少必要字段时停止，避免覆盖异常索引。
- CSV 使用 UTF-8 BOM 方便 Windows 打开；先写临时文件再替换旧索引。请勿同时运行多个索引进程，也不要删除旧 CSV 后期待保留原编号。

此前 `scan/split` 子命令已被当前 CSV 入口替代；已有 `src/memesense/data/` 工具保留，未进行目录重构。旧标注规范与 notebook 面向早期 JSONL 格式，暂不用于当前 CSV 流程。数据和输出默认不进入 Git。

## pHash 近重复检测与人工复核

生成图片索引后运行：

```powershell
python scripts/deduplicate.py
# 更严格的候选阈值，例如 4
python scripts/deduplicate.py --threshold 4
```

也支持 `--input`、`--output`、`--pairs` 指定三个不同的 CSV 路径。默认输出：

- `data/interim/meme_index_with_templates.csv`：原索引全部行和字段，template_id 替换为自动计算的候选分组。
- `data/interim/near_duplicate_pairs.csv`：直接匹配的样本编号、图片相对路径、汉明距离和候选 template_id。

原 `meme_index.csv` 保持不变，包括其中已人工填写的 template_id。脚本只读取 CSV，不打开、修改、移动或删除任何图片，也不产生 OCR 内容。复核时按候选 template_id 查看图片，用 pairs 表检查直接匹配依据；确认后导出新 CSV，再通过 import_reviewed.py 生成独立已复核索引，不填回原索引。人工复核结果应单独保存，重跑会替换这两个候选输出文件，因此复核开始后要固定候选 baseline。

分组规则与限制：

- 对 64 位 pHash 两两计算汉明距离，距离 ≤ 阈值时建立联系。默认 6 是起始经验参数，不代表已验证的准确率；0 表示仅匹配相同 pHash。
- 使用连通分量：A 与 B 相似、B 与 C 相似时三者同组，即使 A 与 C 距离超过阈值。pairs 表只列出直接匹配对，不将这种传递关系伪装成直接相似。
- 组编号取成员最小 sample_id，如 M0003 对应 T0003；单张图片也分配独立模板，编号允许有空缺。相同输入及阈值重跑或行顺序变化不影响结果。新增桥接图片、删除成员或改阈值可能合并或拆分组，因此候选编号不是永久人工标签。
- pHash 为空或不是 16 位十六进制字符串时输出 warning，该行保留但候选 template_id 留空。
- 相同 pHash 不等于文件完全一致；色彩、加字、裁剪等可能导致误匹配或漏匹配。候选模板不代表交流意图标签。
- 当前沿用索引中的 pHash，不检查图片是否已丢失或更改。请先更新索引，再结合原图人工复核。
- 简单两两比较的时间复杂度为 O(n²)，相似对很多时内存也会增加，适合当前原型规模。未引入新依赖或数据库。

## 本地 HTML 人工复核页

生成候选分组后执行：

```powershell
python scripts/build_review_page.py
```

双击 `outputs/template_review.html`，用现代 Edge、Chrome 或 Firefox 离线打开。无需服务器或网络。支持 `--input` 指定候选 CSV、`--images` 指定原图根目录、`--output` 指定独立 HTML，以及 `--threshold` 指定复核高亮阈值（默认 6，请与去重时阈值保持一致）。

- 按 template_id 展示内嵌缩略图、sample_id、相对路径和 pHash；多图组优先，未分组样本单独展示。
- 每组默认使用最小 sample_id 作为距离参照，可在下拉框中切换。距离明确指向参照图，不是组内最大距离；超过阈值的卡片高亮。逐一切换参照可检查传递分组误匹配。
- 支持搜索模板、样本或路径，筛选多图组及点击放大缩略图。复核阈值仅改变高亮，不重新分组；无效 pHash 显示距离不可用。
- 缩略图只读生成，最长边 320 像素，多帧图片仅显示第一帧。损坏或缺失图片显示占位提示，其距离仍取自 CSV 中的旧 pHash。
- 页面不回写原图或输入 CSV。图片已嵌入，因此 HTML 可以独立移动，但大数据集的文件可能较大。

每个原候选组可标记为“分组正确”“疑似误分组”或“未复核”。每张图片可编辑候选 template_id：填不同编号拆组，填相同编号合组，留空表示未分组。页面继续按载入时的分组展示，距离参照也保持原组；修改编号后该展示组恢复为未复核，请确认最终编号再标记。

点击“导出复核 CSV”会通过浏览器下载一个带时间戳的 `meme_index_reviewed_*.csv` 新文件，包括所有样本（含被筛选隐藏的样本），保留原行顺序和原字段，template_id 为编辑后的值，额外包含：

- `review_original_template_id`：首次复核前的模板编号，重新载入已复核 CSV 时保留。
- `review_status`：`pending`（未复核）、`correct`（分组正确）、`suspected`（疑似误分组）。分组按钮将状态应用到当前展示组的全部样本。

导出采用 UTF-8 BOM 和标准 CSV 引号转义，保留中文、逗号、双引号及换行。编辑仅存于页面内存，刷新或关闭前请导出并确认下载成功。要继续复核，可将下载文件作为 `build_review_page.py --input` 的输入重新生成页面；修改后的 template_id 将用于重新分组，已有复核状态会保留。不要把浏览器下载文件手动保存到原索引路径。

## 复核 CSV 校验与导入

先只校验浏览器下载的文件（不会创建输出）：

```powershell
python scripts/import_reviewed.py --input "下载目录/meme_index_reviewed_时间戳.csv" --check-only
```

所有样本确认后导入：

```powershell
python scripts/import_reviewed.py --input "下载目录/meme_index_reviewed_时间戳.csv"
```

默认对照 `data/interim/meme_index_with_templates.csv`，输出独立的 `data/processed/meme_index_reviewed.csv`。可用 `--baseline` 指定生成复核页时使用的候选 CSV，用 `--output` 指定新的 CSV 路径。测试数据务必指定测试 baseline 和 outputs 下的输出路径。已有输出一律拒绝覆盖，不提供强制覆盖选项。

校验规则：

- sample_id 必须规范、唯一且与来源样本集合完全一致，例如 M0001、M10000；拒绝缺失、新增及重复样本。
- template_id 必须为 T0001 形式的正整数编号，允许多个样本共享；未决样本可为空，correct 样本不能为空。
- review_status 只接受 pending、correct、suspected。`--check-only` 可对未决样本完成格式校验并统计状态，但不代表人工复核完成；正式导入要求所有样本均为 correct，不擅自过滤或确认未决样本。
- review_original_template_id 应与来源一致；图片路径、pHash、OCR 字段、source 等原有字段及自定义列必须保持不变。仅允许更改 template_id 和复核状态，以及增加列。
- CSV 表头、行宽、路径和编号异常会报错，记录行号指 CSV 记录结束的物理行号（多行字段可能占多行）。校验失败不会生成已复核索引。
- 保留导出行顺序、所有字段和中文内容。程序只读取 CSV，不打开或修改原图。已复核索引是格式及来源校验通过的人工结果，不代表自动验证了视觉分组正确性。

## 交流意图人工标注

`configs/labels.yaml` 已从早期情绪示例改为交流意图单标签初稿 `intent-draft-v1`，含标签编号及中文解释。当前标签包括赞同、反对、调侃、安慰、请求、问候、感谢、道歉、回应、其他和无法判断。修改分类或含义时更新 `version`；正式标注前应通过小样本试标进一步讨论边界。

从全部已确认的索引生成页面：

```powershell
python scripts/build_annotation_page.py --input data/processed/meme_index_reviewed.csv --output outputs/intent_annotation.html
```

支持 `--images` 指定原图目录、`--labels` 指定 YAML。输出 HTML 必须是新文件，已有文件拒绝覆盖。页面离线使用，无需新依赖。

- 按 sample_id 逐张选择主要意图和填写备注，不根据模板自动复制标签；标签描述可在页面展开查看。
- 标签为空表示未标注；`uncertain` 表示人工判断为无法确定，区别于还没有做标注。没有语境时不要仅凭情绪强行推断意图；`other` 与 `uncertain` 建议注明原因。
- 导出的新 CSV 保留所有原字段，追加 `intent_label`、`annotation_notes`、`annotation_status`（`pending` / `annotated`）与 `label_schema_version`。`annotated` 仅指已填写，不代表经过质量审核。
- 支持搜索和仅显示未标注；导出始终包含全部样本，含隐藏及未完成项。备注支持中文、逗号、双引号及换行。
- 刷新前须导出并确认下载。用下载 CSV 再次作为 `--input`，指定新 HTML 输出即可继续标注；版本不匹配、标签不存在或状态矛盾会报错，不静默改写旧标签。
- 输入须全部 `review_status=correct` 且模板编号有效。页面不会回写 CSV 或原图，本阶段不包含意图标注质量复核、模型训练或 OCR。

独立测试可运行 `python tests/browser_annotation_smoke.py`（依赖已有测试目录和可选 Playwright / Edge）；所有产物写入新的 `outputs/annotation_smoke_*/`。

## 意图标注 CSV 校验与导入

先校验导出文件，检查合法的未完成项而不写入：

```powershell
python scripts/import_annotations.py --input "标注结果.csv" --check-only
```

全部填写后生成独立索引：

```powershell
python scripts/import_annotations.py --input "标注结果.csv"
```

默认来源为 `data/processed/meme_index_reviewed.csv`，默认输出为 `data/processed/meme_index_annotated.csv`。可用 `--baseline` 指定已复核来源、`--labels` 指定标签配置、`--output` 指定新输出；已有输出拒绝覆盖。

- sample_id 格式、唯一性和样本集合必须与来源一致，不允许遗漏或新增。来源自身须全部模板复核完成。
- `intent_label` 必须来自所选 YAML；`annotation_status` 只允许 `pending` / `annotated`，且分别对应空标签 / 非空标签。
- 每行 `label_schema_version` 必须非空且与配置 version 完全一致，不自动迁移版本或补标签。
- `--check-only` 允许合法 pending 项；正式导入要求全部 annotated。`uncertain` 是合法的已填写类别，但不代表已得出明确意图，未来训练是否排除此类需另行决定。
- 仅四个标注字段可修改，其余已有字段（含模板编号、复核状态、图片路径、pHash 及自定义列）必须保留。备注支持中文、逗号、引号及换行。导入不判断人工标签语义是否正确，也不要求把不同图片标成不同类别。
- 失败会报告行号或原因，不生成输出。成功时保留输入行顺序及全部列，仅创建独立 CSV，不访问原图。

独立导入验收：`python tests/annotation_import_smoke.py`。脚本读取之前的测试产物，保留原下载，仅在新建 `outputs/annotation_import_smoke_*/` 中构造全部为 uncertain 的明确测试副本，验证成功与失败路径；不会把该副本纳入正式数据集。

完整浏览器续标与导入验收：`python tests/browser_annotation_import_smoke.py`。需要已有独立测试目录及可选 Playwright / Edge；在浏览器中完成剩余 4 张无语境图片的 uncertain 标注和备注，实际下载 CSV，验证校验、导入、拒绝覆盖及重新载入。新产物仅保存在 `outputs/browser_annotation_import_*/`，保留之前的标注和原文件。

## 按模板划分 train / val / test

从已标注索引生成 CSV 清单，不移动或复制原图：

```powershell
python scripts/split_dataset.py
# 自定义输入、新输出目录、比例和种子
python scripts/split_dataset.py --input "已标注索引.csv" --output-dir outputs/my_split --ratios 0.8 0.1 0.1 --seed 42
```

默认输入 `data/processed/meme_index_annotated.csv`，输出目录 `data/processed/splits` 必须不存在。输出 `train.csv`、`val.csv`、`test.csv`、`excluded_uncertain.csv` 和 `split_report.json`。所有原字段保留；已有目录拒绝覆盖，写入失败时可能留下不完整新目录，只有最后生成报告才表示写入完成。

**无法判断规则：**默认 `--uncertain exclude`，按样本排除 intent_label=uncertain，原样记录到 excluded_uncertain.csv，不改标为其他类。若同模板含明确标签和 uncertain，仅排除 uncertain 行，其余成员仍整组分配。显式使用 `--uncertain include` 才将它作为独立类别保留；不要无意把它当作已知意图。全是 uncertain 时默认产生三个空清单和排除清单，并在报告中标明无可划分样本，这不表示数据已满足训练条件。

比例指**有效模板组数**，不是图片数量。算法先对排序后的模板用固定 seed 打乱，再以最大余数法分配组数；模板数量足够时保证每个非零比例集合至少一组。小数据集或组大小不均时图片比例会偏离目标，不拆模板来凑比例；组数不足则允许空集合并警告。参数直接来自命令行，未读取 `configs/model.yaml`。

同一 template_id 不会同时出现在 train / val / test，输入行顺序变化不影响同种子结果；增删数据、改模板或换种子会改变划分。报告记录输入 SHA-256、种子、标签版本、策略、各集合样本数、模板编号及标签分布。当前不做类别分层，缺失类别会警告；同模板包含多个意图标签不会被拆开。隔离保证以人工模板编号为准，未被归到同一模板的近重复图片仍可能泄漏，需此前人工复核保障。

仅接受 sample_id 唯一、模板已复核、标注完整、标签与版本合法的索引。划分不验证来源溯源，因此应使用 `import_annotations.py` 产出的索引。独立验收运行 `python tests/template_split_smoke.py`：保留之前测试数据标签，同时验证默认全排除和显式 include 的无泄漏分组。

## 数据集统计与划分审计

```powershell
python scripts/dataset_report.py --input "已标注索引.csv" --splits-dir "划分目录" --output-dir "新的报告目录"
```

默认读取正式已标注索引和 `data/processed/splits`，输出到尚不存在的 `outputs/dataset_report`。生成 `dataset_report.html`（离线表格及比例条）和 `dataset_report.json`（完整计数与审计详情），不覆盖现有目录，不读取或修改图片。

展示原索引、train / val / test 和 excluded_uncertain 的记录数、唯一样本数、模板数、配置中全部意图标签（含零计数）、无法判断数量。比例以原索引样本数为分母；不同范围的模板数可能重叠，不能直接相加。

重新读取 CSV 检查模板两两交叉、重复样本、遗漏样本、未知样本和原字段被修改，核对 uncertain 排除清单；存在 split_report.json 时还核对声明策略与来源散列，不采用其中已有统计或无泄漏结论。报告缺失时仍计算实际数据并给出溯源信息不足警告。划分缺失或 CSV 格式异常返回 1；审计发现泄漏或数据不一致时仍生成错误报告并返回 2；无审计错误返回 0。空集合或全 uncertain 给出警告，不把审计通过当作训练就绪。

独立验收：`python tests/dataset_report_smoke.py`，新建测试副本验证正常划分、全排除及故意拆开 T0001 的泄漏场景，产物位于 `outputs/dataset_report_smoke_*/`。

浏览器显示验收：`python tests/browser_dataset_report_smoke.py`，使用已有三份独立报告及可选 Playwright / Edge，实际打开页面并按来源 CSV 逐格核对计数、标签及泄漏提示，保存桌面/移动端截图和验收报告到新的 `outputs/browser_dataset_report_*/`，不改动原报告。

## 独立浏览器验收

可选安装测试工具后，使用本机 Edge 跑完整流程：

```powershell
python -m pip install playwright
python tests/browser_review_smoke.py
```

脚本使用独立无界面 Edge 会话，不使用日常浏览器配置。每次在 `outputs/review_smoke_*/` 生成合成图片、索引、分组、复核 HTML、浏览器下载的 CSV、桌面及移动端截图和 `report.json`。不向正式数据目录添加测试数据，并比较正式数据、测试原图及输入 CSV，验证它们未被修改。测试覆盖重复索引、新图续号、损坏文件跳过、分组、标记、修改编号、下载完整 CSV 和重新载入复核结果。

Playwright 仅为可选验收工具，未加入生产依赖。验收报告只代表测试数据下的流程与交互正确性，不代表真实表情包的近重复识别准确率。

继续之前的独立测试数据，完成浏览器复核及导入验收：

```powershell
python tests/browser_review_import_smoke.py --fixture-run outputs/review_smoke_nefqxagt
```

将路径替换为先前验收生成的目录。此脚本只适用于上述合成数据：在浏览器中将演示拆出的 M0002 恢复为 T0001，确认全部测试样本，下载 CSV，并验证只校验不写入、正式导入成功、重复导入拒绝覆盖。所有新产物保存在新的 `outputs/review_import_smoke_*/` 中，不改变先前测试目录或正式数据。

## 模块与后续实现

| 目录 | 用途 |
| --- | --- |
| `configs/` | 示例标签、模型与划分参数 |
| `src/memesense/data/` | 去重、OCR 接口、标注校验、划分 |
| `src/memesense/models/` | 图像、文本、多模态、上下文模型接口 |
| `src/memesense/inference/` | 统一预测结果与推理接口 |
| `src/memesense/bot/` | QQ 接入接口、LLM 接口、大肥鱼人格 |
| `scripts/` | 数据准备与训练 / 评估入口 |
| `notebooks/` | 数据概览笔记本 |
| `tests/` | 原图保护、去重隔离、标注和上下文测试 |
| `checkpoints/`, `outputs/`, `docs/` | 权重、实验结果、毕设文档 |

训练与评估脚本支持 `--help`，实际执行会明确报告尚未实现。下一步应先确认标签体系和数据规模，再选择 OCR 引擎及模型；目前未预设深度学习框架或自动下载权重。

`.env.example` 记录未来机器人所需配置，复制为 `.env` 后填写；当前骨架不读取密钥或连接外部服务。不要提交真实 API Key。
