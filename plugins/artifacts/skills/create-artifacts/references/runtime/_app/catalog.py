"""Shared artifact catalog infrastructure."""
from __future__ import annotations
import hashlib
import html
import json
import re
import subprocess
from datetime import datetime, timezone

from . import validate
from pathlib import Path

CATEGORIES = ("reports", "pr-reports", "proposals", "plans", "specs", "research", "sessions", "docs", "scripts")
TAGS = {"reports": "report", "pr-reports": "proof", "proposals": "plan", "plans": "plan", "specs": "report", "research": "proof", "sessions": "proof", "docs": "report", "scripts": "proof"}
SKIP = {"CLAUDE.md", "AGENTS.md", "GEMINI.md", "README.md"}
SHA = re.compile(r"\b[0-9a-f]{40}\b", re.I)

def metadata(source, suffix):
    if suffix == ".html":
        return {key: value.strip() for key, value in re.findall(
            r'<meta\s+name=["\']artifact\.([\w-]+)["\']\s+content=["\']([^"\']*)["\']', source, re.I)}
    if source.startswith("---"):
        block = source.split("---", 2)[1]
        return {key: value.strip().strip('"\'') for key, value in re.findall(
            r'^artifact\.([\w-]+):\s*(.+)$', block, re.M)}
    if suffix in {'.sh','.py','.exs','.cjs','.mjs'}:
        return {key: value.strip().strip('"\'') for key,value in re.findall(
            r'^# artifact\.([\w-]+):\s*(.+)$', source, re.M)}
    return {}

def issue(severity, where, message, rule, line=None, repair=None):
    return {"severity": severity, "where": where, "message": message,
            "rule": rule, "line": line, "repair": repair}

def line_of(source, needle):
    position = source.find(needle)
    return source.count("\n", 0, position) + 1 if position >= 0 else None

def esc(value):
    return html.escape(str(value), quote=True)

def text(value):
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()

def find(pattern, source, group=1):
    match = re.search(pattern, source, re.S)
    return match.group(group) if match else None

def plain_blurb(path, lines):
    if path.suffix == ".md":
        body, started = [], False
        for line in lines:
            if line.startswith("#"):
                started = True
                continue
            if started and line.strip():
                body.append(line.strip())
            elif body:
                break
        return " ".join(body)
    comments = []
    for line in lines:
        if line.startswith("#!") or not line.strip():
            if comments:
                break
            continue
        if line.lstrip().startswith(("#", "//")):
            comments.append(line.lstrip("#/ ").rstrip())
        else:
            break
    if comments:
        return " ".join(comments)
    match = re.search(r'"""(.*?)"""', "\n".join(lines[:50]), re.S)
    return " ".join(match.group(1).strip().split("\n\n")[0].split()) if match else ""

def folder_blurb(folder):
    path = folder / "CLAUDE.md"
    return plain_blurb(path, path.read_text(errors="replace").splitlines()) if path.exists() else ""

def load_catalog(root):
    if not any((root / category).is_dir() for category in CATEGORIES):
        from .multi import load_catalog as load_multi
        return load_multi(root)
    meta_path = root / "index-meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    order, overrides = meta.get("order", []), meta.get("blurbs", {})
    groups, issues, fingerprints = [], [], []
    git = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root,
                         text=True, capture_output=True, check=False)
    modified = {line[3:].strip() for line in git.stdout.splitlines() if len(line) > 3}
    for category in CATEGORIES:
        folder = root / category
        if not folder.is_dir():
            issues.append(issue("error", category + "/", "taxonomy folder is missing", "TAXONOMY"))
            continue
        template = next(iter(folder.glob("_template.*")), None)
        if template is None:
            issues.append(issue("warning", category + "/", "category has no template", "TEMPLATE"))
        items = []
        # PR reports deliberately add one repository level
        # (`pr-reports/org-repo/branch.html`). Other categories remain flat so
        # their support directories cannot become accidental artifacts.
        paths = folder.rglob("*") if category == "pr-reports" else folder.iterdir()
        for path in sorted(paths):
            if (not path.is_file() or path.name in SKIP or "evidence" in path.parts
                    or path.name.startswith((".", "_", "test_"))
                    or path.name.endswith(".package.lock")
                    or path.name.endswith((".evidence.jsonl", ".evidence.jsonl.lock",
                                           ".evidence.jsonl.candidate", ".evidence.jsonl.pre-finalize"))):
                continue
            rel = path.relative_to(root).as_posix()
            stat = path.stat()
            fingerprints.append(f"{rel}:{stat.st_size}:{stat.st_mtime_ns}")
            if path.suffix == ".html":
                source = path.read_text(errors="replace")
                meta = metadata(source, path.suffix)
                title = text(find(r"<title>(.*?)</title>", source) or path.stem)
                title = re.sub(r"^[^—\-]*[—\-]\s*", "", title)
                aside = find(r'<aside class="verified">(.*?)</aside>', source) or ""
                item = {
                    "href": rel, "title": title,
                    "eyebrow": text(find(r'class="eyebrow">(.*?)</div>', source) or ""),
                    "blurb": text(find(r'class="eyebrow">.*?<p>(.*?)</p>', source) or ""),
                    "facts": [(text(a), text(b)) for a, b in re.findall(
                        r"<li>\s*<span>(.*?)</span>\s*<strong>(.*?)</strong>", aside, re.S)],
                    "source": source, "kind": "html",
                    "lines": source.count("\n") + 1, "bytes": stat.st_size,
                    "modified": stat.st_mtime, "shas": sorted(set(SHA.findall(source))),
                    "meta": meta,
                }
                template = folder / "_template.html"
                issues.extend(validate.validate_artifact(
                    root, rel, source, order,
                    template.read_text(errors="replace") if template.exists() else ""))
            else:
                lines = path.read_text(errors="replace").splitlines()
                source = "\n".join(lines)
                meta = metadata(source, path.suffix)
                item = {
                    "href": rel, "title": path.name, "eyebrow": "",
                    "blurb": plain_blurb(path, lines), "facts": [],
                    "kind": path.suffix.lstrip(".") or "file", "lines": len(lines),
                    "bytes": stat.st_size, "modified": stat.st_mtime,
                    "shas": sorted(set(SHA.findall("\n".join(lines)))),
                    "meta": meta,
                }
            item["id"] = meta.get("id") or rel.replace("/", "--").replace(".", "-")
            item["topic"] = meta.get("topic", "uncategorized")
            item["status"] = meta.get("status", "unclassified")
            item["date"] = meta.get("date", "")
            item["related_paths"] = [value.strip() for value in meta.get("related", "").split(",") if value.strip() and "[" not in value]
            refs = []
            for href, label in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', source, re.S):
                if href.startswith(("file://", "http://", "https://")):
                    refs.append({"href": href, "label": text(label) or href, "line": line_of(source, 'href="' + href)})
            item["references"] = refs
            item["blurb"] = overrides.get(rel, item["blurb"])
            item["dirty"] = rel in modified
            if not item["blurb"]:
                issues.append(issue("warning", rel, "no description can be derived", "DESCRIPTION"))
            items.append(item)

        # A rendered artifact (e.g. a plan built from its Markdown by
        # scripts/render-plan.py) hides its own source and links back to it,
        # so the catalog shows one card per plan rather than two.
        sources = set()
        for item in items:
            generated = find(r'<meta name="artifact\.generated" content="([^"]*)"',
                             item.get("source", ""))
            if not generated:
                continue
            sources.add(generated)
            src_path = folder / generated
            item["generated_from"] = (folder / generated).relative_to(root).as_posix()
            if not src_path.exists():
                issues.append(issue("error", item["href"], "generated from missing source: " + generated, "GENERATED-SOURCE"))
            elif src_path.stat().st_mtime > item["modified"]:
                issues.append(issue("error", item["href"], "stale render — re-run scripts/render-plan.py " + item["generated_from"],
                                    "STALE-RENDER", repair="scripts/render-plan.py " + item["generated_from"]))
        markdown_paths = folder.rglob("*.md") if category == "pr-reports" else folder.glob("*.md")
        for path in sorted(markdown_paths):
            if path.name in SKIP or path.name.startswith(("_", ".")):
                continue
            if path.name not in sources and not (folder / (path.stem + ".html")).exists():
                if category == "plans":
                    rel_source = path.relative_to(root).as_posix()
                    issues.append(issue("warning", rel_source, "no rendered artifact — run scripts/render-plan.py " + rel_source,
                                        "MISSING-RENDER", repair="scripts/render-plan.py " + rel_source))
        items = [item for item in items if Path(item["href"]).name not in sources]

        items.sort(key=lambda item: (
            (order.index(item["href"]), "") if item["href"] in order
            else (len(order), item["href"])
        ))
        if items or template:
            groups.append({
                "name": category, "blurb": folder_blurb(folder),
                "template": template.relative_to(root).as_posix() if template else None,
                "items": items,
            })
    for rel in order:
        if not (root / rel).exists():
            issues.append(issue("warning", "index-meta.json", "missing ordered artifact: " + rel, "INDEX-ORDER"))
    items = [item for group in groups for item in group["items"]]
    ids = [item["id"] for item in items]
    for duplicate in sorted({value for value in ids if ids.count(value) > 1}):
        paths = [item["href"] for item in items if item["id"] == duplicate]
        issues.append(issue("error", ", ".join(paths),
                            "duplicate artifact.id: " + duplicate,
                            "META-ID-DUPLICATE"))
    by_path = {item["href"]: item for item in items}
    # A rendered artifact hides its own source, so a relation naming the source
    # (plans/x.md) must still resolve to the card that represents it (plans/x.html).
    for item in items:
        origin = item.get("generated_from")
        if origin:
            by_path.setdefault(origin, item)
    for item in items:
        explicit = [by_path[path] for path in item["related_paths"] if path in by_path]
        topical = [other for other in items if other is not item and other["topic"] == item["topic"] and item["topic"] != "uncategorized"]
        reverse = [other for other in items if item["href"] in other["related_paths"]]
        seen = set()
        item["related"] = []
        for other in explicit + reverse + topical:
            if other["href"] not in seen:
                seen.add(other["href"])
                item["related"].append({"href": other["href"], "title": other["title"],
                                        "category": other["href"].split("/", 1)[0], "status": other["status"]})
        for path in item["related_paths"]:
            if path not in by_path and not (root / path).exists():
                issues.append(issue("error", item["href"], "related artifact does not exist: " + path,
                                    "RELATED-MISSING", repair="Correct artifact.related or create the artifact."))
    shas = sorted({sha for item in items if item["kind"] == "html" for sha in item["shas"]})
    return {
        "root": root, "groups": groups, "items": items, "issues": issues,
        "signature": hashlib.sha256("\n".join(sorted(fingerprints)).encode()).hexdigest(),
        "shas": shas, "generated_at": datetime.now(timezone.utc),
    }

def design_parts(catalog):
    if catalog.get("multi_project"):
        from .projects import template_path
        source = template_path("reports", "aurora").read_text()
        top = find(r'(<header class="top">.*?</header>)', source) or ""
        top = re.sub(r'<div class="commit">.*?</div>', '', top, flags=re.S)
        top = top.replace('Artifact Report', 'Project Artifacts')
        return find(r'<style>(.*?)</style>', source) or "", top, "<footer>Project Artifacts · Created with Dendrite</footer>"
    source = next((item["source"] for item in catalog["items"] if "source" in item), None)
    if source is None:
        from .projects import template_path
        source = template_path("reports", "aurora").read_text()
    return (find(r'<style>(.*?)</style>', source) or "", find(r'(<header class="top">.*?</header>)', source) or "", find(r'(<footer>.*?</footer>)', source) or "")
