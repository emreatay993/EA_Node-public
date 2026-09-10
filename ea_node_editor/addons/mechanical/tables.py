# Purpose: Extract supported Mechanical definition, result, probe, and worksheet tables.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_definition_tables.py, tests/mechanical_catalogue/test_result_tables.py, tests/mechanical_catalogue/test_worksheet_tables.py

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from ea_node_editor.addons.mechanical.contracts import DEFINITIONS_COLUMNS, definitions_table
from ea_node_editor.runtime_contracts import TableValue
from ea_node_editor.runtime_contracts.scientific_codec import check_scientific_budget
from ea_node_editor.runtime_contracts.scientific_values import (
    SCIENTIFIC_OPERATION_MAX_BYTES,
    SCIENTIFIC_VALUE_MAX_BYTES,
    snapshot_scientific_value,
)

# JSON may escape one accepted UTF-8 label byte as six ASCII bytes. Eight times
# the decoded operation ceiling also covers base64 buffers and JSON structure.
DEFINITION_ENCODED_MAX_BYTES = 8 * SCIENTIFIC_OPERATION_MAX_BYTES


# This body runs inside Mechanical. Keep it compatible with the product's scripting
# engine and detach every native object before returning across the server boundary.
DEFINITION_SCRIPT_BODY = r'''
def _corex_text(value):
    return '' if value is None else str(value)

def _corex_path(value):
    parts=[]
    seen=[]
    while value is not None and id(value) not in seen:
        seen.append(id(value))
        try:name=_corex_text(value.Name).strip()
        except:name=''
        if name:parts.append(name)
        try:value=value.Parent
        except:value=None
    parts.reverse()
    return '/'.join(parts)

def _corex_type(value):
    try:return str(value.GetType().FullName)
    except:return type(value).__name__

def _corex_property_key(prop,index):
    for name in ('APIName','Name'):
        try:value=_corex_text(getattr(prop,name))
        except:value=''
        if value and value != 'None':return value
    return 'property:'+str(index)

def _corex_quantity(value,quantity_name,source_unit):
    if value is None:return {'value':None,'unit':source_unit}
    target=value
    if _corex_data['units']=='si':
        if not quantity_name:
            raise ValueError('mechanical.table_unsupported: SI conversion requires Variable.QuantityName')
        target=value.ConvertToUnitSystem('SI',quantity_name)
    try:magnitude=float(target.Value)
    except AttributeError:
        if type(target) not in (int,float):
            raise ValueError('mechanical.table_unsupported: Field sample is not a Quantity')
        magnitude=float(target)
    unit=source_unit
    try:unit=_corex_text(target.Unit)
    except:pass
    return {'value':magnitude,'unit':unit}

def _corex_variable(variable,role):
    definition=_corex_text(variable.DefinitionType).split('.')[-1]
    formula=''
    if definition=='Formula':
        raw_formula=variable.Formula
        formula='' if raw_formula is None else str(raw_formula)
    unit=_corex_text(variable.Unit)
    quantity_name=_corex_text(variable.QuantityName)
    try:raw_values=list(variable.DiscreteValues or [])
    except TypeError:raw_values=[]
    values=[]
    converted_unit=unit
    for raw_value in raw_values:
        sample=_corex_quantity(raw_value,quantity_name,unit)
        values.append(sample['value'])
        converted_unit=sample['unit']
    if _corex_data['units']=='si' and not raw_values and unit:
        if not quantity_name:
            raise ValueError('mechanical.table_unsupported: SI conversion requires Variable.QuantityName')
        converted_unit=str(Ansys.Core.Units.UnitsManager.GetQuantityUnitForUnitSystem('SI',quantity_name))
    try:declared_count=int(variable.DiscreteValueCount)
    except:declared_count=len(values)
    if definition!='Free' and declared_count != len(values):
        raise ValueError('mechanical.table_unsupported: Variable discrete count does not match its samples')
    return {
        'name':_corex_text(variable.Name),'role':role,
        'definition_type':definition,'formula':formula,'unit':converted_unit,
        'quantity_name':quantity_name,'values':values,
    }

def _corex_enum(value):
    return _corex_text(value).split('.')[-1]

def _corex_si_target(unit,quantity_name,key):
    if quantity_name:
        return _corex_text(Ansys.Core.Units.UnitsManager.GetQuantityUnitForUnitSystem('SI',quantity_name))
    try:
        target=_corex_text(Ansys.Core.Units.UnitsManager.ToComputationalUnitForUnitSystem(unit,'SI',False))
        zero=Ansys.Core.Units.Quantity(0.0,unit).ConvertUnit(target)
    except Exception:
        raise ValueError('mechanical.table_unsupported: SI conversion requires native quantity metadata or an unambiguous source unit for '+key)
    if float(zero.Value)!=0.0:
        raise ValueError('mechanical.table_unsupported: SI conversion requires native quantity metadata for an affine unit column '+key)
    return target

def _corex_native_value(value,key,unit,quantity_name):
    if value is None:return None
    identifier=key in ('Body','Element','Node','Mode','Step','Substep','Result set','Row','Named selection ID')
    if identifier:
        try:number=float(value)
        except:raise ValueError('mechanical.table_unsupported: native identifier is not integral: '+key)
        if number!=number or abs(number)==float('inf') or int(number)!=number:
            raise ValueError('mechanical.table_unsupported: native identifier is not integral: '+key)
        return int(number)
    if type(value) is bool:return value
    if type(value) is str:
        try:number=float(value)
        except:return value
    else:
        try:number=float(value.Value)
        except:
            try:number=float(value)
            except:return _corex_text(value)
    if _corex_data['units']=='si' and unit:
        quantity=value if callable(getattr(value,'ConvertUnit',None)) and hasattr(value,'Value') else Ansys.Core.Units.Quantity(number,unit)
        target=_corex_si_target(unit,quantity_name,key)
        converted=quantity.ConvertToUnitSystem('SI',quantity_name) if quantity_name else quantity.ConvertUnit(target)
        number=float(converted.Value)
    return number

def _corex_itable_column(table,key):
    getter=getattr(table,'get_Item',None)
    return getter(key) if callable(getter) else table[key]

def _corex_itable_record(obj,source_path):
    try:table=obj.TabularData
    except Exception as exc:
        raise ValueError('mechanical.table_unsupported: native ITable is unavailable for '+source_path)
    keys=[_corex_text(value) for value in list(table.Keys)]
    if not keys:
        raise ValueError('mechanical.table_unsupported: native ITable has no columns for '+source_path)
    metadata={}
    for relation,name in (('independent','Independents'),('dependent','Dependents')):
        try:pairs=list(getattr(table,name))
        except Exception as exc:
            raise ValueError('mechanical.table_unsupported: native ITable '+name+' metadata is unavailable')
        for pair in pairs:
            key=_corex_text(pair.Key)
            if key in metadata:raise ValueError('mechanical.table_unsupported: native ITable column relationship is ambiguous: '+key)
            column=pair.Value
            metadata[key]={
                'relation':relation,
                'unit':_corex_text(getattr(column,'Unit','')),
                'quantity_name':_corex_text(getattr(column,'QuantityName','')),
            }
    columns=[]
    for key in keys:
        native=_corex_itable_column(table,key)
        if key not in metadata:raise ValueError('mechanical.table_unsupported: native ITable column relationship is missing: '+key)
        info=metadata[key]
        unit=info['unit'];quantity_name=info['quantity_name']
        converted_unit=unit
        values=[_corex_native_value(value,key,unit,quantity_name) for value in list(native)]
        if _corex_data['units']=='si' and unit:
            converted_unit=_corex_si_target(unit,quantity_name,key)
        columns.append({'key':key,'label':key,'unit':converted_unit,'quantity_name':quantity_name,
                        'definition_kind':'itable_'+info['relation'],'formula':'','values':values,
                        'location':'','coordinate_system':'','notes':'native ITable '+info['relation']})
    lengths=set(len(column['values']) for column in columns)
    if len(lengths)!=1 or not lengths:
        raise ValueError('mechanical.table_unsupported: native ITable columns have unequal row counts; no rows were padded')
    row_count=next(iter(lengths))
    requested=_corex_data.get('sets',[])
    if requested:
        if len(set(requested))!=len(requested) or any(type(value) is bool or int(value)!=value or int(value)<1 or int(value)>row_count for value in requested):
            raise ValueError('mechanical.selector_missing: Rows / sets contains an unavailable native table row')
        indexes=[int(value)-1 for value in requested]
        for column in columns:column['values']=[column['values'][index] for index in indexes]
    return {'kind':'table','table_key':str(int(obj.ObjectId))+':tabular_data','object_path':source_path,
            'property_key':'TabularData','result_set':None,'columns':columns}

def _corex_analysis(obj):
    cursor=obj
    while cursor is not None:
        if callable(getattr(cursor,'GetResultsData',None)):return cursor
        try:cursor=cursor.Parent
        except:cursor=None
    raise ValueError('mechanical.table_unsupported: T08 result adapter requires an owning analysis GetResultsData API for '+_corex_path(obj))

def _corex_stored_sets(obj,require_unique=False):
    analysis=_corex_analysis(obj);reader=None
    try:
        reader=analysis.GetResultsData()
        if reader is None:raise ValueError('mechanical.results_missing: solved result data is unavailable for '+_corex_path(obj))
        values=[float(value) for value in list(reader.ListTimeFreq)]
    except ValueError:raise
    except Exception as exc:
        raise ValueError('mechanical.results_missing: solved result data is unavailable for '+_corex_path(obj))
    finally:
        if reader is not None:
            try:reader.Dispose()
            except:pass
    if not values or any(value!=value or abs(value)==float('inf') for value in values):
        raise ValueError('mechanical.results_missing: stored result sets are missing or invalid for '+_corex_path(obj))
    if require_unique and len(set(values))!=len(values):
        raise ValueError('mechanical.table_unsupported: ForceReaction stored times are ambiguous')
    requested=_corex_data.get('sets',[])
    selected=list(range(1,len(values)+1)) if not requested else list(requested)
    if len(set(selected))!=len(selected) or any(type(value) is bool or int(value)!=value or int(value)<1 or int(value)>len(values) for value in selected):
        raise ValueError('mechanical.selector_missing: Rows / sets contains an unavailable stored-set ID')
    return [(int(index),values[int(index)-1]) for index in selected]

def _corex_display_metadata(obj):
    display=obj.DisplayTime
    unit=_corex_text(getattr(display,'Unit',''))
    quantity_name=_corex_text(getattr(display,'QuantityName',''))
    by_name=_corex_enum(obj.By)
    if not quantity_name and by_name=='Time':quantity_name='Time'
    return display,unit,quantity_name,by_name

def _corex_restore_result(obj,state,set_count):
    errors=[]
    for name,value in (('By',state['by']),('DisplayTime',state['display']),('CalculateTimeHistory',state['history'])):
        try:setattr(obj,name,value)
        except Exception as exc:errors.append((name,type(exc).__name__+': '+str(exc)))
    set_error=''
    try:obj.SetNumber=state['set']
    except Exception as exc:set_error=type(exc).__name__+': '+str(exc)
    current_set=None;exact=False
    try:
        current_set=int(obj.SetNumber)
        exact=(_corex_enum(obj.By)==state['by_name'] and _corex_text(obj.DisplayTime)==state['display_text'] and bool(obj.CalculateTimeHistory)==state['history'])
    except Exception as exc:errors.append(('verification',type(exc).__name__+': '+str(exc)))
    approved=(not errors and exact and state['by_name']=='Time' and state['set']==0 and bool(set_error) and current_set is not None and current_set>0 and current_set<=set_count)
    if errors or not exact or (set_error and not approved) or (not set_error and current_set!=state['set']):
        details='; '.join(name+' '+value for name,value in errors)
        if set_error:details=('; '.join(filter(None,(details,'SetNumber '+set_error))))
        raise ValueError('mechanical.restore_failed: configured result state could not be restored: '+details)
    if approved:
        return 'inactive SetNumber drift approved: before=0; after='+str(current_set)+'; zero restore rejected: '+set_error
    return ''

def _corex_result_state(obj):
    display,unit,quantity_name,by_name=_corex_display_metadata(obj)
    return {'by':obj.By,'by_name':by_name,'display':display,'display_text':_corex_text(display),
            'unit':unit,'quantity_name':quantity_name,'history':bool(obj.CalculateTimeHistory),'set':int(obj.SetNumber)}

def _corex_quantity_sample(value,key):
    unit=_corex_text(getattr(value,'Unit',''))
    quantity_name=_corex_text(getattr(value,'QuantityName',''))
    number=_corex_native_value(value,key,unit,quantity_name)
    if _corex_data['units']=='si' and unit:
        unit=_corex_si_target(unit,quantity_name,key)
    return number,unit,quantity_name

def _corex_configured_history(obj,source_path):
    selected=_corex_stored_sets(obj);state=_corex_result_state(obj);rows=[];note='';failure=None
    try:
        obj.By=Ansys.Mechanical.DataModel.Enums.SetDriverStyle.ResultSet
        obj.CalculateTimeHistory=False
        for set_number,stored in selected:
            obj.SetNumber=set_number
            obj.RetrieveResult()
            if int(obj.SetNumber)!=set_number:
                raise ValueError('mechanical.operation_failed: configured result evaluated a different stored set')
            row={'set':set_number,'stored':stored,'values':[]}
            for key in ('Minimum','Maximum','Average'):
                value=getattr(obj,key)
                sample,unit,quantity_name=_corex_quantity_sample(value,key)
                row['values'].append((key,sample,unit,quantity_name))
            rows.append(row)
    except Exception as exc:failure=exc
    finally:
        note=_corex_restore_result(obj,state,len(selected) if not _corex_data.get('sets') else max(index for index,_stored in selected))
    if failure is not None:
        raise ValueError(str(failure)+(' ; '+note if note else ''))
    time_unit=state['unit'];time_quantity=state['quantity_name']
    converted_time_unit=time_unit
    stored_values=[_corex_native_value(row['stored'],time_quantity or 'Time',time_unit,time_quantity) for row in rows]
    if _corex_data['units']=='si' and time_unit:
        converted_time_unit=_corex_si_target(time_unit,time_quantity,time_quantity or 'Time')
    columns=[
        {'key':'result_set','label':'Result set','unit':'','quantity_name':'','definition_kind':'result_set','formula':'','values':[row['set'] for row in rows],'location':'','coordinate_system':'','notes':note},
        {'key':time_quantity or 'time_frequency','label':time_quantity or 'Time / frequency','unit':converted_time_unit,'quantity_name':time_quantity,'definition_kind':'stored_set_value','formula':'','values':stored_values,'location':'','coordinate_system':'','notes':''},
    ]
    for ordinal,key in enumerate(('Minimum','Maximum','Average')):
        values=[row['values'][ordinal][1] for row in rows];unit=rows[0]['values'][ordinal][2];quantity=rows[0]['values'][ordinal][3]
        columns.append({'key':key.lower(),'label':key,'unit':unit,'quantity_name':quantity,'definition_kind':'result_summary','formula':'','values':values,'location':'','coordinate_system':'','notes':''})
    return {'kind':'table','table_key':str(int(obj.ObjectId))+':configured_summary','object_path':source_path,
            'property_key':'Minimum/Maximum/Average','result_set':None,'columns':columns},note

def _corex_spatial_tables(obj,source_path):
    selected=_corex_stored_sets(obj);state=_corex_result_state(obj);records=[];note='';failure=None
    try:
        obj.By=Ansys.Mechanical.DataModel.Enums.SetDriverStyle.ResultSet
        obj.CalculateTimeHistory=False
        for set_number,stored in selected:
            obj.SetNumber=set_number;obj.RetrieveResult()
            if int(obj.SetNumber)!=set_number:
                raise ValueError('mechanical.operation_failed: PlotData evaluated a different stored set')
            table=obj.PlotData
            key_values=list(table.Keys);keys=[_corex_text(value) for value in key_values]
            if not all(key in keys for key in ('Body','Node','Values')):
                raise ValueError('mechanical.table_unsupported: PlotData requires the qualified Body/Node/Values columns')
            columns=[]
            for key_value in key_values:
                key=_corex_text(key_value);native=_corex_itable_column(table,key_value)
                unit=_corex_text(getattr(native,'Unit',''));quantity=_corex_text(getattr(native,'QuantityName',''))
                converted_unit=unit
                values=[_corex_native_value(value,key,unit,quantity) for value in list(native)]
                if _corex_data['units']=='si' and unit:
                    converted_unit=_corex_si_target(unit,quantity,key)
                kind='spatial_entity_id' if key in ('Body','Element','Node') else 'spatial_value'
                columns.append({'key':key,'label':key,'unit':converted_unit,'quantity_name':quantity,'definition_kind':kind,'formula':'','values':values,'location':key if kind=='spatial_entity_id' else '', 'coordinate_system':'','notes':''})
            records.append({'kind':'table','table_key':str(int(obj.ObjectId))+':plot_data:set:'+str(set_number),'object_path':source_path,
                            'property_key':'PlotData','result_set':set_number,'columns':columns})
    except Exception as exc:failure=exc
    finally:
        note=_corex_restore_result(obj,state,len(selected) if not _corex_data.get('sets') else max(index for index,_stored in selected))
    if failure is not None:
        raise ValueError(str(failure)+(' ; '+note if note else ''))
    if note:
        for record in records:
            if record['columns']:record['columns'][0]['notes']=note
    return records,note

def _corex_probe_context(obj):
    try:scope=obj.BoundaryConditionSelection
    except:scope=None
    scope_name=_corex_text(getattr(scope,'Name',scope))
    try:orientation=obj.Orientation
    except:orientation=None
    coordinate='Solution Coordinate System' if orientation is None else _corex_text(getattr(orientation,'Name',orientation))
    return scope_name,coordinate

def _corex_force_history(obj,source_path):
    selected=_corex_stored_sets(obj,True);display,unit,quantity_name,by_name=_corex_display_metadata(obj)
    if by_name!='Time':raise ValueError('mechanical.table_unsupported: ForceReaction requires By=Time')
    if not unit or (quantity_name and quantity_name!='Time') or (not quantity_name and unit not in ('s','sec','second','seconds')):
        raise ValueError('mechanical.table_unsupported: ForceReaction requires a supported time-driven analysis')
    rows=[];scope,coordinate=_corex_probe_context(obj);before_by=_corex_enum(obj.By)
    try:
        for (set_number,time_value) in selected:
            obj.DisplayTime=Ansys.Core.Units.Quantity(time_value,unit)
            obj.RetrieveResult()
            actual=obj.DisplayTime
            actual_value=float(actual.Value);actual_unit=_corex_text(actual.Unit);actual_quantity=_corex_text(getattr(actual,'QuantityName',''))
            tolerance=1e-12*max(1.0,abs(time_value))
            if abs(actual_value-time_value)>tolerance or actual_unit!=unit or (actual_quantity and actual_quantity!='Time'):
                raise ValueError('mechanical.table_unsupported: ForceReaction did not evaluate the requested stored time')
            values=[]
            for key in ('XAxis','YAxis','ZAxis','Total'):
                sample,out_unit,out_quantity=_corex_quantity_sample(getattr(obj,key),key)
                values.append((key,sample,out_unit,out_quantity))
            rows.append({'set':set_number,'time':time_value,'values':values})
    finally:
        errors=[]
        try:obj.DisplayTime=display
        except Exception as exc:errors.append(type(exc).__name__+': '+str(exc))
        try:
            if _corex_enum(obj.By)!=before_by or _corex_text(obj.DisplayTime)!=_corex_text(display):
                errors.append('By or DisplayTime drifted')
        except Exception as exc:errors.append('verification '+type(exc).__name__+': '+str(exc))
        if errors:raise ValueError('mechanical.restore_failed: ForceReaction state could not be restored: '+'; '.join(errors))
    converted_time_unit=unit
    time_values=[_corex_native_value(row['time'],'Time',unit,'Time') for row in rows]
    if _corex_data['units']=='si' and unit:converted_time_unit=_corex_si_target(unit,'Time','Time')
    columns=[
        {'key':'result_set','label':'Result set','unit':'','quantity_name':'','definition_kind':'result_set','formula':'','values':[row['set'] for row in rows],'location':scope,'coordinate_system':coordinate,'notes':''},
        {'key':'time','label':'Time','unit':converted_time_unit,'quantity_name':'Time','definition_kind':'stored_set_value','formula':'','values':time_values,'location':scope,'coordinate_system':coordinate,'notes':''},
    ]
    for ordinal,key in enumerate(('X','Y','Z','Total')):
        values=[row['values'][ordinal][1] for row in rows];unit_out=rows[0]['values'][ordinal][2];quantity=rows[0]['values'][ordinal][3]
        columns.append({'key':key.lower(),'label':key,'unit':unit_out,'quantity_name':quantity,'definition_kind':'probe_component','formula':'','values':values,'location':scope,'coordinate_system':coordinate,'notes':''})
    return {'kind':'table','table_key':str(int(obj.ObjectId))+':force_reaction','object_path':source_path,
            'property_key':'RetrieveResult','result_set':None,'columns':columns}

def _corex_mesh_worksheet(obj,source_path):
    if _corex_data['units']=='si':
        raise ValueError('mechanical.table_unsupported: mesh-control worksheet has no native Quantity metadata for SI conversion')
    worksheet=obj if _corex_type(obj).endswith('MeshControlWorksheet') else obj.Worksheet
    if not all(callable(getattr(worksheet,name,None)) for name in ('GetActiveState','GetNamedSelection')) or not hasattr(worksheet,'RowCount'):
        raise ValueError('mechanical.table_unsupported: T08 mesh-control worksheet row API is unavailable')
    count=int(worksheet.RowCount)
    if count<=0:raise ValueError('mechanical.table_unsupported: mesh-control worksheet has no rows')
    rows=[];unit_system=_corex_text(ExtAPI.Application.ActiveUnitSystem)
    for index in range(count):
        named=worksheet.GetNamedSelection(index)
        rows.append((index+1,bool(worksheet.GetActiveState(index)),_corex_text(getattr(named,'Name',named)),None if named is None else int(named.ObjectId),unit_system))
    labels=('Row','Active','Named selection','Named selection ID','Unit system')
    values=list(zip(*rows))
    columns=[]
    for index,key in enumerate(labels):
        columns.append({'key':key.lower().replace(' ','_'),'label':key,'unit':'','quantity_name':'','definition_kind':'worksheet_value','formula':'','values':list(values[index]),'location':'','coordinate_system':'','notes':'active unit system: '+unit_system})
    return {'kind':'table','table_key':str(int(obj.ObjectId))+':mesh_worksheet','object_path':source_path,
            'property_key':'Worksheet','result_set':None,'columns':columns}

def _corex_layered_worksheet(obj,source_path):
    if _corex_data['units']=='si':
        raise ValueError('mechanical.table_unsupported: layered-section worksheet has no native Quantity metadata for SI conversion')
    worksheet=obj if _corex_type(obj).endswith('LayeredSectionWorksheet') else obj.Layers
    if not all(callable(getattr(worksheet,name,None)) for name in ('GetMaterial','GetThickness','GetAngle')) or not hasattr(worksheet,'RowCount'):
        raise ValueError('mechanical.table_unsupported: T08 layered-section worksheet row API is unavailable')
    count=int(worksheet.RowCount)
    if count<=0:raise ValueError('mechanical.table_unsupported: layered-section worksheet has no rows')
    unit_system=_corex_text(ExtAPI.Application.ActiveUnitSystem);rows=[]
    for index in range(count):rows.append((index+1,_corex_text(worksheet.GetMaterial(index)),float(worksheet.GetThickness(index)),float(worksheet.GetAngle(index)),unit_system))
    labels=('Row','Material','Thickness','Angle','Unit system');values=list(zip(*rows));columns=[]
    for index,key in enumerate(labels):
        columns.append({'key':key.lower().replace(' ','_'),'label':key,'unit':'','quantity_name':'','definition_kind':'worksheet_value','formula':'','values':list(values[index]),'location':'','coordinate_system':'','notes':'active unit system: '+unit_system+'; native worksheet scalar has no Quantity metadata'})
    return {'kind':'table','table_key':str(int(obj.ObjectId))+':layered_section','object_path':source_path,
            'property_key':'Layers','result_set':None,'columns':columns}

def _corex_presentation_state():
    try:
        active=[int(value.ObjectId) for value in list(Tree.ActiveObjects)]
        camera=Graphics.Camera
        camera_state=[_corex_text(camera.FocalPoint),_corex_text(camera.ViewVector),_corex_text(camera.UpVector),_corex_text(camera.SceneWidth),_corex_text(camera.SceneHeight)]
    except Exception as exc:
        raise ValueError('mechanical.capability_unproved: tree/graphics state is unavailable for guarded table extraction')
    return {'active':active,'camera':camera_state}

def _corex_require_presentation(before):
    try:after=_corex_presentation_state()
    except Exception as exc:
        raise ValueError('mechanical.restore_failed: tree/graphics state could not be verified: '+str(exc))
    if after!=before:
        raise ValueError('mechanical.restore_failed: result extraction changed tree-active objects or graphics state')

def _corex_select_columns(record):
    component=_corex_data['component']
    if component=='all':return record
    keep=[];matched=False
    for column in record['columns']:
        required=(column['definition_kind'] in ('itable_independent','result_set','stored_set_value','spatial_entity_id')
                  or column['key'] in ('Mode','Step','Substep','Result set','Row','row'))
        selected=component in (column['key'],column['label'])
        if required or selected:keep.append(column)
        if selected:matched=True
    if not matched:raise ValueError('mechanical.selector_missing: component is unavailable: '+component)
    record['columns']=keep
    return record

def _corex_fields(obj):
    result=[]
    try:properties=list(obj.VisibleProperties)
    except Exception as exc:
        raise ValueError('mechanical.table_unsupported: visible properties unavailable for '+_corex_path(obj))
    for index,prop in enumerate(properties):
        key=_corex_property_key(prop,index)
        try:internal=getattr(obj,key)
        except:continue
        if internal is None:continue
        try:
            inputs=list(internal.Inputs or [])
            output=internal.Output
        except:continue
        if output is None:continue
        try:caption=_corex_text(prop.Caption)
        except:caption=key
        try:field_name=_corex_text(internal.Name)
        except:field_name=caption
        variables=[]
        for variable in inputs:variables.append(_corex_variable(variable,'independent'))
        variables.append(_corex_variable(output,'dependent'))
        result.append({
            'kind':'field','table_key':str(int(obj.ObjectId))+':'+key+':field',
            'object_path':_corex_path(obj),'property_key':key,
            'property_caption':caption,'component':field_name or caption or key,
            'variables':variables,
        })
    return result

def _corex_step_count(obj,objects):
    cursor=obj
    while cursor is not None:
        try:return int(cursor.AnalysisSettings.NumberOfSteps)
        except:pass
        try:cursor=cursor.Parent
        except:cursor=None
    counts=[]
    for analysis in objects:
        try:count=int(analysis.AnalysisSettings.NumberOfSteps)
        except:continue
        try:active=str(Model.GetActivationStatusForAnalysis(int(obj.ObjectId),int(analysis.ObjectId))).split('.')[-1]=='ObjectActive'
        except:active=False
        if active:counts.append(count)
    if not counts or len(set(counts)) != 1:
        raise ValueError('mechanical.table_unsupported: Bolt pretension step count is unavailable or ambiguous')
    return counts[0]

def _corex_bolt_states(obj,objects):
    count=_corex_step_count(obj,objects)
    states=[]
    for step in range(1,count+1):
        states.append({'step':step,'state':str(obj.GetDefineBy(step)).split('.')[-1]})
    return {
        'kind':'bolt_states','table_key':str(int(obj.ObjectId))+':bolt_step_states',
        'object_path':_corex_path(obj),'property_key':'GetDefineBy',
        'property_caption':'Bolt pretension step states','component':'Step state',
        'states':states,
    }

objects=list(Tree.AllObjects)
objects_by_id={int(value.ObjectId):value for value in objects}
selected=[]
warnings=[]
for source in _corex_data['sources']:
    obj=objects_by_id.get(int(source['object_id']))
    native_path='' if obj is None else _corex_path(obj)
    if obj is None or (native_path != source['object_path'] and not native_path.endswith('/'+source['object_path'])):
        raise ValueError('mechanical.selector_missing: source object is missing or changed: '+source['object_path'])
    api_type=_corex_type(obj);family=_corex_data['family']
    force=api_type.endswith('.ForceReaction');unsupported_probe='.ProbeResults.' in api_type and not force
    result_source='.Results.' in api_type or api_type.endswith('.Solution')
    mesh=api_type.endswith('.MeshControlWorksheet') or api_type.endswith('.MeshControls.Mesh')
    layered=api_type.endswith('.LayeredSectionWorksheet') or api_type.endswith('.LayeredSection')
    candidates=[]
    if family in ('auto','model_definition') and not result_source and not mesh and not layered:
        for value in _corex_fields(obj):
            value['adapter']='definition';candidates.append(value)
        if source['kind']=='property':
            candidates=[value for value in candidates if value['property_key']==source['property_key']]
            if not candidates:
                raise ValueError('mechanical.table_unsupported: property has no supported Field definition: '+source['property_key'])
        elif api_type.endswith('.BoltPretension'):
            value=_corex_bolt_states(obj,objects);value['adapter']='definition';candidates.append(value)
        for value in candidates:value['object_path']=source['object_path']
    if result_source and family in ('auto','result_history_summary'):
        try:native_table=obj.TabularData
        except:native_table=None
        if native_table is not None:
            candidates.append({'adapter':'itable','table_key':str(int(obj.ObjectId))+':tabular_data','object_path':source['object_path'],'property_key':'TabularData','property_caption':'Native table','component':'Native table'})
        if force:
            candidates.append({'adapter':'force','table_key':str(int(obj.ObjectId))+':force_reaction','object_path':source['object_path'],'property_key':'RetrieveResult','property_caption':'Force reaction history','component':'Force reaction'})
        elif not api_type.endswith('.Solution') and not unsupported_probe:
            candidates.append({'adapter':'configured','table_key':str(int(obj.ObjectId))+':configured_summary','object_path':source['object_path'],'property_key':'Minimum/Maximum/Average','property_caption':'Configured result summary','component':'Result summary'})
    if result_source and not force and not unsupported_probe and not api_type.endswith('.Solution') and family in ('auto','spatial_samples'):
        candidates.append({'adapter':'spatial','table_key':str(int(obj.ObjectId))+':plot_data','object_path':source['object_path'],'property_key':'PlotData','property_caption':'Spatial samples','component':'Values'})
    if family in ('auto','supported_worksheet') and mesh:
        candidates.append({'adapter':'mesh','table_key':str(int(obj.ObjectId))+':mesh_worksheet','object_path':source['object_path'],'property_key':'Worksheet','property_caption':'Mesh-control worksheet','component':'Worksheet'})
    if family in ('auto','supported_worksheet') and layered:
        candidates.append({'adapter':'layered','table_key':str(int(obj.ObjectId))+':layered_section','object_path':source['object_path'],'property_key':'Layers','property_caption':'Layered-section worksheet','component':'Worksheet'})
    table_selector=_corex_data['table_selector']
    table_text=_corex_data['table']
    if table_selector is not None:
        candidates=[value for value in candidates if value['table_key']==table_selector['native_id'] and value['object_path']==table_selector['object_path']]
    elif table_text:
        candidates=[value for value in candidates if table_text in (value['table_key'],value['property_key'],value['property_caption'],value['component'])]
    if _corex_data['component']!='all' and candidates and all(value['adapter']=='definition' for value in candidates):
        candidates=[value for value in candidates if _corex_data['component'] in (value['component'],value['property_key'],value['property_caption'])]
        if not candidates:raise ValueError('mechanical.selector_missing: component is unavailable: '+_corex_data['component'])
    if not candidates:
        if not result_source and not mesh and not layered and family in ('auto','model_definition'):
            raise ValueError('mechanical.selector_missing: requested definition table is unavailable for '+source['object_path'])
        raise ValueError('mechanical.table_unsupported: requested table family is unavailable for '+source['object_path']+' ('+api_type+')')
    if family=='auto' and table_selector is None and not table_text and len(candidates)>1 and any(value['adapter']!='definition' for value in candidates):
        candidates=candidates[:1]
    if len(candidates) != 1:
        names=[value['component'] for value in candidates]
        raise ValueError('mechanical.selector_ambiguous: choose Table / property or Component from '+str(names))
    candidate=candidates[0];adapter=candidate['adapter']
    if adapter=='definition':
        candidate.pop('adapter');selected.append(candidate);continue
    if adapter in ('configured','spatial'):
        _corex_analysis(obj)
        if not callable(getattr(obj,'RetrieveResult',None)):
            raise ValueError('mechanical.table_unsupported: T08 result adapter requires RetrieveResult')
    if adapter=='mesh':
        worksheet=obj if api_type.endswith('MeshControlWorksheet') else getattr(obj,'Worksheet',None)
        if worksheet is None or not hasattr(worksheet,'RowCount'):
            raise ValueError('mechanical.table_unsupported: T08 mesh-control worksheet row API is unavailable')
    if adapter=='layered':
        worksheet=obj if api_type.endswith('LayeredSectionWorksheet') else getattr(obj,'Layers',None)
        if worksheet is None or not hasattr(worksheet,'RowCount'):
            raise ValueError('mechanical.table_unsupported: T08 layered-section worksheet row API is unavailable')
    before=_corex_presentation_state();note=''
    try:
        if adapter=='itable':records=[_corex_itable_record(obj,source['object_path'])]
        elif adapter=='configured':
            record,note=_corex_configured_history(obj,source['object_path']);records=[record]
        elif adapter=='spatial':records,note=_corex_spatial_tables(obj,source['object_path'])
        elif adapter=='force':records=[_corex_force_history(obj,source['object_path'])]
        elif adapter=='mesh':records=[_corex_mesh_worksheet(obj,source['object_path'])]
        elif adapter=='layered':records=[_corex_layered_worksheet(obj,source['object_path'])]
        else:raise ValueError('mechanical.table_unsupported: unknown table adapter')
    finally:
        _corex_require_presentation(before)
    if note:warnings.append(note)
    for record in records:selected.append(_corex_select_columns(record))
_corex_json_payload=json.dumps({'schema_version':1,'records':selected,'warnings':warnings},ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
with open(_corex_data['native_output_path'],'wb') as _corex_stream:
    _corex_stream.write(_corex_json_payload)
import hashlib
_corex_receipt=json.dumps({'byte_length':len(_corex_json_payload),'sha256':hashlib.sha256(_corex_json_payload).hexdigest()},separators=(',',':'))
_corex_receipt
'''


def _text(value: Any, label: str, *, empty: bool = True) -> str:
    if type(value) is not str or (not empty and not value):
        raise TypeError(f"{label} must be text")
    if len(value.encode("utf-8")) > 1024 * 1024:
        raise ValueError(f"{label} is too large")
    return value


def _sample(value: Any) -> Any:
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise TypeError("Mechanical definition samples must be finite scalar values or null")


def _heading(name: str, unit: str, *, formula_samples: bool = False) -> str:
    label = name or "Value"
    if formula_samples:
        label += " API samples"
    return f"{label} [{unit}]" if unit else label


def _definition_row(
    *,
    table_index: int,
    column_index: int,
    column_key: str,
    column_label: str,
    unit: str = "",
    quantity_name: str = "",
    definition_kind: str,
    formula: str = "",
    object_path: str,
    property_key: str,
    notes: str = "",
) -> dict[str, Any]:
    return {
        "table_index": table_index,
        "column_index": column_index,
        "column_key": column_key,
        "column_label": column_label,
        "unit": unit,
        "quantity_name": quantity_name,
        "definition_kind": definition_kind,
        "formula": formula,
        "object_path": object_path,
        "property_key": property_key,
        "result_set": None,
        "location": "",
        "coordinate_system": "",
        "notes": notes,
    }


def _variable(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "name", "role", "definition_type", "formula", "unit", "quantity_name", "values"
    }:
        raise TypeError("Mechanical Variable payload schema is invalid")
    result = {key: _text(value[key], f"Variable {key}") for key in (
        "name", "role", "definition_type", "formula", "unit", "quantity_name"
    )}
    if result["role"] not in {"independent", "dependent"}:
        raise ValueError("Mechanical Variable role is invalid")
    if result["definition_type"] not in {"Discrete", "Formula", "Free"}:
        raise ValueError("Mechanical Variable definition type is unsupported")
    if type(value["values"]) is not list:
        raise TypeError("Mechanical Variable values must be a list")
    result["values"] = [_sample(item) for item in value["values"]]
    return result


def _frame_value(frame: Any, *, table_key: str) -> TableValue:
    from ea_node_editor.runtime_contracts import scientific_values

    size = scientific_values._native_scientific_size(frame)
    if size is None:
        raise TypeError("Mechanical definition table must be a pandas DataFrame")
    if size > SCIENTIFIC_VALUE_MAX_BYTES:
        raise ValueError(
            f"mechanical.capacity_exceeded: table {table_key!r} is {size} decoded bytes; "
            "narrow Source, Table / property, or Component"
        )
    value = snapshot_scientific_value(frame)
    if type(value) is not TableValue:
        raise TypeError("Mechanical definition extraction did not produce a TableValue")
    return value


def build_definition_tables(payload: Any) -> dict[str, Any]:
    """Validate detached native records and create full-fidelity immutable values."""
    if not isinstance(payload, Mapping) or set(payload) not in (
        {"schema_version", "records"}, {"schema_version", "records", "warnings"}
    ):
        raise TypeError("Mechanical definition result schema is invalid")
    if payload["schema_version"] != 1 or type(payload["records"]) is not list:
        raise ValueError("Unsupported Mechanical definition result schema")
    warnings = payload.get("warnings", [])
    if type(warnings) is not list or any(type(item) is not str or not item for item in warnings):
        raise TypeError("Mechanical table warnings are invalid")
    import pandas as pd

    tables: list[TableValue] = []
    definitions: list[dict[str, Any]] = []
    for table_index, raw in enumerate(payload["records"]):
        if not isinstance(raw, Mapping):
            raise TypeError("Mechanical definition record must be a mapping")
        kind = raw.get("kind")
        common = {"kind", "table_key", "object_path", "property_key"}
        expected = common | (
            {"property_caption", "component", "variables"} if kind == "field" else
            {"property_caption", "component", "states"} if kind == "bolt_states" else
            {"result_set", "columns"} if kind == "table" else set()
        )
        if not expected or set(raw) != expected:
            raise TypeError("Mechanical definition record schema is invalid")
        table_key, object_path, property_key = (
            _text(raw[name], f"definition {name}", empty=False)
            for name in ("table_key", "object_path", "property_key")
        )
        if kind != "table":
            _text(raw["property_caption"], "definition property_caption")
            _text(raw["component"], "definition component", empty=False)
        columns: list[tuple[str, list[Any]]] = []
        if kind == "field":
            if type(raw["variables"]) is not list or not raw["variables"]:
                raise ValueError("Mechanical Field has no variables")
            variables = [_variable(item) for item in raw["variables"]]
            visible = [item for item in variables if item["role"] == "dependent" or item["values"]]
            populated_lengths = {len(item["values"]) for item in visible if item["values"]}
            if len(populated_lengths) > 1:
                raise ValueError(
                    f"mechanical.table_unsupported: table {table_key!r} has inconsistent "
                    f"populated column lengths {sorted(populated_lengths)}; no rows were padded"
                )
            row_count = next(iter(populated_lengths), 1)
            for column_index, variable in enumerate(visible):
                samples = list(variable["values"])
                definition_type = variable["definition_type"]
                if not samples:
                    if definition_type not in {"Free", "Formula"}:
                        raise ValueError(
                            f"mechanical.table_unsupported: table {table_key!r} has an empty "
                            f"{definition_type} dependent column"
                        )
                    samples = [None] * row_count
                definition_kind = (
                    "free" if definition_type == "Free" else
                    "formula" if definition_type == "Formula" else
                    "tabular" if len(variable["values"]) > 1 else "constant"
                )
                formula_samples = definition_type == "Formula" and bool(variable["values"])
                label = _heading(variable["name"], variable["unit"], formula_samples=formula_samples)
                columns.append((label, samples))
                notes = "independent variable" if variable["role"] == "independent" else ""
                if formula_samples:
                    notes = "; ".join(filter(None, (notes, "API samples; formula retained separately")))
                definitions.append(_definition_row(
                    table_index=table_index, column_index=column_index,
                    column_key=variable["name"], column_label=label,
                    unit=variable["unit"], quantity_name=variable["quantity_name"],
                    definition_kind=definition_kind, formula=variable["formula"],
                    object_path=object_path, property_key=property_key, notes=notes,
                ))
        elif kind == "bolt_states":
            if type(raw["states"]) is not list or not raw["states"]:
                raise ValueError("Bolt pretension has no step states")
            steps, states = [], []
            for item in raw["states"]:
                if not isinstance(item, Mapping) or set(item) != {"step", "state"}:
                    raise TypeError("Bolt pretension state schema is invalid")
                if type(item["step"]) is not int or item["step"] <= 0:
                    raise ValueError("Bolt pretension step must be a positive integer")
                steps.append(item["step"])
                states.append(_text(item["state"], "Bolt pretension state", empty=False))
            columns = [("Step", steps), ("State", states)]
            definitions.extend((
                _definition_row(
                    table_index=table_index, column_index=0, column_key="step",
                    column_label="Step", definition_kind="step_index",
                    object_path=object_path, property_key=property_key,
                ),
                _definition_row(
                    table_index=table_index, column_index=1, column_key="state",
                    column_label="State", definition_kind="bolt_pretension_state",
                    object_path=object_path, property_key=property_key,
                ),
            ))
        else:
            if raw["result_set"] is not None and (
                type(raw["result_set"]) is not int or raw["result_set"] <= 0
            ):
                raise ValueError("Mechanical result_set must be a positive integer or null")
            if type(raw["columns"]) is not list or not raw["columns"]:
                raise ValueError("Mechanical extracted table has no columns")
            generic_fields = {
                "key", "label", "unit", "quantity_name", "definition_kind",
                "formula", "values", "location", "coordinate_system", "notes",
            }
            populated_lengths: set[int] = set()
            checked_columns = []
            for item in raw["columns"]:
                if not isinstance(item, Mapping) or set(item) != generic_fields:
                    raise TypeError("Mechanical extracted column schema is invalid")
                checked = {
                    name: _text(item[name], f"Mechanical column {name}", empty=name not in {"key", "label", "definition_kind"})
                    for name in generic_fields - {"values"}
                }
                if type(item["values"]) is not list:
                    raise TypeError("Mechanical extracted column values must be a list")
                checked["values"] = [_sample(value) for value in item["values"]]
                populated_lengths.add(len(checked["values"]))
                checked_columns.append(checked)
            if len(populated_lengths) != 1:
                raise ValueError(
                    f"mechanical.table_unsupported: table {table_key!r} has inconsistent "
                    f"populated column lengths {sorted(populated_lengths)}; no rows were padded"
                )
            if not next(iter(populated_lengths)):
                raise ValueError(
                    f"mechanical.table_unsupported: table {table_key!r} has no rows"
                )
            for column_index, column in enumerate(checked_columns):
                label = _heading(column["label"], column["unit"])
                columns.append((label, column["values"]))
                definitions.append(_definition_row(
                    table_index=table_index,
                    column_index=column_index,
                    column_key=column["key"],
                    column_label=label,
                    unit=column["unit"],
                    quantity_name=column["quantity_name"],
                    definition_kind=column["definition_kind"],
                    formula=column["formula"],
                    object_path=object_path,
                    property_key=property_key,
                    notes=column["notes"],
                ) | {
                    "result_set": raw["result_set"],
                    "location": column["location"],
                    "coordinate_system": column["coordinate_system"],
                })
        frame = pd.DataFrame({index: values for index, (_label, values) in enumerate(columns)})
        frame.columns = [label for label, _values in columns]
        tables.append(_frame_value(frame, table_key=table_key))
    definitions_frame = pd.DataFrame(definitions, columns=DEFINITIONS_COLUMNS)
    for column in ("table_index", "column_index", "result_set"):
        definitions_frame[column] = definitions_frame[column].astype("Int64")
    from ea_node_editor.runtime_contracts import scientific_values

    definitions_size = scientific_values._native_scientific_size(definitions_frame)
    if definitions_size is None:
        raise TypeError("Mechanical Definitions must be a pandas DataFrame")
    if definitions_size > SCIENTIFIC_VALUE_MAX_BYTES:
        raise ValueError(
            f"mechanical.capacity_exceeded: table 'Definitions' is {definitions_size} decoded bytes; "
            "narrow Source, Table / property, or Component"
        )
    definitions_value = definitions_table(definitions)
    total = sum(value.nbytes for value in (*tables, definitions_value))
    if total > SCIENTIFIC_OPERATION_MAX_BYTES:
        raise ValueError(
            f"mechanical.capacity_exceeded: definition output is {total} decoded bytes; "
            "narrow Source, Table / property, or Component"
        )
    result = {"tables": tables, "definitions": definitions_value}
    check_scientific_budget(result)
    return result


__all__ = [
    "DEFINITION_ENCODED_MAX_BYTES",
    "DEFINITION_SCRIPT_BODY",
    "build_definition_tables",
]
