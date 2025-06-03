# DePyTree

This repository includes a Python module `depytree`, which parses a given Python package to extract its internal dependency tree, saves the results in two JSON files (`data/graph_data.json` includes the dependencies between all files (modules) and their units, `data/graph_data_modules.json` includes only the dependencies between the modules), which can then be loaded using the `index.html` page to show the resulting dependency tree as an interactive d3.js graph.

### Usage

In the repo's root directory (i.e., where `pyproject.toml` lives), run the `depytree` module script with a package to create the package's internal dependency tree. The package can be supplied either as the Python package name (in this case it needs to be installed in the currently active environment so that it can be imported), or as a path to the folder that contains the package:

```
uv run python -m depytree package_name
```
or
```
uv run python -m depytree /path/to/package
```

This creates two JSON files in the `data` folder.

By passing the `--git-only` flag after the path to a directory under git version control, you can also create the git dependency analysis (i.e., not considering actual imports) for non-Python code repositories.

Next, run
```
python -m http.server 8000
```
to start a server and open http://localhost:8000/index.html to see the resulting graph.

In the page you can switch the data source between "all" (`graph_data.json`) and "modules" (`graph_data_modules.json`) to see either the full dependencies or only the dependencies between the modules (i.e., files; default).

**Green arcs** on the left go from top to bottom, i.e., show that a module or unit relies on a module or unit below it, while **red arcs** on the right show a dependency relationship from the lower node to the upper node. If available and enabled, **orange arcs** indicate that files were changed together in the same git commits.

You can **click on individual nodes** to highlight only its dependencies (in and out).

In accordance with the metrics introduced in the book _"Your Code as a Crime Scene (2nd Edition)"_ by Adam Thornhill, for the modules, the **size** of the node encodes the **complexity** of the code, measured as the average number of leading spaces in the file's lines (since highly indented code suggests nested logic that makes the code more complex). The **color** of the module nodes encodes the code's **volatility** as the number of lines in the file that were changed in the last year normalized by the current total number of lines in the file (only available if the package directory is a git repository; purple: changed a lot, cyan: didn't change).


#### Demo

A demo displaying the dependency graph of the Python FastAPI framework can be found [here](https://franziskahorn.de/demo_depytree/index.html).


### Known limitations / TODOs

- CPython / .pyx dependencies are not recognized and ignored.
- Import aliases that are defined by importing modules at a higher level `__init__.py` file are not considered. This can result in a fair number of missed dependencies if the package itself imports modules according to the path defined through the `__init__.py` file instead of the actual location of a module in the directory tree.
- Import statements that are inside functions or classes (i.e., not at the top level of a file) are not detected.
- Nested classes and functions are ignored (which is actually a feature, since these shouldn't be used by any outside units anyways).
- The sorting of the nodes done in the Python script is not 100% ideal yet. Generally, red arcs going from the bottom up are minimized, but there can still be long arcs going down as modules that belong together don't necessarily come one after the other (unless they are in the same folder). This is because the sorting only relies on a heuristic based on single element statistics instead of optimizing the sorting by considering all elements at once. You can manually sort the nodes in the resulting JSON files - for this it is recommended to start with the modules to get the higher level order right.
- Right now we export two JSON files, `graph_data.json` and `graph_data_modules.json`, which provide either the full graph (files + units in files) or only the overview of the files/modules. It is possible to switch between the files, but ideally there should be an option to open and close individual module nodes to display or hide the units within them, i.e., combine both plots into one.
- The Python code could use more thorough tests...
