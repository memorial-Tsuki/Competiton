"""Common feature, calibration and scoring contract for the unified experiment."""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit

VERSION='homecredit-anchor-v4-20260923'
CATS=['NAME_EDUCATION_TYPE','NAME_INCOME_TYPE','NAME_HOUSING_TYPE','NAME_CONTRACT_TYPE']
POLICY=['cc_limit_log','cc_util_log','cc_limit_income_log']
EXTERNAL=['EXT_SOURCE_1','EXT_SOURCE_2','EXT_SOURCE_3']
DIRECTIONS={'cc_balance_log':1,'cc_util_log':1,'cc_balance_income_log':1,'cc_drawings_log':1,'cc_drawings_income_log':1,'cc_dpd_log':1,'cc_dpd_def_log':1,'cc_payment_log':-1,'cc_payment_balance_log':-1}
VIEWS={'lr':'lr','consistency':'consistency','lr_no_limit':'lr_no_limit','lr_anchor':'lr','hgb_live':'hgb_free','hgb_anchor':'hgb_free','mono_live':'hgb_mono','mono_anchor':'hgb_mono','hgb_no_limit':'hgb_no_limit','mono_no_external':'hgb_no_external'}
ANCHORS={'lr_anchor','hgb_anchor','mono_anchor','mono_no_external'}


def features(df,reference=None):
    f=pd.DataFrame(index=df.index)
    for c in ['limit','balance','drawings','payment','dpd','dpd_def','AMT_INCOME_TOTAL']:
        if c not in df or not np.isfinite(df[c].to_numpy(float)).all():raise ValueError('Missing or nonfinite current input: '+c)
        if (df[c]<0).any():raise ValueError('Negative current input: '+c)
    if (df.limit<=0).any() or (df.AMT_INCOME_TOTAL<=0).any():raise ValueError('Positive current limit and income required')
    limit=df.limit.to_numpy(float) if reference is None else np.asarray(reference,float)
    if limit.ndim==0:limit=np.full(len(df),float(limit))
    if limit.shape!=(len(df),) or not np.isfinite(limit).all() or (limit<=0).any():raise ValueError('Reference must be finite, positive and match row count')
    positive=lambda x:np.log1p(np.maximum(x,0))
    income=df.AMT_INCOME_TOTAL
    for c in EXTERNAL+['CNT_CHILDREN']:f[c]=df[c]
    f['age_years']=-df.DAYS_BIRTH/365.25
    f['employment_years']=-df.DAYS_EMPLOYED.where(df.DAYS_EMPLOYED.le(0))/365.25
    f['income_log']=positive(income)
    f['application_credit_income_log']=positive(df.AMT_CREDIT/income)
    f['application_annuity_income_log']=positive(df.AMT_ANNUITY/income)
    for c in CATS:f[c]=df[c].fillna('Missing').astype(str)
    for src,dst in [('balance','cc_balance_log'),('drawings','cc_drawings_log'),('payment','cc_payment_log'),('dpd','cc_dpd_log'),('dpd_def','cc_dpd_def_log')]:f[dst]=positive(df[src])
    f['cc_limit_log']=positive(limit)
    f['cc_util_log']=positive(df.balance/limit)
    f['cc_balance_income_log']=positive(df.balance/income)
    f['cc_limit_income_log']=positive(limit/income)
    f['cc_drawings_income_log']=positive(df.drawings/income)
    f['cc_payment_balance_log']=positive(df.payment/(df.balance+1))
    f['active_cards']=df.active_cards
    for c in ['hist_mean_balance','hist_mean_drawings','hist_mean_payment','hist_max_dpd','prev_count','prev_credit_mean','inst_count','inst_shortfall_sum','inst_payment_ratio']:f[c+'_log']=positive(df[c])
    for c in ['hist_late_rate','hist_months','prev_refused_rate','prev_latest_day','inst_shortfall_rate','inst_not_paid_by_due_rate','inst_unknown_payment_rate']:f[c]=df[c]
    return f.replace([np.inf,-np.inf],np.nan)


def scenario(df,name,delta=0.):
    x=df.copy()
    if name in ['pure_limit','limit_plus_balance']:x['limit']=x.limit*(1+delta)
    if name in ['balance_up','limit_plus_balance']:
        extra=x.balance*.25;x['balance']=x.balance+extra;x['drawings']=x.drawings+extra
    if name in ['dpd_up','dpd_raw_only']:x['dpd']=x.dpd+30
    if name=='dpd_up':x['dpd_def']=x.dpd_def+30
    if name=='payment_up':x['payment']=x.payment*1.25
    return x


def logit(p):
    p=np.clip(p,1e-6,1-1e-6);return np.log(p/(1-p))


def predict(bundle,df,reference=None,calibrated=True):
    if bundle.get('version')!=VERSION:raise ValueError('Saved model version differs from scoring contract')
    x=bundle['preprocessor'].transform(features(df,reference))[:,bundle['mask']]
    p=bundle['model'].predict_proba(x)[:,1]
    if calibrated and bundle.get('calibrator') is not None:p=bundle['calibrator'].predict_proba(logit(p).reshape(-1,1))[:,1]
    return p


def score(p):return np.clip(600+40/np.log(2)*(-np.log(19)-logit(p)),300,850)
def grade(p):return np.digitize(p,[.03,.06,.1,.2])


class PenalizedLogit:
    def __init__(self,strength=0.,ridge=.001):self.strength,self.ridge=strength,ridge
    def fit(self,x,y,covariance,initial=None):
        n,k=x.shape
        def objective(w):
            z=x@w[:-1]+w[-1];err=expit(z)-y
            loss=np.mean(np.logaddexp(0,z)-y*z)+.5*self.ridge*np.dot(w[:-1],w[:-1])+.5*self.strength*np.dot(w[:-1],covariance@w[:-1])
            gradient=x.T@err/n+self.ridge*w[:-1]+self.strength*(covariance@w[:-1])
            return loss,np.r_[gradient,err.mean()]
        start=np.zeros(k+1) if initial is None else initial.copy()
        if initial is None:start[-1]=np.log(y.mean()/(1-y.mean()))
        result=minimize(objective,start,jac=True,method='L-BFGS-B',options={'maxiter':800,'ftol':1e-11,'gtol':1e-6})
        if not result.success:raise RuntimeError(result.message)
        self.w=result.x;self.iterations=result.nit
        return self
    def predict_proba(self,x):
        p=expit(x@self.w[:-1]+self.w[-1]);return np.c_[1-p,p]
