import sqlite3
import tempfile
import unittest
from pathlib import Path

from test_browser import BrowserBaselineTest

from app.domain import interpret_qualification
from app.eligibility import observe_eligibility, qualification_cache_key
from app.records import (
    load_qualification_observation,
    read_qualification_observations,
)
from app.review import review_eligibility
from app.site import DATA


class EligibilityObservationTest(BrowserBaselineTest):
    ITEM = DATA['items'][0]['id']
    BUILDING_1 = '桐花苑 1 栋'
    BUILDING_2 = '桐花苑 2 栋'

    def test_served_address_produces_sourced_eligible_observation(self):
        observation = observe_eligibility(self.origin, self.ITEM, self.BUILDING_1)
        evidence = observation['evidence']
        self.assertEqual(observation['id'], self.ITEM)
        self.assertEqual(evidence['address_input_value'], self.BUILDING_1)
        self.assertIn(self.BUILDING_1, evidence['address_suggestions'])
        self.assertTrue(evidence['address_result'].startswith(self.BUILDING_1))
        self.assertEqual(evidence['provider'], '城区维修队')
        self.assertTrue(evidence['terms_requires_confirmation'])
        self.assertTrue(evidence['terms_confirmed'])
        self.assertEqual(evidence['slot_selected'], 'tue')
        self.assertEqual(evidence['slot_selected_text'], '周二')
        self.assertTrue(evidence['qualification_preview'].startswith(self.BUILDING_1))
        self.assertIn('周二', evidence['qualification_preview'])
        fact = observation['qualification_fact']
        self.assertEqual(fact['qualification'], 'eligible')
        self.assertEqual(fact['reasons'], [])
        # 即便页面资格链齐备，也永远不是“可下单”结论。
        self.assertFalse(fact['orderable'])
        self.assertFalse(observation['order_submitted'])
        # 来源链：卡片页与详情页 URL 都在记录里。
        roles = {source['role']: source['url'] for source in observation['sources']}
        self.assertEqual(roles['catalog'], self.origin)
        self.assertIn('/detail', roles['detail'])
        self.assertIn(self.ITEM, roles['detail'])
        # 卡片“可预约”只保留为目录事实，不参与资格判读。
        self.assertEqual(observation['catalog_fact']['availability'], '可预约')

    def test_restricted_address_is_unconfirmed_without_invented_slot(self):
        observation = observe_eligibility(self.origin, self.ITEM, self.BUILDING_2)
        evidence = observation['evidence']
        self.assertEqual(evidence['provider'], '东区维修队')
        self.assertEqual(evidence['slot_selected'], '')
        self.assertEqual(evidence['slot_selected_text'], '')
        self.assertIn({'value': '', 'text': '暂无可确认时段'}, evidence['slot_options'])
        self.assertEqual(evidence['qualification_preview'], '资格未确认')
        fact = observation['qualification_fact']
        self.assertEqual(fact['qualification'], 'unconfirmed')
        self.assertIn('no_confirmable_slot', fact['reasons'])
        self.assertIn('preview_unconfirmed', fact['reasons'])
        self.assertFalse(fact['orderable'])
        self.assertFalse(observation['order_submitted'])

    def test_unknown_address_is_unconfirmed_not_bookable(self):
        observation = observe_eligibility(self.origin, self.ITEM, '桐花苑 99 栋')
        evidence = observation['evidence']
        self.assertEqual(evidence['address_result'], '地址未确认')
        self.assertNotIn('桐花苑 99 栋', evidence['address_suggestions'])
        self.assertIn('address_not_in_suggestions', observation['actions'])
        fact = observation['qualification_fact']
        self.assertEqual(fact['qualification'], 'unconfirmed')
        self.assertIn('address_not_recognized', fact['reasons'])
        self.assertFalse(observation['order_submitted'])

    def test_similar_suggestions_are_never_auto_selected(self):
        # 输入一个联想列表里不存在、但与“桐花苑 2 栋”近似的地址，
        # 观察必须保留精确输入并判未确认，不能替客户选成 2 栋。
        observation = observe_eligibility(self.origin, self.ITEM, '桐花苑 2 栋旁门')
        evidence = observation['evidence']
        self.assertEqual(evidence['address_input_value'], '桐花苑 2 栋旁门')
        self.assertEqual(evidence['provider'], '')
        self.assertEqual(evidence['address_result'], '地址未确认')
        self.assertEqual(evidence['slot_selected'], '')
        self.assertEqual(evidence['qualification_preview'], '资格未确认')
        self.assertEqual(
            observation['qualification_fact']['qualification'], 'unconfirmed')

    def test_unconfirmed_terms_keep_observation_unconfirmed(self):
        observation = observe_eligibility(
            self.origin, self.ITEM, self.BUILDING_1, confirm_terms=False)
        evidence = observation['evidence']
        self.assertTrue(evidence['terms_requires_confirmation'])
        self.assertFalse(evidence['terms_confirmed'])
        self.assertIn('terms_confirmation_withheld', observation['actions'])
        # 时段仍属于当前地址，但条款没确认，页面预览自身就是“资格未确认”。
        self.assertEqual(evidence['slot_selected'], 'tue')
        self.assertEqual(evidence['qualification_preview'], '资格未确认')
        fact = observation['qualification_fact']
        self.assertEqual(fact['qualification'], 'unconfirmed')
        self.assertIn('terms_not_confirmed', fact['reasons'])
        self.assertIn('preview_unconfirmed', fact['reasons'])

    def test_same_address_rerun_is_served_from_its_own_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / 'eligibility.sqlite3'
            first = observe_eligibility(self.origin, self.ITEM, self.BUILDING_1,
                                        cache_path=cache)
            self.assertFalse(first['cache_hit'])
            second = observe_eligibility(self.origin, self.ITEM, self.BUILDING_1,
                                         cache_path=cache)
            self.assertTrue(second['cache_hit'])
            self.assertEqual(second['session_id'], first['session_id'])
            self.assertEqual(second['evidence'], first['evidence'])
            self.assertEqual(second['sources'], first['sources'])
            with sqlite3.connect(cache) as db:
                self.assertEqual(
                    db.execute('SELECT count(*) FROM qualification_observations')
                    .fetchone()[0], 1)
            # refresh 强制重新观察，覆盖同一地址自己的缓存行。
            rerun = observe_eligibility(self.origin, self.ITEM, self.BUILDING_1,
                                        cache_path=cache, refresh=True)
            self.assertFalse(rerun['cache_hit'])
            self.assertNotEqual(rerun['session_id'], first['session_id'])
            with sqlite3.connect(cache) as db:
                self.assertEqual(
                    db.execute('SELECT count(*) FROM qualification_observations')
                    .fetchone()[0], 1)

    def test_distinct_addresses_have_distinct_cache_and_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / 'eligibility.sqlite3'
            one = observe_eligibility(self.origin, self.ITEM, self.BUILDING_1,
                                      cache_path=cache)
            two = observe_eligibility(self.origin, self.ITEM, self.BUILDING_2,
                                      cache_path=cache)
            self.assertNotEqual(
                qualification_cache_key(self.origin, self.ITEM, self.BUILDING_1),
                qualification_cache_key(self.origin, self.ITEM, self.BUILDING_2))
            self.assertNotEqual(one['session_id'], two['session_id'])
            with sqlite3.connect(cache) as db:
                rows = db.execute(
                    'SELECT address FROM qualification_observations').fetchall()
            self.assertEqual({row[0] for row in rows},
                             {self.BUILDING_1, self.BUILDING_2})
            # 1 栋的缓存不被 2 栋观察污染。
            cached_one = load_qualification_observation(
                cache, qualification_cache_key(self.origin, self.ITEM, self.BUILDING_1))
            self.assertEqual(cached_one['evidence']['provider'], '城区维修队')
            self.assertEqual(len(read_qualification_observations(cache)), 2)

    def test_each_observation_runs_in_a_fresh_isolated_context(self):
        first = observe_eligibility(self.origin, self.ITEM, self.BUILDING_1)
        second = observe_eligibility(self.origin, self.ITEM, self.BUILDING_1)
        self.assertNotEqual(first['session_id'], second['session_id'])
        for observation in (first, second):
            self.assertEqual(observation['session_isolation']['cookies'], [])
            self.assertEqual(
                observation['session_isolation']['origins_in_storage'], [])

    def test_address_switch_never_carries_over_stale_slot(self):
        # 先观察 1 栋（会选周二），再在全新会话观察 2 栋：
        # 2 栋记录里不得残留任何周二选中态。
        observe_eligibility(self.origin, self.ITEM, self.BUILDING_1)
        second = observe_eligibility(self.origin, self.ITEM, self.BUILDING_2)
        self.assertEqual(second['evidence']['slot_selected'], '')
        self.assertNotIn('周二', second['evidence']['qualification_preview'])
        self.assertNotIn('tue', [option['value']
                                 for option in second['evidence']['slot_options']])

    def test_only_loopback_get_requests_occur_and_no_order_is_submitted(self):
        observation = observe_eligibility(self.origin, self.ITEM, self.BUILDING_1)
        self.assertTrue(observation['requests'])
        self.assertEqual(observation['network_guard']['non_loopback_requests'], [])
        self.assertEqual(observation['network_guard']['write_methods'], [])
        self.assertFalse(observation['order_submitted'])
        for request in observation['requests']:
            self.assertEqual(request['method'], 'GET')

    def test_non_loopback_origin_is_rejected(self):
        with self.assertRaises(ValueError):
            observe_eligibility('https://example.com/', self.ITEM, self.BUILDING_1)

    def test_technical_failure_is_unconfirmed_and_not_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / 'eligibility.sqlite3'
            observation = observe_eligibility(
                self.origin, 'missing-item', self.BUILDING_1, cache_path=cache)
            self.assertEqual(observation['qualification_fact']['qualification'],
                             'unconfirmed')
            self.assertIn('technical_error', observation)
            self.assertFalse(observation['order_submitted'])
            self.assertEqual(read_qualification_observations(cache), [])

    def test_review_summary_is_customer_safe(self):
        eligible = observe_eligibility(self.origin, self.ITEM, self.BUILDING_1)
        restricted = observe_eligibility(self.origin, self.ITEM, self.BUILDING_2)
        summaries = review_eligibility([eligible, restricted])
        self.assertEqual([row['qualification'] for row in summaries],
                         ['eligible', 'unconfirmed'])
        for row in summaries:
            self.assertFalse(row['orderable'])
            self.assertFalse(row['order_submitted'])
            self.assertTrue(row['sources'])
        self.assertIn('周二', summaries[0]['slot'])
        self.assertIsNone(summaries[1]['slot'])
        self.assertIn('no_confirmable_slot', summaries[1]['reasons'])
        self.assertIn('不得向客户承诺', summaries[1]['reply_guidance'])


class QualificationInterpretationTest(unittest.TestCase):
    def _evidence(self, **overrides):
        evidence = {
            'address': '桐花苑 1 栋',
            'address_input_value': '桐花苑 1 栋',
            'address_result': '桐花苑 1 栋：服务区',
            'checked_address': '桐花苑 1 栋',
            'provider': '城区维修队',
            'terms_requires_confirmation': True,
            'terms_confirmed': True,
            'slot_options': [{'value': 'tue', 'text': '周二'}],
            'slot_selected': 'tue',
            'qualification_preview': '桐花苑 1 栋 / 城区维修队：需确认上门条款 / 周二',
        }
        evidence.update(overrides)
        return evidence

    def test_complete_chain_is_eligible_but_never_orderable(self):
        fact = interpret_qualification(self._evidence())
        self.assertEqual(fact['qualification'], 'eligible')
        self.assertEqual(fact['reasons'], [])
        self.assertFalse(fact['orderable'])

    def test_stale_preview_pointing_elsewhere_is_unconfirmed(self):
        fact = interpret_qualification(self._evidence(
            qualification_preview='桐花苑 2 栋 / 东区维修队：范围待核 / 周二'))
        self.assertEqual(fact['qualification'], 'unconfirmed')
        self.assertIn('preview_address_mismatch', fact['reasons'])

    def test_missing_slot_and_unchecked_terms_are_both_reported(self):
        fact = interpret_qualification(self._evidence(
            terms_confirmed=False,
            slot_options=[{'value': '', 'text': '暂无可确认时段'}],
            slot_selected='',
            qualification_preview='资格未确认'))
        self.assertEqual(fact['qualification'], 'unconfirmed')
        self.assertIn('no_confirmable_slot', fact['reasons'])
        self.assertIn('terms_not_confirmed', fact['reasons'])
        self.assertIn('preview_unconfirmed', fact['reasons'])

    def test_unrecognized_address_is_unconfirmed(self):
        fact = interpret_qualification(self._evidence(
            address='桐花苑 99 栋', address_input_value='桐花苑 99 栋',
            checked_address='桐花苑 99 栋', address_result='地址未确认',
            slot_options=[{'value': '', 'text': '暂无可确认时段'}],
            slot_selected='', qualification_preview='资格未确认'))
        self.assertEqual(fact['qualification'], 'unconfirmed')
        self.assertIn('address_not_recognized', fact['reasons'])


if __name__ == '__main__':
    unittest.main()
