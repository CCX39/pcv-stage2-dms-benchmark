# 阶段 1B.3：Open3D 内存 PLY 路径与 Python v2 交付审查

## 1. 阶段目标与实际状态

阶段 1B.2 的 4-candidate 对齐表明，Open3D 0.19.0 path API 即使包含磁盘读取，也远快于阶段 1A 的 plyfile 内存路径。因此本阶段原计划使用 `open3d.io.read_point_cloud_from_bytes(payload, format="ply")` 建立正式内存 PLY processor，并在同一 Python 3.10 环境重新测量 PLY 与 DRC。

实际执行发现：当前 Windows Open3D 0.19.0 wheel 虽然暴露 `read_point_cloud_from_bytes`，但对 synthetic binary PLY 和真实 frame1051 tile binary PLY 均报告 `unknown format for (format: ply)` 并返回空点云。按预先冻结的失败规则，本阶段停止在双格式 smoke，没有运行 100-candidate pilot，没有标定模型，也没有生成 v2 handoff。

阶段状态：

```text
phase_status = blocked_by_open3d_windows_from_bytes_ply
allocation_integration_status = review_pending
```

## 2. 为什么计划从 plyfile 切换

阶段 1B.2 对同一批 4 个 PLY 候选比较了当前 plyfile 内存路径与 Open3D path API。两边均转换到独立 `float32[N,3]` positions 和 `uint8[N,3]` colors，correctness 4/4 通过；Open3D/plyfile p50 比值约为 0.0108–0.0215。

该证据强支持 plyfile 的 structured fields 拆列、`column_stack`、显式 copy 与 Python 侧解析路径是阶段 1A PLY 耗时偏高的主要因素。不过 path API 包含磁盘读取，不能直接成为正式 `d_ms`，所以本阶段必须验证 Open3D 内存 API，而不能复用 1B.2 数值。

## 3. 预定 Open3D from-bytes 路径

已实现的候选 processor 只接收 `bytes`，不接收路径，不创建临时文件，也不调用 Open3D path API。预定正式边界为：

```text
payload 已完整驻留内存
-> 校验 binary little-endian PLY header 与 XYZ/RGB 属性
-> open3d.io.read_point_cloud_from_bytes(payload, format="ply")
-> 提取 points 与 0-1 浮点 colors
-> positions float32[N,3] 独立 copy
-> round(clip(colors, 0, 1) * 255)
-> colors uint8[N,3] 独立 copy
```

shape、dtype、point count、`N > 0` 与 ownership 校验由 runner 在 processor timer 结束后执行。normals 不属于输出。代码没有 path API fallback；当 from-bytes 返回空点云时，runner 明确记录 failure。

## 4. 为什么 PLY 与 DRC 必须同环境重测

阶段 1A 的 DRC measured 数据来自 CPython 3.13.0，而 Open3D 0.19.0 没有该解释器的可用 wheel。若只在 Python 3.10 测 PLY、再拼接 3.13 DRC，会把两个 runtime 混成一个虚假 environment。

因此本阶段建立单一候选 profile：

```text
environment_id = python310_open3d019_dracopy200_windows_x64
```

只有 PLY 与 DRC 都在该 profile 成功完成 100-candidate pilot 后，才允许生成 v2 calibration 与 handoff。

## 5. 实际环境

环境位于仓库 ignored `.venv/open3d310`，没有修改全局 Python、conda base 或已有 `open3d_env` 包内容。

```text
Python implementation CPython
Python version        3.10.20
Open3D               0.19.0
DracoPy              2.0.0
numpy                2.2.6
OS                   Windows 10.0.22631 x64
timer                time.perf_counter_ns
warmup_count         2
sample_count         5
```

## 6. API 能力探测

本地 API docstring 显示：

```text
read_point_cloud_from_bytes(bytes, format='auto', ...)
```

实际使用 1-point/2-point synthetic binary little-endian PLY 调用 `format="ply"` 时，Open3D 输出：

```text
[Open3D WARNING] Read geometry::PointCloud failed: unknown format for (format: ply).
```

返回的 point cloud 为 0 点。进一步只读探测 `PLY`、`.ply`、`memory.ply`、`auto`、`pcd` 和 `xyz` 均得到相同的 unknown-format 行为。这说明问题不是本项目把 `ply` 大小写或扩展名传错；当前 wheel 的 memory point-cloud reader 没有表现出可用的 PLY format handler。

本阶段没有尝试 path API、临时文件或其他 decoder 兜底。

## 7. 双格式 smoke

真实 smoke 输出：

```text
outputs/phase1b3_python_open3d_smoke.json
SHA-256 C8D2414C93B7E46B109BECDAD16740AE5786070D1486711215DC4044EA4ED3B8
```

该文件位于 ignored `outputs/`，不提交。

| representation | candidate | point_count | status | p50_ms | 结论 |
|---|---|---:|---|---:|---|
| PLY | `gx_0_gy_4_gz_0`, PDL 0.2 | 612 | failed | null | Open3D 返回 0 点，计时外 `N > 0` 校验拒绝 |
| DRC | `gx_0_gy_4_gz_0`, PDL 0.2, qp 10 | 612 | success | 0.1582 | DracoPy 2.0.0 在同一 Python 3.10 profile 可用 |

run-level 状态为 `partial_failure`，`success_count = 1`、`failure_count = 1`。由于 PLY smoke 失败，没有执行 plyfile correctness comparison，也不能声称双格式 smoke 通过。

## 8. 100-candidate pilot 状态

未运行。停止原因是 representation-level PLY backend failure，而不是单个资产损坏。未生成：

```text
outputs/phase1b3_python_open3d_pilot.json
```

因此不存在本阶段的 25 PLY + 75 DRC measured pilot，也没有把阶段 1A 的 Python 3.13 DRC 值混入新环境。

## 9. Measured 摘要状态

没有生成或提交 `results/python_open3d_frame1051_measured_summary_v2.json`。单条 DRC smoke 只用于确认 backend/runtime 可用，不足以构成 100-candidate measured summary，也不进入模型。

## 10. Candidate models、selected model 与 grouped validation

没有执行拟合。P0–P2、D0–D3 的代码路径已参数化支持 v2 environment/scope，但由于 v2 pilot 缺失，未产生候选模型指标、selected model、公式、参数或 leave-one-tile-out 结果。

本阶段不得复用 v1 参数来填充 v2 artifact。

## 11. v1 与 v2 的关系

v1 三个文件内容保持不变。其状态记录为：

```text
profile_status = historical_plyfile_profile
allocation_status = superseded_for_allocation_pilot
retention_status = retained_for_audit
```

v1 不是伪造或程序错误；它忠实测量并拟合了 CPython 3.13 + plyfile profile。但阶段 1B.2 已证明该 PLY backend 不适合作为当前 allocation pilot 的优先 profile。

v2 尚未形成，不能替代 v1，也不能标记 ready。

## 12. v2 handoff 完整性状态

没有生成或提交：

```text
results/python_open3d_frame1051_calibration_v2.json
handoff/python_open3d_frame1051_candidate_dms_v2.json
```

因此不存在 800-candidate v2 完整性结论，也不存在 PLY 200/DRC 600 的 v2 derived 数值。代码中的 v2 exporter 只有 synthetic 800-key 单元测试覆盖，不能代替真实交付。

## 13. Allocation 状态

ready gate 要求双格式 smoke、100/100 pilot、两类 grouped validation、800 个有限正预测以及 1B.2 方向一致性全部通过。本轮第一项即失败，所以：

```text
allocation_integration_status = review_pending
```

`ready_for_provisional_integration` 不成立。allocation 仓库继续不修改、不接入 v1 或不存在的 v2。

## 14. 测试

测试覆盖：

- synthetic binary PLY 与 fake from-bytes reader 的 canonical 转换；
- float32 positions、uint8 colors、RGB round/clip 与独立 ownership；
- ASCII PLY 在 reader 前被拒绝；
- 正式 processor 只调用 from-bytes，不调用 path API；
- 空点云由计时外 runner 校验拒绝；
- PLY/DRC 共用一个 v2 environment snapshot；
- synthetic 100-record pilot 可进入 v2 calibration；
- synthetic v2 handoff 覆盖 800 个唯一 candidate key；
- v2 provenance/version 与 v1 哨兵不变。

真实 Open3D synthetic test 在本 wheel 上以明确原因 skipped，并输出 unknown-format warning；这不是成功解析证据。

## 15. 限制

- blocker 仅确认于当前 Windows Open3D 0.19.0 wheel，尚未判断 Linux wheel、其他 Open3D build 或后续版本行为。
- 没有 profiler 或 native source-level 根因分析。
- 没有跨 frame、跨数据集、C++ 或 JavaScript 结果。
- 单条 Python 3.10 DRC smoke 不能替代完整 DRC pilot。
- 当前没有可供 allocation 使用的 Python v2 handoff。

## 16. 下一阶段建议

优先确认 Open3D memory PLY 能力的可行来源：

1. 在不修改全局环境的前提下，验证另一个明确支持 PLY memory reader 的 Open3D wheel/build；记录版本与平台。
2. 若需要自建 Open3D，先做 1-point synthetic 与 1 个真实 tile capability smoke，再运行任何 benchmark。
3. 若 Open3D 0.19.0 Windows memory API 确认不支持 PLY，研究者需决定更换 Open3D build/backend，或版本化调整 Python PLY execution profile；不得回退到 path API 并沿用当前内存边界名称。
4. capability smoke 成功后，重新执行 1 PLY + 1 DRC smoke；随后才允许 100-candidate pilot、grouped calibration 和 v2 handoff。
5. 在真实 v2 完整通过前，allocation 保持 `review_pending`。
