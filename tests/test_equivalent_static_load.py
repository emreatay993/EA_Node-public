"""Engine tests for scripts/equivalent_static_load.

The analytic-recovery suite is the core evidence: synthetic data is built so
exact answers are known in closed form (see synthetic.py docstring), and a
2-DOF spring model ties the solver to the theory anchor f_ESL = K u(t*).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from scripts.equivalent_static_load import cli
from scripts.equivalent_static_load.config import Channel, ConfigError, load_config
from scripts.equivalent_static_load.core import InputError, SolveError
from scripts.equivalent_static_load.io_modal import (
    ModalCoordinates,
    ModalField,
    check_mode_consistency,
    load_modal_coordinates,
    load_modal_field,
)
from scripts.equivalent_static_load.mapping import map_nodes
from scripts.equivalent_static_load.metrics import build_weights, evaluate_case, region_mask
from scripts.equivalent_static_load.reconstruct import (
    interface_resultants,
    reconstruct_at_instant,
    snap_to_grid,
    von_mises,
)
from scripts.equivalent_static_load.solve import (
    closed_form_lambda,
    gang_matrix,
    reduced_bounds,
    solve_esl,
)
from scripts.equivalent_static_load.synthetic import make_synthetic


def _free_channels(n: int, bound: float = np.inf) -> tuple[Channel, ...]:
    return tuple(
        Channel(name=f"c{k}", case_label=f"Case{k + 1}", bounds=(-bound, bound))
        for k in range(n)
    )


def _random_problem(seed: int, n_nodes: int = 40, n_channels: int = 3):
    rng = np.random.default_rng(seed)
    unit = rng.normal(size=(n_nodes, 6, n_channels))
    p_true = rng.uniform(-5.0, 5.0, size=n_channels)
    target = np.einsum("nck,k->nc", unit, p_true)
    weights = rng.uniform(0.1, 1.0, size=n_nodes)
    return unit, p_true, target, weights


# --------------------------------------------------------------------- solve

def test_exact_span_recovery_uniform_and_weighted() -> None:
    unit, p_true, target, weights = _random_problem(1)
    channels = _free_channels(3)
    for w in (np.ones(unit.shape[0]), weights):
        sol = solve_esl(unit, target, w, channels)
        np.testing.assert_allclose(sol.loads, p_true, rtol=1e-10)
        assert sol.relative_residual < 1e-12
        assert not sol.at_bound.any()


def test_tier1_lambda_recovery_matches_closed_form() -> None:
    unit, p_true, _, weights = _random_problem(2)
    channels = _free_channels(3)
    pattern = p_true / 1.8
    target = np.einsum("nck,k->nc", unit, p_true)
    sol = solve_esl(unit, target, weights, channels, gang_map=pattern.reshape(-1, 1))
    assert sol.lam == pytest.approx(1.8, rel=1e-10)
    assert sol.lam == pytest.approx(
        closed_form_lambda(unit, target, weights, pattern), rel=1e-10
    )
    np.testing.assert_allclose(sol.loads, p_true, rtol=1e-10)


def test_two_dof_model_solver_equals_exact_esl() -> None:
    """Ties the solver to f_ESL = K u(t*) on a closed-form 2-DOF spring chain."""
    k1, k2 = 1000.0, 700.0
    m1, m2 = 2.0, 1.0
    stiffness = np.array([[k1 + k2, -k2], [-k2, k2]])
    mass = np.diag([m1, m2])

    eigvals, vecs = np.linalg.eigh(np.linalg.inv(mass) @ stiffness)
    # Mass-normalize the eigenvectors.
    for j in range(2):
        vecs[:, j] /= np.sqrt(vecs[:, j] @ mass @ vecs[:, j])
    omegas = np.sqrt(eigvals)

    def spring_forces(u: np.ndarray) -> np.ndarray:
        """'Stress' observables: the two spring forces."""
        return np.array([k1 * u[0], k2 * (u[1] - u[0])])

    # Modal 'stress' field: spring forces of each mass-normalized mode.
    modal_stress = np.zeros((2, 6, 2))
    for j in range(2):
        modal_stress[:, 0, j] = spring_forces(vecs[:, j])

    # Free response from initial displacement u0: q_j(t) = (phi_j^T M u0) cos(w_j t).
    u0 = np.array([0.8, -0.3])
    times = np.linspace(0.0, 1.0, 2001)
    q = np.stack(
        [(vecs[:, j] @ mass @ u0) * np.cos(omegas[j] * times) for j in range(2)]
    )
    field = ModalField(
        node_ids=np.array([1, 2]), coords=None, data=modal_stress,
        components=("sx", "sy", "sz", "sxy", "syz", "sxz"), source="synthetic",
    )
    coords = ModalCoordinates(q=q, times=times, source="test")
    instant = snap_to_grid(coords, 0.137)

    target = reconstruct_at_instant(field, coords, instant)
    u_t = vecs @ q[:, instant.index]
    np.testing.assert_allclose(target[:, 0], spring_forces(u_t), rtol=1e-10)

    # Channels: unit force at each DOF; unit 'stress' fields from static solves.
    unit = np.zeros((2, 6, 2))
    flex = np.linalg.inv(stiffness)
    for k in range(2):
        e = np.zeros(2)
        e[k] = 1.0
        unit[:, 0, k] = spring_forces(flex @ e)

    sol = solve_esl(unit, target, np.ones(2), _free_channels(2))
    f_exact = stiffness @ u_t  # the exact equivalent static load
    np.testing.assert_allclose(sol.loads, f_exact, rtol=1e-9)


def test_bounds_pin_and_flag() -> None:
    unit, p_true, target, _ = _random_problem(3)
    cap = float(abs(p_true).max()) * 0.5
    channels = tuple(
        Channel(name=f"c{k}", case_label=f"Case{k + 1}", bounds=(-cap, cap))
        for k in range(3)
    )
    sol = solve_esl(unit, target, np.ones(unit.shape[0]), channels)
    assert sol.at_bound.any()
    assert np.all(sol.loads <= cap + 1e-9) and np.all(sol.loads >= -cap - 1e-9)
    assert sol.residual_norm > 0


def test_gang_ratios_respected_including_negative() -> None:
    rng = np.random.default_rng(4)
    unit = rng.normal(size=(50, 6, 3))
    channels = (
        Channel(name="a", case_label="Case1", bounds=(-np.inf, np.inf), gang="g", gang_ratio=1.0),
        Channel(name="b", case_label="Case2", bounds=(-np.inf, np.inf), gang="g", gang_ratio=2.0),
        Channel(name="c", case_label="Case3", bounds=(-np.inf, np.inf), gang="g", gang_ratio=-1.0),
    )
    gang_map, names = gang_matrix(channels)
    assert gang_map.shape == (3, 1) and names == ["gang:g"]
    r_true = 1.7
    target = np.einsum("nck,k->nc", unit, gang_map[:, 0] * r_true)
    sol = solve_esl(unit, target, np.ones(50), channels, gang_map=gang_map)
    np.testing.assert_allclose(sol.loads, [r_true, 2 * r_true, -r_true], rtol=1e-10)


def test_reduced_bounds_negative_ratio_and_conflict() -> None:
    channels = (
        Channel(name="a", case_label="C1", bounds=(0.0, 10.0)),
        Channel(name="b", case_label="C2", bounds=(0.0, 10.0)),
    )
    pattern = np.array([1.0, -2.0])
    with pytest.raises(SolveError, match="Bound conflict"):
        reduced_bounds(channels, pattern.reshape(-1, 1))
    lb, ub = reduced_bounds(
        (channels[0], Channel(name="b", case_label="C2", bounds=(-10.0, 0.0))),
        pattern.reshape(-1, 1),
    )
    assert lb[0] == 0.0 and ub[0] == pytest.approx(5.0)


def test_conditioning_warning_and_tikhonov_shrinks_norm() -> None:
    rng = np.random.default_rng(5)
    base = rng.normal(size=(60, 6))
    unit = np.stack([base, base + 1e-9 * rng.normal(size=base.shape)], axis=2)
    target = base * 2.0
    channels = _free_channels(2)
    sol = solve_esl(unit, target, np.ones(60), channels, cond_warn_threshold=1e6)
    assert sol.diagnostics["condition_warning"]
    sol_reg = solve_esl(unit, target, np.ones(60), channels, tikhonov_alpha=1e-6)
    assert np.linalg.norm(sol_reg.loads) <= np.linalg.norm(sol.unconstrained_loads) + 1e-6


# ------------------------------------------------------------------ io_modal

PCH_FIXTURE = """$TITLE   = synthetic
$DISPLACEMENTS (SOLUTION SET)
$REAL OUTPUT
$SUBCASE ID =           1
$POINT ID =           1
    0.000000E+00 M      1.000000E+00  0.0  0.0
    1.000000E-03 M      2.000000E+00  0.0  0.0
$POINT ID =           2
    0.000000E+00 M      3.000000E+00  0.0  0.0
    1.000000E-03 M      4.000000E+00  0.0  0.0
$DISPLACEMENTS
$POINT ID =           99
    0.000000E+00 G      9.900000E+00  0.0  0.0
"""


def test_pch_parser(tmp_path: Path) -> None:
    p = tmp_path / "run.pch"
    p.write_text(PCH_FIXTURE)
    mc = load_modal_coordinates(p)
    assert mc.source == "pch"
    assert mc.q.shape == (2, 2)
    np.testing.assert_allclose(mc.q, [[1.0, 2.0], [3.0, 4.0]])
    np.testing.assert_allclose(mc.times, [0.0, 1e-3])


def test_mcf_wrapped_lines_via_house_parser(tmp_path: Path) -> None:
    p = tmp_path / "run.mcf"
    p.write_text(
        "Header line\n"
        "Number of Modes: 3\n"
        "Time    Coordinates\n"
        " 0.000E+00  1.0 2.0\n"
        "     3.0\n"
        " 1.000E-03  4.0 5.0\n"
        "     6.0\n"
    )
    mc = load_modal_coordinates(p)
    assert mc.q.shape == (3, 2)
    np.testing.assert_allclose(mc.q[:, 0], [1.0, 2.0, 3.0])
    np.testing.assert_allclose(mc.q[:, 1], [4.0, 5.0, 6.0])


def test_modal_field_loader_and_mode_mismatch(tmp_path: Path) -> None:
    import pandas as pd

    frame = pd.DataFrame(
        {
            "NodeID": [1, 2, 2],
            "X": [0.0, 1.0, 1.0], "Y": [0.0, 0.0, 0.0], "Z": [0.0, 0.0, 0.5],
            "sx_Mode1": [1.0, 2.0, 20.0], "sy_Mode1": [0.0] * 3, "sz_Mode1": [0.0] * 3,
            "sxy_Mode1": [0.0] * 3, "syz_Mode1": [0.0] * 3, "sxz_Mode1": [0.0] * 3,
        }
    )
    p = tmp_path / "modal_stress.csv"
    frame.to_csv(p, index=False)
    field = load_modal_field(p, kind="stress")
    assert field.num_nodes == 2  # duplicate NodeID keeps last (MARS parity)
    assert field.data[1, 0, 0] == 20.0
    assert field.coords is not None and field.coords[1, 2] == 0.5

    coords = ModalCoordinates(q=np.zeros((2, 4)), times=np.arange(4.0), source="t")
    with pytest.raises(InputError, match="Mode-count mismatch"):
        check_mode_consistency(field, coords, "modal stress CSV")


# ------------------------------------------------------------------- mapping

def test_mapping_id_join_and_permutation() -> None:
    ids = np.array([10, 20, 30, 40])
    xyz = np.arange(12.0).reshape(4, 3)
    perm = np.array([2, 0, 3, 1])
    result = map_nodes(ids, xyz, ids[perm], xyz[perm])
    assert result.method == "id_join" and result.n_unmatched == 0
    np.testing.assert_allclose(xyz[result.msup_index], xyz[perm][result.rig_index])


def test_mapping_kdtree_fallback_on_disjoint_ids() -> None:
    rng = np.random.default_rng(6)
    ids = np.arange(1, 101)
    xyz = rng.uniform(0, 100, (100, 3))
    jitter = xyz + rng.normal(0, 0.01, xyz.shape)
    result = map_nodes(ids, xyz, ids + 1_000_000, jitter, kdtree_max_dist=0.5)
    assert result.method == "kdtree_fallback"
    assert result.n_kdtree_matched == 100
    assert result.coord_max_error < 0.5


def test_mapping_coord_tolerance_drops_moved_nodes() -> None:
    ids = np.array([1, 2, 3])
    xyz = np.zeros((3, 3))
    moved = xyz.copy()
    moved[2] = [5.0, 0.0, 0.0]
    result = map_nodes(ids, xyz, ids, moved, coord_tol=0.1)
    assert result.n_mapped == 2 and 3 not in result.node_ids


def test_mapping_no_coords_poor_ids_raises() -> None:
    with pytest.raises(InputError, match="coordinates are unavailable"):
        map_nodes(np.array([1, 2]), None, np.array([3, 4]), None)


# ------------------------------------------------------------------- metrics

def test_metrics_hand_computed_perfect_match() -> None:
    rng = np.random.default_rng(7)
    target = rng.normal(size=(5, 6))
    m = evaluate_case(target, target.copy(), np.ones(5), np.arange(1, 6), None)
    assert m.peak_ratio_at_critical == pytest.approx(1.0)
    assert m.weighted_r2 == pytest.approx(1.0)
    assert m.n_under_test == 0


def test_metrics_under_test_floor() -> None:
    target = np.zeros((3, 6))
    target[:, 0] = [100.0, 50.0, 5.0]     # third node below 10% floor
    achieved = target * 0.9               # 10% deficit everywhere
    m = evaluate_case(
        target, achieved, np.ones(3), np.array([1, 2, 3]), None,
        under_test_tol=0.05, vm_floor_frac=0.10,
    )
    assert m.n_under_test == 2            # node 3 is under the VM floor
    assert set(m.under_test["NodeID"]) == {1, 2}


def test_region_masks_and_weights() -> None:
    vm = np.array([1.0, 5.0, 10.0, 2.0])
    ids = np.array([1, 2, 3, 4])
    xyz = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]], dtype=float)
    mask = region_mask(vm, ids, xyz, "top_vm_percent", 25.0, None, None)
    assert mask.tolist() == [False, False, True, False]
    mask = region_mask(vm, ids, xyz, "node_list_csv", 0.0, np.array([2, 4]), None)
    assert mask.tolist() == [False, True, False, True]
    mask = region_mask(vm, ids, xyz, "bbox", 0.0, None, (0.5, -1, -1, 2.5, 1, 1))
    assert mask.tolist() == [False, True, True, False]
    weights = build_weights(vm, "vm", 2.0)
    assert weights[2] == pytest.approx(1.0) and weights[0] == pytest.approx(0.01)


# ------------------------------------------------- reconstruct / resultants

def test_von_mises_hand_value() -> None:
    tensor = np.array([[100.0, 0, 0, 0, 0, 0], [0, 0, 0, 50.0, 0, 0]])
    np.testing.assert_allclose(von_mises(tensor), [100.0, 50.0 * np.sqrt(3)])


def test_interface_resultants_moment_transfer() -> None:
    # One node at (1, 0, 0) with force (0, 10, 0) and nodal moment (0, 0, 5),
    # single mode with q = 2 -> F = (0, 20, 0); about ref (0,0,0):
    # M = 2*5 z + (r x F) = 10 z + (1,0,0)x(0,20,0) = 10 z + 20 z = 30 z.
    data = np.zeros((1, 6, 1))
    data[0, 1, 0] = 10.0
    data[0, 5, 0] = 5.0
    field = ModalField(
        node_ids=np.array([7]), coords=np.array([[1.0, 0.0, 0.0]]), data=data,
        components=("enfox", "enfoy", "enfoz", "enmox", "enmoy", "enmoz"), source="t",
    )
    coords = ModalCoordinates(q=np.array([[2.0]]), times=np.array([0.0]), source="t")
    instant = snap_to_grid(coords, 0.0)
    force, moment = interface_resultants(field, coords, instant, np.array([7]), (0.0, 0.0, 0.0))
    np.testing.assert_allclose(force, [0.0, 20.0, 0.0])
    np.testing.assert_allclose(moment, [0.0, 0.0, 30.0])


# ------------------------------------------------------------------ instants

def test_suggest_instants_and_quadrature_on_synthetic(tmp_path: Path) -> None:
    truth = make_synthetic(tmp_path, n_nodes=120, n_modes=4, n_channels=3, n_times=600, seed=3)
    cfg = load_config(tmp_path / "config.json")
    from scripts.equivalent_static_load.workflow import choose_instants, load_inputs

    inputs = load_inputs(cfg)
    suggestions = choose_instants(cfg, inputs)
    assert suggestions[0].time == pytest.approx(truth["t_star"], abs=1e-12)
    assert suggestions[0].reason == "global_vm_max"
    assert any(s.reason.startswith("quadrature") for s in suggestions)


# ---------------------------------------------------------------- end-to-end

def test_end_to_end_cli(tmp_path: Path, capsys) -> None:
    demo = tmp_path / "demo"
    assert cli.main(["make-synthetic", "--out", str(demo), "--nodes", "150",
                     "--modes", "5", "--channels", "3", "--times", "500"]) == 0
    truth = json.loads((demo / "truth.json").read_text())
    assert cli.main(["check", "--config", str(demo / "config.json")]) == 0
    assert cli.main(["derive", "--config", str(demo / "config.json"),
                     "--instants", str(truth["t_star"])]) == 0

    case_dir = demo / "esl_out" / ("case_t" + f"{truth['t_star']:.6f}".replace(".", "p"))
    for name in (
        "esl_loads.csv", "target_field.csv", "esl_field.csv", "residual_field.csv",
        "hotspots.csv", "under_test_nodes.csv",
        "verify_forces_tier1.inp", "verify_forces_tier2.inp",
    ):
        assert (case_dir / name).is_file(), name
    for name in ("run_manifest.json", "mapping_report.json", "instants_used.csv", "esl_report.md"):
        assert (demo / "esl_out" / name).is_file(), name

    import pandas as pd

    loads = pd.read_csv(case_dir / "esl_loads.csv")
    tier2 = loads[loads["tier"] == 2] if loads["tier"].dtype != object else loads[loads["tier"] == "2"]
    np.testing.assert_allclose(
        tier2["magnitude"].to_numpy(), truth["P_true_at_t_star"], rtol=1e-6
    )
    tier1 = loads[loads["tier"] == 1] if loads["tier"].dtype != object else loads[loads["tier"] == "1"]
    ratio = tier1["magnitude"].to_numpy() / tier1["pattern_value"].to_numpy()
    np.testing.assert_allclose(ratio, truth["lambda_true"], rtol=1e-6)

    manifest = json.loads((demo / "esl_out" / "run_manifest.json").read_text())
    assert manifest["inputs"]["modal_stress_csv"]["sha256"]

    assert cli.main([
        "verify", "--config", str(demo / "config.json"),
        "--case", case_dir.name.removeprefix("case_"),
        "--solved-field", str(case_dir / "esl_field.csv"),
    ]) == 0
    assert (case_dir / "verification_metrics.csv").is_file()
    assert (case_dir / "esl_loads_corrected.csv").is_file()

    assert cli.main([
        "resultants", "--config", str(demo / "config.json"), "--t", str(truth["t_star"]),
    ]) == 0
    out = capsys.readouterr().out
    assert "iface1" in out


def test_config_validation_errors(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{}")
    with pytest.raises(ConfigError, match="schema_version"):
        load_config(p)
    p.write_text(json.dumps({"schema_version": 1}))
    with pytest.raises(ConfigError, match="'msup' block is required"):
        load_config(p)
