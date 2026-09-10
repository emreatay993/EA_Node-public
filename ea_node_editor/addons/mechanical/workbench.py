# Purpose: Own local Workbench and verify native whole-project save preservation.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_open_model.py, tests/mechanical_catalogue/test_workbench_save.py, tests/mechanical_catalogue/test_workbench_model_export.py

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import math
import os
import re
import socket
import stat
import subprocess
import time
import uuid
from collections import Counter
from ctypes import wintypes
from pathlib import Path
from typing import Any

from ea_node_editor.common.path_safety import is_reparse_point
from ea_node_editor.addons.mechanical.owner_process import (
    _WindowsKillJob,
    _creation_time_for_pid,
)


WORKBENCH_MODEL_COMPONENT_PREDICATE = r'''def _corex_has_model(component_ids):
    return any(value=='Model' or value.startswith('Model ') for value in component_ids)
'''


_WORKBENCH_SNAPSHOT_PREFIX = r'''import hashlib,json,math,os,traceback
try:
    unicode
except NameError:
    unicode=str
def _corex_text(value):
    return value if isinstance(value,unicode) else unicode(value)
''' + WORKBENCH_MODEL_COMPONENT_PREDICATE + r'''def _corex_sha(path):
    digest=hashlib.sha256()
    stream=open(path,'rb')
    try:
        while True:
            chunk=stream.read(1048576)
            if not chunk: break
            digest.update(chunk)
    finally:
        stream.close()
    return digest.hexdigest()
def _corex_path(value):
    return os.path.normcase(os.path.abspath(_corex_text(value)))
def _corex_ref(path,ref,registered,associations):
    exists=os.path.isfile(path)
    if ref is not None and bool(ref.Exists)!=exists: raise RuntimeError('native FileReference.Exists disagrees with its full Location')
    if ref is not None and exists and int(ref.Size)!=os.path.getsize(path): raise RuntimeError('native FileReference.Size disagrees with its full Location')
    return {'file_name':os.path.basename(path) if ref is None else _corex_text(ref.FileName),'display_text':os.path.basename(path) if ref is None else _corex_text(ref.DisplayText),'location':path,'location_key':_corex_path(path),'registered':bool(registered),'exists':exists,'size':os.path.getsize(path) if exists else 0,'sha256':_corex_sha(path) if exists else '','associations':sorted(associations)}
def _corex_snapshot():
    refs={};registered=set();associations={}
    for ref in GetCurrentRegisteredFiles():
        key=_corex_path(ref.Location);refs[key]=ref;registered.add(key)
    systems=[];models=[]
    for system in GetAllSystems():
        system_id=_corex_text(system.UserId);system_name=_corex_text(system.Name)
        components=[];component_ids=[]
        for component in system.Components:
            component_id=_corex_text(component.UserId)
            component_ids.append(component_id)
            components.append({'user_id':component_id,'directory_name':_corex_text(component.DirectoryName)})
            for ref in component.DataContainer.GetFiles():
                key=_corex_path(ref.Location);refs[key]=ref;associations.setdefault(key,[]).append(system_id+'|'+component_id)
        systems.append({'user_id':system_id,'name':system_name,'components':sorted(components,key=lambda row:(row['user_id'],row['directory_name']))})
        if _corex_has_model(component_ids):
            container=system.GetContainer(ComponentName='Model')
            model=container.GetMechanicalModel()
            models.append({'system_user_id':system_id,'file_name':_corex_text(model.File.FileName),'model_id':_corex_text(model.ModelId),'prototype_id':_corex_text(model.PrototypeId)})
    files=[];all_paths=set()
    for raw_path in GetAllFiles():
        path=_corex_path(raw_path);all_paths.add(path)
        files.append(_corex_ref(path,refs.get(path),path in registered,associations.get(path,[])))
    if set(refs)-all_paths: raise RuntimeError('native Workbench file inventory omitted a registered or associated file')
    parameter_refs=list(Parameters.GetAllParameters())
    parameters=[]
    for parameter in parameter_refs:
        quantity_name=getattr(parameter,'ValueQuantityName',None)
        parameters.append({'display_text':_corex_text(parameter.DisplayText),'expression':_corex_text(parameter.Expression),'usage':_corex_text(parameter.Usage),'quantity_name':'' if quantity_name is None else _corex_text(quantity_name)})
    design_points=[]
    retained=set(_corex_text(item.DisplayText) for item in Parameters.GetAllRetainedDesignPoints(IncludingBaseDesignPoint=True))
    exported=set(_corex_text(item.DisplayText) for item in Parameters.GetAllExportedDesignPoints(IncludingBaseDesignPoint=True))
    with_files=set(_corex_text(item.DisplayText) for item in Parameters.GetAllDesignPointsWithFiles())
    for point in Parameters.GetAllDesignPoints():
        label=_corex_text(point.DisplayText)
        values=[]
        for descriptor,parameter in zip(parameters,parameter_refs):
            values.append({'parameter':descriptor,'value':_corex_text(point.GetParameterValue(Parameter=parameter))})
        update_order=float(point.UpdateOrder)
        if math.isnan(update_order) or math.isinf(update_order): raise RuntimeError('native DesignPoint.UpdateOrder is not finite')
        design_points.append({'display_text':label,'exported':label in exported,'retained':label in retained,'with_files':label in with_files,'has_valid_retained_data':bool(point.HasValidRetainedData),'is_up_to_date':bool(point.IsUpToDate),'state_of_parameters':_corex_text(point.StateOfParameters),'update_order':update_order,'values':values})
    return {'project_file':_corex_text(GetProjectFile()),'project_directory':_corex_text(GetProjectDirectory()),'user_files_directory':_corex_text(GetUserFilesDirectory()),'files':sorted(files,key=lambda row:row['location_key']),'systems':sorted(systems,key=lambda row:row['user_id']),'models':sorted(models,key=lambda row:row['system_user_id']),'parameters':parameters,'design_points':sorted(design_points,key=lambda row:row['display_text'])}
'''


WORKBENCH_SAVE_BODY = _WORKBENCH_SNAPSHOT_PREFIX + r'''format_code=_corex_data['format'];work=_corex_text(_corex_data['work_path']);native_project=_corex_text(_corex_data['native_project']);stage=_corex_text(_corex_data['stage_path']);companion=_corex_text(_corex_data['stage_companion']);verify=_corex_text(_corex_data['verify_path']);system=_corex_text(_corex_data['system']);snapshot_path=_corex_text(_corex_data['snapshot_path'])
snapshots={};failure=None
try:
    snapshots['before']=_corex_snapshot()
    container=GetSystem(Name=system).GetContainer(ComponentName='Model')
    if container is None or not callable(getattr(container,'Exit',None)): raise RuntimeError('selected Model container has no native Exit lifecycle')
    container.Exit(SaveDatabase=True);Save();snapshots['working']=_corex_snapshot();Save(FilePath=native_project,Overwrite=False)
    if not os.path.isfile(native_project) or not os.path.isdir(os.path.splitext(native_project)[0]+'_files'): raise RuntimeError('native staged Workbench project is incomplete')
    snapshots['stage']=_corex_snapshot()
    if format_code=='wbpz':
        Archive(FilePath=stage,IncludeSkippedFiles=bool(_corex_data['include_results']),IncludeUserFiles=bool(_corex_data['include_user_files']),IncludeExternalImportedFiles=bool(_corex_data['include_external_imported_files']),FailIfMissingFiles=True)
        if not os.path.isfile(stage): raise RuntimeError('native Workbench archive is missing')
        Unarchive(ArchivePath=stage,ProjectPath=verify,Overwrite=False)
        if not os.path.isfile(verify) or not os.path.isdir(os.path.splitext(verify)[0]+'_files'): raise RuntimeError('native Workbench archive verification project is incomplete')
    else: Open(FilePath=stage)
    snapshots['verify']=_corex_snapshot()
except Exception as exc:
    failure=(type(exc).__name__,hashlib.sha256(_corex_text(traceback.format_exc()).encode('utf-8')).hexdigest())
finally:
    try:
        Open(FilePath=work);snapshots['restore']=_corex_snapshot()
    except Exception as exc:
        restore_failure=(type(exc).__name__,hashlib.sha256(_corex_text(traceback.format_exc()).encode('utf-8')).hexdigest());failure=restore_failure if failure is None else ('restore_after_'+failure[0],restore_failure[1])
snapshot_encoded=json.dumps({'schema_version':2,'snapshots':snapshots},ensure_ascii=False,separators=(',',':')).encode('utf-8')
snapshot_stream=open(snapshot_path,'wb')
try: snapshot_stream.write(snapshot_encoded);snapshot_stream.flush()
finally: snapshot_stream.close()
receipt={'schema_version':1,'marker':'corex-workbench-save-v1','ok':failure is None,'format':format_code,'snapshot_count':len(snapshots),'snapshot_bytes':len(snapshot_encoded),'snapshot_sha256':hashlib.sha256(snapshot_encoded).hexdigest(),'primary_exists':os.path.isfile(stage),'companion_exists':bool(companion and os.path.isdir(companion)),'error_type':'' if failure is None else failure[0],'error_digest':'' if failure is None else failure[1]}
wb_script_result=json.dumps(receipt,ensure_ascii=True,separators=(',',':'))'''


WORKBENCH_MODEL_EXPORT_BODY = _WORKBENCH_SNAPSHOT_PREFIX + r'''work=_corex_text(_corex_data['work_path']);bridge=_corex_text(_corex_data['bridge_path']);system=_corex_text(_corex_data['system']);snapshot_path=_corex_text(_corex_data['snapshot_path'])
snapshots={};failure=None
try:
    container=GetSystem(Name=system).GetContainer(ComponentName='Model')
    if container is None or not callable(getattr(container,'Exit',None)) or not callable(getattr(container,'Export',None)): raise RuntimeError('selected Model container lacks native Exit/Export lifecycle')
    container.Exit(SaveDatabase=True);Save();snapshots['before']=_corex_snapshot();snapshots['working']=snapshots['before']
    container.Export(FilePath=bridge)
    if not os.path.isfile(bridge) or os.path.getsize(bridge)<1: raise RuntimeError('native selected Model export is missing')
    snapshots['stage']=_corex_snapshot();snapshots['verify']=snapshots['stage'];snapshots['restore']=snapshots['stage']
except Exception as exc:
    failure=(type(exc).__name__,hashlib.sha256(_corex_text(traceback.format_exc()).encode('utf-8')).hexdigest())
snapshot_encoded=json.dumps({'schema_version':2,'snapshots':snapshots},ensure_ascii=False,separators=(',',':')).encode('utf-8')
snapshot_stream=open(snapshot_path,'wb')
try: snapshot_stream.write(snapshot_encoded);snapshot_stream.flush()
finally: snapshot_stream.close()
receipt={'schema_version':1,'marker':'corex-workbench-model-export-v1','ok':failure is None,'format':_corex_data['format'],'snapshot_count':len(snapshots),'snapshot_bytes':len(snapshot_encoded),'snapshot_sha256':hashlib.sha256(snapshot_encoded).hexdigest(),'bridge_exists':os.path.isfile(bridge),'bridge_bytes':os.path.getsize(bridge) if os.path.isfile(bridge) else 0,'bridge_sha256':_corex_sha(bridge) if os.path.isfile(bridge) else '','error_type':'' if failure is None else failure[0],'error_digest':'' if failure is None else failure[1]}
wb_script_result=json.dumps(receipt,ensure_ascii=True,separators=(',',':'))'''


def validate_workbench_save_receipt(value: object, *, format_code: str) -> dict[str, Any]:
    if type(value) is str:
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise RuntimeError("mechanical.save_failed: Workbench returned a malformed receipt") from exc
    required = {
        "schema_version", "marker", "ok", "format", "snapshot_count",
        "snapshot_bytes", "snapshot_sha256", "primary_exists", "companion_exists",
        "error_type", "error_digest",
    }
    if (
        not isinstance(value, dict)
        or set(value) != required
        or len(json.dumps(value, ensure_ascii=True, separators=(",", ":"))) > 1024
        or value["schema_version"] != 1
        or value["marker"] != "corex-workbench-save-v1"
        or value["format"] != format_code
        or type(value["snapshot_count"]) is not int
        or not 0 <= value["snapshot_count"] <= 5
        or type(value["snapshot_bytes"]) is not int
        or not 0 < value["snapshot_bytes"] <= 16 * 1024 * 1024
        or any(type(value[key]) is not str for key in ("snapshot_sha256", "error_type", "error_digest"))
        or type(value["ok"]) is not bool
        or type(value["primary_exists"]) is not bool
        or type(value["companion_exists"]) is not bool
    ):
        raise RuntimeError("mechanical.save_failed: Workbench returned an invalid bounded receipt")
    if re.fullmatch(r"[0-9a-f]{64}", value["snapshot_sha256"]) is None or (
        value["error_digest"]
        and re.fullmatch(r"[0-9a-f]{64}", value["error_digest"]) is None
    ) or (value["ok"] is False and (not value["error_type"] or not value["error_digest"])):
        raise RuntimeError("mechanical.save_failed: Workbench receipt digest is invalid")
    if value["ok"] is not True:
        raise RuntimeError(
            "mechanical.save_failed: native Workbench save failed: "
            f"{value['error_type']} receipt={value['error_digest']}"
        )
    if value["snapshot_count"] != 5 or value["primary_exists"] is not True or (
        format_code == "wbpj" and value["companion_exists"] is not True
    ) or value["error_type"] or value["error_digest"]:
        raise RuntimeError("mechanical.save_failed: Workbench save receipt did not prove staging, reopen, and restore")
    return dict(value)


def validate_workbench_model_export_receipt(
    value: object, *, format_code: str,
) -> dict[str, Any]:
    if type(value) is str:
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "mechanical.save_failed: Workbench returned a malformed model-export receipt"
            ) from exc
    required = {
        "schema_version", "marker", "ok", "format", "snapshot_count",
        "snapshot_bytes", "snapshot_sha256", "bridge_exists", "bridge_bytes",
        "bridge_sha256", "error_type", "error_digest",
    }
    if (
        not isinstance(value, dict)
        or set(value) != required
        or len(json.dumps(value, ensure_ascii=True, separators=(",", ":"))) > 1024
        or value["schema_version"] != 1
        or value["marker"] != "corex-workbench-model-export-v1"
        or value["format"] != format_code
        or format_code not in {"mechdb", "mechdat"}
        or type(value["ok"]) is not bool
        or type(value["snapshot_count"]) is not int
        or not 0 <= value["snapshot_count"] <= 5
        or type(value["snapshot_bytes"]) is not int
        or not 0 < value["snapshot_bytes"] <= 16 * 1024 * 1024
        or type(value["bridge_exists"]) is not bool
        or type(value["bridge_bytes"]) is not int
        or value["bridge_bytes"] < 0
        or any(
            type(value[key]) is not str
            for key in ("snapshot_sha256", "bridge_sha256", "error_type", "error_digest")
        )
    ):
        raise RuntimeError(
            "mechanical.save_failed: Workbench returned an invalid model-export receipt"
        )
    digests = (value["snapshot_sha256"], value["bridge_sha256"], value["error_digest"])
    if (
        re.fullmatch(r"[0-9a-f]{64}", digests[0]) is None
        or digests[1] and re.fullmatch(r"[0-9a-f]{64}", digests[1]) is None
        or digests[2] and re.fullmatch(r"[0-9a-f]{64}", digests[2]) is None
        or value["ok"] is False and (not value["error_type"] or not value["error_digest"])
    ):
        raise RuntimeError("mechanical.save_failed: Workbench model-export digest is invalid")
    if value["ok"] is not True:
        raise RuntimeError(
            "mechanical.save_failed: native Workbench Model.Export failed: "
            f"{value['error_type']} receipt={value['error_digest']}"
        )
    if (
        value["snapshot_count"] != 5
        or value["bridge_exists"] is not True
        or value["bridge_bytes"] < 1
        or not value["bridge_sha256"]
        or value["error_type"]
        or value["error_digest"]
    ):
        raise RuntimeError(
            "mechanical.save_failed: Workbench model export did not prove native staging"
        )
    return dict(value)


_STATE_MAX_BYTES = 64 * 1024 * 1024
_HDF5_SIGNATURE = b"\x89HDF\r\n\x1a\n"


def _compare_workbench_state(
    paths: tuple[Path, Path], rows: tuple[dict[str, Any], dict[str, Any]],
) -> dict[str, Any]:
    """Read the qualified state pair inside the existing timed native owner.

    HDF5 logical equality does not establish which container bytes changed.
    No offset masking, payload decoding, database writes, or alternate schema.
    """
    def attest(path: Path, row: dict[str, Any]) -> tuple[int, int, int, int]:
        if os.path.normcase(row["location"]) != os.path.normcase(str(path)):
            raise ValueError("state file path is not the exact attested path")
        for original in (path, *path.parents):
            if is_reparse_point(original):
                raise ValueError("state file path contains a reparse point")
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or not 0 < before.st_size == row["size"] <= _STATE_MAX_BYTES
            or path.resolve(strict=True) != path
        ):
            raise ValueError("state file is missing, unsafe, or exceeds its bound")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            if stream.read(8) != _HDF5_SIGNATURE:
                raise ValueError("state file must have the HDF5 signature at byte zero")
            stream.seek(0)
            remaining = before.st_size
            while remaining:
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("state file became shorter during attestation")
                digest.update(chunk)
                remaining -= len(chunk)
            if stream.read(1) or digest.hexdigest() != row["sha256"]:
                raise ValueError("state file disagrees with its native SHA256")
            opened = os.fstat(stream.fileno())
        after = path.lstat()
        identities = [
            (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
            for item in (before, opened, after)
        ]
        if identities[1:] != identities[:1] * 2:
            raise ValueError("state file changed during attestation")
        return identities[0]

    try:
        before = [attest(path, row) for path, row in zip(paths, rows, strict=True)]
        import h5py

        with h5py.File(paths[0], "r") as left, h5py.File(paths[1], "r") as right:
            states = []
            for handle in (left, right):
                root = handle["/"]
                if (
                    handle.userblock_size != 0
                    or len(root) != 1
                    or list(root) != ["Session"]
                    or len(root.attrs) != 0
                    or type(root.get("Session", getlink=True)) is not h5py.HardLink
                ):
                    raise ValueError("unqualified state root, links, attributes, or user block")
                dataset = root["Session"]
                if not isinstance(dataset, h5py.Dataset):
                    raise ValueError("state Session is not a dataset")
                creation = dataset.id.get_create_plist()
                object_info = h5py.h5o.get_info(dataset.id)
                if (
                    dataset.ndim != 1
                    or not 0 < dataset.size <= _STATE_MAX_BYTES
                    or not dataset.id.get_type().equal(h5py.h5t.STD_U8LE)
                    or dataset.id.get_type().committed()
                    or dataset.chunks != (262144,)
                    or creation.get_nfilters() != 0
                    or creation.get_external_count() != 0
                    or dataset.is_virtual
                    or not creation.get_obj_track_times()
                    # Version-one object headers can report the default tracking
                    # flag after reopen even when creation recorded no times.
                    or object_info.ctime <= 0
                    or object_info.rc != 1
                    or len(dataset.attrs) != 1
                    or list(dataset.attrs) != ["UsedSize"]
                ):
                    raise ValueError("unqualified state Session schema")
                attribute = dataset.attrs.get_id("UsedSize")
                if (
                    not attribute.get_type().equal(h5py.h5t.STD_U64LE)
                    or attribute.get_type().committed()
                    or attribute.shape != (1,)
                    or int(dataset.attrs["UsedSize"][0]) != dataset.size
                ):
                    raise ValueError("unqualified state UsedSize attribute")
                comments = (root.id.get_comment(b"."), root.id.get_comment(b"Session"))
                if any(len(comment) > 65536 for comment in comments):
                    raise ValueError("state object comment exceeds its bound")
                link = root.id.links.get_info(b"Session")
                attr_info = h5py.h5a.get_info(attribute)
                states.append((root, dataset, attribute, comments, (
                    link.type, link.cset, link.corder_valid,
                    link.corder if link.corder_valid else None,
                    attr_info.cset, attr_info.corder_valid,
                    attr_info.corder if attr_info.corder_valid else None,
                    attr_info.data_size,
                )))
            a, b = states
            if a[3:] != b[3:] or not left.id.get_create_plist().equal(right.id.get_create_plist()):
                raise ValueError("state file, comment, or link metadata changed")
            for first, second in zip(a[:2], b[:2], strict=True):
                if not first.id.get_create_plist().equal(second.id.get_create_plist()):
                    raise ValueError("state object creation properties changed")
            for first, second in ((a[1].id, b[1].id), (a[2], b[2])):
                if not first.get_type().equal(second.get_type()):
                    raise ValueError("state datatype changed")
                space_a, space_b = first.get_space(), second.get_space()
                if (
                    space_a.get_simple_extent_type() != space_b.get_simple_extent_type()
                    or space_a.get_simple_extent_dims() != space_b.get_simple_extent_dims()
                    or space_a.get_simple_extent_dims(True) != space_b.get_simple_extent_dims(True)
                ):
                    raise ValueError("state dataspace changed")
            if a[1].attrs["UsedSize"].tobytes() != b[1].attrs["UsedSize"].tobytes():
                raise ValueError("state attribute data changed")
            digest = hashlib.sha256()
            for start in range(0, a[1].size, 1024 * 1024):
                chunk = a[1][start : start + 1024 * 1024].tobytes()
                if chunk != b[1][start : start + 1024 * 1024].tobytes():
                    raise ValueError("state Session data changed")
                digest.update(chunk)
            logical_bytes = int(a[1].size)
        if before != [attest(path, row) for path, row in zip(paths, rows, strict=True)]:
            raise ValueError("state file changed during HDF5 comparison")
    except Exception as exc:
        raise RuntimeError(f"mechanical.save_failed: Workbench state equivalence failed: {exc}") from exc
    return {
        "schema": "workbench-session-v1", "logical_bytes": logical_bytes,
        "logical_sha256": digest.hexdigest(),
        "working_sha256": rows[0]["sha256"], "stage_sha256": rows[1]["sha256"],
    }


def validate_workbench_semantic_snapshots(
    path: Path,
    *,
    receipt: dict[str, Any],
    format_code: str,
    work_path: Path,
    native_project: Path,
    stage_path: Path,
    verify_path: Path,
    include_results: bool = True,
    include_user_files: bool = True,
    include_external_imported_files: bool = True,
) -> dict[str, Any]:
    if is_reparse_point(path) or not path.is_file() or path.stat().st_size != receipt["snapshot_bytes"]:
        raise RuntimeError("mechanical.save_failed: Workbench semantic snapshot file is invalid")
    encoded = path.read_bytes()
    if hashlib.sha256(encoded).hexdigest() != receipt["snapshot_sha256"]:
        raise RuntimeError("mechanical.save_failed: Workbench semantic snapshot digest changed")
    try:
        payload = json.loads(encoded.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("mechanical.save_failed: Workbench semantic snapshot is malformed") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "snapshots"}
        or payload["schema_version"] != 2
        or not isinstance(payload["snapshots"], dict)
        or set(payload["snapshots"])
        != {"before", "working", "stage", "verify", "restore"}
    ):
        raise RuntimeError("mechanical.save_failed: Workbench semantic snapshot envelope is invalid")
    snapshots = payload["snapshots"]
    snapshot_fields = {
        "project_file", "project_directory", "user_files_directory", "files",
        "systems", "models", "parameters", "design_points",
    }
    file_fields = {
        "file_name", "display_text", "location", "registered", "exists", "size",
        "sha256", "associations", "location_key",
    }
    expected_projects = {
        "before": work_path,
        "working": work_path,
        "stage": native_project,
        "verify": stage_path if format_code == "wbpj" else verify_path,
        "restore": work_path,
    }
    for snapshot in snapshots.values():
        if not isinstance(snapshot, dict) or set(snapshot) != snapshot_fields:
            raise RuntimeError("mechanical.save_failed: Workbench semantic snapshot fields are invalid")
        if any(type(snapshot[key]) is not str or not snapshot[key] for key in ("project_file", "project_directory", "user_files_directory")):
            raise RuntimeError("mechanical.save_failed: Workbench semantic project paths are invalid")
        if any(type(snapshot[key]) is not list or len(snapshot[key]) > 100_000 for key in ("files", "systems", "models", "parameters", "design_points")):
            raise RuntimeError("mechanical.save_failed: Workbench semantic snapshot exceeds its bounds")
        for row in snapshot["files"]:
            if (
                not isinstance(row, dict)
                or set(row) != file_fields
                or any(type(row[key]) is not str for key in ("file_name", "display_text", "location", "location_key", "sha256"))
                or not row["file_name"]
                or row["location_key"] != os.path.normcase(os.path.abspath(row["location"]))
                or type(row["registered"]) is not bool
                or type(row["exists"]) is not bool
                or type(row["size"]) is not int
                or row["size"] < 0
                or type(row["associations"]) is not list
                or any(type(value) is not str or not value for value in row["associations"])
                or row["exists"] and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None
                or not row["exists"] and (row["size"] or row["sha256"])
            ):
                raise RuntimeError("mechanical.save_failed: Workbench semantic file row is invalid")
        if len({row["location_key"] for row in snapshot["files"]}) != len(
            snapshot["files"]
        ):
            raise RuntimeError(
                "mechanical.save_failed: Workbench semantic file locations are ambiguous"
            )
        for row in snapshot["systems"]:
            if (
                not isinstance(row, dict)
                or set(row) != {"user_id", "name", "components"}
                or any(type(row[key]) is not str or not row[key] for key in ("user_id", "name"))
                or type(row["components"]) is not list
                or any(
                    not isinstance(component, dict)
                    or set(component) != {"user_id", "directory_name"}
                    or any(type(component[key]) is not str or not component[key] for key in component)
                    for component in row["components"]
                )
            ):
                raise RuntimeError("mechanical.save_failed: Workbench semantic system row is invalid")
        for row in snapshot["models"]:
            if (
                not isinstance(row, dict)
                or set(row) != {"system_user_id", "file_name", "model_id", "prototype_id"}
                or any(type(value) is not str or not value for value in row.values())
            ):
                raise RuntimeError("mechanical.save_failed: Workbench semantic model row is invalid")
        for row in snapshot["parameters"]:
            if (
                not isinstance(row, dict)
                or set(row) != {"display_text", "expression", "usage", "quantity_name"}
                or any(type(value) is not str for value in row.values())
                or not row["display_text"]
            ):
                raise RuntimeError("mechanical.save_failed: Workbench semantic parameter row is invalid")
        if len({tuple(row.items()) for row in snapshot["parameters"]}) != len(snapshot["parameters"]):
            raise RuntimeError("mechanical.save_failed: Workbench semantic parameter identity is ambiguous")
        for row in snapshot["design_points"]:
            if (
                not isinstance(row, dict)
                or set(row) != {
                    "display_text", "exported", "retained", "with_files",
                    "has_valid_retained_data", "is_up_to_date", "state_of_parameters",
                    "update_order", "values",
                }
                or type(row["display_text"]) is not str
                or not row["display_text"]
                or type(row["state_of_parameters"]) is not str
                or any(type(row[key]) is not bool for key in ("exported", "retained", "with_files", "has_valid_retained_data", "is_up_to_date"))
                or type(row["update_order"]) is not float
                or not math.isfinite(row["update_order"])
                or type(row["values"]) is not list
                or len(row["values"]) != len(snapshot["parameters"])
                or any(
                    not isinstance(value, dict)
                    or set(value) != {"parameter", "value"}
                    or value["parameter"] not in snapshot["parameters"]
                    or type(value["value"]) is not str
                    for value in row["values"]
                )
                or [value["parameter"] for value in row["values"]]
                != snapshot["parameters"]
            ):
                raise RuntimeError("mechanical.save_failed: Workbench semantic design-point row is invalid")
        if not snapshot["systems"] or not snapshot["models"] or len({row["user_id"] for row in snapshot["systems"]}) != len(snapshot["systems"]) or len({row["system_user_id"] for row in snapshot["models"]}) != len(snapshot["models"]):
            raise RuntimeError("mechanical.save_failed: Workbench semantic system/model identity is invalid")
    for phase, expected_project in expected_projects.items():
        expected_project = expected_project.resolve(strict=False)
        # Native 261 qualification: this is the containing directory;
        # GetUserFilesDirectory identifies the separate companion tree.
        expected_directory = expected_project.parent
        expected_user_directory = expected_project.with_name(
            expected_project.stem + "_files"
        ) / "user_files"
        snapshot = snapshots[phase]
        if any(
            os.path.normcase(os.path.abspath(snapshot[key]))
            != os.path.normcase(os.path.abspath(expected))
            for key, expected in (
                ("project_file", expected_project),
                ("project_directory", expected_directory),
                ("user_files_directory", expected_user_directory),
            )
        ):
            raise RuntimeError(
                f"mechanical.restore_failed: Workbench {phase} phase path attestation failed"
            )
    baseline = snapshots["stage"]
    for phase in ("before", "working", "verify", "restore"):
        current = snapshots[phase]
        for key in ("systems", "models", "parameters", "design_points"):
            if current[key] != baseline[key]:
                raise RuntimeError(
                    f"mechanical.save_failed: Workbench {key} changed during {phase}"
                )

    def within(location: str, root: str) -> bool:
        try:
            location_path = os.path.normcase(os.path.abspath(location))
            root_path = os.path.normcase(os.path.abspath(root))
            return os.path.commonpath((location_path, root_path)) == root_path
        except ValueError:
            return False

    def file_identity(
        snapshot: dict[str, Any],
        row: dict[str, Any],
        *,
        primary_bytes: bool,
    ) -> tuple[Any, ...]:
        location = os.path.normcase(os.path.abspath(row["location"]))
        project = Path(snapshot["project_file"])
        project_location = os.path.normcase(os.path.abspath(project))
        if location == project_location:
            if not primary_bytes:
                return ("project_file", row["exists"], row["registered"])
            return (
                "project_file", row["file_name"], row["display_text"],
                tuple(row["associations"]), row["exists"], row["size"],
                row["sha256"], row["registered"],
            )
        payload = (
            row["file_name"], row["display_text"], tuple(row["associations"]),
            row["exists"], row["size"], row["sha256"], row["registered"],
        )
        companion = project.with_name(project.stem + "_files")
        if within(location, str(companion)):
            logical_location = (
                "companion",
                os.path.normcase(os.path.relpath(location, companion)),
            )
        else:
            logical_location = ("external", location)
        return (
            *logical_location,
            *payload,
        )

    def external_payload_identity(row: dict[str, Any]) -> tuple[Any, ...]:
        return (
            row["file_name"], row["display_text"], tuple(row["associations"]),
            row["exists"], row["size"], row["sha256"], row["registered"],
        )

    baseline_files = list(baseline["files"])
    required: list[dict[str, Any]] = []
    baseline_project = Path(baseline["project_file"])
    baseline_companion = baseline_project.with_name(
        baseline_project.stem + "_files"
    )
    archive_external_rows: list[dict[str, Any]] = []
    for row in baseline_files:
        user_file = within(row["location"], baseline["user_files_directory"])
        external_file = (
            row["registered"]
            and os.path.normcase(os.path.abspath(row["location"]))
            != os.path.normcase(os.path.abspath(baseline_project))
            and not within(row["location"], str(baseline_companion))
            and not user_file
        )
        if external_file:
            archive_external_rows.append(row)
        if user_file and format_code == "wbpz" and not include_user_files:
            continue
        if external_file and format_code == "wbpz" and not include_external_imported_files:
            continue
        if format_code != "wbpz" or include_results or row["registered"] or row["associations"]:
            required.append(row)

    def validate_archive_external_rebases() -> set[str]:
        if format_code != "wbpz":
            return set()
        stage_import_root = baseline_project.with_name(
            baseline_project.stem + "_files"
        ) / "import_files"
        source_locations = [
            os.path.normcase(os.path.abspath(row["location"]))
            for row in archive_external_rows
        ]
        payloads = [external_payload_identity(row) for row in archive_external_rows]
        if len(set(source_locations)) != len(source_locations) or any(
            count != 1 for count in Counter(payloads).values()
        ):
            raise RuntimeError(
                "mechanical.save_failed: registered external archive mapping is ambiguous"
            )
        verify_project = Path(snapshots["verify"]["project_file"])
        import_root = verify_project.with_name(
            verify_project.stem + "_files"
        ) / "import_files"
        stage_imports = Counter(
            (
                os.path.normcase(os.path.relpath(row["location"], stage_import_root)),
                external_payload_identity(row),
            )
            for row in baseline_files
            if within(row["location"], str(stage_import_root))
        )
        new_imports: list[dict[str, Any]] = []
        for row in snapshots["verify"]["files"]:
            if not within(row["location"], str(import_root)):
                continue
            identity = (
                os.path.normcase(os.path.relpath(row["location"], import_root)),
                external_payload_identity(row),
            )
            if stage_imports[identity]:
                stage_imports[identity] -= 1
            else:
                new_imports.append(row)
        if not include_external_imported_files:
            if new_imports:
                raise RuntimeError(
                    "mechanical.save_failed: excluded registered external file was archived"
                )
            return set()
        candidates = [
            row
            for row in new_imports
            if row["registered"]
        ]
        if len(new_imports) != len(archive_external_rows):
            raise RuntimeError(
                "mechanical.save_failed: registered external archive rebase is missing or ambiguous"
            )
        used_targets: set[str] = set()
        for payload in payloads:
            matches = [
                row for row in candidates if external_payload_identity(row) == payload
            ]
            if len(matches) != 1:
                raise RuntimeError(
                    "mechanical.save_failed: registered external archive rebase is missing or ambiguous"
                )
            target = os.path.normcase(os.path.abspath(matches[0]["location"]))
            if target in used_targets:
                raise RuntimeError(
                    "mechanical.save_failed: registered external archive mapping is ambiguous"
                )
            used_targets.add(target)
        if len(used_targets) != len(new_imports):
            raise RuntimeError(
                "mechanical.save_failed: registered external archive mapping is ambiguous"
            )
        return set(source_locations)

    rebased_external_locations = validate_archive_external_rebases()

    state_paths = tuple(
        Path(snapshots[phase]["project_file"]).with_name(
            Path(snapshots[phase]["project_file"]).stem + "_files"
        ) / "dp0" / "act.dat"
        for phase in ("working", "stage")
    )
    state_rows = [
        [row for row in snapshots[phase]["files"]
         if row["location_key"] == os.path.normcase(os.path.abspath(expected))]
        for phase, expected in zip(("working", "stage"), state_paths, strict=True)
    ]
    if [len(rows) for rows in state_rows] not in ([0, 0], [1, 1]):
        raise RuntimeError("mechanical.save_failed: Workbench state file membership changed")
    pending_state_pair = None

    def require_inventory(
        source: dict[str, Any],
        target: dict[str, Any],
        rows: list[dict[str, Any]],
        phase: str,
    ) -> None:
        nonlocal pending_state_pair
        same_primary = os.path.normcase(os.path.abspath(source["project_file"])) == os.path.normcase(
            os.path.abspath(target["project_file"])
        )
        required_inventory = Counter(
            file_identity(source, row, primary_bytes=same_primary)
            for row in rows
        )
        current = Counter(
            file_identity(target, row, primary_bytes=same_primary)
            for row in target["files"]
        )
        missing = required_inventory - current
        if missing and phase == "stage" and state_rows[0] and not same_primary:
            first, second = state_rows[0][0], state_rows[1][0]
            first_id = file_identity(source, first, primary_bytes=False)
            second_id = file_identity(target, second, primary_bytes=False)
            unchanged_fields = file_fields - {"location", "location_key", "sha256"}
            if (
                first["file_name"] == first["display_text"] == "act.dat"
                and first["registered"] is True and first["exists"] is True
                and all(first[key] == second[key] for key in unchanged_fields)
                and first["sha256"] != second["sha256"]
                and missing == Counter({first_id: 1})
                and current - required_inventory == Counter({second_id: 1})
            ):
                pending_state_pair = (first, second)
                return
        if missing:
            raise RuntimeError(
                f"mechanical.save_failed: required Workbench project inventory changed during {phase}"
            )

    require_inventory(
        snapshots["working"], baseline, list(snapshots["working"]["files"]), "stage"
    )
    verify_required = [
        row
        for row in required
        if os.path.normcase(os.path.abspath(row["location"]))
        not in rebased_external_locations
    ]
    require_inventory(
        baseline,
        snapshots["verify"],
        verify_required,
        "verify",
    )
    require_inventory(
        snapshots["working"],
        snapshots["restore"],
        list(snapshots["working"]["files"]),
        "restore",
    )
    # All ordinary checks pass before this one qualified content comparison.
    state_proof = (
        _compare_workbench_state(state_paths, pending_state_pair)
        if pending_state_pair is not None else None
    )
    model_groups: dict[tuple[str, str, str], list[str]] = {}
    for row in baseline["models"]:
        model_groups.setdefault(
            (row["file_name"], row["model_id"], row["prototype_id"]), []
        ).append(row["system_user_id"])
    return {
        "native_file_count": len(baseline_files),
        "required_file_count": len(required),
        "registered_file_count": sum(row["registered"] for row in baseline_files),
        "associated_file_count": sum(bool(row["associations"]) for row in baseline_files),
        "system_count": len(baseline["systems"]),
        "model_count": len(baseline["models"]),
        "shared_model_group_count": sum(len(systems) > 1 for systems in model_groups.values()),
        "design_point_count": len(baseline["design_points"]),
        "external_rebase_count": len(rebased_external_locations),
        "results_authority": "native IncludeSkippedFiles",
        "state_file_logical_comparison": state_proof,
    }


def validate_workbench_model_export_snapshots(
    path: Path,
    *,
    receipt: dict[str, Any],
    work_path: Path,
) -> dict[str, Any]:
    proof = validate_workbench_semantic_snapshots(
        path,
        receipt=receipt,
        format_code="wbpj",
        work_path=work_path,
        native_project=work_path,
        stage_path=work_path,
        verify_path=work_path,
    )
    proof.pop("results_authority")
    proof.pop("state_file_logical_comparison")
    return {**proof, "source_workbench_preserved": True}


class OwnedWorkbench:
    def __init__(self, client: Any, process: subprocess.Popen[Any], job: _WindowsKillJob) -> None:
        self._client, self._process, self._job = client, process, job
        self.identity = {
            "pid": process.pid,
            "creation_time_ns": _creation_time_for_pid(process.pid),
        }
        self._closed = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    def exit(self) -> None:
        if self._closed:
            return
        try:
            self._client.exit()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        finally:
            self._job.close()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._closed = True


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def launch_workbench_owner(*, release_code: int, show_gui: bool, client_workdir: str, server_workdir: str, timeout_sec: float = 120.0, **_options: Any) -> OwnedWorkbench:
    from ansys.tools.common.path import get_available_ansys_installations
    from ansys.workbench.core import connect_workbench
    import grpc

    root = get_available_ansys_installations().get(int(release_code))
    executable = Path(root or "") / "Framework" / "bin" / "Win64" / "RunWB2.exe"
    if not executable.is_file():
        raise RuntimeError(f"Workbench release {release_code} is not installed")
    work = Path(server_workdir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    port, token = _free_port(), uuid.uuid4().hex
    encoded = base64.b64encode(
        json.dumps(
            {"token": token, "workdir": work.as_posix(), "port": port},
            separators=(",", ":"),
        ).encode()
    ).decode("ascii")
    start = (
        "import base64,json\np=json.loads(base64.b64decode(" + repr(encoded)
        + ").decode('utf-8'))\n"
        "StartServer(EnvironmentPrefix=p['token'],WorkingDirectory=p['workdir'],"
        "PortToUse=p['port'],Security='wnua')"
    )
    args = [str(executable), "-I" if show_gui else "--start-and-wait"]
    if not show_gui:
        args.append("-nowindow")
    args.extend(("-E", start))
    flags = getattr(subprocess, "CREATE_SUSPENDED", 4)
    if not show_gui:
        flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
    job = _WindowsKillJob()
    process = None
    try:
        process = subprocess.Popen(
            args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=flags,
        )
        job.assign(process)
        status = ctypes.WinDLL("ntdll").NtResumeProcess(wintypes.HANDLE(int(process._handle)))
        if status:
            raise OSError(int(status), "NtResumeProcess failed")
        deadline = time.monotonic() + float(timeout_sec)
        while True:
            client = None
            try:
                client = connect_workbench(
                    port, client_workdir=client_workdir, host="localhost", security="wnua"
                )
                grpc.channel_ready_future(client.channel).result(
                    timeout=max(0.1, min(1.0, deadline - time.monotonic()))
                )
                if client.run_script_string(
                    "import json\nwb_script_result=json.dumps(True)"
                ) is True:
                    break
                client.exit()
                raise RuntimeError("Workbench health handshake was not accepted")
            except Exception:
                if client is not None:
                    client.exit()
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("Workbench server did not accept the owned connection")
                time.sleep(0.25)
        return OwnedWorkbench(client, process, job)
    except BaseException:
        job.close()
        if process is not None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        raise


__all__ = [
    "OwnedWorkbench",
    "WORKBENCH_MODEL_COMPONENT_PREDICATE",
    "WORKBENCH_MODEL_EXPORT_BODY",
    "WORKBENCH_SAVE_BODY",
    "launch_workbench_owner",
    "validate_workbench_model_export_receipt",
    "validate_workbench_model_export_snapshots",
    "validate_workbench_semantic_snapshots",
    "validate_workbench_save_receipt",
]
