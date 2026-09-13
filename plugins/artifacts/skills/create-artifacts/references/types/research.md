# research/

An open question investigated, with the evidence and the confidence attached. Research is the artifact type that is allowed to be uncertain — and is required to say so.

## Belongs here

Feasibility investigations, prior-art and ecosystem surveys, benchmark studies, "why does X behave this way" deep dives, evaluations of external tools or approaches.

## Does not belong here

- Settled facts about our own system, fully proven → `reports/`
- A recommendation built on the research → `proposals/`
- A transcript of the investigation session → `sessions/`

The line against `reports/`: a report's claims survived a proof pass and are stated flatly. Research holds claims that are *probably* true and labels them as such. When a research finding hardens into proof, promote it into a report and cite this artifact.

## Required structure

Same scraped elements as every artifact. Use the `.verified` aside for **investigation shape**: sources consulted, sources actually read in full, experiments run, and overall confidence. The gap between "consulted" and "read in full" is information — do not hide it.

## The research bar

Every finding carries:

1. **Method → Observation → Inference** in the `.trace`. Keep the inference step separate and explicit; it is the part most likely to be wrong, and separating it lets a reader disagree with your reasoning while accepting your data.
2. **A confidence tag** — `.runtime` for high confidence (measured or reproduced), `.medium` for tentative, and say why it is tentative.
3. **Cited evidence** in `.evidence` — measurements, quotes, command output. Do not summarize away the numbers.
4. **What would change this answer**, in the `.fix` block. The concrete observation that would falsify the finding. A claim you cannot imagine being wrong has not been investigated.
5. **A `.limit`** — sample size, recency, scope.

## Record the dead ends

Close with hypotheses the evidence contradicted. This is the highest-value section for the next person: it stops the same wrong idea being re-investigated in three months.

## External sources

Cite with real URLs. Distinguish primary sources (source code, specs, measurements) from secondary (blog posts, summaries). Prefer reading the source over reading about the source, and say which one you did.

## Metadata

Fill in the `<meta name="artifact.*">` block under the `<title>`. `status`,
`date`, and `topic` are required; the linter fails without them. Use `related`
to name the artifacts this one answers or feeds — that lineage is how someone
finds the rest of the chain.
