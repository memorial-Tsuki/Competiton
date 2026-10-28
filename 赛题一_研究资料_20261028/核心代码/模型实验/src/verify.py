from study_common import ROOT,SEEDS,digest,read_json,write_json
from reproduce import NUMERIC,PROTOCOLS
from analyze_results import METHODS,load_models,independent_metrics
from delinquency_model import predict,scenario
from evaluation import metrics
import sys,subprocess,hashlib,json,importlib.metadata
import numpy as np,pandas as pd
from threadpoolctl import threadpool_limits

def numerical_fingerprint():
    paths=set()
    for name in NUMERIC+['prepare_study.py','predict.py','make_examples.py','reproduce.py','verify.py']:paths.add(ROOT/'src'/name)
    for name in PROTOCOLS:paths.add(ROOT/'docs'/name)
    for folder in ['tests','data','baseline','models','examples','results']:
        for p in (ROOT/folder).rglob('*'):
            if not p.is_file() or '__pycache__' in p.parts or 'figures' in p.parts:continue
            if p.name in ['verification.json','reproduction.json','visual_review.json']:continue
            if p.suffix in ['.py','.json','.csv','.joblib','.txt']:paths.add(p)
    records={p.relative_to(ROOT).as_posix():digest(p) for p in sorted(paths)}
    return {'sha256':hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest(),'files':len(records)}

def main():
    test=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/'tests'),'-v'],text=True,capture_output=True)
    (ROOT/'results/test_log.txt').write_text(test.stdout+test.stderr,encoding='utf-8')
    if test.returncode:raise RuntimeError(test.stderr)
    for path,h in read_json(ROOT/'data/input_manifest.json')['frozen_inputs'].items():assert digest(ROOT/path)==h,path
    df=pd.read_csv(ROOT/'data/cohort.csv',float_precision='round_trip').set_index('SK_ID_CURR',drop=False)
    pred=pd.read_csv(ROOT/'results/predictions.csv',float_precision='round_trip');perf=pd.read_csv(ROOT/'results/performance.csv',float_precision='round_trip')
    stress=pd.read_csv(ROOT/'results/scenario_predictions.csv',float_precision='round_trip')
    split=pd.read_csv(ROOT/'data/split_manifest.csv',dtype={'group':str});repeat=pd.read_csv(ROOT/'data/repeated_splits.csv',dtype={'group':str})
    count=0;checks=0
    for seed in SEEDS:
        models=load_models(seed);p=pred[pred.seed==seed];x=df.loc[p.SK_ID_CURR];ref=x.limit.to_numpy();roles=split if seed==SEEDS[0] else repeat[repeat.seed==seed]
        assert roles.SK_ID_CURR.is_unique and roles.groupby('group').role.nunique().max()==1
        assert set(x.index)==set(roles.loc[roles.role=='test','SK_ID_CURR']);np.testing.assert_array_equal(x.TARGET,p.TARGET)
        for m,b in models.items():
            for calibrated in [False,True]:
                q=predict(b,x,ref,calibrated);row=perf[(perf.seed==seed)&(perf.method==m)&(perf.calibrated==calibrated)].iloc[0]
                for k,v in metrics(x.TARGET,q).items():np.testing.assert_allclose(v,row[k],atol=1e-12,rtol=0);checks+=1
                if calibrated:np.testing.assert_allclose(q,p[m],atol=1e-12,rtol=0);count+=len(q)
            if seed==SEEDS[0]:
                for (kind,severity),a in stress[stress.method==m].groupby(['scenario','severity'],sort=False):
                    assert a.SK_ID_CURR.tolist()==x.SK_ID_CURR.tolist()
                    q=predict(b,scenario(x,kind,severity),ref);np.testing.assert_allclose(q,a.pd,atol=1e-12,rtol=0);count+=len(q)
        print('Replayed 12 model views for seed',seed,flush=True)
    main_models=load_models(SEEDS[0]);observed=pd.read_csv(ROOT/'results/observed_transition_predictions.csv',float_precision='round_trip');trans=pd.read_csv(ROOT/'data/observed_transitions.csv',float_precision='round_trip').set_index('SK_ID_CURR')
    for m,b in main_models.items():
        a=observed[observed.method==m];x=df.loc[a.SK_ID_CURR];previous=x.copy();previous['dpd']=trans.loc[x.index,'previous_dpd'];previous['dpd_def']=trans.loc[x.index,'previous_dpd_def']
        for records,column in [(x,'pd_with_current_dpd'),(previous,'pd_with_previous_dpd')]:
            q=predict(b,records,x.limit.to_numpy());np.testing.assert_allclose(q,a[column],atol=1e-12,rtol=0);count+=len(q)
    repro=read_json(ROOT/'results/reproduction.json');assert repro['status']=='passed'
    for path,h in repro['inputs'].items():assert digest(ROOT/path)==h,'Stale reproduction input: '+path
    for entry in repro['checked_outputs']:assert digest(ROOT/entry['path'])==entry['original_sha256'],'Stale numerical result: '+entry['path']
    env={p:importlib.metadata.version(p) for p in ['numpy','pandas','scipy','scikit-learn','joblib','matplotlib','threadpoolctl']};write_json(ROOT/'results/environment.json',{'python':sys.version,'libraries':env})
    proof={'status':'passed','unit_tests':16,'new_model_files_replayed':54,'frozen_baseline_files_replayed':18,'prediction_values_replayed':count,'performance_values_recomputed':checks,'independent_main_metric_values':84,'fresh_retraining_outputs':len(repro['checked_outputs']),'fingerprint':numerical_fingerprint()}
    write_json(ROOT/'results/verification.json',proof);print(proof,flush=True)
if __name__=='__main__':
    with threadpool_limits(limits=1):main()
