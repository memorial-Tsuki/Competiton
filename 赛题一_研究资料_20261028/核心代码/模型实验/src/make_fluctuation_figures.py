"""Customer-level score figures from frozen models; no model selection or retraining."""
from study_common import ROOT, digest, write_json
from make_figures import plt, save, F, NAVY, TEAL, CORAL, GRAY, BLUE
from analyze_results import load_models
from delinquency_model import predict, scenario
from risk_model import score
from threadpoolctl import threadpool_limits
import numpy as np
import pandas as pd


def main():
    cohort = pd.read_csv(ROOT/'data/cohort.csv', float_precision='round_trip').set_index('SK_ID_CURR', drop=False)
    pred = pd.read_csv(ROOT/'results/predictions.csv', float_precision='round_trip')
    pred = pred[pred.seed.eq(20260923)].set_index('SK_ID_CURR')
    test = cohort.loc[pred.index].copy()
    bundle = load_models(20260923)['rolling_hybrid']
    initial = predict(bundle, test, test.limit.to_numpy())
    np.testing.assert_allclose(initial, pred.rolling_hybrid, atol=1e-12, rtol=0)
    test['initial_pd'] = initial
    zero = test[test.dpd.eq(0) & test.dpd_def.eq(0)]
    cases = []
    for alias, mask, criterion in [
        ('A', zero.hist_max_dpd.eq(0), 'current DPDs zero, historical peak = 0'),
        ('B', zero.hist_max_dpd.eq(7), 'current DPDs zero, historical peak = 7'),
        ('C', zero.hist_max_dpd.ge(30), 'current DPDs zero, historical peak >= 30'),
    ]:
        group = zero[mask].copy()
        group['distance_to_median'] = abs(group.initial_pd-group.initial_pd.median())
        chosen = group.reset_index(drop=True).sort_values(['distance_to_median', 'SK_ID_CURR']).iloc[0]
        cases.append({'case': alias, 'SK_ID_CURR': int(chosen.SK_ID_CURR),
                      'hist_max_dpd': float(chosen.hist_max_dpd), 'group_n': len(group),
                      'selection': criterion+'; closest to median frozen C-model PD; ID breaks ties',
                      'initial_pd': float(chosen.initial_pd), 'initial_score': float(score(chosen.initial_pd))})
    selected = pd.DataFrame(cases)
    selected.to_csv(F/'fluctuation_cases.csv', index=False)

    records = []
    for case in cases:
        row = test.loc[[case['SK_ID_CURR']]]
        for day in range(61):
            x = scenario(row, 'ordinary_dpd', day)
            p = float(predict(bundle, x, row.limit.to_numpy())[0])
            points = float(score(p))
            records.append({'case': case['case'], 'SK_ID_CURR': case['SK_ID_CURR'],
                            'ordinary_dpd_days': day, 'hist_max_dpd': case['hist_max_dpd'],
                            'pd': p, 'score': points, 'delta_score': points-case['initial_score']})
    dpd = pd.DataFrame(records)
    for _, a in dpd.groupby('case'):
        assert np.max(np.diff(a.score)) <= 1e-10
        assert np.ptp(a.loc[a.ordinary_dpd_days.ge(30), 'score']) <= 1e-10
        h = min(a.hist_max_dpd.iloc[0], 30)
        assert np.ptp(a.loc[a.ordinary_dpd_days.le(h), 'score']) <= 1e-10
    dpd.to_csv(F/'fluctuation_dpd_trajectories.csv', index=False)
    fig, axes = plt.subplots(1, 3, figsize=(12.8, 4.1), layout='constrained', sharey=True)
    ymin = min(-5., float(dpd.delta_score.min())-5.)
    for ax, case in zip(axes, cases):
        a = dpd[dpd.case.eq(case['case'])].set_index('ordinary_dpd_days')
        ax.axhline(0, color=GRAY, lw=1)
        ax.axvspan(30, 60, facecolor='#E9EEF2', alpha=.9)
        h = min(case['hist_max_dpd'], 30)
        if h > 0: ax.axvspan(0, h, facecolor='#D9F3EE', alpha=.8)
        ax.plot(a.index, a.delta_score, color=TEAL, lw=2.6)
        marks = [0, 1, 7, 30, 60]
        ax.scatter(marks, a.loc[marks, 'delta_score'], color=TEAL, s=27, zorder=4)
        ax.text(.04, .09, f"初始 {case['initial_score']:.1f} 分\n30 天 {a.loc[30,'score']:.1f} 分\n净变化 {a.loc[30,'delta_score']:+.1f} 分", transform=ax.transAxes,
                color=NAVY, fontsize=11, bbox={'boxstyle':'round,pad=.4','facecolor':'white','edgecolor':'#D8E3E8','alpha':.95})
        ax.set(title=f"案例 {case['case']}  |  历史峰值 {case['hist_max_dpd']:.0f} 天",
               xlabel='当前普通逾期天数（输入情景）', xlim=(-1, 62), ylim=(ymin, 3), xticks=[0, 7, 30, 60])
        ax.grid(axis='y', alpha=.15)
    axes[0].set_ylabel('相对初始评分变化（分）\n负值表示风险升高')
    fig.suptitle('同一客户的分数如何变化：突破历史峰值后下降，30 天起封顶', fontsize=15, color=NAVY)
    save(fig, 'customer_dpd_fluctuation')

    records = []
    for case in cases:
        row = test.loc[[case['SK_ID_CURR']]]
        for rate in [0, .1, .2, .3, .5, 1.]:
            x = scenario(row, 'pure_limit', rate)
            for mode in ['live_limit', 'fixed_reference']:
                p = float(predict(bundle, x, None if mode=='live_limit' else row.limit.to_numpy())[0])
                points = float(score(p))
                records.append({'case':case['case'], 'SK_ID_CURR':case['SK_ID_CURR'],
                                'limit_increase_fraction':rate, 'mode':mode, 'pd':p,
                                'score':points, 'delta_score':points-case['initial_score']})
    limit = pd.DataFrame(records)
    assert limit.loc[limit['mode'].eq('fixed_reference'), 'delta_score'].abs().max() <= 1e-10
    limit.to_csv(F/'fluctuation_limit_trajectories.csv', index=False)
    fig, axes = plt.subplots(1, 3, figsize=(12.8, 3.9), layout='constrained', sharey=True)
    bottom = min(-1., float(limit.delta_score.min())-1.5)
    top = max(2., float(limit.delta_score.max())+2.)
    for ax, case in zip(axes, cases):
        a = limit[limit.case.eq(case['case'])]
        for mode, label, color, style in [('live_limit','按实时额度重算',CORAL,'--o'), ('fixed_reference','固定审核参考额度',TEAL,'-o')]:
            b = a[a['mode'].eq(mode)]
            ax.plot(b.limit_increase_fraction*100, b.delta_score, style, color=color, label=label, lw=2.3, ms=4)
            end = b.iloc[-1]
            if mode=='live_limit':
                ax.annotate(f'{end.delta_score:+.2f} 分', (100,end.delta_score), xytext=(-3, 8),
                            textcoords='offset points', ha='right', fontsize=11, color=color)
        ax.set(title=f"案例 {case['case']}  |  起点 {case['initial_score']:.1f} 分",
               xlabel='仅额度增加（%）', xlim=(-2, 106), ylim=(bottom, top), xticks=[0, 20, 50, 100])
        ax.grid(alpha=.15)
    axes[0].set_ylabel('相对初始评分变化（分）')
    axes[0].legend(frameon=False, fontsize=9, loc='upper left')
    fig.suptitle('行为完全相同，只改额度：同一个 C 模型的两种计算口径', fontsize=15, color=NAVY)
    save(fig, 'customer_limit_fluctuation')

    observed = pd.read_csv(ROOT/'results/observed_transition_predictions.csv', float_precision='round_trip')
    transitions = pd.read_csv(ROOT/'data/observed_transitions.csv', float_precision='round_trip').set_index('SK_ID_CURR')
    selected_observed = observed[observed.transition.eq('worsening') & observed.method.isin(['baseline_lr_anchor','rolling_hybrid'])].copy()
    selected_observed['score_with_previous_dpd'] = score(selected_observed.pd_with_previous_dpd)
    selected_observed['score_with_current_dpd'] = score(selected_observed.pd_with_current_dpd)
    selected_observed['delta_score'] = selected_observed.score_with_current_dpd-selected_observed.score_with_previous_dpd
    wide = selected_observed.pivot(index='SK_ID_CURR', columns='method', values='delta_score')
    wide = wide.reset_index().sort_values(['rolling_hybrid','SK_ID_CURR']).set_index('SK_ID_CURR')
    order = {int(customer): i+1 for i, customer in enumerate(wide.index)}
    selected_observed['customer_order'] = selected_observed.SK_ID_CURR.map(order)
    for column in ['previous_dpd','previous_dpd_def','current_dpd','current_dpd_def']:
        selected_observed[column] = selected_observed.SK_ID_CURR.map(transitions[column])
    selected_observed.sort_values(['customer_order','method']).to_csv(F/'fluctuation_observed_customers.csv', index=False)
    assert len(wide) == 69
    counts = {}
    for method in wide.columns:
        counts[method] = {'score_falls':int((wide[method]<-1e-10).sum()), 'flat':int((wide[method].abs()<=1e-10).sum()),
                          'score_rises':int((wide[method]>1e-10).sum()), 'min_delta_score':float(wide[method].min()),
                          'max_delta_score':float(wide[method].max())}
    fig, ax = plt.subplots(figsize=(12.8, 4.6), layout='constrained')
    xx = np.arange(1,len(wide)+1)
    ax.bar(xx, wide.rolling_hybrid, color=TEAL, width=.7, label='C 窗口混合：逐客户分差', zorder=3)
    ax.scatter(xx, wide.baseline_lr_anchor, marker='o', facecolors='white', edgecolors=CORAL, s=28,
               label='原参考 LR：同一客户分差', zorder=4, linewidths=1.1)
    flat = abs(wide.rolling_hybrid.to_numpy())<=1e-10
    ax.scatter(xx[flat], np.zeros(flat.sum()), marker='_', color=TEAL, s=70, zorder=5)
    ax.axhline(0, color=NAVY, lw=1)
    ax.set(xlim=(0,70), ylim=(-14.5,36), xticks=[1,10,20,30,40,50,60,69], xlabel='69 名观察逾期恶化客户，按 C 模型分差排序（不是时间轴）',
           ylabel='当前 DPD 分数 - 前月 DPD 分数（分）',
           title='每一根柱都是一名客户：保留反向波动，也保留 28 名持平者')
    ax.grid(axis='y', alpha=.18)
    ax.legend(frameon=False, loc='upper right', fontsize=10)
    c=counts['rolling_hybrid']; old=counts['baseline_lr_anchor']
    ax.text(.02,.96,f"C 模型：{c['score_falls']} 人降分 / {c['flat']} 人持平 / {c['score_rises']} 人升分\n原 LR：{old['score_falls']} 人降分 / {old['flat']} 人持平 / {old['score_rises']} 人升分",
            transform=ax.transAxes, va='top', color=NAVY, fontsize=11,
            bbox={'boxstyle':'round,pad=.4','facecolor':'white','edgecolor':'#D8E3E8','alpha':.95})
    save(fig, 'observed_customer_fluctuation')

    # Cross-check every overlapping stress point against the retained full-cohort outputs.
    stored = pd.read_csv(ROOT/'results/scenario_predictions.csv', float_precision='round_trip')
    stored = stored[stored.method.eq('rolling_hybrid') & stored.SK_ID_CURR.isin(selected.SK_ID_CURR)]
    checks = 0
    for row in dpd[dpd.ordinary_dpd_days.isin([1,7,30,60])].itertuples():
        expected = stored[stored.SK_ID_CURR.eq(row.SK_ID_CURR) & stored.scenario.eq('ordinary_dpd') & stored.severity.eq(row.ordinary_dpd_days)].pd.item()
        np.testing.assert_allclose(row.pd, expected, atol=1e-12, rtol=0); checks += 1
    for row in limit[limit['mode'].eq('fixed_reference') & limit.limit_increase_fraction.gt(0)].itertuples():
        expected = stored[stored.SK_ID_CURR.eq(row.SK_ID_CURR) & stored.scenario.eq('pure_limit') & stored.severity.eq(row.limit_increase_fraction)].pd.item()
        np.testing.assert_allclose(row.pd, expected, atol=1e-12, rtol=0); checks += 1
    sources = ['data/cohort.csv','results/predictions.csv','results/scenario_predictions.csv',
               'results/observed_transition_predictions.csv','data/observed_transitions.csv',
               'models/20260923_rolling_hybrid.joblib','src/make_fluctuation_figures.py']
    proof = {'status':'passed','frozen_test_predictions_checked':len(test),'overlapping_scenario_values_checked':checks,
             'model_retraining':False,'case_selection_uses_target':False,
             'case_selection':'Within historical-peak strata 0, 7, >=30 among current-zero main-test customers: closest to median frozen C-model PD; customer ID resolves ties. Illustrative cases, not population estimates.',
             'score_definition':'clip(600 + (40/log(2)) * (-log(19)-logit(PD)), 300, 850); higher means lower risk',
             'observed_scope':'Actual two-month DPD values, all other current fields and reference fixed; NOT historical score backtest.',
             'observed_counts':counts,'sources':{p:digest(ROOT/p) for p in sources},
             'plot_data':{p.relative_to(ROOT).as_posix():digest(p) for p in sorted(F.glob('fluctuation_*.csv'))}}
    write_json(F/'fluctuation_verification.json', proof)
    print(selected.to_string(index=False))
    print('Observed customer score changes:',counts)
    print('Three customer fluctuation figure sets; 27 retained scenario values matched; no retraining.')


if __name__ == '__main__':
    with threadpool_limits(limits=1):
        main()
