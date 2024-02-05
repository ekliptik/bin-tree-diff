import argparse, tempfile, subprocess
from pathlib import Path
from enum import Enum

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

    args = parser.parse_args()

    tree1 = args.tree1 # .resolve()
    tree2 = args.tree2 # .resolve()

    print(f"Diffing {tree1} and {tree2}")
    dirs1, files1 = crawl_directory(tree1)
    dirs2, files2 = crawl_directory(tree2)

    # Phase 1: checking for missing / extra files and dirs
    def report_diff(one, two):
        for x in one - two:
            print(f"- {x}")

        for x in two - one:
            print(f"+ {x}")

        return one == two

    report_diff(dirs1, dirs2)
    report_diff(files1, files2)
    print(files1 == files2)
    print(dirs1 == dirs2)


    def is_cool(f):
        # print(f.suffix)
        if not f.suffix in ['.a', '.o', '.s', '.S', '.c', '.cpp', '.h', '.dll', '.so'] + exe_suffixes:
            return False
        return True
        # return ('ASCII' in magic.from_file(tree1 / f))
        # print(magic.from_file(tree2 / f))

    ar = 'ar'
    objdump = '/home/emil/work/release-staging/8.1.0/bin/llvm-objdump'
    def diff_file(f):
        new_tmp = tempfile.TemporaryDirectory
        if f.suffix in exe_suffixes:
            # pass
            print(f)
            print(f.suffix)
            one = tempfile.mkdtemp('1')
            two = tempfile.mkdtemp('2')
            r(f"{objdump} -Dr {tree1 / f} > {one}.dis", cwd = one)
            r(f"{objdump} -Dr {tree2 / f} > {one}.dis", cwd = two)
            one.cleanup()
            two.cleanup()
        elif f.suffix == '.a':
            # pass
            with new_tmp('', f.name + '1') as one, new_tmp('', f.name + '2') as two:
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

        # elif f.suffix == '.o':



    # Phase 2: checking contents. Silly and slow, because Python and libmagic.
    files = files1.intersection(files2)
    ignored_suffixes = set()
    for f in files:
        if is_cool(f):
            diff_file(f)
        else:
            ignored_suffixes.add(f.suffix)

    print(ignored_suffixes)

    tempfile.gettempdir()


if __name__ == "__main__":
    main()
