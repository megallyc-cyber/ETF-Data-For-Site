"""Let each mark fill its envelope.

A viewBox-only SVG drew at its own intrinsic size, so BMO and Global X sat
small inside the same card that NEOS filled. Scale every mark to the box.
"""
import json, subprocess, ast
from pathlib import Path

PATCH = "diff --git a/index.html b/index.html\nindex a3e37ff..0e13dd9 100644\n--- a/index.html\n+++ b/index.html\n@@ -151,8 +151,11 @@\n   .mq-logo{display:flex; align-items:center; justify-content:center;\n     height:clamp(46px,7vmin,86px); width:clamp(150px,18vmin,260px); color:var(--mq); flex:none;}\n   /* both kinds of mark get the same envelope */\n-  .mq-logo svg, .mq-logo img{max-height:clamp(46px,7vmin,86px); max-width:clamp(150px,18vmin,260px);\n-    height:auto; width:auto; object-fit:contain; display:block;}\n+  /* Fill the envelope rather than sit at the mark's own intrinsic size: a\n+     viewBox-only SVG (BMO, Global X) otherwise drew at a fraction of the\n+     space while NEOS filled it, so the row looked uneven. */\n+  .mq-logo svg, .mq-logo img{width:100%; height:100%;\n+    object-fit:contain; display:block;}\n   .mq-name{font-family:'Fraunces',serif; font-size:clamp(20px,2.4vmin,30px); color:var(--mq); line-height:1.15;\n     text-align:center; white-space:normal; max-width:clamp(150px,18vmin,260px);}\n   .mq-n{font-family:'IBM Plex Mono',monospace; font-size:clamp(13px,1.5vmin,17px); color:var(--ink-faint);\n"

report = {}
Path("data").mkdir(exist_ok=True)
Path("/tmp/fix.patch").write_text(PATCH)
r = subprocess.run(["git", "apply", "--check", "/tmp/fix.patch"], capture_output=True, text=True)
if r.returncode == 0:
    subprocess.run(["git", "apply", "/tmp/fix.patch"], check=True)
    report["applied"] = True
else:
    report["applied"] = False
    report["error"] = r.stderr[:300]

report["fills"] = "width:100%; height:100%" in Path("index.html").read_text()
home = Path("index.html").read_text()
report["envelopeKept"] = "clamp(46px,7vmin,86px)" in home

Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
if report["applied"]:
    subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
    subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
    subprocess.run(["git", "add", "-A"], check=False)
    subprocess.run(["git", "commit", "-m", "Let each mark fill its envelope so the row reads as equals"], check=False)
    subprocess.run(["git", "push"], check=False)
