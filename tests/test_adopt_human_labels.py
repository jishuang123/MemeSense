"""采用人工标签及下游划分的独立合成测试。"""
import csv
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from build_annotation_page import load_labels
from memesense.data.adopt_human_labels import adopt_human_labels
from memesense.data.second_review_import import ORIGIN
from test_review_page import sample


def write(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def fixtures(root):
    """六条记录含同模板、助手/人工冲突及人工 uncertain。"""
    originals=[]; human=[]
    for i,label in enumerate(['thank','agree','comfort','request','uncertain','thank'],1):
        row={**sample(i,f'{i}.png'),'template_id':f'T{(1 if i==6 else i):04d}',
             'review_status':'correct','review_original_template_id':'T0001',
             'intent_label':'uncertain' if i!=5 else 'agree','annotation_notes':'助手视觉试标（合成测试）',
             'annotation_status':'annotated','label_schema_version':'intent-draft-v1','source':'synthetic_test_only'}
        originals.append(row)
        human.append({**row,'priority':'P0','annotation_origin':ORIGIN,'human_label':label,
            'human_note':'合成测试,备注"\n不是真实人工复核','human_review_status':'reviewed',
            'assistant_reference_viewed':'true','msairs_reference_viewed':'false','reviewer_id':'synthetic'})
    write(root/'assistant.csv',originals);write(root/'human.csv',human)
    return originals,human


class AdoptHumanTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'outputs');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.base,self.human=fixtures(self.root)
        self.config=load_labels(ROOT/'configs/labels.yaml')

    def convert(self):
        return adopt_human_labels(self.root/'human.csv',self.root/'assistant.csv',self.config)

    def test_mapping_and_archival(self):
        _,rows=self.convert()
        for old,new in zip(self.human,rows):
            self.assertEqual(new['intent_label'],old['human_label'])
            self.assertEqual(new['annotation_notes'],old['human_note'])
            self.assertEqual(new['assistant_intent_label'],old['intent_label'])
            self.assertEqual(new['assistant_annotation_notes'],old['annotation_notes'])
            for key in old:
                if key not in ('intent_label','annotation_notes'):self.assertEqual(new[key],old[key])
        write(self.root/'human.csv',rows)
        with self.assertRaises(ValueError):self.convert()

    def test_invalid_and_tampered(self):
        for key,value in [('human_label',''),('human_label','bad'),('human_review_status','pending'),
                          ('label_schema_version','old'),('assistant_reference_viewed',''),
                          ('annotation_origin','human_gold'),('intent_label','thank'),
                          ('annotation_notes','tampered'),('template_id','T9999')]:
            with self.subTest(key=key):
                old=self.human[0][key];self.human[0][key]=value;write(self.root/'human.csv',self.human)
                with self.assertRaises(ValueError):self.convert()
                self.human[0][key]=old

    def test_cli_pipeline_and_protection(self):
        before={p:p.read_bytes() for p in [self.root/'assistant.csv',self.root/'human.csv']}
        target=self.root/'standard.csv'
        args=['--input',str(self.root/'human.csv'),'--baseline',str(self.root/'assistant.csv'),
              '--labels',str(ROOT/'configs/labels.yaml'),'--output',str(target)]
        def run(script,args,expected=0):
            result=subprocess.run([sys.executable,str(ROOT/'scripts'/script),*args],capture_output=True)
            self.assertEqual(result.returncode,expected,result.stderr)
        run('adopt_human_labels.py',args);content=target.read_bytes()
        run('adopt_human_labels.py',args,1);self.assertEqual(content,target.read_bytes())
        run('split_dataset.py',['--input',str(target),'--output-dir',str(self.root/'splits')])
        run('dataset_report.py',['--input',str(target),'--splits-dir',str(self.root/'splits'),'--output-dir',str(self.root/'report')])
        report=json.loads((self.root/'report/dataset_report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['assigned']['samples'],5)
        self.assertEqual(report['source']['labels']['thank'],2)
        self.assertEqual(report['partitions']['excluded_uncertain']['samples'],1)
        self.assertTrue(report['checks']['passed']);self.assertFalse(report['checks']['template_leakage'])
        partitions={}
        for name in ['train','val','test','excluded_uncertain']:
            with (self.root/'splits'/f'{name}.csv').open(encoding='utf-8-sig',newline='') as f:
                partitions[name]=list(csv.DictReader(f))
        self.assertEqual([r['sample_id'] for r in partitions['excluded_uncertain']],['M0005'])
        for rows in partitions.values():
            for row in rows:
                self.assertEqual(row['intent_label'],row['human_label'])
                self.assertEqual(row['assistant_reference_viewed'],'true')
        for path,old in before.items():self.assertEqual(path.read_bytes(),old)


if __name__=='__main__':unittest.main()
