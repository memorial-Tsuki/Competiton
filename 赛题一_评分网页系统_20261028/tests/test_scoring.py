import unittest, sys, json, math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import scoring

class ModelContract(unittest.TestCase):
    def setUp(self):self.payload=scoring.example('pure_limit')
    def test_five_original_examples(self):
        for key in scoring.EXAMPLES:
            with self.subTest(example=key):
                source=json.loads((scoring.RUNTIME/'examples'/f'{key}.json').read_text(encoding='utf-8'))
                expected=json.loads((scoring.RUNTIME/'examples'/f'{key}_output.json').read_text(encoding='utf-8'))
                actual=scoring.run(scoring.example(key))['scenario']
                for field in ['pd','score','live_pd','risk_component_points','total_change_points']:
                    self.assertAlmostEqual(actual[field],expected[field],delta=1e-10)
    def test_pure_limit_and_decomposition(self):
        r=scoring.run(self.payload)
        self.assertEqual(r['base']['pd'],r['scenario']['pd'])
        self.assertGreater(r['scenario']['live_score'],r['base']['live_score'])
        self.assertAlmostEqual(r['scenario']['risk_component_points']+r['scenario']['mechanical_limit_component_points'],r['scenario']['total_change_points'],places=10)
        self.assertEqual(len({p['reference'] for p in r['curves']['limit']}),1)
    def test_missing_optional_not_zero(self):
        self.payload['inputs']={f['key']:self.payload['inputs'][f['key']] for f in scoring.FIELDS if f['required']}
        r=scoring.run(self.payload)
        self.assertEqual(r['quality']['provided'],7)
        self.assertIsNone(r['normalized_input']['hist_max_dpd'])
        self.assertTrue(0<r['base']['pd']<1)
        self.assertTrue(any('不是经过重训' in s for s in r['quality']['notices']))
    def test_zero_balance_absolute_borrowing(self):
        self.payload['inputs']['balance']=0
        self.payload['scenario'].update(kind='new_debt',debt_amount=10000)
        r=scoring.run(self.payload)
        self.assertGreaterEqual(r['scenario']['pd'],r['base']['pd'])
        self.assertTrue(any(f['key']=='balance' and f['after']==10000 for f in r['scenario']['changed_fields']))
    def test_worsening_after_cap_still_review(self):
        r=scoring.run(scoring.example('saturated_but_worsening'))
        self.assertTrue(r['scenario']['requires_review'])
        self.assertIn('new_or_worsened_recorded_delinquency',r['scenario']['review_reasons'])
        self.assertAlmostEqual(r['scenario']['pd'],r['base']['pd'],places=10)
    def test_invalid_inputs(self):
        for key,value in [('AMT_INCOME_TOTAL',0),('limit',-1),('balance',float('nan')),('dpd',1.5),('EXT_SOURCE_1',2)]:
            p=scoring.example('pure_limit');p['inputs'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):scoring.normalize(p)
        p=scoring.example('pure_limit');p['inputs']['dpd_def']=1
        with self.assertRaises(ValueError):scoring.normalize(p)
        p=scoring.example('pure_limit');p['inputs'].pop('payment')
        with self.assertRaises(ValueError):scoring.normalize(p)
    def test_json_finite_and_hash(self):
        r=scoring.run(self.payload);json.dumps(r,allow_nan=False)
        self.assertEqual(r['model']['sha256'],scoring.EXPECTED_SHA)

if __name__=='__main__':unittest.main(verbosity=2)
