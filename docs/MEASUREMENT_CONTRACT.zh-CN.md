# d_ms 解析阶段端到端测量契约

更新日期：2026-07-14。本文件以阶段 1B.5 的研究决策为当前权威契约，替代此前把“内存 payload 到 canonical arrays 的解析核心”直接称为正式 Stage2 `d_ms` 的表述。

## 1. 正式 allocation 指标

Stage2 allocation 正式使用的候选级解析耗时命名为 `d_stage_ms`：

```text
d_stage_ms = t_positions_colors_ready - t_parse_stage_start
```

它表示候选完成网络传输并由上游传输模块交付端侧解析模块后，实际解析模块从开始处理该完整候选，到 positions/colors 数组完整就绪的解析阶段端到端 wall-clock 耗时。

`d_stage_ms` 不是文件大小、网络下载时间、GPU 上传时间、首帧绘制时间或端到端播放延迟。

## 2. 正式起点与终点

正式起点为：

```text
timing_start = complete_payload_delivered_to_parser
```

即完整候选已完成网络传输，并已交付实际端侧 parser/loader/decoder；在解析模块开始处理候选的瞬间计时。“候选”不等同于“磁盘文件路径”，其接口可以是 `ArrayBuffer`、`bytes` 或被研究 profile 明确采用的 path。

正式终点唯一固定为：

```text
timing_end = positions_colors_ready

positions: float32[N, 3]
colors:    uint8[N, 3]
```

两个数组必须完整生成，可直接交给后续渲染模块。终点不含 normals；也不自动延伸到 geometry、GPU 或屏幕呈现。

## 3. d_stage_ms 计入项

- 实际 parser、loader 或 decoder 调用；
- PLY header 和 vertex 属性解析；
- DRC 解码以及位置、颜色属性提取；
- 实际解析链路所需的中间对象构造；
- XYZ/RGB 数组生成；
- 必要 dtype、layout 和颜色范围转换；
- 必要内存分配与复制；
- 为生成 positions/colors 所必需的解析模块内部封装调用；
- 每轮产生新的解析或解码结果，不使用已解码对象缓存。

## 4. d_stage_ms 排除项

- 网络传输、HTTP、服务端处理和下载排队；
- GPU upload；
- Three.js `BufferGeometry` 创建，除非未来真实模块明确把它纳入版本化终点；
- 材质构造、场景挂载、渲染和首帧绘制；
- 与解析无关的日志、manifest 查询、hash 和结果写盘；
- 后续缓存命中复用；
- data-prep CLI decode-integrity validation。

Worker 创建和输入/输出 `postMessage` 暂不纳入第一版正式边界。若未来改变，必须建立新的 profile 与契约版本，不能静默混入现有 `d_stage_ms`。

## 5. 解析核心诊断指标

保留诊断量 `d_core_ms`：

```text
d_core_ms = 已准备的内存 payload
          -> 明确的解析核心或专用转换器
          -> positions/colors ready
```

`d_core_ms` 可用于 backend 诊断、算法下界、实现对比，以及分析 point count、file size、QP 等因素。它默认：

```text
measurement_kind = core_parse_microbenchmark
eligible_for_allocation = false
```

只有未来证明该 processor 就是目标端完整解析模块或经确认等价实现，并通过专门 release review，才能按新的 `parse_stage_end_to_end` profile 重新测量和审查；不能仅修改标签提升历史结果资格。

## 6. Profile 起点解释

### 6.1 浏览器 / Worker 正式目标

```text
完整 ArrayBuffer 已到达 Worker 或解析模块
-> 调用实际 PLYLoader / DRACOLoader 或确认等价 parser
-> positions/colors TypedArray ready
```

网络、Worker 启动、输入/输出 `postMessage`、`BufferGeometry`、GPU 和 render 均排除。该 profile 是下一阶段最高优先级。

### 6.2 Python bytes profile

```text
完整 bytes 已交付实际 Python parser
-> parser/decoder 和必要转换
-> positions/colors ready
```

只有当 Python parser 是被研究的实际执行 profile 或经确认等价实现时，结果才可称为该 Python profile 的 `d_stage_ms`。专用 `frombuffer` 下界不能自动取得该资格。

### 6.3 Python path profile

若实际研究对象本身就是 path API，则可使用：

```text
timing_start = path_delivered_to_loader
path 交付 loader -> loader 内部 open/read/parse -> positions/colors ready
```

此时 open/read 属于该 path profile 的解析阶段开销，但结果只能代表该 path-based Python profile，不能自动代表浏览器流媒体 profile。

阶段 2A 已冻结并实测第一版 Python path stage profile：

```text
environment_id          python310_open3d019_dracopy200_path_stage_windows_x64
measurement_kind        parse_stage_end_to_end
timing_start            path_delivered_to_loader
timing_end              positions_colors_ready
filesystem_cache_policy os_managed_repeated_path_load
PLY                      open3d.t.io.read_point_cloud(path)
DRC                      Path.read_bytes() + DracoPy.decode(bytes)
```

PLY 与 DRC 在同一 CPython 3.10.20 环境测量；两者均在计时内执行文件 open/read 和独立 canonical array 生成。该 profile 通过当前 Longdress frame1051 provisional release gate，但其资格严格限于 Python/Open3D/DracoPy/Windows path load 语义，不扩展到浏览器 ArrayBuffer、C++、严格冷缓存或其他版本。

## 7. measurement_kind 与字段

新生成的 measured、calibrated、derived 记录必须携带：

```text
measurement_kind:
  core_parse_microbenchmark
  parse_stage_end_to_end
  path_loader_diagnostic
  capability_probe

timing_start:
  complete_payload_delivered_to_parser
  path_delivered_to_loader
  backend_core_entry

timing_end:
  positions_colors_ready

eligible_for_allocation: true | false

allocation_integration_status:
  ready_for_provisional_integration
  review_pending
  ineligible_measurement_scope
```

calibration 必须继承 source measurement 的 `measurement_kind`；derived handoff 继续继承 calibration。旧 schema 缺少 `measurement_kind` 时，代码保守解释为 `core_parse_microbenchmark`，缺少起点时解释为 `backend_core_entry`。历史 JSON 不原地改写。

## 8. Allocation 资格规则

只有以下条件全部满足，handoff 才可标记 `eligible_for_allocation = true`：

1. `measurement_kind = parse_stage_end_to_end`；
2. `environment_id` 明确对应实际被研究端侧环境；
3. parser/loader/decoder 是实际实现或经确认等价实现；
4. 起点表示完整候选交付实际解析模块；
5. 终点为 `positions_colors_ready`；
6. 网络与渲染没有混入；
7. measured、calibrated、derived provenance 完整；
8. 样本与模型验证通过；
9. `applicable_scope` 明确；
10. allocation release gate 通过。

`core_parse_microbenchmark`、`path_loader_diagnostic` 和 `capability_probe` 无论内部模型误差多低，都必须是 `eligible_for_allocation = false` 和 `allocation_integration_status = ineligible_measurement_scope`。仅满足 normalized MAE 阈值不能取得 allocation 资格。

## 9. 环境隔离原则

计划中的 C++、Python、JavaScript Worker 环境必须独立记录，不能混成同一个 `d_stage_ms`。不同 Python 版本、backend、浏览器、Draco runtime、计时 API 或输入接口也属于不同 execution profile。每次 Stage2 实验只能使用与明确目标环境一致的 handoff。

## 10. 输入资产范围

正式待测资产仍仅包括：

- Stage2 tile binary PLY；
- Stage2 tile DRC。

raw ASCII full-cloud PLY 只用于来源追溯和 data-prep 输入背景，不进入正式测量、抽样或拟合样本集。当前 Stage2 PLY 是 binary little-endian tile 资产；tile 切分、ASCII 到 binary 转换和低 PDL 嵌套抽样改变单资产点集与文件组织。

当前 Longdress frame1051 pilot 的 active DRC profile 为：

```text
draco_encoder -point_cloud -i <input> -o <output> -cl 10 -qp <8|10|12>
```

`-point_cloud`、`cl=10` 和 `qp in {8,10,12}` 有直接 metadata/命令证据。`qc`、`qg` 等未显式参数不得推断；其行为依赖实际 Draco executable 默认值，正式测量必须记录版本和环境。该 profile 只是当前 pilot，不是永久理论约束。

## 11. Provenance 语义

- `measured`：对真实样本重复测量得到的统计；
- `calibrated`：由 measured 样本拟合的环境/profile 专属模型及验证结果；
- `derived`：模型为大量候选推导的 `d_hat_ms`；
- `proxy`：有工程解释但尚未直接测量或标定的代理值；
- `synthetic`：测试或受控验证的人造数据。

`measurement_kind` 与 provenance 是两个正交维度。一个记录可以是 `provenance = measured` 且同时是 `measurement_kind = core_parse_microbenchmark`；这不使它具备 allocation 资格。derived 不能表述为逐候选 measured，allocation 旧 proxy 不能表述为 measured。

## 12. 最小记录与统计

直接测量至少记录候选稳定身份、environment/profile、representation、资产 metadata、`measurement_kind`、起止边界、backend/runtime、warmup、sample count、raw samples、p50、mean、状态与 warning。后续正式记录可继续保留 p95 与离散度。

当前 Python frame1051 provisional 拟合以 `p50_ms` 为目标，并按 `tile_id` 做 leave-one-tile-out；该选择不自动冻结为所有未来环境的永久统计策略。p50 表示中位数，是典型单次耗时候选。

## 13. 历史资产重新分类

权威状态清单为：

```text
results/measurement_asset_status_v1.json
```

- plyfile v1 measured/calibration/handoff：`core_parse_microbenchmark`，`retained_for_audit`，不可接入 allocation；
- NumPy v2 measured/calibration/handoff：`core_parse_microbenchmark`，`retained_as_core_lower_bound`，不可接入 allocation；
- 阶段 1B.2 Open3D path 对齐：`path_loader_diagnostic`，不可接入 allocation；
- 阶段 1B.3 Open3D from-bytes：`capability_probe` / blocked profile，保留审计。

上述重新分类不表示历史测量伪造或实现错误，也不删除、覆盖或改写历史 JSON；它只修正这些结果相对于正式 `d_stage_ms` 的解释和资格。

## 14. 当前合格 Python path handoff

阶段 2A 新增：

```text
results/python_path_stage_frame1051_measured_summary_v1.json
results/python_path_stage_frame1051_calibration_v1.json
handoff/python_path_stage_frame1051_candidate_dms_v1.json
```

前两项分别是 `measured` 与 `calibrated` 证据；handoff 是覆盖 800 个候选的 `derived d_stage_ms`。只有 handoff 标记 `eligible_for_allocation = true`，且适用范围为 `provisional_python_path_profile` / Longdress frame1051 / Windows x64 / OS-managed repeated path load。该资格不改变历史 core/diagnostic 资产的 ineligible 状态，也不表示已完成 allocation 接入。

## 15. 下一阶段

最高优先级是 JavaScript 浏览器 Worker 的 `parse_stage_end_to_end` 测量设计：完整 `ArrayBuffer` 到达 Worker 后，计时实际 `PLYLoader` / `DRACOLoader` 或确认等价实现，终点为 positions/colors TypedArray ready。第一版排除 Worker 创建、输入输出 `postMessage`、`BufferGeometry`、GPU upload 和 render。

可同时记录诊断分解：

```text
d_loader_core_ms
d_array_conversion_ms
d_stage_ms
```

Stage2 allocation 最终只使用通过资格审查且与所选环境一致的 `d_stage_ms`。阶段 2A 没有实现或运行 JavaScript benchmark；后续 C++ 与 JavaScript 仍需独立建立 measured、calibrated 与 derived 资产。
