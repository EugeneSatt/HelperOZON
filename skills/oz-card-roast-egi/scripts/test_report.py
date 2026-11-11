"""Portable layout behavior using synthetic data only. Requires reportlab and pypdf."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from pypdf import PdfReader
from test_analyze import fixture
from render_pdf import render, private_funnel, register_fonts, check_groups, SKILL


def report_fixture(peers=3):
    audit = fixture(peers)
    audit['meta'].update(cabinet='ДЕМОНСТРАЦИЯ ШАБЛОНА', region='Москва')
    for i, p in enumerate(audit['products']):
        p.update(brand='ОБРАЗЕЦ' if i == 0 else f'АНАЛОГ {i}', name='Условный товар для проверки шаблона', cover_path=None, vision={})
    audit['findings'] = [{
        'metric_id': metric, 'fact': 'Условный факт из синтетического набора данных.',
        'hypothesis': 'Условная гипотеза, её влияние не подтверждено.',
        'action': 'Проверить наблюдение по исходным данным.',
        'verification': 'Повторить сопоставимую проверку и сравнить результат.',
        'source_ids': ['synthetic-0']
    } for metric in ['search_position', 'characteristics_count', 'infographic']]
    audit['limitations'] = ['Демонстрационные данные; это не аудит реального товара.']
    audit['report'] = {'takeaway':'ШАБЛОН ОТЧЁТА', 'summary':'Демонстрационный макет. Все названия и числа условные.',
                      'method_note':'Все значения синтетические и нужны только для проверки переносимого шаблона.',
                      'source_note':'Демонстрационные числа не описывают реальный товар или кабинет.'}
    return audit


class ReportTests(unittest.TestCase):
    def build(self, audit, folder):
        source = Path(folder)/'audit.json'; source.write_text(json.dumps(audit,ensure_ascii=False),encoding='utf-8')
        output = Path(folder)/'report.pdf'
        result = render(source, output)
        return result, output, '\n'.join(p.extract_text() for p in PdfReader(output).pages)

    def test_three_peers_and_current_id(self):
        with tempfile.TemporaryDirectory() as d:
            result, output, text = self.build(report_fixture(), d)
            self.assertEqual(result['pages'],3)
            for p in report_fixture()['products']:
                self.assertIn(p['sku'], text)
            self.assertIn('Обложка недоступна',text)

    def test_search_conversion_keeps_its_source_label(self):
        a=report_fixture()
        a['private_funnel']={'sku':'1000','account':a['meta']['cabinet'],'period':['2026-09-26','2026-10-25'],
                            'source_id':'synthetic-0','views':0,'ctr':0,
                            'labels':{'views':'поиск / каталог','ctr':'поиск > карточка'}}
        with tempfile.TemporaryDirectory() as d:
            _, _, text=self.build(a,d)
            self.assertIn('поиск / каталог',text)
            self.assertIn('поиск > карточка',text)
            self.assertIn('0,0%',text)

    def test_five_peers_expand_without_losing_products(self):
        with tempfile.TemporaryDirectory() as d:
            audit=report_fixture(5)
            result, _, text=self.build(audit,d)
            self.assertEqual(result['pages'],4)
            for p in audit['products']:
                self.assertIn(p['sku'],text)

    def test_sparse_data_no_invented_score_or_findings(self):
        with tempfile.TemporaryDirectory() as d:
            a=report_fixture(0);a['findings']=[]
            for key in a['products'][0]['metrics']:
                a['products'][0]['metrics'][key]={'value':None,'missing_reason':'Синтетический пропуск'}
            result, _, text=self.build(a,d)
            self.assertEqual(result['pages'],3)
            self.assertIn('Индекс не рассчитан',text)
            self.assertIn('Подтверждённых проблем',text)

    def test_private_zero_is_not_missing_and_binding_is_enforced(self):
        a=report_fixture();a['private_funnel']={'sku':'1000','account':a['meta']['cabinet'],'period':['2026-09-26','2026-10-25'],'source_id':'synthetic-0','orders':0,'order_value':0,'views':0}
        self.assertEqual(private_funnel(a)['orders'],0)
        a['private_funnel']['sku']='9000'
        with self.assertRaises(ValueError): private_funnel(a)

    def test_long_findings_paginate_instead_of_clipping(self):
        a=report_fixture();register_fonts()
        for f in a['findings']:
            for key in ['fact','hypothesis','action','verification']:
                f[key]='Проверяемое наблюдение и его ограничение. '*10
        self.assertGreater(len(check_groups(a['findings'])),1)

    def test_qualitative_ozon_finding_has_renderable_heading(self):
        with tempfile.TemporaryDirectory() as d:
            audit = report_fixture()
            audit['findings'] = [dict(audit['findings'][0], metric_id='rich_content', title='Показать состав комплекта')]
            _, _, text = self.build(audit, d)
            self.assertIn('ПОКАЗАТЬ СОСТАВ КОМПЛЕКТА', text)
            self.assertIn('Продавец 1', text)

    def test_declared_missing_file_is_not_silently_replaced(self):
        a=report_fixture();a['products'][0]['cover_path']='does-not-exist.png'
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): self.build(a,d)

    def test_fonts_and_glyphs_are_embedded(self):
        with tempfile.TemporaryDirectory() as d:
            _, output, _=self.build(report_fixture(),d)
            names=[]
            for page in PdfReader(output).pages:
                for obj in page['/Resources']['/Font'].values():
                    f=obj.get_object();descriptor=f.get('/FontDescriptor')
                    if descriptor:
                        self.assertIn('/FontFile2',descriptor.get_object())
                        names.append(str(f['/BaseFont']))
            self.assertTrue(any('WBRoastDisplay' in n for n in names))
            self.assertTrue(any('Caveat' in n for n in names))

    def test_relocation_produces_identical_pdf_without_os_fonts(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);moved=root/'другой компьютер'/'oz-card-roast-egi'
            shutil.copytree(SKILL,moved,ignore=shutil.ignore_patterns('__pycache__','*.pyc','node_modules'))
            _, original, _=self.build(report_fixture(),root)
            output=root/'moved.pdf'
            run=subprocess.run([sys.executable,str(moved/'scripts/render_pdf.py'),str(root/'audit.json'),'--output',str(output)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),hashlib.sha256(output.read_bytes()).hexdigest())


if __name__=='__main__':
    unittest.main()
