import depytree.build_depytree as dpt
from depytree import metrics


def test_get_file_stats():
    loc, loc_nonempty, n_ind = metrics.get_file_stats("tests/mock_package/mock_module.py")
    assert loc == 50
    assert loc_nonempty == 36
    assert n_ind == 112


def test_get_git_revisions():
    commit_count, line_change_sum = metrics.get_git_revisions("tests/mock_package/mock_git_log.txt", "mock_module.py")
    assert commit_count == 8
    assert line_change_sum == 79
    commit_count, line_change_sum = metrics.get_git_revisions("tests/mock_package/mock_git_log.txt", "utils/__init__.py")
    assert commit_count == 3
    assert line_change_sum == 115
    commit_count, line_change_sum = metrics.get_git_revisions("tests/mock_package/mock_git_log.txt", "utils/mock_utils.py")
    assert commit_count == 5
    assert line_change_sum == 446
    commit_count, line_change_sum = metrics.get_git_revisions("tests/mock_package/mock_git_log.txt", "__init__.py")
    assert commit_count == 0
    assert line_change_sum == 0


def test_get_git_dependencies():
    git_deps = metrics.get_git_dependencies("tests/mock_package/mock_git_log.txt")
    assert sorted(git_deps.keys()) == [
        "mock_module.py",
        "utils/__init__.py",
        "utils/mock_utils.py",
    ]
    assert git_deps["mock_module.py"] == {"mock_module.py": 8, "utils/__init__.py": 1, "utils/mock_utils.py": 2}
    assert git_deps["utils/__init__.py"] == {"mock_module.py": 1, "utils/__init__.py": 3, "utils/mock_utils.py": 2}
    assert git_deps["utils/mock_utils.py"] == {"mock_module.py": 2, "utils/__init__.py": 2, "utils/mock_utils.py": 5}


def test_collect_modules():
    root_module_name, collected = dpt.collect_modules("tests/mock_package")
    assert root_module_name == "mock_package"
    assert sorted(collected.keys()) == [
        "mock_package",
        "mock_package.mock_module",
        "mock_package.utils",
        "mock_package.utils.mock_utils",
    ]
    assert collected["mock_package"]["children"] == ["mock_package.utils", "mock_package.mock_module"]
    assert collected["mock_package.utils"]["children"] == ["mock_package.utils.mock_utils"]
    assert collected["mock_package.utils"]["type"] == "directory"
    assert collected["mock_package.utils.mock_utils"]["type"] == "file"


def test_collect_modules_and_units():
    root_module_name, collected_modules, collected_units = dpt.collect_modules_and_units("tests/mock_package")
    assert root_module_name == "mock_package"
    assert sorted(collected_modules.keys()) == [
        "mock_package",
        "mock_package.mock_module",
        "mock_package.utils",
        "mock_package.utils.mock_utils",
    ]
    assert collected_modules["mock_package"]["children"] == ["mock_package.utils", "mock_package.mock_module"]
    assert collected_modules["mock_package.utils"]["children"] == ["mock_package.utils.mock_utils"]
    assert collected_modules["mock_package.utils"]["type"] == "directory"
    assert collected_modules["mock_package.utils.mock_utils"]["type"] == "file"
    assert sorted(collected_modules["mock_package.utils.mock_utils"]["children"]) == [
        "mock_package.utils.mock_utils.DataCleaner",
        "mock_package.utils.mock_utils.DataLoader",
        "mock_package.utils.mock_utils.DataParser",
        "mock_package.utils.mock_utils.ReportFormatter",
        "mock_package.utils.mock_utils.ReportGenerator",
        "mock_package.utils.mock_utils.run_pipeline",
        "mock_package.utils.mock_utils.test_pipeline",
    ]
    assert sorted(collected_modules["mock_package.mock_module"]["children"]) == [
        "mock_package.mock_module.generate_summary_report",
        "mock_package.mock_module.inspect_loader",
        "mock_package.mock_module.main",
        "mock_package.mock_module.parse_and_validate",
        "mock_package.mock_module.preprocess_source",
        "mock_package.mock_module.run_full_process",
        "mock_package.mock_module.run_pipeline",
    ]
    assert collected_modules["mock_package.mock_module"]["dependencies_other"] == {"mock_package.utils.mock_utils"}

    assert sorted(collected_units.keys()) == [
        "mock_package.mock_module.generate_summary_report",
        "mock_package.mock_module.inspect_loader",
        "mock_package.mock_module.main",
        "mock_package.mock_module.parse_and_validate",
        "mock_package.mock_module.preprocess_source",
        "mock_package.mock_module.run_full_process",
        "mock_package.mock_module.run_pipeline",
        "mock_package.utils.mock_utils.DataCleaner",
        "mock_package.utils.mock_utils.DataLoader",
        "mock_package.utils.mock_utils.DataParser",
        "mock_package.utils.mock_utils.ReportFormatter",
        "mock_package.utils.mock_utils.ReportGenerator",
        "mock_package.utils.mock_utils.run_pipeline",
        "mock_package.utils.mock_utils.test_pipeline",
    ]
    assert collected_units["mock_package.utils.mock_utils.DataLoader"]["type"] == "class"
    assert collected_units["mock_package.mock_module.inspect_loader"]["type"] == "function"
    for unit in collected_units:
        if unit.startswith("mock_package.utils.mock_utils"):
            assert collected_units[unit]["dependencies_other"] == set()
    assert collected_units["mock_package.utils.mock_utils.DataLoader"]["dependencies_same"] == {
        "mock_package.utils.mock_utils.DataParser"
    }
    assert collected_units["mock_package.mock_module.run_full_process"]["dependencies_same"] == {
        "mock_package.mock_module.generate_summary_report"
    }
    assert collected_units["mock_package.mock_module.run_full_process"]["dependencies_other"] == {
        "mock_package.utils.mock_utils.run_pipeline"
    }

    collected_modules, collected_units = dpt.add_n_incoming_deps(collected_modules, collected_units)
    assert collected_units["mock_package.utils.mock_utils.DataLoader"]["n_incoming_dependencies_same"] == 1
    assert collected_units["mock_package.utils.mock_utils.DataLoader"]["n_incoming_dependencies_other"] == 1

    collected_modules = dpt.propagate_directory_deps(collected_modules)
    assert collected_modules["mock_package.utils.mock_utils"]["n_incoming_dependencies_other"] == 1
    assert collected_modules["mock_package.utils"]["n_incoming_dependencies_other"] == 1
