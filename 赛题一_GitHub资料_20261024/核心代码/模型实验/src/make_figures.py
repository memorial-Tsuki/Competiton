from study_common import ROOT
import os
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/mplcache')
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.font_manager import fontManager,FontProperties
fontManager.addfont('C:/Windows/Fonts/msyh.ttc')
plt.rcParams.update({'font.family':FontProperties(fname='C:/Windows/Fonts/msyh.ttc').get_name(),'axes.unicode_minus':False,'font.size':11,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'path'})
R=ROOT/'results';F=R/'figures';F.mkdir(exist_ok=True)
NAVY='#122D44';TEAL='#00A397';CORAL='#E8795E';GRAY='#8195A5';BLUE='#447CC0'
def save(fig,name):
    for ext in ['png','svg','pdf']:fig.savefig(F/(name+'.'+ext),dpi=240,bbox_inches='tight',facecolor=fig.get_facecolor())
    plt.close(fig)

def hero():
    perf=pd.read_csv(R/'performance.csv');p=perf[(perf.seed==20260923)&perf.calibrated].set_index('method')
    s=pd.read_csv(R/'scenario_metrics.csv');s=s[(s.seed==20260923)&s.method.eq('rolling_hybrid')&s.scenario.eq('ordinary_dpd')&s.severity.eq(30)&s.group.eq('initial_zero_dpd')].iloc[0]
    fig=plt.figure(figsize=(14,4),facecolor=NAVY);ax=fig.add_axes([0,0,1,1]);ax.set(xlim=(0,14),ylim=(0,4));ax.axis('off')
    ax.text(.45,3.45,'让当前逾期进入历史风险窗口',color='white',fontsize=24,weight='bold')
    for x,title,value,sub in [(.5,'普通逾期 +30 天',f'{s.affected_increase*100:.2f}%','原先两类逾期均为零：5,760 人'),(5.0,'当前申请测试 AUC',f"{p.loc['rolling_hybrid','AUC']:.4f}",'原参考单调树：0.7533'),(9.65,'固定参考 · 纯提额','0 分','10%-100% 五档平均分差均为零')]:
        ax.add_patch(FancyBboxPatch((x,1.15),3.8,1.8,boxstyle='round,pad=.12',facecolor='#1D3D56',edgecolor='#426278'))
        ax.text(x+.15,2.57,title,color='#D3E3ED',fontsize=12);ax.text(x+.15,1.91,value,color='#61DFD1',fontsize=31,weight='bold');ax.text(x+.15,1.39,sub,color='#D3E3ED',fontsize=10)
    ax.text(.5,.55,'前两组失败结果保留；六个划分通过预设验证门槛。',color='white',fontsize=12)
    ax.text(.5,.12,'99.79% 指合成输入的正响应比例，不是违约识别准确率；超过历史峰值或封顶后的响应边界须单独解释。',color='#B6CEDD',fontsize=10)
    save(fig,'response_overview')

def peak_map():
    days=[0,1,7,15,30,60];matrix=np.minimum(np.maximum.outer(days,days),30)
    fig,ax=plt.subplots(figsize=(10,3.9),layout='constrained');ax.imshow(matrix,cmap='Blues',vmin=0,vmax=30,aspect='auto');ax.set_xticks(range(6),days);ax.set_yticks(range(6),days);ax.set(xlabel='当前普通逾期天数（容忍口径保持为 0）',ylabel='历史最大逾期天数')
    for i in range(6):
        for j in range(6):ax.text(j,i,str(matrix[i,j]),ha='center',va='center',color='white' if matrix[i,j]>=30 else NAVY,fontsize=15,weight='bold')
    ax.set_title('窗口峰值 = min(max(历史峰值, 当前逾期), 30)',pad=13)
    save(fig,'rolling_peak_contract')

def response():
    s=pd.read_csv(R/'scenario_metrics.csv');s=s[(s.seed==20260923)&s.scenario.eq('ordinary_dpd')&s.group.eq('initial_zero_dpd')]
    fig,axs=plt.subplots(1,2,figsize=(12,3.7),layout='constrained')
    for m,label,color in [('baseline_mono_anchor','原单调树',GRAY),('hybrid','A 组混合',BLUE),('rolling_hybrid','C 组窗口混合',TEAL)]:
        a=s[s.method==m].sort_values('severity');x=np.r_[0,a.severity];y=np.r_[0,a.mean_pd_change*100]
        for ax in axs:ax.plot(x,y,'-o',label=label,color=color,lw=2,ms=4)
    axs[0].set(xlim=(-1,31),xticks=[0,1,7,30],xlabel='普通逾期增加天数：近期区间',ylabel='平均 PD 变化（百分点）')
    axs[1].set(xlim=(-3,183),xticks=[0,30,60,90,180],xlabel='普通逾期增加天数：完整压力区间',ylabel='平均 PD 变化（百分点）')
    axs[0].legend(frameon=False,loc='upper left',fontsize=10)
    for ax in axs:ax.grid(alpha=.15)
    save(fig,'ordinary_response')

def observed():
    d=pd.read_csv(R/'observed_transition_summary.csv');d=d[d.transition.eq('worsening')].set_index('method')
    methods=['baseline_lr_anchor','baseline_mono_anchor','hybrid','rolling_hybrid'];labels=['原参考 LR','原参考单调树','A 组混合','C 组窗口混合']
    fig,ax=plt.subplots(figsize=(11,3.4),layout='constrained');start=np.zeros(4)
    for key,label,color in [('increase','PD 上升',TEAL),('flat','PD 持平','#D9E2E8'),('decrease','PD 反向下降',CORAL)]:
        vals=d.loc[methods,key].to_numpy()*100;ax.barh(labels,vals,left=start,label=label,color=color,height=.54)
        for i,(v,l) in enumerate(zip(vals,start)):
            if v>2:ax.text(l+v/2,i,f'{v:.1f}%',ha='center',va='center',color=NAVY,fontsize=12)
        start+=vals
    ax.set(xlim=(0,100),xlabel='69 名观察逾期恶化客户：固定当前其他字段，仅替换两期 DPD');ax.invert_yaxis();ax.legend(frameon=False,loc='upper center',bbox_to_anchor=(.5,1.18),ncol=3)
    save(fig,'observed_worsening')

def repeats():
    d=pd.read_csv(R/'performance.csv');d=d[(d.seed!=20260923)&d.calibrated]
    names=[('baseline_mono_anchor','原参考单调树'),('baseline_lr_anchor','原参考 LR'),('hybrid','A 组混合'),('shared_hybrid','B 组共享混合'),('rolling_hybrid','C 组窗口混合')]
    fig,ax=plt.subplots(figsize=(11,3.5),layout='constrained')
    for i,(m,label) in enumerate(names):
        vals=d[d.method.eq(m)].AUC.to_numpy();ax.plot([vals.min(),vals.max()],[i,i],color=GRAY);ax.scatter(vals,np.full(len(vals),i),color=TEAL if m=='rolling_hybrid' else BLUE,s=28);ax.scatter([vals.mean()],[i],color=NAVY,marker='D',s=70)
    ax.set_yticks(range(5),[label for m,label in names]);ax.invert_yaxis();ax.set(xlim=(.743,.78),xlabel='五次划分 AUC；菱形为均值，线段为观察范围');ax.grid(axis='x',alpha=.18)
    save(fig,'repeat_comparison')

if __name__=='__main__':hero();peak_map();response();observed();repeats();print('Five scientific figure sets generated from retained results and the explicit window formula.')
