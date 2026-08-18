# Audits the repository against the MIT convention of CLAUDE.md section 2, checking the rules
# ruff cannot: docstring presence and Google sections, verb-shaped function names, noun-shaped
# class names, English-only source, and continuation-line operator placement.
# Run: python3 claude_test/audit_mit_convention.py
#
# Tokenize rather than regex the source. An earlier regex version reported 17 phantom
# operator-placement faults by matching "or" inside "error", "floor", and "operator", and by
# reading docstring prose as code. A checker that cries wolf gets ignored, so it reads tokens.

import ast
import io
import re
import subprocess
import sys
import token
import tokenize
from pathlib import Path

root = Path(__file__).resolve().parents[1]

# Vendored upstream source and the deliberately broken protocols are excluded, exactly as
# ruff.toml excludes them: reformatting either would destroy what makes them useful.
excluded_dirs = ("external", "protocols", "tests/protocols")

# CLAUDE.md section 8 waives docstrings for claude_test/. It does not waive naming.
docstring_waived = ("claude_test",)

# A function name should read as an action. This is the vocabulary the codebase uses; anything
# outside it is reported for a human to judge rather than auto-failed.
known_verbs = {
    "assert",
    "build",
    "call",
    "count",
    "create",
    "delete",
    "describe",
    "check",
    "execute",
    "find",
    "format",
    "get",
    "health",
    "init",
    "is",
    "list",
    "load",
    "log",
    "main",
    "monitor",
    "parse",
    "pause",
    "play",
    "print",
    "probe",
    "read",
    "request",
    "retry",
    "run",
    "save",
    "server",
    "set",
    "show",
    "stop",
    "stream",
    "test",
    "unique",
    "upload",
    "verify",
    "wait",
    "walk",
    "action",
}

# Binary operators that must open a continuation line, not close the line before it.
trailing_operators = {
    token.PLUS,
    token.MINUS,
    token.STAR,
    token.SLASH,
    token.VBAR,
    token.AMPER,
    token.LESS,
    token.GREATER,
    token.EQEQUAL,
    token.NOTEQUAL,
    token.LESSEQUAL,
    token.GREATEREQUAL,
    token.PERCENT,
    token.DOUBLESTAR,
}
trailing_keywords = {"and", "or", "not", "in", "is"}


def list_source_files():
    """Return the repository's own Python files, upstream code excluded."""
    listed = subprocess.run(
        ["git", "ls-files", "*.py"], cwd=root, capture_output=True, text=True
    ).stdout.split()
    return [p for p in listed if not p.startswith(excluded_dirs)]


def is_public(name):
    return not name.startswith("_")


def is_pytest_function(node):
    """A test function or a fixture, which pytest calls rather than a caller."""
    if node.name.startswith("test_"):
        return True
    return any(
        "fixture" in ast.dump(decorator) for decorator in node.decorator_list
    )


def find_trailing_operators(text):
    """Report lines whose final code token is a binary operator.

    CLAUDE.md section 2 puts operators at the head of a continuation line so the reader can
    see at a glance that the line runs on. Only comments and layout tokens are skipped. A
    string literal is code and may legitimately end a line, so it counts as the last token;
    skipping it once made `x = a or "b"` look like a trailing operator. Docstring prose that
    happens to end in "and" never reaches here, because a docstring is one STRING token.
    """
    faults = []
    last_by_line = {}
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type in (
            token.COMMENT,
            token.NL,
            token.NEWLINE,
            token.INDENT,
            token.DEDENT,
            token.ENDMARKER,
        ):
            continue
        last_by_line[tok.start[0]] = tok
    for line_number, tok in last_by_line.items():
        trailing = tok.type in trailing_operators or (
            tok.type == token.NAME and tok.string in trailing_keywords
        )
        if trailing:
            faults.append(
                (
                    line_number,
                    "operator-placement",
                    f"line ends with {tok.string!r}",
                )
            )
    return faults


def check_file(rel):
    """Audit one file, returning (line, category, detail) for each finding."""
    text = (root / rel).read_text(encoding="utf-8")
    tree = ast.parse(text, filename=rel)
    problems = list(find_trailing_operators(text))
    waived = rel.startswith(docstring_waived)

    for number, line in enumerate(text.splitlines(), 1):
        if any(ord(ch) > 127 for ch in line):
            problems.append(
                (number, "non-english", "non-ASCII character in source")
            )

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node)
            pytest_owned = is_pytest_function(node)
            if is_public(node.name) and not doc and not waived:
                problems.append(
                    (node.lineno, "docstring", f"{node.name}: none")
                )
            if doc and is_public(node.name) and not pytest_owned and not waived:
                # Two exemptions apply here. pytest injects a test's parameters, so
                # documenting them as caller arguments would describe a call that
                # never happens. And CLAUDE.md section 8 makes docstrings optional
                # in claude_test/, which has to mean a voluntary one need not carry
                # the full Google sections -- otherwise writing a one-line note is
                # penalised while writing nothing is not.
                args = [
                    a.arg
                    for a in node.args.args
                    if a.arg not in ("self", "cls")
                ]
                args += [a.arg for a in node.args.kwonlyargs]
                if args and "Args:" not in doc:
                    problems.append(
                        (
                            node.lineno,
                            "docstring-args",
                            f"{node.name}: takes {args}, no Args:",
                        )
                    )
                returns = node.returns
                returns_none = (
                    isinstance(returns, ast.Constant) and returns.value is None
                )
                if (
                    returns is not None
                    and not returns_none
                    and "Returns:" not in doc
                    and "Yields:" not in doc
                ):
                    problems.append(
                        (
                            node.lineno,
                            "docstring-returns",
                            f"{node.name}: returns a value, no Returns:",
                        )
                    )
                if (
                    any(isinstance(x, ast.Raise) for x in ast.walk(node))
                    and "Raises:" not in doc
                ):
                    problems.append(
                        (
                            node.lineno,
                            "docstring-raises",
                            f"{node.name}: raises, no Raises:",
                        )
                    )
            # A pytest fixture supplies a value, so it is named for the value like any
            # other noun. Only callables a person invokes must read as verbs.
            if not pytest_owned:
                first = re.split(r"[_A-Z]", node.name.lstrip("_"))[0].lower()
                if first and first not in known_verbs:
                    problems.append(
                        (
                            node.lineno,
                            "naming-verb",
                            f"{node.name}: '{first}' is not a verb",
                        )
                    )
            if node.name != node.name.lower():
                problems.append(
                    (
                        node.lineno,
                        "naming-case",
                        f"{node.name}: functions are lower_case",
                    )
                )

        if isinstance(node, ast.ClassDef):
            if (
                not ast.get_docstring(node)
                and is_public(node.name)
                and not waived
            ):
                problems.append(
                    (node.lineno, "docstring", f"{node.name}: none")
                )
            if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", node.name):
                problems.append(
                    (
                        node.lineno,
                        "naming-case",
                        f"{node.name}: classes are CamelCase",
                    )
                )
    return problems


files = list_source_files()
total = 0
for rel in files:
    found = check_file(rel)
    if found:
        print(f"\n{rel}")
        for line, kind, detail in sorted(found):
            print(f"  {line:>5}  {kind:<20} {detail}")
        total += len(found)

print(f"\n{'=' * 70}")
print(f"files audited : {len(files)}")
print(f"findings      : {total}")
print("=" * 70)
sys.exit(1 if total else 0)
