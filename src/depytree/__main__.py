import sys

from depytree.build_depytree import main, main_git_only

if __name__ == "__main__":
    root_module = sys.argv[1]
    if len(sys.argv) > 2 and sys.argv[2] == "--git-only":
        sorted_names, collected = main_git_only(root_module)
    else:
        sorted_names, collected = main(root_module)
