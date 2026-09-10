# Purpose: Validate, stage, verify, and publish Mechanical and Workbench saves safely.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_standalone_save.py, tests/mechanical_catalogue/test_workbench_save.py, tests/mechanical_catalogue/test_workbench_model_export.py

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ea_node_editor.common.path_safety import is_reparse_point


SAVE_FORMATS = ("auto", "mechdb", "mechdat", "mechpz", "wbpj", "wbpz")
_MODEL_FORMATS = frozenset({"mechdb", "mechdat"})
_PROJECT_FORMATS = frozenset({"wbpj"})
_BUNDLE_FORMATS = _MODEL_FORMATS | _PROJECT_FORMATS
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


@dataclass(frozen=True, slots=True)
class SaveStaging:
    root: Path
    primary: Path
    companion: Path | None
    verify_project: Path
    native_project: Path | None = None


@dataclass(frozen=True, slots=True)
class DestinationPreflight:
    destination: Path
    companion: Path | None
    source_destination: bool
    identities: tuple[tuple[Path, tuple[Any, ...] | None], ...]


STANDALONE_SAVE_BODY = r'''import json,os,traceback
try:
    unicode
except NameError:
    unicode=str
def _corex_text(value):
    return value if isinstance(value,unicode) else unicode(value)
def _corex_normal(value):
    return os.path.normcase(os.path.abspath(_corex_text(value)))
def _corex_analysis_states():
    rows=[]
    for analysis in Model.Analyses:
        try:
            raw_working_dir=getattr(analysis,'WorkingDir')
            if raw_working_dir is None:
                working_dir=''
                working_dir_status='none'
            else:
                working_dir=_corex_text(raw_working_dir)
                working_dir_status='available' if working_dir else 'empty'
        except AttributeError:
            working_dir=''
            working_dir_status='unavailable'
        except Exception:
            working_dir=''
            working_dir_status='unreadable'
        result_file=_corex_text(getattr(analysis,'ResultFileName','') or '')
        reader=None
        try:
            reader=analysis.GetResultsData()
            reader_available=reader is not None
        except Exception:
            reader_available=False
        finally:
            if reader is not None and callable(getattr(reader,'Dispose',None)):
                try: reader.Dispose()
                except: pass
        rows.append({'id':int(analysis.ObjectId),'working_dir':working_dir,'working_dir_status':working_dir_status,'result_file':result_file,'result_exists':bool(result_file and os.path.isfile(result_file)),'reader_available':bool(reader_available),'solution_status':_corex_text(getattr(getattr(analysis,'Solution',None),'Status','') or '')})
    return rows
project=DataModel.Project
work=_corex_text(_corex_data['work_path'])
stage=_corex_text(_corex_data['stage_path'])
verify=_corex_text(_corex_data['verify_path'])
format_code=_corex_data['format']
before_ids=sorted(int(item.ObjectId) for item in Tree.AllObjects)
if _corex_normal(project.FilePath)!=_corex_normal(work):
    raise RuntimeError('mechanical.restore_failed: admitted Model is not attached to its working database')
required=('Save','Open','Archive','Unarchive') if format_code=='mechpz' else ('Save','Open','SaveAs')
for name in required:
    if not callable(getattr(project,name,None)):
        raise RuntimeError('mechanical.capability_unproved: standalone Project.'+name+' is unavailable')
project.Save()
analysis_states=_corex_analysis_states()
result_directories=[]
user_directory=''
user_directory_status='not_consumed'
if format_code=='mechpz':
    try:
        raw_user_directory=getattr(project,'UserFiles')
        if raw_user_directory is None:
            user_directory_status='none'
        else:
            user_directory=_corex_text(raw_user_directory)
            user_directory_status='available' if user_directory else 'empty'
    except AttributeError:
        user_directory_status='unavailable'
    except Exception:
        user_directory_status='unreadable'
    if user_directory_status=='unavailable':
        raise RuntimeError('mechanical.capability_unproved: standalone Project.UserFiles accessor is unavailable')
    if user_directory_status!='available':
        raise RuntimeError('mechanical.save_failed: standalone Project.UserFiles returned no usable path ('+user_directory_status+')')
    for state in analysis_states:
        if state['working_dir_status']=='unavailable':
            raise RuntimeError('mechanical.capability_unproved: native analysis WorkingDir accessor is unavailable: '+str(state['id']))
        if state['working_dir_status']!='available':
            raise RuntimeError('mechanical.save_failed: native analysis WorkingDir returned no usable path: '+str(state['id'])+' ('+state['working_dir_status']+')')
        result_directories.append(state['working_dir'])
        result_bearing=state['reader_available'] or state['result_exists'] or state['solution_status']=='Done'
        if _corex_data['include_results'] and result_bearing and (not state['result_exists'] or not state['reader_available']):
            raise RuntimeError('mechanical.save_failed: requested solved result resources are missing or unreadable: '+str(state['id']))
failure=None
try:
    if format_code=='mechpz':
        from Ansys.ACT.Automation.Mechanical import ArchiveSettings
        settings=ArchiveSettings(bool(_corex_data['include_results']),bool(_corex_data['include_user_files']))
        project.Archive(stage,False,settings)
        if not os.path.isfile(stage):
            raise RuntimeError('mechanical.save_failed: native archive file is missing')
        project.Unarchive(stage,verify,False)
        if _corex_normal(project.FilePath)!=_corex_normal(verify):
            raise RuntimeError('mechanical.save_failed: native archive did not reopen at the verification path')
    else:
        project.SaveAs(stage,False)
        if not os.path.isfile(stage) or not os.path.isdir(_corex_text(_corex_data['stage_companion'])):
            raise RuntimeError('mechanical.save_failed: native model output or companion directory is missing')
        project.Open(stage)
        if _corex_normal(project.FilePath)!=_corex_normal(stage):
            raise RuntimeError('mechanical.save_failed: native model output did not reopen')
    reopened_ids=sorted(int(item.ObjectId) for item in Tree.AllObjects)
    if reopened_ids!=before_ids:
        raise RuntimeError('mechanical.save_failed: reopened model tree identity changed')
    reopened_analysis_states=_corex_analysis_states()
    if format_code=='mechpz' and _corex_data['include_results']:
        reopened_by_id=dict((state['id'],state) for state in reopened_analysis_states)
        for state in analysis_states:
            if state['reader_available'] or state['result_exists'] or state['solution_status']=='Done':
                reopened=reopened_by_id.get(state['id'])
                if reopened is None or not reopened['result_exists'] or not reopened['reader_available']:
                    raise RuntimeError('mechanical.save_failed: requested result resources did not survive native reopen: '+str(state['id']))
except Exception as exc:
    failure=traceback.format_exc()
finally:
    try:
        if _corex_normal(project.FilePath)!=_corex_normal(work):
            project.Open(work)
        if _corex_normal(project.FilePath)!=_corex_normal(work):
            raise RuntimeError('working database path mismatch')
        restored_ids=sorted(int(item.ObjectId) for item in Tree.AllObjects)
        if restored_ids!=before_ids:
            raise RuntimeError('working model tree identity changed')
    except Exception:
        restore_error=traceback.format_exc()
        raise RuntimeError('mechanical.restore_failed: '+restore_error+(('\nNative save failure:\n'+failure) if failure else ''))
if failure:
    raise RuntimeError(failure)
_corex_payload=json.dumps({'schema_version':1,'format':format_code,'reopen_verified':True,'work_restored':True,'object_count':len(before_ids),'stage_bytes':os.path.getsize(stage),'analysis_states':analysis_states,'reopened_analysis_states':reopened_analysis_states,'result_directories':result_directories,'user_directory':user_directory,'user_directory_status':user_directory_status},ensure_ascii=False,separators=(',',':')).encode('utf-8')
with open(_corex_data['native_output_path'],'wb') as _corex_stream:_corex_stream.write(_corex_payload)
import hashlib
_corex_receipt=json.dumps({'byte_length':len(_corex_payload),'sha256':hashlib.sha256(_corex_payload).hexdigest()},separators=(',',':'))
_corex_receipt'''


MODEL_EXPORT_SNAPSHOT_BODY = r'''import hashlib,json,math
from Ansys.Mechanical.DataModel.Enums import DataModelObjectCategory
try:
    unicode
except NameError:
    unicode=str
def _corex_text(value):
    return value if isinstance(value,unicode) else unicode(value)
def _corex_row(item,index_by_id):
    parent=getattr(item,'Parent',None)
    parent_id=None if parent is None else int(parent.ObjectId)
    return {'name':_corex_text(item.Name),'api_type':_corex_text(item.GetType().FullName),'parent_index':index_by_id.get(parent_id)}
def _corex_quantity(item,name):
    value=getattr(item,name)
    number=float(value.Value)
    if math.isnan(number) or math.isinf(number): raise RuntimeError('mechanical.capability_unproved: non-finite Body.'+name)
    unit=_corex_text(value.Unit)
    if not unit: raise RuntimeError('mechanical.capability_unproved: Body.'+name+' unit is unavailable')
    return {'value':number,'unit':unit}
objects=list(Tree.AllObjects)
index_by_id=dict((int(item.ObjectId),index) for index,item in enumerate(objects))
def _corex_items(category):
    return list(DataModel.GetObjectsByType(category))
tree=[_corex_row(item,index_by_id) for item in objects]
analyses=[_corex_row(item,index_by_id) for item in Model.Analyses]
bodies=[];geometry_ids={}
for body_index,item in enumerate(_corex_items(DataModelObjectCategory.Body)):
    geo=item.GetGeoBody();topology={}
    geometry_ids[int(geo.Id)]={'body_index':body_index,'kind':'body','index':0}
    for plural,kind in (('Faces','face'),('Edges','edge'),('Vertices','vertex')):
        entities=list(getattr(geo,plural));topology[kind+'_count']=len(entities)
        for entity_index,entity in enumerate(entities):
            identity={'body_index':body_index,'kind':kind,'index':entity_index}
            entity_id=int(entity.Id)
            if entity_id in geometry_ids: raise RuntimeError('mechanical.capability_unproved: duplicate geometry entity identity')
            geometry_ids[entity_id]=identity
    geometry={'geometry_type':_corex_text(item.GeometryType),'topology':topology,'quantities':{}}
    for name in ('Volume','SurfaceArea','LengthX','LengthY','LengthZ','CentroidX','CentroidY','CentroidZ'):
        geometry['quantities'][name]=_corex_quantity(item,name)
    bodies.append(dict(_corex_row(item,index_by_id),suppressed=bool(item.Suppressed),geometry=geometry))
scopes=[]
for owner_index,item in enumerate(objects):
    for role in ('Location','SourceLocation','TargetLocation'):
        try: scope=getattr(item,role)
        except AttributeError: continue
        except Exception as exc: raise RuntimeError('mechanical.capability_unproved: '+role+' is unreadable for '+_corex_text(item.Name))
        if scope is None:
            scopes.append({'owner_index':owner_index,'role':role,'selection_type':'none','identities':[]});continue
        try: raw_ids=list(scope.Ids or ());selection_type=_corex_text(scope.SelectionType)
        except AttributeError:
            try: related_index=index_by_id[int(scope.ObjectId)]
            except Exception: raise RuntimeError('mechanical.capability_unproved: '+role+' relation cannot be normalized')
            scopes.append({'owner_index':owner_index,'role':role,'selection_type':'object','identities':[{'kind':'object','tree_index':related_index}]});continue
        ids=[]
        for raw_id in raw_ids:
            entity_id=int(raw_id)
            if entity_id in geometry_ids: ids.append(geometry_ids[entity_id])
            elif 'Geometry' in selection_type: raise RuntimeError('mechanical.capability_unproved: geometry scope identity cannot be normalized')
            else: ids.append({'kind':selection_type,'id':entity_id})
        scopes.append({'owner_index':owner_index,'role':role,'selection_type':selection_type,'identities':ids})
snippets=[]
for item in objects:
    if _corex_text(item.GetType().FullName)!='Ansys.ACT.Automation.Mechanical.CommandSnippet': continue
    snippets.append(dict(_corex_row(item,index_by_id),input=_corex_text(item.Input),step_selection_mode=_corex_text(item.StepSelectionMode),step_number=int(item.StepNumber),issue_solve_command=bool(item.IssueSolveCommand)))
snapshot={'schema_version':1,'native_owner_ids':[int(item.ObjectId) for item in objects],'tree':tree,'analyses':analyses,'bodies':bodies,'scopes':scopes,'snippets':snippets}
encoded=json.dumps(snapshot,ensure_ascii=False,separators=(',',':')).encode('utf-8')
stream=open(_corex_data['native_output_path'],'wb')
try: stream.write(encoded);stream.flush()
finally: stream.close()
_corex_receipt=json.dumps({'byte_length':len(encoded),'sha256':hashlib.sha256(encoded).hexdigest()},separators=(',',':'))
_corex_receipt'''


def resolve_save_format(destination: Path, requested: object) -> str:
    if type(requested) is not str or requested not in SAVE_FORMATS:
        raise ValueError("Format must be auto, mechdb, mechdat, mechpz, wbpj, or wbpz")
    extension = destination.suffix.casefold().removeprefix(".")
    if extension not in set(SAVE_FORMATS) - {"auto"}:
        raise ValueError(
            "Save File must end in .mechdb, .mechdat, .mechpz, .wbpj, or .wbpz"
        )
    format_code = extension if requested == "auto" else requested
    if format_code != extension:
        raise ValueError(
            f"mechanical.save_failed: Format {format_code} does not agree with .{extension}"
        )
    return format_code


def companion_path(primary: Path, format_code: str) -> Path | None:
    if format_code in _MODEL_FORMATS:
        return primary.with_name(primary.stem + "_Mech_Files")
    if format_code in _PROJECT_FORMATS:
        return primary.with_name(primary.stem + "_files")
    return None


def _normal(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def _same_path(first: Path, second: Path) -> bool:
    if _normal(first) == _normal(second):
        return True
    try:
        return first.exists() and second.exists() and os.path.samefile(first, second)
    except OSError:
        return False


def _validate_windows_path(path: Path) -> None:
    name = path.name
    if (
        not name
        or len(name) > 255
        or name.rstrip(" .") != name
        or name.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES
        or any(ord(char) < 32 or char in '<>:"/\\|?*' for char in name)
        or os.name == "nt" and len(str(path)) >= 260
    ):
        raise ValueError(f"Mechanical save destination is not a safe Windows path: {path}")


def _validate_ancestors(path: Path) -> None:
    cursor = path
    while True:
        if cursor.exists() and is_reparse_point(cursor):
            raise ValueError(
                "Mechanical save destination and its ancestors must not be links or reparse points"
            )
        if cursor == cursor.parent:
            return
        cursor = cursor.parent


def _iter_bundle_paths(path: Path):
    if not path.exists():
        return
    yield path
    if path.is_dir():
        for root, directories, files in os.walk(path):
            root_path = Path(root)
            for name in (*directories, *files):
                yield root_path / name


def _assert_normal_bundle(path: Path, *, expected_directory: bool) -> None:
    if not path.exists():
        return
    if is_reparse_point(path) or path.is_dir() is not expected_directory:
        raise ValueError(f"Mechanical save destination has an unsafe type: {path}")
    for item in _iter_bundle_paths(path):
        if is_reparse_point(item):
            raise ValueError(f"Mechanical save bundle contains a link or reparse point: {item}")
        if item != path and not (item.is_dir() or item.is_file()):
            raise ValueError(f"Mechanical save bundle contains a non-file entry: {item}")


def _assert_unlocked(path: Path) -> None:
    if os.name != "nt" or not path.exists():
        return
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.CreateFileW(
        wintypes.LPCWSTR(str(path)),
        0,
        0,
        None,
        3,
        0x02000000 if path.is_dir() else 0x80,
        None,
    )
    if handle == ctypes.c_void_p(-1).value:
        raise PermissionError(f"Mechanical save destination is open or locked: {path}")
    kernel32.CloseHandle(handle)


def _assert_bundle_unlocked(path: Path) -> None:
    for item in _iter_bundle_paths(path):
        _assert_unlocked(item)


def preflight_save_destination(
    destination: Path,
    *,
    source: Path,
    format_code: str,
    overwrite: bool,
) -> DestinationPreflight:
    if type(overwrite) is not bool:
        raise TypeError("Overwrite existing must be Boolean")
    destination = destination.resolve(strict=False)
    source = source.resolve(strict=True)
    _validate_windows_path(destination)
    _validate_ancestors(destination)
    if not destination.parent.is_dir() or is_reparse_point(destination.parent):
        raise ValueError("Mechanical save destination parent must be an existing normal directory")
    companion = companion_path(destination, format_code)
    if companion is not None:
        _validate_windows_path(companion)
        _validate_ancestors(companion)
    source_destination = _normal(destination) == _normal(source)
    if not source_destination and _same_path(destination, source):
        raise ValueError(
            "Mechanical save destination aliases the source; choose the exact source path explicitly"
        )
    source_companion = companion_path(source, source.suffix.casefold().removeprefix("."))
    if source_companion is not None and not source_destination:
        resolved_source_companion = source_companion.resolve(strict=False)
        if destination.is_relative_to(resolved_source_companion) or (
            companion is not None and companion.is_relative_to(resolved_source_companion)
        ):
            raise ValueError("Mechanical save destination must not be inside the source companion directory")
    if source_destination and not overwrite:
        raise FileExistsError(
            "Mechanical source overwrite requires the source as File and Overwrite existing enabled"
        )
    targets = ((destination, False), *(([(companion, True)] if companion else [])))
    for target, is_directory in targets:
        _assert_normal_bundle(target, expected_directory=is_directory)
        if target.exists() and not overwrite:
            raise FileExistsError(f"Mechanical save destination already exists: {target}")
        if target.exists() and overwrite:
            _assert_bundle_unlocked(target)
    if source_destination:
        _assert_bundle_unlocked(source)
        if source_companion is not None and source_companion.exists():
            _assert_normal_bundle(source_companion, expected_directory=True)
            _assert_bundle_unlocked(source_companion)
    return DestinationPreflight(
        destination,
        companion,
        source_destination,
        tuple(
            (target, _fingerprint(target) if target.exists() else None)
            for target, _is_directory in targets
        ),
    )


def create_save_staging(destination: Path, format_code: str) -> SaveStaging:
    root = Path(tempfile.mkdtemp(prefix=f".corex-{format_code}-", dir=destination.parent))
    primary = root / f"s.{format_code}"
    companion = companion_path(primary, format_code)
    verify_directory = root / "v"
    verify_project = verify_directory / ("v.wbpj" if format_code in {"wbpj", "wbpz"} else "v.mechdb")
    native_project = root / "p" / "p.wbpj" if format_code == "wbpz" else (
        primary if format_code == "wbpj" else None
    )
    try:
        for path in (primary, companion, verify_project, native_project):
            if path is not None:
                _validate_windows_path(path)
        verify_directory.mkdir()
        if native_project is not None and native_project != primary:
            native_project.parent.mkdir()
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return SaveStaging(root, primary, companion, verify_project, native_project)


def validate_native_save_receipt(
    value: object,
    *,
    format_code: str,
    staging: SaveStaging,
) -> dict[str, Any]:
    required = {
        "schema_version", "format", "reopen_verified", "work_restored",
        "object_count", "stage_bytes", "analysis_states",
        "reopened_analysis_states", "result_directories", "user_directory",
        "user_directory_status",
    }
    if (
        not isinstance(value, dict)
        or set(value) != required
        or value["schema_version"] != 1
        or value["format"] != format_code
        or value["reopen_verified"] is not True
        or value["work_restored"] is not True
        or type(value["object_count"]) is not int
        or value["object_count"] < 1
        or type(value["stage_bytes"]) is not int
        or value["stage_bytes"] < 1
        or type(value["result_directories"]) is not list
        or len(value["result_directories"]) > 256
        or any(
            type(path) is not str or not path or len(path) > 32767
            for path in value["result_directories"]
        )
        or type(value["user_directory"]) is not str
        or len(value["user_directory"]) > 32767
        or value["user_directory_status"]
        not in {"available", "none", "empty", "unavailable", "unreadable", "not_consumed"}
    ):
        raise RuntimeError("Mechanical standalone save returned an invalid native receipt")
    state_fields = {
        "id", "working_dir", "working_dir_status", "result_file", "result_exists",
        "reader_available", "solution_status",
    }
    for key in ("analysis_states", "reopened_analysis_states"):
        states = value[key]
        if (
            type(states) is not list
            or len(states) > 256
            or any(
                not isinstance(state, dict)
                or set(state) != state_fields
                or type(state["id"]) is not int
                or state["id"] < 0
                or type(state["working_dir"]) is not str
                or state["working_dir_status"]
                not in {"available", "none", "empty", "unavailable", "unreadable"}
                or type(state["result_file"]) is not str
                or type(state["result_exists"]) is not bool
                or type(state["reader_available"]) is not bool
                or type(state["solution_status"]) is not str
                or any(
                    len(state[field]) > 32767
                    for field in ("working_dir", "result_file", "solution_status")
                )
                for state in states
            )
        ):
            raise RuntimeError("Mechanical standalone save returned invalid analysis state")
    if format_code == "mechpz":
        expected_roots = [state["working_dir"] for state in value["analysis_states"]]
        if (
            not value["user_directory"]
            or value["user_directory_status"] != "available"
            or any(not root for root in expected_roots)
            or any(
                state["working_dir_status"] != "available"
                for state in value["analysis_states"]
            )
            or value["result_directories"] != expected_roots
        ):
            raise RuntimeError(
                "Mechanical standalone archive did not provide its native result/user roots"
            )
    elif (
        value["result_directories"]
        or value["user_directory"]
        or value["user_directory_status"] != "not_consumed"
    ):
        raise RuntimeError(
            "Mechanical nonarchive save consumed archive-only inventory roots"
        )
    validate_staged_bundle(staging, format_code=format_code)
    if staging.primary.stat().st_size != value["stage_bytes"]:
        raise RuntimeError("Mechanical standalone save receipt size changed")
    return dict(value)


def model_export_owner_identity(
    tree: list[dict[str, Any]], owner_index: int,
) -> dict[str, Any]:
    if type(owner_index) is not int or not 0 <= owner_index < len(tree):
        raise RuntimeError("mechanical.save_failed: selected-model owner index is invalid")
    chain: list[int] = []
    seen: set[int] = set()
    current: int | None = owner_index
    while current is not None:
        if current in seen or not 0 <= current < len(tree):
            raise RuntimeError("mechanical.save_failed: selected-model owner ancestry is invalid")
        seen.add(current)
        chain.append(current)
        parent = tree[current].get("parent_index")
        if parent is not None and type(parent) is not int:
            raise RuntimeError("mechanical.save_failed: selected-model owner parent is invalid")
        current = parent
    chain.reverse()
    return {
        "owner_index": owner_index,
        "owner_parent_index": tree[owner_index]["parent_index"],
        "object_path": "tree:" + "/".join(str(index) for index in chain),
    }


def model_export_native_owner_map(
    tree: list[dict[str, Any]], native_owner_ids: object,
) -> dict[int, int]:
    if (
        type(native_owner_ids) is not list
        or len(native_owner_ids) != len(tree)
        or len(native_owner_ids) > 100_000
        or any(type(object_id) is not int or object_id < 0 for object_id in native_owner_ids)
        or len(set(native_owner_ids)) != len(native_owner_ids)
    ):
        raise RuntimeError(
            "mechanical.save_failed: selected-model native owner mapping is invalid"
        )
    for index in range(len(tree)):
        model_export_owner_identity(tree, index)
    return {object_id: index for index, object_id in enumerate(native_owner_ids)}


def validate_model_export_snapshot(
    value: object, *, complete: bool = True,
) -> dict[str, Any]:
    base_fields = {"schema_version", "tree", "analyses", "bodies", "scopes", "snippets"}
    semantic_fields = {
        "settings", "definitions", "cameras", "unreadable_display_diagnostics",
    }
    fields = (
        base_fields | semantic_fields
        if complete
        else base_fields | {"native_owner_ids"}
    )
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value["schema_version"] != 1
        or any(type(value[key]) is not list for key in fields - {"schema_version"})
        or len(value["tree"]) > 100_000
        or any(len(value[key]) > len(value["tree"]) for key in (
            "analyses", "bodies", "snippets",
        ))
        or len(value["scopes"]) > 300_000
    ):
        raise RuntimeError("mechanical.save_failed: selected-model snapshot is invalid")
    row_fields = {"name", "api_type", "parent_index"}
    for key in ("tree", "analyses"):
        if any(
            not isinstance(row, dict)
            or set(row) != row_fields
            or any(type(row[field]) is not str or not row[field] for field in ("name", "api_type"))
            or row["parent_index"] is not None
            and (type(row["parent_index"]) is not int or not 0 <= row["parent_index"] < len(value["tree"]))
            for row in value[key]
        ):
            raise RuntimeError(f"mechanical.save_failed: selected-model {key} snapshot is invalid")
    for index in range(len(value["tree"])):
        model_export_owner_identity(value["tree"], index)
    typed_fields = {
        "bodies": row_fields | {"suppressed", "geometry"},
        "snippets": row_fields | {
            "input", "step_selection_mode", "step_number", "issue_solve_command",
        },
    }
    for key, expected in typed_fields.items():
        if any(
            not isinstance(row, dict)
            or set(row) != expected
            or any(type(row[field]) is not str or not row[field] for field in ("name", "api_type"))
            or row["parent_index"] is not None
            and (type(row["parent_index"]) is not int or not 0 <= row["parent_index"] < len(value["tree"]))
            for row in value[key]
        ):
            raise RuntimeError(f"mechanical.save_failed: selected-model {key} snapshot is invalid")
    if any(type(row["suppressed"]) is not bool for row in value["bodies"]):
        raise RuntimeError("mechanical.save_failed: selected-model body state is invalid")
    if any(
        not isinstance(row["geometry"], dict)
        or set(row["geometry"]) != {"geometry_type", "topology", "quantities"}
        or type(row["geometry"]["geometry_type"]) is not str
        or not row["geometry"]["geometry_type"]
        or set(row["geometry"]["topology"])
        != {"face_count", "edge_count", "vertex_count"}
        or any(
            type(count) is not int or count < 0
            for count in row["geometry"]["topology"].values()
        )
        or set(row["geometry"]["quantities"])
        != {
            "Volume", "SurfaceArea", "LengthX", "LengthY", "LengthZ",
            "CentroidX", "CentroidY", "CentroidZ",
        }
        or any(
            not isinstance(quantity, dict)
            or set(quantity) != {"value", "unit"}
            or type(quantity["value"]) not in {int, float}
            or not math.isfinite(quantity["value"])
            or type(quantity["unit"]) is not str
            or not quantity["unit"]
            for quantity in row["geometry"]["quantities"].values()
        )
        for row in value["bodies"]
    ):
        raise RuntimeError("mechanical.save_failed: selected-model geometry fingerprint is invalid")
    scope_fields = {"owner_index", "role", "selection_type", "identities"}
    if any(
        not isinstance(row, dict)
        or set(row) != scope_fields
        or type(row["owner_index"]) is not int
        or not 0 <= row["owner_index"] < len(value["tree"])
        or row["role"] not in {"Location", "SourceLocation", "TargetLocation"}
        or type(row["selection_type"]) is not str
        or not row["selection_type"]
        or type(row["identities"]) is not list
        or len(row["identities"]) > 100_000
        or any(
            not isinstance(identity, dict)
            or identity.get("kind") == "object"
            and set(identity) != {"kind", "tree_index"}
            or identity.get("kind") in {"body", "face", "edge", "vertex"}
            and set(identity) != {"body_index", "kind", "index"}
            or identity.get("kind") not in {"object", "body", "face", "edge", "vertex"}
            and set(identity) != {"kind", "id"}
            for identity in row["identities"]
        )
        for row in value["scopes"]
    ):
        raise RuntimeError("mechanical.save_failed: selected-model scope fingerprint is invalid")
    if any(
        type(row["input"]) is not str
        or type(row["step_selection_mode"]) is not str
        or type(row["step_number"]) is not int
        or row["step_number"] < 0
        or type(row["issue_solve_command"]) is not bool
        for row in value["snippets"]
    ):
        raise RuntimeError("mechanical.save_failed: selected-model snippet state is invalid")
    if not complete:
        model_export_native_owner_map(value["tree"], value["native_owner_ids"])
        return dict(value)
    if any(
        not isinstance(row, dict)
        or set(row) != {
            "owner_index", "owner_parent_index", "object_path",
            "property_key", "caption", "display_value",
            "definition_kind", "scalar_value", "unit", "quantity_name",
            "formula", "has_tabular_data", "tables",
        }
        or any(type(row[key]) is not str for key in (
            "object_path", "property_key", "caption", "display_value",
            "definition_kind", "unit", "quantity_name", "formula",
        ))
        or not row["object_path"]
        or not row["property_key"]
        or {
            key: row[key]
            for key in ("owner_index", "owner_parent_index", "object_path")
        }
        != model_export_owner_identity(value["tree"], row["owner_index"])
        or row["scalar_value"] is not None
        and (type(row["scalar_value"]) not in {int, float} or not math.isfinite(row["scalar_value"]))
        or type(row["has_tabular_data"]) is not bool
        or type(row["tables"]) is not list
        for row in value["settings"]
    ):
        raise RuntimeError("mechanical.save_failed: selected-model settings fingerprint is invalid")
    if any(type(item) is not str or not item for item in value["definitions"]):
        raise RuntimeError("mechanical.save_failed: selected-model definition fingerprint is invalid")
    for encoded in value["definitions"]:
        try:
            definition = json.loads(encoded)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "mechanical.save_failed: selected-model definition fingerprint is malformed"
            ) from exc
        if (
            not isinstance(definition, dict)
            or set(definition) != {"sources", "tables", "definitions"}
            or type(definition["sources"]) is not list
            or type(definition["tables"]) is not list
            or not isinstance(definition["definitions"], dict)
        ):
            raise RuntimeError("mechanical.save_failed: selected-model definition schema is invalid")
        source_pairs: set[tuple[str, str]] = set()
        for source in definition["sources"]:
            if (
                not isinstance(source, dict)
                or set(source) != {
                    "kind", "owner_index", "owner_parent_index", "object_path",
                    "property_key",
                }
                or source["kind"] != "property"
                or type(source["property_key"]) is not str
                or not source["property_key"]
                or {
                    key: source[key]
                    for key in ("owner_index", "owner_parent_index", "object_path")
                }
                != model_export_owner_identity(value["tree"], source["owner_index"])
            ):
                raise RuntimeError("mechanical.save_failed: selected-model definition owner is invalid")
            pair = (source["object_path"], source["property_key"])
            if pair in source_pairs:
                raise RuntimeError("mechanical.save_failed: selected-model definition owner is ambiguous")
            source_pairs.add(pair)
        split = definition["definitions"]
        if (
            set(split) != {"columns", "index", "data"}
            or type(split["columns"]) is not list
            or type(split["data"]) is not list
            or "object_path" not in split["columns"]
            or "property_key" not in split["columns"]
        ):
            raise RuntimeError("mechanical.save_failed: selected-model Definitions table is invalid")
        path_index = split["columns"].index("object_path")
        property_index = split["columns"].index("property_key")
        if any(
            type(row) is not list
            or len(row) != len(split["columns"])
            or (row[path_index], row[property_index]) not in source_pairs
            for row in split["data"]
        ):
            raise RuntimeError("mechanical.save_failed: selected-model Definitions owner is missing")
    camera_fields = {
        "kind", "name", "index", "focal_point", "view_vector", "up_vector",
        "scene_width", "scene_height", "length_unit", "availability_notes",
    }
    if any(
        not isinstance(row, dict)
        or set(row) != camera_fields
        or row["kind"] not in {"saved", "current"}
        or type(row["name"]) is not str
        or row["index"] is not None and (type(row["index"]) is not int or row["index"] < 0)
        or any(
            vector is not None
            and (
                type(vector) is not list
                or len(vector) != 3
                or any(type(item) not in {int, float} or not math.isfinite(item) for item in vector)
            )
            for vector in (row["focal_point"], row["view_vector"], row["up_vector"])
        )
        or any(
            item is not None
            and (type(item) not in {int, float} or not math.isfinite(item))
            for item in (row["scene_width"], row["scene_height"])
        )
        or row["length_unit"] is not None and type(row["length_unit"]) is not str
        or not isinstance(row["availability_notes"], dict)
        for row in value["cameras"]
    ):
        raise RuntimeError("mechanical.save_failed: selected-model camera fingerprint is invalid")
    if any(
        not isinstance(row, dict)
        or set(row) != {
            "owner_index", "owner_parent_index", "object_path", "property_key", "reason"
        }
        or any(
            type(row[key]) is not str or not row[key]
            for key in ("object_path", "property_key", "reason")
        )
        or {
            key: row[key]
            for key in ("owner_index", "owner_parent_index", "object_path")
        }
        != model_export_owner_identity(value["tree"], row["owner_index"])
        for row in value["unreadable_display_diagnostics"]
    ):
        raise RuntimeError("mechanical.save_failed: selected-model diagnostics are invalid")
    return dict(value)


def compare_model_export_snapshot(
    expected: object, actual: object,
) -> dict[str, Any]:
    expected = validate_model_export_snapshot(expected)
    actual = validate_model_export_snapshot(actual)
    semantic_keys = (
        "tree", "analyses", "bodies", "scopes", "snippets", "settings",
        "definitions", "cameras",
    )
    if any(actual[key] != expected[key] for key in semantic_keys):
        changed = [
            key
            for key in semantic_keys
            if actual[key] != expected[key]
        ]
        raise RuntimeError(
            "mechanical.save_failed: selected-model export changed " + ", ".join(changed)
        )
    return {
        "tree_object_count": len(expected["tree"]),
        "analysis_count": len(expected["analyses"]),
        "body_count": len(expected["bodies"]),
        "definition_count": len(expected["definitions"]),
        "setting_count": len(expected["settings"]),
        "scope_count": len(expected["scopes"]),
        "snippet_count": len(expected["snippets"]),
        "camera_count": len(expected["cameras"]),
    }


def validate_model_export_save_receipt(
    value: object,
    *,
    format_code: str,
    staging: SaveStaging,
) -> dict[str, Any]:
    count_fields = {
        "tree_object_count", "analysis_count", "body_count", "definition_count",
        "setting_count", "scope_count", "snippet_count", "camera_count",
    }
    required = {
        "schema_version", "marker", "format", "reopen_verified",
        "source_workbench_preserved", "bridge_bytes", "stage_bytes", *count_fields,
    }
    if (
        not isinstance(value, dict)
        or set(value) != required
        or value["schema_version"] != 1
        or value["marker"] != "corex-workbench-model-export-v1"
        or value["format"] != format_code
        or format_code not in _MODEL_FORMATS
        or value["reopen_verified"] is not True
        or value["source_workbench_preserved"] is not True
        or type(value["bridge_bytes"]) is not int
        or value["bridge_bytes"] < 1
        or type(value["stage_bytes"]) is not int
        or value["stage_bytes"] < 1
        or any(type(value[key]) is not int or value[key] < 0 for key in count_fields)
        or value["tree_object_count"] < 1
        or value["analysis_count"] < 1
        or value["body_count"] < 1
    ):
        raise RuntimeError("mechanical.save_failed: selected-model conversion receipt is invalid")
    validate_staged_bundle(staging, format_code=format_code)
    if staging.primary.stat().st_size != value["stage_bytes"]:
        raise RuntimeError("mechanical.save_failed: selected-model staged size changed")
    return dict(value)


def validate_staged_bundle(staging: SaveStaging, *, format_code: str) -> None:
    _assert_normal_bundle(staging.primary, expected_directory=False)
    if not staging.primary.is_file() or staging.primary.stat().st_size < 1:
        raise RuntimeError("Mechanical native staged primary file is missing or empty")
    if format_code in _BUNDLE_FORMATS:
        assert staging.companion is not None
        _assert_normal_bundle(staging.companion, expected_directory=True)
        if not staging.companion.is_dir():
            raise RuntimeError("Mechanical native staged companion directory is missing")
    elif not zipfile.is_zipfile(staging.primary):
        raise RuntimeError("Mechanical native staged archive is not a readable archive")


def validate_workbench_project_bundle(staging: SaveStaging) -> None:
    validate_staged_bundle(staging, format_code="wbpj")
    try:
        root = ET.parse(staging.primary).getroot()
    except (ET.ParseError, OSError) as exc:
        raise RuntimeError("mechanical.save_failed: staged Workbench project is not readable XML") from exc
    assert staging.companion is not None
    if root.tag != "Storage" or not any(path.is_file() for path in staging.companion.rglob("*")):
        raise RuntimeError("mechanical.save_failed: staged Workbench project or companion is incomplete")


def validate_workbench_archive_structure(archive: Path) -> dict[str, int]:
    members: set[str] = set()
    with zipfile.ZipFile(archive) as stream:
        projects = [member.filename for member in stream.infolist() if not member.is_dir() and member.filename.casefold().endswith(".wbpj")]
        if len(projects) != 1:
            raise RuntimeError("mechanical.save_failed: native Workbench archive has no unique project")
        prefix = projects[0][:-5] + "_files/"
        for member in stream.infolist():
            if member.is_dir():
                continue
            if member.filename in members:
                raise RuntimeError("mechanical.save_failed: native Workbench archive has duplicate members")
            members.add(member.filename)
        if not any(name.startswith(prefix) for name in members):
            raise RuntimeError("mechanical.save_failed: native Workbench archive companion is empty")
    return {"archive_member_count": len(members)}


def validate_archive_inclusions(
    archive: Path,
    *,
    work_path: Path,
    result_directories: list[str],
    user_directory: str,
    include_results: bool,
    include_user_files: bool,
) -> dict[str, Any]:
    work_companion = companion_path(work_path, "mechdb")
    if work_companion is None or not work_companion.is_dir():
        raise RuntimeError("mechanical.save_failed: native working companion directory is missing")
    work_companion = work_companion.resolve(strict=True)

    def inventory(raw_roots: list[str]) -> tuple[dict[str, tuple[int, str]], tuple[str, ...]]:
        files: dict[str, tuple[int, str]] = {}
        prefixes: list[str] = []
        for raw_root in raw_roots:
            root = Path(raw_root).resolve(strict=True)
            if not root.is_dir() or is_reparse_point(root) or not root.is_relative_to(work_companion):
                raise RuntimeError(
                    f"mechanical.save_failed: native archive inventory root is unsafe: {root}"
                )
            prefix = root.relative_to(work_companion).as_posix().rstrip("/")
            if not prefix or prefix in prefixes:
                continue
            prefixes.append(prefix)
            for path in root.rglob("*"):
                if is_reparse_point(path):
                    raise RuntimeError(
                        f"mechanical.save_failed: native archive inventory contains an alias: {path}"
                    )
                if path.is_file():
                    relative = path.relative_to(work_companion).as_posix()
                    files[relative] = (path.stat().st_size, _sha256(path))
        return files, tuple(prefixes)

    result_inventory, result_prefixes = inventory(list(dict.fromkeys(result_directories)))
    user_roots = [user_directory] if user_directory else []
    user_inventory, user_prefixes = inventory(user_roots)
    archive_inventory: dict[str, tuple[int, str]] = {}
    with zipfile.ZipFile(archive) as stream:
        for member in stream.infolist():
            if member.is_dir() or "_Mech_Files/" not in member.filename:
                continue
            relative = member.filename.split("_Mech_Files/", 1)[1]
            if relative in archive_inventory:
                raise RuntimeError(
                    f"mechanical.save_failed: duplicate native archive member: {relative}"
                )
            digest = hashlib.sha256()
            with stream.open(member) as payload:
                for chunk in iter(lambda: payload.read(1024 * 1024), b""):
                    digest.update(chunk)
            archive_inventory[relative] = (member.file_size, digest.hexdigest())
    for label, requested, expected, prefixes in (
        ("result/solution", include_results, result_inventory, result_prefixes),
        ("user", include_user_files, user_inventory, user_prefixes),
    ):
        present = {
            name: identity
            for name, identity in archive_inventory.items()
            if any(name == prefix or name.startswith(prefix + "/") for prefix in prefixes)
        }
        if requested and present != expected:
            missing = sorted(expected.keys() - present.keys())
            changed = sorted(
                name
                for name in expected.keys() & present.keys()
                if expected[name] != present[name]
            )
            unexpected = sorted(present.keys() - expected.keys())
            details = [
                *(f"missing {name}" for name in missing),
                *(f"changed {name}" for name in changed),
                *(f"unexpected {name}" for name in unexpected),
            ]
            raise RuntimeError(
                f"mechanical.save_failed: requested {label} inventory differs from staged archive: "
                + ", ".join(details)
            )
        if not requested and present:
            raise RuntimeError(
                f"mechanical.save_failed: excluded {label} files remain in staged archive: "
                + ", ".join(sorted(present))
            )
    return {
        "results_requested": include_results,
        "result_roots_checked": len(result_prefixes),
        "result_files_checked": len(result_inventory),
        "user_files_requested": include_user_files,
        "user_roots_checked": len(user_prefixes),
        "user_files_checked": len(user_inventory),
        "external_imported_files_consumed": False,
        "complete": bool(include_results and include_user_files),
        "exclusions": [
            label
            for requested, label in (
                (include_results, "result/solution files"),
                (include_user_files, "user files"),
            )
            if not requested
        ],
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint(path: Path) -> tuple[Any, ...]:
    _assert_normal_bundle(path, expected_directory=path.is_dir())
    root_stat = path.stat()
    if path.is_file():
        return (
            "file", root_stat.st_dev, root_stat.st_ino, root_stat.st_size,
            root_stat.st_mtime_ns, _sha256(path),
        )
    rows = []
    for item in sorted(_iter_bundle_paths(path), key=lambda value: value.relative_to(path).as_posix()):
        if item == path:
            continue
        relative = item.relative_to(path).as_posix()
        stat = item.stat()
        if item.is_dir():
            rows.append(("dir", relative, stat.st_dev, stat.st_ino, stat.st_mtime_ns))
        else:
            rows.append((
                "file", relative, stat.st_dev, stat.st_ino, stat.st_size,
                stat.st_mtime_ns, _sha256(item),
            ))
    return (
        "directory", root_stat.st_dev, root_stat.st_ino, root_stat.st_mtime_ns,
        tuple(rows),
    )


def _fsync_bundle(path: Path) -> None:
    for item in _iter_bundle_paths(path):
        if item.is_file():
            with item.open("r+b") as stream:
                os.fsync(stream.fileno())


@dataclass(slots=True)
class PublishedSave:
    staging: SaveStaging
    files: list[Path]
    original: dict[Path, tuple[Any, ...] | None]
    backups: dict[Path, Path]
    published: dict[Path, tuple[Any, ...]]
    closed: bool = False

    def rollback(self) -> None:
        if self.closed:
            return
        restore_errors: list[str] = []
        blocked: set[Path] = set()
        for target, expected in reversed(list(self.published.items())):
            try:
                if target.exists():
                    if _fingerprint(target) != expected:
                        blocked.add(target)
                        restore_errors.append(
                            f"preserved externally changed destination {target}"
                        )
                    elif target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
            except OSError as error:
                blocked.add(target)
                restore_errors.append(f"remove {target}: {error}")
        for target, backup in reversed(list(self.backups.items())):
            if target in blocked:
                continue
            try:
                if not backup.exists():
                    restore_errors.append(f"missing recovery backup {backup}")
                    continue
                if target.exists():
                    if _fingerprint(target) != self.original[target]:
                        restore_errors.append(f"preserved unexpected destination {target}")
                else:
                    os.replace(backup, target)
            except OSError as error:
                restore_errors.append(f"restore {target}: {error}")
        self.closed = True
        if restore_errors:
            raise RuntimeError(
                f"mechanical.publication_recovery_required: {self.staging.root}; "
                + "; ".join(restore_errors)
            )
        try:
            shutil.rmtree(self.staging.root)
        except OSError as error:
            raise RuntimeError(
                f"mechanical.publication_recovery_required: {self.staging.root}; "
                f"restored destinations but recovery cleanup failed: {error}"
            ) from error

    def commit(self) -> None:
        if self.closed:
            raise RuntimeError("Mechanical save publication transaction is closed")
        changed = [
            target
            for target, expected in self.published.items()
            if not target.exists() or _fingerprint(target) != expected
        ]
        if changed:
            try:
                self.rollback()
            except RuntimeError:
                raise
            raise RuntimeError(
                "Mechanical save destination changed before publication commit: "
                + ", ".join(str(path) for path in changed)
            )
        self.closed = True
        try:
            shutil.rmtree(self.staging.root)
        except OSError as error:
            raise RuntimeError(
                f"mechanical.publication_recovery_required: {self.staging.root}; "
                f"publication committed but backup cleanup failed: {error}"
            ) from error


def _verify_destination_snapshot(preflight: DestinationPreflight) -> None:
    for target, expected in preflight.identities:
        current = _fingerprint(target) if target.exists() else None
        if current != expected:
            raise FileExistsError(
                f"Mechanical save destination changed after preflight: {target}"
            )
        if target.exists():
            _assert_bundle_unlocked(target)


def publish_save(
    staging: SaveStaging,
    *,
    preflight: DestinationPreflight,
    format_code: str,
) -> PublishedSave:
    validate_staged_bundle(staging, format_code=format_code)
    _fsync_bundle(staging.primary)
    if staging.companion is not None:
        _fsync_bundle(staging.companion)
    _verify_destination_snapshot(preflight)
    destination = preflight.destination
    destination_companion = preflight.companion
    backups = staging.root / "backups"
    backups.mkdir()
    stage_pairs = [(staging.primary, destination)]
    if staging.companion is not None and destination_companion is not None:
        stage_pairs.insert(0, (staging.companion, destination_companion))
    backup_paths: dict[Path, Path] = {}
    published: dict[Path, tuple[Any, ...]] = {}
    transaction = PublishedSave(
        staging,
        [destination, *([destination_companion] if destination_companion else [])],
        dict(preflight.identities),
        backup_paths,
        published,
    )
    try:
        for index, (stage, target) in enumerate(stage_pairs):
            expected = _fingerprint(stage)
            original = transaction.original[target]
            if original is not None:
                backup = backups / f"{index}-{target.name}"
                if target.is_dir():
                    os.replace(target, backup)
                else:
                    os.link(target, backup)
                backup_paths[target] = backup
            if stage.is_dir():
                os.rename(stage, target)
            elif original is not None:
                os.replace(stage, target)
            else:
                os.link(stage, target)
                stage.unlink()
            published[target] = expected
            if _fingerprint(target) != expected:
                raise RuntimeError(f"Mechanical save destination changed during publication: {target}")
    except BaseException as exc:
        try:
            transaction.rollback()
        except RuntimeError as restore_exc:
            raise restore_exc from exc
        raise
    return transaction


def save_receipt_message(
    *,
    destination: Path,
    source: Path,
    format_code: str,
    files: list[Path],
    overwrite: bool,
    archive_policy: Mapping[str, Any] | None,
    semantic_proof: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    policy = dict(archive_policy or {
        "results_consumed": False,
        "user_files_consumed": False,
        "external_imported_files_consumed": False,
        "complete": format_code == "mechdb",
        "exclusions": (
            ["archive result/user/external inclusion guarantees"]
            if format_code == "mechdat"
            else []
        ),
    })
    return {
        "status": "published",
        "message": json.dumps(
            {
                "schema_version": 1,
                "format": format_code,
                "source": str(source),
                "destination": str(destination),
                "files": [str(path) for path in files],
                "overwrite": overwrite,
                "publication": "complete",
                "archive_policy": policy,
                "semantic_proof": dict(semantic_proof or {}),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }


__all__ = [
    "MODEL_EXPORT_SNAPSHOT_BODY",
    "STANDALONE_SAVE_BODY",
    "SAVE_FORMATS",
    "SaveStaging",
    "companion_path",
    "compare_model_export_snapshot",
    "create_save_staging",
    "model_export_owner_identity",
    "model_export_native_owner_map",
    "preflight_save_destination",
    "publish_save",
    "resolve_save_format",
    "save_receipt_message",
    "validate_archive_inclusions",
    "validate_model_export_save_receipt",
    "validate_model_export_snapshot",
    "validate_native_save_receipt",
    "validate_staged_bundle",
    "validate_workbench_archive_structure",
    "validate_workbench_project_bundle",
]
