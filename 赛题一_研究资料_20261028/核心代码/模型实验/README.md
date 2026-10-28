# 模型实验

赛题一全部训练、评估、出图与复现校验代码。**配套仓库「赛题一_评分网页系统」所用的冻结模型由本目录产出。**

## 运行前必须补数据

为避免重复保存，本目录**不包含** `data/`。请先从仓库根目录执行：

```powershell
Copy-Item -Recurse .\数据集 .\核心代码\模型实验\data
cd 核心代码\模型实验
python -m pip install -r ..\..\requirements.txt
python src\run_experiment.py
```

`data/`、`models/`、`results/`、`tmp/` 均为本地生成，已被 `.gitignore` 排除。

## src/ 脚本分组

### 数据准备
| 文件 | 作用 |
|---|---|
| `prepare_study.py` | 冻结已有输入，构造无标签的观察 DPD 变化表 |

### 模型与公共契约
| 文件 | 作用 |
|---|---|
| `risk_model.py` | 统一的特征、校准与评分契约 |
| `delinquency_model.py` | 带明确封顶与饱和语义的非负 DPD 响应 |
| `study_common.py` | 公共工具与常量 |
| `run_shared.py` | 协议 B：固定等通道共享 + 可学非负公共系数 |

### 训练与复现
| 文件 | 作用 |
|---|---|
| `run_experiment.py` | 冻结开发协议，避免用新测试标签选择模型族或权重 |
| `reproduce.py` | 从冻结队列与冻结基线重训全部候选，比对一致性 |

### 评估与校验
| 文件 | 作用 |
|---|---|
| `evaluation.py` | 评估指标 |
| `analyze_results.py` | 全部候选的联合复核，含未通过开发闸门的方案 |
| `verify.py` | 交付校验 |

### 推理
| 文件 | 作用 |
|---|---|
| `predict.py` | 候选原型：模型响应与运营复核分离输出 |
| `make_examples.py` | 生成评分界面所需的 `examples/` 输入与期望输出 |

### 出图
| 文件 | 作用 |
|---|---|
| `make_figures.py` | 客户级分数图 |
| `make_fluctuation_figures.py` | 图 2、图 3：纯提额响应与逾期边界响应 |

### 报告与打包
| 文件 | 作用 |
|---|---|
| `build_report.py` / `report_layout.py` | 报告生成与版式 |
| `package_delivery.py` | 打包已核验输出并对解压副本做冒烟测试 |

### 首授额度代理
| 文件 | 作用 |
|---|---|
| `first_limit_proxy.py` | 首次可观测信用卡额度代理建模（梯度提升 + 保形区间） |

运行时须另行提供上游 `credit_card_balance.csv`：

```powershell
python src\first_limit_proxy.py --raw-credit-card <credit_card_balance.csv 路径>
```

## baseline/models/

18 个冻结基线模型 = **6 组划分 × 3 类方法**：

- 分组：`101`、`20260923`、`211`、`307`、`401`、`503`
- 方法：`lr`（逻辑回归）、`hgb_mono`（单调梯度提升树）、`consistency`（一致性约束）

这些是复现比对的参照物，评分界面不使用它们。

## docs/

| 文件 | 内容 |
|---|---|
| `实验协议.md` | 主实验协议 |
| `协议补充_B.md` / `协议补充_C.md` | B、C 组的序贯设计补充 |
| `复现说明.md` | 本轮复现方式、容差、契约检查与已知边界 |
| `逾期响应增强实验报告.md` | 逾期响应增强实验结果 |

B、C 两组是在 A/B 验证响应失败后加入的**序贯设计**，不是从全新独立数据中发现的结论，阅读时需注意这一点。

## 其他目录

| 路径 | 内容 |
|---|---|
| `融合阶段图1源代码/` | `make_figures.py` 与 `common.py`，产出论文图 1 |
| `首次可观测额度实验结果/` | 结果 JSON、图 1/图 2、测试集预测 CSV |
| `requirements_原训练环境.txt` | 原训练环境依赖 |
| `数据集放置说明.md` | 数据放置位置说明 |
