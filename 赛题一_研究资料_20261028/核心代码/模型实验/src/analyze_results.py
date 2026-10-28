"""Joint review of every candidate, including failed development gates."""
from study_common import ROOT,SEEDS,read_json,write_json
import numpy as np,pandas as pd,joblib
from scipy.stats import rankdata
from sklearn.metrics import roc_auc_score,average_precision_score
from threadpoolctl import threadpool_limits
from run_experiment import baseline_bundles,BASE,NEW
from delinquency_model import predict,features
from evaluation import metrics,instability

R=ROOT/'results';METHODS=list(BASE)+NEW+['shared_lr','shared_hybrid','rolling_lr','rolling_hybrid']
def load_models(seed):
    return {**baseline_bundles(seed),**{m:joblib.load(ROOT/f'models/{seed}_{m}.joblib') for m in METHODS if m not in BASE}}

def independent_metrics(y,p):
    y=np.asarray(y,int);p=np.asarray(p,float);n=len(y);n1=y.sum();n0=n-n1
    auc=(rankdata(p)[y==1].sum()-n1*(n1+1)/2)/(n1*n0)
    order=np.argsort(-p);ys=y[order];ps=p[order];ends=np.r_[np.flatnonzero(ps[:-1]!=ps[1:]),n-1]
    tp=np.cumsum(ys)[ends];fp=ends+1-tp;bins=np.clip(np.floor(p*10).astype(int),0,9)
    ece=sum(abs(np.sum(y[bins==b]-p[bins==b])) for b in range(10))/n
    q=np.clip(p,np.finfo(float).eps,1-np.finfo(float).eps);slots=int(np.ceil(n*.1));cut=np.sort(p)[-slots];hi=p>cut;tie=p==cut
    return {'AUC':auc,'AP':np.sum(np.diff(np.r_[0,tp])/n1*tp/(ends+1)),'KS':np.max(tp/n1-fp/n0),'Brier':np.mean((y-p)**2),'LogLoss':-np.mean(y*np.log(q)+(1-y)*np.log1p(-q)),'ECE':ece,'Top10Recall':(y[hi].sum()+(slots-hi.sum())*y[tie].mean())/n1}

def three(y,p):return np.array([roc_auc_score(y,p),average_precision_score(y,p),np.mean((y-p)**2)])

def main():
    df=pd.read_csv(ROOT/'data/cohort.csv',float_precision='round_trip').set_index('SK_ID_CURR',drop=False)
    splits=pd.read_csv(ROOT/'data/split_manifest.csv',dtype={'group':str});roles=splits.set_index('SK_ID_CURR').loc[df.index,'role'];test=df.loc[roles=='test'];train=df.loc[roles=='train']
    predictions=pd.read_csv(R/'predictions.csv',float_precision='round_trip');pred=predictions[predictions.seed==SEEDS[0]].set_index('SK_ID_CURR').loc[test.index];y=test.TARGET.to_numpy();perf=pd.read_csv(R/'performance.csv')
    mainperf=perf[(perf.seed==SEEDS[0])&perf.calibrated].set_index('method')
    for m in METHODS:
        for k,v in independent_metrics(y,pred[m].to_numpy()).items():np.testing.assert_allclose(v,mainperf.loc[m,k],atol=1e-12,rtol=0)
    support=[]
    for role in ['train','validation','calibration','test']:
        a=df.loc[roles==role]
        for field in ['dpd','dpd_def']:
            group=pd.cut(a[field],[-.1,0,1,7,30,90,np.inf],labels=['0','1','2-7','8-30','31-90','>90'])
            for label,g in a.groupby(group,observed=True):
                n=len(g);phat=g.TARGET.mean();z=1.95996398454;denom=1+z*z/n;center=(phat+z*z/(2*n))/denom;radius=z*np.sqrt(phat*(1-phat)/n+z*z/(4*n*n))/denom
                support.append({'role':role,'field':field,'bin':str(label),'n':n,'positives':int(g.TARGET.sum()),'target_rate':phat,'wilson_low':center-radius,'wilson_high':center+radius,'median_balance':g.balance.median(),'other_field_zero_fraction':float(g['dpd_def' if field=='dpd' else 'dpd'].eq(0).mean())})
    pd.DataFrame(support).to_csv(R/'field_support.csv',index=False)
    coefficients=[];gates=[];usage=[]
    for seed in SEEDS:
        models=load_models(seed)
        for m in ['sign_lr','capped_sign_lr','capped_lr_no_external','shared_lr','rolling_lr']:
            b=models[m];names=b['feature_names'];active=np.flatnonzero(b['mask']);scale=b['preprocessor'].named_transformers_['num'].named_steps['standardscaler'].scale_
            for j,k in enumerate(active):
                name=names[k]
                if 'dpd' in name:coefficients.append({'seed':seed,'method':m,'feature':name,'standardized_weight':float(b['model'].w[j]),'coefficient_per_feature_unit':float(b['model'].w[j]/scale[k]) if name.startswith('num__') else np.nan,'calibration_slope':float(b['calibrator'].coef_[0,0])})
        for prefix,suffix in [('A',''),('B','_shared'),('C','_rolling')]:
            s=read_json(R/f'{seed}{suffix}_selection.json');gates.append({'seed':seed,'phase':prefix,'alpha':s['hybrid_selected_alpha'],'gate_passed':s['development_gate_passed']})
        for method in ['baseline_mono_anchor','capped_tree']:
            b=models[method]['original'] if method.startswith('baseline') else models[method];model=b['model'];names=np.asarray(b['feature_names'])[b['mask']]
            for k,name in enumerate(names):
                if 'dpd' not in name:continue
                count=sum(int(((tree.nodes['feature_idx']==k)&~tree.nodes['is_leaf'].astype(bool)).sum()) for it in model._predictors for tree in it)
                usage.append({'seed':seed,'method':method,'feature':name,'bin_boundaries':len(model._bin_mapper.bin_thresholds_[k]),'selected_splits':count})
    pd.DataFrame(coefficients).to_csv(R/'delinquency_coefficients.csv',index=False);pd.DataFrame(gates).to_csv(R/'development_gates.csv',index=False);pd.DataFrame(usage).to_csv(R/'tree_field_usage.csv',index=False)
    models=load_models(SEEDS[0]);trans=pd.read_csv(ROOT/'data/observed_transitions.csv',float_precision='round_trip').set_index('SK_ID_CURR');trans=trans.loc[trans.index.intersection(test.index)].copy();current=test.loc[trans.index];previous=current.copy();previous['dpd']=trans.previous_dpd;previous['dpd_def']=trans.previous_dpd_def
    observed=[];observed_summary=[]
    for m,b in models.items():
        p=predict(b,previous,current.limit.to_numpy());q=predict(b,current,current.limit.to_numpy())
        observed.append(pd.DataFrame({'SK_ID_CURR':trans.index,'method':m,'transition':trans.transition,'pd_with_previous_dpd':p,'pd_with_current_dpd':q}))
        for group in ['worsening','improving','unchanged','mixed']:
            mask=trans.transition.eq(group).to_numpy()
            if mask.any():observed_summary.append({'method':m,'transition':group,'n':int(mask.sum()),'increase':float(np.mean(q[mask]>p[mask]+1e-10)),'decrease':float(np.mean(q[mask]<p[mask]-1e-10)),'flat':float(np.mean(abs(q[mask]-p[mask])<=1e-10)),**instability(p[mask],q[mask])})
    pd.concat(observed,ignore_index=True).to_csv(R/'observed_transition_predictions.csv',index=False);pd.DataFrame(observed_summary).to_csv(R/'observed_transition_summary.csv',index=False)
    scenario_predictions=pd.read_csv(R/'scenario_predictions.csv',float_precision='round_trip');ladder=[]
    for m in METHODS:
        for kind in ['ordinary_dpd','joint_dpd']:
            previous=pred[m].to_numpy()
            for day in [1,7,30,60,90,180]:
                a=scenario_predictions[(scenario_predictions.method==m)&(scenario_predictions.scenario==kind)&(scenario_predictions.severity==day)].set_index('SK_ID_CURR').loc[test.index].pd.to_numpy()
                ladder.append({'method':m,'kind':kind,'increment_days':day,'n':len(test),'adjacent_increases':int((a>previous+1e-10).sum()),'adjacent_decreases':int((a<previous-1e-10).sum()),'adjacent_flat':int((abs(a-previous)<=1e-10).sum()),'mean_pd_change_from_initial':float(np.mean(a-pred[m].to_numpy()))})
                previous=a
    pd.DataFrame(ladder).to_csv(R/'response_ladder.csv',index=False)
    subgroup=[]
    masks={'zero_both':test.dpd.eq(0)&test.dpd_def.eq(0),'ordinary_1_30':test.dpd.gt(0)&test.dpd.le(30),'ordinary_over30':test.dpd.gt(30),'tolerant_positive':test.dpd_def.gt(0)}
    for group,mask in masks.items():
        for m in METHODS:
            a=pred[m].to_numpy()[mask.to_numpy()];yy=y[mask.to_numpy()]
            if len(a):subgroup.append({'group':group,'method':m,'n':len(a),'positives':int(yy.sum()),'mean_pd':float(a.mean()),'target_rate':float(yy.mean()),'mean_bias':float(np.mean(a-yy)),'Brier':float(np.mean((a-yy)**2))})
    pd.DataFrame(subgroup).to_csv(R/'subgroup_calibration.csv',index=False)
    targets=['sign_lr','capped_sign_lr','hybrid','shared_hybrid','rolling_lr','rolling_hybrid','capped_tree'];boot={m:[] for m in targets};biases=[];rng=np.random.default_rng(20260928);base=pred.baseline_mono_anchor.to_numpy()
    for _ in range(1000):
        ix=rng.integers(len(y),size=len(y));bm=three(y[ix],base[ix])
        for m in targets:boot[m].append(three(y[ix],pred[m].to_numpy()[ix])-bm)
        biases.append(float(np.mean(pred.rolling_hybrid.to_numpy()[ix]-y[ix])))
    intervals=[]
    for m in targets:
        diff=three(y,pred[m].to_numpy())-three(y,base);ci=np.quantile(boot[m],[.025,.975],axis=0)
        for i,k in enumerate(['AUC','AP','Brier']):intervals.append({'method':m,'baseline':'baseline_mono_anchor','metric':k,'difference':diff[i],'ci_low':ci[0,i],'ci_high':ci[1,i]})
    pd.DataFrame(intervals).to_csv(R/'paired_intervals.csv',index=False)
    repeated=perf[(perf.seed!=SEEDS[0])&perf.calibrated].groupby('method').agg(auc_mean=('AUC','mean'),auc_std=('AUC','std'),auc_min=('AUC','min'),auc_max=('AUC','max'),brier_mean=('Brier','mean'))
    repeated.to_csv(R/'repeat_summary.csv')
    raw_support={c:{'min':float(train[c].min()),'max':float(train[c].max())} for c in ['limit','balance','drawings','payment','dpd','dpd_def','AMT_INCOME_TOTAL']};write_json(R/'raw_training_support.json',raw_support)
    old=read_json(ROOT/'data/input_manifest.json');zero=masks['zero_both'].to_numpy();peak=test.hist_max_dpd.fillna(0).to_numpy()
    write_json(R/'diagnostic_summary.json',{'independent_metric_values_checked':len(METHODS)*7,'main_test_n':len(test),'main_test_initial_zero_dpd_n':int(zero.sum()),'initial_zero_with_historical_peak_ge30':int((zero&(peak>=30)).sum()),'observed_test_transitions':trans.transition.value_counts().to_dict(),'definition_exceeds_ordinary_all_cohort':int(df.dpd_def.gt(df.dpd).sum()),'rolling_hybrid_mean_bias':float(np.mean(pred.rolling_hybrid-y)),'rolling_hybrid_bias_ci':np.quantile(biases,[.025,.975]).tolist(),'bootstrap_repetitions':1000,'bootstrap_scope':'Fixed models, paired customer resamples; no duplicate common-input groups in main cohort; exploratory marginal intervals without multiple-testing correction.','development_status':'Sequential A/B/C feature development using training and validation; previously seen dataset and test baseline, not a new blind evaluation.','old_input_manifest_protocol':old['protocol_sha256']})
    print('All candidate diagnostics complete; independent values:',len(METHODS)*7,flush=True)

if __name__=='__main__':
    with threadpool_limits(limits=1):main()
