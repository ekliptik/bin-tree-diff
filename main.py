import argparse, tempfile, subprocess, re, difflib, os, psutil
from pathlib import Path
from enum import Enum

from alive_progress import alive_bar
import magic

# Short-hand for a function like mkdtemp
new_tmp = tempfile.TemporaryDirectory

"""
    Gets set of directory paths and file paths
"""
def crawl_directory(root_path):
    dirs = []
    files = []
    for current_path in root_path.rglob('*'):
        rel_path = current_path.relative_to(root_path)
        if current_path.is_file():
            files.append(rel_path)
        elif current_path.is_dir():
            dirs.append(rel_path)

    dir_set, file_set = set(dirs), set(files)
    assert len(dir_set) == len(dirs) and len(file_set) == len(files), "Error beyond human comprehension"

    return dir_set, file_set

"""
    Runs a command, returns stdout
"""
def r(args, **kwargs):
    result = subprocess.check_output(args, **kwargs, text=True)
    return result

"""
    Print diff between sets of strings or paths
"""
def set_differs(one, two):
    for x in one - two:
        print(f"- {x}")

    for x in two - one:
        print(f"+ {x}")

    return one != two

# Suspected executables
EXE_SUFFIXES = ['', '.exe', '.lld', '.elf']
# Other binary files we may care about
BIN_SUFFIXES = ['.a', '.o']# '.dll', '.so']
TXT_SIFFIXES = ['.s', '.S', '.c', '.cpp', '.h', '.txt', '.md', '.ld']
"""
    Is filename interesting for diff?
"""
def is_cool(f):
    if not f.suffix in BIN_SUFFIXES + TXT_SIFFIXES + EXE_SUFFIXES:
        return False
    return True

"""
    Print the diff of two files
"""
def contents_differ(path1, path2, all):
    with open(path1, 'r') as file1, open(path2, 'r') as file2:
        # Get the diff
        differ = difflib.Differ()
        diff = list(differ.compare(file1.readlines(), file2.readlines()))
        does_differ = False
        lines_printed = 0

        # Print modified lines only
        for diff_line in diff:
            if diff_line[0] == '+' or diff_line[0] == '-':
                if not lines_printed:
                    print(f"Object {file1.name} differs:")
                print(diff_line.rstrip())
                lines_printed += 1
                if lines_printed > 30 and not all:
                    print("..etc. Diff has been shortened to save screen space. Use --all to get the full diff.")
                    break
                does_differ = True
        return does_differ
def main():
    # Let's not DDoS our machine
    os.nice(20)
    p = psutil.Process(os.getpid())
    p.ionice(psutil.IOPRIO_CLASS_IDLE)

    parser = argparse.ArgumentParser(description="Description of your script.")

    parser.add_argument("tree1", type=Path, help="A tree.")
    parser.add_argument("tree2", type=Path, help="Another tree.")
    parser.add_argument("--objdump", type=Path, default=Path("llvm-objdump"), help="Path to target objdump.")
    parser.add_argument("--all", action="store_true", help="Continue when problems are found.")

    args = parser.parse_args()

    tree1 = args.tree1
    tree2 = args.tree2

    print(f"Diffing {tree1} and {tree2}")
    dirs1, files1 = crawl_directory(tree1)
    dirs2, files2 = crawl_directory(tree2)

    """
        Terminate with error when condition is true, unless --all is set
    """
    def shortcut_exit(condition):
        # Yes, capture args from the context
        if condition and not args.all:
            print("Problem found, terminating early. Use --all to keep going and get the long, full report.")
            exit(1)

    # Phase 1: checking for missing / extra files and dirs

    print(f"dirs1 = dirs2? {dirs1 == dirs2}")
    shortcut_exit(set_differs(dirs1, dirs2))

    print(f"files1 = files2? {files1 == files2}")
    shortcut_exit(set_differs(files1, files2))

    ar = 'ar'
    target_objdump = args.objdump

    def differs(f):
        def obj_differs(abs1, abs2):
            with new_tmp() as one, new_tmp() as two:
                f_dis1, f_dis2 = f"{Path(one) / abs1.name}.dis", f"{Path(two) / abs2.name}.dis"
                r(f"{target_objdump} -dr {abs1.name} > {f_dis1}", cwd=abs1.parent, shell=True)
                r(f"{target_objdump} -dr {abs2.name} > {f_dis2}", cwd=abs2.parent, shell=True)
                return contents_differ(Path(one) / f_dis1, Path(two) / f_dis2, args.all)


        # This differs for rebuilt binaries
        filter_type = lambda x: re.sub(r'BuildID\[xxHash\]=\w+, ', '', x)

        # Sanity checks
        if filter_type(magic.from_file(tree1 / f)) != filter_type(magic.from_file(tree2 / f)):
            print(f"Different types of {f}:\n{magic.from_file(tree1 / f)}\n{magic.from_file(tree2 / f)}")
            return True

        if f.suffix in EXE_SUFFIXES:
            file_type = magic.from_file(tree1 / f)

            if 'executable' not in file_type:
                # Makefiles and some standard headers don't have a suffix. This is ok
                if 'include' in str(f) or f.name == 'Makefile':
                    return contents_differ(tree1 / f, tree2 / f, args.all)

                print(f"Not an executable {f}: {file_type}")
                return True

            if 'x86' not in file_type:
                print(f"Executable {f} unexpectedly doesn't target x86 or x64")
                return True
            # with new_tmp() as one, new_tmp() as two:
            #     r(f"{host_objdump} -dr {tree1 / f} > {one / f}.dis", cwd=one, shell=True)
            #     r(f"{host_objdump} -dr {tree2 / f} > {two / f}.dis", cwd=two, shell=True)
        elif f.suffix == '.a':
            with new_tmp() as one, new_tmp() as two:
                r([ar, 'x', tree1 / f], cwd = one)
                r([ar, 'x', tree2 / f], cwd = two)

                # Gather rel paths to all files in a dir
                relativized = lambda dir: set(map(lambda x: x.relative_to(dir), Path(dir).iterdir()))

                if relativized(one) != relativized(two):
                    print(f"In archive {f}:")
                    for obj in relativized(one) - relativized(two):
                        print(f"- {obj}")
                    for obj in relativized(two) - relativized(one):
                        print(f"+ {obj}")
                    return True

                # Cute little recursion
                if any(obj_differs(one / f, two / f) for f in relativized(one)):
                    return True

        elif f.suffix == '.o':
            if obj_differs(tree1 / f, tree2 / f):
                return True

        else:
            return contents_differ(tree1 / f, tree2 / f, args.all)

        return False


    # Phase 2: checking contents. Silly and slow, because Python and libmagic.
    print("Checking file contents according to built-in rules")
    # We can only compare files in both trees
    files = files1.intersection(files2)
    # Accumulate types of files we ignore, just for the user to audit
    ignored_suffixes = set()
    with alive_bar(len(files), spinner='classic') as bar:
        errors = 0
        for f in files:
            if is_cool(f):
                d = differs(f)
                # Somehow this is 2x faster than "if differs: shortcut(true)"
                shortcut_exit(d)
                if d:
                    errors += 1
            else:
                ignored_suffixes.add(f.suffix)
            # Advance the progress bar
            bar()

    print(f"Found {errors} discrepancies in file contents")
    print(f"Ignored suffixes: {ignored_suffixes}")


if __name__ == "__main__":
    main()
