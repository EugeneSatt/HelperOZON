#!/usr/bin/env node
// Snapshot workbook. Calculations come from analyze.py, never from invented scores.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';

const opts={};
for(let i=2;i<process.argv.length;i+=2){
 const key=process.argv[i];
 if(!['--input','--comparison','--output','--preview-dir'].includes(key)||!process.argv[i+1]) throw Error('Use --input audit.json --comparison comparison.json --output report.xlsx [--preview-dir folder]');
 opts[key.slice(2)]=process.argv[i+1];
}
for(const k of ['input','comparison','output'])if(!opts[k])throw Error('Missing --'+k);
const artifactModule=process.env.ARTIFACT_TOOL_MODULE||'@oai/artifact-tool';
const artifactUrl=import.meta.resolve(artifactModule);
const {Workbook,SpreadsheetFile}=await import(artifactUrl);
const skill=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const theme=JSON.parse(await fs.readFile(path.join(skill,'assets/report-theme.json'),'utf8'));
// Register only in this rendering process. This never installs OS fonts.
const {FontLibrary}=createRequire(artifactUrl)('skia-canvas');
FontLibrary.use(theme.fonts.display.family,path.join(skill,'assets',theme.fonts.display.file));
FontLibrary.use(theme.fonts.body.family,[theme.fonts.body.file,theme.fonts.bold.file].map(f=>path.join(skill,'assets',f)));
FontLibrary.use(theme.fonts.hand.family,path.join(skill,'assets',theme.fonts.hand.file));
const inputBytes=await fs.readFile(opts.input);
const audit=JSON.parse(inputBytes.toString('utf8'));
const comp=JSON.parse(await fs.readFile(opts.comparison,'utf8'));
if(comp.input_sha256!==createHash('sha256').update(inputBytes).digest('hex'))throw Error('audit.json changed; rerun analyze.py before building the workbook');
const run=path.dirname(path.resolve(opts.input));
if(JSON.stringify(audit.meta)!==JSON.stringify(comp.meta))throw Error('audit and comparison metadata differ; rerun analyze.py');
const own=audit.products.find(p=>p.role==='own');
const peers=audit.products.filter(p=>p.role==='competitor');
const findings=audit.findings||[];
if(!own||String(own.sku)!==String(audit.meta.own_sku)||peers.length!==comp.score.competitor_count)throw Error('SKU or peer binding mismatch');
const products=[own,...peers], p=theme.palette;
const color=s=>p[theme.status_palette[s]];
const font={name:theme.fonts.body.family,size:11,color:p.ink};
const display=size=>({name:theme.fonts.display.family,size,color:p.ink});
const wb=Workbook.create();
const [main,actions,covers,sources]=['Сравнение','Что проверить','Обложки','Источники'].map(n=>wb.worksheets.add(n));
const col=i=>String.fromCharCode(65+i);
const last=col(5+peers.length), ownEnd=col(1+peers.length), median=col(2+peers.length), statusCol=col(3+peers.length);
const areaEnd=col(Math.max(7,5+peers.length));
const cell=v=>v===null||v===undefined?'—':typeof v==='boolean'?(v?'Да':'Нет'):v;
const stamp=new Intl.DateTimeFormat('ru-RU',{timeZone:'Europe/Moscow',dateStyle:'short',timeStyle:'short'});
const labels={green:'Выше ориентира',yellow:'На уровне',red:'Ниже ориентира',nodata:'Нет сравнения',info:'Информация'};
for(const [s,range,tab] of [[main,`A1:${areaEnd}43`,p.sky],[actions,'A1:D16',p.pink],[covers,`A1:${col(products.length-1)}33`,p.lime],[sources,'A1:E240',p.paper]]){
 s.showGridLines=false;s.tabColor=tab;
 s.getRange(range).format={fill:p.paper,font,verticalAlignment:'center'};
}
function widths(s,list){list.forEach((w,i)=>s.getRangeByIndexes(0,i,240,1).format.columnWidthPx=w);}
function title(s,t,sub){
 s.getRange('A2').values=[[t.toLocaleUpperCase('ru')]];
 s.getRange('A2').format.font=display(28);s.getRange('A2:L2').format.rowHeightPx=58;
 s.getRange('A3').values=[[sub]];s.getRange('A3').format.font={...font,size:10,color:p.muted};
 s.getRange('A3:L3').format.rowHeightPx=28;
}
function header(s,r){s.getRange(r).format={fill:p.ink,font:{...font,bold:true,color:p.white},wrapText:true,horizontalAlignment:'center',verticalAlignment:'center',rowHeightPx:48};}
function section(s,row,t){s.getRange(`A${row}`).values=[[t]];s.getRange(`A${row}`).format.font=display(20);s.getRange(`A${row}:E${row}`).format.rowHeightPx=39;}
function body(s,r,height=36,fill=p.paper){s.getRange(r).format={font,fill,wrapText:true,verticalAlignment:'center',rowHeightPx:height};}

title(main,(own.brand||'Ozon')+': сравнение карточки',`${own.sku} · ${audit.meta.cabinet} · ${audit.meta.period_start} — ${audit.meta.period_end} · ${audit.meta.region||'регион не задан'}`);
widths(main,[265,115,...peers.map(()=>135),115,165,265,130]);
main.getRange('A5:D5').values=[[comp.score.partial?'Частичный индекс':'Структурный индекс',cell(comp.score.value),'из 100',peers.length+' предварительных аналога']];
main.getRange('A5:C5').format={fill:p.pink,font:{...font,bold:true,size:12},rowHeightPx:55};
main.getRange('B5').format.font=display(30);
main.getRange('D5:F5').merge();main.getRange('D5:F5').format={fill:p.sky,font:{...font,bold:true,size:12},wrapText:true,horizontalAlignment:'center',verticalAlignment:'center'};
main.getRange('A6').values=[[`Покрытие: ${comp.score.counted_metrics}/14; вес ${comp.score.counted_weight}/18; ключевые ${comp.score.counted_key_metrics}/4.`]];
main.getRange('A7').values=[['Структурный индекс не доказывает причины продаж. Снимок обновляется повторным сбором и расчётом.']];
main.getRange(`A6:${areaEnd}7`).format.font={...font,size:10,color:p.muted};
main.getRange(`A9:${last}9`).values=[['Показатель',(own.brand||'Мы')+' / мы',...peers.map(x=>(x.brand||'Конкурент')+'\n'+x.sku),'Медиана','Статус','В индексе / причина','Сопоставимо']];
header(main,`A9:${last}9`);
const fractions=new Set(['negative_share','ctr','cart_to_order','card_to_cart']);
for(let i=0;i<comp.rows.length;i++){
 const r=comp.rows[i],n=i+10;
 const label=r.metric_id==='price'?'Цена MPStats, руб.':r.metric_id==='ozon_card_price'?'С Ozon Картой / банками, руб.':r.metric_id==='buyer_price'?'С другими банками, руб.':r.label;
 const state=r.direction==='bool'&&r.own.valid?(r.own.value?'Есть':'Нет'):!r.own.valid&&r.own.value!==null?'Исключено':labels[r.status];
 const why=r.included_in_score?'Да':r.weight?r.excluded_reason:'Информационная строка';
 main.getRange(`A${n}:${last}${n}`).values=[[label,cell(r.own.value),...r.competitors.map(x=>cell(x.value)),cell(r.median),state,why,r.comparable_competitors]];
 body(main,`A${n}:${last}${n}`,r.metric_id==='background'?66:40,i%2?p.paper:p.stripe);
 main.getRange(`B${n}:${median}${n}`).format.horizontalAlignment='right';
 main.getRange(`${statusCol}${n}`).format.horizontalAlignment='center';
 main.getRange(`B${n}`).format.fill=color(r.included_in_score?r.status:r.weight?'nodata':'info');
 if(fractions.has(r.metric_id))main.getRange(`B${n}:${median}${n}`).setNumberFormat('0.0%');
 else if(['price','ozon_card_price','buyer_price','revenue'].includes(r.metric_id))main.getRange(`B${n}:${median}${n}`).setNumberFormat('#,##0.00');
 else if(r.metric_id==='rating')main.getRange(`B${n}:${median}${n}`).setNumberFormat('0.0');
 else if(!['background','has_video','infographic'].includes(r.metric_id))main.getRange(`B${n}:${median}${n}`).setNumberFormat('#,##0');
}
let funnel=audit.private_funnel||(own.private_metrics&&!Array.isArray(own.private_metrics)?own.private_metrics:{});
if(Object.keys(funnel).length&&(String(funnel.sku)!==String(own.sku)||JSON.stringify(funnel.period)!==JSON.stringify([audit.meta.period_start,audit.meta.period_end])))throw Error('Ozon funnel belongs to a different SKU or period');
if(Object.keys(funnel).length&&funnel.account!==audit.meta.cabinet)throw Error('Ozon funnel belongs to a different seller cabinet');
if(Object.keys(funnel).length&&!audit.sources.some(s=>s.id===funnel.source_id))throw Error('Unknown Ozon funnel source');
main.getRange(`A10:${last}27`).format.autofitRows();
section(main,29,'Фактическая воронка Ozon Seller / наш SKU');
main.getRange('A31:D31').values=[['Показатель','Значение','Показатель','Значение']];header(main,'A31:D31');
const funnelLabels=funnel.labels||{};
main.getRange('A32:D37').values=[[funnelLabels.views||'Показы',cell(funnel.views),funnelLabels.ctr||'CTR',cell(funnel.ctr)],[funnelLabels.clicks||'Переходы',cell(funnel.clicks),'Карточка > корзина',cell(funnel.card_to_cart)],[funnelLabels.carts||'Корзины',cell(funnel.carts),'Корзина > заказ',cell(funnel.cart_to_order)],['Заказано, шт.',cell(funnel.orders),'Заказано > доставлено',cell(funnel.delivered_rate)],['Сумма заказов, руб.',cell(funnel.order_value),'Доставлено, шт.',cell(funnel.purchased)],['Средняя цена реализации, руб.',cell(funnel.average_order_price),'Отменено, шт.',cell(funnel.canceled)]];
body(main,'A32:D37',32);main.getRange('B32:B35').setNumberFormat('#,##0');main.getRange('B36:B37').setNumberFormat('#,##0.00');main.getRange('D32:D35').setNumberFormat('0.0%');main.getRange('D36:D37').setNumberFormat('#,##0');
main.getRange('A32:D37').format.autofitRows();
main.getRange('A39').values=[['Определения, даты снимков, охват склеек, источники значений и ограничения — на листе «Источники».']];
main.getRange('A41').values=[['Розовый — ниже ориентира; лайм — на уровне; голубой — выше / есть; серый — нет сравнения.']];
main.getRange(`A39:${areaEnd}41`).format.font={...font,size:10,color:p.muted};main.freezePanes.freezeRows(9);

title(actions,'Что проверить в карточке','Факт, гипотеза, действие и проверка. Изменения в кабинете не выполняются.');
widths(actions,[55,320,380,380]);actions.getRange('A5:D5').values=[['№','Факт','Действие','Как проверить']];header(actions,'A5:D5');
findings.forEach((f,i)=>{
 const n=6+i*3;
 actions.getRange(`A${n}:D${n}`).values=[[i+1,f.fact,f.action,f.verification]];body(actions,`A${n}:D${n}`,150,i%2?p.paper:p.stripe);
 actions.getRange(`A${n}`).format.font=display(30);actions.getRange(`A${n}`).format.fill=[p.sky,p.pink,p.lime][i];
 actions.getRange(`B${n+1}`).values=[['Гипотеза: '+f.hypothesis]];actions.getRange(`B${n+1}:D${n+1}`).merge();body(actions,`B${n+1}:D${n+1}`,58);
 actions.getRange(`B${n+2}`).values=[['Источники: '+f.source_ids.join(', ')]];actions.getRange(`B${n+2}`).format.font={...font,size:10,color:p.muted};
});
if(!findings.length)actions.getRange('B6').values=[['Данных для подтверждённых рекомендаций недостаточно.']];

title(covers,'Первые обложки','Размечены только доступные первые изображения выбранных SKU.');
widths(covers,products.map(()=>260));
for(let i=0;i<products.length;i++){
 const x=products[i],c=col(i);covers.getRange(`${c}5`).values=[[(x.brand||'Товар')+(x.role==='own'?' / мы':'')]];
 covers.getRange(`${c}5`).format={font:display(20),fill:[p.pink,p.sky,p.sky,p.lime][i%4],rowHeightPx:42};
 covers.getRange(`${c}6`).values=[[String(x.sku)+' · '+x.seller+' · '+x.variant]];covers.getRange(`${c}6`).format={font:{...font,size:10},wrapText:true,rowHeightPx:60};
 if(x.cover_path){
  const imgPath=path.isAbsolute(x.cover_path)?x.cover_path:path.join(run,x.cover_path);
  const img=await fs.readFile(imgPath);const mime=/\.webp$/i.test(imgPath)?'image/webp':/\.jpe?g$/i.test(imgPath)?'image/jpeg':'image/png';
  covers.images.add({dataUrl:`data:${mime};base64,`+img.toString('base64'),anchor:{from:{row:7,col:i},extent:{widthPx:220,heightPx:294}}});
 }else covers.getRange(`${c}8`).values=[['Обложка недоступна']];
 covers.getRange(`${c}22:${c}28`).values=[[x.vision?.text||'—'],[x.vision?.product||'—'],[x.vision?.background||'—'],[x.pack_count?'Упаковка: '+x.pack_count+' шт.':'Количество в упаковке не получено'],[cell(x.metrics.price?.value)],[cell(x.price_per_piece)],['Связанных вариантов: '+cell(x.merged_variants)]];
 covers.getRange(`${c}26:${c}27`).setNumberFormat('#,##0.00" руб."');
}
const coverEnd=col(products.length-1);covers.getRange(`A7:${coverEnd}21`).format.rowHeightPx=22;body(covers,`A22:${coverEnd}24`,82);body(covers,`A25:${coverEnd}28`,40);
covers.getRange('A30').values=[['Строка 26: цена упаковки MPStats; строка 27: цена единицы, если известна. Даты и различия упаковок — в источниках.']];
covers.getRange('A31').values=[['Наблюдаемые признаки обложки не доказывают причинное влияние на конверсию.']];

title(sources,'Источники и ограничения','Время получения приведено к Москве. Подробные определения — в локаторах.');
widths(sources,[185,420,290,550,200]);sources.getRange('A5:E5').values=[['ID','Тип','Файл','Отчёт / поле / метод','Получено, МСК']];header(sources,'A5:E5');
audit.sources.forEach((x,i)=>{const n=i+6;sources.getRange(`A${n}:E${n}`).values=[[x.id,x.kind,x.file||'—',x.locator,stamp.format(new Date(x.captured_at))]];body(sources,`A${n}:E${n}`,76,i%2?p.paper:p.stripe);});
if(audit.sources.length)sources.getRange(`A6:E${5+audit.sources.length}`).format.autofitRows();
const limitsStart=Math.max(27,audit.sources.length+8);section(sources,limitsStart,'Что ограничивает выводы');
(audit.limitations||[]).forEach((x,i)=>{const n=limitsStart+2+i;sources.getRange(`A${n}:B${n}`).values=[[i+1,x]];sources.getRange(`B${n}:E${n}`).merge();body(sources,`A${n}:E${n}`,74,i%2?p.paper:p.stripe);sources.getRange(`A${n}`).format={font:display(22),fill:[p.sky,p.pink,p.lime][i%3],horizontalAlignment:'center'};});
const rules=limitsStart+(audit.limitations||[]).length+4;section(sources,rules,'Как получен индекс '+cell(comp.score.value)+' / 100');
sources.getRange(`A${rules+2}:E${rules+2}`).values=[['Показатель','Вес в индексе','Зачтённый вес','Источник нашего значения','Причина исключения']];header(sources,`A${rules+2}:E${rules+2}`);
comp.rows.forEach((r,i)=>{const n=rules+3+i;sources.getRange(`A${n}:E${n}`).values=[[r.label,r.included_in_score?r.weight:0,r.included_in_score&&['green','yellow'].includes(r.status)?r.weight:0,r.own.source_id||'—',r.excluded_reason||(r.weight?'—':'Информация')]];body(sources,`A${n}:E${n}`,60);});
sources.getRange(`A${rules+3}:E${rules+20}`).format.autofitRows();
let cursor=rules+23;
sources.getRange(`A${cursor}`).values=[['Итого вес: '+comp.score.counted_weight+'; зачтено: '+comp.score.passed_weight+'. Индекс рассчитан скриптом analyze.py.']];
cursor+=2;section(sources,cursor,'Ссылки источников');
audit.sources.forEach((x,i)=>{sources.getRange(`A${cursor+2+i}:B${cursor+2+i}`).values=[[x.id,x.url||'—']];});
cursor+=audit.sources.length+4;section(sources,cursor,'Привязка каждого значения к источнику');
sources.getRange(`A${cursor+2}:E${cursor+2}`).values=[['Ozon SKU','Показатель','source_id','Значение','Охват / причина']];header(sources,`A${cursor+2}:E${cursor+2}`);
let row=cursor+3;
for(const r of comp.rows)for(const obs of [r.own,...r.competitors]){
 const definition=[obs.basis,JSON.stringify(obs.period),obs.scope,obs.region,obs.query_set?.join(', '),obs.reason].filter(Boolean).join(' · ');
 sources.getRange(`A${row}:E${row}`).values=[[String(obs.sku),r.label,obs.source_id||'—',cell(obs.value),definition||'Нет наблюдения']];body(sources,`A${row}:E${row}`,54,row%2?p.paper:p.stripe);row++;
}
sources.getRange(`A${cursor+3}:E${row-1}`).format.autofitRows();
sources.freezePanes.freezeRows(5);
wb.recalculate();
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#NULL!',options:{useRegex:true,maxResults:30},summary:'formula errors'})).ndjson);
if(opts['preview-dir']){
 await fs.mkdir(opts['preview-dir'],{recursive:true});
 for(const [sheet,range,name] of [['Сравнение',`A1:${areaEnd}43`,'comparison'],['Что проверить','A1:D15','actions'],['Обложки',`A1:${coverEnd}32`,'covers'],['Источники',`A1:E${Math.min(24,5+audit.sources.length)}`,'sources'],['Источники',`A${limitsStart}:E${rules+21}`,'methodology']]){
  const img=await wb.render({sheetName:sheet,range,scale:1.1,format:'png'});await fs.writeFile(path.join(opts['preview-dir'],name+'.png'),new Uint8Array(await img.arrayBuffer()));
 }
}
await fs.mkdir(path.dirname(path.resolve(opts.output)),{recursive:true});
const file=await SpreadsheetFile.exportXlsx(wb);await file.save(opts.output);
console.log(JSON.stringify({xlsx:path.resolve(opts.output),theme:theme.id,sku:String(own.sku),peers:peers.length}));
