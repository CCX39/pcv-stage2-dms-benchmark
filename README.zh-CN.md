# pcv-stage2-dms-benchmark

本项目用于准备 Stage2 allocation 所需的候选级端侧解析耗时。阶段 1B.5 将正式指标冻结为解析阶段端到端耗时 `d_stage_ms`；此前 Python 结果重新分类为解析核心诊断量 `d_core_ms`。二者都不是文件大小、网络下载时间或端到端播放延迟。

## 项目边界

本仓库服务于硕士课题“轻量级视口感知点云体积视频传输与渲染协同优化”中的 Work1 / Stage2。Stage1 负责输出总预算 `Budget_total`，Stage2 在预算约束下为每个空间 tile 选择传输候选，本质为多选一背包问题。本仓库只准备 Stage2 后续可使用的候选级处理耗时输入，不实现 allocation solver。

与相邻仓库的职责关系如下：

- `pcv-stage2-data-prep`：负责生成和验证 frame 1051 pilot 的 tile binary PLY 与 tile DRC 资产及 metadata；本仓库只读消费其 metadata 语义。
- `pcv-stage2-allocation`：负责 Stage2 候选选择和 proxy pilot；阶段 2A 已提供通过资格审查的 Python path profile provisional `d_stage_ms` handoff，但 allocation 仓库尚未接入或修改。
- 旧 `PointCloud_Benchmark`：只作为历史实现参考；其计时边界与本仓库冻结的第一版 `d_ms` 边界不同，不能直接复用为新测量契约。

## 正式输入资产范围

本 benchmark 后续正式待测输入只包括：

- Stage2 tile binary PLY；
- Stage2 tile DRC。

原始 8i Longdress raw ASCII full-cloud PLY 只作为来源追溯和 data-prep 输入背景，不进入正式 `d_stage_ms` 测量、抽样或拟合样本集。

## 运行环境

后续计划分别建立三类独立测量环境：

- `cpp_native_windows_x64`；
- `python_windows_x64`；
- `js_worker_browser_windows_x64`。

三种环境不得混合为同一个 `d_ms`。每次 Stage2 实验只能选择一个明确环境配置，并使用该环境对应的候选级处理耗时估计值。阶段 1A 已固定 Python pilot 的实际运行时与后端；C++、JavaScript 以及未来正式测量环境仍需分别冻结。

## 正式测量边界

正式 `d_stage_ms` 从完整候选完成网络传输并交付实际端侧解析模块、模块开始处理的瞬间计时，到 positions/colors 数组完整生成并可交给渲染模块为止。实际 parser/loader/decoder、中间对象、必要转换、分配和复制计入；网络、GPU、geometry、场景和 render 默认排除。

统一 CPU 点云结构（canonical CPU point-cloud representation）建议为：

```text
positions: float32[N, 3]
colors: uint8[N, 3]
```

直接测量、模型标定和候选级推导值必须区分：

- `measured`：直接对真实候选样本重复测量得到的耗时统计；
- `calibrated`：由直接测量样本标定得到的环境专属耗时模型、模型参数及验证结果；
- `derived`：由已标定模型为大量候选推导得到的候选级 `d_hat_ms`；
- `proxy`：具备工程解释但尚未直接测量或标定得到的代理值；
- `synthetic`：用于未来测试或受控验证的人造数据。

后续路线可以概括为：

```text
d_hat_ms = f(environment, representation, candidate_metadata)
```

阶段 1A 至 1B.4 的 Python 资产已按阶段 1B.5 重分类为 `core_parse_microbenchmark`，只用于诊断和下界分析。阶段 2A 新增同一 Python 3.10 环境中的 Open3D PLY path loader 与 DracoPy DRC path stage 测量，生成当前唯一 `eligible_for_allocation = true` 的 provisional Python handoff；allocation 仓库仍未修改。

## 阶段文档

- [d_ms 测量契约](docs/MEASUREMENT_CONTRACT.zh-CN.md)：冻结正式 `d_stage_ms`、诊断 `d_core_ms`、计时边界、measurement kind 和 allocation 资格。
- [阶段 0B 运行环境、采样计划与记录格式](docs/PHASE0B_RUNTIME_SAMPLING_AND_RECORD_PLAN.zh-CN.md)：记录三类运行环境候选配置、Longdress pilot 抽样路线、三类记录字段草案和 allocation join 原则。
- [阶段 0C 候选清单与抽样骨架](docs/PHASE0C_METADATA_INVENTORY_AND_SAMPLING.zh-CN.md)：记录 metadata inventory adapter、sampling planner、CLI、测试和真实 metadata 只读验证结果。
- [阶段 1A Python pilot](docs/PHASE1A_PYTHON_PILOT.zh-CN.md)：记录 Python 进程内 PLY / DRC 后端、真实 smoke、100-candidate pilot 与结果适用边界。
- [阶段 1B Python 标定与交付](docs/PHASE1B_PYTHON_CALIBRATION_AND_HANDOFF.zh-CN.md)：记录 pilot 审查、按 tile 分组验证、模型比较、公式、指标与 provisional handoff 限制。
- [阶段 1B.1 旧 Python timing 差异审查](docs/PHASE1B1_LEGACY_PYTHON_DISCREPANCY_AUDIT.zh-CN.md)：对照旧项目与当前链路的 backend、边界、资产、结果和证据等级，并记录 handoff 暂缓接入状态。
- [阶段 1B.2 PLY backend 最小对齐实验](docs/PHASE1B2_PLY_BACKEND_ALIGNMENT.zh-CN.md)：用 4 个候选对照 plyfile 与 Open3D，记录正确性、边界限制和 backend 切换建议。
- [阶段 1B.3 Open3D 内存 PLY 与 Python v2 审查](docs/PHASE1B3_OPEN3D_IN_MEMORY_PYTHON_V2.zh-CN.md)：记录 from-bytes Windows wheel blocker、双格式 smoke 和未生成 v2 交付的原因。
- [阶段 1B.4 NumPy 快速 PLY 与 Python v2](docs/PHASE1B4_NUMPY_PLY_PYTHON_V2.zh-CN.md)：记录受控 binary PLY 内存解析、4-candidate gate、同环境重测、重新标定与 v2 release-gate 结论。
- [阶段 1B.5 d_ms 契约修正](docs/PHASE1B5_DMS_CONTRACT_CORRECTION.zh-CN.md)：记录 `d_stage_ms` / `d_core_ms` 分离、历史资产重分类和新的 allocation 资格规则。
- [阶段 2A Python path stage pilot 与 handoff](docs/PHASE2A_PYTHON_PATH_STAGE_PILOT_AND_HANDOFF.zh-CN.md)：记录文件到 canonical arrays 的正式 Python profile、测量、分组标定、release gate 与 800-candidate provisional handoff。
- [当前项目状态](docs/PROJECT_STATE_CURRENT.zh-CN.md)：记录本机仓库状态、只读审查发现、当前已冻结与未冻结事项。

## Longdress pilot 路线

第一版结果优先使用 Longdress 数据集快速形成环境专属 `d_hat_ms` 输入，为 `pcv-stage2-allocation` 实验提供可用依据。最快路径是从 `pcv-stage2-data-prep` 已有的 frame 1051 G128 tile binary PLY 与 DRC corpus metadata 出发，设计覆盖性抽样和直接测量计划。

后续再扩展到其他数据集，用于验证模型泛化性和修正误差。若未来需要 Longdress 多帧样本，应单独决定由 data-prep 生成多帧 tile assets，还是由本 benchmark 仓库生成 ignored 本地临时样本；当前阶段不生成任何样本。

## reference/Decode_Worker.js

`reference/Decode_Worker.js` 是 JavaScript Worker 处理路径的只读参考。它用于帮助界定未来 JS Worker 环境中的 PLY / DRC 路径和边界，不是本仓库要修改、优化或复制的实现来源。阶段 0A 与 0B 均记录其 SHA-256，并确认本轮未修改。

## 目录职责

- `reference/`：只读参考材料；当前仅保留研究者手动放入的 `Decode_Worker.js`。
- `docs/`：中文契约、计划与当前状态文档。
- `src/pcv_dms_benchmark/`：metadata planning 与 Python pilot 实现。
- `tests/`：synthetic metadata、binary PLY 与 fake decoder 单元测试。
- `results/`：版本化 measured summary 与 calibrated model artifact。
- `handoff/`：供 allocation 后续 provisional 实验读取的版本化 derived 候选交付。
- `.gitignore`：忽略测量输出、构建产物、环境目录和本地配置。

当前没有 C++、JavaScript、浏览器、WASM 或 allocation 接入工程；阶段 1B 模型仍未完成跨帧、跨数据集验证。

## 阶段 0C 最小用法

阶段 0C 新增的是 metadata-only 工具，不解析 PLY、不解码 DRC、不测量 `d_ms`。在本机可用如下命令从 data-prep metadata 生成 ignored 输出：

```powershell
$env:PYTHONPATH='src'
python -m pcv_dms_benchmark.cli inventory --data-prep-root E:\Miunaaaa\0-work\code\pcv-stage2-data-prep --out outputs\phase0c_frame1051_inventory.json
python -m pcv_dms_benchmark.cli sample-plan --inventory outputs\phase0c_frame1051_inventory.json --out outputs\phase0c_frame1051_sample_plan.json --max-tiles 5
```

`outputs/` 是本地生成结果目录，已由 `.gitignore` 忽略，不纳入版本库。

## 阶段 1A 最小用法

在仓库本地环境安装已声明依赖：

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e .
$env:PYTHONPATH='src'
```

先运行一个 PLY 与一个 DRC 的双格式 smoke：

```powershell
.venv\Scripts\python -m pcv_dms_benchmark.cli python-pilot `
  --inventory outputs\phase0c_frame1051_inventory.json `
  --sample-plan outputs\phase0c_frame1051_sample_plan.json `
  --data-prep-root E:\Miunaaaa\0-work\code\pcv-stage2-data-prep `
  --out outputs\phase1a_python_smoke.json `
  --warmup 2 --samples 5 --smoke
```

删除 `--smoke` 并将 `--out` 改为 `outputs\phase1a_python_pilot.json`，即可运行阶段 0C 计划中的 100 个候选。真实测量 JSON 留在 ignored `outputs/`，不得直接作为最终模型或 allocation 输入。

## 阶段 1B 标定与交付

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python -m pcv_dms_benchmark.cli python-calibrate `
  --pilot outputs\phase1a_python_pilot.json `
  --inventory outputs\phase0c_frame1051_inventory.json `
  --measured-summary-out results\python_frame1051_measured_summary_v1.json `
  --calibration-out results\python_frame1051_calibration_v1.json `
  --handoff-out handoff\python_frame1051_candidate_dms_v1.json
```

版本化交付文件：

- `results/python_frame1051_measured_summary_v1.json`；
- `results/python_frame1051_calibration_v1.json`；
- `handoff/python_frame1051_candidate_dms_v1.json`。

handoff 是由单帧、5 个测量 tile 标定模型生成的 `derived` 历史数据，不是 800 个候选逐个直接 measured 的结果。按阶段 1B.5 新契约，它继承 `core_parse_microbenchmark`，不具备 allocation 资格。

> 阶段 1B.1 历史状态：当时因 apples-to-apples 差异把 handoff 暂记为 `review_pending`。阶段 1B.5 已进一步将其判定为 `ineligible_measurement_scope`。详见 [阶段 1B.1 旧 Python timing 差异审查](docs/PHASE1B1_LEGACY_PYTHON_DISCREPANCY_AUDIT.zh-CN.md)。

> 阶段 1B.2 历史状态：4-candidate 正确性全部通过，诊断结果支持 Open3D backend 差异；Open3D path 数据现明确归类为 `path_loader_diagnostic`，不可接入 allocation。

> 阶段 1B.3 历史状态：Open3D 0.19.0 Windows wheel 的 `read_point_cloud_from_bytes(..., format="ply")` 对 synthetic 与真实 PLY 均返回空点云；该记录现为 blocked `capability_probe`。

## 阶段 1B.4 NumPy Python v2

该阶段验证的 Python 核心 profile 为同一 CPython 3.13 环境中的 NumPy `frombuffer` PLY bytes processor 与 `DracoPy.decode(bytes)`。按阶段 1B.5 新契约，它属于 `core_parse_microbenchmark` / `d_core_ms`，不是正式 `d_stage_ms`，不得接入 allocation。NumPy parser 仅面向当前 Stage2 binary little-endian scalar vertex corpus，不是通用 PLY parser。

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python -m pcv_dms_benchmark.cli numpy-ply-align `
  --inventory outputs\phase0c_frame1051_inventory.json `
  --sample-plan outputs\phase0c_frame1051_sample_plan.json `
  --phase1b2-alignment outputs\phase1b2_ply_backend_alignment.json `
  --data-prep-root E:\Miunaaaa\0-work\code\pcv-stage2-data-prep `
  --out outputs\phase1b4_numpy_ply_alignment.json --warmup 2 --samples 5
```

阶段 1B.4 已生成以下版本化文件：

- `results/python_numpy_frame1051_measured_summary_v2.json`；
- `results/python_numpy_frame1051_calibration_v2.json`；
- `handoff/python_numpy_frame1051_candidate_dms_v2.json`。

v1 plyfile profile 与阶段 1B.3 Open3D blocker 仅保留审计。v2 的 NumPy PLY gate、双格式 smoke、100/100 pilot 和 800-candidate 完整性属于历史实验事实；按阶段 1B.5 的 measurement scope 资格规则，v1/v2 均为 `eligible_for_allocation = false`、`allocation_integration_status = ineligible_measurement_scope`。完整重分类见阶段 1B.5 文档和 `results/measurement_asset_status_v1.json`。

## 阶段 2A Python path stage

当前正式 Python path profile 使用同一 CPython 3.10.20 环境中的 `open3d.t.io.read_point_cloud(path)` 与 `Path.read_bytes() + DracoPy.decode(bytes)`。文件 open/read、parse/decode 和 canonical arrays 生成均计入 `d_stage_ms`；缓存策略为 `os_managed_repeated_path_load`。

```powershell
$env:PYTHONPATH='src'
.venv\open3d310\Scripts\python -m pcv_dms_benchmark.cli python-path-stage-pilot `
  --inventory outputs\phase0c_frame1051_inventory.json `
  --sample-plan outputs\phase0c_frame1051_sample_plan.json `
  --data-prep-root E:\Miunaaaa\0-work\code\pcv-stage2-data-prep `
  --out outputs\phase2a_python_path_stage_pilot.json `
  --warmup 2 --samples 5
```

版本化文件：

- `results/python_path_stage_frame1051_measured_summary_v1.json`；
- `results/python_path_stage_frame1051_calibration_v1.json`；
- `handoff/python_path_stage_frame1051_candidate_dms_v1.json`。

该 handoff 覆盖 Longdress frame1051 的 800 个 derived 候选，状态为 `ready_for_provisional_integration`，仅适用于声明的 Python path profile。C++ 与 JavaScript 环境仍需分别测量，不能复用或混合本结果。
