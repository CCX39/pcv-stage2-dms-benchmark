# 阶段 1B Python pilot 模型标定与 frame1051 derived d_ms 交付

本文档记录阶段 1B 的 measured 输入审查、按 tile 分组验证、模型比较、最终公式和版本化 handoff。该交付是单帧 provisional pilot，不是论文级通用模型。

## 1. 输入与审查

输入文件：

```text
outputs/phase1a_python_pilot.json
outputs/phase0c_frame1051_inventory.json
```

SHA-256：

```text
pilot     0591575D6558DA73E89A2634C0CFA996A385287DCB0F4F083EBF317CB2D06516
inventory 7D5B0B658BDB75B2BB4B81359DDA3A46D4171F4FE28B388FE4C6F43DB8BFA915
```

审查通过：pilot run 为 `success`，100 个候选全部成功，其中 PLY 25 个、DRC 75 个；关键数值均为有限正数，decoded point count 与 metadata 一致，`candidate_key` 唯一且全部存在于 800-candidate inventory。run 与 records 均保持 `provenance = measured`、`measurement_scope = longdress_frame1051_pilot`，并且不具备 final model 或 allocation 直接使用资格。

## 2. 目标统计量与验证方式

本轮冻结 `target_statistic = p50_ms`，仅适用于 Python frame1051 provisional pilot。每候选只有 5 次正式测量，p50 对偶发抖动比 mean 更稳健；mean 仍保留在 measured summary 中供审查，不作为主要拟合目标。

PLY 与 DRC 分别采用按 `tile_id` 分组的留一 tile 交叉验证（leave-one-tile-out cross-validation）。共 5 折，每折以 4 个 tile 拟合，完整留出另 1 个 tile 的全部 PDL / QP 候选。同一 tile 不会同时出现在训练与验证中。

报告指标：`mae_ms`、`rmse_ms`、`median_absolute_error_ms` 和 `normalized_mae`。其中 normalized MAE 为全部 out-of-fold MAE 除以全部验证目标 p50 的中位数，不使用 MAPE 作为主要指标。

## 3. 候选模型与选择规则

PLY：

- P0：训练目标中位数常数；
- P1：`point_count` 线性；
- P2：`file_size_bytes` 线性。

DRC：

- D0：训练目标中位数常数；
- D1：`point_count` 线性；
- D2：`point_count + file_size_bytes` 线性；
- D3：D2 加 `qp` 类别项，以 `qp=8` 为基准。

`point_count` 与 `file_size_bytes` 均除以固定尺度 1000。`cl` 恒为 10，不拟合；`pdl_ratio` 不单独作为默认特征；`candidate_id`、`candidate_key`、`tile_id` 和数组位置均不进入模型。

每种表示先按五折平均 MAE 找到最佳值；处于最佳值 5% 以内的模型选择参数更少者。任何 out-of-fold 或全 inventory 预测非有限、等于 0 或小于 0 的模型均不可选择，不做静默裁剪；常数基线始终保留。

## 4. PLY 验证结果

| 模型 | MAE (ms) | RMSE (ms) | 中位绝对误差 (ms) | normalized MAE | 全 scope 正预测 |
|---|---:|---:|---:|---:|---|
| P0 | 31.255996 | 40.128890 | 28.682050 | 0.978269249 | 是 |
| P1 | 0.238879 | 0.368806 | 0.132629 | 0.007476572 | 是 |
| P2 | 0.240359 | 0.370801 | 0.133194 | 0.007522903 | 是 |

P1 的平均 MAE 最低；P2 在 5% 容差内且复杂度相同，但 MAE 更高，因此选择 P1。

最终 PLY 模型：

```text
d_hat_ms = 0.15954514764960334
           + 3.7770090745876392 * (point_count / 1000)
```

训练样本为 25 个候选、5 个 tile。该公式只适用于当前 Python 环境与 frame1051 PLY metadata scope。

## 5. DRC 验证结果

| 模型 | MAE (ms) | RMSE (ms) | 中位绝对误差 (ms) | normalized MAE | 全 scope 正预测 |
|---|---:|---:|---:|---:|---|
| D0 | 1.990931 | 2.544529 | 1.819250 | 1.016403240 | 是 |
| D1 | 0.040770 | 0.052701 | 0.035622 | 0.020813844 | 是 |
| D2 | 0.040965 | 0.051437 | 0.033690 | 0.020913280 | 是 |
| D3 | 0.041432 | 0.052089 | 0.033891 | 0.021151950 | 是 |

D1 的平均 MAE 最低；D2、D3 虽在 5% 容差内，但特征更多，因此选择 D1。

最终 DRC 模型：

```text
d_hat_ms = -0.029712238641829095
           + 0.23967649584133888 * (point_count / 1000)
```

训练样本为 75 个候选、5 个 tile。截距为负，但在当前 600 个 DRC 候选 scope 上所有完整预测均有限且大于 0；实现没有对预测做裁剪。该公式不支持外推到当前 inventory 之外的点数范围。

## 6. Provisional 交付判定

PLY 与 DRC 的全部 scope 预测均有限且大于 0，身份审查无错误，leave-one-tile-out normalized MAE 均不超过 0.30，因此两类均标记：

```text
recommended_for_allocation_pilot = true
allocation_use_scope = provisional_frame1051_python_pilot
eligible_for_final_model = false
cross_dataset_validated = false
cross_frame_validated = false
```

该 true 只允许 allocation 后续进行 provisional 替换实验，不代表模型已经获得最终研究结论或跨环境适用性。

## 7. 版本化文件与 join

```text
results/python_frame1051_measured_summary_v1.json
results/python_frame1051_calibration_v1.json
handoff/python_frame1051_candidate_dms_v1.json
```

measured summary 保留 100 个直接测量候选的 p50 / mean 和身份摘要，不包含 `raw_samples_ms`。calibration artifact 保留所有候选模型指标、五折信息、选择结果、完整公式、尺度和参数。handoff 覆盖 inventory 全部 800 个候选，其中 PLY 200 个、DRC 600 个。

allocation 后续应以 `candidate_key` 为主键，并同时核验 `dataset_id`、`frame_id`、`grid_profile_id`、`tile_id`、`candidate_id`、representation、PDL 与 DRC codec 参数。不得依赖候选数组位置。`d_hat_ms` 是 `derived` 模型估计，`r_bytes` 仍是 data-prep / allocation metadata 中的文件本体字节数，二者语义不同。

## 8. 限制、可用范围与下一阶段

当前模型只来自 Longdress frame1051 的 5 个测量 tile，使用 CPython 3.13.0、plyfile 1.1.4、DracoPy 2.0.0 和 numpy 2.5.1。尚未跨 frame、跨数据集、跨 Python runtime 或跨后端验证，也不能替代 C++ / JavaScript 环境模型。

当前可以将 handoff 交给 allocation 做明确标注的 provisional 替换实验，但本仓库没有修改 allocation。若未来扩充 Longdress tile / frame 后误差显著变化，应重新标定；后续还需 C++、JavaScript 和多数据集验证，才能讨论最终模型与统计策略。
