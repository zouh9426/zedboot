#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zedboot 只读审计工具 (audit.py)
=================================

用途
----
zedboot 在「改造旧项目」流程中使用的机械式只读审计探测器。
按固定清单探测项目的：基本信息 / 技术栈 / git 状态 / 管理文档 /
部署痕迹 / UI 特征 / 根目录卫生 / 入库文件隐私 / zedboot 就绪度，
输出结构化结果，
只做事实统计，不做主观判断与建议（差距分析交给 AI）。

用法
----
    python3 audit.py [项目路径] [--json]
    python3 audit.py --help

    - 项目路径 : 要审计的目录，默认当前目录。
    - --json   : 输出 JSON（供 AI 读取）；默认输出中文结构化文本报告（供人读）。

只读承诺
--------
本脚本是绝对只读的，绝不往目标项目写任何东西：
- 不创建 / 修改 / 删除目标项目内任何文件；
- 不执行任何 git 写操作；
- 仅通过 subprocess 执行只读 git 命令（rev-parse / branch / remote / log /
  ls-files / status），且每条 git 命令带 10 秒超时与异常兜底。

兼容性
------
纯 Python 3 标准库，兼容 Python 3.8+。

边界约定
--------
- 探测不到的项输出 "unknown" 并附注「交由 AI 判断」，绝不硬猜；
  --json 模式下对应字段值为 null，并伴随同名 *_note 字段说明原因。
- 非 UTF-8 文件名 / 文件内容：非法字节替换后展示，不中断、不报错。
- git 未安装 / 命令超时 / 执行失败：相关字段标记 unknown 并附注原因。
- 「管理文档 N/10」的 10 指（与 references/project-rules-compact.md §16
  最小体系一致）：README.md / AGENTS.md / CHANGELOG.md / docs/README.md /
  archive/README.md + 五件套（docs/project/ 下 PROJECT_RULES.md /
  PROJECT_INDEX.md / PROJECT_STATE.md / TODO.md / DECISION_LOG.md）。
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys

GIT_TIMEOUT = 10  # 秒；每条 git 命令的超时上限

# ---------------------------------------------------------------------------
# 机械关键词表
# ---------------------------------------------------------------------------
JS_FRAMEWORK_KEYWORDS = (
    "next", "react", "vue", "express", "fastify",
    "nuxt", "svelte", "angular", "remix", "gatsby",
    "astro", "nest", "nestjs", "hono", "koa",
)
PY_WEB_FRAMEWORKS = ("fastapi", "flask", "django")

# 管理文档清单（12 项，逐项布尔探测）
MANAGEMENT_DOCS = (
    "README.md",
    "AGENTS.md",
    "CHANGELOG.md",
    "DESIGN.md",
    "docs/README.md",
    "docs/project/PROJECT_RULES.md",
    "docs/project/PROJECT_INDEX.md",
    "docs/project/PROJECT_STATE.md",
    "docs/project/TODO.md",
    "docs/project/DECISION_LOG.md",
    "archive/README.md",
    "docs/guides/deployment.md",
)

# 就绪度统计所用的 10 项核心管理文档（正典十项：不含 DESIGN.md，含 archive/README.md；
# DESIGN.md 由 UI 节 detect_ui 单独检查，不混入十项计数）
CORE_MANAGEMENT_DOCS = (
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

# 管理「五件套」
FIVE_PIECE = (
    "docs/project/PROJECT_RULES.md",
    "docs/project/PROJECT_INDEX.md",
    "docs/project/PROJECT_STATE.md",
    "docs/project/TODO.md",
    "docs/project/DECISION_LOG.md",
)

SECTION_LABELS = {
    "basic": "基本信息",
    "framework": "技术栈",
    "git": "Git",
    "management_docs": "管理文档",
    "deploy_traces": "部署痕迹",
    "ui": "UI",
    "root_hygiene": "根目录卫生",
    "committed_secrets": "入库文件隐私泄露",
    "zedboot_readiness": "zedboot 就绪度",
}

_H1_RE = re.compile(r"^#(?!\#)\s+(.+)$")


# ---------------------------------------------------------------------------
# 基础工具函数
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


def _yn(v):
    """布尔 -> [有]/[无]"""
    return "[有]" if v else "[无]"


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


def _find_dir(root, *rel_parts):
    """大小写不敏感地定位目录；返回实际相对路径或 None。"""
    cur = root
    acc = []
    for part in rel_parts:
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
    if not os.path.isdir(cur):
        return None
    return os.path.join(*acc)


def _first_h1(text):
    """取文本中第一个 H1（'# ' 开头，排除 '##'）。没有返回 None。"""
    text = text.lstrip("\ufeff")
    for line in text.splitlines():
        m = _H1_RE.match(line.strip())
        if m:
            return m.group(1).strip()
    return None


def _run_git(root, args):
    """执行一条只读 git 命令。
    返回 (ok, stdout, stderr, error_note)：
    - error_note 非 None 表示 git 不可用 / 超时 / 其他异常（= unknown 场景）；
    - error_note 为 None 但 ok=False 表示 git 正常执行但命令以非零退出
      （调用方据此判断，例如 rev-parse 在非仓库时退出非零）。
    """
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


def _dep_matches(keyword, dep_names):
    """机械匹配依赖名是否命中关键词（处理 @scope/name 与 - 分词）。"""
    keyword = keyword.lower()
    for dep in dep_names:
        if not isinstance(dep, str):
            continue
        dep = dep.lower()
        tokens = set()
        for part in dep.split("/"):
            tokens.update(re.split(r"[-_.@]", part))
        if keyword in tokens:
            return True
    return False


def _detect_python_web_frameworks(fname, raw):
    """从 Python 依赖文件中机械检出 web 框架关键词。"""
    found = []
    if fname == "requirements.txt":
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-", ".")):
                continue
            m = re.match(r"^([A-Za-z0-9_.\-]+)", line)
            if m:
                name = m.group(1).lower().rstrip(".-_")
                if name in PY_WEB_FRAMEWORKS:
                    found.append(name)
    else:
        low = raw.lower()
        for k in PY_WEB_FRAMEWORKS:
            if re.search(r"(^|[^A-Za-z0-9_])%s([^A-Za-z0-9_]|$)" % re.escape(k), low):
                found.append(k)
    return found


# ---------------------------------------------------------------------------
# 1. 基本信息
# ---------------------------------------------------------------------------
def detect_basic(root):
    data = {
        "dir_name": _clean(os.path.basename(os.path.abspath(root))),
        "has_readme": False,
        "project_name_hint": None,
        "project_name_note": None,
        "root_entry_count": None,
        "root_entry_count_note": None,
        "unknown_notes": [],
    }
    entries = _list_dir(root)
    if entries is None:
        data["root_entry_count"] = None
        data["root_entry_count_note"] = "目录不可读，交由 AI 判断"
        data["unknown_notes"].append("根目录不可读，交由 AI 判断")
    else:
        data["root_entry_count"] = len(entries)

    readme = _find_file(root, "README.md")
    if readme is None:
        data["has_readme"] = False
        data["project_name_note"] = "未找到 README.md，无法猜测项目名"
    else:
        data["has_readme"] = True
        text = _read_text(os.path.join(root, readme))
        if text is None:
            data["project_name_note"] = "README.md 非 UTF-8 编码或读取失败，交由 AI 判断"
        else:
            h1 = _first_h1(text)
            if h1 is None:
                data["project_name_note"] = "README.md 存在但未找到 H1 标题，交由 AI 判断"
            else:
                data["project_name_hint"] = _clean(h1)
    return data


# ---------------------------------------------------------------------------
# 2. 技术栈
# ---------------------------------------------------------------------------
def detect_framework(root):
    """按特征文件检测，可多命中。检测不到 -> status=unknown。"""
    matches = []
    unknown_notes = []

    # ---- Node.js（package.json）----
    pkg = _find_file(root, "package.json")
    pkg_data = None
    if pkg is not None:
        raw = _read_text(os.path.join(root, pkg))
        if raw is None:
            unknown_notes.append("package.json 存在但非 UTF-8 编码或读取失败，交由 AI 判断")
        else:
            try:
                pkg_data = json.loads(raw)
            except ValueError:
                unknown_notes.append("package.json 存在但 JSON 解析失败，交由 AI 判断")
    if pkg is not None:
        if pkg_data is None:
            matches.append({
                "framework": "node",
                "evidence": pkg,
                "detail": None,
                "detail_note": "package.json 无法解析，交由 AI 判断",
            })
        else:
            node_detail = {"name": None, "scripts": [], "framework_keywords": []}
            if isinstance(pkg_data, dict):
                nm = pkg_data.get("name")
                if isinstance(nm, str):
                    node_detail["name"] = _clean(nm)
                sc = pkg_data.get("scripts")
                if isinstance(sc, dict):
                    node_detail["scripts"] = [str(k) for k in sc]
                deps = pkg_data.get("dependencies") or {}
                dev = pkg_data.get("devDependencies") or {}
                if not isinstance(deps, dict):
                    deps = {}
                if not isinstance(dev, dict):
                    dev = {}
                node_detail["framework_keywords"] = sorted(
                    k for k in JS_FRAMEWORK_KEYWORDS
                    if _dep_matches(k, list(deps) + list(dev))
                )
            matches.append({"framework": "node", "evidence": pkg, "detail": node_detail})

    # ---- Next.js（next.config.* 或 package.json dependencies 含 next）----
    entries = _list_dir(root) or []
    next_config = sorted(
        e for e in entries
        if e.startswith("next.config") and os.path.isfile(os.path.join(root, e))
    )
    next_evidences = []
    if next_config:
        next_evidences.append(", ".join(next_config))
    if pkg_data is not None and isinstance(pkg_data, dict):
        deps = pkg_data.get("dependencies") or {}
        dev = pkg_data.get("devDependencies") or {}
        if not isinstance(deps, dict):
            deps = {}
        if not isinstance(dev, dict):
            dev = {}
        if _dep_matches("next", list(deps) + list(dev)):
            next_evidences.append("package.json (dependencies.next)")
    if next_evidences and not any(m["framework"] == "next.js" for m in matches):
        matches.append({"framework": "next.js", "evidence": "; ".join(next_evidences)})

    # ---- Python（requirements.txt / pyproject.toml / Pipfile）----
    py_files = []
    py_kws = []
    for fname in ("requirements.txt", "pyproject.toml", "Pipfile"):
        f = _find_file(root, fname)
        if f is not None:
            py_files.append(f)
            raw = _read_text(os.path.join(root, f))
            if raw is not None:
                py_kws.extend(_detect_python_web_frameworks(fname, raw))
    if py_files:
        matches.append({
            "framework": "python",
            "evidence": ", ".join(py_files),
            "detail": {"web_framework_keywords": sorted(set(py_kws))},
        })

    # ---- Go / Rust / Flutter ----
    for fname, fw in (("go.mod", "go"), ("Cargo.toml", "rust"), ("pubspec.yaml", "flutter")):
        f = _find_file(root, fname)
        if f is not None:
            matches.append({"framework": fw, "evidence": f})

    # ---- 静态站点（有 index.html 且无任何上述后端特征）----
    index_html = _find_file(root, "index.html")
    backend_hits = {m["framework"] for m in matches}
    if index_html is not None and not backend_hits:
        matches.append({
            "framework": "static",
            "evidence": index_html + "（有 index.html 且无任何后端特征）",
        })

    if matches:
        return {"status": "detected", "matches": matches, "unknown_notes": unknown_notes}
    return {
        "status": "unknown",
        "matches": None,
        "matches_note": "未检测到任何特征文件（package.json/requirements.txt/pyproject.toml/Pipfile/go.mod/Cargo.toml/pubspec.yaml/index.html），交由 AI 判断",
        "unknown_notes": unknown_notes,
    }


# ---------------------------------------------------------------------------
# 3. Git
# ---------------------------------------------------------------------------
def detect_git(root):
    data = {
        "status": "unknown",
        "is_repo": None,
        "is_repo_note": None,
        "branch": None,
        "branch_note": None,
        "uncommitted_changes": None,
        "uncommitted_changes_note": None,
        "remotes": None,
        "remotes_note": None,
        "recent_commits": None,
        "recent_commits_note": None,
        "has_main_branch": None,
        "has_main_branch_note": None,
        "task_branches": None,
        "hotfix_branches": None,
        "has_prefixed_branches": None,
        "prefixed_branches_note": None,
        "env_exists": _find_file(root, ".env") is not None,
        "env_tracked": None,
        "env_tracked_note": None,
        "risk_env_tracked": False,
        "unknown_notes": [],
    }

    ok, out, err, note = _run_git(root, ["rev-parse", "--is-inside-work-tree"])
    if note is not None:
        # git 不可用 / 命令超时：全部 git 字段 unknown
        data["status"] = "git_error"
        data["is_repo"] = None
        data["is_repo_note"] = note
        for k in ("branch", "uncommitted_changes", "remotes",
                  "recent_commits", "has_main_branch", "prefixed_branches"):
            data[k + "_note"] = note
        if data["env_exists"]:
            data["env_tracked"] = None
            data["env_tracked_note"] = note
        else:
            data["env_tracked"] = False  # 无 .env，必然未跟踪（确定事实）
        return data

    if not (ok and out.strip() == "true"):
        # rev-parse 未确认仓库：区分「确定非仓库」与「git 命令行为异常」
        definitely_not_repo = (
            ok and out.strip() == "false"
        ) or (not ok and "not a git repository" in (err or "").lower())
        if definitely_not_repo:
            data["status"] = "not_repo"
            data["is_repo"] = False
            data["env_tracked"] = False
            data["unknown_notes"].append("非 git 仓库，git 相关字段无法探测，交由 AI 判断")
        else:
            data["status"] = "git_error"
            data["is_repo"] = None
            data["is_repo_note"] = "git rev-parse 异常退出（无法确定是否仓库），交由 AI 判断"
            for k in ("branch", "uncommitted_changes", "remotes",
                      "recent_commits", "has_main_branch", "prefixed_branches"):
                data[k + "_note"] = data["is_repo_note"]
            if data["env_exists"]:
                data["env_tracked"] = None
                data["env_tracked_note"] = data["is_repo_note"]
            else:
                data["env_tracked"] = False
        return data

    data["status"] = "repo"
    data["is_repo"] = True

    # 嵌套仓库边界：目录自身无 .git、被外层仓库包含时，git 命令会静默命中
    # 外层仓库（分支/远程/提交记录全是外层的）——按"自身非仓库"处理
    ok, out, err, note = _run_git(root, ["rev-parse", "--show-toplevel"])
    if ok and out.strip() and \
            os.path.realpath(out.strip()) != os.path.realpath(root):
        data["status"] = "not_repo"
        data["is_repo"] = False
        data["is_repo_note"] = "目录自身无 git 仓库（被外层仓库包含），git 字段按非仓库处理"
        data["env_tracked"] = False
        data["unknown_notes"].append(
            "目录自身无 git 仓库（被外层仓库包含），git 相关字段无法探测，交由 AI 判断")
        return data

    # 当前分支
    ok, out, err, note = _run_git(root, ["branch", "--show-current"])
    if ok:
        branch = out.strip()
        if branch:
            data["branch"] = _clean(branch)
        else:
            ok2, out2, err2, note2 = _run_git(root, ["rev-parse", "--short", "HEAD"])
            if ok2 and out2.strip():
                data["branch"] = "detached HEAD at %s" % out2.strip()
            elif (err2 or "").find("does not have any commits") != -1:
                data["branch"] = "（仓库尚无提交）"
            else:
                data["branch_note"] = note2 or "无法确定当前分支，交由 AI 判断"
    else:
        data["branch_note"] = note or "git branch 命令失败，交由 AI 判断"

    # 未提交变更数
    ok, out, err, note = _run_git(root, ["status", "--porcelain"])
    if ok:
        data["uncommitted_changes"] = len([l for l in out.splitlines() if l.strip()])
    else:
        data["uncommitted_changes_note"] = note or "git status 命令失败，交由 AI 判断"

    # 远程仓库（去重 fetch 地址）
    ok, out, err, note = _run_git(root, ["remote", "-v"])
    if ok:
        remotes = []
        seen = set()
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                name, url, kind = parts[0], parts[1], parts[2]
            else:
                sp = line.split()
                if len(sp) >= 3:
                    name, url, kind = sp[0], sp[1], " ".join(sp[2:])
                else:
                    continue
            if "fetch" not in kind.lower():
                continue
            if url in seen:
                continue
            seen.add(url)
            remotes.append({"name": _clean(name), "url": _clean(url)})
        data["remotes"] = remotes
    else:
        data["remotes_note"] = note or "git remote 命令失败，交由 AI 判断"

    # 最近 5 条 commit
    ok, out, err, note = _run_git(root, ["log", "-5", "--oneline", "--decorate=no"])
    if ok:
        data["recent_commits"] = [_clean(l.strip()) for l in out.splitlines() if l.strip()]
    elif (err or "").find("does not have any commits") != -1:
        data["recent_commits"] = []  # 空仓库：确定没有提交
    else:
        data["recent_commits_note"] = note or "git log 命令失败，交由 AI 判断"

    # 是否存在 main 分支
    ok, out, err, note = _run_git(root, ["branch", "--list", "main"])
    if ok:
        data["has_main_branch"] = bool(out.strip())
    else:
        data["has_main_branch_note"] = note or "git branch 命令失败，交由 AI 判断"

    # task/ 或 hotfix/ 前缀分支
    ok, out, err, note = _run_git(root, ["branch", "--list", "task/*", "hotfix/*"])
    if ok:
        lines = [l.strip().lstrip("*").strip() for l in out.splitlines() if l.strip()]
        data["task_branches"] = [_clean(b) for b in lines if b.startswith("task/")]
        data["hotfix_branches"] = [_clean(b) for b in lines if b.startswith("hotfix/")]
        data["has_prefixed_branches"] = bool(lines)
    else:
        data["prefixed_branches_note"] = note or "git branch 命令失败，交由 AI 判断"

    # .env 是否被 git 跟踪（安全风险项）
    if data["env_exists"]:
        ok, out, err, note = _run_git(root, ["ls-files", "--error-unmatch", "--", ".env"])
        if ok:
            data["env_tracked"] = True
            data["risk_env_tracked"] = True
        elif note is None:
            data["env_tracked"] = False  # 存在于磁盘但未纳入索引
        else:
            data["env_tracked"] = None
            data["env_tracked_note"] = note
    else:
        data["env_tracked"] = False

    return data


# ---------------------------------------------------------------------------
# 4. 管理文档
# ---------------------------------------------------------------------------
def detect_management_docs(root):
    docs = {}
    case_hits = {}
    for rel in MANAGEMENT_DOCS:
        actual = _find_file(root, *tuple(rel.split("/")))
        docs[rel] = actual is not None
        if actual is not None and actual != rel:
            case_hits[rel] = actual
    return {"docs": docs, "case_insensitive_hits": case_hits}


# ---------------------------------------------------------------------------
# 5. 部署痕迹
# ---------------------------------------------------------------------------
def detect_deploy_traces(root):
    data = {}
    entries = _list_dir(root) or []

    # Dockerfile（含 Dockerfile.* 变体）
    dockerfiles = sorted(
        e for e in entries
        if e.startswith("Dockerfile") and os.path.isfile(os.path.join(root, e))
    )
    data["dockerfile"] = {"exists": bool(dockerfiles), "files": dockerfiles}

    # docker-compose / compose 变体
    comp = []
    for n in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        f = _find_file(root, n)
        if f is not None:
            comp.append(f)
    comp = sorted(set(comp))
    data["compose"] = {"exists": bool(comp), "files": comp}

    data["docker_entrypoint"] = _find_file(root, "docker-entrypoint.sh") is not None
    data["dockerignore"] = _find_file(root, ".dockerignore") is not None

    # .github/workflows/ 下文件数
    wf_dir = _find_dir(root, ".github", "workflows")
    wf_files = []
    if wf_dir is not None:
        try:
            wf_files = [x for x in os.listdir(os.path.join(root, wf_dir))
                        if os.path.isfile(os.path.join(root, wf_dir, x))]
        except OSError:
            wf_files = []
    data["github_workflows"] = {"count": len(wf_files), "exists": len(wf_files) > 0}

    data["caddyfile"] = _find_file(root, "Caddyfile") is not None

    # nginx 配置
    nginx_evidence = []
    nf = _find_file(root, "nginx.conf")
    if nf is not None:
        nginx_evidence.append(nf)
    nginx_dir = _find_dir(root, "nginx")
    if nginx_dir is not None:
        try:
            confs = sorted(
                x for x in os.listdir(os.path.join(root, nginx_dir))
                if x.endswith((".conf", ".template"))
            )
            nginx_evidence.extend(os.path.join(nginx_dir, x) for x in confs)
        except OSError:
            pass
    data["nginx"] = {"exists": bool(nginx_evidence), "evidence": nginx_evidence}

    # deploy/rsync/backup 相关脚本（根目录与 scripts/ 下的文件名）
    script_names = []
    for sub in ("", "scripts"):
        base = root if not sub else os.path.join(root, sub)
        if not os.path.isdir(base):
            continue
        names = _list_dir(base)
        if names is None:
            continue
        for n in names:
            low = n.lower()
            # 只看脚本类文件：文档扩展名（如 deploy-notes.md）不计入部署脚本
            if os.path.isfile(os.path.join(base, n)) and any(
                tag in low for tag in ("deploy", "rsync", "backup")
            ) and not low.endswith((".md", ".markdown", ".txt", ".rst")):
                script_names.append(os.path.join(sub, n) if sub else n)
    data["deploy_scripts"] = {"exists": bool(script_names), "files": sorted(script_names)}

    data["env_example"] = _find_file(root, ".env.example") is not None
    data["env_exists"] = _find_file(root, ".env") is not None

    # 部署痕迹合计（10 项）
    data["count"] = sum([
        1 if data["dockerfile"]["exists"] else 0,
        1 if data["compose"]["exists"] else 0,
        1 if data["docker_entrypoint"] else 0,
        1 if data["dockerignore"] else 0,
        1 if data["github_workflows"]["exists"] else 0,
        1 if data["caddyfile"] else 0,
        1 if data["nginx"]["exists"] else 0,
        1 if data["deploy_scripts"]["exists"] else 0,
        1 if data["env_example"] else 0,
        1 if data["env_exists"] else 0,
    ])
    return data


# ---------------------------------------------------------------------------
# 6. UI
# ---------------------------------------------------------------------------
def detect_ui(root):
    data = {
        "has_design_doc": False,
        "design_doc_actual": None,
        "frontend_features": [],
        "has_frontend": False,
        "unknown_notes": [],
    }
    d = _find_file(root, "DESIGN.md")
    if d is not None:
        data["has_design_doc"] = True
        data["design_doc_actual"] = d

    pkg = _find_file(root, "package.json")
    if pkg is not None:
        raw = _read_text(os.path.join(root, pkg))
        if raw is None:
            data["unknown_notes"].append("package.json 非 UTF-8 编码，无法判断前端特征，交由 AI 判断")
        else:
            try:
                pkg_data = json.loads(raw)
            except ValueError:
                pkg_data = None
                data["unknown_notes"].append("package.json 解析失败，无法判断前端特征，交由 AI 判断")
            if isinstance(pkg_data, dict):
                deps = pkg_data.get("dependencies") or {}
                dev = pkg_data.get("devDependencies") or {}
                if not isinstance(deps, dict):
                    deps = {}
                if not isinstance(dev, dict):
                    dev = {}
                for k in ("react", "vue", "tailwindcss"):
                    if _dep_matches(k, list(deps) + list(dev)):
                        data["frontend_features"].append("package.json 依赖 %s" % k)

    ih = _find_file(root, "index.html")
    if ih is not None:
        data["frontend_features"].append("存在 index.html")

    data["has_frontend"] = len(data["frontend_features"]) > 0
    return data


# ---------------------------------------------------------------------------
# 7. 根目录卫生
# ---------------------------------------------------------------------------
def detect_root_hygiene(root):
    data = {
        "suspicious_dirs": [],
        "screenshot_files": [],
        "ds_store": False,
        "temp_files": [],
        "clean": True,
    }
    entries = _list_dir(root) or []
    # 违禁目录名：精确名 + 序号/日期变体（final-2、最终版2、new_2026 等，规范 §4.3）
    suspicious_re = re.compile(
        r"^(misc|other|new|latest|final|temp|杂项|最终版)([-_\s]?\d+)?$", re.IGNORECASE
    )
    for e in entries:
        low = e.lower()
        full = os.path.join(root, e)
        if os.path.isdir(full) and suspicious_re.match(low):
            data["suspicious_dirs"].append(e)
        elif os.path.isfile(full):
            if low.endswith((".png", ".jpg")):
                data["screenshot_files"].append(e)
            elif low.endswith((".tmp", ".bak")) or low.endswith("~"):
                data["temp_files"].append(e)
            elif low == ".ds_store":
                data["ds_store"] = True
    data["suspicious_dirs"].sort()
    data["screenshot_files"].sort()
    data["temp_files"].sort()
    data["clean"] = not (
        data["suspicious_dirs"] or data["screenshot_files"]
        or data["ds_store"] or data["temp_files"]
    )
    return data


# ---------------------------------------------------------------------------
# 8. zedboot 就绪度（只输出事实计数，不做建议）
# ---------------------------------------------------------------------------
def detect_readiness(management_result, deploy_result):
    docs = management_result["docs"]
    present = sum(1 for d in CORE_MANAGEMENT_DOCS if docs.get(d))
    five = all(docs.get(d) for d in FIVE_PIECE)
    return {
        "management_docs_present": present,
        "management_docs_total": 10,
        # 10 项按正典（references/project-rules-compact.md §16）计数，不含 DESIGN.md；
        # DESIGN.md 属 UI 节独立检查（detect_ui），不混入十项计数
        "design_md_applicable_note": "管理文档 10 项按正典计数（DESIGN.md 不计入，在 UI 节单独检查）",
        "deploy_traces_present": deploy_result["count"],
        "has_full_management_five_piece": bool(five),
    }


# ---------------------------------------------------------------------------
# 9. 入库文件隐私泄露（git 跟踪的文本文件中是否含运维真实值）
# ---------------------------------------------------------------------------
_SCAN_FILE_LIMIT = 2 * 1024 * 1024  # 单文件扫描上限：只读前 2MB，防大文件卡死
_TEXT_HEAD = 4096                   # 二进制判定：头部含 NUL 字节视为二进制

_IPV4_RE = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![\d.])")
# 本机绝对路径：/Users/ 或 /home/ 下的具体名字段；
# 名字段排除代码/占位符语法字符，只匹配"像真实路径"的段：
#   < > —— 占位符（/home/<账号>）；[ ] —— 正则字符类（自检命令里的 /Users/[a-zA-Z0-9_-]+/）；
#   $ { } " ' ` ( ) —— 脚本/代码里的变量与字符串片段（/home/${变量}/、startswith("/home/") 等）
_LOCAL_PATH_RE = re.compile(r"/(?:Users|home)/([^/\s<>\x00\[\]${}\"'`()]+)")
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")

_PRIVACY_TYPE_LABELS = {
    "ip": "疑似公网 IPv4",
    "local_path": "本机绝对路径",
    "private_key": "私钥格式头",
    "docs_private_tracked": "docs/private/ 文件被 git 跟踪",
}

# zedboot 工作流生成的管理文档：按流程必须记录风险与占位说明，
# 其中的 IP/路径字样多为"风险元描述"而非真实泄露——命中单独列示，不计入风险结论
_MANAGEMENT_DOC_PATHS = frozenset({
    "AGENTS.md",
    "docs/project/TODO.md",
    "docs/project/DECISION_LOG.md",
    "docs/project/PROJECT_INDEX.md",
    "docs/project/PROJECT_STATE.md",
    "docs/project/AUDIT_REPORT.md",
    "docs/project/ADOPTION_PLAN.md",
})
# git ls-files 输出与项目实际大小写可能不一致（§4 管理文档检测本就大小写不敏感），
# 降级匹配同样按小写口径，避免 Docs/Project/TODO.md 这类变体漏降级被当真风险
_MANAGEMENT_DOC_PATHS_LOWER = frozenset(p.lower() for p in _MANAGEMENT_DOC_PATHS)


def _is_public_ipv4(ip):
    """IPv4 是否属公网。排除段与 assets/hooks/pre-push.tmpl 的 IP 排除清单对齐：
    0.0.0.0/8、回环 127/8、私网 10/8 与 172.16/12 与 192.168/16、
    链路本地 169.254/16、受限广播 255.255.255.255、RFC 5737 文档示例段。
    （注：对齐仅指 IP 排除段；路径扫描 audit.py 不要求尾部斜杠、比 hook 更严，
    hook 正则要求尾部斜杠、对边界情形宁漏勿滥是刻意设计。）"""
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    try:
        a, b, c, d = (int(x) for x in parts)
    except ValueError:
        return False
    if any(x > 255 for x in (a, b, c, d)):
        return False
    if a == 0:                         # 0.0.0.0/8 本网络
        return False
    if a == 127:                       # 127.0.0.0/8 回环
        return False
    if a == 10:                        # 10.0.0.0/8 私网
        return False
    if a == 172 and 16 <= b <= 31:     # 172.16.0.0/12 私网
        return False
    if a == 192 and b == 168:          # 192.168.0.0/16 私网
        return False
    if a == 169 and b == 254:          # 169.254.0.0/16 链路本地
        return False
    if (a, b, c) in ((192, 0, 2), (198, 51, 100), (203, 0, 113)):
        return False                   # RFC 5737 文档示例段
    if ip == "255.255.255.255":        # 受限广播
        return False
    return True


def _read_text_head(path, limit):
    """读文本文件头部：先读 4KB 判二进制（含 NUL 视为二进制跳过），
    文本则读满 limit 字节并以 UTF-8 解码（无效字节替换为 U+FFFD，绝不抛异常）。
    不可读 / 二进制返回 None。
    注：必须按 UTF-8 解码而非 latin-1，否则 UTF-8 续字节 0x85 等会被
    splitlines() 误判为换行，导致行号错乱。"""
    try:
        with open(path, "rb") as f:
            head = f.read(_TEXT_HEAD)
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


_AGENTS_PROJECT_NAME_RE = re.compile(
    r"^\s*[-*]?\s*项目名称\s*[：:]\s*(.*\S)\s*$"
)


def _project_name_from_agents(root):
    """从项目根 AGENTS.md 的「项目名称」行提取项目名（中/英文冒号均可）。

    该值 = 可推导部署账号（服务器账号 = 项目名），/home/<该值>/ 是部署体系允许
    写入入库文档的服务器端路径，与目录名同权放行；占位符（未填实）不入放行集合。
    找不到或无法提取返回 None。
    """
    rel = _find_file(root, "AGENTS.md")
    if rel is None:
        return None
    text = _read_text(os.path.join(root, rel))
    if text is None:
        return None
    for line in text.splitlines():
        m = _AGENTS_PROJECT_NAME_RE.match(line.strip())
        if not m:
            continue
        name = m.group(1).strip()
        if not name or "<" in name or ">" in name:
            return None
        return name
    return None


def _scan_text_privacy_hits(text, home_allow=None):
    """扫描文本内容，返回 {命中类型: [行号...]}（每行每类只计一次）。

    home_allow：可推导部署账号名集合（默认含项目目录名；若项目根 AGENTS.md 声明了
    「项目名称」则一并加入）。/home/<其中的名字>/ 是部署体系约定的服务器端可推导
    路径（存储纪律允许写入入库文档），不视为本机路径泄露。
    """
    hits = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        if _PRIVATE_KEY_RE.search(line):
            hits.setdefault("private_key", []).append(lineno)
        path_hits = [
            m for m in _LOCAL_PATH_RE.finditer(line)
            if not (home_allow and m.group(0).startswith("/home/")
                    and m.group(1) in home_allow)
        ]
        if path_hits:
            hits.setdefault("local_path", []).append(lineno)
        if any(_is_public_ipv4(m.group(0)) for m in _IPV4_RE.finditer(line)):
            hits.setdefault("ip", []).append(lineno)
    return hits


# 非 git 仓库降级扫描工作区时跳过的噪音目录（依赖/构建产物/IDE）
_WORKSPACE_SKIP_DIRS = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", "target", ".idea", ".vscode",
})
_WORKSPACE_SCAN_MAX_FILES = 500  # 工作区扫描文件数上限，防超大目录树拖垮审计


def _file_exceeds(path, limit):
    """文件大小是否超过扫描上限（无法获取大小时视为未超）。"""
    try:
        return os.path.getsize(path) > limit
    except OSError:
        return False


def _record_hits(data, rel, hits):
    """把命中登记进 data：管理文档命中单独列示（多为风险元描述），
    其余计入风险结论。"""
    target = ("management_doc_items" if rel.lower() in _MANAGEMENT_DOC_PATHS_LOWER
              else "risk_items")
    for htype, lines in hits.items():
        data[target].append({
            "file": _clean(rel),
            "type": htype,
            "type_label": _PRIVACY_TYPE_LABELS[htype],
            "count": len(lines),
            "lines": lines[:20],
        })
    if hits and target == "risk_items":
        data["risk_found"] = True


def _scan_one_file(data, root, rel, home_allow):
    """扫描单个文件并登记命中；返回 True 表示该文件计入了扫描数。"""
    path = os.path.join(root, rel)
    truncated = _file_exceeds(path, _SCAN_FILE_LIMIT)
    text = _read_text_head(path, _SCAN_FILE_LIMIT)
    if text is None:
        return False  # 不可读或二进制，跳过
    if truncated:
        data["truncated_files"].append(_clean(rel))
    _record_hits(data, rel, _scan_text_privacy_hits(text, home_allow))
    return True


def detect_committed_secrets(root):
    """检查文本文件是否含：公网 IPv4 / 本机绝对路径 / 私钥格式头。
    绝对只读：仅执行只读 git 命令与读文件内容，不修改被审计项目。

    git 仓库：扫 git 跟踪的文件（跳过 .env（另有专项检查）与 .gitignore；
    docs/private/ 下文件被跟踪本身即风险，单独列项，不扫其内容）。
    非 git 仓库：无入库文件概念，降级扫描工作区文本文件（跳过依赖/构建噪音目录），
    命中即未入库风险——改造前的项目恰是隐私风险期，不能静默跳过。
    被外层 git 仓库包含的嵌套目录按非仓库处理（git 命令会静默命中外层仓库，
    其跟踪清单与状态不代表本目录，结论不可信）。
    """
    data = {
        "status": "unknown",
        "risk_found": False,
        "risk_items": [],
        "management_doc_items": [],
        "workspace_scan": False,
        "scanned_count": None,
        "truncated_files": [],
        "unknown_notes": [],
    }
    ok, out, err, note = _run_git(root, ["ls-files"])
    if note is not None:
        # git 不可用 / 命令超时：整体 unknown
        data["status"] = "git_error"
        data["unknown_notes"].append(note)
        return data

    files = None
    if ok:
        # 嵌套仓库边界：show-toplevel 不等于被审计根目录时，ls-files 列出的
        # 是外层仓库的跟踪清单——按非仓库降级处理
        ok2, out2, err2, note2 = _run_git(root, ["rev-parse", "--show-toplevel"])
        if ok2 and out2.strip() and \
                os.path.realpath(out2.strip()) != os.path.realpath(root):
            data["unknown_notes"].append(
                "目录自身无 git 仓库（被外层仓库包含），按非仓库做工作区降级扫描")
        else:
            data["status"] = "repo"
            files = [l.strip() for l in out.splitlines() if l.strip()]
    else:
        # git 正常执行但 ls-files 失败：视为非仓库（无跟踪文件概念）
        if err and "not a git repository" not in err.lower():
            data["unknown_notes"].append(
                "git ls-files 执行失败（按非仓库做工作区降级扫描），交由 AI 判断：%s"
                % _clean(err or "无错误输出"))

    home_allow = {os.path.basename(os.path.realpath(root))}
    pn = _project_name_from_agents(root)
    if pn:
        home_allow.add(pn)

    if files is not None:
        # git 仓库：扫跟踪清单
        data["scanned_count"] = len(files)
        # 未跟踪文件不在入库扫描范围——提醒存量，防脏仓库里含密草稿被 git add 直接扫进提交
        ok3, out3, err3, note3 = _run_git(
            root, ["ls-files", "--others", "--exclude-standard"])
        if ok3:
            untracked = [l for l in out3.splitlines() if l.strip()]
            if untracked:
                data["unknown_notes"].append(
                    "存在 %d 个未跟踪文件未纳入入库扫描（git add 前请自查是否含敏感内容）"
                    % len(untracked))
        for rel in files:
            base = os.path.basename(rel)
            if base == ".env" or base == ".gitignore":
                continue  # .env 已有专项检查；.gitignore 本就应被跟踪，不扫内容
            if rel.lower().startswith("docs/private/"):
                # 理论上不该被跟踪：被跟踪本身即风险项，不做内容扫描
                data["risk_items"].append({
                    "file": _clean(rel),
                    "type": "docs_private_tracked",
                    "type_label": _PRIVACY_TYPE_LABELS["docs_private_tracked"],
                    "count": 1,
                    "lines": None,
                })
                data["risk_found"] = True
                continue
            _scan_one_file(data, root, rel, home_allow)
    else:
        # 非仓库：工作区降级扫描
        data["status"] = "not_repo"
        data["workspace_scan"] = True
        scanned = 0
        stop = False
        for dirpath, dirnames, filenames in os.walk(root):
            if stop:
                break
            dirnames[:] = [d for d in dirnames if d not in _WORKSPACE_SKIP_DIRS]
            for fn in sorted(filenames):
                if fn in (".env", ".gitignore"):
                    continue  # .env 不入扫描（非仓库无跟踪概念）；.gitignore 无敏感内容
                if scanned >= _WORKSPACE_SCAN_MAX_FILES:
                    data["unknown_notes"].append(
                        "工作区文件超过 %d 个，仅扫描前 %d 个，其余未检"
                        % (_WORKSPACE_SCAN_MAX_FILES, _WORKSPACE_SCAN_MAX_FILES))
                    stop = True
                    break
                rel = os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/")
                if _scan_one_file(data, root, rel, home_allow):
                    scanned += 1
        data["scanned_count"] = scanned

    for rel in data["truncated_files"][:10]:
        data["unknown_notes"].append(
            "文件 %s 超过 2MB，仅扫描头部，剩余部分未检" % rel)

    data["risk_items"].sort(key=lambda x: (x["file"], x["type"]))
    data["management_doc_items"].sort(key=lambda x: (x["file"], x["type"]))
    return data


def run_audit(root):
    results = {}
    results["basic"] = detect_basic(root)
    results["framework"] = detect_framework(root)
    results["git"] = detect_git(root)
    results["committed_secrets"] = detect_committed_secrets(root)
    results["management_docs"] = detect_management_docs(root)
    results["deploy_traces"] = detect_deploy_traces(root)
    results["ui"] = detect_ui(root)
    results["root_hygiene"] = detect_root_hygiene(root)
    results["zedboot_readiness"] = detect_readiness(
        results["management_docs"], results["deploy_traces"]
    )
    return results


# ---------------------------------------------------------------------------
# unknown 汇总
# ---------------------------------------------------------------------------
def _collect_unknown(results):
    """收集所有 unknown 项：字段值为 null 且带 *_note，或节级 unknown_notes。"""
    items = []
    for sec, data in results.items():
        if not isinstance(data, dict):
            continue
        for note in data.get("unknown_notes") or []:
            items.append((sec, "*", note))
        for k, v in data.items():
            if k.endswith("_note") and v:
                base = k[: -len("_note")]
                if base in data and data[base] is None:
                    items.append((sec, base, v))
    return items


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def _unknown_str(note):
    """把附注渲染成 'unknown（交由 AI 判断：...）'，避免短语重复。"""
    note = (note or "无法探测").strip().rstrip("，。")
    if note.endswith("交由 AI 判断"):
        note = note[: -len("交由 AI 判断")].rstrip("，。 ")
    return "unknown（交由 AI 判断：%s）" % (note or "无法探测")


def _maybe(data, key, fmt=None):
    """字段值；None 视为 unknown 并附 note。"""
    v = data.get(key)
    if v is None:
        return _unknown_str(data.get(key + "_note"))
    return fmt(v) if fmt else str(v)


def _fmt_hit_loc(item):
    """命中位置渲染：'，命中 N 行，行号 1, 2'（截断时补'等共 N 行'）。"""
    if not item["lines"]:
        return ""
    loc = "，命中 %d 行，行号 %s" % (
        item["count"], ", ".join(str(x) for x in item["lines"]))
    if item["count"] > len(item["lines"]):
        loc += " 等共 %d 行" % item["count"]
    return loc


def render_text(results, root, ts):
    L = []
    L.append("# zedboot 只读审计报告")
    L.append("")
    L.append("- 扫描路径: %s" % root)
    L.append("- 生成时间: %s" % ts)
    L.append("")

    # 1. 基本信息
    basic = results["basic"]
    L.append("## 1. 基本信息 (basic)")
    L.append("- 目录名: %s" % basic["dir_name"])
    if basic["has_readme"]:
        L.append("- README.md: [有]")
        if basic["project_name_hint"] is not None:
            L.append("- 项目名猜测(README 第一个 H1): %s" % basic["project_name_hint"])
        else:
            L.append("- 项目名猜测(README 第一个 H1): unknown（交由 AI 判断：%s）"
                     % (basic["project_name_note"] or "无 H1"))
    else:
        L.append("- README.md: [无]")
        L.append("- 项目名猜测(README 第一个 H1): unknown（交由 AI 判断：无 README.md）")
    L.append("- 根目录条目总数: %s" % _maybe(basic, "root_entry_count"))
    L.append("")

    # 2. 技术栈
    fw = results["framework"]
    L.append("## 2. 技术栈 (framework)")
    if fw["status"] == "unknown":
        notes = "; ".join(fw.get("unknown_notes") or [])
        reason = fw.get("matches_note") or notes or "未检测到任何特征文件"
        L.append("- 检测结果: %s" % _unknown_str(reason))
    else:
        for m in fw["matches"]:
            L.append("- %s: [有] 依据: %s" % (m["framework"], m.get("evidence") or "?"))
            det = m.get("detail")
            if det:
                if det.get("name"):
                    L.append("    - package.json name: %s" % det["name"])
                if det.get("scripts"):
                    L.append("    - scripts: %s" % ", ".join(det["scripts"]))
                if det.get("framework_keywords"):
                    L.append("    - 检测到 JS 框架关键词: %s" % ", ".join(det["framework_keywords"]))
                if det.get("web_framework_keywords"):
                    L.append("    - 检测到 Python Web 框架: %s" % ", ".join(det["web_framework_keywords"]))
            if m.get("detail_note"):
                L.append("    - %s" % m["detail_note"])
        for n in fw.get("unknown_notes") or []:
            L.append("- 附注: %s" % n)
    L.append("")

    # 3. Git
    g = results["git"]
    L.append("## 3. Git (git)")
    if g["status"] == "git_error":
        L.append("- 状态: %s" % _unknown_str(g.get("is_repo_note") or "git 不可用"))
        L.append("- 是否为 git 仓库: %s" % _unknown_str(g.get("is_repo_note") or "无法探测"))
        for k, label in (
            ("branch", "当前分支"),
            ("uncommitted_changes", "未提交变更数"),
            ("remotes", "远程仓库"),
            ("recent_commits", "最近提交(5)"),
            ("has_main_branch", "main 分支"),
            ("prefixed_branches", "task/hotfix 前缀分支"),
        ):
            L.append("- %s: %s" % (label, _maybe(g, k)))
        L.append("- .env 是否被 git 跟踪: %s" % _maybe(g, "env_tracked"))
    elif g["status"] == "not_repo":
        L.append("- 是否为 git 仓库: 否")
        if g.get("is_repo_note"):
            L.append("- 附注: %s" % g["is_repo_note"])
        L.append("- 其余 git 字段: unknown（交由 AI 判断：非 git 仓库）")
        L.append("- .env: %s" % ("存在（非 git 仓库，无跟踪风险）" if g["env_exists"] else "不存在"))
    else:
        L.append("- 是否为 git 仓库: 是")
        L.append("- 当前分支: %s" % _maybe(g, "branch"))
        L.append("- 未提交变更数: %s" % _maybe(g, "uncommitted_changes"))
        if g["remotes"] is None:
            L.append("- 远程仓库: %s" % _maybe(g, "remotes"))
        elif not g["remotes"]:
            L.append("- 远程仓库: 无")
        else:
            for r in g["remotes"]:
                L.append("- 远程仓库: %s %s" % (r["name"], r["url"]))
        if g["recent_commits"] is None:
            L.append("- 最近提交(5): %s" % _maybe(g, "recent_commits"))
        elif not g["recent_commits"]:
            L.append("- 最近提交(5): 无提交")
        else:
            L.append("- 最近提交(5):")
            for c in g["recent_commits"]:
                L.append("    %s" % c)
        L.append("- main 分支: %s" % _maybe(g, "has_main_branch", _yn))
        if g["prefixed_branches_note"]:
            L.append("- task/hotfix 前缀分支: %s" % _maybe(g, "has_prefixed_branches"))
        else:
            names = (g["task_branches"] or []) + (g["hotfix_branches"] or [])
            L.append("- task/hotfix 前缀分支: %s"
                     % ("有: " + ", ".join(names) if names else "无"))
        if g["risk_env_tracked"]:
            L.append("- ⚠ .env 被 git 跟踪: 是（安全风险：敏感文件已纳入版本控制）")
        elif g["env_tracked"] is None:
            L.append("- .env 是否被 git 跟踪: %s" % _maybe(g, "env_tracked"))
        elif g["env_exists"]:
            L.append("- .env 存在但未被 git 跟踪（安全）")
        else:
            L.append("- .env 不存在")
    L.append("")

    # 4. 管理文档
    md = results["management_docs"]
    L.append("## 4. 管理文档 (management_docs)")
    for rel, exists in md["docs"].items():
        shown = md["case_insensitive_hits"].get(rel, rel)
        L.append("- %-40s %s" % (shown, _yn(exists)))
    L.append("")

    # 5. 部署痕迹
    dp = results["deploy_traces"]
    L.append("## 5. 部署痕迹 (deploy_traces)")
    if dp["dockerfile"]["exists"]:
        L.append("- Dockerfile: [有] %s" % ", ".join(dp["dockerfile"]["files"]))
    else:
        L.append("- Dockerfile: [无]")
    if dp["compose"]["exists"]:
        L.append("- docker-compose.yml / compose.yaml: [有] %s" % ", ".join(dp["compose"]["files"]))
    else:
        L.append("- docker-compose.yml / compose.yaml: [无]")
    L.append("- docker-entrypoint.sh: %s" % _yn(dp["docker_entrypoint"]))
    L.append("- .dockerignore: %s" % _yn(dp["dockerignore"]))
    if dp["github_workflows"]["count"] > 0:
        L.append("- .github/workflows/: [有] %d 个文件" % dp["github_workflows"]["count"])
    else:
        L.append("- .github/workflows/: [无]")
    L.append("- Caddyfile: %s" % _yn(dp["caddyfile"]))
    if dp["nginx"]["exists"]:
        L.append("- nginx 配置: [有] %s" % ", ".join(dp["nginx"]["evidence"]))
    else:
        L.append("- nginx 配置: [无]")
    if dp["deploy_scripts"]["exists"]:
        L.append("- deploy/rsync/backup 相关脚本: [有] %s" % ", ".join(dp["deploy_scripts"]["files"]))
    else:
        L.append("- deploy/rsync/backup 相关脚本: [无]")
    L.append("- .env.example: %s" % _yn(dp["env_example"]))
    L.append("- .env: %s" % ("存在（不报告内容）" if dp["env_exists"] else "不存在"))
    L.append("- 部署痕迹合计: %d 项" % dp["count"])
    L.append("")

    # 6. UI
    ui = results["ui"]
    L.append("## 6. UI (ui)")
    if ui["design_doc_actual"]:
        L.append("- DESIGN.md: [有]（实际文件名: %s）" % ui["design_doc_actual"])
    else:
        L.append("- DESIGN.md: [无]")
    if ui["frontend_features"]:
        L.append("- 前端特征: [有] %s" % "; ".join(ui["frontend_features"]))
    else:
        L.append("- 前端特征: [无]")
    for n in ui.get("unknown_notes") or []:
        L.append("- 附注: %s" % n)
    L.append("")

    # 7. 根目录卫生
    rh = results["root_hygiene"]
    L.append("## 7. 根目录卫生 (root_hygiene)")
    if rh["clean"]:
        L.append("- 干净: 是")
    else:
        if rh["suspicious_dirs"]:
            L.append("- ⚠ 可疑目录: %s" % ", ".join(rh["suspicious_dirs"]))
        if rh["screenshot_files"]:
            L.append("- ⚠ 根目录散落截图类文件: %s" % ", ".join(rh["screenshot_files"]))
        if rh["ds_store"]:
            L.append("- ⚠ 存在 .DS_Store")
        if rh["temp_files"]:
            L.append("- ⚠ 明显临时文件: %s" % ", ".join(rh["temp_files"]))
        L.append("- 干净: 否")
    L.append("")

    # 8. 就绪度
    rd = results["zedboot_readiness"]
    L.append("## 8. zedboot 就绪度 (zedboot_readiness)")
    L.append("- 管理文档已存在: %d/10 项" % rd["management_docs_present"])
    if rd["management_docs_present"] < rd["management_docs_total"]:
        L.append("  （注：%s）" % rd["design_md_applicable_note"])
    L.append("- 部署痕迹: %d 项" % rd["deploy_traces_present"])
    L.append("- 已具备完整管理五件套: %s"
             % ("是" if rd["has_full_management_five_piece"] else "否"))
    L.append("")

    # 9. 入库文件隐私泄露
    cs = results["committed_secrets"]
    L.append("## 9. 入库文件隐私泄露 (committed_secrets)")
    if cs["status"] == "git_error":
        note = (cs.get("unknown_notes") or ["无法探测"])[0]
        L.append("- 扫描: %s" % _unknown_str(note))
    else:
        if cs.get("workspace_scan"):
            L.append("- 非 git 仓库：降级扫描工作区文本文件 %d 个（命中即未入库风险）"
                     % (cs["scanned_count"] or 0))
        if cs["risk_found"]:
            L.append("- 风险: [有]")
            for item in cs["risk_items"]:
                L.append("- ⚠ %s: %s%s" % (item["type_label"], item["file"],
                                           _fmt_hit_loc(item)))
        elif cs.get("workspace_scan"):
            L.append("- 风险: [无]（工作区扫描未发现命中）")
        else:
            L.append("- 风险: [无]（共 %d 个 git 跟踪文件，未发现命中）"
                     % (cs["scanned_count"] or 0))
        mgmt = cs.get("management_doc_items") or []
        if mgmt:
            L.append("- 管理文档命中 %d 项（多为风险记录/占位说明等元描述，"
                     "不视为泄露，人工确认即可）:" % len(mgmt))
            for item in mgmt:
                L.append("  - %s: %s%s" % (item["type_label"], item["file"],
                                           _fmt_hit_loc(item)))
    L.append("")

    # 未能探测汇总
    L.append("## 未能探测（交由 AI 判断）")
    unknown = _collect_unknown(results)
    if not unknown:
        L.append("无")
    else:
        for sec, field, note in unknown:
            label = SECTION_LABELS.get(sec, sec)
            fld = "整体" if field == "*" else field
            L.append("- [%s] %s: %s" % (label, fld, note))

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


def render_json(results, root, ts):
    doc = {
        "audit_tool": "zedboot/scripts/audit.py",
        "scanned_path": os.path.abspath(root),
        "generated_at": ts,
        "sections": results,
        "unknown_items": [
            {"section": sec, "field": field, "note": note}
            for sec, field, note in _collect_unknown(results)
        ],
    }
    return json.dumps(_json_safe(doc), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="audit.py",
        description="zedboot 只读审计工具：机械探测旧项目的技术栈 / git / "
                    "管理文档 / 部署痕迹 / UI / 根目录卫生 / 入库文件隐私，"
                    "只做事实统计，不做主观判断（差距分析交给 AI）。"
                    "绝对只读，不写任何东西。",
        epilog="示例: python3 audit.py /path/to/project --json",
    )
    parser.add_argument("path", nargs="?", default=None,
                        help="要审计的项目路径（默认当前目录）")
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

    results = run_audit(root)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if args.json:
        print(render_json(results, root, ts))
    else:
        print(render_text(results, root, ts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
