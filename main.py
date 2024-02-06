import argparse, tempfile, subprocess, re, difflib
from pathlib import Path
from enum import Enum

from alive_progress import alive_bar
import magic

exe_suffixes = ['', '.exe', '.lld']


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


def r(args, **kwargs):
    result = subprocess.check_output(args, **kwargs, text=True)
    return result


def main():
    parser = argparse.ArgumentParser(description="Description of your script.")

    parser.add_argument("tree1", type=Path, help="A tree.")
    parser.add_argument("tree2", type=Path, help="Another tree.")
    parser.add_argument("--all", action="store_true", help="Continue when problems are found.")

    args = parser.parse_args()

    tree1 = args.tree1 # .resolve()
    tree2 = args.tree2 # .resolve()

    print(f"Diffing {tree1} and {tree2}")
    dirs1, files1 = crawl_directory(tree1)
    dirs2, files2 = crawl_directory(tree2)

    # Phase 1: checking for missing / extra files and dirs
    def set_differs(one, two):
        for x in one - two:
            print(f"- {x}")

        for x in two - one:
            print(f"+ {x}")

        return one != two

    def shortcut_exit(condition):
        if condition and not args.all:
            print("Problem found, terminating early. Use --all to keep going and get the long, full report.")
            exit(1)

    print(f"dirs1 = dirs2? {dirs1 == dirs2}")
    shortcut_exit(set_differs(dirs1, dirs2))

    print(f"files1 = files2? {files1 == files2}")
    shortcut_exit(set_differs(files1, files2))


    def is_cool(f):
        # print(f.suffix)
        if not f.suffix in ['.a', '.o', '.s', '.S', '.c', '.cpp', '.h', '.dll', '.so'] + exe_suffixes:
            return False
        return True
        # return ('ASCII' in magic.from_file(tree1 / f))
        # print(magic.from_file(tree2 / f))

    ar = 'ar'
    host_objdump = 'objdump'
    target_objdump = '/home/emil/work/release-staging/8.1.0/bin/llvm-objdump'

    def differs(f):
        new_tmp = tempfile.TemporaryDirectory
        def reasonable_types(f):
            # This differs for rebuilt binaries
            filter_type = lambda x: re.sub(r'BuildID\[xxHash\]=\w+, ', '', x)

            assert filter_type(magic.from_file(tree1 / f)) == filter_type(magic.from_file(tree2 / f)), \
                f"Diff types of {f}:\n{magic.from_file(tree1 / f)}\n{magic.from_file(tree2 / f)}"

        def obj_differs(abs1, abs2):
            # print(f"nya {abs1} {abs2}")
            with new_tmp() as one, new_tmp() as two:
                f_dis1, f_dis2 = f"{Path(one) / abs1.name}.dis", f"{Path(two) / abs2.name}.dis"
                r(f"{target_objdump} -dr {abs1.name} > {f_dis1}", cwd=abs1.parent, shell=True)
                r(f"{target_objdump} -dr {abs2.name} > {f_dis2}", cwd=abs2.parent, shell=True)
                with open(Path(one) / f_dis1, 'r') as dis1, open(Path(two) / f_dis2, 'r') as dis2:
                    differ = difflib.Differ()
                    diff = list(differ.compare(dis1.readlines(), dis2.readlines()))
                    does_differ = False
                    lines_printed = 0
                    for diff_line in diff:
                        if diff_line[0] == '+' or diff_line[0] == '-':
                            if not lines_printed:
                                print(f"Object {abs1.name} differs:")
                            print(diff_line, end='')
                            lines_printed += 1
                            if lines_printed > 30 and not args.all:
                                print("..etc. Diff has been shortened to save screen space. Use --all to get the full diff.")
                                break
                            does_differ = True
                    return does_differ


        reasonable_types(f)

        if f.suffix in exe_suffixes:
            file_type = magic.from_file(tree1 / f)

            if 'executable' not in file_type:
                # Makefiles and some standard headers don't have a suffix. This is ok
                if 'include' in str(f) or f.name == 'Makefile':
                    # TODO push to something
                    return False

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
                # print("one")
                # print(relativized(one))
                if any(obj_differs(one / f, two / f) for f in relativized(one)):
                    return True

        elif f.suffix == '.o':
            # print("two")
            if obj_differs(tree1 / f, tree2 / f):
                return True

        return False


    # Phase 2: checking contents. Silly and slow, because Python and libmagic.
    print("Checking file contents according to built-in rules")
    files = files1.intersection(files2)
    ignored_suffixes = set()
    with alive_bar(len(files)) as bar:
        for f in files:
            if is_cool(f):
                shortcut_exit(differs(f))
            else:
                ignored_suffixes.add(f.suffix)
            bar()

    print(f"Ignored suffixes: {ignored_suffixes}")


if __name__ == "__main__":
    main()
