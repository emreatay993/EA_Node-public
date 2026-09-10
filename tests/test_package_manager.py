from __future__ import annotations

import hashlib
import json
import os
import stat
import struct
import zipfile
from pathlib import Path

import pytest

from ea_node_editor.nodes import package_manager, plugin_generation, plugin_loader
from ea_node_editor.nodes.function_plugin import PluginBundleRef, PythonFunctionRef
from ea_node_editor.nodes.plugin_generation import (
    materialize_plugin_generation,
    read_verified_plugin_generation,
)
from ea_node_editor.nodes.package_schema import (
    PLUGIN_ASSET_LIMIT,
    PLUGIN_MANIFEST_LIMIT,
    PLUGIN_MEMBER_LIMIT,
    PLUGIN_REGULAR_FILE_MESSAGE,
    PLUGIN_SOURCE_LIMIT,
    PLUGIN_TOTAL_LIMIT,
    SCHEMA_1_UNSUPPORTED_MESSAGE,
    canonical_bundle_digest,
    canonical_manifest_bytes,
)
from ea_node_editor.nodes.registry import NodeRegistry
from ea_node_editor.ui_qml.node_title_icon_sources import (
    resolve_node_title_icon_source,
)


TYPE_ID = "custom.package_node.1234abcd"


def _node_source(*, icon: str = "", marker: Path | None = None) -> str:
    marker_code = (
        f'Path({str(marker)!r}).write_text("executed", encoding="utf-8")\n'
        if marker is not None
        else ""
    )
    icon_arg = f", icon={icon!r}" if icon else ""
    return f'''import corex
from pathlib import Path
{marker_code}@corex.node(
    id={TYPE_ID!r},
    name="Package Node",
    category=("Tests",){icon_arg},
)
@corex.input("value", value_type=float)
@corex.output("result", value_type=float)
def package_node(ctx, value):
    return {{"result": value}}
'''


def _manifest(
    *,
    name: str = "example_package",
    sources: dict[str, bytes] | None = None,
    assets: dict[str, bytes] | None = None,
    modules: list[str] | None = None,
    schema_version: int | None = 2,
) -> dict[str, object]:
    source_members = sources or {"nodes.py": _node_source().encode("utf-8")}
    asset_members = assets or {}
    raw: dict[str, object] = {
        "name": name,
        "version": "1.0.0",
        "author": "",
        "description": "",
        "modules": modules or ["nodes.py"],
        "sources": [
            {"path": path, "sha256": hashlib.sha256(payload).hexdigest()}
            for path, payload in sorted(source_members.items())
        ],
        "assets": [
            {"path": path, "sha256": hashlib.sha256(payload).hexdigest()}
            for path, payload in sorted(asset_members.items())
        ],
        "nodes": [
            {"id": TYPE_ID, "module": (modules or ["nodes.py"])[0], "function": "package_node"}
        ],
    }
    if schema_version is not None:
        raw = {"schema_version": schema_version, **raw}
    return raw


def _write_raw_archive(
    path: Path,
    manifest: dict[str, object],
    members: dict[str, bytes],
    *,
    extra_infos: list[tuple[zipfile.ZipInfo, bytes]] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(package_manager.MANIFEST_FILENAME, canonical_manifest_bytes(manifest))
        for name, payload in members.items():
            archive.writestr(name, payload)
        for info, payload in extra_infos or []:
            archive.writestr(info, payload)
    return path


def _valid_raw_archive(path: Path, *, marker: Path | None = None) -> Path:
    source = _node_source(marker=marker).encode("utf-8")
    return _write_raw_archive(path, _manifest(sources={"nodes.py": source}), {"nodes.py": source})


def _set_encrypted_flags(path: Path) -> None:
    payload = bytearray(path.read_bytes())
    for signature, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        cursor = 0
        while True:
            cursor = payload.find(signature, cursor)
            if cursor < 0:
                break
            flags = struct.unpack_from("<H", payload, cursor + offset)[0]
            struct.pack_into("<H", payload, cursor + offset, flags | 0x1)
            cursor += 4
    path.write_bytes(payload)


def test_schema2_limits_are_the_documented_values() -> None:
    assert PLUGIN_MANIFEST_LIMIT == 64 * 1024
    assert PLUGIN_SOURCE_LIMIT == 256 * 1024
    assert PLUGIN_ASSET_LIMIT == 4 * 1024 * 1024
    assert PLUGIN_MEMBER_LIMIT == 128
    assert PLUGIN_TOTAL_LIMIT == 16 * 1024 * 1024


def test_export_is_deterministic_exact_and_round_trips_without_execution(tmp_path: Path) -> None:
    marker = tmp_path / "executed.txt"
    nodes = tmp_path / "src" / "nodes.py"
    helper = tmp_path / "src" / "helper.py"
    icon = tmp_path / "src" / "icon.svg"
    nodes.parent.mkdir()
    nodes.write_text(_node_source(icon="assets/icon.svg", marker=marker), encoding="utf-8")
    helper.write_text("VALUE = 1\n", encoding="utf-8")
    icon.write_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'/>")
    manifest = package_manager.PackageManifest(
        name="example_package",
        version="2.3.4",
        author="Package Tests",
        description="Deterministic schema 2",
        nodes=[TYPE_ID],
    )
    sources = [
        package_manager.PackageExportSource(nodes, "nodes.py"),
        package_manager.PackageExportSource(helper, "helper.py"),
    ]
    assets = [package_manager.PackageExportAsset(icon, "assets/icon.svg")]

    first = package_manager.export_package(
        sources,
        manifest,
        tmp_path / "first.cxpkg",
        assets=assets,
    )
    second = package_manager.export_package(
        list(reversed(sources)),
        manifest,
        tmp_path / "second.cxpkg",
        assets=assets,
    )

    assert first.read_bytes() == second.read_bytes()
    assert not marker.exists()
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == [
            package_manager.MANIFEST_FILENAME,
            "assets/icon.svg",
            "helper.py",
            "nodes.py",
        ]
        assert {info.date_time for info in archive.infolist()} == {(1980, 1, 1, 0, 0, 0)}
        raw = json.loads(archive.read(package_manager.MANIFEST_FILENAME))
    assert list(raw) == sorted(raw)
    assert set(raw) == {
        "schema_version",
        "name",
        "version",
        "author",
        "description",
        "modules",
        "sources",
        "assets",
        "nodes",
    }
    assert raw["schema_version"] == 2
    assert raw["modules"] == ["nodes.py"]
    assert raw["nodes"] == [
        {"id": TYPE_ID, "module": "nodes.py", "function": "package_node"}
    ]

    installed = package_manager.import_package(first, target_dir=tmp_path / "plugins")
    assert installed.nodes == [TYPE_ID]
    assert installed.modules == ["nodes.py"]
    assert not marker.exists()


def test_installed_package_discovery_uses_generation_asset_provenance(tmp_path: Path) -> None:
    nodes = tmp_path / "nodes.py"
    icon = tmp_path / "icon.svg"
    nodes.write_text(_node_source(icon="assets/icon.svg"), encoding="utf-8")
    icon.write_bytes(b"<svg/>")
    archive = package_manager.export_package(
        [nodes],
        package_manager.PackageManifest(name="asset_package"),
        tmp_path / "asset_package.cxpkg",
        assets=[package_manager.PackageExportAsset(icon, "assets/icon.svg")],
    )
    installed_root = tmp_path / "plugins"
    package_manager.import_package(archive, target_dir=installed_root)
    registry = NodeRegistry()

    result = plugin_loader.discover_static_plugin_candidate(
        registry,
        roots=(),
        generation_root=tmp_path / "generations",
        staged_package_root=installed_root / "asset_package",
    )
    provenance = registry.provenance_or_none(TYPE_ID)

    assert result.type_ids == (TYPE_ID,)
    assert provenance is not None
    assert provenance.kind == "package"
    assert provenance.package_root is not None
    assert provenance.package_root.parent == (tmp_path / "generations").resolve()
    expected = (provenance.package_root / "assets" / "icon.svg").resolve().as_uri()
    assert resolve_node_title_icon_source("assets/icon.svg", provenance=provenance) == expected
    (installed_root / "asset_package" / "assets" / "icon.svg").write_bytes(b"mutated")
    assert resolve_node_title_icon_source("assets/icon.svg", provenance=provenance) == expected


def test_loose_plugins_cannot_claim_custom_assets(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir()
    (plugin_root / "loose.py").write_text(
        _node_source(icon="assets/icon.svg"),
        encoding="utf-8",
    )
    (plugin_root / "assets").mkdir()
    (plugin_root / "assets" / "icon.svg").write_bytes(b"<svg/>")
    registry = NodeRegistry()

    result = plugin_loader.discover_static_plugins(
        registry,
        roots=(plugin_root,),
        generation_root=tmp_path / "generations",
    )

    assert result.type_ids == ()
    assert registry.spec_or_none(TYPE_ID) is None


@pytest.mark.parametrize(
    "member_name",
    [
        "../escape.py",
        "/absolute.py",
        "C:/drive.py",
        "folder\\node.py",
        "./node.py",
        "folder/../node.py",
        "assets/CON.svg",
        "assets/CONIN$.svg",
        "assets/CONOUT$.png",
        "assets/COM¹.svg",
        "assets/COM².jpg",
        "assets/COM³.jpeg",
        "assets/LPT¹.svg",
        "assets/LPT².jpg",
        "assets/LPT³.jpeg",
        "assets/trailing. ",
    ],
)
def test_import_rejects_unsafe_windows_archive_paths(tmp_path: Path, member_name: str) -> None:
    archive = _valid_raw_archive(tmp_path / "unsafe.cxpkg")
    with zipfile.ZipFile(archive, "a") as writer:
        writer.writestr(member_name, b"bad")
    if "\\" in member_name:
        archive.write_bytes(
            archive.read_bytes().replace(
                member_name.replace("\\", "/").encode("utf-8"),
                member_name.encode("utf-8"),
            )
        )

    with pytest.raises(ValueError, match="Unsafe package archive member"):
        package_manager.import_package(archive, target_dir=tmp_path / "plugins")


def test_import_rejects_windows_case_insensitive_duplicates(tmp_path: Path) -> None:
    source = _node_source().encode("utf-8")
    archive = _write_raw_archive(
        tmp_path / "duplicate.cxpkg",
        _manifest(sources={"nodes.py": source}),
        {"nodes.py": source, "NODES.py": source},
    )

    with pytest.raises(ValueError, match="Duplicate package archive member"):
        package_manager.import_package(archive, target_dir=tmp_path / "plugins")


def test_duplicate_node_ids_across_modules_reject_before_replacing_package(
    tmp_path: Path,
) -> None:
    first_source = _node_source().encode("utf-8")
    second_source = _node_source().encode("utf-8")
    sources = {"first.py": first_source, "second.py": second_source}
    raw = _manifest(sources=sources, modules=["first.py", "second.py"])
    raw["nodes"] = [
        {"id": TYPE_ID, "module": "first.py", "function": "package_node"},
        {"id": TYPE_ID, "module": "second.py", "function": "package_node"},
    ]
    archive = _write_raw_archive(
        tmp_path / "duplicate-node-id.cxpkg",
        raw,
        sources,
    )
    plugins = tmp_path / "plugins"
    installed = plugins / "example_package"
    installed.mkdir(parents=True)
    sentinel = installed / "keep.txt"
    sentinel.write_text("original", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate node ids"):
        package_manager.import_package(archive, target_dir=plugins)

    assert sentinel.read_text(encoding="utf-8") == "original"
    assert not list(plugins.glob(".example_package.incoming-*"))
    assert not list(plugins.glob(".example_package.backup-*"))


def test_import_rejects_symlink_and_encrypted_members(tmp_path: Path) -> None:
    source = _node_source().encode("utf-8")
    link = zipfile.ZipInfo("linked.py")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    symlink_archive = _write_raw_archive(
        tmp_path / "symlink.cxpkg",
        _manifest(sources={"nodes.py": source}),
        {"nodes.py": source},
        extra_infos=[(link, b"nodes.py")],
    )
    with pytest.raises(ValueError, match="regular files"):
        package_manager.import_package(symlink_archive, target_dir=tmp_path / "plugins")

    encrypted_archive = _valid_raw_archive(tmp_path / "encrypted.cxpkg")
    _set_encrypted_flags(encrypted_archive)
    with pytest.raises(ValueError, match="encrypted"):
        package_manager.import_package(encrypted_archive, target_dir=tmp_path / "plugins")


@pytest.mark.parametrize("kind", ["source", "asset", "manifest", "members", "total"])
def test_import_enforces_every_archive_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    source = _node_source().encode("utf-8")
    members: dict[str, bytes] = {"nodes.py": source}
    raw = _manifest(sources={"nodes.py": source})
    if kind == "source":
        monkeypatch.setattr(package_manager, "PLUGIN_SOURCE_LIMIT", len(source) - 1)
    elif kind == "asset":
        members["assets/icon.svg"] = b"12345"
        raw = _manifest(sources={"nodes.py": source}, assets={"assets/icon.svg": b"12345"})
        monkeypatch.setattr(package_manager, "PLUGIN_ASSET_LIMIT", 4)
    elif kind == "manifest":
        monkeypatch.setattr(
            package_manager,
            "PLUGIN_MANIFEST_LIMIT",
            len(canonical_manifest_bytes(raw)) - 1,
        )
    elif kind == "members":
        for index in range(PLUGIN_MEMBER_LIMIT):
            members[f"assets/{index:03}.svg"] = b"x"
    else:
        monkeypatch.setattr(
            package_manager,
            "PLUGIN_TOTAL_LIMIT",
            len(canonical_manifest_bytes(raw)) + len(source) - 1,
        )
    archive = _write_raw_archive(tmp_path / f"{kind}.cxpkg", raw, members)

    with pytest.raises(ValueError, match="too (large|many)"):
        package_manager.import_package(archive, target_dir=tmp_path / "plugins")


def test_import_member_limit_counts_manifest_at_exact_boundary(tmp_path: Path) -> None:
    source = _node_source().encode("utf-8")
    accepted_assets = {f"assets/{index:03}.svg": b"x" for index in range(126)}
    accepted_archive = _write_raw_archive(
        tmp_path / "accepted-128-total.cxpkg",
        _manifest(sources={"nodes.py": source}, assets=accepted_assets),
        {"nodes.py": source, **accepted_assets},
    )
    with zipfile.ZipFile(accepted_archive) as archive:
        assert len(archive.infolist()) == PLUGIN_MEMBER_LIMIT
    package_manager.import_package(accepted_archive, target_dir=tmp_path / "accepted")

    rejected_assets = {f"assets/{index:03}.svg": b"x" for index in range(127)}
    rejected_archive = _write_raw_archive(
        tmp_path / "rejected-129-total.cxpkg",
        _manifest(sources={"nodes.py": source}, assets=rejected_assets),
        {"nodes.py": source, **rejected_assets},
    )
    with zipfile.ZipFile(rejected_archive) as archive:
        assert len(archive.infolist()) == PLUGIN_MEMBER_LIMIT + 1
    with pytest.raises(ValueError, match="too many members"):
        package_manager.import_package(rejected_archive, target_dir=tmp_path / "rejected")


def test_export_member_limit_counts_manifest_at_exact_boundary(tmp_path: Path) -> None:
    source = tmp_path / "nodes.py"
    asset = tmp_path / "asset.svg"
    source.write_text(_node_source(), encoding="utf-8")
    asset.write_bytes(b"x")
    accepted_assets = [
        package_manager.PackageExportAsset(asset, f"assets/{index:03}.svg")
        for index in range(126)
    ]
    accepted_archive = package_manager.export_package(
        [source],
        package_manager.PackageManifest(name="accepted_members"),
        tmp_path / "accepted-members.cxpkg",
        assets=accepted_assets,
    )
    with zipfile.ZipFile(accepted_archive) as archive:
        assert len(archive.infolist()) == PLUGIN_MEMBER_LIMIT

    rejected_assets = [
        package_manager.PackageExportAsset(asset, f"assets/{index:03}.svg")
        for index in range(127)
    ]
    rejected_path = tmp_path / "rejected-members.cxpkg"
    with pytest.raises(ValueError, match="too many members"):
        package_manager.export_package(
            [source],
            package_manager.PackageManifest(name="rejected_members"),
            rejected_path,
            assets=rejected_assets,
        )
    assert not rejected_path.exists()


def test_generation_materialization_and_verification_accept_128_total_members(
    tmp_path: Path,
) -> None:
    source = _node_source().encode("utf-8")
    assets = {f"assets/{index:03}.svg": b"x" for index in range(126)}
    members = {"nodes.py": source, **assets}
    raw = _manifest(sources={"nodes.py": source}, assets=assets)
    digest = canonical_bundle_digest(raw, members)
    generation = materialize_plugin_generation(
        tmp_path / "generations",
        bundle_digest=digest,
        manifest=raw,
        members=members,
    )
    function = PythonFunctionRef(
        bundle_id="plugin:package:boundary",
        bundle_digest=digest,
        module_relative_path="nodes.py",
        function_name="package_node",
        source_digest=hashlib.sha256(source).hexdigest(),
    )
    verified = read_verified_plugin_generation(
        PluginBundleRef(
            owner_id="plugin:package:boundary",
            version="1.0.0",
            generation_id=digest,
            bundle_digest=digest,
            approved_generation_root=str(generation),
            functions=(function,),
        )
    )

    assert len(verified.members) + 1 == PLUGIN_MEMBER_LIMIT


def test_generation_materialization_rejects_129_total_members(tmp_path: Path) -> None:
    source = _node_source().encode("utf-8")
    assets = {f"assets/{index:03}.svg": b"x" for index in range(127)}
    members = {"nodes.py": source, **assets}
    raw = _manifest(sources={"nodes.py": source}, assets=assets)
    digest = canonical_bundle_digest(raw, members)
    generation_root = tmp_path / "generations"

    with pytest.raises(ValueError, match="too many members"):
        materialize_plugin_generation(
            generation_root,
            bundle_digest=digest,
            manifest=raw,
            members=members,
        )

    assert not generation_root.exists()


def test_generation_total_limit_checks_actual_bytes_after_each_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _node_source().encode("utf-8")
    members = {"nodes.py": source}
    raw = _manifest(sources=members)
    digest = canonical_bundle_digest(raw, members)
    generation = materialize_plugin_generation(
        tmp_path / "generations",
        bundle_digest=digest,
        manifest=raw,
        members=members,
    )
    manifest_size = (generation / package_manager.MANIFEST_FILENAME).stat().st_size
    monkeypatch.setattr(
        plugin_generation,
        "PLUGIN_TOTAL_LIMIT",
        manifest_size + len(source) + 1,
    )
    read_member = plugin_generation._read_generation_member  # noqa: SLF001

    def inflated_member(root, relative_path, *, limit):  # noqa: ANN001
        payload = read_member(root, relative_path, limit=limit)
        return payload + b"xx" if relative_path == "nodes.py" else payload

    monkeypatch.setattr(
        plugin_generation,
        "_read_generation_member",
        inflated_member,
    )
    function = PythonFunctionRef(
        bundle_id="plugin:package:actual-size",
        bundle_digest=digest,
        module_relative_path="nodes.py",
        function_name="package_node",
        source_digest=hashlib.sha256(source).hexdigest(),
    )

    with pytest.raises(ValueError, match="expanded size"):
        read_verified_plugin_generation(
            PluginBundleRef(
                owner_id="plugin:package:actual-size",
                version="1.0.0",
                generation_id=digest,
                bundle_digest=digest,
                approved_generation_root=str(generation),
                functions=(function,),
            )
        )


def test_installed_directory_rejects_129_total_members(tmp_path: Path) -> None:
    source = _node_source().encode("utf-8")
    assets = {f"assets/{index:03}.svg": b"x" for index in range(127)}
    members = {"nodes.py": source, **assets}
    raw = _manifest(sources={"nodes.py": source}, assets=assets)
    package_dir = tmp_path / "plugins" / "example_package"
    package_dir.mkdir(parents=True)
    (package_dir / package_manager.MANIFEST_FILENAME).write_bytes(
        canonical_manifest_bytes(raw)
    )
    for relative_path, payload in members.items():
        path = package_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    assert len([path for path in package_dir.rglob("*") if path.is_file()]) == (
        PLUGIN_MEMBER_LIMIT + 1
    )

    with pytest.raises(ValueError, match="too many members"):
        plugin_loader.discover_static_plugin_candidate(
            NodeRegistry(),
            roots=(),
            generation_root=tmp_path / "generations",
            staged_package_root=package_dir,
        )


def test_import_rejects_undeclared_unsupported_nested_bad_hash_and_bad_icon(
    tmp_path: Path,
) -> None:
    source = _node_source().encode("utf-8")
    cases: list[tuple[str, dict[str, object], dict[str, bytes], str]] = []
    cases.append(
        (
            "undeclared",
            _manifest(sources={"nodes.py": source}),
            {"nodes.py": source, "extra.py": b"VALUE = 1\n"},
            "undeclared members",
        )
    )
    cases.append(
        (
            "unsupported",
            _manifest(sources={"nodes.py": source}),
            {"nodes.py": source, "asset.gif": b"GIF"},
            "Unsupported package archive member",
        )
    )
    nested_manifest = _manifest(
        sources={"nested/nodes.py": source},
        modules=["nested/nodes.py"],
    )
    cases.append(
        (
            "nested",
            nested_manifest,
            {"nested/nodes.py": source},
            "canonical relative paths",
        )
    )
    bad_hash = _manifest(sources={"nodes.py": source})
    bad_hash["sources"][0]["sha256"] = "0" * 64  # type: ignore[index]
    cases.append(("hash", bad_hash, {"nodes.py": source}, "hash mismatch"))
    bad_icon_source = _node_source(icon="assets/missing.svg").encode("utf-8")
    cases.append(
        (
            "icon",
            _manifest(sources={"nodes.py": bad_icon_source}),
            {"nodes.py": bad_icon_source},
            "not a declared asset",
        )
    )

    for name, raw, members, message in cases:
        archive = _write_raw_archive(tmp_path / f"{name}.cxpkg", raw, members)
        with pytest.raises(ValueError, match=message):
            package_manager.import_package(archive, target_dir=tmp_path / f"plugins-{name}")


@pytest.mark.parametrize("mutation", ["unknown", "missing"])
def test_import_requires_the_exact_schema2_manifest_fields(
    tmp_path: Path,
    mutation: str,
) -> None:
    source = _node_source().encode("utf-8")
    raw = _manifest(sources={"nodes.py": source})
    if mutation == "unknown":
        raw["dependencies"] = []
    else:
        raw.pop("assets")
    archive = _write_raw_archive(
        tmp_path / f"{mutation}.cxpkg",
        raw,
        {"nodes.py": source},
    )

    with pytest.raises(ValueError, match="(unknown|missing required) fields"):
        package_manager.import_package(archive, target_dir=tmp_path / "plugins")


def test_export_rejects_bad_icon_and_nested_sources(tmp_path: Path) -> None:
    bad_icon = tmp_path / "bad_icon.py"
    bad_icon.write_text(_node_source(icon="assets/missing.svg"), encoding="utf-8")
    with pytest.raises(ValueError, match="not a declared asset"):
        package_manager.export_package(
            [bad_icon],
            package_manager.PackageManifest(name="bad_icon"),
            tmp_path / "bad_icon.cxpkg",
        )
    assert not (tmp_path / "bad_icon.cxpkg").exists()

    with pytest.raises(ValueError, match="canonical relative paths"):
        package_manager.export_package(
            [package_manager.PackageExportSource(bad_icon, "nested/nodes.py")],
            package_manager.PackageManifest(name="nested"),
            tmp_path / "nested.cxpkg",
        )


@pytest.mark.parametrize(
    "member_name",
    [package_manager.MANIFEST_FILENAME, "nodes.py", "assets/icon.svg"],
)
def test_installed_package_rejects_hard_linked_members(
    tmp_path: Path,
    member_name: str,
) -> None:
    source = _node_source().encode("utf-8")
    assets = {"assets/icon.svg": b"<svg/>"}
    archive = _write_raw_archive(
        tmp_path / "hard-linked-installed.cxpkg",
        _manifest(sources={"nodes.py": source}, assets=assets),
        {"nodes.py": source, **assets},
    )
    plugin_root = tmp_path / "plugins"
    package_manager.import_package(archive, target_dir=plugin_root)
    member = plugin_root / "example_package" / member_name
    peer = tmp_path / f"peer-{Path(member_name).name}"
    peer.write_bytes(member.read_bytes())
    member.unlink()
    os.link(peer, member)
    assert member.stat().st_nlink == 2

    with pytest.raises(ValueError) as error:
        plugin_loader.discover_static_plugin_candidate(
            NodeRegistry(),
            roots=(),
            generation_root=tmp_path / "generations",
            staged_package_root=plugin_root / "example_package",
        )
    assert str(error.value) == PLUGIN_REGULAR_FILE_MESSAGE


@pytest.mark.parametrize("member_kind", ["source", "asset"])
def test_export_rejects_hard_linked_local_members(
    tmp_path: Path,
    member_kind: str,
) -> None:
    source = tmp_path / "nodes.py"
    asset = tmp_path / "icon.svg"
    source.write_text(_node_source(), encoding="utf-8")
    asset.write_bytes(b"<svg/>")
    linked_member = source if member_kind == "source" else asset
    os.link(linked_member, tmp_path / f"{member_kind}-peer{linked_member.suffix}")
    assert linked_member.stat().st_nlink == 2

    with pytest.raises(ValueError) as error:
        package_manager.export_package(
            [source],
            package_manager.PackageManifest(name=f"hard_linked_{member_kind}"),
            tmp_path / f"hard-linked-{member_kind}.cxpkg",
            assets=[package_manager.PackageExportAsset(asset, "assets/icon.svg")],
        )
    assert str(error.value) == PLUGIN_REGULAR_FILE_MESSAGE


def test_schema1_archive_and_installed_directory_use_migration_message(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = _node_source().encode("utf-8")
    legacy = _write_raw_archive(
        tmp_path / "legacy.cxpkg",
        {"name": "legacy", "version": "1.0.0", "nodes": [TYPE_ID]},
        {"nodes.py": source},
    )
    with pytest.raises(ValueError, match="schema 1") as archive_error:
        package_manager.import_package(legacy, target_dir=tmp_path / "plugins")
    assert str(archive_error.value) == SCHEMA_1_UNSUPPORTED_MESSAGE
    assert "PLUGIN_MIGRATION_GUIDE.md#node-package-schema-1" in str(
        archive_error.value
    )

    legacy_dir = tmp_path / "installed" / "legacy"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / package_manager.MANIFEST_FILENAME).write_text(
        json.dumps({"name": "legacy", "version": "1.0.0", "nodes": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as installed_error:
        package_manager.list_installed_packages(target_dir=tmp_path / "installed")
    assert str(installed_error.value) == SCHEMA_1_UNSUPPORTED_MESSAGE
    with pytest.raises(ValueError) as loader_error:
        plugin_loader.discover_static_plugin_candidate(
            NodeRegistry(),
            roots=(),
            generation_root=tmp_path / "generations",
            staged_package_root=legacy_dir,
        )
    assert str(loader_error.value) == SCHEMA_1_UNSUPPORTED_MESSAGE
    plugin_loader.discover_static_plugins(
        NodeRegistry(),
        roots=(tmp_path / "installed",),
        generation_root=tmp_path / "static-generations",
    )
    assert SCHEMA_1_UNSUPPORTED_MESSAGE in caplog.text


def test_stage_package_import_validates_without_activating(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    installed = plugins / "example_package"
    installed.mkdir(parents=True)
    sentinel = installed / "keep.txt"
    sentinel.write_text("original", encoding="utf-8")
    marker = tmp_path / "executed.txt"
    archive = _valid_raw_archive(tmp_path / "staged.cxpkg", marker=marker)

    transaction = package_manager.stage_package_import(archive, target_dir=plugins)

    assert transaction.state is package_manager.PackageInstallState.STAGED
    assert transaction.manifest.name == "example_package"
    assert transaction.staged_package_root.is_dir()
    assert transaction.installed_package_root == installed
    assert sentinel.read_text(encoding="utf-8") == "original"
    assert not marker.exists()
    transaction.rollback()
    assert transaction.state is package_manager.PackageInstallState.ROLLED_BACK
    assert sentinel.read_text(encoding="utf-8") == "original"
    assert not list(plugins.glob(".example_package.*"))


def test_activation_revalidates_staged_bytes(tmp_path: Path) -> None:
    archive = _valid_raw_archive(tmp_path / "mutated.cxpkg")
    transaction = package_manager.stage_package_import(
        archive,
        target_dir=tmp_path / "plugins",
    )
    (transaction.staged_package_root / "nodes.py").write_text(
        _node_source() + "# changed\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="hash mismatch"):
        transaction.activate()

    assert transaction.state is package_manager.PackageInstallState.STAGED
    assert not transaction.installed_package_root.exists()
    transaction.rollback()


def test_new_install_rollback_is_idempotent(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    transaction = package_manager.stage_package_import(
        _valid_raw_archive(tmp_path / "new.cxpkg"),
        target_dir=plugins,
    )

    transaction.activate()
    assert transaction.state is package_manager.PackageInstallState.ACTIVATED
    assert (transaction.installed_package_root / "nodes.py").is_file()
    transaction.rollback()
    transaction.rollback()

    assert transaction.state is package_manager.PackageInstallState.ROLLED_BACK
    assert not transaction.installed_package_root.exists()
    assert not list(plugins.glob(".example_package.*"))
    with pytest.raises(RuntimeError, match="rolled_back"):
        transaction.commit()


def test_replacement_rollback_restores_exact_prior_directory(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    installed = plugins / "example_package"
    installed.mkdir(parents=True)
    (installed / "keep.txt").write_text("original", encoding="utf-8")
    transaction = package_manager.stage_package_import(
        _valid_raw_archive(tmp_path / "replacement.cxpkg"),
        target_dir=plugins,
    )

    transaction.activate()
    assert not (installed / "keep.txt").exists()
    assert (installed / "nodes.py").is_file()
    transaction.rollback()

    assert transaction.state is package_manager.PackageInstallState.ROLLED_BACK
    assert [path.name for path in installed.iterdir()] == ["keep.txt"]
    assert (installed / "keep.txt").read_text(encoding="utf-8") == "original"
    assert not list(plugins.glob(".example_package.*"))


def test_commit_removes_retained_paths_and_is_idempotent(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    installed = plugins / "example_package"
    installed.mkdir(parents=True)
    (installed / "keep.txt").write_text("original", encoding="utf-8")
    transaction = package_manager.stage_package_import(
        _valid_raw_archive(tmp_path / "replacement.cxpkg"),
        target_dir=plugins,
    )

    transaction.activate()
    assert len(list(plugins.glob(".example_package.backup-*"))) == 1
    transaction.commit()
    transaction.commit()

    assert transaction.state is package_manager.PackageInstallState.COMMITTED
    assert (installed / "nodes.py").is_file()
    assert not list(plugins.glob(".example_package.*"))
    with pytest.raises(RuntimeError, match="committed"):
        transaction.rollback()


def test_activation_failure_restores_prior_install_and_stays_staged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugins = tmp_path / "plugins"
    installed = plugins / "example_package"
    installed.mkdir(parents=True)
    sentinel = installed / "keep.txt"
    sentinel.write_text("original", encoding="utf-8")
    transaction = package_manager.stage_package_import(
        _valid_raw_archive(tmp_path / "replacement.cxpkg"),
        target_dir=plugins,
    )
    original_replace = Path.replace

    def fail_staged_activation(path: Path, target: Path) -> Path:
        if path == transaction.staged_package_root:
            raise OSError("activation failed")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_staged_activation)
    with pytest.raises(ValueError) as error:
        transaction.activate()

    assert str(error.value) == "Package import failed [filesystem]"
    assert transaction.state is package_manager.PackageInstallState.STAGED
    assert sentinel.read_text(encoding="utf-8") == "original"
    transaction.rollback()
    assert not list(plugins.glob(".example_package.*"))


def test_staged_rollback_cleanup_failure_is_recoverable_and_path_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugins = tmp_path / "plugins"
    transaction = package_manager.stage_package_import(
        _valid_raw_archive(tmp_path / "staged.cxpkg"),
        target_dir=plugins,
    )
    container = transaction.staged_package_root.parent
    original_rmtree = package_manager.shutil.rmtree
    fail_cleanup = True

    def injected_rmtree(path: Path) -> None:
        if fail_cleanup and Path(path) == container:
            raise OSError(f"cannot remove {path}")
        original_rmtree(path)

    monkeypatch.setattr(package_manager.shutil, "rmtree", injected_rmtree)
    with pytest.raises(RuntimeError) as error:
        transaction.rollback()

    assert str(error.value) == (
        "Package install rollback failed [rollback_staging_cleanup]"
    )
    assert str(tmp_path) not in str(error.value)
    assert transaction.state is package_manager.PackageInstallState.FAILED
    assert transaction.issues == ("rollback_staging_cleanup",)
    assert transaction.staged_package_root.is_dir()
    assert not transaction.installed_package_root.exists()

    fail_cleanup = False
    transaction.rollback()
    transaction.rollback()
    assert transaction.state is package_manager.PackageInstallState.ROLLED_BACK
    assert transaction.issues == ()
    assert not container.exists()


@pytest.mark.parametrize("replacement", [False, True])
def test_activated_rollback_move_failure_preserves_active_install_for_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement: bool,
) -> None:
    plugins = tmp_path / "plugins"
    installed = plugins / "example_package"
    if replacement:
        installed.mkdir(parents=True)
        (installed / "keep.txt").write_text("original", encoding="utf-8")
    transaction = package_manager.stage_package_import(
        _valid_raw_archive(tmp_path / "package.cxpkg"),
        target_dir=plugins,
    )
    transaction.activate()
    staged = transaction.staged_package_root
    original_replace = Path.replace
    fail_move = True

    def injected_replace(path: Path, target: Path) -> Path:
        if fail_move and path == installed and target == staged:
            raise OSError(f"cannot move {path}")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", injected_replace)
    with pytest.raises(RuntimeError) as error:
        transaction.rollback()

    assert str(error.value) == "Package install rollback failed [rollback_active_move]"
    assert str(tmp_path) not in str(error.value)
    assert transaction.state is package_manager.PackageInstallState.FAILED
    assert transaction.issues == ("rollback_active_move",)
    assert (installed / "nodes.py").is_file()

    fail_move = False
    transaction.rollback()
    assert transaction.state is package_manager.PackageInstallState.ROLLED_BACK
    assert transaction.issues == ()
    if replacement:
        assert [path.name for path in installed.iterdir()] == ["keep.txt"]
    else:
        assert not installed.exists()
    assert not list(plugins.glob(".example_package.*"))


@pytest.mark.parametrize("partial_cleanup", [False, True])
def test_new_install_rollback_cleanup_failure_is_recoverable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    partial_cleanup: bool,
) -> None:
    plugins = tmp_path / "plugins"
    transaction = package_manager.stage_package_import(
        _valid_raw_archive(tmp_path / "new.cxpkg"),
        target_dir=plugins,
    )
    transaction.activate()
    container = transaction.staged_package_root.parent
    original_rmtree = package_manager.shutil.rmtree
    fail_cleanup = True

    def injected_rmtree(path: Path) -> None:
        if fail_cleanup and Path(path) == container:
            if partial_cleanup:
                original_rmtree(path)
            raise OSError(f"cannot remove {path}")
        original_rmtree(path)

    monkeypatch.setattr(package_manager.shutil, "rmtree", injected_rmtree)
    with pytest.raises(RuntimeError) as error:
        transaction.rollback()

    assert str(error.value) == (
        "Package install rollback failed [rollback_staging_cleanup]"
    )
    assert transaction.state is package_manager.PackageInstallState.FAILED
    assert not transaction.installed_package_root.exists()
    assert transaction.staged_package_root.is_dir() == (not partial_cleanup)

    fail_cleanup = False
    transaction.rollback()
    assert transaction.state is package_manager.PackageInstallState.ROLLED_BACK
    assert not container.exists()


@pytest.mark.parametrize("fail_active_restore", [False, True])
def test_replacement_prior_restore_failure_preserves_both_versions_for_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fail_active_restore: bool,
) -> None:
    plugins = tmp_path / "plugins"
    installed = plugins / "example_package"
    installed.mkdir(parents=True)
    (installed / "keep.txt").write_text("original", encoding="utf-8")
    transaction = package_manager.stage_package_import(
        _valid_raw_archive(tmp_path / "replacement.cxpkg"),
        target_dir=plugins,
    )
    transaction.activate()
    backup = transaction._backup_root
    assert backup is not None
    original_replace = Path.replace
    inject_failures = True

    def injected_replace(path: Path, target: Path) -> Path:
        if inject_failures and path == backup and target == installed:
            raise OSError(f"cannot restore {path}")
        if (
            inject_failures
            and fail_active_restore
            and path == transaction.staged_package_root
            and target == installed
        ):
            raise OSError(f"cannot republish {path}")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", injected_replace)
    with pytest.raises(RuntimeError) as error:
        transaction.rollback()

    expected_issues = ("rollback_prior_restore",) + (
        ("rollback_active_restore",) if fail_active_restore else ()
    )
    assert transaction.state is package_manager.PackageInstallState.FAILED
    assert transaction.issues == expected_issues
    assert str(tmp_path) not in str(error.value)
    assert (backup / "keep.txt").read_text(encoding="utf-8") == "original"
    if fail_active_restore:
        assert not installed.exists()
        assert (transaction.staged_package_root / "nodes.py").is_file()
    else:
        assert (installed / "nodes.py").is_file()
        assert not transaction.staged_package_root.exists()

    inject_failures = False
    transaction.rollback()
    assert transaction.state is package_manager.PackageInstallState.ROLLED_BACK
    assert transaction.issues == ()
    assert [path.name for path in installed.iterdir()] == ["keep.txt"]
    assert not list(plugins.glob(".example_package.*"))


def test_activation_backup_move_failure_leaves_prior_install_untouched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugins = tmp_path / "plugins"
    installed = plugins / "example_package"
    installed.mkdir(parents=True)
    sentinel = installed / "keep.txt"
    sentinel.write_text("original", encoding="utf-8")
    transaction = package_manager.stage_package_import(
        _valid_raw_archive(tmp_path / "replacement.cxpkg"),
        target_dir=plugins,
    )
    original_replace = Path.replace
    inject_failure = True

    def injected_replace(path: Path, target: Path) -> Path:
        if inject_failure and path == installed and ".backup-" in Path(target).name:
            raise OSError(f"cannot back up {path}")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", injected_replace)
    with pytest.raises(ValueError) as error:
        transaction.activate()

    assert str(error.value) == "Package import failed [filesystem]"
    assert str(tmp_path) not in str(error.value)
    assert transaction.state is package_manager.PackageInstallState.STAGED
    assert sentinel.read_text(encoding="utf-8") == "original"
    assert transaction.staged_package_root.is_dir()

    inject_failure = False
    transaction.rollback()
    assert transaction.state is package_manager.PackageInstallState.ROLLED_BACK
    assert sentinel.read_text(encoding="utf-8") == "original"
    assert not list(plugins.glob(".example_package.*"))


def test_activation_restore_failure_can_be_rolled_back_without_data_loss(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugins = tmp_path / "plugins"
    installed = plugins / "example_package"
    installed.mkdir(parents=True)
    (installed / "keep.txt").write_text("original", encoding="utf-8")
    transaction = package_manager.stage_package_import(
        _valid_raw_archive(tmp_path / "replacement.cxpkg"),
        target_dir=plugins,
    )
    original_replace = Path.replace
    inject_failures = True

    def injected_replace(path: Path, target: Path) -> Path:
        if inject_failures and path == transaction.staged_package_root:
            raise OSError(f"cannot activate {path}")
        if inject_failures and ".backup-" in path.name and target == installed:
            raise OSError(f"cannot restore {path}")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", injected_replace)
    with pytest.raises(ValueError) as error:
        transaction.activate()

    backup = transaction._backup_root
    assert backup is not None
    assert str(error.value) == "Package import failed [filesystem]"
    assert transaction.state is package_manager.PackageInstallState.FAILED
    assert transaction.issues == ("activation_prior_restore",)
    assert not installed.exists()
    assert (backup / "keep.txt").is_file()
    assert transaction.staged_package_root.is_dir()

    inject_failures = False
    transaction.rollback()
    assert transaction.state is package_manager.PackageInstallState.ROLLED_BACK
    assert [path.name for path in installed.iterdir()] == ["keep.txt"]
    assert not list(plugins.glob(".example_package.*"))


def test_import_recovers_from_one_failed_activation_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugins = tmp_path / "plugins"
    installed = plugins / "example_package"
    installed.mkdir(parents=True)
    (installed / "keep.txt").write_text("original", encoding="utf-8")
    archive = _valid_raw_archive(tmp_path / "replacement.cxpkg")
    original_replace = Path.replace
    restore_attempts = 0

    def injected_replace(path: Path, target: Path) -> Path:
        nonlocal restore_attempts
        if path.parent.name.startswith(".example_package.incoming-"):
            raise OSError(f"cannot activate {path}")
        if ".backup-" in path.name and target == installed:
            restore_attempts += 1
            if restore_attempts == 1:
                raise OSError(f"cannot restore {path}")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", injected_replace)
    with pytest.raises(ValueError) as error:
        package_manager.import_package(archive, target_dir=plugins)

    assert str(error.value) == "Package import failed [filesystem]"
    assert str(tmp_path) not in str(error.value)
    assert restore_attempts == 2
    assert [path.name for path in installed.iterdir()] == ["keep.txt"]
    assert not list(plugins.glob(".example_package.*"))


def test_committed_cleanup_failures_are_observable_without_undoing_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugins = tmp_path / "plugins"
    installed = plugins / "example_package"
    installed.mkdir(parents=True)
    (installed / "keep.txt").write_text("original", encoding="utf-8")
    transaction = package_manager.stage_package_import(
        _valid_raw_archive(tmp_path / "replacement.cxpkg"),
        target_dir=plugins,
    )
    transaction.activate()
    backup = transaction._backup_root
    assert backup is not None
    container = transaction.staged_package_root.parent
    original_rmtree = package_manager.shutil.rmtree
    fail_cleanup = True

    def injected_rmtree(path: Path) -> None:
        if fail_cleanup and Path(path) in {backup, container}:
            raise OSError(f"cannot remove {path}")
        original_rmtree(path)

    monkeypatch.setattr(package_manager.shutil, "rmtree", injected_rmtree)
    transaction.commit()

    assert transaction.state is package_manager.PackageInstallState.COMMITTED
    assert transaction.issues == (
        "commit_backup_cleanup",
        "commit_staging_cleanup",
    )
    assert (installed / "nodes.py").is_file()
    assert backup.is_dir()
    assert container.is_dir()

    fail_cleanup = False
    transaction.commit()
    assert transaction.state is package_manager.PackageInstallState.COMMITTED
    assert transaction.issues == ()
    assert (installed / "nodes.py").is_file()
    assert not backup.exists()
    assert not container.exists()


def test_failed_replacement_restores_existing_installed_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugins = tmp_path / "plugins"
    installed = plugins / "example_package"
    installed.mkdir(parents=True)
    sentinel = installed / "keep.txt"
    sentinel.write_text("original", encoding="utf-8")
    archive = _valid_raw_archive(tmp_path / "replacement.cxpkg")
    original_replace = Path.replace
    failed = False

    def fail_staged_activation(path: Path, target: Path) -> Path:
        nonlocal failed
        if (
            not failed
            and path.name == "example_package"
            and path.parent.name.startswith(".example_package.incoming-")
        ):
            failed = True
            raise OSError("activation failed")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_staged_activation)
    with pytest.raises(ValueError) as error:
        package_manager.import_package(archive, target_dir=plugins)

    assert str(error.value) == "Package import failed [filesystem]"
    assert str(tmp_path) not in str(error.value)
    assert "incoming-" not in str(error.value)
    assert sentinel.read_text(encoding="utf-8") == "original"
    assert not list(plugins.glob(".example_package.*"))


def test_export_filesystem_error_is_path_free_and_cleans_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "nodes.py"
    source.write_text(_node_source(), encoding="utf-8")
    destination = tmp_path / "failed-export.cxpkg"
    original_replace = Path.replace

    def fail_publish(path: Path, target: Path) -> Path:
        if Path(target) == destination:
            raise OSError(f"cannot publish {path}")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_publish)
    with pytest.raises(ValueError) as error:
        package_manager.export_package(
            [source],
            package_manager.PackageManifest(name="failed_export"),
            destination,
        )

    assert str(error.value) == "Package export failed [filesystem]"
    assert str(tmp_path) not in str(error.value)
    assert not destination.exists()
    assert not list(tmp_path.glob(".failed-export.export-*"))
    assert not list(tmp_path.glob(".failed_export.archive-validation-*"))


def test_cleanup_failure_logs_only_a_bounded_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    staging = tmp_path / ".example.incoming-secret"
    staging.mkdir()

    def fail_cleanup(_path: Path) -> None:
        raise OSError(f"cannot remove {staging}")

    monkeypatch.setattr(package_manager.shutil, "rmtree", fail_cleanup)
    assert not package_manager._cleanup_path(staging, code="import_staging")

    assert "Package cleanup failed [import_staging]" in caplog.text
    assert str(tmp_path) not in caplog.text
    assert "incoming-secret" not in caplog.text
    monkeypatch.undo()
    assert package_manager._cleanup_path(staging, code="import_staging")
    assert package_manager._cleanup_path(staging, code="import_staging")


def test_list_and_uninstall_validate_schema2_packages(tmp_path: Path) -> None:
    archive = _valid_raw_archive(tmp_path / "installed.cxpkg")
    plugins = tmp_path / "plugins"
    package_manager.import_package(archive, target_dir=plugins)

    manifests = package_manager.list_installed_packages(target_dir=plugins)
    assert [(item.name, item.nodes) for item in manifests] == [
        ("example_package", [TYPE_ID])
    ]
    assert package_manager.uninstall_package("example_package", target_dir=plugins) is True
    assert package_manager.uninstall_package("example_package", target_dir=plugins) is False
    with pytest.raises(ValueError):
        package_manager.uninstall_package("../escape", target_dir=plugins)
