# ruff: noqa: B023
import ast
import colorsys
import importlib
import json
import logging
import os
from collections import Counter
from glob import glob

from depytree.metrics import (
    MinMaxScaler,
    generate_git_log,
    get_file_stats,
    get_git_dependencies,
    get_git_revisions,
    norm_counts,
)

logging.basicConfig()
logger = logging.getLogger(" ")
logger.setLevel(logging.INFO)


def is_private(name: str):
    return name.startswith("_") and name != "__main__"


def get_parent(full_name: str, levels_up: int = 1):
    """parent_module.child_module -> parent_module"""
    if levels_up <= 0:
        return full_name
    parts = full_name.split(".")
    if levels_up >= len(parts):
        return parts[0]
    return ".".join(parts[:-levels_up])


def get_all_parents(full_name: str):
    """a.b.c.d -> [a, a.b, a.b.c]"""
    parts = full_name.split(".")
    return [".".join(parts[:i]) for i in range(1, len(parts))]


def resolve_relative_import(module_base_name: str, module: str | None, level: int):
    """parent_module.child, ...other_child -> parent_module.child.other_child"""
    parts = module_base_name.split(".")
    if level > len(parts):
        return module  # fallback if level is too high
    prefix = parts[:-level]
    if module:
        return ".".join(prefix + module.split("."))
    return ".".join(prefix)


def sortkey_collected(info: dict, name: str):
    """
    What is at the bottom:
        - has no dependencies (in or out)
        - has many incoming dependencies from the same module (file for units, folder for files)
        - has many incoming dependencies from other modules
        - has few outgoing dependencies into the same module
        - has few outgoing dependencies into other modules
        - is private
        - module: has few children; units: classes before functions
        - alphabetical
    """
    n_dep_out_same = len(info["dependencies_same"])
    n_dep_out_other = len(info["dependencies_other"])
    n_dep_out = n_dep_out_same + n_dep_out_other
    n_dep_in_same = info["n_incoming_dependencies_same"]
    n_dep_in_other = info["n_incoming_dependencies_other"]
    n_dep_in = n_dep_in_same + n_dep_in_other
    n_any = min(1, n_dep_out + n_dep_in)
    if info["type"] in ("file", "directory"):
        return (
            -n_any,
            n_dep_in,
            -n_dep_out,
            info["private"],
            -len(info["children"]),
            name,
        )
    return (
        -n_any,
        n_dep_in_same,
        -n_dep_out_same,
        n_dep_in_other,
        -n_dep_out_other,
        info["private"],
        info["type"],
        name,
    )


def add_git_dependencies(collected_modules: dict[str, dict], git_dir: str | None, log_file: str | None):
    if log_file is not None:
        # add mapping from relative file paths to module names to match git log entries
        path_mapping = {os.path.relpath(v["path"], git_dir): k for k, v in collected_modules.items() if v["type"] == "file"}
        git_dep = norm_counts(get_git_dependencies(log_file, path_mapping))
        for module, info in collected_modules.items():
            if info["type"] == "file" and module in git_dep:
                info["dependencies_git"] = git_dep[module]
    return collected_modules


def add_metrics_per_file(collected_modules: dict[str, dict], git_dir: str | None, log_file: str | None):
    for _module, info in collected_modules.items():
        if info["type"] == "file":
            loc, loc_nonempty, n_ind = get_file_stats(info["path"])
            # proxy for complexity: average indentation per line (more indents = nested if statements etc)
            info["complexity"] = n_ind / max(1, loc)
            if log_file is not None:
                commit_count, line_change_sum = get_git_revisions(log_file, os.path.relpath(info["path"], git_dir))
                # volatility: number of lines changed in the last year, normalized by total number of lines now
                info["volatility"] = line_change_sum / max(1, loc)
    return collected_modules


def collect_modules(module_name_or_path: str, file_ext: str = ".py"):
    # check if it's a folder with python files or a module we need to import
    if os.path.isdir(module_name_or_path):
        root_path = os.path.abspath(module_name_or_path)
    else:
        try:
            root = importlib.import_module(module_name_or_path)
        except ModuleNotFoundError as e:
            logger.error(f"Could not find {module_name_or_path} - are you in the right Python environment?")
            logger.error(e)
            return module_name_or_path, {}
        root_path = os.path.dirname(root.__file__)  # type: ignore

    root_module_name = root_path.split(os.sep)[-1]
    collected = {}

    def walk(path: str, module_name: str):
        entry = {
            "path": path,
            "level": len(module_name.split(".")),
            "private": is_private(module_name.split(".")[-1]),
            "children": [],
            "dependencies_same": set(),
            "dependencies_other": set(),
        }

        if os.path.isfile(path):
            # we already know that it must by a python file since we don't continue with other files below
            # children for files are units and will be added later
            entry["type"] = "file"

        elif os.path.isdir(path):
            entry["type"] = "directory"
            children = os.listdir(path)
            children_paths = [os.path.join(path, child) for child in children]

            for child_path in children_paths:
                # only explore directories that somewhere along the line contain a python file (i.e., not __pycache__)
                # only move forward with python files that are not __init__.py
                if (os.path.isdir(child_path) and len(glob(f"{child_path}{os.sep}**{os.sep}*{file_ext}", recursive=True))) or (
                    os.path.isfile(child_path) and child_path.endswith(file_ext) and not child_path.endswith("__init__.py")
                ):
                    child_module_name = f"{module_name}.{os.path.splitext(os.path.basename(child_path))[0]}"
                    entry["children"].append(child_module_name)
                    # recursive traversal
                    collected[child_module_name] = walk(child_path, child_module_name)

        return entry

    collected[root_module_name] = walk(root_path, root_module_name)
    return root_module_name, collected


def collect_units(
    file_path: str,
    module_base_name: str,
    known_submodules: set,
    include_globals: bool = False,
):
    """
    Read in a single file and return a dict with all functions, classes, and possibly global variables:
    {
        "unit_name": {
            "type": ("class" / "function" / "global"),
            "private": bool,
            "dependencies[_same/_other]": set(other units from same package),
        }
    }
    """
    if not file_path.endswith(".py"):
        raise RuntimeError(f"{file_path} is not a Python file!")

    logger.info(f"## Analyzing file: {file_path}")
    root_module_name = module_base_name.split(".")[0]
    module_parent_name = get_parent(module_base_name)

    collected = {}
    name_to_fullname = {}
    module_dependencies_same = set()
    module_dependencies_other = set()

    with open(file_path, encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source, filename=file_path)

    for node in tree.body:
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            name = node.name
            full_obj_name = f"{module_base_name}.{name}"

            collected[full_obj_name] = {
                "type": kind,
                "private": is_private(name),
                "dependencies_same": set(),
                "dependencies_other": set(),
                "path": file_path,
                "ast_node": node,
            }
            name_to_fullname[name] = full_obj_name

        elif include_globals and isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    full_obj_name = f"{module_base_name}.{name}"

                    collected[full_obj_name] = {
                        "type": "global",
                        "private": is_private(name),
                        "dependencies_same": set(),
                        "dependencies_other": set(),
                        "path": file_path,
                    }
                    name_to_fullname[name] = full_obj_name

        elif include_globals and isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                name = node.target.id
                full_obj_name = f"{module_base_name}.{name}"

                collected[full_obj_name] = {
                    "type": "global",
                    "private": is_private(name),
                    "dependencies_same": set(),
                    "dependencies_other": set(),
                    "path": file_path,
                }
                name_to_fullname[name] = full_obj_name

        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(root_module_name) and alias.name in known_submodules:
                    if get_parent(alias.name) == module_parent_name:
                        module_dependencies_same.add(alias.name)
                    else:
                        module_dependencies_other.add(alias.name)
                    name_to_fullname[alias.asname or alias.name] = alias.name

        elif isinstance(node, ast.ImportFrom):
            level = node.level
            module = node.module
            base_module = resolve_relative_import(module_base_name, module, level)

            for alias in node.names:
                fullname = f"{base_module}.{alias.name}" if base_module else alias.name
                if fullname.startswith(root_module_name):
                    # check whether we imported a module or individual unit since modules should only have module dependencies
                    from_module_name = fullname if fullname in known_submodules else get_parent(fullname)
                    if from_module_name in known_submodules:
                        if get_parent(from_module_name) == module_parent_name:
                            module_dependencies_same.add(from_module_name)
                        else:
                            module_dependencies_other.add(from_module_name)
                    name_to_fullname[alias.asname or alias.name] = fullname

    for fullname, info in collected.items():
        if "ast_node" not in info:
            continue
        ast_node = info.pop("ast_node")

        logger.info(f"# Processing: {fullname}")

        class DependencyVisitor(ast.NodeVisitor):
            def visit_Name(self, node):
                # for individual names
                name = node.id
                if name in name_to_fullname:
                    fullname = name_to_fullname[name]
                    logger.debug(f"[visit_Name] Dependency found: {name} -> {fullname}")
                    if fullname.startswith(module_base_name):
                        info["dependencies_same"].add(fullname)
                    else:
                        info["dependencies_other"].add(fullname)
                else:
                    logger.debug(f"[visit_Name] Not sure what to do with: {name}")
                self.generic_visit(node)

            def visit_Attribute(self, node):
                # handle dotted names like module.function()
                parts = []
                while isinstance(node, ast.Attribute):
                    parts.append(node.attr)
                    node = node.value
                if isinstance(node, ast.Name):
                    name = node.id
                    if name in name_to_fullname:
                        fullname = name_to_fullname[name]
                        parts.append(fullname)
                        resolved_name = ".".join(reversed(parts))
                        logger.debug(f"[visit_Attribute] Dependency found: {name} -> {resolved_name}")
                        if resolved_name.startswith(module_base_name):
                            info["dependencies_same"].add(resolved_name)
                        else:
                            info["dependencies_other"].add(resolved_name)
                    else:
                        parts.append(name)
                        resolved_name = ".".join(reversed(parts))
                        logger.debug(f"[visit_Attribute] Not sure what to do with: {resolved_name}")
                self.generic_visit(node)

        DependencyVisitor().visit(ast_node)

    return collected, module_dependencies_same, module_dependencies_other


def collect_modules_and_units(root_module_name_or_path: str):
    root_module_name, collected_modules = collect_modules(root_module_name_or_path)

    # identify units for all files and add module dependencies
    collected_units: dict[str, dict] = {}
    for module_name, info in collected_modules.items():
        if info["type"] == "file":
            new_collected_units, module_dep_same, module_dep_other = collect_units(
                info["path"], module_name, set(collected_modules.keys())
            )
            info["children"] = sorted(new_collected_units.keys())
            info["dependencies_same"] = module_dep_same
            info["dependencies_other"] = module_dep_other
            collected_units |= new_collected_units

    # fix dependencies that went too deep
    for unit_name in collected_units:
        for dep_set in ["dependencies_same", "dependencies_other"]:
            new_set = []
            for dep in collected_units[unit_name][dep_set]:
                if dep not in collected_units:
                    if get_parent(dep) in collected_units:
                        logger.info(f"Mapping {dep} to {get_parent(dep)}")
                        dep = get_parent(dep)  # noqa: PLW2901
                    else:
                        logger.warning(f"Unknown dependency for {unit_name}: {dep}")
                        continue
                if dep != unit_name:
                    new_set.append(dep)
            collected_units[unit_name][dep_set] = set(new_set)

    return root_module_name, collected_modules, collected_units


def add_n_incoming_deps(collected_modules: dict, collected_units: dict):
    # add incoming dependencies for sorting
    all_dependencies_same = []
    all_dependencies_other = []
    for _, info in (collected_units | collected_modules).items():
        if info["type"] == "directory":
            continue
        all_dependencies_same.extend(info["dependencies_same"])
        all_dependencies_other.extend(info["dependencies_other"])
        # additionally add all the parents
        if info["type"] == "file":
            for dep in info["dependencies_same"]:
                all_dependencies_same.extend(get_all_parents(dep))
            for dep in info["dependencies_other"]:
                all_dependencies_other.extend(get_all_parents(dep))

    all_dependency_counts_same = Counter(all_dependencies_same)
    all_dependency_counts_other = Counter(all_dependencies_other)
    for name, info in (collected_units | collected_modules).items():
        if info["type"] == "directory":
            continue
        info["n_incoming_dependencies_same"] = all_dependency_counts_same.get(name, 0)
        info["n_incoming_dependencies_other"] = all_dependency_counts_other.get(name, 0)

    return collected_modules, collected_units


def propagate_directory_deps(collected_modules: dict):
    # propagate dependencies up from files to directories by starting with the lowest levels
    for module, info in sorted(collected_modules.items(), key=lambda x: x[1]["level"], reverse=True):
        if info["type"] == "file":
            continue
        module_parent_name = get_parent(module)
        for child in info["children"]:
            for dep in collected_modules[child]["dependencies_same"] | collected_modules[child]["dependencies_other"]:
                if dep.startswith(module) or (
                    dep.startswith(module_parent_name) and collected_modules[dep]["level"] == info["level"]
                ):
                    info["dependencies_same"].add(dep)
                else:
                    info["dependencies_other"].add(dep)
        # we take the avg here since many submodules with individually few incoming dependencies (especially local ones)
        # shouldn't count as much as some files that many modules depend on
        info["n_incoming_dependencies_same"] = sum(
            [collected_modules[child]["n_incoming_dependencies_same"] for child in info["children"]]
        ) / max(1, len(info["children"]))
        info["n_incoming_dependencies_other"] = sum(
            [collected_modules[child]["n_incoming_dependencies_other"] for child in info["children"]]
        ) / max(1, len(info["children"]))
    return collected_modules


def get_sorted_names(root_module_name: str, collected_modules: dict, collected_units: dict):
    # sort modules recursively
    sorted_modules = []
    all_children = sorted(
        collected_modules[root_module_name]["children"],
        key=lambda k: sortkey_collected(collected_modules[k], k),
    )
    while all_children:
        next_child = all_children.pop(0)
        if collected_modules[next_child]["type"] == "file":
            sorted_modules.append(next_child)
        else:
            all_children = (
                sorted(
                    collected_modules[next_child]["children"],
                    key=lambda k: sortkey_collected(collected_modules[k], k),
                )
                + all_children
            )

    # get all names, i.e., modules and then within them the units, sorted
    sorted_names = []
    for module in sorted_modules:
        sorted_names.append(module)
        sorted_names.extend(
            sorted(
                collected_modules[module]["children"],
                key=lambda k: sortkey_collected(collected_units[k], k),
            )
        )
    return sorted_names


def prepare_json(sorted_names: list[str], collected: dict):
    size_scaler = MinMaxScaler(collected, "complexity")
    color_scaler = MinMaxScaler(collected, "volatility")
    units_color_map = {True: "#ccabb2", False: "#bbccab"}
    nodes = []
    links = []
    for name in sorted_names:
        if collected[name]["type"] == "directory":
            continue
        if collected[name]["type"] == "file":
            label = name
            size = size_scaler.scale(collected[name]["complexity"])
            if "volatility" in collected[name]:
                color_s = 0.5 + 0.25 * color_scaler.scale(collected[name]["volatility"])
                color_rgb = colorsys.hsv_to_rgb(color_s, 1.0, 0.8)
                color = f"rgb({int(255 * color_rgb[0])},{int(255 * color_rgb[1])},{int(255 * color_rgb[2])})"
            else:
                # fallback in case this wasn't a git repo
                color = units_color_map[collected[name]["private"]]
        else:
            label = name.split(".")[-1]
            size = 0
            color = units_color_map[collected[name]["private"]]
        nodes.append(
            {
                "id": name,
                "label": label,
                "type": collected[name]["type"],
                "size": size,
                "color": color,
            }
        )

        for dep in collected[name].get("dependencies_same", set()) | collected[name].get("dependencies_other", set()):
            if dep not in collected:
                logger.warning(f"Unknown dependency for {name}: {dep}")
                continue
            if dep in sorted_names:
                links.append({"source": name, "target": dep, "type": "import", "strength": 1.0})

        for dep in collected[name].get("dependencies_git", []):
            if dep in sorted_names:
                links.append(
                    {"source": name, "target": dep, "type": "git", "strength": collected[name]["dependencies_git"][dep]}
                )

    return {"nodes": nodes, "links": links}


def main(root_module_name_or_path: str):
    logger.info(f"### Traversing {root_module_name_or_path}")
    root_module_name, collected_modules, collected_units = collect_modules_and_units(root_module_name_or_path)
    logger.info("# Adding file metrics and git analysis results")
    # try to generate the git log using one of the files' path
    a_path = [v["path"] for v in collected_modules.values() if v["type"] == "file"][0]  # noqa: RUF015
    git_dir, log_file = generate_git_log(a_path)
    collected_modules = add_metrics_per_file(collected_modules, git_dir, log_file)
    collected_modules = add_git_dependencies(collected_modules, git_dir, log_file)
    collected_modules, collected_units = add_n_incoming_deps(collected_modules, collected_units)
    collected_modules = propagate_directory_deps(collected_modules)
    sorted_names = get_sorted_names(root_module_name, collected_modules, collected_units)
    collected = collected_modules | collected_units

    os.makedirs("data", exist_ok=True)
    save_path = "data/graph_data.json"
    logger.info(f"## Creating JSON file {save_path}")
    json_data = prepare_json(sorted_names, collected)
    with open(save_path, "w") as f:
        json.dump(json_data, f, indent=2)

    save_path = "data/graph_data_modules.json"
    logger.info(f"## Creating JSON file {save_path}")
    sorted_names_modules_only = [n for n in sorted_names if collected[n]["type"] == "file"]
    json_data = prepare_json(sorted_names_modules_only, collected)
    with open(save_path, "w") as f:
        json.dump(json_data, f, indent=2)

    return sorted_names, collected


def main_git_only(root_module_path: str):
    logger.info(f"### Analyzing {root_module_path}")
    git_dir, log_file = generate_git_log(root_module_path)
    collected_modules = {}
    git_dep = norm_counts(get_git_dependencies(log_file))  # type: ignore
    for module in git_dep:
        full_path = os.path.join(git_dir, module)  # type: ignore
        # check that we're not trying to access renamed files
        if os.path.isfile(full_path):
            collected_modules[module] = {
                "type": "file",
                "path": full_path,
                "dependencies_git": git_dep[module],
            }
    collected_modules = add_metrics_per_file(collected_modules, git_dir, log_file)
    sorted_names = sorted([k for k, v in collected_modules.items() if v["type"] == "file"])

    # same json for modules and all with only the files
    logger.info("## Creating JSON files")
    json_data = prepare_json(sorted_names, collected_modules)
    os.makedirs("data", exist_ok=True)
    with open("data/graph_data.json", "w") as f:
        json.dump(json_data, f, indent=2)
    with open("data/graph_data_modules.json", "w") as f:
        json.dump(json_data, f, indent=2)

    return sorted_names, collected_modules
