#!/usr/bin/env python3
"""Optional git hook: keep a codeflow map up to date after every commit.

    python scripts/hook.py install   --modules <repo>/.codeflow/modules.json
    python scripts/hook.py status    [--repo <repo>]
    python scripts/hook.py uninstall [--repo <repo>]

`install` adds a small block (between marker lines) to the repository's post-commit hook. After each
commit the block starts `hook.py run` in the background, which repeats the last analysis with the same
options (saved in modules.json) and rebuilds the HTML the way it was last built (saved in
last-build.json next to modules.json). Thanks to the file cache only changed files are re-read.

Nothing is installed without being asked; `uninstall` removes only the block this script added.
The hook runs only this skill's own scripts, never project code, and does not use the network.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BEGIN = "# >>> codeflow-map (scripts/hook.py) >>>"
END = "# <<< codeflow-map (scripts/hook.py) <<<"


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo)] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True)
    if r.returncode:
        raise SystemExit("git %s failed: %s" % (" ".join(args), r.stderr.strip()))
    return r.stdout.strip()


def hook_file(repo):
    p = Path(git(repo, "rev-parse", "--git-path", "hooks/post-commit"))
    return p if p.is_absolute() else (Path(repo) / p)


def strip_block(text):
    out, skip = [], False
    for line in text.splitlines():
        if line.strip() == BEGIN:
            skip = True
            continue
        if line.strip() == END:
            skip = False
            continue
        if not skip:
            out.append(line)
    return "\n".join(out).rstrip() + "\n" if out else ""


def repo_of(modules):
    data = json.loads(Path(modules).read_text(encoding="utf-8"))
    args, cwd = data.get("args") or [], data.get("cwd") or str(Path(modules).resolve().parent.parent)
    path = next((a for a in args if not a.startswith("-")), ".")   # first positional = repository
    return Path(cwd, path).resolve(), data


def cmd_install(a):
    modules = Path(a.modules).resolve()
    if not modules.is_file():
        raise SystemExit("No %s. Run analyze_modules.py and build_flowmap.py --modules once first." % modules)
    if not (modules.parent / "last-build.json").is_file():
        raise SystemExit("No last-build.json next to %s. Build the map once with build_flowmap.py --modules first." % modules)
    repo, _ = repo_of(modules)
    top = git(repo, "rev-parse", "--show-toplevel")
    hf = hook_file(top)
    old = hf.read_text(encoding="utf-8") if hf.is_file() else ""
    if old and not old.startswith("#!"):
        print("Note: the existing post-commit hook has no #! line; adding the block anyway.")
    body = strip_block(old) if old else "#!/bin/sh\n"
    cmd = "%s %s run --modules %s" % (shlex.quote(sys.executable), shlex.quote(str(HERE / "hook.py")), shlex.quote(str(modules)))
    block = "%s\n# Rebuilds the codeflow map in the background. Remove with: python %s uninstall\n(%s >/dev/null 2>&1 &)\n%s\n" % (
        BEGIN, shlex.quote(str(HERE / "hook.py")), cmd, END)
    hf.parent.mkdir(parents=True, exist_ok=True)
    hf.write_text(body.rstrip("\n") + "\n" + block, encoding="utf-8")
    try:
        os.chmod(str(hf), 0o755)
    except OSError:
        pass
    print("OK  installed in %s. After each commit the map is rebuilt in the background (log: %s)." % (
        hf, modules.parent / "hook.log"))
    return 0


def cmd_uninstall(a):
    hf = hook_file(a.repo)
    if not hf.is_file() or BEGIN not in hf.read_text(encoding="utf-8"):
        print("Nothing to remove: no codeflow-map block in %s." % hf)
        return 0
    rest = strip_block(hf.read_text(encoding="utf-8"))
    if rest.strip() in ("", "#!/bin/sh"):
        hf.unlink()
        print("OK  removed %s (it only held the codeflow-map block)." % hf)
    else:
        hf.write_text(rest, encoding="utf-8")
        print("OK  removed the codeflow-map block from %s; the rest of the hook is unchanged." % hf)
    return 0


def cmd_status(a):
    hf = hook_file(a.repo)
    on = hf.is_file() and BEGIN in hf.read_text(encoding="utf-8")
    print("codeflow-map hook: %s (%s)" % ("installed" if on else "not installed", hf))
    return 0


def cmd_run(a):
    modules = Path(a.modules).resolve()
    log = modules.parent / "hook.log"
    lock = modules.parent / "hook.lock"
    try:   # one rebuild at a time; a stale lock (> 30 min) is ignored
        if lock.exists() and time.time() - lock.stat().st_mtime < 1800:
            return 0
        lock.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        return 0
    try:
        data = json.loads(modules.read_text(encoding="utf-8"))
        cwd = data.get("cwd") or os.getcwd()
        last = json.loads((modules.parent / "last-build.json").read_text(encoding="utf-8"))
        steps = [[sys.executable, str(HERE / "analyze_modules.py")] + list(data.get("args") or [])]
        b = [sys.executable, str(HERE / "build_flowmap.py")]
        if last.get("spec"):
            b.append(last["spec"])
        b += ["--modules", last["modules"], "--out", last["out"]] + (["--cdn"] if last.get("cdn") else [])
        steps.append(b)
        with open(str(log), "a", encoding="utf-8") as fh:
            fh.write("\n== %s\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
            for s in steps:
                fh.flush()
                r = subprocess.run(s, cwd=cwd if s is steps[0] else None, stdout=fh, stderr=subprocess.STDOUT)
                if r.returncode:
                    fh.write("stopped: exit code %d\n" % r.returncode)
                    return r.returncode
        return 0
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


def main(argv=None):
    p = argparse.ArgumentParser(description="Optional git post-commit hook that keeps a codeflow map up to date.")
    sub = p.add_subparsers(dest="cmd")
    i = sub.add_parser("install", help="add the block to .git/hooks/post-commit")
    i.add_argument("--modules", required=True, help="the .codeflow/modules.json of the map to keep fresh")
    for name in ("uninstall", "status"):
        s = sub.add_parser(name)
        s.add_argument("--repo", default=".", help="repository (default: current folder)")
    r = sub.add_parser("run", help="(used by the hook) repeat the last analysis and build")
    r.add_argument("--modules", required=True)
    a = p.parse_args(argv)
    if not a.cmd:
        p.print_help()
        return 1
    return {"install": cmd_install, "uninstall": cmd_uninstall, "status": cmd_status, "run": cmd_run}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
