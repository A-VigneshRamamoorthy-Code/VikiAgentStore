"""SSH / rsync transport to the burst VM."""
from __future__ import annotations

import os
import shutil
import subprocess
import time

from azc_common import KEYS_DIR, ensure_dirs, fail, ok, say, warn

KNOWN_HOSTS = os.path.join(KEYS_DIR, "known_hosts")

SSH_OPTS = [
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", f"UserKnownHostsFile={KNOWN_HOSTS}",
    "-o", "ConnectTimeout=10",
    "-o", "ServerAliveInterval=15",
    "-o", "ServerAliveCountMax=4",
    "-o", "LogLevel=ERROR",
    "-o", "BatchMode=yes",
]


def key_paths(job_id: str) -> tuple[str, str]:
    priv = os.path.join(KEYS_DIR, f"{job_id}")
    return priv, priv + ".pub"


def make_key(job_id: str) -> tuple[str, str]:
    ensure_dirs()
    priv, pub = key_paths(job_id)
    if os.path.exists(priv):
        return priv, pub
    subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-q",
                    "-C", f"azc-{job_id}", "-f", priv], check=True)
    os.chmod(priv, 0o600)
    return priv, pub


def drop_key(job_id: str) -> None:
    for path in key_paths(job_id):
        try:
            os.remove(path)
        except OSError:
            pass


def _ssh_base(job: dict) -> list[str]:
    priv, _ = key_paths(job["id"])
    return ["ssh", "-i", priv, *SSH_OPTS, f"{job['user']}@{job['ip']}"]


def wait_for_ssh(job: dict, timeout: int = 420) -> None:
    say(f"waiting for ssh on {job['ip']} …")
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        proc = subprocess.run(_ssh_base(job) + ["true"],
                              capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            ok("ssh up")
            return
        last = (proc.stderr or "").strip().splitlines()[-1:] or [""]
        last = last[0]
        time.sleep(6)
    fail(f"ssh never came up on {job['ip']} ({last})")


def wait_for_cloud_init(job: dict, timeout: int = 1500) -> None:
    """Block until provisioning finishes, so a job never runs on a half-built box."""
    say("waiting for provisioning (cloud-init) …")
    proc = subprocess.run(
        _ssh_base(job) + ["sudo cloud-init status --wait >/dev/null 2>&1; "
                          "sudo cloud-init status --long || true"],
        capture_output=True, text=True, timeout=timeout)
    out = (proc.stdout or "") + (proc.stderr or "")
    if "status: error" in out or "status: degraded" in out:
        warn("cloud-init reported problems — some packages may be missing:\n" + out.strip())
    else:
        ok("machine provisioned")


def heartbeat(job: dict) -> None:
    """Tell the on-box watchdog the controller is still alive."""
    subprocess.run(_ssh_base(job) + ["touch /var/lib/azc/heartbeat 2>/dev/null || true"],
                   capture_output=True, text=True, timeout=40, check=False)


def run(job: dict, command: str, stream: bool = True,
        timeout: int = 86400) -> int:
    """Run a shell command on the VM. Output is streamed straight through."""
    heartbeat(job)
    wrapped = f"set -o pipefail; cd {job.get('workdir', '~')} 2>/dev/null || cd ~; {command}"
    args = _ssh_base(job) + [wrapped]
    if stream:
        return subprocess.run(args, timeout=timeout).returncode
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    print(proc.stdout, end="")
    if proc.returncode != 0:
        warn(proc.stderr.strip())
    return proc.returncode


def capture(job: dict, command: str, timeout: int = 300) -> str:
    proc = subprocess.run(_ssh_base(job) + [command],
                          capture_output=True, text=True, timeout=timeout)
    return (proc.stdout or "").strip()


def _rsync_ssh(job: dict) -> str:
    priv, _ = key_paths(job["id"])
    return "ssh -i %s %s" % (priv, " ".join(SSH_OPTS))


_RSYNC_FLAGS = ["-az"]


def rsync_flags() -> list[str]:
    """Flags every rsync understands.

    macOS ships openrsync, which reports `openrsync: protocol version 29` on its
    first line and rejects GNU extensions such as --info. Version-sniffing that
    output reads the *protocol* number as the version, so we do not sniff at all:
    -az and --delete are supported by both openrsync and GNU rsync, and --info is
    only cosmetic.
    """
    return list(_RSYNC_FLAGS)


def have_rsync() -> bool:
    return bool(shutil.which("rsync"))


def push(job: dict, local: str, remote: str) -> None:
    local = os.path.abspath(os.path.expanduser(local))
    if not os.path.exists(local):
        fail(f"nothing to push: {local} does not exist")
    say(f"uploading {local} → {remote}")
    if not have_rsync():
        _tar_push(job, local, remote)
    else:
        # Trailing slash => copy contents, not the directory itself.
        src = local + "/" if os.path.isdir(local) else local
        run_rsync(rsync_flags() + ["--delete", "-e", _rsync_ssh(job), src,
                                   f"{job['user']}@{job['ip']}:{remote}"],
                  job, remote_mkdir=remote)
    ok("upload complete")


def pull(job: dict, remote: str, local: str) -> None:
    local = os.path.abspath(os.path.expanduser(local))
    os.makedirs(local, exist_ok=True)
    say(f"downloading {remote} → {local}")
    if not have_rsync():
        _tar_pull(job, remote, local)
    else:
        # A directory source needs a trailing slash, or rsync nests it one level
        # deeper than asked. A file source must not have one.
        src = remote.rstrip("/")
        if capture(job, f"test -d '{src}' && echo d || echo f") == "d":
            src += "/"
        run_rsync(rsync_flags() + ["-e", _rsync_ssh(job),
                                   f"{job['user']}@{job['ip']}:{src}",
                                   local + "/"], job)
    ok("download complete")


def _tar_push(job: dict, local: str, remote: str) -> None:
    parent, name = os.path.dirname(local), os.path.basename(local)
    tar = subprocess.Popen(["tar", "-czf", "-", "-C", parent, name],
                           stdout=subprocess.PIPE)
    ssh = subprocess.Popen(
        _ssh_base(job) + [f"mkdir -p {remote} && tar -xzf - -C {remote} --strip-components=1"],
        stdin=tar.stdout)
    tar.stdout.close()
    if ssh.wait() != 0:
        fail("tar upload failed")


def _tar_pull(job: dict, remote: str, local: str) -> None:
    ssh = subprocess.Popen(
        _ssh_base(job) + [f"tar -czf - -C $(dirname {remote}) $(basename {remote})"],
        stdout=subprocess.PIPE)
    tar = subprocess.Popen(["tar", "-xzf", "-", "-C", local,
                            "--strip-components=1"], stdin=ssh.stdout)
    ssh.stdout.close()
    if tar.wait() != 0:
        fail("tar download failed")


def run_rsync(args: list[str], job: dict, remote_mkdir: str | None = None) -> None:
    heartbeat(job)
    if remote_mkdir:
        subprocess.run(_ssh_base(job) + [f"mkdir -p {remote_mkdir}"],
                       capture_output=True, text=True, timeout=60, check=False)
    proc = subprocess.run(["rsync"] + args, capture_output=True, text=True,
                          timeout=14400)
    if proc.returncode != 0:
        fail(f"rsync failed:\n{(proc.stderr or proc.stdout).strip()}")


def mark_done(job: dict) -> None:
    """Arm the watchdog to tear the machine down at its next tick."""
    subprocess.run(_ssh_base(job) + ["touch /var/lib/azc/done 2>/dev/null || true"],
                   capture_output=True, text=True, timeout=40, check=False)
