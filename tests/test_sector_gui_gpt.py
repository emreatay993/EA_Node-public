from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "Sector_gui_gpt.py"


def load_tool_module():
    spec = importlib.util.spec_from_file_location("sector_gui_gpt", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_read_numeric_dat_file_skips_rows_with_text_or_too_few_columns(tmp_path: Path) -> None:
    tool = load_tool_module()
    dat_file = tmp_path / "mixed.dat"
    dat_file.write_text(
        "\n".join(
            [
                "X Y Z Data",
                "1 2 3 4",
                "bad 5 6 7",
                "5 6 7 8 9",
                "9 10 11 nope",
                "12 13 14",
            ]
        ),
        encoding="utf-8",
    )

    frame, skipped_rows = tool._read_numeric_dat_file(str(dat_file))

    assert skipped_rows == 4
    assert frame.columns.tolist() == ["X", "Y", "Z", "Data"]
    assert frame.values.tolist() == [
        [1.0, 2.0, 3.0, 4.0],
        [5.0, 6.0, 7.0, 8.0],
    ]


def test_hover_label_uses_rendered_node_id_and_data_value() -> None:
    tool = load_tool_module()
    frame = tool.pd.DataFrame(
        [
            [1.0, 2.0, 3.0, 4.5],
            [5.0, 6.0, 7.0, 8.25],
        ],
        columns=["X", "Y", "Z", "Data"],
    )

    polydata = tool.make_polydata(frame)

    assert polydata["NodeId"].tolist() == [0, 1]
    assert tool._hover_text_for_polydata(polydata, 1) == "Node ID: 1\nValue: 8.25"
    assert tool._hover_text_for_polydata(polydata, -1) == tool.HOVER_TEXT_EMPTY
