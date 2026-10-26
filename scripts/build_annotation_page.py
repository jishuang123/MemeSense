"""从已复核索引生成离线交流意图人工标注页。"""

import argparse
import csv
from html import escape
import json
import logging
from pathlib import Path
import re

from PIL import Image
import yaml

from _bootstrap import ROOT
from build_review_page import thumbnail_data
from memesense.data.review_import import read_index, valid_id

ANNOTATION_FIELDS = ['intent_label', 'annotation_notes', 'annotation_status', 'label_schema_version']


def load_labels(path: Path) -> dict:
    """读取可调整的单标签初稿，检查版本、编号与中文描述。"""
    config = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(config, dict) or not isinstance(config.get('version'), str) or not config['version'].strip():
        raise ValueError('标签配置必须包含非空 version')
    labels = config.get('labels')
    if not isinstance(labels, list) or not labels or any(not isinstance(x, str) or not re.fullmatch(r'[a-z][a-z0-9_]*', x) for x in labels):
        raise ValueError('labels 必须是非空的英文标签编号列表')
    if len(set(labels)) != len(labels):
        raise ValueError('标签编号不能重复')
    descriptions = config.get('descriptions')
    if not isinstance(descriptions, dict) or any(not isinstance(descriptions.get(x), str) or not descriptions[x].strip() for x in labels):
        raise ValueError('每个标签都必须提供非空 descriptions')
    return config


def annotation_rows(path: Path, config: dict) -> tuple[list[str], list[dict[str, str]]]:
    """只接受已确认的模板索引；继续标注时校验既有标签版本和状态。"""
    fields, records = read_index(path, reviewed=True)
    rows = []
    for line, original in records:
        row = original.copy()
        if row['review_status'] != 'correct' or not valid_id(row['template_id'], 'T'):
            raise ValueError(f'第 {line} 行尚未完成模板复核')
        label = row.get('intent_label', '')
        if label and label not in config['labels']:
            raise ValueError(f'第 {line} 行意图标签不在当前配置中：{label}')
        version = row.get('label_schema_version', '')
        if version and version != config['version']:
            raise ValueError(f'第 {line} 行标签版本与配置不一致，请使用对应版本配置')
        status = 'annotated' if label else 'pending'
        if row.get('annotation_status', status) != status:
            raise ValueError(f'第 {line} 行 annotation_status 与标签不一致')
        row.update(intent_label=label, annotation_notes=row.get('annotation_notes', ''),
                   annotation_status=status, label_schema_version=config['version'])
        rows.append(row)
    return list(dict.fromkeys(fields + ANNOTATION_FIELDS)), rows


def render_annotation(rows: list[dict[str, str]], fields: list[str], config: dict, images: Path) -> str:
    """内嵌完整记录与缩略图，浏览器导出无需联网。"""
    cards = []
    for i, row in enumerate(rows):
        try:
            url = thumbnail_data(row['image_path'], images)
            preview = f'<img src="{url}" alt="{escape(row["sample_id"])}" loading="lazy">'
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
            logging.warning('%s 图片不可用：%s', row['sample_id'], exc)
            preview = '<p>图片缺失或损坏，请勿凭空判断</p>'
        options = '<option value="">未标注</option>' + ''.join(
            f'<option value="{escape(label)}" {"selected" if row["intent_label"] == label else ""}>{escape(config["descriptions"][label])}</option>'
            for label in config['labels'])
        cards.append(f'''<article class="card" data-index="{i}"><div class="preview">{preview}</div>
<div class="body"><h2>{escape(row['sample_id'])} <small>{escape(row['template_id'])}</small></h2>
<p class="path">{escape(row['image_path'])}</p>
<label>主要交流意图<select class="intent" aria-label="{escape(row['sample_id'])} 意图">{options}</select></label>
<label>标注备注<textarea class="notes" rows="3" aria-label="{escape(row['sample_id'])} 备注" placeholder="判断依据、缺少的语境或其他解释">{escape(row['annotation_notes'])}</textarea></label>
<p class="status"></p></div></article>''')
    template = Path(__file__).with_name('annotation_template.html').read_text(encoding='utf-8')
    values = {'{{CARDS}}': ''.join(cards), '{{VERSION}}': escape(config['version']),
              '{{GUIDE}}': ''.join(f'<li><b>{escape(label)}</b>：{escape(config["descriptions"][label])}</li>' for label in config['labels']),
              '{{DATA}}': json.dumps({'rows': rows, 'fields': fields}, ensure_ascii=False).replace('<', '\\u003c')}
    return re.sub(r'\{\{[A-Z]+\}\}', lambda m: values[m.group()], template)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'data/processed/meme_index_reviewed.csv')
    parser.add_argument('--images', type=Path, default=ROOT / 'data/raw/images')
    parser.add_argument('--labels', type=Path, default=ROOT / 'configs/labels.yaml')
    parser.add_argument('--output', type=Path, default=ROOT / 'outputs/intent_annotation.html')
    args = parser.parse_args()
    source, images, output = (p.resolve() for p in (args.input, args.images, args.output))
    try:
        if output.suffix.lower() != '.html' or output in {source, args.labels.resolve()}:
            raise ValueError('输出必须是独立的 HTML 文件')
        if output.is_relative_to(images) or output.is_relative_to((ROOT / 'data/raw').resolve()):
            raise ValueError('禁止向原图目录输出')
        config = load_labels(args.labels)
        fields, rows = annotation_rows(source, config)
        page = render_annotation(rows, fields, config, images)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8') as stream:
            stream.write(page)
        logging.info('生成 %d 个样本的标注页：%s', len(rows), output)
    except (OSError, ValueError, csv.Error, yaml.YAMLError) as exc:
        logging.error('生成失败：%s', exc)
        raise SystemExit(1) from exc


if __name__ == '__main__':
    main()
