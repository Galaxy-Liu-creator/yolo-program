# 代码修改记录

本文档记录每次代码改动的详细内容，按时间倒序排列。  
每次修改代码后必须同步更新本文档，确保每一步改了什么都有据可查。

---

## 2026-03-22  Section 4 小改：四个文件的 YOLOv11 工服检测适配

### 改动背景

基于 `docs/yolov11_migration_reuse_rewrite.md` 第四部分的建议，对"适合小改"的四个文件进行语义和配置层面的改造，将残留的警务系统耦合替换为加油站工服检测语义。不涉及 import 解析问题（其余文件尚未加入工程）。

---

### 1. `inspection-flask/setting.py`

**改动类型**：配置重命名 + 警务配置注释化 + 新增工服检测常量

**改动内容**：

- `YI_WEIGHT` 重命名为 `PERSON_WEIGHT`，权重路径指向 `person_detect.pt`
- `CLOTH_WEIGHT` 重命名为 `WORKWEAR_WEIGHT`，权重路径指向 `workwear_detect.pt`
- `ER_WEIGHT`、`POSE_WEIGHT` 注释掉，标注"警务专用，已弃用"
- `SMOKE_CONF`、`PHONE_CONF`、`LYING_CONF`、`FACE_CONF`、`CLOTH_CONF` 注释掉，标注"警务专用阈值"
- 新增 `WORKWEAR_CONF = 0.45`（工服检测置信度阈值）
- 新增 `WORKWEAR_LABELS`（合规工服类别列表，配置驱动）
- 新增 `MIN_PERSON_BOX_AREA = 3000`（人员框最小像素面积过滤）
- 新增 `TEMPORAL_WINDOW_SIZE = 5`、`TEMPORAL_TRIGGER_RATIO = 0.6`（时序稳定性参数）
- 新增 `WORKWEAR_VIOLATION_TYPE = "workwear_missing"`（违规规则编码）
- 新增 `alert_suppression_seconds = 300`（告警抑制窗口）
- 新增 `thread_idle_sleep = 2`（检测线程空闲轮询间隔）
- 新增 `DEFAULT_CAMERA_PORT = 8000`、`DEFAULT_CAMERA_CHANNEL = 1`（供 `models.py` HKCamera dataclass 使用）
- 用分区注释块重新组织全文，提升可读性

**改动原因**：  
`hk_custom_threading_plus.py`、`models.py` 等已重写文件依赖上述新常量；旧权重名称保留为注释，便于追溯原 YOLOv5 配置。

---

### 2. `inspection-flask/applications/__init__.py`

**改动类型**：初始化恢复 + 模型加载 TODO 化 + 旧 YOLOv5 import 注释化

**改动内容**：

- 旧 YOLOv5 imports（`Lying_Detect`、`get_all_models`、`select_device`、`FaceRecognition`、`Camera`）保留但转为注释，各行标注"已弃用"或"待补齐后按需恢复"
- 模型加载注释块改写为 TODO 格式：变量名从 `person_detect_model`/`cloth_detect_model` 改为 `person_model`/`workwear_model`；`smoke_phone_detect_model`、`pose_net`、`lying_model`、`face_detect_model` 标注"警务专用，已弃用"；说明待 `utils/models_v11.py` 编写后解注释
- **解注释并激活**（不依赖模型）：
  - `ThreadManager()` 初始化 + `bind_app(app)`，写入 `app.config['hk_threadManager']`
  - `app.config['hk_images'] = {}`、`app.config['hk_images_datetime'] = {}`
  - `HKRecorderThreadManager()` 初始化 + `bind_app(app)`，写入 `app.config['hk_recorder_thread_manager']`
  - 新增 `app.config['violation_events'] = []`（全局违规事件队列）
  - 新增 `app.config['camera_registry'] = {}`（启用摄像头注册表）
- **解注释并激活** `BackgroundScheduler`：
  - 按 `settings.get_image_interval` 周期调度 `hk_recorder_thread_manager.run()`
  - 凌晨 4 点 cron 触发 `hk_threadManager.restart_all_threads()`
  - 延迟 2 个采集周期的一次性 date 触发重启，确保摄像头初始化后再检测

**改动原因**：  
`hk_camera.py` 的 `enable`/`disable` 路由依赖 `hk_threadManager`；图像缓存和调度器不依赖模型，可直接激活；模型加载待第二阶段 `utils/models_v11.py` 完成后再解注释。

---

### 3. `inspection-flask/applications/models/admin_violate_photo.py`

**改动类型**：ORM 模型升级（外键修正 + 新增字段 + 注释清理）

**改动内容**：

- `camera_id` 外键：`db.ForeignKey("admin_camera.id")` → `db.ForeignKey("admin_hk_camera.id")`；comment 改为"海康摄像头ID"，并补充说明"原 admin_camera 已由 admin_hk_camera 替代"
- `station_id` comment：`"询问室ID"` → `"监控站点ID"`
- `dept_id` comment：`"部门ID"` → `"所属单位ID"`（FK 表名 `admin_police_station` 暂保留，待后续统一迁移）
- 新增 `rule_code = db.Column(db.String(64), nullable=True, comment='违规规则编码，如 workwear_missing')`
- 新增 `rule_name = db.Column(db.String(100), nullable=True, comment='违规规则名称，如 未穿工服')`
- 注释掉的 camera relationship 更新为指向 `HKCamera`（`admin_hk_camera`）的预留注释
- 移除已无意义的旧 `load_only` import

**改动原因**：  
海康检测链路写入的 `camera_id` 来自 `admin_hk_camera`，原外键指向 `admin_camera` 会导致数据库外键约束失败；`rule_code`/`rule_name` 字段使违规记录具备自描述能力，不再依赖 `violate_id` 反查规则名称。

---

### 4. `inspection-flask/violation_module/base.py`

**改动类型**：接口修复 + 旧警务注释清理

**改动内容**：

- `save()` 调用 `save_violate_photo()` 时补传 `rule_name=name`，使日志和数据库中实际展示违规名称，而非"违规类型xxx"占位
- 类属性及 `__init__` 中注释清理：
  - `"审讯室/值班室id"` → `"监控站点id"`
  - `"单位id 例如：xx派出所"` → `"所属单位id"`
  - `"部门id 例如：东营市公安分局"` → `"上级单位id"`

**改动原因**：  
`save_violate_photo()` 已在上一版本扩展了 `rule_name` 参数，但 `base.py` 的调用处未同步传入，导致该参数形同虚设；注释中的警务描述与加油站场景语义不符，影响代码可读性。

---

## 2026-03-22  `base.py` 与 `hk_camera.py` 适配 YOLOv11 工服检测场景

### 改动背景

基于 `docs/yolov11_migration_reuse_rewrite.md` 和 `docs/yolov11_workwear_system_design.md` 的设计要求，对违规基类和摄像头视图文件进行有针对性的改造：去除残留的警务耦合语义，扩展接口通用性，使两个文件完整适配加油站工人未穿工服检测场景，并为后续新建 `WorkwearMissingViolation` 子类做好接口准备。

---

### 1. `inspection-flask/violation_module/base.py`

**改动类型**：警务语义清除 + 接口扩展 + 稳定性修复

**改动内容**：

**类属性清理**：
- 删除 `clothes_labels = {'coat', 'cloth', 'shirt'}`，该属性是警服类别的硬编码，不应出现在通用基类中；工服类别将在 `settings.py` 中以 `WORKWEAR_LABELS` 配置项的形式定义，由子类读取
- 将 `person_label` 从 `['person', 'fu_person', 'person_szf']` 精简为 `['person']`，去掉 `fu_person`、`person_szf` 等警务场景专属标签；子类可按需覆盖

**`save()` 方法**：
- 新增可选参数 `box_color: list = None`，默认值为橙色 `[0, 165, 255]`（BGR），工服告警在视觉上与红色框区分；`plot_one_box` 和 `plot_txt_PIL` 统一使用 `color` 变量，不再硬编码 `[0, 0, 255]`
- 增加越界保护：在访问 `self.frames[max_conf_each]` 之前判断 `max_conf_each is None or max_conf_each >= len(self.frames)`，条件成立时清空 `plot_targets` 并提前返回 `None`，防止帧缓存与目标索引不一致时崩溃
- 将所有日志从原有的警务语义改为工服检测语义，例如"工服检测-摄像头 X 触发告警，即将保存证据图"和"工服检测-摄像头 X 标注框：... 标签=... 置信度=..."
- 补充完整中文 docstring，说明 `name` 和 `box_color` 参数用途及返回值

**改动原因**：  
基类是所有违规模块共用的骨架，不应携带任何业务专属标签；`box_color` 参数使不同规则子类可传入不同颜色，越界保护修复了帧索引可能越界的潜在 crash。

---

### 2. `inspection-flask/applications/view/system/hk_camera.py`

**改动类型**：接口扩展 + 硬编码日志清除 + 新增查询端点

**改动内容**：

**`save_violate_photo()` 函数**：
- 新增可选参数 `rule_name=None` 和 `extra_meta=None`
  - `rule_name`：违规规则名称（如"未穿工服"），用于日志动态展示，后续调用方传入即可
  - `extra_meta`：扩展元数据预留字段，当前暂不入库，为后续多规则扩展保留接口
- 移除原有 `if type == 21 or type == '21':` 的硬编码"未穿警服"日志分支，替换为动态日志：`display_name = rule_name if rule_name else f"违规类型{type}"`，统一输出格式为"工服检测-摄像头ID：X [规则名] 证据图已保存：..."
- 补充完整中文 docstring，说明所有参数用途

**`dis_enable()` 函数**：
- 将 `print(f"{_id}关闭成功")` 和 `print(f"{_id}关闭失败")` 替换为 `current_app.logger.info/warning`，统一日志输出渠道，文案改为"工服检测线程 camera X 已关闭/关闭失败"

**新增 `GET /hk_camera/violations` 端点**：
- 支持 `camera_id`（int，可选）和 `limit`（int，可选，默认 100，上限 500）两个 query 参数
- 按摄像头过滤并返回最新 N 条违规记录，响应体包含 `code`、`count`、`data` 字段

**新增 `GET /hk_camera/violations/camera/<int:camera_id>` 端点**：
- 按摄像头 ID 查询该摄像头全部违规记录，最多返回最新 200 条
- 响应体包含 `code`、`camera_id`、`count`、`data` 字段

**改动原因**：  
原函数中 `type == 21` 的"未穿警服"日志是典型的警务耦合硬编码，扩展为动态 `rule_name` 后可支持任意规则；新增查询端点满足多摄像头场景下按设备分页查看违规记录的需求。

---

## 2026-03-21  三个可复用文件的细微改造（YOLOv11 工服检测适配）

### 改动背景

基于 `docs/yolov11_migration_reuse_rewrite.md` 中的分析，对三个"可照搬"文件进行细微修改，去除残留的警务语义，补强稳定性与可维护性，使其完全适配加油站工人未穿工服检测场景。

---

### 1. `inspection-flask/app.py`

**改动类型**：细微修改

**改动内容**：

- 在 `app.run(...)` 前增加一行 `app.logger.info(...)` 启动日志，打印"加油站工服检测系统启动，监听 0.0.0.0:8080"
- 删除原有注释掉的 `log.disabled = True`，保持代码整洁

**改动原因**：  
原文件无任何启动提示，增加中文日志后便于运行时确认系统身份，也方便日志排查。

---

### 2. `inspection-flask/applications/common/hk_recorder_threading.py`

**改动类型**：稳定性增强

**改动内容**：

- 新增模块级全局变量 `_FAIL_COUNTS: dict[int, int]` 和 `_FAIL_WARN_THRESHOLD = 5`，用于对每个摄像头独立跟踪连续抓图失败次数
- 修改 `get_img()` 函数：
  - 抓图失败时累加对应摄像头的失败计数，**首次失败**及**每隔 5 次**时输出 `warning` 日志，提示检查设备连接或 `frame_path` 配置
  - 抓图成功时自动重置该摄像头计数，并输出 `info` 恢复日志
  - 在写入缓存的代码处添加中文注释："每个摄像头只保留最新帧，旧帧由新帧直接覆盖"
- 将 `_read_frame_from_camera()` 的 docstring 改为中文，并明确说明"真实部署时此处替换为 HK SDK 取帧逻辑"
- 将占位帧（placeholder frame）上的英文提示文字改为含有"workwear detection"字样的描述，明确调试用途

**改动原因**：  
原文件对抓图失败只打一条 `warning`，无法区分偶发失败和持续断连；新机制在首次和累积失败时升级日志，方便运维定位摄像头故障。

---

### 3. `inspection-flask/applications/common/hk_custom_threading_plus.py`

**改动类型**：settings 缺省回退 + 日志中文化 + 稳定性增强

**改动内容**：

**`_alert_suppressed()` 方法**：
- `settings.alert_suppression_seconds` 改为 `getattr(settings, "alert_suppression_seconds", 300)`，防止 `settings.py` 未定义该字段时抛出 `AttributeError`

**`run_rule_engine()` 方法**：
- `settings.WORKWEAR_VIOLATION_TYPE` 改为 `getattr(settings, "WORKWEAR_VIOLATION_TYPE", "workwear_missing")`，加缺省回退
- `camera.station_id`、`camera.dept_id`、`camera.sub_id` 均改为 `getattr(self.camera, ..., None)`，兼容没有该字段的摄像头对象
- 补充 docstring，说明该方法的返回值语义

**`emit_event()` 方法**：
- 增加 `isinstance(event, dict)` 类型检查，避免 `None` 或异常对象写入队列
- 日志格式改为中文，输出内容扩展为：`rule_name`（或 `rule_code`）、`position_time`、证据图 `href`，便于日志直接定位问题

**`run()` 方法**：
- `settings.thread_idle_sleep` 和 `settings.round_interval` 均改为 `getattr` 缺省回退（默认值分别为 `2` 秒和 `0`）
- `settings.TEMPORAL_WINDOW_SIZE` 改为 `getattr` 读取，默认 `5`
- 线程启动时打印"camera X 工服检测线程启动"，停止时打印"camera X 工服检测线程已停止"
- 检测循环异常日志从英文改为中文

**`restart_all_threads()` 方法**：
- 错峰启动间隔从 `0.1s` 调整为 `0.2s`，减少多摄像头同时初始化时的资源竞争
- 日志从 `warning` 级别改为 `info`，文案改为中文"重启工服检测线程 camera X"

**改动原因**：  
原文件直接引用 `settings.xxx` 属性，若 `settings.py` 尚未补全对应字段会在运行时崩溃；改为 `getattr` 缺省回退后可在 settings 逐步完善过程中安全运行。

---

## 文档更新规范

每次提交代码修改后，在本文档**顶部**按以下格式追加一节：

```
## YYYY-MM-DD  [本次改动的简短标题]

### 改动背景
...

### 1. 文件路径
**改动类型**：...
**改动内容**：
- ...
**改动原因**：...
```

字段说明：
- **改动类型**：可填"新增文件""细微修改""重构""接口扩展""Bug 修复""配置调整"等
- **改动内容**：具体到函数/变量/参数级别，方便定位
- **改动原因**：说明为什么这样改，而不只是描述改了什么
