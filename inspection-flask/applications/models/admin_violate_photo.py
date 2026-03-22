import datetime

from applications.extensions import db


class ViolatePhoto(db.Model):
    __tablename__ = 'admin_violate_photo'

    id           = db.Column(db.Integer, primary_key=True, autoincrement=True, comment='ID')
    violate_id   = db.Column(db.Integer, db.ForeignKey("admin_violate_rule.id"), nullable=False, comment='违规类型ID')
    href         = db.Column(db.String(200), nullable=False, comment='证据图存储路径')
    station_id   = db.Column(db.Integer, nullable=True,  comment='监控站点ID')
    dept_id      = db.Column(db.Integer, db.ForeignKey("admin_police_station.id"), nullable=False, comment='所属单位ID')
    sub_id       = db.Column(db.Integer, nullable=False, comment='上级单位ID')
    # 外键指向海康摄像头表（原 admin_camera 已由 admin_hk_camera 替代）
    camera_id    = db.Column(db.Integer, db.ForeignKey("admin_hk_camera.id"), nullable=False, comment='海康摄像头ID')
    position_time = db.Column(db.DateTime, nullable=False, comment='违规发生时间')
    is_delete    = db.Column(db.Integer, nullable=False, default=0, comment='是否删除（1删除 0正常）')
    review       = db.Column(db.Integer, nullable=False, default=0, comment='0未审核 1审核通过 2审核不通过')
    # 违规规则字段（YOLOv11 工服检测新增，与 violation_module 保持一致）
    rule_code    = db.Column(db.String(64),  nullable=True, comment='违规规则编码，如 workwear_missing')
    rule_name    = db.Column(db.String(100), nullable=True, comment='违规规则名称，如 未穿工服')
    create_time  = db.Column(db.DateTime, default=datetime.datetime.now, comment='创建时间')
    update_time  = db.Column(db.DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now, comment='更新时间')

    # 关联：监控站点信息
    station = db.relationship('Station', backref=db.backref('violatePhoto_station'), lazy='select')
    # 关联：违规规则信息
    violate_rule = db.relationship('ViolateRule', backref=db.backref('violatePhoto_violateRule'), lazy='select')
    # 关联：海康摄像头信息（预留，待 HKCamera ORM 模型加入后启用）
    # hk_camera = db.relationship('HKCamera', backref=db.backref('violatePhoto_hkCamera'), lazy='select')
