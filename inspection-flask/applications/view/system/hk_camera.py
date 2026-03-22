import traceback
import uuid
from datetime import datetime, timedelta
import os
import threading
import time

import cv2
from flask import Blueprint, request, render_template, jsonify, current_app, Response
from sqlalchemy import desc, asc
from sqlalchemy.orm import aliased

from applications.common import curd
from applications.common.curd import enable_status, disable_status, get_one_by_id
from applications.common.logic_judge import judging_cloth, draw_boxes
# from applications.common.test import log_writer
from applications.common.user_auth import dept_auth, sub_auth
from applications.common.utils.http import fail_api, success_api, table_api
from applications.common.utils.rights import authorize
from applications.common.utils.thread_camera import detect

from applications.common.utils.validate import str_escape
from applications.extensions import db
from applications.models import Photo, HKCamera, Station, ViolatePhoto
from applications.models.admin_dept_relations import DeptRelations
from applications.schemas.admin_hk_camera import HkCameraOutSchema
from applications.common.utils import upload as upload_curd

bp = Blueprint('hk_camera', __name__, url_prefix='/hk_camera')


# 摄像头管理主页页面跳转
@bp.get('/')
@authorize("system:camera:main")
def index():
    return render_template('system/hk_camera/main.html')


# 表格数据
@bp.get('/data')
@authorize("system:camera:main")
def table():
    # 部门id
    stationId = request.args.get('stationId', type=int)
    # 分局id
    parentId = request.args.get('parentId', type=int)
    sort_field = request.args.get('sort', 'id')  # 排序字段，默认按照id排序
    sort_order = request.args.get('order', 'asc')  # 排序方式，默认升序
    filters = [HKCamera.is_delete == 0]
    if stationId:
        if stationId:
            if stationId in dept_auth():
                filters.append(HKCamera.dept_id == stationId)
        # filters.append(Camera.dept_id == stationId)
        cameras = HKCamera.query.filter(*filters)
    elif parentId:
        # filters.append(Camera.sub_id == parentId)
        if parentId in sub_auth():
            print("sub_id",parentId)
            print("dept_id",dept_auth())
            filters.append(HKCamera.sub_id == parentId)
            filters.append(HKCamera.dept_id.in_(dept_auth()))
        cameras = HKCamera.query.filter(*filters)
        # cameras = Camera.query.filter(*filters)
        # station_ids = Station.query.filter(Station.is_delete == 0, Station.parent_id == parentId).with_entities(
        #     Station.id).all()
        # station_ids = [id for (id,) in station_ids]  # 将查询结果的元组转换为列表
        # # print("ids", station_ids)
        # # 使用 or_ 进行多条件查询
        # if station_ids:
        #     station_unit_ids = Station.query.filter(Station.is_delete == 0,
        #                                             Station.parent_id.in_(station_ids)).with_entities(
        #         Station.id).all()
        #     station_unit_ids = [id_[0] for id_ in station_unit_ids]
        #     if station_unit_ids:
        #         cameras = Camera.query.filter(Camera.station_id.in_(station_unit_ids), *filters)
        #     else:
        #         cameras = Camera.query.filter(*filters)
        # else:
        #     cameras = Camera.query.filter(*filters)
    else:
        filters.append(HKCamera.dept_id.in_(dept_auth()))
        cameras = HKCamera.query.filter(*filters)
    # 根据传入的排序字段和排序方式进行排序
    if sort_order == 'desc':
        cameras = cameras.order_by(desc(getattr(HKCamera, sort_field)))
    else:
        cameras = cameras.order_by(asc(getattr(HKCamera, sort_field)))
    # 执行分页
    cameras = cameras.layui_paginate()
    # if role_name:
    #     filters.append(Role.name.contains(role_name))
    # if role_code:
    #     filters.append(Role.code.contains(role_code))

    #   .order_by(station_alias.id)\
    # station_parent = Station.query.filter(Station.is_delete == 0, Station.type == 2)
    # station_dict = {station.id: station.dept_name for station in station_parent}
    return table_api(data=HkCameraOutSchema(many=True).dump(cameras), count=cameras.total)


# 启用
# @bp.put('/enable')
# @authorize("system:camera:edit", log=True)
# def enable():
#     id = request.get_json(force=True).get('cameraId')
#     if id:
#         res = enable_status(HKCamera, id)
#
#         if not res:
#             return fail_api(msg="出错啦")
#         # 启动多线程
#         camera_instance = curd.get_one_by_id(HKCamera, id)
#         station = Station(
#             id=camera_instance.station.id,
#             dept_name=camera_instance.station.dept_name,
#             leader=camera_instance.station.leader,
#             phone=camera_instance.station.phone,
#             is_delete=camera_instance.station.is_delete,
#             type=camera_instance.station.type,
#             remark=camera_instance.station.remark,
#             address=camera_instance.station.address,
#             create_at=camera_instance.station.create_at,
#             update_at=camera_instance.station.update_at,
#             # update_at=camera_instance.station.update_at,
#             parent_id=camera_instance.station.parent_id
#         )
#         camera_info = Camera(
#             id=camera_instance.id,
#             camera_name=camera_instance.camera_name,
#             camera_ip=camera_instance.camera_ip,
#             camera_port=camera_instance.camera_port,
#             camera_username=camera_instance.camera_username,
#             camera_password=camera_instance.camera_password,
#             camera_description=camera_instance.camera_description,
#             camera_url=camera_instance.camera_url,
#             enable=camera_instance.enable,
#             camera_type=camera_instance.camera_type,
#             is_delete=camera_instance.is_delete,
#             station_id=camera_instance.station_id,
#             create_time=camera_instance.create_time,
#             update_time=camera_instance.update_time,
#             station=station,
#             sub_id=camera_instance.sub_id,
#             dept_id=camera_instance.dept_id
#         )
#         current_app.config['threadManager'].add_thread(camera_info)
#         # add_new_detect(camera)
#         # add_new_detect(camera.id, camera.camera_url, camera.station_id, camera.camera_type)
#         return success_api(msg="启动成功")
#     return fail_api(msg="数据错误")


# 禁用
# @bp.put('/disable')
# @authorize("system:camera:edit", log=True)
# def dis_enable():
#     _id = request.get_json(force=True).get('cameraId')
#     if _id:
#         res = disable_status(Camera, _id)
#         if not res:
#             return fail_api(msg="出错啦")
#         if current_app.config['threadManager'].stop_thread(_id):
#             print(f"{_id}关闭成功")
#         else:
#             print(f"{_id}关闭失败")
#         return success_api(msg="禁用成功")
#     return fail_api(msg="数据错误")


# 监控编辑
@bp.get('/edit/<int:id>')
@authorize("system:camera:edit", log=True)
def edit(id):
    # 把当前的信息查出来
    c = get_one_by_id(model=HKCamera, id=id)

    # 把所有的区查询出来
    # root_stations = Station.query.filter(Station.is_delete == 0, Station.type == 3)
    # # 当前区是什么
    # root_id = Station.query.filter(Station.is_delete == 0, Station.id == c.station.parent_id).with_entities(
    #     Station.parent_id).first()
    # # 当前区下有哪些部门
    # parent_station = Station.query.filter(Station.is_delete == 0,
    #                                       Station.parent_id == root_id[0]).all()
    # # 部门下的区域
    # stations = Station.query.filter(Station.is_delete == 0,
    #                                 Station.parent_id == c.station.parent_id).all()
    # return render_template('system/camera/edit.html', camera=c, rootStations=root_stations, stations=stations,
    #                        rootId=root_id[0],
    #                        parentStation=parent_station)
    return render_template('system/hk_camera/edit.html', camera=c)


@bp.get('/add')
@authorize("system:camera:add", log=True)
def add():
    # stations = Station.query.filter(Station.is_delete == 0, Station.type == 2).with_entities(Station.id,
    #                                                                                          Station.dept_name)

    return render_template('system/hk_camera/add.html')


@bp.post('/save')
@authorize("system:camera:add", log=True)
def save():
    req_json = request.get_json(force=True)
    username = str_escape(req_json.get("userName"))
    password = str_escape(req_json.get("passWord"))
    ip = str_escape(req_json.get("location"))
    # url = "rtsp://" + username + ":" + str(password) + "@" + ip + ":554"
    # url = url.strip()
    camera = HKCamera(
        name=str_escape(req_json.get("cameraName")),
        # station_id=str_escape(req_json.get("areaId")),
        dept_id=str_escape(req_json.get("stationId")),
        sub_id=str_escape(req_json.get("parentId")),
        username=username,
        password=password,
        ip=ip,
        port=str_escape(req_json.get('port')),
        type=str_escape(req_json.get("cameraType")),
        channel=str_escape(req_json.get("channel")),
    )
    db.session.add(camera)
    db.session.commit()
    return success_api(msg="成功")


# 更新
@bp.put('/update')
@authorize("system:camera:edit", log=True)
def update():
    req_json = request.get_json(force=True)
    id = req_json.get("cameraId")
    username = str_escape(req_json.get("userName"))
    password = str_escape(req_json.get("passWord"))
    ip = str_escape(req_json.get("location"))

    data = {
        "name": str_escape(req_json.get("cameraName")),
        "username": username,
        "password": password,
        "ip": ip,
        "type": str_escape(req_json.get("cameraType")),
        "port": str_escape(req_json.get('port')),
        "dept_id": str_escape(req_json.get('stationId')),
        "sub_id": str_escape(req_json.get('parentId')),
        "channel": str_escape(req_json.get('channel')),
    }
    camera = HKCamera.query.filter_by(id=id).update(data)
    db.session.commit()
    if not camera:
        return fail_api(msg="更新监控信息失败")
    return success_api(msg="更新监控信息成功")


@bp.delete('/remove/<int:id>')
@authorize("system:camera:remove", log=True)
def remove(id):
    # r = curd.logic_delete_one_by_id(Camera, id)
    r = HKCamera.query.filter_by(id=id).update({"is_delete": 1, "enable": 0})
    db.session.commit()
    if not r:
        return fail_api(msg="删除失败")
    return success_api(msg="删除成功")


@bp.get('/add_dept')
@authorize("system:camera:main", log=True)
def add_dept():
    # 把所有的区查询出来
    root_stations = Station.query.filter(Station.is_delete == 0, Station.type == 3).with_entities(
        Station.id).all()
    for id in root_stations:
        result_list = []
        # id[0]
        # 查区以下的派出所部门
        c_stations = Station.query.filter(Station.is_delete == 0, Station.type == 2,
                                          Station.parent_id == id[0]).with_entities(
            Station.id).all()
        # # 将查询结果转换为列表，并追加到结果列表中
        # result_list.extend([c[0] for c in c_stations])
        # print(f"区级id={id[0]}的下面的所有部门{result_list}")
        for c in c_stations:
            # 创建一个 DeptRelations 对象并设置相应属性值
            dept_relation = DeptRelations(
                type=1,  # 假设类型为1
                dept_id=c[0],  # 设置单位的ID
                sub_id=id[0]  # 设置分局ID，这里设置为0，你需要根据实际情况设置正确的值
            )
            result_list.append(c[0])
            # 将 DeptRelations 对象保存到数据库中
            db.session.add(dept_relation)
        print(f"区级id={id[0]}的下面的所有部门{result_list}")
    # 提交所有对象的变更到数据库
    db.session.commit()
    return ""


@bp.get('/add_room')
@authorize("system:camera:main", log=True)
def add_room():
    # 把所有的区查询出来
    root_stations = Station.query.filter(Station.is_delete == 0, Station.type == 3).with_entities(
        Station.id).all()
    for id in root_stations:
        result_list = []
        # id[0]
        # 查区以下的派出所部门
        c_stations = Station.query.filter(Station.is_delete == 0, Station.type == 2,
                                          Station.parent_id == id[0]).with_entities(
            Station.id).all()
        # # 将查询结果转换为列表，并追加到结果列表中
        # result_list.extend([c[0] for c in c_stations])
        # print(f"区级id={id[0]}的下面的所有部门{result_list}")
        for c in c_stations:
            room_stations = Station.query.filter(Station.is_delete == 0,
                                                 Station.parent_id == c[0]).with_entities(
                Station.id).all()
            result_list = []
            for room in room_stations:
                # 创建一个 DeptRelations 对象并设置相应属性值
                dept_relation = DeptRelations(
                    type=0,  # 假设类型为0
                    station_id=room[0],
                    dept_id=c[0],  # 设置单位的ID
                    sub_id=id[0]  # 设置分局ID，这里设置为0，你需要根据实际情况设置正确的值
                )
                result_list.append(room[0])
                # 将 DeptRelations 对象保存到数据库中
                db.session.add(dept_relation)
            print(f"部门级id={c[0]}的下面的所有询问室{result_list}")
    # 提交所有对象的变更到数据库
    db.session.commit()
    return ""


# 开启检测
@bp.put('/enable')
@authorize("system:camera:edit", log=True)
def enable():
    id = request.get_json(force=True).get('cameraId')
    if id:
        res = enable_status(HKCamera, id)

        if not res:
            return fail_api(msg="出错啦")
        # 启动多线程
        camera_instance = curd.get_one_by_id(HKCamera, id)
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
        current_app.config['hk_threadManager'].add_thread(camera_info)
        # add_new_detect(camera)
        # add_new_detect(camera.id, camera.camera_url, camera.station_id, camera.camera_type)
        return success_api(msg="启动成功")
    return fail_api(msg="数据错误")


@bp.put('/disable')
@authorize("system:camera:edit", log=True)
def dis_enable():
    _id = request.get_json(force=True).get('cameraId')
    if _id:
        res = disable_status(HKCamera, _id)
        if not res:
            return fail_api(msg="出错啦")
        if current_app.config['hk_threadManager'].stop_thread(_id):
            current_app.logger.info(f"工服检测线程 camera {_id} 已关闭")
        else:
            current_app.logger.warning(f"工服检测线程 camera {_id} 关闭失败")
        return success_api(msg="禁用成功")
    return fail_api(msg="数据错误")


@bp.get('/violations')
@authorize("system:camera:main")
def violations():
    """
    查询违规记录列表。
    query 参数：
      camera_id (int, 可选)：按摄像头 ID 过滤
      limit     (int, 可选)：返回条数，默认 100，上限 500
    """
    camera_id = request.args.get('camera_id', type=int)
    limit = min(request.args.get('limit', 100, type=int), 500)
    filters = [ViolatePhoto.is_delete == 0]
    if camera_id:
        filters.append(ViolatePhoto.camera_id == camera_id)
    records = ViolatePhoto.query.filter(*filters).order_by(
        desc(ViolatePhoto.position_time)
    ).limit(limit).all()
    data = [
        {
            "id": r.id,
            "camera_id": r.camera_id,
            "violate_id": r.violate_id,
            "href": r.href,
            "position_time": r.position_time.strftime("%Y-%m-%d %H:%M:%S") if r.position_time else None,
            "station_id": r.station_id,
            "dept_id": r.dept_id,
            "sub_id": r.sub_id,
        }
        for r in records
    ]
    return jsonify({"code": 0, "count": len(data), "data": data})


@bp.get('/violations/camera/<int:camera_id>')
@authorize("system:camera:main")
def violations_by_camera(camera_id):
    """
    按摄像头 ID 查询该摄像头的违规记录，最多返回最新 200 条。
    """
    records = ViolatePhoto.query.filter(
        ViolatePhoto.camera_id == camera_id,
        ViolatePhoto.is_delete == 0
    ).order_by(desc(ViolatePhoto.position_time)).limit(200).all()
    data = [
        {
            "id": r.id,
            "camera_id": r.camera_id,
            "violate_id": r.violate_id,
            "href": r.href,
            "position_time": r.position_time.strftime("%Y-%m-%d %H:%M:%S") if r.position_time else None,
            "station_id": r.station_id,
            "dept_id": r.dept_id,
            "sub_id": r.sub_id,
        }
        for r in records
    ]
    return jsonify({"code": 0, "camera_id": camera_id, "count": len(data), "data": data})


def save_violate_photo(type, id, frame, station_id, dept_id, sub_id, path,
                       datetime=datetime.now(), rule_name=None, extra_meta=None):
    """
    保存违规证据图并写入数据库。
    :param type:       违规类型 ID
    :param id:         摄像头 ID
    :param frame:      证据图（numpy 数组）
    :param station_id: 站点 ID
    :param dept_id:    单位 ID
    :param sub_id:     部门 ID
    :param path:       图片保存目录
    :param datetime:   违规发生时间
    :param rule_name:  违规规则名称（如"未穿工服"），用于日志动态展示
    :param extra_meta: 扩展元数据（预留，暂不入库）
    """
    from applications.models import ViolatePhoto
    unique_string = str(uuid.uuid4())
    filename = unique_string + '.jpg'
    file_url = '/_uploads/photos/' + filename
    if not os.path.exists(path):
        os.makedirs(path)
    cv2.imwrite(os.path.join(path, filename), frame)
    href = file_url
    display_name = rule_name if rule_name else f"违规类型{type}"
    current_app.logger.warning(
        f"工服检测-摄像头ID：{id} [{display_name}] 证据图已保存：{file_url}")
    violatePhoto = ViolatePhoto(
        violate_id=type,
        camera_id=id,
        href=href,
        position_time=datetime,
        is_delete=0,
        station_id=station_id,
        sub_id=sub_id,
        dept_id=dept_id
    )
    db.session.add(violatePhoto)
    db.session.commit()
