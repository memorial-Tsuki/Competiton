"""Frozen development protocol; no new test labels select model families or weights."""
from study_common import ROOT,SEEDS,VERSION,digest,read_json,write_json
import numpy as np
import pandas as pd
import joblib
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler,OneHotEncoder
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from threadpoolctl import threadpool_limits
from risk_model import CATS,EXTERNAL,POLICY,DIRECTIONS,logit
from delinquency_model import SignedLogit,features,predict,scenario
from evaluation import metrics,instability

R=ROOT/'results';M=ROOT/'models';R.mkdir(exist_ok=True);M.mkdir(exist_ok=True)
NEW=['sign_lr','capped_sign_lr','capped_lr_no_external','capped_tree','hybrid']
BASE={'baseline_lr_anchor':('lr',True),'baseline_consistency':('consistency',False),'baseline_mono_anchor':('hgb_mono',True)}
MONO=set(NEW)|{'baseline_mono_anchor'}

def baseline_bundles(seed):
    return {name:{'version':VERSION,'kind':'baseline','anchored':anchor,'original':joblib.load(ROOT/f'baseline/models/{seed}_{key}.joblib')} for name,(key,anchor) in BASE.items()}

def fit(df,split,seed):
    roles=split.set_index('SK_ID_CURR').loc[df.SK_ID_CURR,'role'].to_numpy()
    parts={r:df.loc[roles==r].copy() for r in ['train','validation','calibration','test']}
    y=parts['train'].TARGET.to_numpy();val=parts['validation'];vy=val.TARGET.to_numpy()
    bundles=baseline_bundles(seed);preps={};matrices={};selections=[];chosen={}
    for mode in ['raw','cap30']:
        f=features(df,mode);nums=[c for c in f if c not in CATS]
        prep=ColumnTransformer([('num',make_pipeline(SimpleImputer(strategy='median',add_indicator=True),StandardScaler()),nums),('cat',OneHotEncoder(handle_unknown='ignore',sparse_output=False),CATS)])
        prep.fit(f.loc[roles=='train']);preps[mode]=prep
        matrices[mode]={r:prep.transform(f.loc[roles==r]) for r in ['train','validation']}
        names=prep.get_feature_names_out();exclude=['num__'+x for x in POLICY+EXTERNAL]+['num__missingindicator_'+x for x in POLICY+EXTERNAL]
        common=np.array([x not in exclude for x in names]);h=pd.util.hash_pandas_object(pd.DataFrame(prep.transform(f)[:,common]),index=False)
        assert pd.DataFrame({'h':h,'r':roles}).groupby('h').r.nunique().max()==1,'New encoded duplicates cross roles'
    for method,mode,noext in [('sign_lr','raw',False),('capped_sign_lr','cap30',False),('capped_lr_no_external','cap30',True)]:
        prep=preps[mode];names=prep.get_feature_names_out();excluded=['num__'+x for x in EXTERNAL]+['num__missingindicator_'+x for x in EXTERNAL]
        mask=np.array([not noext or n not in excluded for n in names]);signs=np.array([DIRECTIONS.get(n.removeprefix('num__'),0) for n in names[mask]])
        candidates=[]
        for ridge in [.0001,.001,.01]:
            model=SignedLogit(ridge,signs).fit(matrices[mode]['train'][:,mask],y)
            p=model.predict_proba(matrices[mode]['validation'][:,mask])[:,1]
            met=metrics(vy,p);selections.append({'method':method,'ridge':ridge,'min_samples_leaf':None,**met,'iterations':model.iterations,'projected_gradient':model.projected_gradient})
            candidates.append((met['AUC'],ridge,model))
        auc,ridge,model=max(candidates,key=lambda t:(t[0],t[1]));chosen[method]={'ridge':ridge,'validation_auc':auc}
        bundles[method]={'version':VERSION,'kind':'single','feature_mode':mode,'model':model,'preprocessor':prep,'mask':mask,'feature_names':names,'calibrator':None,'seed':seed}
    prep=preps['cap30'];names=prep.get_feature_names_out();mask=np.ones(len(names),bool);signs=[DIRECTIONS.get(n.removeprefix('num__'),0) for n in names]
    candidates=[]
    for leaf in [20,60,120]:
        model=HistGradientBoostingClassifier(learning_rate=.05,max_leaf_nodes=15,max_iter=160,l2_regularization=10.,min_samples_leaf=leaf,early_stopping=False,monotonic_cst=signs,random_state=seed)
        model.fit(matrices['cap30']['train'],y);p=model.predict_proba(matrices['cap30']['validation'])[:,1];met=metrics(vy,p)
        selections.append({'method':'capped_tree','ridge':None,'min_samples_leaf':leaf,**met})
        candidates.append((met['AUC'],leaf,model))
    auc,leaf,model=max(candidates,key=lambda t:(t[0],t[1]));chosen['capped_tree']={'min_samples_leaf':leaf,'validation_auc':auc}
    bundles['capped_tree']={'version':VERSION,'kind':'single','feature_mode':'cap30','model':model,'preprocessor':prep,'mask':mask,'feature_names':names,'calibrator':None,'seed':seed}
    ref=val.limit.to_numpy();old=predict(bundles['baseline_mono_anchor'],val,ref,False);linear=predict(bundles['capped_sign_lr'],val,ref,False);baseline=metrics(vy,old)
    changed=scenario(val,'ordinary_dpd',30);oldq=predict(bundles['baseline_mono_anchor'],changed,ref,False);linearq=predict(bundles['capped_sign_lr'],changed,ref,False)
    zero=(val.dpd.eq(0)&val.dpd_def.eq(0)).to_numpy();trials=[]
    for alpha in [0.,.1,.25,.5,.75,1.]:
        p=(1-alpha)*old+alpha*linear;q=(1-alpha)*oldq+alpha*linearq
        m=metrics(vy,p);row={'alpha':alpha,**m,'initial_zero_n':int(zero.sum()),'strict_increase_zero':float(np.mean(q[zero]>p[zero]+1e-10)),'median_pd_change_zero':float(np.median(q[zero]-p[zero]))}
        row['eligible']=bool(m['AUC']>=baseline['AUC']-.005 and m['Brier']<=baseline['Brier']+.001 and row['strict_increase_zero']>=.99 and row['median_pd_change_zero']>=.001)
        trials.append(row)
    eligible=[t for t in trials if t['eligible']];best=max(eligible or trials,key=lambda t:(t['AUC'],-t['alpha']))
    bundles['hybrid']={'version':VERSION,'kind':'hybrid','alpha':best['alpha'],'baseline':bundles['baseline_mono_anchor'],'linear':bundles['capped_sign_lr'],'calibrator':None,'seed':seed,'development_gate_passed':bool(eligible)}
    # Raw validation contracts for the selected blend, before test evaluation or calibration fitting.
    hp=predict(bundles['hybrid'],val,ref,False)
    np.testing.assert_array_equal(hp,predict(bundles['hybrid'],scenario(val,'pure_limit',.5),ref,False))
    for kind,d in [('balance_up',0),('joint_dpd',30)]:assert np.all(predict(bundles['hybrid'],scenario(val,kind,d),ref,False)>=hp-1e-12)
    assert np.all(predict(bundles['hybrid'],scenario(val,'payment_up'),ref,False)<=hp+1e-12)
    cal=parts['calibration'];calibration=[]
    for name in NEW:
        p=predict(bundles[name],cal,cal.limit.to_numpy(),False)
        model=LogisticRegression(C=1e6).fit(logit(p).reshape(-1,1),cal.TARGET)
        assert model.coef_[0,0]>0
        bundles[name]['calibrator']=model
        calibration.append({'method':name,'slope':float(model.coef_[0,0]),'intercept':float(model.intercept_[0])})
        joblib.dump(bundles[name],M/f'{seed}_{name}.joblib',compress=3)
    write_json(R/f'{seed}_selection.json',{'seed':seed,'protocol_sha256':digest(ROOT/'docs/实验协议.md'),'chosen':chosen,'candidate_trials':selections,'hybrid_trials':trials,'hybrid_selected_alpha':best['alpha'],'development_gate_passed':bool(eligible),'calibrators':calibration,'split_counts':{r:len(x) for r,x in parts.items()},'used_test_labels_for_selection':False})
    return bundles,parts

def diagnostics(bundles,parts,seed,full):
    test=parts['test'];ref=test.limit.to_numpy();p0={m:predict(b,test,ref) for m,b in bundles.items()}
    pred=test[['SK_ID_CURR','TARGET']].copy();pred['seed']=seed
    performance=[]
    for method,p in p0.items():
        pred[method]=p
        for calibrated in [False,True]:
            a=p if calibrated else predict(bundles[method],test,ref,False)
            performance.append({'seed':seed,'method':method,'calibrated':calibrated,**metrics(test.TARGET,a)})
    specs=[('pure_limit',d) for d in [.1,.2,.3,.5,1.]]+[('balance_up',0.),('limit_plus_balance',.5),('payment_up',0.)]+[(kind,float(day)) for kind in ['ordinary_dpd','joint_dpd'] for day in [1,7,30,60,90,180]]+[('clear_dpd',0.)] if full else [('pure_limit',.5),('balance_up',0.),('payment_up',0.),('ordinary_dpd',30.),('joint_dpd',30.)]
    rows=[];long=[];zero=(test.dpd.eq(0)&test.dpd_def.eq(0)).to_numpy()
    for kind,d in specs:
        changed=scenario(test,kind,d)
        affected=(changed.balance!=test.balance).to_numpy() if kind in ['balance_up','limit_plus_balance'] else ((changed.payment!=test.payment).to_numpy() if kind=='payment_up' else (test.dpd.gt(0)|test.dpd_def.gt(0)).to_numpy() if kind=='clear_dpd' else np.ones(len(test),bool))
        for method,bundle in bundles.items():
            p=p0[method];q=predict(bundle,changed,ref)
            for group,mask in [('all',np.ones(len(test),bool)),('initial_zero_dpd',zero),('initial_positive_dpd',~zero)]:
                m=mask&affected
                if m.any():rows.append({'seed':seed,'method':method,'scenario':kind,'severity':d,'group':group,'n':int(mask.sum()),'affected_n':int(m.sum()),'affected_increase':float(np.mean(q[m]>p[m]+1e-10)),'affected_decrease':float(np.mean(q[m]<p[m]-1e-10)),'affected_flat':float(np.mean(abs(q[m]-p[m])<=1e-10)),'affected_median_pd_change':float(np.median(q[m]-p[m])),**instability(p[mask],q[mask])})
            if full:long.append(pd.DataFrame({'SK_ID_CURR':test.SK_ID_CURR,'method':method,'scenario':kind,'severity':d,'pd':q}))
            if kind=='pure_limit' and method!='baseline_consistency':np.testing.assert_array_equal(p,q)
            if method in MONO:
                if kind in ['balance_up','limit_plus_balance','ordinary_dpd','joint_dpd']:assert np.all(q>=p-1e-12)
                if kind in ['payment_up','clear_dpd']:assert np.all(q<=p+1e-12)
    if full:pd.concat(long,ignore_index=True).to_csv(R/'scenario_predictions.csv',index=False)
    return pred,performance,rows

def main():
    manifest=read_json(ROOT/'data/input_manifest.json');assert digest(ROOT/'docs/实验协议.md')==manifest['protocol_sha256']
    for path,h in manifest['frozen_inputs'].items():assert digest(ROOT/path)==h,path
    df=pd.read_csv(ROOT/'data/cohort.csv',float_precision='round_trip')
    split=pd.read_csv(ROOT/'data/split_manifest.csv',dtype={'group':str});repeated=pd.read_csv(ROOT/'data/repeated_splits.csv',dtype={'group':str})
    ps=[];performances=[];scenarios=[]
    for seed in SEEDS:
        roles=split if seed==SEEDS[0] else repeated[repeated.seed==seed]
        bundles,parts=fit(df,roles,seed);p,perf,stress=diagnostics(bundles,parts,seed,seed==SEEDS[0])
        ps.append(p);performances.extend(perf);scenarios.extend(stress)
        pd.concat(ps,ignore_index=True).to_csv(R/'predictions.csv',index=False)
        pd.DataFrame(performances).to_csv(R/'performance.csv',index=False)
        pd.DataFrame(scenarios).to_csv(R/'scenario_metrics.csv',index=False)
        sel=read_json(R/f'{seed}_selection.json')
        print('Completed',seed,'hybrid alpha',sel['hybrid_selected_alpha'],'validation gate',sel['development_gate_passed'],flush=True)
    print('All six experiments complete; 30 new models retained.',flush=True)

if __name__=='__main__':
    with threadpool_limits(limits=1):main()
