"""Publication figures from retained numerical results; no generated observations."""
from common import ROOT
import os
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/mplcache')
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.font_manager import fontManager,FontProperties

fontManager.addfont('C:/Windows/Fonts/msyh.ttc')
plt.rcParams.update({'font.family':FontProperties(fname='C:/Windows/Fonts/msyh.ttc').get_name(),'axes.unicode_minus':False,'font.size':11,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'path'})
R=ROOT/'results';F=R/'figures';F.mkdir(exist_ok=True)
NAVY='#112B43';TEAL='#00A99D';CORAL='#ED775B';BLUE='#477FC2';GRAY='#61788A'
LABEL={'lr':'普通 LR','consistency':'一致性 LR','lr_anchor':'参考额度 LR','hgb_live':'普通树 / 实时','hgb_anchor':'普通树 / 参考','mono_anchor':'单调树 / 参考','hgb_no_limit':'去额度单调树','mono_no_external':'去外部评分'}

def save(fig,name):
    for ext in ['png','svg','pdf']:fig.savefig(F/(name+'.'+ext),dpi=240,bbox_inches='tight',facecolor=fig.get_facecolor())
    plt.close(fig)

def hero():
    fig=plt.figure(figsize=(14,4.2),facecolor=NAVY);ax=fig.add_axes([0,0,1,1]);ax.set(xlim=(0,14),ylim=(0,4.2));ax.axis('off')
    ax.text(.45,3.55,'把额度策略的机械影响，与客户行为变化分开',fontsize=22,color='white',weight='bold')
    for x,num,title,subtitle in [(0.45,'01','观察真实提额','5,730 人固定事件窗口'),(3.95,'02','冻结参考额度','只隔离获批策略变动'),(7.45,'03','重算全部行为','余额 / 支用 / 付款 / 逾期')]:
        ax.add_patch(FancyBboxPatch((x,1.55),3.08,1.45,boxstyle='round,pad=.13',facecolor='#1C3B55',edgecolor='#30546C'))
        ax.text(x+.15,2.55,num,color='#60DFD2',fontsize=13,weight='bold');ax.text(x+.15,2.1,title,color='white',fontsize=15);ax.text(x+.15,1.7,subtitle,color='#C9DBE5',fontsize=10)
        if x<7:ax.annotate('',xy=(x+3.43,2.27),xytext=(x+3.22,2.27),arrowprops={'arrowstyle':'->','color':'#60DFD2','lw':2})
    ax.text(11.2,2.57,'双轨输出',color='#60DFD2',fontsize=16,weight='bold');ax.text(11.2,2.07,'稳定风险分',color='white',fontsize=14);ax.text(11.2,1.67,'+ 策略影响记录',color='#C9DBE5',fontsize=11)
    ax.plot([.45,13.55],[1.22,1.22],color='#426076',lw=.7)
    ax.text(.45,.7,'38,934',color='white',fontsize=23,weight='bold');ax.text(2.37,.7,'当前申请样本',color='#C9DBE5',fontsize=12)
    ax.text(5.0,.7,'0',color='#60DFD2',fontsize=25,weight='bold');ax.text(5.5,.7,'纯提额评分漂移（固定参考）',color='#C9DBE5',fontsize=12)
    ax.text(10.6,.73,'逾期变化 → 人工复核',color='#FFBAA8',fontsize=12);ax.text(.45,.19,'方法保证的是条件不变性；历史观察没有识别提额的因果效果。',color='#A9C0D0',fontsize=10)
    save(fig,'graphical_abstract')

def events():
    d=pd.read_csv(R/'event_curve.csv').set_index('relative_month');x=d.index.to_numpy()
    fig,axs=plt.subplots(1,2,figsize=(12,4.2),layout='constrained')
    for c,label,color in [('limit','平均额度',BLUE),('balance','平均余额',CORAL)]:axs[0].plot(x,100*d[c]/d.loc[-1,c],'-o',label=label,color=color,lw=2.5,ms=4)
    axs[0].set(ylabel='相对月 -1 的指数（=100）',xlabel='相对提额月份',title='额度与余额同时上升');axs[0].legend(frameon=False,loc='upper left')
    axs[1].plot(x,d.utilization*100,'-o',color=TEAL,lw=2.5,ms=4);axs[1].set(ylabel='客户使用率均值（%）',xlabel='相对提额月份',title='使用率却在事件月下降',ylim=(45,78))
    axs[1].annotate('71.1% → 51.4%',xy=(0,d.loc[0,'utilization']*100),xytext=(1.6,48),fontsize=12,color=NAVY,arrowprops={'arrowstyle':'->','color':GRAY})
    for ax in axs:ax.axvline(0,color=GRAY,ls='--',lw=1);ax.grid(alpha=.12);ax.set_xticks([-6,-3,-1,0,3,6])
    save(fig,'observed_event')

def responses():
    d=pd.read_csv(R/'scenario_metrics.csv');d=d[d.subgroup=='all']
    methods=['lr','consistency','hgb_anchor','mono_anchor'];cols=[('pure_limit',.5,'纯提额 +50%'),('balance_up',0,'余额 +25%'),('limit_plus_balance',.5,'提额 + 新增余额'),('dpd_raw_only',0,'普通逾期 +30 天')]
    arr=[];annotations=[]
    for method in methods:
        a=[];b=[]
        for kind,delta,title in cols:
            row=d[(d.method==method)&(d.scenario==kind)&(d.delta==delta)].iloc[0]
            value=row.mean_abs_points if kind=='pure_limit' else row.affected_risk_decrease*100
            a.append(value);b.append(f'{value:.2f}'+(' 分' if kind=='pure_limit' else '%'))
        arr.append(a);annotations.append(b)
    fig,ax=plt.subplots(figsize=(12,3.9),layout='constrained');ax.imshow(arr,cmap='YlOrRd',vmin=0,vmax=35,aspect='auto',alpha=.78)
    ax.set_xticks(range(4),[c[2] for c in cols]);ax.set_yticks(range(4),[LABEL[m] for m in methods]);ax.tick_params(length=0,pad=12)
    for i in range(4):
        for j in range(4):ax.text(j,i,annotations[i][j],ha='center',va='center',fontsize=17,color='white' if arr[i][j]>30 else NAVY,weight='bold')
    for pos in np.arange(.5,4):ax.axhline(pos,color='white',lw=4);ax.axvline(pos,color='white',lw=4)
    ax.set_title('首列：平均绝对分差；其余：风险反向下降比例',fontsize=13,pad=20)
    ax.text(0,-.21,'逾期列为 0% 不代表有响应：两种树在该情景下全部保持原值。',transform=ax.transAxes,fontsize=11,color=CORAL)
    save(fig,'response_map')

def repeats():
    d=pd.read_csv(R/'repeated_metrics.csv');methods=['lr','consistency','hgb_anchor','mono_anchor','hgb_no_limit','mono_no_external']
    fig,ax=plt.subplots(figsize=(11,3.8),layout='constrained')
    for i,m in enumerate(methods):
        vals=d[d.method==m].AUC.to_numpy();ax.plot([vals.min(),vals.max()],[i,i],color=GRAY,lw=2);ax.scatter(vals,np.full(5,i),s=35,color=TEAL if m=='mono_anchor' else BLUE,zorder=3);ax.scatter([vals.mean()],[i],s=80,color=NAVY,marker='D',zorder=4)
    ax.set_yticks(range(len(methods)),[LABEL[m] for m in methods]);ax.invert_yaxis();ax.set(xlabel='AUC（点为 5 次划分；菱形为均值；线为最小值至最大值）',xlim=(.69,.79));ax.grid(axis='x',alpha=.2)
    save(fig,'repeat_sensitivity')

def reference():
    d=pd.read_csv(R/'reference_sensitivity.csv');d=d[d.method=='mono_anchor']
    rows=[d[d.reference=='current_x_0.8'].iloc[0],d[d.reference=='current_x_1.2'].iloc[0],d[d.subgroup=='same_cards'].iloc[0],d[d.subgroup=='recent_increase'].iloc[0]]
    labels=['参考额度为当前的 80%','参考额度为当前的 120%','真实前月参考：同卡集合','真实前月参考：近期提额']
    fig,ax=plt.subplots(figsize=(11,3.6),layout='constrained');values=[r.mean_abs_points for r in rows];ax.barh(labels,values,color=[BLUE,BLUE,TEAL,CORAL],height=.55);ax.invert_yaxis();ax.set(xlabel='相对当前额度口径的平均绝对分差',xlim=(0,18));ax.grid(axis='x',alpha=.15)
    for i,(v,r) in enumerate(zip(values,rows)):ax.text(v+.2,i,f'{v:.2f} 分 · n={int(r.n):,}',va='center',fontsize=10)
    save(fig,'reference_sensitivity')

def calibration():
    d=pd.read_csv(R/'calibration_bins.csv');fig,ax=plt.subplots(figsize=(8.5,4.5),layout='constrained')
    extent=.5
    for m,c in [('consistency',CORAL),('hgb_live',BLUE),('mono_anchor',TEAL)]:
        a=d[(d.method==m)&(d.n>=20)];ax.plot(a.mean_pd,a.event_rate,'-o',label=LABEL[m],color=c)
        extent=max(extent,float(a[['mean_pd','event_rate']].max().max()))
    extent=min(1.,np.ceil((extent+.025)*10)/10)
    ax.plot([0,extent],[0,extent],'--',color=GRAY,lw=1);ax.set(xlabel='分箱平均预测 PD',ylabel='分箱 TARGET 比例',xlim=(0,extent),ylim=(0,extent));ax.legend(frameon=False);ax.grid(alpha=.15)
    save(fig,'calibration')

if __name__=='__main__':
    hero();events();responses();repeats();reference();calibration();print('Six figure sets written: PNG + SVG + PDF.')
