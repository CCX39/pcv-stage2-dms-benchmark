# 当前项目状态

更新日期：2026-07-14。本文档记录阶段 1B.5 解析阶段端到端契约修正后的本机状态；较早章节保留历史过程，当前契约与 allocation 资格以第 22 节以后为准。

## 1. 项目与 Git 基线

本仓库为 Stage2 allocation 准备环境专属候选级 CPU 处理耗时。阶段 0A/0B 已冻结基础契约，阶段 0C 已完成 frame1051 的 800-candidate inventory 与抽样计划，阶段 1A 已完成 Python 真实测量，阶段 1B 已完成 provisional 模型标定和 derived handoff。阶段 1B.1 对旧 Python benchmark 与当前结果的相反排序进行了只读审查。

阶段 1B.1 开始时：

```text
E:\Miunaaaa\0-work\code\pcv-stage2-dms-benchmark
## main...origin/main
7610362 feat: calibrate Python d_ms pilot models
```

远程 `origin` 指向 `https://github.com/CCX39/pcv-stage2-dms-benchmark.git`。本阶段不执行 push。

## 2. 当前 Python measured 与 calibrated 状态

环境为 CPython 3.13.0、numpy 2.5.1、plyfile 1.1.4、DracoPy 2.0.0，`environment_id = python_windows_x64`。

阶段 1A pilot 为 100/100 成功：PLY 25、DRC 75，覆盖 5 个 tile。磁盘读取位于计时外；两条路径都在计时内生成独立 `float32[N,3]` positions 与 `uint8[N,3]` colors；每候选 warmup 2、sample 5，以 p50 为阶段 1B 拟合目标。

阶段 1B 选中模型：

```text
PLY P1: d_hat_ms = 0.15954514764960334
                     + 3.7770090745876392 * (point_count / 1000)
normalized_mae = 0.007476571814053519

DRC D1: d_hat_ms = -0.029712238641829095
                     + 0.23967649584133888 * (point_count / 1000)
normalized_mae = 0.020813844203006367
```

阶段 1B 的 grouped validation 和全 inventory 检查通过。审查未发现 ns/ms 换算、point count、RGB、缓存复用、p50 或 feature scale 错误。模型忠实反映当前 measured pilot，但其低误差只说明当前 5-tile 样本内关系稳定。

## 3. 阶段 1B.1 审查结论

旧项目确有 DRC 慢于 PLY 的本地 CSV 证据，当前项目确有相反排序的 measured 证据。两套实验不具备直接可比性，关键差异包括：

- 当前 PLY 使用 plyfile + `BytesIO`，旧 PLY 使用 Open3D path API。
- 当前排除磁盘读取，旧项目把 PLY/DRC 文件读取包含在 parser timer 内。
- 当前强制生成独立 canonical arrays；旧项目只到 backend arrays，没有统一 dtype/ownership 契约。
- 当前资产是 612–35,548 点的 G128 tile；旧 Longdress 资产是 7,658–765,821 点的降采样 full-cloud。
- 旧 DRC 显式组合 qc，当前 active profile 未显式 qc/qg。
- 当前使用 warmup 2、sample 5、p50；旧项目无显式 warmup，实际 repeat 未写入 CSV，并用 mean。

当前 PLY 路径在 `column_stack` 后执行显式 copy，DRC 路径没有等价 stack 中间步骤。这是可能影响相对耗时的直接代码事实，但不是当前 canonical 输出契约的实现错误。完整证据等级、结果范围和对照表见 `PHASE1B1_LEGACY_PYTHON_DISCREPANCY_AUDIT.zh-CN.md`。

## 4. Handoff 状态

已纳入 Git 的交付仍为：

```text
results/python_frame1051_measured_summary_v1.json
results/python_frame1051_calibration_v1.json
handoff/python_frame1051_candidate_dms_v1.json
```

handoff 覆盖 800 个候选，其中 PLY 200、DRC 600，使用 `provenance = derived`，不是 800 个逐候选 measured 结果。本轮未修改上述 JSON，也未改变其中阶段 1B 的内部判定字段。

操作层面的当前状态为：

```text
review_status = review_pending
allocation_integration_status = temporarily_hold_for_allocation_integration
```

`recommended_for_allocation_pilot = true` 仅表示模型通过阶段 1B 的内部完整性与 normalized MAE 阈值。阶段 1B.2 已完成最小 PLY backend 诊断，但尚未冻结符合正式内存边界的新 PLY profile，因此 allocation 仍暂缓接入。

## 5. 旧项目只读状态

审查开始时：

```text
E:\Miunaaaa\0-work\code\PointCloud_Benchmark
## main...origin/main
?? scripts/plot_time_vs_point_count_filtered.py
cb3a197 修改说明：readme更新
```

既有未跟踪脚本 `scripts/plot_time_vs_point_count_filtered.py` 未被修改。旧 benchmark、`pcv-stage2-allocation`、`pcv-stage2-data-prep` 均保持只读；本轮没有运行旧 benchmark、没有生成点云或新测量结果。

## 6. Reference 与交付完整性

`reference/Decode_Worker.js` 未修改，其阶段基线 SHA-256 为：

```text
0747B51E9983E59ACC5E911047AE7EBC71213303A60EC7B0548329101775E56C
```

阶段 1B.2 仍未修改 `results/`、`handoff/` 或 reference；本轮只新增诊断代码、最小测试、可选 Open3D 依赖声明和中文文档。

## 7. 当前限制

- 只完成 Longdress frame1051、5 个测量 tile、Python 环境的 provisional 标定。
- 尚未完成 Longdress 多帧、其他数据集、C++ 或 JavaScript 测量与模型。
- 旧结果缺少实际 Python/Open3D/DracoPy/Draco 版本、repeat count、机器快照和受控 run manifest。
- 阶段 1B.2 已在 4 个候选上隔离 PLY backend/output-conversion 差异，但尚未验证正式内存边界、更多 tile/frame 或运行时泛化。
- allocation 仓库尚未修改，且当前建议暂缓接入 handoff。

## 8. 阶段 1B.1 原对齐建议

阶段 1B.1 建议先做小规模对齐而不是直接扩大 allocation 使用范围：在同一批 frame1051 tile 上对照当前 plyfile 与 legacy-equivalent Open3D PLY 路径，并进一步隔离 boundary effect。

阶段 1B.2 已完成其中最小 PLY backend 诊断，结果见下一节；Open3D 正式内存输入边界及更大范围复核仍待下一阶段完成。

## 9. 阶段 1B.2 PLY backend 对齐

本阶段新增 `ply-backend-align` 诊断命令，仅选择阶段 0C 计划中 PDL 1.0 point count 最小和最大的 tile，并分别测 PDL 0.2/1.0，共 4 个 binary PLY：

```text
gx_0_gy_4_gz_0  PDL 0.2     612 points
gx_0_gy_4_gz_0  PDL 1.0   3,062 points
gx_2_gy_1_gz_1  PDL 0.2   7,109 points
gx_2_gy_1_gz_1  PDL 1.0  35,548 points
```

诊断运行环境为本地 ignored `.venv/open3d310`：Python 3.10.20、Open3D 0.19.0、plyfile 1.1.4、numpy 2.2.6。Open3D 0.19.0 无 CPython 3.13 wheel，因此没有修改现有阶段 1A `.venv` 或外部 conda 环境。两条 backend 在同一 3.10 进程内比较。

每候选、每路径 warmup 2、sample 5。plyfile 从已驻留 payload 到 canonical arrays；Open3D 使用 path API，并把磁盘读取、parse 和 canonical 转换全部计时。四项 point count、shape、dtype、独立 ownership、坐标和 RGB 校验全部通过。

Open3D/plyfile p50 比值依次约为：

```text
0.0215
0.0127
0.0108
0.0146
```

4/4 候选均满足 Open3D 至少快 2 倍的规则，结论为 `strong_support_for_open3d_backend`。这强支持当前 plyfile 路径是 Python PLY 耗时偏高的主要因素，并建议下一阶段冻结新的 Open3D Python PLY execution profile。

Open3D path API 包含磁盘读取，不符合当前正式 `d_ms` 的内存驻留起点，因此本轮数值只属于诊断结果，不能直接替换阶段 1B 模型或交给 allocation。原始结果保存在 ignored `outputs/phase1b2_ply_backend_alignment.json`，未纳入 Git。

## 10. 当前 handoff 与下一阶段

阶段 1B 的 `results/python_frame1051_calibration_v1.json` 和 `handoff/python_frame1051_candidate_dms_v1.json` 未修改。当前状态继续为：

```text
review_status = review_pending
allocation_integration_status = temporarily_hold_for_allocation_integration
```

allocation 继续暂缓接入。下一阶段应先明确 Open3D 的正式内存输入方案或经研究者确认版本化调整 Python PLY profile，再只重跑必要的 PLY pilot 候选、重新标定 PLY 模型并生成新版本 handoff；不得把本轮 path-API 诊断值直接视为正式 `d_ms`。

## 11. 阶段 1B.3 实现与环境

本阶段新增 Open3D from-bytes 候选 processor 和 `python-v2-pilot` / `python-v2-calibrate` CLI，参数化复用现有 runner、grouped calibration 与 exporter。正式 processor 只接收内存 bytes，不调用 path API、不创建临时文件；PLY header 必须为 binary little-endian 且含 XYZ/RGB，终点仍为独立 float32 positions 与 uint8 colors。

候选环境：

```text
environment_id python310_open3d019_dracopy200_windows_x64
Python         3.10.20
Open3D         0.19.0
DracoPy        2.0.0
numpy          2.2.6
OS             Windows 10.0.22631 x64
timer          time.perf_counter_ns
```

Open3D 0.19.0 Windows wheel 暴露 `read_point_cloud_from_bytes`，但对 synthetic binary PLY 和真实 frame1051 tile PLY 均输出 unknown-format warning 并返回 0 点。没有 path API 或临时文件 fallback。

## 12. Smoke 与停止判定

ignored 输出：

```text
outputs/phase1b3_python_open3d_smoke.json
SHA-256 C8D2414C93B7E46B109BECDAD16740AE5786070D1486711215DC4044EA4ED3B8
```

同一 Python 3.10 environment 的 smoke 结果：

```text
candidate_count 2
success_count   1
failure_count   1
status          partial_failure
PLY             failed, Open3D returned 0 points
DRC             success, 612 decoded points, p50_ms 0.1582
```

PLY 是 representation-level backend capability failure。按冻结规则，本阶段没有运行 100-candidate pilot，没有拟合 PLY/DRC v2 模型，也没有生成 v2 measured summary、calibration 或 handoff。

## 13. v1/v2 与 allocation 状态

v1 三个 JSON 内容保持不变，其语义状态为：

```text
profile_status historical_plyfile_profile
allocation_status superseded_for_allocation_pilot
retention_status retained_for_audit
```

v1 仍是忠实的 plyfile profile measured/calibrated/derived 历史证据，不称为错误或伪造。v2 尚不存在；没有 100 measured records、没有 grouped validation、没有 800 derived candidates。

```text
phase_status blocked_by_open3d_windows_from_bytes_ply
allocation_integration_status review_pending
```

allocation 继续不修改、不接入。`ready_for_provisional_integration` 不成立。

## 14. 下一阶段建议

先验证一个明确支持 PLY memory reader 的 Open3D wheel/build。每次更换 build 后只做 1-point synthetic 和 1 个真实 tile capability smoke；成功后再重复 1 PLY + 1 DRC smoke。只有双格式 smoke 通过，才允许运行 100-candidate pilot、leave-one-tile-out calibration 和 800-candidate v2 handoff。

若 Windows Open3D memory PLY 路径不可获得，需由研究者版本化选择其他内存 backend 或调整 Python PLY execution profile；不得静默回退 path API 并继续沿用 payload-resident `d_ms` 名称。

## 15. 阶段 1B.4 实现与 environment

阶段开始基线为：

```text
branch   main
upstream origin/main
HEAD     e9fb9f0 feat: switch Python PLY benchmark to Open3D memory IO
worktree clean
```

新增 `numpy_ply_backend.py`，使用 header 驱动的 NumPy structured dtype 与 `numpy.frombuffer` 解释 vertex block，再直接填充新的 canonical arrays。正式 processor 只接收 bytes/只读 buffer，不执行文件读取、不调用 path API、不创建临时文件。

实际 profile：

```text
environment_id python313_numpy_ply_dracopy200_windows_x64
Python         CPython 3.13.0
numpy          2.5.1
DracoPy        2.0.0
plyfile        1.1.4，仅作诊断参照
OS             Windows 10.0.22631 x64
timer          time.perf_counter_ns
```

PLY 与 DRC 均在仓库本地 `.venv` 的同一解释器和 pilot profile 中重新测量，没有复用或拼接 Python 3.10/3.13 的跨环境 measured 值。

## 16. 4-candidate gate 与 smoke

沿用阶段 1B.2 的最小/最大 tile、PDL 0.2/1.0，共 4 个 PLY 候选。NumPy fast 与 plyfile 的 point count、shape、dtype、坐标、RGB 和 ownership correctness 为 4/4 passed；NumPy fast 在 4/4 候选上均比 plyfile 快超过 5 倍。正式 processor 的 file I/O 与 path API 检查均通过，gate 为 passed。

```text
outputs/phase1b4_numpy_ply_alignment.json
SHA-256 A5F547EE440751714A8F41EA41053A610BBACF2EA6695F0B7544E62A58158620
```

一个 PLY + 一个 DRC smoke 为 2/2 success：

```text
outputs/phase1b4_python_numpy_smoke.json
SHA-256 B97A792E3D476249B6CC608CFE02AD35E88BB08B688C727CCFDA6F00BC87CE0E
```

上述输出均位于 ignored `outputs/`，不纳入 Git。

## 17. 100-candidate pilot

阶段 0C sample plan 的 100 个候选全部成功：PLY 25、DRC 75、5 个 tile、失败 0；所有 decoded point count 与 metadata 一致。参数仍为 warmup 2、sample 5，目标统计量为 `p50_ms`。

```text
outputs/phase1b4_python_numpy_pilot.json
SHA-256 AE9F1E499D5D37718EC7FE4DB46CA715649A423B84209B0F793BCCC894C51B40
```

原始 pilot 保留 `raw_samples_ms` 供本地审查，但继续由 Git 忽略。版本化 measured summary 不含 raw samples。

## 18. v2 models 与 release gate

PLY 与 DRC 分别执行按 `tile_id` 的 leave-one-tile-out，未使用 `tile_id`、`candidate_id` 或 `candidate_key` 作为特征。

PLY 选择 P1 point-count linear：

```text
d_hat_ms = 0.012501787380941863
         + 0.002856343196791854 * (point_count / 1000)
MAE               0.001591102836467444 ms
RMSE              0.002289788158323121 ms
median absolute   0.0012876845897889528 ms
normalized MAE    0.04419730101298456
recommended       true
```

DRC 的 D1--D3 grouped validation normalized MAE 约为 0.0283--0.0300，但在全量 600 个 DRC inventory 候选上产生负预测；按既有规则不可选、不可裁剪。最终只能选择全量预测有效的 D0 常数中位数：

```text
d_hat_ms          1.9779
MAE               2.0271573333333333 ms
RMSE              2.6063110693980227 ms
median absolute   1.8221 ms
normalized MAE    1.0249038542561977
recommended       false
```

因此模型和交付文件可审计，但整份 v2 未通过 `normalized_mae <= 0.30` 的双表示 release gate。

## 19. v2 版本化交付与完整性

已新增：

```text
results/python_numpy_frame1051_measured_summary_v2.json
results/python_numpy_frame1051_calibration_v2.json
handoff/python_numpy_frame1051_candidate_dms_v2.json
```

measured summary 为 100 条，PLY 25、DRC 75，不含 `raw_samples_ms`。handoff 为 800 条 derived record，PLY 200、DRC 600；800 个 `candidate_key` 唯一，当前 frame1051 中 800 个 `tile_id + candidate_id` 组合唯一，全部 `d_hat_ms` 有限且大于 0。measured、calibrated、derived provenance 保持分离。

当前状态：

```text
phase_status                  completed_with_release_gate_not_met
allocation_integration_status review_pending
```

v1 继续标记为 `historical_plyfile_profile` / `superseded_for_allocation_pilot` / `retained_for_audit`；阶段 1B.3 继续标记为 `blocked_open3d_windows_from_bytes_profile` / `retained_for_audit`。两者证据均未覆盖或删除。

## 20. 当前限制与下一阶段

- 当前只有 Longdress frame1051、5 个测量 tile、单一 Python environment，尚未完成跨帧或跨数据集验证。
- NumPy parser 仅支持当前受控 Stage2 binary little-endian scalar vertex corpus，不是通用 PLY parser。
- PLY backend 问题已经解决，但 DRC 模型在全量小候选上的正值外推 gate 未通过。
- C++ 与 JavaScript 环境仍未实现；allocation 仓库仍未修改。
- 外部 `pcv-stage2-data-prep`、`pcv-stage2-allocation`、`PointCloud_Benchmark` 均保持只读，`reference/Decode_Worker.js` 未修改。

下一阶段应优先补充小 point-count DRC 候选的 Longdress tile/frame measured 覆盖，或审查天然保持正值且仍可解释的简单模型形式，然后重新执行 grouped validation 与全量正值 gate。在 PLY 与 DRC 均达到阈值前，不建议 allocation 接入整份 v2 handoff。

## 21. 外部仓库本机只读状态

阶段 1B.4 收尾时的实际状态为：

```text
pcv-stage2-allocation
## master...origin/master
5870ccc feat: add frame 1051 integrated proxy validation

pcv-stage2-data-prep
## main...origin/main
8473226 feat: record validated frame 1051 DRC pilot corpus

PointCloud_Benchmark
## main...origin/main
 M README.md
?? README.zh-CN.md
?? reproducibility/
?? scripts/plot_time_vs_point_count_filtered.py
cb3a197 修改说明：readme更新
```

旧 benchmark 当前存在上述既有修改/未跟踪内容，不能再沿用阶段 1B.1 中“仅一个未跟踪脚本”的旧状态描述。本阶段对三个外部仓库只执行 `git status`、`git log` 和 metadata/资产只读访问，没有写入、格式化或提交任何外部文件；上述旧 benchmark 工作区内容保持原样，不纳入本项目提交。

## 22. 阶段 1B.5 正式契约决策

Stage2 allocation 正式指标由旧的宽泛 `d_ms` 表述修正为：

```text
formal_allocation_metric = d_stage_ms
measurement_kind         = parse_stage_end_to_end
timing_start             = complete_payload_delivered_to_parser
timing_end               = positions_colors_ready
```

`d_stage_ms` 从完整候选完成网络传输并交付实际端侧解析模块、模块开始处理的瞬间计时，到 `positions float32[N,3]` 和 `colors uint8[N,3]` 完整就绪为止。实际 parser/loader/decoder、中间对象、必要转换、分配与复制计入；网络、GPU、geometry、场景和 render 默认排除。

原“resident payload -> backend/core converter -> canonical arrays”边界保留为 `d_core_ms`，用于 backend 诊断与算法下界，默认 `measurement_kind = core_parse_microbenchmark`、`eligible_for_allocation = false`。

## 23. 历史资产与 allocation 状态

- plyfile v1 measured/calibration/handoff：`core_parse_microbenchmark`，`retained_for_audit`；
- NumPy v2 measured/calibration/handoff：`core_parse_microbenchmark`，`retained_as_core_lower_bound`；
- Open3D path 对齐：`path_loader_diagnostic`；
- Open3D from-bytes blocker：`capability_probe` / `blocked_capability_profile`。

上述资产全部：

```text
eligible_for_allocation = false
allocation_integration_status = ineligible_measurement_scope
```

这项重分类不否定历史 measured/calibrated/derived 结果真实性，也没有改写六个 v1/v2 JSON。此前 v2 的 `review_pending` 是阶段 1B.4 模型 gate 状态；1B.5 在更高层 measurement scope gate 上明确判定其不具备 allocation 资格。

新增权威状态清单：

```text
results/measurement_asset_status_v1.json
```

## 24. 代码与 schema 状态

新增 `src/pcv_dms_benchmark/measurement_records.py`，冻结四类 measurement kind、三类 timing start、唯一 timing end 和 allocation 资格检查。现有 Python runner 新生成的内存核心测量明确标记为 core；calibration、measured summary 与 derived exporter 继承 source 分类。

旧 schema 缺 `measurement_kind` 时默认解释为 `core_parse_microbenchmark`，缺起点时默认 `backend_core_entry`。core/path/capability 即使请求 ready，也会被 exporter 降级为 `ineligible_measurement_scope`。只有实际 `parse_stage_end_to_end` profile 在环境、实现、边界、provenance、验证、scope 和 release gate 全部通过时才可 ready。

本阶段没有运行任何新 benchmark，没有重新拟合模型，没有产生新耗时数值，也没有修改 allocation。

## 25. 下一阶段建议

最高优先级是 JavaScript 浏览器 Worker 的 `parse_stage_end_to_end` 设计与实现：

```text
完整 ArrayBuffer 已到 Worker
-> 实际 PLYLoader / DRACOLoader
-> positions/colors TypedArray ready
```

第一版排除 Worker 创建、输入输出 `postMessage`、`BufferGeometry`、GPU upload 和 render。可选分解 `d_loader_core_ms` 与 `d_array_conversion_ms`，但 allocation 最终只使用通过 release review 的 `d_stage_ms`。

## 26. 阶段 1B.5 外部仓库只读状态

阶段开始与收尾检查使用相同只读命令。当前实际状态：

```text
pcv-stage2-allocation
## master...origin/master
5870ccc feat: add frame 1051 integrated proxy validation

pcv-stage2-data-prep
## main...origin/main
8473226 feat: record validated frame 1051 DRC pilot corpus

PointCloud_Benchmark
## main...origin/main
?? scripts/plot_time_vs_point_count_filtered.py
b99815b docs: publish Figure 2 benchmark reproducibility record
```

三个外部仓库均未被本阶段写入、格式化或提交。`reference/Decode_Worker.js` 继续只读，SHA-256 仍为 `0747B51E9983E59ACC5E911047AE7EBC71213303A60EC7B0548329101775E56C`。
