#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pre-push 隐私闸门（zedboot/assets/hooks/pre-push.tmpl）端到端行为回归测试。

被测对象：自包含 bash 模板（约 138 行），安装时把顶部 PROJECT_NAME 的
<项目名> 占位符替换为项目名后作为 .git/hooks/pre-push 使用（未替换自动降级
为空）。测试在临时目录构造真实 git 仓库 + bare 远程，把替换后的模板装为
pre-push 钩子，用真实 `git push` 端到端触发，断言退出码、拦截消息与远程引用
推进情况——不单测钩子内部函数，全部走真实 git 语义。

钉住的行为（对应 pre-push.tmpl 的实际实现，含 0.5.11 两项修正）：
  1. 从 stdin 读 "local_ref local_sha remote_ref remote_sha" 行；local_sha
     全零（删除分支）跳过。
  2. 新引用（remote_sha 全零）：本地 refs/remotes/ 非空（远程已有引用）时按
     `git rev-list <sha> --not --remotes` 只扫增量；远程全空（真·首次推送）
     退化为全历史扫描。
  3. 拦截三类「新增行」（git log -p 排除 +++ 文件头）：
     a. 私钥格式头（BEGIN ... PRIVATE KEY）
     b. /Users/<名>/ 与 /home/<名>/ 本机绝对路径（正则要求尾部斜杠）
     c. 公网 IPv4（已排除 0./10./127./169.254./192.168./172.16-31./
        RFC 5737 文档段/受限广播）
  4. 放行集合（三事实分离）：/home/<仓库目录名>/、/home/<项目名>/（安装时已
     替换）、docs/private/ops.md「机器可读字段」登记的 /home/<服务器账号>/
     （键后中/英文冒号均可，运行时读取，ops.md 缺失静默降级）。
  5. <项目名> 未替换（仍含 <）→ PROJECT_NAME 降级为空，仅放行目录名派生路径。
  6. 钩子不可执行时 git 的实测行为（git 2.50.1）：git 跳过不运行该钩子、
     push 照常放行，stderr 有 advice.ignoredHook 提示（见 test_10 注释）。
     ——这正是 verify.py 把「不可执行」判 FAIL 的原因：闸门静默失效。

fixture 一律在临时目录动态构造（真实 git 仓库 + bare 远程），仓库文件里不出现
/Users/<名>/ 路径与私钥头完整字面量（运行时拼接，与 test_audit.py 同绕法，
避免命中仓库 CI 的 no-private-paths 扫描与本仓库全局隐私闸门）。所有 git
命令通过对子进程注入 GIT_CONFIG_GLOBAL=os.devnull + GIT_CONFIG_NOSYSTEM=1
隔离真实全局/系统 git 配置（本机全局 core.hooksPath 若存在会让 .git/hooks
整体失效，测试必须确定性，也不读写真实全局配置）。

纯 Python 3 标准库（unittest），兼容 3.8+。
"""

import os
import shutil
import subprocess
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRE_PUSH_TMPL = os.path.join(REPO_ROOT, "zedboot", "assets", "hooks",
                             "pre-push.tmpl")
GIT_AVAILABLE = shutil.which("git") is not None

# 三事实分离的三组独立值：仓库目录名 ≠ 项目名 ≠ 服务器账号（互不相同）
REPO_DIRNAME = "myproj"
PROJECT_NAME = "acme-server"
OPS_ACCOUNT = "svc_prod"       # ops.md 半角冒号登记
OPS_ACCOUNT2 = "deploy_bot"    # ops.md 全角冒号登记（验证 ：→: 归一化）
USERS_USER = "alice"           # 本机 /Users/<虚构名>/ 测试用


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _git_env():
    """git 子进程隔离环境：不读不写真实全局/系统 git 配置（同 test_verify.py）。
    全局配置指到空设备 + 关掉系统级配置后，所有 git 结论只取决于临时仓库自身的
    local config；pre-push 钩子继承该环境，其内部 git 命令同样隔离。"""
    env = dict(os.environ)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    return env


def _git(root, *args):
    """在 root 内执行 git 命令（fixture 构造用），失败即抛异常。"""
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


def git_commit(repo, message="init", add=None):
    """显式 add + commit（-c 注入 user.name/email，不依赖全局 git 配置）。"""
    if add is None:
        _git(repo, "add", "-A")
    else:
        _git(repo, "add", "--", *add)
    _git(repo, "-c", "user.name=test", "-c", "user.email=test@example.com",
         "commit", "-q", "-m", message)


def build_fixture(root, name=REPO_DIRNAME):
    """临时目录内建「工作仓库 + bare 远程」并接好 origin。返回 (repo, bare)。"""
    repo = os.path.join(root, name)
    bare = os.path.join(root, name + ".git")
    os.makedirs(repo)
    _git(repo, "init", "-q", "-b", "main")
    _git(root, "init", "-q", "--bare", bare)
    _git(repo, "remote", "add", "origin", bare)
    return repo, bare


def install_hook(repo, project_name=PROJECT_NAME):
    """读模板替换 <项目名> 后装为 .git/hooks/pre-push 并加执行位，返回钩子路径。
    project_name=None 时不替换（原样安装，模拟安装时未配置的降级场景）。"""
    with open(PRE_PUSH_TMPL, encoding="utf-8") as f:
        tpl = f.read()
    if project_name is not None:
        tpl = tpl.replace("<项目名>", project_name)
    hook = os.path.join(repo, ".git", "hooks", "pre-push")
    with open(hook, "w", encoding="utf-8") as f:
        f.write(tpl)
    os.chmod(hook, 0o755)
    return hook


def git_rev(root, rev):
    """解析 git 对象 sha；对象不存在时返回 None（判远程引用是否推进）。"""
    p = subprocess.run(["git", "rev-parse", "--verify", "--quiet", rev],
                       cwd=root, capture_output=True, text=True, timeout=60,
                       env=_git_env())
    if p.returncode != 0:
        return None
    return p.stdout.strip()


def git_push(repo, *refspec):
    """真实 git push 触发 pre-push 钩子；返回 CompletedProcess（非零退出不抛错，
    拦截结果要由用例自行断言）。"""
    return subprocess.run(["git", "push", "origin"] + list(refspec), cwd=repo,
                          capture_output=True, text=True, timeout=60,
                          env=_git_env())


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------
@unittest.skipUnless(GIT_AVAILABLE, "需要 git 构建动态仓库 fixture")
class TestPrePushPrivacyGate(unittest.TestCase):
    """pre-push.tmpl 装为 .git/hooks/pre-push 后的端到端行为（真实 git push
    触发；每个用例独立临时仓库，互不污染）。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.root = self._td.name

    def test_clean_push_passes(self):
        """用例 1：干净提交 push → 放行（exit 0），远程 main 推进到本地 HEAD。"""
        repo, bare = build_fixture(self.root)
        install_hook(repo)
        _write(os.path.join(repo, "README.md"), "# demo\n\nclean content.\n")
        git_commit(repo, message="init", add=["README.md"])
        p = git_push(repo, "main")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("拦截", p.stderr)
        self.assertEqual(git_rev(bare, "refs/heads/main"),
                         git_rev(repo, "refs/heads/main"))

    def test_private_key_header_blocked(self):
        """用例 2：新增行含私钥格式头 → 拦截（exit 1），远程 main 不推进。
        私钥头字面量拼接构造，fixture 仓库文件不出现完整字面量。"""
        repo, bare = build_fixture(self.root)
        install_hook(repo)
        key_head = "-----BEGIN" + " OPENSSH PRIVATE KEY-----"
        _write(os.path.join(repo, "deploy-keys.txt"), "key = %s\n" % key_head)
        git_commit(repo, message="add key", add=["deploy-keys.txt"])
        p = git_push(repo, "main")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("拦截", p.stderr)
        self.assertIn("私钥格式头", p.stderr)
        self.assertIsNone(git_rev(bare, "refs/heads/main"),
                          "拦截后远程不应推进")

    def test_users_home_path_blocked(self):
        """用例 3：新增行含 /Users/<虚构名>/ 本机路径 → 拦截，远程不推进。
        路径段拼接构造（/Users 绕法同 test_audit.py），本文件与 fixture 仓库
        均不出现 /Users/<名>/ 字面量（避免命中仓库 CI 的 no-private-paths）。"""
        repo, bare = build_fixture(self.root)
        install_hook(repo)
        home_path = "/Users" + "/" + USERS_USER + "/app/secret"
        _write(os.path.join(repo, "local-path.txt"), "home = %s\n" % home_path)
        git_commit(repo, message="add local path", add=["local-path.txt"])
        p = git_push(repo, "main")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("本机绝对路径", p.stderr)
        self.assertIn(USERS_USER, p.stderr)
        self.assertIsNone(git_rev(bare, "refs/heads/main"),
                          "拦截后远程不应推进")

    def test_home_repo_dirname_allowed(self):
        """用例 4：/home/<仓库目录名>/ 是部署体系可推导服务器路径（账号=目录名）
        → 放行（exit 0），远程推进。"""
        repo, bare = build_fixture(self.root)   # 仓库目录名 = REPO_DIRNAME
        install_hook(repo)
        _write(os.path.join(repo, "deploy.md"),
               "server home: /home/%s/.ssh/config\n" % REPO_DIRNAME)
        git_commit(repo, message="deploy note", add=["deploy.md"])
        p = git_push(repo, "main")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("拦截", p.stderr)
        self.assertEqual(git_rev(bare, "refs/heads/main"),
                         git_rev(repo, "refs/heads/main"))

    def test_home_project_name_allowed(self):
        """用例 5：/home/<项目名>/（PROJECT_NAME 替换值，与目录名不同）→ 放行。
        目录名 ≠ 项目名是常见情形，部署体系约定账号 = 项目名。"""
        repo, bare = build_fixture(self.root)
        install_hook(repo, project_name=PROJECT_NAME)  # acme-server ≠ myproj
        self.assertNotEqual(PROJECT_NAME, REPO_DIRNAME, "前置：两事实必须不同")
        _write(os.path.join(repo, "deploy.md"),
               "deploy target: /home/%s/app/systemd\n" % PROJECT_NAME)
        git_commit(repo, message="deploy note", add=["deploy.md"])
        p = git_push(repo, "main")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("拦截", p.stderr)
        self.assertEqual(git_rev(bare, "refs/heads/main"),
                         git_rev(repo, "refs/heads/main"))

    def test_ops_md_server_account_allowed(self):
        """用例 6：docs/private/ops.md 机器可读字段登记的服务器账号
        /home/<账号>/ → 放行（目录名 ≠ 项目名 ≠ 账号，三事实分离）。ops.md 是
        gitignore 的本地文件，不提交不入库，钩子运行时读取；半角冒号与全角冒号
        （sed ：→: 归一化）两种登记形态都放行。"""
        repo, bare = build_fixture(self.root)
        install_hook(repo, project_name=PROJECT_NAME)
        self.assertEqual(len({REPO_DIRNAME, PROJECT_NAME, OPS_ACCOUNT}), 3,
                         "前置：三事实必须互不相同")
        # 半角冒号登记第一个账号
        _write(os.path.join(repo, "docs/private/ops.md"),
               "# Ops\n\n- 服务器账号: %s\n" % OPS_ACCOUNT)
        _write(os.path.join(repo, "service.md"),
               "unit: /home/%s/systemd/app.service\n" % OPS_ACCOUNT)
        git_commit(repo, message="service doc", add=["service.md"])
        p = git_push(repo, "main")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("拦截", p.stderr)
        self.assertEqual(git_rev(bare, "refs/heads/main"),
                         git_rev(repo, "refs/heads/main"))
        # 追加全角冒号登记的第二个账号，再推一个含该账号路径的提交 → 仍放行
        _write(os.path.join(repo, "docs/private/ops.md"),
               "# Ops\n\n- 服务器账号: %s\n- 服务器账号：%s\n"
               % (OPS_ACCOUNT, OPS_ACCOUNT2))
        _write(os.path.join(repo, "service2.md"),
               "unit: /home/%s/systemd/worker.service\n" % OPS_ACCOUNT2)
        git_commit(repo, message="service doc 2", add=["service2.md"])
        p = git_push(repo, "main")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("拦截", p.stderr)
        self.assertEqual(git_rev(bare, "refs/heads/main"),
                         git_rev(repo, "refs/heads/main"))

    def test_public_ipv4_blocked(self):
        """用例 7a：新增行含公网 IPv4（8.8.8.8）→ 拦截，远程不推进。"""
        repo, bare = build_fixture(self.root)
        install_hook(repo)
        _write(os.path.join(repo, "server.txt"), "dns = 8.8.8.8\n")
        git_commit(repo, message="server addr", add=["server.txt"])
        p = git_push(repo, "main")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("疑似公网 IPv4", p.stderr)
        self.assertIn("8.8.8.8", p.stderr)
        self.assertIsNone(git_rev(bare, "refs/heads/main"),
                          "拦截后远程不应推进")

    def test_private_and_rfc5737_ipv4_allowed(self):
        """用例 7b：私网 192.168.x.x 与 RFC 5737 文档示例段（192.0.2.x /
        198.51.100.x / 203.0.113.x）均放行；同提交不含公网 IP，整体 exit 0。"""
        repo, bare = build_fixture(self.root)
        install_hook(repo)
        _write(os.path.join(repo, "net.txt"),
               "lan = 192.168.1.10\n"
               "doc1 = 192.0.2.5\n"
               "doc2 = 198.51.100.9\n"
               "doc3 = 203.0.113.42\n")
        git_commit(repo, message="net doc", add=["net.txt"])
        p = git_push(repo, "main")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("拦截", p.stderr)
        self.assertEqual(git_rev(bare, "refs/heads/main"),
                         git_rev(repo, "refs/heads/main"))

    def test_new_tag_incremental_scan(self):
        """用例 8：新 tag 推送的增量语义（0.5.11）。历史 commit 含会被拦截的
        公网 IP（8.8.8.8）但已推过（本场景在装钩子前推送，模拟闸门启用前的
        遗留值），fetch 使本地 refs/remotes/ 非空；此后新增干净 commit 并打
        新 tag，push 新 tag（remote_sha 全零的新引用）→ 按 `rev-list <sha>
        --not --remotes` 只扫增量、旧历史不再拦截 → 放行。若回归为全历史
        扫描，此 push 会被历史中的 8.8.8.8 拦截，故断言 exit 0 即证明增量
        语义生效。"""
        repo, bare = build_fixture(self.root)
        # 1) 装钩子前推含公网 IP 的历史（无闸门，模拟启用前的遗留值）
        _write(os.path.join(repo, "legacy.txt"), "old server = 8.8.8.8\n")
        git_commit(repo, message="legacy history", add=["legacy.txt"])
        p = git_push(repo, "main")
        self.assertEqual(p.returncode, 0, p.stderr)
        # 2) fetch 建立 refs/remotes/origin/main（push 本身不更新 remote 跟踪）
        _git(repo, "fetch", "-q", "origin")
        self.assertNotEqual(
            _git(repo, "for-each-ref", "refs/remotes/").stdout.strip(), "",
            "fetch 后本地应存在远程跟踪引用")
        # 3) 装钩子（替换 <项目名>），提交干净增量并打 tag
        install_hook(repo)
        _write(os.path.join(repo, "clean.txt"), "clean increment\n")
        git_commit(repo, message="clean increment", add=["clean.txt"])
        _git(repo, "tag", "v1.0.0")
        legacy_sha = git_rev(repo, "HEAD~1")
        clean_sha = git_rev(repo, "HEAD")
        # 增量范围自检：干净提交在内、已推历史不在（钩子正是依赖这个语义）
        revs = _git(repo, "rev-list", clean_sha, "--not",
                    "--remotes").stdout.split()
        self.assertIn(clean_sha, revs, "增量范围应含新干净提交")
        self.assertNotIn(legacy_sha, revs, "增量范围不应含已推过的历史")
        # 4) push 新 tag（remote_sha 全零的新引用）→ 增量扫描 → 放行
        p = git_push(repo, "v1.0.0")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("拦截", p.stderr)
        self.assertEqual(git_rev(bare, "refs/tags/v1.0.0"),
                         git_rev(repo, "refs/tags/v1.0.0"))

    def test_new_tag_dirty_commit_blocked(self):
        """用例 8a：远端已有干净 main（远程非空），本地新增含私钥头的提交并打新
        tag，首次 push 该 tag（remote_sha 全零的新引用）→ 增量扫描（`rev-list
        <sha> --not --remotes`）应命中脏提交 → 拦截（exit 1），远程 tag 不推进。
        回归钉死真实 bug：revs 曾以字符串 "$local_sha --not --remotes" 传给
        git log——双引号使整串成为单个参数，git 报 ambiguous argument，错误被
        2>/dev/null 吞掉 → 扫描静默跳过、push 放行（远端已有引用时首次推新
        tag 的场景漏闸）。"""
        repo, bare = build_fixture(self.root)
        # 1) 装钩子前推干净 main（远端已有引用，新 tag 走增量扫描分支）
        _write(os.path.join(repo, "README.md"), "# demo\n\nclean base.\n")
        git_commit(repo, message="base", add=["README.md"])
        p = git_push(repo, "main")
        self.assertEqual(p.returncode, 0, p.stderr)
        # 2) fetch 建立 refs/remotes/origin/main（增量扫描依赖远程跟踪引用）
        _git(repo, "fetch", "-q", "origin")
        self.assertNotEqual(
            _git(repo, "for-each-ref", "refs/remotes/").stdout.strip(), "",
            "fetch 后本地应存在远程跟踪引用")
        # 3) 装钩子，新增含私钥头的提交并打新 tag
        install_hook(repo)
        key_head = "-----BEGIN" + " OPENSSH PRIVATE KEY-----"
        _write(os.path.join(repo, "deploy-keys.txt"), "key = %s\n" % key_head)
        git_commit(repo, message="add key", add=["deploy-keys.txt"])
        _git(repo, "tag", "v1.0.0")
        dirty_sha = git_rev(repo, "HEAD")
        self.assertIn(dirty_sha,
                      _git(repo, "rev-list", dirty_sha, "--not",
                           "--remotes").stdout.split(),
                      "前置：脏提交应在增量范围内（否则本用例测不到扫描语义）")
        # 4) 首次 push 新 tag → 增量扫描命中脏提交 → 拦截
        p = git_push(repo, "v1.0.0")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("拦截", p.stderr)
        self.assertIn("私钥格式头", p.stderr)
        self.assertIsNone(git_rev(bare, "refs/tags/v1.0.0"),
                          "拦截后远程 tag 不应推进")

    def test_new_branch_dirty_commit_blocked(self):
        """用例 8b：同 8a 的脏提交推新分支 feature/x（remote_sha 全零的新引用）
        → 增量扫描命中 → 拦截（exit 1），远程分支不推进。与 8a 同根因：revs 单
        字符串 bug 同样会让新分支的首次推送静默放行。"""
        repo, bare = build_fixture(self.root)
        # 1) 装钩子前推干净 main
        _write(os.path.join(repo, "README.md"), "# demo\n\nclean base.\n")
        git_commit(repo, message="base", add=["README.md"])
        p = git_push(repo, "main")
        self.assertEqual(p.returncode, 0, p.stderr)
        _git(repo, "fetch", "-q", "origin")
        self.assertNotEqual(
            _git(repo, "for-each-ref", "refs/remotes/").stdout.strip(), "",
            "fetch 后本地应存在远程跟踪引用")
        # 2) 装钩子，新增含私钥头的提交，push 新分支
        install_hook(repo)
        key_head = "-----BEGIN" + " OPENSSH PRIVATE KEY-----"
        _write(os.path.join(repo, "deploy-keys.txt"), "key = %s\n" % key_head)
        git_commit(repo, message="add key", add=["deploy-keys.txt"])
        p = git_push(repo, "HEAD:refs/heads/feature/x")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("拦截", p.stderr)
        self.assertIn("私钥格式头", p.stderr)
        self.assertIsNone(git_rev(bare, "refs/heads/feature/x"),
                          "拦截后远程分支不应推进")

    def test_unreplaced_placeholder_degrades(self):
        """用例 9：<项目名> 未替换（原样安装）→ PROJECT_NAME 降级为空：目录名
        派生路径 /home/<目录名>/ 仍放行；项目名形态路径 /home/<项目名>/（与
        目录名不同）不再放行 → 拦截（宁漏勿滥的保守口径）。"""
        repo, bare = build_fixture(self.root)
        install_hook(repo, project_name=None)   # 占位符原样保留
        # 9a: 目录名派生路径仍放行
        _write(os.path.join(repo, "deploy.md"),
               "server home: /home/%s/.ssh/config\n" % REPO_DIRNAME)
        git_commit(repo, message="deploy note", add=["deploy.md"])
        p = git_push(repo, "main")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("拦截", p.stderr)
        # 9b: 项目名形态路径不再放行 → 拦截，远程停在 9a 的提交不推进
        _write(os.path.join(repo, "deploy2.md"),
               "deploy target: /home/%s/app/systemd\n" % PROJECT_NAME)
        git_commit(repo, message="project-named path", add=["deploy2.md"])
        p = git_push(repo, "main")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("本机绝对路径", p.stderr)
        self.assertIn(PROJECT_NAME, p.stderr)
        self.assertEqual(git_rev(bare, "refs/heads/main"),
                         git_rev(repo, "HEAD~1"),
                         "拦截后远程不应推进")

    def test_nonexecutable_hook_skipped_by_git(self):
        """用例 10：钩子不可执行时 git 的实测行为（本机 git 2.50.1）——
        git 跳过（不运行）不可执行的钩子并提示 advice.ignoredHook，push 照常
        放行：exit 0、无拦截、远程推进（断言 returncode=0 + 远程推进即证明钩子
        未被运行——提交内容本应被拦截）。实测 stderr 提示原文：
        "The '.git/hooks/pre-push' hook was ignored because it's not set as
        executable."（git ≥ 2.41 均有此提示；此处不钉提示文本，只钉行为）。
        即：缺执行位的闸门静默失效——这正是 verify.py 把「不可执行」判 FAIL、
        test_verify.py 用例 9b 钉住的原因。"""
        repo, bare = build_fixture(self.root)
        hook = install_hook(repo)
        os.chmod(hook, 0o644)   # 去掉执行位
        home_path = "/Users" + "/" + USERS_USER + "/app/secret"
        _write(os.path.join(repo, "local-path.txt"), "home = %s\n" % home_path)
        git_commit(repo, message="would-be leak but hook not run",
                   add=["local-path.txt"])
        p = git_push(repo, "main")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("拦截", p.stderr)
        self.assertEqual(git_rev(bare, "refs/heads/main"),
                         git_rev(repo, "refs/heads/main"),
                         "钩子未被运行，push 应推进远程")


if __name__ == "__main__":
    unittest.main()
