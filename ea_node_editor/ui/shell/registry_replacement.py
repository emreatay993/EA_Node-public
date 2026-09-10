# Purpose: Coordinate read-only registry acceptance and reversible shell publication.
# Map: subsystems/ui_shell.md
# Tests: tests/test_registry_replacement.py

from __future__ import annotations

import logging
import shutil
import tempfile
from collections.abc import Callable, Iterable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ea_node_editor.graph.project_state import ProjectData
from ea_node_editor.graph.registry_compatibility import (
    RegistryCompatibilityReport,
    check_registry_compatibility,
)
from ea_node_editor.nodes.bootstrap import build_plugin_candidate_registry
from ea_node_editor.nodes.package_manager import (
    PackageInstallState,
    PackageInstallTransaction,
    stage_package_import,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.persistence.serializer import JsonProjectSerializer
from ea_node_editor.settings import plugin_generations_dir

if TYPE_CHECKING:
    from ea_node_editor.app_preferences import AppPreferencesStore
    from ea_node_editor.nodes.package_manager import PackageManifest

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class RegistryReplacementResult:
    operation: str
    applied: bool
    report: RegistryCompatibilityReport
    registry: NodeRegistry
    package_manifest: "PackageManifest | None" = None
    warnings: tuple[str, ...] = ()


class RegistryReplacementRollbackError(RuntimeError):
    def __init__(self, failures: Iterable[tuple[str, str]]) -> None:
        self.failures = tuple(failures)
        summary = ",".join(
            f"{owner}:{state}" for owner, state in self.failures
        )
        super().__init__(f"Registry replacement rollback failed [{summary}]")


@dataclass(slots=True, frozen=True)
class _PublicationStep:
    name: str
    apply: Callable[[], None]
    rollback: Callable[[], None]


class RegistryReplacementCoordinator:
    """Own one candidate-check-publish transaction for the live shell."""

    def __init__(
        self,
        host: Any,
        *,
        candidate_builder: Callable[..., NodeRegistry] = build_plugin_candidate_registry,
        package_stager: Callable[..., PackageInstallTransaction] = stage_package_import,
        generation_root_provider: Callable[[], Path] = plugin_generations_dir,
        projects_provider: Callable[[], ProjectData | Iterable[ProjectData]] | None = None,
    ) -> None:
        self._host = host
        self._candidate_builder = candidate_builder
        self._package_stager = package_stager
        self._generation_root_provider = generation_root_provider
        self._projects_provider = projects_provider

    def assert_registry_replaceable(self) -> None:
        runtime = self._host.execution_client
        runtime.assert_registry_replaceable()
        viewer_sessions = getattr(self._host, "viewer_session_bridge", None)
        assert_viewer_replaceable = getattr(
            viewer_sessions, "assert_registry_replaceable", None
        )
        if callable(assert_viewer_replaceable):
            assert_viewer_replaceable()

    def reload_plugins(
        self,
        *,
        extra_plugin_dirs: Sequence[Path] | None = None,
    ) -> RegistryReplacementResult:
        return self._replace_registry(
            operation="plugin_reload",
            extra_plugin_dirs=extra_plugin_dirs,
            preferences_document=self._current_preferences_document(),
        )

    def import_package(
        self,
        package_path: Path,
        *,
        extra_plugin_dirs: Sequence[Path] | None = None,
    ) -> RegistryReplacementResult:
        self.assert_registry_replaceable()
        transaction = self._package_stager(Path(package_path))
        return self._replace_registry(
            operation="package_import",
            extra_plugin_dirs=extra_plugin_dirs,
            transaction=transaction,
            preflight=False,
            preferences_document=self._current_preferences_document(),
        )

    def apply_addon_enabled_state(
        self,
        addon_id: str,
        *,
        enabled: bool,
        app_preferences_store: "AppPreferencesStore | None" = None,
        app_preferences_controller: Any = None,
        preferences_document: Any = None,
        extra_plugin_dirs: Sequence[Path] | None = None,
    ):
        from ea_node_editor.addons.state_changes import prepare_addon_enabled_state
        from ea_node_editor.app_preferences import default_app_preferences_document

        if preferences_document is not None:
            source_document = preferences_document
        elif app_preferences_controller is not None:
            source_document = app_preferences_controller.document()
        elif app_preferences_store is not None:
            source_document = app_preferences_store.load_document()
        else:
            source_document = default_app_preferences_document()

        staged = prepare_addon_enabled_state(
            addon_id,
            enabled=enabled,
            preferences_document=source_document,
        )
        if staged.restart_required:
            if app_preferences_controller is not None:
                persisted = app_preferences_controller.persist_document(
                    staged.preferences_document
                )
            elif app_preferences_store is not None:
                persisted = app_preferences_store.persist_document(
                    staged.preferences_document
                )
            else:
                persisted = staged.preferences_document
            return replace(staged, preferences_document=persisted)

        persisted_document = [staged.preferences_document]

        def persist_preferences() -> None:
            if app_preferences_controller is not None:
                persisted_document[0] = app_preferences_controller.persist_document(
                    staged.preferences_document
                )
            elif app_preferences_store is not None:
                persisted_document[0] = app_preferences_store.persist_document(
                    staged.preferences_document
                )

        result = self._replace_registry(
            operation=f"addon_apply:{staged.addon_id}",
            extra_plugin_dirs=extra_plugin_dirs,
            preferences_document=staged.preferences_document,
            previous_preferences_document=source_document,
            addon_id=staged.addon_id,
            expected_addon_enabled=staged.enabled,
            finalize=persist_preferences,
        )
        if not result.applied:
            issue_summary = "; ".join(
                issue.message for issue in result.report.issues[:8]
            )
            raise ValueError(issue_summary or "The add-on change is incompatible")
        return replace(
            staged,
            preferences_document=persisted_document[0],
            registry=result.registry,
        )

    def _replace_registry(
        self,
        *,
        operation: str,
        extra_plugin_dirs: Sequence[Path] | None,
        transaction: PackageInstallTransaction | None = None,
        preflight: bool = True,
        preferences_document: Any = None,
        previous_preferences_document: Any = None,
        addon_id: str = "",
        expected_addon_enabled: bool | None = None,
        finalize: Callable[[], None] | None = None,
    ) -> RegistryReplacementResult:
        if transaction is not None and finalize is not None:
            raise ValueError("package and preference finalizers are mutually exclusive")
        if bool(addon_id) != (expected_addon_enabled is not None):
            raise ValueError(
                "addon_id and expected_addon_enabled must be supplied together"
            )
        if addon_id:
            assert expected_addon_enabled is not None
        if preflight:
            self.assert_registry_replaceable()
        current_registry = self._host.registry
        package_manifest = transaction.manifest if transaction is not None else None
        guarded_phase_entered = False
        try:
            with self._disposable_generation_root() as candidate_root:
                candidate = self._build_candidate(
                    generation_root=candidate_root,
                    extra_plugin_dirs=extra_plugin_dirs,
                    staged_package_root=(
                        transaction.staged_package_root
                        if transaction is not None
                        else None
                    ),
                    preferences_document=preferences_document,
                    addon_id=addon_id,
                )
                if addon_id:
                    self._assert_requested_addon_state(
                        candidate,
                        addon_id=addon_id,
                        expected_enabled=expected_addon_enabled,
                    )
                report = check_registry_compatibility(
                    current_registry=current_registry,
                    candidate_registry=candidate,
                    projects=self._projects(),
                )
                if not report.compatible:
                    with self._host.execution_client.registry_publication_guard():
                        failures = self._rollback_transaction((), transaction)
                    if failures:
                        refusal = RuntimeError("Registry replacement was refused")
                        raise RegistryReplacementRollbackError(failures) from refusal
                    return RegistryReplacementResult(
                        operation=operation,
                        applied=False,
                        report=report,
                        registry=current_registry,
                        package_manifest=package_manifest,
                    )

                with self._host.execution_client.registry_publication_guard():
                    guarded_phase_entered = True
                    completed_steps: list[_PublicationStep] = []
                    try:
                        self._assert_registry_replaceable_under_guard()
                        if transaction is not None:
                            transaction.activate()
                        final_registry = self._build_candidate(
                            generation_root=self._generation_root_provider(),
                            extra_plugin_dirs=extra_plugin_dirs,
                            staged_package_root=None,
                            preferences_document=preferences_document,
                            addon_id=addon_id,
                        )
                        if addon_id:
                            self._assert_requested_addon_state(
                                final_registry,
                                addon_id=addon_id,
                                expected_enabled=expected_addon_enabled,
                            )
                        if (
                            candidate.contract_fingerprint()
                            != final_registry.contract_fingerprint()
                        ):
                            raise RuntimeError(
                                "Final registry contract does not match the accepted candidate"
                            )
                        final_report = check_registry_compatibility(
                            current_registry=current_registry,
                            candidate_registry=final_registry,
                            projects=self._projects(),
                        )
                        if not final_report.compatible:
                            raise RuntimeError(
                                "Final registry is incompatible with the open project"
                            )

                        for step in self._publication_steps(
                            current_registry=current_registry,
                            replacement_registry=final_registry,
                        ):
                            completed_steps.append(step)
                            step.apply()

                        warnings: list[str] = []
                        if transaction is not None:
                            try:
                                transaction.commit()
                            except Exception:
                                if transaction.state is not PackageInstallState.COMMITTED:
                                    raise
                                warnings.extend(
                                    transaction.issues or ("package_commit_cleanup",)
                                )
                            else:
                                warnings.extend(transaction.issues)
                        if finalize is not None:
                            finalize()
                        warnings.extend(self._emit_registry_notifications())
                        for warning in warnings:
                            logger.warning("Registry replacement warning [%s]", warning)
                        return RegistryReplacementResult(
                            operation=operation,
                            applied=True,
                            report=final_report,
                            registry=final_registry,
                            package_manifest=package_manifest,
                            warnings=tuple(warnings),
                        )
                    except Exception as original:
                        failures = self._rollback_transaction(
                            tuple(completed_steps),
                            transaction,
                        )
                        if failures:
                            raise RegistryReplacementRollbackError(failures) from original
                        raise
        except RegistryReplacementRollbackError:
            raise
        except Exception as original:
            if guarded_phase_entered:
                raise
            with self._host.execution_client.registry_publication_guard():
                failures = self._rollback_transaction((), transaction)
            if failures:
                raise RegistryReplacementRollbackError(failures) from original
            raise

    def _build_candidate(
        self,
        *,
        generation_root: Path,
        extra_plugin_dirs: Sequence[Path] | None,
        staged_package_root: Path | None,
        preferences_document: Any,
        addon_id: str,
    ) -> NodeRegistry:
        return self._candidate_builder(
            extra_plugin_dirs=list(extra_plugin_dirs or ()),
            generation_root=Path(generation_root),
            staged_package_root=staged_package_root,
            preferences_document=preferences_document,
        )

    @staticmethod
    def _assert_requested_addon_state(
        registry: NodeRegistry,
        *,
        addon_id: str,
        expected_enabled: bool,
    ) -> None:
        accepted_enabled = dict(registry.addon_runtime_config()).get(addon_id)
        if accepted_enabled is not expected_enabled:
            raise RuntimeError(
                "Add-on registry identity does not match the requested enabled state"
            )

    def _publication_steps(
        self,
        *,
        current_registry: NodeRegistry,
        replacement_registry: NodeRegistry,
    ) -> tuple[_PublicationStep, ...]:
        host = self._host
        runtime = host.execution_client
        scene = host.scene
        interactions = host.graph_interactions
        old_serializer = host.serializer
        new_serializer = JsonProjectSerializer(replacement_registry)
        session_store = host.session_store
        viewer_sessions = host.viewer_session_bridge

        steps: list[_PublicationStep] = [
            _PublicationStep(
                "runtime",
                lambda: runtime.replace_registry(replacement_registry),
                lambda: runtime.replace_registry(current_registry),
            )
        ]
        steps.extend(
            (
                _PublicationStep(
                    "graph_scene",
                    lambda: scene.replace_registry(replacement_registry),
                    lambda: scene.replace_registry(current_registry),
                ),
                _PublicationStep(
                    "host_registry",
                    lambda: setattr(host, "registry", replacement_registry),
                    lambda: setattr(host, "registry", current_registry),
                ),
                _PublicationStep(
                    "graph_interactions",
                    lambda: interactions.replace_registry(replacement_registry),
                    lambda: interactions.replace_registry(current_registry),
                ),
                _PublicationStep(
                    "serializer",
                    lambda: setattr(host, "serializer", new_serializer),
                    lambda: setattr(host, "serializer", old_serializer),
                ),
                _PublicationStep(
                    "session_store",
                    lambda: session_store.replace_serializer(new_serializer),
                    lambda: session_store.replace_serializer(old_serializer),
                ),
                _PublicationStep(
                    "viewer_catalog",
                    lambda: viewer_sessions.replace_data_types(
                        replacement_registry.data_types
                    ),
                    lambda: viewer_sessions.replace_data_types(
                        current_registry.data_types
                    ),
                ),
            )
        )

        return tuple(steps)

    def _emit_registry_notifications(self) -> tuple[str, ...]:
        warnings: list[str] = []
        for name, signal in (
            ("node_library", self._host.node_library_changed),
            ("selection", self._host.selected_node_changed),
            ("workspace", self._host.workspace_state_changed),
        ):
            try:
                signal.emit()
            except Exception:  # noqa: BLE001 - durable publication already succeeded
                warnings.append(f"notification_{name}_failed")
        return tuple(warnings)

    def _assert_registry_replaceable_under_guard(self) -> None:
        self._host.execution_client.assert_registry_replaceable()
        viewer_sessions = getattr(self._host, "viewer_session_bridge", None)
        assert_viewer_replaceable = getattr(
            viewer_sessions, "assert_registry_replaceable", None
        )
        if callable(assert_viewer_replaceable):
            assert_viewer_replaceable()

    def _projects(self) -> ProjectData | tuple[ProjectData, ...]:
        if self._projects_provider is None:
            return self._host.model.project
        projects = self._projects_provider()
        if isinstance(projects, ProjectData):
            return projects
        return tuple(projects)

    def _current_preferences_document(self) -> Any:
        controller = getattr(self._host, "app_preferences_controller", None)
        document = getattr(controller, "document", None)
        return document() if callable(document) else None

    @classmethod
    def _rollback_transaction(
        cls,
        steps: tuple[_PublicationStep, ...],
        transaction: PackageInstallTransaction | None,
    ) -> tuple[tuple[str, str], ...]:
        failures: list[tuple[str, str]] = []
        for step in reversed(steps):
            try:
                step.rollback()
            except Exception:  # noqa: BLE001 - continue restoring remaining owners
                failures.append((step.name, "restore_failed"))
        package_failure = cls._rollback_package(transaction)
        if package_failure is not None:
            failures.append(package_failure)
        return tuple(failures)

    @staticmethod
    def _rollback_package(
        transaction: PackageInstallTransaction | None,
    ) -> tuple[str, str] | None:
        if transaction is None or transaction.state not in {
            PackageInstallState.STAGED,
            PackageInstallState.ACTIVATED,
            PackageInstallState.FAILED,
        }:
            return None
        for attempt in range(2):
            try:
                transaction.rollback()
                return None
            except Exception:  # noqa: BLE001 - retry FAILED once, then aggregate
                if attempt == 0 and transaction.state is PackageInstallState.FAILED:
                    continue
                issues = ",".join(transaction.issues) or "rollback_failed"
                return ("package", f"{transaction.state.value}:{issues}")
        return None

    @staticmethod
    @contextmanager
    def _disposable_generation_root():
        root = Path(tempfile.mkdtemp(prefix="corex-plugin-candidate-"))
        try:
            yield root
        finally:
            try:
                shutil.rmtree(root)
            except OSError:
                logger.warning(
                    "Registry candidate generation cleanup failed [candidate_generation]"
                )


__all__ = [
    "RegistryReplacementCoordinator",
    "RegistryReplacementRollbackError",
    "RegistryReplacementResult",
]
