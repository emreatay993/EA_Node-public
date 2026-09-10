from __future__ import annotations

import threading
import unittest
from dataclasses import replace

from ea_node_editor.common.scene_protocol import COREX_SCENE_HANDLE_KIND
from ea_node_editor.execution.handle_registry import (
    HandleDisposalError,
    HandleRegistry,
    StaleHandleError,
)
from ea_node_editor.runtime_contracts import (
    COREX_VIEWER_SESSION_HANDLE_KIND,
    DataTypeCatalog,
    DataTypeCatalogError,
    DataTypeFamilySpec,
    DataTypeSpec,
    ENGINEERING_SCENE_DATA_TYPE_ID,
    RuntimeHandleRef,
    VIEWER_SESSION_DATA_TYPE_ID,
)
from tests.typed_handle_support import core_worker_services

_CONCURRENT_TYPE_ID = "tests.Runtime.Concurrent"
_CONCURRENT_KIND = "tests.concurrent"


class _BlockingRequireCatalog(DataTypeCatalog):
    def __init__(self) -> None:
        super().__init__()
        self.require_entered = threading.Event()
        self.allow_require = threading.Event()
        self.block_require = False

    def require(self, data_type_id: str) -> DataTypeSpec:
        if self.block_require:
            self.require_entered.set()
            if not self.allow_require.wait(2.0):
                raise RuntimeError("catalog require release timed out")
        return super().require(data_type_id)


def _concurrent_catalog(
    validator,
    *,
    catalog: DataTypeCatalog | None = None,
) -> DataTypeCatalog:
    if catalog is None:
        catalog = DataTypeCatalog()
    catalog.register_many(
        families=(
            DataTypeFamilySpec("tests", "Tests", "data.tests", "tests"),
        ),
        types=(
            DataTypeSpec(
                _CONCURRENT_TYPE_ID,
                "Concurrent",
                "tests",
                validator,
                carriers=frozenset({"handle"}),
            ),
        ),
        owner_id="tests.handle_registry_concurrency",
    )
    catalog.freeze()
    return catalog


class HandleRegistryLeaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.services = core_worker_services()
        self.registry = self.services.handle_registry

    def register(
        self,
        value: object,
        *,
        owner_scope: str = "run:run_leases",
        metadata: dict[str, object] | None = None,
        dispose=None,
    ):
        return self.registry.register(
            value,
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            kind=COREX_SCENE_HANDLE_KIND,
            owner_scope=owner_scope,
            metadata=metadata,
            dispose=dispose,
        )

    def test_run_and_viewer_leases_share_one_record(self) -> None:
        value = object()
        run_ref = self.register(value)
        viewer_ref = self.registry.lease(
            run_ref,
            owner_scope="viewer:ws_main:session_one",
        )

        self.assertEqual(viewer_ref.handle_id, run_ref.handle_id)
        self.assertEqual(self.registry.active_handle_count, 1)
        self.assertEqual(self.registry.active_lease_count, 2)
        self.assertEqual(self.registry.release_owner_scope(run_ref.owner_scope), 1)
        with self.assertRaisesRegex(StaleHandleError, "owner_scope is stale"):
            self.registry.resolve(run_ref)
        self.assertIs(self.registry.resolve(viewer_ref), value)

    def test_identical_registration_reuses_record_and_counts_same_scope(self) -> None:
        value = object()
        first = self.register(value, metadata={"label": "scene"})
        second = self.register(value, metadata={"label": "scene"})

        self.assertEqual(second.handle_id, first.handle_id)
        self.assertEqual(self.registry.active_handle_count, 1)
        self.assertEqual(
            self.registry.lease_count(first, owner_scope=first.owner_scope),
            2,
        )
        self.assertFalse(self.registry.release(first))
        self.assertTrue(self.registry.release(second))

    def test_forged_or_released_scope_cannot_resolve_lease_or_release(self) -> None:
        run_ref = self.register(object())
        forged = replace(run_ref, owner_scope="viewer:forged")

        for operation in (
            lambda: self.registry.resolve(forged),
            lambda: self.registry.lease(
                forged,
                owner_scope="cache:forged",
            ),
            lambda: self.registry.release(forged),
        ):
            with self.assertRaisesRegex(StaleHandleError, "owner_scope is stale"):
                operation()

        self.assertEqual(self.registry.release_owner_scope(run_ref.owner_scope), 1)
        with self.assertRaisesRegex(StaleHandleError, "stale or unknown"):
            self.registry.resolve(run_ref)

    def test_forged_metadata_cannot_resolve_lease_or_release(self) -> None:
        handle_ref = self.register(
            object(),
            metadata={"label": "trusted"},
        )
        forged = replace(handle_ref, metadata={"label": "forged"})

        for operation in (
            lambda: self.registry.resolve(forged),
            lambda: self.registry.lease(
                forged,
                owner_scope="viewer:metadata_forged",
            ),
            lambda: self.registry.release(forged),
        ):
            with self.assertRaisesRegex(StaleHandleError, "metadata is stale"):
                operation()
        self.assertEqual(self.registry.lease_count(handle_ref), 1)

    def test_explicit_final_release_surfaces_disposal_error_once(self) -> None:
        calls: list[str] = []
        secret = r"TOP_SECRET_TOKEN C:\private\model.bin"

        def dispose() -> None:
            calls.append("dispose")
            raise RuntimeError(secret)

        handle_ref = self.register(object(), dispose=dispose)

        with self.assertRaises(HandleDisposalError) as captured:
            self.registry.release(handle_ref)
        self.assertEqual(str(captured.exception), "Runtime handle disposal failed.")
        self.assertIsInstance(captured.exception.__cause__, RuntimeError)
        self.assertIn(secret, str(captured.exception.__cause__))
        self.assertEqual(calls, ["dispose"])
        self.assertEqual(self.registry.active_handle_count, 0)
        with self.assertRaises(StaleHandleError):
            self.registry.release(handle_ref)
        self.assertEqual(calls, ["dispose"])

    def test_automatic_scope_cleanup_warns_and_continues(self) -> None:
        calls: list[str] = []
        warnings: list[str] = []
        secret = r"TOP_SECRET_TOKEN C:\private\model.bin"

        def failing_dispose() -> None:
            calls.append("failing")
            raise RuntimeError(secret)

        def successful_dispose() -> None:
            calls.append("successful")

        self.register(object(), dispose=failing_dispose)
        self.register(object(), dispose=successful_dispose)

        released = self.registry.release_owner_scope(
            "run:run_leases",
            warn=warnings.append,
        )

        self.assertEqual(released, 2)
        self.assertCountEqual(calls, ["failing", "successful"])
        self.assertEqual(
            warnings,
            ["Runtime handle automatic disposal failed."],
        )
        self.assertNotIn("TOP_SECRET_TOKEN", warnings[0])
        self.assertNotIn("private", warnings[0])
        self.assertEqual(self.registry.active_handle_count, 0)

    def test_reset_disposes_all_warns_and_increments_generation_once(self) -> None:
        calls: list[str] = []
        warnings: list[str] = []

        def failing_dispose() -> None:
            calls.append("failing")
            raise RuntimeError("reset close failed")

        def successful_dispose() -> None:
            calls.append("successful")

        first = self.register(object(), dispose=failing_dispose)
        second = self.register(
            object(),
            owner_scope="cache:scene:second",
            dispose=successful_dispose,
        )
        previous_generation = self.registry.worker_generation

        self.assertEqual(self.registry.reset(warn=warnings.append), 2)
        self.assertEqual(
            self.registry.worker_generation,
            previous_generation + 1,
        )
        self.assertCountEqual(calls, ["failing", "successful"])
        self.assertEqual(len(warnings), 1)
        with self.assertRaisesRegex(StaleHandleError, "worker_generation is stale"):
            self.registry.resolve(first)
        with self.assertRaisesRegex(StaleHandleError, "worker_generation is stale"):
            self.registry.resolve(second)

    def test_identity_contract_conflicts_fail_without_adding_a_lease(self) -> None:
        value = object()

        def first_disposer() -> None:
            return

        def conflicting_disposer() -> None:
            return

        handle_ref = self.register(
            value,
            metadata={"label": "original"},
            dispose=first_disposer,
        )

        with self.assertRaisesRegex(ValueError, "conflicting metadata"):
            self.register(
                value,
                metadata={"label": "changed"},
                dispose=first_disposer,
            )
        with self.assertRaisesRegex(ValueError, "conflicting disposer"):
            self.register(
                value,
                metadata={"label": "original"},
                dispose=conflicting_disposer,
            )
        with self.assertRaisesRegex(ValueError, "conflicting contract"):
            self.registry.register(
                value,
                data_type_id=VIEWER_SESSION_DATA_TYPE_ID,
                kind=COREX_VIEWER_SESSION_HANDLE_KIND,
                owner_scope=handle_ref.owner_scope,
                metadata={"label": "original"},
            )

        self.assertEqual(self.registry.lease_count(handle_ref), 1)
        self.assertEqual(self.registry.active_handle_count, 1)

    def test_concurrent_final_releases_dispose_exactly_once(self) -> None:
        calls: list[str] = []
        calls_lock = threading.Lock()
        start = threading.Barrier(3)

        def dispose() -> None:
            with calls_lock:
                calls.append("dispose")

        run_ref = self.register(object(), dispose=dispose)
        viewer_ref = self.registry.lease(
            run_ref,
            owner_scope="viewer:ws_main:session_concurrent",
        )
        outcomes: list[bool] = []

        def release(runtime_ref) -> None:
            start.wait()
            result = self.registry.release(runtime_ref)
            with calls_lock:
                outcomes.append(result)

        threads = (
            threading.Thread(target=release, args=(run_ref,)),
            threading.Thread(target=release, args=(viewer_ref,)),
        )
        for thread in threads:
            thread.start()
        start.wait()
        for thread in threads:
            thread.join(timeout=2.0)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertCountEqual(outcomes, [False, True])
        self.assertEqual(calls, ["dispose"])
        self.assertEqual(self.registry.active_handle_count, 0)

    def test_register_and_catalog_bind_commit_against_one_catalog(self) -> None:
        def validator(value: object) -> bool:
            return (
                isinstance(value, RuntimeHandleRef)
                and value.kind == _CONCURRENT_KIND
            )

        active_catalog = _BlockingRequireCatalog()
        _concurrent_catalog(validator, catalog=active_catalog)
        incompatible_catalog = DataTypeCatalog()
        incompatible_catalog.freeze()
        registry = HandleRegistry(data_types=active_catalog)
        active_catalog.block_require = True
        registered: list[RuntimeHandleRef] = []
        register_errors: list[BaseException] = []
        bind_errors: list[BaseException] = []
        bind_started = threading.Event()
        bind_finished = threading.Event()

        def register_value() -> None:
            try:
                registered.append(
                    registry.register(
                        object(),
                        data_type_id=_CONCURRENT_TYPE_ID,
                        kind=_CONCURRENT_KIND,
                        owner_scope="run:concurrent_catalog",
                    )
                )
            except BaseException as exc:  # noqa: BLE001
                register_errors.append(exc)

        def bind_incompatible_catalog() -> None:
            bind_started.set()
            try:
                registry.bind_data_types(incompatible_catalog)
            except BaseException as exc:  # noqa: BLE001
                bind_errors.append(exc)
            finally:
                bind_finished.set()

        register_thread = threading.Thread(target=register_value)
        bind_thread = threading.Thread(target=bind_incompatible_catalog)
        register_thread.start()
        self.assertTrue(active_catalog.require_entered.wait(2.0))
        bind_thread.start()
        self.assertTrue(bind_started.wait(2.0))
        bind_completed_during_require = bind_finished.wait(0.05)
        active_catalog.allow_require.set()
        register_thread.join(timeout=2.0)
        bind_thread.join(timeout=2.0)

        self.assertFalse(register_thread.is_alive())
        self.assertFalse(bind_thread.is_alive())
        self.assertFalse(bind_completed_during_require)
        self.assertEqual(register_errors, [])
        self.assertEqual(len(bind_errors), 1)
        self.assertIsInstance(bind_errors[0], DataTypeCatalogError)
        self.assertIs(registry.data_types, active_catalog)
        self.assertEqual(registry.active_handle_count, 1)
        self.assertIsNotNone(registry.resolve(registered[0]))

    def test_carrier_validator_reentry_cannot_mutate_registry(self) -> None:
        enabled = False
        attempted: dict[str, BaseException | None] = {}
        registry: HandleRegistry
        seed_ref: RuntimeHandleRef
        incompatible_catalog = DataTypeCatalog()
        incompatible_catalog.freeze()

        def validator(value: object) -> bool:
            if enabled:
                operations = {
                    "register": lambda: registry.register(
                        object(),
                        data_type_id=_CONCURRENT_TYPE_ID,
                        kind=_CONCURRENT_KIND,
                        owner_scope="run:reentrant_extra",
                    ),
                    "bind": lambda: registry.bind_data_types(
                        incompatible_catalog
                    ),
                    "lease": lambda: registry.lease(
                        seed_ref,
                        owner_scope="viewer:reentrant",
                    ),
                    "release": lambda: registry.release(seed_ref),
                    "reset": lambda: registry.reset(),
                }
                for name, operation in operations.items():
                    try:
                        operation()
                    except BaseException as exc:  # noqa: BLE001
                        attempted[name] = exc
                    else:
                        attempted[name] = None
            return (
                isinstance(value, RuntimeHandleRef)
                and value.kind == _CONCURRENT_KIND
            )

        catalog = _concurrent_catalog(validator)
        registry = HandleRegistry(data_types=catalog)
        seed_ref = registry.register(
            object(),
            data_type_id=_CONCURRENT_TYPE_ID,
            kind=_CONCURRENT_KIND,
            owner_scope="run:reentrant_seed",
        )
        generation = registry.worker_generation
        enabled = True

        outer_ref = registry.register(
            object(),
            data_type_id=_CONCURRENT_TYPE_ID,
            kind=_CONCURRENT_KIND,
            owner_scope="run:reentrant_outer",
        )

        self.assertEqual(
            set(attempted),
            {"register", "bind", "lease", "release", "reset"},
        )
        self.assertTrue(
            all(isinstance(error, RuntimeError) for error in attempted.values())
        )
        self.assertIs(registry.data_types, catalog)
        self.assertEqual(registry.worker_generation, generation)
        self.assertEqual(registry.active_handle_count, 2)
        self.assertEqual(registry.lease_count(seed_ref), 1)
        self.assertEqual(registry.lease_count(outer_ref), 1)


if __name__ == "__main__":
    unittest.main()
