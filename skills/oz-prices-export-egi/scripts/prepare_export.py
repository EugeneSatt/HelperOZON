#!/usr/bin/env python3
"""Validate an offline Ozon price snapshot. No network or credentials."""
import argparse
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import math
from pathlib import Path
import re

STATUSES={'ok','partial','unavailable','not_found','load_error','identity_mismatch'}
STATUS_LABELS={'ok':'Цены получены','partial':'Часть данных','unavailable':'Нет в наличии','not_found':'Не найден','load_error':'Ошибка загрузки','identity_mismatch':'Другое предложение'}
SOURCE_KINDS={'ozon_public_ui','browser_json','ozon_seller_ui','export','user_provided'}
BASE_DEFINITION='seller_after_own_promos_before_platform_discount'
TEXT_FIELDS=['sku','region','title','offer_id','seller_name','variant','seller_base_price',
 'price_ozon_card','price_other_banks','spp_rate','captured_at','cabinet_captured_at',
 'cabinet_field','status','reason','url','bank_label','source_ids']
HEADERS=['Ozon SKU','Город','Товар','Артикул продавца','Магазин','Вариант / комплект',
 'Кабинетная цена, ₽','Ozon Карта','Без Ozon Карты','СПП',
 'Время витрины','Время кабинета','Поле кабинетной цены','Статус','Причина / условия',
 'Ссылка на товар','Подпись зелёной цены','ID источников']

def require(ok,message):
    if not ok:raise ValueError(message)

def timestamp(value):
    require(isinstance(value,str),'Время должно быть ISO-строкой с часовым поясом')
    t=datetime.fromisoformat(value.replace('Z','+00:00'))
    require(t.tzinfo is not None,'У времени нет часового пояса')
    return t

def sku(value):
    s=str(value)
    require(type(value) in (str,int) and s.isascii() and s.isdigit() and int(s)>0,'Некорректный Ozon SKU')
    return str(int(s))

def money(value):
    require(type(value) in (int,float) and math.isfinite(value) and value>0,'Цена должна быть положительным числом; неизвестное — null')
    original=Decimal(str(value));rounded=original.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    require(rounded>0 and original==rounded,'Цена должна быть в рублях с точностью до копеек')
    return rounded

def parse_price(text):
    """Parse one currency amount; never strip all nondigits from mixed labels."""
    require(isinstance(text,str),'Ожидался текст цены')
    s=text.replace('\u00a0',' ').replace('\u202f',' ').strip()
    m=re.fullmatch(r'(\d+(?: \d{3})*(?:[.,]\d{1,2})?)\s*(?:₽|руб\.?|RUB)?',s,re.I)
    require(m is not None,'Не одна денежная сумма: проверь диапазон, рассрочку и подпись')
    v=Decimal(m.group(1).replace(' ','').replace(',','.'))
    require(v>0,'Цена должна быть положительной')
    return float(v)

def number(d):return float(d) if d is not None else None

def csv_safe(value):
    if value is None:return ''
    if isinstance(value,str) and (value[:1] in ('\t','\r','\n') or value.lstrip().startswith(('=','+','-','@'))):return "'"+value
    return value

def prepare(data):
    meta=data['meta'];start=timestamp(meta['started_at']);finish=timestamp(meta['finished_at'])
    require(start<=finish,'Конец сбора раньше начала')
    regions=meta.get('regions') or [meta.get('region')]
    require(isinstance(regions,list) and regions and all(isinstance(x,str) and x.strip() for x in regions) and len(set(regions))==len(regions),'Нужен список подтверждённых городов без повторов')
    meta=dict(meta,regions=regions,region=', '.join(regions))
    require(meta.get('currency','RUB')=='RUB','Этот шаблон выгружает рубли; другая валюта требует отдельного согласованного формата')
    maxgap=meta.get('max_spp_gap_minutes',15)
    require(type(maxgap) in (int,float) and math.isfinite(maxgap) and maxgap>0,'Неверный интервал СПП')
    sources={}
    for s in data.get('sources',[]):
        require(s['id'] not in sources,'Повтор ID источника')
        require(s['kind'] in SOURCE_KINDS and bool(s.get('locator')) and bool(s.get('url') or s.get('file')),'Неполный источник')
        timestamp(s['captured_at']);sources[s['id']]=s
    requests={}
    require(bool(data.get('requests')),'Пользователь не задал товары или магазины')
    for r in data['requests']:
        require(r['id'] not in requests,'Повтор ID цели')
        require(r['type'] in ('sku','seller_article','store') and str(r.get('value','')).strip(),'Неполная цель')
        if r['type']=='sku':sku(r['value'])
        requests[r['id']]=r
    catalogs={}
    for c in data.get('catalogs',[]):
        rid=c['request_id']
        require(rid in requests and requests[rid]['type']=='store' and rid not in catalogs,'Каталог не связан с уникальной store-целью')
        require(c['source_id'] in sources and bool(c.get('seller_id')),'Нет источника/продавца каталога')
        require(type(c['complete']) is bool and bool(c.get('stop_reason')),'Неполные условия окончания каталога')
        require(not c['complete'] or c['stop_reason']=='end_of_catalog','Лимит или ошибка не доказывают конец каталога')
        c=dict(c,discovered_skus=list(dict.fromkeys(sku(x) for x in c['discovered_skus'])))
        if c.get('expected_count') is not None:
            require(type(c['expected_count']) is int and c['expected_count']>=0,'Некорректный размер каталога')
        catalogs[rid]=c
    warnings=[];rows=[]
    def amount(obs):
        if obs is None or obs.get('value') is None:return None
        require(obs.get('source_id') in sources,'Нет источника цены')
        return money(obs['value'])
    for raw in data.get('rows',[]):
        row=dict(raw);refs=row.get('request_ids',[])
        require(isinstance(refs,list) and refs and all(x in requests for x in refs),'Строка без известной цели')
        require(row.get('status') in STATUSES,'Неизвестный статус строки')
        require(row.get('region') in regions,'Город строки отсутствует в списке сбора')
        region=row['region']
        time=timestamp(row['captured_at']);require(start<=time<=finish,'Время строки вне интервала сбора')
        if row.get('sku') is not None:row['sku']=sku(row['sku'])
        if row['status'] in ('ok','partial'):
            require(row.get('sku') and row.get('seller_name') and row.get('variant'),'Не хватает идентификации предложения')
            require(row.get('seller_id') or row.get('seller_url'),'Нет ID/ссылки продавца')
            require(row.get('identity_source_id') in sources,'Нет источника привязки предложения')
        else:require(bool(row.get('notes')),'Нужна причина ошибки/недоступности')
        for rid in refs:
            req=requests[rid]
            if row.get('sku') and req['type']=='sku':require(row['sku']==sku(req['value']),'Результат относится к другому запрошенному SKU')
            if req.get('seller_id') and row.get('seller_id'):require(str(req['seller_id'])==str(row['seller_id']),'Результат относится к другому продавцу')
            if rid in catalogs and row.get('sku'):
                require(row['sku'] in catalogs[rid]['discovered_skus'],'SKU отсутствует в зафиксированном каталоге')
                if row.get('seller_id'):require(str(row['seller_id'])==str(catalogs[rid]['seller_id']),'В каталог попал другой продавец')
        ordinary=amount(row.get('other_banks'));bank=amount(row.get('bank_offer'));base=amount(row.get('seller_base'))
        bankobs=row.get('bank_offer') or {};baseobs=row.get('seller_base') or {}
        require(bankobs.get('includes_ozon_bank') is None or type(bankobs['includes_ozon_bank']) is bool,'Участие Ozon Банка должно быть true/false/null')
        if bank is not None:require(bool(bankobs.get('label')),'Не сохранено условие банковской цены')
        ozon=bank if bankobs.get('includes_ozon_bank') is True else None
        verified=row.get('identity_verified') is True and row['status'] in ('ok','partial')
        sd=sr=None;reasons=[row.get('notes','')]
        if ordinary is None:reasons.append((row.get('other_banks') or {}).get('missing_reason') or 'Цена с другими банками недоступна')
        if bank is None:reasons.append(bankobs.get('missing_reason') or 'Банковская цена недоступна')
        if not verified:reasons.append('Предложение/наличие не подтверждено; скидки не рассчитаны')
        spp_reason='Нет подтверждённой базы СПП'
        if base is not None:
            src=sources[baseobs['source_id']]
            seller_match=(bool(row.get('seller_id')) and str(baseobs.get('seller_id'))==str(row['seller_id'])) or (bool(row.get('seller_url')) and baseobs.get('seller_url')==row['seller_url'])
            identity=(str(baseobs.get('sku'))==row.get('sku') and seller_match and baseobs.get('variant')==row.get('variant'))
            if not verified:spp_reason='Идентичность предложения не подтверждена'
            elif ordinary is None:spp_reason='Нет цены с другими банками'
            elif src['kind'] not in ('ozon_seller_ui','export','user_provided'):spp_reason='Публичная зачёркнутая цена не является базой СПП'
            elif baseobs.get('definition') not in (BASE_DEFINITION,'seller_price_cap'):spp_reason='Не подтверждено поле кабинетной цены'
            elif not identity:spp_reason='База относится к другому SKU, продавцу или варианту'
            elif region not in (baseobs.get('regions') or [baseobs.get('region')]):spp_reason='Регион кабинетной цены отличается или не подтверждён'
            elif baseobs.get('conditions_comparable') is not True:spp_reason='Условия цены/состав скидок не сопоставлены'
            elif abs((timestamp(src['captured_at'])-timestamp(sources[row['other_banks']['source_id']]['captured_at'])).total_seconds())>maxgap*60:spp_reason='База и витрина измерены с превышением допустимого интервала'
            else:
                sd=base-ordinary
                sr=sd/base;spp_reason='СПП = (кабинетная − серая) / кабинетная'
                if sd<0:spp_reason+='; серая цена выше кабинетной'
            if not identity or src['kind'] not in ('ozon_seller_ui','export','user_provided'):base=None
        reasons.append(spp_reason)
        if bank is not None and ozon is None:reasons.append('Участие Ozon Банка в банковской цене не подтверждено')
        status=row['status']
        if status=='ok' and (not verified or ordinary is None or bank is None or ozon is None):status='partial'
        ids=list(dict.fromkeys([row.get('identity_source_id')]+[o.get('source_id') for o in (row.get('other_banks'),row.get('bank_offer'),row.get('seller_base')) if o]))
        out={k:row.get(k) for k in ('sku','offer_id','title','seller_id','seller_name','seller_url','variant','region','captured_at','url')}
        out.update(request_ids=list(dict.fromkeys(refs)),price_ozon_card=number(ozon),price_other_banks=number(ordinary),
          seller_base_price=number(base),spp_rate=number(sr),
          cabinet_captured_at=sources[baseobs['source_id']]['captured_at'] if base is not None else None,
          cabinet_field=baseobs.get('label','База продавца') if base is not None else '',
          status=status,identity_verified=verified,spp_reason=spp_reason,reason='; '.join(x for x in reasons if x),bank_label=bankobs.get('label',''),source_ids=', '.join(x for x in ids if x))
        rows.append(out)
    # SKU alone cannot collapse competing offers or variants.
    grouped={};unresolved=[]
    for row in rows:
        if row['sku'] is None or not (row.get('seller_id') or row.get('seller_url')):unresolved.append(row);continue
        key=(row['sku'],str(row.get('seller_id') or row.get('seller_url')),row.get('variant'),row['region'])
        old=grouped.get(key)
        if old:
            if timestamp(old['captured_at'])==timestamp(row['captured_at']):
                fields=('price_ozon_card','price_other_banks','seller_base_price','status')
                require(all(old.get(f)==row.get(f) for f in fields),'Конфликт цен одного предложения в одно время')
            refs=list(dict.fromkeys(old['request_ids']+row['request_ids']))
            row=row if timestamp(row['captured_at'])>=timestamp(old['captured_at']) else old
            row['request_ids']=refs
            warnings.append('Несколько снимков предложения '+row['sku']+': выбран последний; исходные наблюдения сохранены в snapshot.json')
        grouped[key]=row
    rows=list(grouped.values())+unresolved
    for rid,req in requests.items():
        for missing_region in regions:
            if req['type']!='store' and not any(rid in r['request_ids'] and r['region']==missing_region for r in rows):
                rows.append(dict.fromkeys(TEXT_FIELDS,None)|{'request_ids':[rid],'sku':sku(req['value']) if req['type']=='sku' else None,'status':'not_found','reason':'Цель не получила результата: '+str(req['value']),'region':missing_region,'captured_at':meta['finished_at'],'identity_verified':False,'source_ids':''})
    issues=[]
    for rid,req in requests.items():
        target=[r for r in rows if rid in r['request_ids']]
        if req['type']=='store':
            c=catalogs.get(rid)
            if not c:issues.append(rid+': нет журнала каталога');continue
            processed={(r['sku'],r['region']) for r in target if r['sku']}
            missing={(s,g) for s in c['discovered_skus'] for g in regions}-processed
            if missing:
                issues.append(rid+': не обработаны SKU/города '+', '.join(s+' / '+g for s,g in sorted(missing)))
                for lost,lost_region in sorted(missing):
                    placeholder=dict.fromkeys(TEXT_FIELDS,None)|{'request_ids':[rid],'sku':lost,'seller_id':str(c['seller_id']),'status':'load_error','reason':'Обнаружен в каталоге, но карточка не обработана','region':lost_region,'captured_at':meta['finished_at'],'identity_verified':False,'source_ids':c['source_id']}
                    rows.append(placeholder)
            if not c['complete']:issues.append(rid+': каталог не завершён — '+c['stop_reason'])
            if c.get('expected_count') is not None and len(c['discovered_skus'])!=c['expected_count']:issues.append(rid+': число уникальных SKU не совпало с ожидаемым')
        if any(r['status'] in ('not_found','load_error','identity_mismatch') or (r['status'] in ('ok','partial') and not r['identity_verified']) for r in target):issues.append(rid+': есть неразрешённые предложения/ошибки')
    rows.sort(key=lambda r:(r.get('seller_name') or '',int(r['sku']) if r['sku'] else 0,r.get('variant') or '',regions.index(r['region'])))
    return {'meta':meta,'requests':list(requests.values()),'catalogs':list(catalogs.values()),'sources':list(sources.values()),'rows':rows,
      'coverage':{'complete':not issues,'requests':len(requests),'offers':len(rows),'price_pairs':sum(r['price_ozon_card'] is not None and r['price_other_banks'] is not None and r['identity_verified'] for r in rows),'cabinet_prices':sum(r.get('seller_base_price') is not None for r in rows),
      'spp_calculated':sum(r['spp_rate'] is not None for r in rows),'issues':issues,'warnings':list(dict.fromkeys(warnings))},'fields':TEXT_FIELDS,'headers':HEADERS,'status_labels':STATUS_LABELS}

def write_csv(result,path):
    def field(row,key):
        value=STATUS_LABELS.get(row.get(key),row.get(key)) if key=='status' else row.get(key)
        if isinstance(value,float):return format(value,'.12g').replace('.',',')
        return csv_safe(value)
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter=';');w.writerow(HEADERS)
        for row in result['rows']:w.writerow(field(row,k) for k in TEXT_FIELDS)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--csv',type=Path)
    args=p.parse_args();require(args.input.resolve()!=args.output.resolve(),'Нельзя перезаписать исходный снимок')
    if args.csv:require(args.csv.resolve() not in (args.input.resolve(),args.output.resolve()),'CSV не должен перезаписывать JSON')
    raw=args.input.read_bytes();result=prepare(json.loads(raw));result['input_sha256']=hashlib.sha256(raw).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.csv:args.csv.parent.mkdir(parents=True,exist_ok=True);write_csv(result,args.csv)
    print(json.dumps({'output':str(args.output.resolve()),**result['coverage']},ensure_ascii=False))

if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,TypeError,InvalidOperation) as e:raise SystemExit('Ошибка данных: '+str(e))
