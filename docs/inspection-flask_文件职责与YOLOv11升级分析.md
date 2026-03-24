# inspection-flask 文件职责与 YOLOv11 升级分析

生成时间: 2026-03-24  
分析范围: `inspection-flask/**/*`  
分析方式: 只读审查源码、模板、配置、权重、运行产物与第三方资源；未修改 `inspection-flask` 内任何文件。  

## 1. 总体结论

这个目录本质上是一个“Flask 管理后台 + 摄像头接入 + 多模型联合检测 + 违规抓拍入库 + 可视化展示”的综合项目。

当前仓库快照有 2170 个文件，里面真正承载业务逻辑的是以下几类：

- Flask 业务源码: `applications/**/*`
- 检测推理与姿态辅助: `utils/**/*`、`models/**/*`、`modules/**/*`
- 违规规则判定: `violation_module/**/*`
- 海康 SDK 与海康线程链路: `hk/**/*`、`applications/common/hk_*`
- 人脸识别: `insightface_module/**/*`
- 躺卧/值班异常识别: `lying_module/**/*`
- YOLOv5 封装与一份完整的 YOLOv5 本地副本: `yolov5_module/**/*`
- 后台模板: `templates/**/*`

大量文件属于运行期或第三方资源，不需要逐个从业务角度解读：

- `flask_session/*`: Flask Session 文件
- `logs/*`: 运行日志
- `static/**/*`: 前端静态资源、Pear Admin、TinyMCE、图表插件、图片素材
- `libs/win/**/*`: 海康 SDK 二进制依赖
- `**/__pycache__/*.pyc`: Python 编译缓存
- `weights/*`、`insightface_module/buffalo_l/*`、`lying_module/Models/*`: 模型权重与模型文件

## 2. 当前业务主链路

### 2.1 主入口

- `inspection-flask/app.py`: 启动 Flask 应用，监听 `0.0.0.0:8080`。
- `inspection-flask/applications/__init__.py`: 应用工厂，注册扩展、蓝图、日志、异常处理。

### 2.2 业务闭环

当前项目主要有两条检测链：

- 普通 RTSP 摄像头链路  
  `applications/view/system/camera.py` 管理普通摄像头，历史版本中直接用 OpenCV 取流并做检测。

- 海康摄像头链路  
  `applications/view/system/hk_camera.py` 管理海康摄像头。  
  `applications/common/hk_recorder_threading.py` 负责周期性拉取海康各通道图片。  
  `applications/common/hk_custom_threading_plus.py` 负责对每个海康摄像头线程化检测。  
  `violation_module/*` 负责对检测结果做规则判定并最终落库。  
  `applications/view/system/hk_camera.py::save_violate_photo` 负责保存抓拍图并写入 `ViolatePhoto`。

### 2.3 多模型联合方式

当前真正的检测不是单个模型完成，而是多模型拼装：

- 人员检测模型: `settings.YI_WEIGHT`，由 `utils/models.py` 加载
- 二次目标模型: `settings.ER_WEIGHT`，用于手机/烟等目标检测
- 警服检测模型: `settings.CLOTH_WEIGHT`
- 姿态估计模型: `settings.POSE_WEIGHT`
- 人脸识别模型: `insightface_module/FaceRecognition.py`
- 躺卧检测模型: `lying_module/Lying_Detect.py`

海康线程中，典型单帧流程是：

1. `seek_target()` 先做人检测
2. 对每个 person 框做人内二次检测
3. 在 person 框内叠加手机/烟/衣着/人脸/姿态/躺卧等信息
4. 把统一格式的 `targets` 交给 `violation_module/*`
5. 规则模块判断是否违规
6. `BaseVio.save()` 绘框并调用 `save_violate_photo()` 入库

## 3. 一个必须先说明的现状风险

当前仓库快照里，`inspection-flask/applications/__init__.py` 中以下核心初始化代码被整体注释掉了：

- `person_detect_model`
- `smoke_phone_detect_model`
- `cloth_detect_model`
- `pose_net`
- `face_detect_model`
- `lying_model`
- `device`
- `threadManager`
- `hk_threadManager`
- `hk_images`
- `hk_images_datetime`
- `hk_recorder_thread_manager`

但以下文件仍然直接依赖这些配置：

- `inspection-flask/applications/view/system/camera.py`
- `inspection-flask/applications/view/system/hk_camera.py`
- `inspection-flask/applications/common/hk_custom_threading_plus.py`
- `inspection-flask/applications/common/hk_custom_threading.py`
- `inspection-flask/applications/common/hk_recorder_threading.py`

这说明当前仓库很可能是“中途提交态”或“运行环境中还有未提交初始化代码”。  
因此，YOLOv11 升级时不能只改模型加载，还必须先统一应用启动期的模型装配方式。

## 4. 文件职责总览

## 4.1 顶层文件

- `inspection-flask/app.py`: Flask 启动入口。
- `inspection-flask/main.py`: 海康取流与本地实验脚本，不是正式 Web 入口。
- `inspection-flask/settings.py`: 全局路径、权重路径、阈值、取图间隔、模板路径配置。
- `inspection-flask/README.md`: GitLab 默认 README，几乎没有项目业务说明。
- `inspection-flask/test_hk_.py`: 海康取流与通道检查实验脚本。
- `inspection-flask/test_main.py`: 本地测试人检模型与海康图片读取。
- `inspection-flask/test_main_for_cloth.py`: 本地测试“人框裁切 + 警服检测”链路。
- `inspection-flask/test_main_for_crowddetect.py`: 本地测试人员聚集检测逻辑。
- `inspection-flask/test_main_for_insightface.py`: 本地测试人脸识别 + 二次目标组合。
- `inspection-flask/test_main_for_lying.py`: 本地测试躺卧识别。
- `inspection-flask/test_main_for_qk.py`: 本地测试枪库类场景综合检测。
- `inspection-flask/test_new_hk.py`: 海康新版拉流/抓图实验脚本。
- `inspection-flask/test_targets_main.py`: 手工构造 targets，验证目标格式与解析逻辑。
- `inspection-flask/test_vio_main.py`: 手工验证违规规则类。
- `inspection-flask/test_yolo.py`: 综合检测试验脚本。

## 4.2 `applications/` Flask 主业务

### 应用装配

- `inspection-flask/applications/__init__.py`: 应用工厂、日志、异常处理、理论上的模型装配入口。
- `inspection-flask/applications/config.py`: Flask/SQLAlchemy/上传/Mail/Session 基础配置。

### `applications/common/`

- `__init__.py`: 空包初始化。
- `admin.py`: 验证码接口辅助。
- `admin_log.py`: 登录日志与操作日志写入。
- `curd.py`: 通用 CRUD 与逻辑删除、分页辅助。
- `custom_threading.py`: 普通摄像头线程管理旧实现。
- `flask_log.py`: 全局异常捕获与写日志。
- `helper.py`: 模型过滤与查询辅助。
- `hk_custom_threading.py`: 海康检测线程旧实现，模型通过构造参数传入。
- `hk_custom_threading_plus.py`: 海康检测线程新版，直接从 `app.config` 取模型，是当前检测主线之一。
- `hk_info_judge.py`: 按海康 IP 聚合通道并检测账号、通道、重复通道问题。
- `hk_recorder_threading.py`: 周期性从海康通道拉图并写入 `app.config['hk_images']`。
- `logic_judge.py`: 依赖 YOLOv5 `res.pandas().xyxy[0]` 的衣着判定与绘框逻辑。
- `sql.py`: SQL/设备类型相关辅助。
- `test.py`: 早期测试模型与权限关系的实验文件。
- `user_auth.py`: 分局、部门、询问室权限过滤。

### `applications/common/script/`

- `__init__.py`: 命令注册入口。
- `admin.py`: 初始化管理员、角色、权限、角色关系等脚本。

### `applications/common/utils/`

- `export_excel.py`: 违规数据导出 Excel。
- `export_word.py`: 违规统计导出 Word。
- `gen_captcha.py`: 生成验证码图片。
- `http.py`: 标准 API 返回结构。
- `mail.py`: 邮件模板与发送封装。
- `rights.py`: 权限装饰器。
- `test_logic.py`: 检测逻辑测试辅助。
- `thread_camera.py`: 普通摄像头线程启动占位逻辑。
- `upload.py`: 图片上传与图片表查询。
- `upload_video.py`: 视频上传与删除。
- `upload_zip.py`: ZIP 中图片提取。
- `validate.py`: 输入校验与字符转义。
- `fonts/1.ttf`: 导出字体资源。

### `applications/extensions/`

- `__init__.py`: 扩展统一初始化入口。
- `init_error_views.py`: 403/404/500 视图初始化。
- `init_login.py`: Flask-Login 初始化。
- `init_mail.py`: Flask-Mail 初始化。
- `init_migrate.py`: Flask-Migrate 初始化。
- `init_session.py`: 文件型 Session 初始化。
- `init_sqlalchemy.py`: SQLAlchemy/Marshmallow 初始化，自定义分页 Query。
- `init_template_directives.py`: 模板指令初始化。
- `init_upload.py`: 上传组件初始化。
- `init_webargs.py`: Webargs 解析器扩展。

### `applications/models/`

- `__init__.py`: 汇总导出所有 ORM 模型。
- `admin_camera.py`: 普通 RTSP 摄像头表。
- `admin_dept.py`: 通用部门表。
- `admin_dept_relations.py`: 分局/部门/询问室关系映射表。
- `admin_dict.py`: 字典类型表与字典数据表。
- `admin_face.py`: 人脸底库特征表。
- `admin_hk_camera.py`: 海康摄像头表。
- `admin_log.py`: 操作日志表。
- `admin_mail.py`: 邮件记录表。
- `admin_photo.py`: 通用图片上传记录表。
- `admin_police_station.py`: 分局/派出所/询问室树形结构表。
- `admin_power.py`: 菜单/权限点表。
- `admin_role.py`: 角色表。
- `admin_role_power.py`: 角色权限关联表。
- `admin_user.py`: 用户表。
- `admin_user_role.py`: 用户角色关联表。
- `admin_video.py`: 视频资源表。
- `admin_violate_photo.py`: 违规抓拍图表，是检测落库核心。
- `admin_violate_rule.py`: 违规规则字典表。

### `applications/schemas/`

- `__init__.py`: schema 汇总。
- `admin_camera.py`: Camera 序列化。
- `admin_dept.py`: Dept 序列化。
- `admin_dict.py`: DictType/DictData 序列化。
- `admin_face.py`: FaceData 序列化。
- `admin_hk_camera.py`: HKCamera 序列化。
- `admin_log.py`: 日志序列化。
- `admin_mail.py`: 邮件序列化。
- `admin_photo.py`: 图片序列化。
- `admin_police_station.py`: Station 序列化。
- `admin_power.py`: 权限序列化。
- `admin_role.py`: 角色序列化。
- `admin_video.py`: 视频序列化。
- `admin_violate_photo.py`: 违规图片序列化。
- `admin_violate_rule.py`: 违规规则序列化。

### `applications/view/`

- `applications/view/__init__.py`: 蓝图注册总入口。
- `applications/view/plugin/__init__.py`: 插件蓝图注册器，默认插件关闭。

### `applications/view/system/`

- `__init__.py`: 注册系统蓝图。
- `camera.py`: 普通摄像头 CRUD 与历史版检测逻辑。
- `dept.py`: 部门管理。
- `dict.py`: 字典管理。
- `file.py`: 通用图片文件管理。
- `hk_camera.py`: 海康摄像头 CRUD、启停检测、抓拍保存，是当前主链路入口之一。
- `index.py`: 系统首页。
- `log.py`: 登录/操作日志查看。
- `mail.py`: 邮件模板与发送记录管理。
- `monitor.py`: 系统监控页，展示 CPU/内存/磁盘信息。
- `passport.py`: 登录、SSO、登出、验证码。
- `pc_station.py`: 分局/派出所/询问室管理。
- `power.py`: 菜单与权限点管理。
- `rights.py`: 菜单配置、欢迎页、权限树。
- `role.py`: 角色管理与角色授权。
- `task.py`: 海康通道检测任务页与测试接口。
- `user.py`: 用户管理、头像、资料、密码、Excel 导入。
- `violation.py`: 通用违规图片资源页。
- `violate/rule.py`: 违规规则管理。
- `violate/video.py`: 视频资源管理与下载。
- `violate/violate_photo.py`: 违规抓拍图查询、审核、导出 Excel/Word。
- `face/face.py`: 人脸底库管理、ZIP 批量导入、人脸预览。
- `visualize/visualize.py`: 常规可视化大屏接口。
- `visualize/visualize0.py`: 旧版可视化接口备份。
- `visualize/visualize_ducha.py`: 督察专用可视化大屏。

## 4.3 `hk/hksdk/` 海康 SDK 封装

- `__init__.py`: 包初始化。
- `device.py`: 海康 SDK Python 封装，负责 DLL 加载、登录、预览、解码、抓帧。
- `HCNetSDK.py`: SDK 结构与函数声明。
- `header.py`: 海康 SDK 结构体、常量、回调头定义。

## 4.4 `insightface_module/` 人脸识别

- `FaceRecognition.py`: 人脸检测、特征提取、底库匹配、警员/未知人判断、绘字。
- `arcface_onnx.py`: ArcFace ONNX 推理封装。
- `face_align.py`: 人脸对齐。
- `scrfd.py`: SCRFD 人脸检测器封装。
- `test.py`: 人脸识别本地测试。
- `requirements.txt`: InsightFace 依赖说明。
- `buffalo_l/*.onnx`: 人脸检测/特征/关键点/性别年龄模型文件。
- `txt/SimHei.ttf`: 中文字体。
- `txt/results.md`: 结果说明。
- `txt/img.png`: 示例图片。

## 4.5 `lying_module/` 躺卧/值班异常识别

核心源码:

- `Lying_Detect.py`: 躺卧检测统一入口，整合 TinyYOLOv3、姿态估计、动作识别、人脸识别。
- `DetectorLoader.py`: TinyYOLOv3 单类行人检测器加载。
- `PoseEstimateLoader.py`: FastPose 装载。
- `ActionsEstLoader.py`: TSSTG 动作识别装载。
- `CameraLoader.py`: 摄像头读取辅助。
- `Visualizer.py`: 可视化输出。
- `pose_utils.py`: 姿态辅助函数。
- `pPose_nms.py`: pose NMS。
- `fn.py`: 其他实验辅助。
- `App.py`: 旧版演示入口。
- `main.py`, `original_main.py`: 演示主程序。

子模块:

- `Actionsrecognition/*`: 动作识别模型、训练与工具。
- `Detection/*`: 检测工具与模型结构。
- `Track/*`: 跟踪器实现。
- `SPPE/src/**/*`: FastPose 子模块源码。

数据/模型/说明:

- `Models/sppe/*`: Pose 权重。
- `Models/TSSTG/*`: 动作识别权重。
- `Models/yolo-tiny-onecls/*`: TinyYOLOv3 行人模型权重与 cfg。
- `README.md`, `SPPE/README.md`, `SPPE/LICENSE`: 模块说明。
- `sample1.gif`: 示例演示。

演示/测试脚本:

- `demo_for_images.py`
- `demo_for_only_one_images.py`
- `demo_for_yolov3.py`
- `demo_only_for_person.py`
- `demo_simple.py`
- `demo_simple_8.py`
- `demo_simple_16.py`
- `test_1.py`
- `test_2.py`
- `test_for_police.py`
- `test_main_save_map4.py`
- `test_open_model_action.py`

这些脚本本质上都是模块演示或调试文件，不是 Flask 正式链路。

## 4.6 根级 `models/`、`modules/`、`utils/`

这些目录是项目的“检测辅助层”，包含一部分 YOLOv5 拷贝代码和一部分姿态估计/项目自定义工具。

### `models/`

- `__init__.py`: 包初始化。
- `common.py`: YOLOv5 通用模块。
- `experimental.py`: `attempt_load` 等实验模块。
- `export.py`: 导出模型脚本。
- `with_mobilenet.py`: MobileNet 姿态估计网络。
- `yolo.py`: YOLOv5 模型结构定义。
- `hub/*.yaml`, `yolov5*.yaml`: YOLOv5 模型配置。

### `modules/`

- `conv.py`: 卷积模块。
- `get_parameters.py`: 参数获取。
- `keypoints.py`: 关键点提取。
- `load_state.py`: 权重加载。
- `loss.py`: 损失函数。
- `one_euro_filter.py`: 平滑滤波。
- `pose.py`: Pose 类与跟踪。

### `utils/`

- `__init__.py`: 包初始化。
- `autoanchor.py`: anchor 工具。
- `blur_judge.py`: 清晰度/模糊判断。
- `datasets.py`: 数据集工具。
- `dmz.py`: 自定义辅助。
- `general.py`: YOLOv5 通用工具，含 `letterbox`、`check_img_size` 等。
- `get_id.py`: ID 生成辅助。
- `getrycsid.py`: 自定义 ID/编码辅助。
- `google_utils.py`: Google 工具。
- `logger.py`: 日志器。
- `metrics.py`: 指标工具。
- `models.py`: 当前项目最关键的检测装配层，负责加载多个权重并统一输出 target 格式。
- `monitor.py`: 监控辅助。
- `plots.py`: 绘框、绘中文、绘图工具。
- `pose.py`: 姿态估计推理入口。
- `qianzhi.py`: 自定义辅助。
- `sort.py`: SORT 跟踪。
- `test.py`: 工具测试。
- `timesynchronization.py`: 时间同步。
- `tools.py`: 杂项工具。
- `torch_utils.py`: 设备选择与 PyTorch 工具。
- `val.py`: 归一化与 padding 辅助。
- `font/addtext.py`, `font/simsun.ttc`: 中文字体与文字绘制资源。

## 4.7 `violation_module/` 违规规则判定

- `base.py`: 所有违规规则的抽象基类，统一保存绘框后的违规图片。
- `vio_djxw.py`: 单警询问判定。
- `vio_leave_post.py`: 脱岗/离岗判定。
- `vio_lying.py`: 值班睡岗/躺卧判定。
- `vio_qkwg.py`: 枪库规则总类或旧实现。
- `vio_qkwg_not_police.py`: 枪库出现非正式民警判定。
- `vio_qkwg_police_num.py`: 枪库警员人数不足判定。
- `vio_rqmdjc.py`: 人员聚集判定。
- `vio_wjsmoke.py`: 吸烟判定。
- `vio_wjsysj.py`: 玩手机判定。
- `vio_zsmjwcjf.py`: 正式民警未穿警服判定。
- `test_base.py`: 规则基类测试版本。
- `test_vio_djxw.py`: 单警询问规则测试。
- `test_vio_zsmjwcjf.py`: 未穿警服规则测试。

## 4.8 `yolov5_module/` 本地 YOLOv5 副本

顶层核心文件:

- `__init__.py`: 包初始化。
- `jiance.py`: 通过 `torch.hub.load(..., source='local')` 封装 YOLOv5 检测器，是最直接的 YOLOv5 API 绑定层。
- `crowddetect.py`: 人群聚集检测实验版 YOLOv5 包装。
- `yolov5_original.py`: 更早期的 YOLOv5 包装与实验逻辑。
- `hubconf.py`: PyTorch Hub 本地入口。
- `export.py`: YOLOv5 导出脚本。
- `test_distance.py`, `test_pos_relation.py`: 位置/距离实验。
- `testG.py`: 已经使用 `from ultralytics import YOLO` 的新式 API 试验文件，可作为迁移参考。
- `requirements.txt`: YOLOv5 依赖。
- `best.pt`, `gongan.pt`, `yolov5s.pt`: 权重文件。

子目录:

- `models/**/*`: 上游 YOLOv5 模型定义、分割配置、Hub YAML。
- `utils/**/*`: 上游 YOLOv5 工具、日志、segment 支持、REST API、Docker、Google App Engine 样例。

结论: `yolov5_module/` 应视为一个“整体替换或整体退役”的目录，而不是零散修补目录。

## 4.9 模板文件 `templates/`

这些 HTML 文件本质上都是 Flask 页面模板，与算法升级耦合很弱。

### 错误页

- `templates/errors/403.html`: 403 页面
- `templates/errors/404.html`: 404 页面
- `templates/errors/500.html`: 500 页面

### 系统模板

- `templates/system/index.html`: 后台首页
- `templates/system/login.html`: 登录页
- `templates/system/monitor.html`: 系统监控页

### 通用片段

- `templates/system/common/footer.html`
- `templates/system/common/header.html`
- `templates/system/common/index_footer.html`
- `templates/system/common/memory.html`
- `templates/system/common/photo_footer.html`

### 日志/控制台

- `templates/system/admin_log/main.html`: 日志页
- `templates/system/console/console.html`: 欢迎/控制台页

### 摄像头

- `templates/system/camera/add.html`
- `templates/system/camera/camera.html`
- `templates/system/camera/edit.html`
- `templates/system/camera/main.html`
- `templates/system/camera/test.html`

### 海康摄像头

- `templates/system/hk_camera/add.html`
- `templates/system/hk_camera/camera.html`
- `templates/system/hk_camera/edit.html`
- `templates/system/hk_camera/main.html`
- `templates/system/hk_camera/test.html`

### 部门/站点/权限/角色/用户

- `templates/system/dept/add.html`
- `templates/system/dept/edit.html`
- `templates/system/dept/main.html`
- `templates/system/dict/add.html`
- `templates/system/dict/edit.html`
- `templates/system/dict/main.html`
- `templates/system/dict/data/add.html`
- `templates/system/dict/data/edit.html`
- `templates/system/power/add.html`
- `templates/system/power/edit.html`
- `templates/system/power/main.html`
- `templates/system/role/add.html`
- `templates/system/role/edit.html`
- `templates/system/role/main.html`
- `templates/system/role/power.html`
- `templates/system/rule/add.html`
- `templates/system/rule/edit.html`
- `templates/system/rule/main.html`
- `templates/system/rule/power.html`
- `templates/system/station/add.html`
- `templates/system/station/edit.html`
- `templates/system/station/main.html`
- `templates/system/user/add.html`
- `templates/system/user/center.html`
- `templates/system/user/edit.html`
- `templates/system/user/edit_password.html`
- `templates/system/user/main.html`
- `templates/system/user/profile.html`

### 邮件/任务/资源

- `templates/system/mail/add.html`
- `templates/system/mail/main.html`
- `templates/system/task/add.html`
- `templates/system/task/main.html`
- `templates/system/photo/photo.html`
- `templates/system/photo/photo_add.html`
- `templates/system/video/video.html`
- `templates/system/video/video_add.html`

### 人脸

- `templates/system/face/add.html`
- `templates/system/face/add_temp.html`
- `templates/system/face/batch_add.html`
- `templates/system/face/edit.html`
- `templates/system/face/main.html`

### 违规图片

- `templates/system/violate_photo/add.html`
- `templates/system/violate_photo/edit.html`
- `templates/system/violate_photo/export_excel_word.html`
- `templates/system/violate_photo/main.html`
- `templates/system/violate_photo/main_temp.html`
- `templates/system/violate_photo/photo_add.html`
- `templates/system/violate_photo/review.html`
- `templates/system/violation/violation.html`

### 可视化

- `templates/system/visualize/index.html`
- `templates/system/visualize/index0.html`
- `templates/system/visualize/main.html`
- `templates/system/visualize/main0.html`
- `templates/system/visualize/set.html`
- `templates/system/visualize_ducha/index.html`

## 4.10 批量目录说明

以下目录中文件数量巨大，但单个文件职责高度同质，因此按目录整体说明即可覆盖全部文件。

- `inspection-flask/flask_session/*`: 320 个左右的 Flask Session 落盘文件，均为运行期缓存，不参与算法逻辑。
- `inspection-flask/logs/*`: 109 个左右的运行日志文件，记录海康登录失败、检测线程状态、应用错误，不参与算法实现。
- `inspection-flask/**/__pycache__/*.pyc`: Python 编译缓存，不参与源码逻辑。
- `inspection-flask/static/**/*`: 前端 CSS、JS、图片、字体、TinyMCE、Pear Admin、可视化资源。它们支撑后台界面和可视化展示，但不决定 YOLO 推理链。
- `inspection-flask/libs/win/**/*`: 海康 SDK DLL、LIB 和配套运行库。决定海康接入能否运行，但与 YOLOv11 升级本身无直接关系。
- `inspection-flask/weights/*`: 模型权重目录，分别存放人员检测、二次目标检测、警服检测、姿态估计等权重。
- `inspection-flask/vio_data/*`: 违规图片落盘目录。
- `inspection-flask/datasets/*`: 数据集或样例数据目录。

## 5. YOLOv5 -> YOLOv11 升级时，必须调整的功能

### 5.1 强耦合文件

这些文件直接绑定 YOLOv5 的 API、输出对象或工具函数，升级时必须改。

| 文件 | 当前耦合点 | 升级到 YOLOv11 需要改什么 |
| --- | --- | --- |
| `inspection-flask/settings.py` | 权重路径默认指向 `yolov5l.pt` | 切换到 YOLO11 权重路径，最好拆分为“模型注册配置”而不是硬编码单一 `.pt` |
| `inspection-flask/utils/models.py` | `attempt_load`、`letterbox`、`non_max_suppression`、`scale_coords`、YOLOv5 names/stride | 改为 `ultralytics.YOLO` 推理接口，并保留现有 `target` 统一输出格式 |
| `inspection-flask/applications/common/logic_judge.py` | 依赖 `res.pandas().xyxy[0]` | 改为读取 YOLO11 `results[0].boxes` 或通过适配器先转成统一 DataFrame/列表格式 |
| `inspection-flask/yolov5_module/jiance.py` | `torch.hub.load(..., source='local')` 和 `res.pandas()` | 整体重写成 `ultralytics.YOLO` 包装器，或直接废弃 |
| `inspection-flask/yolov5_module/crowddetect.py` | 同上 | 同上 |
| `inspection-flask/yolov5_module/yolov5_original.py` | 早期 YOLOv5 包装 | 建议退役，不继续迁移 |
| `inspection-flask/hk/hksdk/device.py` | 依赖根级 `utils.general.letterbox` | 如果删掉 YOLOv5 utils，需要把 `letterbox` 提出来做项目内独立图像预处理 |
| `inspection-flask/test_main_for_cloth.py` | 直接调用 YOLOv5 的预处理/NMS/坐标缩放 | 改为 YOLO11 测试脚本，或者删掉旧测试 |
| `inspection-flask/test_main_for_crowddetect.py` | 依赖 `get_models()` 与 YOLOv5 target 格式 | 改为适配 YOLO11 target |
| `inspection-flask/test_main_for_insightface.py` | 同上 | 同上 |
| `inspection-flask/test_main_for_qk.py` | 同上 | 同上 |
| `inspection-flask/test_yolo.py` | 同上 | 同上 |

### 5.2 中耦合文件

这些文件不直接依赖 YOLOv5 API，但依赖“当前 target 数据结构”。如果你保留 target 结构，它们可以少改甚至不改。

| 文件/目录 | 当前依赖 | 升级建议 |
| --- | --- | --- |
| `inspection-flask/applications/common/hk_custom_threading_plus.py` | 依赖 `seek_target/seek_targets` 输出的 person + second targets 结构 | 不直接读 YOLO11 原始结果，统一走新适配层 |
| `inspection-flask/violation_module/*` | 依赖 `targets` 列表格式和 label 命名 | 保留 label 命名与结构即可基本不动 |
| `inspection-flask/applications/view/system/hk_camera.py` | 依赖检测线程输出违规图片并入库 | 通常不需要直接改 YOLO 逻辑 |
| `inspection-flask/applications/view/system/camera.py` | 旧普通摄像头检测逻辑直接调 `yolo_model` | 如果还保留普通 RTSP 链路，需要和海康链一起统一适配 |
| `inspection-flask/utils/plots.py` | 只负责绘框与中文标注 | 通常不需要改 |
| `inspection-flask/insightface_module/*` | 独立于 YOLO | 通常不需要改 |
| `inspection-flask/lying_module/*` | 走 TinyYOLOv3 + Pose，不走 YOLOv5 主链 | 与 YOLO11 升级基本独立 |

### 5.3 低耦合或无关文件

以下文件通常不需要因为 YOLOv11 升级而修改：

- `applications/models/*`
- `applications/schemas/*`
- `applications/view/system/dept.py`
- `applications/view/system/user.py`
- `applications/view/system/role.py`
- `applications/view/system/power.py`
- `applications/view/system/mail.py`
- `applications/view/system/passport.py`
- `applications/view/system/pc_station.py`
- `applications/view/system/monitor.py`
- `templates/**/*`
- `static/**/*`
- `libs/win/**/*`
- `flask_session/*`
- `logs/*`

## 6. 最推荐的升级方式

不建议继续在 `yolov5_module/` 这套本地副本上硬迁。

推荐做法是：

1. 保留上层业务协议，不保留 YOLOv5 实现  
核心目标不是“把 YOLOv5 的每个函数迁成 YOLOv11”，而是让上层业务仍然得到同样结构的 `targets`。

2. 新建一个统一推理适配层  
例如可以在未来引入一个新的统一入口，负责：
- 加载 YOLO11 模型
- 输出统一结构 `[x1, y1, x2, y2, conf, label]`
- 对 person 框做二次检测
- 统一标签名为当前业务可接受的名字

3. 让这些老业务文件只依赖“统一 target 协议”  
这样 `violation_module/*`、`hk_custom_threading_plus.py`、`logic_judge.py` 就不再关心底层是 YOLOv5 还是 YOLO11。

## 7. 升级实施顺序

### 第一阶段: 清理架构

- 恢复并统一 `applications/__init__.py` 的模型装配逻辑
- 明确当前正式链路只保留哪一条: 普通 RTSP 还是海康线程
- 决定是否废弃 `camera.py` 里的旧检测实现

### 第二阶段: 建立 YOLO11 兼容层

- 用 `ultralytics.YOLO` 重写 `utils/models.py` 的模型加载
- 把 YOLO11 结果统一转成当前项目使用的 target 结构
- 保持 label 与阈值接口不变

### 第三阶段: 替换调用点

- `hk_custom_threading_plus.py`
- `logic_judge.py`
- `camera.py`
- 测试脚本

### 第四阶段: 收尾

- 退役 `yolov5_module/` 旧副本或至少停止业务引用
- 删除/归档旧测试脚本
- 补充启动文档与依赖说明

## 8. 最小改动版迁移建议

如果你想以最低风险从 YOLOv5 切到 YOLOv11，建议只动下面这些位置：

- `inspection-flask/settings.py`
- `inspection-flask/utils/models.py`
- `inspection-flask/applications/common/logic_judge.py`
- `inspection-flask/applications/__init__.py`
- `inspection-flask/applications/common/hk_custom_threading_plus.py`
- `inspection-flask/applications/view/system/camera.py`
- `inspection-flask/test_main_for_cloth.py`
- `inspection-flask/test_main_for_crowddetect.py`
- `inspection-flask/test_main_for_insightface.py`
- `inspection-flask/test_main_for_qk.py`
- `inspection-flask/test_yolo.py`

这条路线的核心原则是：

- 不改数据库
- 不改违规规则类的接口
- 不改模板
- 不改人脸模块
- 不改海康 SDK
- 只替换“检测结果生产层”

## 9. 文件目录级别的最终判断

### 必须参与 YOLOv11 升级的目录

- `inspection-flask/utils`
- `inspection-flask/yolov5_module`
- `inspection-flask/applications/common`
- `inspection-flask/applications/__init__.py`
- `inspection-flask/test_*.py`

### 可能需要联调但不一定修改的目录

- `inspection-flask/violation_module`
- `inspection-flask/hk`
- `inspection-flask/insightface_module`
- `inspection-flask/lying_module`

### 基本不需要因 YOLO 升级而修改的目录

- `inspection-flask/applications/models`
- `inspection-flask/applications/schemas`
- `inspection-flask/templates`
- `inspection-flask/static`
- `inspection-flask/libs`
- `inspection-flask/logs`
- `inspection-flask/flask_session`

## 10. 一句话总结

这个项目真正需要从 YOLOv5 升到 YOLOv11 的，不是整个 Flask 工程，而是“检测推理层 + 统一 target 适配层 + 启动期模型装配”。  
只要你保住 `targets` 的结构和 label 语义，`violation_module/*`、入库逻辑、页面展示层基本都可以复用。
