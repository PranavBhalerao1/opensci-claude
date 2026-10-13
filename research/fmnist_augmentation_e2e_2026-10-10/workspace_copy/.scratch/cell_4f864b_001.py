import ast, pathlib
src = pathlib.Path("src/train.py").read_text()
ast.parse(src)
print("Syntax OK — no errors")
print(f"Lines: {len(src.splitlines())}")
