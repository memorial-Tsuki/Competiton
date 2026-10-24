"""Freeze existing inputs and construct an unlabeled observed DPD transition table."""
from study_common import ROOT,SEEDS,digest,write_json,read_json
import shutil
import pandas as pd
import numpy as np

def main():
    base=ROOT.parent/'赛题一融合版';manifest=ROOT/'data/input_manifest.json'
    if manifest.exists():
        m=read_json(manifest)
        for p,h in m['frozen_inputs'].items():assert digest(ROOT/p)==h,p
        print('Frozen study inputs verified.');return
    files={'data/cohort.csv':'data/cohort.csv','results/split_manifest.csv':'data/split_manifest.csv','results/repeated_splits.csv':'data/repeated_splits.csv','src/risk_model.py':'src/risk_model.py','src/evaluation.py':'src/evaluation.py'}
    for seed in SEEDS:
        for method in ['lr','consistency','hgb_mono']:files[f'models/{seed}_{method}.joblib']=f'baseline/models/{seed}_{method}.joblib'
    hashes={}
    for src,dst in files.items():
        target=ROOT/dst;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(base/src,target);hashes[dst]=digest(target)
    raw=base/'data/raw/credit_card_balance.csv';raw_hash=digest(raw)
    assert raw_hash==read_json(base/'data/source_manifest.json')['files']['credit_card_balance.csv']['sha256']
    use=['SK_ID_CURR','SK_ID_PREV','MONTHS_BALANCE','AMT_CREDIT_LIMIT_ACTUAL','AMT_BALANCE','SK_DPD','SK_DPD_DEF','NAME_CONTRACT_STATUS']
    chunks=[]
    for x in pd.read_csv(raw,usecols=use,chunksize=500000):
        chunks.append(x[x.MONTHS_BALANCE.isin([-2,-1])&x.NAME_CONTRACT_STATUS.eq('Active')&x.AMT_CREDIT_LIMIT_ACTUAL.gt(0)&x.AMT_BALANCE.ge(0)])
    cc=pd.concat(chunks);a=cc[cc.MONTHS_BALANCE.eq(-1)];b=cc[cc.MONTHS_BALANCE.eq(-2)]
    both=a.merge(b,on=['SK_ID_CURR','SK_ID_PREV'],suffixes=('_current','_previous'),validate='one_to_one')
    g=both.groupby('SK_ID_CURR').agg(matched=('SK_ID_PREV','size'),current_dpd=('SK_DPD_current','max'),current_dpd_def=('SK_DPD_DEF_current','max'),previous_dpd=('SK_DPD_previous','max'),previous_dpd_def=('SK_DPD_DEF_previous','max'))
    g['a']=a.groupby('SK_ID_CURR').size();g['b']=b.groupby('SK_ID_CURR').size();g=g[g.matched.eq(g.a)&g.matched.eq(g.b)]
    cohort=pd.read_csv(ROOT/'data/cohort.csv').set_index('SK_ID_CURR');g=g.loc[g.index.intersection(cohort.index)].copy()
    assert set(g.index)==set(cohort.index[cohort.reference_eligible])
    np.testing.assert_array_equal(g.current_dpd,cohort.loc[g.index,'dpd']);np.testing.assert_array_equal(g.current_dpd_def,cohort.loc[g.index,'dpd_def'])
    d=g.current_dpd-g.previous_dpd;e=g.current_dpd_def-g.previous_dpd_def
    g['transition']=np.select([(d.eq(0)&e.eq(0)),(d.ge(0)&e.ge(0)&(d.gt(0)|e.gt(0))),(d.le(0)&e.le(0)&(d.lt(0)|e.lt(0)))],['unchanged','worsening','improving'],default='mixed')
    g[['current_dpd','current_dpd_def','previous_dpd','previous_dpd_def','transition']].to_csv(ROOT/'data/observed_transitions.csv')
    hashes['data/observed_transitions.csv']=digest(ROOT/'data/observed_transitions.csv')
    write_json(manifest,{'source':'Frozen 2026-09-24 fusion deliverable; third-stage exploratory development.','frozen_inputs':hashes,'source_raw_csv_sha256':raw_hash,'source_archive_sha256':read_json(base/'data/source_manifest.json')['received_archive_sha256'],'observed_transition_counts':g.transition.value_counts().to_dict(),'protocol_sha256':digest(ROOT/'docs/实验协议.md')})
    print('Prepared',len(cohort),'customers;',len(g),'same-card observed transitions.',g.transition.value_counts().to_dict(),flush=True)

if __name__=='__main__':main()
