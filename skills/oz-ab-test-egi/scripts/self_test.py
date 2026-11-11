#!/usr/bin/env python3
"""Offline synthetic scenarios; never opens a browser or changes a seller cabinet."""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image
import ledger
import workflow as w


class Scenarios(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='oz-ab-offline-')
        self.root = Path(self.tmp.name)
        self.at = datetime.fromisoformat('2026-10-28T12:00:00+03:00')
        self.old_now = w.now
        w.now = lambda: self.at
        self.raw = self.root / 'synthetic-source.txt'
        self.raw.write_text('SYNTHETIC OFFLINE FIXTURE. No real seller data.')
        self.original = self.root / 'original.png'
        self.new = self.root / 'new.png'
        Image.new('RGB', (750, 1000), '#A8CEDF').save(self.original)
        Image.new('RGB', (750, 1000), '#EDA4B9').save(self.new)
        self.seq = 0

    def tearDown(self):
        w.now = self.old_now
        self.tmp.cleanup()

    def contract(self, source):
        return {'definition_id': source + '-test-definition', 'scope_id': source + '-fixed-sku',
                'metric_name': 'SYNTHETIC CTR', 'numerator_label': 'Переходы', 'denominator_label': 'Показы',
                'traffic_scope': 'SYNTHETIC exact SKU', 'unit': 'events', 'granularity': 'intraday',
                'settled_day_report_available': True, 'intraday_probe_passed': True}

    def setup_data(self, ads=False, mode='intraday_counts'):
        contracts = {'funnel': self.contract('funnel')}
        if ads:
            contracts['ads'] = self.contract('ads')
        data = {'test_id': 'SELF-TEST', 'title': 'ИСКУССТВЕННЫЕ ДАННЫЕ / проверка скилла', 'original': str(self.original),
                'image_generation_authorized': True,
                'config': {'target_funnel_ctr': 3, 'use_ad_ctr': ads, 'target_ad_ctr': 2, 'views_per_interval': 1000,
                           'ad_views_per_interval': 1000, 'mode': mode, 'min_hours': .5, 'max_interval_hours': 168,
                           'cycles': 2, 'confirmation_multiplier': 1, 'max_generations': 2, 'finish_policy': 'leader',
                           'price_tolerance_pct': 0, 'accept_approximate_boundaries': True},
                'binding': {'seller': 'SYNTHETIC-SELLER', 'sku': 'SYNTHETIC-SKU', 'timezone': 'Europe/Moscow',
                            'media_order': ['Фото 2: SYNTHETIC'], 'sources': contracts}}
        stub = {'binding': data['binding'], 'variants': {'A': {'sha256': w.sha(self.original)}}}
        data['probe'] = self.observation(stub, {'funnel': (1200, 30), **({'ads': (1200, 30)} if ads else {})})
        return data

    def cover(self, state, variant='A'):
        return {'seller': state['binding']['seller'], 'sku': state['binding']['sku'], 'timezone': 'Europe/Moscow',
                'observed_at': (self.at - timedelta(seconds=2)).isoformat(), 'variant_sha256': state['variants'][variant]['sha256'],
                'first_image_matches': True, 'other_media_unchanged': True, 'media_order': ['Фото 2: SYNTHETIC'],
                'reopened': True, 'evidence': [str(self.raw)],
                'conditions': {'price': 1000, 'currency': 'RUB', 'region': 'Москва', 'payment': 'Другие банки',
                               'promotion': 'Нет', 'available': True, 'delivery': '2 дня'}}

    def row(self, state, source, views, clicks, day=None, settled=False):
        contract = state['binding']['sources'][source]
        return {'source': source, 'definition_id': contract['definition_id'], 'scope_id': contract['scope_id'],
                'date': day or self.at.date().isoformat(), 'captured_at': (self.at - timedelta(seconds=1)).isoformat(),
                'settled': settled, 'views': views, 'clicks': clicks, 'url': 'https://example.invalid/SYNTHETIC', 'evidence': [str(self.raw)]}

    def observation(self, state, values, variant='A', extra=None):
        self.seq += 1
        return {'observation_id': 'test-' + str(self.seq), 'seller': state['binding']['seller'], 'sku': state['binding']['sku'],
                'timezone': 'Europe/Moscow', 'observed_at': self.at.isoformat(), 'cover': self.cover(state, variant),
                'rows': [self.row(state, source, *counts) for source, counts in values.items()] + (extra or [])}

    def prepared(self, ads=False, mode='intraday_counts', one_pass=False):
        data = self.setup_data(ads, mode)
        if one_pass:
            del data['config']['cycles']
            del data['config']['confirmation_multiplier']
        state = w.initialize(self.root, data)
        w.add_variant(self.root, state, {'id': 'B', 'file': str(self.new), 'label': 'Новая', 'hypothesis': 'SYNTHETIC contrast', 'source': 'provided', 'approved': True})
        return state

    def publish(self, state, values=None):
        pending = state['pending']
        if pending['variant'] != state['on_card']:
            pre = self.cover(state, state['on_card'])
            pre['intent_id'] = pending['id']
            w.begin_ui(self.root, state, pre)
        proof = self.cover(state, pending['variant'])
        proof.update(intent_id=pending['id'], no_upload_needed=pending['variant'] == state['on_card'])
        if pending['purpose'] == 'interval' and state['config']['mode'] == 'intraday_counts':
            if values is None:
                values = {source: (state['days'][source][self.at.date().isoformat()]['views'], state['days'][source][self.at.date().isoformat()]['clicks']) for source in ledger.sources(state)}
            proof['snapshot'] = self.observation(state, values, pending['variant'])
        w.confirm(self.root, state, proof)

    def running(self, ads=False, mode='intraday_counts'):
        state = self.prepared(ads, mode)
        w.start(state, {'active_test_authorized': True})
        self.publish(state)
        return state

    def test_midnight_zero_and_final_yesterday(self):
        self.at = self.at.replace(hour=23)
        s = self.running()
        self.at += timedelta(minutes=55)
        w.observe(self.root, s, self.observation(s, {'funnel': (2000, 50)}))
        self.at = self.at.replace(hour=0, minute=0, second=5) + timedelta(days=1)
        w.observe(self.root, s, self.observation(s, {'funnel': (0, 0)}))
        self.assertEqual(w.next_action(s)['action'], 'collect_closed_days')
        self.at += timedelta(hours=8)
        yesterday = self.row(s, 'funnel', 2100, 54, '2026-10-28', True)
        w.observe(self.root, s, self.observation(s, {'funnel': (100, 6)}, extra=[yesterday]))
        m, at, _ = w.calculation(s)
        self.assertEqual(m['sources']['funnel']['views'], 1000)
        self.assertEqual(m['sources']['funnel']['clicks'], 30)
        self.assertEqual(m['sources']['funnel']['ctr'], 3)
        self.assertTrue(ledger.ready(s, s['current'], m, at))

    def test_missing_history_blocks_close(self):
        s = self.running()
        self.at += timedelta(days=1)
        w.observe(self.root, s, self.observation(s, {'funnel': (5000, 200)}))
        with self.assertRaises(ValueError): w.close_interval(s)

    def unique_period_state(self):
        data = self.setup_data(mode='whole_days')
        data['binding']['sources']['funnel'].update(unit='period_unique', granularity='period')
        row = data['probe']['rows'][0]
        row.update(date='2026-10-27', period_start='2026-10-27', settled=True)
        s = w.initialize(self.root, data)
        w.add_variant(self.root, s, {'id':'B','file':str(self.new),'label':'Новая','hypothesis':'SYNTHETIC','source':'provided','approved':True})
        w.start(s, {'active_test_authorized':True})
        self.publish(s)
        return s

    def unique_period_observation(self, s, first, last, views, clicks):
        obs = self.observation(s, {'funnel':(views, clicks)})
        obs['rows'][0].update(period_start=first, date=last, settled=True)
        return obs

    def test_unique_period_uses_deduplicated_period_not_sum_of_days(self):
        s = self.unique_period_state()
        self.at += timedelta(days=3)
        for first,last,v,c in [('2026-10-29','2026-10-29',900,90),('2026-10-30','2026-10-30',900,90),('2026-10-29','2026-10-30',1200,100)]:
            w.observe(self.root,s,self.unique_period_observation(s,first,last,v,c))
        m,at,_ = w.calculation(s)
        self.assertEqual(m['sources']['funnel']['views'],1200)
        self.assertEqual(m['sources']['funnel']['clicks'],100)
        self.assertTrue(ledger.ready(s,s['current'],m,at))

    def test_unique_daily_rows_cannot_replace_missing_period(self):
        s=self.unique_period_state()
        self.at += timedelta(days=3)
        for day in ('2026-10-29','2026-10-30'):
            w.observe(self.root,s,self.unique_period_observation(s,day,day,900,90))
        m,_,_=w.calculation(s)
        self.assertTrue(m['missing'])
        self.assertEqual(m['sources']['funnel']['views'],0)
        with self.assertRaises(ValueError):w.close_interval(s)

    def test_unique_period_excludes_start_day_and_current_day(self):
        s=self.unique_period_state()
        self.at += timedelta(days=2)
        w.observe(self.root,s,self.unique_period_observation(s,'2026-10-28','2026-10-29',5000,500))
        self.assertTrue(w.calculation(s)[0]['missing'])
        w.observe(self.root,s,self.unique_period_observation(s,'2026-10-29','2026-10-29',1107,287))
        m,_,_=w.calculation(s)
        self.assertFalse(m['missing'])
        self.assertAlmostEqual(m['sources']['funnel']['ctr'],287/1107*100)

    def test_unique_period_correction_of_closed_interval_pauses(self):
        s=self.unique_period_state()
        self.at += timedelta(days=2)
        w.observe(self.root,s,self.unique_period_observation(s,'2026-10-29','2026-10-29',1107,287))
        w.close_interval(s)
        self.at += timedelta(minutes=1)
        w.observe(self.root,s,self.unique_period_observation(s,'2026-10-29','2026-10-29',1100,280))
        self.assertEqual(s['status'],'paused_attention')

    def test_unique_period_rejects_intraday_mode_and_future_period(self):
        data=self.setup_data()
        data['binding']['sources']['funnel']['unit']='period_unique'
        with self.assertRaises(ValueError):w.validate_config(data)
        s=self.unique_period_state()
        obs=self.unique_period_observation(s,'2026-10-28','2026-10-27',1,0)
        with self.assertRaises(ValueError):w.observe(self.root,s,obs)

    def test_all_skipped_days_required(self):
        s = self.running()
        self.at += timedelta(days=3)
        w.observe(self.root, s, self.observation(s, {'funnel': (1000, 30)}, extra=[self.row(s, 'funnel', 2200, 60, '2026-10-28', True)]))
        missing = w.calculation(s)[0]['missing']
        self.assertEqual([x['date'] for x in missing], ['2026-10-29', '2026-10-30'])

    def test_same_date_counter_decrease_rejected(self):
        s = self.running()
        self.at += timedelta(hours=1)
        with self.assertRaises(ValueError): w.observe(self.root, s, self.observation(s, {'funnel': (0, 0)}))

    def test_repeated_observation_is_idempotent(self):
        s = self.running()
        self.at += timedelta(hours=1)
        observation = self.observation(s, {'funnel': (2200, 60)})
        w.observe(self.root, s, observation)
        before = deepcopy(s)
        self.assertFalse(w.observe(self.root, s, observation))
        self.assertEqual(s, before)
        observation['rows'][0]['views'] = 2300
        with self.assertRaises(ValueError): w.observe(self.root, s, observation)

    def test_yesterday_upsert_not_double_count(self):
        s = self.running()
        self.at += timedelta(days=1)
        w.observe(self.root, s, self.observation(s, {'funnel': (100, 3)}, extra=[self.row(s, 'funnel', 2100, 54, '2026-10-28', True)]))
        self.at += timedelta(minutes=1)
        w.observe(self.root, s, self.observation(s, {'funnel': (100, 3)}, extra=[self.row(s, 'funnel', 2200, 58, '2026-10-28', True)]))
        self.assertEqual(w.calculation(s)[0]['sources']['funnel']['views'], 1100)
        self.assertEqual(s['status'], 'running')

    def test_ads_off_does_not_require_ads(self):
        s = self.running()
        self.at += timedelta(hours=1)
        w.observe(self.root, s, self.observation(s, {'funnel': (2200, 70)}))
        self.assertEqual(w.next_action(s)['action'], 'close_interval')
        self.assertEqual(ledger.sources(s), ['funnel'])

    def test_ads_requires_own_sample(self):
        s = self.running(ads=True)
        self.at += timedelta(hours=1)
        w.observe(self.root, s, self.observation(s, {'funnel': (2200, 70), 'ads': (1300, 40)}))
        self.assertFalse(ledger.ready(s, s['current'], w.calculation(s)[0], self.at.isoformat()))

    def test_both_targets_required(self):
        s = self.prepared(ads=True)
        values = {'sources': {'funnel': {'ctr': 5}, 'ads': {'ctr': 1}}}
        self.assertFalse(ledger.passes(s, values))
        values['sources']['ads']['ctr'] = 2
        self.assertTrue(ledger.passes(s, values))

    def test_daily_unique_cannot_use_intraday(self):
        data = self.setup_data()
        data['binding']['sources']['funnel']['unit'] = 'daily_unique'
        with self.assertRaises(ValueError): w.validate_config(data)

    def test_daily_unique_requires_agreement(self):
        data = self.setup_data(mode='whole_days')
        data['binding']['sources']['funnel']['unit'] = 'daily_unique'
        with self.assertRaises(ValueError): w.validate_config(data)
        data['config']['daily_unique_aggregation_accepted'] = True
        w.validate_config(data)

    def test_whole_days_excludes_switch_date(self):
        s = self.running(mode='whole_days')
        self.at += timedelta(days=2)
        rows = [self.row(s, 'funnel', 9000, 900, '2026-10-28', True), self.row(s, 'funnel', 1000, 40, '2026-10-29', True)]
        w.observe(self.root, s, self.observation(s, {'funnel': (500, 40)}, extra=rows))
        m = w.calculation(s)[0]
        self.assertEqual(m['sources']['funnel']['views'], 1000)
        self.assertEqual(m['sources']['funnel']['clicks'], 40)

    def test_future_date_cannot_be_settled(self):
        s = self.prepared()
        row = self.row(s, 'funnel', 1000, 40, settled=True)
        with self.assertRaises(ValueError): ledger.validate_row(s, row)

    def test_scope_change_rejected(self):
        s = self.running()
        ob = self.observation(s, {'funnel': (2200, 70)})
        ob['rows'][0]['scope_id'] = 'another-campaign-or-filter'
        with self.assertRaises(ValueError): w.observe(self.root, s, ob)

    def test_wrong_sku_rejected(self):
        s = self.running()
        ob = self.observation(s, {'funnel': (2200, 70)})
        ob['sku'] = 'ANOTHER'
        with self.assertRaises(ValueError): w.observe(self.root, s, ob)

    def test_no_active_start_without_authorization(self):
        s = self.prepared()
        with self.assertRaises(ValueError): w.start(s, {'active_test_authorized': False})

    def test_only_one_ui_attempt(self):
        s = self.prepared()
        w.start(s, {'active_test_authorized': True})
        w.request(s, 'B')
        p = self.cover(s, 'A')
        p['intent_id'] = s['pending']['id']
        w.begin_ui(self.root, s, p)
        with self.assertRaises(ValueError): w.begin_ui(self.root, s, p)
        self.assertEqual(w.next_action(s)['action'], 'verify_cover')

    def test_confirm_requires_registered_change(self):
        s = self.prepared()
        w.start(s, {'active_test_authorized': True})
        w.request(s, 'B')
        p = self.cover(s, 'B')
        p['intent_id'] = s['pending']['id']
        with self.assertRaises(ValueError): w.confirm(self.root, s, p)

    def test_price_change_pauses_and_excludes_interval(self):
        s = self.running()
        self.at += timedelta(hours=1)
        ob = self.observation(s, {'funnel': (2200, 70)})
        ob['cover']['conditions']['price'] = 900
        w.observe(self.root, s, ob)
        self.assertEqual(s['status'], 'paused_attention')
        self.assertTrue(s['current']['excluded'])

    def test_resume_new_conditions_starts_new_epoch(self):
        s = self.running()
        s['leader'] = 'B'
        self.at += timedelta(minutes=1)
        ob = self.observation(s, {'funnel': (2200, 70)})
        ob['cover']['conditions']['price'] = 900
        w.observe(self.root, s, ob)
        p = self.cover(s)
        p['conditions']['price'] = 900
        w.resume(self.root, s, {'resume_authorized': True, 'cover': p})
        self.assertEqual(s['epoch'], 2)
        self.assertNotIn('leader', s)
        self.assertEqual(ledger.summary(s, 'exploration'), {})

    def test_correction_revokes_closed_result(self):
        s = self.running()
        self.at += timedelta(days=1)
        w.observe(self.root, s, self.observation(s, {'funnel': (100, 6)}, extra=[self.row(s, 'funnel', 2100, 54, '2026-10-28', True)]))
        w.close_interval(s)
        s['goal_reached'] = True
        self.at += timedelta(minutes=1)
        w.observe(self.root, s, self.observation(s, {'funnel': (100, 6)}, extra=[self.row(s, 'funnel', 2200, 58, '2026-10-28', True)]))
        self.assertFalse(s['goal_reached'])
        self.assertEqual(s['status'], 'paused_attention')

    def test_complete_flow_requires_fresh_confirmation_and_final_cover(self):
        s = self.running()
        views, clicks = 1200, 30
        for _ in range(6):
            self.assertEqual(s['status'], 'running')
            self.at += timedelta(hours=1)
            views += 1000
            clicks += 20 if s['on_card'] == 'A' else 40
            w.observe(self.root, s, self.observation(s, {'funnel': (views, clicks)}, s['on_card']))
            w.close_interval(s)
            self.assertFalse(s['goal_reached'])
            self.publish(s)
        self.assertEqual(s['status'], 'finished')
        self.assertTrue(s['goal_reached'])
        self.assertEqual(s['on_card'], 'B')
        self.assertEqual(ledger.summary(s, 'confirmation')['B']['sources']['funnel']['views'], 1000)

    def test_one_pass_finishes_without_opening_a_second_interval_for_either_cover(self):
        s = self.prepared(one_pass=True)
        w.start(s, {'active_test_authorized': True})
        self.assertEqual(s['plan'], ['A', 'B'])
        self.publish(s)
        for variant, totals in [('A', (2200, 50)), ('B', (3200, 90))]:
            self.at += timedelta(hours=1)
            w.observe(self.root, s, self.observation(s, {'funnel': totals}, variant))
            w.close_interval(s)
            self.assertFalse(s['goal_reached'])
            self.publish(s)
        self.assertEqual(s['status'], 'finished')
        self.assertTrue(s['goal_reached'])
        self.assertEqual(s['on_card'], 'B')
        self.assertEqual([interval['variant'] for interval in s['intervals']], ['A', 'B'])
        self.assertEqual(ledger.summary(s, 'confirmation'), {})

    def test_time_limit_is_not_success(self):
        s = self.running()
        self.at += timedelta(hours=169)
        self.assertEqual(w.next_action(s)['action'], 'pause')
        self.assertFalse(s['goal_reached'])

    def test_stop_restores_without_statistics(self):
        s = self.running()
        w.stop(s, {'stop_authorized': True, 'variant': 'A'})
        s['days'] = {}
        self.publish(s)
        self.assertEqual(s['status'], 'finished')
        self.assertFalse(s['goal_reached'])

    def test_generation_reservation_limit_and_repeat(self):
        s = self.prepared()
        data = {'operation': 'reserve', 'name': 'concept-1', 'prompt': 'SYNTHETIC', 'hypothesis': 'SYNTHETIC'}
        w.generation(self.root, s, data)
        with self.assertRaises(ValueError): w.generation(self.root, s, data)
        w.generation(self.root, s, {'operation': 'fail', 'name': 'concept-1', 'reason': 'SYNTHETIC'})
        data['name'] = 'concept-2'
        w.generation(self.root, s, data)
        w.generation(self.root, s, {'operation': 'complete', 'name': 'concept-2', 'file': str(self.new)})
        data['name'] = 'concept-3'
        with self.assertRaises(ValueError): w.generation(self.root, s, data)

    def test_report_is_standalone_and_escaped(self):
        s = self.prepared()
        s['title'] = '<script>alert(1)</script>'
        from dashboard import render
        html = render(self.root, s).read_text()
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertIn('data:font/ttf;base64,', html)
        self.assertIn('data:image/jpeg;base64,', html)
        self.assertNotIn('{{', html)
        self.assertNotIn('src="https://', html)

    def test_stale_snapshot_rejected(self):
        s = self.prepared()
        ob = self.observation(s, {'funnel': (2200, 70)})
        ob['observed_at'] = (self.at - timedelta(hours=1)).isoformat()
        with self.assertRaises(ValueError): w.observe(self.root, s, ob)

    def test_media_order_change_rejected(self):
        s = self.prepared()
        p = self.cover(s)
        p['media_order'] = []
        with self.assertRaises(ValueError): w.proof(self.root, s, p, 'A')

    def test_stop_after_interrupted_upload_reconciles_actual_cover(self):
        s = self.prepared()
        w.start(s, {'active_test_authorized': True})
        w.request(s, 'B')
        old = self.cover(s, 'A')
        old['intent_id'] = s['pending']['id']
        w.begin_ui(self.root, s, old)
        # The external upload succeeded; state still says A because confirm never ran.
        w.stop(s, {'stop_authorized': True, 'variant': 'A'})
        self.assertEqual(w.next_action(s)['action'], 'reconcile_cover')
        actual = self.cover(s, 'B')
        actual['intent_id'] = s['pending']['id']
        w.reconcile(self.root, s, actual)
        self.assertEqual(s['on_card'], 'B')
        self.assertEqual(w.next_action(s)['action'], 'change_cover')
        w.begin_ui(self.root, s, actual)
        restored = self.cover(s, 'A')
        restored['intent_id'] = s['pending']['id']
        w.confirm(self.root, s, restored)
        self.assertEqual(s['on_card'], 'A')
        self.assertEqual(s['status'], 'finished')

    def test_uncertain_stop_cannot_skip_reconciliation(self):
        s = self.prepared()
        w.start(s, {'active_test_authorized': True})
        w.request(s, 'B')
        old = self.cover(s)
        old['intent_id'] = s['pending']['id']
        w.begin_ui(self.root, s, old)
        w.stop(s, {'stop_authorized': True, 'variant': 'A'})
        old.update(intent_id=s['pending']['id'], no_upload_needed=True)
        with self.assertRaises(ValueError): w.confirm(self.root, s, old)
        w.reconcile(self.root, s, old)
        self.assertEqual(w.next_action(s)['action'], 'verify_cover')

    def test_final_conditions_change_cannot_confirm_goal(self):
        s = self.running()
        views, clicks = 1200, 30
        for index in range(6):
            self.at += timedelta(hours=1)
            views += 1000
            clicks += 20 if s['on_card'] == 'A' else 40
            w.observe(self.root, s, self.observation(s, {'funnel': (views, clicks)}, s['on_card']))
            w.close_interval(s)
            if index < 5:
                self.publish(s)
        self.assertTrue(s['result']['confirmed'])
        final = self.cover(s, 'B')
        final.update(intent_id=s['pending']['id'], no_upload_needed=True)
        final['conditions']['price'] = 900
        w.confirm(self.root, s, final)
        self.assertFalse(s['goal_reached'])
        self.assertEqual(s['status'], 'paused_attention')
        self.assertEqual(s['last_conditions']['price'], 900)


if __name__ == '__main__':
    unittest.main(verbosity=2)
