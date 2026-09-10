# Purpose: Hold inert decorated Mechanical Open, read, graphics, mutation, and save declarations.
# Map: subsystems/addons.md
# Tests: tests/mechanical_catalogue/test_catalogue.py, tests/mechanical_catalogue/test_controls.py, tests/mechanical_catalogue/test_visuals.py, tests/mechanical_catalogue/test_search_tree.py, tests/mechanical_catalogue/test_definition_tables.py, tests/mechanical_catalogue/test_image_export.py, tests/mechanical_catalogue/test_scripts.py, tests/mechanical_catalogue/test_snippets.py, tests/mechanical_catalogue/test_standalone_save.py, tests/mechanical_catalogue/test_workbench_save.py, tests/mechanical_catalogue/test_workbench_model_export.py

SOURCE = r'''import corex
from ea_node_editor.addons.mechanical.runtime import execute_open_model
from ea_node_editor.addons.mechanical.runtime import execute_search_tree
from ea_node_editor.addons.mechanical.runtime import execute_fea_table
from ea_node_editor.addons.mechanical.runtime import execute_camera_views
from ea_node_editor.addons.mechanical.runtime import execute_image_export
from ea_node_editor.addons.mechanical.runtime import execute_run_script
from ea_node_editor.addons.mechanical.runtime import execute_apdl_snippet
from ea_node_editor.addons.mechanical.runtime import execute_save_model

@corex.node(
    id="mechanical.open_model", name="Open Mechanical Model",
    category=("FEA", "ANSYS", "Mechanical"),
    icon="mechanical/open.svg",
    description="Opens a fresh isolated Mechanical model for this run. Interactive sessions are inspection-only after completion.",
    keywords=("mechanical", "ansys", "model", "open"),
    _default_expanded_settings_group_ids=("open_options",),
    _solution_reuse_scope="never",
)
@corex.path("file", default="", label="File", port=True,
    section="Open options", _section_order=0,
    file_filter="Mechanical (*.mechdat *.mechdb *.mechpz *.wbpj *.wbpz);;All Files (*)",
    _inspector_editor="path", _property_group="Open options",
    _port_value_type="COREX.DataTypes.Path", _port_required=True,
    _port_description="Standalone Mechanical file or native Mechanical/Workbench archive or project.")
@corex.text("system", default="", label="Model / system", port=True,
    section="Open options", _section_order=1,
    _inspector_editor="text", _property_group="Open options",
    _port_value_type="COREX.DataTypes.String", _port_required=False,
    _port_description="Stable Workbench Model/system selector; empty selects the sole distinct model.")
@corex.dropdown("mode", default="background", options=("background", "interactive"), label="Mode", port=True,
    section="Open options", _section_order=2,
    _inspector_editor="enum", _property_group="Open options",
    _port_value_type="COREX.DataTypes.String", _port_description="Background owner or real interactive editor.")
@corex.dropdown("version", default=0, options=("Auto · 2026 R1 or newer", "2026 R1 (261)"), codes=(0, 261), label="Version", port=True,
    section="Open options", _section_order=3,
    _inspector_editor="enum", _property_group="Open options", _property_type="int",
    _port_value_type="COREX.DataTypes.Int", _port_description="0 selects the newest installed Mechanical release 261 or newer.")
@corex.path("working_folder", default="", label="Working folder", port=True,
    section="Session options", _section_order=0,
    _inspector_editor="path", _property_group="Session options",
    _port_value_type="COREX.DataTypes.Path", _port_required=False,
    _port_description="Optional empty folder for this run's disposable native working copy.")
@corex.number("timeout_s", default=600.0, minimum=1.0, maximum=86400.0, step=1.0, label="Timeout (s)", port=True,
    section="Session options", _section_order=1,
    _inspector_editor="text", _property_group="Session options",
    _port_value_type="COREX.DataTypes.Double", _port_description="Native open timeout from 1 to 86400 seconds.")
@corex.output("model", value_type="COREX.Mechanical.Model", label="Model", description="Run-owned Mechanical model state.")
@corex.output("info", value_type="COREX.DataTypes.TableValue", label="Info", description="Bounded session, system, object, property, table, and view descriptors.")
def open_mechanical_model(ctx, settings):
    return execute_open_model(ctx, settings)

@corex.node(
    id="mechanical.search_tree", name="Search Mechanical Tree",
    category=("FEA", "ANSYS", "Mechanical"),
    icon="mechanical/search.svg",
    description="Searches the current model snapshot with eleven COREX background data filters without changing the Mechanical Outline.",
    keywords=("mechanical", "ansys", "tree", "search", "property"),
    _default_expanded_settings_group_ids=("search",),
    _solution_reuse_scope="never",
)
@corex.input("model", value_type="COREX.Mechanical.Model", required=True,
    label="Model", description="Run-owned Mechanical model state.")
@corex.dropdown("filter", default="name",
    options=("name", "tag", "type", "state", "coordinate_system", "model", "graphics", "environment", "scoping", "property_name", "property_value"),
    label="Filter", section="Search", port=True, _section_order=0,
    _inspector_editor="enum", _property_group="Search",
    _port_value_type="COREX.DataTypes.String", _port_description="COREX background data-query category.")
@corex.text("query", default="", label="Query", port=True,
    section="Search", _section_order=1,
    _inspector_editor="text", _property_group="Search",
    _port_value_type="COREX.DataTypes.String", _port_description="Text query or accepted typed picker identity.")
@corex.dropdown("match", default="contains", options=("contains", "exact"), label="Match", port=True,
    section="Match options", _section_order=0,
    _inspector_editor="enum", _property_group="Match options",
    _port_value_type="COREX.DataTypes.String", _port_description="Whole-query Contains or Exact matching.")
@corex.switch("case_sensitive", default=False, label="Case sensitive", port=True,
    section="Match options", _section_order=1,
    _inspector_editor="toggle", _property_group="Match options",
    _port_value_type="COREX.DataTypes.Bool", _port_description="Use case-sensitive text matching.")
@corex.switch("include_hidden_properties", default=False, label="Include hidden properties", port=True,
    section="Match options", _section_order=2,
    _inspector_editor="toggle", _property_group="Match options",
    _port_value_type="COREX.DataTypes.Bool", _port_description="Include non-visible properties without changing tree suppression.")
@corex.switch("invert", default=False, label="Invert results", port=True,
    section="Match options", _section_order=3,
    _inspector_editor="toggle", _property_group="Match options",
    _port_value_type="COREX.DataTypes.Bool", _port_description="Invert only complete available applicable predicates.")
@corex.output("objects", value_type="COREX.Mechanical.Object", structure="list", label="Objects", description="Deduplicated matching objects in tree order.")
@corex.output("properties", value_type="COREX.Mechanical.Property", structure="list", label="Properties", description="Matching or discoverable properties in object order.")
@corex.output("found", value_type="COREX.DataTypes.Bool", label="Found", description="True when the complete search found an object or property.")
@corex.output("details", value_type="COREX.DataTypes.TableValue", label="Details", description="One data-only row per search match.")
def search_mechanical_tree(ctx, model, settings):
    return execute_search_tree(ctx, model, settings)

@corex.node(
    id="mechanical.fea_table", name="FEA Table",
    category=("FEA", "ANSYS", "Mechanical"),
    icon="mechanical/table.svg",
    description="Extracts supported Mechanical definitions, existing results, probes, and worksheets into immutable COREX tables without solving.",
    keywords=("mechanical", "ansys", "fea", "table", "definition", "result", "worksheet"),
    _default_expanded_settings_group_ids=("table_selection",),
    _solution_reuse_scope="never",
)
@corex.input("model", value_type="COREX.Mechanical.Model", required=True,
    label="Model", description="Run-owned Mechanical model state.")
@corex.input("source", value_type="COREX.Mechanical.Object",
    _accepted_data_types=("COREX.Mechanical.Property",), structure="list", required=True,
    label="Source", description="Ordered Mechanical Object or Property selectors to extract.",
    section="Table selection")
@corex.dropdown("family", default="auto",
    options=("auto", "model_definition", "result_history_summary", "spatial_samples", "supported_worksheet"),
    label="Family", section="Table selection", port=True,
    _inspector_editor="enum", _property_group="Table selection",
    _port_value_type="COREX.DataTypes.String", _port_description="Automatic or explicit definition, result, spatial, or worksheet table family.")
@corex.text("table", default="", label="Table / property", port=True,
    section="Table selection",
    _inspector_editor="text", _property_group="Table selection",
    _port_value_type="COREX.DataTypes.String", _port_description="Exact table/property selector; empty requires one applicable table.")
@corex.text("component", default="all", label="Component", port=True,
    section="Table selection",
    _inspector_editor="text", _property_group="Table selection",
    _port_value_type="COREX.DataTypes.String", _port_description="All or one exact component exposed by accepted metadata.")
@corex.dropdown("units", default="source", options=("source", "si"),
    label="Units", port=True, _inspector_editor="enum",
    section="Values and units", _section_order=0,
    _property_group="Values and units", _port_value_type="COREX.DataTypes.String",
    _port_description="Preserve source units or convert quantity samples with native Ansys SI facilities.")
@corex.list("sets", default=[], item_type=int, label="Rows / sets", port=True,
    section="Values and units", _section_order=1,
    _property_group="Values and units", _port_description="Stored result-set IDs; inactive for model definitions and worksheets.")
@corex.output("tables", value_type="COREX.DataTypes.TableValue", structure="list",
    label="Tables", description="Full-fidelity immutable tables in source order.")
@corex.output("definitions", value_type="COREX.DataTypes.TableValue", label="Definitions",
    description="Column units, identities, formulas, locations, and definition metadata.")
def fea_table(ctx, model, source, settings):
    return execute_fea_table(ctx, model, source, settings)

@corex.node(
    id="mechanical.camera_views", name="Mechanical Camera Views",
    category=("FEA", "ANSYS", "Mechanical"),
    icon="mechanical/views.svg",
    description="Extracts saved and current Mechanical cameras as data-only snapshots and a readable details table.",
    keywords=("mechanical", "ansys", "camera", "view", "saved"),
    _default_expanded_settings_group_ids=("view_selection",),
    _solution_reuse_scope="never",
)
@corex.input("model", value_type="COREX.Mechanical.Model", required=True,
    label="Model", description="Run-owned Mechanical model state.")
@corex.dropdown("include", default="saved_and_current",
    options=("saved_and_current", "saved", "current"), label="Include",
    section="View selection", port=True, _section_order=0,
    _inspector_editor="enum", _property_group="View selection",
    _port_value_type="COREX.DataTypes.String",
    _port_description="Saved views plus current, saved views only, or current view only.")
@corex.output("views", value_type="COREX.Mechanical.CameraView", structure="list",
    label="Views", description="Saved camera snapshots in native order, followed by current when requested.")
@corex.output("names", value_type="COREX.DataTypes.String", structure="list",
    label="Names", description="Camera labels in the same order as Views.")
@corex.output("details", value_type="COREX.DataTypes.TableValue", label="Details",
    description="Readable camera vectors, dimensions, units, availability, and source identity.")
def mechanical_camera_views(ctx, model, settings):
    return execute_camera_views(ctx, model, settings)

@corex.node(
    id="mechanical.export_image", name="Export Mechanical Image",
    category=("FEA", "ANSYS", "Mechanical"),
    icon="mechanical/image.svg",
    description="Captures deterministic object-by-view viewport PNG batches and optionally publishes them atomically.",
    keywords=("mechanical", "ansys", "viewport", "image", "png", "capture"),
    _default_expanded_settings_group_ids=("selection",),
    _solution_reuse_scope="never",
)
@corex.input("model", value_type="COREX.Mechanical.Model", structure="list", required=True,
    label="Model", description="Exactly one run-owned Mechanical model per matched branch; graft multiple models.")
@corex.list("objects", default=[], item_type=str, label="Objects", port=True,
    section="Selection", _section_order=0,
    _property_group="Selection", _port_structure="list",
    _port_value_type="COREX.Mechanical.Object", _port_accepted_data_types=("COREX.DataTypes.String",),
    _port_description="Mechanical objects or exact path/name selectors; empty keeps the current display.")
@corex.list("views", default=[], item_type=str, label="Views", port=True,
    section="Selection", _section_order=1,
    _property_group="Selection", _port_structure="list",
    _port_value_type="COREX.Mechanical.CameraView", _port_accepted_data_types=("COREX.DataTypes.String",),
    _port_description="Saved/current camera records or exact view names; empty keeps the current camera.")
@corex.number("width", default=1600, minimum=64, maximum=8192, step=1,
    label="Width (px)", section="Image options", port=True, _section_order=0,
    _property_group="Image options",
    _property_type="int", _port_value_type="COREX.DataTypes.Int", _port_description="Viewport image width from 64 to 8192 pixels.")
@corex.number("height", default=1000, minimum=64, maximum=8192, step=1,
    label="Height (px)", section="Image options", port=True, _section_order=1,
    _property_group="Image options",
    _property_type="int", _port_value_type="COREX.DataTypes.Int", _port_description="Viewport image height from 64 to 8192 pixels; total area is bounded.")
@corex.dropdown("background", default="white", options=("white", "model"),
    label="Background", section="Image options", port=True, _section_order=2,
    _inspector_editor="enum", _property_group="Image options",
    _port_value_type="COREX.DataTypes.String", _port_description="White or current Mechanical model background.")
@corex.switch("fit_view", default=False, label="Fit view", port=True,
    section="Image options", _section_order=3,
    _inspector_editor="toggle", _property_group="Image options",
    _port_value_type="COREX.DataTypes.Bool", _port_description="Fit after applying the selected camera only when enabled.")
@corex.path("folder", default="", label="Folder", port=True,
    section="Save to disk", _section_order=0,
    _inspector_editor="path", _property_group="Save to disk",
    _port_value_type="COREX.DataTypes.Path", _port_required=False,
    _port_description="Optional destination folder; empty returns images without writing user files.")
@corex.text("file_name", default="{object}_{view}.png", label="File name", port=True,
    section="Save to disk", _section_order=1,
    _inspector_editor="text", _property_group="Save to disk",
    _port_value_type="COREX.DataTypes.String",
    _port_description="PNG template using object, view, object_index, view_index, or index tokens.")
@corex.switch("overwrite", default=False, label="Overwrite", port=True,
    section="Save to disk", _section_order=2,
    _inspector_editor="toggle", _property_group="Save to disk",
    _port_value_type="COREX.DataTypes.Bool", _port_description="Replace existing destination files as one rollback-protected batch.")
@corex.output("images", value_type="COREX.DataTypes.Image", structure="tree",
    label="Images", description="Object-grouped image tree with selected views in order.")
@corex.output("files", value_type="COREX.DataTypes.Path", structure="list",
    label="Files", description="Published PNG paths in flattened object-major order; empty when Folder is blank.")
@corex.output("details", value_type="COREX.DataTypes.TableValue", label="Details",
    description="Object/view identities, DataPaths, image ordinals, dimensions, and published paths.")
def export_mechanical_image(ctx, model, settings):
    return execute_image_export(ctx, model, settings.objects, settings.views, settings)

@corex.node(
    id="mechanical.run_script", name="Run Mechanical Script",
    category=("FEA", "ANSYS", "Mechanical"),
    icon="mechanical/script.svg",
    description="Runs authored IronPython-compatible Mechanical code in the isolated working model. Authored code may explicitly solve or save; the node adds neither operation.",
    keywords=("mechanical", "ansys", "script", "ironpython", "environment"),
    _default_expanded_settings_group_ids=("script",),
    _solution_reuse_scope="never",
)
@corex.input("source_model", value_type="COREX.Mechanical.Model", required=True,
    label="Model", description="Run-owned Mechanical model state to mutate.")
@corex.list("environments", default=[], item_type=str, label="Environments", port=True,
    section="Script", _section_order=0,
    _property_group="Script", _port_structure="list",
    _port_value_type="COREX.Mechanical.Object", _port_accepted_data_types=("COREX.DataTypes.String",),
    _port_description="Analysis objects or exact paths/names; empty selects every analysis in tree order.")
@corex.dropdown("scope", default="each_environment", options=("each_environment", "model_once"),
    label="Scope", section="Script", port=True, _section_order=1,
    _inspector_editor="enum", _property_group="Script",
    _port_value_type="COREX.DataTypes.String", _port_description="Run once per selected analysis or once for the model.")
@corex.text("code", default="", label="Code", port=True,
    section="Script", _section_order=2,
    _inline_editor="textarea", _inspector_editor="textarea", _property_group="Script",
    _port_value_type="COREX.DataTypes.String", _port_required=True,
    _port_description="Required IronPython-compatible Mechanical code.")
@corex.number("timeout_s", default=600.0, minimum=1.0, maximum=86400.0, step=1.0,
    label="Timeout (s)", section="Execution options", port=True, _section_order=0,
    _inspector_editor="text", _property_group="Execution options",
    _port_value_type="COREX.DataTypes.Double", _port_description="Script timeout from 1 to 86400 seconds.")
@corex.switch("stop_on_error", default=True, label="Stop on error", port=True,
    section="Execution options", _section_order=1,
    _inspector_editor="toggle", _property_group="Execution options",
    _port_value_type="COREX.DataTypes.Bool", _port_description="Stop after the first failed analysis; disabling still fails the node after all attempts.")
@corex.output("model", value_type="COREX.Mechanical.Model", label="Model", description="New model revision after complete success.")
@corex.output("report", value_type="COREX.DataTypes.TableValue", label="Report", description="Per-analysis receipts followed by refreshed discovery descriptors.")
def run_mechanical_script(ctx, source_model, settings):
    return execute_run_script(ctx, source_model, settings.environments, settings)

@corex.node(
    id="mechanical.apdl_snippet", name="Mechanical APDL Snippet",
    category=("FEA", "ANSYS", "Mechanical"),
    icon="mechanical/snippet.svg",
    description="Creates or updates workflow-owned APDL command snippets in supported Static Structural analyses without solving or saving.",
    keywords=("mechanical", "ansys", "apdl", "command", "snippet", "load step"),
    _default_expanded_settings_group_ids=("command_snippet",),
    _solution_reuse_scope="never",
)
@corex.input("source_model", value_type="COREX.Mechanical.Model", required=True,
    label="Model", description="Run-owned Mechanical model state to mutate.")
@corex.list("environments", default=[], item_type=str, label="Environments", port=True,
    section="Command snippet", _section_order=0,
    _property_group="Command snippet", _port_structure="list",
    _port_value_type="COREX.Mechanical.Object", _port_accepted_data_types=("COREX.DataTypes.String",),
    _port_description="Static Structural analysis objects or exact paths/names; empty selects every supported analysis in tree order.")
@corex.text("name", default="COREX commands", label="Name", port=True,
    section="Command snippet", _section_order=1,
    _inspector_editor="text", _property_group="Command snippet",
    _port_value_type="COREX.DataTypes.String", _port_required=True,
    _port_description="Non-empty base name; selected steps append a deterministic step suffix.")
@corex.text("commands", default="", label="Commands", port=True,
    section="Command snippet", _section_order=2,
    _inline_editor="textarea", _inspector_editor="textarea", _property_group="Command snippet",
    _port_value_type="COREX.DataTypes.String", _port_required=True,
    _port_description="Required APDL source preserved exactly after the ownership marker.")
@corex.dropdown("steps", default="all", options=("all", "selected"),
    label="Steps", section="Solver placement", port=True, _section_order=0,
    _inspector_editor="enum", _property_group="Solver placement",
    _port_value_type="COREX.DataTypes.String", _port_description="Use the native all-load-step mode or one owned snippet per selected load step.")
@corex.list("selected_steps", default=[1], item_type=int, label="Selected load steps", port=True,
    section="Solver placement", _section_order=1,
    _property_group="Solver placement",
    _port_description="Positive unique load-step numbers; retained but unconsumed while Steps is All.")
@corex.switch("issue_solve_command", default=False, label="Issue SOLVE command", port=True,
    section="Solver placement", _section_order=2,
    _inspector_editor="toggle", _property_group="Solver placement",
    _port_value_type="COREX.DataTypes.Bool",
    _port_description="Controls generated solver input only; running this node never launches a solve.")
@corex.output("model", value_type="COREX.Mechanical.Model", label="Model", description="New model revision after complete success.")
@corex.output("snippets", value_type="COREX.Mechanical.Object", structure="list",
    label="Snippets", description="Owned snippets in analysis order, then selected load-step order.")
@corex.output("report", value_type="COREX.DataTypes.TableValue", label="Report", description="Per-target create/update receipts followed by refreshed discovery descriptors.")
def mechanical_apdl_snippet(ctx, source_model, settings):
    return execute_apdl_snippet(ctx, source_model, settings.environments, settings)

@corex.node(
    id="mechanical.save_model", name="Save Mechanical Model",
    category=("FEA", "ANSYS", "Mechanical"),
    icon="mechanical/save.svg",
    description="Explicitly saves standalone Mechanical outputs, complete Workbench projects/archives, or a selected Workbench model-only export through staged rollback-protected publication.",
    keywords=("mechanical", "ansys", "save", "archive", "mechdb", "mechdat", "mechpz", "wbpj", "wbpz"),
    _default_expanded_settings_group_ids=("destination",),
    _solution_reuse_scope="never",
)
@corex.input("source_model", value_type="COREX.Mechanical.Model", required=True,
    label="Model", description="Run-owned Mechanical model state after every intended mutation.")
@corex.path("file", default="", label="File", port=True,
    section="Destination", _section_order=0,
    file_filter="Mechanical and Workbench (*.mechdb *.mechdat *.mechpz *.wbpj *.wbpz);;All Files (*)",
    _inspector_editor="path", _property_group="Destination",
    _port_value_type="COREX.DataTypes.Path", _port_required=True,
    _port_description="Required explicit destination; no implicit source overwrite.")
@corex.dropdown("format", default="auto", options=("auto", "mechdb", "mechdat", "mechpz", "wbpj", "wbpz"),
    label="Format", section="Destination", port=True, _section_order=1,
    _inspector_editor="enum", _property_group="Destination",
    _port_value_type="COREX.DataTypes.String",
    _port_description="Auto infers the exact destination extension; explicit format and extension must agree.")
@corex.switch("include_results", default=True, label="Include result files", port=True,
    section="Save options", _section_order=0,
    _inspector_editor="toggle", _property_group="Save options",
    _port_value_type="COREX.DataTypes.Bool",
    _port_description="Native .mechpz/.wbpz result or solution inclusion; inactive and unconsumed for nonarchives.")
@corex.switch("include_user_files", default=True, label="Include user files", port=True,
    section="Save options", _section_order=1,
    _inspector_editor="toggle", _property_group="Save options",
    _port_value_type="COREX.DataTypes.Bool",
    _port_description="Native .mechpz/.wbpz user-file inclusion; inactive and unconsumed for nonarchives.")
@corex.switch("include_external_imported_files", default=True, label="Include external imported files", port=True,
    section="Save options", _section_order=2,
    _inspector_editor="toggle", _property_group="Save options",
    _port_value_type="COREX.DataTypes.Bool",
    _port_description="Native .wbpz external-import inclusion; inactive and unconsumed for other formats.")
@corex.switch("overwrite", default=False, label="Overwrite existing", port=True,
    section="Save options", _section_order=3,
    _inspector_editor="toggle", _property_group="Save options",
    _port_value_type="COREX.DataTypes.Bool",
    _port_description="Replace the explicit destination only after complete native staging and rollback preflight.")
@corex.output("model", value_type="COREX.Mechanical.Model", label="Model",
    description="Fresh admissible Model revision restored to its run-owned working database.")
@corex.output("files", value_type="COREX.DataTypes.Path", structure="list", label="Files",
    description="Published primary file and required companion directory in dependency order.")
@corex.output("report", value_type="COREX.DataTypes.TableValue", label="Report",
    description="Publication, inclusion, source/destination, and refreshed discovery receipt.")
def save_mechanical_model(ctx, source_model, settings):
    return execute_save_model(ctx, source_model, settings)
'''

__all__ = ["SOURCE"]
