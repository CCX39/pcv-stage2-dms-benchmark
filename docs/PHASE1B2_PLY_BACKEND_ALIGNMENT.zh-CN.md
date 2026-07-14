# 阶段 1B.2：PLY backend 最小对齐实验

## 1. 实验目的

阶段 1B.1 发现当前 `plyfile + BytesIO + canonical arrays` 路径与旧项目 Open3D path API 的 PLY 耗时差异很大。本轮只用 4 个 frame1051 tile binary PLY 做诊断，判断 plyfile 路径是否可能是当前 Python PLY 耗时偏高的主要原因。

本实验不修改阶段 1B 模型或 handoff，不重测 DRC，不把 Open3D path API 的结果定义为正式 `d_ms`。

## 2. 环境

Open3D 0.19.0 没有适用于当前 CPython 3.13 `.venv` 的 wheel。本轮没有修改全局 Python 或既有 conda 环境，而是在仓库 ignored `.venv/` 内创建本地嵌套环境 `.venv/open3d310`，继承研究者已有 `open3d_env` 的只读 system site packages，并将 plyfile 与本项目安装到该本地环境。

两条 backend 路径在同一个诊断进程中运行：

```text
Python  3.10.20
Open3D  0.19.0
plyfile 1.1.4
numpy    2.2.6
timer    time.perf_counter_ns
```

阶段 1A 的正式 Python profile 仍为 CPython 3.13.0、numpy 2.5.1、plyfile 1.1.4、DracoPy 2.0.0。本轮环境只用于 backend 对齐，不覆盖或重写阶段 1A 环境记录。

## 3. 样本选择

从阶段 0C 的 5 个已选 tile 中，以 PDL 1.0 PLY 的 `point_count` 表示 tile 规模，确定性选择最小和最大 tile；每个 tile 选择 PDL 0.2 与 1.0，共 4 个候选。选择通过 `candidate_key` 与 sample plan/inventory join，不使用数组位置或单独的 `candidate_id`。

候选键：

```text
K1 dataset=8i_longdress|frame=1051|grid=longdress_raw_g128_fullseq_pilot_v1|tile=gx_0_gy_4_gz_0|repr=ply|pdl=0p2|codec=none
K2 dataset=8i_longdress|frame=1051|grid=longdress_raw_g128_fullseq_pilot_v1|tile=gx_0_gy_4_gz_0|repr=ply|pdl=1p0|codec=none
K3 dataset=8i_longdress|frame=1051|grid=longdress_raw_g128_fullseq_pilot_v1|tile=gx_2_gy_1_gz_1|repr=ply|pdl=0p2|codec=none
K4 dataset=8i_longdress|frame=1051|grid=longdress_raw_g128_fullseq_pilot_v1|tile=gx_2_gy_1_gz_1|repr=ply|pdl=1p0|codec=none
```

只选 4 个候选是为了先隔离 backend effect，同时覆盖小/大 tile 和低/高 PDL；本轮不追求统计泛化，也不扩大到 100 个候选。

## 4. 两条路径与边界

### 4.1 plyfile current boundary

文件在计时外通过 `read_bytes()` 预载一次。每轮计时从内存 payload 开始，执行 `plyfile + BytesIO` 解析、structured fields 提取、`column_stack` 和显式 copy，终点为独立拥有的：

```text
positions: float32[N, 3]
colors: uint8[N, 3]
```

该边界与阶段 1A 当前 PLY 实现相同。

### 4.2 Open3D legacy total boundary

每轮在计时内调用 `open3d.io.read_point_cloud(path)`，因此包含磁盘读取和 Open3D path API 解析。随后在计时内把 points 转为新的 float32 positions；Open3D 的 0–1 浮点颜色通过 `round(clamp(color, 0, 1) * 255)` 转为新的 uint8 colors。

该路径终点与 plyfile 路径相同，但起点不同。`open3d_legacy_total_ms` 包含磁盘读取，不符合当前“payload 已驻留内存”的正式 `d_ms` 边界，只是 backend 诊断参照，不能直接交付给 allocation。

## 5. 测量与正确性协议

每候选、每路径均使用 warmup 2 次、正式 sample 5 次，保留 raw samples、p50 与 mean。每轮重新调用 backend，不复用解析结果。

计时外校验：

- point count、shape 与 `N > 0`；
- positions 为独立拥有的 float32 `[N,3]`；
- colors 为独立拥有的 uint8 `[N,3]`；
- 两条路径坐标使用 `rtol=1e-6`、`atol=1e-5` 比较；
- RGB 最大允许 1 个 uint8 量化级误差。

4 个候选全部通过正确性校验，没有因点数、坐标或颜色不一致而中止结论。

## 6. 结果

单位均为 ms。DRC 列只引用阶段 1A 的 qp=10 p50，`source = existing_phase1a_measured`，不是本轮新测量。

| key | tile_id | PDL | point_count | file_size_bytes | plyfile p50 | plyfile mean | Open3D p50 | Open3D mean | Open3D / plyfile p50 | 既有 DRC qp=10 p50 | correctness |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| K1 | `gx_0_gy_4_gz_0` | 0.2 | 612 | 9,631 | 3.9478 | 3.9560 | 0.0850 | 0.0834 | 0.0215 | 0.1530 | passed |
| K2 | `gx_0_gy_4_gz_0` | 1.0 | 3,062 | 46,284 | 19.0935 | 19.1442 | 0.2427 | 0.2532 | 0.0127 | 0.6617 | passed |
| K3 | `gx_2_gy_1_gz_1` | 0.2 | 7,109 | 107,087 | 43.7813 | 44.0744 | 0.4741 | 0.4824 | 0.0108 | 1.6847 | passed |
| K4 | `gx_2_gy_1_gz_1` | 1.0 | 35,548 | 533,575 | 219.4121 | 222.6539 | 3.2073 | 3.2220 | 0.0146 | 8.5162 | passed |

本地原始诊断记录位于：

```text
outputs/phase1b2_ply_backend_alignment.json
```

`outputs/` 已被 Git 忽略，该 JSON 不提交。

## 7. 判定

四个候选 correctness 全部通过；Open3D 即使包含磁盘读取，在 4/4 个候选上的 p50 也都小于 plyfile p50 的一半。按预先冻结的规则，本轮结论为：

```text
strong_support_for_open3d_backend
```

实际比值约为 0.0108–0.0215，说明当前 plyfile 解析与 canonical 整理路径很可能是 Python PLY 耗时偏高的主要因素。该结论支持下一阶段认真评估用 Open3D 替换 plyfile，而不是继续把当前 PLY 模型直接接入 allocation。

这仍不是正式 backend 切换决定：Open3D path API 的磁盘起点不符合当前测量契约，且诊断运行在 Python 3.10.20，而阶段 1A profile 是 Python 3.13.0。本轮只能回答 backend 瓶颈问题，不能把这些 Open3D 数值替换进 handoff。

## 8. Handoff 状态

阶段 1B 的 calibration 与 handoff JSON 均未修改。当前操作状态继续保持：

```text
review_status = review_pending
allocation_integration_status = temporarily_hold_for_allocation_integration
```

allocation 应继续暂缓使用当前 handoff。

## 9. 下一阶段建议

1. 冻结新的 Python PLY execution profile，明确 Python 版本、Open3D 版本和正式计时起点。
2. 解决 Open3D path API 与“payload 已驻留内存”契约的冲突：选择可接受内存输入的 Open3D 路径，或经研究者确认后版本化调整 Python PLY profile；不得静默改边界。
3. 在新 profile 冻结后，先做双路径小规模复核，再重跑阶段 0C 的 25 个 PLY pilot 候选；DRC 不必因本轮结论无理由重测。
4. 重新标定 PLY 模型并版本化生成新的 handoff；保留当前阶段 1A/1B 文件作为历史证据。
5. 只有新 PLY measured/calibrated 结果完成完整性与 grouped validation 后，才重新评估 allocation 暂缓状态。

## 10. 阶段 1B.3 后续验证

阶段 1B.3 已验证当前 Open3D 0.19.0 Windows wheel 的 `read_point_cloud_from_bytes`。该 API 存在，但 `format="ply"` 对 synthetic 和真实 tile 均返回空点云；PLY smoke 失败，未生成 v2。阶段 1B.2 的 path-API 性能结论仍有效，但不能转换为正式内存 PLY profile。详见 `PHASE1B3_OPEN3D_IN_MEMORY_PYTHON_V2.zh-CN.md`。
