#!/usr/bin/env python3
"""Prepare Ozon query exports and audit three generated descriptions."""

import argparse
import json
import math
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

QUERY_ALIASES = ["поисковый запрос", "запрос", "текст запроса", "search query", "query"]
POP_ALIASES = ["популярность запроса", "популярность", "частотность", "показы", "query popularity", "popularity"]
META_COPY_PATTERNS = [
    ("search_query", re.compile(r"\bпоисков\w*\s+(?:запрос\w*|синоним\w*|ключ\w*|фраз\w*)\b", re.I)),
    ("keyword_explanation", re.compile(r"\b(?:этот|данный)\s+ключ\w*\b", re.I)),
    ("card_reference", re.compile(r"\b(?:в|на)\s+карточк\w*\b", re.I)),
    ("characteristics_reference", re.compile(r"\bпо\s+характеристикам\s+(?:товар\w*|карточк\w*)\b", re.I)),
    ("release_form", re.compile(r"\bформа\s+выпуск\w*\b", re.I)),
]

PROFILE_PATTERNS = {
    "laundry": [
        ("volume", r"\b\d+(?:[.,]\d+)?\s*(?:л|литр(?:а|ов)?|мл|миллилитр(?:а|ов)?)\b"),
        ("laundry_type", r"\b(?:бел\w*|черн\w*|цветн\w*|темн\w*|детск\w*)\s+бель"),
        ("fragrance", r"\b(?:запах\w*|аромат\w*|парфюм\w*)\b"),
        ("product_type", r"\b(?:гель|порошок|средство|капсул\w*)\b"),
    ],
    "child_diapers": [
        ("child_weight", r"\b\d{1,2}\s*[-–—]\s*\d{1,2}\s*кг\b"),
        ("pack_count", r"\b\d{1,3}\s*(?:шт\.?|штук\w*)\b"),
        ("size", r"\b(?:размер\s*)?(?:[1-7]|x{0,3}l|m|s)\b"),
        ("night_use", r"\b(?:ночн\w*|для\s+ноч\w*)\b"),
        ("gender", r"\b(?:девоч\w*|мальчик\w*|унисекс)\b"),
        ("sensitive_skin", r"\b(?:чувствительн\w*\s+кож\w*|гипоаллерген\w*)\b"),
        ("wetness_indicator", r"\bиндикатор\w*\s+(?:влаг\w*|наполн\w*)\b"),
        ("breathable_surface", r"\bдышащ\w*\s+(?:слой\w*|поверхност\w*|материал\w*)\b"),
        ("construction", r"\b(?:трусик\w*|липучк\w*|заст[её]жк\w*|бортик\w*|резинк\w*|посадк\w*)\b"),
        ("product_type", r"\b(?:подгузник\w*|памперс\w*|трусик\w*)\b"),
    ],
    "generic": [
        ("volume_or_count", r"\b\d+(?:[.,]\d+)?\s*(?:л|литр\w*|мл|шт\.?|штук\w*|г|кг)\b"),
        ("fragrance", r"\b(?:запах\w*|аромат\w*|парфюм\w*)\b"),
    ],
}

PROFILE_WORDS = {
    "laundry": "гель порошок средство капсулы стирка стиральный белье белое черное цветное темное детское концентрат универсальный аромат запах литр мл",
    "child_diapers": "подгузник подгузники трусики памперс детский дети ребенок малыша малышей мальчик девочка унисекс ночной ночь размер вес кг штук шт упаковка кожа чувствительная индикатор влаги наполнения дышащий поверхность слой материал липучка застежка бортик резинка посадка xl xxl xxxl s m l",
    "generic": "товар средство набор упаковка штука штук шт объем мл литр грамм кг аромат запах женский мужской детский",
}


def norm(value):
    return re.sub(r"\s+", " ", ("" if value is None else str(value)).replace("ё", "е").replace("Ё", "Е").casefold()).strip()


def header(value):
    return re.sub(r"[^a-zа-я0-9]+", " ", norm(value)).strip()


def pattern(phrase):
    parts = [re.escape(item) for item in norm(phrase).split()]
    if not parts:
        return re.compile(r"(?!x)x")
    return re.compile(r"(?<![0-9a-zа-я])" + r"\s+".join(parts) + r"(?![0-9a-zа-я])", re.I)


def read_json(path):
    with Path(path).open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return data


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def json_value(value):
    if value is None:
        return None
    try:
        if math.isnan(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def column_number(cell_ref):
    letters = re.match(r"[A-Z]+", cell_ref or "")
    result = 0
    for char in (letters.group(0) if letters else "A"):
        result = result * 26 + ord(char) - 64
    return result - 1


def load_xlsx_values(path, sheet=None):
    """Read values directly from OOXML and ignore broken or unusual styles."""
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required; use the bundled workspace Python") from exc
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
          "p": "http://schemas.openxmlformats.org/package/2006/relationships"}
    with zipfile.ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.text or "" for node in item.findall(".//m:t", ns))
                      for item in root.findall("m:si", ns)]
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {node.attrib["Id"]: node.attrib["Target"] for node in rels.findall("p:Relationship", ns)}
        sheets = workbook.findall("m:sheets/m:sheet", ns)
        selected = sheets[0]
        if sheet is not None:
            if isinstance(sheet, int):
                selected = sheets[sheet]
            else:
                matches = [node for node in sheets if node.attrib.get("name") == str(sheet)]
                if not matches:
                    raise ValueError(f"Worksheet not found: {sheet}")
                selected = matches[0]
        rel_id = selected.attrib[f"{{{ns['r']}}}id"]
        target = targets[rel_id].lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        xml = ET.fromstring(archive.read(target))
        rows, width = [], 0
        for row_node in xml.findall(".//m:sheetData/m:row", ns):
            row = {}
            for cell in row_node.findall("m:c", ns):
                index = column_number(cell.attrib.get("r", ""))
                cell_type = cell.attrib.get("t")
                if cell_type == "inlineStr":
                    value = "".join(node.text or "" for node in cell.findall(".//m:t", ns))
                else:
                    value_node = cell.find("m:v", ns)
                    value = "" if value_node is None else (value_node.text or "")
                    if cell_type == "s" and value:
                        value = shared[int(value)]
                row[index] = value
                width = max(width, index + 1)
            rows.append((int(row_node.attrib.get("r", len(rows) + 1)), row))
        if not rows:
            return pd.DataFrame()
        height = max(row_number for row_number, _ in rows)
        matrix = [[None] * width for _ in range(height)]
        for row_number, values in rows:
            for index, value in values.items():
                matrix[row_number - 1][index] = value
        return pd.DataFrame(matrix)


def raw_table(path, sheet=None):
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required; use the bundled workspace Python") from exc
    suffix = path.suffix.casefold()
    if suffix == ".xlsx":
        try:
            return pd.read_excel(path, sheet_name=0 if sheet is None else sheet, header=None, dtype=object)
        except Exception:
            return load_xlsx_values(path, sheet)
    if suffix == ".xls":
        return pd.read_excel(path, sheet_name=0 if sheet is None else sheet, header=None, dtype=object)
    if suffix in {".csv", ".tsv"}:
        separator = "\t" if suffix == ".tsv" else None
        for encoding in ("utf-8-sig", "utf-8", "cp1251"):
            try:
                return pd.read_csv(path, sep=separator, engine="python", encoding=encoding, header=None, dtype=object)
            except UnicodeDecodeError:
                continue
        raise ValueError(f"Cannot decode {path}")
    raise ValueError(f"Unsupported file: {path}")


def find_col(columns, aliases, label):
    mapped = {column: header(column) for column in columns}
    wanted = {header(alias) for alias in aliases}
    exact = [column for column, value in mapped.items() if value in wanted]
    if len(exact) == 1:
        return exact[0]
    first_level = [column for column in columns if header(str(column).split("|", 1)[0]) in wanted]
    if len(first_level) == 1:
        return first_level[0]
    partial = [column for column, value in mapped.items()
               if any(alias in value or value in alias for alias in wanted if alias and value)]
    if len(partial) == 1:
        return partial[0]
    raise ValueError(f"Cannot identify one {label} column; found {list(map(str, columns))}")


def candidate_headers(raw, start, depth):
    top, names, last_top = [], [], ""
    for value in raw.iloc[start].tolist():
        clean = "" if value is None or norm(value) == "nan" else str(value).strip()
        if clean:
            last_top = clean
        top.append(last_top)
    for column in range(raw.shape[1]):
        parts = []
        for row in range(start, start + depth):
            value = raw.iat[row, column]
            clean = "" if value is None or norm(value) == "nan" else str(value).strip()
            if depth == 2 and row == start and not clean:
                clean = top[column]
            if clean and clean not in parts:
                parts.append(clean)
        names.append(" | ".join(parts) or f"column_{column + 1}")
    seen, unique = Counter(), []
    for name in names:
        seen[name] += 1
        unique.append(name if seen[name] == 1 else f"{name} [{seen[name]}]")
    return unique


def load_table(path, sheet, query_aliases, popularity_aliases):
    raw = raw_table(path, sheet)
    if raw.empty:
        raise ValueError(f"Empty table: {path}")
    best = None
    for start in range(min(20, len(raw))):
        for depth in (1, 2):
            if start + depth > len(raw):
                continue
            names = candidate_headers(raw, start, depth)
            try:
                query_col = find_col(names, query_aliases, "query")
                popularity_col = find_col(names, popularity_aliases, "popularity")
            except ValueError:
                continue
            if query_col == popularity_col:
                continue
            score = 4 + (2 if depth == 1 else 1) - start / 100
            if best is None or score > best[0]:
                best = (score, start, depth, names, query_col, popularity_col)
    if best is None:
        raise ValueError(f"Cannot find Ozon headers in first 20 rows: {path}")
    _, start, depth, names, query_col, popularity_col = best
    # Ozon often puts explanatory text directly below the real headings. Treat it
    # as the second header level instead of emitting a fake data row.
    if depth == 1 and start + 1 < len(raw):
        query_index = names.index(query_col)
        popularity_index = names.index(popularity_col)
        next_query = norm(raw.iat[start + 1, query_index])
        next_popularity = number(raw.iat[start + 1, popularity_index])
        if next_query in {"—", "-", ""} and next_popularity is None:
            depth = 2
            names = candidate_headers(raw, start, depth)
            query_col = find_col(names, query_aliases, "query")
            popularity_col = find_col(names, popularity_aliases, "popularity")
    table = raw.iloc[start + depth:].copy()
    table.columns = names
    table.insert(0, "__source_row__", [int(index) + 1 for index in table.index])
    return table, query_col, popularity_col, {"header_row": start + 1, "header_depth": depth, "columns": names}


def number(value):
    if value is None:
        return None
    try:
        result = float(value)
        return None if result != result else result
    except (TypeError, ValueError):
        text = re.sub(r"[^0-9.\-]", "", str(value).replace(" ", "").replace("\u00a0", "").replace(",", "."))
        try:
            return float(text)
        except ValueError:
            return None


def contains(text, phrase):
    return bool(pattern(phrase).search(norm(text)))


def contains_token_sequence(text, phrase):
    """Fast whole-token containment for normalized keyword-to-keyword checks."""
    text_tokens = norm(text).split()
    phrase_tokens = norm(phrase).split()
    width = len(phrase_tokens)
    return bool(width) and any(text_tokens[index:index + width] == phrase_tokens
                               for index in range(len(text_tokens) - width + 1))


def semantic_norm(value):
    text = norm(value).replace("–", "-").replace("—", "-")
    return re.sub(r"(?<=\d)\s+(?=(?:мл|л|г|кг)\b)", "", text)


def anchor_contains(text, phrase):
    return bool(pattern(semantic_norm(phrase)).search(semantic_norm(text)))


def profile_name(product):
    configured = norm(product.get("category_profile", ""))
    aliases = {"детские подгузники": "child_diapers", "подгузники": "child_diapers", "стирка": "laundry"}
    if configured:
        selected = aliases.get(configured, configured)
        return selected if selected in PROFILE_PATTERNS else "generic"
    title = norm(product.get("page_title", ""))
    if re.search(r"\b(?:подгузник\w*|памперс\w*)\b", title):
        return "child_diapers"
    if re.search(r"\b(?:стирк\w*|стиральн\w*)\b", title):
        return "laundry"
    return "generic"


def categories(query, profile):
    result = [name for name, regex in PROFILE_PATTERNS.get(profile, PROFILE_PATTERNS["generic"])
              if re.search(regex, norm(query), re.I)]
    return result or ["other"]


def anchor_definitions(product):
    result = []
    for index, raw in enumerate(product.get("required_product_anchors", []), 1):
        if isinstance(raw, str):
            item = {"name": f"anchor_{index}", "label": raw, "aliases": [raw], "required": True}
        elif isinstance(raw, dict):
            item = dict(raw)
            item.setdefault("name", f"anchor_{index}")
            item.setdefault("label", item.get("value", item["name"]))
            aliases = item.get("aliases", [])
            if isinstance(aliases, str):
                aliases = [aliases]
            item["aliases"] = [item.get("value"), item.get("label"), *aliases]
            item["required"] = item.get("required", True)
        else:
            raise ValueError("required_product_anchors items must be strings or objects")
        item["aliases"] = list(dict.fromkeys(norm(value) for value in item["aliases"] if norm(value)))
        if not item["aliases"]:
            raise ValueError(f"Anchor has no usable aliases: {item.get('name')}")
        result.append(item)
    return result


def matched_anchors(text, anchors):
    return [item["name"] for item in anchors if any(anchor_contains(text, alias) for alias in item["aliases"])]


def attribute_values(text, profile):
    value = semantic_norm(text)
    result = defaultdict(set)
    for amount, unit in re.findall(r"\b(\d+(?:[.,]\d+)?)\s*(мл|литр\w*|л|кг|г)\b", value):
        number_value = float(amount.replace(",", "."))
        if unit == "мл" or unit.startswith("л"):
            result["volume_ml"].add(round(number_value if unit == "мл" else number_value * 1000, 3))
        elif unit == "г" or unit == "кг":
            result["mass_g"].add(round(number_value if unit == "г" else number_value * 1000, 3))
    for amount in re.findall(r"\b(\d{1,4})\s*(?:шт\.?|штук\w*)\b", value):
        result["pack_count"].add(int(amount))
    for left, right in re.findall(r"\b(\d{1,2})\s*-\s*(\d{1,2})\s*кг\b", value):
        result["child_weight"].add((int(left), int(right)))
    if profile == "child_diapers":
        for size in re.findall(r"\b(?:размер\s*)?(x{0,3}l|s|m)\b", value):
            result["size"].add(size)
        for size in re.findall(r"\b(?:размер\s*)?([1-7])\b(?!\s*(?:шт|кг))", value):
            result["size"].add(size)
    return {name: values for name, values in result.items() if values}


def product_attribute_values(product, anchors, profile):
    parts = [product.get("page_title", "")]
    for fact in product.get("facts", []):
        parts.append(f"{fact.get('name', '')} {fact.get('value', '')}" if isinstance(fact, dict) else str(fact))
    for anchor in anchors:
        parts.extend(anchor.get("aliases", []))
    return attribute_values(" ".join(str(part) for part in parts), profile)


def conflicting_attributes(query, known, profile):
    found = attribute_values(query, profile)
    return [{"attribute": name, "query_values": sorted(values, key=str), "product_values": sorted(known[name], key=str)}
            for name, values in found.items() if name in known and values.isdisjoint(known[name])]


def alias_map(values, shared_aliases=None):
    shared_aliases = shared_aliases if isinstance(shared_aliases, dict) else {}
    result = {}
    iterable = values.items() if isinstance(values, dict) else ((value, []) for value in (values or []))
    for canonical, aliases in iterable:
        aliases = aliases if isinstance(aliases, list) else [aliases]
        extra = shared_aliases.get(canonical, [])
        extra = extra if isinstance(extra, list) else [extra]
        result[str(canonical)] = list(dict.fromkeys(norm(value) for value in [canonical, *aliases, *extra] if norm(value)))
    return result


def brand_matches(text, mapping):
    return [canonical for canonical, aliases in mapping.items() if any(contains(text, alias) for alias in aliases)]


def unknown_brand_tokens(original, profile, own_aliases, allowed_words):
    own_tokens = {token for alias in own_aliases for token in re.findall(r"[a-zа-я]+", alias)}
    known = set(PROFILE_WORDS.get(profile, PROFILE_WORDS["generic"]).split()) | own_tokens | allowed_words
    tokens = re.findall(r"[A-Za-zА-ЯЁа-яё][A-Za-zА-ЯЁа-яё0-9-]{2,}", str(original))
    candidates = []
    for token in tokens:
        clean = norm(token).strip("-")
        stem_known = any(clean.startswith(word[:5]) or word.startswith(clean[:5]) for word in known if len(word) >= 5)
        latin = bool(re.search(r"[a-z]", clean))
        capitalized_cyrillic = bool(re.match(r"[А-ЯЁ][а-яё]+$", token))
        if clean not in known and not stem_known and (latin or capitalized_cyrillic):
            candidates.append(token)
    return list(dict.fromkeys(candidates))


def detect_fact_conflicts(product):
    conflicts = []
    for raw in product.get("fact_conflicts", []):
        item = dict(raw) if isinstance(raw, dict) else {"name": str(raw), "claims": []}
        item.setdefault("status", "resolved" if item.get("resolution") else "needs_review")
        if item["status"] != "resolved" and not item.get("resolution"):
            conflicts.append(item)
    fact_texts = []
    for fact in product.get("facts", []):
        fact_texts.append(norm(f"{fact.get('name', '')} {fact.get('value', '')}" if isinstance(fact, dict) else fact))
    for left in fact_texts:
        for match in re.finditer(r"\bбез\s+([а-я]{5,})", left):
            word = match.group(1)
            stem = word[:-2] if len(word) > 6 else word[:5]
            positives = [right for right in fact_texts if right != left and stem in right and not re.search(rf"\bбез\s+\w*{re.escape(stem)}", right)]
            if positives:
                name = f"auto:{stem}"
                if not any(item.get("name") == name for item in conflicts):
                    conflicts.append({"name": name, "claims": [left, positives[0]], "status": "needs_review", "detected_automatically": True})
    return conflicts


def product_type_terms(product, profile):
    configured = product.get("product_type_terms", [])
    if isinstance(configured, str):
        configured = [configured]
    configured = [norm(value) for value in configured if norm(value)]
    if configured:
        return configured
    if profile == "child_diapers":
        return ["подгузники", "подгузник", "трусики", "памперс"]
    if profile == "laundry":
        return ["гель для стирки", "порошок", "средство для стирки", "капсулы для стирки"]
    title = norm(product.get("page_title", ""))
    common_types = [
        "гель для душа", "шампунь", "бальзам", "кондиционер", "крем", "сыворотка",
        "маска", "скраб", "мыло", "лосьон", "дезодорант", "зубная паста",
    ]
    return [value for value in common_types if contains(title, value)]


def relevance(query, profile, anchors, own_brand_aliases, product_terms):
    matched = matched_anchors(query, anchors)
    cats = categories(query, profile)
    own_match = any(contains(query, alias) for alias in own_brand_aliases)
    product_match = any(contains(query, term) for term in product_terms)
    if (matched or own_match) and product_match:
        tier = 3
    elif product_match and any(item not in {"product_type", "other"} for item in cats):
        tier = 2
    elif product_match:
        tier = 1
    else:
        tier = 0
    specificity = len(re.findall(r"[0-9a-zа-я]+", norm(query))) + 2 * len(matched) + sum(item not in {"product_type", "other"} for item in cats)
    return tier, specificity, matched, cats


def prepare(args):
    cfg = read_json(args.config)
    product = cfg.get("product", {})
    product_url = str(product.get("url", "")).strip()
    parsed_url = urlparse(product_url)
    hostname = (parsed_url.hostname or "").casefold()
    if parsed_url.scheme not in {"http", "https"} or not (hostname == "ozon.ru" or hostname.endswith(".ozon.ru")):
        raise ValueError("product.url must be an Ozon product URL analyzed before keyword processing")
    if not str(product.get("page_title", "")).strip():
        raise ValueError("product.page_title is required after analyzing the Ozon page")
    if not isinstance(product.get("facts"), list) or not product.get("facts"):
        raise ValueError("product.facts must contain characteristics extracted from the Ozon page")
    if "protected_broad_terms" not in product or not isinstance(product.get("protected_broad_terms"), list):
        raise ValueError("product.protected_broad_terms must be a reviewed list; use [] only after lexical-risk review")
    if "required_product_anchors" not in product or not isinstance(product.get("required_product_anchors"), list):
        raise ValueError("product.required_product_anchors must be a reviewed list; use [] only after commercial review")

    profile = profile_name(product)
    anchors = anchor_definitions(product)
    type_terms = product_type_terms(product, profile)
    if not type_terms:
        raise ValueError("product.product_type_terms is required when the generic category profile cannot infer a product type")
    aliases = cfg.get("column_aliases", {})
    query_aliases = aliases.get("query", QUERY_ALIASES)
    popularity_aliases = aliases.get("popularity", POP_ALIASES)
    shared_brand_aliases = cfg.get("brand_aliases", {})
    own_brand = str(product.get("brand", "")).strip()
    own_aliases = list(dict.fromkeys([norm(own_brand), *[norm(value) for value in product.get("brand_aliases", []) if norm(value)]]))
    competitors = alias_map(cfg.get("competitor_brands", []), shared_brand_aliases)
    owned = alias_map(cfg.get("owned_brands", product.get("owned_brands", [])), shared_brand_aliases)
    competitors = {name: values for name, values in competitors.items() if norm(name) != norm(own_brand)}
    other_owned = {name: values for name, values in owned.items() if norm(name) != norm(own_brand)}
    suspected = alias_map(cfg.get("suspected_brands", []), shared_brand_aliases)
    allowed_brand_words = {norm(value) for value in cfg.get("brand_detection_allowlist", []) if norm(value)}
    forbidden_claims = [str(value) for value in product.get("forbidden_claims", []) if norm(value)]
    conflicts = detect_fact_conflicts(product)
    known_attributes = product_attribute_values(product, anchors, profile)

    rows, source_metadata = [], []
    for source in cfg.get("sources", []):
        path = Path(source["path"]).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        threshold = float(source.get("min_popularity", 0))
        table, query_col, popularity_col, metadata = load_table(path, source.get("sheet"), query_aliases, popularity_aliases)
        metadata.update({"path": str(path), "query_column": query_col, "popularity_column": popularity_col})
        source_metadata.append(metadata)
        for _, rec in table.iterrows():
            original = "" if rec[query_col] is None else str(rec[query_col]).strip()
            pop = number(rec[popularity_col])
            query = norm(original)
            direct_competitors = brand_matches(query, competitors)
            owned_matches = brand_matches(query, other_owned)
            configured_suspects = brand_matches(query, suspected)
            unknown = unknown_brand_tokens(original, profile, own_aliases, allowed_brand_words)
            tier, specificity, anchor_names, cats = relevance(query, profile, anchors, own_aliases, type_terms)
            unsupported = [claim for claim in forbidden_claims if contains(query, claim)]
            attribute_conflicts = conflicting_attributes(query, known_attributes, profile)
            decision, reason = "accepted", ""
            if not query or query == "nan":
                decision, reason = "excluded", "empty_query"
            elif pop is None:
                decision, reason = "excluded", "invalid_or_missing_popularity"
            elif pop < threshold:
                decision, reason = "excluded", "below_threshold"
            elif direct_competitors:
                decision, reason = "excluded", "competitor_brand"
            elif owned_matches:
                decision, reason = "excluded", "other_owned_brand"
            elif unsupported or attribute_conflicts:
                decision, reason = "excluded", "unsupported_claim"
            elif tier == 0:
                decision, reason = "excluded", "irrelevant_to_product"
            elif configured_suspects or unknown:
                decision, reason = "needs_review", "suspected_brand"
            metrics = {str(column): json_value(rec[column]) for column in table.columns if column != "__source_row__"}
            rows.append({
                "query_original": original, "query_normalized": query, "popularity": pop,
                "source_file": str(path), "source_row": int(rec["__source_row__"]),
                "seed_query": source.get("seed_query", ""), "threshold": threshold,
                "category_profile": profile, "categories": cats, "category": cats[0],
                "relevance_tier": tier, "specificity": specificity, "matched_anchors": anchor_names,
                "decision": decision, "reason": reason,
                "brand_matches": direct_competitors or owned_matches or configured_suspects,
                "unknown_brand_candidates": unknown, "unsupported_claims": unsupported,
                "attribute_conflicts": attribute_conflicts,
                "source_metrics": metrics,
            })
    if not rows:
        raise ValueError("config.sources contains no readable rows")

    groups = defaultdict(list)
    for row in rows:
        groups[row["query_normalized"]].append(row)
    canonical, all_rows = [], []
    for group in groups.values():
        candidates = [row for row in group if row["decision"] in {"accepted", "needs_review"}] or group
        winner = max(candidates, key=lambda row: -1 if row["popularity"] is None else row["popularity"])
        merged = dict(winner)
        merged["sources"] = sorted({row["source_file"] for row in group})
        merged["seed_queries"] = sorted({row["seed_query"] for row in group if row["seed_query"]})
        merged["duplicate_count"] = len(group)
        merged["source_records"] = [{"source_file": row["source_file"], "source_row": row["source_row"],
                                     "popularity": row["popularity"], "metrics": row["source_metrics"]} for row in group]
        canonical.append(merged)
        for row in group:
            item = dict(row)
            if row is not winner:
                item["decision"], item["reason"] = "excluded", "duplicate_lower_popularity"
            all_rows.append(item)

    accepted = sorted(
        [row for row in canonical if row["decision"] == "accepted"],
        key=lambda row: (-row["relevance_tier"], -len(row["matched_anchors"]), -row["specificity"], -row["popularity"], row["query_normalized"]),
    )
    for rank, row in enumerate(accepted, 1):
        row["selection_rank"] = rank
        row["selection_basis"] = "relevance_then_anchor_coverage_then_specificity_then_popularity"

    overlaps = []
    for index, left in enumerate(accepted):
        for right in accepted[index + 1:]:
            if contains_token_sequence(left["query_normalized"], right["query_normalized"]) or contains_token_sequence(right["query_normalized"], left["query_normalized"]):
                short, long = sorted([left, right], key=lambda row: len(row["query_normalized"]))
                long_specific = bool(long["matched_anchors"] or long["relevance_tier"] > short["relevance_tier"])
                overlaps.append({
                    "shorter_key": short["query_original"], "longer_key": long["query_original"],
                    "recommendation": "prefer_long_specific" if long_specific else "review",
                    "protected_anchors": long["matched_anchors"],
                })

    output = {
        "schema_version": 2, "product": product, "category_profile": profile, "product_type_terms": type_terms,
        "known_product_attributes": {name: sorted(values, key=str) for name, values in known_attributes.items()},
        "required_product_anchors": anchors, "product_fact_conflicts": conflicts,
        "accepted_rows": accepted,
        "needs_review_rows": [row for row in canonical if row["decision"] == "needs_review"],
        "excluded_canonical_rows": [row for row in canonical if row["decision"] == "excluded"],
        "all_source_rows": all_rows, "source_metadata": source_metadata, "overlaps": overlaps,
        "summary": {
            "source_rows": len(rows), "canonical_keys": len(canonical), "accepted": len(accepted),
            "needs_review": sum(row["decision"] == "needs_review" for row in canonical),
            "excluded": sum(row["decision"] == "excluded" for row in canonical),
            "blocking_fact_conflicts": len(conflicts),
        },
    }
    write_json(args.output, output)
    print(json.dumps(output["summary"], ensure_ascii=False))
    return 0


def audit(args):
    prepared, desc = read_json(args.prepared), read_json(args.descriptions)
    variants = desc.get("variants", [])
    limit = desc.get("limit", prepared.get("product", {}).get("description_limit"))
    if not isinstance(limit, int) or limit <= 0:
        raise ValueError("positive integer limit required")
    overlap_policy = desc.get("overlap_policy", "strict")
    if overlap_policy not in {"strict", "warn", "prefer_specific"}:
        raise ValueError("overlap_policy must be strict, warn, or prefer_specific")
    broad_policy = desc.get("broad_term_policy", "strict")
    if broad_policy not in {"strict", "warn"}:
        raise ValueError("broad_term_policy must be strict or warn")
    product = prepared.get("product", {})
    if "protected_broad_terms" not in desc and "protected_broad_terms" not in product:
        raise ValueError("protected_broad_terms is required; use [] only after lexical-risk review")
    raw_broad_terms = desc.get("protected_broad_terms", product.get("protected_broad_terms"))
    if not isinstance(raw_broad_terms, list):
        raise ValueError("protected_broad_terms must be a list")
    broad_terms = list(dict.fromkeys(norm(value) for value in raw_broad_terms if norm(value)))
    anchors = prepared.get("required_product_anchors", anchor_definitions(product))
    accepted = prepared.get("accepted_rows", [])
    by_key = {row["query_normalized"]: row for row in accepted}
    global_technical_errors = [] if len(variants) == 3 else [f"Expected 3 variants, got {len(variants)}"]
    global_commercial_errors = []

    raw_tiers = desc.get("key_tiers")
    tier_keys = {"core": [], "extension": [], "experimental": []}
    tier_by_key = {}
    if not isinstance(raw_tiers, dict):
        global_technical_errors.append("key_tiers object is required")
    else:
        for tier in tier_keys:
            values = raw_tiers.get(tier)
            if not isinstance(values, list):
                global_technical_errors.append(f"key_tiers.{tier} must be a list")
                continue
            normalized = [norm(value) for value in values if norm(value)]
            tier_keys[tier] = normalized
            if len(normalized) != len(values):
                global_technical_errors.append(f"key_tiers.{tier} contains an empty key")
            if len(normalized) != len(set(normalized)):
                global_technical_errors.append(f"key_tiers.{tier} contains duplicate keys")
            if not normalized:
                global_technical_errors.append(f"key_tiers.{tier} must contain at least 1 key")
            for key in normalized:
                if key not in by_key:
                    global_technical_errors.append(f"Unknown or unaccepted {tier} key: {key}")
                if key in tier_by_key:
                    global_technical_errors.append(
                        f"Key assigned to multiple tiers: {key} ({tier_by_key[key]}, {tier})"
                    )
                else:
                    tier_by_key[key] = tier

    if len(accepted) < 3:
        global_technical_errors.append("Fewer than 3 accepted keywords")
    if prepared.get("needs_review_rows"):
        global_commercial_errors.append(f"Unresolved needs_review rows: {len(prepared['needs_review_rows'])}")
    conflicts = prepared.get("product_fact_conflicts", [])
    if conflicts:
        global_commercial_errors.append(f"Unresolved product fact conflicts: {len(conflicts)}")
    key_sets = [[norm(key) for key in variant.get("keys", [])] for variant in variants]
    if len(key_sets) == 3 and key_sets[0] == key_sets[1] == key_sets[2]:
        global_technical_errors.append("All three variants use an identical keyword set")
    expected_strategies = ["core_strict", "relevant_expansion", "controlled_test"]
    if len(variants) == 3:
        actual_strategies = [variant.get("strategy") for variant in variants]
        if actual_strategies != expected_strategies:
            global_technical_errors.append(
                f"Variant strategies must be ordered as {expected_strategies}, got {actual_strategies}"
            )
        expected_sets = [
            set(tier_keys["core"]),
            set(tier_keys["core"] + tier_keys["extension"]),
            set(tier_keys["core"] + tier_keys["experimental"]),
        ]
        labels = ["Основной", "Расширенный", "Тестовый"]
        for label, actual, expected in zip(labels, key_sets, expected_sets):
            if set(actual) != expected:
                global_technical_errors.append(
                    f"{label} keyword set does not match its declared key tiers"
                )

    results = []
    for number_variant, variant in enumerate(variants, 1):
        text = str(variant.get("text", "")).strip()
        keys = [str(value) for value in variant.get("keys", [])]
        normalized_keys = [norm(value) for value in keys]
        seo_sentence_count = variant.get("seo_sentence_count", len(keys))
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
        technical_errors, technical_warnings = [], []
        commercial_errors, commercial_warnings = [], []
        key_results, broad_results, anchor_results = [], [], []

        if not isinstance(seo_sentence_count, int) or seo_sentence_count < 0:
            technical_errors.append("seo_sentence_count must be a non-negative integer")
            seo_sentence_count = len(keys)
        if seo_sentence_count != len(keys):
            technical_errors.append(f"seo_sentence_count must equal assigned keys: {seo_sentence_count}/{len(keys)}")
        if len(sentences) < seo_sentence_count:
            technical_errors.append(f"Not enough SEO sentences: {len(sentences)}/{seo_sentence_count}")
        ordinary_sentence_count = max(0, len(sentences) - seo_sentence_count)
        if ordinary_sentence_count < 2:
            technical_errors.append(
                f"At least 2 ordinary sentences are required after the SEO block: {ordinary_sentence_count}/2"
            )
        if len(text) > limit:
            technical_errors.append(f"Character limit exceeded: {len(text)} > {limit}")
        if len(normalized_keys) != len(set(normalized_keys)):
            technical_errors.append("Duplicate assigned keys")
        for index, left in enumerate(normalized_keys):
            for right in normalized_keys[index + 1:]:
                if left != right and (contains(left, right) or contains(right, left)):
                    technical_errors.append(f"Nested assigned keys: {left} / {right}")
        if any(value not in by_key for value in normalized_keys):
            technical_errors.append("Unknown or unaccepted assigned key")
        popularities = [by_key[value].get("popularity") for value in normalized_keys if value in by_key]
        if any(not isinstance(value, (int, float)) for value in popularities):
            technical_errors.append("Assigned keys must have numeric popularity")
        elif any(left < right for left, right in zip(popularities, popularities[1:])):
            technical_errors.append("Keys are not ordered as a descending popularity ladder")

        normalized_text = norm(text)
        for sentence_number, sentence in enumerate(sentences, 1):
            for label, meta_pattern in META_COPY_PATTERNS:
                match = meta_pattern.search(sentence)
                if match:
                    technical_errors.append(f"Sentence {sentence_number} contains internal SEO copy ({label}): {match.group(0)}")

        previous_popularity = None
        for position, key in enumerate(keys, 1):
            normalized_key = norm(key)
            key_popularity = by_key.get(normalized_key, {}).get("popularity")
            actual = len(pattern(normalized_key).findall(normalized_text))
            induced = sum(len(pattern(normalized_key).findall(norm(other))) for other in keys)
            expected = induced if overlap_policy == "prefer_specific" else 1
            status, issue = "pass", ""
            if actual < expected:
                status, issue = "error", "missing"
                technical_errors.append(f"Key {position} missing or obscured: {key} ({actual}/{expected})")
            elif actual > expected:
                issue = "extra_repeat"
                message = f"Key {position} has {actual - expected} extra occurrence(s): {key}"
                if overlap_policy == "warn":
                    status = "warning"
                    technical_warnings.append(message)
                else:
                    status = "error"
                    technical_errors.append(message)
            if position <= seo_sentence_count and position <= len(sentences):
                sentence = norm(sentences[position - 1])
                if not sentence.startswith(normalized_key):
                    status, issue = "error", "wrong_start"
                    technical_errors.append(f"SEO sentence {position} does not start with key")
                if len(sentence[len(normalized_key):].strip(" ,:;—-–.!?")) < 4:
                    status, issue = "error", "no_continuation"
                    technical_errors.append(f"SEO sentence {position} has no continuation")
            key_results.append({
                "position": position, "key": key, "popularity": by_key.get(normalized_key, {}).get("popularity"),
                "popularity_change": None if previous_popularity is None or key_popularity is None else key_popularity - previous_popularity,
                "relevance_tier": by_key.get(normalized_key, {}).get("relevance_tier"),
                "selection_rank": by_key.get(normalized_key, {}).get("selection_rank"),
                "key_role": tier_by_key.get(normalized_key, "unassigned"),
                "occurrences": actual, "expected_occurrences": expected, "status": status, "issue": issue,
            })
            previous_popularity = key_popularity

        for term in broad_terms:
            allowed = sum(len(pattern(term).findall(norm(key))) for key in keys)
            actual = len(pattern(term).findall(normalized_text))
            extra = max(0, actual - allowed)
            status = "pass"
            if extra:
                status = "error" if broad_policy == "strict" else "warning"
                message = f"Protected broad term '{term}' has {extra} extra occurrence(s): {actual} actual, {allowed} allowed by assigned keys"
                if broad_policy == "strict":
                    technical_errors.append(message)
                else:
                    technical_warnings.append(message)
            broad_results.append({"term": term, "actual": actual, "allowed": allowed, "extra": extra, "status": status})

        for anchor in anchors:
            aliases = anchor.get("aliases", [])
            in_text = [alias for alias in aliases if anchor_contains(normalized_text, alias)]
            in_keys = [alias for alias in aliases if any(anchor_contains(key, alias) for key in normalized_keys)]
            covered = bool(in_text or in_keys)
            status = "pass" if covered else ("error" if anchor.get("required", True) else "warning")
            if not covered:
                message = f"Missing product anchor: {anchor.get('label', anchor.get('name'))}"
                if anchor.get("required", True):
                    commercial_errors.append(message)
                else:
                    commercial_warnings.append(message)
            anchor_results.append({
                "name": anchor.get("name"), "label": anchor.get("label"), "required": anchor.get("required", True),
                "covered": covered, "matched_in_text": in_text, "matched_in_keys": in_keys, "status": status,
            })

        technical_status = "pass" if not technical_errors else "error"
        commercial_status = "pass" if not commercial_errors and not global_commercial_errors else "error"
        results.append({
            "name": variant.get("name", f"Variant {number_variant}"), "strategy": variant.get("strategy"),
            "characters": len(text), "limit": limit, "remaining": limit - len(text),
            "seo_sentence_count": seo_sentence_count, "ordinary_sentence_count": ordinary_sentence_count,
            "total_sentences": len(sentences),
            "technical_status": technical_status, "commercial_status": commercial_status,
            "status": "pass" if technical_status == commercial_status == "pass" else "error",
            "technical_errors": technical_errors, "technical_warnings": technical_warnings,
            "commercial_errors": commercial_errors, "commercial_warnings": commercial_warnings,
            "errors": technical_errors + commercial_errors, "warnings": technical_warnings + commercial_warnings,
            "keys": key_results, "broad_terms": broad_results, "anchors": anchor_results,
        })

    technical_status = "pass" if not global_technical_errors and all(item["technical_status"] == "pass" for item in results) else "error"
    commercial_status = "pass" if not global_commercial_errors and all(item["commercial_status"] == "pass" for item in results) else "error"
    output = {
        "schema_version": 3, "overlap_policy": overlap_policy, "broad_term_policy": broad_policy,
        "key_tiers": tier_keys,
        "protected_broad_terms": broad_terms, "technical_status": technical_status,
        "commercial_status": commercial_status,
        "global_status": "pass" if technical_status == commercial_status == "pass" else "error",
        "global_technical_errors": global_technical_errors,
        "global_commercial_errors": global_commercial_errors,
        "global_errors": global_technical_errors + global_commercial_errors, "variants": results,
    }
    write_json(args.output, output)
    error_count = len(output["global_errors"]) + sum(len(item["errors"]) for item in results)
    warning_count = sum(len(item["warnings"]) for item in results)
    print(json.dumps({"global_status": output["global_status"], "technical_status": technical_status,
                      "commercial_status": commercial_status, "errors": error_count,
                      "warnings": warning_count}, ensure_ascii=False))
    return 0 if output["global_status"] == "pass" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--config", required=True)
    prepare_parser.add_argument("--output", required=True)
    prepare_parser.set_defaults(func=prepare)
    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--prepared", required=True)
    audit_parser.add_argument("--descriptions", required=True)
    audit_parser.add_argument("--output", required=True)
    audit_parser.set_defaults(func=audit)
    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
