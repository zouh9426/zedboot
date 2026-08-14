#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zedboot 装后机械校验工具 (verify.py)
====================================

用途
----
zedboot 的「装后机械校验」工具，与 scripts/audit.py 的「装前只读审计」互补：
在 zedboot 按 SKILL.md 完成开局安装（init）或旧项目改造（adopt）之后，
逐项机械核对安装承诺是否兑现：
  1. 管理文件齐备（init-workflow.md 第 1 步）
  2. 占位符替换干净（info-collection.md 存储纪律 / 填写约定）
  3. .gitignore 含 .env* / data/ / backups/ / docs/private/ 四项（条目存在 +
     git check-ignore 生效语义双层判定，.env* 覆盖全部 .env 变体）；.env 与
     docs/private/ 未被 git 跟踪
     （init-workflow.md 第 1 步 Git 条目）
  4. pre-push 隐私闸门已安装且可执行（含 core.hooksPath 影响探测）
  5. 部署产物（仅可部署项目；init-workflow.md 第 2 步）
  6. 入库文件私钥格式头快扫（SKILL.md 硬性规则 3 秘密边界）
输出逐项 PASS / FAIL / WARN / SKIP 中文报告；存在任何 FAIL 则 exit 1，否则 exit 0。

用法
----
    python3 verify.py [项目路径] [--json]
    python3 verify.py --help

    - 项目路径 : 要校验的项目目录，默认当前目录。
    - --json   : 输出结构化 JSON（供 AI 读取）；默认输出中文文本报告（供人读）。

只读承诺
--------
本脚本是绝对只读的，绝不往目标项目写任何东西：
- 不创建 / 修改 / 删除目标项目内任何文件；
- 不执行任何 git 写操作；
- 仅通过 subprocess 执行只读 git 命令（rev-parse / config --get / ls-files），
  且每条 git 命令带 10 秒超时与异常兜底。

兼容性
------
纯 Python 3 标准库，兼容 Python 3.8+。

边界约定（与 audit.py 同一口径：无法确认的项一律 WARN / SKIP 并说明原因，绝不臆断）
----------------------------------------------------------------------------------
- 非 git 仓库 / git 不可用：无「入库文件」概念，占位符与私钥头检查降级为工作区
  文本扫描（跳过依赖/构建噪音目录与 docs/private/），无命中时标 WARN（扫描范围
  不完整）而非 PASS，有命中仍 FAIL；.env 跟踪状态与 pre-push 钩子检查整体 SKIP。
- 嵌套仓库（目录自身无 .git、被外层仓库包含）：按非仓库处理，git 结论不可信。
- 项目模式判定：读取 PROJECT_INDEX.md → PROJECT_STATE.md → AGENTS.md 的
  「项目模式」行；三处皆无/为空 → 部署产物检查 SKIP（不臆断），判定本身标 WARN。
- 非 UTF-8 文本：非法字节替换后扫描，不中断；二进制（头部含 NUL）文件跳过。
- 单文件扫描上限 2MB（只读头部），超过时在报告中标注。
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys

GIT_TIMEOUT = 10            # 秒；每条 git 命令的超时上限
SCAN_FILE_LIMIT = 2 * 1024 * 1024  # 单文件扫描上限：只读前 2MB，防大文件卡死
TEXT_HEAD = 4096            # 二进制判定：头部含 NUL 字节视为二进制
WORKSPACE_SCAN_MAX_FILES = 500  # 工作区降级扫描的文件数上限

# 工作区降级扫描时跳过的噪音目录（依赖/构建产物/IDE）
_WORKSPACE_SKIP_DIRS = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", "target", ".idea", ".vscode",
})

# ---------------------------------------------------------------------------
# 机械判定口径（与 SKILL.md / audit.py 对齐）
# ---------------------------------------------------------------------------
# 管理文件清单（init-workflow.md 第 1 步承诺安装的 10 项；与 audit.py 正典十项一致）
MANAGEMENT_DOCS = (
    "README.md",
    "AGENTS.md",
    "CHANGELOG.md",
    "docs/README.md",
    "docs/project/PROJECT_RULES.md",
    "docs/project/PROJECT_INDEX.md",
    "docs/project/PROJECT_STATE.md",
    "docs/project/TODO.md",
    "docs/project/DECISION_LOG.md",
    "archive/README.md",
)

# 中文占位符残留：字面量 <项目名> 或任何 <...> 形态且内部含中文字符的占位符。
# 对应 info-collection.md 存储纪律：可推导/业务中文占位符（<项目名>/<域名>/<端口> 等）
# 安装时必须全文替换（含代码块内的命令示例），不留残留；英文大写隔离占位符
# （<PRODUCTION_SERVER_IP>/<DEPLOY_USER>/<DEPLOY_KEY> 等）属设计内占位，
# 入库文档只写占位符 + 指向 docs/private/ops.md 的注记，本检查不判。
PLACEHOLDER_RE = re.compile(r"<[^<>\n]*[\u4e00-\u9fff][^<>\n]*>")
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")

# 「项目模式」行（中/英文冒号均可；值与 audit.py 的 ops 键解析同口径）
MODE_LINE_RE = re.compile(r"^\s*[-*]?\s*项目模式\s*[：:]\s*(.+?)\s*$")

# 项目模式判定来源：PROJECT_INDEX → PROJECT_STATE → AGENTS
MODE_SOURCES = (
    "docs/project/PROJECT_INDEX.md",
    "docs/project/PROJECT_STATE.md",
    "AGENTS.md",
)


# ---------------------------------------------------------------------------
# 基础工具函数（沿用 audit.py 口径）
# ---------------------------------------------------------------------------
def _clean(s):
    """清洗字符串用于展示/JSON：替换非法字节、去掉控制字符，绝不抛异常。"""
    if s is None:
        return None
    try:
        s = s.encode("utf-8", "replace").decode("utf-8")
    except UnicodeError:
        s = s.encode("ascii", "replace").decode("ascii")
    out = []
    for ch in s:
        if ch in ("\t", "\n"):
            out.append(ch)
        elif ord(ch) < 32 or ord(ch) == 0x7F:
            continue
        else:
            out.append(ch)
    return "".join(out)


def _list_dir(path):
    try:
        return os.listdir(path)
    except OSError:
        return None


def _read_text(path):
    """读取 UTF-8 文本；非 UTF-8 或不可读返回 None。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (UnicodeDecodeError, OSError):
        return None


def _find_file(root, *rel_parts):
    """大小写不敏感地定位文件；中间目录必须是目录、末级必须是文件。
    返回磁盘上的实际相对路径（可能大小写不同），找不到返回 None。"""
    cur = root
    acc = []
    last = len(rel_parts) - 1
    for i, part in enumerate(rel_parts):
        entries = _list_dir(cur)
        if entries is None:
            return None
        low = part.lower()
        match = None
        for e in entries:
            if e.lower() == low:
                match = e
                break
        if match is None:
            return None
        acc.append(match)
        cur = os.path.join(cur, match)
        if i < last and not os.path.isdir(cur):
            return None
    if not os.path.isfile(cur):
        return None
    return os.path.join(*acc)


def _read_text_head(path, limit):
    """读文本文件头部：先读 4KB 判二进制（含 NUL 视为二进制跳过），
    文本则读满 limit 字节并以 UTF-8 解码（无效字节替换为 U+FFFD，绝不抛异常）。
    不可读 / 二进制返回 None。"""
    try:
        with open(path, "rb") as f:
            head = f.read(TEXT_HEAD)
    except OSError:
        return None
    if b"\x00" in head:
        return None
    try:
        with open(path, "rb") as f:
            raw = f.read(limit)
    except OSError:
        return None
    return raw.decode("utf-8", "replace")


def _file_exceeds(path, limit):
    """文件大小是否超过扫描上限（无法获取大小时视为未超）。"""
    try:
        return os.path.getsize(path) > limit
    except OSError:
        return False


def _run_git(root, args):
    """执行一条只读 git 命令。
    返回 (ok, stdout, stderr, error_note)：
    - error_note 非 None 表示 git 不可用 / 超时 / 其他异常；
    - error_note 为 None 但 ok=False 表示 git 正常执行但命令以非零退出。"""
    cmd = ["git"] + args
    try:
        p = subprocess.run(
            cmd, cwd=root, capture_output=True, text=True,
            errors="replace", timeout=GIT_TIMEOUT,
        )
        return p.returncode == 0, p.stdout, p.stderr, None
    except subprocess.TimeoutExpired:
        return False, "", "", "git 命令超时(>%ds)，交由 AI 判断" % GIT_TIMEOUT
    except FileNotFoundError:
        return False, "", "", "系统未安装 git，交由 AI 判断"
    except OSError as e:
        return False, "", "", "git 命令执行失败：%s，交由 AI 判断" % e


# ---------------------------------------------------------------------------
# Git 语境与扫描范围
# ---------------------------------------------------------------------------
def _git_context(root):
    """判定目标目录的 git 语义。返回 (status, note)：
    status 为 repo / not_repo / git_error；note 仅在非正常情形给出。"""
    ok, out, err, note = _run_git(root, ["rev-parse", "--is-inside-work-tree"])
    if note is not None:
        return "git_error", note
    if not (ok and out.strip() == "true"):
        definitely_not_repo = (
            ok and out.strip() == "false"
        ) or (not ok and "not a git repository" in (err or "").lower())
        if definitely_not_repo:
            return "not_repo", "非 git 仓库"
        return "git_error", "git rev-parse 异常退出，无法确定是否仓库"
    # 嵌套仓库边界：目录自身无 .git、被外层仓库包含时，git 命令会静默命中
    # 外层仓库（跟踪清单与状态不代表本目录）——按非仓库处理
    ok2, out2, err2, note2 = _run_git(root, ["rev-parse", "--show-toplevel"])
    if ok2 and out2.strip() and \
            os.path.realpath(out2.strip()) != os.path.realpath(root):
        return "not_repo", "目录自身无 git 仓库（被外层仓库包含）"
    return "repo", None


def _tracked_files(root):
    """git 仓库：返回跟踪文件相对路径列表；非仓库/命令失败返回 None。"""
    ok, out, err, note = _run_git(root, ["ls-files"])
    if note is not None or not ok:
        return None
    return [l.strip() for l in out.splitlines() if l.strip()]


def _scan_committed_text(root, git_status, git_note, tracked):
    """单次扫描入库/工作区文本文件，收集「中文占位符残留」与「私钥格式头」命中。

    git 仓库：扫「下次 commit 会进去的全部文件」= 已跟踪 + 未跟踪但未被
    gitignore 排除（`git ls-files -co --exclude-standard`）——zedboot 流程里
    verify 跑在装后 commit 之前，init 第 2/3 步与 adopt C 步新落盘的文件此时
    很可能尚未 git add，只扫已跟踪会漏掉最该查的一批（跳过 .env 与
    .gitignore，口径同 audit.py）。
    非仓库/嵌套/git 不可用：无入库文件概念，降级扫描工作区文本文件
    （跳过依赖/构建噪音目录与 docs/private/——后者按 SKILL.md 契约永不入库），
    无命中标 WARN（扫描范围不完整）而非 PASS，有命中仍 FAIL。

    返回 dict：
      scope              'tracked' | 'workspace_degraded'
      note               降级原因说明（tracked 时为 None）
      scanned_count      实际扫描文本文件数
      untracked_count    扫描范围内未跟踪（且未被忽略）的文件数
      truncated          超过 2MB 仅扫头部的文件列表
      placeholder_hits   {rel: [(行号, 命中文本), ...]}
      key_hits           {rel: [行号, ...]}
    """
    result = {
        "scope": "tracked",
        "note": None,
        "scanned_count": 0,
        "untracked_count": 0,
        "truncated": [],
        "placeholder_hits": {},
        "key_hits": {},
    }

    if git_status == "repo" and tracked is not None:
        ok, out, err, note = _run_git(
            root, ["ls-files", "-co", "--exclude-standard"])
        if note is None and ok:
            all_files = [l.strip() for l in out.splitlines() if l.strip()]
            tracked_set = set(tracked)
            result["untracked_count"] = len(
                [f for f in all_files if f not in tracked_set])
            files = [(rel, os.path.join(root, rel)) for rel in all_files]
        else:
            # 命令失败时回退为仅已跟踪，不臆断
            result["note"] = ("ls-files -co 失败，回退为仅扫描已跟踪文件"
                              "（未跟踪文件未纳入）")
            files = [(rel, os.path.join(root, rel)) for rel in tracked]
    else:
        result["scope"] = "workspace_degraded"
        if git_status == "not_repo":
            result["note"] = git_note or "非 git 仓库"
        elif git_status == "git_error":
            result["note"] = git_note or "git 不可用"
        else:
            result["note"] = "git ls-files 执行失败"
        result["note"] += ("：降级扫描工作区文本文件（跳过依赖/构建噪音目录与 "
                           "docs/private/，入库语义不适用）")
        files = []
        stop = False
        for dirpath, dirnames, filenames in os.walk(root):
            if stop:
                break
            dirnames[:] = [d for d in dirnames if d not in _WORKSPACE_SKIP_DIRS]
            rel_dir = os.path.relpath(dirpath, root)
            if rel_dir == "docs" and "private" in dirnames:
                dirnames.remove("private")
            for fn in sorted(filenames):
                if len(files) >= WORKSPACE_SCAN_MAX_FILES:
                    stop = True
                    break
                if _is_env_file(fn) or fn == ".gitignore":
                    continue
                rel = fn if rel_dir == "." else os.path.join(rel_dir, fn)
                files.append((rel.replace(os.sep, "/"), os.path.join(dirpath, fn)))

    for rel, path in files:
        base = os.path.basename(rel)
        if _is_env_file(base) or base == ".gitignore":
            continue  # .env* 全家族永不入库（且内容可能含任意秘密）；.gitignore 无占位/私钥语义
        if _file_exceeds(path, SCAN_FILE_LIMIT):
            result["truncated"].append(rel)
        text = _read_text_head(path, SCAN_FILE_LIMIT)
        if text is None:
            continue  # 不可读或二进制，跳过
        result["scanned_count"] += 1
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in PLACEHOLDER_RE.finditer(line):
                result["placeholder_hits"].setdefault(rel, []).append(
                    (lineno, m.group(0)))
            if PRIVATE_KEY_RE.search(line):
                result["key_hits"].setdefault(rel, []).append(lineno)
    return result


# ---------------------------------------------------------------------------
# 检查项构造
# ---------------------------------------------------------------------------
def _mk(cid, name, status, detail, section, items=None):
    return {
        "id": cid, "name": name, "status": status, "detail": detail,
        "section": section, "items": items or [],
    }


def _check_management_docs(root):
    """1. 管理文件齐备（init-workflow.md 第 1 步）。缺失即 FAIL。"""
    checks = []
    for rel in MANAGEMENT_DOCS:
        actual = _find_file(root, *rel.split("/"))
        if actual is not None:
            detail = "存在"
            if actual != rel:
                detail += "（磁盘实际路径 %s）" % actual
            checks.append(_mk("mgmt:" + rel, "管理文件 %s" % rel, "PASS",
                              detail, "management"))
        else:
            checks.append(_mk("mgmt:" + rel, "管理文件 %s" % rel, "FAIL",
                              "缺失（init-workflow.md 第 1 步承诺安装）", "management"))
    return checks


def _check_placeholder(scan):
    """2. 占位符替换干净：入库文本文件无 <项目名> / 中文占位符残留。"""
    hits = scan["placeholder_hits"]
    total = sum(len(v) for v in hits.values())
    if hits:
        items = []
        for rel in sorted(hits):
            for lineno, match in hits[rel]:
                items.append({"file": rel, "line": lineno, "match": match})
        items = items[:50]
        detail = ("发现中文占位符残留 %d 处（info-collection.md 存储纪律：可推导/业务中文"
                  "占位符全文替换不留残留，含代码块内示例）" % total)
        if scan["scope"] != "tracked":
            detail += "；扫描范围受限（%s）" % scan["note"]
        return _mk("placeholder", "占位符替换干净（<项目名> 等中文占位符）",
                   "FAIL", detail, "placeholder", items=items)
    if scan["scope"] != "tracked":
        return _mk("placeholder", "占位符替换干净（<项目名> 等中文占位符）",
                   "WARN",
                   "未发现中文占位符残留，但扫描范围受限（%s）" % scan["note"],
                   "placeholder")
    return _mk("placeholder", "占位符替换干净（<项目名> 等中文占位符）", "PASS",
               "入库文本文件未发现中文占位符残留（共扫描 %d 个文本文件）"
               % scan["scanned_count"], "placeholder")


def _is_env_file(name):
    """是否 .env* 环境文件（.env 本体与 .env.<后缀> 变体；example/sample/template 为例外名，不算敏感）。
    与 audit.py 同名助手口径一致。"""
    if name in (".env.example", ".env.sample", ".env.template"):
        return False
    return name == ".env" or name.startswith(".env.")


def _gitignore_covers(pattern, target):
    """gitignore 行是否覆盖 target（target 如 .env / data / backups / docs/private）。

    语义：无斜杠的模式匹配任意层级同名项；含斜杠的模式锚定仓库根比较全路径。
    （init-workflow.md 第 1 步要求 .gitignore 含 .env*、data/、backups/、
    docs/private/ 四项。）"""
    p = pattern.strip()
    if not p or p.startswith("#") or p.startswith("!"):
        return False
    p = p.lstrip("/").rstrip("/")
    if p.startswith("**/"):
        p = p[3:]
    if not p:
        return False
    if target == ".env":
        # 收紧口径：只接受能覆盖全部 .env* 变体的模式。`/.env*`、`**/.env*`
        # 已在上方归一化为 `.env*`（等效写法），gitignore 语义里 `.env*`
        # 同时护住 .env / .env.local / .env.production 等全部变体；字面
        # `.env` 只护单文件、`.env.*` 不护 .env 本体，都不再接受——防止
        # 只写单文件而漏掉变体（init-workflow.md 第 1 步 Git 条目口径）。
        return p == ".env*"
    if "/" in p:
        return p == target
    return p == target.rsplit("/", 1)[-1]


# .gitignore 必须覆盖的四项（init-workflow.md 第 1 步 Git 条目）
GITIGNORE_REQUIRED = (".env", "data", "backups", "docs/private")


def _check_gitignore_rules(root):
    """3a. .gitignore 含 .env* / data/ / backups/ / docs/private/ 四项。"""
    gi = _find_file(root, ".gitignore")
    if gi is None:
        return [_mk("gitignore_rules", ".gitignore 必含四项", "FAIL",
                    ".gitignore 不存在（要求含 %s）"
                    % "、".join(GITIGNORE_REQUIRED), "git_privacy")]
    text = _read_text(os.path.join(root, gi))
    if text is None:
        return [_mk("gitignore_rules", ".gitignore 必含四项", "WARN",
                    ".gitignore 非 UTF-8 或不可读，无法确认忽略条目", "git_privacy")]
    lines = text.splitlines()
    checks = []
    for target in GITIGNORE_REQUIRED:
        label = ".env*" if target == ".env" else target + "/"
        if any(_gitignore_covers(line, target) for line in lines):
            checks.append(_mk("gitignore:" + target, ".gitignore 含 %s 条目" % label,
                              "PASS", "找到条目", "git_privacy"))
        else:
            checks.append(_mk("gitignore:" + target, ".gitignore 含 %s 条目" % label,
                              "FAIL", "未找到 %s 条目" % label, "git_privacy"))
    return checks


# 生效语义探测用的哨兵路径（check-ignore 按路径名文本匹配，不要求存在；
# 取不可能被业务规则单独反向放行的名字）。.env* 变体各探一个代表：
# 变体是 .env* 规则要护住的第二现场，只探 .env 会漏掉 .env.local 等
# 被单独反向放行/未覆盖的情形；.env.example 类例外名不入探针（gitignore
# 里常写 !.env.example 放行模板，属刻意设计，不判失效——探针不探它即可）。
_GITIGNORE_PROBES = (
    (".env", ".env"),
    (".env.local", ".env.local"),
    (".env.production", ".env.production"),
    ("data/", "data/.zedboot-probe"),
    ("backups/", "backups/.zedboot-probe"),
    ("docs/private/", "docs/private/.zedboot-probe"),
)


def _check_gitignore_effective(root, git_status, git_note):
    """3b. .gitignore 四项的「生效语义」（git check-ignore --no-index 判哨兵路径）。

    条目存在 ≠ 最终生效——反向规则（如 `.env` 后写 `!.env`）会让防护静默失效，
    自写解析器不可能完整复刻 gitignore 语义（顺序/取反/层级），交给 git 自己判。"""
    if git_status != "repo":
        return _mk("gitignore_effective", ".gitignore 四项生效语义", "SKIP",
                   "非 git 仓库（%s），生效语义不适用" % (git_note or "git 不可用"),
                   "git_privacy")
    not_ignored = []
    errors = []
    for label, probe in _GITIGNORE_PROBES:
        ok, out, err, note = _run_git(
            root, ["check-ignore", "-q", "--no-index", "--", probe])
        if note is not None or (not ok and (err or "").strip()):
            errors.append(label)  # git 不可用 / 命令异常（exit>1）
        elif not ok:
            not_ignored.append(label)  # exit 1 = 实际未被忽略
    if errors:
        return _mk("gitignore_effective", ".gitignore 四项生效语义", "WARN",
                   "git check-ignore 异常，无法判定：%s" % "、".join(errors),
                   "git_privacy")
    if not_ignored:
        return _mk("gitignore_effective", ".gitignore 四项生效语义", "FAIL",
                   "条目存在但未生效（存在反向规则或覆盖问题），实际未被忽略：%s"
                   % "、".join(not_ignored), "git_privacy")
    return _mk("gitignore_effective", ".gitignore 四项生效语义", "PASS",
               "四项哨兵路径经 git check-ignore 确认均被实际忽略", "git_privacy")


def _check_private_not_tracked(root, git_status, git_note):
    """3d. docs/private/ 未被 git 跟踪（ops.md / backup-manifest.conf 含运维真实值，
    跟踪即泄露事故；git ls-files 判定，命令带超时）。"""
    if git_status != "repo":
        return _mk("private_not_tracked", "docs/private/ 未被 git 跟踪", "SKIP",
                   "非 git 仓库（%s），无法判定跟踪状态" % (git_note or "git 不可用"),
                   "git_privacy")
    ok, out, err, note = _run_git(
        root, ["ls-files", "--", "docs/private"])
    if note is not None or not ok:
        return _mk("private_not_tracked", "docs/private/ 未被 git 跟踪", "WARN",
                   "git 命令失败，无法判定：%s" % (note or err), "git_privacy")
    hits = [l.strip() for l in out.splitlines() if l.strip()]
    if hits:
        return _mk("private_not_tracked", "docs/private/ 未被 git 跟踪", "FAIL",
                   "docs/private/ 下 %d 个文件已被 git 跟踪（运维真实值入库风险；"
                   "adopt-workflow.md C 步要求 git rm --cached + .gitignore 覆盖）：%s"
                   % (len(hits), "、".join(hits[:5])), "git_privacy")
    return _mk("private_not_tracked", "docs/private/ 未被 git 跟踪", "PASS",
               "docs/private/ 无被跟踪文件", "git_privacy")


def _check_env_tracked(root, git_status, git_note):
    """3c. .env 未被 git 跟踪（git ls-files 判定，命令带超时）。"""
    if git_status != "repo":
        return _mk("env_not_tracked", ".env 未被 git 跟踪", "SKIP",
                   "非 git 仓库（%s），无法判定跟踪状态" % (git_note or "git 不可用"),
                   "git_privacy")
    env = _find_file(root, ".env")
    if env is None:
        return _mk("env_not_tracked", ".env 未被 git 跟踪", "PASS",
                   ".env 未创建（无跟踪风险）", "git_privacy")
    ok, out, err, note = _run_git(root, ["ls-files", "--error-unmatch", "--", ".env"])
    if note is not None:
        return _mk("env_not_tracked", ".env 未被 git 跟踪", "WARN",
                   "git 命令失败，无法判定：%s" % note, "git_privacy")
    if ok:
        return _mk("env_not_tracked", ".env 未被 git 跟踪", "FAIL",
                   ".env 已被 git 跟踪（敏感文件入库风险；adopt-workflow.md C 步 要求 "
                   "git rm --cached + .gitignore 覆盖）", "git_privacy")
    return _mk("env_not_tracked", ".env 未被 git 跟踪", "PASS",
               ".env 存在但未被 git 跟踪", "git_privacy")


def _check_pre_push_hook(root, git_status, git_note):
    """4. pre-push 隐私闸门已安装且可执行（含 core.hooksPath 影响探测）。"""
    if git_status != "repo":
        return _mk("pre_push_hook", "pre-push 隐私闸门（.git/hooks/pre-push）",
                   "SKIP", "非 git 仓库（%s），钩子不适用" % (git_note or "git 不可用"),
                   "git_privacy")
    ok, out, err, note = _run_git(root, ["config", "--get", "core.hooksPath"])
    if note is not None:
        return _mk("pre_push_hook", "pre-push 隐私闸门（.git/hooks/pre-push）",
                   "WARN", "git config 失败，无法确认 core.hooksPath：%s" % note,
                   "git_privacy")
    hooks_path = out.strip()
    if hooks_path:
        return _mk("pre_push_hook", "pre-push 隐私闸门（.git/hooks/pre-push）",
                   "WARN",
                   "core.hooksPath=%s 非空：.git/hooks 会被整体忽略；无法确认该路径"
                   "下全局钩子是否链式调用项目级闸门（init-workflow.md 第 1 步口径），"
                   "需人工确认" % hooks_path, "git_privacy")
    hook = os.path.join(root, ".git", "hooks", "pre-push")
    if not os.path.exists(hook):
        return _mk("pre_push_hook", "pre-push 隐私闸门（.git/hooks/pre-push）",
                   "FAIL",
                   "未安装：.git/hooks/pre-push 不存在（init-workflow.md 要求复制 "
                   "assets/hooks/pre-push.tmpl 并 chmod +x）", "git_privacy")
    if not os.access(hook, os.X_OK):
        return _mk("pre_push_hook", "pre-push 隐私闸门（.git/hooks/pre-push）",
                   "FAIL", "已安装但不可执行（init-workflow.md 要求 chmod +x）",
                   "git_privacy")
    return _mk("pre_push_hook", "pre-push 隐私闸门（.git/hooks/pre-push）",
               "PASS", ".git/hooks/pre-push 存在且可执行，core.hooksPath 未设置",
               "git_privacy")


def _classify_mode(value):
    """按 SKILL.md 模式口径分类：可部署/混合 → deployable；静态 → static；
    无部署 → no_deploy；其余 → unknown（不臆断）。"""
    if "无部署" in value:
        return "no_deploy"
    if "静态" in value:
        return "static"
    if "可部署" in value or "混合" in value:
        return "deployable"
    return "unknown"


def _detect_project_mode(root):
    """读取 PROJECT_INDEX → PROJECT_STATE → AGENTS 的「项目模式」行。"""
    for rel in MODE_SOURCES:
        f = _find_file(root, *rel.split("/"))
        if f is None:
            continue
        text = _read_text(os.path.join(root, f))
        if text is None:
            continue
        for line in text.splitlines():
            m = MODE_LINE_RE.match(line.strip())
            if not m:
                continue
            value = m.group(1).strip().rstrip("。，")
            if not value:
                continue
            return {"mode": _classify_mode(value), "value": value,
                    "source": rel}
    return {"mode": "unknown", "value": None, "source": None}


def _find_compose(root):
    for n in ("docker-compose.yml", "docker-compose.yaml",
              "compose.yml", "compose.yaml"):
        f = _find_file(root, n)
        if f is not None:
            return f
    return None


def _find_dockerfile(root):
    entries = _list_dir(root) or []
    hits = sorted(
        e for e in entries
        if e.startswith("Dockerfile") and os.path.isfile(os.path.join(root, e))
    )
    return hits[0] if hits else None


def _file_check(cid, name, label, root, section):
    """按相对路径（大小写不敏感）查文件存在性：存在 PASS，缺失 FAIL。"""
    f = _find_file(root, *name.split("/"))
    if f is not None:
        detail = "存在"
        if f != name:
            detail += "（磁盘实际路径 %s）" % f
        return _mk(cid, label, "PASS", detail, section)
    return _mk(cid, label, "FAIL", "缺失（%s）" % name, section)


def _build_deploy_checks(root, mode_info):
    """5. 部署产物（仅可部署项目；init-workflow.md 第 2 步）。"""
    mode = mode_info["mode"]
    if mode == "unknown":
        return [_mk("project_mode", "项目模式判定", "WARN",
                    "无法确认：PROJECT_INDEX / PROJECT_STATE / AGENTS 均未登记"
                    "「项目模式」，部署产物检查跳过（不臆断）", "deploy"),
                _mk("deploy:skip", "部署产物检查", "SKIP",
                    "项目模式无法确认，按 SKILL.md 无法确定应装哪些部署产物，跳过",
                    "deploy")]
    if mode == "no_deploy":
        return [_mk("project_mode", "项目模式判定", "PASS",
                    "项目模式=%s（来源 %s）：无部署交付项目，按 SKILL.md 不生成"
                    "部署产物" % (mode_info["value"], mode_info["source"]), "deploy"),
                _mk("deploy:skip", "部署产物检查", "SKIP",
                    "无部署交付项目，按 init-workflow.md 第 2 步不装部署体系，跳过",
                    "deploy")]

    # 可部署：判定静态站（无容器）还是容器栈风味
    static = (mode == "static")
    if not static:
        static = _find_file(root, "deploy-rsync-static.sh") is not None
    if not static:
        doc = _find_file(root, "docs", "guides", "deployment.md")
        if doc is not None:
            t = _read_text(os.path.join(root, doc))
            if t is not None and "静态站" in t:
                static = True
    mode_info["flavor"] = "static" if static else "container"

    flavor_label = "静态站（无容器）" if static else "容器栈"
    checks = [_mk("project_mode", "项目模式判定", "PASS",
                  "项目模式=%s（来源 %s），按 %s 校验部署产物"
                  % (mode_info["value"], mode_info["source"], flavor_label),
                  "deploy")]
    checks.append(_file_check(
        "deploy:deployment_doc", "docs/guides/deployment.md",
        "部署产物: 部署文档 docs/guides/deployment.md（入库）", root, "deploy"))
    checks.append(_file_check(
        "deploy:ops_md", "docs/private/ops.md",
        "部署产物: 本地运维文档 docs/private/ops.md（gitignore，永不入库）",
        root, "deploy"))
    rsync = "deploy-rsync-static.sh" if static else "deploy-rsync.sh"
    checks.append(_file_check(
        "deploy:rsync_script", rsync,
        "部署产物: 部署脚本 %s（init-workflow.md 要求 chmod +x）" % rsync, root, "deploy"))
    checks.append(_file_check(
        "deploy:backup_manifest", "docs/private/backup-manifest.conf",
        "部署产物: 备份清单 docs/private/backup-manifest.conf（gitignore，不入库）",
        root, "deploy"))
    # deploy.env：部署五事实（机器真源，pre-push 闸门与 audit.py 读取服务器账号），
    # 只查存在不读内容；缺失 FAIL 并指引模板 assets/project/deploy.env.tmpl
    env_actual = _find_file(root, "docs", "private", "deploy.env")
    if env_actual is not None:
        detail = "存在"
        if env_actual != "docs/private/deploy.env":
            detail += "（磁盘实际路径 %s）" % env_actual
        checks.append(_mk("deploy:deploy_env",
                          "部署产物: 部署五事实 docs/private/deploy.env（gitignore，不入库）",
                          "PASS", detail, "deploy"))
    else:
        checks.append(_mk("deploy:deploy_env",
                          "部署产物: 部署五事实 docs/private/deploy.env（gitignore，不入库）",
                          "FAIL",
                          "缺失（docs/private/deploy.env；按 assets/project/deploy.env.tmpl "
                          "补齐部署五事实：PROJECT_NAME / DEPLOY_USER / REMOTE_DIR / "
                          "SERVER_IP / DEPLOY_KEY）", "deploy"))

    if static:
        checks.append(_mk(
            "deploy:container_skip", "部署产物: 容器件", "SKIP",
            "纯静态站（无容器）：不装 Dockerfile / docker-compose / "
            "docker-entrypoint / .dockerignore / backup.sh / .env.example",
            "deploy"))
    else:
        compose = _find_compose(root)
        if compose is not None:
            detail = "存在"
            if compose not in ("docker-compose.yml", "docker-compose.yaml",
                               "compose.yml", "compose.yaml"):
                detail += "（磁盘实际路径 %s）" % compose
            checks.append(_mk("deploy:compose", "部署产物: docker-compose.yml",
                              "PASS", detail, "deploy"))
        else:
            checks.append(_mk("deploy:compose", "部署产物: docker-compose.yml",
                              "FAIL", "缺失（docker-compose.yml / compose.yaml）",
                              "deploy"))
        dockerfile = _find_dockerfile(root)
        if dockerfile is not None:
            detail = "存在"
            if dockerfile != "Dockerfile":
                detail += "（磁盘实际路径 %s）" % dockerfile
            checks.append(_mk("deploy:dockerfile", "部署产物: Dockerfile",
                              "PASS", detail, "deploy"))
        else:
            checks.append(_mk("deploy:dockerfile", "部署产物: Dockerfile",
                              "FAIL", "缺失（Dockerfile / Dockerfile.*）", "deploy"))
        dockerfile_text = (_read_text(os.path.join(root, dockerfile))
                           if dockerfile is not None else None)
        if dockerfile is None:
            checks.append(_mk(
                "deploy:entrypoint", "部署产物: docker-entrypoint.sh", "SKIP",
                "Dockerfile 缺失，无法判定是否需要独立 entrypoint 脚本", "deploy"))
        elif dockerfile_text is not None and \
                "docker-entrypoint" not in dockerfile_text:
            checks.append(_mk(
                "deploy:entrypoint", "部署产物: docker-entrypoint.sh", "PASS",
                "Dockerfile 自含 ENTRYPOINT（如 go 栈），无需独立 entrypoint 脚本",
                "deploy"))
        else:
            checks.append(_file_check(
                "deploy:entrypoint", "docker-entrypoint.sh",
                "部署产物: docker-entrypoint.sh", root, "deploy"))
        checks.append(_file_check(
            "deploy:dockerignore", ".dockerignore",
            "部署产物: .dockerignore（防 COPY . . 把 .env/data 拷进镜像）",
            root, "deploy"))
        checks.append(_file_check(
            "deploy:backup_script", "backup.sh",
            "部署产物: backup.sh（init-workflow.md 要求 chmod +x）", root, "deploy"))
        checks.append(_file_check(
            "deploy:env_example", ".env.example",
            "部署产物: .env.example（只写键名入库）", root, "deploy"))
    return checks


def _check_privacy(scan):
    """6. 入库文件私钥格式头快扫（SKILL.md 硬性规则 3 秘密边界）。"""
    hits = scan["key_hits"]
    total = sum(len(v) for v in hits.values())
    if hits:
        items = []
        for rel in sorted(hits):
            for lineno in hits[rel]:
                items.append({"file": rel, "line": lineno})
        items = items[:50]
        detail = "入库文件发现私钥格式头 %d 处（秘密本体永不入库）" % total
        if scan["scope"] != "tracked":
            detail += "；扫描范围受限（%s）" % scan["note"]
        return _mk("privacy_scan", "入库文件私钥格式头快扫", "FAIL", detail,
                   "privacy", items=items)
    if scan["scope"] != "tracked":
        return _mk("privacy_scan", "入库文件私钥格式头快扫", "WARN",
                   "未发现私钥格式头，但扫描范围受限（%s）" % scan["note"],
                   "privacy")
    return _mk("privacy_scan", "入库文件私钥格式头快扫", "PASS",
               "入库文本文件未发现私钥格式头（共扫描 %d 个文本文件）"
               % scan["scanned_count"], "privacy")


# ---------------------------------------------------------------------------
# 汇总与输出
# ---------------------------------------------------------------------------
SECTION_LABELS = [
    ("management", "1. 管理文件齐备（init-workflow.md 第 1 步）"),
    ("placeholder", "2. 占位符替换干净（info-collection.md 存储纪律 / 填写约定）"),
    ("git_privacy", "3. Git 与隐私防线（init-workflow.md 第 1 步 / adopt-workflow.md C 步）"),
    ("deploy", "4. 部署产物（init-workflow.md 第 2 步）"),
    ("privacy", "5. 隐私快扫（SKILL.md 硬性规则 3 秘密边界）"),
]


def _summarize(checks):
    counts = {"PASS": 0, "FAIL": 0, "WARN": 0, "SKIP": 0, "total": len(checks)}
    for c in checks:
        counts[c["status"]] += 1
    return counts


def _git_label(status, note):
    if status == "repo":
        return "是（git 仓库，扫描跟踪文件）"
    if status == "not_repo":
        return "否（%s）" % (note or "非 git 仓库")
    return "未知（%s）" % (note or "git 不可用")


def _mode_label(mode_info):
    mode = mode_info["mode"]
    if mode == "unknown":
        return ("无法确认（PROJECT_INDEX / PROJECT_STATE / AGENTS 均未登记"
                "「项目模式」）")
    flavor = mode_info.get("flavor")
    if mode == "deployable" and flavor:
        return "可部署（%s，来源 %s）" % (
            "静态站，无容器" if flavor == "static" else "容器栈",
            mode_info["source"])
    labels = {"deployable": "可部署", "static": "可部署（静态站，无容器）",
              "no_deploy": "无部署交付"}
    return "%s（来源 %s: %s）" % (labels[mode], mode_info["source"],
                                mode_info["value"])


def _scan_label(scan):
    if scan["scope"] == "tracked":
        base = "扫描文本文件 %d 个（已跟踪 + 未跟踪且未被忽略）" % scan["scanned_count"]
        if scan["untracked_count"]:
            base += "（其中 %d 个未跟踪、未被忽略的文件已纳入扫描）" \
                    % scan["untracked_count"]
        return base
    return "%s；工作区降级扫描文本文件 %d 个" % (scan["note"],
                                           scan["scanned_count"])


def _fmt_item(item):
    if "match" in item:
        return "%s:%d — %s" % (item["file"], item["line"], item["match"])
    return "%s:%d" % (item["file"], item["line"])


def render_text(root, ts, git_status, git_note, mode_info, scan, checks, summary,
                exit_code):
    L = []
    L.append("# zedboot 装后机械校验报告（verify.py）")
    L.append("")
    L.append("- 扫描路径: %s" % root)
    L.append("- 生成时间: %s" % ts)
    L.append("- Git: %s" % _git_label(git_status, git_note))
    L.append("- 项目模式: %s" % _mode_label(mode_info))
    L.append("- 扫描范围: %s" % _scan_label(scan))
    for rel in scan["truncated"][:10]:
        L.append("  （附注：文件 %s 超过 2MB，仅扫描头部，剩余部分未检）" % rel)
    L.append("")
    for sec, sec_label in SECTION_LABELS:
        sec_checks = [c for c in checks if c["section"] == sec]
        if not sec_checks:
            continue
        L.append("## %s" % sec_label)
        for c in sec_checks:
            L.append("- [%s] %s: %s" % (c["status"], c["name"], c["detail"]))
            for it in c["items"][:20]:
                L.append("    - %s" % _fmt_item(it))
            if len(c["items"]) > 20:
                L.append("    - …等共 %d 条" % len(c["items"]))
        L.append("")
    L.append("## 汇总")
    L.append("PASS %d / FAIL %d / WARN %d / SKIP %d"
             % (summary["PASS"], summary["FAIL"], summary["WARN"],
                summary["SKIP"]))
    if summary["FAIL"]:
        L.append("结论: 校验未通过（存在 %d 项 FAIL，exit 1）" % summary["FAIL"])
    else:
        L.append("结论: 校验通过（无 FAIL 项，exit 0）")
    return "\n".join(_clean(x) for x in L)


def _json_safe(obj):
    """递归清洗，保证可 JSON 序列化（处理代理对/控制字符）。"""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(x) for x in obj]
    if isinstance(obj, str):
        return _clean(obj)
    return obj


def render_json(root, ts, git_status, git_note, mode_info, scan, checks,
                summary, exit_code):
    doc = {
        "verify_tool": "zedboot/scripts/verify.py",
        "scanned_path": os.path.abspath(root),
        "generated_at": ts,
        "git": {"status": git_status, "note": git_note},
        "project_mode": mode_info,
        "scan": {
            "scope": scan["scope"],
            "note": scan["note"],
            "scanned_count": scan["scanned_count"],
            "untracked_count": scan["untracked_count"],
            "truncated_files": scan["truncated"][:50],
        },
        "checks": checks,
        "summary": summary,
        "exit_code": exit_code,
    }
    return json.dumps(_json_safe(doc), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="verify.py",
        description="zedboot 装后机械校验工具：按 SKILL.md 安装承诺逐项核对目标项目"
                    "（管理文件齐备 / 占位符替换干净 / .gitignore 与 .env 跟踪状态 / "
                    "pre-push 隐私闸门 / 部署产物 / 入库文件私钥头）。绝对只读，"
                    "存在任何 FAIL 则 exit 1。",
        epilog="示例: python3 verify.py /path/to/project --json",
    )
    parser.add_argument("path", nargs="?", default=None,
                        help="要校验的项目路径（默认当前目录）")
    parser.add_argument("--json", action="store_true",
                        help="输出 JSON（供 AI 读取）；默认输出中文文本报告（供人读）")
    args = parser.parse_args(argv)

    root = args.path if args.path is not None else os.getcwd()
    root = os.path.abspath(root)
    if not os.path.exists(root):
        print("错误: 路径不存在: %s" % root, file=sys.stderr)
        return 2
    if not os.path.isdir(root):
        print("错误: 不是目录: %s" % root, file=sys.stderr)
        return 2

    git_status, git_note = _git_context(root)
    tracked = _tracked_files(root) if git_status == "repo" else None
    scan = _scan_committed_text(root, git_status, git_note, tracked)
    mode_info = _detect_project_mode(root)

    checks = []
    checks.extend(_check_management_docs(root))
    checks.append(_check_placeholder(scan))
    checks.extend(_check_gitignore_rules(root))
    checks.append(_check_gitignore_effective(root, git_status, git_note))
    checks.append(_check_env_tracked(root, git_status, git_note))
    checks.append(_check_private_not_tracked(root, git_status, git_note))
    checks.append(_check_pre_push_hook(root, git_status, git_note))
    checks.extend(_build_deploy_checks(root, mode_info))
    checks.append(_check_privacy(scan))

    summary = _summarize(checks)
    exit_code = 1 if summary["FAIL"] > 0 else 0
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if args.json:
        print(render_json(root, ts, git_status, git_note, mode_info, scan,
                          checks, summary, exit_code))
    else:
        print(render_text(root, ts, git_status, git_note, mode_info, scan,
                          checks, summary, exit_code))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
