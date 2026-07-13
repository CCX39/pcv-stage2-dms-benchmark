# pcv-stage2-dms-benchmark

本项目用于准备 Stage2 allocation 所需的候选级端侧处理耗时 `d_ms` benchmark。`d_ms` 描述一个传输候选在固定目标运行环境中的 CPU 侧解析或解码成本；它不是文件大小、网络下载时间，也不是端到端播放延迟。

## 项目边界

本仓库服务于硕士课题“轻量级视口感知点云体积视频传输与渲染协同优化”中的 Work1 / Stage2。Stage1 负责输出总预算 `Budget_total`，Stage2 在预算约束下为每个空间 tile 选择传输候选，本质为多选一背包问题。本仓库只准备 Stage2 后续可使用的候选级处理耗时输入，不实现 allocation solver。

与相邻仓库的职责关系如下：

- `pcv-stage2-data-prep`：负责生成和验证 frame 1051 pilot 的 tile binary PLY 与 tile DRC 资产及 metadata；本仓库只读消费其 metadata 语义。
- `pcv-stage2-allocation`：负责 Stage2 候选选择和 proxy pilot；本仓库未来输出的环境专属 `d_ms` 估计应作为 allocation 输入之一，但当前阶段不接入。
- 旧 `PointCloud_Benchmark`：只作为历史实现参考；其计时边界与本仓库冻结的第一版 `d_ms` 边界不同，不能直接复用为新测量契约。

## 正式输入资产范围

本 benchmark 后续正式待测输入只包括：

- Stage2 tile binary PLY；
- Stage2 tile DRC。

原始 8i Longdress raw ASCII full-cloud PLY 只作为来源追溯和 data-prep 输入背景，不进入正式 `d_ms` 测量、抽样或拟合样本集。

## 运行环境

后续计划分别建立三类独立测量环境：

- `cpp_native_windows_x64`；
- `python_windows_x64`；
- `js_worker_browser_windows_x64`。

三种环境不得混合为同一个 `d_ms`。每次 Stage2 实验只能选择一个明确环境配置，并使用该环境对应的候选级处理耗时估计值。阶段 1A 已固定 Python pilot 的实际运行时与后端；C++、JavaScript 以及未来正式测量环境仍需分别冻结。

## 已冻结的第一版测量边界

第一版 `d_ms` 的推荐边界是：候选文件完整内容已经驻留于内存后，从调用该候选对应的 PLY 解析或 DRC 解码逻辑开始，到得到统一、独立拥有、CPU 侧可供后续渲染或几何处理使用的点云数据结构为止的 wall-clock 处理耗时。

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

阶段 1A 已生成 Longdress frame 1051 的 Python 直接测量 pilot；阶段 1B 已拟合 provisional PLY / DRC 模型，并为 frame1051 全部候选生成 `derived d_hat_ms` handoff。allocation 仓库尚未修改。

## 阶段文档

- [d_ms 测量契约](docs/MEASUREMENT_CONTRACT.zh-CN.md)：冻结第一版 `d_ms` 定义、计时边界、输入资产范围和 provenance 语义。
- [阶段 0B 运行环境、采样计划与记录格式](docs/PHASE0B_RUNTIME_SAMPLING_AND_RECORD_PLAN.zh-CN.md)：记录三类运行环境候选配置、Longdress pilot 抽样路线、三类记录字段草案和 allocation join 原则。
- [阶段 0C 候选清单与抽样骨架](docs/PHASE0C_METADATA_INVENTORY_AND_SAMPLING.zh-CN.md)：记录 metadata inventory adapter、sampling planner、CLI、测试和真实 metadata 只读验证结果。
- [阶段 1A Python pilot](docs/PHASE1A_PYTHON_PILOT.zh-CN.md)：记录 Python 进程内 PLY / DRC 后端、真实 smoke、100-candidate pilot 与结果适用边界。
- [阶段 1B Python 标定与交付](docs/PHASE1B_PYTHON_CALIBRATION_AND_HANDOFF.zh-CN.md)：记录 pilot 审查、按 tile 分组验证、模型比较、公式、指标与 provisional handoff 限制。
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

handoff 是由单帧、5 个测量 tile 标定模型生成的 `derived` provisional 数据，不是 800 个候选逐个直接 measured 的结果，也不具备最终模型资格。
