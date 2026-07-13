# 阶段 1A Python 最小测量链路与 Longdress pilot

本文档记录阶段 1A 的 Python 进程内 PLY / DRC 直接测量实现与本机 pilot 状态。文档不记录具体耗时数值；真实记录保存在 git ignored `outputs/`。

## 1. 环境与依赖

本轮使用仓库本地 `.venv`，未修改全局 Python 环境：

- 解释器：CPython 3.13.0，Windows x64；
- 数组：`numpy 2.5.1`；
- PLY：`plyfile 1.1.4`；
- DRC：`DracoPy 2.0.0`；
- 计时 API：`time.perf_counter_ns`。

PLY 后端从 `bytes` 经 `BytesIO` 读取 binary little-endian PLY。DRC 后端直接把内存 `bytes` 交给 `DracoPy.decode`，属于 Python 进程内解码，未使用 `draco_decoder` CLI 或子进程。

## 2. 测量边界

每个候选先在计时外完成 `asset_ref` 定位、文件存在性与 `stat` size 校验、`read_bytes` 预加载。计时区间只覆盖：

```text
payload bytes 已驻留内存
-> PLY parse 或 DRC decode
-> 新建且独立拥有的 positions float32[N, 3] 与 colors uint8[N, 3]
```

输出 dtype、shape、RGB、独立内存所有权以及 metadata point count 一致性均在计时外检查。每轮重新解析或解码，不复用上一轮结果。normals 不属于第一版统一输出。

## 3. 参数与结果语义

本轮每候选 `warmup_count = 2`、`sample_count = 5`，保留 `raw_samples_ms`，并计算 `p50_ms` 与 `mean_ms`。单候选失败会记录 `status/error` 并继续；若进程内 DRC backend 整体不可用，则 DRC 候选统一失败且不会回退到 CLI。

结果 provenance 为 `measured`，同时固定标记：

```text
measurement_scope = longdress_frame1051_pilot
eligible_for_final_model = false
eligible_for_allocation = false
```

这些记录用于下一阶段拟合准备，不代表最终模型输入，也不是候选级 `derived d_hat_ms`。

## 4. CLI

双格式 smoke：

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python -m pcv_dms_benchmark.cli python-pilot `
  --inventory outputs\phase0c_frame1051_inventory.json `
  --sample-plan outputs\phase0c_frame1051_sample_plan.json `
  --data-prep-root E:\Miunaaaa\0-work\code\pcv-stage2-data-prep `
  --out outputs\phase1a_python_smoke.json `
  --warmup 2 --samples 5 --smoke
```

完整 sample plan pilot 使用相同命令但移除 `--smoke`，输出到 `outputs\phase1a_python_pilot.json`。运行时代码不硬编码 data-prep 绝对路径；示例路径仅是本机人工执行线索。

## 5. 测试与真实执行状态

synthetic unittest 覆盖 binary little-endian PLY、ASCII PLY 拒绝、`candidate_key` 定位、磁盘读取与计时顺序、warmup / sample 数量、统计计算、pilot 资格标记和 fake DRC 输出转换。

本机双格式 smoke 成功：一个 PLY 与一个 DRC 候选均完成。随后阶段 0C 的 `max_tiles=5` sample plan 全部执行成功，共 100 个候选，其中 PLY 25 个、DRC 75 个，失败 0 个；所有 decoded point count 均与 metadata 一致。这里不做格式间性能比较。

本地输出：

```text
outputs/phase1a_python_smoke.json
outputs/phase1a_python_pilot.json
```

两个文件均被 `.gitignore` 忽略，不纳入提交。

## 6. 当前未做与下一阶段

本轮未实现 C++ 或 JavaScript benchmark，未拟合 calibrated 模型，未生成 derived `d_hat_ms`，未创建 allocation 输入，未修改外部仓库或点云资产。

下一阶段建议分别对 Python PLY 与 DRC 使用简单、可解释的候选 metadata 特征拟合初版 `d_hat_ms` 模型，并通过留出验证检查误差。在模型与统计策略确认前，本 pilot 不进入 allocation。
