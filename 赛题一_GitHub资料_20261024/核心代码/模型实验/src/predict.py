"""Candidate prototype: model response and operational review are separate outputs."""
from study_common import ROOT,VERSION,read_json
from datetime import datetime
from pathlib import Path
import argparse,json,math
import numpy as np,pandas as pd,joblib
from delinquency_model import predict
from risk_model import score,grade

def validate(payload):
    if payload.get('reference_source') not in ['pre_policy_snapshot','reviewed_initial_limit']:raise ValueError('Reviewed reference source required')
    reference=float(payload['reference_limit'])
    if not math.isfinite(reference) or reference<=0:raise ValueError('Positive finite reference required')
    for record in [payload['current']]+([payload['previous']] if 'previous' in payload else []):
        if float(record['dpd_def'])>float(record['dpd']):raise ValueError('Tolerant DPD cannot exceed ordinary DPD in this data contract')
    context=payload.get('event_context')
    if context is None:return reference,'research_input_without_verified_event'
    required=['customer_id','reference_customer_id','event_id','reference_snapshot_id','reference_review_status','reference_model_version','reference_model_variant','event_kind']
    if any(not context.get(k) for k in required):raise ValueError('Incomplete event context')
    if context['customer_id']!=context['reference_customer_id']:raise ValueError('Reference belongs to another customer')
    if context['reference_model_version']!=VERSION or context['reference_model_variant']!='rolling_hybrid' or context['reference_review_status']!='reviewed':raise ValueError('Reference model/version/review mismatch')
    times=[datetime.fromisoformat(context[k]) for k in ['reference_captured_at','previous_observed_at','event_at','current_observed_at','reference_valid_until']]
    if any(t.tzinfo is None for t in times) or any(a>b for a,b in zip(times,times[1:])):raise ValueError('Invalid reference chronology')
    before=payload['previous'];now=payload['current']
    if any(str(r.get('SK_ID_CURR'))!=str(context['customer_id']) for r in [before,now]):raise ValueError('Snapshot customer mismatch')
    if context['event_kind']=='bank_marketing_limit_increase':
        if float(now['limit'])<=float(before['limit']):raise ValueError('Marketing increase must raise the limit')
    elif context['event_kind']=='behavior_update':
        if float(now['limit'])!=float(before['limit']):raise ValueError('Behavior event cannot also change limit')
    else:raise ValueError('Event requires reference review')
    return reference,'declared_consistent_external_authenticity_not_verified'

def evaluate(payload,bundle=None):
    reference,provenance=validate(payload)
    if bundle is None:bundle=joblib.load(ROOT/'models/20260923_rolling_hybrid.joblib')
    x=pd.DataFrame([payload['current']]);p=float(predict(bundle,x,reference)[0]);live=float(predict(bundle,x)[0]);reasons=[]
    maximum=float(np.fmax(x.hist_max_dpd.iloc[0],max(x.dpd.iloc[0],x.dpd_def.iloc[0])))
    if maximum>=30:reasons.append('rolling_dpd_at_or_above_30_day_cap')
    if float(x.dpd.iloc[0])>0 or float(x.dpd_def.iloc[0])>0:reasons.append('current_recorded_delinquency')
    bounds=read_json(ROOT/'results/raw_training_support.json');outside=[c for c,b in bounds.items() if float(x.iloc[0][c])<b['min'] or float(x.iloc[0][c])>b['max']]
    if outside:reasons.append('raw_input_outside_training_range')
    result={'model_version':VERSION,'method':'rolling_hybrid','development_gate_passed':bool(bundle['development_gate_passed']),'pd':p,'score':float(score(p)),'grade':'ABCDE'[int(grade(p))],'live_pd':live,'reference_limit':reference,'rolling_peak_observed_days':maximum,'capped_peak_days':min(maximum,30.),'mechanical_limit_component_points':float(score(live)-score(p)),'provenance':provenance,'status':'research_candidate_not_credit_approval','outside_training_range':outside}
    if 'previous' in payload:
        before=pd.DataFrame([payload['previous']]);prior=float(predict(bundle,before,reference)[0])
        result.update({'previous_recomputed_pd':prior,'pd_change':p-prior,'risk_component_points':float(score(p)-score(prior)),'total_change_points':float(score(live)-score(prior)),'change_basis':'same model/reference; current live score minus recomputed previous reference score'})
        if x.dpd.iloc[0]>before.dpd.iloc[0] or x.dpd_def.iloc[0]>before.dpd_def.iloc[0]:reasons.append('new_or_worsened_recorded_delinquency')
    result['review_reasons']=reasons;result['requires_review']=bool(reasons)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('input',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
    try:result=evaluate(json.loads(args.input.read_text(encoding='utf-8')))
    except (KeyError,ValueError,TypeError) as e:parser.exit(2,'Input error: '+str(e)+'\n')
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text,encoding='utf-8')
    print(text)
