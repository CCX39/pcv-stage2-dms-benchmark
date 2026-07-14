# 阶段 1B.5：修正 d_ms 解析阶段端到端契约

## 1. 决策背景

阶段 0A 至 1B.4 把“完整 payload 已驻留内存，进入明确 parser/decoder，到 canonical arrays 就绪”作为正式 `d_ms` 边界。该边界适合解析核心微基准，但阶段 1B.4 的 NumPy `frombuffer` PLY 路径接近内存解释与数组复制下界，不能代表真实流媒体播放器完整解析模块的端到端开销。

研究者在本阶段确认：Stage2 allocation 最终需要的是传输完成后，实际端侧解析模块处理完整候选并交付 positions/colors 的解析阶段端到端耗时。因此正式指标改名并冻结为 `d_stage_ms`；历史内存核心结果重新分类为 `d_core_ms` 诊断证据。

本阶段没有运行 benchmark、没有重新拟合模型、没有产生新耗时数值，也没有修改 allocation 或历史 v1/v2 JSON。

## 2. 正式 d_stage_ms

```text
d_stage_ms = t_positions_colors_ready - t_parse_stage_start
```

起点：完整候选已完成网络传输，并由上游模块交付实际端侧解析模块；解析模块开始处理候选的瞬间。

终点：以下数组已完整生成并可交给后续渲染模块：

```text
positions: float32[N, 3]
colors:    uint8[N, 3]
```

计入实际 parser/loader/decoder、header/属性解析、DRC 解码、必要中间对象、XYZ/RGB 提取、dtype/layout/颜色转换、内存分配与复制，以及生成目标数组所需的模块内部封装。

排除网络与服务端处理、GPU upload、材质与场景、render、首帧绘制、无关日志/写盘和后续缓存命中。`BufferGeometry` 默认排除；只有未来真实模块终点明确包含时，才能建立新版本 profile。

## 3. d_core_ms

```text
d_core_ms = resident payload -> backend core/specialized converter -> positions/colors ready
```

它用于 backend 诊断、算法下界、特征影响分析和实现对比。默认分类和资格为：

```text
measurement_kind = core_parse_microbenchmark
timing_start = backend_core_entry
timing_end = positions_colors_ready
eligible_for_allocation = false
allocation_integration_status = ineligible_measurement_scope
```

内部验证误差低不等于具备 allocation 资格。若未来证明某 processor 就是目标端完整模块，必须建立并测量新的 `parse_stage_end_to_end` profile，不能只给旧结果换标签。

## 4. 三类输入接口

### 浏览器 Worker

正式目标是完整 `ArrayBuffer` 已到 Worker/解析模块，调用实际 `PLYLoader` / `DRACOLoader` 或确认等价实现，到 positions/colors TypedArray ready。网络、Worker 创建、输入输出 `postMessage`、geometry、GPU 和 render 排除。

### Python bytes

完整 bytes 交付实际 Python parser 后开始，到 positions/colors ready。只有 parser 本身代表实际目标 profile 或确认等价实现，结果才是该 profile 的 `d_stage_ms`。

### Python path

若研究对象就是 path API，起点可以是 `path_delivered_to_loader`，并把 loader 内部 open/read/parse 计入。该结果只代表 path-based Python profile，不代表浏览器 profile。阶段 1B.2 的 path 数据仍只是诊断，因为其目的和采样设计不是正式目标端交付。

## 5. measurement_kind 与兼容策略

代码冻结四类：

- `core_parse_microbenchmark`；
- `parse_stage_end_to_end`；
- `path_loader_diagnostic`；
- `capability_probe`。

起点冻结为 `complete_payload_delivered_to_parser`、`path_delivered_to_loader` 或 `backend_core_entry`；终点只允许 `positions_colors_ready`。

新生成的 calibration 和 handoff 必须携带并继承 source `measurement_kind`。旧 schema 缺字段时，读取代码保守解释为 `core_parse_microbenchmark` / `backend_core_entry`，从而保持历史 JSON 可读但不可被误标 ready。

## 6. Allocation 资格

`eligible_for_allocation = true` 必须同时满足：

1. `measurement_kind = parse_stage_end_to_end`；
2. 环境标识明确；
3. 实际或确认等价 parser/loader/decoder；
4. 完整候选交付解析模块后开始；
5. positions/colors ready 结束；
6. 网络和渲染排除；
7. provenance 完整；
8. 样本及模型验证通过；
9. applicable scope 明确；
10. allocation release gate 通过。

代码 gate 对 core、path diagnostic 和 capability probe 强制返回 `ineligible_measurement_scope`。`parse_stage_end_to_end` 若尚缺其他条件，则是 `review_pending`；所有条件通过才是 `ready_for_provisional_integration`。

## 7. 历史资产分类

| 资产 | profile | measurement_kind | 历史状态 | allocation |
|---|---|---|---|---|
| plyfile v1 measured/calibration/handoff | `python_plyfile_dracopy` | `core_parse_microbenchmark` | `retained_for_audit` | false |
| NumPy v2 measured/calibration/handoff | `python_numpy_fast_ply_dracopy` | `core_parse_microbenchmark` | `retained_as_core_lower_bound` | false |
| 阶段 1B.2 Open3D path | `python_open3d_path_alignment` | `path_loader_diagnostic` | `retained_for_audit` | false |
| 阶段 1B.3 Open3D from-bytes | `python_open3d_windows_from_bytes` | `capability_probe` | `blocked_capability_profile` | false |

v1/v2 仍是其原 profile 下真实的 measured/calibrated/derived 科研记录，不称为伪造或程序错误。重新分类只说明它们不等价于正式 `d_stage_ms`。

权威清单为 `results/measurement_asset_status_v1.json`。历史 JSON 本体未覆盖或删除。

## 8. 代码与测试

新增 `measurement_records.py`，集中处理字段枚举、旧 schema 默认值和 allocation 资格。Python runner 新生成的现有 bytes benchmark 明确写入 core 分类；calibration 继承 measured 分类；measured summary 与 derived handoff 继续继承，并在非正式 scope 下强制 `eligible_for_allocation = false`。

测试覆盖 core/path 不可获得资格、正式 parse stage 在其余条件通过时可以 ready、derived 继承、旧 schema 保守默认、唯一终点，以及历史六个 JSON 的可读取性和固定 SHA-256。

## 9. 当前状态

```text
formal_allocation_metric = d_stage_ms
current_historical_results = d_core_ms / diagnostic
eligible_python_handoff = none
allocation_integration_status = ineligible_measurement_scope
```

此前 v2 的 `review_pending` 是当时模型 release gate 的状态；按本阶段更高层的 measurement scope 资格重新审查后，v1/v2 均明确不可接入 allocation。

## 10. 下一阶段

最高优先级是 JavaScript 浏览器 Worker 的 `parse_stage_end_to_end` 测量设计：

```text
完整 ArrayBuffer 已到 Worker
-> 实际 PLYLoader / DRACOLoader
-> positions/colors TypedArray ready
```

第一版排除 Worker 创建、输入输出 `postMessage`、`BufferGeometry`、GPU upload 和 render。可附加记录 `d_loader_core_ms` 与 `d_array_conversion_ms`，但 Stage2 allocation 只使用通过 release review 的 `d_stage_ms`。

本阶段仅完成设计，不实现 JavaScript benchmark。当前限制仍包括单帧 pilot、缺少真实目标端 profile、尚无 C++/JavaScript measured 数据和跨数据集验证。
