"""Protocol B: fixed equal-channel sharing, learned nonnegative common coefficient."""
from study_common import ROOT,SEEDS,VERSION,digest,write_json,read_json
import numpy as np,pandas as pd,joblib
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler,OneHotEncoder
from sklearn.linear_model import LogisticRegression
from threadpoolctl import threadpool_limits
from risk_model import CATS,DIRECTIONS,EXTERNAL,POLICY,logit
from delinquency_model import SignedLogit,features,predict,scenario
from evaluation import metrics
from run_experiment import baseline_bundles,diagnostics,MONO

R=ROOT/'results';M=ROOT/'models';MONO.update(['shared_lr','shared_hybrid'])

def fit_shared(df,split,seed,prefix='shared'):
    roles=split.set_index('SK_ID_CURR').loc[df.SK_ID_CURR,'role'].to_numpy();parts={r:df.loc[roles==r].copy() for r in ['train','validation','calibration','test']}
    mode=prefix+'_cap30';f=features(df,mode);nums=[c for c in f if c not in CATS]
    prep=ColumnTransformer([('num',make_pipeline(SimpleImputer(strategy='median',add_indicator=True),StandardScaler()),nums),('cat',OneHotEncoder(handle_unknown='ignore',sparse_output=False),CATS)])
    x=prep.fit_transform(f.loc[roles=='train']);xv=prep.transform(f.loc[roles=='validation']);names=prep.get_feature_names_out()
    common=np.array([n not in ['num__'+c for c in POLICY+EXTERNAL]+['num__missingindicator_'+c for c in POLICY+EXTERNAL] for n in names])
    hashes=pd.util.hash_pandas_object(pd.DataFrame(prep.transform(f)[:,common]),index=False)
    assert pd.DataFrame({'g':hashes,'role':roles}).groupby('g').role.nunique().max()==1
    signs=[{**DIRECTIONS,'cc_shared_dpd_log':1,'cc_rolling_dpd_log':1}.get(n.removeprefix('num__'),0) for n in names]
    trials=[];candidates=[];val=parts['validation'];ref=val.limit.to_numpy();y=parts['train'].TARGET.to_numpy()
    for ridge in [.0001,.001,.01]:
        model=SignedLogit(ridge,signs).fit(x,y);met=metrics(val.TARGET,model.predict_proba(xv)[:,1])
        trials.append({'ridge':ridge,**met,'iterations':model.iterations,'projected_gradient':model.projected_gradient});candidates.append((met['AUC'],ridge,model))
    auc,ridge,model=max(candidates,key=lambda t:(t[0],t[1]))
    b={'version':VERSION,'kind':'single','feature_mode':mode,'model':model,'preprocessor':prep,'mask':np.ones(len(names),bool),'feature_names':names,'calibrator':None,'seed':seed}
    tree=baseline_bundles(seed)['baseline_mono_anchor'];p0=predict(tree,val,ref,False);p1=predict(b,val,ref,False);oldmet=metrics(val.TARGET,p0)
    stress=scenario(val,'ordinary_dpd',30);q0=predict(tree,stress,ref,False);q1=predict(b,stress,ref,False);zero=(val.dpd.eq(0)&val.dpd_def.eq(0)).to_numpy();weights=[]
    for alpha in [0.,.1,.25,.5,.75,1.]:
        p=(1-alpha)*p0+alpha*p1;q=(1-alpha)*q0+alpha*q1;met=metrics(val.TARGET,p)
        row={'alpha':alpha,**met,'initial_zero_n':int(zero.sum()),'strict_increase_zero':float(np.mean(q[zero]>p[zero]+1e-10)),'median_pd_change_zero':float(np.median(q[zero]-p[zero]))}
        row['eligible']=bool(row['AUC']>=oldmet['AUC']-.005 and row['Brier']<=oldmet['Brier']+.001 and row['strict_increase_zero']>=.99 and row['median_pd_change_zero']>=.001);weights.append(row)
    good=[t for t in weights if t['eligible']];best=max(good or weights,key=lambda t:(t['AUC'],-t['alpha']))
    hybrid={'version':VERSION,'kind':'hybrid','baseline':tree,'linear':b,'alpha':best['alpha'],'calibrator':None,'seed':seed,'development_gate_passed':bool(good)}
    hp=predict(hybrid,val,ref,False)
    np.testing.assert_array_equal(hp,predict(hybrid,scenario(val,'pure_limit',.5),ref,False))
    for kind,s in [('balance_up',0),('joint_dpd',30)]:assert np.all(predict(hybrid,scenario(val,kind,s),ref,False)>=hp-1e-12)
    assert np.all(predict(hybrid,scenario(val,'payment_up'),ref,False)<=hp+1e-12)
    models={prefix+'_lr':b,prefix+'_hybrid':hybrid};cal=parts['calibration'];calibrators=[]
    for name,bundle in models.items():
        cp=predict(bundle,cal,cal.limit.to_numpy(),False);sigmoid=LogisticRegression(C=1e6).fit(logit(cp).reshape(-1,1),cal.TARGET)
        assert sigmoid.coef_[0,0]>0;bundle['calibrator']=sigmoid;joblib.dump(bundle,M/f'{seed}_{name}.joblib',compress=3)
        calibrators.append({'method':name,'slope':float(sigmoid.coef_[0,0]),'intercept':float(sigmoid.intercept_[0])})
    protocol='协议补充_B.md' if prefix=='shared' else '协议补充_C.md'
    write_json(R/f'{seed}_{prefix}_selection.json',{'seed':seed,'additional_protocol_sha256':digest(ROOT/'docs'/protocol),'selected_ridge':ridge,'candidate_trials':trials,'hybrid_trials':weights,'hybrid_selected_alpha':best['alpha'],'development_gate_passed':bool(good),'calibrators':calibrators,'used_test_labels_for_selection':False})
    return models,parts

def main(prefix='shared'):
    df=pd.read_csv(ROOT/'data/cohort.csv',float_precision='round_trip');split=pd.read_csv(ROOT/'data/split_manifest.csv',dtype={'group':str});repeat=pd.read_csv(ROOT/'data/repeated_splits.csv',dtype={'group':str})
    names=[prefix+'_lr',prefix+'_hybrid'];MONO.update(names);ps=[];ms=[];ss=[]
    for seed in SEEDS:
        bundles,parts=fit_shared(df,split if seed==SEEDS[0] else repeat[repeat.seed==seed],seed,prefix)
        # The common diagnostic function writes only the B main scenarios temporarily.
        previous=R/'scenario_predictions.csv'
        if seed==SEEDS[0] and previous.exists():
            prior=pd.read_csv(previous,float_precision='round_trip');prior=prior[~prior.method.isin(names)]
        p,perf,stress=diagnostics(bundles,parts,seed,seed==SEEDS[0]);ps.append(p);ms.extend(perf);ss.extend(stress)
        if seed==SEEDS[0]:pd.concat([prior,pd.read_csv(previous,float_precision='round_trip')],ignore_index=True).to_csv(previous,index=False)
        sel=read_json(R/f'{seed}_{prefix}_selection.json');print(prefix,'group',seed,'alpha',sel['hybrid_selected_alpha'],'gate',sel['development_gate_passed'],flush=True)
    base=pd.read_csv(R/'predictions.csv',float_precision='round_trip').drop(columns=names,errors='ignore')
    p=pd.concat(ps,ignore_index=True);base=base.merge(p[['SK_ID_CURR','seed']+names],on=['SK_ID_CURR','seed'],validate='one_to_one');base.to_csv(R/'predictions.csv',index=False)
    for name,rows in [('performance.csv',ms),('scenario_metrics.csv',ss)]:
        old=pd.read_csv(R/name,float_precision='round_trip');old=old[~old.method.isin(names)]
        pd.concat([old,pd.DataFrame(rows)],ignore_index=True).to_csv(R/name,index=False)
    print(prefix,'complete: 12 new models.',flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--group',choices=['shared','rolling'],default='shared');args=parser.parse_args()
    with threadpool_limits(limits=1):main(args.group)
