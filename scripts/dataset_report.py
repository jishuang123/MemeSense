"""生成已标注数据及划分统计的 JSON 和离线 HTML 报告。"""

import argparse
import csv
import hashlib
from html import escape
import json
import logging
from pathlib import Path

import yaml

from _bootstrap import ROOT
from build_annotation_page import load_labels
from split_dataset import load_annotated
from memesense.data.statistics import audit_dataset, read_partition


def render_report(report: dict) -> str:
    """用标准 HTML 表格和比例条展示统计，无外部资源。"""
    total = report['source']['samples']
    rows = []
    for name, item in [('已标注索引', report['source']), ('已纳入划分（合计）', report['assigned']), *report['partitions'].items()]:
        share = item['samples'] / total * 100 if total else 0
        rows.append(f'<tr><th>{escape(name)}</th><td>{item["samples"]}</td><td>{item["unique_samples"]}</td><td>{item["templates"]}</td><td>{item["uncertain"]}</td><td>{share:.1f}%</td></tr>')
    label_rows = []
    for label, count in report['source']['labels'].items():
        cells = ''.join(f'<td>{report["partitions"][name]["labels"].get(label, 0)}</td>' for name in report['partitions'])
        width = count / total * 100 if total else 0
        description = report['label_descriptions'].get(label, label)
        label_rows.append(f'<tr><th>{escape(label)}<small>{escape(description)}</small></th><td>{count}<div class="bar" style="width:{width:.1f}%"></div></td>{cells}</tr>')
    overlaps = ''.join(f'<li>{escape(pair)}：{escape(", ".join(ids)) if ids else "无交叉"}</li>' for pair, ids in report['checks']['template_overlaps'].items())
    issues = ''.join(f'<li>{escape(item)}</li>' for item in report['errors'] + report['warnings']) or '<li>未发现错误或警告。</li>'
    state = '审计通过' if report['checks']['passed'] else '审计失败，请先修复划分'
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MemeSense 数据集统计</title><style>body{{font-family:system-ui,"Microsoft YaHei",sans-serif;background:#f2f5f7;color:#20343d;margin:0}}main{{max-width:1150px;margin:auto;padding:30px 22px}}section{{background:white;padding:20px;border-radius:12px;margin:20px 0;overflow:auto}}table{{border-collapse:collapse;width:100%}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #dde5e8}}small{{display:block;font-weight:normal;color:#687a83}}p,li{{line-height:1.8;overflow-wrap:anywhere}}.bar{{height:6px;background:#2b7e8e;margin-top:6px}}.status{{font-size:20px;color:{"#216759" if report['checks']['passed'] else "#ac3327"}}}</style>
<main><h1>MemeSense · 数据集统计</h1><p class="status">{state}</p>
<p>标签版本：{escape(report['label_schema_version'])} · 声明的 uncertain 策略：{escape(str(report['uncertain_policy']))}</p>
<p>直接读取 CSV 重算；统计与“通过”不代表标注语义质量或训练就绪。未打开或修改原图。</p>
<section><h2>样本与模板分布</h2><p>占比以原索引样本数为分母；模板数按各行去重，排除清单与已纳入划分可能共享模板，不能直接相加。</p>
<table><tr><th>范围</th><th>记录数</th><th>唯一样本数</th><th>模板数</th><th>无法判断</th><th>占原索引</th></tr>{''.join(rows)}</table></section>
<section><h2>交流意图标签分布</h2><table><tr><th>标签</th><th>原索引</th><th>train</th><th>val</th><th>test</th><th>排除</th></tr>{''.join(label_rows)}</table></section>
<section><h2>模板跨集合检查</h2><ul>{overlaps}</ul><p>仅检查 train / val / test 两两交集。编号不同但实际相似的模板仍需人工核查。</p></section>
<section><h2>错误与提示</h2><ul>{issues}</ul></section>
<section><h2>数据来源</h2><p>{escape(report['input'])}</p><p>SHA-256：{report['input_sha256']}</p><p>划分目录：{escape(report['splits_dir'])}</p><p>完整计数、交叉编号、文件散列和错误详情见同目录 dataset_report.json。</p></section></main></html>'''


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'data/processed/meme_index_annotated.csv')
    parser.add_argument('--splits-dir', type=Path, default=ROOT / 'data/processed/splits')
    parser.add_argument('--labels', type=Path, default=ROOT / 'configs/labels.yaml')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'outputs/dataset_report')
    args = parser.parse_args()
    source, splits, output = (p.resolve() for p in (args.input, args.splits_dir, args.output_dir))
    try:
        if output.exists() or output.is_relative_to((ROOT / 'data/raw').resolve()):
            raise ValueError('输出必须是 data/raw/ 之外尚不存在的新目录')
        config = load_labels(args.labels)
        fields, source_rows = load_annotated(source, config)
        names = ('train', 'val', 'test', 'excluded_uncertain')
        partitions = {name: read_partition(splits / f'{name}.csv', fields) for name in names}
        report = audit_dataset(source_rows, partitions, config['labels'])
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        metadata_path = splits / 'split_report.json'
        policy = 'unknown'
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            if not isinstance(metadata, dict):
                raise ValueError('split_report.json 必须是 JSON 对象')
            policy = metadata.get('uncertain_policy', 'unknown')
            if metadata.get('input_sha256') != digest:
                report['errors'].append('划分报告中的来源散列与当前索引不符。')
            if policy not in ('include', 'exclude'):
                report['errors'].append('划分报告中的 uncertain 策略无效。')
            if policy == 'exclude' and report['assigned']['uncertain']:
                report['errors'].append('策略为 exclude，但 train/val/test 中仍有 uncertain。')
            if policy == 'include' and partitions['excluded_uncertain']:
                report['errors'].append('策略为 include，但排除清单非空。')
        else:
            report['warnings'].append('未提供 split_report.json：可检查实际数据，但无法核对声明的策略和来源散列。')
        report['checks']['passed'] = not report['errors']
        report.update(input=str(source), input_sha256=digest, splits_dir=str(splits),
                      label_schema_version=config['version'], uncertain_policy=policy,
                      label_descriptions=config['descriptions'],
                      split_sha256={name: hashlib.sha256((splits / f'{name}.csv').read_bytes()).hexdigest() for name in names})
        html = render_report(report)
        output.mkdir(parents=True, exist_ok=False)
        (output / 'dataset_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        (output / 'dataset_report.html').write_text(html, encoding='utf-8')
        logging.info('生成统计报告：%s；原索引 %d 样本 / %d 模板', output, report['source']['samples'], report['source']['templates'])
        for error in report['errors']:
            logging.error(error)
        for warning in report['warnings']:
            logging.warning(warning)
        if report['errors']:
            raise SystemExit(2)
    except (OSError, ValueError, csv.Error, yaml.YAMLError) as exc:
        logging.error('统计报告生成失败：%s', exc)
        raise SystemExit(1) from exc


if __name__ == '__main__':
    main()
