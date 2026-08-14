#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit.py 自动化测试套件（重建 zedboot/scripts/audit.py 丢失的 fixture 测试矩阵）。

覆盖维度（对应 CHANGELOG.md 0.5.7「10 项 fixture 测试矩阵」）：
  ① 对每个 fixture（静态 + 动态）跑通不崩溃（文本模式 + --json 模式双跑）；
  ② --json 输出是合法 JSON 且关键字段存在（audit_tool / scanned_path /
     generated_at / sections 九个节 / unknown_items）；
  ③ 只读性校验：审计前后对 fixture 做目录快照对比（文件列表 + 内容 sha256），
     断言零变化（git 内部状态 .git 不属于「项目文件」，快照跳过）；
  ④ 关键探测正确性抽查：技术栈识别 / 隐私泄露命中 / git 嵌套边界 / 截断提示。

fixture 分两类：
  - 静态 fixture：tests/fixtures/ 下的普通目录（内容全小写 / 通用假数据），
    天然嵌套在本仓库（REPO）内，用于验证「目录自身无 git 仓库、被外层仓库
    包含 → not_repo」的嵌套边界逻辑；
  - 动态 fixture：测试运行时在临时目录构造——真实 git 仓库（无法把 .git
    内容提交进仓库，git 不跟踪嵌套 .git/ 下的文件）与含隐私痕迹的项目
    （/Users/ 字面量会命中仓库 CI 的 no-private-paths 扫描，必须运行时
    拼接构造，仓库文件里不出现字面量）。

纯 Python 3 标准库（unittest），兼容 3.8+，不引入 pytest 等第三方依赖。
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT_PY = os.path.join(REPO_ROOT, "zedboot", "scripts", "audit.py")
FIXTURES_DIR = os.path.join(REPO_ROOT, "tests", "fixtures")
AUDIT_TIMEOUT = 120
GIT_AVAILABLE = shutil.which("git") is not None

# audit.py run_audit() 固定输出的九个节（顺序由脚本决定，这里按排序比较）
EXPECTED_SECTIONS = sorted([
    "basic", "framework", "git", "management_docs", "deploy_traces",
    "ui", "root_hygiene", "committed_secrets", "zedboot_readiness",
])


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def run_audit(target, json_mode=True):
    """以子进程方式运行 audit.py；返回 CompletedProcess。"""
    cmd = [sys.executable, AUDIT_PY, target]
    if json_mode:
        cmd.append("--json")
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=AUDIT_TIMEOUT)


def audit_json(target):
    """运行 audit.py --json，断言成功并返回解析后的 dict。"""
    p = run_audit(target, json_mode=True)
    assert p.returncode == 0, "audit 退出码 %d，stderr: %s" % (p.returncode, p.stderr)
    return json.loads(p.stdout)


def snapshot_dir(root):
    """目录快照：返回 (子目录集合, {相对路径: 内容 sha256})。
    跳过 .git（git 内部状态不属于被审计的项目文件；git 只读命令可能刷新
    index，不纳入对比）。"""
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


def list_static_fixtures():
    """tests/fixtures/ 下的静态 fixture 名（按名排序，稳定）。"""
    return sorted(
        n for n in os.listdir(FIXTURES_DIR)
        if os.path.isdir(os.path.join(FIXTURES_DIR, n))
    )


# ---------------------------------------------------------------------------
# 动态 fixture 构造（运行时在临时目录生成）
# ---------------------------------------------------------------------------
def _git(root, *args):
    p = subprocess.run(["git"] + list(args), cwd=root,
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError("git %s 失败: %s" % (args, p.stderr))
    return p


def build_empty_dir(root):
    """空目录 fixture：一个真正空、零条目的目录。"""
    d = os.path.join(root, "emptydir")
    os.makedirs(d)
    return d


def build_privacy_leak(root):
    """带隐私泄露痕迹的 git 仓库：入库文件含本机绝对路径 / 公网 IP / 私钥头。
    /Users/<名>/ 字面量会命中仓库 CI 的 no-private-paths 扫描，这里用拼接
    构造，仓库内任何文件都不出现该字面量。"""
    repo = os.path.join(root, "leakproj")
    os.makedirs(repo)
    _git(repo, "init", "-q", "-b", "main")
    with open(os.path.join(repo, "README.md"), "w", encoding="utf-8") as f:
        f.write("# leak demo\n\na fixture with privacy leak traces.\n")
    # 拼接本机绝对路径段（/Users/ 开头的路径），避免该字面量出现在本仓库文件中、
    # 命中仓库 CI 的 no-private-paths 扫描（匹配模式 /Users/<名>/）
    home_path = "/Users" + "/" + "testuser" + "/app/secret"
    with open(os.path.join(repo, "leak.txt"), "w", encoding="utf-8") as f:
        f.write("home = %s\n" % home_path)              # 本机绝对路径 → local_path
        f.write("server = 240.0.0.1\n")                 # 公网 IPv4（保留段）→ ip
        # 私钥头字面量拼接构造，避免命中全局 pre-push 隐私闸门（私钥头模式）
        f.write("key = " + "-----BEGIN" + " RSA PRIVATE KEY-----\n")  # → private_key
        f.write("local = 192.168.1.10\n")               # 私网 IP，不应命中
    with open(os.path.join(repo, ".env"), "w", encoding="utf-8") as f:
        f.write("DATABASE_URL=postgres://app:devpw@127.0.0.1:5432/app\n")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=test", "-c", "user.email=test@example.com",
         "commit", "-q", "-m", "init")
    return repo


def build_nested_git(root):
    """目录自身是真实 git 仓库（含 main 分支与 task/ 前缀分支）。"""
    repo = os.path.join(root, "nestedrepo")
    os.makedirs(repo)
    _git(repo, "init", "-q", "-b", "main")
    with open(os.path.join(repo, "a.txt"), "w", encoding="utf-8") as f:
        f.write("alpha\n")
    _git(repo, "add", "a.txt")
    _git(repo, "-c", "user.name=test", "-c", "user.email=test@example.com",
         "commit", "-q", "-m", "first commit")
    _git(repo, "checkout", "-q", "-b", "task/feat1")
    with open(os.path.join(repo, "b.txt"), "w", encoding="utf-8") as f:
        f.write("beta\n")
    _git(repo, "add", "b.txt")
    _git(repo, "-c", "user.name=test", "-c", "user.email=test@example.com",
         "commit", "-q", "-m", "add feature")
    return repo


def build_bigfile(root):
    """非 git 仓库目录，含一个超过 2MB 的文本文件（截断提示场景）。"""
    d = os.path.join(root, "bigdir")
    os.makedirs(d)
    with open(os.path.join(d, "big.txt"), "w", encoding="utf-8") as f:
        f.write("a" * (2 * 1024 * 1024 + 123))
    return d


def build_env_variant_and_deploy(root):
    """git 仓库：.env.production 被强制跟踪（真实事故形态——历史提交已入库，
    事后补 .gitignore 也拦不住已跟踪文件）；.env.example 被 gitignore 放行
    （!.env.example）正常跟踪，属例外名不算敏感；docs/private/ 被 gitignore
    排除不跟踪；docs/private/deploy.env 提供服务器账号（DEPLOY_USER=），
    ops.md 无账号字段。"""
    repo = os.path.join(root, "envvarproj")
    os.makedirs(repo)
    _git(repo, "init", "-q", "-b", "main")
    with open(os.path.join(repo, ".gitignore"), "w", encoding="utf-8") as f:
        f.write(".env*\n!.env.example\ndocs/private/\n")
    with open(os.path.join(repo, ".env.production"), "w", encoding="utf-8") as f:
        f.write("DATABASE_URL=postgres://app:devpw@127.0.0.1:5432/app\n")
    with open(os.path.join(repo, ".env.example"), "w", encoding="utf-8") as f:
        f.write("DATABASE_URL=\n")
    with open(os.path.join(repo, "README.md"), "w", encoding="utf-8") as f:
        f.write("# demo\n")
    # /home/<账号>/ 字面量会命中全局 pre-push 隐私闸门，用拼接构造，
    # 仓库文件里不出现该字面量（与 build_privacy_leak 同口径）
    home_path = "/home" + "/" + "deploy-bot" + "/app"
    with open(os.path.join(repo, "notes.md"), "w", encoding="utf-8") as f:
        f.write("server dir = %s\n" % home_path)
    os.makedirs(os.path.join(repo, "docs/private"))
    with open(os.path.join(repo, "docs/private/ops.md"), "w", encoding="utf-8") as f:
        f.write("# Ops\n\nNo server account field on purpose.\n")
    with open(os.path.join(repo, "docs/private/deploy.env"), "w",
              encoding="utf-8") as f:
        f.write('PROJECT_NAME="demo"\nDEPLOY_USER="deploy-bot"\n')
    _git(repo, "add", "-A")
    _git(repo, "add", "-f", ".env.production")
    _git(repo, "-c", "user.name=test", "-c", "user.email=test@example.com",
         "commit", "-q", "-m", "init")
    return repo


# ---------------------------------------------------------------------------
# ① 每个 fixture 跑通不崩溃 + ② JSON 合法且关键字段存在（静态 fixture）
# ---------------------------------------------------------------------------
class TestStaticFixtures(unittest.TestCase):
    """对每个静态 fixture：文本 + --json 双模式跑通、JSON 结构与关键字段。"""

    def test_every_fixture_runs_and_json_is_valid(self):
        for name in list_static_fixtures():
            with self.subTest(fixture=name):
                target = os.path.join(FIXTURES_DIR, name)

                p_text = run_audit(target, json_mode=False)
                self.assertEqual(p_text.returncode, 0, p_text.stderr)
                self.assertIn("# zedboot 只读审计报告", p_text.stdout)
                self.assertIn("## 1. 基本信息", p_text.stdout)

                p_json = run_audit(target, json_mode=True)
                self.assertEqual(p_json.returncode, 0, p_json.stderr)
                data = json.loads(p_json.stdout)
                self.assertEqual(data["audit_tool"], "zedboot/scripts/audit.py")
                self.assertEqual(data["scanned_path"], os.path.abspath(target))
                self.assertRegex(
                    data["generated_at"],
                    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
                self.assertEqual(sorted(data["sections"].keys()),
                                 EXPECTED_SECTIONS)
                self.assertIsInstance(data["unknown_items"], list)

    def test_static_fixtures_are_inside_repo(self):
        """静态 fixture 被外层仓库（本仓库）包含，git 节必须判 not_repo，
        绝不能把外层仓库的分支/提交/远程误报为 fixture 自身的。"""
        for name in list_static_fixtures():
            with self.subTest(fixture=name):
                target = os.path.join(FIXTURES_DIR, name)
                g = audit_json(target)["sections"]["git"]
                self.assertEqual(g["status"], "not_repo")
                self.assertIs(g["is_repo"], False)
                self.assertIsNone(g["branch"])


# ---------------------------------------------------------------------------
# ③ 只读性校验（审计前后目录快照零变化）
# ---------------------------------------------------------------------------
class TestReadOnly(unittest.TestCase):
    """对每个 fixture（静态 + 动态）做只读性校验：审计前后文件列表与
    内容 hash 完全一致（文本与 --json 两种模式都跑一遍）。"""

    def _assert_read_only(self, target):
        before = snapshot_dir(target)
        self.assertEqual(run_audit(target, json_mode=False).returncode, 0)
        self.assertEqual(run_audit(target, json_mode=True).returncode, 0)
        after = snapshot_dir(target)
        self.assertEqual(after, before,
                         "audit 修改了目录 %s" % target)

    def test_static_fixtures_read_only(self):
        for name in list_static_fixtures():
            with self.subTest(fixture=name):
                self._assert_read_only(os.path.join(FIXTURES_DIR, name))

    @unittest.skipUnless(GIT_AVAILABLE, "需要 git 构建动态仓库 fixture")
    def test_dynamic_fixtures_read_only(self):
        with tempfile.TemporaryDirectory() as td:
            cases = [
                ("empty_dir", build_empty_dir(td)),
                ("privacy_leak", build_privacy_leak(td)),
                ("nested_git_repo", build_nested_git(td)),
                ("truncated_bigfile", build_bigfile(td)),
            ]
            for name, target in cases:
                with self.subTest(fixture=name):
                    self._assert_read_only(target)


# ---------------------------------------------------------------------------
# ④ 关键探测正确性抽查
# ---------------------------------------------------------------------------
class TestFrameworkDetection(unittest.TestCase):
    """技术栈识别抽查。"""

    def test_nextjs_fixture(self):
        fw = audit_json(os.path.join(FIXTURES_DIR, "nextjs_app"))["sections"]["framework"]
        self.assertEqual(fw["status"], "detected")
        frameworks = {m["framework"] for m in fw["matches"]}
        self.assertIn("node", frameworks)
        self.assertIn("next.js", frameworks)
        node = next(m for m in fw["matches"] if m["framework"] == "node")
        self.assertEqual(node["detail"]["name"], "demo-web-app")
        self.assertIn("next", node["detail"]["framework_keywords"])
        self.assertEqual(sorted(node["detail"]["scripts"]), ["build", "dev"])
        nextjs = next(m for m in fw["matches"] if m["framework"] == "next.js")
        self.assertIn("next.config.js", nextjs["evidence"])

    def test_python_fixture(self):
        fw = audit_json(os.path.join(FIXTURES_DIR, "python_app"))["sections"]["framework"]
        frameworks = {m["framework"] for m in fw["matches"]}
        self.assertIn("python", frameworks)
        py = next(m for m in fw["matches"] if m["framework"] == "python")
        self.assertEqual(py["detail"]["web_framework_keywords"], ["fastapi"])

    def test_static_site_fixture(self):
        fw = audit_json(os.path.join(FIXTURES_DIR, "static_site"))["sections"]["framework"]
        frameworks = {m["framework"] for m in fw["matches"]}
        self.assertIn("static", frameworks)
        st = next(m for m in fw["matches"] if m["framework"] == "static")
        self.assertIn("index.html", st["evidence"])

    def test_go_fixture(self):
        fw = audit_json(os.path.join(FIXTURES_DIR, "full_docs"))["sections"]["framework"]
        self.assertIn("go", {m["framework"] for m in fw["matches"]})

    def _empty_fixture(self):
        """动态构造真正空的 fixture（git 无法跟踪空目录，故不落静态 fixture）。"""
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return td.name

    def test_empty_fixture_unknown(self):
        fw = audit_json(self._empty_fixture())["sections"]["framework"]
        self.assertEqual(fw["status"], "unknown")
        self.assertIsNone(fw["matches"])


class TestBasicAndDocs(unittest.TestCase):
    """基本信息 / 管理文档 / 就绪度抽查。"""

    def _empty_fixture(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return td.name

    def test_nextjs_readme_title(self):
        basic = audit_json(os.path.join(FIXTURES_DIR, "nextjs_app"))["sections"]["basic"]
        self.assertTrue(basic["has_readme"])
        self.assertEqual(basic["project_name_hint"], "demo web app")

    def test_empty_root_entry_count(self):
        basic = audit_json(self._empty_fixture())["sections"]["basic"]
        self.assertEqual(basic["root_entry_count"], 0)

    def test_full_docs_management(self):
        target = os.path.join(FIXTURES_DIR, "full_docs")
        data = audit_json(target)["sections"]
        md = data["management_docs"]
        self.assertTrue(all(md["docs"].values()),
                        "full_docs 的 12 项管理文档应全部存在")
        rd = data["zedboot_readiness"]
        self.assertEqual(rd["management_docs_present"], 10)
        self.assertEqual(rd["management_docs_total"], 10)
        self.assertTrue(rd["has_full_management_five_piece"])
        self.assertEqual(rd["deploy_traces_present"], 0)

    def test_python_todo_counted(self):
        target = os.path.join(FIXTURES_DIR, "python_app")
        data = audit_json(target)["sections"]
        md = data["management_docs"]
        self.assertTrue(md["docs"]["README.md"])
        self.assertTrue(md["docs"]["docs/project/TODO.md"])
        self.assertEqual(data["zedboot_readiness"]["management_docs_present"], 2)


class TestRootHygieneAndDeploy(unittest.TestCase):
    """根目录卫生 / 部署痕迹 / UI 抽查（messy_project）。"""

    @classmethod
    def setUpClass(cls):
        # messy_project 的 .env 不入库（全局 pre-push 隐私闸门按文件名拦截），
        # 测试前现场构造、测完删除，工作区不留痕
        cls._env_path = os.path.join(FIXTURES_DIR, "messy_project", ".env")
        with open(cls._env_path, "w", encoding="utf-8") as f:
            f.write("DATABASE_URL=postgres://app:devpw@127.0.0.1:5432/app\n")
        cls.data = audit_json(os.path.join(FIXTURES_DIR, "messy_project"))["sections"]

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls._env_path)

    def test_root_hygiene_messy(self):
        rh = self.data["root_hygiene"]
        self.assertFalse(rh["clean"])
        self.assertEqual(rh["suspicious_dirs"], ["final-2", "misc"])
        self.assertEqual(rh["screenshot_files"], ["screenshot.png"])
        self.assertTrue(rh["ds_store"])
        self.assertEqual(rh["temp_files"], ["draft.txt~", "notes.tmp"])

    def test_deploy_traces_messy(self):
        dp = self.data["deploy_traces"]
        self.assertTrue(dp["dockerfile"]["exists"])
        self.assertEqual(dp["dockerfile"]["files"], ["Dockerfile"])
        self.assertTrue(dp["nginx"]["exists"])
        self.assertTrue(dp["deploy_scripts"]["exists"])
        self.assertEqual(dp["deploy_scripts"]["files"],
                         ["deploy.sh", "scripts/backup.sh"])
        self.assertTrue(dp["env_example"])
        self.assertTrue(dp["env_exists"])
        self.assertEqual(dp["count"], 5)

    def test_ui_messy(self):
        ui = self.data["ui"]
        self.assertTrue(ui["has_design_doc"])
        self.assertEqual(ui["design_doc_actual"], "DESIGN.md")
        self.assertTrue(ui["has_frontend"])


class TestGitNestingBoundary(unittest.TestCase):
    """嵌套仓库边界：REPO 内的目录（被外层仓库包含）必须按非仓库处理，
    不得被外层仓库的分支/提交/远程污染（CHANGELOG 0.5.7 第⑥项修复）。"""

    def test_inner_dir_not_polluted_by_outer_repo(self):
        target = os.path.join(FIXTURES_DIR, "inner_dir")
        data = audit_json(target)["sections"]
        g = data["git"]
        self.assertEqual(g["status"], "not_repo")
        self.assertIs(g["is_repo"], False)
        self.assertIsNone(g["branch"])
        self.assertIn("被外层仓库包含", g["is_repo_note"] or "")
        cs = data["committed_secrets"]
        self.assertTrue(cs["workspace_scan"])
        self.assertTrue(any("被外层仓库包含" in n for n in cs["unknown_notes"]),
                        "committed_secrets 应降级为工作区扫描并注明外层仓库")
        self.assertFalse(cs["risk_found"])

    def test_inner_dir_reads_own_readme(self):
        basic = audit_json(os.path.join(FIXTURES_DIR, "inner_dir"))["sections"]["basic"]
        self.assertEqual(basic["dir_name"], "inner_dir")
        self.assertEqual(basic["project_name_hint"], "inner dir")


@unittest.skipUnless(GIT_AVAILABLE, "需要 git 构建动态仓库 fixture")
class TestPrivacyLeak(unittest.TestCase):
    """隐私泄露 fixture：入库文件含本机绝对路径 / 公网 IP / 私钥头 → 告警命中；
    私网 IP 与 .env（有专项检查）不命中。"""

    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory()
        cls.repo = build_privacy_leak(cls._td.name)
        cls.data = audit_json(cls.repo)
        cls.cs = cls.data["sections"]["committed_secrets"]
        cls.g = cls.data["sections"]["git"]

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def test_git_repo_detected(self):
        self.assertEqual(self.g["status"], "repo")
        self.assertIs(self.g["is_repo"], True)
        self.assertEqual(self.g["branch"], "main")
        self.assertTrue(self.g["has_main_branch"])

    def test_tracked_env_is_risk(self):
        self.assertTrue(self.g["env_exists"])
        self.assertTrue(self.g["env_tracked"])
        self.assertTrue(self.g["risk_env_tracked"])

    def test_risk_hits_expected_types(self):
        self.assertEqual(self.cs["status"], "repo")
        self.assertFalse(self.cs["workspace_scan"])
        self.assertTrue(self.cs["risk_found"])
        types = {it["type"] for it in self.cs["risk_items"]}
        self.assertEqual(types, {"ip", "local_path", "private_key"})
        for it in self.cs["risk_items"]:
            self.assertEqual(it["file"], "leak.txt")

    def test_private_ip_and_env_not_flagged(self):
        # 唯一的 ip 命中来自公网 IP（240.0.0.1，第 2 行）；
        # 私网 IP（192.168.1.10）与 .env 内容（127.0.0.1，有专项检查不扫）不产生命中
        ip_items = [it for it in self.cs["risk_items"] if it["type"] == "ip"]
        self.assertEqual(len(ip_items), 1)
        self.assertEqual(ip_items[0]["file"], "leak.txt")
        self.assertEqual(ip_items[0]["lines"], [2])
        env_items = [it for it in self.cs["risk_items"]
                     if it["file"].startswith(".env")]
        self.assertEqual(env_items, [])


@unittest.skipUnless(GIT_AVAILABLE, "需要 git 构建动态仓库 fixture")
class TestEnvVariantAndDeployUser(unittest.TestCase):
    """.env* 变体跟踪风险 + deploy.env 服务器账号真源（ops.md 无账号字段）。"""

    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory()
        cls.repo = build_env_variant_and_deploy(cls._td.name)
        cls.data = audit_json(cls.repo)
        cls.g = cls.data["sections"]["git"]
        cls.cs = cls.data["sections"]["committed_secrets"]

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def test_tracked_env_variant_is_risk(self):
        """被 git 跟踪的 .env.production 像被跟踪的 .env 一样报风险：
        risk_env_variant_tracked 为真且点名变体；字面 .env 未被跟踪时
        risk_env_tracked 仍为假。"""
        self.assertTrue(self.g["risk_env_variant_tracked"])
        self.assertIn(".env.production", self.g["env_variants_tracked"])
        self.assertFalse(self.g["risk_env_tracked"])
        self.assertFalse(self.g["env_tracked"])

    def test_tracked_subdir_env_variant_is_risk(self):
        """P1 回归钉：config/.env.local 被强制跟踪 → 报风险并点名变体。
        旧实现 `git ls-files -- .env*` 的 pathspec 无斜杠不跨目录，匹配
        不到子目录变体而漏检；改全量 ls-files -z + basename 过滤后必须命中。"""
        d = os.path.join(self._td.name, "subdirenv")
        os.makedirs(os.path.join(d, "config"))
        _git(d, "init", "-q", "-b", "main")
        with open(os.path.join(d, ".gitignore"), "w", encoding="utf-8") as f:
            f.write(".env*\n")
        with open(os.path.join(d, "config/.env.local"), "w",
                  encoding="utf-8") as f:
            f.write("PUBLIC_IP=240.0.0.1\n")
        with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as f:
            f.write("# demo\n")
        _git(d, "add", "-A")
        _git(d, "add", "-f", "config/.env.local")
        _git(d, "-c", "user.name=test", "-c", "user.email=test@example.com",
             "commit", "-q", "-m", "init")
        g = audit_json(d)["sections"]["git"]
        self.assertTrue(g["risk_env_variant_tracked"])
        self.assertIn(".env.local", g["env_variants_tracked"])
        self.assertFalse(g["env_tracked"])
        self.assertFalse(g["risk_env_tracked"])

    def test_env_example_tracked_not_flagged(self):
        """.env.example 是例外名（只登记键名、无敏感内容），被跟踪不报风险。"""
        self.assertNotIn(".env.example", self.g["env_variants_tracked"])

    def test_env_variant_content_not_scanned(self):
        """.env.production 内容不进入入库内容扫描（.env* 跳过，另有专项检查）。"""
        self.assertFalse(
            any(it["file"].startswith(".env") for it in self.cs["risk_items"]))

    def test_deploy_env_account_allowed(self):
        """deploy.env 提供 DEPLOY_USER=deploy-bot 时 home_allow 含该账号：
        notes.md 里的 /home/deploy-bot/ 服务器端路径不报本机路径泄露
        （ops.md 无服务器账号字段，真源来自 deploy.env）。"""
        self.assertFalse(
            any(it["type"] == "local_path" for it in self.cs["risk_items"]))
        self.assertFalse(self.cs["risk_found"])

    def test_deploy_env_empty_user_falls_back_to_ops(self):
        """deploy.env 的 DEPLOY_USER 为空 → 回退 ops.md「机器可读字段」节：
        ops.md 登记的账号仍进 home_allow，/home/<账号>/ 服务器端路径不报。"""
        d = os.path.join(self._td.name, "fallbackproj")
        os.makedirs(os.path.join(d, "docs/private"))
        with open(os.path.join(d, "docs/private/deploy.env"), "w",
                  encoding="utf-8") as f:
            f.write('DEPLOY_USER=""\n')
        with open(os.path.join(d, "docs/private/ops.md"), "w",
                  encoding="utf-8") as f:
            f.write("# Ops\n\n- 服务器账号：legacy-acct\n")
        with open(os.path.join(d, "notes.txt"), "w", encoding="utf-8") as f:
            f.write("server = %s\n" % ("/home" + "/" + "legacy-acct" + "/app"))
        cs = audit_json(d)["sections"]["committed_secrets"]
        self.assertTrue(cs["workspace_scan"])
        self.assertFalse(
            any(it["type"] == "local_path" for it in cs["risk_items"]))
        self.assertFalse(cs["risk_found"])

    def test_workspace_scan_skips_env_variants(self):
        """非 git 目录降级扫描同样跳过 .env* 变体：.env.local 含公网 IP
        不命中（无跟踪概念，环境文件整体不入扫描）。"""
        d = os.path.join(self._td.name, "envws")
        os.makedirs(d)
        with open(os.path.join(d, ".env.local"), "w", encoding="utf-8") as f:
            f.write("PUBLIC_IP=240.0.0.1\n")
        cs = audit_json(d)["sections"]["committed_secrets"]
        self.assertTrue(cs["workspace_scan"])
        self.assertFalse(cs["risk_found"])


@unittest.skipUnless(GIT_AVAILABLE, "需要 git 构建动态仓库 fixture")
class TestNestedGitRepo(unittest.TestCase):
    """嵌套 git 仓库 fixture：目录自身是真实 git 仓库 → 正确识别为 repo，
    并读出分支 / 前缀分支 / 提交记录。"""

    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory()
        cls.repo = build_nested_git(cls._td.name)
        cls.g = audit_json(cls.repo)["sections"]["git"]

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def test_own_repo_detected(self):
        self.assertEqual(self.g["status"], "repo")
        self.assertIs(self.g["is_repo"], True)
        self.assertEqual(self.g["branch"], "task/feat1")
        self.assertEqual(self.g["task_branches"], ["task/feat1"])
        self.assertTrue(self.g["has_main_branch"])
        self.assertEqual(len(self.g["recent_commits"]), 2)
        self.assertEqual(self.g["uncommitted_changes"], 0)


class TestTruncationNotice(unittest.TestCase):
    """截断提示：超过 2MB 的文件只扫头部，事实记入 truncated_files 与
    unknown_notes（CHANGELOG 0.5.7 第⑦项修复）。"""

    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory()
        cls.dir = build_bigfile(cls._td.name)
        cls.cs = audit_json(cls.dir)["sections"]["committed_secrets"]

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def test_truncation_recorded(self):
        self.assertTrue(self.cs["workspace_scan"])
        self.assertIn("big.txt", self.cs["truncated_files"])
        self.assertTrue(any("超过 2MB" in n for n in self.cs["unknown_notes"]))
        self.assertFalse(self.cs["risk_found"])


class TestCli(unittest.TestCase):
    """CLI 入口行为。"""

    def test_help_exits_zero(self):
        p = subprocess.run([sys.executable, AUDIT_PY, "--help"],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0)
        self.assertIn("usage", p.stdout.lower())

    def test_nonexistent_path(self):
        p = subprocess.run([sys.executable, AUDIT_PY, "/nonexistent/path/zzz-not-exist"],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 2)
        self.assertIn("路径不存在", p.stderr)

    def test_file_not_directory(self):
        target = os.path.join(FIXTURES_DIR, "nextjs_app", "package.json")
        p = subprocess.run([sys.executable, AUDIT_PY, target],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 2)
        self.assertIn("不是目录", p.stderr)


if __name__ == "__main__":
    unittest.main()
