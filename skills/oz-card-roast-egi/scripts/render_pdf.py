#!/usr/bin/env python3
"""Offline PDF renderer with packaged fonts and a fixed portable visual theme."""
import argparse
from datetime import date, datetime
from html import escape
import json
import math
from pathlib import Path
import random
import sys
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from analyze import analyze, private_funnel

SKILL = Path(__file__).resolve().parents[1]
THEME = json.loads((SKILL / 'assets/report-theme.json').read_text(encoding='utf-8'))
P = THEME['palette']
INK, PAPER, WHITE = P['ink'], P['paper'], P['white']
SKY, PINK, LIME, MUTED = P['sky'], P['pink'], P['lime'], P['muted']
W, H = A4


def register_fonts():
    for role, alias in [('display', 'Heavy'), ('body', 'Body'), ('bold', 'Bold'), ('hand', 'Hand')]:
        font = SKILL / 'assets' / THEME['fonts'][role]['file']
        if not font.is_file():
            raise ValueError('Не хватает шрифта из пакета: ' + str(font))
        pdfmetrics.registerFont(TTFont(alias, str(font)))
    pdfmetrics.registerFontFamily('Body', normal='Body', bold='Bold', italic='Body', boldItalic='Bold')


def fill(c):
    cv.setFillColor(colors.HexColor(c))


def rect(x, y, w, h, c, stroke=None):
    fill(c)
    if stroke:
        cv.setStrokeColor(colors.HexColor(stroke))
        cv.setLineWidth(.55)
    cv.rect(x, H-y-h, w, h, fill=1, stroke=bool(stroke))


def text(t, x, y, size=10, font='Body', color=INK, width=None):
    if width:
        natural = pdfmetrics.stringWidth(t, font, size)
        if natural > width:
            size *= width / natural
    fill(color)
    cv.setFont(font, size)
    cv.drawString(x, H-y-size*.84, t)


def para(t, x, y, width, size=9.5, leading=13, color=INK, font='Body'):
    p = Paragraph(t, ParagraphStyle('p', fontName=font, fontSize=size,
                  leading=leading, textColor=colors.HexColor(color)))
    _, height = p.wrap(width, 1000)
    p.drawOn(cv, x, H-y-height)
    return height


def line(x1, y1, x2, y2, color=INK, weight=.65):
    cv.setStrokeColor(colors.HexColor(color))
    cv.setLineWidth(weight)
    cv.line(x1, H-y1, x2, H-y2)


def scribble_oval(x, y, w, h, color=LIME, weight=4, angle=0):
    cv.saveState()
    cv.translate(x+w/2, H-y-h/2)
    cv.rotate(angle)
    cv.setStrokeColor(colors.HexColor(color))
    cv.setLineWidth(weight)
    for delta in [0, 2.5]:
        p = cv.beginPath()
        p.moveTo(-w*.5, 0)
        p.curveTo(-w*.48, h*.53+delta, w*.40, h*.58, w*.50, h*.02)
        p.curveTo(w*.52, -h*.49, -w*.37, -h*.64+delta, -w*.50, -h*.03)
        cv.drawPath(p)
    cv.restoreState()


def arrow(x1, y1, x2, y2, bend=18):
    cv.setStrokeColor(colors.HexColor(INK))
    cv.setLineWidth(1.6)
    p = cv.beginPath()
    p.moveTo(x1, H-y1)
    p.curveTo(x1+(x2-x1)*.25, H-y1-bend,
              x1+(x2-x1)*.75, H-y2-bend, x2, H-y2)
    cv.drawPath(p)
    line(x2, y2, x2-10, y2-2, weight=1.6)
    line(x2, y2, x2-5, y2+8, weight=1.6)


def star(x, y, radius=12):
    p = cv.beginPath()
    for i in range(10):
        a = math.pi/2 + i*math.pi/5
        r = radius if i % 2 == 0 else radius*.40
        px, py = x+r*math.cos(a), H-y+r*math.sin(a)
        if i == 0:
            p.moveTo(px, py)
        else:
            p.lineTo(px, py)
    p.close()
    cv.setStrokeColor(colors.HexColor(INK))
    cv.setLineWidth(1.4)
    cv.drawPath(p)


def tape(x, y, w=66, angle=-5):
    cv.saveState()
    cv.translate(x, H-y)
    cv.rotate(angle)
    cv.setFillColor(colors.HexColor('#E6DFC7'))
    cv.rect(-w/2, -9, w, 18, fill=1, stroke=0)
    cv.setStrokeColor(colors.HexColor('#D4CDB8'))
    cv.setLineWidth(.25)
    for j in range(9):
        cv.line(-w/2+j*w/8, -9, -w/2+j*w/8+3, 9)
    cv.restoreState()


def image_card(path, x, y, w, h, angle=0):
    cv.saveState()
    cv.translate(x+w/2, H-y-h/2)
    cv.rotate(angle)
    cv.setFillColor(colors.HexColor('#D7D0C6'))
    cv.rect(-w/2+3, -h/2-4, w, h, fill=1, stroke=0)
    cv.setFillColor(colors.HexColor(WHITE))
    cv.rect(-w/2, -h/2, w, h, fill=1, stroke=0)
    cv.drawImage(str(path), -w/2+8, -h/2+21, width=w-16, height=h-33,
                 preserveAspectRatio=True, anchor='c', mask='auto')
    cv.restoreState()


def base(page, label):
    rect(0, 0, W, H, PAPER)
    rng = random.Random(27+page)
    for _ in range(1100):
        fill(rng.choice(['#E8E2D9', '#F7F2EA', '#ECE6DD']))
        cv.circle(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(.12, .35), fill=1, stroke=0)
    text('OZON / CARD STUDY', 30, 25, 10, 'Bold')
    text(label, 227, 26, 8, width=280)
    text(f'{page:02d} / {TOTAL:02d}', W-72, 26, 8, 'Bold')
    line(30, 48, W-30, 48, weight=.8)
    line(30, H-39, W-30, H-39, weight=.6)
    text(FOOTER, 30, H-28, 7.5, width=355)
    text('OZON SELLER + MPSTATS', W-177, H-28, 7.2)


def number(value, decimals=0):
    if value is None:
        return '—'
    return f'{value:,.{decimals}f}'.replace(',', ' ').replace('.', ',')


def safe(value):
    return escape(str(value)).replace('\n', '<br/>')


def measured(value, width, size=9.5, leading=12.3):
    p = Paragraph(value, ParagraphStyle('measure', fontName='Body', fontSize=size, leading=leading))
    return p.wrap(width, 2000)[1]


def bounded_para(value, x, y, width, max_height, size=9.5, leading=13):
    h = measured(value, width, size, leading)
    if h > max_height:
        raise ValueError(f'Текст не помещается в блок {width:.0f}×{max_height}: '
                         'сократи повторы в audit.report, сохранив существенные ограничения')
    return para(value, x, y, width, size, leading)


def cover_path(product, run_dir):
    value = product.get('cover_path')
    if not value:
        return None
    path = Path(value)
    path = path if path.is_absolute() else run_dir / path
    if not path.is_file():
        raise ValueError('Обложка не найдена: ' + str(path))
    return path


def check_groups(findings):
    groups, current, used = [], [], 0
    labels = [('fact', 'Факт'), ('hypothesis', 'Гипотеза'), ('action', 'Действие'), ('verification', 'Проверка')]
    for i, finding in enumerate(findings):
        blocks = ['<b>'+label+'.</b> '+safe(finding[key]) for key, label in labels]
        height = 34 + sum(measured(t, 449)+6 for t in blocks)
        if height > 530:
            raise ValueError('Одно наблюдение слишком длинное для страницы: сократи повторы в findings')
        if current and used+height+16 > 535:
            groups.append(current)
            current, used = [], 0
        current.append((i, finding, blocks, height))
        used += height+16
    if current or not groups:
        groups.append(current)
    return groups


def overview(audit, comp, own, f, run_dir):
    score, meta, report = comp['score'], audit['meta'], audit.get('report', {})
    base(1, 'СНИМОК КАРТОЧКИ / '+str(meta.get('region', 'РЕГИОН НЕ ЗАДАН')).upper())
    rect(327, 64, W-327, 389, SKY)
    for yy, delta in [(64, 4), (127, -3), (193, 5), (260, -2), (327, 4), (389, -3)]:
        rect(323+delta, yy, 6-delta, 64, PAPER)
    for value, y, size, width in [('КАРТОЧКА', 73, 65, 292), ('ПОД', 141, 100, 287), ('ЛУПОЙ', 237, 100, 298)]:
        text(value, 30, y, size, 'Heavy', width=width)
    rect(31, 344, 272, 26, LIME)
    text(own.get('brand') or 'НАШ ТОВАР', 38, 349, 16, 'Heavy', width=255)
    bounded_para(safe(own.get('name') or '')+'<br/>'+safe(meta['cabinet']), 31, 381, 277, 40, 9.5, 12.5)
    start, end = date.fromisoformat(meta['period_start']), date.fromisoformat(meta['period_end'])
    text(start.strftime('%d.%m')+'-'+end.strftime('%d.%m.%Y')+f' / {(end-start).days+1} дней', 31, 429, 8.6)
    text(number(score['value'])+'/100', 375, 75, 41, 'Heavy', width=165)
    scribble_oval(360, 69, 169, 52, weight=3, angle=5)
    text('частичный индекс' if score['partial'] else 'структурный индекс', 381, 124, 14, 'Hand', width=177)
    image = cover_path(own, run_dir)
    if image:
        image_card(image, 355, 158, 199, 267, angle=-4)
        tape(458, 159, 78, angle=5)
    else:
        rect(355, 165, 199, 255, WHITE)
        para('Обложка недоступна.<br/>Визуальная оценка не выполнена.', 374, 269, 165, 10, 14)
    star(554, 137, 14)
    text(f"{score['counted_metrics']} из {score['possible_metrics']} метрик / ключевые: {score['counted_key_metrics']} из 4", 345, 436, 7.8)
    text(number(f.get('orders')), 30, 475, 59, 'Heavy', width=218)
    text(number(f.get('order_value')), 274, 475, 59, 'Heavy', width=285)
    text('заказано, шт. / Ozon Seller', 31, 539, 10, 'Bold')
    text('руб. сумма заказов по Ozon Seller', 275, 539, 10, 'Bold', width=285)
    line(30, 566, W-30, 566)
    rect(30, 583, W-60, 103, PINK)
    labels = f.get('labels', {})
    metrics = [(number(f.get('views')), labels.get('views', 'показы')), (number(f.get('clicks')), labels.get('clicks', 'переходы')),
               (number(f.get('carts')), labels.get('carts', 'в корзину')),
               (number(f['ctr']*100, 1)+'%' if f.get('ctr') is not None else '—', labels.get('ctr', 'CTR')),
               (number(f['cart_to_order']*100, 1)+'%' if f.get('cart_to_order') is not None else '—', 'корзина > заказ')]
    col = (W-60)/5
    for i, (v, label) in enumerate(metrics):
        x = 40+i*col
        text(v, x, 609, 29, 'Heavy', width=col-17)
        text(label, x, 650, 8.4, width=col-15)
        if i:
            line(x-10, 600, x-10, 670, '#C27C92', .45)
    rect(30, 712, 409, 8, LIME)
    text(report.get('takeaway', 'ОТ ФАКТА К ПРОВЕРКЕ.'), 30, 701, 28, 'Heavy', width=470)
    bounded_para(safe(report.get('summary', 'Наблюдения и проверяемые действия - на следующих страницах. '
                    'Индекс описывает признаки карточки; причины продаж он не устанавливает.')),
                 31, 742, 465, 43, 10, 14)
    arrow(503, 741, 558, 759, bend=-13)
    cv.showPage()


def actions_page(group, page, comp):
    base(page, 'ПЛАН ПРОВЕРОК')
    rect(348, 69, 247, 142, SKY)
    text('ТРИ' if len(comp['findings']) == 3 else 'ПЛАН', 28, 67, 103, 'Heavy', width=305)
    text('ПРОВЕРКИ', 28, 164, 58, 'Heavy', width=526)
    text('факты > гипотезы > тест', 365, 103, 16, 'Hand', width=201)
    star(531, 162, 20)
    y = 235
    titles = {'search_position': 'ПОВТОРИТЬ ПОИСК', 'characteristics_count': 'РАСКРЫТЬ ХАРАКТЕРИСТИКИ', 'infographic': 'ПРОВЕРИТЬ ИДЕЮ ОБЛОЖКИ'}
    if not group:
        para('Подтверждённых проблем для рекомендации пока недостаточно. '
             'Пробелы данных перечислены в Excel; действия не выдумывались.', 31, 270, 510, 11, 16)
    for index, finding, blocks, height in group:
        accent = [SKY, PINK, LIME][index % 3]
        rect(30, y, 69, height, accent)
        text(f'{index+1:02d}', 38, y+12, 59, 'Heavy', width=52)
        title = finding.get('title') or titles.get(finding['metric_id']) or next((r['label'] for r in comp['rows'] if r['metric_id'] == finding['metric_id']), 'УТОЧНИТЬ СОДЕРЖАНИЕ')
        text(title.upper(), 114, y+2, 26, 'Heavy', width=449)
        pos = y+34
        for block in blocks:
            pos += para(block, 114, pos, 449, 9.5, 12.3)+6
        y += height+16
    cv.showPage()


def method_panel(audit, comp, f, y=605, full_page=False):
    score = comp['score']
    report = audit.get('report', {})
    text('КАК ЧИТАТЬ '+number(score['value'])+'/100', 30, y, 27, 'Heavy', width=260)
    numerator, denominator = score['passed_weight'], score['counted_weight']
    rule = f"<b>{number(score['value'])} = округление {numerator} / {denominator} × 100.</b>" if denominator else '<b>Индекс не рассчитан: нет сопоставимых показателей.</b>'
    summary = rule + f" Учтены {score['counted_metrics']} из 14 показателей, ключевых - {score['counted_key_metrics']} из 4. Это структурное сравнение; причины продаж оно не доказывает."
    h = para(summary, 31, y+40, 252, 9.1, 12.2)
    note = report.get('method_note', f"Сопоставимых кандидатов: {score['competitor_count']}. Полный подбор, определения и ограничения показаны на листе «Источники» в Excel.")
    bounded_para(safe(note), 31, y+50+h, 252, 128-h, 9, 12)
    rect(306, y, W-336, 178, SKY)
    external = next(r for r in comp['rows'] if r['metric_id'] == 'sales')['own']['value']
    heading = number(f.get('orders'))+' / '+number(external)
    text(heading, 320, y+12, 40, 'Heavy', width=226)
    fallback = 'Слева - заказы Ozon Seller, справа - внешнее наблюдение MPStats. Их определения и охват могут различаться. Источники и причины исключения из индекса указаны в Excel.'
    bounded_para(safe(report.get('source_note', fallback)), 320, y+65, W-364, 88, 9.1, 12.5)
    text('Ozon Seller / MPStats / снимок данных', 320, y+158, 7.8, width=230)


def covers_page(audit, comp, f, products, run_dir, page, with_method):
    base(page, 'ОБЛОЖКИ / МЕТОД / ИСТОЧНИКИ')
    text('КТО РЯДОМ?', 29, 72, 65, 'Heavy', width=495)
    scribble_oval(271, 115, 188, 13, color=LIME, weight=4, angle=3)
    para(f"Предварительных аналогов: {comp['score']['competitor_count']}. Сравнивались первые обложки. "
         'Различия упаковок и назначения учитываются в подборе.', 31, 153, 520, 9.5, 13)
    count = len(products)
    cols = max(count, 1) if count <= 4 else 3
    gap = 9
    cw = (W-60-(cols-1)*gap)/cols
    ch = 288 if count <= 4 else 245
    image_h = 154 if count <= 4 else 110
    for i, product in enumerate(products):
        x, top = 30+(i % cols)*(cw+gap), 200+(i//cols)*(ch+15)
        rect(x+2, top+3, cw, ch, '#DDD5C9')
        rect(x, top, cw, ch, WHITE, '#C2BBAF')
        rect(x, top, cw, 5, [PINK, SKY, SKY, LIME][i % 4])
        text(product.get('brand') or 'ТОВАР', x+7, top+14, 16, 'Heavy', width=cw-14)
        text(str(product['sku'])+(' / мы' if product['role'] == 'own' else ''), x+7, top+35, 8.4, width=cw-14)
        image = cover_path(product, run_dir)
        if image:
            cv.drawImage(str(image), x+6, H-top-56-image_h,
                         width=cw-12, height=image_h, preserveAspectRatio=True, anchor='c', mask='auto')
        else:
            para('Нет обложки.<br/>Визуальная проверка недоступна.', x+8, top+85, cw-16, 9, 12)
        text(product['seller'], x+7, top+ch-66, 8.3, width=cw-14)
        price = product.get('metrics', {}).get('price', {}).get('value')
        text(number(price)+' руб.', x+7, top+ch-54, 22, 'Heavy', width=cw-14)
        caption = product['variant']
        text(caption, x+7, top+ch-21, 8.3, width=cw-14)
    if with_method:
        rect(30, 510, W-60, 55, PINK)
        text('СРАВНИВАЕМ ФАКТЫ', 42, 527, 23, 'Heavy', width=192)
        para('Признаки обложки показывают различия. Их влияние на CTR и заказы '
             'проверяется отдельным тестом.', 248, 522, 304, 9.4, 12.8)
        arrow(61, 498, 518, 498, bend=-9)
        line(30, 587, W-30, 587)
        method_panel(audit, comp, f)
    cv.showPage()


def render(input_path, output_path):
    global cv, TOTAL, FOOTER
    audit = json.loads(input_path.read_text(encoding='utf-8'))
    comp = analyze(audit)
    register_fonts()
    f = private_funnel(audit)
    own = next(p for p in audit['products'] if p['role'] == 'own')
    products = [own]+[p for p in audit['products'] if p['role'] != 'own']
    groups = check_groups(comp['findings'])
    with_method = len(products) <= 4
    TOTAL = 2+len(groups)+(0 if with_method else 1)
    meta = audit['meta']
    stamp = datetime.fromisoformat(meta['collected_at']).strftime('%d.%m.%Y')
    FOOTER = str(meta['own_sku'])+' / '+str(own.get('brand', 'Ozon'))+' / '+stamp
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv = canvas.Canvas(str(output_path), pagesize=A4, pageCompression=1, invariant=1)
    cv.setTitle('Аудит карточки Ozon '+str(meta['own_sku']))
    cv.setAuthor('Ozon Seller / MPStats')
    overview(audit, comp, own, f, input_path.parent)
    for i, group in enumerate(groups):
        actions_page(group, i+2, comp)
    covers_page(audit, comp, f, products, input_path.parent, len(groups)+2, with_method)
    if not with_method:
        base(TOTAL, 'МЕТОД / ИСТОЧНИКИ')
        text('ПРОВЕРЯЕМ ДАННЫЕ', 30, 76, 56, 'Heavy', width=W-60)
        method_panel(audit, comp, f, 188)
        para('Подробные определения, локаторы источников, ограничения и исключённые показатели - в Excel. '
             'Оценка относится только к указанным SKU, периоду и выборке.', 31, 405, W-62, 11, 16)
        cv.showPage()
    cv.save()
    return {'pdf': str(output_path.resolve()), 'pages': TOTAL, 'theme': THEME['id'], 'sku': str(meta['own_sku'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error('Нельзя перезаписывать audit.json')
    try:
        print(json.dumps(render(args.input, args.output), ensure_ascii=False))
    except (ValueError, KeyError, OSError) as error:
        print('Ошибка отчёта: '+str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())


