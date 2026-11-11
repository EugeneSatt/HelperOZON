#!/usr/bin/env python3
"""Read selected SKU rows from an Ozon Seller price XLSX without loading its styles."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import posixpath
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'

def extract(path,skus):
    with ZipFile(path) as z:
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            shared=[''.join(x.itertext()) for x in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        def values(row):
            result={}
            for cell in row.findall('s:c',NS):
                v=cell.find('s:v',NS);text=v.text if v is not None else ''
                if cell.get('t')=='s':text=shared[int(text)] if text else ''
                elif cell.get('t')=='inlineStr':text=''.join(cell.find('s:is',NS).itertext())
                result[re.sub(r'\d+$','',cell.get('r'))]=text
            return result
        rels={r.get('Id'):r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        found=[];definitions={}
        for sheet in ET.fromstring(z.read('xl/workbook.xml')).findall('s:sheets/s:sheet',NS):
            target=rels[sheet.get('{'+REL+'}id')]
            part=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            rows=ET.fromstring(z.read(part)).findall('s:sheetData/s:row',NS)
            header=None;cols=None
            for row in rows:
                vals=values(row)
                if 'SKU' in vals.values() and 'Предельная цена, руб.' in vals.values():
                    header=row.get('r');cols={v:k for k,v in vals.items() if v};continue
                if cols is None:continue
                if row.get('r')==str(int(header)+2):
                    definitions={name:vals.get(cols[name],'') for name in ['Предельная цена, руб.','Цена реализации, руб.'] if name in cols}
                target_sku=vals.get(cols['SKU'])
                if target_sku not in skus:continue
                field='Предельная цена, руб.'
                raw=vals.get(cols[field],'')
                price=float(raw.replace(',','.')) if raw else None
                found.append({'sku':target_sku,'offer_id':vals.get(cols.get('Артикул')),
                    'title':vals.get(cols.get('Название товара')),'cabinet_price':price,'cabinet_field':field,
                    'realization_price':vals.get(cols.get('Цена реализации, руб.')),
                    'sheet':sheet.get('name'),'row':int(row.get('r')),
                    'locator':sheet.get('name')+'!'+cols['SKU']+row.get('r')+', '+cols[field]+row.get('r')})
        if len({r['sku'] for r in found})!=len(found):raise ValueError('Несколько строк одного SKU: проверь предложение/схему')
        return {'rows':found,'missing_skus':[s for s in skus if s not in {r['sku'] for r in found}], 'definitions':definitions}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--skus',nargs='+',required=True);p.add_argument('--captured-at',required=True)
    p.add_argument('--seller-name',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();t=datetime.fromisoformat(a.captured_at.replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('Время исходного отчёта должно содержать часовой пояс')
    if a.input.resolve()==a.output.resolve():raise ValueError('Не перезаписывай исходный отчёт')
    result=extract(a.input,a.skus);result.update(source_file=str(a.input.resolve()),captured_at=a.captured_at,seller_name=a.seller_name)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'matched':len(result['rows']),'missing_skus':result['missing_skus']},ensure_ascii=False))

if __name__=='__main__':main()
