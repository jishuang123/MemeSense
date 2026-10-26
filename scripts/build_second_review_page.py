"""生成独立二次人工复核页，默认隐藏既有判断，不修改输入。"""
import argparse
from collections import defaultdict
from html import escape
import json
from pathlib import Path

from build_annotation_page import load_labels
from build_review_page import thumbnail_data


def build_page(queue: list[dict], contexts: list[dict], labels: dict, images: Path) -> str:
    """生成内嵌图片与参考资料的离线页面；人工结果从空白开始。"""
    refs = defaultdict(list)
    for entry in contexts:
        if entry['sample_id']:
            refs[entry['sample_id']].append(entry['original_record'])
    ids = [r['sample_id'] for r in queue]
    if len(ids) != len(set(ids)) or any(r['priority'] not in ('P0','P1','P2') for r in queue):
        raise ValueError('样本编号重复或优先级无效')
    rows = sorted(queue, key=lambda r: (r['priority'], r['sample_id']))
    cards = []
    data = []
    for i, row in enumerate(rows):
        sid = row['sample_id']
        options = '<option value="">未复核</option>' + ''.join(f'<option value="{escape(k)}">{escape(labels["descriptions"][k])}</option>' for k in labels['labels'])
        assistant = json.dumps({k:row[k] for k in ('current_label','assistant_note','review_questions')}, ensure_ascii=False, indent=2)
        upstream = json.dumps(refs[sid], ensure_ascii=False, indent=2)
        cards.append(f'''<article data-index="{i}" data-priority="{row['priority']}">
<h2>{escape(sid)} <small>{row['priority']}</small></h2>
<img loading="lazy" src="{thumbnail_data(row['image_path'], images)}" alt="{escape(sid)}">
<p>{escape(row['image_path'])}</p>
<label>人工标签<select aria-label="{sid} 人工标签" class="label">{options}</select></label>
<label>人工备注<textarea aria-label="{sid} 人工备注" class="note" rows="3" placeholder="判断依据；缺少哪些语境"></textarea></label><p class="status">未复核</p>
<details class="assistant"><summary>查看助手试标及复核问题（可能影响独立判断）</summary><pre>{escape(assistant)}</pre></details>
<details class="upstream"><summary>查看 MSAIRS 原始上下文与标签（独立参考）</summary><pre>{escape(upstream)}</pre></details>
</article>''')
        data.append(dict(sample_id=sid,template_id=row['template_id'],image_path=row['image_path'],priority=row['priority'],annotation_origin='assistant_visual_trial_not_human_gold',label_schema_version=labels['version'],human_label='',human_note='',human_review_status='pending',assistant_reference_viewed=False,msairs_reference_viewed=False))
    payload = json.dumps(data, ensure_ascii=False).replace('<','\\u003c')
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MemeSense 人工二次复核</title>
<style>body{font:16px/1.6 system-ui;background:#f3f6f8;color:#20343d;margin:0}header,main{max-width:1250px;margin:auto;padding:20px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px}article{background:white;padding:18px;border-radius:12px;min-width:0}article[hidden]{display:none}img{width:100%;height:230px;object-fit:contain}label{display:block;margin:10px 0}select,textarea,input,button{font:inherit;box-sizing:border-box;padding:8px}select,textarea{width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere}summary{cursor:pointer}small{font-size:14px}button{cursor:pointer;margin:8px}details{margin:12px 0}</style>
<header><h1>人工二次复核</h1><p>来源：助手视觉试标，未经独立人工交叉复核，不是金标准。请先独立看图判断；缺少语境可标“无法判断”。P0 优先，但不代表需要改成某个标签。</p>
<p>默认隐藏助手标签、备注、含标签提示的复核问题，以及 MSAIRS 上下文和标签。展开参考会在导出中记录；收起不会清除记录。这是界面隐藏，不是技术盲测，HTML 源码仍含参考信息。</p>
<p>当前修改只在浏览器内存中，关闭或刷新前请导出。导出始终包括全部样本，未填写的保留 pending；结果是二次复核清单，不要直接交给旧意图标注导入器。</p>
<label>复核者代号（建议填写）<input id="reviewer" placeholder="例如 reviewer_A"></label>
<label>显示优先级<select id="priority"><option value="">全部（P0 优先）</option><option>P0</option><option>P1</option><option>P2</option></select></label>
<label>搜索样本编号<input id="search"></label><label><input type="checkbox" id="pending">仅显示未复核</label>
<button id="export">导出人工复核 CSV</button><p id="progress"></p><p id="save">尚未导出</p></header><main>''' + ''.join(cards) + '''</main><script>
const rows='''+payload+''';
const cards=[...document.querySelectorAll('article')]; let dirty=false;
function refresh(){let shown=0;cards.forEach((c,i)=>{const r=rows[i];c.hidden=!!((priority.value&&r.priority!==priority.value)||(search.value&&!r.sample_id.toLowerCase().includes(search.value.toLowerCase()))||(pending.checked&&r.human_review_status!=='pending'));if(!c.hidden)shown++;c.querySelector('.status').textContent=r.human_review_status==='reviewed'?'已填写':'未复核';});document.querySelector('#progress').textContent=`已填写 ${rows.filter(r=>r.human_review_status==='reviewed').length} / ${rows.length}；当前显示 ${shown}`;}
const priority=document.querySelector('#priority'),search=document.querySelector('#search'),pending=document.querySelector('#pending');
function changed(){dirty=true;document.querySelector('#save').textContent='有未导出的修改';refresh();}
cards.forEach((c,i)=>{const r=rows[i];c.querySelector('.label').addEventListener('change',e=>{r.human_label=e.target.value;r.human_review_status=r.human_label?'reviewed':'pending';changed();});c.querySelector('.note').addEventListener('input',e=>{r.human_note=e.target.value;changed();});for(const [cls,key] of [['assistant','assistant_reference_viewed'],['upstream','msairs_reference_viewed']]){const d=c.querySelector('.'+cls);d.addEventListener('toggle',()=>{if(d.open){r[key]=true;changed();}});}});
for(const e of [priority,search,pending])e.addEventListener('input',refresh);
document.querySelector('#reviewer').addEventListener('input',changed);
document.querySelector('#export').addEventListener('click',()=>{const fields=[...Object.keys(rows[0]),'reviewer_id'];const q=v=>'"'+String(v??'').replaceAll('"','""')+'"';const text='\\uFEFF'+[fields.map(q).join(','),...rows.map(r=>fields.map(k=>q(k==='reviewer_id'?document.querySelector('#reviewer').value:r[k])).join(','))].join('\\r\\n')+'\\r\\n';const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='human_second_review_'+new Date().toISOString().replace(/[:.]/g,'-')+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);dirty=false;document.querySelector('#save').textContent='已发起下载，请确认文件已保存';});
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});refresh();
</script></html>'''


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('queue','contexts','labels','images','output'):
        parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args()
    output=args.output.resolve()
    raw = Path(__file__).resolve().parents[1] / 'data/raw'
    if output.exists() or output.suffix.lower()!='.html' or output.is_relative_to(args.images.resolve()) or output.is_relative_to(raw.resolve()):
        raise ValueError('输出须为图片目录外的新 HTML 文件')
    page=build_page(json.loads(args.queue.read_text(encoding='utf-8')),json.loads(args.contexts.read_text(encoding='utf-8')),load_labels(args.labels),args.images)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as f:f.write(page)
    print(output)

if __name__=='__main__':main()
