# 阶段 0B 运行环境、采样计划与记录格式

本文档记录阶段 0B 的收敛结果：运行环境候选配置、第一版 Longdress pilot 数据路线、抽样原则、记录格式草案和与 allocation 的 join 原则。本阶段不实现测量代码，不安装依赖，不运行 benchmark，不产生任何 `d_ms` 数值。

## 1. 阶段 0B 目的

阶段 0B 只做三类计划冻结：

- 确认 C++、Python、JavaScript Worker 三类目标环境的候选运行配置；
- 冻结第一版 Longdress pilot 的测量样本路线；
- 定义后续直接测量记录、模型标定记录和候选级 derived 估计记录的字段草案。

本阶段不创建 parser、runner、schema、配置工程、测试工程或 allocation 输入文件。

## 2. 三类运行环境候选配置

### 2.1 C++ 环境

计划用途：

- 建立 native CPU 侧 PLY parse / DRC decode 处理耗时基线；
- 为 Stage2 allocation 提供 `cpp_native_windows_x64` 环境下的候选级 `d_hat_ms`。

候选计时 API：

- 第一候选为 `std::chrono::steady_clock`；
- 后续应确认计时范围只覆盖“内存中 payload -> 统一 CPU 点云结构”，不包含磁盘 open/read/stat。

可参考旧 `PointCloud_Benchmark` 的内容：

- C++ binary PLY header 与 payload 读取思路；
- Draco C++ library 的 decode 与 attribute extraction 思路；
- 异常处理和基本输出字段组织。

旧仓库不能直接复用的原因：

- 旧 C++ parser 的计时从 `parse(filepath)` 开始，包含 `std::ifstream` open/read；
- 旧输出以平均值和 CSV pipeline 为主，未冻结本项目要求的 warmup、raw samples、p50、p95、stddev 等记录；
- 旧输入组织不是 Stage2 tile binary PLY / tile DRC metadata 驱动的候选级流程。

后续待确认：

- compiler，例如 MSVC `cl` 或 MinGW `g++`；
- Draco C++ library 获取方式、版本和构建方式；
- CMake 或其他构建方式；
- 运行时版本、编译选项、CPU 与系统负载控制；
- 是否预热 Draco runtime 以及如何排除一次性初始化成本。

### 2.2 Python 环境

计划用途：

- 建立 Python runtime 下的 PLY parse / DRC decode 处理耗时估计；
- 为使用 Python 数据处理或实验流程的 Stage2 输入准备环境专属 `d_hat_ms`。

候选计时 API：

- 第一候选为 `time.perf_counter()`；
- 后续应明确 raw bytes 或 memory buffer 如何传入 parser / decoder，以排除磁盘读取。

可能涉及的库：

- Open3D 可作为 PLY 读取候选库；
- DracoPy 可作为 DRC 解码候选库；
- 也可在后续比较其他库或自写最小解析逻辑。

当前阶段不得假装依赖已经冻结。Python 结果受解释器版本、库实现、数组布局和内存分配策略影响，不得与 C++ 或 JavaScript Worker 的 `d_ms` 混用。

后续待确认：

- Python 版本与环境管理方式；
- Open3D、DracoPy 或其他库版本；
- 是否需要把 parser 输出显式整理为 `positions: float32[N, 3]` 与 `colors: uint8[N, 3]`；
- warmup、GC 控制、异常处理和离群值策略。

### 2.3 JavaScript Worker 环境

计划用途：

- 建立浏览器 Worker 内 PLY parse / DRC decode 到 TypedArray 的处理耗时估计；
- 为 JS Worker 播放路径或浏览器端 Stage2 实验提供环境专属 `d_hat_ms`。

候选计时 API：

- 第一候选为 `performance.now()`；
- 后续应确认计时点放在 Worker 内 payload 已可访问之后。

参考文件：

- `reference/Decode_Worker.js`。

第一版 JS `d_ms` 边界：

```text
payload 已在 Worker 可访问的 ArrayBuffer 中
-> PLY parse 或 DRC decode
-> positions / colors TypedArray 已生成
```

明确不计入：

- Worker 启动；
- 主线程与 Worker 之间的 `postMessage`；
- Worker 返回主线程的消息传输；
- 主线程 Three.js geometry 创建；
- GPU upload；
- 首帧渲染或屏幕呈现。

`reference/Decode_Worker.js` 当前还会计算并返回 normals。第一版统一 CPU 点云结构只冻结 positions 与 colors，normals 是否纳入未来 JS `d_ms` 仍为 pending。

后续待确认：

- 浏览器版本；
- Three.js / `PLYLoader` / `DRACOLoader` 版本；
- Draco WASM 或 JS decoder 版本；
- decoder path、runtime 初始化和缓存策略；
- 是否复用 Worker 或每轮新建 Worker，第一版推荐复用 Worker 并排除 Worker 启动。

## 3. 本机环境探测结果

以下只是阶段 0B 的只读环境探测，不代表正式依赖冻结：

| 命令 | 当前结果 |
| --- | --- |
| `python --version` | `Python 3.13.12` |
| `where python` | `C:\Users\admin\miniconda3\python.exe`; `C:\Users\admin\AppData\Local\Programs\Python\Python313\python.exe`; `C:\Users\admin\AppData\Local\Microsoft\WindowsApps\python.exe` |
| `node --version` | `v22.11.0` |
| `where node` | `C:\Program Files\nodejs\node.exe` |
| `where cl` | 未找到 |
| `where g++` | `C:\mingw64\bin\g++.exe` |
| `where cmake` | `C:\Program Files\CMake\bin\cmake.exe` |

正式测量前仍需冻结具体版本、依赖、构建方式、浏览器环境和计时方法。

## 4. 第一版 Longdress pilot 数据路线

研究路线分两部分：

第一部分先使用 Longdress 数据集快速给出第一版结果，为 `pcv-stage2-allocation` 实验提供可用的环境专属 `d_hat_ms` 输入。

第二部分未来扩展到其他数据集，用于验证模型泛化性和修正误差。

当前原则：

- 正式测量输入仍只允许 Stage2 tile binary PLY 和 Stage2 tile DRC；
- raw ASCII full-cloud PLY 只作为来源背景；
- 当前 `pcv-stage2-data-prep` 已有 frame 1051 G128 tile binary PLY 和 DRC corpus，可作为第一版最快路径；
- 若未来要使用 Longdress 多帧样本，需要单独决定由 data-prep 生成多帧 tile assets，还是在本 benchmark 仓库中生成本地临时样本；
- 当前阶段不生成多帧样本；
- 若未来生成本地临时样本，必须保存在 ignored 目录，并明确 provenance，不能伪装为 data-prep 已发布资产；
- 低 PDL 生成应尽量沿用 tile-local、嵌套式降采样思路，不要求随机种子与 data-prep 完全一致。

本阶段只做路径与文件名级别确认，不读取 raw PLY 大文件内容。

## 5. 第一版抽样原则

后续抽样应覆盖：

- PLY 与 DRC 两种表示；
- 不同 `point_count` 区间；
- 不同 `file_size_bytes` 区间；
- `PDL = 0.2 / 0.4 / 0.6 / 0.8 / 1.0`；
- DRC `qp = 8 / 10 / 12`；
- 不同 tile 稀疏程度；
- 避免只抽取很小或很大的 tile。

对 PLY，`point_count` 很可能是主要解释变量，`file_size_bytes` 可作为交叉验证字段。对 DRC，不能只依赖 `file_size_bytes`，也不能只依赖 `point_count`；`qp`、decoded point count、码流大小都可能影响耗时。

第一版模型应优先采用简单、可解释、可验证误差的形式。不应为了拟合好看而直接引入复杂黑箱模型。留出验证比单纯追求 R² 更重要，验证误差应记录到 calibrated record，并传递给 derived record 的误差说明。

## 6. 记录格式规划

本阶段不创建 JSON schema 文件，只定义字段草案。

### 6.1 直接测量记录 measured record

至少包括：

- `measurement_id`
- `environment_id`
- `representation`
- `dataset_id`
- `frame_id`
- `grid_profile_id`
- `tile_id`
- `candidate_id` 或 candidate identity fields
- `source_pdl` / `pdl_ratio`
- `file_format`
- `codec`
- `codec_params`
- `asset_ref`
- `artifact_sha256`
- `point_count`
- `file_size_bytes`
- `timer_api`
- `runtime_versions`
- `warmup_count`
- `sample_count`
- `raw_samples_ms`
- `p50`
- `mean`
- `p95`
- `stddev`
- `status`
- `warning_codes`
- `provenance = measured`

### 6.2 模型标定记录 calibrated record

至少包括：

- `calibration_id`
- `environment_id`
- `representation`
- `input_measurement_ids`
- `feature_set`
- `model_family`
- `fit_parameters`
- `validation_protocol`
- `error_metrics`
- `applicable_candidate_scope`
- `limitations`
- `provenance = calibrated`

### 6.3 候选级估计记录 derived record

至少包括：

- `environment_id`
- candidate identity fields
- `candidate_metadata_snapshot`
- `calibration_id`
- `d_hat_ms`
- `statistic_policy`
- `prediction_error_summary` 或 `model_error_reference`
- `provenance = derived`
- `limitations`

derived record 不是逐候选直接 measured 结果。它必须能追溯到 calibrated record，并明确模型适用范围和误差说明。

## 7. 与 allocation 的 join 原则

后续与 allocation 对齐时不能依赖候选数组位置，应使用稳定字段组合：

- `dataset_id`
- `frame_id`
- `grid_profile_id`
- `tile_id`
- `candidate_id`
- `representation` / `file_format` / `codec`
- `source_pdl` / `pdl_ratio`
- `qp`
- `cl`
- point-cloud mode
- `asset_ref`
- artifact hash

`r_bytes` 是文件本体字节数，仍来自 data-prep / allocation metadata；`d_hat_ms` 是 benchmark 产物。二者语义不同，不能互相替代，也不能从其中一个直接推断另一个。

## 8. 当前不做事项

阶段 0B 明确不做：

- 不实现任何 C++、Python、JavaScript benchmark 代码；
- 不创建 `src/`、`tests/`、`scripts/`、`schemas/`、`configs/`；
- 不创建 `CMakeLists.txt`、`package.json`、`pyproject.toml`、`requirements.txt`；
- 不安装依赖；
- 不运行真实 benchmark；
- 不读取或批量遍历 PLY / DRC 大文件内容；
- 不复制、移动、生成、重新编码任何点云资产；
- 不修改外部仓库；
- 不修改 `reference/Decode_Worker.js`；
- 不创建任何 `d_ms` 测量结果文件；
- 不创建 allocation 输入文件。

## 9. 阶段 0C 衔接

阶段 0C 已在阶段 0B 的计划基础上新增 metadata-only 候选清单适配器与抽样计划骨架，详见：

```text
docs/PHASE0C_METADATA_INVENTORY_AND_SAMPLING.zh-CN.md
```

该阶段只生成候选清单和抽样计划，不进行 PLY / DRC 内容解析、解码或 `d_ms` 测量。
