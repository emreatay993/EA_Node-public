from __future__ import annotations

import unittest

from ea_node_editor.execution.handle_registry import HandleRegistry, StaleHandleError
from ea_node_editor.execution.worker_services import WorkerServices
from ea_node_editor.common.scene_protocol import COREX_SCENE_HANDLE_KIND
from ea_node_editor.nodes.execution_context import ExecutionContext
from ea_node_editor.runtime_contracts.value_refs import RuntimeHandleRef
from ea_node_editor.runtime_contracts import (
    DataTypeCatalog,
    DataTypeCatalogError,
    DataTypeFamilySpec,
    DataTypeSpec,
    ENGINEERING_SCENE_DATA_TYPE_ID,
    VIEWER_SESSION_DATA_TYPE_ID,
)
from tests.typed_handle_support import core_worker_services

_TEST_HANDLE_TYPE_ID = "tests.Runtime.Payload"
_TEST_HANDLE_KIND = "tests.payload"
_TEST_ABSTRACT_TYPE_ID = "tests.Runtime.Abstract"
_TEST_NATIVE_TYPE_ID = "tests.Runtime.Native"


def _test_handle_catalog() -> DataTypeCatalog:
    catalog = DataTypeCatalog()
    catalog.register_many(
        families=(
            DataTypeFamilySpec("tests", "Tests", "data.tests", "tests"),
        ),
        types=(
            DataTypeSpec(
                _TEST_HANDLE_TYPE_ID,
                "Test Payload",
                "tests",
                lambda value: (
                    isinstance(value, RuntimeHandleRef)
                    and value.kind == _TEST_HANDLE_KIND
                ),
                parents=(_TEST_ABSTRACT_TYPE_ID,),
                carriers=frozenset({"handle"}),
                payload_schema_version=3,
            ),
            DataTypeSpec(
                _TEST_ABSTRACT_TYPE_ID,
                "Abstract Test Payload",
                "tests",
                lambda _value: True,
                abstract=True,
                carriers=frozenset({"handle"}),
            ),
            DataTypeSpec(
                _TEST_NATIVE_TYPE_ID,
                "Native Test Payload",
                "tests",
                lambda _value: True,
                carriers=frozenset({"native"}),
            ),
        ),
        owner_id="tests.execution_handles",
    )
    catalog.freeze()
    return catalog


class HandleRegistryTests(unittest.TestCase):
    def test_registry_tracks_ref_counts_until_final_release(self) -> None:
        registry = HandleRegistry(
            worker_generation=4,
            data_types=_test_handle_catalog(),
        )
        payload = object()

        handle_ref = registry.register(
            payload,
            data_type_id=_TEST_HANDLE_TYPE_ID,
            kind=_TEST_HANDLE_KIND,
            owner_scope="run:run_registry",
            metadata={"label": "demo"},
        )

        self.assertEqual(handle_ref.worker_generation, 4)
        self.assertEqual(handle_ref.data_type_id, _TEST_HANDLE_TYPE_ID)
        self.assertEqual(handle_ref.schema_version, 3)
        self.assertEqual(handle_ref.metadata, {"label": "demo"})
        self.assertIs(registry.resolve(handle_ref, expected_kind="tests.payload"), payload)
        self.assertEqual(registry.lease_count(handle_ref), 1)

        retained_ref = registry.lease(
            handle_ref,
            owner_scope=handle_ref.owner_scope,
        )

        self.assertEqual(registry.lease_count(handle_ref), 2)
        self.assertFalse(registry.release(handle_ref))
        self.assertEqual(registry.lease_count(retained_ref), 1)
        self.assertTrue(registry.release(retained_ref))
        self.assertEqual(registry.active_handle_count, 0)

        with self.assertRaisesRegex(StaleHandleError, "stale or unknown"):
            registry.resolve(handle_ref)

    def test_registry_lease_keeps_target_scope_alive_after_run_cleanup(self) -> None:
        registry = HandleRegistry(data_types=_test_handle_catalog())
        payload = {"value": "cached"}

        run_ref = registry.register(
            payload,
            data_type_id=_TEST_HANDLE_TYPE_ID,
            kind=_TEST_HANDLE_KIND,
            owner_scope="run:run_cache",
            metadata={"cache_key": "mesh:primary"},
        )
        cache_ref = registry.lease(
            run_ref,
            owner_scope="cache:mesh:primary",
        )

        self.assertEqual(cache_ref.owner_scope, "cache:mesh:primary")
        self.assertEqual(cache_ref.metadata, {"cache_key": "mesh:primary"})
        self.assertIs(registry.resolve(cache_ref), payload)
        self.assertEqual(registry.release_owner_scope("run:run_cache"), 1)

        with self.assertRaisesRegex(StaleHandleError, "owner_scope is stale"):
            registry.resolve(run_ref)
        self.assertIs(registry.resolve(cache_ref), payload)

    def test_registry_reset_invalidates_generation_mismatched_refs(self) -> None:
        registry = HandleRegistry(
            worker_generation=2,
            data_types=_test_handle_catalog(),
        )
        handle_ref = registry.register(
            object(),
            data_type_id=_TEST_HANDLE_TYPE_ID,
            kind=_TEST_HANDLE_KIND,
            owner_scope="run:run_reset",
        )
        mismatched_ref = RuntimeHandleRef(
            data_type_id=handle_ref.data_type_id,
            schema_version=handle_ref.schema_version,
            handle_id=handle_ref.handle_id,
            kind=handle_ref.kind,
            owner_scope=handle_ref.owner_scope,
            worker_generation=handle_ref.worker_generation + 1,
        )

        with self.assertRaisesRegex(StaleHandleError, "worker_generation is stale"):
            registry.resolve(mismatched_ref)

        self.assertEqual(registry.reset(), 1)
        self.assertEqual(registry.worker_generation, 3)

        with self.assertRaisesRegex(StaleHandleError, "worker_generation is stale"):
            registry.resolve(handle_ref)

    def test_registry_rejects_unknown_or_kind_inconsistent_semantic_types(self) -> None:
        registry = HandleRegistry(data_types=_test_handle_catalog())
        with self.assertRaisesRegex(DataTypeCatalogError, "unknown data-type ID"):
            registry.register(
                object(),
                data_type_id="tests.Runtime.Unknown",
                kind=_TEST_HANDLE_KIND,
                owner_scope="run:unknown",
            )
        with self.assertRaisesRegex(DataTypeCatalogError, "invalid"):
            registry.register(
                object(),
                data_type_id=_TEST_HANDLE_TYPE_ID,
                kind="tests.wrong",
                owner_scope="run:wrong_kind",
            )

    def test_registry_requires_bound_concrete_handle_carrier_type(self) -> None:
        with self.assertRaisesRegex(DataTypeCatalogError, "frozen catalog"):
            HandleRegistry(data_types=DataTypeCatalog())
        with self.assertRaisesRegex(DataTypeCatalogError, "active data-type catalog"):
            HandleRegistry().register(
                object(),
                data_type_id=_TEST_HANDLE_TYPE_ID,
                kind=_TEST_HANDLE_KIND,
                owner_scope="run:unbound",
            )

        registry = HandleRegistry(data_types=_test_handle_catalog())
        with self.assertRaisesRegex(DataTypeCatalogError, "must be concrete"):
            registry.register(
                object(),
                data_type_id=_TEST_ABSTRACT_TYPE_ID,
                kind=_TEST_HANDLE_KIND,
                owner_scope="run:abstract",
            )
        with self.assertRaisesRegex(DataTypeCatalogError, "does not allow 'handle'"):
            registry.register(
                object(),
                data_type_id=_TEST_NATIVE_TYPE_ID,
                kind=_TEST_HANDLE_KIND,
                owner_scope="run:native",
            )

    def test_registry_rejects_forged_semantic_identity(self) -> None:
        registry = HandleRegistry(data_types=_test_handle_catalog())
        handle_ref = registry.register(
            object(),
            data_type_id=_TEST_HANDLE_TYPE_ID,
            kind=_TEST_HANDLE_KIND,
            owner_scope="run:identity",
        )
        forged_ref = RuntimeHandleRef(
            data_type_id=handle_ref.data_type_id,
            schema_version=handle_ref.schema_version + 1,
            handle_id=handle_ref.handle_id,
            kind=handle_ref.kind,
            owner_scope=handle_ref.owner_scope,
            worker_generation=handle_ref.worker_generation,
        )

        with self.assertRaisesRegex(StaleHandleError, "schema_version is stale"):
            registry.resolve(forged_ref)

    def test_registry_rejects_absolute_paths_before_storing_handle(self) -> None:
        registry = HandleRegistry(data_types=_test_handle_catalog())

        with self.assertRaisesRegex(ValueError, "absolute paths"):
            registry.register(
                object(),
                data_type_id=_TEST_HANDLE_TYPE_ID,
                kind=_TEST_HANDLE_KIND,
                owner_scope="run:strict_metadata",
                metadata={"source": r"C:\private\payload.bin"},
            )

        self.assertEqual(registry.active_handle_count, 0)

    def test_registry_resolves_and_acquires_serialized_ref_with_bound_catalog(self) -> None:
        registry = HandleRegistry(data_types=_test_handle_catalog())
        payload = object()
        handle_ref = registry.register(
            payload,
            data_type_id=_TEST_HANDLE_TYPE_ID,
            kind=_TEST_HANDLE_KIND,
            owner_scope="run:serialized",
        )
        serialized_ref = handle_ref.to_payload(catalog=registry.data_types)

        self.assertIs(registry.resolve(serialized_ref), payload)
        retained_ref = registry.lease(
            serialized_ref,
            owner_scope=handle_ref.owner_scope,
        )
        self.assertEqual(registry.lease_count(retained_ref), 2)

    def test_registry_resolve_authenticates_then_enforces_semantic_assignability(self) -> None:
        registry = HandleRegistry(data_types=_test_handle_catalog())
        payload = object()
        handle_ref = registry.register(
            payload,
            data_type_id=_TEST_HANDLE_TYPE_ID,
            kind=_TEST_HANDLE_KIND,
            owner_scope="run:expected_type",
        )

        self.assertIs(
            registry.resolve(
                handle_ref,
                expected_data_type=_TEST_HANDLE_TYPE_ID,
                expected_kind=_TEST_HANDLE_KIND,
            ),
            payload,
        )
        self.assertIs(
            registry.resolve(
                handle_ref,
                expected_data_type=_TEST_ABSTRACT_TYPE_ID,
                expected_kind=_TEST_HANDLE_KIND,
            ),
            payload,
        )
        with self.assertRaisesRegex(TypeError, "data type mismatch"):
            registry.resolve(
                handle_ref,
                expected_data_type=_TEST_NATIVE_TYPE_ID,
                expected_kind=_TEST_HANDLE_KIND,
            )

        forged_ref = RuntimeHandleRef(
            data_type_id=_TEST_NATIVE_TYPE_ID,
            schema_version=handle_ref.schema_version,
            handle_id=handle_ref.handle_id,
            kind=handle_ref.kind,
            owner_scope=handle_ref.owner_scope,
            worker_generation=handle_ref.worker_generation,
        )
        with self.assertRaisesRegex(StaleHandleError, "data_type_id is stale"):
            registry.resolve(
                forged_ref,
                expected_data_type=_TEST_NATIVE_TYPE_ID,
                expected_kind=_TEST_HANDLE_KIND,
            )


class ExecutionContextHandleTests(unittest.TestCase):
    def test_execution_context_routes_handle_apis_through_worker_services(self) -> None:
        services = WorkerServices()
        services.bind_data_types(_test_handle_catalog())
        ctx = ExecutionContext(
            run_id="run_ctx",
            node_id="node_ctx",
            workspace_id="ws_main",
            inputs={},
            properties={},
            emit_log=lambda _level, _message: None,
            worker_services=services,
        )

        payload = {"value": "runtime"}
        handle_ref = ctx.register_handle(
            payload,
            data_type_id=_TEST_HANDLE_TYPE_ID,
            kind=_TEST_HANDLE_KIND,
        )
        retained_ref = ctx.lease_handle(
            handle_ref,
            owner_scope=handle_ref.owner_scope,
        )

        self.assertEqual(handle_ref.owner_scope, "run:run_ctx")
        self.assertIs(
            ctx.resolve_handle(
                handle_ref,
                expected_data_type=_TEST_ABSTRACT_TYPE_ID,
                expected_kind="tests.payload",
            ),
            payload,
        )
        self.assertIs(
            ctx.resolve_handle(
                handle_ref.to_payload(catalog=services.data_types),
                expected_data_type=_TEST_HANDLE_TYPE_ID,
                expected_kind="tests.payload",
            ),
            payload,
        )
        with self.assertRaisesRegex(TypeError, "data type mismatch"):
            ctx.resolve_handle(
                handle_ref,
                expected_data_type=_TEST_NATIVE_TYPE_ID,
                expected_kind="tests.payload",
            )
        self.assertEqual(services.handle_registry.lease_count(handle_ref), 2)
        self.assertFalse(ctx.release_handle(retained_ref))
        self.assertTrue(ctx.release_handle(handle_ref))

        with self.assertRaisesRegex(StaleHandleError, "stale or unknown"):
            ctx.resolve_handle(handle_ref)


class ConcreteHandleSemanticTests(unittest.TestCase):
    def test_engineering_scene_semantics_reject_wrong_backend_kind(self) -> None:
        services = core_worker_services()
        with self.assertRaisesRegex(DataTypeCatalogError, "invalid"):
            services.register_handle(
                object(),
                data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
                kind="corex.scene.spoof",
                owner_scope="run:scene_spoof",
            )
        scene_ref = services.register_handle(
            object(),
            data_type_id=ENGINEERING_SCENE_DATA_TYPE_ID,
            kind=COREX_SCENE_HANDLE_KIND,
            owner_scope="run:scene",
        )
        self.assertIsNotNone(
            services.resolve_handle(
                scene_ref,
                expected_data_type=ENGINEERING_SCENE_DATA_TYPE_ID,
                expected_kind=COREX_SCENE_HANDLE_KIND,
            )
        )
        scene_spoof = RuntimeHandleRef(
            data_type_id=VIEWER_SESSION_DATA_TYPE_ID,
            schema_version=1,
            handle_id="spoof-scene",
            kind=COREX_SCENE_HANDLE_KIND,
            owner_scope="run:spoof",
            worker_generation=services.handle_registry.worker_generation,
        )
        with self.assertRaisesRegex(DataTypeCatalogError, "invalid"):
            services.data_types.validate_output(
                ENGINEERING_SCENE_DATA_TYPE_ID,
                scene_spoof,
            )


if __name__ == "__main__":
    unittest.main()
