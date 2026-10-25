# 上传 — 自助执行手册（v0.6.0）

本文档给你直接复制粘贴的命令。token 由你自己输入，不进对话记录。

**当前状态**：`dist/tmaudit-0.6.0-py3-none-any.whl`（103,033 B）与 `.tar.gz`（173,045 B）已构建，`twine check --strict` 双包 PASSED，工作区 429 passed / 3 skipped，wheel/sdist 内全部源文件与 `src/` 字节一致。**尚未上传任何索引。**

PyPI 现有版本只有 `0.5.0`、`0.5.1`（实测确认），`0.6.0` 未被占用。

**先决定一件事**：要不要先走 TestPyPI。
- **要**（推荐）：走 §0–§2，验证安装与功能，再走 §3。多花约 5 分钟；传错了只脏 TestPyPI。
- **不要**：直接跳 §3。PyPI 版本号不可回收。

---

## 0. 取 token

**TestPyPI**（§1–§2 用）：https://test.pypi.org/manage/account/token/
**PyPI**（§3 用）：https://pypi.org/manage/account/token/

两个站是独立账号，token 不通用。首次上传时项目尚不存在，Scope 只能选 **Entire account**；等 `tmaudit` 0.6.0 上传成功后，建议改建限定到 `tmaudit` 项目的 token（作用域更小，泄漏损失有限）。

---

## 1. 上传到 TestPyPI

```bash
cd /home/liuzewen/project-review-20261013/verify/tmaudit

/tmp/wv3/bin/python -m twine upload \
  --repository-url https://test.pypi.org/legacy/ \
  --username __token__ \
  dist/*
```

**故意不写 `--password`**：twine 会提示 `Enter your password:`，粘贴时屏幕不回显，token 不会进入 `~/.bash_history`。这比 `--password 'pypi-...'` 干净——后者会让你之后在 shell 历史里留下一串可直接盗用的凭据。

> 另一种等价的干净写法（适合不想被提示打断时）：先 `read -rs TWINE_PASSWORD` 再
> `export TWINE_PASSWORD`，twine 会自动读取这个环境变量。`read -s` 同样不回显。

**预期输出**：

```
Uploading tmaudit-0.6.0-py3-none-any.whl
Uploading tmaudit-0.6.0.tar.gz
View at:
https://test.pypi.org/project/tmaudit/0.6.0/
```

**若报错**：

| 报错 | 原因 | 处置 |
|---|---|---|
| `403 Invalid or non-existent authentication` | 用了 PyPI 的 token，不是 TestPyPI 的 | 回 §0 重新取 |
| `400 File already exists` | 该版本此前传过 | 无法覆盖。改 `pyproject.toml` 版本为 `0.6.0.post1`，重新 build 再传 |
| `SSL: CERTIFICATE_VERIFY_FAILED` | 代理/证书问题 | 见 §5，**不要**用 `--disable-ssl-verify` |

---

## 2. 从 TestPyPI 安装并验证

必须带 `--extra-index-url https://pypi.org/simple/`：TestPyPI 上的包可能缺依赖，pip 需要用主索引补齐。

```bash
rm -rf /tmp/tp-verify
/home/liuzewen/.workbuddy/binaries/python/versions/3.13.12/bin/python3 -m venv /tmp/tp-verify

/tmp/tp-verify/bin/pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  "tmaudit==0.6.0"
```

**必须确认是从 test.pypi.org 下载的**，输出里应出现 `test-files.pythonhosted.org`。若显示 `files.pythonhosted.org`（无 `test-` 前缀），说明装到了正式 PyPI 的旧版，**不是**你要验的东西。

### 五项验证

```bash
# 1. 版本
/tmp/tp-verify/bin/tmaudit --version
# 期望: tmaudit 0.6.0

# 2. yaml 随包（发布级缺陷的回归检查）
/tmp/tp-verify/bin/python -c "
import pathlib, tmaudit
p = pathlib.Path(tmaudit.__file__).parent
print('yaml:', sorted(x.name for x in (p/'detector_config').glob('*.yaml')))
"
# 期望: yaml: ['detector.yaml']

# 3. admission
/tmp/tp-verify/bin/tmaudit admission --gain 7.3 --tasks 89
# 期望: [NOT CERTIFIED] gain=+7.30pp  upper=+32.10pp  m=89  K=5  T=10  delta=0.05  eta=0.00pp
#       note: certifying this gain would need tasks m >= 2,593

# 4. list 对缺失路径的处理（v0.6.0 新增）
/tmp/tp-verify/bin/tmaudit list
# 期望: 5 行都带 (missing)，末尾有 "5 of 5 rulepack path(s) do not exist"
#       以及 TMAUDIT_RESEARCH_DIR 和 --paper-dir 两条提示
# 若显示 (missing) 但无末尾说明，说明装到了旧包

# 5. 外部论文端到端（0.6.0 的核心能力）
mkdir -p /tmp/tp-ext
printf '\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nCode at \\url{https://github.com/x/y}.\n\\end{document}\n' > /tmp/tp-ext/paper.tex
/tmp/tp-verify/bin/tmaudit verify --paper-dir /tmp/tp-ext
# 期望: Source 指向 paper.tex（不是 main.tex），TOTAL 行给出 findings，rc=0
```

第 5 项特意用 `paper.tex` 而非 `main.tex`，验证运行时自动探测根文件——这是合并进来的远端能力。

---

## 3. 上传到正式 PyPI（不可逆）

**先确认 §2 全部通过。** 只有一步：

```bash
cd /home/liuzewen/project-review-20261013/verify/tmaudit
ls -l dist/          # 确认只有 0.6.0 的两个文件，没有别的版本残留

/tmp/wv3/bin/python -m twine upload \
  --username __token__ \
  dist/*
```

不带 `--repository-url` 时 twine 默认走 `https://upload.pypi.org/legacy/`。同样故意省略 `--password`，让它交互式询问。

**不可逆**：`0.6.0` 一经上传无法删除或复用（PyPI 不允许重传同版本号），只能发 `0.6.1`。上传前这一刻是最后的检查点。

---

## 4. 上线后核对

```bash
# 元数据传播约需 1 分钟
curl -s https://pypi.org/pypi/tmaudit/json | \
  /tmp/wv3/bin/python -c "import json,sys; d=json.load(sys.stdin); print(d['info']['version']); print(sorted(d['releases']))"
# 期望: 0.6.0
#       ['0.5.0', '0.5.1', '0.6.0']
```

页面：https://pypi.org/project/tmaudit/0.6.0/

再跑一次真实安装，确认用户路径可用：

```bash
rm -rf /tmp/pypi-verify
/home/liuzewen/.workbuddy/binaries/python/versions/3.13.12/bin/python3 -m venv /tmp/pypi-verify
/tmp/pypi-verify/bin/pip install tmaudit==0.6.0
/tmp/pypi-verify/bin/tmaudit --version
```

---

## 5. 已知坑

**twine 7 移除了 `--repository`**（不带 url 的那个）。本仓 twine 为 7.0.0，若见到 `unrecognized arguments: --repository`，就是用了旧写法，改成 `--repository-url`。

**SSL 证书错误**：若 `CERTIFICATE_VERIFY_FAILED`，先看是否走了代理：

```bash
echo $HTTPS_PROXY
```

用了自签证书代理的话，用 `--cert` 指向 CA bundle，或临时 unset 代理。**不要用 `--disable-ssl-verify`**——那样 token 会明文穿过不受信的 TLS 层。

**`400 File already exists` 不可绕过**。PyPI 与 TestPyPI 都拒绝覆盖已存在的文件名，改版本号重发是唯一出路。

---

## 6. 上传后还差什么

- **git tag 未打**，本地提交未 push（`behind=0`、`ahead=4`）。远端 `github.com/aidless/tmaudit` 已存在且可访问（实测 200），所以 PyPI 页面不会链到 404。
- **`Author-email` 是 `aidless@example.com`**。`example.com` 是保留占位域名，真实邮件发不过去；0.5.1 发布时用的也是这个值，属既有状态。若要改，改 `pyproject.toml:13` 后重新 build 再上传（版本号需升到 0.6.1，因为 0.6.0 已不可覆写）。
- **0.5.2 未单独发布**。CHANGELOG 已标注「not yet on PyPI; publishing alongside v0.6.0」，0.6.0 上线后该标注即成立。

把 §1 或 §3 的输出（失败则贴报错原文）发我，我据此更新 `RELEASE_CHECKLIST.md` 并落记忆。
