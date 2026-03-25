import traceback
import uuid
from datetime import datetime, timedelta
import os
import threading
import time
from types import SimpleNamespace

import cv2
from flask import Blueprint, request, render_template, jsonify, current_app, Response
from sqlalchemy import desc, asc, inspect, text
from sqlalchemy.orm import aliased

from applications.common import curd
from applications.common.curd import enable_status, disable_status, get_one_by_id
# from applications.common.test import log_writer
from applications.common.user_auth import dept_auth, sub_auth
from applications.common.utils.http import fail_api, success_api, table_api
from applications.common.utils.rights import authorize
from applications.common.utils.thread_camera import detect

import settings
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
    stationId = request.args.get('stationId', type=int)
    parentId = request.args.get('parentId', type=int)
    sort_field = request.args.get('sort', 'id')
    sort_order = request.args.get('order', 'asc')

    _SORT_WHITELIST = {"id", "name", "ip", "enable", "create_time", "update_time", "type", "port"}
    if sort_field not in _SORT_WHITELIST:
        sort_field = "id"

    filters = [HKCamera.is_delete == 0]
    authorized_depts = dept_auth()

    if stationId:
        if stationId not in authorized_depts:
            return table_api(data=[], count=0)
        filters.append(HKCamera.dept_id == stationId)
    elif parentId:
        if parentId not in sub_auth():
            return table_api(data=[], count=0)
        filters.append(HKCamera.sub_id == parentId)
        filters.append(HKCamera.dept_id.in_(authorized_depts))
    else:
        filters.append(HKCamera.dept_id.in_(authorized_depts))

    cameras = HKCamera.query.filter(*filters)
    order_col = getattr(HKCamera, sort_field, HKCamera.id)
    cameras = cameras.order_by(desc(order_col) if sort_order == 'desc' else asc(order_col))
    cameras = cameras.layui_paginate()
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


def _validate_camera_params(ip, port, channel):
    """校验摄像头关键参数，返回 (ok, error_msg)。"""
    import re
    if ip and not re.match(r'^\d{1,3}(\.\d{1,3}){3}$', ip):
        return False, "IP 地址格式不合法"
    if port is not None:
        try:
            p = int(port)
            if not (1 <= p <= 65535):
                return False, "端口号范围应为 1-65535"
        except (TypeError, ValueError):
            return False, "端口号必须为整数"
    if channel is not None:
        try:
            c = int(channel)
            if c < 1:
                return False, "通道号必须为正整数"
        except (TypeError, ValueError):
            return False, "通道号必须为正整数"
    return True, ""


@bp.post('/save')
@authorize("system:camera:add", log=True)
def save():
    req_json = request.get_json(force=True)
    username = str_escape(req_json.get("userName"))
    password = str_escape(req_json.get("passWord"))
    ip = str_escape(req_json.get("location"))
    port = str_escape(req_json.get('port'))
    channel = str_escape(req_json.get("channel"))

    ok, err = _validate_camera_params(ip, port, channel)
    if not ok:
        return fail_api(msg=err)

    camera = HKCamera(
        name=str_escape(req_json.get("cameraName")),
        dept_id=str_escape(req_json.get("stationId")),
        sub_id=str_escape(req_json.get("parentId")),
        username=username,
        password=password,
        ip=ip,
        port=port,
        type=str_escape(req_json.get("cameraType")),
        channel=channel,
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
    port = str_escape(req_json.get('port'))
    channel = str_escape(req_json.get('channel'))

    ok, err = _validate_camera_params(ip, port, channel)
    if not ok:
        return fail_api(msg=err)

    data = {
        "name": str_escape(req_json.get("cameraName")),
        "username": username,
        "password": password,
        "ip": ip,
        "type": str_escape(req_json.get("cameraType")),
        "port": port,
        "dept_id": str_escape(req_json.get('stationId')),
        "sub_id": str_escape(req_json.get('parentId')),
        "channel": channel,
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


@bp.post('/add_dept')
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


@bp.post('/add_room')
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
    if not id:
        return fail_api(msg="数据错误")

    res = enable_status(HKCamera, id)
    if not res:
        return fail_api(msg="出错啦")

    camera_instance = curd.get_one_by_id(HKCamera, id)
    if camera_instance is None:
        disable_status(HKCamera, id)
        return fail_api(msg="摄像头不存在")

    camera_info = SimpleNamespace(
        id=camera_instance.id,
        name=getattr(camera_instance, "name", None),
        ip=getattr(camera_instance, "ip", None),
        port=getattr(camera_instance, "port", None),
        username=getattr(camera_instance, "username", None),
        password=getattr(camera_instance, "password", None),
        channel=getattr(camera_instance, "channel", None),
        type=getattr(camera_instance, "type", None),
        enable=camera_instance.enable,
        is_delete=camera_instance.is_delete,
        station_id=getattr(camera_instance, "station_id", None),
        dept_id=getattr(camera_instance, "dept_id", None),
        sub_id=getattr(camera_instance, "sub_id", None),
        roi=getattr(camera_instance, "roi", None),
        frame_path=getattr(camera_instance, "frame_path", None),
    )

    started = current_app.config['hk_threadManager'].add_thread(camera_info)
    if not started:
        disable_status(HKCamera, id)
        init_error = current_app.config.get("detection_model_init_error") or "检测模型未就绪"
        current_app.logger.error("工服检测线程 camera %s 启动失败: %s", id, init_error)
        return fail_api(msg=f"启动失败：{init_error}")
    return success_api(msg="启动成功")


@bp.put('/disable')
@authorize("system:camera:edit", log=True)
def dis_enable():
    _id = request.get_json(force=True).get('cameraId')
    if not _id:
        return fail_api(msg="数据错误")

    thread_stopped = current_app.config['hk_threadManager'].stop_thread(_id)
    if thread_stopped:
        current_app.logger.info("工服检测线程 camera %s 已关闭", _id)
    else:
        current_app.logger.warning("工服检测线程 camera %s 关闭失败或不存在", _id)

    res = disable_status(HKCamera, _id)
    if not res:
        return fail_api(msg="数据库状态更新失败")

    if not thread_stopped:
        return success_api(msg="已禁用（线程可能未完全退出，将在下次重启时清理）")
    return success_api(msg="禁用成功")


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
    authorized_depts = dept_auth()
    filters = [ViolatePhoto.is_delete == 0, ViolatePhoto.dept_id.in_(authorized_depts)]
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
            "rule_code": r.rule_code,
            "rule_name": r.rule_name,
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
    校验 camera_id 归属当前用户权限范围。
    """
    authorized_depts = dept_auth()
    camera = HKCamera.query.filter_by(id=camera_id, is_delete=0).first()
    if camera is None or camera.dept_id not in authorized_depts:
        return jsonify({"code": 0, "camera_id": camera_id, "count": 0, "data": []})
    records = ViolatePhoto.query.filter(
        ViolatePhoto.camera_id == camera_id,
        ViolatePhoto.is_delete == 0,
        ViolatePhoto.dept_id.in_(authorized_depts),
    ).order_by(desc(ViolatePhoto.position_time)).limit(200).all()
    data = [
        {
            "id": r.id,
            "camera_id": r.camera_id,
            "violate_id": r.violate_id,
            "rule_code": r.rule_code,
            "rule_name": r.rule_name,
            "href": r.href,
            "position_time": r.position_time.strftime("%Y-%m-%d %H:%M:%S") if r.position_time else None,
            "station_id": r.station_id,
            "dept_id": r.dept_id,
            "sub_id": r.sub_id,
        }
        for r in records
    ]
    return jsonify({"code": 0, "camera_id": camera_id, "count": len(data), "data": data})


def _normalize_rule_value(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _coerce_rule_id(value):
    normalized = _normalize_rule_value(value)
    if normalized is None:
        return None
    try:
        return int(normalized)
    except (TypeError, ValueError):
        return None


def _load_violate_rule_columns():
    cached_columns = current_app.config.get("violate_rule_table_columns")
    if cached_columns is not None:
        return cached_columns

    inspector = inspect(db.engine)
    if not inspector.has_table("admin_violate_rule"):
        current_app.config["violate_rule_table_columns"] = set()
        return set()

    columns = {column["name"] for column in inspector.get_columns("admin_violate_rule")}
    current_app.config["violate_rule_table_columns"] = columns
    return columns


def _query_violate_rule(columns, column_name, value):
    if column_name not in columns:
        return None

    select_fields = ["id"]
    if "rule_code" in columns:
        select_fields.append("rule_code")
    elif "code" in columns:
        select_fields.append("code")

    if "rule_name" in columns:
        select_fields.append("rule_name")
    elif "name" in columns:
        select_fields.append("name")

    sql = text(
        f"SELECT {', '.join(select_fields)} "
        f"FROM admin_violate_rule "
        f"WHERE {column_name} = :value "
        f"ORDER BY id ASC LIMIT 1"
    )
    return db.session.execute(sql, {"value": value}).mappings().first()


def _extract_rule_meta(row):
    if row is None:
        return None, None, None

    resolved_id = row.get("id")
    resolved_code = row.get("rule_code") or row.get("code")
    resolved_name = row.get("rule_name") or row.get("name")

    try:
        resolved_id = int(resolved_id)
    except (TypeError, ValueError):
        resolved_id = None

    return resolved_id, _normalize_rule_value(resolved_code), _normalize_rule_value(resolved_name)


_RULE_CACHE_TTL_SECONDS = 300


def _resolve_violate_rule(rule_value, rule_name=None):
    normalized_value = _normalize_rule_value(rule_value)
    normalized_name = _normalize_rule_value(rule_name)
    cache_key = (normalized_value, normalized_name)
    cache_store = current_app.config.setdefault("violate_rule_resolution_cache", {})
    cache_ts = current_app.config.setdefault("violate_rule_cache_ts", {})

    cached_time = cache_ts.get(cache_key)
    if cached_time is not None and cache_key in cache_store:
        if (time.time() - cached_time) < _RULE_CACHE_TTL_SECONDS:
            return cache_store[cache_key]
        cache_store.pop(cache_key, None)
        cache_ts.pop(cache_key, None)

    resolved_id = _coerce_rule_id(normalized_value)
    resolved_code = normalized_value if resolved_id is None else None
    resolved_name = normalized_name
    table_available = False

    try:
        columns = _load_violate_rule_columns()
        table_available = bool(columns)
        lookup_order = []

        if resolved_id is not None and "id" in columns:
            lookup_order.append(("id", resolved_id))
        if resolved_code:
            if "rule_code" in columns:
                lookup_order.append(("rule_code", resolved_code))
            if "code" in columns:
                lookup_order.append(("code", resolved_code))
        if resolved_name:
            if "rule_name" in columns:
                lookup_order.append(("rule_name", resolved_name))
            if "name" in columns:
                lookup_order.append(("name", resolved_name))

        seen = set()
        for column_name, value in lookup_order:
            key = (column_name, value)
            if key in seen:
                continue
            seen.add(key)
            row = _query_violate_rule(columns, column_name, value)
            if row is None:
                continue
            resolved_id, db_rule_code, db_rule_name = _extract_rule_meta(row)
            resolved_code = db_rule_code or resolved_code
            resolved_name = db_rule_name or resolved_name
            break
    except Exception:
        current_app.logger.exception("Resolve violate rule failed for value=%s", normalized_value)

    if resolved_id is None and resolved_code:
        default_rule_code = _normalize_rule_value(getattr(settings, "WORKWEAR_VIOLATION_TYPE", None))
        configured_rule_id = _coerce_rule_id(getattr(settings, "WORKWEAR_VIOLATION_ID", None))
        if configured_rule_id is not None and resolved_code == default_rule_code:
            resolved_id = configured_rule_id

    if resolved_name is None and resolved_code == _normalize_rule_value(getattr(settings, "WORKWEAR_VIOLATION_TYPE", None)):
        resolved_name = getattr(settings, "WORKWEAR_VIOLATION_NAME", "未穿工服")

    if table_available and resolved_id is None:
        result = (None, resolved_code, resolved_name)
    else:
        result = (resolved_id, resolved_code, resolved_name)

    cache_store[cache_key] = result
    cache_ts[cache_key] = time.time()
    return result


def save_violate_photo(rule_value, id, frame, station_id, dept_id, sub_id, path,
                       position_time=None, rule_name=None, extra_meta=None):
    """
    保存违规证据图并写入数据库。
    :param type:       违规类型 ID
    :param id:         摄像头 ID
    :param frame:      证据图（numpy 数组）
    :param station_id: 站点 ID
    :param dept_id:    单位 ID
    :param sub_id:     部门 ID
    :param path:       图片保存目录
    :param position_time: 违规发生时间
    :param rule_name:  违规规则名称（如"未穿工服"），用于日志动态展示
    :param extra_meta: 扩展元数据（预留，暂不入库）
    """
    from applications.models import ViolatePhoto

    if frame is None or getattr(frame, "size", 0) == 0:
        current_app.logger.error("工服检测-摄像头ID：%s 证据图为空，取消落库", id)
        return None

    resolved_rule_id, resolved_rule_code, resolved_rule_name = _resolve_violate_rule(
        rule_value,
        rule_name=rule_name,
    )
    if resolved_rule_id is None:
        current_app.logger.warning(
            "camera %s violate_rule_id 未解析 (rule_value=%s rule_name=%s)，将以 rule_code 入库",
            id, rule_value, rule_name,
        )

    type = resolved_rule_id
    rule_name = resolved_rule_name or rule_name

    unique_string = str(uuid.uuid4())
    filename = unique_string + '.jpg'
    file_url = '/_uploads/photos/' + filename
    if not os.path.exists(path):
        os.makedirs(path)
    file_path = os.path.join(path, filename)
    if not cv2.imwrite(file_path, frame):
        current_app.logger.error("工服检测-摄像头ID：%s 证据图保存失败：%s", id, file_path)
        return None
    href = file_url
    display_name = rule_name if rule_name else f"违规类型{type}"
    current_app.logger.warning(
        f"工服检测-摄像头ID：{id} [{display_name}] 证据图已保存：{file_url}")
    violatePhoto = ViolatePhoto(
        violate_id=type,
        camera_id=id,
        href=href,
        position_time=position_time or datetime.now(),
        is_delete=0,
        station_id=station_id,
        sub_id=sub_id,
        dept_id=dept_id
    )
    violatePhoto.rule_code = resolved_rule_code
    violatePhoto.rule_name = resolved_rule_name
    try:
        db.session.add(violatePhoto)
        db.session.commit()
    except Exception:
        db.session.rollback()
        if os.path.exists(file_path):
            os.remove(file_path)
        current_app.logger.exception("工服检测-摄像头ID：%s 违规记录写库失败，已回滚证据图", id)
        return None
    return href
