"""Per-dataset aggregation of subject-level statistics.

Aggregates subject-level stats to dataset level using appropriate
aggregation methods (sum, min, max, weighted mean).
"""

import json
from typing import Any


def aggregate_to_dataset(
    subjects_stats: list[dict[str, Any]],
    source_id: str,
) -> dict[str, Any]:
    """Aggregate subject-level stats to dataset level.

    Args:
        subjects_stats: List of per-subject statistics
        source_id: Source dataset ID

    Returns:
        Dataset-level aggregated statistics
    """
    if not subjects_stats:
        return {
            "source_id": source_id,
            "subjects_num": 0,
            "sessions_num": "n/a",
            "sessions_min": "n/a",
            "sessions_max": "n/a",
            "bold_num": 0,
            "t1w_num": 0,
            "t2w_num": 0,
            "bold_size": 0,
            "t1w_size": 0,
            "bold_size_max": "n/a",
            "bold_duration_total": "n/a",
            "bold_duration_mean": "n/a",
            "bold_voxels_total": "n/a",
            "bold_voxels_mean": "n/a",
            "bold_tasks": "n/a",
            "bold_timepoints": 0,
            "bold_trs": "n/a",
            "datatypes": "n/a",
        }

    # Count unique subjects
    unique_subjects = {s["subject_id"] for s in subjects_stats}

    # Count sessions per subject (only valid ses-* sessions)
    session_counts: dict[str, int] = {}
    for s in subjects_stats:
        subj = s["subject_id"]
        sess = s["session_id"]
        # Only count valid sessions (not n/a and starts with ses-)
        if sess != "n/a" and sess.startswith("ses-"):
            session_counts[subj] = session_counts.get(subj, 0) + 1

    # Sum numeric fields
    total_bold_num = sum(s["bold_num"] for s in subjects_stats)
    total_t1w_num = sum(s["t1w_num"] for s in subjects_stats)
    total_t2w_num = sum(s["t2w_num"] for s in subjects_stats)
    total_bold_size = sum(s["bold_size"] for s in subjects_stats if isinstance(s["bold_size"], int))
    total_t1w_size = sum(s["t1w_size"] for s in subjects_stats if isinstance(s["t1w_size"], int))

    # Find max BOLD size (approximation from average)
    bold_size_max = total_bold_size // total_bold_num if total_bold_num > 0 else None

    # Aggregate duration and voxels (weighted means)
    total_duration = 0.0
    total_voxels = 0
    duration_count = 0
    voxels_count = 0

    for s in subjects_stats:
        if s["bold_duration_total"] is not None:
            total_duration += s["bold_duration_total"]
            duration_count += s["bold_num"]
        if s["bold_voxels_total"] is not None:
            total_voxels += s["bold_voxels_total"]
            voxels_count += s["bold_num"]

    # Aggregate bold_tasks (set-union), bold_timepoints (sum), bold_trs (dict-merge)
    all_tasks: set[str] = set()
    total_timepoints = 0
    merged_trs: dict[str, int] = {}

    for s in subjects_stats:
        bt = s.get("bold_tasks", "n/a")
        if bt and bt != "n/a":
            for t in bt.split(","):
                if t:
                    all_tasks.add(t)
        bp = s.get("bold_timepoints", 0)
        if isinstance(bp, int):
            total_timepoints += bp
        elif isinstance(bp, str) and bp != "n/a":
            total_timepoints += int(bp)
        btr = s.get("bold_trs", "n/a")
        if btr and btr != "n/a":
            try:
                tr_dict = json.loads(btr) if isinstance(btr, str) else btr
                for k, v in tr_dict.items():
                    merged_trs[k] = merged_trs.get(k, 0) + int(v)
            except (ValueError, TypeError, json.JSONDecodeError):
                pass

    # Collect all datatypes
    all_datatypes: set[str] = set()
    for s in subjects_stats:
        if s["datatypes"] and s["datatypes"] != "n/a":
            for dt in s["datatypes"].split(","):
                all_datatypes.add(dt)

    result = {
        "source_id": source_id,
        "subjects_num": len(unique_subjects),
        "sessions_num": sum(session_counts.values()) if session_counts else "n/a",
        "sessions_min": min(session_counts.values()) if session_counts else "n/a",
        "sessions_max": max(session_counts.values()) if session_counts else "n/a",
        "bold_num": total_bold_num,
        "t1w_num": total_t1w_num,
        "t2w_num": total_t2w_num,
        "bold_size": total_bold_size,
        "t1w_size": total_t1w_size,
        "bold_size_max": bold_size_max if bold_size_max else "n/a",
        "bold_duration_total": total_duration if duration_count > 0 else "n/a",
        "bold_duration_mean": (total_duration / duration_count if duration_count > 0 else "n/a"),
        "bold_voxels_total": total_voxels if voxels_count > 0 else "n/a",
        "bold_voxels_mean": (total_voxels / voxels_count if voxels_count > 0 else "n/a"),
        "bold_tasks": ",".join(sorted(all_tasks)) if all_tasks else "n/a",
        "bold_timepoints": total_timepoints,
        "bold_trs": json.dumps(dict(sorted(merged_trs.items()))) if merged_trs else "n/a",
        "datatypes": ",".join(sorted(all_datatypes)) if all_datatypes else "n/a",
    }

    return result
