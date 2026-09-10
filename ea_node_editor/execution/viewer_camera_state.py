from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _vector3(value: Any) -> tuple[float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    components = [_coerce_float(item) for item in value]
    if any(component is None for component in components):
        return None
    return (float(components[0]), float(components[1]), float(components[2]))


def _camera_position_triplet(value: Any) -> tuple[
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    first = _vector3(value[0])
    second = _vector3(value[1])
    third = _vector3(value[2])
    if first is None or second is None or third is None:
        return None
    return (first, second, third)


def _camera_position_payload(camera_state: Mapping[str, Any]) -> Any:
    explicit = _camera_position_triplet(camera_state.get("camera_position"))
    if explicit is not None:
        return [explicit[0], explicit[1], explicit[2]]
    position = _vector3(camera_state.get("position"))
    focal_point = _vector3(camera_state.get("focal_point"))
    view_up = _vector3(camera_state.get("viewup", camera_state.get("view_up")))
    if position is not None and focal_point is not None and view_up is not None:
        return [position, focal_point, view_up]
    if position is not None:
        return position
    return None


def _assign_camera_vector(camera: Any, *, attribute: str, setter: str, value: tuple[float, float, float]) -> bool:
    if hasattr(camera, attribute):
        setattr(camera, attribute, value)
        return True
    method = getattr(camera, setter, None)
    if callable(method):
        method(*value)
        return True
    return False


def _assign_camera_scalar(camera: Any, *, attribute: str, setter: str, value: float) -> bool:
    if hasattr(camera, attribute):
        setattr(camera, attribute, value)
        return True
    method = getattr(camera, setter, None)
    if callable(method):
        method(value)
        return True
    return False


def _assign_camera_bool(camera: Any, *, attribute: str, setter: str, value: bool) -> bool:
    if hasattr(camera, attribute):
        setattr(camera, attribute, value)
        return True
    method = getattr(camera, setter, None)
    if callable(method):
        method(value)
        return True
    return False


def _camera_vector(camera: Any, *, attribute: str, getter: str) -> tuple[float, float, float] | None:
    if camera is None:
        return None
    if hasattr(camera, attribute):
        return _vector3(getattr(camera, attribute))
    method = getattr(camera, getter, None)
    if callable(method):
        try:
            return _vector3(method())
        except TypeError:
            return None
    return None


def _camera_scalar(camera: Any, *, attribute: str, getter: str) -> float | None:
    if camera is None:
        return None
    if hasattr(camera, attribute):
        return _coerce_float(getattr(camera, attribute))
    method = getattr(camera, getter, None)
    if callable(method):
        try:
            return _coerce_float(method())
        except TypeError:
            return None
    return None


def _camera_bool(camera: Any, *, attribute: str, getter: str) -> bool | None:
    if camera is None:
        return None
    if hasattr(camera, attribute):
        return bool(getattr(camera, attribute))
    method = getattr(camera, getter, None)
    if callable(method):
        try:
            return bool(method())
        except TypeError:
            return None
    return None


def apply_camera_state(target: Any, camera_state: Mapping[str, Any]) -> bool:
    camera_payload = _mapping(camera_state)
    if not camera_payload:
        reset_camera = getattr(target, "reset_camera", None)
        if callable(reset_camera):
            reset_camera()
        return False

    camera_applied = False
    camera_position = _camera_position_payload(camera_payload)
    if camera_position is not None and hasattr(target, "camera_position"):
        setattr(target, "camera_position", camera_position)
        camera_applied = True

    camera = getattr(target, "camera", None)
    if camera is not None:
        position = _vector3(camera_payload.get("position"))
        if position is not None and camera_position is None:
            camera_applied = _assign_camera_vector(
                camera,
                attribute="position",
                setter="SetPosition",
                value=position,
            ) or camera_applied
        focal_point = _vector3(camera_payload.get("focal_point"))
        if focal_point is not None:
            camera_applied = _assign_camera_vector(
                camera,
                attribute="focal_point",
                setter="SetFocalPoint",
                value=focal_point,
            ) or camera_applied
        view_up = _vector3(camera_payload.get("viewup", camera_payload.get("view_up")))
        if view_up is not None:
            camera_applied = _assign_camera_vector(
                camera,
                attribute="up",
                setter="SetViewUp",
                value=view_up,
            ) or camera_applied

        view_angle = _coerce_float(camera_payload.get("view_angle"))
        if view_angle is not None:
            camera_applied = _assign_camera_scalar(
                camera,
                attribute="view_angle",
                setter="SetViewAngle",
                value=view_angle,
            ) or camera_applied

        if "parallel_projection" in camera_payload:
            camera_applied = _assign_camera_bool(
                camera,
                attribute="parallel_projection",
                setter="SetParallelProjection",
                value=bool(camera_payload.get("parallel_projection")),
            ) or camera_applied
        parallel_scale = _coerce_float(camera_payload.get("parallel_scale"))
        if parallel_scale is not None:
            camera_applied = _assign_camera_scalar(
                camera,
                attribute="parallel_scale",
                setter="SetParallelScale",
                value=parallel_scale,
            ) or camera_applied

        zoom_value = _coerce_float(camera_payload.get("zoom"))
        zoom = getattr(camera, "zoom", None)
        if view_angle is None and zoom_value is not None and callable(zoom):
            zoom(zoom_value)
            camera_applied = True

    if camera_applied:
        return True
    reset_camera = getattr(target, "reset_camera", None)
    if callable(reset_camera):
        reset_camera()
    return False


def extract_camera_state(target: Any) -> dict[str, Any]:
    camera_state: dict[str, Any] = {}
    camera_position = _camera_position_triplet(getattr(target, "camera_position", None))
    if camera_position is not None:
        camera_state["position"] = list(camera_position[0])
        camera_state["focal_point"] = list(camera_position[1])
        camera_state["viewup"] = list(camera_position[2])
        camera_state["camera_position"] = [
            list(camera_position[0]),
            list(camera_position[1]),
            list(camera_position[2]),
        ]

    camera = getattr(target, "camera", None)
    position = _camera_vector(camera, attribute="position", getter="GetPosition")
    focal_point = _camera_vector(camera, attribute="focal_point", getter="GetFocalPoint")
    view_up = (
        _camera_vector(camera, attribute="up", getter="GetViewUp")
        or _camera_vector(camera, attribute="view_up", getter="GetViewUp")
    )

    if position is None and camera_position is not None:
        position = camera_position[0]
    if focal_point is None and camera_position is not None:
        focal_point = camera_position[1]
    if view_up is None and camera_position is not None:
        view_up = camera_position[2]

    if position is not None:
        camera_state["position"] = list(position)
    if focal_point is not None:
        camera_state["focal_point"] = list(focal_point)
    if view_up is not None:
        camera_state["viewup"] = list(view_up)
    if position is not None and focal_point is not None and view_up is not None:
        camera_state["camera_position"] = [
            list(position),
            list(focal_point),
            list(view_up),
        ]

    parallel_projection = _camera_bool(
        camera,
        attribute="parallel_projection",
        getter="GetParallelProjection",
    )
    if parallel_projection is not None:
        camera_state["parallel_projection"] = parallel_projection

    parallel_scale = _camera_scalar(
        camera,
        attribute="parallel_scale",
        getter="GetParallelScale",
    )
    if parallel_scale is not None:
        camera_state["parallel_scale"] = parallel_scale

    view_angle = _camera_scalar(
        camera,
        attribute="view_angle",
        getter="GetViewAngle",
    )
    if view_angle is not None:
        camera_state["view_angle"] = view_angle

    return camera_state


__all__ = [
    "apply_camera_state",
    "extract_camera_state",
]
