# Purpose: Extract Mechanical cameras and deterministic viewport image batches without retaining native objects.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_camera_views.py, tests/mechanical_catalogue/test_image_export.py

from __future__ import annotations

import hashlib
import json
import os
import shutil
import string
import tempfile
import unicodedata
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ea_node_editor.addons.mechanical.contracts import (
    camera_view_value,
    encode_selector,
)
from ea_node_editor.runtime_contracts import DataTree, ImageValue, TableValue
from ea_node_editor.runtime_contracts.scientific_values import snapshot_scientific_value

CAMERA_DETAILS_COLUMNS = (
    "name",
    "kind",
    "saved_index",
    "focal_x",
    "focal_y",
    "focal_z",
    "view_x",
    "view_y",
    "view_z",
    "up_x",
    "up_y",
    "up_z",
    "scene_width",
    "scene_height",
    "length_unit",
    "availability_notes",
    "run_id",
    "session_id",
    "document_id",
    "source_key",
    "system_key",
    "model_revision",
    "selector_code",
)

IMAGE_DETAILS_COLUMNS = (
    "object_name",
    "object_path",
    "object_id",
    "view_name",
    "view_kind",
    "view_index",
    "data_path",
    "image_ordinal",
    "width",
    "height",
    "file_path",
    "run_id",
    "session_id",
    "document_id",
    "source_key",
    "system_key",
    "model_revision",
)
IMAGE_CAPTURE_LIMIT = 256
IMAGE_MAX_PIXELS = 33_554_432
_IMAGE_TEMPLATE_FIELDS = frozenset(
    {"object", "view", "object_index", "view_index", "index"}
)
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
)

CAMERA_IDENTITY_FIELDS = (
    "run_id",
    "session_id",
    "document_id",
    "source_key",
    "system_key",
    "model_revision",
)
_RAW_CAMERA_FIELDS = frozenset(
    {
        "kind",
        "name",
        "index",
        "focal_point",
        "view_vector",
        "up_vector",
        "scene_width",
        "scene_height",
        "length_unit",
        "availability_notes",
    }
)


# Runs inside Mechanical's scripting engine. All native state is restored and
# verified before the detached snapshots cross the server boundary.
CAMERA_SCRIPT_BODY = r'''
import json,math,xml.etree.ElementTree as ET

def _corex_note(exc):
    return type(exc).__name__+': '+str(exc)

def _corex_finite(value):
    return not math.isnan(value) and not math.isinf(value)

def _corex_vector(value):
    try:values=list(value)
    except Exception:
        values=[getattr(value,name) for name in ('X','Y','Z')]
    if len(values)!=3:raise ValueError('expected three components')
    result=[float(item) for item in values]
    if not all(_corex_finite(item) for item in result):raise ValueError('components must be finite')
    return result

def _corex_quantity(value):
    number=float(value.Value)
    if not _corex_finite(number):raise ValueError('quantity must be finite')
    unit=str(value.Unit)
    if not unit:raise ValueError('quantity unit is unavailable')
    return number,unit

def _corex_camera():
    camera=Graphics.Camera;notes={};units={}
    try:
        focal=camera.FocalPoint
        focal_point=_corex_vector(focal.Location)
        units['focal_point']=str(focal.Unit)
        if not units['focal_point']:
            focal_point=None;notes['focal_point']='focal-point unit is unavailable'
    except Exception as exc:
        focal_point=None;notes['focal_point']=_corex_note(exc)
    values={}
    for field,attribute in (('view_vector','ViewVector'),('up_vector','UpVector')):
        try:values[field]=_corex_vector(getattr(camera,attribute))
        except Exception as exc:values[field]=None;notes[field]=_corex_note(exc)
    quantities={}
    for field,attribute in (('scene_width','SceneWidth'),('scene_height','SceneHeight')):
        try:
            quantity=getattr(camera,attribute);number,unit=_corex_quantity(quantity)
            quantities[field]=(number,unit,quantity);units[field]=unit
        except Exception as exc:
            quantities[field]=(None,'',None);notes[field]=_corex_note(exc)
    available_units=[unit for unit in units.values() if unit]
    length_unit=available_units[0] if available_units else None
    if length_unit is None:notes['length_unit']='camera length unit is unavailable'
    for field in ('scene_width','scene_height'):
        number,unit,quantity=quantities[field]
        if number is not None and length_unit is not None and unit!=length_unit:
            try:number,_unit=_corex_quantity(quantity.ConvertUnit(length_unit))
            except Exception as exc:number=None;notes[field]='unit conversion failed: '+_corex_note(exc)
        values[field]=number
    return {
        'focal_point':focal_point,'view_vector':values['view_vector'],'up_vector':values['up_vector'],
        'scene_width':values['scene_width'],'scene_height':values['scene_height'],
        'length_unit':length_unit,'availability_notes':notes,
    }

def _corex_presentation_state():
    try:
        camera=Graphics.Camera
        return {
            'active_ids':[int(value.ObjectId) for value in list(Tree.ActiveObjects)],
            'camera':[str(camera.FocalPoint),str(camera.ViewVector),str(camera.UpVector),str(camera.SceneWidth),str(camera.SceneHeight)],
        }
    except Exception as exc:
        raise ValueError('mechanical.capability_unproved: exact camera restoration state is unavailable: '+_corex_note(exc))

def _corex_local_name(tag):
    return str(tag).split('}')[-1]

include=_corex_data['include'];records=[];current=_corex_camera()
if include in ('saved','saved_and_current'):
    manager=Graphics.ModelViewManager;count=int(manager.NumberOfViews)
    manager.ExportModelViews(_corex_data['export_path'])
    stream=open(_corex_data['export_path'],'rb')
    try:root=ET.fromstring(stream.read())
    finally:stream.close()
    if _corex_local_name(root.tag)!='ModelViewsManager':
        raise ValueError('mechanical.camera_schema_invalid: exported saved-view root is unsupported')
    saved=[]
    for original_index,child in enumerate(list(root)):
        if _corex_local_name(child.tag)!='ModelView':
            raise ValueError('mechanical.camera_schema_invalid: exported saved-view child is unsupported')
        if 'Name' not in child.attrib or not str(child.attrib['Name']):
            raise ValueError('mechanical.camera_schema_invalid: saved ModelView requires Name')
        saved.append({'index':original_index,'name':str(child.attrib['Name'])})
    if len(saved)!=count or [item['index'] for item in saved]!=list(range(count)):
        raise ValueError('mechanical.camera_schema_invalid: exported saved-view count/index does not match NumberOfViews')
    if saved:
        before=_corex_presentation_state();restore_name=_corex_data['restore_name']
        if restore_name in [item['name'] for item in saved]:
            raise ValueError('mechanical.camera_schema_invalid: restore view name collides with a saved view')
        created=False;operation_error=None;restore_errors=[]
        try:
            manager.CreateView(restore_name);created=True
            if int(manager.NumberOfViews)!=count+1:
                raise ValueError('restore view was not created exactly once')
            for item in saved:
                manager.ApplyModelView(item['index'])
                records.append(dict({'kind':'saved','name':item['name'],'index':item['index']},**_corex_camera()))
        except BaseException as exc:
            operation_error=exc
        finally:
            if created:
                try:manager.ApplyModelView(restore_name)
                except Exception as exc:restore_errors.append('camera apply: '+_corex_note(exc))
                try:
                    Tree.Activate([DataModel.GetObjectById(object_id) for object_id in before['active_ids']])
                except Exception as exc:restore_errors.append('active objects: '+_corex_note(exc))
                try:manager.DeleteView(restore_name)
                except Exception as exc:restore_errors.append('restore view delete: '+_corex_note(exc))
                try:
                    if int(manager.NumberOfViews)!=count:restore_errors.append('saved-view count changed')
                    if _corex_presentation_state()!=before:restore_errors.append('camera or active objects changed')
                except Exception as exc:restore_errors.append('verification: '+_corex_note(exc))
        if restore_errors:
            raise ValueError('mechanical.restore_failed: camera state restoration failed: '+'; '.join(restore_errors))
        if operation_error is not None:raise operation_error
if include in ('current','saved_and_current'):
    records.append(dict({'kind':'current','name':'Current view','index':None},**current))
_corex_receipt=json.dumps({'views':records},ensure_ascii=False,separators=(',',':'))
_corex_receipt
'''


# Runs inside Mechanical's scripting engine. Selector resolution completes before
# the restore view is created and before the first viewport export.
IMAGE_SCRIPT_BODY = r'''
import json,os

def _corex_note(exc):
    return type(exc).__name__+': '+str(exc)

def _corex_path(value):
    parts=[];seen=[]
    while value is not None and id(value) not in seen:
        seen.append(id(value))
        try:name=str(value.Name).strip()
        except:name=''
        if name:parts.append(name)
        try:value=value.Parent
        except:value=None
    parts.reverse()
    return '/'.join(parts)

def _corex_type(value):
    try:return str(value.GetType().FullName)
    except:return type(value).__name__

def _corex_enum(value):
    return str(value).split('.')[-1]

def _corex_presentation_state(objects):
    try:
        camera=Graphics.Camera
        hidden=[]
        for value in objects:
            try:hidden.append((int(value.ObjectId),bool(value.Hidden)))
            except AttributeError:pass
            except Exception as exc:
                raise ValueError('mechanical.capability_unproved: object visibility is unreadable for '+_corex_path(value)+': '+_corex_note(exc))
        return {
            'active_ids':[int(value.ObjectId) for value in list(Tree.ActiveObjects)],
            'camera':[str(camera.FocalPoint),str(camera.ViewVector),str(camera.UpVector),str(camera.SceneWidth),str(camera.SceneHeight)],
            'hidden':hidden,
        }
    except Exception as exc:
        raise ValueError('mechanical.capability_unproved: exact graphics restoration state is unavailable: '+_corex_note(exc))

def _corex_restore_result(obj,state,set_count):
    errors=[]
    for name,value in (('By',state['by']),('DisplayTime',state['display']),('CalculateTimeHistory',state['history'])):
        try:setattr(obj,name,value)
        except Exception as exc:errors.append((name,_corex_note(exc)))
    set_error=''
    try:obj.SetNumber=state['set']
    except Exception as exc:set_error=_corex_note(exc)
    current_set=None;exact=False
    try:
        current_set=int(obj.SetNumber)
        exact=(_corex_enum(obj.By)==state['by_name'] and str(obj.DisplayTime)==state['display_text'] and bool(obj.CalculateTimeHistory)==state['history'])
    except Exception as exc:errors.append(('verification',_corex_note(exc)))
    approved=(not errors and exact and state['by_name']=='Time' and state['set']==0 and bool(set_error) and current_set is not None and current_set>0 and current_set<=set_count)
    if errors or not exact or (set_error and not approved) or (not set_error and current_set!=state['set']):
        details='; '.join(name+' '+value for name,value in errors)
        if set_error:details='; '.join(filter(None,(details,'SetNumber '+set_error)))
        raise ValueError('mechanical.restore_failed: configured result state could not be restored: '+details)
    if approved:return 'inactive SetNumber drift approved: before=0; after='+str(current_set)+'; zero restore rejected: '+set_error
    return ''

def _corex_evaluate(obj):
    retrieve=getattr(obj,'RetrieveResult',None)
    if not callable(retrieve):return ''
    api_type=_corex_type(obj)
    if api_type.endswith('.ForceReaction'):
        if not all(hasattr(obj,name) for name in ('By','DisplayTime')) or _corex_enum(obj.By)!='Time':
            raise ValueError('mechanical.table_unsupported: ForceReaction image capture requires By=Time')
        before_by=_corex_enum(obj.By);display=obj.DisplayTime;display_text=str(display);failure=None
        try:retrieve()
        except Exception as exc:failure=exc
        finally:
            errors=[]
            try:obj.DisplayTime=display
            except Exception as exc:errors.append('DisplayTime '+_corex_note(exc))
            try:
                if _corex_enum(obj.By)!=before_by or str(obj.DisplayTime)!=display_text:errors.append('By or DisplayTime drifted')
            except Exception as exc:errors.append('verification '+_corex_note(exc))
            if errors:raise ValueError('mechanical.restore_failed: ForceReaction state could not be restored: '+'; '.join(errors))
        if failure is not None:raise failure
        return ''
    has_full=all(hasattr(obj,name) for name in ('By','DisplayTime','CalculateTimeHistory','SetNumber'))
    if has_full:
        state={'by':obj.By,'by_name':_corex_enum(obj.By),'display':obj.DisplayTime,'display_text':str(obj.DisplayTime),'history':bool(obj.CalculateTimeHistory),'set':int(obj.SetNumber)}
        reader=None;set_count=0
        cursor=obj
        while cursor is not None:
            if callable(getattr(cursor,'GetResultsData',None)):
                try:
                    reader=cursor.GetResultsData();set_count=len(list(reader.ListTimeFreq))
                except:set_count=0
                finally:
                    if reader is not None:
                        try:reader.Dispose()
                        except:pass
                break
            try:cursor=cursor.Parent
            except:cursor=None
        failure=None
        try:retrieve()
        except Exception as exc:failure=exc
        finally:
            note=_corex_restore_result(obj,state,set_count)
        if failure is not None:raise failure
        return note
    raise ValueError('mechanical.capability_unproved: selected result has unsupported addressing fields: '+api_type)

objects=list(Tree.AllObjects);by_id={int(value.ObjectId):value for value in objects}
object_choices=[]
for selector in _corex_data['objects']:
    if selector['kind']=='current':
        object_choices.append((None,'Current display','',None))
        continue
    if selector['kind']=='typed':
        obj=by_id.get(selector['object_id'])
        if obj is None or _corex_path(obj)!=selector['object_path']:
            raise ValueError('mechanical.selector_missing: object is missing or changed: '+selector['object_path'])
    else:
        text=selector['text'];matches=[value for value in objects if _corex_path(value)==text]
        if not matches:matches=[value for value in objects if str(value.Name)==text]
        if len(matches)>1:
            raise ValueError('mechanical.selector_ambiguous: object name matches multiple paths: '+str([_corex_path(value) for value in matches]))
        if not matches:raise ValueError('mechanical.selector_missing: object is unavailable: '+text)
        obj=matches[0]
    object_choices.append((obj,str(obj.Name),_corex_path(obj),int(obj.ObjectId)))

manager=Graphics.ModelViewManager;view_count=int(manager.NumberOfViews)
manager.ExportModelViews(_corex_data['view_export_path'])
import xml.etree.ElementTree as ET
stream=open(_corex_data['view_export_path'],'rb')
try:root=ET.fromstring(stream.read())
finally:stream.close()
if str(root.tag).split('}')[-1]!='ModelViewsManager':
    raise ValueError('mechanical.camera_schema_invalid: exported saved-view root is unsupported')
saved=[]
for original_index,child in enumerate(list(root)):
    if str(child.tag).split('}')[-1]!='ModelView' or 'Name' not in child.attrib or not str(child.attrib['Name']):
        raise ValueError('mechanical.camera_schema_invalid: exported saved-view child is unsupported')
    saved.append({'index':original_index,'name':str(child.attrib['Name'])})
if len(saved)!=view_count:
    raise ValueError('mechanical.camera_schema_invalid: exported saved-view count does not match NumberOfViews')
view_choices=[]
for selector in _corex_data['views']:
    if selector['kind']=='current':view_choices.append({'kind':'current','name':'Current view','index':None});continue
    if selector['kind']=='typed':
        matches=[item for item in saved if item['index']==selector['index'] and (selector.get('name') is None or item['name']==selector['name'])]
    else:
        matches=[item for item in saved if item['name']==selector['text']]
    if len(matches)>1:raise ValueError('mechanical.selector_ambiguous: saved view name is ambiguous: '+selector.get('text',selector.get('name','')))
    if not matches:raise ValueError('mechanical.selector_missing: saved view is unavailable: '+selector.get('text',selector.get('name','')))
    view_choices.append(dict({'kind':'saved'},**matches[0]))

before=_corex_presentation_state(objects);restore_name=_corex_data['restore_name'];created=False;operation_error=None;restore_errors=[];records=[];warnings=[]
if restore_name in [item['name'] for item in saved]:raise ValueError('mechanical.camera_schema_invalid: restore view name collides with a saved view')
try:
    manager.CreateView(restore_name);created=True
    if int(manager.NumberOfViews)!=view_count+1:raise ValueError('restore view was not created exactly once')
    for object_index,object_item in enumerate(object_choices):
        obj,object_name,object_path,object_id=object_item
        for view_index,view in enumerate(view_choices):
            if obj is not None:
                Tree.Activate([obj])
                note=_corex_evaluate(obj)
                if note and note not in warnings:warnings.append(note)
            if view['kind']=='saved':manager.ApplyModelView(view['index'])
            else:manager.ApplyModelView(restore_name)
            if _corex_data['fit_view']:Graphics.Camera.SetFit()
            settings=Ansys.Mechanical.Graphics.GraphicsImageExportSettings()
            settings.Width=_corex_data['width'];settings.Height=_corex_data['height']
            settings.CurrentGraphicsDisplay=False
            settings.Background=Ansys.Mechanical.DataModel.Enums.GraphicsBackgroundType.White if _corex_data['background']=='white' else Ansys.Mechanical.DataModel.Enums.GraphicsBackgroundType.GraphicsAppearanceSetting
            output=_corex_data['output_paths'][object_index*len(view_choices)+view_index]
            Graphics.ExportImage(output,Ansys.Mechanical.DataModel.Enums.GraphicsImageExportFormat.PNG,settings)
            records.append({'object_index':object_index,'object_name':object_name,'object_path':object_path,'object_id':object_id,'view_ordinal':view_index,'view_name':view['name'],'view_kind':view['kind'],'view_index':view['index'],'output_path':output})
except BaseException as exc:operation_error=exc
finally:
    if created:
        try:manager.ApplyModelView(restore_name)
        except Exception as exc:restore_errors.append('camera apply: '+_corex_note(exc))
        try:Tree.Activate([DataModel.GetObjectById(object_id) for object_id in before['active_ids']])
        except Exception as exc:restore_errors.append('active objects: '+_corex_note(exc))
        for object_id,hidden in before['hidden']:
            try:
                value=DataModel.GetObjectById(object_id)
                if bool(value.Hidden)!=hidden:value.Hidden=hidden
                if bool(value.Hidden)!=hidden:restore_errors.append('visibility changed for object '+str(object_id))
            except Exception as exc:restore_errors.append('visibility '+str(object_id)+': '+_corex_note(exc))
        try:manager.DeleteView(restore_name)
        except Exception as exc:restore_errors.append('restore view delete: '+_corex_note(exc))
        try:
            after=_corex_presentation_state(objects)
            if int(manager.NumberOfViews)!=view_count:restore_errors.append('saved-view count changed')
            if after!=before:restore_errors.append('camera, active objects, or visibility changed')
        except Exception as exc:restore_errors.append('verification: '+_corex_note(exc))
if restore_errors:raise ValueError('mechanical.restore_failed: graphics state restoration failed: '+'; '.join(restore_errors))
if operation_error is not None:
    if warnings:raise ValueError(str(operation_error)+' ; '+'; '.join(warnings))
    raise operation_error
_corex_receipt=json.dumps({'images':records,'warnings':warnings},ensure_ascii=False,separators=(',',':'))
_corex_receipt
'''

_IMAGE_CAPTURE_MARKER = "before=_corex_presentation_state(objects)"
_IMAGE_SELECTOR_PREFIX, _IMAGE_MARKER_FOUND, _IMAGE_CAPTURE_SUFFIX = IMAGE_SCRIPT_BODY.partition(
    _IMAGE_CAPTURE_MARKER
)
if not _IMAGE_MARKER_FOUND:  # pragma: no cover - source invariant
    raise RuntimeError("Mechanical image script preflight marker is unavailable")
IMAGE_PREFLIGHT_SCRIPT_BODY = _IMAGE_SELECTOR_PREFIX + r'''
records=[]
for object_index,object_item in enumerate(object_choices):
    _obj,object_name,object_path,object_id=object_item
    for view_ordinal,view in enumerate(view_choices):
        records.append({'object_index':object_index,'object_name':object_name,'object_path':object_path,'object_id':object_id,'view_ordinal':view_ordinal,'view_name':view['name'],'view_kind':view['kind'],'view_index':view['index']})
_corex_receipt=json.dumps({'images':records},ensure_ascii=False,separators=(',',':'))
_corex_receipt
'''


def _safe_filename_token(value: object, fallback: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or fallback))
    text = "".join("_" if ord(char) < 32 or char in '<>:"/\\|?*' else char for char in text)
    text = " ".join(text.split()).strip(" .") or fallback
    if text.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        text = f"_{text}"
    return text[:120].rstrip(" .") or fallback


def render_image_filenames(
    template: object,
    labels: list[tuple[str, str]],
    *,
    view_count: int,
) -> list[str]:
    if type(template) is not str or not template:
        raise TypeError("Mechanical image File name must be non-empty text")
    formatter = string.Formatter()
    try:
        parsed = list(formatter.parse(template))
    except ValueError as exc:
        raise ValueError("Mechanical image File name template is invalid") from exc
    for _literal, field, format_spec, conversion in parsed:
        if field is not None and (
            field not in _IMAGE_TEMPLATE_FIELDS or format_spec or conversion
        ):
            raise ValueError(
                "Mechanical image File name supports only object, view, object_index, view_index, and index tokens"
            )
    names = []
    if type(view_count) is not int or view_count < 1:
        raise ValueError("Mechanical image view count must be positive")
    for index, (object_name, view_name) in enumerate(labels):
        object_index, view_index = divmod(index, view_count)
        name = formatter.format(
            template,
            object=_safe_filename_token(object_name, "current_display"),
            view=_safe_filename_token(view_name, "current_view"),
            object_index=object_index,
            view_index=view_index,
            index=index,
        )
        path = Path(name)
        if (
            path.name != name
            or path.is_absolute()
            or path.suffix.casefold() != ".png"
            or not 1 <= len(name) <= 255
            or any(ord(char) < 32 or char in '<>:"/\\|?*' for char in name)
            or path.stem.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES
            or name.rstrip(" .") != name
        ):
            raise ValueError("Mechanical image File name must produce a local .png filename")
        names.append(name)
    if len(set(os.path.normcase(name) for name in names)) != len(names):
        raise ValueError("mechanical.destination_collision: image File name template produces duplicate destinations")
    return names


def _unsafe_existing_path(path: Path) -> bool:
    try:
        stat = path.lstat()
    except FileNotFoundError:
        return False
    return path.is_symlink() or bool(getattr(stat, "st_file_attributes", 0) & 0x400)


def preflight_image_destinations(
    folder: Path,
    names: list[str],
    *,
    overwrite: bool,
) -> list[Path]:
    folder = Path(folder)
    cursor = folder
    while True:
        if _unsafe_existing_path(cursor):
            raise ValueError("Mechanical image Folder and its ancestors must not be links or reparse points")
        if cursor == cursor.parent:
            break
        cursor = cursor.parent
    folder = folder.resolve(strict=False)
    if folder.exists() and (not folder.is_dir() or _unsafe_existing_path(folder)):
        raise ValueError("Mechanical image Folder must be a normal directory")
    parent = folder if folder.exists() else folder.parent
    if not parent.is_dir() or _unsafe_existing_path(parent):
        raise ValueError("Mechanical image Folder parent must be an existing normal directory")
    paths = [folder / name for name in names]
    if any(path.parent.resolve(strict=False) != folder for path in paths):
        raise ValueError("mechanical.path_escape: image destination escapes Folder")
    for path in paths:
        if _unsafe_existing_path(path) or path.exists() and path.is_dir():
            raise ValueError(f"Mechanical image destination is not a normal file: {path}")
        if path.exists() and not overwrite:
            raise FileExistsError(f"Mechanical image destination already exists: {path}")
    return paths


def publish_image_batch(
    images: list[ImageValue],
    destinations: list[Path],
    *,
    overwrite: bool,
) -> None:
    if len(images) != len(destinations):
        raise ValueError("Mechanical image publication count mismatch")
    if not destinations:
        return
    folder = destinations[0].parent
    folder.mkdir(parents=True, exist_ok=True)
    transaction = Path(tempfile.mkdtemp(prefix=".corex-image-batch-", dir=folder))
    staged = transaction / "staged"
    backups = transaction / "backups"
    staged.mkdir()
    backups.mkdir()
    published: dict[Path, tuple[int, int, int, int, str]] = {}
    backup_paths: dict[Path, Path] = {}
    keep_recovery = False
    try:
        for index, image in enumerate(images):
            path = staged / f"{index}.png"
            with path.open("wb") as stream:
                stream.write(image.encoded_bytes)
                stream.flush()
                os.fsync(stream.fileno())
        preflight_image_destinations(folder, [path.name for path in destinations], overwrite=overwrite)
        for index, destination in enumerate(destinations):
            if destination.exists():
                backup = backups / f"{index}.png"
                os.replace(destination, backup)
                backup_paths[destination] = backup
            source = staged / f"{index}.png"
            source_stat = source.stat()
            receipt = (
                source_stat.st_dev,
                source_stat.st_ino,
                source_stat.st_size,
                source_stat.st_mtime_ns,
                hashlib.sha256(source.read_bytes()).hexdigest(),
            )
            os.link(source, destination)
            published[destination] = receipt
            source.unlink()
            stat = destination.stat()
            current = (
                stat.st_dev,
                stat.st_ino,
                stat.st_size,
                stat.st_mtime_ns,
                hashlib.sha256(destination.read_bytes()).hexdigest(),
            )
            if current != receipt:
                raise RuntimeError("Mechanical image destination changed during publication")
    except BaseException as exc:
        restore_errors = []
        blocked: set[Path] = set()
        for destination, receipt in reversed(list(published.items())):
            try:
                if destination.exists():
                    stat = destination.stat()
                    current = (
                        stat.st_dev,
                        stat.st_ino,
                        stat.st_size,
                        stat.st_mtime_ns,
                        hashlib.sha256(destination.read_bytes()).hexdigest(),
                    )
                    if _unsafe_existing_path(destination) or current != receipt:
                        blocked.add(destination)
                        restore_errors.append(f"preserved externally changed destination {destination}")
                    else:
                        destination.unlink()
            except OSError as error:
                blocked.add(destination)
                restore_errors.append(f"remove {destination}: {error}")
        for destination, backup in reversed(list(backup_paths.items())):
            if destination in blocked:
                continue
            try:
                if backup.exists():
                    if destination.exists():
                        blocked.add(destination)
                        restore_errors.append(f"preserved unexpected destination {destination}")
                    else:
                        os.replace(backup, destination)
            except OSError as error:
                restore_errors.append(f"restore {destination}: {error}")
        if restore_errors:
            keep_recovery = True
            raise RuntimeError(
                f"mechanical.publication_recovery_required: {transaction}; "
                + "; ".join(restore_errors)
            ) from exc
        raise
    finally:
        if not keep_recovery:
            shutil.rmtree(transaction, ignore_errors=True)


def build_image_outputs(
    records: list[Mapping[str, Any]],
    *,
    identity: Mapping[str, Any],
    target_path: tuple[int, ...],
    target_iteration: int,
    file_paths: list[Path],
) -> dict[str, Any]:
    images_by_object: dict[int, list[ImageValue]] = {}
    rows = []
    for ordinal, record in enumerate(records):
        image = record["image"]
        if type(image) is not ImageValue:
            raise TypeError("Mechanical image result contains an invalid image")
        object_index = int(record["object_index"])
        path = target_path + (target_iteration, object_index)
        images_by_object.setdefault(object_index, []).append(image)
        rows.append(
            {
                "object_name": record["object_name"],
                "object_path": record["object_path"],
                "object_id": record["object_id"],
                "view_name": record["view_name"],
                "view_kind": record["view_kind"],
                "view_index": record["view_index"],
                "data_path": json.dumps(list(path), separators=(",", ":")),
                "image_ordinal": ordinal,
                "width": image.width,
                "height": image.height,
                "file_path": str(file_paths[ordinal]) if file_paths else "",
                **identity,
            }
        )
    import pandas as pd

    frame = pd.DataFrame(rows, columns=IMAGE_DETAILS_COLUMNS)
    for column in ("object_id", "view_index"):
        frame[column] = frame[column].astype("Int64")
    for column in ("image_ordinal", "width", "height", "model_revision"):
        frame[column] = frame[column].astype("int64")
    details = snapshot_scientific_value(frame)
    if type(details) is not TableValue:
        raise TypeError("Mechanical image details did not produce TableValue")
    return {
        "images": DataTree(
            (target_path + (target_iteration, index), tuple(values))
            for index, values in sorted(images_by_object.items())
        ),
        "files": [str(path) for path in file_paths],
        "details": details,
    }


def build_camera_views(
    payload: object,
    *,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != {"views"}:
        raise ValueError("Mechanical camera extraction payload is invalid")
    if set(identity) != set(CAMERA_IDENTITY_FIELDS):
        raise ValueError("Mechanical camera identity is invalid")
    raw_views = payload["views"]
    if type(raw_views) is not list:
        raise TypeError("Mechanical camera views must be a list")
    views, rows = [], []
    for raw in raw_views:
        if not isinstance(raw, Mapping) or set(raw) != _RAW_CAMERA_FIELDS:
            raise ValueError("Mechanical camera record schema is invalid")
        item = {**identity, **dict(raw)}
        item["selector_code"] = encode_selector(
            "camera_view",
            document_id=str(identity["document_id"]),
            system_key=str(identity["system_key"]),
            object_path="",
            native_id=raw["index"] if raw["kind"] == "saved" else "current",
        )
        value = camera_view_value(item)
        views.append(value)
        focal = raw["focal_point"] or (None, None, None)
        view = raw["view_vector"] or (None, None, None)
        up = raw["up_vector"] or (None, None, None)
        rows.append(
            {
                "name": raw["name"],
                "kind": raw["kind"],
                "saved_index": raw["index"],
                "focal_x": focal[0],
                "focal_y": focal[1],
                "focal_z": focal[2],
                "view_x": view[0],
                "view_y": view[1],
                "view_z": view[2],
                "up_x": up[0],
                "up_y": up[1],
                "up_z": up[2],
                "scene_width": raw["scene_width"],
                "scene_height": raw["scene_height"],
                "length_unit": raw["length_unit"] or "",
                "availability_notes": json.dumps(
                    raw["availability_notes"],
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                **identity,
                "selector_code": item["selector_code"],
            }
        )
    import pandas as pd

    frame = pd.DataFrame(rows, columns=CAMERA_DETAILS_COLUMNS)
    frame["saved_index"] = frame["saved_index"].astype("Int64")
    frame["model_revision"] = frame["model_revision"].astype("Int64")
    for column in (
        "focal_x",
        "focal_y",
        "focal_z",
        "view_x",
        "view_y",
        "view_z",
        "up_x",
        "up_y",
        "up_z",
        "scene_width",
        "scene_height",
    ):
        frame[column] = frame[column].astype("Float64")
    details = snapshot_scientific_value(frame)
    if type(details) is not TableValue:
        raise TypeError("Mechanical camera details did not produce TableValue")
    return {
        "views": views,
        "names": [str(raw["name"]) for raw in raw_views],
        "details": details,
    }


__all__ = [
    "CAMERA_IDENTITY_FIELDS",
    "CAMERA_DETAILS_COLUMNS",
    "CAMERA_SCRIPT_BODY",
    "IMAGE_CAPTURE_LIMIT",
    "IMAGE_DETAILS_COLUMNS",
    "IMAGE_MAX_PIXELS",
    "IMAGE_PREFLIGHT_SCRIPT_BODY",
    "IMAGE_SCRIPT_BODY",
    "build_image_outputs",
    "build_camera_views",
    "preflight_image_destinations",
    "publish_image_batch",
    "render_image_filenames",
]
