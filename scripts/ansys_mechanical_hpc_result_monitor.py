# -*- coding: utf-8 -*-
# Purpose: Monitor Windows-visible MAPDL result folders and import completed results into Mechanical v261.
# Map: subsystems/supporting_runtime_assets.md
# Tests: tests/test_ansys_mechanical_hpc_result_monitor.py
# Landmarks: pure readiness helpers; MonitorEngine; MechanicalAdapter; HpcResultMonitorForm; show_hpc_result_monitor

"""ANSYS Mechanical 2026 R1 HPC result monitor (IronPython 2.7).

The module deliberately delays CLR and Mechanical imports so its file-monitor,
parser, queue, and persistence behavior can be tested with ordinary CPython.
Run the file with ``execfile`` from Workbench-launched Mechanical.
"""

from __future__ import print_function

import copy
import io
import json
import ntpath
import os
import re
import shutil
import threading
import time
import traceback
import uuid


SCHEMA_VERSION = 1
DEFAULT_POLL_SECONDS = 300
DEFAULT_SETTLE_SECONDS = 300
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY_SECONDS = 600

STATUS_DRAFT = "Draft"
STATUS_WAITING = "Waiting"
STATUS_SETTLING = "Settling"
STATUS_READY = "Ready"
STATUS_IMPORTING = "Importing"
STATUS_EVALUATING = "Evaluating"
STATUS_SAVING = "Saving"
STATUS_RETRY_WAITING = "Retry Waiting"
STATUS_COMPLETED = "Completed"
STATUS_FAILED = "Failed"
STATUS_ATTENTION = "Attention Required"
STATUS_SKIPPED = "Skipped"
STATUS_PAUSED = "Paused"

ACTIVE_STATUSES = (STATUS_IMPORTING, STATUS_EVALUATING, STATUS_SAVING)
TERMINAL_STATUSES = (STATUS_COMPLETED, STATUS_FAILED, STATUS_ATTENTION, STATUS_SKIPPED)
SCAN_STATUSES = (STATUS_WAITING, STATUS_SETTLING, STATUS_READY)

_ERROR_COUNT_RE = re.compile(
    r"NUMBER\s+OF\s+ERROR\s+MESSAGES\s+ENCOUNTERED\s*=\s*([0-9]+)",
    re.IGNORECASE,
)
_FATAL_MARKERS = (
    "*** FATAL ***",
    "*** ERROR ***",
    "ABNORMAL TERMINATION",
    "ERROR TERMINATION",
)


def utc_timestamp():
    return time.time()


def format_clock(value):
    if value is None:
        return "-"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(value)))
    except Exception:
        return "-"


def format_duration(seconds):
    if seconds is None:
        return "-"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return "{0:d}h {1:02d}m {2:02d}s".format(hours, minutes, seconds)
    return "{0:d}m {1:02d}s".format(minutes, seconds)


def safe_get(obj, name, default=None):
    try:
        return getattr(obj, name)
    except Exception:
        return default


def type_name(obj):
    try:
        return str(obj.GetType().FullName)
    except Exception:
        return str(type(obj))


def non_none_text(value):
    return "" if value is None else str(value)


def normalize_analysis_family(analysis_type, physics_type):
    """Return one approved MAPDL family from v261 AnalysisType/PhysicsType text."""
    analysis_token = re.sub(r"[^a-z0-9]", "", non_none_text(analysis_type).lower())
    physics_token = re.sub(r"[^a-z0-9]", "", non_none_text(physics_type).lower())
    families = {
        ("static", "mechanical"): "Static Structural",
        ("modal", "mechanical"): "Modal",
        ("transient", "mechanical"): "Transient Structural",
        ("static", "thermal"): "Steady-State Thermal",
    }
    return families.get((analysis_token, physics_token))


ANALYSIS_IDENTITY_KEYS = (
    "analysis_object_id",
    "solution_object_id",
    "analysis_tree_path",
    "analysis_name",
    "solution_name",
    "analysis_type",
    "analysis_api_type",
    "analysis_physics_type",
    "analysis_clr_type",
)


def analysis_identity_tuple(record):
    return tuple(non_none_text(record.get(key)) for key in ANALYSIS_IDENTITY_KEYS)


def normalized_windows_path(path):
    return ntpath.normcase(ntpath.normpath(str(path or "").strip()))


def validate_leaf_filename(filename, allowed_extensions=None):
    name = str(filename or "").strip()
    if not name:
        raise ValueError("A filename is required.")
    if name in (".", "..") or ntpath.basename(name) != name:
        raise ValueError("Use a filename only; folders and subfolders are not allowed.")
    if "/" in name or "\\" in name or ":" in name:
        raise ValueError("The filename must not contain a path separator or drive prefix.")
    if allowed_extensions:
        extension = ntpath.splitext(name)[1].lower()
        if extension not in tuple([item.lower() for item in allowed_extensions]):
            raise ValueError(
                "Expected one of these file extensions: {0}.".format(
                    ", ".join(allowed_extensions)
                )
            )
    return name


def validate_job_config(job):
    folder = str(job.get("folder", "")).strip()
    if not folder:
        raise ValueError("A Windows folder is required.")
    if not ntpath.isabs(folder):
        raise ValueError("Use an absolute Windows folder path (UNC is recommended).")
    validate_leaf_filename(job.get("result_filename"), (".rst", ".rth"))
    validate_leaf_filename(job.get("output_filename"), (".out",))
    if not str(job.get("unit_system", "")).strip():
        raise ValueError("Choose the result-file unit system.")
    for key, label, minimum in (
        ("poll_seconds", "Poll interval", 1),
        ("settle_seconds", "Settle interval", 1),
        ("max_retries", "Retry count", 0),
        ("retry_delay_seconds", "Retry delay", 1),
    ):
        try:
            value = int(job.get(key))
        except Exception:
            raise ValueError("{0} must be a whole number.".format(label))
        if value < minimum:
            raise ValueError("{0} must be at least {1}.".format(label, minimum))
    return True


def file_signature(path):
    """Return a JSON-safe exact-file signature without searching subfolders."""
    result = {
        "path": str(path),
        "exists": False,
        "readable": False,
        "size": None,
        "mtime": None,
    }
    try:
        stat_value = os.stat(path)
        if not os.path.isfile(path):
            return result
        result["exists"] = True
        result["size"] = int(stat_value.st_size)
        result["mtime"] = float(stat_value.st_mtime)
        handle = open(path, "rb")
        try:
            handle.read(1)
            result["readable"] = True
        finally:
            handle.close()
    except (IOError, OSError):
        pass
    return result


def signatures_equal(first, second):
    if first is None or second is None:
        return False
    keys = ("exists", "readable", "size", "mtime")
    return all(first.get(key) == second.get(key) for key in keys)


def signature_changed_from_baseline(current, baseline):
    if current is None or not current.get("exists"):
        return False
    if baseline is None or not baseline.get("exists"):
        return True
    return not signatures_equal(current, baseline)


def scan_file_pair(folder, result_filename, output_filename):
    """Inspect only the two named files directly under ``folder``."""
    response = {
        "folder_available": False,
        "result": None,
        "output": None,
        "error": "",
    }
    try:
        if not os.path.isdir(folder):
            response["error"] = "Folder unavailable"
            return response
        response["folder_available"] = True
        result_path = os.path.join(folder, validate_leaf_filename(result_filename, (".rst", ".rth")))
        output_path = os.path.join(folder, validate_leaf_filename(output_filename, (".out",)))
        response["result"] = file_signature(result_path)
        response["output"] = file_signature(output_path)
    except (IOError, OSError, ValueError) as exc:
        response["error"] = str(exc)
    return response


def parse_mapdl_output(path):
    """Stream a MAPDL output and apply fatal/error precedence over completion."""
    completed = False
    error_count = None
    fatal_markers = []
    try:
        handle = open(path, "rb")
        try:
            for raw_line in handle:
                if not isinstance(raw_line, str):
                    line = raw_line.decode("utf-8", "replace")
                else:
                    try:
                        line = raw_line.decode("utf-8", "replace")
                    except AttributeError:
                        line = raw_line
                upper = line.upper()
                if "RUN COMPLETED" in upper:
                    completed = True
                match = _ERROR_COUNT_RE.search(line)
                if match:
                    error_count = int(match.group(1))
                for marker in _FATAL_MARKERS:
                    if marker in upper and marker not in fatal_markers:
                        fatal_markers.append(marker)
        finally:
            handle.close()
    except (IOError, OSError) as exc:
        return {
            "ready": False,
            "completed": False,
            "error_count": None,
            "fatal_markers": [],
            "message": "Output file could not be read: {0}".format(exc),
        }

    if fatal_markers:
        message = "Solver output contains {0}.".format(", ".join(fatal_markers))
    elif error_count is not None and error_count != 0:
        message = "Solver output reports {0} error message(s).".format(error_count)
    elif not completed:
        message = "RUN COMPLETED has not been written yet."
    elif error_count is None:
        message = "The final MAPDL error count has not been written yet."
    else:
        message = "MAPDL run completed with zero errors."
    return {
        "ready": bool(completed and error_count == 0 and not fatal_markers),
        "completed": completed,
        "error_count": error_count,
        "fatal_markers": fatal_markers,
        "message": message,
    }


def new_job(**overrides):
    now = utc_timestamp()
    job = {
        "id": uuid.uuid4().hex,
        "order": 0,
        "analysis_object_id": None,
        "solution_object_id": None,
        "analysis_tree_path": "",
        "analysis_name": "",
        "solution_name": "Solution",
        "analysis_type": "",
        "analysis_api_type": "",
        "analysis_physics_type": "",
        "analysis_clr_type": "",
        "folder": "",
        "result_filename": "file.rst",
        "output_filename": "file.out",
        "unit_system": "",
        "poll_seconds": DEFAULT_POLL_SECONDS,
        "settle_seconds": DEFAULT_SETTLE_SECONDS,
        "max_retries": DEFAULT_MAX_RETRIES,
        "retry_delay_seconds": DEFAULT_RETRY_DELAY_SECONDS,
        "accept_existing": False,
        "status": STATUS_DRAFT,
        "message": "Configure this job.",
        "created_at": now,
        "monitoring_started_at": None,
        "next_scan_at": None,
        "last_scan_at": None,
        "ready_at": None,
        "import_started_at": None,
        "completed_at": None,
        "checkpoint_at": None,
        "baseline_pending": False,
        "baseline_result": None,
        "baseline_output": None,
        "last_result_signature": None,
        "last_output_signature": None,
        "stable_since": None,
        "retry_count": 0,
        "retry_due_at": None,
        "failed_phase": None,
        "completed_phase": None,
        "last_error": "",
        "mutation_uncertain": False,
        "recovery_acknowledged": False,
        "checkpoint": None,
        "scan_generation": 0,
    }
    job.update(overrides)
    return job


def begin_monitoring_job(job, now=None):
    validate_job_config(job)
    now = utc_timestamp() if now is None else float(now)
    job["status"] = STATUS_WAITING
    job["message"] = "Waiting for the first folder scan."
    job["monitoring_started_at"] = now
    job["next_scan_at"] = now
    job["last_scan_at"] = None
    job["ready_at"] = None
    job["baseline_pending"] = True
    job["baseline_result"] = None
    job["baseline_output"] = None
    job["last_result_signature"] = None
    job["last_output_signature"] = None
    job["stable_since"] = None
    job["retry_count"] = 0
    job["retry_due_at"] = None
    job["failed_phase"] = None
    job["completed_phase"] = None
    job["last_error"] = ""
    job["mutation_uncertain"] = False
    job["recovery_acknowledged"] = False
    job["scan_generation"] = int(job.get("scan_generation") or 0) + 1


def update_job_readiness(job, now=None, pair=None):
    """Advance one job from Waiting/Settling to Ready, or report why not."""
    now = utc_timestamp() if now is None else float(now)
    was_ready = job.get("status") == STATUS_READY

    def set_not_ready(status, message):
        job["status"] = status
        job["message"] = message
        if was_ready:
            job["ready_at"] = None

    if pair is None:
        pair = scan_file_pair(
            job["folder"], job["result_filename"], job["output_filename"]
        )
    job["last_scan_at"] = now
    job["next_scan_at"] = now + int(job["poll_seconds"])

    if not pair.get("folder_available"):
        set_not_ready(
            STATUS_WAITING,
            "Folder unavailable. Waiting without consuming a retry.",
        )
        job["stable_since"] = None
        return False

    result_sig = pair.get("result") or {}
    output_sig = pair.get("output") or {}
    if job.get("baseline_pending"):
        job["baseline_result"] = copy.deepcopy(result_sig)
        job["baseline_output"] = copy.deepcopy(output_sig)
        job["baseline_pending"] = False
        job["last_result_signature"] = copy.deepcopy(result_sig)
        job["last_output_signature"] = copy.deepcopy(output_sig)
        job["stable_since"] = now
        if job.get("accept_existing"):
            set_not_ready(
                STATUS_WAITING,
                "Baseline captured; current files may be accepted after settling.",
            )
        else:
            set_not_ready(
                STATUS_WAITING,
                "Baseline captured; both files must appear or change.",
            )
        return False

    if not result_sig.get("exists") or not output_sig.get("exists"):
        missing = []
        if not result_sig.get("exists"):
            missing.append(job["result_filename"])
        if not output_sig.get("exists"):
            missing.append(job["output_filename"])
        set_not_ready(
            STATUS_WAITING, "Waiting for: {0}.".format(", ".join(missing))
        )
        job["stable_since"] = None
        job["last_result_signature"] = copy.deepcopy(result_sig)
        job["last_output_signature"] = copy.deepcopy(output_sig)
        return False

    if not result_sig.get("readable") or not output_sig.get("readable"):
        set_not_ready(STATUS_WAITING, "Files exist but are not yet readable.")
        job["stable_since"] = None
        job["last_result_signature"] = copy.deepcopy(result_sig)
        job["last_output_signature"] = copy.deepcopy(output_sig)
        return False
    if int(result_sig.get("size") or 0) <= 0 or int(output_sig.get("size") or 0) <= 0:
        set_not_ready(STATUS_WAITING, "Files exist but are still empty.")
        job["stable_since"] = None
        job["last_result_signature"] = copy.deepcopy(result_sig)
        job["last_output_signature"] = copy.deepcopy(output_sig)
        return False

    if not job.get("accept_existing"):
        result_changed = signature_changed_from_baseline(result_sig, job.get("baseline_result"))
        output_changed = signature_changed_from_baseline(output_sig, job.get("baseline_output"))
        if not result_changed or not output_changed:
            waiting = []
            if not result_changed:
                waiting.append(job["result_filename"])
            if not output_changed:
                waiting.append(job["output_filename"])
            set_not_ready(
                STATUS_WAITING,
                "Pre-existing file baseline unchanged: {0}.".format(
                    ", ".join(waiting)
                ),
            )
            job["stable_since"] = None
            job["last_result_signature"] = copy.deepcopy(result_sig)
            job["last_output_signature"] = copy.deepcopy(output_sig)
            return False

    unchanged = (
        signatures_equal(result_sig, job.get("last_result_signature"))
        and signatures_equal(output_sig, job.get("last_output_signature"))
    )
    if not unchanged or job.get("stable_since") is None:
        job["stable_since"] = now
        set_not_ready(
            STATUS_SETTLING, "File signatures changed; settling timer restarted."
        )
        job["last_result_signature"] = copy.deepcopy(result_sig)
        job["last_output_signature"] = copy.deepcopy(output_sig)
        return False

    job["last_result_signature"] = copy.deepcopy(result_sig)
    job["last_output_signature"] = copy.deepcopy(output_sig)
    elapsed = now - float(job["stable_since"])
    if elapsed < int(job["settle_seconds"]):
        set_not_ready(
            STATUS_SETTLING,
            "Files stable for {0}; waiting for {1}.".format(
                format_duration(elapsed), format_duration(job["settle_seconds"])
            ),
        )
        return False

    parsed = parse_mapdl_output(output_sig["path"])
    if parsed.get("fatal_markers") or (
        parsed.get("error_count") is not None and parsed.get("error_count") != 0
    ):
        set_not_ready(STATUS_FAILED, parsed["message"])
        job["last_error"] = parsed["message"]
        job["failed_phase"] = "readiness"
        return False
    if not parsed.get("ready"):
        set_not_ready(STATUS_WAITING, parsed["message"])
        return False

    job["status"] = STATUS_READY
    job["message"] = "Stable result and output files are ready for Mechanical."
    if job.get("ready_at") is None:
        job["ready_at"] = now
    return True


class MonitorEngine(object):
    """Small lock-protected queue; it contains no CLR or Mechanical objects."""

    def __init__(self, jobs=None):
        self.jobs = list(jobs or [])
        self.active_job_id = None
        self.paused = False
        self.stop_after_current = False
        self.attention_required = False
        self._scan_in_flight = {}
        self._lock = threading.RLock()
        self._renumber()

    def _renumber(self):
        for index, job in enumerate(self.jobs):
            job["order"] = index + 1

    def add_job(self, job):
        with self._lock:
            validate_job_config(job)
            self.jobs.append(job)
            self._renumber()

    def _recovery_stop_is_unacknowledged(self, job):
        return bool(
            (job.get("status") == STATUS_ATTENTION or job.get("mutation_uncertain"))
            and not job.get("recovery_acknowledged")
        )

    def _refresh_attention_required(self):
        self.attention_required = any(
            self._recovery_stop_is_unacknowledged(job) for job in self.jobs
        )

    def can_mutate_job(self, job):
        with self._lock:
            return not self._recovery_stop_is_unacknowledged(job)

    def require_safe_job_mutation(self, job, action):
        if self._recovery_stop_is_unacknowledged(job):
            raise ValueError(
                "{0} is blocked until recovery is explicitly acknowledged for this job.".format(
                    action
                )
            )

    def update_job(self, job_id, replacement):
        with self._lock:
            current = self.get_job(job_id)
            self.require_safe_job_mutation(current, "Updating the job")
            replacement["scan_generation"] = int(current.get("scan_generation") or 0) + 1
            index = self.index_of(job_id)
            self.jobs[index] = replacement
            self._renumber()
            self._refresh_attention_required()

    def remove_job(self, job_id):
        with self._lock:
            current = self.get_job(job_id)
            self.require_safe_job_mutation(current, "Removing the job")
            self.jobs = [job for job in self.jobs if job.get("id") != job_id]
            self._renumber()
            self._refresh_attention_required()

    def move_job(self, job_id, offset):
        with self._lock:
            index = self.index_of(job_id)
            target = max(0, min(len(self.jobs) - 1, index + int(offset)))
            if target != index:
                self.jobs[index], self.jobs[target] = self.jobs[target], self.jobs[index]
                self._renumber()

    def index_of(self, job_id):
        for index, job in enumerate(self.jobs):
            if job.get("id") == job_id:
                return index
        raise KeyError(job_id)

    def get_job(self, job_id):
        return self.jobs[self.index_of(job_id)]

    def start(self, now=None):
        now = utc_timestamp() if now is None else float(now)
        with self._lock:
            for job in self.jobs:
                if job.get("status") == STATUS_PAUSED and job.get("paused_from_status") in SCAN_STATUSES:
                    job["status"] = job.pop("paused_from_status")
                    job["message"] = "Monitoring resumed."
                    job["next_scan_at"] = now
                    job["scan_generation"] = int(job.get("scan_generation") or 0) + 1
                elif job.get("status") in (STATUS_DRAFT, STATUS_FAILED, STATUS_PAUSED):
                    begin_monitoring_job(job, now)
            self.paused = False
            self.stop_after_current = False

    def pause(self):
        with self._lock:
            self.paused = True
            for job in self.jobs:
                if job.get("status") in SCAN_STATUSES:
                    job["paused_from_status"] = job.get("status")
                    job["status"] = STATUS_PAUSED
                    job["message"] = "Monitoring paused."
                    job["scan_generation"] = int(job.get("scan_generation") or 0) + 1

    def scan_due(self, now=None):
        now = utc_timestamp() if now is None else float(now)
        events = []
        changed = False
        with self._lock:
            if self.paused:
                return changed, events
            due_jobs = []
            for job in self.jobs:
                if job.get("status") not in SCAN_STATUSES:
                    continue
                if job.get("id") in self._scan_in_flight:
                    continue
                due = job.get("next_scan_at")
                if due is not None and float(due) > now:
                    continue
                token = {
                    "generation": int(job.get("scan_generation") or 0),
                    "status": job.get("status"),
                    "result_signature": copy.deepcopy(job.get("last_result_signature")),
                    "output_signature": copy.deepcopy(job.get("last_output_signature")),
                }
                self._scan_in_flight[job["id"]] = token
                due_jobs.append((copy.deepcopy(job), token))
        for scanned_job, token in due_jobs:
            try:
                before = (scanned_job.get("status"), scanned_job.get("message"))
                update_job_readiness(scanned_job, now)
                after = (scanned_job.get("status"), scanned_job.get("message"))
                with self._lock:
                    try:
                        current = self.get_job(scanned_job["id"])
                    except KeyError:
                        continue
                    if self._scan_in_flight.get(scanned_job["id"]) is not token:
                        continue
                    if (
                        self.paused
                        or current.get("status") not in SCAN_STATUSES
                        or int(current.get("scan_generation") or 0) != token["generation"]
                        or current.get("status") != token["status"]
                        or current.get("last_result_signature") != token["result_signature"]
                        or current.get("last_output_signature") != token["output_signature"]
                    ):
                        continue
                    scanned_job["scan_generation"] = token["generation"] + 1
                    current.clear()
                    current.update(scanned_job)
                    if before != after:
                        changed = True
                        events.append(
                            (
                                scanned_job.get("id"),
                                scanned_job.get("status"),
                                scanned_job.get("message"),
                            )
                        )
            except Exception:
                with self._lock:
                    for pending_job, pending_token in due_jobs:
                        if self._scan_in_flight.get(pending_job["id"]) is pending_token:
                            del self._scan_in_flight[pending_job["id"]]
                raise
            finally:
                with self._lock:
                    if self._scan_in_flight.get(scanned_job["id"]) is token:
                        del self._scan_in_flight[scanned_job["id"]]
        return changed, events

    def _set_phase_locked(self, job, phase, now):
        if phase not in ("import", "evaluate", "save"):
            phase = "import"
        self.active_job_id = job["id"]
        if phase == "import":
            job["status"] = STATUS_IMPORTING
            if job.get("import_started_at") is None:
                job["import_started_at"] = now
        elif phase == "evaluate":
            job["status"] = STATUS_EVALUATING
        else:
            job["status"] = STATUS_SAVING
        job["message"] = "Mechanical {0} is running.".format(phase)
        job["scan_generation"] = int(job.get("scan_generation") or 0) + 1

    def next_dispatch(self, now=None):
        now = utc_timestamp() if now is None else float(now)
        with self._lock:
            if self.active_job_id or self.paused or self.stop_after_current or self.attention_required:
                return None
            selected = None
            mutation_waiters = [
                job for job in self.jobs
                if job.get("status") == STATUS_RETRY_WAITING and job.get("mutation_uncertain")
            ]
            if mutation_waiters:
                due = [job for job in mutation_waiters if float(job.get("retry_due_at") or 0) <= now]
                if not due:
                    return None
                due.sort(key=lambda item: (float(item.get("retry_due_at") or 0), int(item["order"])))
                selected = due[0]
            if selected is None:
                retries = [
                    job for job in self.jobs
                    if job.get("status") == STATUS_RETRY_WAITING
                    and float(job.get("retry_due_at") or 0) <= now
                ]
                if retries:
                    retries.sort(key=lambda item: (float(item.get("retry_due_at") or 0), int(item["order"])))
                    selected = retries[0]
            if selected is None:
                ready = [
                    job for job in self.jobs
                    if job.get("status") == STATUS_READY
                    and job.get("id") not in self._scan_in_flight
                ]
                if ready:
                    ready.sort(key=lambda item: (float(item.get("ready_at") or now), int(item["order"])))
                    selected = ready[0]
            if selected is None:
                return None
            phase = selected.get("failed_phase") or "import"
            self._set_phase_locked(selected, phase, now)
            return selected

    def mark_phase(self, job, phase, now=None):
        now = utc_timestamp() if now is None else float(now)
        with self._lock:
            current = self.get_job(job["id"])
            if (
                current is not job
                or self.active_job_id != job["id"]
                or current.get("status") not in ACTIVE_STATUSES
            ):
                raise ValueError("The Mechanical dispatch claim is stale.")
            self._set_phase_locked(current, phase, now)

    def complete_phase(self, job, phase):
        with self._lock:
            job["completed_phase"] = phase
            job["failed_phase"] = None
            job["last_error"] = ""

    def finish_job(self, job, checkpoint, now=None):
        now = utc_timestamp() if now is None else float(now)
        with self._lock:
            job["status"] = STATUS_COMPLETED
            job["message"] = "Results evaluated and Save Database checkpoint verified."
            job["completed_phase"] = "save"
            job["completed_at"] = now
            job["checkpoint_at"] = now
            job["checkpoint"] = copy.deepcopy(checkpoint)
            job["retry_due_at"] = None
            job["mutation_uncertain"] = False
            job["recovery_acknowledged"] = False
            self.active_job_id = None
            if self.stop_after_current:
                self.paused = True

    def fail_phase(self, job, phase, message, may_have_mutated, now=None):
        now = utc_timestamp() if now is None else float(now)
        with self._lock:
            job["retry_count"] = int(job.get("retry_count") or 0) + 1
            job["failed_phase"] = phase
            job["last_error"] = str(message)
            job["mutation_uncertain"] = bool(may_have_mutated)
            job["recovery_acknowledged"] = False
            self.active_job_id = None
            if job["retry_count"] <= int(job["max_retries"]):
                job["status"] = STATUS_RETRY_WAITING
                job["retry_due_at"] = now + int(job["retry_delay_seconds"])
                job["message"] = "{0} failed; retry {1}/{2} at {3}.".format(
                    phase.capitalize(),
                    job["retry_count"],
                    job["max_retries"],
                    format_clock(job["retry_due_at"]),
                )
            else:
                if may_have_mutated or phase == "save":
                    job["status"] = STATUS_ATTENTION
                    job["message"] = (
                        "Retries exhausted after a possibly mutating Mechanical failure. "
                        "Restore the last database or explicitly accept the current model."
                    )
                    self.attention_required = True
                else:
                    job["status"] = STATUS_FAILED
                    job["message"] = "Retries exhausted: {0}".format(message)

    def acknowledge_recovery(self, job):
        with self._lock:
            job["recovery_acknowledged"] = True
            job["mutation_uncertain"] = False
            self._refresh_attention_required()

    def release_attention_for_retry(self, job, now=None):
        now = utc_timestamp() if now is None else float(now)
        with self._lock:
            self.acknowledge_recovery(job)
            job["status"] = STATUS_RETRY_WAITING
            job["retry_due_at"] = now
            job["message"] = "Operator accepted recovery state; retry is due now."
            self._refresh_attention_required()

    def skip_job(self, job):
        with self._lock:
            if job.get("id") == self.active_job_id:
                raise ValueError("The active Mechanical job cannot be skipped.")
            self.require_safe_job_mutation(job, "Skipping the job")
            job["status"] = STATUS_SKIPPED
            job["message"] = "Skipped by operator."
            job["retry_due_at"] = None
            self._refresh_attention_required()

    def to_state(self, project_path, checkpoint=None):
        with self._lock:
            return {
                "schema_version": SCHEMA_VERSION,
                "project_path": str(project_path or ""),
                "saved_at": utc_timestamp(),
                "active_job_id": self.active_job_id,
                "paused": self.paused,
                "stop_after_current": self.stop_after_current,
                "attention_required": self.attention_required,
                "last_verified_checkpoint": copy.deepcopy(checkpoint),
                "jobs": copy.deepcopy(self.jobs),
            }

    @classmethod
    def from_state(cls, state, expected_project_path):
        if int(state.get("schema_version", -1)) != SCHEMA_VERSION:
            raise ValueError("Unsupported monitor state schema.")
        if normalized_windows_path(state.get("project_path")) != normalized_windows_path(expected_project_path):
            raise ValueError("The saved monitor state belongs to a different Workbench project.")
        engine = cls(state.get("jobs") or [])
        engine.active_job_id = None
        engine.paused = True
        engine.stop_after_current = False
        engine.attention_required = bool(state.get("attention_required"))
        for job in engine.jobs:
            job.setdefault("recovery_acknowledged", False)
            job["scan_generation"] = int(job.get("scan_generation") or 0) + 1
            if job.get("status") == STATUS_READY:
                job["status"] = STATUS_SETTLING
                job["message"] = (
                    "Restored Ready job must pass a fresh file-settle cycle."
                )
                job["stable_since"] = None
                job["ready_at"] = None
                job["next_scan_at"] = utc_timestamp()
            if job.get("status") in ACTIVE_STATUSES:
                job["status"] = STATUS_ATTENTION
                job["message"] = "Mechanical closed during an active operation; reconcile manually."
                job["recovery_acknowledged"] = False
            if job.get("mutation_uncertain") or job.get("status") == STATUS_ATTENTION:
                job["recovery_acknowledged"] = False
        engine._refresh_attention_required()
        return engine


def atomic_write_json(path, payload):
    """Atomically replace JSON and retain one previous copy."""
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    temp_path = path + ".tmp"
    previous_path = path + ".previous"
    with io.open(temp_path, "w", encoding="utf-8") as handle:
        text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write(text)
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except (AttributeError, OSError):
            pass
    if hasattr(os, "replace"):
        if os.path.exists(path):
            shutil.copy2(path, previous_path)
        os.replace(temp_path, path)
    else:
        import clr
        clr.AddReference("System")
        from System.IO import File
        if os.path.exists(path):
            File.Replace(temp_path, path, previous_path, True)
        else:
            File.Move(temp_path, path)
    return path


def load_json(path):
    with io.open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def append_jsonl(path, payload):
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with io.open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False))
        handle.write(u"\n")
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except (AttributeError, OSError):
            pass


def signature_advanced(before, after):
    if not after or not after.get("exists") or not after.get("readable"):
        return False
    if not before or not before.get("exists"):
        return True
    return not signatures_equal(before, after)


class MechanicalPhaseError(Exception):
    def __init__(self, phase, message, may_have_mutated):
        Exception.__init__(self, message)
        self.phase = phase
        self.may_have_mutated = bool(may_have_mutated)


class MechanicalAdapter(object):
    """All Mechanical access is routed through the v261 UI-thread callable."""

    UNIT_LABELS = (
        ("UnitsMKS", "MKS (m, kg, N, s)"),
        ("UnitsCGS", "CGS (cm, g, dyn, s)"),
        ("UnitsNMM", "NMM (mm, kg, N, s)"),
        ("UnitsBFT", "BFT (ft, slug, lbf, s)"),
        ("UnitsBIN", "BIN (in, lbf-s2/in, lbf, s)"),
        ("UnitsUMKS", "uMKS (um, kg, N, s)"),
        ("UnitsKNMS", "KNMS (m, tonne, kN, s)"),
        ("UnitsGMMS", "GMMS (mm, tonne, N, s)"),
    )

    def __init__(self, global_namespace):
        self.extapi = global_namespace.get("ExtAPI")
        self.datamodel = global_namespace.get("DataModel")
        if self.extapi is None:
            raise RuntimeError("Run this script inside Workbench-launched Mechanical 2026 R1.")
        import clr
        clr.AddReference("System")
        from System import Func, Object
        from Ansys.Mechanical.DataModel.Enums import UnitSystemIDType
        self._func_type = Func[Object]
        self._unit_enum = UnitSystemIDType
        self._bound_project_path = None
        self._bound_user_files = None

    def invoke(self, function):
        return self.extapi.Application.InvokeUIThread(self._func_type(function))

    def _project_info_ui(self):
        project = self.extapi.DataModel.Project
        database_path = str(safe_get(project, "FilePath", "") or "")
        user_files = str(safe_get(project, "UserFiles", "") or "")
        project_directory = str(safe_get(project, "ProjectDirectory", "") or "")
        last_saved = str(safe_get(project, "LastSaved", "") or "")
        if not database_path or not os.path.isfile(database_path):
            raise RuntimeError(
                "Save the Workbench/Mechanical database before starting the monitor."
            )
        if not user_files:
            raise RuntimeError("Mechanical did not report a Workbench User Files folder.")
        if not os.path.isdir(user_files):
            os.makedirs(user_files)
        return {
            "project_path": database_path,
            "project_directory": project_directory,
            "user_files": user_files,
            "last_saved": last_saved,
            "database_signature": file_signature(database_path),
        }

    def project_info(self):
        return self.invoke(self._project_info_ui)

    def bind_project(self, project_info):
        project_value = non_none_text(project_info.get("project_path")).strip()
        user_files_value = non_none_text(project_info.get("user_files")).strip()
        if not project_value or not user_files_value:
            raise RuntimeError("The monitor cannot bind an incomplete Workbench project identity.")
        self._bound_project_path = normalized_windows_path(project_value)
        self._bound_user_files = normalized_windows_path(user_files_value)

    def _assert_bound_project_ui(self, phase):
        expected_project = getattr(self, "_bound_project_path", None)
        expected_user_files = getattr(self, "_bound_user_files", None)
        project = self.extapi.DataModel.Project
        current_project_value = non_none_text(safe_get(project, "FilePath", None)).strip()
        current_user_files_value = non_none_text(safe_get(project, "UserFiles", None)).strip()
        current_project = (
            normalized_windows_path(current_project_value) if current_project_value else None
        )
        current_user_files = (
            normalized_windows_path(current_user_files_value)
            if current_user_files_value
            else None
        )
        if (
            not expected_project
            or not expected_user_files
            or current_project != expected_project
            or current_user_files != expected_user_files
        ):
            raise MechanicalPhaseError(
                phase,
                "The Workbench project changed after the monitor opened. Close this "
                "window and run the script again for the current project.",
                False,
            )

    def _object_path(self, obj):
        names = []
        current = obj
        seen = set()
        while current is not None and len(names) < 32:
            identifier = id(current)
            if identifier in seen:
                break
            seen.add(identifier)
            name = str(safe_get(current, "Name", "") or "")
            if name:
                names.append(name)
            current = safe_get(current, "Parent", None)
        names.reverse()
        return " / ".join(names)

    def _analysis_choices_ui(self):
        model = safe_get(safe_get(self.extapi.DataModel, "Project", None), "Model", None)
        analyses = list(safe_get(model, "Analyses", None) or [])
        choices = []
        seen = set()
        for analysis in analyses:
            solution = safe_get(analysis, "Solution", None)
            if solution is None:
                continue
            analysis_id = safe_get(analysis, "ObjectId", None)
            solution_id = safe_get(solution, "ObjectId", None)
            if analysis_id is not None and solution_id is not None:
                key = (str(analysis_id), str(solution_id))
                if key in seen:
                    continue
                seen.add(key)
            analysis_name = str(safe_get(analysis, "Name", "Analysis"))
            solution_name = str(safe_get(solution, "Name", "Solution"))
            analysis_api_type = non_none_text(safe_get(analysis, "AnalysisType", None))
            analysis_physics_type = non_none_text(safe_get(analysis, "PhysicsType", None))
            analysis_type = normalize_analysis_family(
                analysis_api_type, analysis_physics_type
            )
            if analysis_type is None:
                continue
            analysis_clr_type = type_name(analysis)
            tree_path = self._object_path(analysis)
            choices.append(
                {
                    "analysis_object_id": int(analysis_id) if analysis_id is not None else None,
                    "solution_object_id": int(solution_id) if solution_id is not None else None,
                    "analysis_tree_path": tree_path,
                    "analysis_name": analysis_name,
                    "solution_name": solution_name,
                    "analysis_type": analysis_type,
                    "analysis_api_type": analysis_api_type,
                    "analysis_physics_type": analysis_physics_type,
                    "analysis_clr_type": analysis_clr_type,
                    "display": "{0} / {1}  [{2}; {3}]".format(
                        analysis_name,
                        solution_name,
                        analysis_type,
                        analysis_physics_type or "MAPDL",
                    ),
                }
            )
        return choices

    def analysis_choices(self):
        return self.invoke(self._analysis_choices_ui)

    def _resolve_solution_ui(self, job):
        model = safe_get(safe_get(self.extapi.DataModel, "Project", None), "Model", None)
        analyses = list(safe_get(model, "Analyses", None) or [])
        exact = []
        fallback = []
        for analysis in analyses:
            solution = safe_get(analysis, "Solution", None)
            if solution is None:
                continue
            analysis_id = safe_get(analysis, "ObjectId", None)
            solution_id = safe_get(solution, "ObjectId", None)
            analysis_api_type = non_none_text(safe_get(analysis, "AnalysisType", None))
            analysis_physics_type = non_none_text(safe_get(analysis, "PhysicsType", None))
            analysis_type = normalize_analysis_family(
                analysis_api_type, analysis_physics_type
            )
            identity_matches = (
                analysis_type is not None
                and self._object_path(analysis) == job.get("analysis_tree_path")
                and str(safe_get(analysis, "Name", "")) == job.get("analysis_name")
                and str(safe_get(solution, "Name", "")) == job.get("solution_name")
                and analysis_type == job.get("analysis_type")
                and analysis_api_type == job.get("analysis_api_type")
                and analysis_physics_type == job.get("analysis_physics_type")
                and type_name(analysis) == job.get("analysis_clr_type")
            )
            ids_match = (
                job.get("analysis_object_id") is not None
                and job.get("solution_object_id") is not None
                and analysis_id is not None
                and solution_id is not None
                and int(analysis_id) == int(job["analysis_object_id"])
                and int(solution_id) == int(job["solution_object_id"])
            )
            if ids_match and identity_matches:
                exact.append(solution)
                continue
            if identity_matches:
                fallback.append(solution)
        matches = exact or fallback
        if len(matches) != 1:
            if not matches:
                raise RuntimeError("The selected Mechanical analysis/Solution no longer exists.")
            raise RuntimeError("The analysis identity is ambiguous; select the analysis again.")
        return matches[0]

    def resolve_solution(self, job):
        def resolve():
            self._resolve_solution_ui(job)
            return True

        return bool(self.invoke(resolve))

    def _unit_value(self, unit_symbol):
        try:
            return getattr(self._unit_enum, str(unit_symbol))
        except Exception:
            raise RuntimeError("Unsupported v261 UnitSystemIDType symbol: {0}".format(unit_symbol))

    def result_path(self, job):
        return os.path.join(job["folder"], job["result_filename"])

    def _status_token(self, value):
        return re.sub(r"[^a-z0-9]", "", non_none_text(value).lower())

    def _bad_status(self, value):
        text = self._status_token(value)
        if not text:
            return True
        return any(
            token in text
            for token in (
                "solverequired",
                "solvefailed",
                "notsolved",
                "unsolved",
                "postprocessingrequired",
                "notevaluated",
                "unevaluated",
                "failed",
                "invalid",
                "error",
            )
        )

    def _failed_descendants(self, solution):
        failed = []
        pending = list(safe_get(solution, "Children", None) or [])
        seen = set()
        while pending:
            obj = pending.pop(0)
            identifier = id(obj)
            if identifier in seen:
                continue
            seen.add(identifier)
            state = safe_get(obj, "ObjectState", None)
            status = safe_get(obj, "Status", None)
            state_token = self._status_token(state)
            status_text = non_none_text(status).strip()
            if (
                self._bad_status(state)
                or state_token not in ("solved", "uptodate")
                or (status_text and self._bad_status(status))
            ):
                failed.append(
                    "{0}: state={1}, status={2}".format(
                        safe_get(obj, "Name", type_name(obj)), state, status
                    )
                )
            try:
                pending.extend(list(safe_get(obj, "Children", None) or []))
            except Exception:
                pass
        return failed

    def _verify_loaded_ui(self, job, require_healthy):
        solution = self._resolve_solution_ui(job)
        result_path = self.result_path(job)
        if not bool(solution.IsResultFileSameAsLoaded(result_path)):
            raise MechanicalPhaseError(
                "import",
                "Mechanical did not confirm the requested result file as loaded.",
                True,
            )
        reported_path = str(safe_get(solution, "ResultFilePath", "") or "")
        if reported_path and normalized_windows_path(reported_path) != normalized_windows_path(result_path):
            raise MechanicalPhaseError(
                "import", "Mechanical reported a different loaded result path.", True
            )
        if require_healthy:
            status = safe_get(solution, "Status", None)
            if (
                self._bad_status(status)
                or self._status_token(status) not in ("done", "solved", "uptodate")
            ):
                raise MechanicalPhaseError(
                    "evaluate",
                    "Solution status is not acceptable after result evaluation: {0}".format(status),
                    True,
                )
            failed = self._failed_descendants(solution)
            if failed:
                raise MechanicalPhaseError(
                    "evaluate",
                    "One or more result objects failed: {0}".format("; ".join(failed[:8])),
                    True,
                )
        return {
            "reported_path": reported_path,
            "result_file_size": int(safe_get(solution, "ResultFileSize", 0) or 0),
            "result_file_timestamp": str(safe_get(solution, "ResultFileTimestamp", "") or ""),
            "result_file_unit_system": non_none_text(
                safe_get(solution, "ResultFileUnitSystem", None)
            ),
            "solution_status": non_none_text(safe_get(solution, "Status", None)),
        }

    def verify_loaded(self, job, require_healthy=True):
        return self.invoke(lambda: self._verify_loaded_ui(job, require_healthy))

    def _import_ui(self, job):
        result_path = self.result_path(job)
        signature = file_signature(result_path)
        if not signature.get("exists") or not signature.get("readable") or not signature.get("size"):
            raise MechanicalPhaseError(
                "import", "The result file disappeared or became unreadable before import.", False
            )
        solution = self._resolve_solution_ui(job)
        self._assert_bound_project_ui("import")
        try:
            solution.ReadGivenAnsysResultFileByReference(
                result_path, self._unit_value(job["unit_system"])
            )
        except Exception as exc:
            raise MechanicalPhaseError(
                "import", "ReadGivenAnsysResultFileByReference failed: {0}".format(exc), True
            )
        return self._verify_loaded_ui(job, False)

    def import_result(self, job):
        return self.invoke(lambda: self._import_ui(job))

    def _evaluate_ui(self, job):
        solution = self._resolve_solution_ui(job)
        self._assert_bound_project_ui("evaluate")
        try:
            solution.EvaluateAllResults()
        except Exception as exc:
            raise MechanicalPhaseError(
                "evaluate", "EvaluateAllResults failed: {0}".format(exc), True
            )
        return self._verify_loaded_ui(job, True)

    def evaluate_results(self, job):
        return self.invoke(lambda: self._evaluate_ui(job))

    def _save_ui(self, job):
        self._assert_bound_project_ui("save")
        self._verify_loaded_ui(job, True)
        project = self.extapi.DataModel.Project
        database_path = str(safe_get(project, "FilePath", "") or "")
        if not database_path or not os.path.isfile(database_path):
            raise MechanicalPhaseError("save", "The Mechanical database path is unavailable.", False)
        before = file_signature(database_path)
        try:
            engine = self.extapi.Application.ScriptByName("jscript")
            self._assert_bound_project_ui("save")
            engine.ExecuteCommand("DS.Script.doFileSaveDatabase();")
        except MechanicalPhaseError:
            raise
        except Exception as exc:
            raise MechanicalPhaseError(
                "save", "Workbench Save Database failed: {0}".format(exc), True
            )

        deadline = time.time() + 30.0
        previous = None
        stable_count = 0
        candidate = None
        while time.time() < deadline:
            candidate = file_signature(database_path)
            if signature_advanced(before, candidate):
                if signatures_equal(candidate, previous):
                    stable_count += 1
                else:
                    stable_count = 0
                if stable_count >= 1:
                    break
            previous = copy.deepcopy(candidate)
            time.sleep(0.5)
        if not signature_advanced(before, candidate) or stable_count < 1:
            raise MechanicalPhaseError(
                "save",
                "Save Database returned but the .mechdb signature did not advance and stabilize.",
                True,
            )
        self._verify_loaded_ui(job, True)
        return {
            "database_path": database_path,
            "database_signature": candidate,
            "project_last_saved": str(safe_get(project, "LastSaved", "") or ""),
            "result_path": self.result_path(job),
            "verified_at": utc_timestamp(),
        }

    def save_database(self, job):
        return self.invoke(lambda: self._save_ui(job))

    def reconcile_completed_job(self, job):
        checkpoint = job.get("checkpoint") or {}
        stored = checkpoint.get("database_signature") or {}

        def check():
            project = self.extapi.DataModel.Project
            current_path = str(safe_get(project, "FilePath", "") or "")
            if normalized_windows_path(current_path) != normalized_windows_path(
                checkpoint.get("database_path")
            ):
                return False
            current = file_signature(current_path)
            if not current.get("exists") or float(current.get("mtime") or 0) < float(stored.get("mtime") or 0):
                return False
            try:
                self._verify_loaded_ui(job, True)
            except Exception:
                return False
            return True

        return bool(self.invoke(check))


def _load_winforms():
    import clr
    clr.AddReference("System")
    clr.AddReference("System.Drawing")
    clr.AddReference("System.Windows.Forms")
    from System import Action, Decimal
    from System.Drawing import Color, ContentAlignment, Font, FontStyle, Point, Size
    from System.Windows.Forms import (
        AnchorStyles,
        Application,
        AutoScaleMode,
        BorderStyle,
        Button,
        CheckBox,
        ComboBox,
        ComboBoxStyle,
        ColumnStyle,
        DataGridView,
        DataGridViewAutoSizeRowsMode,
        DataGridViewCellBorderStyle,
        DataGridViewColumnHeadersHeightSizeMode,
        DataGridViewSelectionMode,
        DialogResult,
        DockStyle,
        FlowDirection,
        FlowLayoutPanel,
        FlatStyle,
        FolderBrowserDialog,
        Form,
        FormBorderStyle,
        FormStartPosition,
        FormWindowState,
        Label,
        MessageBox,
        MessageBoxButtons,
        MessageBoxIcon,
        NumericUpDown,
        OpenFileDialog,
        Orientation,
        Padding,
        Panel,
        ProgressBarStyle,
        RowStyle,
        ScrollBars,
        SplitContainer,
        StatusStrip,
        SizeType,
        TableLayoutPanel,
        TextBox,
        ToolStripStatusLabel,
        ToolStripProgressBar,
        ToolTip,
    )
    return locals()


class HpcResultMonitorForm(object):
    """One modeless native operator console; no external UI dependency."""

    STATUS_COLORS = {
        STATUS_DRAFT: (92, 104, 116),
        STATUS_WAITING: (79, 106, 128),
        STATUS_SETTLING: (31, 111, 170),
        STATUS_READY: (17, 122, 101),
        STATUS_IMPORTING: (0, 95, 184),
        STATUS_EVALUATING: (0, 95, 184),
        STATUS_SAVING: (0, 95, 184),
        STATUS_RETRY_WAITING: (183, 111, 0),
        STATUS_COMPLETED: (34, 139, 34),
        STATUS_FAILED: (190, 45, 45),
        STATUS_ATTENTION: (190, 45, 45),
        STATUS_SKIPPED: (110, 110, 110),
        STATUS_PAUSED: (92, 104, 116),
    }

    def __init__(self, adapter, ui):
        self.adapter = adapter
        self.ui = ui
        self.project = adapter.project_info()
        self.adapter.bind_project(self.project)
        self.state_path = os.path.join(
            self.project["user_files"], "ansys_mechanical_hpc_result_monitor_state.json"
        )
        self.event_path = os.path.join(
            self.project["user_files"], "ansys_mechanical_hpc_result_monitor_events.jsonl"
        )
        self.engine = MonitorEngine()
        self.last_verified_checkpoint = None
        self.analysis_choices = []
        self._cancel_event = threading.Event()
        self._refresh_lock = threading.Lock()
        self._refresh_pending = False
        self._pending_persist = False
        self._pending_worker_events = []
        self._close_after_current = False
        self._closing = False
        self._selected_job_id = None

        Form = ui["Form"]
        Size = ui["Size"]
        Font = ui["Font"]
        AutoScaleMode = ui["AutoScaleMode"]
        FormBorderStyle = ui["FormBorderStyle"]
        FormStartPosition = ui["FormStartPosition"]
        self.form = Form()
        self.form.Text = "ANSYS Mechanical HPC Result Monitor"
        self.form.ClientSize = Size(1420, 880)
        self.form.MinimumSize = Size(1120, 700)
        self.form.AutoScaleMode = AutoScaleMode.Dpi
        self.form.Font = Font("Segoe UI", 9.0)
        self.form.FormBorderStyle = FormBorderStyle.Sizable
        self.form.StartPosition = FormStartPosition.CenterScreen
        self.form.FormClosing += self._on_form_closing

        self.tool_tip = ui["ToolTip"]()
        self.tool_tip.AutoPopDelay = 15000
        self.tool_tip.InitialDelay = 350
        self.tool_tip.ReshowDelay = 100
        self._build_layout()
        self._reload_analysis_choices(select_first=True)
        self._refresh_grid()
        self._start_worker()
        self._log("INFO", "Monitor opened for {0}.".format(self.project["project_path"]))

    def _set_tooltip(self, control, text):
        control.AccessibleDescription = text
        self.tool_tip.SetToolTip(control, text)

    def _button(self, text, tooltip, handler, accent=False):
        Button = self.ui["Button"]
        Size = self.ui["Size"]
        Color = self.ui["Color"]
        button = Button()
        button.Text = text
        button.AutoSize = False
        button.Size = Size(max(82, 18 + len(text) * 7), 30)
        button.Margin = self.ui["Padding"](3, 5, 3, 3)
        button.FlatStyle = self.ui["FlatStyle"].System
        if accent:
            button.BackColor = Color.FromArgb(0, 95, 184)
            button.ForeColor = Color.White
            button.UseVisualStyleBackColor = False
        button.AccessibleName = text
        self._set_tooltip(button, tooltip)
        button.Click += handler
        return button

    def _label(self, text, bold=False):
        Label = self.ui["Label"]
        Font = self.ui["Font"]
        FontStyle = self.ui["FontStyle"]
        label = Label()
        label.Text = text
        label.AutoSize = True
        label.Margin = self.ui["Padding"](3, 7, 5, 3)
        if bold:
            label.Font = Font("Segoe UI", 9.0, FontStyle.Bold)
        return label

    def _build_layout(self):
        ui = self.ui
        DockStyle = ui["DockStyle"]
        Color = ui["Color"]
        Padding = ui["Padding"]
        SizeType = ui["SizeType"]
        Orientation = ui["Orientation"]

        root = ui["TableLayoutPanel"]()
        root.Dock = DockStyle.Fill
        root.BackColor = Color.FromArgb(245, 247, 249)
        root.Padding = Padding(10)
        root.ColumnCount = 1
        root.RowCount = 3
        root.ColumnStyles.Add(ui["ColumnStyle"](SizeType.Percent, 100.0))
        root.RowStyles.Add(ui["RowStyle"](SizeType.Absolute, 68.0))
        root.RowStyles.Add(ui["RowStyle"](SizeType.Absolute, 43.0))
        root.RowStyles.Add(ui["RowStyle"](SizeType.Percent, 100.0))

        header = ui["Panel"]()
        header.Dock = DockStyle.Fill
        header.BackColor = Color.White
        header.Padding = Padding(14, 9, 14, 7)
        title = self._label("HPC RESULT MONITOR", True)
        title.Font = ui["Font"]("Segoe UI Semibold", 14.0, ui["FontStyle"].Bold)
        title.ForeColor = Color.FromArgb(34, 47, 62)
        title.Location = ui["Point"](14, 9)
        project_label = self._label(self.project["project_path"], False)
        project_label.ForeColor = Color.FromArgb(80, 90, 100)
        project_label.Location = ui["Point"](16, 36)
        project_label.AutoEllipsis = True
        project_label.Width = 760
        self.counter_label = self._label("Waiting 0 | Ready 0 | Active 0 | Completed 0 | Failed 0 | Attention 0", True)
        self.counter_label.AutoSize = False
        self.counter_label.TextAlign = ui["ContentAlignment"].MiddleRight
        self.counter_label.Dock = DockStyle.Right
        self.counter_label.Width = 610
        self.counter_label.ForeColor = Color.FromArgb(34, 67, 94)
        self._set_tooltip(self.counter_label, "Live count of jobs in the major operational states.")
        header.Controls.Add(title)
        header.Controls.Add(project_label)
        header.Controls.Add(self.counter_label)

        toolbar = ui["FlowLayoutPanel"]()
        toolbar.Dock = DockStyle.Fill
        toolbar.BackColor = Color.FromArgb(232, 237, 242)
        toolbar.FlowDirection = ui["FlowDirection"].LeftToRight
        toolbar.WrapContents = False
        toolbar.AutoScroll = True
        self.add_button = self._button("Add", "Add the configured job to the queue.", self._add_clicked)
        self.update_button = self._button("Update", "Apply editor values to the selected queue job.", self._update_clicked)
        self.remove_button = self._button("Remove", "Remove the selected inactive job.", self._remove_clicked)
        self.up_button = self._button("Move Up", "Move the selected job earlier for FIFO tie-breaking.", self._move_up_clicked)
        self.down_button = self._button("Move Down", "Move the selected job later for FIFO tie-breaking.", self._move_down_clicked)
        self.start_button = self._button("Start Monitoring", "Capture baselines and begin periodic folder checks.", self._start_clicked, True)
        self.pause_button = self._button("Pause", "Pause future scans and dispatch after the current scan/Mechanical call.", self._pause_clicked)
        self.stop_button = self._button("Stop After Current", "Finish the active Mechanical chain, then prevent another dispatch.", self._stop_clicked)
        self.retry_button = self._button("Retry Now", "Make the selected failed/retry job immediately eligible.", self._retry_clicked)
        self.skip_button = self._button("Skip", "Skip the selected inactive job and continue the queue.", self._skip_clicked)
        self.restore_button = self._button("Restore Session", "Load and reconcile the per-project saved queue state.", self._restore_clicked)
        self.log_button = self._button("Open Log", "Open the append-only JSONL event log.", self._open_log_clicked)
        for button in (
            self.add_button, self.update_button, self.remove_button, self.up_button,
            self.down_button, self.start_button, self.pause_button, self.stop_button,
            self.retry_button, self.skip_button, self.restore_button, self.log_button,
        ):
            toolbar.Controls.Add(button)

        body = ui["SplitContainer"]()
        body.Dock = DockStyle.Fill
        body.Size = ui["Size"](1380, 740)
        body.Orientation = Orientation.Horizontal
        body.SplitterDistance = 590
        body.Panel1MinSize = 360
        body.Panel2MinSize = 120
        body.BackColor = Color.FromArgb(210, 216, 222)

        upper = ui["SplitContainer"]()
        upper.Dock = DockStyle.Fill
        upper.Size = ui["Size"](1380, 590)
        upper.Orientation = Orientation.Vertical
        upper.SplitterDistance = 930
        upper.Panel1MinSize = 600
        upper.Panel2MinSize = 370
        self._build_grid(upper.Panel1)
        self._build_editor(upper.Panel2)
        body.Panel1.Controls.Add(upper)

        log_panel = ui["TableLayoutPanel"]()
        log_panel.Dock = DockStyle.Fill
        log_panel.Padding = Padding(8, 5, 8, 5)
        log_panel.RowCount = 2
        log_panel.ColumnCount = 1
        log_panel.RowStyles.Add(ui["RowStyle"](SizeType.Absolute, 24.0))
        log_panel.RowStyles.Add(ui["RowStyle"](SizeType.Percent, 100.0))
        log_title = self._label("EVENT LOG", True)
        log_title.ForeColor = Color.FromArgb(34, 67, 94)
        self.event_box = ui["TextBox"]()
        self.event_box.Dock = DockStyle.Fill
        self.event_box.Multiline = True
        self.event_box.ReadOnly = True
        self.event_box.ScrollBars = ui["ScrollBars"].Both
        self.event_box.WordWrap = False
        self.event_box.BackColor = Color.FromArgb(28, 34, 40)
        self.event_box.ForeColor = Color.FromArgb(224, 232, 240)
        self.event_box.Font = ui["Font"]("Consolas", 8.5)
        self.event_box.AccessibleName = "Monitor event log"
        self._set_tooltip(self.event_box, "Copyable operator log; durable JSONL is stored in Workbench User Files.")
        log_panel.Controls.Add(log_title, 0, 0)
        log_panel.Controls.Add(self.event_box, 0, 1)
        body.Panel2.Controls.Add(log_panel)

        root.Controls.Add(header, 0, 0)
        root.Controls.Add(toolbar, 0, 1)
        root.Controls.Add(body, 0, 2)
        self.form.Controls.Add(root)
        self._build_status_strip()

    def _build_grid(self, parent):
        ui = self.ui
        DockStyle = ui["DockStyle"]
        Color = ui["Color"]
        grid = ui["DataGridView"]()
        grid.Dock = DockStyle.Fill
        grid.ReadOnly = True
        grid.AllowUserToAddRows = False
        grid.AllowUserToDeleteRows = False
        grid.AllowUserToResizeRows = False
        grid.MultiSelect = False
        grid.SelectionMode = ui["DataGridViewSelectionMode"].FullRowSelect
        grid.AutoGenerateColumns = False
        grid.BackgroundColor = Color.White
        grid.BorderStyle = ui["BorderStyle"].FixedSingle
        grid.CellBorderStyle = ui["DataGridViewCellBorderStyle"].SingleHorizontal
        grid.ColumnHeadersHeightSizeMode = ui["DataGridViewColumnHeadersHeightSizeMode"].AutoSize
        grid.AutoSizeRowsMode = ui["DataGridViewAutoSizeRowsMode"].AllCellsExceptHeaders
        grid.RowHeadersVisible = False
        grid.AccessibleName = "HPC result import queue"
        columns = (
            ("Order", "#", 38, "Queue order and FIFO tie-breaker."),
            ("Analysis", "Analysis / Solution", 180, "Selected Mechanical environment."),
            ("Type", "Analysis type", 120, "Mechanical analysis object type."),
            ("Folder", "Folder", 180, "Exact non-recursive Windows folder."),
            ("Result", "Result", 80, "Exact .rst or .rth filename."),
            ("Output", "Output", 80, "Exact MAPDL .out filename."),
            ("Status", "Status", 105, "Current queue and Mechanical phase."),
            ("Message", "Last message", 260, "Latest readiness or operation detail."),
            ("Waiting", "Waiting", 85, "Elapsed time since monitoring started."),
            ("ReadyAt", "Ready at", 130, "Time the stable completed pair became ready."),
            ("ImportAt", "Import start", 130, "First Mechanical import start time."),
            ("Elapsed", "Operation", 85, "Elapsed active Mechanical time."),
            ("Retry", "Retry", 52, "Failures consumed versus configured retries."),
            ("Checkpoint", "Checkpoint", 130, "Verified Save Database checkpoint time."),
        )
        for name, header, width, tip in columns:
            index = grid.Columns.Add(name, header)
            column = grid.Columns[index]
            column.Width = width
            column.HeaderCell.ToolTipText = tip
        grid.SelectionChanged += self._grid_selection_changed
        self.grid = grid
        parent.Controls.Add(grid)

    def _build_editor(self, parent):
        ui = self.ui
        DockStyle = ui["DockStyle"]
        SizeType = ui["SizeType"]
        Padding = ui["Padding"]
        Color = ui["Color"]
        ComboBoxStyle = ui["ComboBoxStyle"]
        editor = ui["TableLayoutPanel"]()
        editor.Dock = DockStyle.Fill
        editor.BackColor = Color.White
        editor.Padding = Padding(12, 8, 12, 8)
        editor.ColumnCount = 3
        editor.RowCount = 13
        editor.ColumnStyles.Add(ui["ColumnStyle"](SizeType.Absolute, 105.0))
        editor.ColumnStyles.Add(ui["ColumnStyle"](SizeType.Percent, 100.0))
        editor.ColumnStyles.Add(ui["ColumnStyle"](SizeType.Absolute, 72.0))
        editor.RowStyles.Add(ui["RowStyle"](SizeType.Absolute, 30.0))
        for index in range(1, 12):
            editor.RowStyles.Add(ui["RowStyle"](SizeType.Absolute, 35.0))
        editor.RowStyles.Add(ui["RowStyle"](SizeType.Percent, 100.0))

        title = self._label("JOB CONFIGURATION", True)
        title.ForeColor = Color.FromArgb(34, 67, 94)
        editor.Controls.Add(title, 0, 0)
        editor.SetColumnSpan(title, 3)

        self.analysis_combo = ui["ComboBox"]()
        self.analysis_combo.Dock = DockStyle.Fill
        self.analysis_combo.DropDownStyle = ComboBoxStyle.DropDownList
        self.analysis_combo.AccessibleName = "Mechanical analysis and Solution"
        self._set_tooltip(self.analysis_combo, "Target analysis/Solution from the currently open Mechanical tree.")
        self._editor_row(editor, 1, "Analysis", self.analysis_combo, None)

        self.folder_box = ui["TextBox"]()
        self.folder_button = self._button("Browse", "Choose the exact Windows-visible HPC folder.", self._browse_folder_clicked)
        self._set_tooltip(self.folder_box, "Absolute folder only. No subfolder search is performed; UNC paths are preferred.")
        self._editor_row(editor, 2, "Folder", self.folder_box, self.folder_button)

        self.result_box = ui["TextBox"]()
        self.result_box.Text = "file.rst"
        self.result_button = self._button("Browse", "Choose the exact .rst or .rth file.", self._browse_result_clicked)
        self._set_tooltip(self.result_box, "Exact MAPDL result filename; paths and subfolders are rejected.")
        self._editor_row(editor, 3, "Result file", self.result_box, self.result_button)

        self.output_box = ui["TextBox"]()
        self.output_box.Text = "file.out"
        self.output_button = self._button("Browse", "Choose the exact MAPDL .out file.", self._browse_output_clicked)
        self._set_tooltip(self.output_box, "Exact output filename containing RUN COMPLETED and the final error count.")
        self._editor_row(editor, 4, "Output file", self.output_box, self.output_button)

        self.unit_combo = ui["ComboBox"]()
        self.unit_combo.Dock = DockStyle.Fill
        self.unit_combo.DropDownStyle = ComboBoxStyle.DropDownList
        for symbol, label in MechanicalAdapter.UNIT_LABELS:
            self.unit_combo.Items.Add("{0} - {1}".format(symbol, label))
        self.unit_combo.SelectedIndex = -1
        self._set_tooltip(self.unit_combo, "Explicit v261 UnitSystemIDType used to interpret the external result file.")
        self._editor_row(editor, 5, "Units", self.unit_combo, None)

        self.poll_numeric = self._numeric(DEFAULT_POLL_SECONDS, 1, 86400, "Seconds between folder checks for this job.")
        self._editor_row(editor, 6, "Poll (s)", self.poll_numeric, None)
        self.settle_numeric = self._numeric(DEFAULT_SETTLE_SECONDS, 1, 86400, "Both file signatures must remain unchanged for this many seconds.")
        self._editor_row(editor, 7, "Settle (s)", self.settle_numeric, None)
        self.retries_numeric = self._numeric(DEFAULT_MAX_RETRIES, 0, 20, "Retries after the initial Mechanical attempt.")
        self._editor_row(editor, 8, "Retries", self.retries_numeric, None)
        self.retry_delay_numeric = self._numeric(DEFAULT_RETRY_DELAY_SECONDS, 1, 86400, "Seconds before a failed Mechanical phase is eligible again.")
        self._editor_row(editor, 9, "Retry delay", self.retry_delay_numeric, None)

        self.accept_existing_box = ui["CheckBox"]()
        self.accept_existing_box.Text = "Accept current completed files"
        self.accept_existing_box.AutoSize = True
        self._set_tooltip(
            self.accept_existing_box,
            "Off by default: both result and output files must appear or change after Start Monitoring.",
        )
        self._editor_row(editor, 10, "Pre-existing", self.accept_existing_box, None)

        self.validation_label = self._label("Ready to add a job.", False)
        self.validation_label.ForeColor = Color.FromArgb(80, 90, 100)
        self.validation_label.AutoSize = False
        self.validation_label.Dock = DockStyle.Fill
        self.validation_label.AutoEllipsis = True
        editor.Controls.Add(self.validation_label, 0, 11)
        editor.SetColumnSpan(self.validation_label, 3)

        note = self._label(
            "Safety: Mechanical imports, evaluation, and Save Database run one at a time. "
            "The interface may not repaint while Evaluate All Results is executing.",
            False,
        )
        note.AutoSize = False
        note.Dock = DockStyle.Fill
        note.ForeColor = Color.FromArgb(88, 99, 110)
        editor.Controls.Add(note, 0, 12)
        editor.SetColumnSpan(note, 3)
        parent.Controls.Add(editor)

    def _editor_row(self, table, row, label_text, control, button):
        label = self._label(label_text, False)
        control.Dock = self.ui["DockStyle"].Fill
        control.Margin = self.ui["Padding"](3, 4, 3, 4)
        control.AccessibleName = label_text
        table.Controls.Add(label, 0, row)
        table.Controls.Add(control, 1, row)
        if button is not None:
            button.Dock = self.ui["DockStyle"].Fill
            button.Margin = self.ui["Padding"](3, 3, 3, 3)
            table.Controls.Add(button, 2, row)
        else:
            table.SetColumnSpan(control, 2)

    def _numeric(self, value, minimum, maximum, tooltip):
        control = self.ui["NumericUpDown"]()
        control.Minimum = self.ui["Decimal"](minimum)
        control.Maximum = self.ui["Decimal"](maximum)
        control.Value = self.ui["Decimal"](value)
        control.ThousandsSeparator = True
        self._set_tooltip(control, tooltip)
        return control

    def _set_numeric(self, control, value):
        bounded = max(
            int(str(control.Minimum)), min(int(str(control.Maximum)), int(value))
        )
        control.Value = self.ui["Decimal"](bounded)

    def _build_status_strip(self):
        strip = self.ui["StatusStrip"]()
        strip.SizingGrip = False
        strip.ShowItemToolTips = True
        self.busy_indicator = self.ui["ToolStripProgressBar"]()
        self.busy_indicator.Style = self.ui["ProgressBarStyle"].Marquee
        self.busy_indicator.MarqueeAnimationSpeed = 30
        self.busy_indicator.Width = 90
        self.busy_indicator.Visible = False
        self.busy_indicator.ToolTipText = (
            "Indeterminate activity while Mechanical imports, evaluates, or saves. "
            "No percentage or ETA is inferred."
        )
        self.operation_status = self.ui["ToolStripStatusLabel"]("Operation: Idle")
        self.scan_status = self.ui["ToolStripStatusLabel"]("Last scan: - | Next scan: -")
        self.folder_status = self.ui["ToolStripStatusLabel"]("Folders: -")
        self.checkpoint_status = self.ui["ToolStripStatusLabel"]("Checkpoint: -")
        self.operation_status.ToolTipText = "Current serialized Mechanical operation."
        self.scan_status.ToolTipText = "Most recent and next scheduled folder scan."
        self.folder_status.ToolTipText = "Number of configured folders currently unavailable."
        self.checkpoint_status.ToolTipText = "Most recent verified Save Database checkpoint."
        self.operation_status.Spring = True
        self.operation_status.TextAlign = self.ui["ContentAlignment"].MiddleLeft
        strip.Items.Add(self.busy_indicator)
        strip.Items.Add(self.operation_status)
        strip.Items.Add(self.scan_status)
        strip.Items.Add(self.folder_status)
        strip.Items.Add(self.checkpoint_status)
        self.status_strip = strip
        self.form.Controls.Add(strip)

    def _reload_analysis_choices(self, preferred_identity=None, select_first=False):
        if preferred_identity is None:
            selected_index = int(self.analysis_combo.SelectedIndex)
            if 0 <= selected_index < len(self.analysis_choices):
                preferred_identity = analysis_identity_tuple(
                    self.analysis_choices[selected_index]
                )
        choices = self.adapter.analysis_choices()
        self.analysis_combo.Items.Clear()
        for choice in choices:
            self.analysis_combo.Items.Add(choice["display"])
        self.analysis_choices = choices
        matches = []
        if preferred_identity is not None:
            matches = [
                index
                for index, choice in enumerate(choices)
                if analysis_identity_tuple(choice) == preferred_identity
            ]
        if len(matches) == 1:
            self.analysis_combo.SelectedIndex = matches[0]
            self.validation_label.Text = "Ready to add a job."
        elif select_first and self.analysis_combo.Items.Count:
            self.analysis_combo.SelectedIndex = 0
            self.validation_label.Text = "Ready to add a job."
        elif self.analysis_combo.Items.Count:
            self.analysis_combo.SelectedIndex = -1
            self.validation_label.Text = "Select a current Mechanical analysis/Solution."
        else:
            self.analysis_combo.SelectedIndex = -1
            self.validation_label.Text = (
                "No supported Static Structural, Modal, Transient Structural, or "
                "Steady-State Thermal Solution was found."
            )
        return choices

    def _selected_job(self):
        if not self._selected_job_id:
            return None
        try:
            return self.engine.get_job(self._selected_job_id)
        except KeyError:
            return None

    def _job_from_editor(self, existing=None):
        index = int(self.analysis_combo.SelectedIndex)
        if index < 0 or index >= len(self.analysis_choices):
            raise ValueError("Choose a Mechanical analysis/Solution.")
        choice = self.analysis_choices[index]
        unit_text = str(self.unit_combo.SelectedItem or "")
        unit_symbol = unit_text.split(" - ", 1)[0].strip()
        values = {
            "analysis_object_id": choice["analysis_object_id"],
            "solution_object_id": choice["solution_object_id"],
            "analysis_tree_path": choice["analysis_tree_path"],
            "analysis_name": choice["analysis_name"],
            "solution_name": choice["solution_name"],
            "analysis_type": choice["analysis_type"],
            "analysis_api_type": choice["analysis_api_type"],
            "analysis_physics_type": choice["analysis_physics_type"],
            "analysis_clr_type": choice["analysis_clr_type"],
            "folder": str(self.folder_box.Text).strip(),
            "result_filename": str(self.result_box.Text).strip(),
            "output_filename": str(self.output_box.Text).strip(),
            "unit_system": unit_symbol,
            "poll_seconds": int(str(self.poll_numeric.Value)),
            "settle_seconds": int(str(self.settle_numeric.Value)),
            "max_retries": int(str(self.retries_numeric.Value)),
            "retry_delay_seconds": int(str(self.retry_delay_numeric.Value)),
            "accept_existing": bool(self.accept_existing_box.Checked),
        }
        if existing is None:
            job = new_job(**values)
        else:
            job = new_job(**values)
            job["id"] = existing["id"]
            job["order"] = existing["order"]
            job["created_at"] = existing["created_at"]
        validate_job_config(job)
        return job

    def _load_editor(self, job):
        if job is None:
            return
        selected_index = -1
        identity = analysis_identity_tuple(job)
        matches = []
        for index, choice in enumerate(self.analysis_choices):
            if analysis_identity_tuple(choice) == identity:
                matches.append(index)
        if len(matches) == 1:
            selected_index = matches[0]
        self.analysis_combo.SelectedIndex = selected_index
        self.folder_box.Text = job.get("folder", "")
        self.result_box.Text = job.get("result_filename", "")
        self.output_box.Text = job.get("output_filename", "")
        self.unit_combo.SelectedIndex = -1
        for index, item in enumerate(self.unit_combo.Items):
            if str(item).startswith(str(job.get("unit_system")) + " - "):
                self.unit_combo.SelectedIndex = index
                break
        self._set_numeric(self.poll_numeric, int(job.get("poll_seconds") or DEFAULT_POLL_SECONDS))
        self._set_numeric(self.settle_numeric, int(job.get("settle_seconds") or DEFAULT_SETTLE_SECONDS))
        self._set_numeric(self.retries_numeric, int(job.get("max_retries") or 0))
        self._set_numeric(self.retry_delay_numeric, int(job.get("retry_delay_seconds") or DEFAULT_RETRY_DELAY_SECONDS))
        self.accept_existing_box.Checked = bool(job.get("accept_existing"))
        self.validation_label.Text = "Selected: {0}".format(job.get("message", ""))

    def _grid_selection_changed(self, sender, args):
        if getattr(self, "_refreshing_grid", False):
            return
        if self.grid.SelectedRows.Count:
            job_id = str(self.grid.SelectedRows[0].Tag or "")
            if job_id:
                self._selected_job_id = job_id
                self._load_editor(self._selected_job())

    def _refresh_grid(self):
        now = utc_timestamp()
        selected_id = self._selected_job_id
        self._refreshing_grid = True
        try:
            self.grid.Rows.Clear()
            with self.engine._lock:
                jobs = list(self.engine.jobs)
                active_id = self.engine.active_job_id
            for job in jobs:
                waiting = None
                if job.get("monitoring_started_at") is not None:
                    end = job.get("completed_at") or now
                    waiting = end - float(job["monitoring_started_at"])
                elapsed = None
                if job.get("id") == active_id and job.get("import_started_at") is not None:
                    elapsed = now - float(job["import_started_at"])
                values = [
                    job.get("order"),
                    "{0} / {1}".format(job.get("analysis_name"), job.get("solution_name")),
                    str(job.get("analysis_type", "")).rsplit(".", 1)[-1],
                    job.get("folder"),
                    job.get("result_filename"),
                    job.get("output_filename"),
                    job.get("status"),
                    job.get("message"),
                    format_duration(waiting),
                    format_clock(job.get("ready_at")),
                    format_clock(job.get("import_started_at")),
                    format_duration(elapsed),
                    "{0}/{1}".format(job.get("retry_count", 0), job.get("max_retries", 0)),
                    format_clock(job.get("checkpoint_at")),
                ]
                row_index = self.grid.Rows.Add(*values)
                row = self.grid.Rows[row_index]
                row.Tag = job.get("id")
                color_tuple = self.STATUS_COLORS.get(job.get("status"), (60, 60, 60))
                row.Cells[6].Style.ForeColor = self.ui["Color"].FromArgb(*color_tuple)
                row.Cells[6].Style.Font = self.ui["Font"](
                    "Segoe UI Semibold", 8.5, self.ui["FontStyle"].Bold
                )
                if job.get("id") == selected_id:
                    row.Selected = True
                    self.grid.CurrentCell = row.Cells[0]
            if selected_id and self._selected_job() is None:
                self._selected_job_id = None
        finally:
            self._refreshing_grid = False
        self._refresh_header_status()
        self._update_enabled_state()

    def _refresh_header_status(self):
        now = utc_timestamp()
        counts = {}
        last_scan = None
        next_scan = None
        unavailable = 0
        with self.engine._lock:
            jobs = list(self.engine.jobs)
            active_id = self.engine.active_job_id
            paused = self.engine.paused
        for job in jobs:
            status = job.get("status")
            counts[status] = counts.get(status, 0) + 1
            if job.get("last_scan_at") is not None:
                last_scan = max(last_scan or 0, float(job["last_scan_at"]))
            if job.get("next_scan_at") is not None and status in SCAN_STATUSES:
                candidate = float(job["next_scan_at"])
                next_scan = candidate if next_scan is None else min(next_scan, candidate)
            if "Folder unavailable" in str(job.get("message", "")):
                unavailable += 1
        active = sum(counts.get(status, 0) for status in ACTIVE_STATUSES)
        failed = counts.get(STATUS_FAILED, 0)
        self.counter_label.Text = (
            "Waiting {0} | Ready {1} | Active {2} | Completed {3} | Failed {4} | Attention {5}"
        ).format(
            counts.get(STATUS_WAITING, 0) + counts.get(STATUS_SETTLING, 0),
            counts.get(STATUS_READY, 0),
            active,
            counts.get(STATUS_COMPLETED, 0),
            failed,
            counts.get(STATUS_ATTENTION, 0),
        )
        if active_id:
            job = self.engine.get_job(active_id)
            self.operation_status.Text = "Operation: {0} - {1}".format(job["status"], job["analysis_name"])
        elif paused:
            self.operation_status.Text = "Operation: Paused"
        else:
            self.operation_status.Text = "Operation: Idle"
        self.scan_status.Text = "Last scan: {0} | Next scan: {1}".format(
            format_clock(last_scan), format_clock(next_scan)
        )
        self.folder_status.Text = "Folders unavailable: {0}".format(unavailable)
        self.checkpoint_status.Text = "Checkpoint: {0}".format(
            format_clock((self.last_verified_checkpoint or {}).get("verified_at"))
        )

    def _editing_allowed(self):
        with self.engine._lock:
            if self.engine.active_job_id:
                return False
            if self.engine.paused:
                return True
            return not any(
                job.get("status") in SCAN_STATUSES + (STATUS_READY, STATUS_RETRY_WAITING)
                for job in self.engine.jobs
            )

    def _update_enabled_state(self):
        editable = self._editing_allowed()
        selected_job = self._selected_job()
        selected = selected_job is not None
        safe_to_change = selected and self.engine.can_mutate_job(selected_job)
        controls = (
            self.analysis_combo, self.folder_box, self.folder_button, self.result_box,
            self.result_button, self.output_box, self.output_button, self.unit_combo,
            self.poll_numeric, self.settle_numeric, self.retries_numeric,
            self.retry_delay_numeric, self.accept_existing_box,
        )
        for control in controls:
            control.Enabled = editable
        self.add_button.Enabled = editable
        self.update_button.Enabled = editable and safe_to_change
        self.remove_button.Enabled = editable and safe_to_change
        self.up_button.Enabled = editable and selected
        self.down_button.Enabled = editable and selected
        self.start_button.Enabled = bool(self.engine.jobs) and not self.engine.active_job_id
        self.pause_button.Enabled = not self.engine.paused and bool(self.engine.jobs)
        self.stop_button.Enabled = bool(self.engine.jobs) and not self.engine.stop_after_current
        self.retry_button.Enabled = bool(
            selected
            and not self.engine.active_job_id
            and selected_job.get("status")
            in (STATUS_ATTENTION, STATUS_RETRY_WAITING, STATUS_FAILED, STATUS_SKIPPED)
        )
        self.skip_button.Enabled = bool(
            selected
            and not self.engine.active_job_id
            and selected_job.get("status") not in (STATUS_COMPLETED, STATUS_SKIPPED)
        )
        self.restore_button.Enabled = not self.engine.active_job_id

    def _log(self, level, message, job=None):
        stamp = utc_timestamp()
        job_id = job.get("id") if job else None
        job_name = job.get("analysis_name") if job else None
        line = "[{0}] {1:<7} {2}".format(format_clock(stamp), level, message)
        try:
            self.event_box.AppendText(line + "\r\n")
            self.event_box.SelectionStart = len(self.event_box.Text)
            self.event_box.ScrollToCaret()
        except Exception:
            pass
        try:
            append_jsonl(
                self.event_path,
                {
                    "timestamp": stamp,
                    "level": level,
                    "message": str(message),
                    "job_id": job_id,
                    "analysis": job_name,
                },
            )
        except Exception:
            pass

    def _persist(self):
        payload = self.engine.to_state(
            self.project["project_path"], self.last_verified_checkpoint
        )
        atomic_write_json(self.state_path, payload)

    def _require_original_project(self):
        current = self.adapter.project_info()
        if (
            normalized_windows_path(current.get("project_path"))
            != normalized_windows_path(self.project.get("project_path"))
            or normalized_windows_path(current.get("user_files"))
            != normalized_windows_path(self.project.get("user_files"))
        ):
            raise RuntimeError(
                "The Workbench project changed after the monitor opened. Close this "
                "window and run the script again for the current project."
            )
        return current

    def _show_error(self, message):
        self._log("ERROR", str(message))
        self.ui["MessageBox"].Show(
            self.form,
            str(message),
            "HPC Result Monitor",
            self.ui["MessageBoxButtons"].OK,
            self.ui["MessageBoxIcon"].Error,
        )

    def _show_info(self, message):
        self.ui["MessageBox"].Show(
            self.form,
            str(message),
            "HPC Result Monitor",
            self.ui["MessageBoxButtons"].OK,
            self.ui["MessageBoxIcon"].Information,
        )

    def _add_clicked(self, sender, args):
        try:
            job = self._job_from_editor()
            self.engine.add_job(job)
            self._selected_job_id = job["id"]
            self._persist()
            self._log("INFO", "Job added for {0}.".format(job["analysis_name"]), job)
            self.validation_label.Text = "Job added to the queue."
            self.validation_label.ForeColor = self.ui["Color"].FromArgb(80, 90, 100)
            self._refresh_grid()
        except Exception as exc:
            self.validation_label.Text = str(exc)
            self.validation_label.ForeColor = self.ui["Color"].FromArgb(190, 45, 45)
            self._show_error(exc)

    def _update_clicked(self, sender, args):
        existing = self._selected_job()
        if existing is None:
            return
        try:
            replacement = self._job_from_editor(existing)
            self.engine.update_job(existing["id"], replacement)
            self._persist()
            self._log("INFO", "Job configuration updated.", replacement)
            self.validation_label.Text = "Selected job updated."
            self.validation_label.ForeColor = self.ui["Color"].FromArgb(80, 90, 100)
            self._refresh_grid()
        except Exception as exc:
            self.validation_label.Text = str(exc)
            self.validation_label.ForeColor = self.ui["Color"].FromArgb(190, 45, 45)
            self._show_error(exc)

    def _remove_clicked(self, sender, args):
        job = self._selected_job()
        if job is None:
            return
        try:
            self.engine.remove_job(job["id"])
            self._selected_job_id = None
            self._persist()
            self._log("INFO", "Job removed: {0}.".format(job["analysis_name"]), job)
            self._refresh_grid()
        except Exception as exc:
            self._show_error(exc)

    def _move_up_clicked(self, sender, args):
        self._move_selected(-1)

    def _move_down_clicked(self, sender, args):
        self._move_selected(1)

    def _move_selected(self, offset):
        job = self._selected_job()
        if job is None:
            return
        self.engine.move_job(job["id"], offset)
        self._persist()
        self._refresh_grid()

    def _start_clicked(self, sender, args):
        try:
            if not self.engine.jobs:
                raise ValueError("Add at least one job before starting.")
            for job in self.engine.jobs:
                validate_job_config(job)
            self._require_original_project()
            current_choices = self._reload_analysis_choices()
            if not current_choices:
                raise ValueError(
                    "No supported Static Structural, Modal, Transient Structural, or "
                    "Steady-State Thermal Solution is available."
                )
            for job in self.engine.jobs:
                self.adapter.resolve_solution(job)
            self._require_original_project()
            self.engine.start()
            self._persist()
            self._log("INFO", "Monitoring started; both-file baselines will be captured.")
            self._refresh_grid()
        except Exception as exc:
            self._show_error(exc)

    def _pause_clicked(self, sender, args):
        self.engine.pause()
        self._persist()
        self._log("INFO", "Monitoring paused. The active Mechanical call, if any, was not interrupted.")
        self._refresh_grid()

    def _stop_clicked(self, sender, args):
        with self.engine._lock:
            self.engine.stop_after_current = True
            if not self.engine.active_job_id:
                self.engine.paused = True
        self._persist()
        self._log("INFO", "Stop After Current requested.")
        self._refresh_grid()

    def _retry_clicked(self, sender, args):
        job = self._selected_job()
        if job is None:
            return
        try:
            now = utc_timestamp()
            if job.get("status") == STATUS_ATTENTION:
                answer = self.ui["MessageBox"].Show(
                    self.form,
                    "Retrying confirms that you reopened the last verified database or explicitly "
                    "accept the current in-memory Mechanical state. Continue?",
                    "Confirm recovery state",
                    self.ui["MessageBoxButtons"].YesNo,
                    self.ui["MessageBoxIcon"].Warning,
                )
                if answer != self.ui["DialogResult"].Yes:
                    return
                self.engine.release_attention_for_retry(job, now)
            elif job.get("failed_phase") == "readiness" or job.get("status") in (STATUS_FAILED, STATUS_SKIPPED):
                begin_monitoring_job(job, now)
            elif job.get("status") == STATUS_RETRY_WAITING:
                job["retry_due_at"] = now
                job["message"] = "Operator requested an immediate retry."
            else:
                raise ValueError("The selected job is not waiting for a retry.")
            self._persist()
            self._log("INFO", "Retry requested now.", job)
            self._refresh_grid()
            self._schedule_dispatch()
        except Exception as exc:
            self._show_error(exc)

    def _skip_clicked(self, sender, args):
        job = self._selected_job()
        if job is None:
            return
        try:
            if not self.engine.can_mutate_job(job):
                answer = self.ui["MessageBox"].Show(
                    self.form,
                    "Skipping confirms that you reopened the last verified database or "
                    "explicitly accept the current in-memory Mechanical state. Continue?",
                    "Confirm recovery state",
                    self.ui["MessageBoxButtons"].YesNo,
                    self.ui["MessageBoxIcon"].Warning,
                )
                if answer != self.ui["DialogResult"].Yes:
                    return
                self.engine.acknowledge_recovery(job)
            self.engine.skip_job(job)
            self._persist()
            self._log("WARN", "Job skipped by operator.", job)
            self._refresh_grid()
            self._schedule_dispatch()
        except Exception as exc:
            self._show_error(exc)

    def _restore_clicked(self, sender, args):
        try:
            self._require_original_project()
            self._reload_analysis_choices()
            restore_path = self.state_path
            if not os.path.isfile(restore_path) and os.path.isfile(restore_path + ".previous"):
                restore_path += ".previous"
            if not os.path.isfile(restore_path):
                raise ValueError("No saved monitor state exists for this project.")
            try:
                state = load_json(restore_path)
            except Exception:
                previous_path = self.state_path + ".previous"
                if restore_path == previous_path or not os.path.isfile(previous_path):
                    raise
                restore_path = previous_path
                state = load_json(restore_path)
            restored = MonitorEngine.from_state(state, self.project["project_path"])
            for job in restored.jobs:
                try:
                    self.adapter.resolve_solution(job)
                except Exception as exc:
                    job["status"] = STATUS_ATTENTION
                    job["message"] = "Analysis must be selected again: {0}".format(exc)
                    restored.attention_required = True
                    continue
                if job.get("status") == STATUS_COMPLETED and not self.adapter.reconcile_completed_job(job):
                    job["status"] = STATUS_ATTENTION
                    job["message"] = "Saved completion could not be reconciled with the open database."
                    restored.attention_required = True
            self._require_original_project()
            self.engine = restored
            self.last_verified_checkpoint = state.get("last_verified_checkpoint")
            self._selected_job_id = restored.jobs[0]["id"] if restored.jobs else None
            self._load_editor(self._selected_job())
            self._log("INFO", "Saved session restored and reconciled from {0}.".format(restore_path))
            self._refresh_grid()
        except Exception as exc:
            self._show_error(exc)

    def _open_log_clicked(self, sender, args):
        try:
            if not os.path.isfile(self.event_path):
                append_jsonl(self.event_path, {"timestamp": utc_timestamp(), "level": "INFO", "message": "Log created."})
            os.startfile(self.event_path)
        except Exception as exc:
            self._show_error(exc)

    def _browse_folder_clicked(self, sender, args):
        dialog = self.ui["FolderBrowserDialog"]()
        dialog.Description = "Choose the exact non-recursive HPC result folder"
        if os.path.isdir(str(self.folder_box.Text)):
            dialog.SelectedPath = str(self.folder_box.Text)
        if dialog.ShowDialog(self.form) == self.ui["DialogResult"].OK:
            self.folder_box.Text = str(dialog.SelectedPath)

    def _browse_result_clicked(self, sender, args):
        self._browse_file(self.result_box, "ANSYS result files (*.rst;*.rth)|*.rst;*.rth|All files (*.*)|*.*")

    def _browse_output_clicked(self, sender, args):
        self._browse_file(self.output_box, "MAPDL output files (*.out)|*.out|All files (*.*)|*.*")

    def _browse_file(self, target_box, filter_text):
        dialog = self.ui["OpenFileDialog"]()
        dialog.Filter = filter_text
        dialog.CheckFileExists = False
        folder = str(self.folder_box.Text)
        if os.path.isdir(folder):
            dialog.InitialDirectory = folder
        if dialog.ShowDialog(self.form) == self.ui["DialogResult"].OK:
            self.folder_box.Text = ntpath.dirname(str(dialog.FileName))
            target_box.Text = ntpath.basename(str(dialog.FileName))

    def _start_worker(self):
        thread = threading.Thread(target=self._worker_loop)
        thread.daemon = True
        thread.start()
        self._worker_thread = thread

    def _worker_loop(self):
        while not self._cancel_event.is_set():
            try:
                changed, events = self.engine.scan_due(utc_timestamp())
                with self.engine._lock:
                    has_jobs = bool(self.engine.jobs)
                    active = bool(self.engine.active_job_id)
                if changed or events or active or has_jobs:
                    self._request_ui_refresh(events, changed or bool(events))
            except Exception as exc:
                self._request_ui_refresh(
                    [(None, STATUS_FAILED, "Folder scan failed: {0}".format(exc))], True
                )
            self._cancel_event.wait(1.0)

    def _request_ui_refresh(self, events, persist=False):
        with self._refresh_lock:
            self._pending_worker_events.extend(events or [])
            self._pending_persist = self._pending_persist or bool(persist)
            if self._refresh_pending:
                return
            self._refresh_pending = True
        try:
            self.form.BeginInvoke(self.ui["Action"](self._worker_ui_tick))
        except Exception:
            with self._refresh_lock:
                self._refresh_pending = False

    def _worker_ui_tick(self):
        with self._refresh_lock:
            events = list(self._pending_worker_events)
            self._pending_worker_events = []
            persist = self._pending_persist
            self._pending_persist = False
            self._refresh_pending = False
        for job_id, status, message in events:
            job = None
            if job_id:
                try:
                    job = self.engine.get_job(job_id)
                except KeyError:
                    pass
            level = "ERROR" if status in (STATUS_FAILED, STATUS_ATTENTION) else "INFO"
            self._log(level, message, job)
        if persist:
            try:
                self._persist()
            except Exception as exc:
                self._log("ERROR", "Monitor state could not be saved: {0}".format(exc))
        self._refresh_grid()
        self._dispatch_next()

    def _schedule_dispatch(self):
        try:
            self.form.BeginInvoke(self.ui["Action"](self._dispatch_next))
        except Exception:
            pass

    def _paint_phase(self, job, phase):
        self.engine.mark_phase(job, phase)
        self.busy_indicator.Visible = True
        self._log("INFO", "Starting Mechanical {0}.".format(phase), job)
        self._persist()
        self._refresh_grid()
        try:
            self.ui["Application"].DoEvents()
        except Exception:
            pass

    def _dispatch_next(self):
        if self._closing or self.engine.active_job_id:
            return
        job = self.engine.next_dispatch(utc_timestamp())
        if job is None:
            return
        self._execute_job(job)

    def _execute_job(self, job):
        phase = job.get("failed_phase") or "import"
        if phase not in ("import", "evaluate", "save"):
            phase = "import"
        try:
            if phase != "import":
                try:
                    self.adapter.verify_loaded(job, phase == "save")
                except Exception:
                    phase = "import"

            if phase == "import":
                self._paint_phase(job, "import")
                evidence = self.adapter.import_result(job)
                self.engine.complete_phase(job, "import")
                self._log("INFO", "Result reference loaded: {0}.".format(evidence.get("reported_path")), job)
                phase = "evaluate"

            if phase == "evaluate":
                self._paint_phase(job, "evaluate")
                evidence = self.adapter.evaluate_results(job)
                self.engine.complete_phase(job, "evaluate")
                self._log("INFO", "Result objects evaluated; Solution status={0}.".format(evidence.get("solution_status")), job)
                phase = "save"

            self._paint_phase(job, "save")
            checkpoint = self.adapter.save_database(job)
            self.engine.complete_phase(job, "save")
            self.engine.finish_job(job, checkpoint)
            self.last_verified_checkpoint = checkpoint
            self._log("INFO", "Save Database checkpoint verified.", job)
            self._persist()
            self._refresh_grid()
        except MechanicalPhaseError as exc:
            self.engine.fail_phase(job, exc.phase or phase, str(exc), exc.may_have_mutated)
            self._log("ERROR", str(exc), job)
            self._persist()
            self._refresh_grid()
        except Exception as exc:
            self.engine.fail_phase(job, phase, str(exc), True)
            self._log("ERROR", "Unexpected Mechanical failure: {0}\n{1}".format(exc, traceback.format_exc()), job)
            self._persist()
            self._refresh_grid()
        finally:
            self.busy_indicator.Visible = False
            if self._close_after_current and not self.engine.active_job_id:
                self._closing = True
                self.form.Close()
                return
            self._schedule_dispatch()

    def _on_form_closing(self, sender, args):
        if self._closing:
            self._cancel_event.set()
            return
        if self.engine.active_job_id:
            answer = self.ui["MessageBox"].Show(
                self.form,
                "Mechanical is busy. Choose Yes to close after the current operation, "
                "or No to keep the monitor open.",
                "Mechanical operation in progress",
                self.ui["MessageBoxButtons"].YesNo,
                self.ui["MessageBoxIcon"].Warning,
            )
            args.Cancel = True
            if answer == self.ui["DialogResult"].Yes:
                self._close_after_current = True
                self.engine.stop_after_current = True
                self._log("WARN", "Close After Current requested.")
            return
        self._closing = True
        self._cancel_event.set()
        try:
            self._persist()
        except Exception:
            pass

    def show(self):
        self.form.Show()
        self.form.BringToFront()
        self.form.Activate()

    def focus(self):
        if self.form.WindowState == self.ui["FormWindowState"].Minimized:
            self.form.WindowState = self.ui["FormWindowState"].Normal
        self.form.Show()
        self.form.BringToFront()
        self.form.Activate()


if "_HPC_RESULT_MONITOR" not in globals():
    _HPC_RESULT_MONITOR = None


def show_hpc_result_monitor():
    """Show or focus the singleton Workbench-launched Mechanical v261 console."""
    global _HPC_RESULT_MONITOR
    if _HPC_RESULT_MONITOR is not None:
        try:
            if not _HPC_RESULT_MONITOR.form.IsDisposed:
                _HPC_RESULT_MONITOR.focus()
                return _HPC_RESULT_MONITOR
        except Exception:
            pass
    ui = _load_winforms()
    try:
        ui["Application"].EnableVisualStyles()
    except Exception:
        pass
    adapter = MechanicalAdapter(globals())
    _HPC_RESULT_MONITOR = HpcResultMonitorForm(adapter, ui)
    _HPC_RESULT_MONITOR.show()
    return _HPC_RESULT_MONITOR


if __name__ == "__main__" and globals().get("ExtAPI") is not None:
    show_hpc_result_monitor()
