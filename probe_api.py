"""Let the provider strip run the width of the window.

The marquee sat at column width with a mark filling about a fifth of each
card, so it read as a row of mostly empty boxes with paper down both sides.
Full bleed, bigger cards, and a mark scaled to the card. Phones keep the
sizes they already had.
"""
import json, subprocess, ast
from pathlib import Path

PATCH = "diff --git a/index.html b/index.html\nindex 89f3ff7..a3e37ff 100644\n--- a/index.html\n+++ b/index.html\n@@ -126,10 +126,11 @@\n   @media (prefers-reduced-motion: reduce){\n     .fade{animation:none; opacity:1; transform:none;}\n   }\n-  /* Same width as the cards beneath it, so the page reads as one column\n-     rather than a full-bleed band interrupting it. */\n-  .marquee{position:relative; width:100%; margin:0; padding:0; overflow:hidden;\n-    border-radius:14px;\n+  /* Full width of the window, not of the column: the strip is the one band\n+     on this page that should run edge to edge, and at column width it left a\n+     stripe of empty paper down both sides of the screen. */\n+  .marquee{position:relative; width:100vw; margin-left:calc(50% - 50vw); padding:0; overflow:hidden;\n+    border-radius:0;\n     -webkit-mask-image:linear-gradient(90deg,transparent,#000 7%,#000 93%,transparent);\n     mask-image:linear-gradient(90deg,transparent,#000 7%,#000 93%,transparent);}\n   .mq-track{display:flex; gap:clamp(12px,1.5vmin,20px); width:max-content; animation:marquee 46s linear infinite;}\n@@ -137,23 +138,25 @@\n   @keyframes marquee{from{transform:translateX(0);} to{transform:translateX(-50%);}}\n   /* One fixed box size for every provider so the strip reads as a row of\n      equals, with each mark scaled to fit inside rather than overflowing. */\n-  .mq-item{flex:none; display:flex; align-items:center; justify-content:center; gap:14px;\n-    width:clamp(196px,24vmin,340px); height:clamp(104px,15.5vmin,232px);\n-    padding:0 clamp(16px,2vmin,26px); box-sizing:border-box;\n+  .mq-item{flex:none; display:flex; align-items:center; justify-content:center; gap:18px;\n+    width:clamp(230px,28vmin,420px); height:clamp(120px,18vmin,280px);\n+    padding:0 clamp(18px,2.4vmin,32px); box-sizing:border-box;\n     background:var(--white); border:1px solid var(--line); border-left:3px solid var(--mq);\n     border-radius:10px; white-space:nowrap;\n     text-decoration:none; cursor:pointer;\n     transition:transform .18s, box-shadow .18s;}\n   .mq-item:hover{transform:translateY(-3px); box-shadow:0 6px 16px rgba(21,32,25,0.12);}\n+  /* The mark filled about a fifth of its card before, which is what made the\n+     strip read as mostly empty boxes. Scale it with the card. */\n   .mq-logo{display:flex; align-items:center; justify-content:center;\n-    height:38px; width:132px; color:var(--mq); flex:none;}\n+    height:clamp(46px,7vmin,86px); width:clamp(150px,18vmin,260px); color:var(--mq); flex:none;}\n   /* both kinds of mark get the same envelope */\n-  .mq-logo svg, .mq-logo img{max-height:38px; max-width:132px;\n+  .mq-logo svg, .mq-logo img{max-height:clamp(46px,7vmin,86px); max-width:clamp(150px,18vmin,260px);\n     height:auto; width:auto; object-fit:contain; display:block;}\n-  .mq-name{font-family:'Fraunces',serif; font-size:19px; color:var(--mq); line-height:1.15;\n-    text-align:center; white-space:normal; max-width:132px;}\n-  .mq-n{font-family:'IBM Plex Mono',monospace; font-size:12px; color:var(--ink-faint);\n-    flex:none; padding-left:13px; border-left:1px solid var(--line);}\n+  .mq-name{font-family:'Fraunces',serif; font-size:clamp(20px,2.4vmin,30px); color:var(--mq); line-height:1.15;\n+    text-align:center; white-space:normal; max-width:clamp(150px,18vmin,260px);}\n+  .mq-n{font-family:'IBM Plex Mono',monospace; font-size:clamp(13px,1.5vmin,17px); color:var(--ink-faint);\n+    flex:none; padding-left:15px; border-left:1px solid var(--line);}\n   .count{display:block; font-family:'IBM Plex Mono',monospace; font-size:13px;\n     letter-spacing:0.08em; color:var(--ink-faint); margin-top:30px;}\n   .count b{color:var(--teal-deep); font-weight:500; font-size:19px;}\n"

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

report["fullBleed"] = "width:100vw" in Path("index.html").read_text()
home = Path("index.html").read_text()
report["biggerCards"] = "clamp(230px,28vmin,420px)" in home
report["biggerMarks"] = "clamp(46px,7vmin,86px)" in home

Path("data/api-probe.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
if report["applied"]:
    subprocess.run(["git", "config", "user.name", "ledger-bot"], check=False)
    subprocess.run(["git", "config", "user.email", "bot@users.noreply.github.com"], check=False)
    subprocess.run(["git", "add", "-A"], check=False)
    subprocess.run(["git", "commit", "-m", "Let the provider strip run the width of the window, with marks that fill their cards"], check=False)
    subprocess.run(["git", "push"], check=False)
