# Code Quality Audit

Compliance of this repository with `CLAUDE.md` §2 (MIT CommLab convention)
and §6 (Ruff). Audited 2026-08-13 against commit `711d41a`.

**Result: clean.** Every automated and manual check passes. Two genuine
findings were raised and fixed during the audit; both are recorded below
rather than quietly corrected.

---

## 1. How the audit was run

| Check | Tool | Rule |
|---|---|---|
| Lint | `ruff check .` | §6 |
| Format | `ruff format --check .` | §6 |
| Column limit, tabs | `awk`, `grep -P '\t'` | §2 Structure |
| Docstrings, naming, operator placement, English-only | `claude_test/audit_mit_convention.py` | §2 |
| Behaviour unchanged by the audit | `pytest tests/` | §5 |

Ruff covers formatting and a large class of defects. It does **not** check
docstring presence, Google sections, verb-shaped names, or operator
placement on continuation lines, so those are audited by a purpose-built
script that parses the AST and the token stream.

## 2. Results

```
$ ruff check .
All checks passed!

$ ruff format --check .
6 files already formatted

$ python3 claude_test/audit_mit_convention.py
files audited : 6
findings      : 0

$ python3 -m pytest tests/ -q
84 passed in 18.60s
```

| §2 rule | Status | Evidence |
|---|---|---|
| 80-column limit | Pass | Only `protocols/OD_Normalization.py` exceeds it; vendored, see §4 |
| 4-space indent, no tabs | Pass | No tab found in any tracked `.py` |
| One statement per line | Pass | Enforced by `ruff format` |
| Operators lead continuation lines | Pass | Token-level check, 0 findings |
| Variables and classes are nouns | Pass | `FlexController`, `TransportError`, `AnalysisError`, `RunError` |
| Functions and methods are verbs | Pass after fix | See §3.1 |
| `lower_case` functions, `CamelCase` classes | Pass | AST check |
| Constants `lower_case` | Pass | `terminal_run_states`, `default_port`, `server_error_floor` — note §5 |
| Complete-sentence comments, context only | Pass | Manual read |
| English throughout | Pass | No non-ASCII character in any source file |
| PEP 257 docstrings on public functions and classes | Pass | AST check |
| `Args:` / `Returns:` / `Raises:` when applicable | Pass | AST check |

## 3. Findings raised and fixed

### 3.1 Scenario functions in `claude_test/` were nouns, not verbs

`show_error_detection.py` named its scenarios for the fault they injected
— `undefined_labware`, `syntax_error`, `layout_collision`. These are
callables, and §2 requires callables to read as verbs. CLAUDE.md §8 waives
the column limit and docstrings for `claude_test/`; it does not waive
naming.

Renamed to `probe_undefined_labware`, `probe_syntax_error`,
`probe_layout_collision`, `probe_missing_csv_parameter`,
`probe_unknown_run_id`, `probe_missing_deck_fixture`, and `controller` to
`build_controller`. The script was re-run afterwards and still reports all
six faults.

### 3.2 The audit script itself was wrong twice

Worth recording, because a checker that reports phantom faults trains
people to ignore it.

| Version | Findings | What was actually wrong |
|---|---|---|
| First, regex-based | 94 | 17 phantom operator faults from matching `or` inside `error`, `floor`, `operator`; 70 phantom docstring faults from demanding `Args:` for pytest fixtures |
| Second, token-based | 8 | Skipped `STRING` tokens, so `x = a or "b"` looked like a trailing operator |
| Third | 6 → 0 | `probe` was missing from the verb vocabulary |

Two rules were encoded that the first version lacked:

- **pytest fixtures are nouns.** A fixture supplies a value, so it is named
  for the value. Only callables a person invokes must read as verbs.
- **pytest injects test parameters.** Documenting them under `Args:` would
  describe a call that never happens, so tests and fixtures are exempt
  from the `Args:` requirement.

## 4. Formal exclusions

Both mirror `ruff.toml`, and both exist because linting the file would
destroy what makes it useful.

| Path | Why excluded |
|---|---|
| `protocols/OD_Normalization.py` | Vendored verbatim from the Opentrons Protocol Library (spec §1.3). Reformatting it would make it a different protocol from the one under test. |
| `tests/protocols/` | Deliberately broken — an uncompilable file, an undefined labware, a slot collision. Fixing them defeats their purpose. |
| `external/` | Third-party, carried as a submodule. |

`claude_test/*` additionally carries a `per-file-ignores` entry for `E501`,
encoding the §8 waiver so the linter enforces the same rule the prose
states.

## 5. One convention worth flagging

`CLAUDE.md` §2 gives `lower_case` for constants, with the example
`settle_mid_ms`. This departs from PEP 8, which uses `UPPER_SNAKE_CASE`,
and from the CommonClaude source table, which lists
`Constant | UPPER_SNAKE_CASE | SETTLE_MID_MS` for C. The project table is
followed here, since §1 gives the project file precedence:
`terminal_run_states`, `default_port`, `server_error_floor`. Ruff's `N`
rules accept it. Flagged only so the divergence is a decision on record
rather than an oversight.

## 6. Reproducing this audit

```bash
ruff check . && ruff format --check .
python3 claude_test/audit_mit_convention.py
python3 -m pytest tests/ -q
```

The audit script exits non-zero on any finding, so it can be wired into
CI or a pre-commit hook as-is.
