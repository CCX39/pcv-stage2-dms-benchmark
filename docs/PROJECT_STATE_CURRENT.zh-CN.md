# 当前项目状态

更新日期：2026-07-10。本文档用于阶段 0B 之后的接力，记录本机真实仓库状态、只读审查证据、已冻结契约、运行环境候选配置、Longdress pilot 路线和仍未冻结事项。

## 1. 当前项目定位

本仓库位于 Stage2 allocation 与 data-prep 之间，用于准备候选级端侧处理耗时 `d_ms` benchmark。阶段 0A 已冻结第一版 `d_ms` 语义与边界；阶段 0B 进一步冻结运行环境候选配置、Longdress pilot 抽样路线和三类记录格式草案。

当前仍没有实现代码、没有测量结果、没有候选级 `d_ms` 数据表、没有耗时模型、没有 allocation 输入文件。

## 2. Git 状态

本机仓库路径：

```text
E:\Miunaaaa\0-work\code\pcv-stage2-dms-benchmark
```

当前真实分支与 upstream：

```text
## main...origin/main
```

当前远程：

```text
origin  https://github.com/CCX39/pcv-stage2-dms-benchmark.git (fetch)
origin  https://github.com/CCX39/pcv-stage2-dms-benchmark.git (push)
```

阶段 0A 完成后，本地分支已统一为 `main` 并跟踪 `origin/main`。阶段 0B 开始时 HEAD 为：

```text
d0b9a9b docs: establish d_ms benchmark baseline
```

阶段 0B 本轮提交主题为：

```text
docs: define runtime sampling and record plan
```

本轮不执行 `git push`，因此提交后预期 `git status -sb` 显示本地相对 `origin/main` ahead。

## 3. 阶段 0B 已完成事项

- 确认当前分支为 `main`，upstream 为 `origin/main`；
- 确认 `.gitignore` 已是一行一个规则，无需修正；
- 新增 `docs/PHASE0B_RUNTIME_SAMPLING_AND_RECORD_PLAN.zh-CN.md`；
- 小幅更新 README，加入阶段 0B 文档入口和 Longdress pilot 路线摘要；
- 小幅更新测量契约，加入阶段 0B 计划文档引用；
- 更新本状态文档；
- 只读探测本机 Python、Node、C++ 工具链候选可见状态；
- 只读确认外部仓库状态和 Longdress 原始路径存在性；
- 确认 `reference/Decode_Worker.js` SHA-256 未变化。

## 4. .gitignore 状态

`.gitignore` 当前为一行一个规则，包含：

```text
__pycache__/
*.py[cod]
.venv/
venv/
node_modules/
dist/
build/
out/
outputs/
artifacts/
coverage/
*.log
.env
.env.*
local/
```

未忽略 `reference/Decode_Worker.js`、`README.zh-CN.md` 或 `docs/`。本轮没有创建 `outputs/`、`artifacts/`、`local/` 等目录。

## 5. 运行环境探测结果

以下只是阶段 0B 的只读探测，不代表正式依赖冻结：

| 命令 | 当前结果 |
| --- | --- |
| `python --version` | `Python 3.13.12` |
| `where python` | `C:\Users\admin\miniconda3\python.exe`; `C:\Users\admin\AppData\Local\Programs\Python\Python313\python.exe`; `C:\Users\admin\AppData\Local\Microsoft\WindowsApps\python.exe` |
| `node --version` | `v22.11.0` |
| `where node` | `C:\Program Files\nodejs\node.exe` |
| `where cl` | 未找到 |
| `where g++` | `C:\mingw64\bin\g++.exe` |
| `where cmake` | `C:\Program Files\CMake\bin\cmake.exe` |

正式测量前仍需冻结 compiler / interpreter / browser / library / Draco runtime 版本、构建方式、计时 API、warmup 与 sample 策略。

## 6. 阶段 0B 运行环境候选配置摘要

C++：

- 用于 native CPU 侧 PLY parse / DRC decode 基线；
- 候选计时 API 为 `std::chrono::steady_clock`；
- 可参考旧 `PointCloud_Benchmark` 的 C++ parser 与 Draco 调用思路；
- 旧仓库不能直接复用，因为其计时包含磁盘 open/read，且输出统计不满足新契约。

Python：

- 用于 Python runtime 下的环境专属 `d_hat_ms`；
- 候选计时 API 为 `time.perf_counter()`；
- Open3D、DracoPy 或其他库都只是候选，依赖尚未冻结；
- Python 结果受解释器和库实现影响，不得与 C++ 或 JS 混用。

JavaScript Worker：

- 用于浏览器 Worker 内 payload 已可访问后的 parse/decode 到 TypedArray 生成；
- 候选计时 API 为 `performance.now()`；
- 参考 `reference/Decode_Worker.js`；
- Worker 启动、`postMessage`、主线程 geometry、GPU upload 不计入；
- normals 是否纳入仍为 pending。

## 7. Longdress pilot 与多数据集路线

第一部分先使用 Longdress 数据集快速给出第一版结果，为 `pcv-stage2-allocation` 实验提供可用的环境专属 `d_hat_ms` 输入。

第二部分未来扩展到其他数据集，用于验证模型泛化性和修正误差。

当前最快路径是使用 `pcv-stage2-data-prep` 已有 frame 1051 G128 tile binary PLY 和 DRC corpus metadata 设计覆盖性抽样。正式测量输入仍只允许 Stage2 tile binary PLY 和 Stage2 tile DRC；raw ASCII full-cloud PLY 只作为来源背景。

若未来使用 Longdress 多帧样本，需要单独决定由 data-prep 生成多帧 tile assets，还是在本 benchmark 仓库中生成 ignored 本地临时样本。当前阶段不生成多帧样本。未来若生成本地临时样本，必须明确 provenance，不能伪装为 data-prep 已发布资产。

## 8. 记录格式规划摘要

直接测量记录 `measured record` 至少包含：

- 环境与候选身份：`measurement_id`、`environment_id`、`representation`、`dataset_id`、`frame_id`、`grid_profile_id`、`tile_id`、`candidate_id` 或 candidate identity fields；
- 候选 metadata：`source_pdl` / `pdl_ratio`、`file_format`、`codec`、`codec_params`、`asset_ref`、`artifact_sha256`、`point_count`、`file_size_bytes`；
- 计时与统计：`timer_api`、`runtime_versions`、`warmup_count`、`sample_count`、`raw_samples_ms`、`p50`、`mean`、`p95`、`stddev`；
- 状态与来源：`status`、`warning_codes`、`provenance = measured`。

模型标定记录 `calibrated record` 至少包含 `calibration_id`、`environment_id`、`representation`、`input_measurement_ids`、`feature_set`、`model_family`、`fit_parameters`、`validation_protocol`、`error_metrics`、`applicable_candidate_scope`、`limitations`、`provenance = calibrated`。

候选级估计记录 `derived record` 至少包含 `environment_id`、candidate identity fields、`candidate_metadata_snapshot`、`calibration_id`、`d_hat_ms`、`statistic_policy`、`prediction_error_summary` 或 `model_error_reference`、`provenance = derived`、`limitations`。derived record 不是逐候选直接 measured 结果。

## 9. allocation join 原则

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

`r_bytes` 是文件本体字节数，仍来自 data-prep / allocation metadata；`d_hat_ms` 是 benchmark 产物。二者语义不同。

## 10. 外部仓库只读状态

`pcv-stage2-data-prep`：

```text
HEAD 8473226f653cac1ed2be4c9be5287f6ff23de08b
status ## main...origin/main
```

`pcv-stage2-allocation`：

```text
HEAD 5870ccceb92598c3b66cffffe3adfa386cfde618
status ## master...origin/master
```

旧 `PointCloud_Benchmark`：

```text
HEAD cb3a1975464c9d26cccff9861943e394f10aada3
status ## main...origin/main
       ?? scripts/plot_time_vs_point_count_filtered.py
```

旧 benchmark 的未跟踪脚本是既有状态，本轮未修改。

## 11. 当前可用输入资产线索

原始 Longdress raw ASCII full-cloud PLY 路径存在：

```text
E:\Miunaaaa\0-work\data\8i\longdress\longdress\Ply
```

本轮只做存在性和文件名级别确认，可见 `longdress_vox10_1051.ply` 到 `longdress_vox10_1055.ply` 等文件名，未读取大文件内容。

data-prep 当前可用的正式候选资产线索：

- Stage2 tile binary PLY root：`artifacts/pilot_1051_g128_tilelocal_pdl5_v1/`；
- Stage2 tile DRC root：`artifacts/pilot_1051_g128_drc_pdl5_qp3_cl10_v1/`。

这些路径是本机人工审查线索，未来运行时代码或配置不得硬编码本机绝对路径。

## 12. reference/Decode_Worker.js

SHA-256：

```text
0747B51E9983E59ACC5E911047AE7EBC71213303A60EC7B0548329101775E56C
```

阶段 0A 与阶段 0B 哈希一致。本轮未修改该文件。

## 13. 当前没有的内容

当前仓库没有：

- `src/`
- `tests/`
- `scripts/`
- `schemas/`
- `configs/`
- `CMakeLists.txt`
- `package.json`
- `pyproject.toml`
- `requirements.txt`
- benchmark runner
- PLY / DRC parser
- 任何测量结果
- 任何 `d_ms` 数据表
- 任何拟合模型
- 任何 allocation 接入逻辑
- 任何生成点云资产

## 14. 已冻结事项

- 第一版 `d_ms` 定义与计时边界；
- 三类环境独立建模；
- 正式输入资产仅为 Stage2 tile binary PLY 与 Stage2 tile DRC；
- raw ASCII full-cloud PLY 只作为来源背景；
- 第一版 Longdress pilot 先行、后续多数据集扩展的路线；
- 直接测量、模型标定、候选级 derived 三类记录字段草案；
- allocation join 不依赖候选数组位置。

## 15. 仍未冻结事项

- 具体 compiler / interpreter / browser / library / Draco runtime 版本；
- C++、Python、JavaScript 的正式计时 API 细节和代码实现；
- warmup、sample count、异常处理和离群值策略；
- Stage2 最终使用 `p50`、`mean`、`p95` 或其他统计量；
- 抽样数量和具体候选文件清单；
- 模型形式、feature set 和验证协议；
- 多帧 Longdress 样本由 data-prep 生成还是 benchmark ignored 临时生成；
- 是否纳入 normals 或其他属性；
- benchmark 输出 schema 与 allocation 正式输入 schema。

## 16. 下一阶段建议

下一阶段可以在仍不测量的前提下设计具体 benchmark 输入清单生成规则和测量 runner 接口；或者进入实现前准备，先冻结每个环境的 dependency 版本、构建方式、计时 API 和输出文件布局。进入任何实现前，仍需保持 provenance 区分，避免把 allocation proxy、data-prep validation 或 derived 估计写成 measured。
