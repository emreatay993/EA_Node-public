# -*- coding: utf-8 -*-
"""
Ansys Mechanical IronPython button script for reaction-force handoff snippets.

Run this from a Mechanical toolbar/button action, or paste it into a Mechanical
Scripting console. It prompts for:

1. A Static or Transient analysis in the Mechanical tree.
2. A named selection from an autocomplete-enabled Windows dropdown.
3. The source load step N after which displacement constraints should be
   converted to nodal forces in load step N+1.

The script then adds the two embedded APDL command snippets:

- source solve/extract block at load step N
- target apply block at load step N+1
"""

import re

try:
    import clr
    clr.AddReference("System.Windows.Forms")
    clr.AddReference("System.Drawing")
    from System.Drawing import Point, Size
    from System.Windows.Forms import (
        AutoCompleteMode,
        AutoCompleteSource,
        Button,
        ComboBox,
        ComboBoxStyle,
        DialogResult,
        Form,
        FormStartPosition,
        Label,
        MessageBox,
        MessageBoxButtons,
        MessageBoxIcon,
        NumericUpDown,
    )
except Exception:
    clr = None

from Ansys.Mechanical.DataModel.Enums import DataModelObjectCategory, SequenceSelectionType


TITLE = "Reaction Force Handoff"
SOURCE_PREP_MACRO_TEXT = r"""! ======================================================================
! Source-step solve/extract block for reaction-to-force handoff
!
! Usage:
!   Place this command snippet in load step N and set the Mechanical command
!   object property "Issue Solve Command" to No. This block solves the source
!   step, extracts the final source-step nodal reactions, and leaves them in
!   APDL memory for the target-step apply block.
! ======================================================================

! ----------------------- USER SETTINGS -------------------------------
RTF_NS_NAME='MY_NAMED_SELECTION'
! --------------------- END USER SETTINGS -----------------------------

/COM,BEGIN reaction_to_force_two_block_source_prep

! This command object is inserted by Mechanical inside /SOLU. Keep it there:
! no FINISH, no /PREP7, no /POST1, and no PARSAV/PARRES are used.

! Remove stale handoff arrays from any previous solve attempt in this session.
RTF_HANDOFF_READY=0
*DEL,RTF_NODE_IDS,,NOPR
*DEL,RTF_FORCE_X,,NOPR
*DEL,RTF_FORCE_Y,,NOPR
*DEL,RTF_FORCE_Z,,NOPR
ALLSEL,ALL

! Resolve the Mechanical named selection to active nodes.
! Node components are used directly. MESH200 element-face components are
! reduced to their attached active nodes. Other component types are rejected.
*GET,RTF_COMP_TYPE,COMP,RTF_NS_NAME,TYPE

*IF,RTF_COMP_TYPE,EQ,1,THEN
  ! Nodal, face, edge, and vertex named selections normally arrive as nodes.
  CMSEL,S,RTF_NS_NAME
*ELSEIF,RTF_COMP_TYPE,EQ,2,THEN
  ! Element-face named selections can arrive as MESH200 elements.
  ESEL,NONE
  CMSEL,S,RTF_NS_NAME
  *GET,RTF_ELEM_COUNT,ELEM,0,COUNT
  *IF,RTF_ELEM_COUNT,LE,0,THEN
    *MSG,ERROR,RTF_ELEM_COUNT
Named selection selected %G elements; expected at least one.
  *ENDIF
  *GET,RTF_FIRST_ELEM,ELEM,0,NUM,MIN
  *GET,RTF_ELEM_TYPE,ELEM,RTF_FIRST_ELEM,ATTR,TYPE
  *GET,RTF_ELEM_NAME,ETYP,RTF_ELEM_TYPE,ATTR,ENAM
  *IF,RTF_ELEM_NAME,NE,200,THEN
    *MSG,ERROR,RTF_ELEM_NAME
Named selection type is incorrect (%G): use face, edge, element face, or nodal.
  *ENDIF
  NSLE,S,ACTIVE
*ELSE
  *MSG,ERROR,RTF_COMP_TYPE
Named selection type is incorrect (%G): use face, edge, element face, or nodal.
*ENDIF

! Save the selected nodes under a stable component name before solving.
*GET,RTF_NODE_COUNT,NODE,0,COUNT
*IF,RTF_NODE_COUNT,LE,0,THEN
  *MSG,ERROR,RTF_NODE_COUNT
Named selection selected %G nodes; expected at least one.
*ENDIF
CM,RTF_SOURCE_NODES,NODE

! Ensure reaction forces are written, then solve the source load step.
! The Mechanical source command object must have IssueSolveCommand = False
! because this APDL block performs the source-step SOLVE itself.
OUTRES,RSOL,ALL
ALLSEL,ALL
SOLVE

! Immediately after SOLVE, RF values belong to the just-completed source step.
! Avoid /POST1 SET here; SET between Mechanical load-step solves can corrupt
! the ramped result timeline in the final RST.
CMSEL,S,RTF_SOURCE_NODES
*GET,RTF_NODE_COUNT,NODE,0,COUNT

*DIM,RTF_NODE_IDS,ARRAY,RTF_NODE_COUNT
*DIM,RTF_FORCE_X,ARRAY,RTF_NODE_COUNT
*DIM,RTF_FORCE_Y,ARRAY,RTF_NODE_COUNT
*DIM,RTF_FORCE_Z,ARRAY,RTF_NODE_COUNT
*VGET,RTF_NODE_IDS(1),NODE,,NLIST

*DO,RTF_INDEX,1,RTF_NODE_COUNT
  RTF_NODE_ID=RTF_NODE_IDS(RTF_INDEX)
  RTF_CURRENT_FX=0
  RTF_CURRENT_FY=0
  RTF_CURRENT_FZ=0
  *GET,RTF_CURRENT_FX,NODE,RTF_NODE_ID,RF,FX
  *GET,RTF_CURRENT_FY,NODE,RTF_NODE_ID,RF,FY
  *GET,RTF_CURRENT_FZ,NODE,RTF_NODE_ID,RF,FZ
  RTF_FORCE_X(RTF_INDEX)=RTF_CURRENT_FX
  RTF_FORCE_Y(RTF_INDEX)=RTF_CURRENT_FY
  RTF_FORCE_Z(RTF_INDEX)=RTF_CURRENT_FZ
*ENDDO

! Mark the in-memory arrays as ready for the target-step command object.
RTF_HANDOFF_READY=1
ALLSEL,ALL
/COM,END reaction_to_force_two_block_source_prep"""

TARGET_APPLY_MACRO_TEXT = r"""! ======================================================================
! Target-step apply block for reaction-to-force handoff
!
! Usage:
!   Place this command snippet in load step N+1 before that step solves.
!   Use reaction_to_force_two_block_source_prep.mac in load step N with
!   the Mechanical command object property "Issue Solve Command" set to No.
!   This block reads the source-step reaction arrays that are still in APDL
!   memory and applies them as nodal forces.
! ======================================================================

! ----------------------- USER SETTINGS -------------------------------
! Kept as a paired source/target setting. The target block uses the node
! IDs saved by the source block rather than re-reading the named selection.
RTF_NS_NAME='MY_NAMED_SELECTION'
RTF_FORCE_SCALE=1.0

RTF_APPLY_FX=1
RTF_APPLY_FY=1
RTF_APPLY_FZ=1

RTF_DELETE_UX=1
RTF_DELETE_UY=1
RTF_DELETE_UZ=1
! --------------------- END USER SETTINGS -----------------------------

/COM,BEGIN reaction_to_force_two_block_target_apply

! This command object is inserted by Mechanical inside /SOLU. Keep it there:
! no FINISH, no /PREP7, no /POST1, and no PARSAV/PARRES are used.
ALLSEL,ALL

! Confirm the source block ran earlier in this same Mechanical solve.
*IF,RTF_HANDOFF_READY,NE,1,THEN
  *MSG,ERROR,RTF_HANDOFF_READY
Saved handoff arrays are not ready (%G). Run the source block in the previous load step.
*ENDIF
*IF,RTF_NODE_COUNT,LE,0,THEN
  *MSG,ERROR,RTF_NODE_COUNT
Saved handoff node count is invalid (%G). Run the source block in the previous load step.
*ENDIF

! Recreate the source-node component from the saved node IDs.
NSEL,NONE
*DO,RTF_INDEX,1,RTF_NODE_COUNT
  RTF_NODE_ID=RTF_NODE_IDS(RTF_INDEX)
  NSEL,A,NODE,,RTF_NODE_ID
*ENDDO
CM,RTF_SOURCE_NODES,NODE
CMSEL,S,RTF_SOURCE_NODES

! Mechanical may emit DDELE,...,FORCE when the original displacement BC is
! deactivated in the target step. That can leave ramped release-force loads
! on these nodes before this snippet applies the explicit replacement forces.
! Displacement constraints and force components are deleted by explicit saved
! node ID immediately before this snippet applies the replacement force value.

! Apply the saved source-step reactions as nodal forces in the target step.
*DO,RTF_INDEX,1,RTF_NODE_COUNT
  RTF_NODE_ID=RTF_NODE_IDS(RTF_INDEX)
  *IF,RTF_DELETE_UX,NE,0,THEN
    DDELE,RTF_NODE_ID,UX
  *ENDIF
  *IF,RTF_DELETE_UY,NE,0,THEN
    DDELE,RTF_NODE_ID,UY
  *ENDIF
  *IF,RTF_DELETE_UZ,NE,0,THEN
    DDELE,RTF_NODE_ID,UZ
  *ENDIF
  *IF,RTF_APPLY_FX,NE,0,THEN
    FDELE,RTF_NODE_ID,FX
    RTF_APPLIED_FX=RTF_FORCE_X(RTF_INDEX)*RTF_FORCE_SCALE
    F,RTF_NODE_ID,FX,RTF_APPLIED_FX
  *ENDIF
  *IF,RTF_APPLY_FY,NE,0,THEN
    FDELE,RTF_NODE_ID,FY
    RTF_APPLIED_FY=RTF_FORCE_Y(RTF_INDEX)*RTF_FORCE_SCALE
    F,RTF_NODE_ID,FY,RTF_APPLIED_FY
  *ENDIF
  *IF,RTF_APPLY_FZ,NE,0,THEN
    FDELE,RTF_NODE_ID,FZ
    RTF_APPLIED_FZ=RTF_FORCE_Z(RTF_INDEX)*RTF_FORCE_SCALE
    F,RTF_NODE_ID,FZ,RTF_APPLIED_FZ
  *ENDIF
*ENDDO

! Step the replacement force at the start of the target load step so the
! source-end state is held rather than ramping the force from zero.
KBC,1
ALLSEL,ALL
/COM,END reaction_to_force_two_block_target_apply"""


def _show(message, icon):
    if clr is None:
        raise RuntimeError(message)
    MessageBox.Show(message, TITLE, MessageBoxButtons.OK, icon)


def _info(message):
    _show(message, MessageBoxIcon.Information)


def _error(message):
    _show(message, MessageBoxIcon.Error)


def _safe_text(value):
    try:
        if value is None:
            return ""
        return str(value)
    except Exception:
        return ""


def _safe_attr(obj, name, default=None):
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _object_name(obj):
    text = _safe_text(_safe_attr(obj, "Name", ""))
    if text:
        return text
    return _safe_text(obj)


def _type_text(obj):
    values = []
    for attr in ("AnalysisType", "PhysicsType", "SolverType"):
        values.append(_safe_text(_safe_attr(obj, attr, "")))
    try:
        values.append(_safe_text(obj.GetType().Name))
        values.append(_safe_text(obj.GetType().FullName))
    except Exception:
        pass
    return " ".join([value for value in values if value])


def _analysis_label(index, analysis):
    name = _object_name(analysis)
    type_text = _type_text(analysis)
    if type_text:
        return "{0}. {1} [{2}]".format(index + 1, name, type_text)
    return "{0}. {1}".format(index + 1, name)


def _is_static_or_transient(analysis):
    text = (_object_name(analysis) + " " + _type_text(analysis)).lower()
    return ("static" in text) or ("transient" in text)


def _model():
    try:
        return ExtAPI.DataModel.Project.Model
    except Exception:
        pass
    try:
        return Model
    except Exception:
        return None


def _data_model():
    try:
        return ExtAPI.DataModel
    except Exception:
        try:
            return DataModel
        except Exception:
            return None


def _iter_children(obj):
    try:
        return list(obj.Children)
    except Exception:
        return []


def _analyses():
    model = _model()
    analyses = []
    try:
        analyses = list(model.Analyses)
    except Exception:
        analyses = []

    if not analyses:
        data_model = _data_model()
        try:
            analyses = list(data_model.Project.Model.Analyses)
        except Exception:
            analyses = []

    supported = []
    for analysis in analyses:
        if _is_static_or_transient(analysis):
            supported.append(analysis)
    return supported


def _named_selections_from_model():
    model = _model()
    result = []
    named_selections = _safe_attr(model, "NamedSelections", None)
    for child in _iter_children(named_selections):
        if _object_name(child):
            result.append(child)
    return result


def _named_selections_from_data_model():
    data_model = _data_model()
    if data_model is None:
        return []
    try:
        return list(data_model.GetObjectsByType(DataModelObjectCategory.NamedSelection))
    except Exception:
        return []


def _named_selections():
    result = []
    seen = set()
    for item in _named_selections_from_model() + _named_selections_from_data_model():
        name = _object_name(item)
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        if _named_selection_is_valid_for_picker(item):
            result.append(item)
    result.sort(key=lambda ns: _object_name(ns).lower())
    return result


def _truthy_false(value):
    text = _safe_text(value).strip().lower()
    return value is False or text == "false" or text == "0"


def _truthy_true(value):
    text = _safe_text(value).strip().lower()
    return value is True or text == "true" or text == "1"


def _zero_total_selection(ns):
    value = _safe_attr(ns, "TotalSelection", None)
    if value is None:
        return False
    text = _safe_text(value).strip()
    match = re.match(r"^0(\D|$)", text)
    if match:
        return True
    try:
        return int(value) == 0
    except Exception:
        return False


def _scope_text(ns):
    fields = []
    for obj in (ns, _safe_attr(ns, "Location", None), _safe_attr(ns, "ScopingDefinition", None)):
        if obj is None:
            continue
        for attr in ("SelectionType", "Type", "ScopingMethod", "GeometrySelection"):
            fields.append(_safe_text(_safe_attr(obj, attr, "")))
    return " ".join([field for field in fields if field]).lower()


def _scope_looks_supported(ns):
    text = _scope_text(ns)
    if not text:
        return True

    supported_terms = ("face", "edge", "node", "nodal", "meshnode", "element face", "elementface")
    rejected_terms = ("body", "assembly", "volume", "area", "line", "keypoint")

    for term in supported_terms:
        if term in text:
            return True
    for term in rejected_terms:
        if term in text:
            return False
    return True


def _named_selection_is_valid_for_picker(ns):
    if _truthy_false(_safe_attr(ns, "SendToSolver", True)):
        return False
    if _truthy_true(_safe_attr(ns, "Suppressed", False)):
        return False
    if _zero_total_selection(ns):
        return False
    return _scope_looks_supported(ns)


def _choose_from_dropdown(title, prompt, items, autocomplete):
    form = Form()
    form.Text = title
    form.StartPosition = FormStartPosition.CenterScreen
    form.Size = Size(640, 155)
    form.MinimizeBox = False
    form.MaximizeBox = False

    label = Label()
    label.Text = prompt
    label.Location = Point(12, 12)
    label.Size = Size(600, 22)

    combo = ComboBox()
    combo.Location = Point(12, 39)
    combo.Size = Size(600, 24)
    combo.DropDownStyle = ComboBoxStyle.DropDown if autocomplete else ComboBoxStyle.DropDownList
    if autocomplete:
        combo.AutoCompleteMode = AutoCompleteMode.SuggestAppend
        combo.AutoCompleteSource = AutoCompleteSource.ListItems
    for label_text in items:
        combo.Items.Add(label_text)
    if items:
        combo.SelectedIndex = 0

    ok_button = Button()
    ok_button.Text = "OK"
    ok_button.Location = Point(432, 78)
    ok_button.Size = Size(90, 28)

    cancel_button = Button()
    cancel_button.Text = "Cancel"
    cancel_button.Location = Point(522, 78)
    cancel_button.Size = Size(90, 28)
    cancel_button.DialogResult = DialogResult.Cancel

    valid = {}
    for item in items:
        valid[item.lower()] = item

    def _ok_clicked(sender, args):
        choice = _safe_text(combo.Text).strip()
        selected = valid.get(choice.lower(), None)
        if selected is None:
            MessageBox.Show(
                "Choose one item from the dropdown list.",
                TITLE,
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning,
            )
            return
        form.Tag = selected
        form.DialogResult = DialogResult.OK
        form.Close()

    ok_button.Click += _ok_clicked
    form.AcceptButton = ok_button
    form.CancelButton = cancel_button
    form.Controls.Add(label)
    form.Controls.Add(combo)
    form.Controls.Add(ok_button)
    form.Controls.Add(cancel_button)

    result = form.ShowDialog()
    if result == DialogResult.OK:
        return _safe_text(form.Tag)
    return None


def _choose_analysis(analyses):
    labels = []
    by_label = {}
    for index, analysis in enumerate(analyses):
        label = _analysis_label(index, analysis)
        labels.append(label)
        by_label[label] = analysis
    choice = _choose_from_dropdown(
        TITLE,
        "Select a Static or Transient analysis from the Mechanical tree:",
        labels,
        False,
    )
    if choice is None:
        return None
    return by_label[choice]


def _choose_named_selection(named_selections):
    labels = []
    by_label = {}
    for named_selection in named_selections:
        label = _object_name(named_selection)
        labels.append(label)
        by_label[label] = named_selection
    choice = _choose_from_dropdown(
        TITLE,
        "Select the named selection to convert from displacement reaction to force:",
        labels,
        True,
    )
    if choice is None:
        return None
    return by_label[choice]


def _number_of_steps(analysis):
    settings = _safe_attr(analysis, "AnalysisSettings", None)
    value = _safe_attr(settings, "NumberOfSteps", None)
    try:
        return int(value)
    except Exception:
        return None


def _choose_source_step(number_of_steps):
    max_source_step = number_of_steps - 1

    form = Form()
    form.Text = TITLE
    form.StartPosition = FormStartPosition.CenterScreen
    form.Size = Size(500, 160)
    form.MinimizeBox = False
    form.MaximizeBox = False

    label = Label()
    label.Text = (
        "Select source load step N. The force-apply snippet will be placed in N+1."
    )
    label.Location = Point(12, 12)
    label.Size = Size(460, 30)

    spinner = NumericUpDown()
    spinner.Location = Point(12, 48)
    spinner.Size = Size(120, 24)
    spinner.Minimum = 1
    spinner.Maximum = max_source_step
    spinner.Value = 1

    range_label = Label()
    range_label.Text = "Allowed: 1 to {0}".format(max_source_step)
    range_label.Location = Point(145, 51)
    range_label.Size = Size(300, 22)

    ok_button = Button()
    ok_button.Text = "OK"
    ok_button.Location = Point(286, 84)
    ok_button.Size = Size(90, 28)

    cancel_button = Button()
    cancel_button.Text = "Cancel"
    cancel_button.Location = Point(376, 84)
    cancel_button.Size = Size(90, 28)
    cancel_button.DialogResult = DialogResult.Cancel

    def _ok_clicked(sender, args):
        form.Tag = int(spinner.Value)
        form.DialogResult = DialogResult.OK
        form.Close()

    ok_button.Click += _ok_clicked
    form.AcceptButton = ok_button
    form.CancelButton = cancel_button
    form.Controls.Add(label)
    form.Controls.Add(spinner)
    form.Controls.Add(range_label)
    form.Controls.Add(ok_button)
    form.Controls.Add(cancel_button)

    result = form.ShowDialog()
    if result == DialogResult.OK:
        return int(form.Tag)
    return None


def _replace_apdl_setting(text, name, value):
    pattern = r"(?m)^{0}\s*=.*$".format(re.escape(name))
    replacement = "{0}={1}".format(name, value)
    return re.sub(pattern, replacement, text)


def _validate_apdl_component_name(name):
    if len(name) > 32:
        raise RuntimeError(
            "The named selection name is {0} characters long. APDL component "
            "character parameters are limited to 32 characters. Rename the named "
            "selection or edit the macro manually.".format(len(name))
        )
    if "'" in name:
        raise RuntimeError("Named selection names used by this button cannot contain a single quote.")
    if "," in name:
        raise RuntimeError("Named selection names used by this button cannot contain a comma.")


def _macro_with_settings(text, named_selection_name, source_step):
    _validate_apdl_component_name(named_selection_name)
    text = _replace_apdl_setting(
        text,
        "RTF_NS_NAME",
        "'{0}'".format(named_selection_name),
    )
    if "RTF_SOURCE_LS=" in text:
        text = _replace_apdl_setting(text, "RTF_SOURCE_LS", _safe_text(source_step))
    return text


def _existing_analysis_child_names(analysis):
    names = set()
    for child in _iter_children(analysis):
        name = _object_name(child)
        if name:
            names.add(name.lower())
    return names


def _unique_name(analysis, base):
    names = _existing_analysis_child_names(analysis)
    if base.lower() not in names:
        return base
    index = 2
    while True:
        candidate = "{0} ({1})".format(base, index)
        if candidate.lower() not in names:
            return candidate
        index += 1


def _configure_command_snippet_step(snippet, load_step):
    snippet.StepSelectionMode = SequenceSelectionType.ByNumber
    snippet.StepNumber = int(load_step)


def _add_command_snippet(analysis, name, input_text, load_step, issue_solve_command):
    add_command_snippet = _safe_attr(analysis, "AddCommandSnippet", None)
    if add_command_snippet is None:
        raise RuntimeError("The selected analysis does not support AddCommandSnippet().")

    snippet = add_command_snippet()
    snippet.Name = _unique_name(analysis, name)
    snippet.Input = input_text
    snippet.IssueSolveCommand = bool(issue_solve_command)
    try:
        snippet.Suppressed = False
    except Exception:
        pass
    _configure_command_snippet_step(snippet, load_step)
    return snippet


def _create_snippets(analysis, named_selection, source_step):
    ns_name = _object_name(named_selection)
    target_step = source_step + 1

    source_text = _macro_with_settings(SOURCE_PREP_MACRO_TEXT, ns_name, source_step)
    target_text = _macro_with_settings(TARGET_APPLY_MACRO_TEXT, ns_name, source_step)

    source_name = "RTF solve-extract - {0} - step {1}".format(ns_name, source_step)
    target_name = "RTF apply - {0} - step {1}".format(ns_name, target_step)

    created = []

    def _work():
        created.append(
            _add_command_snippet(analysis, source_name, source_text, source_step, False)
        )
        created.append(
            _add_command_snippet(analysis, target_name, target_text, target_step, True)
        )

    try:
        with Transaction():
            _work()
    except Exception:
        if created:
            raise
        _work()

    try:
        ExtAPI.DataModel.Tree.Refresh()
    except Exception:
        pass
    return created


def main():
    if clr is None:
        raise RuntimeError("This script must run inside Ansys Mechanical IronPython.")

    analyses = _analyses()
    if not analyses:
        _error("No Static or Transient analysis was found in the Mechanical tree.")
        return

    analysis = _choose_analysis(analyses)
    if analysis is None:
        return

    named_selections = _named_selections()
    if not named_selections:
        _error(
            "No valid named selections were found. Use a face, edge, element-face, "
            "or nodal named selection that is sent to the solver."
        )
        return

    named_selection = _choose_named_selection(named_selections)
    if named_selection is None:
        return

    number_of_steps = _number_of_steps(analysis)
    if number_of_steps is None:
        _error("Could not read Analysis Settings > Number Of Steps for the selected analysis.")
        return
    if number_of_steps < 2:
        _error(
            "This workflow needs at least two load steps. Increase Analysis Settings "
            "> Number Of Steps, then run the button again."
        )
        return

    source_step = _choose_source_step(number_of_steps)
    if source_step is None:
        return

    try:
        _create_snippets(analysis, named_selection, source_step)
    except Exception as exc:
        _error(_safe_text(exc))
        return

    _info(
        "Created reaction-force handoff snippets for '{0}'.\n\n"
        "Solve/extract snippet load step: {1}\n"
        "Apply snippet load step: {2}".format(
            _object_name(named_selection),
            source_step,
            source_step + 1,
        )
    )


main()
