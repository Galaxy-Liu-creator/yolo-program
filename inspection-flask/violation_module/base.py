import copy
import os
import uuid
from abc import ABCMeta, abstractmethod

import cv2

import settings

from utils.plots import plot_one_box, plot_txt_PIL


def format_targets_for_log(original_targets):
    filtered_targets = []
    _targets = copy.deepcopy(original_targets)
    for each_frame in _targets:
        filtered_frame = []
        for person in each_frame:
            if person[5] == 'person' and len(person) == 9 and person[4] > 0:  # 替换为实际阈值
                # 删除 person[7]
                del person[7]
                filtered_frame.append(person)
        filtered_targets.append(filtered_frame)
    _targets = filtered_targets
    return _targets


class BaseVio(metaclass=ABCMeta):
    # 有效人员标签（子类可按需覆盖）
    person_label = ['person']
    # 违规类型
    vio_type = ""
    # 摄像头信息
    camera_id = ""
    # 原图
    frames = []
    # time_list 对应图片时间
    datatime_list = []
    # 对应frame的检测结果
    targets = []
    # 监控站点id
    station_id = ""
    # 所属单位id
    dept_id = ""
    # 上级单位id
    sub_id = ""
    # 存放符合违规的信息
    plot_targets = {}

    def __init__(self):
        self.vio_type = ""
        # 摄像头信息
        self.camera_id = ""
        # 原图
        self.frames = []
        # time_list 对应图片时间
        self.datatime_list = []
        # 对应frame的检测结果
        self.targets = []
        # 监控站点id
        self.station_id = ""
        # 所属单位id
        self.dept_id = ""
        # 上级单位id
        self.sub_id = ""
        # 存放符合违规的信息
        self.plot_targets = {}

    def init(self, frames, datetime_list, targets, vio_type=None, camera_id=None, station_id=None, dept_id=None,
             sub_id=None):
        self.vio_type = vio_type
        self.camera_id = camera_id
        self.frames = frames
        self.datetime_list = datetime_list
        self.targets = targets
        self.station_id = station_id
        self.dept_id = dept_id
        self.sub_id = sub_id
        self.plot_targets = {}

    @abstractmethod
    def run(self):
        pass

    def add_plot_targets(self, key, up_box_list):
        if key in self.plot_targets:
            self.plot_targets[key].append(up_box_list)
        else:
            self.plot_targets[key] = [up_box_list]

    def save(self, name, box_color=None):
        """
        从 plot_targets 中挑选置信度最高的帧，绘制检测框和违规标注，
        保存证据图并写入数据库。
        :param name:      违规名称，将叠加到证据图左上角
        :param box_color: 标注框颜色（BGR），默认橙色 [0, 165, 255]
        :return: None
        """
        from applications.view.system.hk_camera import save_violate_photo
        from app import app

        color = box_color if box_color is not None else [0, 165, 255]

        max_conf = float('-inf')
        max_conf_each = None
        for each, lists in self.plot_targets.items():
            max_each_conf = max(lists, key=lambda x: x[2])[2]
            if max_each_conf > max_conf:
                max_conf = max_each_conf
                max_conf_each = each

        if max_conf_each is None or max_conf_each >= len(self.frames):
            self.plot_targets.clear()
            return None

        max_conf_lists = self.plot_targets[max_conf_each]
        vio_image = self.frames[max_conf_each].copy()
        if max_conf_lists:
            app.logger.warning(
                f"工服检测-摄像头 {self.camera_id} 触发告警，即将保存证据图，本轮目标：{format_targets_for_log(self.targets)}")
            for target_list in max_conf_lists:
                if isinstance(target_list, list) and len(target_list) == 3:
                    for target in target_list:
                        if isinstance(target, list) and len(target) >= 6:
                            app.logger.warning(
                                f"工服检测-摄像头 {self.camera_id} 标注框：{target[:4]} 标签={target[5]} 置信度={target[4]:.2f}")
                            plot_one_box(target[:4], vio_image, color=color,
                                         label=f"{target[5]} {target[4]:.2f}",
                                         line_thickness=1)
            vio_image = plot_txt_PIL(box=[20, 20], img=vio_image, label=name, color=color)
            with app.app_context():
                save_violate_photo(self.vio_type, self.camera_id, vio_image,
                                   self.station_id, self.dept_id, self.sub_id,
                                   settings.VIO_IMAGE_PATH,
                                   self.datetime_list[max_conf_each],
                                   rule_name=name)
        self.plot_targets.clear()
        return None
    # def save(self, image, vio_name, targets=None):
    #     """
    #     :param image:  frames里面置信度最高的违规原图
    #     :param vio_name:   违规名称
    #     :param target:   target是一个list嵌套,包含了要打的所有框[[x1,y1,x2,y2,conf,class_name],[x1,y1,x2,y2,conf,class_name]]
    #     """
    #     vio_image = image.copy()
    #     if targets:
    #         for target in targets:
    #             plot_one_box(target[:4], vio_image, color=[0, 0, 255], label=f"{target[5]} {target[4]:.2f}",
    #                          line_thickness=1)
    #     vio_image = plot_txt_PIL(box=[20, 20], img=vio_image, label=vio_name, color=[0, 0, 255], )
    #     unique_string = str(uuid.uuid4())
    #     filename = unique_string + '.jpg'
    #     cv2.imwrite(os.path.join(settings.VIO_IMAGE_PATH, filename), vio_image)
    #     # 虚拟访问地址
    #     file_url = settings.VIO_IMAGE_PATH + filename
    #     return file_url
