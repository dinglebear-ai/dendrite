"""Every artifact-library rule, as pure functions returning issue dicts.

One module so the index build and the standalone linter cannot drift apart.
Each check takes source text and returns a list of dicts with the keys
severity ("error" or "warning"), where (a repo-relative path), message and
rule, plus line and repair where they help a reader act.
"""
from __future__ import annotations

import re
from pathlib import Path
from .pr_reports import (BLOCKING_STATES, ID_PREFIXES, SCHEMA_VERSION, STATES,
                         branch_stem, repository_dir)

REQUIRED = {
    "title": r"<title>.+?</title>",
    "eyebrow": r'class="eyebrow">.+?</div>',
    "hero description": r'class="eyebrow">.*?<p>.+?</p>',
    "verification facts": r'<aside class="verified">.*?<strong>',
    "headline statistic": r'class="num">.+?</div>\s*<div class="label">',
}

STATUSES = ("draft", "review", "accepted", "superseded")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Folders whose findings make evidentiary claims. A claim with no stated
# boundary is the failure those artifacts exist to avoid, so it is an error
# there and a warning where a "finding" is a rule or a requirement.
PROOF_FOLDERS = ("reports", "pr-reports", "research", "proposals")

PR_REPORT_SECTIONS = {
    "public-summary": "sanitized public PR summary",
    "problem": "issue and impact",
    "provenance": "PR and environment provenance",
    "authorship": "claim authorship and independent verification",
    "timeline": "complete lifecycle timeline",
    "revisions": "report revision history",
    "decisions": "decisions and rejected alternatives",
    "disagreements": "disagreements and resolution",
    "changes": "files and changes",
    "coverage": "requirements-to-proof coverage",
    "dependencies": "dependency and version changes",
    "patterns": "reused repository patterns",
    "testing": "test matrix",
    "proof": "targeted reproducible proof",
    "resources": "resource lifecycle and zero-residual cleanup",
    "evidence-manifest": "evidence manifest and integrity",
    "review-threads": "review thread ledger",
    "post-review": "changes after review",
    "documentation": "documentation impact",
    "sessions": "agents and session transcripts",
    "tooling": "MCP, skills, commands, and agents",
    "issues": "encountered and pre-existing issues",
    "findings": "findings not acted upon",
    "risks": "risks and opportunities",
    "followup": "pre-merge and post-merge follow-up",
    "references": "complete references",
    "learnings": "learnings, repeated mistakes, and notable decisions",
    "disclosure": "public-payload and disclosure boundary",
    "artifact-quality": "artifact accessibility and portability",
}

PR_SCHEMA_VERSION = SCHEMA_VERSION
PR_STATES = STATES


def issue(severity, where, message, rule="CHECK", line=None, repair=None):
    record = {"severity": severity, "where": where, "message": message, "rule": rule}
    if line is not None:
        record["line"] = line
    if repair:
        record["repair"] = repair
    return record


def line_of(source, token):
    """1-based line of the first occurrence, so an issue can deep-link to it."""
    at = source.find(token)
    return source.count("\n", 0, at) + 1 if at >= 0 else 1


def check_structure(rel, source):
    """The five elements the index scrapes. Missing one renders a card with holes."""
    return [issue("error", rel, "missing " + label, "HTML-STRUCTURE", 1)
            for label, pattern in REQUIRED.items()
            if not re.search(pattern, source, re.S)]


def read_meta(source):
    """artifact.* fields from <meta> tags (HTML) or YAML front matter (Markdown)."""
    found = {key: value.strip() for key, value in
             re.findall(r'<meta name="artifact\.([\w-]+)" content="([^"]*)"', source)}
    if not found and source.startswith("---") and source.count("---") >= 2:
        block = source.split("---", 2)[1]
        found = {key: value.strip().strip("\"'") for key, value in
                 re.findall(r"^artifact\.([\w-]+):\s*(.+)$", block, re.M)}
    return found


def check_metadata(root, rel, source):
    issues, meta = [], read_meta(source)
    for field in ("id", "status", "date", "topic"):
        if not meta.get(field):
            issues.append(issue("error", rel, "missing artifact." + field, "META-REQUIRED",
                                1, "Add the field to the metadata block."))
    status = meta.get("status")
    if status and status not in STATUSES:
        issues.append(issue("error", rel, "artifact.status '" + status + "' is not one of "
                            + ", ".join(STATUSES), "META-STATUS", 1))
    date = meta.get("date")
    if date and not DATE.match(date):
        issues.append(issue("error", rel, "artifact.date '" + date + "' is not YYYY-MM-DD",
                            "META-DATE", 1))
    related = [value.strip() for value in meta.get("related", "").split(",")
               if value.strip() and "[" not in value]
    if status == "superseded" and not related:
        issues.append(issue("error", rel, "superseded artifacts must name a successor in "
                            "artifact.related", "META-SUPERSEDED", 1))
    return issues


def check_provenance(rel, source):
    """An artifact must say which branch and checkout produced it.

    `artifact.target` names the commit, which is not enough on its own: several
    worktrees share one repository here, and reconstructing which checkout a
    finding came from months later is the part nobody can do from memory. A
    warning rather than an error while the existing artifacts are backfilled.
    """
    meta = read_meta(source)
    return [issue("warning", rel, "missing artifact." + field, "META-PROVENANCE", 1,
                  repair="Add it from `git branch --show-current` / "
                         "`git rev-parse --show-toplevel`.")
            for field in ("branch", "worktree")
            if not meta.get(field)]


def check_pr_report(rel, source):
    """PR reports are repository-scoped, branch-named lifecycle records."""
    if not rel.startswith("pr-reports/"):
        return []
    parts = Path(rel).parts
    issues = []
    if (len(parts) != 3
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", parts[1])
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*(?:--[0-9a-f]{8})?\.html", parts[-1])):
        issues.append(issue(
            "error", rel,
            "PR reports must be named pr-reports/<org-repo>/<branch-with-slashes-as-hyphens>.html",
            "PR-PATH", 1,
            "Use the GitHub org/repo slug and normalize each branch slash to a hyphen."))
    meta = read_meta(source)
    for field in ("schema-version", "revision", "repository", "branch", "base", "head", "target",
                  "merge-base", "pr", "started", "updated", "worktree",
                  "evidence-manifest", "evidence-manifest-digest", "report-digest",
                  "provenance-status"):
        if not meta.get(field):
            issues.append(issue("error", rel, "missing artifact." + field, "PR-METADATA", 1,
                                "Fill the canonical PR provenance metadata."))
    if meta.get("schema-version") and meta["schema-version"] != PR_SCHEMA_VERSION:
        issues.append(issue("error", rel, "unsupported artifact.schema-version '"
                            + meta["schema-version"] + "'", "PR-SCHEMA", 1,
                            "Migrate the report to schema " + PR_SCHEMA_VERSION + "."))
    if meta.get("revision") and not re.fullmatch(r"[1-9]\d*", meta["revision"]):
        issues.append(issue("error", rel, "artifact.revision must be a positive integer",
                            "PR-REVISION", 1))
    if meta.get("repository") and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*",
                                                    meta["repository"]):
        issues.append(issue("error", rel, "artifact.repository must be owner/repository",
                            "PR-REPOSITORY", 1))
    sha = r"[0-9a-fA-F]{40}"
    for field in ("base", "head"):
        value = meta.get(field, "")
        if value and not re.fullmatch(r".+\s+@\s+" + sha, value):
            issues.append(issue("error", rel, "artifact." + field
                                + " must be '<branch> @ <full SHA>'", "PR-SHA", 1))
    for field in ("target", "merge-base"):
        value = meta.get(field, "")
        if value and not re.fullmatch(sha, value):
            issues.append(issue("error", rel, "artifact." + field + " must be a full SHA",
                                "PR-SHA", 1))
    head_sha = meta.get("head", "").split("@")[-1].strip().lower()
    head_branch = meta.get("head", "").split("@", 1)[0].strip()
    if meta.get("branch") and head_branch and meta["branch"] != head_branch:
        issues.append(issue("error", rel, "artifact.branch must equal artifact.head branch",
                            "PR-BRANCH", 1))
    if meta.get("target") and head_sha and meta["target"].lower() != head_sha:
        issues.append(issue("error", rel, "artifact.target must equal the head SHA",
                            "PR-SHA", 1))
    if meta.get("worktree") and not Path(meta["worktree"]).is_absolute():
        issues.append(issue("error", rel, "artifact.worktree must be absolute",
                            "PR-PATH", 1))
    if meta.get("evidence-manifest") and not Path(meta["evidence-manifest"]).is_absolute():
        issues.append(issue("error", rel, "artifact.evidence-manifest must be absolute",
                            "PR-PATH", 1))
    iso = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})"
    for field in ("started", "updated"):
        if meta.get(field) and not re.fullmatch(iso, meta[field]):
            issues.append(issue("error", rel, "artifact." + field
                                + " must be ISO-8601 with a time-zone offset", "PR-TIME", 1))
    report_digest = meta.get("report-digest", "")
    if report_digest and report_digest != "UNSEALED" and not re.fullmatch(r"[0-9a-f]{64}", report_digest):
        issues.append(issue("error", rel, "artifact.report-digest is not UNSEALED or SHA-256",
                            "PR-INTEGRITY", 1))
    manifest_digest = meta.get("evidence-manifest-digest", "")
    if manifest_digest and manifest_digest != "UNSEALED" and not re.fullmatch(r"[0-9a-f]{64}", manifest_digest):
        issues.append(issue("error", rel, "artifact.evidence-manifest-digest is invalid",
                            "PR-INTEGRITY", 1))
    if len(parts) == 3:
        repository = meta.get("repository", "")
        expected_repo_dir = repository_dir(repository)
        if repository and expected_repo_dir != parts[1]:
            issues.append(issue("error", rel, "artifact.repository does not match repository directory",
                                "PR-REPOSITORY", 1,
                                "Place the report under " + expected_repo_dir + "/."))
        expected_file = branch_stem(head_branch) + ".html"
        collision_file = expected_file[:-5] + "--" + meta.get("target", "")[:8] + ".html"
        if head_branch and re.sub(r"^\d{2}-\d{2}-\d{2}-", "", parts[-1]) not in (expected_file, collision_file):
            issues.append(issue("error", rel, "artifact.head branch does not match report filename",
                                "PR-BRANCH", 1,
                                "Rename the report to " + expected_file + "."))
    for section_id, label in PR_REPORT_SECTIONS.items():
        if not re.search(r'\bid=["\']' + re.escape(section_id) + r'["\']', source):
            issues.append(issue("error", rel, "missing PR report section: " + label,
                                "PR-SECTION", 1,
                                "Restore the #" + section_id + " section from the template."))
    declared_states = set(re.findall(r'data-state=["\']([^"\']+)["\']', source))
    invalid_states = declared_states - PR_STATES
    if invalid_states:
        issues.append(issue("error", rel, "unknown PR state(s): "
                            + ", ".join(sorted(invalid_states)), "PR-STATE", 1,
                            "Use one of " + ", ".join(sorted(PR_STATES)) + "."))
    record_ids = re.findall(r'data-record-id=["\']([^"\']+)["\']', source)
    bad_ids = [value for value in record_ids
               if not re.fullmatch(r"(?:REQ|CLM|DEC|TEST|E|RISK|REV|FUP|DIS)-\d{3,}", value)]
    if bad_ids:
        issues.append(issue("error", rel, "invalid stable record ID(s): "
                            + ", ".join(sorted(set(bad_ids))), "PR-ID", 1))
    duplicates = sorted({value for value in record_ids if record_ids.count(value) > 1})
    if duplicates:
        issues.append(issue("error", rel, "duplicate stable record ID(s): "
                            + ", ".join(duplicates), "PR-ID", 1))
    for section_id, prefix in ID_PREFIXES.items():
        block = re.search(r'<details id="' + re.escape(section_id) + r'".*?</details>', source, re.S)
        ids = re.findall(r'data-record-id="([^"]+)"', block.group(0)) if block else []
        rows = re.findall(r'<tr\b[^>]*>.*?</tr>', block.group(0), re.S) if block else []
        if any('data-record-id=' not in row for row in rows if '<td' in row):
            issues.append(issue("error", rel, "every data row in #" + section_id
                                + " requires a stable ID", "PR-ID", 1))
        if not ids:
            issues.append(issue("error", rel, "section #" + section_id
                                + " has no stable record IDs", "PR-ID", 1))
        elif any(not value.startswith(prefix + "-") for value in ids):
            issues.append(issue("error", rel, "section #" + section_id
                                + " must use " + prefix + " IDs", "PR-ID", 1))
        elif [int(value.rsplit("-", 1)[1]) for value in ids] != sorted(
                int(value.rsplit("-", 1)[1]) for value in ids):
            issues.append(issue("error", rel, "section #" + section_id
                                + " IDs are not monotonically ordered", "PR-ID", 1))
    known_ids = set(record_ids)
    missing_refs = sorted({value for group in re.findall(r'data-ref-ids="([^"]*)"', source)
                           for value in group.split() if value and value not in known_ids})
    if missing_refs:
        issues.append(issue("error", rel, "unresolved stable ID reference(s): "
                            + ", ".join(missing_refs), "PR-ID", 1))
    public = re.search(r'<details id="public-summary".*?</details>', source, re.S)
    if public:
        forbidden = re.search(r'(?:file:///|/Users/|/home/|\\Users\\|\b(?:10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)\d+\.\d+|[0-9a-f]{8}-[0-9a-f-]{27,})',
                              public.group(0), re.I)
        if forbidden:
            issues.append(issue("error", rel, "public summary contains private provenance: "
                                + forbidden.group(0), "PR-DISCLOSURE",
                                line_of(source, forbidden.group(0))))
    governed = ("public-summary", "coverage", "testing", "proof", "documentation",
                "review-threads", "post-review", "followup", "resources",
                "artifact-quality", "authorship", "decisions", "disagreements", "risks")
    for section_id in governed:
        block = re.search(r'<details id="' + section_id + r'".*?</details>', source, re.S)
        if block and 'data-state=' not in block.group(0):
            issues.append(issue("error", rel, "governed section #" + section_id
                                + " has no machine state", "PR-STATE", 1))
        if block:
            rows = re.findall(r'<tr\b[^>]*>.*?</tr>', block.group(0), re.S)
            if any('data-state=' not in row for row in rows if '<td' in row):
                issues.append(issue("error", rel, "every data row in governed section #"
                                    + section_id + " requires data-state", "PR-STATE", 1))
            for row in rows:
                if '<td' in row and 'data-state="PASS"' in row and not re.search(
                        r'data-ref-ids="[^"]*\bE-\d{3,}\b[^"]*"', row):
                    issues.append(issue("error", rel, "PASS row in #" + section_id
                                        + " requires manifest evidence reference", "PR-EVIDENCE", 1))
            for carrier in re.findall(r'<[^>]+data-state="PASS"[^>]*>', block.group(0)):
                if not re.search(r'data-ref-ids="[^"]*\bE-\d{3,}\b[^"]*"', carrier):
                    issues.append(issue("error", rel, "PASS state in #" + section_id
                                        + " requires manifest evidence reference", "PR-EVIDENCE", 1))
    for match in re.finditer(r'<[^>]+data-state="([^"]+)"[^>]*>', source):
        tag, state = match.group(0), match.group(1)
        if state != "PASS" and not re.search(r'data-reason="[^"]+"', tag):
            issues.append(issue("error", rel, state + " state has no data-reason",
                                "PR-STATE", line_of(source, tag)))
        if state == "NOT APPLICABLE" and not re.search(r'data-rule="[^"]+"', tag):
            issues.append(issue("error", rel, "NOT APPLICABLE has no data-rule",
                                "PR-STATE", line_of(source, tag)))
        if 'data-blocks-readiness="false"' in tag and not all(
                re.search(r'data-' + field + r'="[^"]+"', tag)
                for field in ("reason", "owner", "scope")):
            issues.append(issue("error", rel, "nonblocking state requires reason, owner, and scope",
                                "PR-READINESS", line_of(source, tag)))
    for section_id in ("coverage", "testing", "review-threads", "proof"):
        block = re.search(r'<details id="' + section_id + r'".*?</details>', source, re.S)
        for row in re.findall(r'<tr\b[^>]*>.*?</tr>', block.group(0), re.S) if block else []:
            if '<td' in row and not re.search(r'data-source-sha="[0-9a-fA-F]{40}"', row):
                issues.append(issue("error", rel, "head-bound row in #" + section_id
                                    + " requires full data-source-sha", "PR-STALE", 1))
    if meta.get("status") == "accepted":
        for section_id in governed:
            block = re.search(r'<details id="' + section_id + r'".*?</details>', source, re.S)
            if not block:
                continue
            states = set(re.findall(r'data-state="([^"]+)"', block.group(0))) if block else set()
            blocking_tags = [match.group(0) for match in re.finditer(r'<[^>]+data-state="([^"]+)"[^>]*>', block.group(0))
                             if match.group(1) in BLOCKING_STATES and 'data-blocks-readiness="false"' not in match.group(0)]
            if blocking_tags:
                issues.append(issue("error", rel, "accepted readiness section #" + section_id
                                    + " contains unresolved/stale states", "PR-READINESS", 1))
    return issues


def check_findings(rel, source):
    """A finding that cites evidence must state what that evidence does not prove."""
    if rel.split("/")[0] not in PROOF_FOLDERS:
        # A spec's rows are requirements and a doc's are rules. Neither makes an
        # evidentiary claim, so neither owes a proof boundary.
        return []
    bare, total, first = 0, 0, ""
    for index, block in enumerate(
            re.findall(r'<details\b(?=[^>]*\bclass="[^"]*\bissue\b)[^>]*>.*?</details>', source, re.S), 1):
        if 'class="evidence"' not in block and 'class="links"' not in block:
            continue
        total += 1
        if 'class="limit"' in block:
            continue
        bare += 1
        if not first:
            title = re.search(r"<h3>(.*?)</h3>", block, re.S)
            first = re.sub(r"<[^>]+>", "", title.group(1)).strip()[:48] if title else "#" + str(index)
    if not bare:
        return []
    return [issue("warning", rel, str(bare) + " of " + str(total)
                  + ' evidence-citing findings have no .limit (first: "' + first + '")',
                  "PROOF-LIMIT", line_of(source, '<details class="issue"'),
                  "State what the evidence does not establish.")]


# Paths inside a temporary checkout: the citation dies with the worktree, and
# cannot be rewritten to a remote base because the segment is not in the repo.
EPHEMERAL = re.compile(r"/\.claude/worktrees/|/\.git/|/tmp/|/private/var/folders/")


def check_local_links(rel, source):
    """Absolute file:// citations must resolve — the one rule that reaches outside."""
    issues, transient = [], set()
    for href in re.findall(r'href="file://([^"]+)"', source):
        target = href.split("#", 1)[0]
        if EPHEMERAL.search(target):
            transient.add(target)
        if not Path(target).exists():
            issues.append(issue("error", rel, "broken local link: " + target, "BROKEN-LINK",
                                line_of(source, 'href="file://' + href),
                                "Update or remove the stale source link."))
    if transient:
        issues.append(issue("warning", rel, str(len(transient))
                            + " citation(s) point into a temporary checkout, e.g. "
                            + sorted(transient)[0],
                            "EPHEMERAL-CITATION", line_of(source, sorted(transient)[0]),
                            "Cite the durable repository path; a worktree link dies with it."))
    return issues


# Elements an artifact may legitimately open, HTML plus the SVG subset the
# diagrams use. Anything else in angle brackets is prose the browser will eat.
ELEMENTS = set("""
html head body main section article aside div span details summary nav header footer
h1 h2 h3 h4 h5 h6 p ul ol li dl dt dd a b i em strong small mark sup sub del ins q
code pre kbd samp var cite dfn abbr time data address blockquote figure figcaption
table thead tbody tfoot tr td th caption colgroup col hgroup search menu dialog
meta link title style script br hr img input source template noscript wbr base
button label select option optgroup textarea form fieldset legend datalist output
progress meter canvas video audio iframe picture track object embed param map area
svg path circle rect g use line polyline polygon text tspan defs linearGradient
radialGradient stop clipPath mask pattern ellipse foreignObject marker symbol desc
""".lower().split())

# Elements with no closing tag, so tracking them on a stack would misreport.
VOID = set("""meta link br hr img input source col base area wbr track param embed
              path circle rect line polyline polygon stop ellipse use""".split())

# HTML5 lets these close themselves when the parent closes, so `<div><p>x</div>`
# is correct and must not be reported. Only a tag with a mandatory end tag says
# anything about the author's intent.
OPTIONAL_END = set("""p li dt dd td th tr thead tbody tfoot colgroup option
                      optgroup rt rp""".split())

TAG = re.compile(r"<\s*(/?)([A-Za-z][\w:-]*)([^>]*?)(/?)>")


def check_markup(rel, source):
    """Angle brackets the browser eats, and structural tags that do not balance.

    A placeholder written as a bare <name> parses as an unknown element, so the
    reader sees the sentence with a hole in it and nothing reports a problem.
    An unbalanced structural tag moves whatever follows it into the wrong box.
    Both survive every other rule here because the page still loads.

    Warning rather than error while the existing artifacts are backfilled.
    """
    text = prose(source)
    swallowed, stack, unbalanced = set(), [], []

    for match in TAG.finditer(text):
        closing, name, attrs, self_closing = match.groups()
        lowered = name.lower()
        if lowered not in ELEMENTS:
            # Attribute-free and lowercase reads as an unescaped placeholder;
            # anything else is likelier a stray fragment worth the same fix.
            if not attrs.strip():
                swallowed.add("<" + name + ">")
            continue
        if lowered in VOID or self_closing:
            continue
        if not closing:
            stack.append((lowered, match.start()))
        elif stack and stack[-1][0] == lowered:
            stack.pop()
        elif any(open_tag == lowered for open_tag, _ in stack):
            skipped = []
            while stack and stack[-1][0] != lowered:
                skipped.append(stack.pop()[0])
            stack.pop()
            if not set(skipped) <= OPTIONAL_END:
                still_open = sorted(set(skipped) - OPTIONAL_END)[0]
                unbalanced.append("</" + lowered + "> closes while <"
                                  + still_open + "> is still open")
        else:
            unbalanced.append("</" + lowered + "> has no matching open tag")

    issues = []
    if swallowed:
        first = sorted(swallowed)[0]
        issues.append(issue("warning", rel, str(len(swallowed))
                            + " placeholder(s) the browser will discard, e.g. " + first,
                            "SWALLOWED-MARKUP", line_of(source, first),
                            "Escape the angle brackets as &lt; and &gt; so the text renders."))
    never_closed = [tag for tag, _ in stack if tag not in OPTIONAL_END]
    for problem in unbalanced[:2] + [f"<{tag}> is never closed" for tag in never_closed[:2]]:
        issues.append(issue("warning", rel, "unbalanced markup: " + problem,
                            "UNBALANCED-MARKUP", 1,
                            "Match the tag to its partner; the page still loads, "
                            "so nothing else catches this."))
    return issues


PLACEHOLDER = re.compile(r"\[[^\]\n]+\]")
PR_PLACEHOLDER = re.compile(r"\{\{[^{}\n]+\}\}")


def prose(source):
    """Page text with CSS and scripts removed; explicit double braces mark slots."""
    source = re.sub(r"<style>.*?</style>", "", source, flags=re.S)
    return re.sub(r"<script>.*?</script>", "", source, flags=re.S)


def check_placeholders(rel, source, template_source=""):
    """PR reports reject every prompt token; other artifacts use template vocabulary."""
    if Path(rel).name.startswith("_template") or read_meta(source).get("template") == "true":
        return []                          # fill-in artifacts are placeholders by design
    if rel.startswith("pr-reports/"):
        left = set(PR_PLACEHOLDER.findall(prose(source)))
        if not left:
            return []
        return [issue("error", rel, str(len(left)) + " unfilled template placeholder(s), e.g. "
                      + sorted(left)[0], "PLACEHOLDER", line_of(source, sorted(left)[0]))]
    found = set(PLACEHOLDER.findall(prose(source)))
    known = set(PLACEHOLDER.findall(prose(template_source)))
    left = found if rel.startswith("pr-reports/") else found & known
    if not left:
        return []
    return [issue("error", rel, str(len(left)) + " unfilled template placeholder(s), e.g. "
                  + sorted(left)[0], "PLACEHOLDER", line_of(source, sorted(left)[0]))]


PLAN_BANNED = [
    (r"\bTBD\b", "TBD"),
    (r"\bTODO\b", "TODO"),
    (r"implement later", "'implement later'"),
    (r"appropriate error handling", "'add appropriate error handling'"),
    (r"handle edge cases", "'handle edge cases'"),
    (r"[Ss]imilar to Task \d", "a back-reference to another task instead of the code"),
    (r"[Ww]rite tests for the above", "'write tests for the above' with no test code"),
]


def check_plan(rel, source, template=False):
    """Check the self-contained implementation plan contract."""
    issues = []
    if "**For agentic workers:**" not in source and "superpowers:subagent-driven-development" not in source:
        issues.append(issue("error", rel, "missing the agentic-worker execution header", "PLAN-HEADER", 1))
    for field in ("**Goal:**", "**Architecture:**", "**Tech Stack:**"):
        if field not in source:
            issues.append(issue("error", rel, "missing " + field + " in the plan header",
                                "PLAN-HEADER", 1))
    for section in ("## Global Constraints", "## File Structure"):
        if section not in source:
            issues.append(issue("error", rel, "no " + section + " section", "PLAN-SECTION", 1))

    # Mask fenced code before parsing structure. A plan's examples legitimately
    # contain "### Task" headings, "- [ ] **Step" lines, and the banned phrases
    # themselves; the marker keeps "does this task show code?" answerable.
    masked = re.sub(r"(`{3,})\w*\n.*?^\1`*[ \t]*$", "\n<CODE>\n", source, flags=re.S | re.M)
    modern = bool(re.search(r'^artifact\.contract-version:\s*["\']?1(?:["\']|\s|$)',source,re.M))
    tasks = re.split(r"^### Task \d+:", masked, flags=re.M)[1:]
    if not tasks:
        issues.append(issue("error", rel, "no '### Task N:' sections", "PLAN-TASKS", 1))
    for number, task in enumerate(tasks, 1):
        name = task.splitlines()[0].strip()[:40]
        prefix = "Task " + str(number) + " (" + name + ")"
        if "**Files:**" not in task:
            issues.append(issue("error", rel, prefix + " has no **Files:** block", "PLAN-TASK", 1))
        else:
            block = re.search(r"\*\*Files:\*\*\s*(.*?)(?:\n\n|\*\*Interfaces)", task, re.S)
            for line in (block.group(1).splitlines() if block else []):
                entry = line.strip().lstrip("- ").strip()
                if entry and not re.match(r"(?i)(create|modify|test|delete|read)\s*:", entry):
                    issues.append(issue("warning", rel, prefix + " file entry does not start "
                                        "with Create/Modify/Test/Delete/Read: " + entry[:40],
                                        "PLAN-FILES", 1))
        if "**Interfaces:**" not in task:
            issues.append(issue("error", rel, prefix + " has no **Interfaces:** block",
                                "PLAN-TASK", 1))
        steps = re.findall(r"^- \[[ x]\] \*\*Step", task, re.M)
        if len(steps) < (1 if modern else 3):
            issues.append(issue("error", rel, prefix + " has " + str(len(steps))
                                + " checkbox steps — include a concrete action and verification",
                                "PLAN-STEPS", 1))
        if "<CODE>" not in task and not (modern and "Run:" in task and "Expected:" in task):
            issues.append(issue("error", rel, prefix + " needs concrete code or a verification command and expected result", "PLAN-CODE", 1))

    for pattern, label in ([] if template else PLAN_BANNED):
        if re.search(pattern, masked):
            issues.append(issue("error", rel, "plan contains " + label, "PLAN-PLACEHOLDER", 1))
    return issues


def check_design_tokens(sources):
    """One palette across the library. Artifacts may add classes, not redefine tokens."""
    seen = {}
    for rel, source in sorted(sources.items()):
        style = re.search(r"<style>(.*?)</style>", source, re.S)
        root = re.search(r":root\{(.*?)\}", style.group(1), re.S) if style else None
        if root is None:
            continue
        for token, value in re.findall(r"(--[\w-]+):([^;}]+)", root.group(1)):
            seen.setdefault(token, {}).setdefault(value.strip(), []).append(rel)

    issues, defined = [], set()
    for values in seen.values():
        for files in values.values():
            defined.update(files)
    for token in sorted(seen):
        values = seen[token]
        if len(values) > 1:
            detail = "; ".join(value + " in " + ", ".join(files)
                               for value, files in sorted(values.items()))
            issues.append(issue("error", "design system", "token " + token
                                + " has conflicting values — " + detail, "TOKEN-DRIFT"))
            continue
        missing = defined - {rel for files in values.values() for rel in files}
        if missing:
            issues.append(issue("warning", "design system", "token " + token
                                + " is undefined in: " + ", ".join(sorted(missing)),
                                "TOKEN-MISSING"))
    return issues


def validate_artifact(root, rel, source, order, template_source=""):
    """Every rule that applies to one artifact, chosen by folder, suffix, and origin."""
    folder = rel.split("/")[0]
    name = rel.rsplit("/", 1)[-1]
    template = name.startswith("_template")

    if rel.endswith(".md"):
        issues = check_plan(rel, source, template=template) if folder == "plans" else []
        if not template:
            issues.extend(check_metadata(root, rel, source))
            issues.extend(check_provenance(rel, source))
        return issues

    if not rel.endswith(".html"):
        return []

    issues = check_structure(rel, source)
    issues.extend(check_local_links(rel, source))
    issues.extend(check_markup(rel, source))
    if template:
        return issues
    issues.extend(check_metadata(root, rel, source))
    issues.extend(check_provenance(rel, source))
    if read_meta(source).get("generated"):
        return issues                      # rendered output, not authored content
    issues.extend(check_findings(rel, source))
    issues.extend(check_placeholders(rel, source, template_source))
    issues.extend(check_pr_report(rel, source))
    if rel not in order:
        issues.append(issue("warning", rel, "HTML artifact is not ordered in index-meta.json",
                            "INDEX-ORDER", repair="Add the path to index-meta.json order."))
    return issues
