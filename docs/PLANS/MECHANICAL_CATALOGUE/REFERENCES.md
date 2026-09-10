# Mechanical Catalogue — API References and Evidence Boundaries

These references were used to plan the integration. They establish documented API surfaces, not completed compatibility tests. The follow-up [backend resolution](BACKEND_DECISIONS.md) pins native source-family archives, the separate model-only `.dsdb` export route, camera XML/name/index, and headless table dispatch. Under the user's 2026-09-07 release amendment, T01 must record actual behavior on Ansys 2026 R1 (261), the sole initial reference and acceptance release, including the exact Python package versions used. Instructions or example actions inside third-party documents were treated as reference content, not as authorization to run software or modify user models.

## A01 — Embedded Mechanical and interactive launching

- [PyMechanical App API](https://mechanical.docs.pyansys.com/version/stable/api/ansys/mechanical/core/embedding/app/App.html)
- [Mechanical launch/connect API](https://mechanical.docs.pyansys.com/version/stable/api/ansys/mechanical/core/mechanical/index.html)
- [Embedded UI helper](https://mechanical.docs.pyansys.com/version/stable/api/ansys/mechanical/core/embedding/ui/index.html)
- [Known Mechanical limitations](https://mechanical.docs.pyansys.com/version/stable/kil/mechanical.html)

Planning use: an embedded App is a headless application in its owner process; API calls require serialized ownership. Interactive server launch is a separate route. The UI helper's temporary-copy behavior is unsuitable as the catalogue's same-session mode switch. The selected COREX contract retains successful Interactive windows only for inspection until the next graph-run start in the same workspace or workspace/application shutdown; runs in other workspaces do not retire them. Background and failed/cancelled owners close with bounded cleanup. Exact API/process behavior remains T01/T03 proof work.

## A02 — Tree filtering and visible property labels

- [v261 Tree](https://scripting.mechanical.docs.pyansys.com/version/stable/api/ansys/mechanical/stubs/v261/Ansys/ACT/Automation/Mechanical/Tree.html)
- [v261 outline filter behavior](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/wb_sim/ds_filter_tree.html)
- [v261 visible property access](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/act_script/mech_script_GetVisiblePropertiesForTreeObject.html)

Planning outcome: the 261 live probe rejected native Filter/Find/IsObjInTreeView in embedded mode. The user chose COREX-owned background data queries; their exact eleven-category definitions and deliberate association/history differences are fixed in BACKEND_DECISIONS section 3 and PLAN section 9. Use Tree.AllObjects and documented object/property/relation data. Do not use native UI counts as expected results for deliberately different modes, or imply Parent/Location heuristics reproduce full native parity. VisibleProperties/Caption/StringValue remains the property-text route; required unavailable match data fails as search_incomplete.

## A03 — Model field tables and formulas

- [v261 Field](https://scripting.mechanical.docs.pyansys.com/version/stable/api/ansys/mechanical/stubs/v261/Ansys/ACT/Mechanical/Fields/Field.html)
- [v261 Variable](https://scripting.mechanical.docs.pyansys.com/version/stable/api/ansys/mechanical/stubs/v261/Ansys/ACT/Mechanical/Fields/Variable.html)

Planning use: Inputs/Output and Variable definition/value/unit metadata are the headless model-definition route. Formula text and evaluated discrete samples are different information. Preserve null/free/locked states, units and ordered independent/dependent columns. The bundled release-scoped 2026 R1 scripting guide corroborated this family; T01 still verifies 2026 R1 behavior.

## A04 — Result tables, spatial data, probes and worksheets

- [v261 Result](https://scripting.mechanical.docs.pyansys.com/version/stable/api/ansys/mechanical/stubs/v261/Ansys/ACT/Automation/Mechanical/Results/Result.html)
- [v261 Solution](https://scripting.mechanical.docs.pyansys.com/version/stable/api/ansys/mechanical/stubs/v261/Ansys/ACT/Automation/Mechanical/Solution.html)
- [v261 ITable](https://scripting.mechanical.docs.pyansys.com/version/stable/api/ansys/mechanical/stubs/v261/Ansys/Mechanical/Interfaces/ITable.html)
- [v261 ForceReaction](https://scripting.mechanical.docs.pyansys.com/version/stable/api/ansys/mechanical/stubs/v261/Ansys/ACT/Automation/Mechanical/Results/ProbeResults/ForceReaction.html)
- [v261 mesh-control worksheet](https://scripting.mechanical.docs.pyansys.com/version/stable/api/ansys/mechanical/stubs/v261/Ansys/ACT/Automation/Mechanical/MeshControlWorksheet.html)
- [v261 layered-section worksheet](https://scripting.mechanical.docs.pyansys.com/version/stable/api/ansys/mechanical/stubs/v261/Ansys/ACT/Automation/Mechanical/LayeredSectionWorksheet.html)

Planning use: API-native ITable columns are distinct from spatial PlotData and are not universally available GUI histories. Use ITable.Keys/key access/Independents/Dependents, not IDataTable.Columns. Configured-result summary histories use result-reader ListTimeFreq, By/SetNumber and native Minimum/Maximum/Average. For the proved initial `By=Time`/inactive `SetNumber=0` case, restore the active addressing fields exactly and report valid positive SetNumber drift when the public setter rejects zero; all other restoration failures remain fatal. ForceReaction exposes DisplayTime/RetrieveResult and axis/total quantities, has no SetNumber, and has read-only By on live 261. Accept only already-Time probes with unambiguous stored times, never assign By, and reject other modes. Worksheets retain explicit mixed-column row adapters.

- [Ansys headless result-table discussion and per-set approach](https://discuss.ansys.com/discussion/3129/how-to-access-tabular-data-values-in-mechanical-scripting-without-the-gui-open)
- [Ansys discussion distinguishing modal Frequency access from universal table support](https://discuss.ansys.com/discussion/255/how-to-access-tabular-data-using-act)

## A05 — Camera data and viewport image export

- [v261 MechanicalCameraWrapper](https://scripting.mechanical.docs.pyansys.com/version/stable/api/ansys/mechanical/stubs/v261/Ansys/ACT/Common/Graphics/MechanicalCameraWrapper.html)
- [Official viewport capture example](https://examples.mechanical.docs.pyansys.com/examples/00_basic/example_02_capture_images.html)

Planning use: extract current focal point/view/up vectors and quantity-valued scene size; enumerate saved names using ExportModelViews XML direct ModelView children, required Name and original child indices; apply the index and read numeric public Camera fields. Keep duplicate-name records in a list and validate count against NumberOfViews. This selected route has a concrete public example; its 261 structure/index/restoration behavior remains a validation check. Object activation precedes the final camera application; an explicit named camera must not be overwritten by unconditional fitting.

- [Ansys example of exported view Name/original-index enumeration](https://discuss.ansys.com/discussion/4537/act-python-or-js-how-to-get-the-view-objects-managed-views-and-get-their-names)
- [v261 saved model views](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/act_script/mech_apis_graphics_manage_views.html)

## A06 — Python scripts and APDL command objects

- [Official script scope example](https://examples.mechanical.docs.pyansys.com/examples/01_tips_n_tricks/example_02_run_python_script_scope.html)
- [v261 CommandSnippet API](https://scripting.mechanical.docs.pyansys.com/version/stable/api/ansys/mechanical/stubs/v261/Ansys/ACT/Automation/Mechanical/CommandSnippet.html)
- [v261 command object](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/mech_obj/ds_Commands_o_r.html)
- [v261 command-object solver semantics](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/wb_sim/ds_using_cmds_obj_w_MAPDL.html)

Planning use: Input is the snippet source property. StepSelectionMode/StepNumber are load-step/phase controls, not a generic substep callback. IssueSolveCommand affects generated solver commands. APDL uses solver units; the node cannot silently convert arbitrary command text. Immediate Python scripts and solver-time snippets are separate nodes/operations.

## A07 — Workbench ownership, projects and archives

- [PyWorkbench launch API](https://workbench.docs.pyansys.com/version/stable/api/ansys/workbench/core/public_api/index.html)
- [PyWorkbench client API](https://workbench.docs.pyansys.com/version/stable/api/ansys/workbench/core/workbench_client/WorkbenchClient.html)
- [Historical v252 Workbench Project namespace](https://ansyshelp.ansys.com/public/Views/Secured/corp/v252/en/wb2_js/Namespace15.html)
- [v261 Mechanical Model container](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/wb2_js/ContainerName30.html)
- [Official PyWorkbench client implementation](https://raw.githubusercontent.com/ansys/pyworkbench/main/src/ansys/workbench/core/workbench_client.py)

Planning use: retain Workbench as owner, use native Open/Unarchive, select a stable system/Model container and connect to its Mechanical server. Flush the owned editor and use Workbench Save/Archive for whole-project output. Workbench 261 exposes `IncludeSkippedFiles` for result/solution files (default True), `IncludeUserFiles` (default True), and `IncludeExternalImportedFiles` (default False). COREX exposes all three as Boolean ports and defaults them True while retaining `FailIfMissingFiles=True`. Unarchive uses `ArchivePath` and `ProjectPath`. The convenience archive download helper does not by itself establish the explicit inclusion policy required here.

T14 preservation additionally uses [h5py datatype equality](https://api.h5py.org/h5t.html), [dataspace dimensions](https://api.h5py.org/h5s.html), [creation-property equality](https://api.h5py.org/h5p.html), and the [HDF5 object-time contract](https://support.hdfgroup.org/documentation/hdf5/latest/group___o_c_p_l.html). Installed h5py 3.16.0 exposes these APIs; the low-level online reference currently identifies a development version and is supplementary. The narrow closed-schema state-file rule and evidence limitation are recorded in BACKEND_DECISIONS.md. Logical equality is not proof of timestamp-only byte changes.

The final native exclusion evidence distinguishes active registered external references from pre-existing unregistered internal copies, including equal-content files with the same basename. It supports identity-specific no-import/rebase and preserves unrelated internal assets; it is not a claim that every copy of the source bytes is absent. Failed historical aggregates and the first `.wbpj` producer's replayability limit remain explicit in BACKEND_DECISIONS.md and the retained T14 receipt.

## A08 — Standalone save and required cross-format export gate

- [v261 standalone Project API](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/act_ref/item41515884641331155064551942059670254159175752181.html)
- [v261 Mechanical File tab](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/wb_sim/ds_menu_file.html)
- [v261 Workbench import formats](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/wb2_help/wb2h_importing_files.html)

Planning correction: native archives remain with their source owner: standalone `.mechpz` uses Project.Archive/Unarchive and whole Workbench `.wbpz` uses Workbench Archive/Unarchive. Workbench Model.Export(`.dsdb`) followed by separate same-release standalone Project.Open and SaveAs is retained only for model-only `.mechdb`/`.mechdat` selected exports. The retained fixture proved native `.wbpz` result inclusion and separately showed that `.dsdb` omits the result. That historical failure is no longer an archive gate and must not prompt further result-preserving `.dsdb` investigation.

- [v261 standalone `.dsdb` opening support](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/wb_sim/ds_Define_Analysis_Type_step.html)
- [v261 standalone Open API](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/act_ref/item24511471501692523719712618616310178171248191184916825.html)
- [v261 standalone SaveAs API](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/act_ref/item2301862269413248198541712202549813619610921712886182.html)
- [v261 standalone Archive API](https://ansyshelp.ansys.com/public/Views/Secured/corp/v261/en/act_ref/item1322132429717421118220323412032182984249342261881849.html)

## A09 — Limited DPF opportunity

- [DPF reaction-force operator](https://dpf.docs.pyansys.com/version/stable/api/ansys/dpf/core/operators/result/reaction_force/reaction_force.html)

DPF can be useful for explicitly scoped bulk RST/RTH result histories or reductions. It does not automatically reproduce a configured Mechanical probe's scope, coordinate frame, averaging or reduction. The plan prefers native tables and permits only a specifically proved adapter; it does not use DPF for tree properties, authored load definitions, cameras or Workbench saving.

## Release amendment and reference verification

The user replaced the historical 252 compatibility requirement with 261 on 2026-09-07. Release 252 is outside initial supported scope; no 252 compatibility is claimed. Later releases remain capability-checked only. This amendment preserves every non-release qualification gate.

The replacement v261 pages were opened and their relevant API content checked: Field Inputs/Output; Variable definition/value/unit metadata; ITable Keys/Item/Independents/Dependents; ForceReaction DisplayTime/RetrieveResult; both worksheet row APIs; CommandSnippet step fields; command-object solver semantics; the Outline difference guide; standalone Open/SaveAs/Archive. These references establish declarations, not runtime compatibility. The v261 Workbench Project namespace page could not be retrieved during this amendment, so its v252 link is retained explicitly as historical context. It does not establish 261 keyword or dependency behavior: T01 must prove the 261 native Project lifecycle, formal arguments and missing-dependency failure.

## Local source grounding

The plan was grounded in the current add-on catalog/contract registration, ExecutionContext and WorkerServices/HandleRegistry, NodeExecutor DataTree matching, CorexRuntime solution reuse, existing immutable scientific values, Signal Plot metadata enrichment, shared QML settings groups/controls, and icon registration. Exact source paths and task write scopes are listed in PLAN.md. These source facts were re-read during planning; future implementers must check current ownership before editing.

Initial document preparation did not launch Ansys. In the subsequent user-authorized 261 refinement, disposable no-solve Mechanical/Workbench probes confirmed the basic native export/conversion and saved-view route and rejected native embedded Outline filtering. BACKEND_DECISIONS records reports, results and limits. No existing user project, solver run, application-node implementation or task commit was involved. Full 261 acceptance and realistic result/dependency coverage remain T01/T18 work.
