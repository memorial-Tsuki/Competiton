"""首次可观测信用卡额度代理建模。

该程序不会把历史信用卡表中最早可见的额度误称为银行首次批核额度。
它以每个客户最早可观测账户快照的正额度构造代理标签，并仅用申请时可见字段
训练额度中位数预测器；校准集绝对残差用于生成 80% 的保形预测区间。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT.parents[1] / "数据集"
NUMERIC = [
    "CNT_CHILDREN", "AMT_INCOME_TOTAL", "AMT_CREDIT", "AMT_ANNUITY",
    "DAYS_BIRTH", "DAYS_EMPLOYED", "EXT_SOURCE_1", "EXT_SOURCE_2", "EXT_SOURCE_3",
]
CATEGORICAL = [
    "NAME_CONTRACT_TYPE", "NAME_INCOME_TYPE", "NAME_EDUCATION_TYPE", "NAME_HOUSING_TYPE",
]


def extract_first_observed_limit(raw_path: Path) -> pd.DataFrame:
    """Select the earliest observed positive card limit for each account then customer.

    MONTHS_BALANCE is a retrospective observation index. Its minimum is only the
    earliest row supplied in the public extract; it is not an account-origination date.
    """
    usecols = ["SK_ID_CURR", "SK_ID_PREV", "MONTHS_BALANCE", "AMT_CREDIT_LIMIT_ACTUAL"]
    pieces: list[pd.DataFrame] = []
    for chunk in pd.read_csv(raw_path, usecols=usecols, chunksize=250_000):
        chunk = chunk[chunk["AMT_CREDIT_LIMIT_ACTUAL"].gt(0)]
        if not chunk.empty:
            pieces.append(chunk.loc[chunk.groupby(["SK_ID_CURR", "SK_ID_PREV"])["MONTHS_BALANCE"].idxmin()])
    if not pieces:
        raise ValueError("No positive observed card limit was found.")
    accounts = pd.concat(pieces, ignore_index=True)
    accounts = accounts.loc[accounts.groupby(["SK_ID_CURR", "SK_ID_PREV"])["MONTHS_BALANCE"].idxmin()]
    customers = accounts.sort_values(["SK_ID_CURR", "MONTHS_BALANCE", "SK_ID_PREV"]).groupby("SK_ID_CURR", as_index=False).first()
    return customers.rename(columns={
        "MONTHS_BALANCE": "first_observed_month",
        "AMT_CREDIT_LIMIT_ACTUAL": "first_observed_limit",
    })[["SK_ID_CURR", "first_observed_month", "first_observed_limit"]]


def metric_block(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    return {
        "MAE": float(mean_absolute_error(y, pred)),
        "RMSE": float(mean_squared_error(y, pred) ** 0.5),
        "R2": float(r2_score(y, pred)),
        "log_MAE": float(mean_absolute_error(np.log1p(y), np.log1p(np.maximum(pred, 0)))),
    }


def save_figures(out: Path, test: pd.DataFrame, pred: np.ndarray, low: np.ndarray, high: np.ndarray) -> None:
    plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial Unicode MS"], "axes.unicode_minus": False})
    fig, axes = plt.subplots(1, 2, figsize=(12.2, 4.6), layout="constrained")
    axes[0].hist(test["first_observed_limit"], bins=45, color="#2B6F8A", alpha=.82)
    axes[0].set(title="首次可观测信用卡额度代理的分布", xlabel="额度（原始数据单位）", ylabel="客户数")
    clipped_y = np.clip(test["first_observed_limit"].to_numpy(float), 0, np.quantile(test["first_observed_limit"], .99))
    clipped_p = np.clip(pred, 0, np.quantile(test["first_observed_limit"], .99))
    axes[1].scatter(clipped_y, clipped_p, s=7, alpha=.28, color="#008C86", edgecolors="none")
    bound = max(clipped_y.max(), clipped_p.max())
    axes[1].plot([0, bound], [0, bound], "--", color="#8B98A5", lw=1)
    axes[1].set(title="测试集：代理额度与预测中位数", xlabel="代理额度", ylabel="预测中位数")
    fig.savefig(out / "程序输出_first_limit_proxy_图1_代理额度分布与预测散点.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    order = np.argsort(pred)
    selected = np.linspace(0, len(order) - 1, min(220, len(order))).astype(int)
    idx = order[selected]
    fig, ax = plt.subplots(figsize=(10.8, 4.2), layout="constrained")
    x = np.arange(len(idx))
    ax.fill_between(x, low[idx], high[idx], color="#A9DDD5", alpha=.72, label="80% 保形预测区间")
    ax.plot(x, pred[idx], color="#007D74", lw=1.8, label="预测中位数")
    ax.scatter(x, test["first_observed_limit"].to_numpy(float)[idx], color="#D76A4A", s=12, alpha=.62, label="代理额度")
    ax.set(title="测试集额度建议及不确定性区间（按预测额度排序）", xlabel="抽样客户（按预测额度排序）", ylabel="额度（原始数据单位）")
    ax.legend(frameon=False, ncol=3, loc="upper left")
    fig.savefig(out / "程序输出_first_limit_proxy_图2_额度建议与保形区间.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-credit-card", type=Path, required=True, help="credit_card_balance.csv 的本地路径")
    parser.add_argument("--output", type=Path, default=ROOT / "首次可观测额度实验结果")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)

    cohort = pd.read_csv(DATA / "cohort.csv")
    split = pd.read_csv(DATA / "split_manifest.csv", dtype={"group": str})[["SK_ID_CURR", "role"]]
    labels = extract_first_observed_limit(args.raw_credit_card)
    data = cohort.merge(labels, on="SK_ID_CURR", how="inner").merge(split, on="SK_ID_CURR", how="inner")
    if data["SK_ID_CURR"].duplicated().any():
        raise ValueError("Customer duplication after label merge.")
    parts = {role: data[data["role"].eq(role)].copy() for role in ["train", "validation", "calibration", "test"]}
    if min(map(len, parts.values())) == 0:
        raise ValueError("At least one role has no proxy label.")

    preprocess = ColumnTransformer([
        ("numeric", Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True))]), NUMERIC),
        ("categorical", Pipeline([
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]), CATEGORICAL),
    ])
    model = Pipeline([
        ("preprocess", preprocess),
        ("regressor", HistGradientBoostingRegressor(
            learning_rate=.05, max_leaf_nodes=15, max_iter=220, min_samples_leaf=80,
            l2_regularization=10.0, random_state=20261027,
        )),
    ])
    target_train = np.log1p(parts["train"]["first_observed_limit"].to_numpy(float))
    model.fit(parts["train"][NUMERIC + CATEGORICAL], target_train)
    pred_cal = np.expm1(model.predict(parts["calibration"][NUMERIC + CATEGORICAL]))
    residual = np.abs(parts["calibration"]["first_observed_limit"].to_numpy(float) - pred_cal)
    # Finite-sample split-conformal radius for target marginal coverage 80%.
    rank = int(np.ceil((len(residual) + 1) * .80))
    radius = float(np.partition(residual, min(rank - 1, len(residual) - 1))[min(rank - 1, len(residual) - 1)])

    test = parts["test"].copy()
    pred = np.maximum(0, np.expm1(model.predict(test[NUMERIC + CATEGORICAL])))
    low = np.maximum(0, pred - radius)
    high = pred + radius
    y = test["first_observed_limit"].to_numpy(float)
    dummy = DummyRegressor(strategy="median").fit(parts["train"][NUMERIC + CATEGORICAL], parts["train"]["first_observed_limit"])
    base = dummy.predict(test[NUMERIC + CATEGORICAL])
    results = {
        "task": "first_observed_credit_limit_proxy",
        "label_definition": "For each card account, retain the earliest supplied MONTHS_BALANCE row with a positive limit; for each customer retain the earliest such account. This is an observation-window proxy, not confirmed first credit approval.",
        "feature_timing": "Application-side fields only; no card balance, payment, delinquency, historical-card or post-observation fields are used.",
        "coverage": {role: int(len(part)) for role, part in parts.items()},
        "model": "HistGradientBoostingRegressor on log1p(proxy limit), with median/mode preprocessing fitted only on train.",
        "baseline": "Train-set global median proxy limit.",
        "test_metrics": {"hgb_proxy_model": metric_block(y, pred), "median_baseline": metric_block(y, base)},
        "conformal_interval": {
            "target_coverage": .80,
            "calibration_absolute_residual_radius": radius,
            "test_coverage": float(np.mean((y >= low) & (y <= high))),
            "mean_interval_width": float(np.mean(high - low)),
        },
        "limitations": [
            "The public data do not contain an observed initial approval timestamp or a counterfactual approved-limit label.",
            "The earliest available credit-card record may occur after account origination and may reflect later policy changes.",
            "The result is a research proxy and uncertainty band, not an automated credit-limit decision or causal policy estimate.",
            "A conditional GAN would generate synthetic values but cannot establish the correctness of an unobserved initial-limit target; it is therefore not used as the primary method.",
        ],
    }
    (out / "first_limit_proxy_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame({
        "SK_ID_CURR": test["SK_ID_CURR"], "first_observed_month": test["first_observed_month"],
        "first_observed_limit": y, "predicted_limit_median": pred,
        "interval_low_80": low, "interval_high_80": high,
    }).to_csv(out / "程序输出_first_limit_proxy_测试集预测.csv", index=False)
    save_figures(out, test, pred, low, high)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
