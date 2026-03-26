# inspection-flask 修正清单

更新时间：2026-03-26  
检查范围：`inspection-flask/**/*`  
检查约束：忽略尚未导入的包、模块和文件，只基于当前已存在代码检查业务逻辑是否严谨。  
说明：本清单按时间倒序整理；同一天如有多轮检查，以当日最新复审结果为准。

---

## 2026-03-26（最新复审）

### 本轮已确认的进展

1. 人员检测与工服检测的主链路已经完成 YOLOv11 风格封装，入口统一在 `utils/models.py`。
2. ROI 口径已从“整框完全包含”调整为“中心点落入 ROI”，比旧逻辑更符合边缘作业人员场景。
3. 工服合规判断已经参数化，支持 `WORKWEAR_COMPLIANCE_MODE` 与 `WORKWEAR_REQUIRED_LABELS`，不再完全写死在逻辑中。
4. 时序判定已开始从“按帧统计”向“按轨迹统计”演进，引入了 `SimpleIoUTracker` 做基础关联。
5. 结合当前数据集样例，二阶段数据标签基本是单类 `clothes` 正样本，因此当前 `WORKWEAR_LABELS = ["clothes"]`、`WORKWEAR_COMPLIANCE_MODE = "any"` 与现有标注口径是一致的。

### 当前结论

当前代码比上一轮更接近“可用版本”，尤其是在 ROI、配置化和时序判定方向上已经做了实质修正。  
但如果目标是“在真实加油站共享作业区稳定识别员工未穿工服”，仍有几项关键逻辑问题没有闭合，主要集中在：监管对象边界、轨迹判定有效性、告警证据一致性。

### P0（优先修正）

| ID | 问题 | 影响 | 修正动作 | 代码定位 |
| ---- | ---- | ---- | ---- | ---- |
| 20260326-R2-P0-1 | 当前监管对象仍然是 ROI 内所有 `person`，并没有真正区分员工与顾客 | 在你给出的这种加油站前庭画面中，顾客与员工共享区域，只要顾客未命中 `clothes`，仍可能被纳入“未穿工服”统计，核心混淆问题仍未根治 | 在业务上补“谁受工服约束”的约束条件；若短期无法补监督信号，至少只能在员工专属 ROI 内使用该规则 | `inspection-flask/settings.py:38`, `inspection-flask/utils/models.py:53`, `inspection-flask/violation_module/vio_workwear_missing.py:39` |
| 20260326-R2-P0-2 | 新的轨迹判定仍可能被“只出现 1 帧的人”直接触发 | 某个目标如果只出现 1 次且未检出工服，就会得到 `1/1 = 1.0`，直接满足 `TEMPORAL_TRIGGER_RATIO = 0.6`；这与“同一人持续违规才触发”的设计目标不一致 | 为轨迹触发补充最少出现帧数、最少连续违规帧数或最短停留时间约束 | `inspection-flask/violation_module/vio_workwear_missing.py:47`, `inspection-flask/violation_module/vio_workwear_missing.py:67`, `inspection-flask/settings.py:69` |
| 20260326-R2-P0-3 | `SimpleIoUTracker` 的关联假设与当前取帧节奏不匹配 | 当前抓图周期仍是 `110` 秒，远大于 IoU 跟踪适用的短时连续帧场景；同一油机位置前后两帧很可能已换人，导致 track_id 不可信，进而影响整条时序规则 | 让采样频率与跟踪方式匹配；否则“按轨迹判定”在逻辑上不成立 | `inspection-flask/applications/common/hk_custom_threading_plus.py:14`, `inspection-flask/applications/common/hk_custom_threading_plus.py:115`, `inspection-flask/settings.py:94`, `inspection-flask/applications/__init__.py:106` |
| 20260326-R2-P0-4 | 规则虽计算了 `triggered_track`，但存证仍会落到所有违规人的最高置信度帧上 | 触发告警的轨迹和最终保存的证据图可能不是同一个人，导致“触发原因”和“证据对象”不一致，汇报和复核时解释困难 | 存证时应与真正触发阈值的轨迹绑定，而不是继续从全量违规框中选最高分 | `inspection-flask/violation_module/vio_workwear_missing.py:56`, `inspection-flask/violation_module/vio_workwear_missing.py:67`, `inspection-flask/violation_module/base.py:136`, `inspection-flask/violation_module/base.py:171` |

### P1（建议尽快修正）

| ID | 问题 | 影响 | 修正动作 | 代码定位 |
| ---- | ---- | ---- | ---- | ---- |
| 20260326-R2-P1-1 | `MIN_PERSON_AREA_MODE` 只在构建 `person_contexts` 时生效，规则引擎二次校验仍只看绝对面积 | 如果后续切换到 `relative` 模式，多机位或多分辨率下会出现“前面放进来、后面又按旧口径筛掉”的配置语义不一致问题 | 统一面积过滤口径，避免构建阶段和规则阶段各用一套标准 | `inspection-flask/applications/common/hk_custom_threading_plus.py:197`, `inspection-flask/applications/common/hk_custom_threading_plus.py:211`, `inspection-flask/violation_module/vio_workwear_missing.py:105`, `inspection-flask/violation_module/vio_workwear_missing.py:136` |
| 20260326-R2-P1-2 | 辅助模块 `logic_judge.py` 仍然保留旧的“按帧统计 + 任一标签即合规”逻辑 | 主链路已经改成“按轨迹 + 可配置工服模式”，但辅助判断逻辑没有同步，会导致调试脚本、可视化工具或后续测试结果与真实主流程不一致 | 保持辅助模块与主链路语义一致，避免后续调试被旧逻辑带偏 | `inspection-flask/applications/common/logic_judge.py:41`, `inspection-flask/applications/common/logic_judge.py:56` |

### P2（优化项）

| ID | 问题 | 影响 | 修正动作 | 代码定位 |
| ---- | ---- | ---- | ---- | ---- |
| 20260326-R2-P2-1 | 当前实时采集链路仍主要依赖 `frame_path` 调试图输入 | 对离线验证足够，但对真实摄像头联调和生产落地仍有明显距离 | 下一阶段需要补齐真实视频流或海康 SDK 取帧链路，并完成与规则线程联调 | `inspection-flask/applications/common/hk_recorder_threading.py:18` |

### 当日复审结论

1. 这轮修正已经显著改善了上一版“完全按帧判违规”的问题，方向是对的。
2. 但由于当前数据集只标注了 `clothes` 正样本，没有提供“员工身份/受监管对象”信息，所以共享场景下的 customer/worker 混淆依然存在。
3. 当前最需要优先收口的不是模型版本，而是“轨迹判定是否真的可信”以及“证据图是否和触发对象一致”。
4. 因此，`20260326-R2-P0-*` 四项仍然是下一阶段最优先要处理的逻辑问题。

---

## 2026-03-25（历史记录，部分问题已在 2026-03-26 得到缓解）

检查范围：`inspection-flask/**/*`  
检查约束：仅基于当时已存在代码，重点检查权限边界、线程一致性、接口健壮性和运行链路完整性。

### 结论概览

结合 `docs/inspection-flask_文件职责与YOLOv11升级分析.md` 中关于 YOLOv11 升级后数据流的拆分，当时的主链路已经基本成型，但仍存在以下高优先级问题：

1. 权限过滤存在越权窗口，主要在摄像头列表和违规记录查询接口。
2. 线程生命周期和共享状态同步存在竞态条件。
3. 数据库状态与检测线程状态可能出现不一致。
4. 输入参数校验不足，接口鲁棒性不够。

### P0（必须优先修正）

| ID | 问题 | 影响 | 修正动作 | 代码定位 |
| ---- | ---- | ---- | ---- | ---- |
| 20260325-P0-1 | `/hk_camera/data` 在传入未授权 `stationId/parentId` 时会退化为宽查询 | 可能返回超出当前用户权限范围的数据 | 对未授权的 `stationId/parentId` 直接返回空结果或 `403`，不要回退到宽过滤条件 | `inspection-flask/applications/view/system/hk_camera.py:50`, `inspection-flask/applications/view/system/hk_camera.py:58`, `inspection-flask/applications/view/system/hk_camera.py:63` |
| 20260325-P0-2 | 违规记录接口缺少部门 / 分局数据权限过滤 | 具备页面权限的用户可能读取跨单位违规记录 | 在 `/violations` 与 `/violations/camera/<id>` 增加 `dept_auth()/sub_auth()` 过滤，并校验 `camera_id` 归属 | `inspection-flask/applications/view/system/hk_camera.py:410`, `inspection-flask/applications/view/system/hk_camera.py:445` |
| 20260325-P0-3 | 启用摄像头时先改数据库状态，再尝试启动线程 | 线程启动失败时会留下“数据库已启用、线程未运行”的漂移状态 | 将“启用数据库 + 启线程”做成原子流程；线程失败时回滚启用状态，或改为线程成功后再提交启用状态 | `inspection-flask/applications/view/system/hk_camera.py:345`, `inspection-flask/applications/view/system/hk_camera.py:383` |
| 20260325-P0-4 | `stop_thread()` 处理中先移除线程引用再等待退出 | 线程超时未退出时会形成幽灵线程，重启时可能重复拉起同一 camera 的检测线程 | 先 `stop + join`，确认退出后再移除；超时线程要显式标记，阻止重复启动 | `inspection-flask/applications/common/hk_custom_threading_plus.py:289`, `inspection-flask/applications/common/hk_custom_threading_plus.py:293` |
| 20260325-P0-5 | 帧与时间戳缓存分离写入且无统一保护 | 可能读到不一致的“帧-时间戳”组合，导致重复处理或漏处理 | 统一成单对象原子更新，并在读写两侧做好并发保护 | `inspection-flask/applications/common/hk_recorder_threading.py:63`, `inspection-flask/applications/common/hk_recorder_threading.py:64`, `inspection-flask/applications/common/hk_custom_threading_plus.py:47`, `inspection-flask/applications/common/hk_custom_threading_plus.py:48` |

### P1（建议尽快修正）

| ID | 问题 | 影响 | 修正动作 | 代码定位 |
| ---- | ---- | ---- | ---- | ---- |
| 20260325-P1-1 | 列表排序字段 `sort` 未做白名单校验 | 非法字段会触发异常并导致 `500` | 增加可排序字段白名单，不合法值回退到默认字段 | `inspection-flask/applications/view/system/hk_camera.py:47`, `inspection-flask/applications/view/system/hk_camera.py:86` |
| 20260325-P1-2 | `/add_dept`、`/add_room` 使用非幂等方式写库 | 重复访问会重复插入关系数据，且不符合 REST 语义 | 改成 `POST`，补唯一约束或“已存在则跳过”逻辑，并返回结构化结果 | `inspection-flask/applications/view/system/hk_camera.py:269`, `inspection-flask/applications/view/system/hk_camera.py:301` |
| 20260325-P1-3 | `save/update` 缺少关键字段合法性校验 | 脏数据可能入库，后续线程或取帧阶段异常 | 增加参数校验层，对空值、IP、端口、channel 等做严格校验 | `inspection-flask/applications/view/system/hk_camera.py:207`, `inspection-flask/applications/view/system/hk_camera.py:234` |
| 20260325-P1-4 | `_resolve_violate_rule` 缓存缺少失效策略 | 规则表变更后可能长时间命中旧映射 | 为缓存增加 TTL 或在规则更新时主动清理 | `inspection-flask/applications/view/system/hk_camera.py:549` |
| 20260325-P1-5 | `rule_name` 的默认值硬编码在逻辑中 | 扩展规则或多语言时维护成本高 | 将默认展示名挪到配置或规则表，不要在逻辑层硬编码中文字符串 | `inspection-flask/applications/view/system/hk_camera.py:598` |
| 20260325-P1-6 | 告警抑制期间窗口语义不够清晰 | 抑制窗口结束后可能携带历史样本再次触发，不利于解释 | 抑制命中时清空窗口，或只保留抑制后新帧再判定 | `inspection-flask/applications/common/hk_custom_threading_plus.py:229` |

### P2（优化项）

| ID | 问题 | 影响 | 修正动作 | 代码定位 |
| ---- | ---- | ---- | ---- | ---- |
| 20260325-P2-1 | `main.py` 在当时的分析中被视作维护噪音入口 | 容易让人误解真实启动入口 | 删除无用入口，或明确其用途 | `inspection-flask/main.py:1` |
| 20260325-P2-2 | 采集链路当时仅实现 `frame_path` 读图调试 | 与“摄像头实时采集”的目标不完全一致 | 在既有框架下补齐 RTSP / 海康 SDK 读取实现，`frame_path` 仅保留为调试后备 | `inspection-flask/applications/common/hk_recorder_threading.py:18` |
| 20260325-P2-3 | 日志目录与日志文件变量语义曾不够清晰 | 增加理解成本，容易误用 | 拆分为目录变量和文件变量，避免语义混用 | `inspection-flask/settings.py:69`, `inspection-flask/settings.py:71` |

### 历史修复顺序建议

1. 先修权限问题：`20260325-P0-1`、`20260325-P0-2`。
2. 再修线程一致性：`20260325-P0-4`、`20260325-P0-5`、`20260325-P1-6`。
3. 再修启停原子性：`20260325-P0-3`。
4. 最后补接口健壮性和维护项：`20260325-P1-*`、`20260325-P2-*`。
