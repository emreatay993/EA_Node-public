import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal
from sklearn.cluster import KMeans

# Import our computation and selection modules
from . import computation
from . import selection_strategies


def _load_and_combine_data(filepaths):
    """
    Loads data from multiple files and combines their strain tensors.
    Assumes nodes and coordinates are identical across all files.
    """
    if not filepaths:
        raise ValueError("No input files provided.")

    # Load the first file to get the base node and coordinate data
    nodes, coords, _ = computation.load_data(filepaths[0])

    combined_strain_tensors = {}
    measurement_idx = 0

    for fpath in filepaths:
        # Load data from each file
        # We assume nodes and coords are the same, so we discard them after the first file
        _, _, strain_tensors = computation.load_data(fpath)

        # Append the strain tensors from the current file to the combined dictionary
        for i in range(len(strain_tensors)):
            combined_strain_tensors[measurement_idx] = strain_tensors[i]
            measurement_idx += 1

    return nodes, coords, combined_strain_tensors


class AnalysisEngine(QObject):
    """
    Performs the core analysis, completely decoupled from the UI. This class is
    the "Model" in the MVC pattern. It takes parameters, runs calculations, and
    emits signals with the results or errors.
    """
    # Signal emitted on successful completion of a full analysis run.
    # Carries the final data needed for visualization and reporting.
    analysis_complete = pyqtSignal(
        object, object, object, object
    )  # coords, aggregate_scalars, case_scalars, candidates_df

    # Signal emitted when the K-Means preview step is ready.
    # Carries the coordinates and the cluster labels for visualization.
    kmeans_preview_ready = pyqtSignal(object, object)  # coords, cluster_labels

    # Signal emitted when any part of the analysis fails.
    # Carries a string with the error message.
    analysis_failed = pyqtSignal(str)

    def __init__(self, filepaths, params, display_in_strain, is_continued_kmeans=False,
                 preloaded_data=None, parent=None):
        super().__init__(parent)
        if filepaths is None:
            self.filepaths = []
        else:
            self.filepaths = filepaths if isinstance(filepaths, list) else [filepaths]
        self.params = params
        self.display_in_strain = display_in_strain
        self.is_continued_kmeans = is_continued_kmeans
        # Optional pre-extracted dataset (nodes, coords, strain_tensors), e.g. from
        # the DPF .rst loader. When present, text-file loading is bypassed entirely.
        self.preloaded_data = preloaded_data

    def run(self):
        """The main entry point to start the analysis workflow."""
        try:
            # Reset k-NN fallback counters for this run
            try:
                computation.reset_knn_counters()
            except Exception:
                pass

            if self.preloaded_data is not None:
                # Dataset already extracted (e.g. from a .rst via DPF).
                nodes, coords, strain_tensors = self.preloaded_data
            else:
                nodes, coords, strain_tensors = _load_and_combine_data(self.filepaths)

            # Special handling for the two-step K-Means strategy
            if self.params["strategy"] == "Max Coverage (K-Means)" and not self.is_continued_kmeans:
                # This is the first step: generate and show the clusters.
                candidate_count = self.params["candidate_count"]
                if len(coords) < candidate_count:
                    candidate_count = len(coords)

                kmeans = KMeans(n_clusters=candidate_count, random_state=42, n_init='auto').fit(coords)
                self.kmeans_preview_ready.emit(coords, kmeans.labels_)
                return  # Stop execution here until user clicks "Continue"

            # Proceed with the full analysis for all other cases
            agg_quality_df, current_scalars, case_scalars = self._compute_quality(
                nodes, coords, strain_tensors
            )

            candidates_df = self._select_candidates(agg_quality_df, coords)

            # Report k-NN fallback usage (console; escalate if >5%)
            try:
                used, total = computation.get_knn_counters()
                if total > 0:
                    ratio = 100.0 * used / float(total)
                    msg = f"Local_Std k-NN fallback used for {used}/{total} nodes ({ratio:.1f}%)."
                    print(msg)
            except Exception:
                pass

            self.analysis_complete.emit(
                coords, current_scalars, case_scalars, candidates_df
            )

        except Exception as e:
            import traceback
            print(traceback.format_exc())  # For debugging
            self.analysis_failed.emit(f"An unexpected error occurred: {e}")

    def _compute_quality(self, nodes, coords, strain_tensors):
        """Private helper to run the core strain and quality computations."""
        quality_dfs = []
        threshold_metric = None
        case_scalars = {}

        if self.params["measurement_mode"] == "Rosette":
            angles = [0]
            strains_list = []
            for case_idx, tensor in strain_tensors.items():
                # All internal calculations use microstrain
                strain_data = tensor
                # von Mises equivalent strain calculation
                vm_strains = np.sqrt(
                    strain_data[:, 0] ** 2 - strain_data[:, 0] * strain_data[:, 1] + strain_data[:, 1] ** 2 + 3 * (
                                strain_data[:, 2] ** 2)
                )
                strains_list.append(vm_strains)
                case_scalars[case_idx] = vm_strains
                df = computation.compute_quality_metrics(
                    nodes, coords, vm_strains.reshape(-1, 1), angles,
                    self.params["quality_mode"], self.params["uniformity_radius"]
                )
                quality_dfs.append(df)

            strains_stack = np.column_stack(strains_list)
            agg_method = self.params["agg_method"]
            current_scalars = np.max(strains_stack, axis=1) if agg_method == "Max" else np.mean(strains_stack, axis=1)
            # Threshold metric across load cases
            thresh_agg = self.params.get("strain_threshold_agg", "Max")
            if thresh_agg == "Average":
                threshold_metric = np.mean(strains_stack, axis=1)
            else:
                threshold_metric = np.max(strains_stack, axis=1)

        else:  # Uniaxial
            interval = 15
            angles = [0] + list(range(interval, 180, interval))
            strains_list = []
            for case_idx, tensor in strain_tensors.items():
                strain_data = tensor
                strains_i = computation.compute_normal_strains(strain_data, angles)
                strains_list.append(strains_i)
                case_scalars[case_idx] = np.max(np.abs(strains_i), axis=1)
                df = computation.compute_quality_metrics(
                    nodes, coords, strains_i, angles,
                    self.params["quality_mode"], self.params["uniformity_radius"]
                )
                quality_dfs.append(df)

            strains_stack = np.stack([np.max(np.abs(s), axis=1) for s in strains_list], axis=1)
            agg_method = self.params["agg_method"]
            current_scalars = np.max(strains_stack, axis=1) if agg_method == "Max" else np.mean(strains_stack, axis=1)
            # Threshold metric across load cases
            thresh_agg = self.params.get("strain_threshold_agg", "Max")
            if thresh_agg == "Average":
                threshold_metric = np.mean(strains_stack, axis=1)
            else:
                threshold_metric = np.max(strains_stack, axis=1)

        agg_quality_df = computation.aggregate_quality_metrics(quality_dfs, self.params["agg_method"])

        # Apply microstrain threshold filtering if enabled
        if self.params.get("strain_threshold_enabled", False) and threshold_metric is not None:
            # threshold_metric is in the same unit as input tensors after conversion depending on display mode
            # Convert user-provided microstrain threshold into the working unit
            user_thresh_micro = float(self.params.get("strain_threshold_value_microstrain", 0.0))
            threshold_value = user_thresh_micro  # compare in microstrain

            # Filter DataFrame rows where the metric is below threshold
            mask = threshold_metric >= threshold_value
            if not np.all(mask):
                agg_quality_df = agg_quality_df.loc[mask].reset_index(drop=True)

        return agg_quality_df, current_scalars, case_scalars

    def _select_candidates(self, agg_quality_df, coords):
        """Private helper to dispatch to the correct selection strategy."""
        strategy = self.params["strategy"]
        candidate_count = self.params["candidate_count"]

        # A dispatch dictionary maps the strategy string to the correct function call
        strategy_functions = {
            "Max Quality (Greedy Search)":
                lambda: selection_strategies.select_candidates_quality_greedy(
                    agg_quality_df, self.params["min_distance"], candidate_count
                ),
            "Max Coverage (K-Means)":
                lambda: selection_strategies.select_candidates_kmeans(
                    agg_quality_df, agg_quality_df[["X", "Y", "Z"]].values, candidate_count
                ),
            "Greedy Gradient Search":
                lambda: selection_strategies.select_candidates_gradient_greedy(
                    agg_quality_df,
                    self.params["min_distance"],
                    candidate_count,
                    True if self.params.get("gradient_mode", "Max Local Std").startswith("Max") else False
                ),
            "Quality-Filtered K-Means":
                lambda: selection_strategies.select_candidates_filtered_kmeans(
                    agg_quality_df, candidate_count, self.params["quality_percentile"]
                ),
            "Region of Interest (ROI) Search":
                lambda: selection_strategies.select_candidates_roi(
                    agg_quality_df, self.params["roi_center"], self.params["roi_radius"],
                    self.params["min_distance"], candidate_count
                )
        }

        if strategy in strategy_functions:
            return strategy_functions[strategy]()
        else:
            raise ValueError(f"Unknown selection strategy: {strategy}")
