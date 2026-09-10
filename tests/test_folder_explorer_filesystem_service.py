from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from ea_node_editor.ui.folder_explorer import (
    FolderExplorerClipboard,
    FolderExplorerFilesystemService,
    FolderExplorerServiceError,
)


class FolderExplorerFilesystemServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FolderExplorerFilesystemService()

    @staticmethod
    def _write_file(path: Path, text: str, *, modified_timestamp: float | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if modified_timestamp is not None:
            os.utime(path, (modified_timestamp, modified_timestamp))

    def test_list_directory_returns_normalized_metadata_with_folders_before_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            folder = root / "Beta"
            folder.mkdir()
            text_file = root / "alpha.TXT"
            self._write_file(text_file, "alpha")
            binary_file = root / "gamma.bin"
            self._write_file(binary_file, "payload")

            listing = self.service.list_directory(root)

        self.assertEqual(listing.directory_path, str(root.resolve(strict=False)))
        self.assertEqual(listing.parent_path, str(root.parent.resolve(strict=False)))
        self.assertEqual([entry.name for entry in listing.entries], ["Beta", "alpha.TXT", "gamma.bin"])
        self.assertGreaterEqual(len(listing.breadcrumbs), 2)
        self.assertEqual(listing.breadcrumbs[-1].absolute_path, str(root.resolve(strict=False)))

        entries_by_name = {entry.name: entry for entry in listing.entries}
        self.assertEqual(entries_by_name["Beta"].kind, "folder")
        self.assertEqual(entries_by_name["Beta"].type_label, "File folder")
        self.assertEqual(entries_by_name["Beta"].display_size, "")
        self.assertIsNone(entries_by_name["Beta"].size_bytes)
        self.assertEqual(entries_by_name["alpha.TXT"].kind, "file")
        self.assertEqual(entries_by_name["alpha.TXT"].absolute_path, str(text_file.resolve(strict=False)))
        self.assertEqual(entries_by_name["alpha.TXT"].extension, ".txt")
        self.assertEqual(entries_by_name["alpha.TXT"].type_label, "TXT File")
        self.assertEqual(entries_by_name["alpha.TXT"].display_size, "5 bytes")
        self.assertIsInstance(entries_by_name["alpha.TXT"].modified_timestamp, float)

    def test_list_directory_returns_breadcrumb_targets_for_temp_navigation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parent = root / "Alpha"
            child = parent / "Beta"
            child.mkdir(parents=True)

            listing = self.service.list_directory(child)

        self.assertEqual(listing.directory_path, str(child.resolve(strict=False)))
        self.assertEqual(listing.parent_path, str(parent.resolve(strict=False)))
        self.assertGreaterEqual(len(listing.breadcrumbs), 2)
        self.assertEqual(
            [(crumb.name, crumb.absolute_path) for crumb in listing.breadcrumbs[-2:]],
            [
                ("Alpha", str(parent.resolve(strict=False))),
                ("Beta", str(child.resolve(strict=False))),
            ],
        )

    def test_filtering_is_case_insensitive_and_does_not_mutate_filesystem(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            keep = root / "Report.TXT"
            skip = root / "image.png"
            self._write_file(keep, "report")
            self._write_file(skip, "image")

            listing = self.service.list_directory(root, filter_text="report")

            self.assertEqual([entry.name for entry in listing.entries], ["Report.TXT"])
            self.assertTrue(keep.exists())
            self.assertTrue(skip.exists())

    def test_sorting_supports_type_size_modified_and_reversed_name_groups(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "AlphaFolder").mkdir()
            (root / "ZuluFolder").mkdir()
            os.utime(root / "AlphaFolder", (1_700_000_010, 1_700_000_010))
            os.utime(root / "ZuluFolder", (1_700_000_020, 1_700_000_020))
            self._write_file(root / "small.txt", "1", modified_timestamp=1_700_000_100)
            self._write_file(root / "large.bin", "123456789", modified_timestamp=1_700_000_000)

            by_type = self.service.list_directory(root, sort_key="type")
            by_size = self.service.list_directory(root, sort_key="size")
            by_modified_desc = self.service.list_directory(root, sort_key="modified", reverse=True)
            by_name_desc = self.service.list_directory(root, sort_key="name", reverse=True)

        self.assertEqual([entry.name for entry in by_type.entries], ["large.bin", "AlphaFolder", "ZuluFolder", "small.txt"])
        self.assertEqual([entry.name for entry in by_size.entries], ["AlphaFolder", "ZuluFolder", "small.txt", "large.bin"])
        self.assertEqual(by_modified_desc.entries[0].name, "small.txt")
        self.assertEqual(
            [entry.name for entry in by_name_desc.entries],
            ["ZuluFolder", "AlphaFolder", "small.txt", "large.bin"],
        )

    def test_invalid_listing_inputs_raise_structured_service_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file_path = root / "not-a-folder.txt"
            self._write_file(file_path, "content")

            with self.assertRaises(FolderExplorerServiceError) as missing_error:
                self.service.list_directory(root / "missing")
            with self.assertRaises(FolderExplorerServiceError) as not_directory_error:
                self.service.list_directory(file_path)
            with self.assertRaises(FolderExplorerServiceError) as invalid_sort_error:
                self.service.list_directory(root, sort_key="created")  # type: ignore[arg-type]

        self.assertEqual(missing_error.exception.code, "not_found")
        self.assertEqual(missing_error.exception.operation, "list")
        self.assertIn("path", missing_error.exception.to_dict())
        self.assertEqual(not_directory_error.exception.code, "not_directory")
        self.assertEqual(invalid_sort_error.exception.code, "invalid_sort_key")

    def test_new_folder_rename_and_delete_require_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            with self.assertRaises(FolderExplorerServiceError) as new_folder_error:
                self.service.new_folder(root, "Drafts")
            self.assertEqual(new_folder_error.exception.code, "confirmation_required")
            self.assertFalse((root / "Drafts").exists())

            created = self.service.new_folder(root, "Drafts", confirmed=True)
            self.assertEqual(created.kind, "folder")
            self.assertTrue((root / "Drafts").is_dir())

            with self.assertRaises(FolderExplorerServiceError) as rename_error:
                self.service.rename(root / "Drafts", "Renamed")
            self.assertEqual(rename_error.exception.code, "confirmation_required")
            self.assertTrue((root / "Drafts").exists())
            self.assertFalse((root / "Renamed").exists())

            renamed = self.service.rename(root / "Drafts", "Renamed", confirmed=True)
            self.assertEqual(renamed.name, "Renamed")
            self.assertFalse((root / "Drafts").exists())
            self.assertTrue((root / "Renamed").is_dir())

            with self.assertRaises(FolderExplorerServiceError) as delete_error:
                self.service.delete(root / "Renamed")
            self.assertEqual(delete_error.exception.code, "confirmation_required")
            self.assertTrue((root / "Renamed").exists())

            self.service.delete(root / "Renamed", confirmed=True)
            self.assertFalse((root / "Renamed").exists())

    def test_confirmed_delete_removes_only_selected_temp_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            selected = root / "selected"
            selected.mkdir()
            self._write_file(selected / "child.txt", "selected")
            sibling = root / "sibling.txt"
            self._write_file(sibling, "sibling")

            self.service.delete(selected, confirmed=True)

            self.assertFalse(selected.exists())
            self.assertTrue(sibling.exists())

    def test_copy_and_paste_require_confirmation_and_fail_fast_on_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.txt"
            self._write_file(source, "source")
            destination = root / "destination"
            destination.mkdir()

            with self.assertRaises(FolderExplorerServiceError) as copy_error:
                self.service.copy(source)
            self.assertEqual(copy_error.exception.code, "confirmation_required")
            self.assertIsNone(self.service.clipboard)

            clipboard = self.service.copy(source, confirmed=True)
            self.assertEqual(clipboard.mode, "copy")
            with self.assertRaises(FolderExplorerServiceError) as paste_error:
                self.service.paste(destination)
            self.assertEqual(paste_error.exception.code, "confirmation_required")
            self.assertFalse((destination / "source.txt").exists())

            pasted = self.service.paste(destination, confirmed=True)
            self.assertEqual(pasted.name, "source.txt")
            self.assertEqual((destination / "source.txt").read_text(encoding="utf-8"), "source")
            self.assertTrue(source.exists())

            with self.assertRaises(FolderExplorerServiceError) as collision_error:
                self.service.paste(destination, confirmed=True)
            self.assertEqual(collision_error.exception.code, "already_exists")
            self.assertEqual((destination / "source.txt").read_text(encoding="utf-8"), "source")

    def test_cut_and_paste_moves_source_and_clears_internal_clipboard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_dir = root / "source-dir"
            source_dir.mkdir()
            self._write_file(source_dir / "child.txt", "child")
            destination = root / "destination"
            destination.mkdir()

            clipboard = self.service.cut(source_dir, confirmed=True)
            moved = self.service.paste(destination, confirmed=True)

            self.assertEqual(clipboard.mode, "cut")
            self.assertEqual(moved.kind, "folder")
            self.assertFalse(source_dir.exists())
            self.assertEqual((destination / "source-dir" / "child.txt").read_text(encoding="utf-8"), "child")
            self.assertIsNone(self.service.clipboard)

    def test_external_clipboard_can_copy_directory_without_overwriting_existing_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_dir = root / "source-dir"
            source_dir.mkdir()
            self._write_file(source_dir / "child.txt", "child")
            destination = root / "destination"
            destination.mkdir()
            external_clipboard = FolderExplorerClipboard(
                source_path=str(source_dir.resolve(strict=False)),
                mode="copy",
            )

            self.service.paste(destination, clipboard=external_clipboard, confirmed=True)
            with self.assertRaises(FolderExplorerServiceError) as collision_error:
                self.service.paste(destination, clipboard=external_clipboard, confirmed=True)

            self.assertEqual(collision_error.exception.code, "already_exists")
            self.assertTrue(source_dir.exists())
            self.assertEqual((destination / "source-dir" / "child.txt").read_text(encoding="utf-8"), "child")

    def test_copy_path_returns_normalized_path_and_optional_quotes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "copy me.txt"
            self._write_file(target, "content")

            plain = self.service.copy_path(target)
            quoted = self.service.copy_path(target, quote=True)

        self.assertEqual(plain, str(target.resolve(strict=False)))
        self.assertEqual(quoted, f'"{target.resolve(strict=False)}"')

    def test_parent_path_returns_none_for_filesystem_root(self) -> None:
        root_anchor = Path.cwd().anchor
        if not root_anchor:
            self.skipTest("Current platform does not expose a pathlib anchor.")

        self.assertIsNone(self.service.parent_path(Path(root_anchor)))


if __name__ == "__main__":
    unittest.main()
