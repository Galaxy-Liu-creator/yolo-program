# inspection-flask 修正清单（仅基于当前已存在代码）

更新时间：2026-03-25  
检查范围：`inspection-flask/**/*`（当前目录已存在文件）  
检查约束：按要求忽略“尚未导入的包/模块文件”，仅评估现有代码逻辑与健壮性。

## 1. 结论概览

结合 `docs/inspection-flask_文件职责与YOLOv11升级分析.md` 中关于 YOLOv11 升级后数据流（person -> crop -> workwear -> violation）的职责划分，当前实现主链路已经成型，但仍存在以下高优先级问题：

1. 权限过滤存在越权窗口（摄像头列表、违规记录查询）。
2. 线程生命周期与状态同步存在竞争条件（停线程、重启、共享缓存读写）。
3. “数据库状态”和“检测线程状态”在启停流程中可能不一致。
4. 输入参数校验不足，接口鲁棒性不够。

---

## 2. P0（必须优先修正）


| ID   | 问题                                                                       | 影响                             | 修正动作                                                                                          | 代码定位                                                                                                                                                                                                                                                                                 |
| ---- | ------------------------------------------------------------------------ | ------------------------------ | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| P0-1 | `/hk_camera/data` 在传入未授权 `stationId/parentId` 时，会退化为仅 `is_delete=0` 的宽查询 | 可能返回超出当前用户权限的数据                | 当 `stationId` 或 `parentId` 非授权时，直接返回空结果或 `403`；不要回落到宽过滤条件                                     | `inspection-flask/applications/view/system/hk_camera.py:50`, `inspection-flask/applications/view/system/hk_camera.py:58`, `inspection-flask/applications/view/system/hk_camera.py:63`                                                                                                |
| P0-2 | 违规记录接口缺少部门/分局数据权限过滤                                                      | 具备页面权限的用户可能读取跨单位违规记录           | 在 `/violations` 与 `/violations/camera/<id>` 增加 `dept_auth()/sub_auth()` 过滤，并校验 `camera_id` 归属 | `inspection-flask/applications/view/system/hk_camera.py:410`, `inspection-flask/applications/view/system/hk_camera.py:445`                                                                                                                                                           |
| P0-3 | 启用摄像头时先改数据库启用状态，再尝试启动线程；线程失败时仅返回错误，不回滚状态                                 | 造成“DB 已启用、线程未运行”的状态漂移          | 将“启用DB+起线程”做成原子流程：线程失败时回滚 enable，或改为“线程成功后提交 enable”                                          | `inspection-flask/applications/view/system/hk_camera.py:345`, `inspection-flask/applications/view/system/hk_camera.py:383`                                                                                                                                                           |
| P0-4 | `stop_thread()` 先从字典移除线程，再 `join(timeout=1s)`，超时后仍可能活着                   | 存在幽灵线程；后续重启可能同 camera 并发多个检测线程 | 先 `stop+join` 成功后再移除；超时线程需要标记并阻止重复启动                                                          | `inspection-flask/applications/common/hk_custom_threading_plus.py:289`, `inspection-flask/applications/common/hk_custom_threading_plus.py:293`                                                                                                                                       |
| P0-5 | 帧缓存 `hk_images` 与 `hk_images_datetime` 分开读写，且无共享锁                        | 可能读到不一致的“帧-时间戳”组合，导致重复/漏处理     | 统一为单对象原子更新（如 `{camera_id: {frame, timestamp}}`）并加锁；读取端同锁保护                                    | `inspection-flask/applications/common/hk_recorder_threading.py:63`, `inspection-flask/applications/common/hk_recorder_threading.py:64`, `inspection-flask/applications/common/hk_custom_threading_plus.py:47`, `inspection-flask/applications/common/hk_custom_threading_plus.py:48` |


---

## 3. P1（建议尽快修正）


| ID   | 问题                                                       | 影响                              | 修正动作                                  | 代码定位                                                                                                                       |
| ---- | -------------------------------------------------------- | ------------------------------- | ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| P1-1 | 列表排序字段 `sort` 未做白名单校验，直接 `getattr(HKCamera, sort_field)` | 非法字段会触发 `AttributeError`，导致 500 | 增加可排序字段白名单，不合法值回退默认字段（如 `id`）         | `inspection-flask/applications/view/system/hk_camera.py:47`, `inspection-flask/applications/view/system/hk_camera.py:86`   |
| P1-2 | `/add_dept`、`/add_room` 使用 `GET` 执行写库且无幂等控制              | 重复访问会重复插入关系数据，且不符合 REST 语义      | 改为 `POST`；加唯一约束或“存在即跳过”；返回结构化结果而非空字符串 | `inspection-flask/applications/view/system/hk_camera.py:269`, `inspection-flask/applications/view/system/hk_camera.py:301` |
| P1-3 | `save/update` 缺少关键字段合法性校验（空值、IP格式、端口范围、channel范围）        | 脏数据入库，后续线程或抓帧异常                 | 增加请求参数校验层；校验失败返回明确错误                  | `inspection-flask/applications/view/system/hk_camera.py:207`, `inspection-flask/applications/view/system/hk_camera.py:234` |
| P1-4 | `_resolve_violate_rule` 缓存无失效策略                          | 规则表变更后可能长期命中旧映射                 | 给缓存加 TTL 或在规则配置变更时主动清理                | `inspection-flask/applications/view/system/hk_camera.py:549`                                                               |
| P1-5 | `rule_name` 默认值硬编码在逻辑里                                   | 多语言/可配置性较差，后续规则扩展成本高            | 将默认展示名称放入配置或规则表，不在代码硬编码中文字符串          | `inspection-flask/applications/view/system/hk_camera.py:598`                                                               |
| P1-6 | 线程告警抑制期间窗口不清理，持续堆积“旧语义”样本                                | 抑制窗口结束后可能基于历史窗再次触发，不够可解释        | 抑制命中时清理窗口，或只保留抑制后新帧再判定                | `inspection-flask/applications/common/hk_custom_threading_plus.py:229`                                                     |


---

## 4. P2（优化项）


| ID   | 问题                                   | 影响                      | 修正动作                                              | 代码定位                                                                 |
| ---- | ------------------------------------ | ----------------------- | ------------------------------------------------- | -------------------------------------------------------------------- |
| P2-1 | `main.py` 为空文件                       | 增加维护噪音，容易混淆入口           | 删除或补充用途说明                                         | `inspection-flask/main.py:1`                                         |
| P2-2 | 采集链路当前仅实现 `frame_path` 读取（调试图）       | 与“摄像头实时采集”目标不一致，生产可用性受限 | 在当前框架下补齐 RTSP/海康 SDK 读取实现，并保留 `frame_path` 作为测试后备 | `inspection-flask/applications/common/hk_recorder_threading.py:18`   |
| P2-3 | `LOG_PATH` 先创建目录再重赋值为时间戳文件路径，变量语义不稳定 | 新人阅读成本高，容易误用            | 拆分为 `LOG_DIR` 与 `LOG_FILE` 两个变量                   | `inspection-flask/settings.py:69`, `inspection-flask/settings.py:71` |


---

## 5. 与 YOLOv11 升级文档的一致性备注

以下方向与升级文档基本一致，可保留：

1. 双模型链路（person + workwear）职责拆分清晰，入口在 `utils/models.py`。
2. 规则引擎聚焦于 `violation_module/vio_workwear_missing.py`，并通过 `BaseVio.save()` 统一落图落库。
3. 线程框架已形成“抓帧线程管理 + 规则线程管理 + 调度器”三段式结构。

当前建议主要集中在“权限边界、线程一致性、接口健壮性”，不改变你现在的 YOLOv11 核心判定思路。

---

## 6. 建议修复顺序

1. 先修权限问题：`P0-1`、`P0-2`。
2. 再修线程一致性：`P0-4`、`P0-5`、`P1-6`。
3. 再修启停原子性：`P0-3`。
4. 最后补接口健壮性和维护项：`P1-*`、`P2-*`。

