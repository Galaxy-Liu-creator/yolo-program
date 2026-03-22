import threading
import time
import traceback
from datetime import datetime

import cv2
import numpy as np

import settings
from applications.common.curd import disable_status
from applications.common.logic_judge import draw_boxes, judging_cloth
from hk.hksdk.device import HKStream
from utils.logger import logger
from utils.models import seek_targets, seek_target
from utils.pose import run_pose
# 值班脱岗
from violation_module.vio_leave_post import LeavePostViolation as tg_Violation
# 值班睡岗
from violation_module.vio_lying import LyingViolation as sg_Violation
# 枪库出现非正式民警
from violation_module.vio_qkwg_not_police import GunRoomNotPoliceViolation as qkfmj_Violation
# 枪库正式民警数量不够
from violation_module.vio_qkwg_police_num import GunRoomPoliceNumViolation as qkmjnum_Violation
# 枪库
# 人员聚集
from violation_module.vio_rqmdjc import Crowd_Detect_Violation as jj_Violation
# 抽烟
from violation_module.vio_wjsmoke import SmokeViolation as cy_Violation
# 手机
from violation_module.vio_wjsysj import PhoneViolation as sj_Violation
# 正式民警未穿警服
from violation_module.vio_zsmjwcjf import NoClothesViolation as wcjf_Violation
# 单警询问
from violation_module.vio_djxw import PoliceNumViolation as djxw_Violation


def add_white_background(img, det):
    # 获取图像的高度和宽度
    height, width = img.shape[:2]

    # 创建一个白色的背景图像
    white_bg = np.ones((height, width, 3), dtype=np.uint8) * 255

    # 获取人的坐标
    x1, y1, x2, y2 = det

    # 在白色背景上将指定人的区域复制为原图的对应区域
    white_bg[y1:y2, x1:x2] = img[y1:y2, x1:x2]

    return white_bg


def get_stream(team: str, team_info):
    hks = HKStream(team)
    if hks.login(team_info["ip"], team_info["port"], team_info["username"], team_info["password"]):
        # print(team_info["channels"])
        cjs = hks.play_preview(team_info["channels"])
        if not len(cjs):
            hks.logout()
            logger.error(f"no cj to check!")
            return None, []
        else:
            return hks, cjs
    else:
        hks.logout()
        print("登陆失败！")
        return None, []


def get_img(HK_INFO_list):
    pixel_data = None
    for item in HK_INFO_list:
        # print("正在登录" + item["device_name"] + "...")
        hks, cjs = get_stream('test', item)
        if hks is not None:
            for channel_name, channel_id, in item["channels"].items():
                pixel_data = hks.IMAGES[channel_name]
                print(f"摄像头图像获取成功{item}")
            hks.logout()
    return pixel_data

# HKCustomThread
class HKCustomThread(threading.Thread):
    def __init__(self, hk_camera):
        super().__init__()
        # 海康摄像头信息
        self.camera = hk_camera
        self.status = True
        # 设置获取一张图片的时间间隔s 默认1*60s
        self.get_image_interval = int(settings.get_image_interval)
        # 设置轮次检测时间间隔s (完成一轮检测后 你要休眠多少 或者选择不休眠)
        self.round_interval = int(settings.round_interval)
        # 设置一轮用多少张图片 默认十张
        self.images_num = int(settings.images_num)
        # 未检测到人员 休息20分钟
        self.rest_time = int(settings.rest_time)
        # targets 除了躺之外的targets
        self.targets = []
        # lying_targets
        self.lying_targets = []
        # has_person
        self.has_person = 0

    def add_target(self, image, app):
        if self.camera.type == 1:
            self.lying_target(image, app)
        self.common_target(image, app)

    def lying_target(self, image, app):
        target = app.config.get('lying_model').detect_lying_for_img(image, app.config.get('face_detect_model'),
                                                                    self.camera.sub_id)
        self.lying_targets.append(target)
        return True

    # 人脸、衣服、手机、烟
    def common_target(self, image, app):
        # 可删除代码
        # save_path = r'C:\Users\Admin\Desktop\test_imgs_for_HK'
        # camera_info_path = os.path.join(save_path, str(self.camera.id))
        # if not os.path.exists(camera_info_path):
        #     os.makedirs(camera_info_path)
        # curr_time = datetime.now().strftime("%H%M%S")
        # image_name = f"{curr_time}.jpg"
        # image_path = os.path.join(camera_info_path, image_name)
        # cv2.imwrite(image_path, image)
        #########################################
        target = seek_target(app.config.get('person_detect_model'), app.config.get('device'), image)
        has_person = False
        for i, det in enumerate(target):
            if det[4] > 0.6 and det[5] == 'person':
                has_person = True
                # 先做姿态估计
                images_pose = image[det[1]:det[3], det[0]:det[2]].copy()
                poses = run_pose(net=app.config.get('pose_net'), height_size=256, cpu=False, track=1, smooth=1,
                                 img=images_pose)
                # 模拟ID
                det.append(-1)
                det.append(poses or [])
                new_img = add_white_background(image, det[:4])
                targets2_cloth = seek_targets(app.config.get('cloth_detect_model'), app.config.get('device'),
                                              [new_img, ])

                targets2 = seek_targets(app.config.get('smoke_phone_detect_model'), app.config.get('device'),
                                        [image[det[1]:det[3], det[0]:det[2]], ])
                targets_face = app.config.get('face_detect_model').detect_faces_in_person_img(
                    image[det[1]:det[3], det[0]:det[2]], self.camera.sub_id)
                targets2[0].extend(targets_face)
                targets2[0].extend(targets2_cloth[0])
                det.append(targets2[0])
        # images.clear()
        # 一个人都没人就返回None
        if has_person:
            self.has_person += 1
        self.targets.append(target)
        return True

    # def vio_logic(self, images, targets, datetime_list):
    # 单警询讯问违规
    def dj_vio(self, images, targets, datetime_list):
        vio_djxw = djxw_Violation()
        vio_djxw.init(images, datetime_list, targets, vio_type=22, camera_id=self.camera.id,
                      station_id=self.camera.station_id, dept_id=self.camera.dept_id,
                      sub_id=self.camera.sub_id)

        vio_djxw.run()

    # 值班判断 脱岗 睡岗
    def zb_vio(self, images, targets, lying_targets, datetime_list):
        # 脱岗
        vio_tg = tg_Violation()
        vio_tg.init(images, datetime_list, targets, vio_type=2, camera_id=self.camera.id,
                    station_id=self.camera.station_id,
                    dept_id=self.camera.dept_id,
                    sub_id=self.camera.sub_id)

        # 睡岗
        vio_sg = sg_Violation()
        vio_sg.init(images, datetime_list, lying_targets, vio_type=1, camera_id=self.camera.id,
                    station_id=self.camera.station_id, dept_id=self.camera.dept_id,
                    sub_id=self.camera.sub_id)
        vio_tg.run()
        vio_sg.run()
        # print("值班脱岗检测结果：", vio_tg.run())
        # print("睡岗检测：", vio_sg.run())

    # 枪库违规项 正式民警、数量判断
    def qk_vio(self, images, targets, datetime_list):
        # 枪库出现非正式民警
        vio_qkfmj = qkfmj_Violation()
        # 正式民警数量不足
        vio_qkmjnum = qkmjnum_Violation()
        # 枪库非正式民警判断
        vio_qkfmj.init(images, datetime_list, targets, vio_type=18, camera_id=self.camera.id,
                       station_id=self.camera.station_id, dept_id=self.camera.dept_id,
                       sub_id=self.camera.sub_id)
        # 正式民警不足两人
        vio_qkmjnum.init(images, datetime_list, targets, vio_type=20, camera_id=self.camera.id,
                         station_id=self.camera.station_id, dept_id=self.camera.dept_id,
                         sub_id=self.camera.sub_id)
        # print("枪库非正式民警判断：", vio_qkfmj.run())
        # print("枪库正式民警大于等于两人判断：", vio_qkmjnum.run())
        vio_qkfmj.run()
        vio_qkmjnum.run()

    # 常规项 抽烟、玩手机、人员聚集、未穿警服
    def common_vio(self, images, targets, datetime_list):
        vio_sj = sj_Violation()
        vio_cy = cy_Violation()
        # 人员聚集
        vio_jj = jj_Violation()
        # 未穿警服
        vio_wcjf = wcjf_Violation()
        vio_jj.init(images, datetime_list, targets, vio_type=19, camera_id=self.camera.id,
                    station_id=self.camera.station_id, dept_id=self.camera.dept_id,
                    sub_id=self.camera.sub_id)
        vio_sj.init(images, datetime_list, targets, vio_type=3, camera_id=self.camera.id,
                    station_id=self.camera.station_id, dept_id=self.camera.dept_id,
                    sub_id=self.camera.sub_id)
        vio_cy.init(images, datetime_list, targets, vio_type=16, camera_id=self.camera.id,
                    station_id=self.camera.station_id, dept_id=self.camera.dept_id,
                    sub_id=self.camera.sub_id)
        # 未穿警服检测
        vio_wcjf.init(images, datetime_list, targets, vio_type=21, camera_id=self.camera.id,
                      station_id=self.camera.station_id,
                      dept_id=self.camera.dept_id,
                      sub_id=self.camera.sub_id)
        # print("正式民警是否穿警服检测：", vio_wcjf.run())
        # print("人员聚集检测结果：", vio_jj.run())
        # print("抽烟", vio_cy.run())
        # print("手机：", vio_sj.run())
        vio_wcjf.run()
        vio_jj.run()
        vio_cy.run()
        vio_sj.run()

    def detect_vio(self):
        from app import app
        app.logger.warning(f"摄像头ID：{self.camera.id}开启检测")
        hk_camera_images = []
        datetime_list = []
        try:
            with app.app_context():
                while True:
                    # print(f"当前线程状态{self.status}-已经获取的图片数量{len(hk_camera_images)}")
                    if not self.status:
                        print(
                            f"多线程-摄像头ID：{self.camera.id}*******************正常关闭*************************")
                        app.logger.warning(
                            f"多线程-摄像头ID：{self.camera.id}*******************摄像头已关闭*************************")
                        break
                    # 够一轮了没
                    if len(hk_camera_images) == self.images_num:
                        # 如果没检测到人且不是值班室场景下  那么就休眠
                        if self.has_person == 0:
                            print(f"{self.camera.id}未检测到人员")
                            # 值班室就多休眠一会
                            if self.camera.type == 1:
                                self.reSleep(3 * self.rest_time)
                            else:
                                self.reSleep(self.rest_time)
                        else:
                            # 调用违规类判断
                            self.common_vio(hk_camera_images, self.targets, datetime_list)
                            # 值班室
                            if self.camera.type == 1:
                                self.zb_vio(hk_camera_images, self.targets, self.lying_targets,
                                            datetime_list)
                            # 枪库
                            if self.camera.type == 2:
                                self.qk_vio(hk_camera_images, self.targets, datetime_list)
                            # 询问/讯问室
                            if self.camera.type == 0:
                                self.dj_vio(hk_camera_images, self.targets, datetime_list)
                        # 一轮结束
                        hk_camera_images.clear()
                        datetime_list.clear()
                        self.targets.clear()
                        self.has_person = 0
                        self.lying_targets.clear()
                        self.reSleep(self.round_interval)
                    # 把图像添加进去
                    if int(self.camera.id) not in app.config['hk_images'] or app.config['hk_images'][
                        int(self.camera.id)] is None or app.config['hk_images'][
                        int(self.camera.id)].shape[0] < 0 or app.config['hk_images'][
                        int(self.camera.id)].shape[1] < 0:
                        if not self.reSleepCauseImage(app, settings.get_image_interval * 10):
                            continue
                    image = app.config['hk_images'][int(self.camera.id)].copy()
                    hk_camera_images.append(image)
                    if image is not None:
                        self.add_target(image, app)
                        app.config['hk_images'][int(self.camera.id)] = None
                    datetime_list.append(app.config['hk_images_datetime'][int(self.camera.id)])
                    self.reSleep(self.get_image_interval)
        except Exception as e:
            trace = traceback.format_exc()  # 获取异常的堆栈跟踪信息
            app.logger.error(f'摄像头-{self.camera.id}:发生异常: %s\n%s', e, trace)
            print(f"摄像头-{self.camera.id}发生异常: {str(e)}")
        finally:
            hk_camera_images.clear()
            print(f"检测到手动关闭 停止休眠 结束运行 摄像头的ID:{self.camera.id}")
            app.logger.warning(f"{self.camera.id}资源已经释放")
            self.stop()

    def run(self):
        self.detect_vio()

    def stop(self):
        self.status = False

    def reSleep(self, num):
        for i in range(num):
            if not self.status:
                print(f"检测到手动关闭 停止休眠 结束运行 摄像头的ID:{self.camera.id}")
                break
            time.sleep(1)

    def reSleepCauseImage(self, app, num):
        for i in range(num):
            if not self.status:
                print(f"检测到手动关闭 停止休眠 结束运行 摄像头的ID:{self.camera.id}")
                break
            if int(self.camera.id) in app.config['hk_images'] and app.config['hk_images'][
                int(self.camera.id)] is not None:
                break
            time.sleep(1)
        if i == num - 1:
            print(f"超出最长无法获取图片的时间:{self.camera.id}")
            self.status = False
        return self.status

    def detect_camera(self):
        from app import app
        from applications import Camera
        from applications.view.system.camera import save_violate_photo
        print(f"detect_camera:{self.camera.id}+{self.camera.camera_url}")
        print(f"detect:{self.camera.id}+{self.camera.camera_url}")
        # 记录轮次违规数
        violate_round_num = 0
        violate_one_police = 0
        violate_cloth = 0
        bbox_result = None
        # 单警询问违规帧（打完框的图）
        violate_one_police_frame_list = []
        # 记录违规时间
        violate_one_police_time_list = []
        violate_cloth_time_list = []
        # 未穿警服违规帧（打完框的图）
        violate_cloth_frame_list = []
        # 检测间隔秒数
        skip_seconds = 30
        # 睡眠时间 10分钟
        sleep_min = 10
        # 一轮检测多少次
        one_round = 16
        with app.app_context():
            try:
                print(f"正在打开视频流{self.camera.camera_url}")
                camera_capture = cv2.VideoCapture(self.camera.camera_url)
                if not camera_capture.isOpened():
                    print(f"无法打开摄像头-{self.camera.id}: {self.camera.camera_url}")
                    app.logger.error(f"无法打开摄像头-{self.camera.id}: {self.camera.camera_url}")
                    return
                fps = int(camera_capture.get(cv2.CAP_PROP_FPS))
                print(f"fps:{fps}-{self.camera.id}: {self.camera.camera_url}")
                print(f"多线程-{self.camera.id}已开启{self.camera.camera_url}")
                # 获取模型***
                face_model = app.config.get("face_model")
                yolo_model = app.config.get('yolo_model')
                # 下面是对民警的检测
                while True:
                    # 单警询问违规帧（打完框的图）
                    # violate_one_police_frame_list = []
                    # 未穿警服违规帧（打完框的图）
                    # violate_cloth_frame_list = []
                    frame = None
                    success, frame = camera_capture.read()  # 读取摄像头帧
                    violate_time = datetime.now()
                    # not true
                    if not self.status:
                        print(
                            f"多线程-{self.camera.id}*******************正常关闭*************************{self.camera.camera_url}")
                        app.logger.warning(
                            f"多线程-{self.camera.id}*******************摄像头检测按钮已关闭*************************{self.camera.camera_url}")
                        break
                    if not success:
                        app.logger.error(
                            f"摄像头camera_capture.read()success参数-{success}*******************读取失败*************************{self.camera.camera_url}")
                        if not self.reconnect_video_stream(camera_capture, self.camera.camera_url):
                            app.logger.error(f"摄像头{self.camera.camera_url}重新连接失败*************************")
                            break
                        app.logger.warning(f"摄像头{self.camera.camera_url}重新连接成功！~~~(^v^)~~~")
                        continue
                    # 成功读取到视频
                    else:
                        # 在这里可以添加你的检测逻辑，例如处理 frame 等操作
                        # 计算一轮检测的数量
                        violate_round_num += 1
                        # 人的检测结果
                        person_res = yolo_model.original_predict(frame)
                        # 衣服检测结果
                        cloth_res = yolo_model.predict(frame)
                        person_num = yolo_model.original_get_num(person_res)
                        cloth_num = yolo_model.get_cloth_num(cloth_res)
                        print(f"摄像头id:{self.camera.id}--人员数量:{person_num}--警服数量:{cloth_num}")
                        if person_num < 2:
                            # 先判断之前的违规
                            # 此轮检测了几次 若没检测 直接跳过
                            if violate_one_police != 0 or violate_cloth != 0:
                                # 单警询问违规 2
                                if (violate_one_police / violate_round_num) >= 0.5:
                                    # 保存违规图片
                                    # save*****
                                    length = len(violate_one_police_frame_list)
                                    save_violate_photo(2, self.camera.id, violate_one_police_frame_list[length // 2],
                                                       self.camera.station_id, self.camera.dept_id, self.camera.sub_id,
                                                       app.config.get("UPLOADED_VIOLATE_PHOTOS_DEST_ABS"),
                                                       violate_one_police_time_list[length // 2])
                                # 未穿警服 1
                                if (violate_cloth / violate_round_num) >= 0.5:
                                    # 保存违规图片
                                    # save*******
                                    length = len(violate_cloth_frame_list)
                                    save_violate_photo(1, id, violate_cloth_frame_list[length // 2],
                                                       self.camera.station_id, self.camera.dept_id, self.camera.sub_id,
                                                       app.config.get("UPLOADED_VIOLATE_PHOTOS_DEST_ABS"),
                                                       violate_cloth_time_list[length // 2])
                            # 最后进行归0 清空操作
                            violate_one_police = 0
                            violate_cloth = 0
                            # 存储的图片信息清空
                            violate_cloth_frame_list.clear()
                            violate_one_police_frame_list.clear()
                            # 轮次信息归0
                            violate_round_num = 0
                            if person_num == 1:
                                print(f"检测到1个人，休息{sleep_min // 2}min")
                                self.skip_frame(60 * sleep_min // 2, fps, camera_capture)
                            else:
                                print(f"检测到0个人，休息{sleep_min}min")
                                self.skip_frame(60 * sleep_min, fps, camera_capture)
                        # 检测有人
                        else:
                            bbox_result = None
                            police_num, unknow_num, bbox_result = face_model.detect_faces_in_frame(frame,
                                                                                                   self.camera.sub_id)
                            print(f"警察数量：{police_num}--未知人员数量：{unknow_num}")
                            # （某些场景不对）如果人脸数量 不和person person-1相等的话 那就相当于算是检测失误
                            # 如果警察人脸一个也没有 那就别检测了
                            face_error = True
                            face_num = police_num + unknow_num
                            if face_num == person_num or face_num == person_num - 1:
                                face_error = False
                            # 如果一个警察人脸都没有的话 别检测了
                            if police_num == 0:
                                face_error = True
                            # 如果只有两个警察 那就别报单警询问了
                            if person_num == (max(cloth_num, police_num)):
                                face_error = True
                            # 如果正式民警数量少于2且不为
                            if police_num < 2 and not face_error:
                                # 添加打框后的违规图片
                                # 添加违规时间
                                violate_one_police_time_list.append(violate_time)
                                violate_one_police_frame_list.append(
                                    face_model.draw_info_on_frame_violate_by_PIL(
                                        draw_boxes(frame, person_res, cloth_res),
                                        bbox_result,
                                        "单警询问"))
                                # 单警询问
                                violate_one_police += 1
                                # if cloth_num == 0:
                                #     violate_cloth += 1
                                #     # 添加打框后的违规图片
                                #     # 添加违规时间
                                #     violate_cloth_time_list.append(violate_time)
                                #     violate_cloth_frame_list.append(
                                #         face_model.draw_info_on_frame_violate_by_PIL(res.render()[0], bbox_result, "未穿警服"))
                            # 人脸有俩 警服有俩 但是没人脸数据
                            # 判断有没穿警服的警察
                            if not face_error and judging_cloth(person_res, cloth_res, bbox_result):
                                # 未穿警服
                                violate_cloth += 1
                                # 添加打框后的违规图片
                                # 添加违规时间
                                violate_cloth_time_list.append(violate_time)
                                violate_cloth_frame_list.append(
                                    face_model.draw_info_on_frame_violate_by_PIL(
                                        draw_boxes(frame, person_res, cloth_res),
                                        bbox_result,
                                        "未穿警服"))
                            print(f"{skip_seconds}秒后再检测")
                            self.skip_frame(skip_seconds, fps, camera_capture)
                        # 是否一轮检测（60s检测六次 2分钟一轮）
                        if violate_round_num != 0 and violate_round_num % one_round == 0:
                            if violate_one_police != 0 or violate_cloth != 0:
                                # 单警询问违规(1/2的占比 则认定违规)
                                if (violate_one_police / violate_round_num) >= 0.5:
                                    # 保存违规图片
                                    # 取中间元素
                                    length = len(violate_one_police_frame_list)
                                    save_violate_photo(2, self.camera.id, violate_one_police_frame_list[length // 2],
                                                       self.camera.station_id, self.camera.dept_id, self.camera.sub_id,
                                                       app.config.get("UPLOADED_VIOLATE_PHOTOS_DEST_ABS"),
                                                       violate_one_police_time_list[length // 2])
                                # 未穿警服违规(1/2的占比 则认定违规)
                                if (violate_cloth / violate_round_num) >= 0.5:
                                    # 保存违规图片
                                    # save
                                    length = len(violate_cloth_frame_list)
                                    # violate_frame = res.render()[0]
                                    # violate_frame = face_model.draw_info_on_frame_violate(violate_frame, bbox_result, "未穿警服")
                                    save_violate_photo(1, self.camera.id, violate_cloth_frame_list[length // 2],
                                                       self.camera.station_id, self.camera.dept_id, self.camera.sub_id,
                                                       app.config.get("UPLOADED_VIOLATE_PHOTOS_DEST_ABS"),
                                                       violate_cloth_time_list[length // 2])
                            # 违规信息处理完把数量归0
                            violate_one_police = 0
                            violate_cloth = 0
                            # 存储的图片信息清空
                            violate_cloth_frame_list.clear()
                            # del violate_cloth_frame_list
                            violate_one_police_frame_list.clear()
                            # del violate_one_police_frame_list
                            violate_cloth_time_list.clear()
                            violate_one_police_time_list.clear()
                            # 轮次信息归0
                            violate_round_num = 0
            except Exception as e:
                camera_capture.release()
                trace = traceback.format_exc()  # 获取异常的堆栈跟踪信息
                app.logger.error('摄像头-{self.camera.id}: {self.camera.camera_url}发生异常: %s\n%s', e, trace)
                # app.logger.error(f"摄像头-{id}: {url}发生异常: {str(e)}")
                print(f"摄像头-{id}: {self.camera.camera_url}发生异常: {str(e)}")
            finally:
                disable_status(Camera, self.camera.id)
                # 释放摄像头资源
                app.logger.warning(f"摄像头-{self.camera.id}: {self.camera.camera_url}资源释放")
                camera_capture.release()
                violate_cloth_frame_list.clear()
                violate_one_police_frame_list.clear()
                violate_cloth_time_list.clear()
                violate_one_police_time_list.clear()

# ThreadManager
class ThreadManager:
    def __init__(self):
        self.threads = {}

    def add_thread(self, camera):
        # print("add_thread{}=", str(self.threads))
        id = str(camera.id)
        if id not in self.threads:
            from app import app
            new_thread = HKCustomThread(camera)
            self.threads[id] = new_thread
            new_thread.start()
            return True
        return False

    def stop_thread(self, id):
        id = str(id)
        # print("stop_thread{}=", str(self.threads))
        if id in self.threads:
            # print("id in self.threads")
            self.threads[id].status = False
            del self.threads[id]
            return True
        return False

    def stop_all_threads(self, app):
        for key in self.threads:
            self.threads[key].status = False
        self.threads.clear()
        app.logger.warning(f"stop_all_threads后threads：{str(self.threads)}")
        # app.logger.warning()

    def restart_all_threads(self, app):

        print("开始执行restart_all_threads~")
        # from applications import Camera
        from applications.models import Station, HKCamera
        # 开启全局变量
        # 查询所有状态为1的camera
        with app.app_context():
            cameras = HKCamera.query.filter_by(is_delete=0, enable=1).all()
            for camera_instance in cameras:
                station = Station(
                    id=camera_instance.station.id,
                    dept_name=camera_instance.station.dept_name,
                    leader=camera_instance.station.leader,
                    phone=camera_instance.station.phone,
                    is_delete=camera_instance.station.is_delete,
                    type=camera_instance.station.type,
                    remark=camera_instance.station.remark,
                    address=camera_instance.station.address,
                    create_at=camera_instance.station.create_at,
                    update_at=camera_instance.station.update_at,
                    # update_at=camera_instance.station.update_at,
                    parent_id=camera_instance.station.parent_id
                )
                camera_info = HKCamera(
                    id=camera_instance.id,
                    name=camera_instance.name,
                    ip=camera_instance.ip,
                    port=camera_instance.port,
                    username=camera_instance.username,
                    password=camera_instance.password,
                    enable=camera_instance.enable,
                    type=camera_instance.type,
                    is_delete=camera_instance.is_delete,
                    station_id=camera_instance.station_id,
                    create_time=camera_instance.create_time,
                    update_time=camera_instance.update_time,
                    station=station,
                    sub_id=camera_instance.sub_id,
                    dept_id=camera_instance.dept_id,
                    channel=camera_instance.channel
                )
                if self.add_thread(camera_info):
                    app.logger.warning(f"restart_all_threads-{camera_info.id}")
                    time.sleep(3)
                else:
                    app.logger.warning(f"restart_all_threads-失败-{camera_info.id}无需重启")
