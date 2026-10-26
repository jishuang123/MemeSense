"""独立合成数据验证二次复核，不代填真实人工结果。"""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'scripts')]
from build_annotation_page import load_labels
from memesense.data.second_review_import import EXPORT_FIELDS, ORIGIN, validate_second_review
from test_review_page import sample


class SecondReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'outputs')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = load_labels(ROOT/'configs/labels.yaml')
        self.base, self.source, self.queue = [self.root/n for n in ('base.csv','human.csv','queue.json')]
        self.originals = [{**sample(i,f'{i}.png'), 'review_status':'correct',
            'review_original_template_id':'T0001', 'intent_label':'uncertain',
            'annotation_status':'annotated', 'annotation_notes':'助手视觉试标',
            'label_schema_version':self.config['version']} for i in (1,2)]
        self.write(self.base,self.originals)
        queue = [dict(sample_id=r['sample_id'], template_id=r['template_id'], image_path=r['image_path'],
                      priority='P0', annotation_origin=ORIGIN, current_label=r['intent_label'],
                      assistant_note=r['annotation_notes']) for r in self.originals]
        self.queue.write_text(json.dumps(queue),encoding='utf-8')
        self.rows = [{k:q[k] for k in ('sample_id','template_id','image_path','priority','annotation_origin')}
                     | dict(label_schema_version=self.config['version'],human_label='thank',human_note='人工,引号"\n换行',
                            human_review_status='reviewed',assistant_reference_viewed='false',
                            msairs_reference_viewed='true',reviewer_id='tester') for q in queue]

    def write(self,path,rows,fields=None):
        with path.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)

    def validate(self,complete=True):
        self.write(self.source,self.rows,EXPORT_FIELDS)
        return validate_second_review(self.source,self.base,self.queue,self.config,complete)

    def test_preserves_both_judgments(self):
        _, rows, counts=self.validate()
        self.assertEqual(counts,{'reviewed':2,'pending':0})
        for original,row in zip(self.originals,rows):
            for key,value in original.items():self.assertEqual(row[key],value)
            self.assertEqual(row['human_label'],'thank')
            self.assertEqual(row['msairs_reference_viewed'],'true')
            self.assertEqual(row['human_note'],self.rows[0]['human_note'])

    def test_reject_bad_fields(self):
        cases=[('sample_id','M0000'),('sample_id','M0002'),('sample_id','M9999'),
               ('human_label','happy'),('human_label',''),('human_review_status','pending'),
               ('human_review_status','done'),('label_schema_version','old'),
               ('template_id','T9999'),('image_path','changed.png'),('priority','P2'),
               ('annotation_origin','human_gold'),('assistant_reference_viewed',''),
               ('msairs_reference_viewed','TRUE')]
        for key,value in cases:
            with self.subTest(key=key,value=value):
                old=self.rows[0][key];self.rows[0][key]=value
                with self.assertRaises(ValueError):self.validate(False)
                self.rows[0][key]=old

    def test_pending_and_uncertain(self):
        self.rows[0].update(human_label='',human_review_status='pending')
        self.assertEqual(self.validate(False)[2]['pending'],1)
        with self.assertRaises(ValueError):self.validate()
        self.rows[0].update(human_label='uncertain',human_review_status='reviewed')
        self.assertEqual(self.validate()[2]['reviewed'],2)

    def test_missing_rows_headers_and_stale_queue(self):
        removed=self.rows.pop()
        with self.assertRaises(ValueError):self.validate()
        self.rows.append(removed)
        for fields in [EXPORT_FIELDS[:-1],EXPORT_FIELDS+['sample_id']]:
            self.source.write_text(','.join(fields)+'\n',encoding='utf-8')
            with self.assertRaises(ValueError):validate_second_review(self.source,self.base,self.queue,self.config)
        queue=json.loads(self.queue.read_text());queue[0]['current_label']='thank'
        self.queue.write_text(json.dumps(queue))
        with self.assertRaises(ValueError):self.validate()

    def test_cli_check_import_and_no_overwrite(self):
        self.validate();output=self.root/'result.csv'
        before={p:p.read_bytes() for p in [self.source,self.base,self.queue]}
        command=[sys.executable,str(ROOT/'scripts/import_second_review.py'),'--input',str(self.source),
                 '--baseline',str(self.base),'--queue',str(self.queue),'--labels',str(ROOT/'configs/labels.yaml'),'--output',str(output)]
        self.assertEqual(subprocess.run(command+['--check-only'],capture_output=True).returncode,0)
        self.assertFalse(output.exists())
        self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)
        data=output.read_bytes()
        self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
        self.assertEqual(output.read_bytes(),data)
        for p,content in before.items():self.assertEqual(p.read_bytes(),content)


if __name__=='__main__':unittest.main()
