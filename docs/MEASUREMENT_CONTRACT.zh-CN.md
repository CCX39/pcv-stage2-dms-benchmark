# d_ms 测量契约

本文档冻结阶段 0A 已确认的 `d_ms` 语义、第一版测量边界、输入资产范围、数据来源语义和后续记录原则。本阶段不实现 PLY / DRC 解析、解码或 benchmark 代码，不产生任何实际测量数值。

## 1. 正式定义

`d_ms` 表示一个 Stage2 传输候选在固定目标运行环境中的 CPU 侧处理成本。它描述候选文件内容已经在内存中之后，解析或解码到统一 CPU 点云结构所需的 wall-clock 处理耗时。

`d_ms` 不等于：

- 文件大小；
- 网络下载时间；
- HTTP、排队、缓存或播放调度时间；
- GPU upload；
- 首帧渲染或屏幕呈现；
- 端到端播放延迟。

后续候选级估计路线为：

```text
d_hat_ms = f(environment, representation, candidate_metadata)
```

其中 `environment` 表示目标运行环境，`representation` 表示候选表示形式，`candidate_metadata` 可包括点数、文件本体字节数、`pdl_ratio`、`qp`、`cl`、格式、属性布局及其他与实际处理成本有关的 metadata。

## 2. 计时起点与终点

第一版推荐边界：

```text
候选文件完整内容已驻留内存
-> 调用该候选对应的 PLY 解析或 DRC 解码逻辑
-> 得到统一、独立拥有、CPU 侧可供后续渲染或几何处理使用的点云数据结构
```

计时起点不是磁盘 open/read/stat，也不是网络下载完成前的任何阶段。计时终点不是 Three.js geometry、GPU buffer 或屏幕呈现，而是 CPU 侧统一点云数据结构已生成。

建议统一 CPU 点云结构（canonical CPU point-cloud representation）为：

```text
positions: float32[N, 3]
colors: uint8[N, 3]
```

后续文档中简称“统一 CPU 点云结构”。

## 3. 计入项

第一版 `d_ms` 计入：

- PLY header 解析；
- binary PLY 的 XYZ / RGB 属性读取；
- DRC 的 Draco 解码；
- DRC 中位置与颜色属性提取；
- 为得到统一 CPU 点云结构所必需的内存分配、属性整理和必要类型转换；
- 每轮测量产生新的解析或解码结果，不使用已解码对象缓存。

## 4. 不计入项

第一版 `d_ms` 不计入：

- 本地磁盘 open/read/stat；
- 文件 hash、manifest 查询、目录扫描；
- 网络下载、HTTP、排队、缓存命中、播放调度；
- GPU upload；
- Three.js `BufferGeometry` 创建；
- 首帧渲染、屏幕呈现；
- data-prep 中的 CLI decode-integrity validation；
- Worker 启动；
- 主线程与 Worker 之间的 `postMessage`；
- Worker 返回主线程的消息传输；
- 日志写盘、结果写盘；
- 其他与单候选解析/解码无直接关系的初始化成本。

Draco runtime 初始化、WASM 模块加载、浏览器缓存状态、Python / C++ 库初始化等属于后续需要冻结的环境细节。第一版测量应避免把一次性初始化成本混入候选级 `d_ms`。

## 5. 三类独立运行环境

后续计划分别建立三类独立测量环境：

- `cpp_native_windows_x64`；
- `python_windows_x64`；
- `js_worker_browser_windows_x64`。

三种环境不得混合为同一个 `d_ms`。后续每次 Stage2 实验只能选定一个明确环境配置，并使用该环境对应的候选处理耗时估计值。

上述名称只是概念性名称。具体编译器、Python 版本、库版本、浏览器版本、Draco runtime、计时 API、CPU governor、系统负载控制与重复测量策略仍未冻结。

## 6. JavaScript Worker 边界

JavaScript Worker 环境的第一版边界理解为：

```text
payload 已在 Worker 可访问的 ArrayBuffer 中
-> PLY parse 或 DRC decode
-> 统一 CPU 点云 TypedArray 已生成
```

不计入 Worker 启动、主线程发送 payload、Worker `postMessage` 返回主线程，也不计入主线程收到结果后的 geometry 创建或 GPU upload。

`reference/Decode_Worker.js` 当前对 PLY 使用 Three.js `PLYLoader.parse(ArrayBuffer)`，对 DRC 使用 `DRACOLoader` 与 WASM decoder。该文件还会计算 normals 并返回 `normals` TypedArray。阶段 0A 的统一 CPU 点云结构仅要求 positions 与 colors；normals 是否纳入未来测量边界仍未冻结。

## 7. 单候选、无缓存、单线程基线

第一版测量基线采用：

- 单候选处理；
- 不使用已解码对象缓存；
- C++ 与 Python 默认单线程；
- JavaScript 采用单个 Worker 内的单候选处理，不测 Worker 启动或消息调度；
- 并行解码、线程池排队、多候选流水线和播放级调度均不属于第一版 `d_ms`。

允许未来通过 warmup 排除一次性 runtime 初始化，但不得把已解码对象缓存用于候选处理本身。

## 8. 输入资产类型

需要明确区分三类资产：

1. raw ASCII full-cloud PLY  
   原始 8i Longdress 全帧 PLY。它只作为来源追溯和 data-prep 输入背景。

2. Stage2 tile binary PLY  
   由 `pcv-stage2-data-prep` 从原始 PLY 按 G128 网格切块生成，使用 `binary_little_endian 1.0`，schema 为 `float x/y/z` 与 `uchar red/green/blue`。XYZ / RGB 数值不应写成经过坐标或颜色重标定；但 tile 切分、ASCII 到 binary 表示转换和低 PDL 嵌套抽样会改变单个资产的点集与文件组织。

3. Stage2 tile DRC  
   由对应 tile binary PLY 生成的 Draco point-cloud artifact。

本 benchmark 的正式待测资产仅为 Stage2 tile binary PLY 与 Stage2 tile DRC。raw ASCII full-cloud PLY 不进入正式 `d_ms` 测量、抽样或拟合样本集。

后续如需构造不同点数的受控样本，应以 Stage2 tile binary PLY 为基础，使用与 data-prep 类似的 tile-local、嵌套式降采样思路，并保留低档位点集是高档位点集子集的基本性质。不要求与 data-prep 使用完全相同的随机种子；若未来生成，必须明确 provenance，不能伪装为 data-prep 既有交付资产。本阶段不生成任何此类样本。

## 9. 当前 DRC active profile

当前 data-prep 的 Longdress frame 1051 pilot active DRC profile 为：

```text
draco_encoder -point_cloud -i <input> -o <output> -cl 10 -qp <8|10|12>
```

已确认含义：

- `-point_cloud`：显式启用 point-cloud mode；
- `-cl 10`：显式固定；
- `-qp ∈ {8, 10, 12}`：当前可变参数。

`-qc`、`-qg` 等参数当前未显式传入。未显式参数的具体行为依赖实际 Draco executable 的默认值，未来正式测量必须记录 executable 版本和运行时环境。

该 DRC profile 只是 Longdress frame 1051 pilot 的当前 active profile，不是通用 Stage2 理论的永久固定 profile。

## 10. 数据来源语义

必须使用以下 provenance 语义：

- `measured`：直接对真实候选样本重复测量得到的耗时统计。
- `calibrated`：由直接测量样本标定得到的环境专属耗时模型、模型参数及其验证结果。
- `derived`：由已标定模型为大量候选推导得到的候选级 `d_hat_ms`。
- `proxy`：具备工程解释但尚未直接测量或标定得到的代理值。
- `synthetic`：用于未来测试或受控验证的人造数据。

不得把 `derived` 的候选级耗时估计写成“逐候选直接测得的真实耗时”。不得把 allocation 中按格式设置的既有 proxy `d_ms` 写成 `measured`。不得把 data-prep 的 CLI decode-integrity validation 写成 target-side `d_ms`。

## 11. 后续最小记录字段

每个直接测量候选至少应保留：

- `measurement_id`；
- `environment_id`；
- `representation`；
- `dataset_id`；
- `frame_id`；
- `grid_profile_id`；
- `tile_id`；
- `candidate_id` 或可稳定重建 candidate identity 的字段；
- `source_pdl` / `pdl_ratio`；
- `file_format`；
- `codec`；
- `codec_params`，例如 `qp`、`cl`、point-cloud mode；
- `asset_ref`；
- `artifact_sha256`；
- `point_count`；
- `file_size_bytes`；
- `sample_count`；
- `warmup_count`；
- `p50`；
- `mean`；
- `p95`；
- `stddev` 或其他离散度指标；
- `timer_api`；
- `runtime_versions`；
- `provenance = measured`。

其中 `p50` 表示第 50 百分位数，即中位数，反映典型单次处理耗时。阶段 0A 不冻结 Stage2 最终应使用 `p50`、`mean` 还是其他统计量；`p50` 是当前优先考虑的典型值候选。

每个模型标定记录至少应保留：

- `calibration_id`；
- `environment_id`；
- `representation`；
- `input_measurement_ids`；
- `feature_set`；
- `model_family`；
- `fit_parameters`；
- `validation_split_or_protocol`；
- `error_metrics`；
- `applicable_candidate_scope`；
- `provenance = calibrated`。

每个候选级估计记录至少应保留：

- `environment_id`；
- `candidate identity`；
- `candidate_metadata_snapshot`；
- `calibration_id`；
- `d_hat_ms`；
- `statistic_policy`；
- `provenance = derived`；
- `limitations`。

## 12. allocation join 原则

后续 benchmark 结果与 allocation 对接时，应优先依赖稳定身份字段，而不是文件排序或候选数组位置。建议 join 口径包括：

- `dataset_id`；
- `frame_id`；
- `grid_profile_id`；
- `tile_id`；
- `representation` / `file_format` / `codec`；
- `source_pdl` 或 `pdl_ratio`；
- 对 DRC 还包括 `qp`、`cl`、point-cloud mode；
- `asset_ref` 与 artifact hash 用于完整性校验。

allocation 中的 `candidate_id` 可以作为候选身份字段，但必须与上述 metadata 一起校验，避免把命名习惯误当成质量、数据量或耗时顺序。

## 13. 当前明确不做

阶段 0A 明确不做：

- 不实现任何 PLY / DRC 解析、解码或 benchmark 代码；
- 不创建 `src/`、`tests/`、`scripts/`、`schemas/`、`configs/` 等实现目录；
- 不创建 CMake、Python、Node.js、浏览器、WASM、测试或绘图工程；
- 不进行真实耗时测量、抽样测量、批量测量或性能比较；
- 不复制、移动、重新生成、重新编码任何 PLY / DRC 大文件；
- 不修改外部仓库；
- 不修改 `reference/Decode_Worker.js`；
- 不创建 allocation 输入、候选级 `d_ms` 数据表、拟合模型或 proxy 替换逻辑。

## 14. 尚未冻结事项

后续需要研究者确认：

- 每个环境的具体 runtime、版本、依赖库和编译 / 解释器配置；
- C++、Python、JavaScript 各自的计时 API；
- Draco executable / runtime 版本记录方式；
- 是否预加载 Draco runtime，以及如何排除一次性初始化成本；
- warmup 次数、正式 sample 次数、异常重试规则和离群值处理；
- Stage2 最终使用 `p50`、`mean`、`p95` 或其他统计量；
- 覆盖性抽样策略和受控样本生成规则；
- 模型形式、特征集合和验证协议；
- allocation 最终输入 schema 与 join 校验策略；
- 是否在后续阶段纳入 normals 或其他属性。

## 15. 阶段 0B 关联计划

阶段 0B 已将运行环境候选配置、Longdress pilot 抽样路线、记录格式草案和 allocation join 原则整理到：

```text
docs/PHASE0B_RUNTIME_SAMPLING_AND_RECORD_PLAN.zh-CN.md
```

该文档不改变本契约中已冻结的 `d_ms` 定义、计时起点、计时终点或输入资产范围。

## 16. 阶段 0C 关联工具

阶段 0C 新增 metadata-only 候选清单适配器与抽样计划骨架，说明见：

```text
docs/PHASE0C_METADATA_INVENTORY_AND_SAMPLING.zh-CN.md
```

这些工具只读取 JSON metadata 并生成 planning 输出，不解析 PLY、不解码 DRC、不产生 `d_ms` 测量值，也不改变本契约中已冻结的测量边界。

## 17. 阶段 1A Python pilot 实例化

阶段 1A 在 `python_windows_x64` 候选环境中完成第一版真实直接测量链路：

- CPython 3.13.0；
- `time.perf_counter_ns` 计时；
- PLY 后端为 `plyfile 1.1.4 + numpy 2.5.1`；
- DRC 后端为进程内 `DracoPy 2.0.0 + numpy 2.5.1`，不调用 decoder CLI；
- 每个候选预热 2 次、正式测量 5 次；
- 第一版统一输出只包含 `positions: float32[N, 3]` 与 `colors: uint8[N, 3]`，normals 不属于本版输出。

该实例化没有改变第 2 至第 4 节的测量边界。真实结果标记为 `measured`，但 `measurement_scope = longdress_frame1051_pilot`、`eligible_for_final_model = false`、`eligible_for_allocation = false`；必须经过后续验证与模型阶段，不能直接作为最终输入。
