"""Standalone HTML snapshot in the inherited paper-sky-pink-lime theme."""
import base64
from datetime import datetime, timedelta, timezone
from html import escape
import io
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import ledger


def text(value):
    return escape(str(value), quote=True)


def num(value):
    return '—' if value is None else f'{value:,.0f}'.replace(',', ' ')


def pct(value):
    return '—' if value is None else f'{value:.2f}%'.replace('.', ',')


def table(headers, rows):
    head = ''.join('<th>' + text(value) + '</th>' for value in headers)
    body = ''.join('<tr>' + ''.join('<td class="wrap">' + text(value) + '</td>' for value in row) + '</tr>' for row in rows)
    return '<table><thead><tr>' + head + '</tr></thead><tbody>' + (body or '<tr><td class="empty" colspan="' + str(len(headers)) + '">Нет завершённых данных</td></tr>') + '</tbody></table>'


def thumbnail(root, variant):
    from PIL import Image
    path = (root / variant['file']).resolve()
    if root.resolve() not in path.parents:
        raise ValueError('Изображение находится вне папки теста')
    with Image.open(path) as image:
        image = image.convert('RGB')
        image.thumbnail((600, 800))
        stream = io.BytesIO()
        image.save(stream, 'JPEG', quality=85)
    return 'data:image/jpeg;base64,' + base64.b64encode(stream.getvalue()).decode('ascii')


def render(root, state):
    root = Path(root)
    assets = Path(__file__).resolve().parent.parent / 'assets'
    theme = json.loads((assets / 'report-theme.json').read_text())
    css = [':root{' + ';'.join('--' + k + ':' + v for k, v in theme['palette'].items()) + '}']
    for role, font in theme['fonts'].items():
        encoded = base64.b64encode((assets / font['file']).read_bytes()).decode('ascii')
        weight = 900 if role == 'display' else 700 if role in ('bold', 'hand') else 400
        css.append('@font-face{font-family:' + json.dumps(font['family']) + ';font-weight:' + str(weight) + ';src:url(data:font/ttf;base64,' + encoded + ') format("truetype")}')
    summaries = {phase: ledger.summary(state, phase) for phase in ('exploration', 'confirmation')}
    values = summaries['exploration']
    leader = state.get('leader')
    images = {key: thumbnail(root, variant) for key, variant in state['variants'].items()}
    leader_variant = state['variants'].get(leader)
    leader_values = values.get(leader, {}).get('sources', {}).get('funnel', {})
    status = {'prepared': 'Подготовка', 'running': 'Сбор данных', 'awaiting_cover': 'Проверка публикации',
              'paused_attention': 'Нужна проверка', 'finished': 'Завершено'}.get(state['status'], state['status'])
    message = '; '.join(state.get('attention', [])) or (state.get('result') or {}).get('reason') or 'Нормативы ещё не подтверждены'
    cards = []
    for key, variant in state['variants'].items():
        source = values.get(key, {}).get('sources', {})
        ads = pct(source.get('ads', {}).get('ctr')) if state['config']['use_ad_ctr'] else 'не учитывается'
        cards.append('<article class="variant' + (' leader' if key == leader else '') + '"><button class="photo" type="button"><img alt="' + text(variant['label']) + '" src="' + images[key] + '"></button><div class="body"><div class="headline"><strong>' + text(key) + '</strong><span>' + text(variant['label']) + '</span></div><p>' + text(variant['hypothesis']) + '</p><div class="kpi-pair"><span>Воронка<br><b>' + pct(source.get('funnel', {}).get('ctr')) + '</b></span><span>Реклама<br><b>' + text(ads) + '</b></span></div><span class="variant-tag">' + num(source.get('funnel', {}).get('views')) + ' показов / база воронки</span></div></article>')
    result_rows = []
    for phase, summary in summaries.items():
        for key, entry in summary.items():
            f = entry['sources']['funnel']
            a = entry['sources'].get('ads', {})
            result_rows.append(['Подтверждение' if phase == 'confirmation' else 'Сравнение', key, num(f['views']), num(f['clicks']), pct(f['ctr']),
                                num(a.get('views')) if state['config']['use_ad_ctr'] else 'выкл.', pct(a.get('ctr')) if state['config']['use_ad_ctr'] else 'выкл.',
                                'Выполнены' if entry['meets_targets'] else 'Не выполнены'])
    definitions = []
    for source in ledger.sources(state):
        c = state['binding']['sources'][source]
        definitions.append(('Воронка' if source == 'funnel' else 'Реклама') + ': ' + c['metric_name'] + '; ' + c['numerator_label'] + ' / ' + c['denominator_label'] + '; ' + c['traffic_scope'])
    current = 'Нет открытого интервала'
    if state.get('current'):
        from workflow import calculation
        opened = state['current']
        zone = ZoneInfo(state['binding']['timezone'])
        started = ledger.timestamp(opened['started_at']).astimezone(zone)
        prefix = 'На карточке ' + opened['variant'] + '. Начало ' + started.strftime('%d.%m.%Y %H:%M') + '. '
        try:
            calc, _, _ = calculation(state)
            f = calc['sources']['funnel']
            current = state['current']['variant'] + ': ' + num(f['views']) + ' показов / база; CTR ' + pct(f['ctr'])
            if calc['missing']:
                current += '. Нужны дневные итоги: ' + ', '.join(item['source'] + ' ' + item['date'] for item in calc['missing'])
            if calc['empty']:
                current += '. Пока нет полного пригодного дня'
        except ValueError as exc:
            first_day = started.date() + timedelta(days=1)
            if state['config']['mode'] == 'whole_days' and datetime.now(zone).date() <= first_day:
                current = prefix + 'Первый полный день учёта ' + first_day.strftime('%d.%m.%Y') + '; итог за него можно прочитать с ' + (first_day + timedelta(days=1)).strftime('%d.%m.%Y') + '. Статистика пока не накоплена.'
            else:
                current = prefix + str(exc)
    day_rows = []
    for source in ledger.sources(state):
        for day, row in sorted(state['days'].get(source, {}).items()):
            day_rows.append(['Воронка' if source == 'funnel' else 'Реклама', day, num(row['views']), num(row['clicks']), 'Завершённый' if row['settled'] else 'Промежуточный', row['observation_id']])
        for period, row in sorted(state.get('periods', {}).get(source, {}).items()):
            day_rows.append(['Воронка' if source == 'funnel' else 'Реклама', period, num(row['views']), num(row['clicks']), 'Завершённый период' if row['settled'] else 'Промежуточный период', row['observation_id']])
    c = state['config']
    units_note = ('Суммы дневных уникальных — взвешенные дневные показатели; не уникальные люди за весь тест.'
                  if any(state['binding']['sources'][s]['unit'] == 'daily_unique' for s in ledger.sources(state)) else 'База — аддитивные события в зафиксированном охвате источников.')
    if any(state['binding']['sources'][s]['unit'] == 'period_unique' for s in ledger.sources(state)):
        units_note = 'В каждом интервале — уникальные посетители за его полный период, без сложения дневных уникальных. Итог повторных интервалов — взвешенное сравнение блоков, а не уникальные люди всего теста.'
    quality = 'Внутридневная атрибуция приблизительная по моментам чтения.' if c['mode'] == 'intraday_counts' else 'День начала/смены исключается; учитываются завершённые полные дни.'
    conditions = state.get('last_conditions', state['conditions'])
    replacements = {
        'STATUS': text(status), 'TITLE': text(state['title']),
        'CONTEXT': text('SKU ' + state['binding']['sku'] + ' · ' + state['binding']['seller'] + ' · блок условий ' + str(state['epoch'])),
        'LEADER_CTR': pct(leader_values.get('ctr')), 'LEADER_LABEL': text(leader or 'лидер не определён'),
        'LEADER_IMAGE': '<img alt="Обложка лидера" src="' + images[leader] + '">' if leader_variant else '<span class="no-cover">Лидер появится после сравнения</span>',
        'LEADER_NOTE': text('Итоговый результат' if state['status'] == 'finished' else 'Предварительные результаты'),
        'MESSAGE': text(message),
        'STATS': ''.join('<div class="stat"><span class="label">' + text(label) + '</span><b class="value">' + text(value) + '</b><span class="mini">' + text(note) + '</span></div>' for label, value, note in [
            ('Цель воронки', pct(c['target_funnel_ctr']), 'Норматив пользователя'),
            ('Цель рекламы', pct(c.get('target_ad_ctr')) if c['use_ad_ctr'] else 'Выкл.', 'Отдельный критерий'),
            ('Показы на интервал', num(c['views_per_interval']), 'Минимум, не точка мгновенной смены'),
            ('Закрыто интервалов', str(sum(not x.get('excluded') for x in state['intervals'])), quality)]),
        'VARIANTS': ''.join(cards), 'DEFINITIONS': text(' | '.join(definitions)),
        'RESULTS': table(['Этап', 'Фото', 'База воронки', 'Переходы', 'CTR воронки', 'Показы рекламы', 'CTR рекламы', 'Нормативы'], result_rows),
        'BASIS_NOTE': text(units_note), 'CURRENT': text(current),
        'CONDITIONS': text('Цена: ' + str(conditions['price']) + ' ' + conditions['currency'] + ' · ' + conditions['region'] + ' · ' + conditions['payment'] + ' · ' + conditions['promotion'] + ' · ' + conditions['delivery']),
        'CONFIG': table(['Параметр', 'Значение'], [['Режим', 'Полные завершённые дни' if c['mode'] == 'whole_days' else 'Счётчики внутри дня'], ['Минимум часов', c['min_hours']], ['Предел часов', c['max_interval_hours']], ['Круги', c['cycles']], ['Дополнительная проверка', f'×{c["confirmation_multiplier"]}' if c.get('confirmation_multiplier') else '—'], ['Допуск цены, %', c['price_tolerance_pct']]]),
        'DAYS': table(['Источник', 'Дата', 'Показы / база', 'Переходы', 'Статус', 'Наблюдение'], day_rows),
        'LOG': ''.join('<li><time>' + text(item['at']) + '</time><span>' + text(item['message']) + '</span></li>' for item in reversed(state['log'])),
        'TEST_ID': text(state['test_id']), 'UPDATED': text(datetime.now(timezone.utc).isoformat(timespec='seconds')),
        'GENERATIONS': text(str(len(state['generations'])) + ' / ' + str(c['max_generations']) + ' попыток'), 'QUALITY': text(quality),
    }
    document = (assets / 'dashboard.html').read_text().replace('/*REPORT_THEME*/', '\n'.join(css))
    for key, value in replacements.items():
        document = document.replace('{{' + key + '}}', value)
    path = root / 'dashboard.html'
    temporary = root / '.dashboard.html.tmp'
    temporary.write_text(document, encoding='utf-8')
    temporary.replace(path)
    return path
