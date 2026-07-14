# 阶段 1B.1：旧 Python benchmark 与当前结果差异审查

## 1. 审查背景与结论摘要

阶段 1A/1B 在当前 Python 契约下得到的 provisional 结果显示，同一点数下 DRC 路径明显快于 PLY；旧 `PointCloud_Benchmark` 的本地既有结果则显示 DRC 慢于 PLY。本轮只读核对代码、资产 metadata 与既有结果，不运行任何新 benchmark，也不修改模型或 handoff。

审查结论如下：

- 未发现当前阶段 1A 的 ns/ms 换算、计时位置、点数、RGB、缓存复用或统计实现错误。
- 阶段 1B 的模型参数与阶段 1A measured 数据一致，按 tile 留一验证只能证明当前样本内拟合稳定，不能证明两套实验之间的 backend 比较公平。
- 两套实验在 PLY backend、磁盘读取边界、输出终点、资产组织、点数范围、DRC profile、预热与汇总统计等方面不同，不具备直接可比性。
- 旧结果确有“DRC 慢于 PLY”的本地结果文件证据；当前结果也确有相反排序的直接 measured 证据。顺序反转不能仅凭其中一套结果判定另一套实现错误。
- handoff JSON 中既有 `recommended_for_allocation_pilot = true` 不在本轮修改；该标记表示其通过阶段 1B 的内部阈值。操作层面新增 `review_pending` 和 `temporarily_hold_for_allocation_integration`，建议在最小对齐实验完成前暂停接入 allocation。

## 2. 仓库基线与状态

审查开始时的当前项目：

```text
E:\Miunaaaa\0-work\code\pcv-stage2-dms-benchmark
## main...origin/main
7610362 feat: calibrate Python d_ms pilot models
```

旧项目只读状态：

```text
E:\Miunaaaa\0-work\code\PointCloud_Benchmark
## main...origin/main
?? scripts/plot_time_vs_point_count_filtered.py
cb3a1975464c9d26cccff9861943e394f10aada3
cb3a197 修改说明：readme更新
```

旧项目的未跟踪绘图脚本在审查前已经存在。本轮未删除、修改、格式化或提交该文件。旧项目的 benchmark 代码首次提交于 `685cdd0`；随后可见提交只改动分析脚本或 README。旧 `results/` 为 ignored 本地结果，未记录产生结果时的 commit、环境 lock 或 repeat count，因此代码与结果的对应关系可信但不可做加密级证明。

## 3. 审查证据清单

当前项目重点证据：

- `src/pcv_dms_benchmark/python_benchmark.py`
- `src/pcv_dms_benchmark/measurement_stats.py`
- `src/pcv_dms_benchmark/calibration.py`
- `src/pcv_dms_benchmark/derived_export.py`
- `src/pcv_dms_benchmark/cli.py`
- `outputs/phase1a_python_pilot.json`（ignored，只读）
- `outputs/phase0c_frame1051_inventory.json`（ignored，只读）
- `results/python_frame1051_measured_summary_v1.json`
- `results/python_frame1051_calibration_v1.json`
- `handoff/python_frame1051_candidate_dms_v1.json`

旧项目重点证据：

- `PointCloud_Benchmark/scripts/benchmark_python.py`
- `PointCloud_Benchmark/scripts/run_benchmark.py`
- `PointCloud_Benchmark/scripts/data_preparation.py`
- `PointCloud_Benchmark/requirements.txt`
- `PointCloud_Benchmark/README.md`
- `PointCloud_Benchmark/results/20260416_165042/benchmark_results.csv`
- 旧项目本地 `data/processed/` 与 `data/compressed/` 的文件名、文件大小和小型 PLY header；未读取 DRC payload。

## 4. 当前项目测量链路复核

### 4.1 PLY 路径

`python_benchmark.py` 使用 `PlyData.read(io.BytesIO(payload))` 解析已驻留内存的 payload。随后分别提取 `x/y/z` 与 `red/green/blue` 列，使用 `numpy.column_stack` 组织二维数组，再通过 `numpy.array(..., dtype=..., order="C", copy=True)` 生成独立拥有的 canonical arrays。

因此，PLY 计时内包括：`BytesIO` 包装、PLY header 与 structured array 解析、六列提取、两次 `column_stack`，以及显式 dtype/C-order 独立 copy。`column_stack` 本身已经分配数组，后续 `copy=True` 形成额外 copy。这是当前契约下的真实成本和一个可进一步隔离的实现因素，不是输出语义错误。

### 4.2 DRC 路径

DRC 使用 `DracoPy.decode(payload)` 进行进程内解码，没有调用 CLI 子进程。解码结果的 `points` 和 `colors` 分别通过 `numpy.array(..., dtype=numpy.float32/uint8, order="C", copy=True)` 转为独立 canonical arrays。

DRC 路径也在计时内创建新的 positions/colors。与 PLY 相比，它没有经过 structured vertex array 的逐列提取和 `column_stack`；两条路径做了相同的最终 dtype、C-order 和独立拥有要求，但 backend 返回形态与中间整理步骤不同。

### 4.3 计时、校验与统计

- `stat`、metadata size 对照和 `read_bytes()` 位于 warmup 与计时循环之前；每候选 payload 只预加载一次。
- 每次 warmup 和正式 sample 都重新调用 processor，没有复用上一轮 decoded output。
- 计时使用 `time.perf_counter_ns()`；耗时通过除以 `1_000_000.0` 从 ns 转为 ms，换算正确。
- dtype、shape、C-contiguous、独立 ownership、RGB 与 decoded point count 校验在计时结束后执行。
- 两条路径使用相同的 `warmup_count = 2`、`sample_count = 5`；`p50_ms` 使用 `statistics.median`，`mean_ms` 使用 `statistics.fmean`。
- pilot 中 PLY 25 条、DRC 75 条覆盖相同 5 个 tile 和相同五档 PDL；DRC 额外展开 qp 8/10/12。
- 所有成功记录的 `decoded_point_count == point_count`，未见某一路少做 RGB、复用结果或浅拷贝绕过 ownership 要求。

## 5. 旧项目测量链路复核

### 5.1 PLY 路径

`PointCloud_Benchmark/scripts/benchmark_python.py` 使用 `o3d.t.io.read_point_cloud(str(file_path))` 按文件路径读取 PLY，再对 positions/colors 调用 `.numpy()`。代码未强制 `float32[N,3]`、`uint8[N,3]`、C-order 或独立 ownership，也没有显式 canonical copy。

这一路径的 PLY 读取和主要解析由 Open3D 原生实现承担。仅凭仓库代码不能确定 `.numpy()` 在该版本与该 tensor 状态下是否发生 copy，因此不能把“零 copy”写成事实。

### 5.2 DRC 路径

旧 DRC 路径在 parser 内执行 `file_path.read_bytes()`，随后调用 `DracoPy.decode(file_content)`。解码结果通过 `numpy.asarray(..., dtype=numpy.float32/uint8).reshape(-1, 3)` 整理。`asarray` 是否 copy 取决于返回数组的 dtype/layout；代码没有强制独立 ownership。

旧项目与当前项目都使用 DracoPy API，但旧结果没有记录实际 DracoPy 版本。`requirements.txt` 只给出 `DracoPy>=1.0.0`，不能据此断言旧运行版本与当前 2.0.0 相同。

### 5.3 计时、校验与统计

`PointCloud_Benchmark/scripts/run_benchmark.py` 在 parser 调用前启动 `time.perf_counter()`，对整个 `parser.parse(file_path)` 计时。因此旧 PLY 的 Open3D 路径读取，以及旧 DRC 的 `read_bytes()` 都在计时内。文件 `stat`、日志和结果写盘不在 parser timer 内。

旧代码只检查 positions 的二维 shape，不检查 colors、dtype、ownership 或 decoded point count 与来源 metadata 的一致性。每次 timed parse 后还有一次用于内存统计的 parse；后者不计入该次耗时，却会影响下一轮的 OS 文件缓存和 backend 状态。代码没有显式 warmup。最终结果使用重复样本的 arithmetic mean，而非 p50；交互入口默认 repeat 为 1，CSV 没有记录实际 repeat count，因此旧结果的真实重复次数未知。

## 6. 输入资产与 codec profile

旧项目的 Longdress 输入是 frame 1051 的整帧点云经独立随机降采样得到的 binary little-endian PLY，不是 G128 tile，也不是当前 data-prep 的 tile-local 嵌套 PDL。其可见档位包括 1.0、0.8、0.6、0.4、0.2、0.1、0.01。

旧 data preparation 为 DRC 显式组合 qp 12/10/8、qc 8/6/4 和 cl 10，并使用 point-cloud encoder flag。当前 active profile 是 tile DRC、`-point_cloud`、cl 10、qp 8/10/12，未显式传入 qc/qg。两者不能视为相同 codec profile；未显式参数的实际默认行为也不能由旧 profile 反推。

本机旧 Longdress 资产线索：

- 整帧 PLY point count：7,658 至 765,821；文件大小约 115,048 至 11,487,495 bytes。
- 对应 DRC 文件大小约 27,166 至 2,592,508 bytes。

当前 5-tile pilot：

- PLY/DRC point count：612 至 35,548。
- PLY 文件大小：9,631 至 533,575 bytes。
- DRC 文件大小：2,133 至 162,360 bytes。

点数范围仅有部分重叠，且空间组织、降采样关系和 DRC 参数均不同。

## 7. 逐项对照表

状态含义：`same` 表示仓库证据支持一致，`different` 表示证据支持不同，`unknown` 表示当前证据不足。

| 维度 | 当前项目 | 旧项目 | 状态 | 证据 |
|---|---|---|---|---|
| 实验目的 | 内存 payload 到 canonical arrays 的 target-side `d_ms` | 含磁盘读取的端到端解析耗时 | different | 当前测量契约；旧 README 与 `run_benchmark.py` |
| 数据集与 frame | Longdress 1051 | Longdress 1051 结果可见 | same | 两边 inventory/文件名/CSV |
| full-cloud 或 tile | G128 tile | 降采样 full-cloud | different | 当前 inventory；旧 `data_preparation.py` |
| 点数范围 | 612–35,548 | 7,658–765,821 | different | 当前 pilot；旧 PLY header/CSV |
| PLY 表示形式 | binary little-endian | binary little-endian | same | metadata 与 PLY header |
| DRC 生成来源 | 对应 tile binary PLY | 对应降采样 full-cloud PLY | different | 两边 generation/data-prep 记录 |
| Draco 参数 | point-cloud、cl=10、qp=8/10/12；qc/qg 未显式 | point-cloud、cl=10、qp=8/10/12、qc=4/6/8 | different | 两边 manifest/脚本 |
| Draco executable/library 版本 | DracoPy 2.0.0；encoder 版本另行记录 | 实际 DracoPy/encoder 版本未记录 | unknown | 当前 pilot；旧 requirements |
| Python 版本 | CPython 3.13.0 | 推荐 3.10+，实际未知 | unknown | 当前 pilot；旧 README/requirements |
| PLY backend 与版本 | plyfile 1.1.4 | Open3D，实际版本未知 | different | 两边代码与环境记录 |
| DRC backend 与版本 | DracoPy 2.0.0 | DracoPy，实际版本未知 | unknown | 两边代码；旧版本缺失 |
| 同一进程/机器 | 当前单一 Python run | 旧结果缺少环境快照 | unknown | 当前 run；旧 CSV 无环境记录 |
| 计时 API | `perf_counter_ns` | `perf_counter` | different | 两边 benchmark 代码 |
| 磁盘读取计入 | 否 | 是 | different | 两边计时位置 |
| import/初始化计入 | module import 不计；processor 已构造 | module import 与 parser factory 不计 | same | 两边入口与计时位置 |
| 输出终点 | 独立 canonical arrays | backend arrays；无独立 ownership 契约 | different | 两边 parser 与校验代码 |
| 强制 float32 XYZ | 是 | `asarray`/`.numpy()` 后未统一强制检查 | different | 两边代码 |
| 强制 uint8 RGB | 是 | DRC 请求 uint8；PLY 未统一强制检查 | different | 两边代码 |
| numpy copy/stack/astype | PLY `column_stack` 后显式 copy；DRC 显式 copy | PLY `.numpy()`；DRC `asarray().reshape()`，copy 行为不确定 | different | 两边代码 |
| warmup | 2 | 无显式 warmup | different | 两边 runner |
| sample count | 5 | CSV 未记录，实际未知 | unknown | 当前 pilot；旧 CSV/CLI |
| 汇总统计 | p50 为拟合目标，保留 mean | arithmetic mean | different | 两边统计代码 |
| 文件缓存条件 | payload 预读一次，解析轮次不读盘 | timed read；额外 memory parse 会触碰缓存 | different | 两边 runner |
| measured 单位 | ms，ns/1e6 | ms，seconds×1000 | same | 两边代码 |
| 结果适用范围 | frame1051、5 tile、Python provisional | 旧整帧本地实验 | different | 两边文档与结果 |

## 8. 旧结果的实际数值与来源

证据文件为 `PointCloud_Benchmark/results/20260416_165042/benchmark_results.csv`。Longdress 有 7 条 PLY 和 63 条 DRC 记录。在同一点数下对照：

| point count | PLY Python time (ms) | DRC Python time 范围 (ms) | DRC/PLY 范围 |
|---:|---:|---:|---:|
| 7,658 | 0.4976 | 1.8076–1.9243 | 3.63–3.87 |
| 76,582 | 4.4068 | 18.5540–19.3546 | 4.21–4.39 |
| 153,164 | 9.0124 | 37.0367–38.6614 | 4.11–4.29 |
| 306,328 | 17.7038 | 73.8661–78.7255 | 4.17–4.45 |
| 459,492 | 26.9133 | 112.9945–118.0430 | 4.20–4.39 |
| 612,656 | 36.2739 | 153.5754–158.6687 | 4.23–4.37 |
| 765,821 | 44.5823 | 185.8843–194.5485 | 4.17–4.36 |

本机共有 16 个 timestamped CSV batch。除最早一批有少量配对比值不大于 1 外，之后 15 批的 Longdress 63 条 DRC 均慢于同点数 PLY；最新批次的平均 DRC/PLY 比值约为 4.209。这支持“旧本地结果通常为 DRC 慢于 PLY”，但结果目录被 Git 忽略，且缺少 repeat count、环境版本和 run manifest，不能提升为可完全复现实验记录。

## 9. 当前结果的实际数值与来源

来源为 ignored `outputs/phase1a_python_pilot.json` 与 tracked `results/python_frame1051_measured_summary_v1.json`。当前 pilot 的直接 measured 范围：

- PLY p50：2.4124–134.2540 ms。
- DRC p50：0.1487–8.5162 ms。
- 对同一 tile、同一 PDL 的 75 个 PLY/DRC 配对，DRC p50 均较低；DRC/PLY 比值约为 0.0566–0.0682。

阶段 1B 选中公式：

```text
PLY: d_hat_ms = 0.15954514764960334
                + 3.7770090745876392 * (point_count / 1000)

DRC: d_hat_ms = -0.029712238641829095
                + 0.23967649584133888 * (point_count / 1000)
```

对应 leave-one-tile-out normalized MAE 分别约为 0.00748 和 0.02081。公式中的 feature scale 为 1000，代码与 artifact 一致；未发现 ms/ns、点数或 feature-scale 错误。

## 10. 顺序反转原因与证据等级

### A. 直接证据支持

1. PLY backend 不同：当前为 plyfile + `BytesIO`，旧项目为 Open3D path API。
2. 计时边界不同：当前明确排除磁盘读取，旧项目把 path read/`read_bytes()` 包含在 parser timer 内。
3. 输出终点不同：当前强制生成独立 float32 XYZ 与 uint8 RGB；旧项目只到 backend arrays，未强制统一 ownership/dtype。
4. 当前 PLY 路径有 structured array 拆列、`column_stack` 和显式 copy；当前 DRC 路径是 DracoPy 结果到 canonical arrays 的显式 copy，二者中间整理工作不同。
5. 输入资产不同：当前为小 tile；旧项目为整帧独立随机降采样，点数范围显著更大。
6. DRC profile 不同：旧项目显式展开 qc，当前 profile 未显式 qc/qg。
7. 测量协议不同：当前 warmup 2、sample 5、p50；旧项目无显式 warmup、repeat 未记录、汇总 mean。
8. 当前结果未见单位、点数、RGB、缓存复用或 canonical ownership 错误；阶段 1B 参数忠实反映当前 measured 数据。

### B. 高可信推断

1. PLY backend 与输出转换差异很可能是顺序反转的重要因素。Open3D 的主要读取逻辑由原生代码执行，而当前 plyfile 路径包含 Python/NumPy 侧 structured fields 整理与额外 copy；但其因果量级仍需对齐实验测定。
2. 资产尺度可能改变固定调用开销、数组整理和实际 codec work 的相对占比。当前 tile 最大约 3.55 万点，旧结果扩展到约 76.6 万点；尺度差异足以使相对排序不能外推。
3. 旧 PLY 与 DRC 输出后处理并不对称，当前二者则统一到 canonical arrays。该边界变化可能显著改变相对成本，但不能仅靠静态代码量化。
4. 磁盘读取是明确边界差异，却不能简单解释为“因此 DRC 更慢”。旧 PLY 文件普遍更大，单看 I/O 方向反而可能更不利于 PLY；必须用分解计时实验判断净影响。

### C. 未证实假设

1. Open3D、DracoPy、Python 或 NumPy 的具体版本变化是否改变两条路径的相对性能。
2. 旧结果所在机器、系统负载、CPU 电源策略和实际 repeat count 的影响。
3. OS 文件缓存和旧 runner 的第二次 memory parse 对后续 timed sample 的量化影响。
4. 旧 Draco executable 的准确版本，以及其 point-cloud flag 与 codec 默认参数的实际行为。
5. 两条曲线是否存在稳定的 asset-scale crossover，以及 crossover 位于何处。
6. 旧 `.numpy()` 和 `numpy.asarray` 在实际版本、dtype/layout 下是否发生 copy。

## 11. 是否发现当前实现错误

没有发现足以推翻阶段 1A measured 数据的实现或统计错误。两条路径都在计时内创建新的 canonical arrays，磁盘读取在计时外，校验在计时外，每轮重新处理 payload，计时单位和 p50/mean 计算正确。

需要保留的实现观察是：PLY 的 `column_stack` 后又执行 `copy=True`，形成额外 copy；DRC 没有等价的 stack 中间步骤。这是当前实现对“得到独立 canonical arrays”的一种实现选择，可能使 PLY 变慢，但不构成契约违规。后续对齐实验应把 output-conversion effect 单独隔离，而不是在本轮修改实现。

## 12. 阶段 1B 模型解释

阶段 1B 的 PLY P1 与 DRC D1 对阶段 1A 的 p50 数据拟合忠实，feature scale、单位、全 inventory 正预测检查和 provenance 均正确。低 grouped-validation error 的含义仅是：在当前 5 个 tile、当前 backend、当前边界内，点数线性关系对留出 tile 稳定。

它不证明：

- plyfile 与 Open3D 具有可直接比较的处理终点；
- 当前 DRC/PLY 排序可推广到整帧或其他点数范围；
- 当前模型可替代旧实验定义；
- backend 间比较已满足 apples-to-apples 条件。

## 13. 当前 handoff 使用建议

`handoff/python_frame1051_candidate_dms_v1.json` 中的 `recommended_for_allocation_pilot = true` 是阶段 1B 内部完整性与 normalized MAE 阈值的结果，本轮不改 JSON，也不将其解释为最终公平性认证。

当前操作状态冻结为：

```text
review_status = review_pending
allocation_integration_status = temporarily_hold_for_allocation_integration
```

建议 allocation 暂缓使用该 handoff，直到最小对齐实验确认顺序反转主要来自哪个因素。现有 measured、calibrated、derived 文件继续保留，作为可追溯的当前契约结果，不应删除或改写历史。

## 14. 最小 apples-to-apples 对齐实验设计

本轮只设计，不实现。优先选择 frame1051 的 1–2 个已测 tile，保留相同 PDL，并为 DRC 选择固定 qp。所有比较使用同一资产 payload、同一点数、同一 Python 环境和明确版本。

2×2 核心矩阵：

| representation | 当前 backend 路径 | legacy-equivalent 路径 |
|---|---|---|
| PLY | plyfile 内存解析 | Open3D 路径读取，或能严格复现旧项目的 Open3D API |
| DRC | DracoPy 内存 decode | 旧项目实际 DracoPy path/read/decode 路径 |

每一路分别测两种边界：

- `legacy boundary`：尽量复现旧项目，从路径读取到旧 backend 返回/整理终点。
- `current boundary`：payload 已驻留内存，到独立 canonical float32 XYZ 与 uint8 RGB。

实验应固定 warmup、sample count、p50/mean，并交错执行候选，记录 runtime/backend 版本。结果至少拆分回答：

- `backend effect`：plyfile 与 Open3D、当前/旧 DRC API 的差异；
- `boundary effect`：磁盘与旧 endpoint 对比内存到 canonical endpoint；
- `asset-scale effect`：小 tile 与更大点数资产；
- `output-conversion effect`：backend output 到独立 canonical arrays 的 copy/stack/astype。

先完成小规模因果隔离，再决定是否扩大到更多 tile/frame；不应先扩大样本却继续混用边界。

## 15. 限制与待确认事项

- 旧本地 CSV 被 Git 忽略，缺少 run manifest、commit hash、repeat count 和环境版本。
- 本轮没有运行 profiler、microbenchmark 或任何新点云测量，因果解释仍受静态代码与既有结果限制。
- 未读取或 hash DRC 大文件内容，也未验证旧压缩资产的 bitstream metadata。
- 未确认旧 Open3D `.numpy()` 与 DracoPy/NumPy `asarray` 的实际 copy 行为。
- 未确认旧结果的 CPU、OS、Python、Open3D、DracoPy 与 Draco executable 版本。
- 当前 handoff 的内部拟合状态与 allocation 操作状态必须分开理解；前者保留，后者暂缓。

## 16. 阶段 1B.2 后续结果

阶段 1B.2 已按本审查建议完成 4-candidate PLY backend 最小对齐。两条路径输出均通过 canonical point count、dtype、shape、坐标和 RGB 校验；Open3D path API 即使包含磁盘读取，4/4 个候选仍比当前 plyfile 内存路径快超过 2 倍，达到 `strong_support_for_open3d_backend`。

该结果强化了“PLY backend/output-conversion effect 是顺序反转主要因素”的解释，但 Open3D path API 仍不是正式内存驻留 `d_ms`。当前 handoff 继续保持 `review_pending` 与 `temporarily_hold_for_allocation_integration`。完整实验记录见 `PHASE1B2_PLY_BACKEND_ALIGNMENT.zh-CN.md`。

## 17. 阶段 1B.3 后续状态

阶段 1B.3 尝试以 Open3D 0.19.0 `read_point_cloud_from_bytes` 保持正式内存边界，但当前 Windows wheel 对 PLY format 返回空点云。双格式 smoke 中 DRC 成功、PLY 失败，因此没有运行 100-candidate pilot 或生成 v2 handoff。该 blocker 不推翻 1B.2 的 backend 诊断，但说明“path API 很快”不能直接推出“当前 wheel 的 memory API 可用”。allocation 继续 `review_pending`。
