# 当前项目状态

更新日期：2026-07-10。本文档用于阶段 0C 之后的接力，记录本机真实仓库状态、当前代码能力、只读验证结果、已冻结事项和仍未冻结事项。

## 1. 当前项目定位

本仓库位于 Stage2 allocation 与 data-prep 之间，用于准备候选级端侧处理耗时 `d_ms` benchmark。阶段 0A 已冻结第一版 `d_ms` 语义与边界；阶段 0B 已冻结运行环境候选配置、Longdress pilot 抽样路线和三类记录格式草案；阶段 0C 新增 metadata-only 候选清单适配器与抽样计划骨架。

当前仍没有 PLY 内容解析、DRC 解码、真实 `d_ms` 测量、耗时模型、measured / calibrated / derived 结果数据或 allocation 接入。

## 2. Git 状态

本机仓库路径：

```text
E:\Miunaaaa\0-work\code\pcv-stage2-dms-benchmark
```

阶段 0C 开始时真实分支与 upstream：

```text
## main...origin/main
```

当前远程：

```text
origin  https://github.com/CCX39/pcv-stage2-dms-benchmark.git (fetch)
origin  https://github.com/CCX39/pcv-stage2-dms-benchmark.git (push)
```

阶段 0C 开始时 HEAD：

```text
046f96d docs: define runtime sampling and record plan
```

阶段 0C 本轮提交主题为：

```text
feat: add metadata inventory and sampling planner
```

本轮不执行 `git push`。

## 3. 阶段 0C 已完成事项

- 新增最小 Python 项目骨架；
- 新增 metadata inventory adapter；
- 新增 sampling plan generator；
- 新增 CLI 子命令 `inventory` 与 `sample-plan`；
- 新增 synthetic JSON fixtures；
- 新增 unittest 覆盖候选规范化、稳定 key、DRC codec params、缺失 metadata warning 和抽样计划覆盖；
- 新增 `docs/PHASE0C_METADATA_INVENTORY_AND_SAMPLING.zh-CN.md`；
- 更新 README、测量契约、阶段 0B 计划文档和当前状态文档；
- 对真实 data-prep frame1051 metadata 做一次只读验证；
- 确认 `reference/Decode_Worker.js` 未变化。

## 4. 新增代码与职责

`src/pcv_dms_benchmark/metadata_inventory.py`：

- 读取 PLY tile index JSON 与 DRC generation manifest JSON；
- 将 PLY / DRC metadata 规范化为统一 candidate record；
- 生成稳定 `candidate_key`，不依赖数组位置；
- 只使用 metadata 中已有的 file size 与 hash 字段；
- 字段缺失时记录 warning 或 `null`，不编造值；
- 不打开 PLY / DRC 文件内容。

`src/pcv_dms_benchmark/sampling_plan.py`：

- 从 inventory 中按 tile 聚合候选；
- 基于 tile 最大 `point_count` 做确定性 bucket selection；
- 对选中 tile 默认保留所有 PLY PDL 与所有 DRC PDL × QP；
- 输出 sampling plan JSON；
- 不进行任何测量。

`src/pcv_dms_benchmark/cli.py`：

- `inventory`：从 data-prep root 或显式 manifest path 生成候选清单；
- `sample-plan`：从候选清单生成抽样计划；
- 输出路径由调用者指定，推荐写入 ignored `outputs/`。

## 5. 候选清单与抽样计划输出语义

inventory 与 sampling plan 都是 `metadata_planning`，不是 measured / calibrated / derived 结果。

candidate record 主要字段包括：

- `dataset_id`
- `frame_id`
- `grid_profile_id`
- `tile_id`
- `candidate_id`
- `candidate_key`
- `representation`
- `file_format`
- `source_pdl`
- `pdl_ratio`
- `codec`
- `codec_profile`
- `codec_params`
- `point_count`
- `file_size_bytes`
- `asset_ref`
- `asset_sha256`
- `source_manifest`
- `provenance`
- `status`
- `warning_codes`

sampling plan 主要字段包括：

- `plan_id`
- `source_inventory`
- `selection_policy`
- `selected_tiles`
- `selected_candidates`
- `coverage_summary`
- `warnings`

`selected_candidates` 引用 `candidate_key` / `candidate_id`，并保留少量摘要字段供人工审查。

## 6. 测试状态

测试命令：

```text
python -m unittest discover
```

结果：

```text
Ran 12 tests
OK
```

测试只依赖 `tests/fixtures/` 下的极小 synthetic JSON，不依赖真实 data-prep 仓库和真实点云文件。

## 7. 真实 metadata 只读验证结果

执行命令：

```powershell
$env:PYTHONPATH='src'
python -m pcv_dms_benchmark.cli inventory --data-prep-root E:\Miunaaaa\0-work\code\pcv-stage2-data-prep --out outputs\phase0c_frame1051_inventory.json
python -m pcv_dms_benchmark.cli sample-plan --inventory outputs\phase0c_frame1051_inventory.json --out outputs\phase0c_frame1051_sample_plan.json --max-tiles 5
```

inventory 摘要：

```text
candidate_count=800
ply_candidate_count=200
drc_candidate_count=600
tile_count=40
```

sample plan 摘要：

```text
selected_tile_count=5
selected_candidate_count=100
ply_candidate_count=25
drc_candidate_count=75
```

验证只读取 JSON metadata，没有读取 PLY / DRC 文件内容。生成文件位于 `outputs/`，该目录已被 `.gitignore` 忽略，不纳入 git。

## 8. 外部仓库只读状态

`pcv-stage2-data-prep`：

```text
status ## main...origin/main
```

`pcv-stage2-allocation`：

```text
status ## master...origin/master
```

旧 `PointCloud_Benchmark`：

```text
status ## main...origin/main
       ?? scripts/plot_time_vs_point_count_filtered.py
```

旧 benchmark 的未跟踪脚本是既有状态，本轮未修改。

## 9. reference/Decode_Worker.js

SHA-256：

```text
0747B51E9983E59ACC5E911047AE7EBC71213303A60EC7B0548329101775E56C
```

阶段 0A、0B、0C 哈希一致。本轮未修改该文件。

## 10. 当前可用输入资产线索

原始 Longdress raw ASCII full-cloud PLY 路径存在：

```text
E:\Miunaaaa\0-work\data\8i\longdress\longdress\Ply
```

该路径只作为来源背景。本阶段未读取大文件内容。

data-prep 当前可用的正式候选资产 metadata 线索：

- Stage2 tile binary PLY index：`artifacts/pilot_1051_g128_tilelocal_pdl5_v1/frame_1051_tile_index.json`；
- Stage2 tile DRC manifest：`artifacts/pilot_1051_g128_drc_pdl5_qp3_cl10_v1/generation_manifest.json`。

运行时代码通过 CLI 参数传入 data-prep root 或 manifest path，不硬编码本机绝对路径。

## 11. 当前没有的内容

当前仓库没有：

- PLY 文件内容 parser；
- DRC decoder；
- Draco 调用；
- C++ benchmark 工程；
- JavaScript / 浏览器 / WASM benchmark 工程；
- 真实 `d_ms` 测量结果；
- measured / calibrated / derived 结果数据；
- allocation 输入文件；
- 点云资产复制、移动、生成或重新编码产物。

## 12. 已冻结事项

- 候选清单 adapter 只读 JSON metadata；
- `candidate_key` 由显式身份字段组成，不依赖数组位置；
- PLY / DRC 候选统一到 metadata planning record；
- DRC `codec_params` 只记录显式可见的 point-cloud mode、`cl`、`qp`，不编造 `qc` / `qg`；
- 第一版 sampling plan 默认按 tile bucket 选 tile，并保留选中 tile 的所有 PLY PDL 与 DRC PDL × QP；
- `outputs/` 作为本地生成结果目录，不提交。

## 13. 仍未冻结事项

- 正式测量 runner 的实现方式；
- 是否对真实 asset path 做 file existence / stat 校验，以及何时做；
- 具体抽样数量和人工审查流程；
- 环境依赖版本、计时 API、warmup / sample 策略；
- 真实 measured record / calibrated record / derived record 的文件格式；
- 多帧 Longdress 样本由 data-prep 生成还是 benchmark ignored 临时生成；
- normals 是否纳入 JS `d_ms`。

## 14. 下一阶段建议

下一阶段可以先做 metadata-only 人工审查报告，检查 inventory 与 sampling plan 的覆盖性；也可以进入测量 runner 设计，但在实现前必须冻结 runtime 版本、计时 API、warmup / sample 策略、异常处理和输出 layout。任何测量 runner 都必须继续排除磁盘读取、网络下载、Worker 消息传输、GPU upload 和播放级调度。
