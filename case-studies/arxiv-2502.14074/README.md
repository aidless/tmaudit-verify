# Case study: `tmaudit` on a real paper — arXiv:2502.14074

`tmaudit`'s built-in categories are a per-paper rulepack. For a paper they
were not written for, the tool offers two paths: the generic checks via
`tmaudit verify --paper-dir DIR`, and a plugin via
`tmaudit plugins run NAME --paper-dir DIR`. This case study runs both
against one real paper and records what they report and what they don't.

Subject: **Investigating Non-Transitivity in LLM-as-a-Judge**
(arXiv:[2502.14074](https://arxiv.org/abs/2502.14074), ICML 2025 Spotlight).
The LaTeX source is published by the authors; `inputs.txt` pins every file
this audit read by SHA-256, and `audit_paper.py` re-verifies them (a
mismatch aborts with exit 2).

> **What this is.** A reporting-standards observation about two things a
> quantitative paper can make easier to read: it uses the word
> "significant" with no hypothesis-test standard anywhere, and its
> percentage tables carry no uncertainty.
>
> **What this is not.** A claim that any result in the paper is wrong. The
> numbers the text quotes agree with the numbers in the tables; the
> availability statement is present. Both observations are about *how a
> claim is presented*, not about whether it holds.

## How the audit runs

```bash
python3 audit_paper.py --paper-dir _paper --archive src.tar.gz
```

Three commands run against a **copy** of the extracted sources (the
pristine download is never mutated by the fork `verify` writes):

| # | command | what it is |
|---|---|---|
| 1 | `tmaudit verify --paper-dir DIR` | the generic categories (empty config) |
| 2 | `tmaudit plugins run claims-significance-no-test --paper-dir DIR` | finding A |
| 3 | `tmaudit plugins run claims-percent-table-no-uncertainty --paper-dir DIR` | finding B |

Both plugins are `requires_config=False`: they read only the manuscript and
name no line number, symbol, or table of this paper, so they are general
checks rather than a rulepack aimed at this document.

## What the generic categories reported

| category | marker | n | reading |
|---|---|---:|---|
| C1 / C2 / C3 / C6 | OK | 0 | **not applicable** — no per-paper config; by design |
| **C4 citation hygiene** | OK | 0 | all cite keys resolved — from the compiled `.bbl` (44 entries), since the paper ships **no `refs.bib`** |
| C5 sample size / test | OK | 0 | no p-value or `d=` in the abstract to check |
| C7 ceremonial citations | MEDIUM | 10 | the coarse C7 detector (see `case-studies/arxiv-corpus/`); **not** reported as a defect of this paper |
| C8 statistical power | OK | 0 | no "significantly different" claim to check |
| **C9 figure captions** | OK | 0 | after the fix below (first run reported 2, both false positives) |
| C10 reproducibility | LOW | 3 | metadata keyword checks only (hyperparameters / seed / library version); the availability statement itself is present |

Two things about this table are worth naming.

* **C4 = 0 is a positive result, not a silent skip.** The paper publishes
  no `.bib`, only a compiled `paper.bbl`. Before this audit, a missing
  `refs.bib` was an operational error (`exit 2`). `verify --paper-dir` now
  reads keys from a `.bbl` (`\bibitem{key}`) and, when neither source is
  present, reports C4 as *not applicable* rather than aborting — so the
  check ran here and found the citations intact.
* **C10's three LOW findings are the coarse keyword tier**, not evidence
  that the paper is irreproducible: it does state the judge `temperature`
  (line 340) and the code/data URL (line 468), but not an ML "learning
  rate / seed / library version" string.

## Finding A — significance wording with no test standard

`claims-significance-no-test`: **10 uses of "significant/significantly"
on 9 lines** (211, 288, 327, 369, 401, 408, 662, 722, 770), and the
document reports **no p-value, bootstrap, permutation test, or significance
test anywhere** (verified: zero matches for `p-value` or `bootstrap` in the
source).

The nuance is the point: the uses are not homogeneous. Line 288
("significant computational challenges") is ordinary English, and line 327
explicitly **defines** the term — "We denote significant performance
advantages with \(\gg\)" — giving "significant" a paper-local, non-statistical
meaning before using it at 369, 401, 408. Others read as inferential
claims ("exhibits a **significant** increase in non-transitivity", line 408).

What is missing is a single place where the word is tied to a test. Because
the paper reports no test standard at all, a reader cannot tell which uses
are statistical and which are the local \(\gg\) notation. The finding is a
reporting observation; it does not say any of those differences is spurious.

## Finding B — percentage tables with no uncertainty

`claims-percent-table-no-uncertainty`: three tables report percentages as
point estimates with no uncertainty marker, in a paper that reports
intervals elsewhere.

| table (line) | what it holds | example |
|---|---|---|
| **416** | main correlation comparison `RRBT_cor` | Spearman 96.4% (round-robin, w. LC) vs 95.0% (AlpacaEval); Kendall 86.3% vs 82.1%; Δ +1.4% / +4.2% |
| 827 | round-robin vs AlpacaEval | 6 percentage values |
| 882 | full leaderboard, 20 models | 40 percentage values |

The check fires only because the paper **is** capable of reporting spread:
line 446's figure caption states "reporting the mean correlation with a
95 % confidence interval" over 2000 trials, and line 754/764 gives
\(\pm\) and a standard deviation. So the headline comparison table at 416
carries less information than the paper gives elsewhere — and it is the one
whose Δ values the abstract-level text leans on (lines 451, 453).

To be explicit about what is **not** wrong: the Δ values quoted in the text
(+4% / +5.2% without LC; +1.4% / +4.2% with LC) match the table's Δ row
exactly. There is no numeric inconsistency; there is a missing interval.

## One tool defect this audit surfaced (and fixed)

The first run reported **C9 = 2**: "figure (line 187) has no caption" and
"figure (line 435) has no caption". Both figures **do** have captions. The
cause is in the tool, not the paper: the caption was extracted with a
brace-bounded regex that accepted a single nesting level, and both captions
nest twice — `\caption{\textbf{... \textsc{Swim} ...}}` and
`\caption{\textcolor[HTML]{2f70b8}{{Llama-3-70B}} ...}`. A figure that
carried a caption was reported as having none.

Fixed in this commit: caption extraction is now a balanced-brace scan
(`_c9_balanced_content`), with regression tests for the `\textbf{...\textsc{...}}`
and `{{...}}` forms and for a genuinely unbalanced group. The committed
`results.json` is the post-fix run (C9 = 0).

## What was checked and withdrawn

Three candidate weaknesses were investigated and **did not hold**; they are
recorded here so the audit is not read as more than it is.

1. **Tie-threshold sensitivity.** Hypothesis: the non-transitivity results
   might be fragile to how ties are handled. Withdrawn: the paper already
   reports the variants — `4senarios_strict_tie` (lines 660–664),
   `4senarios_4omini` (552, 586), `4senarios_arena` (554, 618).
2. **Body/table numeric mismatch.** Hypothesis: the improvements stated in
   the prose differ from the table. Withdrawn: they agree exactly (lines
   451/453 vs the `\Delta` row of `RRBT_cor` at line 429).
3. **Missing reproducibility statement.** Hypothesis: no code/data
   availability. Withdrawn: `\url{https://github.com/yix8/llm-nontransitivity}`
   is present (line 468), and the judge configuration is stated
   (`temperature set to 0`, line 340).

## What this does not establish

* It does not evaluate the paper's correctness, novelty, or
  reproducibility. It measures two reporting conventions.
* The two plugin checks are heuristics with named boundaries: finding A is
  document-level (it fires because *no* test standard appears, not per
  sentence), and finding B fires on *every* percentage table without an
  uncertainty marker, not only the headline one. Both say so in their
  message text.
* A significance word with a confidence interval but no test, or a
  percentage table that legitimately needs no interval, can still be
  flagged. That is the cost of a mechanical rule that reads only text.

## Reproduce

```bash
# 1. fetch and extract the source
curl -L -o src.tar.gz https://arxiv.org/e-print/2502.14074
mkdir -p _paper && tar -xzf src.tar.gz -C _paper

# 2. install tmaudit and the plugin from a checkout of this repo
pip install -e .
pip install -e ./case-studies/arxiv-2502.14074/tmaudit_claims_plugin

# 3. audit (verifies inputs.txt hashes, runs in a temp copy)
python3 audit_paper.py --paper-dir _paper --archive src.tar.gz
```

`_paper/` and `src.tar.gz` are git-ignored; `inputs.txt` and `results.json`
are committed, so the results can be read without the download.

---

# 中文部分

**这是 `tmaudit` 对一篇真实论文的审计。** 对象是 **arXiv:2502.14074**
《Investigating Non-Transitivity in LLM-as-a-Judge》（ICML 2025 Spotlight），
作者公开了 LaTeX 源。`inputs.txt` 用 SHA-256 锁定审计读到的每个文件，
`audit_paper.py` 会重新校验（不符即 exit 2）。审计跑两条对外路径：通用检查
`verify --paper-dir`，以及两个插件 `plugins run --paper-dir`。

> **这是什么**：关于「量化论文的呈现规范」的两条观察——全文用「significant」
> 却没有任何统计检验标准；百分比表格没有不确定性。
> **这不是什么**：不是「论文结论错了」。正文引用的数字与表格一致，代码/数据可用
> 性声明也在。两条观察说的是**结论怎么呈现**，不是结论是否成立。

## 通用检查报了什么

| 类别 | 记号 | n | 含义 |
|---|---|---:|---|
| C1 / C2 / C3 / C6 | OK | 0 | **不适用**——无逐篇配置，本就如此 |
| **C4 引用卫生** | OK | 0 | 全部 cite key 命中——来自编译好的 `.bbl`（44 条），因为论文**没有 `refs.bib`** |
| C5 样本量/检验 | OK | 0 | 摘要里没有 p 值或 `d=` 可查 |
| C7 礼节性引用 | MEDIUM | 10 | C7 是粗检测器（见 `case-studies/arxiv-corpus/`），**不**记为本篇缺陷 |
| C8 统计功效 | OK | 0 | 无「significantly different」主张可查 |
| **C9 图题** | OK | 0 | 修复后为 0（首轮报了 2 条，**均为假阳性**） |
| C10 可复现性 | LOW | 3 | 只是元数据关键词检查；可用性声明本身是有的 |

两点值得点名：

* **C4 = 0 是正向结果，不是静默跳过。** 论文没有 `.bib`，只有编译好的
  `paper.bbl`。此前缺 `refs.bib` 会直接 `exit 2`；现在 `verify --paper-dir`
  能从 `.bbl`（`\bibitem{key}`）读 key，两者都没有时如实报「不适用」而不中断
  ——**所以这条检查在本篇是真的跑了，并且引文完好**。
* **C10 的三条 LOW 是粗关键词层**，不代表论文不可复现：它声明了 judge
  `temperature`（340 行）和代码/数据地址（468 行），只是没有
  「learning rate / seed / 库版本」这类字符串。

## 发现 A —— 用了「significant」却没有检验标准

`claims-significance-no-test`：**10 处 "significant/significantly"，落在 9 行**
（211、288、327、369、401、408、662、722、770），而全文**没有 p 值、bootstrap、
置换检验或显著性检验**（已核验：源码中 `p-value`、`bootstrap` 命中数均为 0）。

关键在「不齐一」：288 行（"significant computational challenges"）是普通措辞；
327 行作者**显式定义了**这个词——"We denote significant performance
advantages with \(\gg\)"——先给了论文内的非统计含义，再在 369/401/408 使用。
另一些则明显是推断性主张（408 行"exhibits a **significant** increase in
non-transitivity"）。

缺的是**一个把这个词与检验绑定的地方**。因为全文没有任何检验标准，读者无法
分辨哪些用法是统计的、哪些是本地 \(\gg\) 记号。本发现是呈现层面的观察，**没有**
声称其中哪个差异是虚假的。

## 发现 B —— 百分比表格没有不确定性

`claims-percent-table-no-uncertainty`：三张表以点估计给百分比、无不确定性标记，
而论文在别处报了区间。

| 表（行） | 内容 | 例 |
|---|---|---|
| **416** | 主相关对比表 `RRBT_cor` | Spearman 96.4%（round-robin, w. LC）vs 95.0%（AlpacaEval）；Kendall 86.3% vs 82.1%；Δ +1.4% / +4.2% |
| 827 | round-robin vs AlpacaEval | 6 个百分比 |
| 882 | 20 模型完整榜 | 40 个百分比 |

这条检查之所以触发，恰恰因为论文**有能力**报离散度：446 行图注写明
"reporting the mean correlation with a 95 % confidence interval"（2000 次试验），
754/764 行给出 \(\pm\) 与标准差。所以 416 行这张主表**比论文能给的更少信息**——
而它正是正文（451、453 行）依赖其 Δ 值的那张表。

明确说清**没坏的地方**：正文引的 Δ（无 LC +4% / +5.2%；有 LC +1.4% / +4.2%）
与表格 Δ 行完全一致。**不存在数字矛盾，缺的是区间。**

## 本次审计还暴露并修复了一处工具缺陷

首轮报 **C9 = 2**：「图（187 行）无 caption」「图（435 行）无 caption」。
这两张图**都有** caption。原因在工具不在论文：caption 用「大括号有界」正则
提取，只接受一层嵌套，而这两个 caption 嵌套两层——
`\caption{\textbf{... \textsc{Swim} ...}}` 与
`\caption{\textcolor[HTML]{2f70b8}{{Llama-3-70B}} ...}`。于是**有图题被判成无图题**。

本次提交已修复：caption 提取改为平衡括号扫描（`_c9_balanced_content`），并补
回归测试（`\textbf{...\textsc{...}}`、`{{...}}` 两种形式，以及真正未闭合的组）。
提交的 `results.json` 是修复后的运行（C9 = 0）。

## 查过但已撤回的假设

三条候选薄弱点经核验**不成立**，如实记录，避免本审计被读得比它本身更重。

1. **平局阈值敏感性**：担心非传递性结果对平局处理敏感。撤回——论文本就报了
   各变体：`4senarios_strict_tie`（660–664 行）、`4senarios_4omini`（552、586）、
   `4senarios_arena`（554、618）。
2. **正文/表格数字不一致**：担心散文里的提升与表格不符。撤回——完全一致
   （451/453 行 vs `RRBT_cor`（429 行）的 `\Delta` 行）。
3. **缺少可复现性声明**：担心没有代码/数据可用性。撤回——
   `\url{https://github.com/yix8/llm-nontransitivity}` 在 468 行，judge 配置也
   声明了（`temperature set to 0`，340 行）。

## 本审计**不**成立的推论

* 不评价论文的正确性、新颖性或可复现性，只度量两条呈现规范。
* 两个插件检查都是有明确边界的启发式：发现 A 是**文档级**（因全文没有检验标准
  而触发，不是逐句判定）；发现 B 会对**每张**无不确定性标记的百分比表触发，
  不限于主表。两者都在消息文本里写明了这一点。
* 「有区间但无检验的 significant」或「本就不需要区间的百分比表」仍可能被标记
  ——这是只读文本的机械规则要付的代价。

## 复现

```bash
curl -L -o src.tar.gz https://arxiv.org/e-print/2502.14074
mkdir -p _paper && tar -xzf src.tar.gz -C _paper

pip install -e .
pip install -e ./case-studies/arxiv-2502.14074/tmaudit_claims_plugin

python3 audit_paper.py --paper-dir _paper --archive src.tar.gz
```

`_paper/` 与 `src.tar.gz` 已 gitignore；`inputs.txt` 与 `results.json` 已提交，
无需下载即可读结论。
