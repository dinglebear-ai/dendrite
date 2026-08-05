---
name: new-report
description: Create a sourced investigation, audit, benchmark, comparison, incident-analysis, or research report in the personal knowledge base. Use when the user says "write a report", "document the investigation", "capture the audit", "summarize the benchmark", or needs conclusions that are broader than a session or maintenance log. This skill writes a report from observed evidence and never performs unrelated remediation, commits, or publishes it.
allowed-tools: Read, Write, Bash
---

# New Report

Create a durable report under `~/docs/reports/`.

## Distinction

- A session log records work chronology.
- A maintenance log records an operational change or incident.
- A report answers a question through evidence and analysis.

## Requirements

Use flat frontmatter with `title`, `created`, `updated`, `status`, `kind: report`, `scope`, `observed-at`, and related paths when available.

Include:

1. Question or objective
2. Scope and exclusions
3. Methodology
4. Sources and evidence
5. Findings
6. Analysis
7. Conclusions
8. Risks and limitations
9. Recommendations
10. Reproduction or verification steps
11. Related decisions, plans, logs, standards, and configuration

Separate observation from inference. Date point-in-time measurements. Do not silently remediate findings while writing the report. Print the final path and stop.
