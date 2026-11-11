#!/usr/bin/env python3
"""Local Ozon cover-test state. Browser and image generation are performed by the agent."""
import argparse
import base64
import contextlib
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from uuid import uuid4
from zoneinfo import ZoneInfo

import ledger


def now():
    return datetime.now(timezone.utc)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    fd, temporary = tempfile.mkstemp(prefix='.state-', dir=Path(path).parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextlib.contextmanager
def lock(root):
    import fcntl
    with (root / '.lock').open('a+b') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError('Другой шаг уже обрабатывает этот тест') from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def log(state, message):
    state['log'].append({'at': now().isoformat(), 'message': message})


def fresh(value):
    age = (now() - ledger.timestamp(value)).total_seconds()
    if not -60 <= age <= 900:
        raise ValueError('Нужен фактический свежий снимок: не старше 15 минут')


def evidence(root, paths):
    if not paths:
        raise ValueError('Нет сохранённого первичного источника')
    result = []
    for source in paths:
        path = Path(source).expanduser().resolve()
        if not path.is_file() or not path.stat().st_size:
            raise ValueError('Первичный файл не существует или пуст')
        fingerprint = sha(path)
        name = fingerprint + path.suffix.lower()
        target = root / 'evidence' / name
        target.parent.mkdir(exist_ok=True)
        if not target.exists():
            shutil.copyfile(path, target)
        result.append({'file': str(target.relative_to(root)), 'sha256': fingerprint, 'name': path.name})
    return result


def photo(root, variant, file, label, hypothesis, source):
    if not re.fullmatch(r'[A-Z][A-Z0-9_-]{0,20}', variant):
        raise ValueError('ID варианта: A, B, C или другой короткий ID латиницей')
    path = Path(file).expanduser().resolve()
    if path.suffix.lower() not in ('.jpg', '.jpeg', '.png', '.webp') or not path.is_file():
        raise ValueError('Нужен существующий JPG/PNG/WebP')
    from PIL import Image
    with Image.open(path) as image:
        width, height = image.size
        image.verify()
    target = root / 'variants' / (variant + path.suffix.lower())
    target.parent.mkdir(exist_ok=True)
    shutil.copyfile(path, target)
    return {'id': variant, 'file': str(target.relative_to(root)), 'sha256': sha(target),
            'label': label, 'hypothesis': hypothesis, 'source': source, 'width': width, 'height': height}


def binding_matches(state, observed):
    for key in ('seller', 'sku', 'timezone'):
        if observed.get(key) != state['binding'][key]:
            raise ValueError('Не совпали кабинет, SKU или часовой пояс источника')


def proof(root, state, data, variant):
    binding_matches(state, data)
    fresh(data['observed_at'])
    for key in ('first_image_matches', 'other_media_unchanged', 'reopened'):
        if data.get(key) is not True:
            raise ValueError('Нужна визуальная проверка опубликованного фото и остальных медиа')
    if data.get('media_order') != state['binding'].get('media_order') or not isinstance(data.get('media_order'), list):
        raise ValueError('Не совпал сохранённый состав и порядок остальных медиа')
    expected = state['variants'][variant]['sha256']
    if data.get('variant_sha256') != expected:
        raise ValueError('Проверено другое изображение')
    if sha(root / state['variants'][variant]['file']) != expected:
        raise ValueError('Локальная обложка изменилась')
    evidence(root, data['evidence'])
    conditions = data['conditions']
    ledger.number(conditions['price'])
    if conditions['price'] <= 0 or type(conditions.get('available')) is not bool:
        raise ValueError('Нужны цена покупателя и подтверждённая доступность')
    for key in ('region', 'payment', 'currency', 'promotion', 'delivery'):
        if not isinstance(conditions.get(key), str) or not conditions[key].strip():
            raise ValueError('Заполните контекст цены, акции и доставки; неизвестное не заменять догадкой')
    return conditions


def conditions_changed(state, current):
    base = state['conditions']
    change = 100 * abs(current['price'] - base['price']) / base['price']
    reasons = ['Цена вышла за допуск'] if change > state['config']['price_tolerance_pct'] + 1e-9 else []
    for key in ('region', 'payment', 'currency', 'promotion', 'available', 'delivery'):
        if current[key] != base[key]:
            reasons.append('Изменилось условие: ' + key)
    if not current['available']:
        reasons.append('Товар недоступен')
    return reasons


def validate_config(data):
    c = data['config']
    if type(c['use_ad_ctr']) is not bool:
        raise ValueError('Пользователь должен выбрать, учитывать ли рекламный CTR')
    if c['mode'] not in ('whole_days', 'intraday_counts'):
        raise ValueError('Выберите режим whole_days или intraday_counts')
    c.setdefault('cycles', 1)
    for key in ('views_per_interval', 'cycles', 'max_interval_hours'):
        if ledger.number(c[key], True) < 1:
            raise ValueError(f'{key}: требуется положительное целое число')
    ledger.number(c.get('confirmation_multiplier', 0), True)
    for key in ('min_hours', 'price_tolerance_pct'):
        ledger.number(c[key])
    if c['min_hours'] <= 0 or c['max_interval_hours'] < c['min_hours']:
        raise ValueError('Неверные пределы длительности')
    ledger.number(c['max_generations'], True)
    for key in ['target_funnel_ctr'] + (['target_ad_ctr'] if c['use_ad_ctr'] else []):
        ledger.number(c[key])
        if not 0 < c[key] <= 100:
            raise ValueError('Норматив CTR должен быть в процентах от 0 до 100')
    if c['use_ad_ctr']:
        ledger.number(c['ad_views_per_interval'], True)
        if c['ad_views_per_interval'] < 1:
            raise ValueError('Нужен отдельный минимальный объём рекламных показов')
    if c['finish_policy'] not in ('leader', 'original'):
        raise ValueError('Задайте, какое фото оставить после теста')
    b = data['binding']
    if not b.get('seller') or not isinstance(b.get('sku'), str) or not b['sku']:
        raise ValueError('Нужны устойчивое обозначение кабинета и точный SKU строкой')
    ZoneInfo(b['timezone'])
    for source in ['funnel', 'ads'] if c['use_ad_ctr'] else ['funnel']:
        contract = b['sources'][source]
        for key in ('definition_id', 'scope_id', 'metric_name', 'numerator_label', 'denominator_label', 'traffic_scope'):
            if not contract.get(key):
                raise ValueError('Не зафиксировано определение или охват метрики')
        if contract['settled_day_report_available'] is not True:
            raise ValueError('Без доступа к итогу за прошлые дни тест с переходом через полночь не запускается')
        if contract['unit'] not in ('events', 'daily_unique', 'period_unique'):
            raise ValueError('Нужно определить, считаются события или дневные уникальные посетители')
        if contract['unit'] == 'daily_unique' and c.get('daily_unique_aggregation_accepted') is not True:
            raise ValueError('Нужно согласовать сравнение взвешенных дневных метрик; это не уникальные люди за весь тест')
        if contract['unit'] == 'period_unique' and c['mode'] != 'whole_days':
            raise ValueError('Уникальные за период считаются только по завершённым полным дням')
        if c['mode'] == 'intraday_counts':
            if contract['unit'] != 'events' or contract['granularity'] != 'intraday' or contract.get('intraday_probe_passed') is not True:
                raise ValueError('Внутридневная ротация требует аддитивных счётчиков и проверенной детализации')
            if c.get('accept_approximate_boundaries') is not True:
                raise ValueError('Нужно согласовать приблизительную атрибуцию по времени чтения счётчиков')


def initialize(root, data):
    if (root / 'state.json').exists():
        raise ValueError('Тест уже существует')
    validate_config(data)
    root.mkdir(parents=True, exist_ok=True)
    state = {'schema': 1, 'test_id': data['test_id'], 'title': data['title'], 'binding': data['binding'],
             'config': data['config'], 'consent': {'active_test': False, 'image_generation': data.get('image_generation_authorized') is True},
             'status': 'prepared', 'phase': 'exploration', 'epoch': 1, 'variants': {}, 'days': {},
             'observations': {}, 'intervals': [], 'current': None, 'pending': None, 'on_card': 'A',
             'plan': [], 'position': 0, 'log': [], 'generations': {}, 'goal_reached': False, 'result': None}
    state['variants']['A'] = photo(root, 'A', data['original'], 'Исходная обложка', 'Контрольный вариант', 'original')
    state['conditions'] = proof(root, state, data['probe']['cover'], 'A')
    if not state['conditions']['available']:
        raise ValueError('Недоступный товар нельзя запускать в тест')
    observe(root, state, data['probe'], preparation=True)
    if any(not state['days'].get(s) and not state.get('periods', {}).get(s) for s in ledger.sources(state)):
        raise ValueError('До подготовки нужен пробный источник по каждой включённой метрике')
    log(state, 'Тест подготовлен к согласованию запуска')
    return state


def request(state, variant, purpose='interval'):
    state['pending'] = {'id': uuid4().hex, 'variant': variant, 'purpose': purpose, 'begun': False}
    state['status'] = 'awaiting_cover'


def add_variant(root, state, data):
    if state['status'] != 'prepared' or data.get('approved') is not True:
        raise ValueError('Варианты добавляются после визуальной проверки до старта')
    variant = data['id']
    if variant in state['variants']:
        raise ValueError('ID варианта уже используется')
    if data['source'] == 'chatgpt_image_gen':
        job = state['generations'][data['generation_name']]
        if job['status'] != 'done' or sha(data['file']) != job['sha256']:
            raise ValueError('Нет завершённой генерации этого файла')
    elif data['source'] != 'provided':
        raise ValueError('Источник: provided или chatgpt_image_gen')
    state['variants'][variant] = photo(root, variant, data['file'], data['label'], data['hypothesis'], data['source'])
    log(state, 'Одобрен вариант ' + variant)


def start(state, data):
    if state['status'] != 'prepared' or data.get('active_test_authorized') is not True:
        raise ValueError('Нужен запрос пользователя на активный тест')
    if len(state['variants']) < 2:
        raise ValueError('Нужны исходная A и минимум один новый одобренный вариант')
    state['consent']['active_test'] = True
    variants = list(state['variants'])
    state['plan'] = []
    for cycle in range(state['config']['cycles']):
        state['plan'].extend(variants if cycle % 2 == 0 else list(reversed(variants)))
    request(state, state['plan'][0])
    log(state, 'Разрешён активный тест. Порядок обложек: ' + ' → '.join(state['plan']))


def begin_ui(root, state, data):
    p = state['pending']
    if not p or p['begun'] or state['status'] == 'paused_attention' or not state['consent']['active_test']:
        raise ValueError('Нет новой разрешённой попытки смены; сначала сверить карточку')
    if data['intent_id'] != p['id']:
        raise ValueError('Не совпал ID намерения')
    if p.get('possible_current_variants'):
        raise ValueError('Сначала reconcile: после прерванной смены фактическое фото неизвестно')
    proof(root, state, data, state['on_card'])
    p['begun'] = True
    p['begun_at'] = now().isoformat()
    log(state, 'Записана одна попытка UI для ' + p['variant'])


def current_counts(state, at):
    key = ledger.timestamp(at).astimezone(ZoneInfo(state['binding']['timezone'])).date().isoformat()
    result = {}
    for source in ledger.sources(state):
        row = state['days'].get(source, {}).get(key)
        if not row:
            raise ValueError('Нет дневного снимка ' + source + ' за ' + key)
        fresh(row['captured_at'])
        result[source] = deepcopy(row)
    return result


def confirm(root, state, data):
    p = state['pending']
    if not p or state['status'] == 'paused_attention' or data['intent_id'] != p['id']:
        raise ValueError('Нет соответствующей ожидающей проверки')
    if p.get('possible_current_variants'):
        raise ValueError('Сначала визуально сверить фактическое фото командой reconcile')
    if not p['begun'] and not (p['variant'] == state['on_card'] and data.get('no_upload_needed') is True):
        raise ValueError('Смена не зарегистрирована до UI-действия')
    conditions = proof(root, state, data, p['variant'])
    state['last_conditions'] = conditions
    if p['purpose'] == 'interval' and conditions_changed(state, conditions):
        raise ValueError('Условия изменились: сначала согласовать новый блок сравнения')
    if p['purpose'] == 'finish' and conditions_changed(state, conditions):
        state['status'] = 'paused_attention'
        state['attention'] = conditions_changed(state, conditions)
        state['goal_reached'] = False
        state['result']['confirmed'] = False
        state['result']['reason'] = 'Условия изменились при итоговой проверке'
        log(state, state['result']['reason'])
        return
    if p['purpose'] == 'interval':
        if state['config']['mode'] == 'intraday_counts':
            snapshot = data['snapshot']
            if ledger.timestamp(snapshot['observed_at']) < ledger.timestamp(data['observed_at']):
                raise ValueError('Стартовые счётчики получены до проверки публикации')
            observe(root, state, snapshot, preparation=True, expected_variant=p['variant'])
            if conditions_changed(state, state['last_conditions']):
                raise ValueError('Условия изменились при получении стартовых счётчиков')
            baseline = current_counts(state, snapshot['observed_at'])
            for row in baseline.values():
                if ledger.timestamp(row['captured_at']) < ledger.timestamp(data['observed_at']):
                    raise ValueError('Счётчики должны быть прочитаны после проверки опубликованного фото')
            started = snapshot['observed_at']
        else:
            baseline, started = {}, data['observed_at']
        state['current'] = {'id': uuid4().hex, 'variant': p['variant'], 'epoch': state['epoch'], 'phase': state['phase'],
                            'started_at': started, 'baseline': baseline, 'conditions': conditions}
        state['status'] = 'running'
    else:
        state['status'] = 'finished'
        state['goal_reached'] = state['result'].get('confirmed', False) if p['purpose'] == 'finish' else False
        state['current'] = None
    state['on_card'] = p['variant']
    state['pending'] = None
    state['last_cover_check'] = data['observed_at']
    log(state, 'Подтверждено опубликованное фото ' + state['on_card'])


def observe(root, state, data, preparation=False, expected_variant=None):
    binding_matches(state, data)
    fresh(data['observed_at'])
    identity = data['observation_id']
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if identity in state['observations']:
        if state['observations'][identity] != fingerprint:
            raise ValueError('Повторный ID наблюдения с другим содержимым')
        return False
    variant = expected_variant or state['on_card']
    conditions = proof(root, state, data['cover'], variant)
    reasons = conditions_changed(state, conditions)
    changed_days = []
    if not data.get('rows'):
        raise ValueError('Нужны фактические строки источников')
    seen = set()
    for raw in data['rows']:
        key = (raw['source'], raw.get('period_start'), raw['date'])
        if key in seen:
            raise ValueError('Повтор источника и даты в одном наблюдении')
        seen.add(key)
        row = deepcopy(raw)
        fresh(row['captured_at'])
        if ledger.timestamp(row['captured_at']) > ledger.timestamp(data['observed_at']):
            raise ValueError('Время строки позже времени наблюдения')
        row['evidence'] = evidence(root, row['evidence'])
        row['observation_id'] = identity
        if ledger.put(state, row):
            changed_days.append((raw['source'], raw['date']))
    state['observations'][identity] = fingerprint
    state['last_observed_at'] = data['observed_at']
    state['last_conditions'] = conditions
    state['last_cover_check'] = data['cover']['observed_at']
    for source, day in changed_days:
        for interval in state['intervals']:
            if interval.get('excluded'):
                continue
            zone = ZoneInfo(state['binding']['timezone'])
            first = ledger.timestamp(interval['started_at']).astimezone(zone).date().isoformat()
            last = ledger.timestamp(interval['ended_at']).astimezone(zone).date().isoformat()
            if first <= day <= last:
                reasons.append('Исправлен завершённый день закрытого интервала: ' + source + ' ' + day)
                state['goal_reached'] = False
                state['result'] = None
                break
    if data.get('settings_changed') is True:
        reasons.append('Изменились настройки рекламы')
    if reasons and not preparation:
        if state.get('current'):
            state['current']['excluded'] = True
        state['status'] = 'paused_attention'
        state['attention'] = reasons
        log(state, '; '.join(reasons))
    log(state, 'Сохранено наблюдение ' + identity)
    return True


def calculation(state):
    interval = state['current']
    at = state.get('last_observed_at')
    if not interval or not at or ledger.timestamp(at) < ledger.timestamp(interval['started_at']):
        raise ValueError('Нужен новый снимок после начала интервала')
    counts = current_counts(state, at) if state['config']['mode'] == 'intraday_counts' else None
    return ledger.totals(state, interval, at, counts), at, counts


def close_interval(state):
    if state['status'] != 'running':
        raise ValueError('Нет работающего интервала')
    fresh(state['last_observed_at'])
    fresh(state['last_cover_check'])
    calculated, at, counts = calculation(state)
    if (now() - ledger.timestamp(state['current']['started_at'])).total_seconds() / 3600 > state['config']['max_interval_hours']:
        raise ValueError('Превышен предел длительности; нужна пауза и решение пользователя')
    if not ledger.ready(state, state['current'], calculated, at):
        raise ValueError('Не набран объём, минимальное время или итог прошлого дня')
    closed = state['current']
    closed.update(ended_at=at, end_counts=counts)
    state['intervals'].append(closed)
    state['current'] = None
    state['position'] += 1
    log(state, 'Закрыт интервал ' + closed['variant'])
    if state['position'] < len(state['plan']):
        request(state, state['plan'][state['position']])
    else:
        evaluate(state)


def evaluate(state):
    values = ledger.summary(state, state['phase'])
    if state['phase'] == 'exploration':
        eligible = [key for key in state['variants'] if key in values and values[key]['meets_targets']]
        pool = eligible or list(values)
        best = max(pool, key=lambda key: (values[key]['sources']['funnel']['ctr'], key == 'A'))
        state['leader'] = best
        if eligible and state['config'].get('confirmation_multiplier'):
            state['candidate'] = best
            state['phase'] = 'confirmation'
            state['plan'] = ['A'] if best == 'A' else ['A', best]
            state['position'] = 0
            request(state, state['plan'][0])
            log(state, 'Предварительный лидер ' + best + '; требуется отдельное подтверждение')
            return
        state['result'] = {
            'confirmed': bool(eligible),
            'reason': 'Нормативы выполнены за один проход' if eligible else 'Нормативы не достигнуты',
            'leader': best,
            'interpretation': 'Сравнение CTR при последовательной смене обложек',
        }
    else:
        best = state['candidate']
        confirmed = values[best]['meets_targets']
        if best != 'A':
            confirmed = confirmed and values[best]['sources']['funnel']['ctr'] > values['A']['sources']['funnel']['ctr']
        state['result'] = {'confirmed': confirmed, 'reason': 'Норматив подтверждён на новых данных' if confirmed else 'Подтверждение не пройдено',
                           'leader': best, 'interpretation': 'Последовательное наблюдение; причинный эффект не доказан'}
    target = state['leader'] if state['config']['finish_policy'] == 'leader' else 'A'
    request(state, target, 'finish')


def next_action(state):
    if state['status'] in ('prepared', 'finished', 'paused_attention'):
        return {'action': {'prepared': 'prepare_or_start', 'finished': 'none', 'paused_attention': 'needs_attention'}[state['status']],
                'reason': state.get('attention'), 'goal_reached': state['goal_reached']}
    if state['pending']:
        p = state['pending']
        return {'action': 'reconcile_cover' if p.get('possible_current_variants') else ('verify_cover' if p['begun'] or p['variant'] == state['on_card'] else 'change_cover'),
                'intent_id': p['id'], 'variant': p['variant'], 'purpose': p['purpose'],
                'possible_current_variants': p.get('possible_current_variants', []),
                'file': state['variants'][p['variant']]['file'], 'sha256': state['variants'][p['variant']]['sha256']}
    if (now() - ledger.timestamp(state['current']['started_at'])).total_seconds() / 3600 > state['config']['max_interval_hours']:
        return {'action': 'pause', 'reason': 'Достигнут предел длительности интервала; требуется решение пользователя'}
    try:
        calc, at, _ = calculation(state)
    except ValueError as exc:
        return {'action': 'collect_snapshot', 'reason': str(exc)}
    if calc['missing']:
        return {'action': 'collect_closed_days', 'missing': calc['missing']}
    is_fresh = (now() - ledger.timestamp(at)).total_seconds() <= 900
    if is_fresh and ledger.ready(state, state['current'], calc, at):
        return {'action': 'close_interval', 'metrics': calc}
    return {'action': 'collect_snapshot', 'metrics': calc}


def stop(state, data):
    if data.get('stop_authorized') is not True:
        raise ValueError('Нужен запрос пользователя остановить тест')
    target = data['variant']
    if target == 'leader':
        target = state.get('leader')
        if not target:
            raise ValueError('Лидер ещё не определён; укажите конкретное фото для остановки')
    if target not in state['variants']:
        raise ValueError('Неизвестная целевая обложка')
    uncertain = []
    if state['pending']:
        uncertain = state['pending'].get('possible_current_variants', [])
        if state['pending']['begun']:
            uncertain = list(set(uncertain + [state['on_card'], state['pending']['variant']]))
    if state['current']:
        state['current'].update(excluded=True, ended_at=now().isoformat(), end_counts=None)
        state['intervals'].append(state['current'])
    state['current'] = None
    state['goal_reached'] = False
    state['result'] = {'confirmed': False, 'reason': 'Остановлено пользователем'}
    request(state, target, 'stop')
    if uncertain:
        state['pending']['possible_current_variants'] = uncertain


def reconcile(root, state, data):
    pending = state['pending']
    if not pending or not pending.get('possible_current_variants') or data['intent_id'] != pending['id']:
        raise ValueError('Нет перехода, требующего сверки фактического фото')
    candidates = [key for key in pending['possible_current_variants'] if state['variants'][key]['sha256'] == data.get('variant_sha256')]
    if not candidates:
        raise ValueError('Фактическое фото не совпало ни с одним ожидаемым вариантом')
    variant = candidates[0]
    state['last_conditions'] = proof(root, state, data, variant)
    state['on_card'] = variant
    pending.pop('possible_current_variants')
    log(state, 'После прерывания визуально установлено фактическое фото ' + variant)


def resume(root, state, data):
    if state['status'] != 'paused_attention' or data.get('resume_authorized') is not True:
        raise ValueError('Нужно устранить причину и получить указание продолжить')
    if state['pending']:
        pending = state['pending']
        seen = data['cover'].get('variant_sha256')
        target_hash = state['variants'][pending['variant']]['sha256']
        variant = pending['variant'] if seen == target_hash else state['on_card']
        conditions = proof(root, state, data['cover'], variant)
        if conditions_changed(state, conditions) and pending['purpose'] != 'stop':
            state['on_card'] = variant
            state['pending'] = None
        else:
            if variant != pending['variant']:
                if pending['begun'] and data.get('repeat_ui_authorized') is not True:
                    raise ValueError('Целевое фото не опубликовано; повтор UI требует отдельного указания')
                pending['begun'] = False
            state['status'] = 'awaiting_cover'
            state.pop('attention', None)
            log(state, 'Сверено состояние прерванной смены; следующий шаг — проверка либо разрешённая попытка')
            return
    conditions = proof(root, state, data['cover'], state['on_card'])
    if not conditions['available']:
        raise ValueError('Товар недоступен')
    if state['current']:
        state['current'].update(excluded=True, ended_at=data['cover']['observed_at'], end_counts=None)
        state['intervals'].append(state['current'])
    state['current'] = None
    state['conditions'] = conditions
    state['epoch'] += 1
    state['phase'] = 'exploration'
    state['position'] = 0
    state['goal_reached'] = False
    state['result'] = None
    state.pop('leader', None)
    state.pop('candidate', None)
    state.pop('attention', None)
    variants = list(state['variants'])
    state['plan'] = [key for cycle in range(state['config']['cycles']) for key in (variants if cycle % 2 == 0 else list(reversed(variants)))]
    request(state, state['plan'][0])
    log(state, 'Новый блок условий: прежние интервалы не участвуют в новом сравнении')


def generation(root, state, data):
    if state['status'] != 'prepared' or not state['consent']['image_generation']:
        raise ValueError('Нет разрешения на генерацию при подготовке')
    name = data['name']
    jobs = state['generations']
    if data['operation'] == 'reserve':
        if name in jobs or any(j['status'] == 'reserved' for j in jobs.values()):
            raise ValueError('Сначала сверить предыдущий вызов; повторная генерация не разрешена')
        if len(jobs) >= state['config']['max_generations']:
            raise ValueError('Лимит попыток исчерпан')
        if not data.get('hypothesis') or not data.get('prompt'):
            raise ValueError('Нужны гипотеза и промпт')
        jobs[name] = {'status': 'reserved', 'prompt': data['prompt'], 'hypothesis': data['hypothesis'], 'reserved_at': now().isoformat()}
    elif data['operation'] in ('complete', 'fail'):
        job = jobs[name]
        if job['status'] != 'reserved':
            raise ValueError('Попытка уже закрыта')
        if data['operation'] == 'fail':
            job.update(status='failed', reason=data['reason'])
        else:
            generated = photo(root, 'G' + str(len(jobs)), data['file'], name, job['hypothesis'], 'chatgpt_image_gen')
            job.update(status='done', file=generated['file'], sha256=generated['sha256'])
    else:
        raise ValueError('Неизвестная операция генерации')
    return jobs[name]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'add-variant', 'start', 'begin-ui', 'confirm', 'reconcile', 'observe', 'close', 'next-action', 'report', 'stop', 'resume', 'pause', 'generation'])
    parser.add_argument('--test-dir', required=True)
    parser.add_argument('--input')
    args = parser.parse_args()
    root = Path(args.test_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    with lock(root):
        data = read(args.input) if args.input else None
        if args.command == 'init':
            state = initialize(root, data)
        else:
            state = deepcopy(read(root / 'state.json'))
            if args.command == 'add-variant': add_variant(root, state, data)
            elif args.command == 'start': start(state, data)
            elif args.command == 'begin-ui': begin_ui(root, state, data)
            elif args.command == 'confirm': confirm(root, state, data)
            elif args.command == 'reconcile': reconcile(root, state, data)
            elif args.command == 'observe': observe(root, state, data)
            elif args.command == 'close': close_interval(state)
            elif args.command == 'stop': stop(state, data)
            elif args.command == 'resume': resume(root, state, data)
            elif args.command == 'generation': generation(root, state, data)
            elif args.command == 'pause':
                state['status'] = 'paused_attention'
                state['attention'] = [data['reason']]
                log(state, data['reason'])
        write(root / 'state.json', state)
        from dashboard import render
        render(root, state)
        print(json.dumps(next_action(state), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, KeyError, OSError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
