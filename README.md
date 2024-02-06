# A simple binary tree diff tool

Find differences between embedded toolchain deliverables.
Useful for refactoring build automation. Checks the following:

- there are no extra files or directories in either tree
- human-readable text files are equal
- objects have equal disassembly
- libraries contain the same objects
- the same objects in those libraries have equal disassembly
- all executables are x86 or x64

## Usage

```sh
pip install -r requirements.txt # or just nix-shell
# Screen-friendly mode
python3 main.py path/to/tree1 path/to/tree2 --objdump=/path/to/objdump
# Full log mode
python3 main.py path/to/tree1 path/to/tree2 --objdump=/path/to/objdump --all
```
