"""Daily counters for one Ozon SKU. Local calculations only; no network access."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import math


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('Время должно содержать часовой пояс')
    return result


def number(value, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError('Нужно точное неотрицательное число, без сокращений')
    if integer and value != int(value):
        raise ValueError('Счётчики должны быть целыми числами')
    return value


def sources(state):
    return ['funnel', 'ads'] if state['config']['use_ad_ctr'] else ['funnel']


def validate_row(state, row):
    source = row['source']
    if source not in sources(state):
        raise ValueError('Источник не включён в этот тест')
    contract = state['binding']['sources'][source]
    if row['definition_id'] != contract['definition_id'] or row['scope_id'] != contract['scope_id']:
        raise ValueError('Изменилось определение метрики или охват источника')
    local = timestamp(row['captured_at']).astimezone(ZoneInfo(state['binding']['timezone']))
    day = date.fromisoformat(row['date'])
    if day > local.date() or type(row.get('settled')) is not bool:
        raise ValueError('Неверная дата или признак завершённого дня')
    if row['settled'] and day >= local.date():
        raise ValueError('Текущий день нельзя объявлять завершённым')
    if contract['unit'] == 'period_unique':
        first = date.fromisoformat(row['period_start'])
        if first > day or state['config']['mode'] != 'whole_days':
            raise ValueError('Уникальные за период требуют полного календарного периода')
    number(row['views'], True)
    number(row['clicks'], True)
    if row['clicks'] > row['views']:
        raise ValueError('Числитель больше знаменателя: перепроверьте пару метрик')
    if not row.get('evidence') or not row.get('url'):
        raise ValueError('Нужны фактический URL и сохранённый первичный источник')


def put(state, row):
    """Upsert a day; zero on a different date is normal, never a negative delta."""
    validate_row(state, row)
    period_unique = state['binding']['sources'][row['source']]['unit'] == 'period_unique'
    bucket = state.setdefault('periods', {}) if period_unique else state['days']
    days = bucket.setdefault(row['source'], {})
    key = row['period_start'] + '..' + row['date'] if period_unique else row['date']
    previous = days.get(key)
    changed = False
    if previous:
        if timestamp(row['captured_at']) < timestamp(previous['captured_at']):
            raise ValueError('Новый снимок старше уже сохранённого')
        different = any(row[k] != previous[k] for k in ('views', 'clicks'))
        if timestamp(row['captured_at']) == timestamp(previous['captured_at']) and different:
            raise ValueError('Одинаковое время снимка с разными значениями')
        if not previous['settled'] and not row['settled']:
            if row['views'] < previous['views'] or row['clicks'] < previous['clicks']:
                raise ValueError('Счётчик уменьшился внутри одного дня; нужна сверка источника')
        if previous['settled'] and not row['settled']:
            raise ValueError('Нельзя заменить завершённый день текущим снимком')
        changed = different and previous['settled']
    days[key] = row
    return changed


def totals(state, interval, end_at, end_counts=None):
    zone = ZoneInfo(state['binding']['timezone'])
    start = timestamp(interval['started_at']).astimezone(zone)
    end = timestamp(end_at).astimezone(zone)
    if end < start:
        raise ValueError('Конец интервала раньше начала')
    mode = state['config']['mode']
    first = start.date() + timedelta(days=1) if mode == 'whole_days' else start.date()
    last = end.date() - timedelta(days=1) if mode == 'whole_days' else end.date()
    result, missing = {}, []
    for source in sources(state):
        views = clicks = 0
        used = []
        if state['binding']['sources'][source]['unit'] == 'period_unique':
            key = first.isoformat() + '..' + last.isoformat()
            row = state.get('periods', {}).get(source, {}).get(key)
            if first <= last:
                if not row or not row['settled']:
                    missing.append({'source': source, 'date': key, 'reason': 'Нужен точный итог уникальных за весь этот период; дневные значения не суммировать'})
                else:
                    views, clicks = row['views'], row['clicks']
                    used = [{'date': key, 'observation_id': row['observation_id'], 'views': views, 'clicks': clicks}]
            result[source] = {'views': views, 'clicks': clicks, 'ctr': 100 * clicks / views if views else None,
                              'days': used, 'unit': 'period_unique'}
            continue
        day = first
        while day <= last:
            key = day.isoformat()
            row = (end_counts or {}).get(source) if mode != 'whole_days' and day == end.date() else state['days'].get(source, {}).get(key)
            if not row or row['date'] != key or (day < end.date() and not row['settled']):
                missing.append({'source': source, 'date': key, 'reason': 'Нужен итог завершённого дня' if day < end.date() else 'Нужен свежий дневной снимок'})
                day += timedelta(days=1)
                continue
            before = interval['baseline'][source] if mode != 'whole_days' and day == start.date() else {'views': 0, 'clicks': 0}
            dv, dc = row['views'] - before['views'], row['clicks'] - before['clicks']
            if dv < 0 or dc < 0 or dc > dv:
                raise ValueError('Несопоставимые границы интервала или коррекция статистики')
            views += dv
            clicks += dc
            used.append({'date': key, 'observation_id': row['observation_id'], 'views': dv, 'clicks': dc})
            day += timedelta(days=1)
        result[source] = {'views': views, 'clicks': clicks, 'ctr': 100 * clicks / views if views else None, 'days': used,
                          'unit': state['binding']['sources'][source]['unit']}
    return {'sources': result, 'missing': missing, 'empty': first > last}


def ready(state, interval, calculated, end_at):
    hours = (timestamp(end_at) - timestamp(interval['started_at'])).total_seconds() / 3600
    multiplier = state['config']['confirmation_multiplier'] if interval['phase'] == 'confirmation' else 1
    requirements = {'funnel': state['config']['views_per_interval'] * multiplier}
    if state['config']['use_ad_ctr']:
        requirements['ads'] = state['config']['ad_views_per_interval'] * multiplier
    return (not calculated['missing'] and not calculated['empty'] and hours >= state['config']['min_hours']
            and all(calculated['sources'][source]['views'] >= cap for source, cap in requirements.items()))


def summary(state, phase):
    result = {}
    for interval in state['intervals']:
        if interval['epoch'] != state['epoch'] or interval['phase'] != phase or interval.get('excluded'):
            continue
        calculated = totals(state, interval, interval['ended_at'], interval.get('end_counts'))
        if calculated['missing']:
            raise ValueError('В закрытом интервале пропали данные')
        dest = result.setdefault(interval['variant'], {'intervals': 0, 'sources': {}})
        dest['intervals'] += 1
        for source, values in calculated['sources'].items():
            target = dest['sources'].setdefault(source, {'views': 0, 'clicks': 0, 'unit': values['unit']})
            target['views'] += values['views']
            target['clicks'] += values['clicks']
    for values in result.values():
        for source in values['sources'].values():
            source['ctr'] = 100 * source['clicks'] / source['views'] if source['views'] else None
        values['meets_targets'] = passes(state, values)
    return result


def passes(state, values):
    if values['sources']['funnel']['ctr'] is None or values['sources']['funnel']['ctr'] < state['config']['target_funnel_ctr']:
        return False
    if state['config']['use_ad_ctr']:
        ctr = values['sources']['ads']['ctr']
        if ctr is None or ctr < state['config']['target_ad_ctr']:
            return False
    return True
