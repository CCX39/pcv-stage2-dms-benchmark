# 当前项目状态

更新日期：2026-07-13。本文档记录阶段 1B.1 只读差异审查完成后的本机状态。

## 1. 项目与 Git 基线

本仓库为 Stage2 allocation 准备环境专属候选级 CPU 处理耗时。阶段 0A/0B 已冻结基础契约，阶段 0C 已完成 frame1051 的 800-candidate inventory 与抽样计划，阶段 1A 已完成 Python 真实测量，阶段 1B 已完成 provisional 模型标定和 derived handoff。阶段 1B.1 对旧 Python benchmark 与当前结果的相反排序进行了只读审查。

阶段 1B.1 开始时：

```text
E:\Miunaaaa\0-work\code\pcv-stage2-dms-benchmark
## main...origin/main
7610362 feat: calibrate Python d_ms pilot models
```

远程 `origin` 指向 `https://github.com/CCX39/pcv-stage2-dms-benchmark.git`。本阶段不执行 push。

## 2. 当前 Python measured 与 calibrated 状态

环境为 CPython 3.13.0、numpy 2.5.1、plyfile 1.1.4、DracoPy 2.0.0，`environment_id = python_windows_x64`。

阶段 1A pilot 为 100/100 成功：PLY 25、DRC 75，覆盖 5 个 tile。磁盘读取位于计时外；两条路径都在计时内生成独立 `float32[N,3]` positions 与 `uint8[N,3]` colors；每候选 warmup 2、sample 5，以 p50 为阶段 1B 拟合目标。

阶段 1B 选中模型：

```text
PLY P1: d_hat_ms = 0.15954514764960334
                     + 3.7770090745876392 * (point_count / 1000)
normalized_mae = 0.007476571814053519

DRC D1: d_hat_ms = -0.029712238641829095
                     + 0.23967649584133888 * (point_count / 1000)
normalized_mae = 0.020813844203006367
```

阶段 1B 的 grouped validation 和全 inventory 检查通过。审查未发现 ns/ms 换算、point count、RGB、缓存复用、p50 或 feature scale 错误。模型忠实反映当前 measured pilot，但其低误差只说明当前 5-tile 样本内关系稳定。

## 3. 阶段 1B.1 审查结论

旧项目确有 DRC 慢于 PLY 的本地 CSV 证据，当前项目确有相反排序的 measured 证据。两套实验不具备直接可比性，关键差异包括：

- 当前 PLY 使用 plyfile + `BytesIO`，旧 PLY 使用 Open3D path API。
- 当前排除磁盘读取，旧项目把 PLY/DRC 文件读取包含在 parser timer 内。
- 当前强制生成独立 canonical arrays；旧项目只到 backend arrays，没有统一 dtype/ownership 契约。
- 当前资产是 612–35,548 点的 G128 tile；旧 Longdress 资产是 7,658–765,821 点的降采样 full-cloud。
- 旧 DRC 显式组合 qc，当前 active profile 未显式 qc/qg。
- 当前使用 warmup 2、sample 5、p50；旧项目无显式 warmup，实际 repeat 未写入 CSV，并用 mean。

当前 PLY 路径在 `column_stack` 后执行显式 copy，DRC 路径没有等价 stack 中间步骤。这是可能影响相对耗时的直接代码事实，但不是当前 canonical 输出契约的实现错误。完整证据等级、结果范围和对照表见 `PHASE1B1_LEGACY_PYTHON_DISCREPANCY_AUDIT.zh-CN.md`。

## 4. Handoff 状态

已纳入 Git 的交付仍为：

```text
results/python_frame1051_measured_summary_v1.json
results/python_frame1051_calibration_v1.json
handoff/python_frame1051_candidate_dms_v1.json
```

handoff 覆盖 800 个候选，其中 PLY 200、DRC 600，使用 `provenance = derived`，不是 800 个逐候选 measured 结果。本轮未修改上述 JSON，也未改变其中阶段 1B 的内部判定字段。

操作层面的当前状态为：

```text
review_status = review_pending
allocation_integration_status = temporarily_hold_for_allocation_integration
```

`recommended_for_allocation_pilot = true` 仅表示模型通过阶段 1B 的内部完整性与 normalized MAE 阈值，不代表已经完成与旧实验的公平性对齐。建议 allocation 在最小 apples-to-apples 实验完成前暂缓接入。

## 5. 旧项目只读状态

审查开始时：

```text
E:\Miunaaaa\0-work\code\PointCloud_Benchmark
## main...origin/main
?? scripts/plot_time_vs_point_count_filtered.py
cb3a197 修改说明：readme更新
```

既有未跟踪脚本 `scripts/plot_time_vs_point_count_filtered.py` 未被修改。旧 benchmark、`pcv-stage2-allocation`、`pcv-stage2-data-prep` 均保持只读；本轮没有运行旧 benchmark、没有生成点云或新测量结果。

## 6. Reference 与交付完整性

`reference/Decode_Worker.js` 未修改，其阶段基线 SHA-256 为：

```text
0747B51E9983E59ACC5E911047AE7EBC71213303A60EC7B0548329101775E56C
```

阶段 1B.1 不修改 `results/`、`handoff/`、源代码、测试或依赖，只新增审查文档并更新中文状态入口。

## 7. 当前限制

- 只完成 Longdress frame1051、5 个测量 tile、Python 环境的 provisional 标定。
- 尚未完成 Longdress 多帧、其他数据集、C++ 或 JavaScript 测量与模型。
- 旧结果缺少实际 Python/Open3D/DracoPy/Draco 版本、repeat count、机器快照和受控 run manifest。
- 当前留一 tile 验证不能回答 backend effect、boundary effect、asset-scale effect 或 output-conversion effect。
- allocation 仓库尚未修改，且当前建议暂缓接入 handoff。

## 8. 下一阶段建议

下一阶段应先做小规模 2×2 对齐实验，而不是直接扩大 allocation 使用范围：在同一批 frame1051 tile、同一 payload 和同一点数上，对照当前 plyfile 与 legacy-equivalent Open3D PLY 路径，以及当前与旧 DRC 路径；每一路分别使用 legacy boundary 和 current canonical boundary。

该实验应固定 runtime/backend 版本、warmup、sample count 与统计量，优先分离 backend、计时边界、资产尺度和输出转换影响。对齐完成后再决定恢复 provisional allocation 接入，或扩充 Longdress tile/frame 后重新标定。
