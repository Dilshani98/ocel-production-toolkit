import ast, os, re, sys

# Blind separation (CLAUDE.md section 3): toolkit code in reconstruction/ must not import from
# injection/ or evaluation/, and must not mention ground truth or the clean log. Hard asserts.
# Also a non-failing report of clean activity or object type names hard-coded in the toolkit.

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLKIT = os.path.join(ROOT, "reconstruction")
FORBIDDEN_IMPORTS = ("injection", "evaluation")
FORBIDDEN_TEXT = ("ground_truth", "socel2", ".xml")


def toolkit_files():
    return sorted(os.path.join(TOOLKIT, f) for f in os.listdir(TOOLKIT) if f.endswith(".py"))   # tests/ excluded


def clean_names():
    # Names declared in the clean log's header (read as text; nothing is parsed into the toolkit)
    with open(os.path.join(ROOT, "socel2_hinge.xml"), encoding="utf-8") as f:
        head = f.read(200_000)
    return set(re.findall(r'<(?:event|object)-type name="([^"]+)"', head))


def check():
    problems, hardcoded = [], []
    names = clean_names()
    assert len(names) >= 20, f"expected the 11 activities and 12 object types, found {len(names)}"
    for path in toolkit_files():
        rel = os.path.relpath(path, ROOT)
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            else:
                mods = []
            for mod in mods:
                if mod.split(".")[0] in FORBIDDEN_IMPORTS:
                    problems.append(f"{rel}:{node.lineno} imports {mod}")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value.lower()
                for bad in FORBIDDEN_TEXT:
                    if bad in text:
                        problems.append(f"{rel}:{node.lineno} mentions '{bad}'")
                for name in names:
                    if name.lower() in text:
                        hardcoded.append(f"{rel}:{node.lineno} '{name}' in {node.value[:60]!r}")
    return problems, hardcoded


if __name__ == "__main__":
    files = toolkit_files()
    print("toolkit files checked:", [os.path.basename(f) for f in files])
    problems, hardcoded = check()
    print("REPORT (does not fail): clean activity / object type names hard-coded in the toolkit:")
    print("\n".join("   " + h for h in hardcoded) if hardcoded else "   none found")
    for p in problems:
        print("FAIL", p)
    assert files, "no toolkit files found"
    assert not problems, f"{len(problems)} blind-separation problems"
    print("BLIND SEPARATION TEST PASSED")
