# File: app/selection_strategies.py

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans


def _greedy_selection(df, min_distance, candidate_count):
    """
    Optimized greedy selection using NumPy for faster distance checks.
    This is a private helper function.

    Args:
        df (pd.DataFrame): DataFrame sorted by the desired metric (e.g., Quality, Local_Std).
        min_distance (float): The minimum allowable distance between selected candidates.
        candidate_count (int): The maximum number of candidates to select.

    Returns:
        pd.DataFrame: A DataFrame containing the selected candidate points.
    """
    if df.empty or candidate_count == 0:
        return pd.DataFrame()

    # Use a list of dicts for faster appending compared to DataFrame concatenation
    selected_rows = []
    all_coords = df[['X', 'Y', 'Z']].values

    # Keep track of indices that are still available for selection
    available_indices = np.arange(len(df))

    while len(selected_rows) < candidate_count and len(available_indices) > 0:
        # Select the first available point (which has the highest metric value)
        current_idx_in_df = available_indices[0]
        current_point_coords = all_coords[current_idx_in_df]
        selected_rows.append(df.iloc[current_idx_in_df].to_dict())

        # If there are still points left to check...
        if len(available_indices) > 1:
            # Get the indices of the remaining points
            remaining_indices = available_indices[1:]
            # Calculate distances from the new point to all *remaining* available points
            distances = np.linalg.norm(all_coords[remaining_indices] - current_point_coords, axis=1)
            # Keep only those points that are far enough away
            available_indices = remaining_indices[distances >= min_distance]
        else:
            # No more points to check, exit the loop
            break

    return pd.DataFrame(selected_rows)


def select_candidates_quality_greedy(df, min_distance, candidate_count):
    """
    Selects candidates with the highest 'Quality' using a greedy algorithm
    that enforces a minimum distance between points.
    """
    df_sorted = df.sort_values(by='Quality', ascending=False)
    return _greedy_selection(df_sorted, min_distance, candidate_count)


def select_candidates_kmeans(df, coords, candidate_count):
    """
    Selects one candidate per cluster, choosing the point with the highest
    'Quality' from each cluster.
    """
    if df.empty or candidate_count == 0:
        return pd.DataFrame()

    # Ensure there are enough unique points to form the requested number of clusters
    if len(df) < candidate_count:
        print(f"Warning: Requested clusters ({candidate_count}) is more than available points ({len(df)}). "
              f"Reducing cluster count for K-Means.")
        candidate_count = len(df)

    kmeans = KMeans(n_clusters=candidate_count, random_state=42, n_init='auto').fit(coords)
    df_with_clusters = df.copy()
    df_with_clusters['Cluster'] = kmeans.labels_

    # Find the index of the row with the maximum quality within each cluster
    best_indices = df_with_clusters.groupby('Cluster')['Quality'].idxmax()
    best_rows = df_with_clusters.loc[best_indices]

    return best_rows.sort_values(by='Quality', ascending=False).reset_index(drop=True)


def select_candidates_gradient_greedy(df, min_distance, candidate_count, maximize: bool = True):
    """
    Selects candidates by strain gradient ('Local_Std') using a greedy algorithm
    that enforces a minimum distance.

    Args:
        df: DataFrame with 'Local_Std'.
        min_distance: exclusion radius between picks.
        candidate_count: number of picks to return.
        maximize: if True (default) selects highest Local_Std; if False selects lowest.
    """
    df_sorted = df.sort_values(by='Local_Std', ascending=not maximize)
    return _greedy_selection(df_sorted, min_distance, candidate_count)


def select_candidates_filtered_kmeans(df, candidate_count, quality_percentile):
    """
    Runs K-Means on a high-quality subset of nodes, filtered by a quality percentile.
    """
    if df.empty or candidate_count == 0:
        return pd.DataFrame()

    # Determine the quality threshold from the percentile
    threshold_value = df['Quality'].quantile(quality_percentile / 100.0)
    df_filtered = df[df['Quality'] >= threshold_value].copy()

    if df_filtered.empty:
        print("Warning: No nodes met the quality threshold for Filtered K-Means. Returning empty.")
        return pd.DataFrame()

    filtered_coords = df_filtered[['X', 'Y', 'Z']].values
    return select_candidates_kmeans(df_filtered, filtered_coords, candidate_count)


def select_candidates_roi(df, roi_center, roi_radius, min_distance, candidate_count):
    """
    Selects candidates within a user-defined Region of Interest (ROI) using a
    quality-based greedy search.
    """
    if df.empty:
        return pd.DataFrame()

    # Calculate distance from each point to the ROI center and filter
    distances = np.linalg.norm(df[['X', 'Y', 'Z']].values - roi_center, axis=1)
    df_roi = df[distances <= roi_radius].copy()

    if df_roi.empty:
        # The engine will return this empty DataFrame, and the UI will be responsible
        # for notifying the user that the ROI was empty.
        return pd.DataFrame()

    # Perform a standard greedy search within the filtered ROI subset
    return select_candidates_quality_greedy(df_roi, min_distance, candidate_count)