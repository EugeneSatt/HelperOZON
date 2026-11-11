#!/usr/bin/env python3
"""Validate an evidence-backed Ozon comparison and calculate a partial structural index.

Standard library only. No network calls, browser access or credential handling.
"""

import argparse
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import json
import hashlib
import math
from pathlib import Path
import statistics
import sys


# id, label, direction, weight, kind
METRICS = [
    ("price", "Цена в отчёте MPStats", "info", 0, "number"),
    ("ozon_card_price", "Цена с Ozon Картой", "info", 0, "number"),
    ("buyer_price", "Цена с другими банками", "info", 0, "number"),
    ("description_length", "Длина описания", "up", 1, "count"),
    ("characteristics_count", "Заполненные характеристики", "up", 1, "count"),
    ("photos_count", "Фото в карусели", "up", 1, "count"),
    ("has_video", "Видео", "bool", 1, "bool"),
    ("infographic", "Инфографика на обложке", "bool", 1, "bool"),
    ("background", "Тип фона", "info", 0, "text"),
    ("reviews_count", "Число отзывов", "up", 1, "count"),
    ("rating", "Средняя оценка", "up", 1, "rating"),
    ("negative_share", "Доля отзывов 1–2 звезды", "down", 1, "fraction"),
    ("search_position", "Позиция по выбранным запросам", "down", 2, "position"),
    ("ctr", "CTR", "up", 2, "fraction"),
    ("cart_to_order", "Корзина → заказ", "up", 2, "fraction"),
    ("card_to_cart", "Карточка → корзина", "up", 2, "fraction"),
    ("revenue", "Сумма заказов MPStats", "up", 1, "number"),
    ("sales", "Заказы, штуки MPStats", "up", 1, "count"),
]
METRIC_IDS = {m[0] for m in METRICS}
SOURCE_KINDS = {
    "ozon_seller_ui", "ozon_public_ui", "mpstats_mcp", "mpstats_ui",
    "export", "vision", "derived",
}
FINDING_IDS = METRIC_IDS | {
    "title", "description", "characteristics", "media_sequence", "rich_content",
    "variant_binding", "review_objections", "delivery_promise",
}
MIN_COMPARABLE_PEERS = 3


def require(condition, message):
    if not condition:
        raise ValueError(message)


def timestamp(value, label):
    require(isinstance(value, str), f"{label}: нужен timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, f"{label}: нужен часовой пояс")
    return result


def iso_date(value):
    require(isinstance(value, str), "Дата должна быть строкой YYYY-MM-DD")
    result = date.fromisoformat(value)
    require(result.isoformat() == value, f"Неверный формат даты: {value}")
    return result


def sku(value):
    require(type(value) in (str, int), "Ozon SKU должен быть строкой или целым числом")
    result = str(value)
    require(result.isascii() and result.isdecimal() and int(result) > 0,
            f"Некорректный Ozon SKU: {result}")
    return str(int(result))


def validate(data):
    require(isinstance(data, dict), "Корень audit.json должен быть объектом")
    meta = data.get("meta", {})
    require(isinstance(meta, dict), "meta должен быть объектом")
    own_id = sku(meta.get("own_sku"))
    start = iso_date(meta.get("period_start"))
    end = iso_date(meta.get("period_end"))
    require(start <= end, "Начало периода позже конца")
    timestamp(meta.get("collected_at"), "meta.collected_at")
    sources = {}
    source_list = data.get("sources", [])
    require(isinstance(source_list, list), "sources должен быть массивом")
    for source in source_list:
        require(isinstance(source, dict), "Источник должен быть объектом")
        sid = source.get("id")
        require(isinstance(sid, str) and sid.strip(), "У источника отсутствует id")
        require(sid not in sources, f"Повтор source_id: {sid}")
        require(source.get("kind") in SOURCE_KINDS, f"Неизвестный тип источника {sid}")
        require(isinstance(source.get("locator"), str) and source["locator"].strip(),
                f"У источника {sid} нет локатора")
        require(any(isinstance(source.get(k), str) and source[k].strip() for k in ("url", "file")),
                f"У источника {sid} нет URL или файла")
        timestamp(source.get("captured_at"), f"{sid}.captured_at")
        sources[sid] = source
    products = data.get("products")
    require(isinstance(products, list) and products, "Нужен список products")
    seen = set()
    own = []
    peers = []
    for product in products:
        require(isinstance(product, dict), "Товар должен быть объектом")
        pid = sku(product.get("sku"))
        require(pid not in seen, f"Повтор Ozon SKU: {pid}")
        seen.add(pid)
        for field in ("name", "seller", "variant"):
            require(isinstance(product.get(field), str) and product[field].strip(),
                    f"{pid}: отсутствует {field}; зафиксируй выбранное предложение и вариант")
        require(product.get("identity_source_id") in sources,
                f"{pid}: нужен зарегистрированный identity_source_id")
        require(product.get("role") in ("own", "competitor"), f"Неверная роль у {pid}")
        (own if product["role"] == "own" else peers).append(product)
        metrics = product.get("metrics", {})
        require(isinstance(metrics, dict), f"metrics у {pid} должен быть объектом")
        require(not (set(metrics) - METRIC_IDS), f"Неизвестные metric_id у {pid}: {set(metrics) - METRIC_IDS}")
        for key, obs in metrics.items():
            require(isinstance(obs, dict) and "value" in obs, f"{pid}/{key}: нужен объект value")
    require(len(own) == 1, "Должен быть ровно один own")
    require(sku(own[0]["sku"]) == own_id, "own_sku не совпадает с own")
    require(len(peers) <= 5, "Нужно не более пяти конкурентов")
    findings = data.get("findings", [])
    require(isinstance(findings, list) and len(findings) <= 3, "findings: до трёх объектов")
    for finding in findings:
        require(isinstance(finding, dict), "Каждый finding должен быть объектом")
        require(finding.get("metric_id") in FINDING_IDS, "finding с неизвестным metric_id")
        for field in ("fact", "hypothesis", "action", "verification"):
            require(isinstance(finding.get(field), str) and finding[field].strip(), f"finding: нет {field}")
        ids = finding.get("source_ids")
        require(isinstance(ids, list) and ids and all(s in sources for s in ids),
                "finding: нужны существующие source_ids")
    private_funnel(data)
    return own[0], peers, sources


def private_funnel(data):
    own = next(p for p in data['products'] if p['role'] == 'own')
    funnel = data.get('private_funnel')
    if funnel is None and isinstance(own.get('private_metrics'), dict):
        funnel = own['private_metrics']
    if funnel is None or funnel == {}:
        return {}
    require(isinstance(funnel, dict), 'private_funnel должен быть объектом')
    meta = data['meta']
    require(sku(funnel.get('sku')) == sku(meta['own_sku']), 'Воронка относится к другому Ozon SKU')
    require(funnel.get('period') == [meta['period_start'], meta['period_end']], 'Воронка относится к другому периоду')
    require(isinstance(meta.get('cabinet'), str) and bool(meta['cabinet'].strip()) and funnel.get('account') == meta['cabinet'],
            'Воронка относится к другому кабинету или кабинет не указан')
    require(funnel.get('source_id') in {s['id'] for s in data['sources']}, 'Нет зарегистрированного источника воронки')
    fractions = {'ctr', 'card_to_cart', 'cart_to_order', 'delivered_rate'}
    counts = {'views', 'clicks', 'carts', 'orders', 'purchased', 'canceled'}
    labels = funnel.get('labels', {})
    require(isinstance(labels, dict) and set(labels) <= {'views', 'clicks', 'carts', 'ctr'},
            'Неизвестные подписи воронки')
    require(all(isinstance(v, str) and v.strip() and len(v) <= 80 for v in labels.values()),
            'Подписи воронки должны быть непустыми строками до 80 знаков')
    for key in fractions | counts | {'order_value', 'average_order_price'}:
        value = funnel.get(key)
        if value is None:
            continue
        require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
                f'Недопустимое значение воронки: {key}')
        if key in fractions:
            require(value <= 1, f'Доля воронки должна быть в диапазоне 0..1: {key}')
        if key in counts:
            require(value == int(value), f'Нужен целый счётчик воронки: {key}')
    return funnel


def observation(product, metric, kind, meta, sources):
    obs = product.get("metrics", {}).get(metric, {"value": None, "missing_reason": "Не получено"})
    value = obs.get("value")
    result = {"sku": sku(product["sku"]), "value": value, "source_id": obs.get("source_id")}
    result.update({key: obs.get(key) for key in ('basis', 'period', 'scope', 'region', 'query_set')})
    if value is None:
        result.update(valid=False, reason=obs.get("missing_reason") or "Не указана причина пропуска")
        return result, obs
    label = f"{product['sku']}/{metric}"
    if kind == "bool":
        require(type(value) is bool, f"{label}: нужно true/false/null")
    elif kind == "text":
        require(isinstance(value, str) and value.strip(), f"{label}: нужен текст или null")
    else:
        require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
                f"{label}: нужно конечное неотрицательное число или null")
        if kind == "fraction":
            require(value <= 1, f"{label}: проценты хранятся долями 0..1")
        elif kind == "rating":
            require(1 <= value <= 5, f"{label}: рейтинг должен быть 1..5")
        elif kind == "position":
            require(value >= 1, f"{label}: позиция 0 недопустима, для 'не найден' нужен null")
        elif kind == "count":
            require(value == int(value), f"{label}: нужен целый счётчик")
    reasons = []
    if obs.get("source_id") not in sources:
        reasons.append("нет зарегистрированного источника")
    for field in ("basis", "scope"):
        if not isinstance(obs.get(field), str) or not obs[field].strip():
            reasons.append(f"не задан {field}")
    for field in ("region", "query_set"):
        if field not in obs:
            reasons.append(f"не задан {field}; для неприменимого поля нужен null")
    period = obs.get("period")
    if period != "snapshot":
        if not isinstance(period, list) or len(period) != 2:
            reasons.append("нет периода или snapshot")
        elif period != [meta["period_start"], meta["period_end"]]:
            reasons.append("период отличается от периода аудита")
    if obs.get("region") is not None and not isinstance(obs.get("region"), str):
        reasons.append("region должен быть строкой или null")
    queries = obs.get("query_set")
    if queries is not None and not (isinstance(queries, list) and queries and all(isinstance(x, str) and x.strip() for x in queries)):
        reasons.append("query_set должен быть непустым списком запросов или null")
    if metric == "search_position" and (not queries or not obs.get("region")):
        reasons.append("позиции требуют одинаковых запросов и региона")
    if "comparison_eligible" in obs:
        require(type(obs["comparison_eligible"]) is bool, f"{label}: comparison_eligible должен быть true/false")
        if not obs["comparison_eligible"]:
            reasons.append(obs.get("comparison_exclusion_reason") or "Источник не позволяет сопоставление")
    result.update(valid=not reasons, reason="; ".join(reasons) if reasons else None)
    return result, obs


def compare(ours, theirs, sources):
    fields = ("basis", "period", "scope", "region", "query_set")
    mismatches = [field for field in fields if ours.get(field) != theirs.get(field)]
    if mismatches:
        return "Несопоставимы: " + ", ".join(mismatches)
    if ours["period"] == "snapshot":
        t1 = timestamp(sources[ours["source_id"]]["captured_at"], "captured_at")
        t2 = timestamp(sources[theirs["source_id"]]["captured_at"], "captured_at")
        if abs((t1 - t2).total_seconds()) > 86400:
            return "Снимки получены с разницей более 24 часов"
    return None


def status_for(value, peers, direction):
    if direction == "bool":
        yes = sum(1 for x in peers if x is True)
        return ("green" if value else "red" if yes > len(peers) / 2 else "yellow"), None, None
    med = statistics.median(peers)
    # Decimal keeps the inclusive 5% boundary stable for decimal-valued inputs.
    our_d, med_d = Decimal(str(value)), Decimal(str(med))
    low, high = med_d * Decimal("0.95"), med_d * Decimal("1.05")
    if direction == "up":
        status = "green" if our_d > high else "red" if our_d < low else "yellow"
    else:
        status = "green" if our_d < low else "red" if our_d > high else "yellow"
    gap = None if med == 0 else (med - value) / med if direction == "up" else (value - med) / med
    return status, med, gap


def analyze(data):
    own, peers, sources = validate(data)
    rows = []
    numerator = denominator = counted = key_count = 0
    for metric, label, direction, weight, kind in METRICS:
        ours, own_obs = observation(own, metric, kind, data["meta"], sources)
        comparable = []
        peer_rows = []
        for peer in peers:
            item, peer_obs = observation(peer, metric, kind, data["meta"], sources)
            item["comparable"] = False
            if item["valid"] and ours["valid"]:
                mismatch = compare(own_obs, peer_obs, sources)
                item["comparable"] = mismatch is None
                if mismatch:
                    item["reason"] = mismatch
                else:
                    comparable.append(item["value"])
            elif item["valid"]:
                item["reason"] = "Собственное наблюдение отсутствует или не подтверждено"
            peer_rows.append(item)
        status, med, gap = "nodata", None, None
        if direction == "info":
            status = "info"
        elif ours["valid"] and comparable:
            status, med, gap = status_for(ours["value"], comparable, direction)
        included = bool(weight and ours["valid"] and len(comparable) >= MIN_COMPARABLE_PEERS)
        reason = None
        if weight and not included:
            reason = ours["reason"] if not ours["valid"] else f"Сопоставимых конкурентов {len(comparable)}; нужно минимум {MIN_COMPARABLE_PEERS}"
        if included:
            counted += 1
            denominator += weight
            key_count += int(weight == 2)
            if status in ("green", "yellow"):
                numerator += weight
        rows.append({
            "metric_id": metric, "label": label, "direction": direction, "weight": weight,
            "own": ours, "competitors": peer_rows, "median": med,
            "comparable_competitors": len(comparable), "status": status,
            "included_in_score": included, "excluded_reason": reason,
            "gap_fraction": gap,
            "absolute_difference": None if med is None or not ours["valid"] else ours["value"] - med,
        })
    score = None if not denominator else int((Decimal(numerator) * 100 / Decimal(denominator)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    missing = [r["metric_id"] for r in rows if r["weight"] and not r["included_in_score"]]
    return {
        "schema_version": "2.0", "meta": data["meta"],
        "score": {
            "value": score,
            "label": "Индекс соответствия выбранным признакам",
            "partial": counted < 14,
            "counted_metrics": counted, "possible_metrics": 14,
            "passed_weight": numerator, "counted_weight": denominator, "possible_weight": 18,
            "counted_key_metrics": key_count, "possible_key_metrics": 4,
            "competitor_count": len(peers), "excluded_metrics": missing,
            "interpretation": "Структурное сравнение; не доказательство качества карточки или причин продаж",
        },
        "rows": rows, "findings": data.get("findings", []),
        "limitations": data.get("limitations", []),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        raw = args.input.read_bytes()
        result = analyze(json.loads(raw.decode('utf-8')))
        result['input_sha256'] = hashlib.sha256(raw).hexdigest()
        content = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            require(args.input.resolve() != args.output.resolve(), "Выход не должен перезаписывать исходные данные")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding="utf-8")
            print(json.dumps({"output": str(args.output.resolve()), "score": result["score"]}, ensure_ascii=False))
        else:
            print(content, end="")
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"Ошибка данных: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
