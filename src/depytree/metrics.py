"""Code metrics inspired by the book "Your Code as a Crime Scene (2nd Edition)" by Adam Thornhill"""

import os
import subprocess
from collections import defaultdict


class MinMaxScaler:
    def __init__(self, collection: dict[str, dict], key: str):
        """
        Identify min & max values from the given data

        Inputs:
            - collection: dict, e.g., collected_modules with "complexity" in subdicts
            - key: which item in the dict should be used when extracting values (e.g., "complexity")
        """
        values = sorted([d[key] for d in collection.values() if key in d])
        # do some rough outlier filtering
        if len(values) > 2:
            self._min = min(values[1:])
            self._max = max(values[:-1])
        else:
            values.append(0)  # in case the list is empty
            self._min = min(values)
            self._max = max(values)

    def scale(self, value) -> float:
        """
        Scale the given value to be between 0 and 1

        Inputs:
            - value: some number that should be between _min and _max
        Returns:
            - the given number scaled as (value - min) / (max - min)
        """
        if (self._max - self._min) == 0:
            return 0
        return min(1, max(0, (value - self._min) / (self._max - self._min)))


def get_file_stats(filepath: str, space_per_tab: int = 4) -> tuple[int, int, int]:
    """
    Extract file statistics related to code complexity

    Inputs:
        - filepath: the path to the file that should be analyzed
        - space_per_tab: how to count tabs (default: 4 spaces)

    Returns:
        - loc (lines of code incl. empty lines and comments)
        - loc without empty lines (but with comments)
        - total indentations (i.e., leading whitespace, both spaces and tabs)
    """
    loc = 0
    loc_nonempty = 0
    n_indents = 0
    try:
        with open(filepath, encoding="utf-8") as f:
            for line in f:
                loc += 1
                if line.strip():
                    loc_nonempty += 1
                leading = len(line) - len(line.lstrip())
                for ch in line[:leading]:
                    if ch == "\t":
                        n_indents += space_per_tab
                    elif ch == " ":
                        n_indents += 1
    except UnicodeDecodeError as e:
        print(f"Problem with file {filepath}: {e}")
    return loc, loc_nonempty, n_indents


def generate_git_log(path: str) -> tuple[str | None, str | None]:
    """
    Generate the git log for a given path considering only the last year

    Inputs:
        - path: path to a file or directory under git version control

    Returns (upon success):
        - git root directory (since file names in git log are listed with relative paths)
        - file path for the created git log file (data/git_log.txt)
    -> if this is not a git repository, returns (None, None) instead
    """
    # the git command needs to be called from inside the corresponding git directory
    original_dir = os.getcwd()
    if not os.path.isdir(path):
        path = os.path.dirname(path)
    target_dir = os.path.abspath(path)
    log_file = os.path.join(original_dir, "data", "git_log.txt")

    try:
        os.chdir(target_dir)
        # check whether this is a git repo and get the path relative to which the file paths will be listed in the log
        cmd = ["git", "rev-parse", "--show-toplevel"]
        result = subprocess.run(cmd, capture_output=True, check=False, text=True)
        if result.returncode != 0:
            # fatal: not a git repository
            print(result.stderr)
            return None, None
        git_dir = result.stdout.strip()

        since = "1 year ago"  # could be function argument, but then we have the potential risk of arbitrary command execution
        cmd = [
            "git",
            "log",
            "--numstat",
            "--date=short",
            "--pretty=format:--COMMIT--%ad--%aN",
            "--no-renames",
            f"--since={since}",
        ]
        result = subprocess.run(cmd, capture_output=True, check=False, text=True)
        if result.returncode != 0:
            # should never happen....
            print(result.stderr)
            return None, None

        with open(log_file, "w") as f:
            f.write(result.stdout)

        return git_dir, log_file
    finally:
        os.chdir(original_dir)


def get_git_revisions(git_log_path: str, filename: str) -> tuple[int, int]:
    """
    Compute git revision stats for a single file

    Inputs:
        - git_log_path: path to a text file with the git log as created by generate_git_log
        - filename: path to a file relative to the git repo for which the stats should be computed
            (needs to match the filenames in the git log)

    Returns:
        - the number of commits associated with the corresponding file
        - the number of lines that were changed over all commits (additions and removals)
    """
    with open(git_log_path) as f:
        git_log = f.readlines()

    commit_count = 0
    line_change_sum = 0

    for next_line in git_log:
        line = next_line.strip()
        if not line or line.startswith("--COMMIT"):
            continue
        parts = line.split()
        if len(parts) == 3 and parts[2] == filename:
            commit_count += 1
            added = int(parts[0]) if parts[0].isdigit() else 0
            removed = int(parts[1]) if parts[1].isdigit() else 0
            line_change_sum += added + removed

    return commit_count, line_change_sum


def _extract_commits(git_log_path: str, file_map: dict[str, str] | None = None) -> list[list[str]]:
    """
    Process the git log to extract the files for each commit

    Inputs:
        - git_log_path: path to a text file with the git log as created by generate_git_log
        - file_map (optional): in case the file names should be mapped to other names (like module names)
            if given, only files listed in this dict are included in the results

    Returns:
        - list with one entry per commit, which itself is a list of all the (possibly mapped) filenames
            which were changed in this commit
    """
    with open(git_log_path) as f:
        git_log = f.readlines()

    commits = []
    current_files: list[str] = []

    for next_line in git_log:
        line = next_line.strip()
        if line.startswith("--COMMIT--"):
            if current_files:
                commits.append(current_files)
                current_files = []
        elif line:
            parts = line.split()
            if len(parts) == 3:
                _, _, filename = parts
                if file_map is None:
                    current_files.append(filename)
                elif filename in file_map:
                    current_files.append(file_map[filename])

    # append last commit if any
    if current_files:
        commits.append(current_files)

    return commits


def get_git_dependencies(git_log_path: str, file_map: dict[str, str] | None = None) -> dict[str, dict[str, int]]:
    """
    Count how often files were changed in the same commit

    Inputs:
        - git_log_path: path to a text file with the git log as created by generate_git_log
        - file_map (optional): in case the file names should be mapped to other names (like module names)
            if given, only files listed in this dict are considered as dependencies

    Returns:
        - dict with {file: {dep: count}}: how often a dependency occurred in the same commit as this file;
            it also includes an entry for the file itself so the counts can later be normalized
    """
    commits = _extract_commits(git_log_path, file_map)

    results: dict[str, dict[str, int]] = {}
    for files in commits:
        for f in files:
            if f not in results:
                results[f] = defaultdict(int)
            for f_dep in files:
                results[f][f_dep] += 1

    return results


def norm_counts(
    dep_counts: dict[str, dict[str, int]], norm_global: bool = True, scale: float = 0.7
) -> dict[str, dict[str, float]]:
    """
    Normalize a dict like that returned by get_git_dependencies by dividing
        the counts by the max counts (e.g., those of the file itself)

    Inputs:
        - dep_counts: dictionary with dependency counts like returned by get_git_dependencies
        - norm_global: whether to use the global max value to normalize all values (default)
            or normalize the dependencies for each file w.r.t. the number of commits of this file
        - scale: scale factor applied to the normalized value (default: 0.7; useful if number is used
            for opacity value when plotting)

    Returns:
        - same dict as dep_counts only with normalized count values and excluding the file itself
            as a dependency (useful for plotting)
    """
    # second highest commit count overall (to avoid outliers)
    max_count_all = sorted([1, 1] + [max(dep_counts[f].values()) for f in dep_counts], reverse=True)[1]
    dep_counts_normed = {}
    for f in dep_counts:
        max_count = max_count_all if norm_global else max(dep_counts[f].values())
        # the file itself was only included in the original dict to get the max value for normalization
        dep_counts_normed[f] = {
            f_dep: scale * min(1.0, count / max_count) for f_dep, count in dep_counts[f].items() if f_dep != f
        }
    return dep_counts_normed
