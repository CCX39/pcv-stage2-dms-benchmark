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

三种环境不得混合为同一个 `d_ms`。每次 Stage2 实验只能选择一个明确环境配置，并使用该环境对应的候选级处理耗时估计值。具体编译器、Python 版本、库版本、浏览器版本、Draco runtime 与计时 API 均未冻结。

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

当前阶段不拟合函数，不产生任何 `d_hat_ms` 数值，也不生成 benchmark 代码。

## 阶段文档

- [d_ms 测量契约](docs/MEASUREMENT_CONTRACT.zh-CN.md)：冻结第一版 `d_ms` 定义、计时边界、输入资产范围和 provenance 语义。
- [阶段 0B 运行环境、采样计划与记录格式](docs/PHASE0B_RUNTIME_SAMPLING_AND_RECORD_PLAN.zh-CN.md)：记录三类运行环境候选配置、Longdress pilot 抽样路线、三类记录字段草案和 allocation join 原则。
- [当前项目状态](docs/PROJECT_STATE_CURRENT.zh-CN.md)：记录本机仓库状态、只读审查发现、当前已冻结与未冻结事项。

## Longdress pilot 路线

第一版结果优先使用 Longdress 数据集快速形成环境专属 `d_hat_ms` 输入，为 `pcv-stage2-allocation` 实验提供可用依据。最快路径是从 `pcv-stage2-data-prep` 已有的 frame 1051 G128 tile binary PLY 与 DRC corpus metadata 出发，设计覆盖性抽样和直接测量计划。

后续再扩展到其他数据集，用于验证模型泛化性和修正误差。若未来需要 Longdress 多帧样本，应单独决定由 data-prep 生成多帧 tile assets，还是由本 benchmark 仓库生成 ignored 本地临时样本；当前阶段不生成任何样本。

## reference/Decode_Worker.js

`reference/Decode_Worker.js` 是 JavaScript Worker 处理路径的只读参考。它用于帮助界定未来 JS Worker 环境中的 PLY / DRC 路径和边界，不是本仓库要修改、优化或复制的实现来源。阶段 0A 与 0B 均记录其 SHA-256，并确认本轮未修改。

## 目录职责

- `reference/`：只读参考材料；当前仅保留研究者手动放入的 `Decode_Worker.js`。
- `docs/`：中文契约、计划与当前状态文档。
- `.gitignore`：忽略未来可能产生的大型输出、构建产物、环境目录和本地配置。

当前没有 `src/`、`tests/`、`scripts/`、`schemas/` 或 `configs/`，也没有 CMake、Python、Node.js、WASM、测试或绘图工程。
