"""Human-readable input contract; optional unknowns are preserved as missing."""
GROUPS = [
    ('current', '当前授信与履约', '必填。金额需与原始数据使用同一单位和口径；请勿混用月收入与其他收入周期。'),
    ('profile', '基础资质与申请', '选填。未知请留空，系统沿用冻结模型的缺失处理，不会替你编造客户信息。'),
    ('history', '历史信用卡行为', '选填。最近月为 -1，以下历史窗口为 -6 至 -2 月；均值按账户月记录计算。'),
    ('applications', '历史申请与分期支付', '选填。分期指标仅针对已知且有效的应还期次，未知不等于未还款。'),
    ('external', '外部评分', '选填。仅填写真实可得的 EXT_SOURCE 标准化评分；缺失可能显著影响结果。'),
]

def field(key, label, group, required=False, minimum=0, maximum=None, hint='', scale=1, integer=False, options=None):
    return dict(key=key,label=label,group=group,required=required,min=minimum,max=maximum,hint=hint,scale=scale,integer=integer,options=options)

FIELDS = [
 field('AMT_INCOME_TOTAL','收入金额','current',True,0,hint='对应原始 AMT_INCOME_TOTAL；必须大于 0。'),
 field('limit','当前总授信额度','current',True,0,hint='当前有效活跃卡额度之和，必须大于 0。'),
 field('balance','当前借款余额','current',True,hint='当前有效活跃卡余额之和。'),
 field('drawings','本期支用金额','current',True,hint='当月各有效活跃卡支用之和。'),
 field('payment','本期付款金额','current',True,hint='当月各有效活跃卡付款之和。'),
 field('dpd','普通逾期天数','current',True,hint='当前有效卡普通 DPD 最大值。',integer=True),
 field('dpd_def','容忍口径逾期天数','current',True,hint='忽略小额欠款的口径；不得大于普通逾期天数。',integer=True),
 field('DAYS_BIRTH','年龄（岁）','profile',minimum=18,maximum=110,hint='按年龄 × 365.25 换算原始相对出生天数。',scale=-365.25),
 field('DAYS_EMPLOYED','就业年限（年）','profile',maximum=90,scale=-365.25),
 field('CNT_CHILDREN','子女人数','profile',integer=True),
 field('active_cards','活跃信用卡数','profile',minimum=1,integer=True),
 field('AMT_CREDIT','本次申请贷款金额','profile',hint='不是信用卡授信额度。'),
 field('AMT_ANNUITY','本次贷款还款额（原字段）','profile',hint='原始 AMT_ANNUITY；不擅自转换支付频率。'),
 field('NAME_CONTRACT_TYPE','合同类型','profile',options=[('Cash loans','现金贷款'),('Revolving loans','循环贷款')]),
 field('NAME_INCOME_TYPE','收入类型','profile',options=[('Working','在职工作'),('Commercial associate','商业从业'),('Pensioner','领取养老金'),('State servant','公共部门'),('Unemployed','失业'),('Student','学生'),('Businessman','经营者'),('Maternity leave','产假')]),
 field('NAME_EDUCATION_TYPE','教育程度','profile',options=[('Higher education','高等教育'),('Secondary / secondary special','中等或中等专业教育'),('Incomplete higher','未完成高等教育'),('Lower secondary','初等中学'),('Academic degree','学术学位')]),
 field('NAME_HOUSING_TYPE','住房类型','profile',options=[('House / apartment','住宅 / 公寓'),('With parents','与父母同住'),('Municipal apartment','市政公寓'),('Rented apartment','租赁公寓'),('Office apartment','单位公寓'),('Co-op apartment','合作公寓')]),
 field('hist_mean_balance','历史平均余额','history'),
 field('hist_mean_drawings','历史平均支用','history'),
 field('hist_mean_payment','历史平均付款','history'),
 field('hist_max_dpd','历史最大普通逾期（天）','history',integer=True,hint='未知留空；请勿用 0 代替未知。'),
 field('hist_late_rate','历史逾期记录比例','history',maximum=1,hint='0 到 1；例如 20% 填 0.2。'),
 field('hist_months','历史可见月份数','history',maximum=5,integer=True),
 field('prev_count','历史申请次数','applications',integer=True),
 field('prev_refused_rate','历史申请拒绝比例','applications',maximum=1),
 field('prev_credit_mean','历史平均申请金额','applications'),
 field('prev_latest_day','距最近申请天数','applications',minimum=1,scale=-1,hint='填正数天数，系统转换为原始负相对日。'),
 field('inst_count','有效已知分期期数','applications',integer=True),
 field('inst_shortfall_rate','最终支付不足期次比例','applications',maximum=1),
 field('inst_shortfall_sum','最终支付缺口合计','applications'),
 field('inst_not_paid_by_due_rate','到期未足额支付比例','applications',maximum=1),
 field('inst_payment_ratio','平均实付 / 应还比率','applications',hint='1 表示平均实付与应还相等；可能超过 1。'),
 field('inst_unknown_payment_rate','未知支付期次比例','applications',maximum=1),
 field('EXT_SOURCE_1','外部评分 1','external',maximum=1),
 field('EXT_SOURCE_2','外部评分 2','external',maximum=1),
 field('EXT_SOURCE_3','外部评分 3','external',maximum=1),
]
BY_KEY = {f['key']: f for f in FIELDS}
SCENARIOS = [
 dict(id='pure_limit', label='纯提额', help='只增加当前额度，冻结参考额度和客户其他状态。'),
 dict(id='new_debt', label='新增借款', help='新增金额同时加到借款余额和本期支用。'),
 dict(id='combined', label='提额并借款', help='同时提额和增加借款；派生比值全部重新计算。'),
 dict(id='ordinary_dpd', label='普通逾期增加', help='只增加普通逾期天数；其他字段固定。'),
 dict(id='joint_dpd', label='两类逾期增加', help='两类逾期天数同时增加；其他字段固定。'),
 dict(id='payment', label='增加付款', help='只增加模型中的本期付款；并非完整账务结算模拟。'),
]
