# Purpose: Prove shared external paste/drop detection, literal alternatives, and owned snapshots.
# Map: feature_routes/clipboard_undo_redo_mutation_history.md
# Tests: tests/test_canvas_import_inputs.py
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QMimeData, QUrl
from PyQt6.QtGui import QImage

from ea_node_editor.nodes.builtins.data_control import PANEL_MODE_TEXT
from ea_node_editor.ui.shell.clipboard_paste_nodes import (
    CanvasImportSnapshot,
    capture_canvas_drop,
    capture_canvas_mime_data,
    classify_canvas_import,
    clipboard_paste_items_signature,
)
from ea_node_editor.ui.shell.runtime_clipboard import (
    GRAPH_FRAGMENT_MIME_TYPE,
    build_graph_fragment_payload,
)


def _detected(source):
    return source.choice(source.detected_choice).item


@pytest.mark.parametrize("name,choice,type_id,key", [
    ("image.PNG", "media", "media.panel", "source"),
    ("document.pdf", "media", "media.panel", "source"),
    ("movie.mp4", "media", "media.panel", "source"),
    ("message.eml", "mail", "passive.media.mail_panel", "source_path"),
    ("message.msg", "mail", "passive.media.mail_panel", "source_path"),
    ("message.oft", "mail", "passive.media.mail_panel", "source_path"),
    ("page.HTML", "web", "web.page_viewer", "start_location"),
    ("page.xhtml", "web", "web.page_viewer", "start_location"),
    ("data.xlsx", "path", "io.path_pointer", "path"),
    ("solver.rst", "path", "io.path_pointer", "path"),
    ("notes.txt", "path", "io.path_pointer", "path"),
    ("unknown", "path", "io.path_pointer", "path"),
])
def test_local_file_mapping_and_literal_choices_match_both_gestures(tmp_path, name, choice, type_id, key):
    path = str(tmp_path / name)
    url = QUrl.fromLocalFile(path)
    mime = QMimeData()
    mime.setUrls([url])
    for snapshot in (capture_canvas_mime_data(mime), capture_canvas_drop([url])):
        source, = classify_canvas_import(snapshot)
        item = _detected(source)
        assert source.detected_choice == choice
        assert item.type_id == type_id
        assert Path(item.properties[key]) == Path(path)
        assert Path(source.choice("path").item.properties["path"]) == Path(path)
        literal = source.choice("text").item.properties["text"]
        assert Path(literal) == Path(path)
        assert source.choice("text").item.properties["format"] == "plain"
        assert source.choice("panel").item.properties == {
            "value": literal, "mode": PANEL_MODE_TEXT, "parse_numbers": False,
        }
        assert source.choice("skip").item is None


def test_real_folder_and_folder_explorer_hint_override_media_suffix(tmp_path):
    folder = tmp_path / "folder.pdf"
    folder.mkdir()
    snapshots = (
        capture_canvas_drop([QUrl.fromLocalFile(str(folder))]),
        capture_canvas_drop([r"C:\not-mounted\folder.mp4"], folder_hints=[True]),
    )
    for snapshot in snapshots:
        source, = classify_canvas_import(snapshot)
        assert source.detected_choice == "path"
        assert _detected(source).properties["mode"] == "folder"
        assert [choice.key for choice in source.choices] == ["path", "text", "panel", "skip"]


def test_mixed_file_url_batch_keeps_order_and_every_source(tmp_path):
    locations = [
        QUrl.fromLocalFile(str(tmp_path / "image.png")),
        QUrl.fromLocalFile(str(tmp_path / "model.step")),
        QUrl("https://example.test/a.pdf?token=a%2Fb#page=2"),
        QUrl.fromLocalFile(str(tmp_path)),
        QUrl.fromLocalFile(str(tmp_path / "page.html")),
    ]
    mime = QMimeData()
    mime.setUrls(locations)
    mime.setText("Some application-provided extra text")
    mime.setHtml("<p>Extra format</p>")
    mime.setData("application/pdf", b"%PDF-binary-alternative")
    snapshots = (capture_canvas_mime_data(mime), capture_canvas_drop(locations))
    for snapshot in snapshots:
        sources = classify_canvas_import(snapshot)
        assert [source.detected_choice for source in sources] == ["media", "path", "media", "path", "web"]
        assert _detected(sources[2]).properties["source"] == locations[2].toString(QUrl.ComponentFormattingOption.FullyEncoded)
    assert snapshots[0].text == "Some application-provided extra text"
    assert snapshots[0].html == "<p>Extra format</p>"
    assert snapshots[0].media[0].data == b"%PDF-binary-alternative"


@pytest.mark.parametrize("url,choice", [
    ("https://example.test/a%20b.PDF?token=a%2Fb%2BC#page=4", "media"),
    ("http://example.test/video.mp4?download=1#t=10", "media"),
    ("https://example.test/report?filename=graph.png#top", "web"),
    ("https://example.test/mail.eml", "web"),
    ("https://example.test/docs/", "web"),
])
def test_remote_url_spelling_is_not_a_local_path_for_paste_or_drop(url, choice):
    mime = QMimeData()
    mime.setText(url)
    for snapshot in (capture_canvas_mime_data(mime), capture_canvas_drop([url])):
        source, = classify_canvas_import(snapshot)
        item = _detected(source)
        assert source.detected_choice == choice
        assert list(item.properties.values()) == [url]
        assert source.choice("text").item.properties["text"] == url
        assert source.choice("panel").item.properties["value"] == url
        assert "path" not in {choice.key for choice in source.choices}


def test_qurl_mime_keeps_percent_encoding_query_and_fragment():
    url = "https://example.test/a%20b.pdf?token=a%2Fb%2BC#page=4"
    mime = QMimeData()
    mime.setUrls([QUrl(url)])
    source, = classify_canvas_import(capture_canvas_mime_data(mime))
    assert _detected(source).properties["source"] == url
    assert source.choice("panel").item.properties["value"] == url


def test_snapshot_owns_image_and_all_encoded_media_after_clipboard_changes():
    image = QImage(3, 2, QImage.Format.Format_ARGB32)
    image.fill(0xff102030)
    mime = QMimeData()
    mime.setImageData(image)
    mime.setData("application/pdf", b"%PDF-original")
    mime.setData("video/mp4", b"original-video")
    mime.setText("Original image description")
    mime.setHtml("<p>Original image description</p>")
    snapshot = capture_canvas_mime_data(mime)
    mime.clear()
    image.fill(0xffabcdef)
    assert snapshot.text == "Original image description"
    assert snapshot.html == "<p>Original image description</p>"
    assert snapshot.media[0].data.startswith(b"\x89PNG")
    assert [payload.data for payload in snapshot.media[1:]] == [b"%PDF-original", b"original-video"]
    source, = classify_canvas_import(snapshot)
    assert _detected(source).artifact == snapshot.media[0]
    for key, property_key in (("text", "text"), ("panel", "value")):
        choice = source.choice(key)
        assert choice.item.artifact is None
        assert choice.item.properties[property_key] == "Original image description"
        assert not choice.explanation
    assert source.choice("formatted_text").item.properties == {
        "text": "Original image description", "format": "markdown",
    }


@pytest.mark.parametrize("mime_type,filename", [
    ("application/pdf", "clipboard-document.pdf"),
    ("video/mp4", "clipboard-video.mp4"),
    ("image/svg+xml", "clipboard-image.svg"),
])
def test_raw_media_recipes_capture_bytes_without_filesystem_writes(mime_type, filename):
    mime = QMimeData()
    mime.setData(mime_type, b"source-bytes")
    with patch.object(Path, "write_bytes", side_effect=AssertionError("classification wrote a file")), \
         patch.object(Path, "read_bytes", side_effect=AssertionError("classification read a file")):
        source, = classify_canvas_import(capture_canvas_mime_data(mime))
    assert source.detected_choice == "media"
    assert _detected(source).artifact.filename == filename
    assert _detected(source).artifact.data == b"source-bytes"
    for key, property_key in (("text", "text"), ("panel", "value")):
        choice = source.choice(key)
        assert choice.item.artifact.data == b"source-bytes"
        assert choice.item.artifact.property_key == property_key
        assert choice.item.properties[property_key] == ""
        assert "managed reference" in choice.explanation


@pytest.mark.parametrize("explicit_text", [None, "  Selected paragraph\r\n"])
def test_browser_source_url_does_not_replace_selected_paragraph(explicit_text):
    url = "https://example.test/source%20page?key=a%2Fb#part"
    mime = QMimeData()
    mime.setUrls([QUrl(url)])
    mime.setHtml("<p>Selected paragraph</p>")
    if explicit_text is not None:
        mime.setText(explicit_text)
    for snapshot in (
        capture_canvas_mime_data(mime),
        capture_canvas_drop([url], text=explicit_text or "", html=mime.html()),
    ):
        source, = classify_canvas_import(snapshot)
        assert source.detected_choice == "formatted_text"
        assert _detected(source).properties == {"text": "Selected paragraph", "format": "markdown"}
        assert source.choice("text").item.properties["text"] == (explicit_text or "Selected paragraph")
        assert source.choice("panel").item.properties["value"] == (explicit_text or "Selected paragraph")
        assert source.choice("web").item.properties["start_location"] == url


@pytest.mark.parametrize("caption", [None, "  Literal caption\r\n"])
def test_browser_source_url_does_not_replace_copied_image(caption):
    url = "https://example.test/source%20page?key=a%2Fb#part"
    image = QImage(3, 2, QImage.Format.Format_ARGB32)
    image.fill(0xff102030)
    mime = QMimeData()
    mime.setUrls([QUrl(url)])
    mime.setImageData(image)
    mime.setHtml('<img src="https://example.test/photo.png">' + ("<p>Literal caption</p>" if caption else ""))
    if caption is not None:
        mime.setText(caption)
    source, = classify_canvas_import(capture_canvas_mime_data(mime))
    assert source.detected_choice == "media"
    assert _detected(source).artifact.data.startswith(b"\x89PNG")
    assert source.choice("web").item.properties["start_location"] == url
    assert source.choice("text").item.properties["text"] == (caption or url)
    assert source.choice("panel").item.properties["value"] == (caption or url)
    assert source.choice("text").item.artifact is None
    assert source.choice("panel").item.artifact is None
    if caption:
        assert source.choice("formatted_text").item.properties["text"] == "Literal caption"


def test_copied_image_keeps_original_media_url_as_an_alternative():
    url = "https://example.test/photo%20file.png?key=a%2Fb#part"
    image = QImage(3, 2, QImage.Format.Format_ARGB32)
    image.fill(0xff102030)
    mime = QMimeData()
    mime.setUrls([QUrl(url)])
    mime.setImageData(image)
    mime.setHtml(f'<img src="{url}">')
    snapshot = capture_canvas_mime_data(mime)
    assert snapshot.text == ""
    source, = classify_canvas_import(snapshot)
    assert _detected(source).artifact is not None
    assert source.choice("source_url_0").item.properties["source"] == url
    assert source.choice("text").item.properties["text"] == url


def test_copied_image_with_html_caption_has_literal_and_formatted_choices():
    image = QImage(3, 2, QImage.Format.Format_ARGB32)
    image.fill(0xff102030)
    mime = QMimeData()
    mime.setImageData(image)
    mime.setHtml("<p>Image caption</p>")
    source, = classify_canvas_import(capture_canvas_mime_data(mime))
    assert source.detected_choice == "media"
    assert source.choice("formatted_text").item.properties == {"text": "Image caption", "format": "markdown"}
    assert source.choice("text").item.properties["text"] == "Image caption"
    assert source.choice("panel").item.properties["value"] == "Image caption"
    assert source.choice("text").item.artifact is None
    assert source.choice("panel").item.artifact is None


def test_table_defaults_to_tabular_and_preserves_literal_copied_cells():
    text = 'Label\tValue\r\n"a\tb"\t001.20\r\n'
    mime = QMimeData()
    mime.setText(text)
    mime.setHtml("<table><tr><td>Alternate</td><td>format</td></tr></table>")
    for snapshot in (capture_canvas_mime_data(mime), capture_canvas_drop(text=text, html=mime.html())):
        source, = classify_canvas_import(snapshot)
        assert source.detected_choice == "tabular"
        assert _detected(source).type_id == "tabular.input"
        assert _detected(source).artifact.data == b'Label\tValue\n"a\tb"\t001.20\n'
        assert source.choice("text").item.properties["text"] == text
        assert source.choice("panel").item.properties["value"] == text
        assert source.choice("markdown_table").item.properties["format"] == "markdown"
        assert {choice.key for choice in source.choices} == {"tabular", "markdown_table", "text", "panel", "skip"}


def test_html_only_table_has_tsv_and_escaped_markdown_alternatives():
    snapshot = capture_canvas_drop(html="<table><tr><th>Name</th><th>Value</th></tr><tr><td>a|b</td><td>1<br>2</td></tr></table>")
    source, = classify_canvas_import(snapshot)
    assert source.detected_choice == "tabular"
    assert source.choice("text").item.properties["text"] == 'Name\tValue\na|b\t"1\n2"\n'
    assert r"a\|b" in source.choice("markdown_table").item.properties["text"]
    assert "1<br>2" in source.choice("markdown_table").item.properties["text"]


def test_single_column_html_table_preserves_supplied_plain_text_and_source_url():
    text = "  A  \r\n  B  \r\n"
    url = "https://example.test/table?key=a%2Fb#part"
    raw_html = "<table><tr><td>A</td></tr><tr><td>B</td></tr></table>"
    mime = QMimeData()
    mime.setUrls([QUrl(url)])
    mime.setHtml(raw_html)
    mime.setText(text)
    for snapshot in (capture_canvas_mime_data(mime), capture_canvas_drop([url], text=text, html=raw_html)):
        source, = classify_canvas_import(snapshot)
        assert source.detected_choice == "tabular"
        assert source.choice("text").item.properties["text"] == text
        assert source.choice("panel").item.properties["value"] == text
        assert source.choice("web").item.properties["start_location"] == url


def test_rich_text_keeps_literal_and_converted_variants():
    literal = "  A copied line\r\nSecond line  "
    source, = classify_canvas_import(capture_canvas_drop(text=literal, html="<p>A copied line</p><p>Second line</p>"))
    assert source.detected_choice == "formatted_text"
    assert _detected(source).properties == {"text": "A copied line\n\nSecond line", "format": "markdown"}
    assert source.choice("text").item.properties == {"text": literal, "format": "plain"}
    assert source.choice("panel").item.properties["value"] == literal


def test_rich_single_link_retains_copied_text_and_url_choices():
    url = "https://example.test/docs?x=1&y=2#summary"
    snapshot = capture_canvas_drop(text="Guide title", html='<a href="https://example.test/docs?x=1&amp;y=2#summary">Guide title</a>')
    source, = classify_canvas_import(snapshot)
    assert source.detected_choice == "web"
    assert _detected(source).properties["start_location"] == url
    assert source.choice("text").item.properties["text"] == "Guide title"
    assert source.choice("panel").item.properties["value"] == "Guide title"
    assert source.choice("formatted_text").item.properties["text"] == "Guide title"


@pytest.mark.parametrize("text", ["  001.23\r\n *literal*  ", "https://[invalid", "https://example.test:bad/a.pdf", "https://example.test/a b", '{"not": "a graph"}'])
def test_plain_text_and_malformed_urls_are_preserved_without_number_parsing(text):
    source, = classify_canvas_import(capture_canvas_drop(text=text))
    assert source.detected_choice == "text"
    assert _detected(source).properties == {"text": text, "format": "plain"}
    assert source.choice("panel").item.properties == {"value": text, "mode": PANEL_MODE_TEXT, "parse_numbers": False}


@pytest.mark.parametrize("graph_bytes", [b"not-json", b"", b"\xff", b'{"kind":"invalid"}'])
def test_graph_fragment_mime_blocks_external_fallback_even_when_invalid(graph_bytes):
    mime = QMimeData()
    mime.setData(GRAPH_FRAGMENT_MIME_TYPE, graph_bytes)
    mime.setText("A\tB\n1\t2")
    mime.setUrls([QUrl("https://example.test/image.png")])
    snapshot = capture_canvas_mime_data(mime)
    assert snapshot.graph_fragment == graph_bytes
    assert classify_canvas_import(snapshot) == ()


def test_valid_graph_text_does_not_become_an_annotation():
    payload = build_graph_fragment_payload(nodes=[{"ref_id": "n1", "type_id": "data.panel", "x": 0, "y": 0}], edges=[])
    assert classify_canvas_import(capture_canvas_drop(text=json.dumps(payload))) == ()


def test_native_folder_explorer_mime_without_source_or_text_preserves_folder_hint():
    mime = QMimeData()
    mime.setData("application/x-corex-path-pointer", json.dumps({
        "type_id": "io.path_pointer", "properties": {"path": "C:/folder.name", "mode": "folder"},
    }).encode("utf-8"))
    source, = classify_canvas_import(capture_canvas_mime_data(mime))
    assert source.detected_choice == "path"
    assert source.choice("path").item.properties == {"path": "C:/folder.name", "mode": "folder"}


def test_empty_input_unknown_choice_and_recipe_signature():
    assert capture_canvas_mime_data(None) == CanvasImportSnapshot()
    assert classify_canvas_import(CanvasImportSnapshot()) == ()
    assert classify_canvas_import(capture_canvas_drop(text=" \n ")) == ()
    mime = QMimeData()
    mime.setText("copied")
    source, = classify_canvas_import(capture_canvas_mime_data(mime))
    with pytest.raises(KeyError):
        source.choice("media")
    signature = clipboard_paste_items_signature((_detected(source),))
    assert json.loads(signature)[0]["properties"]["text"] == "copied"
