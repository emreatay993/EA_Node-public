from __future__ import annotations

import unittest

from ea_node_editor.ui.icon_registry import (
    DEFAULT_ICON_COLOR,
    UiIconRegistryBridge,
    icon_names,
    icon_path,
    icon_pixmap,
)


class IconRegistryTests(unittest.TestCase):
    def test_known_icons_resolve_to_existing_files(self) -> None:
        for name in (
            "code",
            "crop",
            "door-enter",
            "open-session",
            "run",
            "node-run",
            "node-expand",
            "node-collapse",
            "pause",
            "resume",
            "stop",
            "step",
            "focus",
            "zoom-fit",
            "keep-live",
            "clock-update",
            "calendar",
            "pin",
            "more",
            "palette",
            "arrow-right",
            "navigate",
            "navigate-previous",
            "navigate-next",
            "rotate-clockwise",
            "flip-horizontal",
            "flip-vertical",
            "path-style",
            "edge-path-solid",
            "edge-path-dashed",
            "edge-path-dotted",
            "edge-arrow-filled",
            "edge-arrow-open",
            "edge-arrow-none",
            "label-off",
            "content-only",
            "node-chrome",
            "title-heading",
            "frame-corners",
            "fit-width",
            "fit-height",
            "settings",
        ):
            self.assertIn(name, icon_names())
            self.assertTrue(icon_path(name).is_file(), name)

    def test_pdf_navigation_icons_resolve_to_existing_files(self) -> None:
        expected = {
            "navigate": "Navigate",
            "navigate-previous": "Previous Page",
            "navigate-next": "Next Page",
            "rotate-clockwise": "Rotate Clockwise",
            "flip-horizontal": "Flip Horizontal",
            "flip-vertical": "Flip Vertical",
        }
        bridge = UiIconRegistryBridge()

        for name, label in expected.items():
            self.assertIn(name, icon_names())
            self.assertTrue(icon_path(name).is_file(), name)
            self.assertTrue(bridge.has(name))
            self.assertEqual(bridge.label(name), label)
            self.assertIn(f"image://ui-icons/{name}?", bridge.sourceSized(name, 16, DEFAULT_ICON_COLOR))

    def test_content_fullscreen_icon_resolves_to_existing_file(self) -> None:
        bridge = UiIconRegistryBridge()

        self.assertIn("fullscreen", icon_names())
        self.assertTrue(icon_path("fullscreen").is_file())
        self.assertTrue(bridge.has("fullscreen"))
        self.assertEqual(bridge.label("fullscreen"), "Fullscreen")
        self.assertEqual(
            bridge.sourceSized("fullscreen", 18, DEFAULT_ICON_COLOR),
            "image://ui-icons/fullscreen?size=18&color=%23D8DEEA",
        )

    def test_viewer_capture_and_copy_action_icons_resolve(self) -> None:
        bridge = UiIconRegistryBridge()
        for name, label in {"export": "Export", "copy": "Copy"}.items():
            self.assertTrue(bridge.has(name))
            self.assertEqual(bridge.label(name), label)
            self.assertTrue(icon_path(name).is_file())

    def test_viewer_render_and_projection_icons_resolve(self) -> None:
        bridge = UiIconRegistryBridge()
        expected = {
            "viewer-wireframe": "Wireframe",
            "viewer-visible-edges": "Visible Edges",
            "viewer-shaded": "Shaded",
            "viewer-body-edges": "Shaded with Body Edges",
            "viewer-mesh-edges": "Mesh or Facet Edges",
            "viewer-attribute-colors": "Attribute Colors",
            "viewer-perspective": "Perspective Projection",
            "viewer-orthographic": "Orthographic Projection",
            "viewer-fit-all": "Fit All",
            "viewer-fit-selection": "Fit Selection",
            "viewer-isolate": "Isolate Selection",
            "viewer-ui-controls": "Viewer UI Controls",
            "viewer-saved-views": "Saved Views",
            "viewer-detach": "Detach Viewer",
            "viewer-dock": "Dock Viewer",
            "viewer-fullscreen": "Fullscreen Viewer",
        }
        for name, label in expected.items():
            self.assertTrue(bridge.has(name))
            self.assertEqual(bridge.label(name), label)
            self.assertTrue(icon_path(name).is_file())
            self.assertEqual(icon_path(name).name, f"{name}.svg")
            image = icon_pixmap(name, size=16, color="#d8deea").toImage()
            self.assertGreater(
                sum(
                    1
                    for y in range(image.height())
                    for x in range(image.width())
                    if image.pixelColor(x, y).alpha() > 32
                ),
                8,
                name,
            )

        wireframe = icon_pixmap("viewer-wireframe", size=20, color="#d8deea").toImage()
        visible_edges = icon_pixmap("viewer-visible-edges", size=20, color="#d8deea").toImage()
        different_pixels = sum(
            1
            for y in range(wireframe.height())
            for x in range(wireframe.width())
            if wireframe.pixelColor(x, y) != visible_edges.pixelColor(x, y)
        )
        self.assertGreater(different_pixels, 20)

    def test_viewer_selection_filter_icons_resolve(self) -> None:
        bridge = UiIconRegistryBridge()
        expected = {
            "viewer-select-vertex": "Select CAD Vertex",
            "viewer-select-edge": "Select CAD Edge",
            "viewer-select-face": "Select CAD Face",
            "viewer-select-body": "Select CAD Body",
            "viewer-select-node": "Select FE Node",
            "viewer-select-element-face": "Select FE Element Face",
            "viewer-select-element": "Select FE Element",
            "viewer-select-tangent": "Tangent Selection Angle",
        }
        for name, label in expected.items():
            self.assertTrue(bridge.has(name))
            self.assertEqual(bridge.label(name), label)
            self.assertTrue(icon_path(name).is_file())
            self.assertEqual(icon_path(name).name, f"{name}.svg")
            image = icon_pixmap(name, size=16, color="#d8deea").toImage()
            self.assertGreater(
                sum(
                    1
                    for y in range(image.height())
                    for x in range(image.width())
                    if image.pixelColor(x, y).alpha() > 32
                ),
                8,
                name,
            )

    def test_attribute_color_icon_preserves_multiple_source_colors(self) -> None:
        image = icon_pixmap("viewer-attribute-colors", size=32, color="#ffffff").toImage()
        colors = {
            image.pixelColor(x, y).name().lower()
            for y in range(image.height())
            for x in range(image.width())
            if image.pixelColor(x, y).alpha() > 200
        }
        self.assertIn("#f3c84b", colors)
        self.assertIn("#ef6572", colors)
        self.assertIn("#29aee8", colors)

    def test_browser_toolbar_icons_resolve_to_existing_files(self) -> None:
        expected = {
            "browser-back": "Back",
            "browser-forward": "Forward",
            "browser-reload": "Reload",
            "browser-stop": "Stop",
            "browser-home": "Home",
            "browser-detach": "Detach",
            "zoom-in": "Zoom In",
            "zoom-out": "Zoom Out",
        }
        bridge = UiIconRegistryBridge()

        for name, label in expected.items():
            self.assertIn(name, icon_names())
            self.assertTrue(icon_path(name).is_file(), name)
            self.assertTrue(bridge.has(name))
            self.assertEqual(bridge.label(name), label)
            self.assertIn(f"image://ui-icons/{name}?", bridge.sourceSized(name, 16, DEFAULT_ICON_COLOR))

    def test_web_page_source_icons_resolve_to_existing_files(self) -> None:
        expected = {
            "file-type-html": "HTML File",
            "folder-open": "Browse Files",
            "world-www": "Web Address",
        }
        bridge = UiIconRegistryBridge()

        for name, label in expected.items():
            self.assertIn(name, icon_names())
            self.assertTrue(icon_path(name).is_file(), name)
            self.assertTrue(bridge.has(name))
            self.assertEqual(bridge.label(name), label)
            self.assertIn(f"image://ui-icons/{name}?", bridge.sourceSized(name, 16, DEFAULT_ICON_COLOR))

    def test_node_link_icons_resolve_to_existing_files(self) -> None:
        expected = {
            "link": "Link",
            "world-www": "Web Address",
            "file-text": "File",
            "folder": "Folder",
            "layout-dashboard": "Workspace",
            "hierarchy-2": "Node",
            "plus": "Add",
            "x": "Remove",
            "external-link": "Open",
            "internalize-source": "Copy Into Project",
            "edit": "Edit",
            "chevron-up": "Expand",
            "chevron-down": "Collapse",
        }
        bridge = UiIconRegistryBridge()

        for name, label in expected.items():
            self.assertIn(name, icon_names())
            self.assertTrue(icon_path(name).is_file(), name)
            self.assertTrue(bridge.has(name))
            self.assertEqual(bridge.label(name), label)
            self.assertIn(f"image://ui-icons/{name}?", bridge.sourceSized(name, 16, DEFAULT_ICON_COLOR))

    def test_node_comment_action_icons_resolve_to_existing_files(self) -> None:
        expected = {
            "comment": "Comment",
            "reply": "Reply",
            "edit": "Edit",
            "pin": "Pin",
            "pin-off": "Unpin",
            "check": "Check",
            "rotate-clockwise": "Rotate Clockwise",
            "delete": "Delete",
            "send": "Send",
            "x": "Remove",
        }
        bridge = UiIconRegistryBridge()

        for name, label in expected.items():
            self.assertIn(name, icon_names())
            self.assertTrue(icon_path(name).is_file(), name)
            self.assertTrue(bridge.has(name))
            self.assertEqual(bridge.label(name), label)
            self.assertIn(f"image://ui-icons/{name}?", bridge.sourceSized(name, 16, DEFAULT_ICON_COLOR))

    def test_video_toolbar_volume_icons_resolve_to_existing_files(self) -> None:
        expected = {
            "volume": "Volume",
            "volume-muted": "Muted",
        }
        bridge = UiIconRegistryBridge()

        for name, label in expected.items():
            self.assertIn(name, icon_names())
            self.assertTrue(icon_path(name).is_file(), name)
            self.assertTrue(bridge.has(name))
            self.assertEqual(bridge.label(name), label)
            self.assertIn(f"image://ui-icons/{name}?", bridge.sourceSized(name, 16, DEFAULT_ICON_COLOR))

    def test_video_panel_toolbar_icons_resolve_to_existing_files(self) -> None:
        expected = {
            "video-bookmarks": "Video Bookmarks",
            "video-bookmark-add": "Add Video Bookmark",
            "video-bookmark-jump": "Jump To Video Bookmark",
            "video-capture-frame": "Capture Video Frame",
            "video-timestamp-note": "Timestamp Note",
            "video-clip-range": "Video Clip Range",
            "video-clip-in": "Set Clip In",
            "video-clip-out": "Set Clip Out",
            "video-trim-save": "Save Trimmed Video",
            "video-seek-back-10": "Seek Back 10 Seconds",
            "video-seek-forward-10": "Seek Forward 10 Seconds",
            "video-rewind": "Rewind Video",
            "video-fit": "Fit Video",
            "video-fill": "Fill Video",
            "video-loop": "Loop Video",
        }
        bridge = UiIconRegistryBridge()

        for name, label in expected.items():
            self.assertIn(name, icon_names())
            self.assertTrue(icon_path(name).is_file(), name)
            self.assertTrue(bridge.has(name))
            self.assertEqual(bridge.label(name), label)
            self.assertIn(f"image://ui-icons/{name}?", bridge.sourceSized(name, 16, DEFAULT_ICON_COLOR))

    def test_annotation_text_toolbar_icons_resolve_to_existing_files(self) -> None:
        expected = {
            "text-decrease": "Decrease Text Size",
            "text-increase": "Increase Text Size",
            "format-bold-italic": "Bold Italic",
            "format-bold": "Bold",
            "format-italic": "Italic",
            "format-align-left": "Align Left",
            "format-align-center": "Align Center",
            "format-align-right": "Align Right",
            "format-align-justify": "Justify",
            "format-list-bulleted": "Bulleted List",
            "format-list-numbered": "Numbered List",
            "text-wrap": "Wrap Text",
            "text-color": "Text Color",
            "color-picker": "Pick Color",
            "circle-filled": "Color Swatch",
            "copy-text-style": "Copy Text Style",
            "paste-text-style": "Paste Text Style",
        }
        bridge = UiIconRegistryBridge()

        for name, label in expected.items():
            self.assertIn(name, icon_names())
            self.assertTrue(icon_path(name).is_file(), name)
            self.assertTrue(bridge.has(name))
            self.assertEqual(bridge.label(name), label)
            self.assertIn(f"image://ui-icons/{name}?", bridge.sourceSized(name, 16, DEFAULT_ICON_COLOR))

    def test_timestamp_toolbar_icons_keep_tabler_provenance_notice(self) -> None:
        icon_root = icon_path("calendar").parent
        source_notice = (icon_root / "TABLER_SOURCES.txt").read_text(encoding="utf-8")
        license_notice = (icon_root / "TABLER_LICENSE.txt").read_text(encoding="utf-8")

        self.assertIn("https://github.com/tabler/tabler-icons", source_notice)
        self.assertIn("icons/outline/calendar.svg", source_notice)
        self.assertIn("icons/outline/clock-up.svg", source_notice)
        self.assertIn("icons/outline/door-enter.svg", source_notice)
        self.assertIn("icons/outline/text-increase.svg", source_notice)
        self.assertIn("icons/outline/align-justified.svg", source_notice)
        self.assertIn("icons/outline/list.svg", source_notice)
        self.assertIn("icons/outline/list-numbers.svg", source_notice)
        self.assertIn("icons/outline/color-picker.svg", source_notice)
        self.assertIn("icons/filled/circle.svg", source_notice)
        self.assertIn("icons/outline/arrows-horizontal.svg", source_notice)
        self.assertIn("icons/outline/chevron-left.svg", source_notice)
        self.assertIn("icons/outline/chevron-right.svg", source_notice)
        self.assertIn("icons/outline/rotate-clockwise.svg", source_notice)
        self.assertIn("icons/outline/flip-horizontal.svg", source_notice)
        self.assertIn("icons/outline/flip-vertical.svg", source_notice)
        self.assertIn("icons/outline/focus-2.svg", source_notice)
        self.assertIn("icons/outline/layout-navbar.svg", source_notice)
        self.assertIn("icons/outline/heading.svg", source_notice)
        self.assertIn("icons/outline/border-corners.svg", source_notice)
        self.assertIn("copy-text-style.svg", source_notice)
        self.assertIn("paste-text-style.svg", source_notice)
        self.assertIn("icons/outline/link.svg", source_notice)
        self.assertIn("icons/outline/file-text.svg", source_notice)
        self.assertIn("icons/outline/file-type-html.svg", source_notice)
        self.assertIn("icons/outline/folder.svg", source_notice)
        self.assertIn("icons/outline/folder-open.svg", source_notice)
        self.assertIn("icons/outline/layout-dashboard.svg", source_notice)
        self.assertIn("icons/outline/hierarchy-2.svg", source_notice)
        self.assertIn("icons/outline/world-www.svg", source_notice)
        self.assertIn("icons/outline/plus.svg", source_notice)
        self.assertIn("icons/outline/x.svg", source_notice)
        self.assertIn("icons/outline/external-link.svg", source_notice)
        self.assertIn("icons/outline/package-import.svg", source_notice)
        self.assertIn("icons/outline/edit.svg", source_notice)
        self.assertIn("icons/outline/chevron-up.svg", source_notice)
        self.assertIn("icons/outline/chevron-down.svg", source_notice)
        self.assertIn("icons/outline/bookmarks.svg", source_notice)
        self.assertIn("icons/outline/bookmark-plus.svg", source_notice)
        self.assertIn("icons/outline/bookmark.svg", source_notice)
        self.assertIn("icons/outline/camera-plus.svg", source_notice)
        self.assertIn("icons/outline/clock-edit.svg", source_notice)
        self.assertIn("icons/outline/scissors.svg", source_notice)
        self.assertIn("icons/outline/brackets-contain-start.svg", source_notice)
        self.assertIn("icons/outline/brackets-contain-end.svg", source_notice)
        self.assertIn("icons/outline/rewind-backward-10.svg", source_notice)
        self.assertIn("icons/outline/rewind-forward-10.svg", source_notice)
        self.assertIn("icons/outline/player-track-prev.svg", source_notice)
        self.assertIn("icons/outline/aspect-ratio.svg", source_notice)
        self.assertIn("icons/outline/crop.svg", source_notice)
        self.assertIn("icons/outline/repeat.svg", source_notice)
        self.assertIn("icons/outline/arrow-back-up.svg", source_notice)
        self.assertIn("icons/outline/check.svg", source_notice)
        self.assertIn("icons/outline/pinned-off.svg", source_notice)
        self.assertIn("icons/outline/send.svg", source_notice)
        self.assertIn("MIT License", license_notice)

    def test_bridge_exposes_label_and_provider_url(self) -> None:
        bridge = UiIconRegistryBridge()
        self.assertTrue(bridge.has("run"))
        self.assertEqual(bridge.label("run"), "Run")
        self.assertTrue(bridge.has("open-session"))
        self.assertEqual(bridge.label("open-session"), "Open Session")
        self.assertTrue(bridge.has("door-enter"))
        self.assertEqual(bridge.label("door-enter"), "Enter Subnode")

        source = bridge.sourceSized("pause", 20, DEFAULT_ICON_COLOR)
        self.assertEqual(source, "image://ui-icons/pause?size=20&color=%23D8DEEA")

    def test_unknown_icons_fail_closed(self) -> None:
        bridge = UiIconRegistryBridge()
        self.assertFalse(bridge.has("missing"))
        self.assertEqual(bridge.label("missing"), "missing")
        self.assertEqual(bridge.sourceSized("missing", 16, DEFAULT_ICON_COLOR), "")


if __name__ == "__main__":
    unittest.main()
