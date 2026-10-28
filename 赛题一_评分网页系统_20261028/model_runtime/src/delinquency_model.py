"""Learned nonnegative DPD responses, with explicit cap and saturation semantics."""
import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.optimize import minimize
from study_common import VERSION
from risk_model import features as original_features,predict as baseline_predict,logit,scenario as original_scenario

class SignedLogit:
    def __init__(self,ridge=.001,signs=None):self.ridge,self.signs=ridge,signs
    def fit(self,x,y):
        n,k=x.shape;y=np.asarray(y,float)
        signs=np.zeros(k) if self.signs is None else np.asarray(self.signs)
        bounds=[(0.,None) if s>0 else ((None,0.) if s<0 else (None,None)) for s in signs]+[(None,None)]
        def objective(w):
            z=x@w[:-1]+w[-1];error=expit(z)-y
            return np.mean(np.logaddexp(0,z)-y*z)+self.ridge*np.dot(w[:-1],w[:-1])/2,np.r_[x.T@error/n+self.ridge*w[:-1],error.mean()]
        start=np.zeros(k+1);start[-1]=np.log(y.mean()/(1-y.mean()))
        fit=minimize(objective,start,jac=True,bounds=bounds,method='L-BFGS-B',options={'maxiter':1000,'ftol':1e-12,'gtol':1e-7})
        if not fit.success:raise RuntimeError(fit.message)
        self.w=fit.x;self.iterations=fit.nit;self.objective=float(fit.fun)
        g=fit.jac.copy();active=((signs>0)&(self.w[:-1]<1e-8)&(g[:-1]>0))|((signs<0)&(self.w[:-1]>-1e-8)&(g[:-1]<0));g[:-1][active]=0
        self.projected_gradient=float(np.max(abs(g)))
        assert np.all(self.w[:-1][signs>0]>=-1e-12) and np.all(self.w[:-1][signs<0]<=1e-12)
        return self
    def predict_proba(self,x):
        p=expit(x@self.w[:-1]+self.w[-1]);return np.c_[1-p,p]

def features(df,mode='raw',reference=None):
    f=original_features(df,reference)
    if mode in ['cap30','shared_cap30']:
        f['cc_dpd_log']=np.log1p(np.minimum(df.dpd,30))
        f['cc_dpd_def_log']=np.log1p(np.minimum(df.dpd_def,30))
        if mode=='shared_cap30':
            f['cc_shared_dpd_log']=(f['cc_dpd_log']+f['cc_dpd_def_log'])/2
            f=f.drop(columns=['cc_dpd_log','cc_dpd_def_log'])
    elif mode=='rolling_cap30':
        peak=np.fmax(df.hist_max_dpd.to_numpy(float),np.maximum(df.dpd.to_numpy(float),df.dpd_def.to_numpy(float)))
        f['cc_rolling_dpd_log']=np.log1p(np.minimum(peak,30))
        f['hist_dpd_missing']=df.hist_max_dpd.isna().astype(float)
        f=f.drop(columns=['cc_dpd_log','cc_dpd_def_log','hist_max_dpd_log'])
    elif mode!='raw':raise ValueError('Unknown feature mode')
    return f

def predict(bundle,df,reference=None,calibrated=True):
    if bundle.get('version')!=VERSION:raise ValueError('Enhanced model version mismatch')
    if bundle['kind']=='baseline':
        return baseline_predict(bundle['original'],df,reference if bundle['anchored'] else None,calibrated)
    if bundle['kind']=='hybrid':
        a=predict(bundle['baseline'],df,reference,False);b=predict(bundle['linear'],df,reference,False)
        p=(1-bundle['alpha'])*a+bundle['alpha']*b
    elif bundle['kind']=='single':
        x=bundle['preprocessor'].transform(features(df,bundle['feature_mode'],reference))[:,bundle['mask']]
        p=bundle['model'].predict_proba(x)[:,1]
    else:raise ValueError('Unknown model kind')
    if calibrated and bundle.get('calibrator') is not None:p=bundle['calibrator'].predict_proba(logit(p).reshape(-1,1))[:,1]
    return p

def scenario(df,kind,severity=0.):
    if kind in ['pure_limit','balance_up','limit_plus_balance','payment_up']:return original_scenario(df,kind,severity)
    x=df.copy()
    if kind in ['ordinary_dpd','joint_dpd']:
        if not np.isfinite(severity) or severity<0:raise ValueError('Invalid DPD increment')
        x['dpd']=x.dpd+severity
        if kind=='joint_dpd':x['dpd_def']=x.dpd_def+severity
    elif kind=='clear_dpd':x['dpd']=0.;x['dpd_def']=0.
    else:raise ValueError('Unknown scenario')
    return x
