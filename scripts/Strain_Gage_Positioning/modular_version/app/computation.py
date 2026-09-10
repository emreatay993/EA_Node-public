# File: app/computation.py

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

# ---- Local Std fallback tracking (module-level) ---------------------------------------
_KNN_FALLBACK_COUNT = 0
_TOTAL_LOCAL_STD_POINTS = 0
_MIN_NEIGHBORS = 4  # minimum neighbors desired for a stable local std estimate


def reset_knn_counters():
    global _KNN_FALLBACK_COUNT, _TOTAL_LOCAL_STD_POINTS
    _KNN_FALLBACK_COUNT = 0
    _TOTAL_LOCAL_STD_POINTS = 0


def get_knn_counters():
    return _KNN_FALLBACK_COUNT, _TOTAL_LOCAL_STD_POINTS


def load_data(input_filename):
    """Reads the input file and returns nodes, coords (in mm), and strain tensors.

    Unit handling:
    - Detects coordinate units from the header's location fields:
      "X Location (m)"/"Y Location (m)"/"Z Location (m)" => coordinates in meters → converted to mm
      "X Location (mm)"/... => already in mm
    - Strains are treated as dimensionless and converted to microstrain (×1e6) regardless
      of header labeling (m/m or mm/mm).
    """
    # Peek the first line to infer units from the header text
    coord_scale_to_mm = 1.0
    try:
        with open(input_filename, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline().strip().lower()
        if "location (m)" in first_line:
            # Coordinates are provided in meters; convert to millimeters for internal consistency
            coord_scale_to_mm = 1000.0
        elif "location (mm)" in first_line:
            coord_scale_to_mm = 1.0
        # else: leave as 1.0 (assume mm if unspecified)
    except Exception:
        coord_scale_to_mm = 1.0

    df = pd.read_csv(input_filename, sep='\s+', skiprows=1, header=None)
    if df.shape[1] < 8:
        raise ValueError("Input file must have at least 8 columns: Node, X, Y, Z, Exx, Eyy, Ezz, Exy...")

    nodes = df.iloc[:, 0].astype(int).values
    coords = df.iloc[:, 1:4].values * coord_scale_to_mm
    conversion_factor = 1e6  # Convert from strain to microstrain

    # Determine the number of measurements based on columns available
    num_measurements = (df.shape[1] - 4) // 4
    if num_measurements == 0:
        raise ValueError("No strain measurement columns found in the input file.")

    strain_tensors = {}
    for i in range(num_measurements):
        base_col_idx = 4 + 4 * i
        # Ensure that the required columns exist for this measurement
        if base_col_idx + 3 >= df.shape[1]:
            print(f"Warning: Incomplete strain tensor columns for measurement set {i + 1}. Skipping.")
            continue

        exx = df.iloc[:, base_col_idx].values * conversion_factor
        eyy = df.iloc[:, base_col_idx + 1].values * conversion_factor
        # The input convention is [Exx, Eyy, Ezz, Exy, (optional Eyz, Exz)] per measurement block
        # We only need Exx, Eyy, and engineering shear Exy for normal strain transform.
        exy = df.iloc[:, base_col_idx + 3].values * conversion_factor  # 4th component of tensor is Exy
        strain_tensors[i] = np.column_stack((exx, eyy, exy))

    return nodes, coords, strain_tensors


def compute_normal_strains(strain_data, angles):
    """
    Compute the normal strain for each node at specified angles.

    Args:
        strain_data (np.ndarray): Array of shape (n_nodes, 3) with columns [exx, eyy, exy].
        angles (list or np.ndarray): Angles in degrees to compute strain for.

    Returns:
        np.ndarray: Array of shape (n_nodes, n_angles) with normal strains.
    """
    angles_rad = np.radians(angles)
    cos_t = np.cos(angles_rad)
    sin_t = np.sin(angles_rad)

    # Use broadcasting for efficient computation
    exx = strain_data[:, 0][:, np.newaxis]
    eyy = strain_data[:, 1][:, np.newaxis]
    exy = strain_data[:, 2][:, np.newaxis]

    # Strain transformation equation: ε_n = ε_xx*cos²θ + ε_yy*sin²θ + γ_xy*sinθ*cosθ
    # Note: Engineering shear strain (γ_xy) is 2 * tensor shear strain (ε_xy).
    # The provided data seems to use engineering strain conventions where the tensor is [exx, eyy, ezz, exy],
    # and the transformation uses exy directly. We will assume the input 'exy' is γ_xy.
    normal_strains = exx * cos_t ** 2 + eyy * sin_t ** 2 + exy * sin_t * cos_t

    return normal_strains


def compute_quality_metrics(nodes, coords, strains, angles, quality_mode, uniformity_radius):
    """
    Computes the best strain, best angle, local standard deviation, and a quality metric.

    Args:
        nodes (np.ndarray): Array of node IDs.
        coords (np.ndarray): N-D array of node coordinates.
        strains (np.ndarray): Array of strains, shape (n_nodes, n_angles).
        angles (list or np.ndarray): Angles in degrees.
        quality_mode (str): The formula to use for the quality metric.
        uniformity_radius (float): The search radius for calculating local standard deviation.

    Returns:
        pd.DataFrame: A DataFrame with comprehensive metrics for each node.
    """
    if strains.ndim == 1:
        strains = strains[:, np.newaxis]

    best_idx = np.argmax(np.abs(strains), axis=1)
    best_strains = strains[np.arange(len(strains)), best_idx]
    best_angles = np.array(angles)[best_idx]

    if len(angles) == 1:
        # For modes like von Mises, there is no "best angle"
        best_angles = np.full(len(nodes), np.nan)

    # Use cKDTree for efficient spatial queries
    tree = cKDTree(coords)
    local_std = np.zeros(len(nodes))

    # Query all points at once for better performance
    neighbors_list = tree.query_ball_point(coords, uniformity_radius)

    global _KNN_FALLBACK_COUNT, _TOTAL_LOCAL_STD_POINTS
    for i, indices in enumerate(neighbors_list):
        # Track total attempts
        _TOTAL_LOCAL_STD_POINTS += 1

        # Standard deviation requires at least 2 points; prefer >= _MIN_NEIGHBORS
        use_fallback = len(indices) < _MIN_NEIGHBORS
        if use_fallback:
            # k-NN fallback to stabilize estimate in sparse/edge regions
            k = min(_MIN_NEIGHBORS, len(coords))
            if k >= 2:
                _, knn_idx = tree.query(coords[i], k=k)
                # Ensure array of indices
                knn_idx = np.atleast_1d(knn_idx)
                local_std[i] = np.std(best_strains[knn_idx])
                _KNN_FALLBACK_COUNT += 1
            elif len(indices) > 1:
                local_std[i] = np.std(best_strains[indices])
            else:
                local_std[i] = 0.0
        else:
            # Enough neighbors within radius
            local_std[i] = np.std(best_strains[indices]) if len(indices) > 1 else 0.0

    abs_strain = np.abs(best_strains)

    # Data-driven calibration helpers (microstrain):
    # Use 75th percentile of local_std as a reference scale.
    positive_std = local_std[local_std > 0]
    sigma_ref = float(np.percentile(positive_std, 75)) if positive_std.size > 0 else 1.0
    # Unit-aware epsilon for SNR: 1% of sigma_ref with a floor of 1 microstrain
    eps0 = max(1.0, 0.01 * sigma_ref)
    # Auto-k for exponential: set attenuation A at sigma_ref
    A = 0.5
    k_exp = (0.0 if sigma_ref <= 0 else -np.log(A) / sigma_ref)

    if quality_mode == "Default: |ε|/(1+σ)":
        quality = abs_strain / (1.0 + local_std)
    elif quality_mode == "Squared: |ε|/(1+σ²)":
        quality = abs_strain / (1.0 + local_std ** 2)
    elif quality_mode == "Exponential: |ε|·exp(–1000σ)":
        # Auto-calibrated exponential penalty
        quality = abs_strain * np.exp(-k_exp * local_std)
    elif quality_mode == "Signal-Noise Ratio: |ε|/(σ+1e-12)":
        # Use a data-driven epsilon to avoid singularities and keep scale stable
        quality = abs_strain / (local_std + eps0)
    else:
        raise ValueError(f"Unknown quality_mode: {quality_mode}")

    return pd.DataFrame({
        'Node': nodes,
        'X': coords[:, 0],
        'Y': coords[:, 1],
        'Z': coords[:, 2],
        'Best_Strain': best_strains,
        'Best_Angle': best_angles,
        'Local_Std': local_std,
        'Quality': quality
    })


def aggregate_quality_metrics(quality_dfs, agg_method):
    """
    Aggregate multiple quality metric DataFrames into a single DataFrame.
    This is used when multiple load cases (measurements) are present.

    Args:
        quality_dfs (list): A list of pandas DataFrames from compute_quality_metrics.
        agg_method (str): The aggregation method ("max" or "average").

    Returns:
        pd.DataFrame: A single DataFrame with the aggregated 'Quality' column.
    """
    if not quality_dfs:
        raise ValueError("No quality dataframes provided for aggregation.")

    # Use the first DataFrame as a template for node/coord info
    agg_df = quality_dfs[0].copy()

    if len(quality_dfs) == 1:
        return agg_df

    quality_matrix = np.stack([df["Quality"].values for df in quality_dfs], axis=1)
    local_std_matrix = np.stack([df["Local_Std"].values for df in quality_dfs], axis=1)

    if agg_method.lower() == "max":
        agg_quality = np.max(quality_matrix, axis=1)
        agg_local_std = np.max(local_std_matrix, axis=1)
    elif agg_method.lower() == "average":
        agg_quality = np.mean(quality_matrix, axis=1)
        agg_local_std = np.mean(local_std_matrix, axis=1)
    else:
        raise ValueError(f"Unknown aggregation method: {agg_method}")

    agg_df["Quality"] = agg_quality
    # Aggregate the gradient metric across load cases so Greedy Gradient Search
    # reflects multi-load behavior (instead of using only the first case).
    agg_df["Local_Std"] = agg_local_std
    return agg_df