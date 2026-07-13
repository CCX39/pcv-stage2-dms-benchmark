# 当前项目状态

更新日期：2026-07-13。本文档记录阶段 1A 完成后的本机真实状态，供后续接力使用。

## 1. 项目定位与阶段状态

本仓库为 Stage2 allocation 准备环境专属候选级 CPU 处理耗时。阶段 0A/0B 已冻结测量边界、运行环境原则、Longdress 路线与记录语义；阶段 0C 已完成 metadata inventory 和 sampling plan；阶段 1A 已完成 Python 进程内 PLY / DRC 最小测量链路及 Longdress frame 1051 pilot。

当前已有真实 `measured` pilot，但尚未拟合 calibrated 模型、生成 derived `d_hat_ms` 或接入 allocation。

## 2. Git 基线

本机仓库：

```text
E:\Miunaaaa\0-work\code\pcv-stage2-dms-benchmark
```

阶段 1A 开始时状态：

```text
## main...origin/main
4c5d9c7 feat: add metadata inventory and sampling planner
```

远程 `origin` 指向 `https://github.com/CCX39/pcv-stage2-dms-benchmark.git`。阶段 1A 提交后不执行 push。

## 3. 阶段 1A 实现

- `python_benchmark.py`：从 inventory 与 sample plan 以 `candidate_key` 定位候选，校验并预加载资产，调用 PLY / DRC 进程内后端，执行 warmup、重复测量与计时外输出校验。
- `measurement_stats.py`：计算 `p50_ms` 与 `mean_ms`。
- `cli.py`：新增 `python-pilot` 子命令与 `--smoke` 双格式子集。
- `test_python_benchmark.py`：使用 synthetic binary PLY 和 fake DRC decoder 验证核心边界。
- `PHASE1A_PYTHON_PILOT.zh-CN.md`：记录环境、后端、执行状态与适用限制。

实现不调用 `draco_decoder` CLI，不把 open/read/stat、JSON 写盘或结果校验计入 `d_ms`。每轮创建新的 `positions: float32[N, 3]` 与 `colors: uint8[N, 3]`；normals 不属于第一版输出。

## 4. Python 环境

仓库本地 `.venv`：

```text
CPython 3.13.0
numpy 2.5.1
plyfile 1.1.4
DracoPy 2.0.0
timer: time.perf_counter_ns
```

`.venv/` 被 git ignore。PLY 使用 `plyfile + BytesIO`；DRC 使用 `DracoPy.decode(bytes)` 进程内解码。

## 5. 真实执行状态

阶段 0C inventory 重新生成后仍为 800 个候选；`max_tiles=5` sample plan 仍为 100 个候选，其中 PLY 25 个、DRC 75 个。

双格式 smoke 成功，随后 100-candidate pilot 成功 100 个、失败 0 个。所有候选使用预热 2 次、测量 5 次，decoded point count 与 metadata 一致。项目文档不记录具体耗时，也不做 PLY / DRC 性能结论。

真实输出位于：

```text
outputs/phase1a_python_smoke.json
outputs/phase1a_python_pilot.json
```

`outputs/` 被 git ignore，结果不纳入提交。记录标记为 `provenance = measured`、`measurement_scope = longdress_frame1051_pilot`，并明确 `eligible_for_final_model = false`、`eligible_for_allocation = false`。

## 6. 测试状态

测试命令：

```powershell
.venv\Scripts\python -m unittest discover
```

阶段 1A 增加后共 19 个测试，覆盖阶段 0C metadata planning 与阶段 1A 测量核心语义。最终定向检查中测试与 `git diff --check` 均通过。

## 7. 外部仓库与 reference

阶段 1A 开始时只读状态：

```text
pcv-stage2-data-prep   ## main...origin/main
pcv-stage2-allocation  ## master...origin/master
PointCloud_Benchmark   ## main...origin/main
                       ?? scripts/plot_time_vs_point_count_filtered.py
```

旧 benchmark 的未跟踪脚本为既有状态，本轮未修改。`reference/Decode_Worker.js` 的阶段 1A 前 SHA-256 为：

```text
0747B51E9983E59ACC5E911047AE7EBC71213303A60EC7B0548329101775E56C
```

最终检查需确认 hash 不变，且三个外部仓库状态与上述基线一致。

## 8. 已冻结事项

- Python pilot 环境为 `python_windows_x64`，与 C++ / JavaScript 结果隔离。
- 计时起点为 payload 已驻留内存，终点为统一 CPU 点云数组生成完毕。
- PLY 正式输入只接受 Stage2 binary little-endian tile PLY；raw ASCII full-cloud PLY 不进入正式测量。
- DRC 必须进程内解码，不允许用 CLI 子进程替代。
- `candidate_key` 是 benchmark 内部唯一主键；不以 `candidate_id` 或数组位置单独定位。
- 第一版使用 `warmup_count = 2`、`sample_count = 5`，保留 raw samples、p50 与 mean。
- 当前 pilot 是直接测量，但不具备最终模型或 allocation 使用资格。

## 9. 尚未完成与下一阶段

尚未完成：

- Python PLY / DRC 的简单可解释模型与留出验证；
- `p50`、`mean` 或其他统计量作为 Stage2 最终输入的选择；
- calibrated / derived 记录落盘格式与 allocation join；
- Longdress 多帧及其他数据集泛化验证；
- C++ 与 JavaScript 独立测量实现。

下一阶段建议先分别拟合 Python PLY 与 DRC 的简单模型，报告留出误差和适用范围；在研究者确认统计策略与验证结果前，不生成 allocation 输入。
