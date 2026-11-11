#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
const args={};
for(let i=2;i<process.argv.length;i+=2){
 if(!['--input','--output','--preview-dir'].includes(process.argv[i])||!process.argv[i+1])throw Error('Use --input prices.json --output prices.xlsx [--preview-dir folder]');
 args[process.argv[i].slice(2)]=process.argv[i+1];
}
if(!args.input||!args.output||path.resolve(args.input)===path.resolve(args.output))throw Error('Input and distinct output required');
const {Workbook,SpreadsheetFile}=await import(process.env.ARTIFACT_TOOL_MODULE||'@oai/artifact-tool');
const data=JSON.parse(await fs.readFile(args.input,'utf8'));
if(!data.coverage||!Array.isArray(data.rows)||!data.input_sha256)throw Error('Run prepare_export.py first');
const wb=Workbook.create(),prices=wb.worksheets.add('Цены'),notes=wb.worksheets.add('Сбор');
const font={name:'Arial',size:11,color:'#172841'};
const offset=data.meta.display_utc_offset_minutes??180,zone=data.meta.display_timezone_label??'МСК';
const serial=s=>s?Date.parse(s)/86400000+25569+offset/1440:null;
const literal=v=>typeof v==='string'&&(/^[\s]*[=+@-]/.test(v)||/^[\t\r\n]/.test(v))?"'"+v:v;
const timeText=s=>s?new Date(Date.parse(s)+offset*60000).toISOString().slice(0,19).replace('T',' '):'';
const rows=data.rows,last=rows.length+5;
for(const s of [prices,notes]){s.showGridLines=false;s.tabColor='#005BFF';}
const headers=['Ozon SKU','Артикул продавца','Товар','Город','Кабинетная цена, ₽',
 'Ozon Карта','Без Ozon Карты','СПП',`Витрина (${zone})`,`Кабинет (${zone})`,'Условия / пропуски'];
const fields=['sku','offer_id','title','region','seller_base_price','price_ozon_card','price_other_banks','spp_rate','captured_at','cabinet_captured_at','reason'];
function heading(s,range){s.getRange(range).format={font:{...font,bold:true,color:'#FFFFFF'},fill:'#172841',wrapText:true,rowHeightPx:58,horizontalAlignment:'center',verticalAlignment:'center'};}
function title(s,text,sub,end){
 s.getRange(`A2:${end}2`).merge();s.getRange('A2').values=[[text]];
 s.getRange(`A2:${end}2`).format={font:{...font,size:16,bold:true},rowHeightPx:34};
 s.getRange(`A3:${end}3`).merge();s.getRange('A3').values=[[sub]];
 s.getRange(`A3:${end}3`).format={font:{...font,size:10,color:'#66758B'},wrapText:true,rowHeightPx:38};
}
title(prices,(data.meta.demo?'ДЕМОНСТРАЦИЯ. ':'')+'Цены Ozon',`${data.meta.region}. ${timeText(data.meta.started_at)} — ${timeText(data.meta.finished_at)} ${zone}. Проверок: ${rows.length}. ${data.coverage.complete?'Все цели обработаны.':'Частичная выгрузка: причины на листе «Сбор».'}`,'K');
prices.getRange('A5:K5').values=[headers];heading(prices,'A5:K5');
const widths=[125,135,310,165,135,140,140,135,170,170,390];
widths.forEach((v,i)=>prices.getRangeByIndexes(0,i,Math.max(last,6),1).format.columnWidthPx=v);
if(rows.length){
 prices.getRange(`A6:K${last}`).values=rows.map(r=>fields.map(k=>literal(k==='captured_at'||k==='cabinet_captured_at'?serial(r[k]):r[k]??null)));
 prices.getRange(`A6:K${last}`).format={font,wrapText:true,verticalAlignment:'center',rowHeightPx:58};
 prices.getRange(`E6:G${last}`).setNumberFormat('#,##0.00');prices.getRange(`H6:H${last}`).setNumberFormat('0.0%');
 prices.getRange(`I6:J${last}`).setNumberFormat('yyyy-mm-dd hh:mm:ss');
 prices.getRange(`E6:J${last}`).format.horizontalAlignment='right';
 for(let i=0;i<rows.length;i++){
  const n=i+6;if(i%2)prices.getRange(`A${n}:K${n}`).format.fill='#F5F8FC';
 }
 prices.getRange(`F6:F${last}`).format.fill='#E4F4DE';prices.getRange(`G6:G${last}`).format.fill='#ECEFF3';
 prices.getRange(`K6:K${last}`).format.font={...font,size:10,color:'#66758B'};
 prices.getRange(`A6:K${last}`).format.autofitRows();
 const table=prices.tables.add(`A5:K${last}`,true,'OzonPrices');table.showFilterButton=true;table.style='TableStyleLight1';
}
prices.freezePanes.freezeRows(5);prices.freezePanes.freezeColumns(2);
title(notes,'Сбор и определения','Зелёная — Ozon Карта. Серая — «С другими банками». СПП рассчитана только от серой цены относительно кабинетной.','D');
[210,360,460,370].forEach((v,i)=>notes.getRangeByIndexes(0,i,80+data.sources.length,1).format.columnWidthPx=v);
const records=[
 ['Охват',`${new Set(rows.map(r=>r.sku).filter(Boolean)).size} SKU; ${data.meta.regions?.length??1} города; ${rows.length} проверок; ${data.coverage.complete?'полный сбор':'частичный сбор'}`],
 ['Города',data.meta.region],['Период витрины',`${timeText(data.meta.started_at)} — ${timeText(data.meta.finished_at)} ${zone}`],
 ['Кабинет',data.meta.seller_cabinet??'Определяется по источникам'],
 ['Кабинетная цена','Поле Seller указано для каждого SKU ниже. «Предельная цена» — установленный продавцом предел цены на сайте. «Цена реализации» и зачёркнутая цена не подменяют это поле.'],
 ['Расчёт СПП','(Кабинетная цена − серая цена) / кабинетная цена. В Excel — процент. Зелёная цена в формулу не входит. Это расчётное сравнение цен, не сумма компенсации и не выручка.'],
 ['Неизвестное и ноль','Неизвестное — пусто с причиной. Подтверждённые 0% сохраняются числом 0. Отрицательный процент означает, что серая цена выше кабинетной.'],
 ['Сопоставимость',`Проверяются SKU, продавец, вариант, город/область действия, условия и время. Максимальная разница времени: ${data.meta.max_spp_gap_minutes??15} мин. Несопоставимая кабинетная цена по времени видна, СПП остаётся пустой.`],
 ...data.coverage.issues.map(x=>['Проблема',x]),...data.coverage.warnings.map(x=>['Примечание',x])];
let n=5;
for(const [label,value] of records){
 notes.getRange(`A${n}:D${n}`).values=[[label,literal(value),null,null]];notes.getRange(`B${n}:D${n}`).merge();
 notes.getRange(`A${n}:D${n}`).format={font,wrapText:true,verticalAlignment:'center',rowHeightPx:42};
 notes.getRange(`A${n}`).format.font={...font,bold:true};n++;
}
notes.getRange(`A5:D${n-1}`).format.autofitRows();n+=2;
const cabinetStart=n;
notes.getRange(`A${n}:D${n}`).values=[['SKU / артикул','Кабинетная цена, ₽','Поле / время','Источник / строка']];heading(notes,`A${n}:D${n}`);n++;
const seen=new Set(),unique=rows.filter(r=>{const k=[r.sku,r.seller_id||r.seller_url,r.cabinet_captured_at,r.seller_base_price].join('|');if(seen.has(k))return false;seen.add(k);return true;});
for(const r of unique){
 notes.getRange(`A${n}:D${n}`).values=[[`${r.sku??''} / ${r.offer_id??''}`,r.seller_base_price??null,`${r.cabinet_field??''}; ${timeText(r.cabinet_captured_at)} ${zone}`,r.source_ids??'']];
 notes.getRange(`A${n}:D${n}`).format={font,wrapText:true,rowHeightPx:48};notes.getRange(`B${n}`).setNumberFormat('#,##0.00');n++;
}
notes.getRange(`A${cabinetStart+1}:D${n-1}`).format.autofitRows();n+=2;
const sourceStart=n;
notes.getRange(`A${n}:D${n}`).values=[['Источник','Тип / время','Локатор','Ссылка / исходный файл']];heading(notes,`A${n}:D${n}`);n++;
for(const s of data.sources){
 notes.getRange(`A${n}:D${n}`).values=[[s.id,`${s.kind}; ${timeText(s.captured_at)} ${zone}`,s.locator,s.url||path.basename(s.file||'')].map(literal)];
 notes.getRange(`A${n}:D${n}`).format={font,wrapText:true,rowHeightPx:48};n++;
}
if(n>sourceStart+1)notes.getRange(`A${sourceStart+1}:D${n-1}`).format.autofitRows();
wb.recalculate();
console.log((await wb.inspect({kind:'table',range:`Цены!A5:J${Math.min(last,14)}`,include:'values,formulas',tableMaxRows:10,tableMaxCols:10,maxChars:4000})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:10},summary:'formula errors'})).ndjson);
if(args['preview-dir']){
 await fs.mkdir(args['preview-dir'],{recursive:true});
 for(const [sheet,range,name] of [['Цены',`A1:K${last}`,'prices'],['Сбор',`A1:D${n}`,'collection']]){
  const b=await wb.render({sheetName:sheet,range,scale:1,format:'png'});await fs.writeFile(path.join(args['preview-dir'],name+'.png'),new Uint8Array(await b.arrayBuffer()));
 }
}
await fs.mkdir(path.dirname(path.resolve(args.output)),{recursive:true});
await (await SpreadsheetFile.exportXlsx(wb)).save(args.output);
console.log(JSON.stringify({output:path.resolve(args.output),observations:rows.length,complete:data.coverage.complete}));
