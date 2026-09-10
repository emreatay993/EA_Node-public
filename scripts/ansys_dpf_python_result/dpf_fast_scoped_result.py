def post_started(sender, analysis):# Do not edit this line
    define_dpf_workflow(analysis)


def _custom_value(path, default):
    try:
        prop = this.GetCustomPropertyByPath(path)
    except:
        return default
    for attr in ('ValueString', 'Value'):
        try:
            value = getattr(prop, attr)
            if value is not None and str(value).strip() != '':
                return str(value).strip()
        except:
            pass
    return default


def _result_label():
    raw = _custom_value('DPF Extraction/Result', 'Total Deformation')
    text = str(raw).strip().lower()
    if text in ('2', '2.0') or 'stress' in text:
        return 'Equivalent Stress'
    if text in ('3', '3.0') or 'strain' in text:
        return 'Equivalent Elastic Strain'
    return 'Total Deformation'


def _requested_location():
    raw = _custom_value('DPF Extraction/Requested Location', 'Nodal')
    text = str(raw).strip().lower().replace(' ', '')
    if text in ('2', '2.0', 'elemental'):
        return 'Elemental'
    if text in ('3', '3.0', 'elementalnodal', 'elemental_nodal'):
        return 'ElementalNodal'
    return 'Nodal'


def _last_set_id(model):
    try:
        return int(model.TimeFreqSupport.NumberSets)
    except:
        return 1


def _parse_set_ids(text, model):
    ids = []
    source = str(text).replace(';', ',')
    last_id = _last_set_id(model)
    for raw in source.split(','):
        part = raw.strip()
        if not part:
            continue
        if part.lower() == 'last':
            ids.append(last_id)
            continue
        if '-' in part:
            pieces = part.split('-', 1)
            try:
                start_text = pieces[0].strip().lower()
                stop_text = pieces[1].strip().lower()
                start = last_id if start_text == 'last' else int(float(start_text))
                stop = last_id if stop_text == 'last' else int(float(stop_text))
                step = 1
                if stop < start:
                    step = -1
                current = start
                while True:
                    ids.append(current)
                    if current == stop:
                        break
                    current += step
            except:
                pass
        else:
            try:
                ids.append(int(float(part)))
            except:
                pass
    if not ids:
        ids = [1]
    unique = []
    for value in ids:
        if value not in unique:
            unique.append(value)
    return unique


def _connect_if_present(operator, pin_name, value):
    try:
        getattr(operator.inputs, pin_name).Connect(value)
        return True
    except:
        return False


def _named_selection_scoping(dpf, data_source, model, name, requested_location):
    clean = str(name).strip()
    if clean == '' or clean.lower() in ('all', 'none', '*'):
        return None, 'all'
    available = []
    try:
        for item in model.AvailableNamedSelections:
            available.append(str(item))
    except:
        available = []
    match = clean
    for item in available:
        if item.upper() == clean.upper():
            match = item
            break
    try:
        ns_op = dpf.operators.scoping.on_named_selection()
        ns_op.inputs.data_sources.Connect(data_source)
        ns_op.inputs.named_selection_name.Connect(match)
        ns_op.inputs.requested_location.Connect(requested_location)
        return ns_op.outputs.mesh_scoping.GetData(), match
    except Exception as exc:
        message = 'DPF Fast Scoped Result: named selection "' + clean + '" was not found in the result file.'
        if available:
            message += ' Available: ' + ', '.join(available[:20])
        try:
            ExtAPI.Application.LogWarning(message)
        except:
            print(message)
        return None, 'all'


def _first_field_count(fields_container, set_ids):
    try:
        field = fields_container[0]
        return len(field.Scoping.Ids)
    except:
        pass
    try:
        field = fields_container.GetFieldByTimeId(set_ids[0])
        return len(field.Scoping.Ids)
    except:
        return -1


def _solution_object(analysis):
    try:
        return analysis.Solution
    except:
        pass
    try:
        for obj in ExtAPI.DataModel.Tree.AllObjects:
            try:
                if str(obj.Name) == 'Solution':
                    return obj
            except:
                pass
    except:
        pass
    return None


def _property_text(obj, name):
    if obj is None:
        return ''
    try:
        value = getattr(obj, name)
        if value is not None:
            return str(value).strip()
    except:
        pass
    return ''


def _rst_in_folder(folder, result_name, checked):
    import os
    if not folder:
        return None
    names = []
    if result_name:
        names.append(result_name)
    if 'file.rst' not in [name.lower() for name in names]:
        names.append('file.rst')
    for name in names:
        candidate = os.path.join(folder, name)
        checked.append(candidate)
        if os.path.isfile(candidate):
            return candidate
    try:
        rst_files = [name for name in os.listdir(folder) if name.lower().endswith('.rst')]
    except:
        rst_files = []
    if len(rst_files) == 1:
        return os.path.join(folder, rst_files[0])
    return None


def _error(message):
    try:
        ExtAPI.Application.LogError(message)
    except:
        try:
            ExtAPI.Application.LogWarning(message)
        except:
            print(message)
    raise Exception(message)


def _result_file_name(analysis):
    import os
    checked = []
    solution = _solution_object(analysis)

    reference_path = _property_text(solution, 'ResultFilePath')
    if reference_path:
        checked.append(reference_path)
        if os.path.isfile(reference_path):
            return reference_path
        _error('DPF Fast Scoped Result: could not find the actual RST file from Solution.ResultFilePath: ' + reference_path)

    result_name = _property_text(solution, 'ResultFileName')
    for attr in ('ResultFileDirectory', 'WorkingDir'):
        rst_path = _rst_in_folder(_property_text(solution, attr), result_name, checked)
        if rst_path:
            return rst_path

    for attr in ('WorkingDir', 'SolverFilesDirectory'):
        rst_path = _rst_in_folder(_property_text(analysis, attr), result_name, checked)
        if rst_path:
            return rst_path

    _error('DPF Fast Scoped Result: could not find the actual RST file. Checked: ' + '; '.join(checked))


def define_dpf_workflow(analysis):
    import time
    import mech_dpf
    import Ans.DataProcessing as dpf

    mech_dpf.setExtAPI(ExtAPI)
    rst_path = _result_file_name(analysis)
    data_source = dpf.DataSources(rst_path)
    model = dpf.Model(data_source)

    named_selection = _custom_value('DPF Extraction/Named Selection', 'NS_BODY_MIDDLE')
    result_label = _result_label()
    requested_location = _requested_location()
    set_ids = _parse_set_ids(_custom_value('DPF Extraction/Time Set IDs', _custom_value('DPF Extraction/Set IDs', 'last')), model)

    time_scoping = dpf.Scoping()
    time_scoping.Ids = set_ids
    scoping_location = requested_location
    if result_label == 'Total Deformation':
        scoping_location = 'Nodal'
    mesh_scoping, scoped_name = _named_selection_scoping(dpf, data_source, model, named_selection, scoping_location)

    if result_label == 'Equivalent Stress':
        base = dpf.operators.result.stress()
        _connect_if_present(base, 'requested_location', requested_location)
        final_op = dpf.operators.invariant.von_mises_eqv_fc()
        final_op.inputs.fields_container.Connect(base.outputs.fields_container)
    elif result_label == 'Equivalent Elastic Strain':
        base = dpf.operators.result.elastic_strain()
        _connect_if_present(base, 'requested_location', requested_location)
        final_op = dpf.operators.invariant.von_mises_eqv_fc()
        final_op.inputs.fields_container.Connect(base.outputs.fields_container)
    else:
        base = dpf.operators.result.displacement()
        final_op = dpf.operators.math.norm_fc()
        final_op.inputs.fields_container.Connect(base.outputs.fields_container)

    base.inputs.data_sources.Connect(data_source)
    _connect_if_present(base, 'time_scoping', time_scoping)
    if mesh_scoping is not None:
        _connect_if_present(base, 'mesh_scoping', mesh_scoping)

    start = time.time()
    try:
        fields = final_op.outputs.fields_container.GetData()
        count = _first_field_count(fields, set_ids)
    except Exception as exc:
        count = -1
        try:
            ExtAPI.Application.LogWarning('DPF Fast Scoped Result: timed fetch failed before contour recording: ' + str(exc))
        except:
            print('DPF Fast Scoped Result timing fetch failed: ' + str(exc))
    elapsed = time.time() - start

    workflow = dpf.Workflow()
    workflow.Add(base)
    workflow.Add(final_op)
    workflow.SetOutputContour(final_op)
    workflow.Record('wf_id', False)
    this.WorkflowId = workflow.GetRecordedId()

    message = 'DPF Fast Scoped Result: {0}; named selection={1}; set ids={2}; location={3}; entities={4}; DPF fetch={5:.4f} s'.format(
        result_label, scoped_name, ','.join([str(i) for i in set_ids]), requested_location, count, elapsed)
    try:
        ExtAPI.Application.LogMessage(message)
    except:
        print(message)
