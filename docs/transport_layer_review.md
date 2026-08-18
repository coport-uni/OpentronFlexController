# Transport Layer Review

Spec §4.3 rule 5: *"메서드 총수가 30개를 초과하면 전송 계층 분리를
재검토한다"* — when the method count exceeds thirty, reconsider
splitting out the transport layer.

`FlexController` crossed the threshold at **32 methods** when
`get_instruments` and `get_modules` were added so the operator console
could show what is physically attached. This file is the
reconsideration the rule requires. Reviewed 2026-08-13.

## What the 32 methods are

| Group | Count | Methods |
|---|---|---|
| Construction | 1 | `__init__` |
| Transport | 2 | `_request`, `_retry` |
| Status | 4 | `health`, `is_reachable`, `get_instruments`, `get_modules` |
| Deck | 2 | `get_deck_configuration`, `set_deck_configuration` |
| Data files | 2 | `upload_data_file`, `list_data_files` |
| Protocol | 6 | `upload_protocol`, `get_analysis`, `wait_for_analysis`, `assert_analysis_clean`, `list_protocols`, `delete_protocol` |
| Run | 10 | `create_run`, `play`, `pause`, `stop`, `_action`, `get_run`, `get_commands`, `get_errors`, `monitor`, `list_runs`, `delete_run` |
| Workflow | 2 | `verify_only`, `execute` |
| Records | 2 | `save_artifact`, `log_event` |

## The decision: do not split yet

Splitting would mean a `FlexTransport` class owning `_session`,
`_request`, and `_retry`, with `FlexController` holding one as a
collaborator. That is the obvious shape, and it is the right shape
eventually. It is being deferred, for reasons that are about evidence
rather than taste:

1. **The count grew for a shallow reason.** Twenty-eight of the 32
   methods are one HTTP call and a field lookup. The class is wide, not
   deep — which is a different problem from the one rule 5 guards
   against. Rule 5 exists because a class holding transport *and*
   orchestration becomes hard to test; that has not happened here.
2. **The seam rule 5 wants already exists.** Spec §4.3 rule 4 requires
   that unit tests substitute `_request`, and all 31 unit tests do
   exactly that. The benefit a split would deliver — being able to test
   the endpoint methods without a network — is already delivered by the
   single-seam design. Splitting would relocate that seam, not create
   it.
3. **The cost lands on an in-review pull request.** The split touches
   every method and every test. Doing it inside the branch that added a
   console would make one reviewable change into two unreviewable ones.

## When to split

Any of these makes the split due, not optional:

- **Orchestration grows.** A third workflow method beside `verify_only`
  and `execute`, or a workflow that branches on transport concerns such
  as retry budgets or connection state. That is the coupling rule 5 is
  actually about.
- **Transport gains behaviour.** Authentication, connection pooling per
  host, request signing, or a second protocol beside HTTP. Any of these
  gives `_request` and `_retry` enough substance to own a class.
- **A second robot type appears.** If an OT-2 controller ever shares
  this transport, the shared part must be extracted rather than copied.
- **The count reaches 40**, which no amount of shallowness excuses.

## What holds the line meanwhile

`tests/test_flex_controller.py` asserts the method count equals a
documented constant rather than merely staying under a limit, so the
next method added fails the suite and forces this file to be revisited.
That test also requires this document to exist while the count is over
thirty.

## 2026-08-18 — `collect_labware_files`, count 32 to 33

A protocol that loads custom labware needs those definitions uploaded
with it, so `upload_protocol` gained a `labware_paths` argument and the
path resolution behind it needed a home. Resolving a file-or-directory
list is pure and touches neither the network nor instance state, so the
natural place was a module-level function.

Spec section 4.1 rules that out: the only entry points exposed outside
this module are the class and one CLI function. A public module-level
helper would be a third. It became a static method instead, which keeps
the module surface exactly as the spec fixes it and costs one method.

This does not move the split any closer. The new method is not
transport, not orchestration, and not state; it would sit on neither
side of a controller/transport boundary and would simply follow
`upload_protocol` wherever that goes. The triggers listed above are
unchanged, and the count remains well under forty.
