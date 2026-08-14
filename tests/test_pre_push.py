#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pre-push 隐私闸门（zedboot/assets/hooks/pre-push.tmpl）端到端行为回归测试。

被测对象：自包含 bash 模板（约 226 行），安装时把顶部 PROJECT_NAME 的
<项目名> 占位符替换为项目名后作为 .git/hooks/pre-push 使用（未替换自动降级
为空）。测试在临时目录构造真实 git 仓库 + bare 远程，把替换后的模板装为
pre-push 钩子，用真实 `git push` 端到端触发，断言退出码、拦截消息与远程引用
推进情况——不单测钩子内部函数，全部走真实 git 语义。

钉住的行为（对应 pre-push.tmpl 的实际实现，含 0.5.11 与隐私闸门修复）：
  1. 从 stdin 读 "local_ref local_sha remote_ref remote_sha" 行；local_sha
     全零（删除分支）跳过。
  2. 新引用（remote_sha 全零）：只排除「当前目标远程」（pre-push 入参 $1）的
     remote-tracking refs——`git rev-list <sha> --not --remotes=<remote>`。
     目标远程本地无 tracking refs（真·首次推送/从未 fetch 过该远程）时排除集
     为空，自动退化为全历史扫描（fail-closed）；remote_name 为空（非 git 正常
     调用路径）时同样退化全历史扫描（空模式的 --remotes= 会排除所有远程）。
     已有引用（remote_sha 非零）时先 `git cat-file -e` 验证远端对象本地存在，
     不存在（force-push 独立历史等）→ fail-closed 拦截并提示 fetch；两处 git
     log 扫描命令退出码非零同样 fail-closed 拦截（扫描异常不放行，P0）。
  3. 拦截三类「新增行」（git log -p --diff-merges=first-parent 排除 +++
     文件头；不用 --first-parent（截断遍历）——侧分支历史也是推送内容必须
     扫描，--first-parent 只遍历第一父代会使侧分支泄露在合回 main 后不可见
     （P0）；--diff-merges=first-parent 只让 merge commit 相对第一父出一次
     diff——冲突解决引入的敏感行不漏扫，且不会把第一父侧已接受的旧行（如已推
     公网 IP）当新增再扫一遍（干净 merge 不误拦，P1））：
     a. 私钥格式头（BEGIN ... PRIVATE KEY）
     b. /Users/<名>/ 与 /home/<名>/ 本机绝对路径（正则要求尾部斜杠）
     c. 公网 IPv4（已排除 0./10./127./169.254./192.168./172.16-31./
        RFC 5737 文档段/受限广播）
  4. 路径级拦截：文件路径命中 .env* 变体（.env / .env.local /
     .env.production 等任意变体，含子目录内）一律拦截；.env.example /
     .env.sample / .env.template 例外放行。git log --diff-filter=ACMRT 覆盖
     Added / Copied / Modified / Renamed / type-change：git mv .env.example
     .env.production 识别为 R100、目标路径同样命中（--diff-filter=A 只筛
     Added，rename 提交无输出漏闸）；已跟踪 .env* 改值靠 M 命中
     （--diff-filter=ACR 不含 M，改值提交无输出漏闸）；chmod 改权限位实测归 M。
     在内容检查之前独立执行（内容扫描为空时路径检查仍须生效）。
  5. 放行集合（三事实分离）：/home/<仓库目录名>/、/home/<项目名>/（安装时已
     替换）、docs/private/deploy.env 的 DEPLOY_USER（机器真源，去引号去空白）
     或 docs/private/ops.md「机器可读字段」（旧项目 fallback，键后中/英文冒号
     均可）登记的 /home/<服务器账号>/，运行时读取，两者都缺失静默降级。
  6. <项目名> 未替换（仍含 <）→ PROJECT_NAME 降级为空，仅放行目录名派生路径。
  7. 钩子不可执行时 git 的实测行为（git 2.50.1）：git 跳过不运行该钩子、
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
DEPLOY_ENV_ACCOUNT = "deploy_env_acct"  # docs/private/deploy.env 的 DEPLOY_USER（机器真源）
OTHER_ACCOUNT = "stranger_acct"         # 未登记账号（对照拦截）
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
    """显式 add + commit（identity 来自 build_fixture 写入的仓库本地 config，
    不依赖全局 git 配置——CI 无全局 identity，统一本地 config 一次到位）。"""
    if add is None:
        _git(repo, "add", "-A")
    else:
        _git(repo, "add", "--", *add)
    _git(repo, "commit", "-q", "-m", message)


def build_fixture(root, name=REPO_DIRNAME):
    """临时目录内建「工作仓库 + bare 远程」并接好 origin。返回 (repo, bare)。
    建仓时统一写本地 user.name/user.email：普通 commit、git merge（-c 注入的
    user.name/email 对 merge 命令同样生效但此前只在 git_commit 里注入，CI 无
    全局 identity 时直接调 git merge 报 "Committer identity unknown"——五矩阵
    全红，根因即此）等所有 git 操作一律受益，全文件不再做逐命令 -c 注入。"""
    repo = os.path.join(root, name)
    bare = os.path.join(root, name + ".git")
    os.makedirs(repo)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "test")
    _git(repo, "config", "user.email", "test@example.com")
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


def git_push(repo, *refspec, remote="origin"):
    """真实 git push 触发 pre-push 钩子；返回 CompletedProcess（非零退出不抛错，
    拦截结果要由用例自行断言）。默认推 origin，multi-remote 用例可指定 remote。"""
    return subprocess.run(["git", "push", remote] + list(refspec), cwd=repo,
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


    def test_multi_remote_private_history_blocked(self):
        """用例 11：multi-remote 漏扫回归（P0）。私有 origin 已有脏历史（装钩子前
        推入，模拟闸门启用前的遗留值），fetch 建立 refs/remotes/origin/*；新增
        public remote 后从脏历史处开新分支首推 public——修复前 `--not --remotes`
        排除所有远程，会把 origin 的脏历史一并排除而漏扫放行；修复后只排除目标
        远程（public 本地无 tracking refs → 排除集为空 → 全历史扫描）→ 必须拦截，
        public 端引用不推进。"""
        repo, bare_origin = build_fixture(self.root)
        bare_public = os.path.join(self.root, "public.git")
        _git(self.root, "init", "-q", "--bare", bare_public)
        # 1) 装钩子前把含私钥头的脏历史推上 origin（遗留值场景）
        key_head = "-----BEGIN" + " OPENSSH PRIVATE KEY-----"
        _write(os.path.join(repo, "secret.txt"), "key = %s\n" % key_head)
        git_commit(repo, message="dirty legacy", add=["secret.txt"])
        p = git_push(repo, "main")
        self.assertEqual(p.returncode, 0, p.stderr)
        _git(repo, "fetch", "-q", "origin")
        self.assertNotEqual(
            _git(repo, "for-each-ref", "refs/remotes/origin/").stdout.strip(), "",
            "前置：fetch 后应有 origin 的远程跟踪引用")
        # 2) 新增 public 远程并接好
        _git(repo, "remote", "add", "public", bare_public)
        # 3) 装钩子，从脏历史处开新分支，首推 public（新引用场景）
        install_hook(repo)
        _git(repo, "checkout", "-q", "-b", "feature/x")
        p = git_push(repo, "HEAD:refs/heads/feature/x", remote="public")
        self.assertNotEqual(p.returncode, 0, "脏历史推 public 必须被拦")
        self.assertIn("拦截", p.stderr)
        self.assertIn("私钥格式头", p.stderr)
        self.assertIsNone(git_rev(bare_public, "refs/heads/feature/x"),
                          "拦截后 public 端不应推进")

    def test_merge_conflict_resolution_blocked(self):
        """用例 12：--no-ff 合回 main、冲突解决时新增一行私钥头（两父均无此行）
        → push 必须拦截（P1 修复）。默认 git log -p 不显示 merge diff，冲突解决
        引入的新增行会漏扫放行；修复后 --first-parent -m 按主线视角出一次 diff，
        冲突解决的新增行可见。"""
        repo, bare = build_fixture(self.root)
        install_hook(repo)
        # 基线提交，然后两个分支并行改同一行制造冲突
        _write(os.path.join(repo, "conflict.txt"), "line1 = base\nline2 = common\n")
        git_commit(repo, message="base", add=["conflict.txt"])
        _git(repo, "checkout", "-q", "-b", "feature")
        _write(os.path.join(repo, "conflict.txt"), "line1 = feature\nline2 = common\n")
        git_commit(repo, message="feature change", add=["conflict.txt"])
        _git(repo, "checkout", "-q", "main")
        _write(os.path.join(repo, "conflict.txt"), "line1 = main\nline2 = common\n")
        git_commit(repo, message="main change", add=["conflict.txt"])
        # --no-ff merge 触发冲突（返回非零，属预期）
        pm = subprocess.run(["git", "merge", "--no-ff", "feature"], cwd=repo,
                            capture_output=True, text=True, timeout=60,
                            env=_git_env())
        self.assertNotEqual(pm.returncode, 0, "前置：应产生合并冲突")
        # 冲突解决：两父均无的私钥行（两父的 line1 都不含 key 行）
        key_head = "-----BEGIN" + " OPENSSH PRIVATE KEY-----"
        _write(os.path.join(repo, "conflict.txt"),
               "line1 = merged\nline2 = common\nkey = %s\n" % key_head)
        git_commit(repo, message="merge feature with resolution",
                   add=["conflict.txt"])
        p = git_push(repo, "main")
        self.assertNotEqual(p.returncode, 0, "冲突解决引入的私钥行必须被拦")
        self.assertIn("拦截", p.stderr)
        self.assertIn("私钥格式头", p.stderr)
        self.assertIsNone(git_rev(bare, "refs/heads/main"),
                          "拦截后远程不应推进")

    def test_env_dot_production_blocked(self):
        """用例 13a：新增 .env.production（内容为普通 KEY=VALUE，不命中任何内容
        正则）→ 路径级检查拦截（P0 配套）。修复前只扫内容三类正则，.env* 一般
        密钥值漏扫放行。"""
        repo, bare = build_fixture(self.root)
        install_hook(repo)
        _write(os.path.join(repo, ".env.production"),
               "DB_PASSWORD=supersecret123\nAPI_KEY=abc123456789\n")
        git_commit(repo, message="add env production", add=[".env.production"])
        p = git_push(repo, "main")
        self.assertNotEqual(p.returncode, 0, ".env.production 必须被拦")
        self.assertIn("拦截", p.stderr)
        self.assertIn(".env.production", p.stderr)
        self.assertIsNone(git_rev(bare, "refs/heads/main"),
                          "拦截后远程不应推进")

    def test_env_dot_in_subdir_blocked(self):
        """用例 13b：子目录内的 .env 变体（config/.env.local）同样拦截。"""
        repo, bare = build_fixture(self.root)
        install_hook(repo)
        _write(os.path.join(repo, "config", ".env.local"),
               "TOKEN=localdevtoken123\n")
        git_commit(repo, message="add env local", add=["config/.env.local"])
        p = git_push(repo, "main")
        self.assertNotEqual(p.returncode, 0, "子目录 .env 变体必须被拦")
        self.assertIn("拦截", p.stderr)
        self.assertIn(".env.local", p.stderr)
        self.assertIsNone(git_rev(bare, "refs/heads/main"),
                          "拦截后远程不应推进")

    def test_env_example_template_allowed(self):
        """用例 13c 对照：.env.example / .env.sample / .env.template 是模板文件
        （无真实值），同内容 → 放行。"""
        repo, bare = build_fixture(self.root)
        install_hook(repo)
        for name in (".env.example", ".env.sample", ".env.template"):
            _write(os.path.join(repo, name), "DB_PASSWORD=supersecret123\n")
        git_commit(repo, message="add env templates",
                   add=[".env.example", ".env.sample", ".env.template"])
        p = git_push(repo, "main")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("拦截", p.stderr)
        self.assertEqual(git_rev(bare, "refs/heads/main"),
                         git_rev(repo, "refs/heads/main"))

    def test_deploy_env_account_allowed(self):
        """用例 14：docs/private/deploy.env 的 DEPLOY_USER（机器真源）登记的服务器
        账号 /home/<账号>/ → 放行（ops.md 未登记该账号，证明放行来自 deploy.env）；
        对照：未登记账号路径 → 拦截。修复前只读 ops.md，deploy.env 登记的账号路径
        会被误拦。"""
        repo, bare = build_fixture(self.root)
        install_hook(repo)
        self.assertEqual(len({REPO_DIRNAME, PROJECT_NAME, DEPLOY_ENV_ACCOUNT}), 3,
                         "前置：三事实必须互不相同")
        # ops.md 不写服务器账号（deploy.env 为唯一来源）
        _write(os.path.join(repo, "docs/private/deploy.env"),
               'DEPLOY_USER="%s"\n' % DEPLOY_ENV_ACCOUNT)
        _write(os.path.join(repo, "service.md"),
               "unit: /home/%s/systemd/app.service\n" % DEPLOY_ENV_ACCOUNT)
        git_commit(repo, message="service doc", add=["service.md"])
        p = git_push(repo, "main")
        self.assertEqual(p.returncode, 0,
                         "deploy.env 登记的账号路径应放行: %s" % p.stderr)
        self.assertNotIn("拦截", p.stderr)
        self.assertEqual(git_rev(bare, "refs/heads/main"),
                         git_rev(repo, "refs/heads/main"))
        # 对照：未登记账号 → 拦截
        _write(os.path.join(repo, "other.md"),
               "unit: /home/%s/systemd/app.service\n" % OTHER_ACCOUNT)
        git_commit(repo, message="other account", add=["other.md"])
        p = git_push(repo, "main")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("本机绝对路径", p.stderr)
        self.assertIn(OTHER_ACCOUNT, p.stderr)

    def test_side_branch_leak_deleted_merged_blocked(self):
        """用例 15：侧分支历史泄露（加私钥头→再删除）--no-ff 合回 main，工作树
        干净但侧分支历史有私钥 → push main 必须拦截（P0）。修复前 --first-parent
        只遍历第一父代主线，侧分支提交对扫描不可见，泄露放行；去掉后侧分支历史
        同样纳入扫描（侧分支历史也是推送内容）。"""
        repo, bare = build_fixture(self.root)
        install_hook(repo)
        _write(os.path.join(repo, "README.md"), "# demo\n\nbase.\n")
        git_commit(repo, message="base", add=["README.md"])
        # feature 分支：提交加私钥头 → 再提交删除（最终树干净，泄露只在历史）
        _git(repo, "checkout", "-q", "-b", "feature")
        key_head = "-----BEGIN" + " OPENSSH PRIVATE KEY-----"
        _write(os.path.join(repo, "deploy-keys.txt"), "key = %s\n" % key_head)
        git_commit(repo, message="add key", add=["deploy-keys.txt"])
        _git(repo, "rm", "-q", "deploy-keys.txt")
        git_commit(repo, message="delete key")
        self.assertFalse(os.path.exists(os.path.join(repo, "deploy-keys.txt")),
                         "前置：合回前工作树已无泄露文件")
        # --no-ff 合回 main（无冲突，净变化为空），工作树依旧干净
        _git(repo, "checkout", "-q", "main")
        _git(repo, "merge", "-q", "--no-ff", "-m", "merge feature", "feature")
        self.assertFalse(os.path.exists(os.path.join(repo, "deploy-keys.txt")),
                         "前置：合并后工作树应干净（泄露只在侧分支历史）")
        p = git_push(repo, "main")
        self.assertNotEqual(p.returncode, 0, "侧分支历史的私钥必须被拦")
        self.assertIn("拦截", p.stderr)
        self.assertIn("私钥格式头", p.stderr)
        self.assertIsNone(git_rev(bare, "refs/heads/main"),
                          "拦截后远程不应推进")

    def test_env_rename_blocked(self):
        """用例 16：.env.example 被 git mv 为 .env.production（rename R100）→
        push 必须拦截（P1）。修复前 --diff-filter=A 只筛 Added，rename 提交在
        --name-only 下无输出（R 不命中 A 过滤），新路径不可见漏闸；改为
        --diff-filter=ACR 后 rename 检出输出目标路径 .env.production → 路径
        检查命中。"""
        repo, bare = build_fixture(self.root)
        install_hook(repo)
        _write(os.path.join(repo, ".env.example"), "DB_PASSWORD=clean\n")
        git_commit(repo, message="add env example", add=[".env.example"])
        _git(repo, "mv", ".env.example", ".env.production")
        git_commit(repo, message="rename to prod")
        p = git_push(repo, "main")
        self.assertNotEqual(p.returncode, 0,
                            "rename 成的 .env.production 必须被拦")
        self.assertIn("拦截", p.stderr)
        self.assertIn(".env.production", p.stderr)
        self.assertIsNone(git_rev(bare, "refs/heads/main"),
                          "拦截后远程不应推进")

    def test_force_push_missing_remote_obj_blocked(self):
        """用例 17：force-push 独立历史 fail-open 回归（P0）。远端已有引用
        （remote_sha 非零）但本地对象库无该对象（force-push 独立历史等），修复
        前 git log "X..Y" 报 fatal、错误被 2>/dev/null 吞 → 扫描为空即放行；
        修复后先 git cat-file -e 验证远端对象本地存在，不存在 → fail-closed
        拦截并提示 fetch。直接以模拟 stdin（refs/heads/main <local_sha>
        refs/heads/main <X>）执行钩子——X 在本地不存在，真实 git push 语义
        不变但 force-push 独立历史被 git 自身拒绝前钩子已先触发（钉 fail-open
        必须直接喂 stdin 才能走到钩子逻辑）。"""
        # 1) 仓 A：推入干净 commit X（造"远端已接受"的引用与对象）
        repo_a, bare_a = build_fixture(self.root, name="repoA")
        _write(os.path.join(repo_a, "README.md"), "# A\n\nclean.\n")
        git_commit(repo_a, message="X on A", add=["README.md"])
        p = git_push(repo_a, "main")
        self.assertEqual(p.returncode, 0, p.stderr)
        sha_x = git_rev(bare_a, "refs/heads/main")
        self.assertIsNotNone(sha_x, "前置：远端应已有 X")
        # 2) 仓 B：本地独立历史（无 X），含私钥头
        repo_b, _ = build_fixture(self.root, name="repoB")
        install_hook(repo_b)
        key_head = "-----BEGIN" + " OPENSSH PRIVATE KEY-----"
        _write(os.path.join(repo_b, "deploy-keys.txt"), "key = %s\n" % key_head)
        git_commit(repo_b, message="local history", add=["deploy-keys.txt"])
        local_sha = git_rev(repo_b, "refs/heads/main")
        # 对象存在性必须用 cat-file -e（rev-parse --verify 对 40 位完整 sha 不
        # 校验对象库存在性，与钩子内同一检查口径）
        px = subprocess.run(
            ["git", "cat-file", "-e", "%s^{commit}" % sha_x], cwd=repo_b,
            capture_output=True, text=True, timeout=60, env=_git_env())
        self.assertNotEqual(px.returncode, 0,
                            "前置：X 必须在仓 B 本地对象库不存在")
        # 3) 模拟 pre-push stdin 直接执行钩子（remote 名经 $1 传入）
        hook = os.path.join(repo_b, ".git", "hooks", "pre-push")
        stdin_line = "refs/heads/main %s refs/heads/main %s\n" % (local_sha,
                                                                  sha_x)
        pr = subprocess.run([hook, "origin"], cwd=repo_b, input=stdin_line,
                            capture_output=True, text=True, timeout=60,
                            env=_git_env())
        self.assertNotEqual(pr.returncode, 0,
                            "远端对象本地不存在必须 fail-closed 拦截")
        self.assertIn("拦截", pr.stderr)
        self.assertIn("远端对象本地不存在", pr.stderr)
        self.assertIn("fetch", pr.stderr)

    def test_clean_merge_with_accepted_public_ip_allowed(self):
        """用例 18：merge 误报回归（P1）。main 已有含公网 IP 8.8.8.8 的已接受
        历史（装钩子前推 origin，模拟闸门启用前遗留值），feature 从更早的 main
        分叉、干净；--no-ff 合回 main 后 push → 必须放行。修复前 -m 使 merge
        commit 对第二父（feature 侧）再出一次 diff，把第一父侧已接受的 8.8.8.8
        当新增行再扫一遍 → 干净 merge 误拦；修复后 --diff-merges=first-parent
        只相对第一父出 diff（完整遍历下 feature 提交本身干净）→ 放行。"""
        repo, bare = build_fixture(self.root)
        # 1) 装钩子前：main 提交含 8.8.8.8 的历史并推 origin（已接受遗留值）
        _write(os.path.join(repo, "README.md"), "# demo\n\nbase.\n")
        git_commit(repo, message="base", add=["README.md"])
        _git(repo, "checkout", "-q", "-b", "feature")
        _write(os.path.join(repo, "feat.txt"), "feature work\n")
        git_commit(repo, message="feature work", add=["feat.txt"])
        _git(repo, "checkout", "-q", "main")
        _write(os.path.join(repo, "server.txt"), "dns = 8.8.8.8\n")
        git_commit(repo, message="accepted public ip", add=["server.txt"])
        p = git_push(repo, "main")
        self.assertEqual(p.returncode, 0, p.stderr)
        # 2) 装钩子；feature 从 8.8.8.8 提交之前的历史分叉、干净
        install_hook(repo)
        _git(repo, "checkout", "-q", "-b", "feature2", "feature")
        # 3) --no-ff 合回 main（无冲突，feature 提交本身干净）
        _git(repo, "checkout", "-q", "main")
        _git(repo, "merge", "-q", "--no-ff", "-m", "merge feature2", "feature2")
        # 4) push → 必须放行（干净 merge 不应被已接受历史误拦）
        p = git_push(repo, "main")
        self.assertEqual(p.returncode, 0,
                         "干净 merge 必须放行: %s" % p.stderr)
        self.assertNotIn("拦截", p.stderr)
        self.assertEqual(git_rev(bare, "refs/heads/main"),
                         git_rev(repo, "refs/heads/main"))

    def test_tracked_env_production_modified_blocked(self):
        """用例 19：已跟踪 .env.production 改值 → 拦（P1）。路径扫描
        --diff-filter 曾为 ACR 不含 M——已跟踪的 .env* 改值提交在 --name-only
        下无输出漏闸放行；改为 ACMRT 后 Modified 提交输出目标路径 → 路径级检查
        命中。初始 .env.production 在装钩子前推 origin（绕开闸门建"已接受"的
        已跟踪文件），此后改值再推 → 必须拦截（改值内容为普通键值，不命中任何
        内容正则，证明拦截来自路径级 M 检出而非内容）。"""
        repo, bare = build_fixture(self.root)
        # 1) 装钩子前：提交并 push .env.production（普通键值，内容不命中正则）
        _write(os.path.join(repo, ".env.production"),
               "DB_PASSWORD=supersecret123\n")
        git_commit(repo, message="init env production",
                   add=[".env.production"])
        p = git_push(repo, "main")
        self.assertEqual(p.returncode, 0, p.stderr)
        # 2) 装钩子，已跟踪文件改值（内容仍不命中任何内容正则）
        install_hook(repo)
        _write(os.path.join(repo, ".env.production"),
               "DB_PASSWORD=anothersecret456\nAPI_KEY=xyz987654321\n")
        git_commit(repo, message="modify env production",
                   add=[".env.production"])
        p = git_push(repo, "main")
        self.assertNotEqual(p.returncode, 0,
                            "已跟踪 .env.production 改值必须被拦")
        self.assertIn("拦截", p.stderr)
        self.assertIn(".env.production", p.stderr)
        # 远程应停在步骤 1 的初始提交（step-1 已推），不被推进到改值提交
        self.assertEqual(git_rev(bare, "refs/heads/main"),
                         git_rev(repo, "HEAD~1"),
                         "拦截后远程不应推进到改值提交")


if __name__ == "__main__":
    unittest.main()
