# Launch post (draft) — tmaudit

> Status: draft. Do not publish until `pip install tmaudit` serves 0.5.2 and the
> pre-flight checklist below passes.

## I ran my own audit tool on 25 papers. It found four bugs in the tool.

I wrote `tmaudit` because I kept finding the same class of defect in my own
submissions — not wrong theorems, but missing reporting: no seed, no hardware,
no library version, a figure nobody references, a significance claim with a
p-value and no power analysis. Reviewers find these. They are cheap to fix.
They are also easy to miss when you are the author, because you know what you
meant.

So the tool is deliberately narrow. It reads the LaTeX source and checks
reporting completeness against a fixed rulepack. It does not judge novelty, it
does not predict acceptance, and it does not need an API key or a network
connection.

### The part I trust least is the part I tested hardest

A rulepack written for five of my own papers is suspicious by construction. The
obvious question: what happens on a paper the configs were not written for?

I ran all ten categories over 25 real arXiv `cs.CL` LaTeX sources, exactly as
the CLI runs them. It found four defects in `tmaudit` itself:

1. the factory config was one specific paper's config, so a generic run applied
   that paper's checks to every document;
2. "clean" could mean "the check never ran" — a category with no configuration
   printed zero findings, indistinguishable from a pass;
3. one missing config key aborted the whole audit with a `KeyError`;
4. the BibTeX key parser fabricated "missing citation" findings when a key sat
   on its own line.

All four are fixed in 0.5.1 with regression tests, and the v0.5.0 findings are
kept verbatim in `case-studies/arxiv-corpus/` as evidence. A second case study
runs the tool on *Investigating Non-Transitivity in LLM-as-a-Judge*
(arXiv:2502.14074): it reports two reporting observations, records three
candidate weaknesses that were checked and **withdrawn**, and surfaced a
caption-parsing defect that is now fixed.

That is the pitch, honestly stated: the tool's value is not that it is always
right. It is that its failures are inspectable, and refusing to report a pass is
part of the output.

### What it actually checks

Six categories run on any LaTeX manuscript:

- **C4** citations that do not resolve to a `.bib`/`.bbl` entry;
- **C5** sample-size and effect-size omissions;
- **C7** ceremonial citations (cited, never engaged with);
- **C8** significance claims with no effect size or power analysis;
- **C9** figures without a caption, and `fig:` labels that are never referenced;
- **C10** no availability statement, or missing seeds / hyperparameters /
  hardware / library versions.

Four more (C1–C3, C6) are a per-paper rulepack for five specific manuscripts:
symbol definition, Bonferroni consistency, formalization, hype vocabulary. On
another paper they report **not applicable**, and the output says so instead of
printing a green `0 findings`.

### Try it

```bash
pipx install tmaudit
tmaudit verify --paper-dir path/to/your/paper
```

`verify` forks a `verify_generic.py` script into the target directory and runs
it. The audit is a readable Python file, not a hidden service: you can edit the
thresholds or delete it afterwards. A deliberately flawed sample ships in
`examples/sample-paper/` if you want to see the output before pointing it at
your own work.

If the generic categories are not enough, a plugin is a function under the
`tmaudit.plugins` entry-point group that receives the paper root and returns
`Finding` objects.

### Limits, stated plainly

- It is not a reviewer. It does not judge novelty or correctness.
- C1–C3/C6 are configured for five papers. They are not a universal rulepack.
- A clean run means "no finding from this rulepack", not "this paper is ready".
- It reads LaTeX. A paper whose source does not compile may still produce
  misleading line numbers.

### Why I am posting this

Not because it is finished — it is at 0.5.2 and the plugin API is still young —
but because the failure modes above are common, and the tool is most useful
before submission, when there is still time to fix them. If it finds one missing
seed statement in your paper, it did its job.

MIT licensed. Issues and counter-examples are more useful to me than stars.

```bash
pipx install tmaudit
tmaudit verify --paper-dir .
```

## Pre-flight checklist (do these before publishing this post)

1. `python -m build` and inspect the wheel: `detector_config/detector.yaml`
   must be present.
2. Fresh venv: `pip install tmaudit==0.5.2`, then
   `tmaudit verify --paper-dir examples/sample-paper` succeeds.
3. CI green on the release commit; `_check_pyz_fresh.py` accepts `tmaudit.pyz`.
4. Publish 0.5.2 to PyPI (trusted publishing from the GitHub Release).
5. Post the long version once; link the repo; do not cross-post the same text to
   five communities on the same day.
