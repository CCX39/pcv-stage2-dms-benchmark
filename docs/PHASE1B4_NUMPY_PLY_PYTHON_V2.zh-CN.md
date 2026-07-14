# 阶段 1B.4：NumPy 快速 PLY 内存解析与 Python v2 交付

> **阶段 1B.5 重分类：** NumPy v2 measured/calibrated/derived 资产现统一归类为 `core_parse_microbenchmark` / `d_core_ms` 下界，`eligible_for_allocation = false`、`allocation_integration_status = ineligible_measurement_scope`。本文中的 gate、数值和模型仍是历史实验事实，但不代表正式 `d_stage_ms`。

## 1. 背景与结论

阶段 1B.2 已证明 Open3D path API 明显快于 `plyfile`，但该路径包含磁盘读取；阶段 1B.3 又确认当前 Open3D 0.19.0 Windows wheel 的 `read_point_cloud_from_bytes` 对 PLY 返回空点云。继续更换或编译 Open3D wheel 不属于本阶段路线。

本阶段针对受控的 Stage2 tile binary PLY 实现 NumPy `frombuffer` 内存路径，并在同一 CPython 3.13 环境中重新测量 PLY 与 DRC。4-candidate gate、双格式 smoke 和 100-candidate pilot 均通过；v2 measured、calibrated、derived 文件均已形成。但 DRC 的可解释线性候选模型会对全量 inventory 中的小候选产生负预测，常数基线虽有效却未达到 `normalized_mae <= 0.30`，因此最终状态是：

```text
phase_status = completed_with_release_gate_not_met
allocation_integration_status = review_pending
```

## 2. NumPy PLY 适用范围

正式 processor 只接收 `bytes` 或只读 buffer，不接收路径、不执行文件读取、不调用 Open3D，也不创建临时文件。它面向当前 Stage2 corpus，不宣称是通用 PLY parser。

支持：

- `binary_little_endian 1.0`；
- LF 与 CRLF header；
- 动态 property 顺序；
- vertex scalar type：`char/int8`、`uchar/uint8`、`short/int16`、`ushort/uint16`、`int/int32`、`uint/uint32`、`float/float32`、`double/float64`；
- 必需的 `x/y/z/red/green/blue`；
- vertex 后续 element 可忽略。

明确拒绝：

- ASCII 或非 little-endian PLY；
- vertex list property；
- 缺失 vertex 或 XYZ/RGB；
- 非 `uint8` RGB；
- 不支持的 scalar type、非法点数或截断的 vertex payload。

失败使用明确的 capability/error code，包括 `UNSUPPORTED_PLY_FORMAT`、`VERTEX_ELEMENT_MISSING`、`REQUIRED_PROPERTY_MISSING`、`VERTEX_LIST_PROPERTY_UNSUPPORTED`、`UNSUPPORTED_SCALAR_TYPE`、`TRUNCATED_VERTEX_PAYLOAD`、`INVALID_VERTEX_COUNT` 和 `INVALID_RGB_TYPE`，不静默 fallback。

## 3. 正式计时边界

```text
payload 已完整驻留内存
-> 解析 PLY header 并构造 structured dtype
-> numpy.frombuffer 解释 vertex block
-> 分配新的 positions float32[N,3]
-> 分配新的 colors uint8[N,3]
-> 按列赋值完成 XYZ/RGB 提取与必要转换
```

计时外执行文件定位、`stat`、`read_bytes`、shape/dtype/point count/ownership 校验、record 组装和 JSON 写盘。`frombuffer` 视图不是最终交付结果；最终 positions/colors 均由 `numpy.empty` 新建并独立拥有。输出不含 normals。

## 4. 运行环境

```text
environment_id python313_numpy_ply_dracopy200_windows_x64
Python         CPython 3.13.0
numpy          2.5.1
DracoPy        2.0.0
plyfile        1.1.4，仅作诊断参照
OS             Windows 10.0.22631 x64
timer          time.perf_counter_ns
warmup_count   2
sample_count   5
```

PLY 与 DRC 在同一解释器、同一 `.venv` 和同一 pilot profile 中测量，没有拼接其他 Python 环境的 measured 值。

## 5. 4-candidate correctness 与性能 gate

选择阶段 0C 五个 tile 中 PDL 1.0 点数最小与最大的 tile，并分别取 PDL 0.2/1.0。NumPy fast 与 `plyfile` 在本轮同一 Python 3.13 环境测量；Open3D path p50 仅只读引用阶段 1B.2 诊断结果。

| tile_id | PDL | point_count | file_size_bytes | NumPy p50_ms | plyfile p50_ms | NumPy/plyfile | 既有 Open3D path p50_ms | correctness |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `gx_0_gy_4_gz_0` | 0.2 | 612 | 9,354 | 0.0176 | 2.3938 | 0.007352 | 0.0850 | passed |
| `gx_0_gy_4_gz_0` | 1.0 | 3,062 | 46,104 | 0.0229 | 11.8540 | 0.001932 | 0.2427 | passed |
| `gx_2_gy_1_gz_1` | 0.2 | 7,109 | 106,809 | 0.0422 | 26.7293 | 0.001579 | 0.4741 | passed |
| `gx_2_gy_1_gz_1` | 1.0 | 35,548 | 533,394 | 0.2285 | 134.3503 | 0.001701 | 3.2073 | passed |

4/4 候选的 point count、shape、dtype、坐标、RGB 与独立 ownership 校验通过；4/4 均比 `plyfile` 快超过 5 倍；正式 processor 的 file I/O 与 path API 检查均为 false。进入 100-candidate pilot 的 gate 通过。

原始诊断输出位于 ignored `outputs/phase1b4_numpy_ply_alignment.json`，SHA-256 为 `A5F547EE440751714A8F41EA41053A610BBACF2EA6695F0B7544E62A58158620`。

## 6. Smoke 与 100-candidate pilot

双格式 smoke 的 PLY 与 DRC 均成功，输出 `outputs/phase1b4_python_numpy_smoke.json`，SHA-256 为 `B97A792E3D476249B6CC608CFE02AD35E88BB08B688C727CCFDA6F00BC87CE0E`。

100-candidate pilot 使用阶段 0C 的原 sample plan：PLY 25、DRC 75、共 5 个 tile；成功 100、失败 0；所有 decoded point count 与 metadata 一致。PLY p50 范围为 0.0160--0.1190 ms，中位数为 0.0360 ms；DRC p50 范围为 0.1481--8.8203 ms，中位数为 1.9779 ms。这些数值只描述当前单帧 provisional profile，不构成 backend 的普遍速度结论。

原始 pilot 位于 ignored `outputs/phase1b4_python_numpy_pilot.json`，SHA-256 为 `AE9F1E499D5D37718EC7FE4DB46CA715649A423B84209B0F793BCCC894C51B40`；其中 raw samples 不纳入 Git。

主要 CLI 入口为：

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python -m pcv_dms_benchmark.cli python-numpy-v2-pilot `
  --inventory outputs\phase0c_frame1051_inventory.json `
  --sample-plan outputs\phase0c_frame1051_sample_plan.json `
  --alignment-gate outputs\phase1b4_numpy_ply_alignment.json `
  --data-prep-root E:\Miunaaaa\0-work\code\pcv-stage2-data-prep `
  --out outputs\phase1b4_python_numpy_pilot.json --warmup 2 --samples 5

.venv\Scripts\python -m pcv_dms_benchmark.cli python-numpy-v2-calibrate `
  --alignment-gate outputs\phase1b4_numpy_ply_alignment.json `
  --smoke outputs\phase1b4_python_numpy_smoke.json `
  --pilot outputs\phase1b4_python_numpy_pilot.json `
  --inventory outputs\phase0c_frame1051_inventory.json `
  --measured-summary-out results\python_numpy_frame1051_measured_summary_v2.json `
  --calibration-out results\python_numpy_frame1051_calibration_v2.json `
  --handoff-out handoff\python_numpy_frame1051_candidate_dms_v2.json
```

标定命令在 release gate 未通过时返回非零状态，但仍写出带 `review_pending` 和完整审计信息的三个 v2 文件；该行为不等于执行失败或强行 ready。

## 7. 标定方法

目标统计量仍为 `p50_ms`。PLY 与 DRC 分别使用按 `tile_id` 分组的五折 leave-one-tile-out 验证，同一 tile 的候选不会同时进入训练与验证。模型选择以验证 MAE 为主；若与最佳值相差不超过 5%，选择特征更少者。所有模型还必须在对应的 200 或 600 个 inventory 候选上产生有限正预测，禁止裁剪负值。

特征尺度为：

```text
point_count_scaled = point_count / 1000
file_size_scaled = file_size_bytes / 1000
```

## 8. PLY candidate models

| 模型 | 特征 | MAE ms | RMSE ms | Median AE ms | normalized MAE | 全量预测有效 |
|---|---|---:|---:|---:|---:|---|
| P0 | 常数中位数 | 0.022752 | 0.030020 | 0.019500 | 0.632000 | 是 |
| P1 | point_count | 0.001591 | 0.002290 | 0.001288 | 0.044197 | 是 |
| P2 | file_size_bytes | 0.001592 | 0.002290 | 0.001285 | 0.044219 | 是 |

P1 与 P2 的 MAE 差异远小于 5%，二者特征数相同；P1 直接表达解析点数成本并略优，因此选择 P1：

```text
d_hat_ms = 0.012501787380941863
         + 0.002856343196791854 * (point_count / 1000)
```

训练候选 25、训练 tile 5，`recommended_for_allocation_pilot = true`。

## 9. DRC candidate models

| 模型 | 特征 | MAE ms | RMSE ms | Median AE ms | normalized MAE | 全量预测有效 |
|---|---|---:|---:|---:|---:|---|
| D0 | 常数中位数 | 2.027157 | 2.606311 | 1.822100 | 1.024904 | 是 |
| D1 | point_count | 0.055935 | 0.078063 | 0.039056 | 0.028280 | 否，最小预测为负 |
| D2 | point_count + file_size_bytes | 0.058713 | 0.081561 | 0.041577 | 0.029684 | 否，最小预测为负 |
| D3 | D2 + qp 类别项 | 0.059400 | 0.082337 | 0.039956 | 0.030032 | 否，最小预测为负 |

D1--D3 的 grouped validation 很好，但在全量 600 个 DRC 候选上分别产生负预测；按冻结规则它们不可选且不得裁剪。唯一通过全量正值 gate 的 D0 为：

```text
d_hat_ms = 1.9779
```

D0 的 normalized MAE 超过 0.30，因此 `recommended_for_allocation_pilot = false`。这不是测量失败，而是当前候选模型族、5-tile 测量覆盖与全量小候选范围之间的 release-gate 失败。

## 10. v2 交付与完整性

已生成并提交：

```text
results/python_numpy_frame1051_measured_summary_v2.json
results/python_numpy_frame1051_calibration_v2.json
handoff/python_numpy_frame1051_candidate_dms_v2.json
```

measured summary 包含 100 条简化 measured record，PLY 25、DRC 75，不含 `raw_samples_ms`。handoff 覆盖 inventory 全部 800 个唯一 `candidate_key`，PLY 200、DRC 600；`tile_id + candidate_id` 在当前 frame1051 范围内同样唯一；全部 `d_hat_ms` 有限且大于 0。handoff 是 calibrated 模型生成的 `derived` 数据，不是 800 个候选逐个 measured。

三个文件的 SHA-256 分别为：

```text
measured summary 4B15FF63339964F3339578C602C2EAE652105BEBFCAEC0CDD99FFD14D1F962D2
calibration    5AFAC010D1BD164659902C8D42F23600AC4C7F95531F2DC55582CF188E0760BE
handoff        2301CCF3CBF76C7E1929933BBCB477F571B54A3612B173FBEDB483C9282C627B
```

## 11. v1、Open3D blocker 与 v2

- v1：`historical_plyfile_profile`、`superseded_for_allocation_pilot`、`retained_for_audit`。它忠实记录 plyfile profile，不是伪造或程序错误。
- 阶段 1B.3：`blocked_open3d_windows_from_bytes_profile`、`retained_for_audit`。blocker 证据和代码未删除。
- v2：NumPy PLY + DracoPy 同环境 measured/calibrated/derived 交付已形成，但整体 release gate 未通过。

由于 DRC selected model 未达到 provisional 推荐阈值：

```text
allocation_integration_status = review_pending
```

当前不建议 allocation 接入整份 v2 handoff，也不应只取其中 PLY 后与其他环境 DRC 拼接。

## 12. 限制与下一阶段

- 仅覆盖 Longdress frame1051、5 个测量 tile 和 Python 单环境；尚无跨帧、跨数据集验证。
- NumPy PLY parser 只承诺当前受控 Stage2 binary little-endian scalar vertex corpus。
- 每候选仅 5 次正式样本，当前指标属于 provisional pilot。
- DRC 的线性模型在测量区间内稳定，但外推到更小候选时截距导致负值，不能用裁剪掩盖。
- C++ 与 JavaScript profile 尚未实现。

下一阶段应优先扩充覆盖小 point-count DRC 候选的 Longdress tile/frame 直接测量，或在保留可解释性的前提下评估天然保持正值的简单模型形式，再重复 grouped validation 和全量正值 gate。只有 PLY 与 DRC 都满足阈值后，整份 Python v2 handoff 才能改为 `ready_for_provisional_integration`。
