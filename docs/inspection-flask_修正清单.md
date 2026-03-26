# inspection-flask 修正清单

更新时间：2026-03-26  
检查范围：`inspection-flask/**/*`  
检查约束：忽略尚未导入的包、模块和文件，只基于当前已存在代码检查业务逻辑是否严谨。  
说明：本清单按时间倒序整理，今天的在前，历史记录在后。

---

## 2026-03-26

### 本次结论

当前代码已经具备 `person -> crop -> workwear -> violation` 的基础链路，也能在接口层面兼容 YOLOv11 风格的 `ultralytics.YOLO(...)` 模型调用；但如果目标是“加油站工人未穿戴工服检测”，现有规则口径还不够严谨，主要风险集中在“监管对象不准”“合规判定过松”“时序判定按帧而不是按人”这三类问题。

### P0（优先修正）

| ID | 问题 | 影响 | 修正动作 | 代码定位 |
| ---- | ---- | ---- | ---- | ---- |
| 20260326-P0-1 | 规则把 ROI 内所有 `person` 都当成监管对象，没有区分工人、顾客、路人 | 加油站场景中顾客进入画面时也可能被判成“未穿工服”，误报风险很高 | 在第一阶段或规则层补充“员工身份”约束；至少不能把所有 `person` 默认视为工服监管对象 | `inspection-flask/utils/models.py:48`, `inspection-flask/utils/models.py:60`, `inspection-flask/violation_module/vio_workwear_missing.py:43`, `inspection-flask/violation_module/vio_workwear_missing.py:48` |
| 20260326-P0-2 | “穿工服”采用任意标签命中即合规的 `OR` 口径 | 只识别到一个局部部件也会被判为合规，不适合“必须按规范穿戴工服”的严格场景 | 明确业务口径，是“任一工服特征即合规”还是“完整工服组合才合规”；规则层应与标注口径一致 | `inspection-flask/settings.py:37`, `inspection-flask/applications/common/hk_custom_threading_plus.py:138`, `inspection-flask/violation_module/vio_workwear_missing.py:127` |
| 20260326-P0-3 | 时序判断按“违规帧占比”触发，而不是按“同一人持续违规”触发 | 多个不同人分散出现在窗口内，也可能累计成一次告警，解释性弱，误报高 | 如果要做严谨监管，应引入按目标维度的连续性约束，至少区分“同一人连续违规”和“不同人拼出来的违规帧” | `inspection-flask/violation_module/vio_workwear_missing.py:35`, `inspection-flask/violation_module/vio_workwear_missing.py:63`, `inspection-flask/applications/common/hk_custom_threading_plus.py:218` |

### P1（建议尽快修正）

| ID | 问题 | 影响 | 修正动作 | 代码定位 |
| ---- | ---- | ---- | ---- | ---- |
| 20260326-P1-1 | ROI 判定要求整个人框完全落在 ROI 内 | 站在边缘、半身入镜、框稍微越界的真实工人会被直接排除，漏报明显 | 改成中心点落入 ROI、关键区域落入 ROI，或采用 IoU / 覆盖比阈值，而不是全框硬包含 | `inspection-flask/applications/common/hk_custom_threading_plus.py:83`, `inspection-flask/applications/common/hk_custom_threading_plus.py:89`, `inspection-flask/violation_module/vio_workwear_missing.py:115` |
| 20260326-P1-2 | 有效目标仅靠固定像素面积阈值 `MIN_PERSON_BOX_AREA=3000` 过滤 | 不同机位、分辨率、焦距、安装高度下稳定性差，远处员工容易漏检，近处顾客更容易被纳入 | 改成与分辨率、ROI、人体高度比例相关的阈值，或分机位配置 | `inspection-flask/settings.py:46`, `inspection-flask/applications/common/hk_custom_threading_plus.py:112`, `inspection-flask/applications/common/hk_custom_threading_plus.py:123` |
| 20260326-P1-3 | 类别名绑定过死：第一阶段必须是 `person`，第二阶段必须命中 `WORKWEAR_LABELS` 指定字符串 | 虽然能接 YOLOv11 权重，但不利于后续引入更贴近业务的 `worker/customer/full_uniform/no_uniform` 类别体系 | 将类别映射做成配置或适配层，不要把业务语义直接写死在类名字符串里 | `inspection-flask/utils/models.py:58`, `inspection-flask/utils/models.py:60`, `inspection-flask/settings.py:37` |

### P2（优化项）

| ID | 问题 | 影响 | 修正动作 | 代码定位 |
| ---- | ---- | ---- | ---- | ---- |
| 20260326-P2-1 | `IMGSZ`、`VIDEO_CRT`、`VIDEO_CRT_SECONDS`、`images_num` 这类配置没有真正进入当前判定链路 | 调参时容易误判系统行为，以为改了配置就会生效 | 删除无效配置，或明确接入实际推理 / 取帧 / 窗口控制逻辑 | `inspection-flask/settings.py:22`, `inspection-flask/settings.py:74`, `inspection-flask/settings.py:75`, `inspection-flask/settings.py:83` |

### 与 YOLOv11 适配的判断

1. 从模型接口看，可以适配 YOLOv11。
2. 从业务规则看，当前逻辑还不能严谨支撑“加油站工人未穿戴工服检测”。
3. 如果摄像头画面只覆盖员工专属区域、模型标签完全按当前字符串约定训练、并接受“任一工服部件即合规”的口径，这套代码可以先跑。
4. 如果要用于真实加油站生产环境，建议优先修正 `20260326-P0-*` 三项，否则误报和漏报都会比较明显。

---

## 2026-03-25

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
