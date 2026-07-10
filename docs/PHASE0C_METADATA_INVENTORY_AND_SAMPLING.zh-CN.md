# 阶段 0C 候选清单适配器与抽样计划骨架

本文档记录阶段 0C 的实现边界、代码职责、CLI 用法、测试策略和真实 metadata 只读验证结果。本阶段只处理 JSON metadata，不解析 PLY 文件内容，不解码 DRC，不运行任何 `d_ms` benchmark。

## 1. 阶段 0C 目的

阶段 0C 的目标是建立最小 metadata-only 工具链：

- 从 `pcv-stage2-data-prep` 的 frame1051 pilot metadata 读取 tile binary PLY 与 DRC 候选信息；
- 规范化为统一候选清单；
- 基于候选 metadata 生成第一版 Longdress pilot 抽样计划；
- 提供 CLI 入口写入本地 ignored `outputs/`；
- 用极小 synthetic fixture 做 unittest，避免测试依赖真实点云文件。

本阶段不产生 measured / calibrated / derived 结果数据，不产生真实 `d_ms` 数值。

## 2. 新增代码职责

`src/pcv_dms_benchmark/metadata_inventory.py`：

- 读取 PLY tile index JSON 与 DRC generation manifest JSON；
- 将 PLY / DRC metadata 规范化为统一 candidate record；
- 生成稳定 `candidate_key`，不依赖数组位置；
- 仅使用 metadata 中已有的 file size 与 hash 字段，不重新计算真实点云文件 hash；
- 对缺失字段记录 warning 或 `null`，不编造值；
- 不打开 PLY / DRC 文件内容。

`src/pcv_dms_benchmark/sampling_plan.py`：

- 从 inventory 中按 tile 聚合候选；
- 基于 tile 最大 `point_count` 做确定性 bucket selection；
- 对选中 tile 默认保留所有 PLY PDL 与所有 DRC PDL × QP；
- 输出 sampling plan JSON；
- 不进行任何测量。

`src/pcv_dms_benchmark/cli.py`：

- 提供 `inventory` 与 `sample-plan` 两个子命令；
- 只读输入 JSON metadata；
- 写入调用者指定的本地输出路径。

## 3. 候选清单记录字段

当前 candidate record 包含：

- `inventory_schema_version`
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

PLY 的 `representation` 为 `ply`，`codec` 为 `null`，`codec_profile` 为 `binary_little_endian_ply`。DRC 的 `representation` 为 `drc`，`codec` 为 `draco`，`codec_params` 记录 `point_cloud_mode`、`cl` 与 `qp`。未显式传入的 `qc`、`qg` 等参数不会被编造。

当前 `provenance.record_kind` 为 `metadata_planning`，表示该记录只是候选 metadata 清单，不是 measured / calibrated / derived 结果。

## 4. 抽样计划记录字段

sampling plan 顶层包含：

- `sampling_plan_schema_version`
- `plan_kind`
- `plan_id`
- `source_inventory`
- `selection_policy`
- `selected_tiles`
- `selected_candidates`
- `coverage_summary`
- `warnings`

`selected_candidates` 引用 `candidate_key` / `candidate_id`，并保留 `tile_id`、`representation`、`pdl_ratio`、`qp`、`cl`、`point_count`、`file_size_bytes` 和 `status`，便于人工审查。

## 5. CLI 用法

生成候选清单：

```powershell
$env:PYTHONPATH='src'
python -m pcv_dms_benchmark.cli inventory --data-prep-root E:\Miunaaaa\0-work\code\pcv-stage2-data-prep --out outputs\phase0c_frame1051_inventory.json
```

生成抽样计划：

```powershell
$env:PYTHONPATH='src'
python -m pcv_dms_benchmark.cli sample-plan --inventory outputs\phase0c_frame1051_inventory.json --out outputs\phase0c_frame1051_sample_plan.json --max-tiles 5
```

`outputs/` 已由 `.gitignore` 忽略，不应提交。

## 6. 测试策略

测试使用 `python -m unittest discover`，只依赖 `tests/fixtures/` 下的极小 synthetic JSON。

覆盖点包括：

- PLY candidate 规范化；
- DRC candidate 规范化；
- DRC `codec_params` 保留 `qp` 与 `cl`；
- 不编造未显式 `qc` / `qg`；
- `candidate_key` 不依赖数组位置；
- `representation`、`tile_id`、`pdl_ratio`、`file_size_bytes`、`point_count` 保留；
- metadata 缺失时产生 warning 或 `null`；
- sampling plan 无重复 candidate；
- sampling plan 覆盖 PLY 与 DRC；
- sampling plan 覆盖多个 PDL；
- sampling plan 覆盖 DRC 多个 QP；
- inventory / plan 表达为 `metadata_planning`，不是测量结果。

## 7. 真实 metadata 只读验证结果

在本机对 `pcv-stage2-data-prep` frame1051 metadata 执行只读验证成功。命令只读取 JSON metadata，不读取 PLY / DRC 文件内容。

inventory 输出摘要：

```text
candidate_count=800
ply_candidate_count=200
drc_candidate_count=600
tile_count=40
```

sample plan 输出摘要，参数为 `--max-tiles 5`：

```text
selected_tile_count=5
selected_candidate_count=100
ply_candidate_count=25
drc_candidate_count=75
```

生成文件位于 `outputs/`，未纳入 git。

## 8. 当前不做事项

阶段 0C 明确不做：

- 不实现 PLY 文件内容解析；
- 不实现 DRC 解码；
- 不调用 Draco decoder；
- 不运行真实 `d_ms` benchmark；
- 不产生真实 `d_ms` 数值；
- 不创建 measured / calibrated / derived 结果数据；
- 不读取、复制、移动、生成或重新编码点云资产；
- 不接入 allocation；
- 不创建浏览器、WASM 或 C++ benchmark 工程。

## 9. 下一阶段建议

下一阶段可以继续保持 metadata-only，完善 inventory / sampling plan 的人工审查报告；也可以进入测量实现准备，先冻结各运行环境依赖版本、计时 API、warmup / sample 策略、输出 layout 和异常处理规则。进入任何测量实现前，仍需确认 runner 不包含磁盘读取、网络下载、Worker 消息传输或 GPU upload。
