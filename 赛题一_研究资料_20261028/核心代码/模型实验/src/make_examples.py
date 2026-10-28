from study_common import ROOT,VERSION,write_json
import pandas as pd,copy
from delinquency_model import scenario
from predict import evaluate
from threadpoolctl import threadpool_limits
def main():
    df=pd.read_csv(ROOT/'data/cohort.csv',float_precision='round_trip');split=pd.read_csv(ROOT/'data/split_manifest.csv')
    x=df[df.SK_ID_CURR.isin(split.loc[split.role=='test','SK_ID_CURR'])&df.dpd.eq(0)&df.dpd_def.eq(0)&df.hist_max_dpd.eq(0)&df.balance.gt(1000)].iloc[:1]
    def record(a):return {k:(None if pd.isna(v) else v) for k,v in a.iloc[0].to_dict().items()}
    before=record(x);customer=str(int(before['SK_ID_CURR']))
    template={'reference_limit':float(x.limit.iloc[0]),'reference_source':'pre_policy_snapshot','previous':before,'example_note':'First qualifying public test record; times/events and interventions are synthetic demonstrations, not observed bank actions.','event_context':{'customer_id':customer,'reference_customer_id':customer,'event_id':'synthetic-demo','reference_snapshot_id':'synthetic-reference','reference_review_status':'reviewed','reference_model_version':VERSION,'reference_model_variant':'rolling_hybrid','event_kind':'behavior_update','reference_captured_at':'2026-01-01T00:00:00+08:00','previous_observed_at':'2026-01-01T00:00:00+08:00','event_at':'2026-01-02T00:00:00+08:00','current_observed_at':'2026-01-02T01:00:00+08:00','reference_valid_until':'2026-02-01T00:00:00+08:00'}}
    specs=[('pure_limit','pure_limit',.5),('new_ordinary_dpd','ordinary_dpd',30),('new_joint_dpd','joint_dpd',30),('new_debt','balance_up',0)]
    for name,kind,severity in specs:
        payload=copy.deepcopy(template);payload['current']=record(scenario(x,kind,severity))
        if kind=='pure_limit':payload['event_context']['event_kind']='bank_marketing_limit_increase'
        result=evaluate(payload);write_json(ROOT/f'examples/{name}.json',payload);write_json(ROOT/f'examples/{name}_output.json',result)
        if kind=='pure_limit':assert abs(result['pd_change'])<1e-12
        if kind in ['ordinary_dpd','joint_dpd']:assert result['pd_change']>0 and result['requires_review']
    payload=copy.deepcopy(template);payload['previous']['dpd']=30.;payload['previous']['dpd_def']=30.;current=copy.deepcopy(payload['previous']);current['dpd']=60.;current['dpd_def']=60.;payload['current']=current
    result=evaluate(payload);assert abs(result['pd_change'])<1e-12 and result['requires_review']
    write_json(ROOT/'examples/saturated_but_worsening.json',payload);write_json(ROOT/'examples/saturated_but_worsening_output.json',result)
    print('Five candidate CLI examples generated; saturation remains a review event.')
if __name__=='__main__':
    with threadpool_limits(limits=1):main()
