# Regenerate DragonBall35H cleanly, then re-apply the two follow-up edits:
#   1) retarget the static NETWORK label -> LLM and hide the real NET text
#   2) inject CUSTOM LLM total + rate text blocks (no line graph)
# The baked-in "VOLUME" word in the source background is erased by
# build_dragonball35L.py, so the "LLM" label no longer ghosts as "LLMUME".
import subprocess, sys

subprocess.run([sys.executable, "res/themes/build_dragonball35L.py"], check=True)

p = "res/themes/DragonBall35H/theme.yaml"
t = open(p).read()

t = t.replace("   TEXT: NETWORK", "   TEXT: LLM")
t = t.replace(
    "NET:\n    INTERVAL: 1\n    ETH:\n      UPLOAD:\n        TEXT:\n          SHOW: True",
    "NET:\n    INTERVAL: 0\n    ETH:\n      UPLOAD:\n        TEXT:\n          SHOW: False",
)

custom = """  CUSTOM:
    INTERVAL: 1
    LLMTokenTotal:
      TEXT:
        SHOW: True
        X: 101
        Y: 40
        FONT: jetbrains-mono/JetBrainsMono-ExtraBold.ttf
        FONT_SIZE: 17
        FONT_COLOR: 255, 224, 139
        BACKGROUND_IMAGE: background.png
    LLMTokenRate:
      TEXT:
        SHOW: True
        X: 101
        Y: 58
        FONT: jetbrains-mono/JetBrainsMono-Bold.ttf
        FONT_SIZE: 14
        FONT_COLOR: 255, 255, 255
        BACKGROUND_IMAGE: background.png
"""
t = t.replace("  DATE:", custom + "  DATE:", 1)

# no line graph anywhere under CUSTOM (user removed it)
assert "LINE_GRAPH" not in t.split("CUSTOM:")[1].split("DATE:")[0]

open(p, "w").write(t)
print("DragonBall35H regenerated: LLM label, NET hidden, CUSTOM total+rate, no line graph")
