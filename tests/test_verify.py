#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify.py 自动化测试套件（zedboot/scripts/verify.py 装后机械校验工具的测试）。

被测对象：装后机械校验（与 audit.py 的装前只读审计互补），逐项核对安装承诺：
  1. 管理文件齐备（10 项，init-workflow.md 第 1 步）
  2. 占位符替换干净（<项目名> 等中文占位符）
  3. .gitignore 含 .env / data/ / backups/ / docs/private/ 四项；.env 与
     docs/private/ 未被 git 跟踪
  4. pre-push 隐私闸门存在且可执行（含 core.hooksPath 影响探测）
  5. 部署产物（仅可部署项目，按项目模式区分容器栈 / 静态站 / 无部署）
  6. 入库文件私钥格式头快扫
输出逐项 PASS / FAIL / WARN / SKIP，存在 FAIL 则 exit 1，否则 exit 0。

fixture 一律在临时目录动态构造（真实 git 仓库 + 部署产物），仓库文件里不出现
任何静态 .env 文件、/Users/ 路径或私钥头字面量。所有 git 命令在临时仓库内
执行，并通过对子进程注入 GIT_CONFIG_GLOBAL=/dev/null + GIT_CONFIG_NOSYSTEM=1
隔离真实全局/系统 git 配置（本机与 CI 的全局 core.hooksPath 可能不同，测试
必须确定性，也不读写真实全局配置）。

钉住的回归点（对应 verify.py 两个修复）：
  - P0-1：未跟踪（未 git add、未被忽略）文件含中文占位符 → 必须 FAIL
    （扫描范围从「仅 git 已跟踪」扩大为 `git ls-files -co --exclude-standard`）；
  - P0-2：docs/private/ 下文件被 git 跟踪 → 必须 FAIL（.gitignore 检查从
    只查 .env 扩为四项 + docs/private 跟踪即事故）。

纯 Python 3 标准库（unittest），兼容 3.8+。
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY_PY = os.path.join(REPO_ROOT, "zedboot", "scripts", "verify.py")
VERIFY_TIMEOUT = 120
GIT_AVAILABLE = shutil.which("git") is not None


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _git_env():
    """git 子进程隔离环境：不读不写真实全局/系统 git 配置。

    本机全局可能设了 core.hooksPath（会让 pre-push 检查直接 WARN）、CI 可能
    没有全局配置——不隔离则同一 fixture 在不同机器上结论不同。把全局配置
    指到空设备 + 关掉系统级配置后，所有 git 结论只取决于临时仓库自身的
    local config，测试确定且不触碰真实配置。"""
    env = dict(os.environ)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    return env


def _git(root, *args):
    """在 root 内执行只读/本地 git 命令（fixture 构造用），失败即抛异常。"""
    p = subprocess.run(["git"] + list(args), cwd=root, capture_output=True,
                       text=True, timeout=60, env=_git_env())
    if p.returncode != 0:
        raise RuntimeError("git %s 失败: %s" % (args, p.stderr))
    return p


def _write(path, content):
    """动态写文件（含中间目录），仓库文件里不留静态敏感字面量。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def git_commit(repo, message="init", add=None, force=False):
    """显式 add + commit（-c 注入 user.name/email，不依赖全局 git 配置）。
    add=None 时 add -A；force=True 时 add -f（强制添加被 ignore 的文件）。"""
    if add is None:
        _git(repo, "add", "-A")
    else:
        cmd = ["add"] + (["-f"] if force else []) + ["--"] + list(add)
        _git(repo, *cmd)
    _git(repo, "-c", "user.name=test", "-c", "user.email=test@example.com",
         "commit", "-q", "-m", message)


def run_verify(target, json_mode=True):
    """以子进程方式运行 verify.py（注入隔离环境）；返回 CompletedProcess。"""
    cmd = [sys.executable, VERIFY_PY, target]
    if json_mode:
        cmd.append("--json")
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=VERIFY_TIMEOUT, env=_git_env())


def verify_json(target):
    """运行 verify.py --json，断言正常执行（rc∈{0,1}、无崩溃）并返回 (dict, proc)。"""
    p = run_verify(target, json_mode=True)
    if p.returncode not in (0, 1):
        raise AssertionError("verify 异常退出码 %d，stderr: %s"
                             % (p.returncode, p.stderr))
    if "Traceback" in p.stderr:
        raise AssertionError("verify 崩溃：%s" % p.stderr)
    return json.loads(p.stdout), p


def check_by_id(data, cid):
    """按 check id 取检查项；找不到即断言失败（避免静默漏检）。"""
    for c in data["checks"]:
        if c["id"] == cid:
            return c
    raise AssertionError("未找到检查 %s（实际: %s）"
                         % (cid, sorted(c["id"] for c in data["checks"])))


def snapshot_dir(root):
    """目录快照：返回 (子目录集合, {相对路径: 内容 sha256})，跳过 .git。
    口径同 test_audit.py（git 内部状态不属于被校验的项目文件）。"""
    dirs = set()
    files = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        rel = os.path.relpath(dirpath, root)
        if rel != ".":
            dirs.add(rel.replace(os.sep, "/"))
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            relf = os.path.relpath(full, root).replace(os.sep, "/")
            with open(full, "rb") as f:
                files[relf] = hashlib.sha256(f.read()).hexdigest()
    return (dirs, files)


# ---------------------------------------------------------------------------
# 动态 fixture 构造（临时目录内的真实 git 仓库）
# ---------------------------------------------------------------------------
# 首次 commit 显式纳入跟踪的公共文件（docs/private/ 与 .env 永不默认入库，
# 无论 .gitignore 内容如何——保证「缺 docs/private 条目」用例里 docs/private
# 仍保持未跟踪，不会因 add -A 误入库而叠加第二个 FAIL）。
TRACKED_COMMON = [
    "README.md", "AGENTS.md", "CHANGELOG.md", ".gitignore",
    "docs/README.md", "docs/guides/deployment.md",
    "docs/project/PROJECT_RULES.md", "docs/project/PROJECT_INDEX.md",
    "docs/project/PROJECT_STATE.md", "docs/project/TODO.md",
    "docs/project/DECISION_LOG.md", "archive/README.md",
]


def build_project(root, name="proj",
                  mode_line="项目模式：可部署",
                  gitignore_lines=(".env*", "!.env.example", "data/", "backups/",
                                   "docs/private/"),
                  flavor="container",
                  dockerfile=None,
                  entrypoint_script=True,
                  with_hook=True,
                  hook_executable=True):
    """构造一个「管理文件齐备 + .gitignore 四项 + .env 未跟踪 + pre-push 可执行
    + 全部部署产物 + docs/private 未跟踪」的容器栈 git 仓库；按参数变体出
    静态站 / 无部署 / 缺失件等 fixture。返回仓库路径。"""
    repo = os.path.join(root, name)
    os.makedirs(repo)
    _git(repo, "init", "-q", "-b", "main")

    # 10 项管理文件（verify.py MANAGEMENT_DOCS 正典十项）
    _write(os.path.join(repo, "README.md"), "# demo\n\ndemo project.\n")
    _write(os.path.join(repo, "AGENTS.md"),
           "# Agent Rules\n\nAct within the repository.\n")
    _write(os.path.join(repo, "CHANGELOG.md"),
           "# Changelog\n\n## 0.1.0\n\n- initial.\n")
    _write(os.path.join(repo, ".gitignore"),
           "\n".join(gitignore_lines) + "\n")
    _write(os.path.join(repo, ".env"),
           "DATABASE_URL=postgres://app:devpw@127.0.0.1:5432/app\n")
    _write(os.path.join(repo, "docs/README.md"), "# Docs\n")
    _write(os.path.join(repo, "docs/guides/deployment.md"), "# Deployment\n")
    _write(os.path.join(repo, "docs/project/PROJECT_RULES.md"), "# Rules\n")
    _write(os.path.join(repo, "docs/project/PROJECT_INDEX.md"),
           "# Project Index\n\n%s\n" % mode_line)
    _write(os.path.join(repo, "docs/project/PROJECT_STATE.md"), "# State\n")
    _write(os.path.join(repo, "docs/project/TODO.md"), "# TODO\n")
    _write(os.path.join(repo, "docs/project/DECISION_LOG.md"), "# Decisions\n")
    # docs/private/：gitignore 覆盖，永不默认入库（含运维真实值）
    _write(os.path.join(repo, "docs/private/ops.md"),
           "# Ops\n\nServer, users and secrets live here, never in git.\n")
    _write(os.path.join(repo, "docs/private/backup-manifest.conf"),
           "DEPLOYED=true\nSERVER=demo-host\n")
    _write(os.path.join(repo, "docs/private/deploy.env"),
           'PROJECT_NAME="demo"\nDEPLOY_USER="deploy-bot"\n'
           'REMOTE_DIR="/opt/demo"\nSERVER_IP="198.51.100.10"\n'
           'DEPLOY_KEY="~/.ssh/demo_deploy"\n')
    _write(os.path.join(repo, "archive/README.md"), "# Archive\n")
    os.makedirs(os.path.join(repo, "data"))
    os.makedirs(os.path.join(repo, "backups"))

    tracked = list(TRACKED_COMMON)
    if flavor == "container":
        _write(os.path.join(repo, "deploy-rsync.sh"),
               "#!/bin/sh\nrsync -a --delete ./ host:/srv/app\n")
        _write(os.path.join(repo, "docker-compose.yml"),
               "services:\n  app:\n    build: .\n")
        _write(os.path.join(repo, ".dockerignore"), ".env\ndata/\nbackups/\n")
        _write(os.path.join(repo, "backup.sh"),
               "#!/bin/sh\nrsync -a data/ host:/backups\n")
        _write(os.path.join(repo, ".env.example"), "DATABASE_URL=\n")
        if dockerfile is None:
            # 默认 python/nextjs 风格：Dockerfile 引用独立 entrypoint 脚本
            dockerfile = ("FROM python:3.11-slim\n"
                          "COPY docker-entrypoint.sh /usr/local/bin/\n"
                          "ENTRYPOINT [\"docker-entrypoint.sh\"]\n")
        _write(os.path.join(repo, "Dockerfile"), dockerfile)
        if entrypoint_script:
            _write(os.path.join(repo, "docker-entrypoint.sh"),
                   "#!/bin/sh\nexec \"$@\"\n")
        tracked += ["deploy-rsync.sh", "docker-compose.yml", ".dockerignore",
                    "backup.sh", ".env.example", "Dockerfile"]
        if entrypoint_script:
            tracked.append("docker-entrypoint.sh")
    elif flavor == "static":
        _write(os.path.join(repo, "deploy-rsync-static.sh"),
               "#!/bin/sh\nrsync -a --delete public/ host:/var/www\n")
        tracked.append("deploy-rsync-static.sh")
    # flavor == "no_deploy"：不落任何部署产物

    git_commit(repo, add=tracked)

    if with_hook:
        hook = os.path.join(repo, ".git", "hooks", "pre-push")
        _write(hook, "#!/bin/sh\n# zedboot privacy gate\n")
        if hook_executable:
            os.chmod(hook, 0o755)
    return repo


# ---------------------------------------------------------------------------
# 用例 1/2/14a/15：完整容器栈项目全 PASS、缺件 FAIL、JSON 形状、只读性
# ---------------------------------------------------------------------------
@unittest.skipUnless(GIT_AVAILABLE, "需要 git 构建动态仓库 fixture")
class TestFullContainerProject(unittest.TestCase):
    """装全的容器栈项目：10 管理文件 + .gitignore 四项 + .env 未跟踪 +
    pre-push 可执行 + 全部部署产物 + docs/private 未跟踪 → 全 PASS，exit 0。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.root = self._td.name

    def test_full_container_project_all_pass(self):
        """用例 1：装全的容器栈项目全 PASS，exit 0。"""
        repo = build_project(self.root)
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(data["exit_code"], 0)
        self.assertEqual(data["summary"],
                         {"PASS": 32, "FAIL": 0, "WARN": 0, "SKIP": 0,
                          "total": 32})
        for cid in ("placeholder", "gitignore:.env", "gitignore:data",
                    "gitignore:backups", "gitignore:docs/private",
                    "gitignore_effective",
                    "env_not_tracked", "private_not_tracked", "pre_push_hook",
                    "project_mode", "deploy:compose", "deploy:dockerfile",
                    "deploy:entrypoint", "deploy:env_example", "privacy_scan"):
            self.assertEqual(check_by_id(data, cid)["status"], "PASS", cid)

    def test_missing_management_file_fails(self):
        """用例 2：缺一个管理文件 → 对应 mgmt: 检查 FAIL，exit 1。"""
        repo = build_project(self.root)
        os.unlink(os.path.join(repo, "CHANGELOG.md"))
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(data["exit_code"], 1)
        self.assertEqual(check_by_id(data, "mgmt:CHANGELOG.md")["status"],
                         "FAIL")
        self.assertGreaterEqual(data["summary"]["FAIL"], 1)

    def test_json_output_shape(self):
        """用例 14（前半）：--json 输出是合法 JSON，关键字段存在且结构完整。"""
        repo = build_project(self.root)
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(data["verify_tool"], "zedboot/scripts/verify.py")
        self.assertEqual(data["scanned_path"], os.path.abspath(repo))
        self.assertRegex(data["generated_at"],
                         r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        self.assertEqual(data["git"]["status"], "repo")
        self.assertIn("mode", data["project_mode"])
        self.assertIn("source", data["project_mode"])
        self.assertEqual(data["scan"]["scope"], "tracked")
        self.assertIsInstance(data["checks"], list)
        for c in data["checks"]:
            self.assertEqual(set(c.keys()),
                             {"id", "name", "status", "detail", "section",
                              "items"}, c["id"])
        self.assertEqual(data["summary"]["total"], len(data["checks"]))
        self.assertEqual(data["summary"]["FAIL"] > 0, data["exit_code"] == 1)

    def test_read_only_snapshot_unchanged(self):
        """用例 15：verify 运行前后 fixture 目录快照（文件名+内容 hash）零变化。"""
        repo = build_project(self.root)
        before = snapshot_dir(repo)
        self.assertEqual(run_verify(repo, json_mode=False).returncode, 0)
        data, _ = verify_json(repo)
        self.assertEqual(data["exit_code"], 0)
        after = snapshot_dir(repo)
        self.assertEqual(after, before, "verify 修改了 fixture 目录")


# ---------------------------------------------------------------------------
# 用例 3/4/5：占位符残留（含 P0-1 未跟踪文件回归钉）
# ---------------------------------------------------------------------------
@unittest.skipUnless(GIT_AVAILABLE, "需要 git 构建动态仓库 fixture")
class TestPlaceholderScan(unittest.TestCase):
    """中文占位符残留检查：已提交 / 未跟踪未忽略 / 被忽略三种情形。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.root = self._td.name

    def test_committed_placeholder_fails(self):
        """用例 3：已提交文件含 <项目名> → placeholder FAIL，exit 1。"""
        repo = build_project(self.root)
        _write(os.path.join(repo, "README.md"),
               "# demo\n\nproject name: <项目名>\n")
        git_commit(repo, message="add placeholder", add=["README.md"])
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 1)
        ph = check_by_id(data, "placeholder")
        self.assertEqual(ph["status"], "FAIL")
        self.assertTrue(
            any(it["file"] == "README.md" and it["match"] == "<项目名>"
                for it in ph["items"]), ph["items"])

    def test_untracked_placeholder_fails(self):
        """用例 4（P0-1 回归钉）：未 git add、未被忽略的文件含 <项目名>
        → 扫描范围必须覆盖（ls-files -co --exclude-standard）→ FAIL，exit 1。
        旧实现只扫已跟踪文件会漏掉它。"""
        repo = build_project(self.root)
        _write(os.path.join(repo, "scratch.txt"), "release: <项目名>\n")
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 1)
        self.assertGreaterEqual(data["scan"]["untracked_count"], 1)
        ph = check_by_id(data, "placeholder")
        self.assertEqual(ph["status"], "FAIL")
        self.assertTrue(
            any(it["file"] == "scratch.txt" and it["match"] == "<项目名>"
                for it in ph["items"]), ph["items"])

    def test_gitignored_untracked_placeholder_not_flagged(self):
        """用例 5：被 .gitignore 排除的未跟踪文件含 <项目名> → 不因此 FAIL
        （排除语义正确：data/ 被忽略，文件不进入扫描范围），整体 exit 0。"""
        repo = build_project(self.root)
        _write(os.path.join(repo, "data", "scratch.txt"),
               "release: <项目名>\n")
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(data["exit_code"], 0)
        self.assertEqual(data["summary"]["FAIL"], 0)
        self.assertEqual(check_by_id(data, "placeholder")["status"], "PASS")


# ---------------------------------------------------------------------------
# 用例 6/7/8：.gitignore 四项与 .env / docs/private 跟踪状态
# ---------------------------------------------------------------------------
@unittest.skipUnless(GIT_AVAILABLE, "需要 git 构建动态仓库 fixture")
class TestGitignoreAndTracking(unittest.TestCase):
    """.gitignore 四项覆盖、.env 未跟踪、docs/private 未跟踪（P0-2）。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.root = self._td.name

    def test_gitignore_missing_data_fails(self):
        """用例 6a：.gitignore 缺 data/ 条目 → gitignore:data FAIL，exit 1；
        其余三项仍 PASS。"""
        repo = build_project(
            self.root, gitignore_lines=(".env*", "!.env.example", "backups/",
                                        "docs/private/"))
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(check_by_id(data, "gitignore:data")["status"], "FAIL")
        for cid in ("gitignore:.env", "gitignore:backups",
                    "gitignore:docs/private"):
            self.assertEqual(check_by_id(data, cid)["status"], "PASS", cid)

    def test_gitignore_missing_docs_private_fails(self):
        """用例 6b：.gitignore 缺 docs/private/ 条目 → gitignore:docs/private
        FAIL，exit 1；docs/private 文件未被忽略但内容干净 → 占位符/跟踪检查
        不叠加 FAIL。"""
        repo = build_project(
            self.root, gitignore_lines=(".env*", "!.env.example", "data/",
                                        "backups/"))
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(check_by_id(data, "gitignore:docs/private")["status"],
                         "FAIL")
        self.assertEqual(check_by_id(data, "placeholder")["status"], "PASS")
        self.assertEqual(check_by_id(data, "private_not_tracked")["status"],
                         "PASS")

    def test_env_tracked_fails(self):
        """用例 7：.env 被 git 跟踪 → env_not_tracked FAIL，exit 1。"""
        repo = build_project(self.root)
        git_commit(repo, message="track env", add=[".env"], force=True)
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 1)
        env = check_by_id(data, "env_not_tracked")
        self.assertEqual(env["status"], "FAIL")
        self.assertIn("已被 git 跟踪", env["detail"])

    def test_docs_private_tracked_fails(self):
        """用例 8（P0-2 回归钉）：docs/private/ 下文件被 git 跟踪
        → private_not_tracked FAIL（运维真实值入库即事故），exit 1。"""
        repo = build_project(self.root)
        git_commit(repo, message="track private",
                   add=["docs/private/ops.md"], force=True)
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 1)
        priv = check_by_id(data, "private_not_tracked")
        self.assertEqual(priv["status"], "FAIL")
        # 被跟踪文件必须在检查结果中被点名（当前实现内嵌在 detail，
        # 历史实现放在 items——两种都接受，钉住的是「跟踪即 FAIL + 点名」）
        named = [priv["detail"]] + [it.get("file", "") for it in priv["items"]]
        self.assertTrue(any("docs/private/ops.md" in str(x) for x in named),
                        "被跟踪文件应在检查结果中点名")

    def test_gitignore_literal_env_not_enough(self):
        """.gitignore 只写字面 .env（无 .env*）：只护住单文件，覆盖全部
        .env* 变体不成立 → gitignore:.env FAIL，exit 1。"""
        repo = build_project(self.root, name="literalenv",
                             gitignore_lines=(".env", "!.env.example", "data/",
                                              "backups/", "docs/private/"))
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(check_by_id(data, "gitignore:.env")["status"], "FAIL")

    def test_gitignore_env_star_covers(self):
        """.gitignore 写 .env*：覆盖全部变体 → gitignore:.env PASS；
        .env / .env.local / .env.production 探针全部实际被忽略 →
        gitignore_effective PASS。"""
        repo = build_project(self.root, name="envstar")
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(data["exit_code"], 0)
        self.assertEqual(check_by_id(data, "gitignore:.env")["status"], "PASS")
        self.assertEqual(check_by_id(data, "gitignore_effective")["status"],
                         "PASS")


# ---------------------------------------------------------------------------
# 用例 9/10：pre-push 隐私闸门
# ---------------------------------------------------------------------------
@unittest.skipUnless(GIT_AVAILABLE, "需要 git 构建动态仓库 fixture")
class TestGitignoreEffective(unittest.TestCase):
    """3b 生效语义层（git check-ignore）：条目存在但被反向规则抵消 → FAIL。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.root = self._td.name

    def test_env_negation_effective_fails(self):
        """P1 回归钉：.gitignore 写 .env* 又写 !.env —— 条目检查 PASS，
        但 git 实际不忽略 .env → gitignore_effective 必须 FAIL，exit 1。"""
        repo = build_project(self.root, name="negenv",
                             gitignore_lines=(".env*", "!.env.example", "data/",
                                              "backups/", "docs/private/",
                                              "!.env"))
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(check_by_id(data, "gitignore:.env")["status"], "PASS")
        eff = check_by_id(data, "gitignore_effective")
        self.assertEqual(eff["status"], "FAIL")
        self.assertIn(".env", eff["detail"])

    def test_effective_pass_on_normal_project(self):
        """正向对照：四项齐全且无反向规则 → gitignore_effective PASS。"""
        repo = build_project(self.root, name="normproj")
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(check_by_id(data, "gitignore_effective")["status"],
                         "PASS")

    def test_env_variant_probe_not_ignored_fails(self):
        """.gitignore 只有字面 .env：.env.local / .env.production 探针未被
        忽略 → gitignore_effective FAIL 并在 detail 点名变体，exit 1。"""
        repo = build_project(self.root, name="variantprobe",
                             gitignore_lines=(".env", "!.env.example", "data/",
                                              "backups/", "docs/private/"))
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 1)
        eff = check_by_id(data, "gitignore_effective")
        self.assertEqual(eff["status"], "FAIL")
        self.assertIn(".env.local", eff["detail"])
        self.assertIn(".env.production", eff["detail"])


class TestPrePushHook(unittest.TestCase):
    """pre-push 缺失 / 不可执行 → FAIL；core.hooksPath 非空 → WARN。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.root = self._td.name

    def test_pre_push_hook_missing_fails(self):
        """用例 9a：.git/hooks/pre-push 缺失 → FAIL（未安装），exit 1。"""
        repo = build_project(self.root, with_hook=False)
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 1)
        hk = check_by_id(data, "pre_push_hook")
        self.assertEqual(hk["status"], "FAIL")
        self.assertIn("不存在", hk["detail"])

    def test_pre_push_hook_not_executable_fails(self):
        """用例 9b：pre-push 存在但不可执行（无 +x）→ FAIL，exit 1。"""
        repo = build_project(self.root, hook_executable=False)
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 1)
        hk = check_by_id(data, "pre_push_hook")
        self.assertEqual(hk["status"], "FAIL")
        self.assertIn("不可执行", hk["detail"])

    def test_core_hooks_path_warns(self):
        """用例 10：core.hooksPath 非空 → pre_push_hook WARN（需人工确认），
        不判 FAIL，exit 0。用仓库局部 git config 设置，隔离环境确保不读写
        真实全局配置。"""
        repo = build_project(self.root)
        _git(repo, "config", "core.hooksPath", "shared/hooks")
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(data["exit_code"], 0)
        hk = check_by_id(data, "pre_push_hook")
        self.assertEqual(hk["status"], "WARN")
        self.assertIn("core.hooksPath", hk["detail"])


# ---------------------------------------------------------------------------
# 用例 11/12/13：部署产物（按项目模式分流）
# ---------------------------------------------------------------------------
@unittest.skipUnless(GIT_AVAILABLE, "需要 git 构建动态仓库 fixture")
class TestDeployModes(unittest.TestCase):
    """静态站 → 容器件 SKIP；go 栈 → entrypoint PASS；python/nextjs 缺
    entrypoint → FAIL；无部署交付 → 部署检查 SKIP。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.root = self._td.name

    def test_static_project_container_checks_skip(self):
        """用例 11：项目模式含「静态」，有 deploy-rsync-static.sh + 公共件、
        无容器件 → 容器件检查 SKIP，无容器检查项，exit 0。"""
        repo = build_project(self.root, mode_line="项目模式：静态站",
                             flavor="static")
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(data["exit_code"], 0)
        self.assertEqual(data["summary"]["FAIL"], 0)
        self.assertEqual(check_by_id(data, "project_mode")["status"], "PASS")
        self.assertEqual(check_by_id(data, "deploy:container_skip")["status"],
                         "SKIP")
        self.assertEqual(check_by_id(data, "deploy:rsync_script")["status"],
                         "PASS")
        self.assertFalse(
            any(c["id"].startswith("deploy:compose")
                or c["id"].startswith("deploy:dockerfile")
                or c["id"] == "deploy:entrypoint"
                for c in data["checks"]),
            "静态站不应出现容器件检查")

    def test_self_contained_entrypoint_pass(self):
        """用例 12（go 栈）：Dockerfile 自含 ENTRYPOINT 且不引用独立脚本、
        无 docker-entrypoint.sh → deploy:entrypoint PASS，exit 0。"""
        repo = build_project(
            self.root,
            dockerfile='FROM golang:1.22\nENTRYPOINT ["/app/server"]\n',
            entrypoint_script=False)
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(data["exit_code"], 0)
        ep = check_by_id(data, "deploy:entrypoint")
        self.assertEqual(ep["status"], "PASS")
        self.assertIn("自含 ENTRYPOINT", ep["detail"])

    def test_missing_entrypoint_script_fails(self):
        """用例 12（python/nextjs 风格）：Dockerfile 引用 docker-entrypoint.sh
        但文件缺失 → deploy:entrypoint FAIL，exit 1。"""
        repo = build_project(self.root, entrypoint_script=False)
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 1)
        ep = check_by_id(data, "deploy:entrypoint")
        self.assertEqual(ep["status"], "FAIL")
        self.assertIn("docker-entrypoint.sh", ep["detail"])

    def test_no_deploy_project_deploy_checks_skip(self):
        """用例 13：项目模式=无部署交付 → 部署产物检查 SKIP，exit 0。"""
        repo = build_project(self.root, mode_line="项目模式：无部署交付",
                             flavor="no_deploy")
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(data["exit_code"], 0)
        self.assertEqual(data["summary"]["FAIL"], 0)
        self.assertEqual(check_by_id(data, "project_mode")["status"], "PASS")
        self.assertEqual(check_by_id(data, "deploy:skip")["status"], "SKIP")

    def test_deploy_env_missing_fails(self):
        """部署项目缺 docs/private/deploy.env → deploy:deploy_env FAIL，
        文案指引 assets/project/deploy.env.tmpl，exit 1。"""
        repo = build_project(self.root, name="nodeployenv")
        os.unlink(os.path.join(repo, "docs/private/deploy.env"))
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 1)
        de = check_by_id(data, "deploy:deploy_env")
        self.assertEqual(de["status"], "FAIL")
        self.assertIn("deploy.env.tmpl", de["detail"])

    def test_deploy_env_present_passes(self):
        """部署项目含 docs/private/deploy.env → deploy:deploy_env PASS，
        exit 0（只查存在，不读内容）。"""
        repo = build_project(self.root, name="withdeployenv")
        data, p = verify_json(repo)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(data["exit_code"], 0)
        self.assertEqual(check_by_id(data, "deploy:deploy_env")["status"],
                         "PASS")


# ---------------------------------------------------------------------------
# 用例 14b：非 git 目录降级路径
# ---------------------------------------------------------------------------
class TestCliDegraded(unittest.TestCase):
    """非 git 目录：verify 不崩溃，降级为工作区扫描（WARN/SKIP/FAIL 语义）。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.root = self._td.name

    def test_non_git_directory_degraded_no_crash(self):
        """用例 14（后半）：非 git 目录降级路径不崩溃——JSON 可解析、
        无 Traceback、git 判 not_repo、扫描降级 workspace_degraded、
        无命中时 placeholder/privacy 判 WARN、git 相关检查 SKIP。"""
        d = os.path.join(self.root, "plain")
        os.makedirs(d)
        _write(os.path.join(d, "notes.txt"), "nothing here\n")
        data, p = verify_json(d)
        self.assertEqual(p.returncode, 1)  # 管理文件全缺 → 存在 FAIL
        self.assertNotIn("Traceback", p.stderr)
        self.assertEqual(data["git"]["status"], "not_repo")
        self.assertEqual(data["scan"]["scope"], "workspace_degraded")
        self.assertEqual(check_by_id(data, "placeholder")["status"], "WARN")
        self.assertEqual(check_by_id(data, "privacy_scan")["status"], "WARN")
        for cid in ("env_not_tracked", "private_not_tracked", "pre_push_hook"):
            self.assertEqual(check_by_id(data, cid)["status"], "SKIP", cid)

    def test_non_git_directory_placeholder_still_fails(self):
        """降级路径下工作区文件含中文占位符仍判 FAIL（有命中不因降级而放过）。"""
        d = os.path.join(self.root, "plain2")
        os.makedirs(d)
        _write(os.path.join(d, "notes.txt"), "name: <项目名>\n")
        data, p = verify_json(d)
        self.assertEqual(check_by_id(data, "placeholder")["status"], "FAIL")
        self.assertEqual(p.returncode, 1)


if __name__ == "__main__":
    unittest.main()
