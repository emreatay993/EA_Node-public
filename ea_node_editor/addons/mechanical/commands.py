# Purpose: Build bounded Mechanical Python and owned APDL snippet mutation payloads.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_scripts.py, tests/mechanical_catalogue/test_snippets.py

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from ea_node_editor.addons.mechanical.contracts import encode_selector, object_value

SCRIPT_ENVIRONMENT_LIMIT = 256
SCRIPT_RECEIPT_TEXT_LIMIT = 1024
SCRIPT_FAILURE_TEXT_LIMIT = 128
SNIPPET_LIMIT = 256
SNIPPET_TEXT_LIMIT = 4096


SCRIPT_PREFLIGHT_BODY = r'''import json
def _corex_path(item):
    parts=[]
    seen=set()
    while item is not None and id(item) not in seen:
        seen.add(id(item))
        name=str(getattr(item,'Name','')).strip()
        if name: parts.append(name)
        item=getattr(item,'Parent',None)
    parts.reverse()
    return '/'.join(parts)
_corex_all=list(Model.Analyses)
_corex_records=[{'id':int(item.ObjectId),'name':str(item.Name),'path':_corex_path(item)} for item in _corex_all]
if len(_corex_records)>256: raise ValueError('mechanical.capacity_exceeded: Script supports at most 256 analyses')
_corex_selected=[]
for selector in _corex_data['environments']:
    if selector['kind']=='typed':
        matches=[row for row in _corex_records if row['id']==selector['object_id']]
    else:
        matches=[row for row in _corex_records if row['path']==selector['text']]
        if not matches: matches=[row for row in _corex_records if row['name']==selector['text']]
    if len(matches)!=1: raise ValueError('mechanical.selector_ambiguous: Environment is unavailable or ambiguous: '+str(selector))
    if matches[0]['id'] not in _corex_selected: _corex_selected.append(matches[0]['id'])
if not _corex_data['environments']: _corex_selected=[row['id'] for row in _corex_records]
else: _corex_selected=[row['id'] for row in _corex_records if row['id'] in _corex_selected]
_corex_payload=json.dumps({'analyses':_corex_records,'selected_ids':_corex_selected},ensure_ascii=False,separators=(',',':')).encode('utf-8')
with open(_corex_data['native_output_path'],'wb') as _corex_stream:_corex_stream.write(_corex_payload)
import hashlib
_corex_receipt=json.dumps({'byte_length':len(_corex_payload),'sha256':hashlib.sha256(_corex_payload).hexdigest()},separators=(',',':'))
_corex_receipt'''


SCRIPT_EXECUTION_BODY = r'''import json,sys,traceback
try:
    unicode
except ImportError:
    pass
except NameError:
    unicode=str
class _CorexBoundedWriter(object):
    def __init__(self,limit):
        self.limit=limit
        self.parts=[]
        self.length=0
    def write(self,value):
        if not isinstance(value,unicode): value=str(value)
        remaining=self.limit-self.length
        if remaining>0:
            value=value[:remaining]
            self.parts.append(value)
            self.length+=len(value)
    def flush(self):
        pass
    def getvalue(self):
        return u''.join(self.parts)
_corex_all=list(Model.Analyses)
_corex_by_id=dict((int(item.ObjectId),item) for item in _corex_all)
_corex_selected=[]
for object_id in _corex_data['selected_ids']:
    if object_id not in _corex_by_id: raise ValueError('mechanical.selector_missing: selected analysis changed after preflight')
    _corex_selected.append(_corex_by_id[object_id])
_corex_invocations=[None] if _corex_data['scope']=='model_once' else list(_corex_selected)
_corex_receipts=[]
_corex_failed=False
for _corex_analysis in _corex_invocations:
    _corex_scope=globals()
    _corex_names=('ExtAPI','DataModel','Model','analyses','analysis','result')
    _corex_missing=[]
    _corex_previous={}
    for _corex_name in _corex_names:
        if _corex_name in _corex_scope: _corex_previous[_corex_name]=_corex_scope[_corex_name]
        else: _corex_missing.append(_corex_name)
    _corex_stdout=_CorexBoundedWriter(1024)
    _corex_old_stdout=sys.stdout
    _corex_error=''
    _corex_result=''
    try:
        _corex_scope['ExtAPI']=ExtAPI
        _corex_scope['DataModel']=DataModel
        _corex_scope['Model']=Model
        _corex_scope['analyses']=list(_corex_selected)
        _corex_scope['analysis']=_corex_analysis
        _corex_scope.pop('result',None)
        sys.stdout=_corex_stdout
        eval(compile(_corex_data['code'],'<COREX Mechanical Script>','exec'),_corex_scope,_corex_scope)
        if 'result' in _corex_scope and _corex_scope['result'] is not None: _corex_result=str(_corex_scope['result'])
    except Exception:
        _corex_error=traceback.format_exc()
        _corex_failed=True
    finally:
        sys.stdout=_corex_old_stdout
        for _corex_name in _corex_names:
            if _corex_name in _corex_previous: _corex_scope[_corex_name]=_corex_previous[_corex_name]
            elif _corex_name in _corex_scope: del _corex_scope[_corex_name]
    _corex_receipts.append({
        'environment_id':None if _corex_analysis is None else int(_corex_analysis.ObjectId),
        'environment_name':'Model' if _corex_analysis is None else str(_corex_analysis.Name),
        'stdout':_corex_stdout.getvalue(),
        'result':_corex_result[:1024],
        'error':_corex_error[:1024],
        'status':'failed' if _corex_error else 'completed',
    })
    if _corex_error and _corex_data['stop_on_error']: break
_corex_payload=json.dumps({'success':not _corex_failed,'receipts':_corex_receipts},ensure_ascii=False,separators=(',',':')).encode('utf-8')
with open(_corex_data['native_output_path'],'wb') as _corex_stream:_corex_stream.write(_corex_payload)
import hashlib
_corex_receipt=json.dumps({'byte_length':len(_corex_payload),'sha256':hashlib.sha256(_corex_payload).hexdigest()},separators=(',',':'))
_corex_receipt'''


SNIPPET_PREFLIGHT_BODY = r'''import json
from System import Enum
try: unicode
except NameError: unicode=str
def _corex_text(value):
    return value if isinstance(value,unicode) else unicode(value)
def _corex_path(item):
    parts=[]
    seen=set()
    while item is not None and id(item) not in seen:
        seen.add(id(item))
        name=_corex_text(getattr(item,'Name','')).strip()
        if name: parts.append(name)
        item=getattr(item,'Parent',None)
    parts.reverse()
    return '/'.join(parts)
def _corex_type(item):
    try: return _corex_text(item.GetType().FullName)
    except Exception: return ''
def _corex_marker(analysis_id,selection):
    return '! COREX_OWNER_V1:'+_corex_data['owner_node_token']+':'+str(analysis_id)+':'+selection
def _corex_snippets(analysis):
    analysis_id=int(analysis.ObjectId)
    return [item for item in list(Tree.AllObjects) if _corex_type(item)=='Ansys.ACT.Automation.Mechanical.CommandSnippet' and getattr(item,'Parent',None) is not None and int(item.Parent.ObjectId)==analysis_id]
def _corex_capability(analysis,mode):
    physics=_corex_text(analysis.PhysicsType)
    analysis_type=_corex_text(analysis.AnalysisType)
    if physics!='Mechanical' or analysis_type!='Static':
        raise ValueError('mechanical.capability_unproved: APDL snippets support only Static Structural analyses; got '+physics+'/'+analysis_type+' at '+_corex_path(analysis))
    settings=analysis.AnalysisSettings
    count=int(settings.NumberOfSteps)
    method=analysis.GetType().GetMethod('AddCommandSnippet')
    if method is None:
        raise ValueError('mechanical.capability_unproved: AddCommandSnippet is unavailable at '+_corex_path(analysis))
    snippet_type=method.ReturnType
    for property_name in ('Name','Input','StepSelectionMode','StepNumber','IssueSolveCommand'):
        prop=snippet_type.GetProperty(property_name)
        if prop is None or not prop.CanWrite:
            raise ValueError('mechanical.capability_unproved: CommandSnippet.'+property_name+' is not writable')
    if snippet_type.GetMethod('Delete') is None:
        raise ValueError('mechanical.capability_unproved: CommandSnippet.Delete is unavailable')
    enum_type=snippet_type.GetProperty('StepSelectionMode').PropertyType
    names=[_corex_text(value) for value in Enum.GetNames(enum_type)]
    if mode not in names:
        raise ValueError('mechanical.capability_unproved: CommandSnippet mode '+mode+' is unavailable')
    return physics,analysis_type,count
_corex_all=list(Model.Analyses)
_corex_records=[{'id':int(item.ObjectId),'name':_corex_text(item.Name),'path':_corex_path(item)} for item in _corex_all]
if len(_corex_records)>256: raise ValueError('mechanical.capacity_exceeded: Snippet supports at most 256 analyses')
_corex_selected=[]
for selector in _corex_data['environments']:
    if selector['kind']=='typed':
        matches=[row for row in _corex_records if row['id']==selector['object_id'] and row['path']==selector['object_path']]
    else:
        matches=[row for row in _corex_records if row['path']==selector['text']]
        if not matches: matches=[row for row in _corex_records if row['name']==selector['text']]
    if len(matches)!=1: raise ValueError('mechanical.selector_ambiguous: Environment is unavailable or ambiguous: '+str(selector))
    if matches[0]['id'] not in _corex_selected: _corex_selected.append(matches[0]['id'])
if not _corex_data['environments']: _corex_selected=[row['id'] for row in _corex_records]
else: _corex_selected=[row['id'] for row in _corex_records if row['id'] in _corex_selected]
_corex_mode='All' if _corex_data['steps']=='all' else 'ByNumber'
_corex_targets=[]
for analysis in _corex_all:
    analysis_id=int(analysis.ObjectId)
    if analysis_id not in _corex_selected: continue
    if not _corex_data['environments'] and (_corex_text(analysis.PhysicsType)!='Mechanical' or _corex_text(analysis.AnalysisType)!='Static'):
        continue
    physics,analysis_type,count=_corex_capability(analysis,_corex_mode)
    requested=[None] if _corex_data['steps']=='all' else list(_corex_data['selected_steps'])
    if any(step is not None and (step<1 or step>count) for step in requested):
        raise ValueError('mechanical.operation_failed: selected load step is outside 1..'+str(count)+' at '+_corex_path(analysis))
    existing=_corex_snippets(analysis)
    entries=[]
    for step in requested:
        selection='all' if step is None else 'step-'+str(step)
        marker=_corex_marker(analysis_id,selection)
        desired=_corex_data['name'] if step is None else _corex_data['name']+u' — Step '+str(step)
        owned=[item for item in existing if _corex_text(item.Input).split('\n',1)[0].rstrip('\r')==marker]
        if len(owned)>1:
            raise ValueError('mechanical.operation_failed: duplicate owned snippets at '+_corex_path(analysis))
        named=[item for item in existing if _corex_text(item.Name)==desired]
        if any(not owned or int(item.ObjectId)!=int(owned[0].ObjectId) for item in named):
            raise ValueError('mechanical.operation_failed: same-name unowned snippet collision at '+_corex_path(named[0]))
        item=owned[0] if owned else None
        if item is not None:
            try:
                _corex_text(item.Name);_corex_text(item.Input);_corex_text(item.StepSelectionMode);int(item.StepNumber);bool(item.IssueSolveCommand)
            except Exception:
                raise ValueError('mechanical.capability_unproved: owned snippet settings are unreadable at '+_corex_path(item))
        entries.append({'selection':selection,'step':step,'name':desired,'marker':marker,'existing_id':None if item is None else int(item.ObjectId),'action':'create' if item is None else 'update'})
    _corex_targets.append({'analysis_id':analysis_id,'analysis_name':_corex_text(analysis.Name),'analysis_path':_corex_path(analysis),'physics_type':physics,'analysis_type':analysis_type,'number_of_steps':count,'entries':entries})
if sum(len(target['entries']) for target in _corex_targets)>256:
    raise ValueError('mechanical.capacity_exceeded: Snippet supports at most 256 command objects per invocation')
if not _corex_targets:
    raise ValueError('mechanical.capability_unproved: no supported Static Structural analysis is available')
_corex_payload=json.dumps({'targets':_corex_targets},ensure_ascii=False,separators=(',',':')).encode('utf-8')
with open(_corex_data['native_output_path'],'wb') as _corex_stream:_corex_stream.write(_corex_payload)
import hashlib
_corex_receipt=json.dumps({'byte_length':len(_corex_payload),'sha256':hashlib.sha256(_corex_payload).hexdigest()},separators=(',',':'))
_corex_receipt'''


SNIPPET_EXECUTION_BODY = r'''import io,json,os,traceback
from System import Enum
try: unicode
except NameError: unicode=str
def _corex_text(value):
    return value if isinstance(value,unicode) else unicode(value)
def _corex_path(item):
    parts=[]
    seen=set()
    while item is not None and id(item) not in seen:
        seen.add(id(item))
        name=_corex_text(getattr(item,'Name','')).strip()
        if name: parts.append(name)
        item=getattr(item,'Parent',None)
    parts.reverse()
    return '/'.join(parts)
def _corex_type(item):
    try: return _corex_text(item.GetType().FullName)
    except Exception: return ''
def _corex_snippets(analysis):
    analysis_id=int(analysis.ObjectId)
    return [item for item in list(Tree.AllObjects) if _corex_type(item)=='Ansys.ACT.Automation.Mechanical.CommandSnippet' and getattr(item,'Parent',None) is not None and int(item.Parent.ObjectId)==analysis_id]
def _corex_capability(analysis,mode):
    if _corex_text(analysis.PhysicsType)!='Mechanical' or _corex_text(analysis.AnalysisType)!='Static':
        raise ValueError('mechanical.capability_unproved: APDL snippets support only Static Structural analyses')
    method=analysis.GetType().GetMethod('AddCommandSnippet')
    if method is None: raise ValueError('mechanical.capability_unproved: AddCommandSnippet is unavailable')
    snippet_type=method.ReturnType
    for property_name in ('Name','Input','StepSelectionMode','StepNumber','IssueSolveCommand'):
        prop=snippet_type.GetProperty(property_name)
        if prop is None or not prop.CanWrite: raise ValueError('mechanical.capability_unproved: CommandSnippet.'+property_name+' is not writable')
    if snippet_type.GetMethod('Delete') is None: raise ValueError('mechanical.capability_unproved: CommandSnippet.Delete is unavailable')
    enum_type=snippet_type.GetProperty('StepSelectionMode').PropertyType
    if mode not in [_corex_text(value) for value in Enum.GetNames(enum_type)]:
        raise ValueError('mechanical.capability_unproved: CommandSnippet mode '+mode+' is unavailable')
def _corex_restore(snapshot):
    item=snapshot['item']
    item.Name=snapshot['name']
    item.Input=snapshot['input']
    item.StepSelectionMode=Enum.Parse(item.StepSelectionMode.GetType(),snapshot['mode'])
    item.StepNumber=snapshot['step_number']
    item.IssueSolveCommand=snapshot['issue_solve']
    if _corex_text(item.Name)!=snapshot['name'] or _corex_text(item.Input)!=snapshot['input'] or _corex_text(item.StepSelectionMode)!=snapshot['mode'] or int(item.StepNumber)!=snapshot['step_number'] or bool(item.IssueSolveCommand)!=snapshot['issue_solve']:
        raise RuntimeError('updated snippet restoration mismatch')
def _corex_persist_rollback():
    payload={'updates':[],'created':list(_corex_created_records)}
    for snapshot in _corex_updates:
        payload['updates'].append({'id':int(snapshot['item'].ObjectId),'name':snapshot['name'],'input':snapshot['input'],'mode':snapshot['mode'],'step_number':snapshot['step_number'],'issue_solve':snapshot['issue_solve']})
    with io.open(_corex_data['rollback_path'],'w',encoding='utf-8') as stream:
        stream.write(json.dumps(payload,ensure_ascii=False,separators=(',',':')))
_corex_by_id=dict((int(item.ObjectId),item) for item in list(Model.Analyses))
_corex_resolved=[]
for target in _corex_data['plan']['targets']:
    analysis_id=target['analysis_id']
    if analysis_id not in _corex_by_id: raise ValueError('mechanical.selector_missing: selected analysis changed after preflight')
    analysis=_corex_by_id[analysis_id]
    existing=_corex_snippets(analysis)
    for entry in target['entries']:
        mode='All' if entry['step'] is None else 'ByNumber'
        _corex_capability(analysis,mode)
        if entry['step'] is not None and (entry['step']<1 or entry['step']>int(analysis.AnalysisSettings.NumberOfSteps)):
            raise ValueError('mechanical.operation_failed: selected load step changed after preflight')
        owned=[item for item in existing if _corex_text(item.Input).split('\n',1)[0].rstrip('\r')==entry['marker']]
        named=[item for item in existing if _corex_text(item.Name)==entry['name']]
        if len(owned)>1 or any(not owned or int(item.ObjectId)!=int(owned[0].ObjectId) for item in named):
            raise ValueError('mechanical.operation_failed: snippet ownership or name collision changed after preflight')
        actual_id=None if not owned else int(owned[0].ObjectId)
        if actual_id!=entry['existing_id']:
            raise ValueError('mechanical.operation_failed: snippet ownership changed after preflight')
        _corex_resolved.append((analysis,target,entry,None if not owned else owned[0]))
_corex_updates=[]
for analysis,target,entry,item in _corex_resolved:
    if item is not None:
        _corex_updates.append({'item':item,'name':_corex_text(item.Name),'input':_corex_text(item.Input),'mode':_corex_text(item.StepSelectionMode),'step_number':int(item.StepNumber),'issue_solve':bool(item.IssueSolveCommand)})
_corex_created=[]
_corex_created_records=[]
_corex_receipts=[]
_corex_objects=[]
_corex_persist_rollback()
try:
    for analysis,target,entry,item in _corex_resolved:
        if item is None:
            item=analysis.AddCommandSnippet()
            _corex_created.append(item)
            _corex_created_records.append({'id':int(item.ObjectId),'marker':entry['marker']})
            _corex_persist_rollback()
        item.Name=entry['name']
        item.Input=entry['marker']+'\n'+_corex_data['commands']
        item.StepSelectionMode=Enum.Parse(item.StepSelectionMode.GetType(),'All' if entry['step'] is None else 'ByNumber')
        if entry['step'] is not None: item.StepNumber=entry['step']
        item.IssueSolveCommand=_corex_data['issue_solve_command']
        if _corex_text(item.Name)!=entry['name'] or _corex_text(item.Input)!=entry['marker']+'\n'+_corex_data['commands'] or _corex_text(item.StepSelectionMode)!=('All' if entry['step'] is None else 'ByNumber') or (entry['step'] is not None and int(item.StepNumber)!=entry['step']) or bool(item.IssueSolveCommand)!=_corex_data['issue_solve_command']:
            raise RuntimeError('snippet setting verification failed')
        category=''
        try: category=_corex_text(item.DataModelObjectCategory)
        except Exception: pass
        _corex_objects.append({'object_id':int(item.ObjectId),'parent_id':int(analysis.ObjectId),'analysis_id':int(analysis.ObjectId),'object_path':_corex_path(item),'display_name':_corex_text(item.Name),'api_type':_corex_type(item),'category':category})
        _corex_receipts.append({'analysis_id':int(analysis.ObjectId),'analysis_name':_corex_text(analysis.Name),'step_selection':entry['selection'],'step_number':entry['step'],'snippet_id':int(item.ObjectId),'snippet_name':_corex_text(item.Name),'action':entry['action'],'status':'completed','message':''})
    _corex_payload={'success':True,'rollback_verified':True,'error':'','receipts':_corex_receipts,'snippets':_corex_objects}
except Exception:
    _corex_original=traceback.format_exc()[:4096]
    _corex_restore_errors=[]
    for snapshot in reversed(_corex_updates):
        try: _corex_restore(snapshot)
        except Exception: _corex_restore_errors.append(traceback.format_exc()[:1024])
    _corex_created_ids=[int(item.ObjectId) for item in _corex_created]
    for item in reversed(_corex_created):
        try: item.Delete()
        except Exception: _corex_restore_errors.append(traceback.format_exc()[:1024])
    _corex_remaining=set(int(item.ObjectId) for item in list(Tree.AllObjects))
    if any(object_id in _corex_remaining for object_id in _corex_created_ids):
        _corex_restore_errors.append('newly created snippet remains after rollback')
    if _corex_restore_errors:
        raise RuntimeError('mechanical.restore_failed: '+_corex_original+'; '+'; '.join(_corex_restore_errors))
    try:
        if os.path.exists(_corex_data['rollback_path']): os.remove(_corex_data['rollback_path'])
    except Exception: pass
    _corex_payload={'success':False,'rollback_verified':True,'error':_corex_original,'receipts':[],'snippets':[]}
_corex_encoded=json.dumps(_corex_payload,ensure_ascii=False,separators=(',',':')).encode('utf-8')
with open(_corex_data['native_output_path'],'wb') as _corex_stream:_corex_stream.write(_corex_encoded)
import hashlib
_corex_receipt=json.dumps({'byte_length':len(_corex_encoded),'sha256':hashlib.sha256(_corex_encoded).hexdigest()},separators=(',',':'))
_corex_receipt'''


SNIPPET_ROLLBACK_BODY = r'''import io,json,os,traceback
from System import Enum
try: unicode
except NameError: unicode=str
def _corex_text(value):
    return value if isinstance(value,unicode) else unicode(value)
with io.open(_corex_data['rollback_path'],'r',encoding='utf-8') as stream:
    _corex_rollback=json.loads(stream.read())
_corex_by_id=dict((int(item.ObjectId),item) for item in list(Tree.AllObjects))
_corex_errors=[]
for snapshot in reversed(_corex_rollback['updates']):
    try:
        if snapshot['id'] not in _corex_by_id: raise RuntimeError('updated snippet is unavailable')
        item=_corex_by_id[snapshot['id']]
        item.Name=snapshot['name']
        item.Input=snapshot['input']
        item.StepSelectionMode=Enum.Parse(item.StepSelectionMode.GetType(),snapshot['mode'])
        item.StepNumber=snapshot['step_number']
        item.IssueSolveCommand=snapshot['issue_solve']
        if _corex_text(item.Name)!=snapshot['name'] or _corex_text(item.Input)!=snapshot['input'] or _corex_text(item.StepSelectionMode)!=snapshot['mode'] or int(item.StepNumber)!=snapshot['step_number'] or bool(item.IssueSolveCommand)!=snapshot['issue_solve']:
            raise RuntimeError('updated snippet restoration mismatch')
    except Exception: _corex_errors.append(traceback.format_exc()[:1024])
for created in reversed(_corex_rollback['created']):
    try:
        if created['id'] not in _corex_by_id: continue
        item=_corex_by_id[created['id']]
        if _corex_text(item.Input).split('\n',1)[0].rstrip('\r')!=created['marker']:
            raise RuntimeError('created snippet ownership marker changed')
        item.Delete()
    except Exception: _corex_errors.append(traceback.format_exc()[:1024])
_corex_remaining=set(int(item.ObjectId) for item in list(Tree.AllObjects))
if any(created['id'] in _corex_remaining for created in _corex_rollback['created']):
    _corex_errors.append('newly created snippet remains after rollback')
if _corex_errors: raise RuntimeError('mechanical.restore_failed: '+'; '.join(_corex_errors))
if os.path.exists(_corex_data['rollback_path']): os.remove(_corex_data['rollback_path'])
if os.path.exists(_corex_data['rollback_path']): raise RuntimeError('mechanical.restore_failed: rollback record remains')
_corex_receipt=json.dumps({'restored':True})
_corex_receipt'''


def validate_script_payload(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"success", "receipts"}:
        raise RuntimeError("Mechanical script returned an invalid receipt")
    if type(value["success"]) is not bool or type(value["receipts"]) is not list:
        raise RuntimeError("Mechanical script returned invalid receipt fields")
    receipts: list[dict[str, Any]] = []
    required = {
        "environment_id",
        "environment_name",
        "stdout",
        "result",
        "error",
        "status",
    }
    for receipt in value["receipts"]:
        if not isinstance(receipt, Mapping) or set(receipt) != required:
            raise RuntimeError("Mechanical script receipt schema is invalid")
        normalized = dict(receipt)
        if (
            normalized["environment_id"] is not None
            and (type(normalized["environment_id"]) is not int or normalized["environment_id"] < 0)
        ):
            raise RuntimeError("Mechanical script environment identity is invalid")
        if normalized["status"] not in {"completed", "failed"}:
            raise RuntimeError("Mechanical script receipt status is invalid")
        for field in ("environment_name", "stdout", "result", "error"):
            if type(normalized[field]) is not str or len(normalized[field]) > SCRIPT_RECEIPT_TEXT_LIMIT:
                raise RuntimeError("Mechanical script receipt text is invalid")
        receipts.append(normalized)
    if len(receipts) > SCRIPT_ENVIRONMENT_LIMIT:
        raise RuntimeError("Mechanical script returned too many receipts")
    if value["success"] != all(row["status"] == "completed" for row in receipts):
        raise RuntimeError("Mechanical script success status does not match its receipts")
    return {"success": value["success"], "receipts": receipts}


def receipt_messages(receipts: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "status": str(receipt["status"]),
            "message": json.dumps(dict(receipt), ensure_ascii=False, separators=(",", ":")),
        }
        for receipt in receipts
    ]


def compact_failure_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    checked = validate_script_payload(value)
    receipts = [
        {
            **receipt,
            **{
                field: receipt[field][:SCRIPT_FAILURE_TEXT_LIMIT]
                for field in ("environment_name", "stdout", "result", "error")
            },
        }
        for receipt in checked["receipts"]
    ]
    compact = {"success": False, "receipts": receipts}
    if len(json.dumps(compact, ensure_ascii=True, separators=(",", ":")).encode()) >= 1024 * 1024:
        raise RuntimeError("Mechanical script failure diagnostics exceed the owner envelope")
    return compact


def validate_snippet_preflight(
    value: object,
    *,
    owner_node_token: str,
    name: str,
    steps: str,
    selected_steps: Sequence[int],
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"targets"} or type(value["targets"]) is not list:
        raise RuntimeError("Mechanical snippet preflight returned an invalid result")
    targets: list[dict[str, Any]] = []
    seen_analyses: set[int] = set()
    count = 0
    expected_steps = [None] if steps == "all" else list(selected_steps)
    for target in value["targets"]:
        required = {
            "analysis_id", "analysis_name", "analysis_path", "physics_type",
            "analysis_type", "number_of_steps", "entries",
        }
        if not isinstance(target, Mapping) or set(target) != required:
            raise RuntimeError("Mechanical snippet target schema is invalid")
        normalized = dict(target)
        analysis_id = normalized["analysis_id"]
        if (
            type(analysis_id) is not int
            or analysis_id < 0
            or analysis_id in seen_analyses
            or type(normalized["number_of_steps"]) is not int
            or normalized["number_of_steps"] < 1
            or normalized["physics_type"] != "Mechanical"
            or normalized["analysis_type"] != "Static"
            or type(normalized["entries"]) is not list
            or any(type(normalized[field]) is not str or len(normalized[field]) > SNIPPET_TEXT_LIMIT for field in ("analysis_name", "analysis_path"))
        ):
            raise RuntimeError("Mechanical snippet target identity or phase is invalid")
        seen_analyses.add(analysis_id)
        entries: list[dict[str, Any]] = []
        for index, entry in enumerate(normalized["entries"]):
            fields = {"selection", "step", "name", "marker", "existing_id", "action"}
            if not isinstance(entry, Mapping) or set(entry) != fields:
                raise RuntimeError("Mechanical snippet plan entry schema is invalid")
            row = dict(entry)
            expected_step = expected_steps[index] if index < len(expected_steps) else object()
            selection = "all" if expected_step is None else f"step-{expected_step}"
            marker = f"! COREX_OWNER_V1:{owner_node_token}:{analysis_id}:{selection}"
            expected_name = name if expected_step is None else f"{name} — Step {expected_step}"
            if (
                row["step"] != expected_step
                or row["selection"] != selection
                or row["marker"] != marker
                or row["name"] != expected_name
                or row["action"] not in {"create", "update"}
                or (row["existing_id"] is not None and (type(row["existing_id"]) is not int or row["existing_id"] < 0))
                or (row["action"] == "create") != (row["existing_id"] is None)
                or (row["step"] is not None and row["step"] > normalized["number_of_steps"])
            ):
                raise RuntimeError("Mechanical snippet plan entry is inconsistent")
            entries.append(row)
        if len(entries) != len(expected_steps):
            raise RuntimeError("Mechanical snippet plan does not contain every requested load step")
        normalized["entries"] = entries
        targets.append(normalized)
        count += len(entries)
    if not targets or count > SNIPPET_LIMIT:
        raise RuntimeError("Mechanical snippet preflight target count is invalid")
    return {"targets": targets}


def validate_snippet_payload(value: object, plan: Mapping[str, Any]) -> dict[str, Any]:
    required = {"success", "rollback_verified", "error", "receipts", "snippets"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise RuntimeError("Mechanical snippet returned an invalid receipt")
    if (
        type(value["success"]) is not bool
        or type(value["rollback_verified"]) is not bool
        or type(value["error"]) is not str
        or len(value["error"]) > SNIPPET_TEXT_LIMIT
        or type(value["receipts"]) is not list
        or type(value["snippets"]) is not list
    ):
        raise RuntimeError("Mechanical snippet receipt fields are invalid")
    expected_entries = [
        (target, entry)
        for target in plan["targets"]
        for entry in target["entries"]
    ]
    if not value["success"]:
        if not value["rollback_verified"] or not value["error"] or value["receipts"] or value["snippets"]:
            raise RuntimeError("Mechanical snippet failure receipt is invalid")
        return dict(value)
    if value["error"] or len(value["receipts"]) != len(expected_entries) or len(value["snippets"]) != len(expected_entries):
        raise RuntimeError("Mechanical snippet success receipt count is invalid")
    receipts: list[dict[str, Any]] = []
    snippets: list[dict[str, Any]] = []
    for (target, entry), receipt, snippet in zip(expected_entries, value["receipts"], value["snippets"], strict=True):
        receipt_fields = {
            "analysis_id", "analysis_name", "step_selection", "step_number",
            "snippet_id", "snippet_name", "action", "status", "message",
        }
        snippet_fields = {
            "object_id", "parent_id", "analysis_id", "object_path",
            "display_name", "api_type", "category",
        }
        if not isinstance(receipt, Mapping) or set(receipt) != receipt_fields:
            raise RuntimeError("Mechanical snippet operation receipt schema is invalid")
        if not isinstance(snippet, Mapping) or set(snippet) != snippet_fields:
            raise RuntimeError("Mechanical snippet object receipt schema is invalid")
        receipt, snippet = dict(receipt), dict(snippet)
        if (
            receipt["analysis_id"] != target["analysis_id"]
            or receipt["analysis_name"] != target["analysis_name"]
            or receipt["step_selection"] != entry["selection"]
            or receipt["step_number"] != entry["step"]
            or receipt["snippet_name"] != entry["name"]
            or receipt["action"] != entry["action"]
            or receipt["status"] != "completed"
            or receipt["message"]
            or type(receipt["snippet_id"]) is not int
            or receipt["snippet_id"] < 0
            or snippet["object_id"] != receipt["snippet_id"]
            or snippet["parent_id"] != target["analysis_id"]
            or snippet["analysis_id"] != target["analysis_id"]
            or snippet["display_name"] != entry["name"]
            or any(type(snippet[field]) is not str or len(snippet[field]) > SNIPPET_TEXT_LIMIT for field in ("object_path", "display_name", "api_type", "category"))
        ):
            raise RuntimeError("Mechanical snippet receipt does not match its preflight plan")
        receipts.append(receipt)
        snippets.append(snippet)
    return {"success": True, "rollback_verified": True, "error": "", "receipts": receipts, "snippets": snippets}


def snippet_receipt_messages(receipts: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "status": str(receipt["action"]),
            "message": json.dumps(dict(receipt), ensure_ascii=False, separators=(",", ":")),
        }
        for receipt in receipts
    ]


def snippet_object_values(
    records: Sequence[Mapping[str, Any]], identity: Mapping[str, Any]
) -> list[Any]:
    values = []
    for record in records:
        values.append(object_value({
            **{
                field: identity[field]
                for field in (
                    "run_id", "session_id", "document_id", "source_key",
                    "system_key", "model_revision",
                )
            },
            **dict(record),
            "selector_code": encode_selector(
                "object",
                document_id=identity["document_id"],
                system_key=identity["system_key"],
                object_path=record["object_path"],
                native_id=record["object_id"],
            ),
        }))
    return values


__all__ = [
    "SCRIPT_ENVIRONMENT_LIMIT",
    "SCRIPT_EXECUTION_BODY",
    "SCRIPT_FAILURE_TEXT_LIMIT",
    "SCRIPT_PREFLIGHT_BODY",
    "SNIPPET_EXECUTION_BODY",
    "SNIPPET_LIMIT",
    "SNIPPET_PREFLIGHT_BODY",
    "SNIPPET_ROLLBACK_BODY",
    "SNIPPET_TEXT_LIMIT",
    "compact_failure_payload",
    "receipt_messages",
    "snippet_object_values",
    "snippet_receipt_messages",
    "validate_script_payload",
    "validate_snippet_payload",
    "validate_snippet_preflight",
]
