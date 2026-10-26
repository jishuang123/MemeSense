"""生成内嵌缩略图的离线人工复核页，不修改原图或 CSV。"""

import argparse
import base64
import csv
from collections import defaultdict
from html import escape
from io import BytesIO
import json
import logging
from pathlib import Path
import re
import tempfile

from PIL import Image, ImageOps

from prepare_data import ROOT, FIELDS, load_existing_index

LOGGER = logging.getLogger(__name__)


def thumbnail_data(image_path: str, images_dir: Path) -> str:
    """只读生成最大 320 像素 PNG 缩略图，返回可离线显示的 data URL。"""
    path = (images_dir / image_path).resolve()
    if not path.is_relative_to(images_dir.resolve()):
        raise ValueError("图片路径越出输入目录")
    with Image.open(path) as image:
        image.seek(0)
        preview = ImageOps.exif_transpose(image).convert("RGBA")
        preview.thumbnail((320, 320))
        buffer = BytesIO()
        preview.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def render_page(rows: list[dict[str, str]], images_dir: Path, threshold: int = 6,
                fields: list[str] | None = None) -> str:
    """按模板生成卡片；距离由浏览器根据当前参照图计算。"""
    if not 0 <= threshold <= 64:
        raise ValueError("复核阈值必须在 0 到 64 之间")
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row["template_id"]].append(row)
    sections = []
    data: list[list[dict[str, str]]] = []
    # 多图模板优先，未分组放在最后；组内按稳定编号排序。
    ordered = sorted(groups.items(), key=lambda item: (not bool(item[0]), -len(item[1]), item[0]))
    for group_number, (template, members) in enumerate(ordered):
        members.sort(key=lambda row: int(row["sample_id"][1:]))
        options, cards, hashes = [], [], []
        title = template or "未分组（不代表同一模板）"
        for number, row in enumerate(members):
            sample_id = row["sample_id"]
            value = row["phash"].strip()
            valid_hash = value if re.fullmatch(r"[0-9a-fA-F]{16}", value) else ""
            hashes.append({"sample_id": sample_id, "phash": valid_hash})
            options.append(f'<option value="{number}">{escape(sample_id)}</option>')
            try:
                source = thumbnail_data(row["image_path"], images_dir)
                preview = f'<button class="preview" type="button" title="点击放大缩略图"><img loading="lazy" src="{source}" alt="{escape(sample_id)}"></button>'
            except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
                LOGGER.warning("%s 缩略图不可用：%s", sample_id, exc)
                preview = '<div class="missing">图片缺失、损坏或路径不可用</div>'
            cards.append(f'''<article class="card" data-index="{number}">
{preview}<div class="card-body"><strong>{escape(sample_id)}</strong>
<p class="distance">距离待计算</p><p class="path">{escape(row['image_path'])}</p>
<code>{escape(value) if valid_hash else 'pHash 无效或缺失'}</code>
<label class="edit-label">候选 template_id
<input class="template-edit" type="text" value="{escape(row['template_id'])}" aria-label="{escape(sample_id)} 的候选 template_id"></label>
<p class="sample-status"></p></div></article>''')
        data.append(hashes)
        sections.append(f'''<section class="group" data-group="{group_number}" data-count="{len(members)}">
<div class="group-heading"><h2>{escape(title)} <small>{len(members)} 张</small></h2>
<label>距离参照 <select class="reference">{''.join(options)}</select></label></div>
<div class="review-actions"><button type="button" data-status="correct">分组正确</button>
<button type="button" data-status="suspected">疑似误分组</button>
<button type="button" data-status="pending">设为未复核</button><span class="group-status" role="status"></span></div>
<div class="cards">{''.join(cards)}</div></section>''')
    template = Path(__file__).with_name("review_template.html").read_text(encoding="utf-8")
    replacements = {
        "{{TOTAL}}": str(len(rows)), "{{GROUPS}}": str(sum(bool(key) for key in groups)),
        "{{THRESHOLD}}": str(threshold),
        "{{CONTENT}}": "".join(sections) or '<div class="empty">暂无样本。请先添加原图，运行 prepare_data.py 和 deduplicate.py，然后重新生成本页。</div>',
        "{{DATA}}": json.dumps(data, ensure_ascii=False).replace("<", "\\u003c"),
        "{{RECORDS}}": json.dumps({"rows": rows, "fields": fields or list(dict.fromkeys(
            FIELDS + [key for row in rows for key in row]))}, ensure_ascii=False).replace("<", "\\u003c"),
        "{{LOGIC}}": Path(__file__).with_name("review_logic.js").read_text(encoding="utf-8"),
    }
    # 一次替换，避免把样本路径中形似占位符的内容当作模板处理。
    return re.sub(r"\{\{[A-Z]+\}\}", lambda match: replacements[match.group()], template)


def main() -> None:
    """默认输出 outputs/template_review.html，可双击离线打开。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/interim/meme_index_with_templates.csv")
    parser.add_argument("--images", type=Path, default=ROOT / "data/raw/images")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/template_review.html")
    parser.add_argument("--threshold", type=int, default=6, help="复核高亮阈值，应与分组时设置一致")
    args = parser.parse_args()
    source, images_dir, output = (p.resolve() for p in (args.input, args.images, args.output))
    temporary: Path | None = None
    try:
        if not source.is_file():
            raise ValueError("候选索引不存在，请先运行 deduplicate.py")
        if output == source or output.suffix.lower() != ".html":
            raise ValueError("输出必须是独立的 .html 文件")
        if output.is_relative_to(images_dir) or output.is_relative_to((ROOT / "data/raw").resolve()):
            raise ValueError("不能向图片目录或 data/raw/ 写入页面")
        rows = load_existing_index(source)
        with source.open(encoding="utf-8-sig", newline="") as stream:
            fields = csv.DictReader(stream).fieldnames
        page = render_page(rows, images_dir, args.threshold, fields)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(page)
        temporary.replace(output)
    except (OSError, ValueError) as exc:
        LOGGER.error("复核页面生成失败：%s", exc)
        raise SystemExit(1) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    LOGGER.info("已生成 %d 张图片的复核页面：%s", len(rows), output)


if __name__ == "__main__":
    main()
