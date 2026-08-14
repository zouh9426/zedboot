#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
部署脚本行为回归测试（zedboot/assets/deploy/ 下的 rsync 部署模板）。

被测对象：
  1. deploy-rsync.sh.tmpl（容器栈：把项目代码从本地 rsync 直推服务器）
  2. static/deploy-rsync-static.sh.tmpl（静态站：只推发布目录，fail-closed）
  3. nextjs/Dockerfile.tmpl 的 Prisma COPY 结构（纯文本断言，见文件尾 TestNextjsDockerfilePrismaCopy）

fixture 风格与 test_pre_push.py 一致：把模板拷贝进临时项目目录，PATH 前置
stub 的 rsync/ssh（只把参数记录到文件后 exit 0），以真实 `bash <脚本>` 运行，
断言退出码、stderr 提示与 rsync 实际收到的参数。部署事实（项目名/账号/目录/
IP/密钥）在运行时写入 docs/private/deploy.env（与模板口径一致，脚本 source）；
IP 用 RFC 5737 文档示例段 192.0.2.1，密钥用 ~ 相对占位路径，不指向真实服务器。

钉住的行为：
  容器脚本：
    - 缺 docs/private/deploy.env → exit 1 且报 PROJECT_NAME 提示（:? 空变量守卫）
    - 配齐五事实 → rsync 被调用，排除项含 docs/private 与 .env*（容器脚本已
      扩为 .env* 全家族，覆盖 .env/.env.local 等），目标 <DEPLOY_USER>@<SERVER_IP>:<REMOTE_DIR>/
  静态脚本：
    - 发布目录存在（默认 dist / 或 STATIC_OUTPUT_DIR=out）→ 只推该目录
    - STATIC_OUTPUT_DIR=. 或越出项目根的 ../x（目录存在）→ exit 1（越界防护）
    - 发布目录缺失 → exit 1（fail-closed）
    注：静态脚本的 rsync 排除同样是 `.env*` 全家族（覆盖 .env/.env.local 等，
    与容器脚本一致）；测试只按实际脚本内容断言。

纯 Python 3 标准库（unittest），兼容 3.8+。
"""

import os
import shutil
import subprocess
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOY_RSYNC_TMPL = os.path.join(REPO_ROOT, "zedboot", "assets", "deploy",
                                 "deploy-rsync.sh.tmpl")
DEPLOY_RSYNC_STATIC_TMPL = os.path.join(REPO_ROOT, "zedboot", "assets",
                                        "deploy", "static",
                                        "deploy-rsync-static.sh.tmpl")
NEXTJS_DOCKERFILE_TMPL = os.path.join(REPO_ROOT, "zedboot", "assets", "deploy",
                                      "nextjs", "Dockerfile.tmpl")
BASH_AVAILABLE = shutil.which("bash") is not None

# 部署五事实（运行时写入 deploy.env；IP 为 RFC 5737 文档示例段，密钥为占位路径）
PROJECT_NAME = "acme-server"
DEPLOY_USER = "deploybot"
REMOTE_DIR = "/opt/acme-server"
SERVER_IP = "192.0.2.1"
DEPLOY_KEY = "~/.ssh/acme-server_deploy"
FIVE_FACTS = [("PROJECT_NAME", PROJECT_NAME), ("DEPLOY_USER", DEPLOY_USER),
              ("REMOTE_DIR", REMOTE_DIR), ("SERVER_IP", SERVER_IP),
              ("DEPLOY_KEY", DEPLOY_KEY)]


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _write(path, content):
    """动态写文件（含中间目录）。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _make_stub_bin(root):
    """在 root 下建 stub-bin/，放入 rsync 与 ssh stub（把每次调用参数按空格
    拼接成一行追加进 $STUB_LOG 后 exit 0）。"""
    bin_dir = os.path.join(root, "stub-bin")
    os.makedirs(bin_dir)
    stub = ("#!/bin/sh\n"
            "printf '%s' \"$0\" >> \"${STUB_LOG}\"\n"
            "for a in \"$@\"; do printf ' %s' \"$a\" >> \"${STUB_LOG}\"; done\n"
            "printf '\\n' >> \"${STUB_LOG}\"\n"
            "exit 0\n")
    for name in ("rsync", "ssh"):
        p = os.path.join(bin_dir, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(stub)
        os.chmod(p, 0o755)
    return bin_dir


def _run_script(script, env):
    """以 bash 运行脚本，返回 CompletedProcess（非零退出不抛错）。"""
    return subprocess.run(["bash", script], capture_output=True, text=True,
                          timeout=60, env=env)


@unittest.skipUnless(BASH_AVAILABLE, "需要 bash 运行部署模板")
class TestDeployRsyncScripts(unittest.TestCase):
    """deploy-rsync.sh.tmpl 与 deploy-rsync-static.sh.tmpl 拷贝落地后的行为。
    每个用例独立临时项目目录，互不污染。"""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.root = self._td.name
        self.proj = os.path.join(self.root, "proj")
        os.makedirs(self.proj)
        self.log = os.path.join(self.root, "rsync.log")
        bin_dir = _make_stub_bin(self.root)
        self.env = dict(os.environ)
        self.env["PATH"] = bin_dir + os.pathsep + self.env.get("PATH", "")
        self.env["STUB_LOG"] = self.log

    # ---- fixture 辅助 ----
    def _install(self, tmpl, script_name):
        """把模板拷进临时项目根（模拟落地），返回落地脚本绝对路径。"""
        dst = os.path.join(self.proj, script_name)
        shutil.copy(tmpl, dst)
        return dst

    def _install_container(self):
        return self._install(DEPLOY_RSYNC_TMPL, "deploy-rsync.sh")

    def _install_static(self):
        return self._install(DEPLOY_RSYNC_STATIC_TMPL, "deploy-rsync-static.sh")

    def _deploy_env(self, extra=None):
        """写 docs/private/deploy.env：五事实 + 可选附加行（如 STATIC_OUTPUT_DIR）。"""
        lines = ["%s=%s" % (k, v) for k, v in FIVE_FACTS]
        if extra is not None:
            lines.append(extra)
        _write(os.path.join(self.proj, "docs/private", "deploy.env"),
               "\n".join(lines) + "\n")

    def _rsync_log(self):
        with open(self.log, encoding="utf-8") as f:
            return f.read().strip()

    # ---- 容器脚本 ----
    def test_container_missing_deploy_env(self):
        """缺 docs/private/deploy.env → exit 1 且报 PROJECT_NAME 提示（不触发 rsync）。"""
        script = self._install_container()
        p = _run_script(script, self.env)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("PROJECT_NAME", p.stderr)
        self.assertIn("deploy.env", p.stderr)
        self.assertFalse(os.path.exists(self.log),
                         "缺部署事实不应调用 rsync")

    def test_container_full_facts_invokes_rsync(self):
        """配齐五事实 → exit 0，rsync 被调用：排除含 docs/private 与 .env*
        （容器脚本现状已扩为 .env*，覆盖 .env 全家族，勿回退为裸 .env），
        目标地址正确。"""
        script = self._install_container()
        self._deploy_env()
        p = _run_script(script, self.env)
        self.assertEqual(p.returncode, 0, p.stderr)
        line = self._rsync_log()   # 日志由 rsync stub 写入，非空即证明 rsync 被调用
        self.assertTrue(line, "rsync 未被调用（日志为空）")
        self.assertIn("--exclude .env*", line)
        self.assertIn("--exclude docs/private", line)
        self.assertIn("%s@%s:%s/" % (DEPLOY_USER, SERVER_IP, REMOTE_DIR), line)
        self.assertTrue(line.endswith("%s@%s:%s/" % (DEPLOY_USER, SERVER_IP,
                                                     REMOTE_DIR)), line)

    def test_container_ssh_port_default_22(self):
        """默认 deploy.env（无 SSH_PORT）→ ssh -e 参数含 -p 22（默认 22 兼容旧 deploy.env）。"""
        script = self._install_container()
        self._deploy_env()
        p = _run_script(script, self.env)
        self.assertEqual(p.returncode, 0, p.stderr)
        line = self._rsync_log()
        self.assertIn("-p 22", line)

    def test_container_ssh_port_custom(self):
        """deploy.env 设 SSH_PORT=2222 → ssh -e 参数含 -p 2222。"""
        script = self._install_container()
        self._deploy_env(extra='SSH_PORT="2222"')
        p = _run_script(script, self.env)
        self.assertEqual(p.returncode, 0, p.stderr)
        line = self._rsync_log()
        self.assertIn("-p 2222", line)

    # ---- 静态脚本 ----
    def test_static_pushes_dist_by_default(self):
        """默认发布目录 dist 存在 → exit 0，只推 <项目>/dist/。"""
        script = self._install_static()
        os.makedirs(os.path.join(self.proj, "dist"))
        self._deploy_env()
        p = _run_script(script, self.env)
        self.assertEqual(p.returncode, 0, p.stderr)
        line = self._rsync_log()
        self.assertIn("%s/dist/" % self.proj, line)
        self.assertIn("--exclude docs/private", line)

    def test_static_pushes_out_when_configured(self):
        """STATIC_OUTPUT_DIR=out → exit 0，只推 <项目>/out/（覆盖默认 dist）。"""
        script = self._install_static()
        os.makedirs(os.path.join(self.proj, "out"))
        self._deploy_env(extra='STATIC_OUTPUT_DIR="out"')
        p = _run_script(script, self.env)
        self.assertEqual(p.returncode, 0, p.stderr)
        line = self._rsync_log()
        self.assertIn("%s/out/" % self.proj, line)
        self.assertNotIn("%s/dist/" % self.proj, line)

    def test_static_dot_output_rejected(self):
        """STATIC_OUTPUT_DIR=. → exit 1（越界防护：发布目录不能是项目根）。"""
        script = self._install_static()
        self._deploy_env(extra='STATIC_OUTPUT_DIR="."')
        p = _run_script(script, self.env)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("STATIC_OUTPUT_DIR", p.stderr)
        self.assertIn("项目内", p.stderr)
        self.assertFalse(os.path.exists(self.log),
                         "越界路径不应触发 rsync")

    def test_static_escape_output_rejected(self):
        """STATIC_OUTPUT_DIR=../x（目录存在，越出项目根）→ exit 1。"""
        script = self._install_static()
        os.makedirs(os.path.join(self.root, "x"))
        self._deploy_env(extra='STATIC_OUTPUT_DIR="../x"')
        p = _run_script(script, self.env)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("STATIC_OUTPUT_DIR", p.stderr)
        self.assertIn("项目内", p.stderr)
        self.assertFalse(os.path.exists(self.log),
                         "越界路径不应触发 rsync")

    def test_static_missing_output_dir(self):
        """发布目录缺失（默认 dist 不存在）→ exit 1（fail-closed，绝不发布项目根）。"""
        script = self._install_static()
        self._deploy_env()
        p = _run_script(script, self.env)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("未找到发布目录", p.stderr)
        self.assertFalse(os.path.exists(self.log),
                         "目录缺失不应触发 rsync")


# ---------------------------------------------------------------------------
# nextjs Dockerfile.tmpl 的 Prisma COPY 结构（纯文本断言，不需要 docker）
# ---------------------------------------------------------------------------
class TestNextjsDockerfilePrismaCopy(unittest.TestCase):
    """钉住 v0.8.0 修复后的 COPY 结构：prisma/ 目录整体拷入保持 /app/prisma，
    禁止回退到 `COPY prisma*` 通配；prisma.config 的可选拷贝以注释行形式
    同时存在于 prisma-cli 与 runner 两个 stage（防"config 进不了 runner"回归
    以任何形式复活）。"""

    @classmethod
    def setUpClass(cls):
        with open(NEXTJS_DOCKERFILE_TMPL, encoding="utf-8") as f:
            cls.text = f.read()

    def test_prisma_cli_uses_directory_copy_not_wildcard(self):
        """prisma-cli stage：含 `COPY prisma ./prisma`，且不含 `COPY prisma*` 通配。"""
        self.assertIn("COPY prisma ./prisma", self.text)
        self.assertNotIn("COPY prisma*", self.text)

    def test_runner_has_prisma_config_copy_guidance(self):
        """runner stage：含 prisma.config 可选拷贝指引（注释行也算存在）。"""
        self.assertIn("COPY --from=prisma-cli /app/prisma ./prisma", self.text)
        self.assertIn("COPY --from=prisma-cli /app/prisma.config.ts "
                      "./prisma.config.ts", self.text)


if __name__ == "__main__":
    unittest.main()
