---
artifact.status: draft
artifact.id: "[stable-artifact-id]"
artifact.date: "[YYYY-MM-DD]"
artifact.topic: "[subject-slug]"
artifact.branch: "[branch the work was done on]"       # git branch --show-current
artifact.worktree: "[absolute path of the checkout]"   # git rev-parse --show-toplevel
artifact.related: "[specs/what-this-implements.html, proposals/what-approved-it.html]"
---

# [Feature Name] Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** [One sentence describing what this builds.]

**Architecture:** [2-3 sentences about the approach — the shape of the solution, the authority it respects, the seam it uses.]

**Tech Stack:** [Key technologies and libraries, e.g. Elixir 1.17, Phoenix LiveView, ExUnit, Ecto.]

## Global Constraints

[Project-wide requirements, one line each, exact values copied verbatim from the
spec. Every task's requirements implicitly include this section.]

- [Version floor, e.g. must run on OTP 26.]
- [Dependency limit, e.g. no new runtime dependencies.]
- [Naming or copy rule, e.g. all user-facing strings go through gettext.]
- [Platform requirement, e.g. must not require an array stop.]

---

## File Structure

[Map every file before defining tasks — this is where decomposition gets locked
in. One clear responsibility per file. Files that change together live together.
Follow the existing patterns in the target repo; do not unilaterally restructure.]

| File | Responsibility |
| --- | --- |
| `lib/unraid/[area]/[thing].ex` | [What this module owns, in one line.] |
| `lib/unraid/[area]/[thing]/[part].ex` | [What this part owns.] |
| `test/unraid/[area]/[thing]_test.exs` | [What this proves.] |

---

### Task 1: [Component Name]

**Files:**
- Create: `lib/unraid/[area]/[thing].ex`
- Modify: `lib/unraid/[area]/[caller].ex:120-138`
- Test: `test/unraid/[area]/[thing]_test.exs`

**Interfaces:**
- Consumes: [Exact signatures this task uses from earlier tasks. "None" for Task 1.]
- Produces: `[Module].[function]/[arity]` → `{:ok, [type]} | {:error, [reason]}`
  [The implementer of a later task sees only their own task. This block is how
  they learn the names and types you chose here — write them exactly.]

- [ ] **Step 1: Write the failing test**

```elixir
# test/unraid/[area]/[thing]_test.exs
defmodule Unraid.[Area].[Thing]Test do
  use ExUnit.Case, async: true

  alias Unraid.[Area].[Thing]

  test "[the specific behavior, stated as a fact]" do
    assert {:ok, %{[field]: [value]}} = [Thing].[function]([input])
  end
end
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `mix test test/unraid/[area]/[thing]_test.exs:8`
Expected: FAIL — `** (UndefinedFunctionError) function Unraid.[Area].[Thing].[function]/1 is undefined`

- [ ] **Step 3: Write the minimal implementation**

```elixir
# lib/unraid/[area]/[thing].ex
defmodule Unraid.[Area].[Thing] do
  @moduledoc "[One line: what this module owns.]"

  @spec [function]([input_type]) :: {:ok, [ok_type]} | {:error, [error_type]}
  def [function]([arg]) do
    {:ok, %{[field]: [value]}}
  end
end
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `mix test test/unraid/[area]/[thing]_test.exs`
Expected: PASS — `1 test, 0 failures`

- [ ] **Step 5: Commit**

```bash
git add test/unraid/[area]/[thing]_test.exs lib/unraid/[area]/[thing].ex
git commit -m "feat([area]): [what this task delivered]"
```

---

### Task 2: [Next Component]

**Files:**
- Create: `[exact path]`
- Test: `[exact path]`

**Interfaces:**
- Consumes: `Unraid.[Area].[Thing].[function]/1` → `{:ok, [type]} | {:error, [reason]}`
- Produces: `[exact signature later tasks depend on]`

- [ ] **Step 1: Write the failing test**

```elixir
[Complete test code. Never write "similar to Task 1" — repeat it in full;
the implementer may be reading tasks out of order.]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `[exact command]`
Expected: FAIL — `[exact error]`

- [ ] **Step 3: Write the minimal implementation**

```elixir
[Complete implementation code.]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `[exact command]`
Expected: PASS — `[exact output]`

- [ ] **Step 5: Commit**

```bash
git add [exact paths]
git commit -m "feat([area]): [what this task delivered]"
```

---

## Before handing this off

Run the self-review, then delete this section.

1. **Spec coverage** — skim each requirement in the spec this plan implements.
   Point at the task that delivers it. Add a task for any gap.
2. **Placeholder scan** — these are plan failures, not shorthand: "TBD",
   "implement later", "add appropriate error handling", "handle edge cases",
   "write tests for the above" with no test code, "similar to Task N", or any
   reference to a function or type no task defines.
3. **Type consistency** — a function called `clear_layers/1` in Task 3 and
   `clear_full_layers/1` in Task 7 is a bug. Check every Interfaces block
   against the tasks that consume it.
4. **Rendering conventions** — these strings are load-bearing, because
   `scripts/render-plan.py` colours the artifact from them:
   - Every `**Files:**` line starts with `Create:`, `Modify:`, `Test:`,
     `Delete:` or `Read:` — the verb becomes a coloured badge.
   - Every `**Interfaces:**` line starts with `Consumes:` or `Produces:`, and
     puts signatures in `backticks` so they highlight as code.
   - Step prose uses `Run:` and `Expected:`, and says `PASS` or `FAIL` in caps.
   - Every fence carries a language tag (```elixir, ```bash) or its code
     renders uncoloured.
   - Step titles keep the TDD wording (write the failing test / verify it fails
     / implementation / verify it passes / commit) so the cycle colours
     correctly and a missing verify step is visible at a glance.
