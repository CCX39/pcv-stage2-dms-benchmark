# 阶段 2A：Python 文件到数组的 d_stage_ms pilot 与 provisional handoff

更新日期：2026-07-14。

## 1. 目的与环境关系

阶段 1B.5 将 allocation 正式指标修正为解析阶段端到端耗时 `d_stage_ms`。本阶段先建立一个可审查、可复现的 Python path execution profile，为 allocation 提供 Longdress frame1051 provisional handoff。该结果只代表本节冻结的 Python/Windows 路径，不代表未来 C++ 或 JavaScript Worker；三类环境的 measured、calibrated 与 derived 记录不得混合。

## 2. Execution profile

正式 profile 为：

```text
environment_id          python310_open3d019_dracopy200_path_stage_windows_x64
measurement_kind        parse_stage_end_to_end
timing_start            path_delivered_to_loader
timing_end              positions_colors_ready
filesystem_cache_policy os_managed_repeated_path_load
timer_api                time.perf_counter_ns
Python                   CPython 3.10.20
Open3D                   0.19.0
DracoPy                  2.0.0
NumPy                    2.2.6
OS                       Windows 10.0.22631 x64
```

测量使用仓库 ignored 环境 `.venv/open3d310`。只读探测的研究者 conda 环境 `open3d_env` 同为 Python 3.10.20、Open3D 0.19.0、DracoPy 2.0.0 和 NumPy 2.2.6；本阶段没有修改该 conda 环境、全局 Python 或 conda base。PLY 与 DRC 的 smoke 和 pilot 均由 `.venv/open3d310` 的同一个解释器执行，没有拼接 Python 3.10 与 3.13 的结果。

## 3. 精确计时链路

正式起点是候选路径已经作为函数参数交付解析模块、准备调用实际 loader 的瞬间；终点是新的独立数组完整生成：

```text
positions: float32[N, 3]
colors:    uint8[N, 3]
```

PLY 路径经旧 `PointCloud_Benchmark/scripts/benchmark_python.py` 的只读代码证据确认，使用 Tensor API：

```text
path
-> open3d.t.io.read_point_cloud(path)
-> points/colors tensor extraction
-> positions float32 copy
-> round(clip(colors, 0, 1) * 255) -> colors uint8 copy
```

DRC 路径为：

```text
path
-> Path(path).read_bytes()
-> DracoPy.decode(payload)
-> positions float32 copy
-> colors uint8 copy
```

两条路径都把文件 open/read、loader/decoder、属性提取、必要转换、分配和复制纳入计时。路径定位、文件存在性与 metadata stat 检查在计时外；网络、服务端、GPU、`BufferGeometry`、材质、场景、渲染、日志和结果写盘排除。每次 warmup 和 sample 都重新打开并处理文件，不复用 payload、点云对象或 decoded object，也不计算 normals。

## 4. 文件系统缓存策略

本轮没有清理操作系统文件缓存，也不声称测量严格冷启动磁盘性能：

```text
warmup_count            2
sample_count            5
target_statistic        p50_ms
filesystem_cache_policy os_managed_repeated_path_load
```

每次 sample 仍会重新执行 path load；warmup 后文件可能位于 OS cache。因此该 profile 表示同一播放会话式、操作系统管理缓存条件下的重复 path load 性能。

## 5. Smoke 与 pilot

确定性选择 sample plan 中第一个 PLY 和第一个 DRC 后执行双格式 smoke，结果为 2/2 成功。两条记录均满足 point count、shape、dtype、RGB、独立 ownership、五个 raw samples 和 timing contract 检查。

```text
outputs/phase2a_python_path_stage_smoke.json
SHA-256 D3B3C1BE73253092641330DC674BB58B8730A6835AE5070D9568F9FC7B0B634A
```

随后运行阶段 0C 的 100-candidate sample plan：PLY 25、DRC 75、5 个 tile，成功 100、失败 0；所有 decoded point count 与 metadata 一致。

```text
outputs/phase2a_python_path_stage_pilot.json
SHA-256 FD9B3394A9B0B9828E254BB877A9418E41F295BDC9B84DB23F2BFB2E1633F059
```

raw pilot 位于 ignored `outputs/`，保留 `raw_samples_ms` 供本地审查但不提交。直接 measured 的 p50 范围为：

| representation | records | p50_ms 最小值 | p50_ms 最大值 |
|---|---:|---:|---:|
| PLY | 25 | 0.0782 | 2.1727 |
| DRC | 75 | 0.1947 | 9.2994 |

这些数值只描述本 profile，不用于断言其他环境中的 PLY/DRC 快慢关系。

## 6. 模型与分组验证

目标统计量为 `p50_ms`。PLY 与 DRC 独立按 `tile_id` 执行五折 leave-one-tile-out；每折将一个 tile 的全部 PDL/QP 留作验证，避免同 tile 候选进入训练和验证两侧。选择以 grouped CV MAE 为主，最佳值 5% 内偏向较简单模型，并要求 frame1051 全部适用候选预测有限且大于 0。

PLY 候选为 P0 常数、P1 点数线性、P2 文件大小线性、P3 非负点数线性。主要指标如下：

| 模型 | MAE ms | RMSE ms | median AE ms | normalized MAE | 全量正值 |
|---|---:|---:|---:|---:|---|
| P0 | 0.476166 | 0.613167 | 0.457650 | 0.892198 | 是 |
| P1 | 0.024084 | 0.034908 | 0.010117 | 0.045126 | 是 |
| P2 | 0.024035 | 0.034856 | 0.009714 | 0.045035 | 是 |
| P3 | 0.024084 | 0.034908 | 0.010117 | 0.045126 | 是 |

最终选择 P2：

```text
d_stage_ms = 0.040619658097626035
           + 0.003926988877250943 * (file_size_bytes / 1000)
```

DRC 候选为 D0 常数、D1 点数线性、D2 点数加文件大小、D3 再加 qp 类别项、D4 非负点数线性：

| 模型 | MAE ms | RMSE ms | median AE ms | normalized MAE | 全量正值 |
|---|---:|---:|---:|---:|---|
| D0 | 2.081215 | 2.731415 | 1.830450 | 1.017560 | 是 |
| D1 | 0.139835 | 0.182947 | 0.109793 | 0.068369 | 否 |
| D2 | 0.141519 | 0.187249 | 0.109264 | 0.069192 | 否 |
| D3 | 0.143795 | 0.191551 | 0.110715 | 0.070305 | 否 |
| D4 | 0.124579 | 0.177313 | 0.077144 | 0.060910 | 是 |

D1--D3 虽然 grouped CV 误差较低，但对全部 600 个 DRC 候选产生非正预测，不能被选择，也没有做预测后裁剪。最终选择 D4，其参数在拟合阶段满足非负约束：

```text
d_stage_ms = 0.0
           + 0.25404561763166683 * (point_count / 1000)
```

`tile_id`、`candidate_id` 和 `candidate_key` 均未作为模型特征。

## 7. 版本化交付与完整性

新增三个可提交资产：

```text
results/python_path_stage_frame1051_measured_summary_v1.json
results/python_path_stage_frame1051_calibration_v1.json
handoff/python_path_stage_frame1051_candidate_dms_v1.json
```

measured summary 含 100 条记录且不含 `raw_samples_ms`。calibration 完整保留候选模型、公式、参数、五折分组验证和 release gate。handoff 覆盖 inventory 的全部 800 个唯一 `candidate_key`，其中 PLY 200、DRC 600；所有 `d_stage_ms` 有限且大于 0。兼容字段 `d_hat_ms` 与 `d_stage_ms` 数值相同，但 provenance 明确为 `derived`，不能解释为 800 个候选逐个 measured。

allocation join 必须使用 `candidate_key`，并核对 `tile_id + candidate_id` 等身份字段，不能依赖数组位置。

## 8. Allocation release gate

以下条件均已通过：双格式 smoke、100/100 pilot、point count、同一 Python environment、`parse_stage_end_to_end` 边界、无 tile 泄漏、两类 normalized MAE 不高于 0.30、800 个有限正预测、provenance、文档和版本化资产完整。

```text
eligible_for_allocation       true
allocation_integration_status ready_for_provisional_integration
allocation_use_scope          provisional_python_path_profile
```

该资格只允许 allocation 后续对如下范围做 provisional 行为验证：Longdress frame1051、Windows x64、Python 3.10.20、Open3D 0.19.0 Tensor path loader、DracoPy 2.0.0、OS-managed repeated path load。它不是最终论文模型，不具备跨帧、跨数据集、跨环境泛化结论，也不代表浏览器 Worker 或 C++。

历史 plyfile v1 与 NumPy v2 继续作为 `core_parse_microbenchmark` 审计证据；Open3D path 对齐仍是 `path_loader_diagnostic`；Open3D from-bytes 仍是 blocked `capability_probe`。本阶段没有覆盖这些文件。

## 9. CLI

```powershell
$env:PYTHONPATH='src'
.venv\open3d310\Scripts\python -m pcv_dms_benchmark.cli python-path-stage-pilot `
  --inventory outputs\phase0c_frame1051_inventory.json `
  --sample-plan outputs\phase0c_frame1051_sample_plan.json `
  --data-prep-root E:\Miunaaaa\0-work\code\pcv-stage2-data-prep `
  --out outputs\phase2a_python_path_stage_pilot.json `
  --warmup 2 --samples 5

.venv\open3d310\Scripts\python -m pcv_dms_benchmark.cli python-path-stage-calibrate `
  --smoke outputs\phase2a_python_path_stage_smoke.json `
  --pilot outputs\phase2a_python_path_stage_pilot.json `
  --inventory outputs\phase0c_frame1051_inventory.json `
  --measured-summary-out results\python_path_stage_frame1051_measured_summary_v1.json `
  --calibration-out results\python_path_stage_frame1051_calibration_v1.json `
  --handoff-out handoff\python_path_stage_frame1051_candidate_dms_v1.json
```

## 10. 限制与下一阶段

本轮只有单帧、5 个测量 tile 和一个 Python path profile；文件缓存策略不是严格冷缓存，模型尚未跨帧或跨数据集验证。当前 handoff 可交给 allocation 做明确标注环境与范围的 provisional integration，但本仓库没有修改 allocation，也没有自动启动接入。

后续应分别测量 C++ 与 JavaScript Worker 的 `d_stage_ms`。JavaScript 正式边界仍应是完整 `ArrayBuffer` 到达 Worker 后，实际 PLY/DRC loader 开始处理，到 positions/colors TypedArray 就绪；不得与本 Python path profile 混合。
