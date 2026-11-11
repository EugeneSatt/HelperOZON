"""Offline behavioral checks. All inputs are explicitly synthetic."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from analyze import METRICS, analyze, private_funnel


def fixture(peer_count=5):
    sources = []
    products = []
    for i in range(peer_count + 1):
        sid = f"synthetic-{i}"
        sources.append({
            "id": sid, "kind": "export", "file": f"synthetic-{i}.json",
            "captured_at": "2026-10-26T14:00:00+03:00",
            "locator": f"Synthetic fixture, Ozon SKU={1000 + i}",
        })
        values = {}
        for metric, _, _, _, kind in METRICS:
            value = True if kind == "bool" else "white_studio" if kind == "text" else 0.1 if kind == "fraction" else 4.8 if kind == "rating" else 10
            values[metric] = {
                "value": value, "source_id": sid, "basis": f"synthetic_{metric}",
                "scope": "sku", "period": ["2026-09-26", "2026-10-25"],
                "region": "Москва" if metric == "search_position" else None,
                "query_set": ["synthetic query"] if metric == "search_position" else None,
            }
        products.append({"sku": str(1000 + i), "role": "own" if i == 0 else "competitor", "metrics": values, "name": "Условный товар", "seller": f"Продавец {i}", "variant": "1 шт., модель А", "identity_source_id": sid})
    return {
        "meta": {"own_sku": "1000", "period_start": "2026-09-26", "period_end": "2026-10-25", "collected_at": "2026-10-26T14:00:00+03:00"},
        "sources": sources, "products": products,
    }


def row(result, metric):
    return next(r for r in result["rows"] if r["metric_id"] == metric)


class ComparisonTests(unittest.TestCase):
    def test_offer_identity_requires_seller_variant_and_evidence(self):
        for key in ('seller', 'variant', 'identity_source_id'):
            data = fixture()
            del data['products'][1][key]
            with self.assertRaises(ValueError):
                analyze(data)

    def test_ozon_card_price_is_money_and_never_scores(self):
        data = fixture()
        data['products'][0]['metrics']['ozon_card_price']['value'] = 2350
        result = row(analyze(data), 'ozon_card_price')
        self.assertEqual(result['own']['value'], 2350)
        self.assertFalse(result['included_in_score'])

    def test_content_findings_work_without_fabricated_numeric_metric(self):
        data = fixture(0)
        for product in data['products']:
            product['metrics'] = {}
        data['findings'] = [{
            'metric_id': 'rich_content', 'fact': 'Синтетическое наблюдение блока комплектации.',
            'hypothesis': 'Вопрос о комплектации может остаться открытым.',
            'action': 'Показать подтверждённый состав набора.',
            'verification': 'Сравнить вопросы о комплектации до и после правки.',
            'source_ids': ['synthetic-0'],
        }]
        result = analyze(data)
        self.assertIsNone(result['score']['value'])
        self.assertEqual(result['findings'][0]['metric_id'], 'rich_content')

    def test_private_funnel_cannot_leak_another_sku_account_or_period(self):
        for key, invalid in [('sku', '9000'), ('account', 'Другой кабинет'), ('period', ['2026-09-25', '2026-10-24']), ('source_id', None), ('ctr', 12), ('orders', 0.5)]:
            data = fixture()
            data['meta']['cabinet'] = 'Демонстрационный кабинет'
            data['private_funnel'] = {'sku': '1000', 'account': data['meta']['cabinet'],
                                     'period': ['2026-09-26', '2026-10-25'], 'source_id': 'synthetic-0',
                                     'orders': 0, 'ctr': 0}
            self.assertEqual(private_funnel(data)['orders'], 0)
            data['private_funnel'][key] = invalid
            with self.assertRaises(ValueError):
                analyze(data)

    def test_full_coverage(self):
        result = analyze(fixture())
        self.assertEqual((result["score"]["value"], result["score"]["counted_metrics"], result["score"]["counted_weight"], result["score"]["counted_key_metrics"]), (100, 14, 18, 4))
        self.assertFalse(result["score"]["partial"])
        self.assertEqual(len(result["rows"]), 18)

    def test_missing_core_is_visible(self):
        data = fixture()
        for product in data["products"]:
            for key in ("ctr", "cart_to_order", "card_to_cart"):
                product["metrics"][key] = {"value": None, "missing_reason": "Not available in synthetic test"}
        score = analyze(data)["score"]
        self.assertTrue(score["partial"])
        self.assertEqual((score["value"], score["counted_metrics"], score["counted_weight"], score["counted_key_metrics"]), (100, 11, 12, 1))
        self.assertEqual(set(score["excluded_metrics"]), {"ctr", "cart_to_order", "card_to_cart"})

    def test_zero_negative_share_is_best(self):
        data = fixture()
        data["products"][0]["metrics"]["negative_share"]["value"] = 0
        self.assertEqual(row(analyze(data), "negative_share")["status"], "green")

    def test_zero_baseline_no_division_by_zero(self):
        data = fixture()
        for product in data["products"]:
            product["metrics"]["negative_share"]["value"] = 0
        data["products"][0]["metrics"]["negative_share"]["value"] = 0.1
        result = row(analyze(data), "negative_share")
        self.assertEqual(result["status"], "red")
        self.assertIsNone(result["gap_fraction"])
        self.assertEqual(result["absolute_difference"], 0.1)

    def test_unavailable_position_never_zero(self):
        data = fixture()
        data["products"][0]["metrics"]["search_position"]["value"] = 0
        with self.assertRaisesRegex(ValueError, "позиция 0"):
            analyze(data)

    def test_mixed_definitions_excluded(self):
        data = fixture()
        data["products"][0]["metrics"]["revenue"]["basis"] = "actual_ozon_delivered_rub"
        result = row(analyze(data), "revenue")
        self.assertFalse(result["included_in_score"])
        self.assertIsNone(result["median"])
        self.assertIn("basis", result["competitors"][0]["reason"])

    def test_period_and_scope_mismatch_excluded(self):
        for key, value in (("period", ["2026-09-25", "2026-10-24"]), ("scope", "merged_card")):
            data = fixture()
            for product in data["products"][1:]:
                product["metrics"]["reviews_count"][key] = value
            result = row(analyze(data), "reviews_count")
            self.assertEqual(result["comparable_competitors"], 0)
            self.assertFalse(result["included_in_score"])

    def test_small_manual_set_has_no_composite_score(self):
        result = analyze(fixture(peer_count=2))
        self.assertIsNone(result["score"]["value"])
        self.assertEqual(row(result, "photos_count")["status"], "yellow")

    def test_binary_uses_actual_peer_count(self):
        data = fixture(peer_count=3)
        data["products"][0]["metrics"]["has_video"]["value"] = False
        data["products"][3]["metrics"]["has_video"]["value"] = False
        self.assertEqual(row(analyze(data), "has_video")["status"], "red")
        data["products"][2]["metrics"]["has_video"]["value"] = False
        self.assertEqual(row(analyze(data), "has_video")["status"], "yellow")

    def test_unknown_boolean_and_missing_evidence(self):
        data = fixture()
        data["products"][0]["metrics"]["has_video"] = {"value": None, "missing_reason": "Image unavailable"}
        data["products"][0]["metrics"]["photos_count"]["source_id"] = "unregistered"
        result = analyze(data)
        self.assertEqual(row(result, "has_video")["status"], "nodata")
        self.assertFalse(row(result, "photos_count")["included_in_score"])

    def test_region_queries_and_snapshot_age(self):
        for field, value in (("region", "Казань"), ("query_set", ["another query"])):
            data = fixture()
            for product in data["products"][1:]:
                product["metrics"]["search_position"][field] = value
            self.assertFalse(row(analyze(data), "search_position")["included_in_score"])
        data = fixture()
        for product in data["products"]:
            product["metrics"]["photos_count"]["period"] = "snapshot"
        for source in data["sources"][1:]:
            source["captured_at"] = "2026-10-24T14:00:00+03:00"
        self.assertFalse(row(analyze(data), "photos_count")["included_in_score"])

    def test_duplicate_id_rejected(self):
        data = fixture()
        data["products"][1]["sku"] = data["products"][0]["sku"]
        with self.assertRaisesRegex(ValueError, "Повтор Ozon SKU"):
            analyze(data)

    def test_incomplete_source_keeps_value_but_excludes_score(self):
        data = fixture()
        obs = data["products"][0]["metrics"]["revenue"]
        obs.update(value=12345, comparison_eligible=False,
                   comparison_exclusion_reason="Неполное наблюдение FBO")
        result = row(analyze(data), "revenue")
        self.assertEqual(result["own"]["value"], 12345)
        self.assertFalse(result["included_in_score"])
        self.assertIn("FBO", result["excluded_reason"])

    def test_percent_units_and_non_finite_values_rejected(self):
        for invalid in (25, float("nan"), float("inf"), "0.25", True):
            data = fixture()
            data["products"][0]["metrics"]["ctr"]["value"] = invalid
            with self.assertRaises(ValueError):
                analyze(data)

    def test_exact_five_percent_boundary_and_weight(self):
        data = fixture()
        data["products"][0]["metrics"]["ctr"]["value"] = 0.095
        self.assertEqual(row(analyze(data), "ctr")["status"], "yellow")
        data["products"][0]["metrics"]["ctr"]["value"] = 0.094
        score = analyze(data)["score"]
        self.assertEqual((score["value"], score["passed_weight"]), (89, 16))

    def test_empty_data_never_returns_healthy_zero(self):
        data = fixture()
        for product in data["products"]:
            product["metrics"] = {}
        score = analyze(data)["score"]
        self.assertIsNone(score["value"])
        self.assertEqual(score["counted_metrics"], 0)
        self.assertEqual(len(score["excluded_metrics"]), 14)

    def test_command_line_writes_valid_json_and_preserves_input(self):
        script = Path(__file__).with_name("analyze.py")
        with tempfile.TemporaryDirectory() as work:
            source = Path(work) / "audit.json"
            output = Path(work) / "comparison.json"
            raw = json.dumps(fixture(), ensure_ascii=False)
            source.write_text(raw, encoding="utf-8")
            result = subprocess.run([sys.executable, str(script), str(source), "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text())["score"]["value"], 100)
            self.assertEqual(source.read_text(encoding="utf-8"), raw)
            blocked = subprocess.run([sys.executable, str(script), str(source), "--output", str(source)], capture_output=True, text=True)
            self.assertEqual(blocked.returncode, 2)
            self.assertEqual(source.read_text(encoding="utf-8"), raw)


if __name__ == "__main__":
    unittest.main()
