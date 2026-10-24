"""Adapter around the unchanged, hash-checked C model. No fitting occurs here."""
import os
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import sys, math, json, hashlib, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from schema import FIELDS, BY_KEY, SCENARIOS

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
RUNTIME = ROOT / 'model_runtime'
sys.path.insert(0,str(RUNTIME/'src'))
import study_common
study_common.ROOT = RUNTIME
import predict as original
from risk_model import score
MODEL = RUNTIME/'models/20260923_rolling_hybrid.joblib'
EXPECTED_SHA = '70576bba02e2207188626878673a1bdd8409bc45180f8e637f258536d12694cf'
BUNDLE = None
LOAD_WARNINGS = []

def load():
    global BUNDLE, LOAD_WARNINGS
    if BUNDLE is None:
        if hashlib.sha256(MODEL.read_bytes()).hexdigest() != EXPECTED_SHA:
            raise RuntimeError('模型文件校验失败，请重新解压完整提交包。')
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            BUNDLE = joblib.load(MODEL)
        LOAD_WARNINGS = sorted(set(str(w.message) for w in caught))
    return BUNDLE

def number(value,label,low=None,high=None,integer=False):
    if isinstance(value,bool): raise ValueError(label+'必须填写数字。')
    try: n=float(value)
    except (TypeError,ValueError): raise ValueError(label+'必须填写数字。')
    if not math.isfinite(n): raise ValueError(label+'必须是有限数值。')
    if low is not None and n<low: raise ValueError(label+f'不能小于 {low}。')
    if high is not None and n>high: raise ValueError(label+f'不能大于 {high}。')
    if integer and n!=int(n): raise ValueError(label+'必须是整数。')
    return n

def normalize(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get('inputs'),dict): raise ValueError('请输入客户信息。')
    inputs=payload['inputs']; x={'SK_ID_CURR':0}; missing=[]
    extra=set(inputs)-set(BY_KEY)
    if extra: raise ValueError('输入包含未支持的字段：'+', '.join(sorted(extra)))
    for f in FIELDS:
        key=f['key']; v=inputs.get(key)
        if v is None or v=='':
            if f['required']: raise ValueError('请填写'+f['label']+'；未知时不能直接评估。')
            x[key]=np.nan;missing.append(f['label']);continue
        if f['options']:
            if v not in {p[0] for p in f['options']}: raise ValueError(f['label']+'不在支持的类别中。')
            x[key]=v
        else:
            x[key]=number(v,f['label'],f['min'],f['max'],f['integer'])*f['scale']
    if x['limit']<=0 or x['AMT_INCOME_TOTAL']<=0: raise ValueError('收入和当前额度必须大于 0。')
    if x['dpd_def']>x['dpd']: raise ValueError('容忍口径逾期天数不能超过普通逾期天数。')
    if np.isfinite(x['DAYS_EMPLOYED']) and np.isfinite(x['DAYS_BIRTH']) and x['DAYS_EMPLOYED']<x['DAYS_BIRTH']:
        raise ValueError('就业年限不能超过年龄。')
    ref=payload.get('reference',{})
    if not isinstance(ref,dict): raise ValueError('参考额度设置格式错误。')
    mode=ref.get('mode','current')
    if mode not in ['current','fixed']: raise ValueError('未知的参考额度方式。')
    limit=x['limit'] if mode=='current' else number(ref.get('limit'),'参考额度',0)
    if limit<=0: raise ValueError('参考额度必须大于 0。')
    label=payload.get('customer_label','未命名客户')
    if not isinstance(label,str) or len(label)>80: raise ValueError('客户代号请控制在 80 字以内。')
    return x,limit,missing,mode,label

REASONS={
 'rolling_dpd_at_or_above_30_day_cap':'窗口峰值已达到 30 天封顶，进一步恶化可能不改变评分。',
 'current_recorded_delinquency':'当前存在逾期记录，需要结合金额和实际情况复核。',
 'raw_input_outside_training_range':'部分当前输入超出训练样本范围，概率水平需要复核。',
 'new_or_worsened_recorded_delinquency':'出现新增或加重逾期，即使评分持平仍需复核。',
}

def evaluate(x,ref,previous=None):
    p={'reference_limit':ref,'reference_source':'pre_policy_snapshot','current':x}
    if previous is not None:p['previous']=previous
    r=original.evaluate(p,load())
    r['live_score']=float(score(r['live_pd']))
    r['review_messages']=[REASONS.get(k,k) for k in r['review_reasons']]
    r['outside_training_labels']=[BY_KEY[k]['label'] for k in r['outside_training_range']]
    r['reasons_are_causal']=False
    return r

def clean(value):
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if isinstance(value,(float,np.floating)):return float(value) if math.isfinite(value) else None
    if isinstance(value,np.integer):return int(value)
    return value

def run(payload):
    x,ref,missing,mode,label=normalize(payload)
    base=evaluate(x,ref)
    scenario=payload.get('scenario',{})
    if not isinstance(scenario,dict):raise ValueError('情景设置格式错误。')
    kind=scenario.get('kind','pure_limit')
    if kind not in {s['id'] for s in SCENARIOS}:raise ValueError('未知情景。')
    increase=number(scenario.get('limit_percent',50),'提额比例',0,1000)
    debt=number(scenario.get('debt_amount',x['balance']*.25),'新增借款',0)
    days=number(scenario.get('dpd_days',30),'新增逾期天数',0,3650,True)
    payment=number(scenario.get('payment_amount',x['payment']*.25),'增加付款',0)
    changed=x.copy()
    if kind in ['pure_limit','combined']:changed['limit']*=1+increase/100
    if kind in ['new_debt','combined']:changed['balance']+=debt;changed['drawings']+=debt
    if kind in ['ordinary_dpd','joint_dpd']:changed['dpd']+=days
    if kind=='joint_dpd':changed['dpd_def']+=days
    if kind=='payment':changed['payment']+=payment
    after=evaluate(changed,ref,x)
    after['reference_delta']=after['score']-base['score']
    after['live_delta']=after['live_score']-base['live_score']
    after['grade_before']=base['grade']
    after['kind']=kind
    after['changed_fields']=[dict(key=k,label=BY_KEY[k]['label'],before=x[k],after=changed[k]) for k in changed if k in BY_KEY and np.isscalar(x[k]) and isinstance(x[k],(int,float)) and math.isfinite(x[k]) and changed[k]!=x[k]]
    # These are controlled input-response curves, not SHAP or observed trajectories.
    limit_curve=[]
    for step in [0,10,20,30,50,100]:
        z=x.copy();z['limit']*=1+step/100;r=evaluate(z,ref)
        limit_curve.append(dict(x=step,reference=r['score'],live=r['live_score']))
    dpd_curve=[]
    for step in [0,1,7,15,30,60,90]:
        z=x.copy();z['dpd']+=step;r=evaluate(z,ref)
        dpd_curve.append(dict(x=step,reference=r['score']))
    complete=len(FIELDS)-len(missing)
    notices=[]
    if missing:notices.append(f'{len(missing)} 项选填信息缺失，已沿用模型训练时的缺失处理；本结果不能替代完整信息评估。')
    if all(pd.isna(x[k]) for k in ['EXT_SOURCE_1','EXT_SOURCE_2','EXT_SOURCE_3']):notices.append('三个外部评分均缺失。此处仍使用原模型的缺失处理，不是经过重训验证的“去外部评分模型”。')
    if pd.isna(x['hist_max_dpd']):notices.append('历史最大逾期未知，窗口分支采用已知当前逾期并保留缺失标记。')
    if mode=='current':notices.append('本次以当前额度建立研究参考；后续情景固定此参考。独立重新评估会重新建立参考。')
    else:notices.append('参考额度由使用者提供，系统未认证其来源或适用账户集合。')
    result=dict(customer_label=label,base=base,scenario=after,curves=dict(limit=limit_curve,dpd=dpd_curve),quality=dict(provided=complete,total=len(FIELDS),missing=missing,notices=notices),reference_mode=mode,model=dict(version=study_common.VERSION,sha256=EXPECTED_SHA,tree_weight=.75,lr_weight=.25),scope='对公开数据当前申请 TARGET 的研究估计；不是银行征信分、固定一年违约率或自动授信结论。',normalized_input=x,reference_limit=ref)
    return clean(result)

def raw_to_form(record):
    return {f['key']:(record.get(f['key']) if f['options'] else (float(record[f['key']])/f['scale'] if record.get(f['key']) is not None else None)) for f in FIELDS}

EXAMPLES={
 'pure_limit':('纯提额，观察参考分不变','pure_limit',0),
 'new_debt':('新增借款，观察负债响应','new_debt',0),
 'new_ordinary_dpd':('新增普通逾期','ordinary_dpd',30),
 'new_joint_dpd':('两类逾期同时增加','joint_dpd',30),
 'saturated_but_worsening':('封顶后恶化，仍须复核','joint_dpd',30),
}

def example(key):
    if key not in EXAMPLES:raise ValueError('不存在的示例。')
    p=json.loads((RUNTIME/'examples'/f'{key}.json').read_text(encoding='utf-8'))
    old=p['previous'];now=p['current'];title,kind,days=EXAMPLES[key]
    return dict(customer_label='公开案例 '+str(old['SK_ID_CURR']),inputs=raw_to_form(old),reference=dict(mode='fixed',limit=p['reference_limit']),scenario=dict(kind=kind,limit_percent=(now['limit']/old['limit']-1)*100,debt_amount=max(0,now['balance']-old['balance']),dpd_days=max(now['dpd']-old['dpd'],0),payment_amount=0),example_note='使用公开测试记录；事件和变化由研究者构造，不是真实银行客户轨迹。',title=title)
