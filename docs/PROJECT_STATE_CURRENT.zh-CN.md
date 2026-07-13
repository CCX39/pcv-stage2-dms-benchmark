# 当前项目状态

更新日期：2026-07-13。本文档记录阶段 1B 完成后的本机真实状态，供后续接力使用。

## 1. 项目与 Git 基线

本仓库为 Stage2 allocation 准备环境专属候选级 CPU 处理耗时。阶段 0A/0B 已冻结基础契约，阶段 0C 已完成 800-candidate inventory 与抽样计划，阶段 1A 已完成 Python 真实测量，阶段 1B 已完成 provisional 模型标定与 frame1051 derived handoff。

阶段 1B 开始时：

```text
E:\Miunaaaa\0-work\code\pcv-stage2-dms-benchmark
## main...origin/main
72236f3 feat: add Python pilot benchmark
```

远程 `origin` 指向 `https://github.com/CCX39/pcv-stage2-dms-benchmark.git`。本阶段不执行 push。

## 2. 输入与环境

Python 环境：CPython 3.13.0、numpy 2.5.1、plyfile 1.1.4、DracoPy 2.0.0，`environment_id = python_windows_x64`。

输入 SHA-256：

```text
phase1a pilot 0591575D6558DA73E89A2634C0CFA996A385287DCB0F4F083EBF317CB2D06516
inventory     7D5B0B658BDB75B2BB4B81359DDA3A46D4171F4FE28B388FE4C6F43DB8BFA915
```

pilot 审查通过：100/100 成功，PLY 25、DRC 75，5 个 tile，身份、provenance、正数值、点数一致性和 inventory join 均无错误。`target_statistic = p50_ms`。

## 3. 标定实现与验证

- `calibration.py`：严格审查、P0-P2 / D0-D3 模型、按 `tile_id` 留一交叉验证、误差指标、5% 简化选择规则和推荐判定。
- `derived_export.py`：measured summary、calibration artifact 和 800-candidate derived handoff。
- `cli.py`：新增 `python-calibrate`。
- `test_calibration.py`、`test_derived_export.py`：覆盖分组无泄漏、拟合预测、模型选择、provenance 与 handoff 身份完整性。

验证为 5 折 leave-one-tile-out，每折 4 个训练 tile、1 个完整验证 tile。模型不使用 `candidate_key`、`candidate_id`、`tile_id` 或数组位置作为特征。

## 4. 选中模型

PLY 选择 P1：

```text
d_hat_ms = 0.15954514764960334
           + 3.7770090745876392 * (point_count / 1000)
normalized_mae = 0.007476571814053519
recommended_for_allocation_pilot = true
```

DRC 选择 D1：

```text
d_hat_ms = -0.029712238641829095
           + 0.23967649584133888 * (point_count / 1000)
normalized_mae = 0.020813844203006367
recommended_for_allocation_pilot = true
```

两类在完整 inventory scope 上均产生有限正预测，没有做负值裁剪。详细候选模型指标、公式和选择理由见 `PHASE1B_PYTHON_CALIBRATION_AND_HANDOFF.zh-CN.md`。

## 5. 版本化交付

已生成并纳入 Git：

```text
results/python_frame1051_measured_summary_v1.json
results/python_frame1051_calibration_v1.json
handoff/python_frame1051_candidate_dms_v1.json
```

measured summary 为 100 条且不含 raw samples；handoff 为 800 条，其中 PLY 200、DRC 600。800 个 `candidate_key` 唯一，800 个 `(tile_id, candidate_id)` 组合唯一，全部 `d_hat_ms` 有限且大于 0。

handoff 使用 `provenance = derived`，不是逐候选直接 measured。其 scope 为 `provisional_frame1051_python_pilot`，两类均不具备 final model、跨 frame 或跨数据集资格。

## 6. 测试、外部仓库与 reference

阶段 1B 实现后共 31 个 unittest。最终定向检查已执行：

```powershell
.venv\Scripts\python -m unittest discover
git diff --check
```

两项均通过；三个版本化 JSON 也已完成重载、计数、唯一身份、正预测、provenance、raw-sample 排除和 grouped-validation 泄漏检查。

外部仓库阶段 1B 开始状态：

```text
pcv-stage2-data-prep   ## main...origin/main
pcv-stage2-allocation  ## master...origin/master
PointCloud_Benchmark   ## main...origin/main
                       ?? scripts/plot_time_vs_point_count_filtered.py
```

旧 benchmark 未跟踪脚本为既有状态。本轮不修改三个外部仓库，也不修改 `reference/Decode_Worker.js`；其基线 SHA-256 为：

```text
0747B51E9983E59ACC5E911047AE7EBC71213303A60EC7B0548329101775E56C
```

## 7. 当前限制与下一阶段

当前只完成单帧、5 个测量 tile、Python 环境的 provisional 标定。尚未完成 Longdress 多帧、其他数据集、C++、JavaScript、统计策略最终确认或论文级模型验证。

下一阶段可以将版本化 handoff 交给 allocation 做 provisional proxy 替换实验，但必须在 allocation 侧显式记录 calibration ID、环境与 scope；本仓库当前没有修改 allocation。并行研究路线应扩充 tile / frame 覆盖并重新做 grouped validation，后续再建立 C++、JavaScript 独立模型。
