# Short launch copy (draft) — tmaudit

> Status: draft. Pick one or two channels; do not paste the same text everywhere
> on the same day. Facts to keep in sync: 263 tests passing, 3 skipped; MIT;
> `tmaudit` 0.5.2 on PyPI.

## Show HN

**Title:** Show HN: tmaudit – audit an ML paper's LaTeX for reporting defects

**Body:**

I kept finding the same reporting defects in my own submissions: no seed, no
hardware, no library version, a figure nobody references, a significance claim
with no power analysis. Reviewers find them; authors miss them.

tmaudit is a zero-dependency CLI that checks a LaTeX manuscript for those. Six
categories run on any paper (citations, sample/effect-size transparency,
ceremonial cites, statistical claims, figure captions, reproducibility). A
per-paper rulepack adds four more for five specific manuscripts and reports
"not applicable" elsewhere instead of a false green.

The interesting part for me was testing it: I ran all ten categories over 25
real arXiv cs.CL sources and it found four bugs in the tool, all fixed with
regression tests. One case study runs it on arXiv:2502.14074 and records three
candidate weaknesses that were checked and withdrawn.

`pipx install tmaudit && tmaudit verify --paper-dir path/to/paper`

It writes a readable `verify_generic.py` into the paper directory and runs it —
no API key, no network. MIT. I would rather hear where it is wrong than get a
star.

## r/MachineLearning (weekly-ish tools thread or a self-post)

**Title:** I built a CLI that audits an ML paper's LaTeX for the reporting
defects reviewers flag

**Body:**

Most of the review comments I get are not about the idea; they are about
reporting. Missing seeds/hardware/library versions, an unreferenced figure, a
p-value with no effect size or power analysis, a "code available" claim that
isn't there.

`tmaudit` checks those from the LaTeX source. Six generic categories + four
per-paper ones + a plugin API. No API key, no network, no runtime dependencies.

What makes me trust it a little: I ran it over 25 real arXiv papers and it found
four defects in itself (one category silently reported zero when it had not
run); all four are fixed and the failure is in the test suite. The scope is
stated in the output: a category without a config labels its zero
`[not applicable: ...]` instead of leaving it as a plain pass.

Quick start: `pipx install tmaudit` then
`tmaudit verify --paper-dir path/to/your/paper`. There is a deliberately flawed
sample in the repo. MIT. Feedback and counter-examples welcome.

## X / Mastodon thread (4 posts)

1. I built `tmaudit`: a CLI that reads an ML paper's LaTeX and flags the
   reporting defects reviewers find — missing seed/hardware/library versions,
   unreferenced figures, significance claims without power. No API key, no
   network.
2. Six generic checks + a per-paper rulepack + plugins. On a paper the rulepack
   was not written for, the zero carries a "not applicable" note instead of
   reading as a plain pass.
3. I tested it on 25 arXiv cs.CL sources. It found four bugs in the tool itself,
   including a category that reported zero without running. All fixed with
   regression tests; the failures are kept as evidence.
4. `pipx install tmaudit && tmaudit verify --paper-dir .` Writes a readable
   script into the paper dir and runs it. MIT. Tell me where it is wrong.

## 中文社区（知乎 / 即刻 / V2EX）

**标题：** 写了个工具，投稿前扫一遍论文的 LaTeX 里的“报告缺陷”

**正文：**

我投稿时被打回的意见，大多不是想法的问题，而是报告不完整：没写随机种子、
没写硬件、没写库版本、图定义了但正文没引用、给了 p 值却没有效应量或功效分析。
这些问题审稿人一眼能看到，作者自己反而容易漏。

`tmaudit` 直接从 LaTeX 源码检查这些。六个通用类别对任何论文都能跑（引用可解析、
样本量与效应量、礼节性引用、统计声明、图注、可复现性）；另外四个类别是给我自己
五篇论文写的规则包，遇到别的稿子会明确显示 `not applicable`，不会假装通过。

我拿 25 篇真实 arXiv cs.CL 源码跑了一遍，结果在工具自己身上找出四个 bug，
包括“某个类别根本没跑却报 0 个发现”。四个都修了并加了回归测试。

安装：`pipx install tmaudit`，然后
`tmaudit verify --paper-dir 你的论文目录`。不需要 API key，不联网，MIT。
它会在目录里生成一个可读的 `verify_generic.py` 并运行，你可以自己改阈值。
我更想要的是“你这里判断错了”的反例，不是 star。

## Posting notes

- Do not ask for stars. Ask for counter-examples and missing checks.
- Post the long version first; wait a day before the short ones.
- Reply to every issue in the first week, including the hostile ones.
- If someone reports a false positive, reproduce it on the bundled sample or their
  redacted `.tex`, then either fix it or add it to the "known limits" section.
