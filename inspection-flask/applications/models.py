from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

import settings


@dataclass
class Station:
    id: int | None = None
    dept_name: str = ""
    parent_id: int | None = None
    leader: str = ""
    phone: str = ""
    remark: str = ""
    address: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HKCamera:
    id: int
    name: str = ""
    ip: str = ""
    port: int = settings.DEFAULT_CAMERA_PORT
    username: str = ""
    password: str = ""
    enable: int = 0
    type: int = 0
    is_delete: int = 0
    station_id: int | None = None
    create_time: datetime = field(default_factory=datetime.now)
    update_time: datetime = field(default_factory=datetime.now)
    station: Station | None = None
    sub_id: int | None = None
    dept_id: int | None = None
    channel: int = settings.DEFAULT_CAMERA_CHANNEL
    channel_type: int = 1
    frame_path: str | None = None
    roi: list[int] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["create_time"] = self.create_time.isoformat()
        data["update_time"] = self.update_time.isoformat()
        return data


@dataclass
class ViolatePhoto:
    violate_id: int | str
    camera_id: int
    href: str
    position_time: datetime
    station_id: int | None = None
    dept_id: int | None = None
    sub_id: int | None = None
    rule_code: str | None = None
    rule_name: str | None = None
    extra_meta: dict[str, Any] | None = None
    is_delete: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["position_time"] = self.position_time.isoformat()
        return data
