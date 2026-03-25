import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent  # 根目录

# ─── 图像与存储路径 ────────────────────────────────────────────────────────────
VIO_IMAGE_PATH = BASE_DIR.joinpath('vio_data')

# ─── 模型权重路径 ──────────────────────────────────────────────────────────────
# 人员检测模型（YOLOv11）
PERSON_WEIGHT = BASE_DIR.joinpath("weights", "person_detect.pt")
# 工服检测模型（YOLOv11）
WORKWEAR_WEIGHT = BASE_DIR.joinpath("weights", "workwear_detect.pt")

# 以下为旧 YOLOv5 警务专用权重，已弃用，保留供参考
# YI_WEIGHT    = BASE_DIR.joinpath("weights", "yolov5l.pt")          # 原一次人体检测
# ER_WEIGHT    = BASE_DIR.joinpath("weights", "zj_erci_230324.pt")   # 原烟/手机二次检测
# CLOTH_WEIGHT = BASE_DIR.joinpath("weights", "police_uniform.pt")   # 原警服检测
# POSE_WEIGHT  = BASE_DIR.joinpath("weights", "checkpoint_iter_370000.pth")  # 原姿态估计

# ─── 推理图像尺寸 ──────────────────────────────────────────────────────────────
IMGSZ = 640  # YOLOv11 输入分辨率

# ─── 检测置信度阈值 ────────────────────────────────────────────────────────────
PERSON_CONF   = 0.55   # 人员检测置信度阈值
WORKWEAR_CONF = 0.45   # 工服检测置信度阈值

# 以下为旧警务专用阈值，已弃用
# SMOKE_CONF  = 0.55
# PHONE_CONF  = 0.55
# LYING_CONF  = 0.78
# FACE_CONF   = 0.50
# CLOTH_CONF  = 0.45

# ─── 工服检测业务配置 ──────────────────────────────────────────────────────────
# 合规工服类别列表（模型输出的 label 名称，命中任一即视为穿戴合规）
WORKWEAR_LABELS = ["work_clothes", "reflective_vest", "protective_suit", "uniform_top"]

# 工服检测前的人员区域预处理方式
# True：将帧中人员框外区域替换为白色后裁剪（对应原 YOLOv5 add_white_background 逻辑，
#       兼容在白底格式数据上训练的工服模型）
# False：直接裁剪人员框区域（推荐默认，适用于在真实场景数据上训练的 YOLOv11 模型）
USE_WHITE_BG_MASK = False

# 人员框最小面积（像素²），小于此值的人员目标视为过远/过小，跳过检测
MIN_PERSON_BOX_AREA = 3000

# 违规规则编码（写入数据库 rule_code 字段）
WORKWEAR_VIOLATION_TYPE = "workwear_missing"
WORKWEAR_VIOLATION_ID = None

# ─── 时序稳定性配置 ────────────────────────────────────────────────────────────
# 时间窗口帧数：最近 N 帧用于比例判定
TEMPORAL_WINDOW_SIZE   = 5
# 触发比例阈值：窗口内 >= 60% 帧未检出工服则触发告警
TEMPORAL_TRIGGER_RATIO = 0.6

# 同一摄像头告警抑制窗口（秒），避免短时间重复报警
alert_suppression_seconds = 300

# 检测线程空闲等待时间（秒），缓存无新帧时的轮询间隔
thread_idle_sleep = 2

# ─── 海康摄像头默认参数 ────────────────────────────────────────────────────────
DEFAULT_CAMERA_PORT    = 8000
DEFAULT_CAMERA_CHANNEL = 1

# ─── 海康日志路径 ──────────────────────────────────────────────────────────────
LOG_PATH = BASE_DIR.joinpath("logs")
LOG_PATH.mkdir(exist_ok=True, parents=True)
LOG_PATH = BASE_DIR.joinpath("logs", str(datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S"))).with_suffix(".log")

VIDEO_CRT         = 1  # 视频帧数
VIDEO_CRT_SECONDS = 1  # 一次处理单位秒

# ─── 轮次采集调度参数 ──────────────────────────────────────────────────────────
# 每次抓图的时间间隔（秒）
get_image_interval = 110
# 完成一轮检测后的额外休眠（秒），0 表示不额外等待
round_interval = 0
# 每轮累计帧数
images_num = 5
# 连续无人时的长休眠时长（秒）
rest_time = 20 * 60

# ─── 导出模板路径 ──────────────────────────────────────────────────────────────
excel_template_path = BASE_DIR.joinpath("static", "file_template", "export.xlsx")
word_template_path  = BASE_DIR.joinpath("static", "file_template", "export.docx")
