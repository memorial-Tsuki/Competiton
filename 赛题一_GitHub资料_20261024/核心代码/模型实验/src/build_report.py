from study_common import ROOT,read_json
from report_layout import Writer
import pandas as pd
R=ROOT/'results';D=ROOT/'docs';O=ROOT/'output/pdf';O.mkdir(parents=True,exist_ok=True)
P=pd.read_csv(R/'performance.csv');P=P[(P.seed==20260923)&P.calibrated].set_index('method')
S=pd.read_csv(R/'scenario_metrics.csv');S=S[(S.seed==20260923)&S.group.eq('initial_zero_dpd')&S.scenario.eq('ordinary_dpd')&S.severity.eq(30)].set_index('method')
LABEL={'baseline_lr_anchor':'原参考 LR','baseline_consistency':'原一致性 LR','baseline_mono_anchor':'原参考单调树','sign_lr':'A：符号约束 LR','capped_sign_lr':'A：封顶约束 LR','capped_lr_no_external':'A：去外部评分','capped_tree':'A：封顶单调树','hybrid':'A：封顶混合','shared_lr':'B：共享逾期 LR','shared_hybrid':'B：共享混合','rolling_lr':'C：窗口峰值 LR','rolling_hybrid':'C：窗口峰值混合'}
def main():
    w=Writer('授信风险评分稳定性 | 逾期响应增强实验',8)
    w.page('逾期响应增强实验报告')
    w.p('统一当前与历史逾期窗口，保留纯提额不变性','h2')
    w.fig('response_overview.png','图 1 主划分、独立校准后的结果。正响应率对应输入情景；AUC 对应当前申请 TARGET，二者回答不同问题。')
    w.h('本轮结论')
    w.p('建议把“窗口峰值混合模型”作为后续参赛稿的增强候选。它将最近六个可见月份的最严重逾期纳入一个封顶特征，再将受方向约束的 LR 与上一版单调树结合。主验证选择 LR 权重 25%；所有系数由训练标签估计，没有手工给 PD 加上固定惩罚。')
    w.p('测试 AUC 为 0.7580，原参考单调树为 0.7533。固定参考额度时，纯提额 10%-100% 五档仍完全不变；初始无逾期客户中，普通逾期 +30 天的正响应为 5,748/5,760，即 99.79%。其余 12 人已有至少 30 天历史峰值。')
    w.table(['研究对象','规模与边界'],[['当前申请预测','38,934 人，3,878 个 TARGET=1；主测试 5,838 人'],['新模型对照','A/B/C 三批、9 个新方法、6 个冻结划分，共 54 个新模型'],['旧基准','普通 LR、一致性 LR、单调树各 6 个，共 18 个保存模型'],['实际变化诊断','同卡集合的前后两月 DPD；测试恶化 69 人、改善 39 人']],[108,377])
    w.p('本轮是已见数据集上的序贯开发，使用上一版相同角色划分与独立校准集。本专项报告与原 8 页正文分开保存；旧结论没有被覆盖，也不能将本轮称为新盲测或生产验收。','small')

    w.page('一、诊断：不是加一个正系数就能解决')
    w.p('训练集有 315 人普通逾期为正、159 人容忍口径逾期为正。字段字典说明后者忽略小额欠款；普通逾期很长，不一定对应更高的当前申请 TARGET 比例。不能把两个字段当作含义完全相同的严重程度刻度。')
    w.table(['训练集普通 DPD','人数 / TARGET=1','TARGET 比例'],[['0 天','23,049 / 2,279','9.89%'],['2-7 天','65 / 12','18.46%'],['8-30 天','81 / 21','25.93%'],['>90 天','65 / 5','7.69%']],[174,174,137])
    w.p('原树为两个当前逾期字段保留了 70/9 个分箱边界，却没有使用它们分裂；历史最大逾期使用了 22 次。原 LR 当前普通逾期系数为负、历史峰值系数为正。加入符号约束后，主划分将普通逾期系数学成零；封顶及共享当前字段也未恢复响应。')
    w.fig('rolling_peak_contract.png','图 2 C 组输入定义示意，格内数字为封顶峰值天数，不是违约概率。横向只有刷新既有峰值时才改变输入。',width=440)
    w.p('C 组令 r=log(1+min(max(历史峰值, 当前普通 DPD, 当前容忍 DPD),30))。')
    w.p('该特征替换原三个逾期项，并保留历史缺失标记。r 的系数非负、允许为零。主划分学到每单位 r 的未校准 log-odds 系数为 0.1394。该窗口假设将历史证据传递到当前月，不能解释为数据已证明每种逾期的风险效果相同。')

    w.page('二、方法对照：保留失败分支，分别评价两个目标')
    w.table(['方法','AUC','Brier','普通 +30 正响应'],[[LABEL[m],f'{P.loc[m,"AUC"]:.4f}',f'{P.loc[m,"Brier"]:.5f}',f'{S.loc[m,"affected_increase"]*100:.2f}%'] for m in LABEL],[194,76,88,127])
    w.p('表 1 同一主测试集，概率均独立校准；响应列限初始两类 DPD 均为零的 5,760 人。A/B 主划分的混合权重虽改善了 AUC，仍未通过普通逾期响应门槛，不能称作修复成功。','small')
    w.h('按验证结果选择，不按测试结果挑权重')
    w.p('LR 的 L2 为 0.0001/0.001/0.01；封顶树最小叶样本为 20/60/120。分别按验证 AUC 选。混合权重 α 为 0/0.1/0.25/0.5/0.75/1；要求验证 AUC 较原树下降不超过 0.005、Brier 增幅不超过 0.001，同时初始双零客户普通 +30 天至少 99% 上升、中位 PD 增加至少 0.1 个百分点。')
    w.p('A 组通过 1/6 个划分，B 组通过 2/6，C 组通过 6/6；主 C 组 α=0.25。最终 p_raw=0.75p_tree+0.25p_LR，再在独立校准集拟合正斜率 sigmoid。两条分支都用参考额度计算余额、支用与付款的全部依赖项。')
    w.p('A 组发现问题后才增加 B、C，各组开始前本地固定补充协议，未做第三方预注册。候选扩展参考了训练/验证结果；新测试输出在 C 组完成后统一审阅。所有旧测试基准早已知晓，仍须承认开发选择带来的乐观偏差。','small')

    w.page('三、响应验证：改善了恶化响应，也出现恢复滞后')
    w.fig('ordinary_response.png','图 3 初始双零逾期客户的平均 PD 变化。C 组 +30 天中位增幅为 0.883 个百分点；均值为 1.055 个百分点，之后主模型进入封顶平台。')
    w.fig('observed_worsening.png','图 4 使用同一客户实际观察到的前后月逾期值，固定当前其他特征。41/69 人在 C 组中 PD 上升，28 人持平，无反降；不等同于历史时点预测回测。')
    w.p('新增余额情景同时把旧余额的 25% 加到余额与支用；3,473 名实际增加者在 C 组中均上升。付款增加 25% 的 3,563 名受影响者均下降。纯提额平均绝对 PD 变化、分差、等级迁移率均为零。')
    w.h('不能用“单调”掩盖持平')
    w.p('69 名观察恶化者仍有 40.58% 持平；39 名观察改善者全部持平，因为固定的历史窗口保留了先前峰值。30 天封顶还压缩了严重程度差异。在本队列中容忍 DPD 不超过普通 DPD，取最大值也压缩了金额容忍信息。恢复速度、债务金额重要性与严重逾期区分仍需真实跨月结果来验证。')

    w.page('四、预测质量：区分度收益不能全归功于窗口')
    w.fig('repeat_comparison.png','图 5 五次重划分有客户重叠，点和范围不代表五个独立试验。C 组 AUC 均值 0.7622、标准差 0.0078，原参考单调树均值 0.7576。')
    w.p('A 组混合的五次均值为 0.7623，略高于 C 组，说明区分度收益主要与模型组合有关；C 组的附加价值在于普通逾期响应契约。五次 C 组初始双零客户 +30 天正响应率为 99.83%-100%，中位 PD 增幅为 1.05-1.87 个百分点。')
    ci=pd.read_csv(R/'paired_intervals.csv');ci=ci[ci.method.eq('rolling_hybrid')]
    w.table(['C 组减去原树','点差','95% 区间'],[[a.metric,f'{a.difference:+.5f}',f'[{a.ci_low:+.5f}, {a.ci_high:+.5f}]'] for a in ci.itertuples()],[164,99,222])
    w.p('1,000 次固定模型配对抽样，未重训、未作多重比较校正；区间只反映当前样本条件不确定性，不能抵消序贯开发或分布变化的影响。','small')
    w.h('逾期人群的概率仍偏低')
    g=pd.read_csv(R/'subgroup_calibration.csv');g=g[g.method.eq('rolling_hybrid')&~g.group.eq('zero_both')]
    names={'ordinary_1_30':'普通 1-30 天','ordinary_over30':'普通 >30 天','tolerant_positive':'容忍口径 >0'}
    w.table(['测试子组','人数 / 坏样本','平均 PD','TARGET 比例'],[[names[a.group],f'{a.n} / {a.positives}',f'{a.mean_pd*100:.2f}%',f'{a.target_rate*100:.2f}%'] for a in g.itertuples()],[153,117,108,107])
    w.p('子组很小且相互重叠，改善输入方向并不等于概率校准充分。原 A 组去外部评分 LR 的 AUC 只有 0.6990；这说明该对照依赖外部信息，尚不能定量替代 C 组自身的去外部评分消融。','small')

    w.page('五、逐客户曲线：逾期增加后，具体降多少分')
    w.fig('customer_dpd_fluctuation.png','图 6 同一客户固定其他字段，仅把当前普通逾期从 0 调至 60 天。纵轴为相对初始分差，横轴是输入情景，不是真实时间。浅绿为未突破历史峰值的区间，浅灰为 30 天封顶区间。')
    trajectories=pd.read_csv(R/'figures/fluctuation_dpd_trajectories.csv')
    cases=pd.read_csv(R/'figures/fluctuation_cases.csv')
    rows=[]
    for case in cases.itertuples():
        a=trajectories[trajectories.case.eq(case.case)].set_index('ordinary_dpd_days')
        rows.append([f'案例 {case.case}',f'{case.hist_max_dpd:.0f} 天']+[f'{a.loc[d,"score"]:.2f}' for d in [0,7,30,60]])
    w.table(['客户','历史峰值','当前 0 天','当前 7 天','当前 30 天','当前 60 天'],rows,[67,90,82,82,82,82])
    w.p('表 2 为图 6 对应的绝对分数。分数越高，模型估计风险越低；分差为负表示风险升高。案例 A 从 0 天起降分；案例 B 在 7 天以内持平，超过历史峰值后才降分；案例 C 全程持平。')
    w.h('客户如何选取')
    w.p('从主测试集中当前两类逾期均为零的客户，分别取历史峰值为 0 天、7 天、至少 30 天三组；每组选择最接近该组 C 模型初始 PD 中位数的记录，同距按客户编号排序。不使用 TARGET，也不按降分幅度挑案例。三例用于解释机制，不代表总体效果。')
    peak=cases.loc[cases.case.eq('C'),'hist_max_dpd'].item()
    w.p(f'案例 C 的公开数据原始历史峰值为 {peak:.0f} 天，属于极端记录；模型按规则封顶到 30 天。此处保留原值来展示持平边界，不据此认定该记录在银行业务中合理。实际使用需要单独核验字段口径与异常值。','small')
    w.p('评分统一为 score=clip(600+(40/log(2))*(-log(19)-logit(PD)),300,850)。图中所有点来自冻结模型重算；与原情景表重叠的 27 个概率逐点一致，未重新训练或选择模型。','small')

    w.page('六、具体波动：纯提额漂移与逐客户分差')
    w.fig('customer_limit_fluctuation.png','图 7 同样三名客户、同一个 C 模型，比较实时额度与固定审核参考额度两种输入口径。只改额度，余额、支用、付款、逾期及历史均固定；折线连接六个实际计算档位。固定参考的三条分差曲线均为 0。')
    limits=pd.read_csv(R/'figures/fluctuation_limit_trajectories.csv')
    b=limits[limits.case.eq('B')&limits['mode'].eq('live_limit')&limits.limit_increase_fraction.eq(1)].iloc[0]
    w.p(f'案例 B 仅额度翻倍，实时口径就从 531.70 分变为 {b.score:.2f} 分（+{b.delta_score:.2f} 分）；固定参考保持 531.70 分。这是同一模型的输入口径差异，不是客户风险真实下降的证据。','small')
    w.fig('observed_customer_fluctuation.png','图 8 覆盖全部 69 名观察到逾期恶化的测试客户。每个横坐标是一名客户，柱为 C 模型、圆点为原参考 LR；排序仅为便于阅读。使用实际前后月 DPD，但其余字段固定在当前，故不是历史评分回测。')
    stats=read_json(R/'figures/fluctuation_verification.json')['observed_counts']
    c=stats['rolling_hybrid'];old=stats['baseline_lr_anchor']
    w.p(f'C 模型分差范围为 {c["min_delta_score"]:.2f} 至 {c["max_delta_score"]:.2f} 分，41 人降分、28 人持平；原 LR 分差范围为 {old["min_delta_score"]:.2f} 至 +{old["max_delta_score"]:.2f} 分，其中 39 人在逾期恶化时反而升分。另有 39 名观察改善者在 C 模型中全部持平，恢复滞后的结论不变。','small')
    w.p('逐点分数、客户来源编号、选择规则和数据哈希均保存在 results/figures/fluctuation_*.csv 与 fluctuation_verification.json，可沿每条曲线追溯原始计算。','small')

    w.page('七、原型、复现与使用建议')
    w.table(['环节','增强原型行为'],[['参考审核','客户、模型版本、参考来源、事件类型与带时区时间链一致；外部真实性仍需认证'],['双轨输出','参考 PD / 分数 / 等级、实时 PD、行为与额度分量、当前窗口峰值与封顶状态'],['逾期处理','当前有逾期、新发生或加重、窗口峰值 ≥30 天、原始输入越界均给出复核原因'],['关键保护','分数持平不撤销逾期复核；30→60 天示例仍触发人工复核'],['模型状态','仅标为通过本轮开发门槛的研究候选；不自动审批或声称生产可用']],[96,389])
    w.p('五个可运行 JSON 示例覆盖纯提额、新增普通逾期、联合逾期、新增余额及封顶后恶化。示例来自公开测试记录，时间和事件人工构造。运行 python src/predict.py examples/new_ordinary_dpd.json 即可查看原型输出。')
    w.h('复核证据')
    w.p('保留 54 个新模型、18 个冻结基准、全部逐客预测与情景，16 项契约测试覆盖非负系数可学成零、缺失历史、窗口/封顶、混合校准、参考不变性与事件校验。主测试 84 个指标另用排序/计数公式核验；所有保存模型与情景重放。')
    w.p('在空结果目录从冻结队列和旧基准重新训练 54 个候选，34 项数值输出一致。此复现沿用同机同环境，不重复原始 CSV 清洗；原始清洗在上一版已有独立复核。本轮输入来源和字节哈希见 data/input_manifest.json，重训与重放证明见 results/reproduction.json、verification.json。')
    w.h('建议与剩余研究问题')
    w.p('优先保留 C 组窗口混合作为增强候选，同时保留 A/B 与原基准。下一阶段需要未参与开发的时间外数据、策略发起方、固定未来窗口结果和逾期金额信息，重点检验概率校准、恢复滞后与峰值退出窗口后的变化。本轮不再依据已查看测试结果追加调参。')
    w.p('来源：上一阶段 Home Credit 队列、保存模型与原字段字典；原始出处 https://www.kaggle.com/competitions/home-credit-default-risk/data。当前申请 TARGET 不是历史卡月违约结果；观察变化和合成输入不能识别逾期的因果效果。','small')
    w.save(O/'逾期响应增强实验报告.pdf',D/'逾期响应增强实验报告.md')

if __name__=='__main__':main()
