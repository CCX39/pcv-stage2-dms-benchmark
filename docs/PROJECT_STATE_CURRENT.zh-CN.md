# 当前项目状态

更新日期：2026-07-06。本文档用于阶段 0A 之后的接力，记录本机只读审查证据、已冻结契约、未冻结事项和当前仓库状态。

## 1. 项目定位

本仓库位于 Stage2 allocation 与 data-prep 之间，用于准备候选级端侧处理耗时 `d_ms` benchmark。当前目标是冻结测量语义、输入资产范围、运行环境原则、数据来源语义和后续对接边界。

本阶段没有实现代码、没有测量结果、没有候选级 `d_ms` 数据表、没有耗时模型、没有 allocation 输入文件。

## 2. Git 初始状态与本轮提交

阶段 0A 开始时，当前目录没有 `.git`，仅有研究者手动创建的 `reference/Decode_Worker.js`。本轮已执行 `git init -b master`，并配置远程：

```text
https://github.com/CCX39/pcv-stage2-dms-benchmark.git
```

本轮提交主题为：

```text
docs: establish d_ms benchmark baseline
```

未执行 `git push`。

## 3. 阶段 0A 已完成事项

- 初始化当前 benchmark 仓库；
- 添加最小 `.gitignore`；
- 创建中文 README；
- 创建 `docs/MEASUREMENT_CONTRACT.zh-CN.md`；
- 创建本状态文档；
- 只读审查 `pcv-stage2-data-prep`、`pcv-stage2-allocation`、旧 `PointCloud_Benchmark` 与 `reference/Decode_Worker.js`；
- 记录 `reference/Decode_Worker.js` 的 SHA-256；
- 明确本阶段未做任何实现、测量、抽样、拟合或 allocation 接入。

## 4. 只读审查对象与发现

### 4.1 pcv-stage2-data-prep

本机路径：

```text
E:\Miunaaaa\0-work\code\pcv-stage2-data-prep
```

本机 HEAD：

```text
8473226f653cac1ed2be4c9be5287f6ff23de08b
```

Git 状态为干净：`## main...origin/main`。

关键 evidence：

- `configs/pilot_grid_profile.longdress_1051_g128_raw_v1.json`；
- `configs/pilot_sampling_profile.longdress_1051_g128_tilelocal_pdl5_v1.json`；
- `configs/pilot_drc_corpus.longdress_1051_g128_pdl5_qp3_cl10_v1.json`；
- `artifacts/pilot_1051_g128_tilelocal_pdl5_v1/generation_manifest.json`；
- `artifacts/pilot_1051_g128_tilelocal_pdl5_v1/frame_1051_tile_index.json`；
- `artifacts/pilot_1051_g128_drc_pdl5_qp3_cl10_v1/generation_manifest.json`；
- `artifacts/pilot_1051_g128_drc_pdl5_qp3_cl10_v1/generation_summary.json`；
- `artifacts/pilot_1051_g128_drc_pdl5_qp3_cl10_v1/validation_report.json`；
- `docs/DATA_PREP_CONTRACT.zh-CN.md`；
- `docs/PILOT_MULTIPDL_BINARY_ASSETS_CURRENT.zh-CN.md`；
- `docs/PILOT_DRC_CORPUS_CURRENT.zh-CN.md`。

发现摘要：

- frame 1051 pilot 的 Stage2 tile binary PLY metadata 位于 `artifacts/pilot_1051_g128_tilelocal_pdl5_v1/`，核心索引是 `frame_1051_tile_index.json`。
- frame 1051 pilot 的 DRC corpus metadata 位于 `artifacts/pilot_1051_g128_drc_pdl5_qp3_cl10_v1/`，核心 manifest 是 `generation_manifest.json`。
- tile binary PLY root 记录 `dataset_id`、`frame_id`、`grid_profile_id`、`tile_id`、`target_pdl`、`source_point_count`、`retained_point_count`、`actual_retained_ratio`、`relative_path`、`file_size_bytes`、`sha256` 与 `provenance_kind`。
- DRC manifest 记录 `variant_id`、`tile_id`、`source_pdl`、`codec_id`、`point_cloud_flag`、`compression_level`、`qp`、source PLY relpath/hash/size/point count、DRC relpath/hash/size、encoder/decoder path/hash、encoder command argv、basic decode-integrity 结果与 decoded schema 字段。
- DRC corpus summary 显示 frame 1051 pilot 覆盖 40 个非空 tile、5 个 source_pdl、3 个 qp，共 600 个 DRC variants；对应 tile binary PLY 为 200 个候选资产。
- 当前 active DRC profile 与用户给定契约一致：`-point_cloud` 显式传入，`-cl 10` 显式固定，`-qp` 取当前三档；`-qc`、`-qg` 等未显式传入。
- data-prep 的 decode-integrity validation 是资产完整性检查，不是 target-side `d_ms`。

可作为 future benchmark 对齐字段：

- `dataset_id`；
- `frame_id`；
- `grid_profile_id`；
- `tile_id`；
- `target_pdl` / `source_pdl` / `pdl_ratio`；
- `file_format` / `codec_id`；
- `qp`；
- `compression_level` / `cl`；
- point-cloud mode；
- `relative_path` / `asset_ref`；
- `file_size_bytes`；
- `point_count` / `source_point_count` / `retained_point_count`；
- `sha256`；
- `provenance_kind`；
- data-prep profile id 与 manifest hash。

### 4.2 pcv-stage2-allocation

本机路径：

```text
E:\Miunaaaa\0-work\code\pcv-stage2-allocation
```

本机 HEAD：

```text
5870ccceb92598c3b66cffffe3adfa386cfde618
```

Git 状态为干净：`## master...origin/master`。

关键 evidence：

- `src/pcv_stage2/frame1051_metadata_bridge.py`；
- `schemas/stage2_input.schema.json`；
- `configs/frame1051_fullbody_proxy_dms_sensitivity_v1.json`；
- `configs/frame1051_integrated_proxy_mainline_v1.json`；
- `README.zh-CN.md`；
- `docs/IMPLEMENTATION_STATE_CURRENT.zh-CN.md`；
- `docs/manual_review_checklist.zh-CN.md`。

发现摘要：

- 当前真实候选 metadata bridge 位于 `src/pcv_stage2/frame1051_metadata_bridge.py`。
- bridge 只读消费 data-prep 的 profile、manifest、tile index 和 validation report，构建 `frame1051_candidate_metadata_catalog`。
- catalog 自身声明 `solver_ready = false`，不是正式 `Stage2Input`。
- PLY candidate identity 形如 `ply__pdl_*`，DRC candidate identity 形如 `drc__pdl_*__qp_*__cl_10`。
- `r_bytes` 来自候选文件本体字节数，provenance 为 `measured`，但不是端到端网络开销。
- `d_ms_status` 与 `q_base_status` 在真实 catalog 中保持 `pending`。
- allocation 的 proxy pilot 会按 candidate kind 注入固定 proxy `d_ms`，但这些值只是 solver behavior sensitivity 用的 proxy，不是 target-side measured benchmark，也不是逐 tile 测量。
- 当前 PDL lookup 使用 `candidate.pdl_ratio <= pdl_max_dist` 的 cap 语义，来源是 PLY nested-PDL calibration，不是 DRC-aware quality measurement。

后续 benchmark 结果与 allocation join 时，应使用稳定 metadata 组合校验：`dataset_id`、`frame_id`、`grid_profile_id`、`tile_id`、`candidate_id`、`file_format`、`codec`、`codec_params`、`source_pdl` / `pdl_ratio`、`qp`、`cl`、`asset_ref` 与 hash。不得依赖候选数组顺序。

### 4.3 旧 PointCloud_Benchmark

本机路径：

```text
E:\Miunaaaa\0-work\code\PointCloud_Benchmark
```

本机 HEAD：

```text
cb3a1975464c9d26cccff9861943e394f10aada3
```

Git 状态含既有未跟踪文件：

```text
## main...origin/main
?? scripts/plot_time_vs_point_count_filtered.py
```

本轮未修改该仓库。

关键 evidence：

- `src/main.cpp`；
- `src/parser/PlyParser.cpp`；
- `src/parser/DrcParser.cpp`；
- `src/include/Timer.hpp`；
- `src/include/PointCloudData.hpp`；
- `scripts/benchmark_python.py`；
- `scripts/run_benchmark.py`；
- `requirements.txt`。

发现摘要：

- C++ PLY parser 的 `Timer` 从 `PlyParser::parse(filepath)` 进入即开始，随后执行 `std::ifstream` open、header 读取、binary payload 读取和结构整理；因此包含磁盘 open/read。
- C++ DRC parser 的 `Timer` 从 `DrcParser::parse(filepath)` 进入即开始，随后执行 `std::ifstream` open/read、Draco decode 和属性提取；因此包含磁盘 open/read。
- C++ 使用 Draco C++ library；PLY parser 是项目内的 binary PLY 读取实现。
- Python PLY 使用 Open3D Tensor API `o3d.t.io.read_point_cloud`；Python DRC 使用 `Path.read_bytes()` 加 `DracoPy.decode`，因此 Python 计时也包含文件读取。
- `scripts/run_benchmark.py` 支持重复运行并求平均值，记录 wall-clock、CPU、memory 与 CSV 输出；没有阶段 0A 契约要求的 warmup、p50、p95、stddev 完整统计冻结。
- 旧仓库可参考 parser 路径、异常处理和结果字段，但其计时边界、输入组织和输出格式不能直接复用为本项目第一版 `d_ms`。

### 4.4 reference/Decode_Worker.js

本机路径：

```text
E:\Miunaaaa\0-work\code\pcv-stage2-dms-benchmark\reference\Decode_Worker.js
```

SHA-256：

```text
0747B51E9983E59ACC5E911047AE7EBC71213303A60EC7B0548329101775E56C
```

发现摘要：

- Worker 通过 `self.onmessage` 接收 `data`、`cellKey`、`cellId`、`frameId` 与 `transMode`。
- PLY 路径调用 `self.parsePLY(...)`，内部确认 `ArrayBuffer`，必要时从 `Uint8Array` 转换，然后使用 Three.js `PLYLoader.parse`。
- DRC 路径调用 `self.decodeDRC(...)`，内部确认 `ArrayBuffer`，构造 `DRACOLoader`，设置 decoder path 与 WASM config，然后调用 `dracoLoader.parse`。
- 两条路径都返回 positions、colors 和 normals，并把 positions/colors/normals 的 buffer 作为 transferable object 发回主线程。
- 当前文件内的 `performance.now()` 计时覆盖了 parse/decode 路径内的一些工作，但还包括 normals 计算；阶段 0A 的统一 CPU 点云结构只冻结 positions 与 colors，normals 是否纳入后续 JS `d_ms` 未冻结。
- 未来 JS `d_ms` 边界内应包含 payload 已在 Worker 可访问 `ArrayBuffer` 后的 PLY parse 或 DRC decode、必要属性提取和 TypedArray 生成。
- 未来 JS `d_ms` 边界外应排除 Worker 启动、主线程到 Worker 的 `postMessage`、Worker 返回主线程的消息传输、主线程 geometry 创建与 GPU upload。
- 本轮未重构、未优化、未复制、未修改该文件。

## 5. 已确认、已冻结的决策

- `d_ms` 是固定运行环境中的候选级 CPU 侧处理耗时，不是文件大小、下载时间或端到端延迟。
- 第一版测量边界从“候选文件完整内容已经驻留内存后调用解析/解码逻辑”开始，到“统一 CPU 点云结构生成”为止。
- 统一 CPU 点云结构建议为 `positions: float32[N, 3]` 与 `colors: uint8[N, 3]`。
- C++、Python、JavaScript Worker 三类环境独立建模，不混为同一个 `d_ms`。
- 第一版采用单候选、无已解码对象缓存、C++ / Python 默认单线程、单 Worker 内单候选处理的基线。
- 正式待测资产仅为 Stage2 tile binary PLY 与 Stage2 tile DRC。
- raw ASCII full-cloud PLY 只作为来源追溯与 data-prep 输入背景。
- 当前 Longdress frame 1051 pilot DRC active profile 只冻结为本 pilot 的事实，不是永久 Stage2 profile。
- provenance 必须区分 `measured`、`calibrated`、`derived`、`proxy`、`synthetic`。

## 6. 尚未冻结的决策

- 各环境的 compiler / interpreter / browser / library / Draco runtime 版本；
- C++、Python、JavaScript 的正式计时 API 与 runtime 初始化排除方式；
- warmup 次数、正式 sample 次数、异常处理和离群值策略；
- Stage2 最终使用 `p50`、`mean`、`p95` 或其他统计量；
- 覆盖性抽样规则；
- 模型形式、feature set 与验证协议；
- 是否纳入 normals 或其他属性；
- benchmark 输出 schema 与 allocation 正式 join schema；
- 多帧或全序列扩展策略。

## 7. 当前可用输入资产线索

原始 Longdress raw ASCII full-cloud PLY 路径存在：

```text
E:\Miunaaaa\0-work\data\8i\longdress\longdress\Ply
```

该路径下可见 `longdress_vox10_1051.ply` 等原始帧文件。本阶段只做目录级确认和少量文件名查看，未读取原始 PLY 内容。

data-prep 当前可用的正式候选资产线索：

- Stage2 tile binary PLY root：`artifacts/pilot_1051_g128_tilelocal_pdl5_v1/`；
- Stage2 tile DRC root：`artifacts/pilot_1051_g128_drc_pdl5_qp3_cl10_v1/`；
- 这些路径记录在 data-prep repo 的 metadata 中，是本机审查线索；未来 benchmark 运行时配置不应硬编码本机绝对路径。

## 8. 当前没有的内容

当前仓库没有：

- `src/`；
- `tests/`；
- `scripts/`；
- `schemas/`；
- `configs/`；
- `CMakeLists.txt`；
- `package.json`；
- `pyproject.toml`；
- `requirements.txt`；
- benchmark runner；
- PLY / DRC parser；
- 任何测量结果；
- 任何 `d_ms` 数据表；
- 任何拟合模型；
- 任何 allocation 接入逻辑。

## 9. 下一阶段建议

建议下一阶段先冻结每个目标环境的 runtime 与计时 API，然后定义只读 benchmark 输入清单 schema、直接测量记录 schema、模型标定记录 schema 和候选级 derived 估计记录 schema。实现前应继续遵守：不把 data-prep validation 当成 `d_ms`，不把 allocation proxy 当成 measured，不把 raw full-cloud PLY 当成正式 benchmark 输入。

## 10. 风险与注意事项

- data-prep manifest 中记录的 Draco executable 行为只证明当前 pilot 的显式命令参数；未显式参数不得推断为固定取值。
- 旧 benchmark 的计时包含磁盘读取，与阶段 0A 冻结边界不同。
- JavaScript Worker 参考文件当前包含 normals 计算和每次构造 `DRACOLoader` 的行为；这些都不是未来 JS benchmark 的已冻结实现。
- allocation 当前 proxy `d_ms` 只能解释 solver sensitivity pilot，不能作为真实 target-side benchmark。
- 文档可记录本机路径用于人工审查，但未来运行时代码或配置不得硬编码这些绝对路径。
