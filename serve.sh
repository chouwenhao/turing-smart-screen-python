#!/usr/bin/env bash
# turing-smart-screen-python supervisor
# 只在 USB 顯示螢幕插上時執行 main.py:
#  - 沒插螢幕:循環 waits for /dev/ttyACM0(每 15 秒檢查,不耗 CPU)
#  - 插上後:啟動 main.py,並持續檢查裝置存在;拔掉螢幕就會關掉 main.py
# 搭配 systemd user service(Restart=always)即可開機啟用,不用手動操作。
set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEVICE="${TURING_DEVICE:-/dev/ttyACM0}"
PYTHON="$DIR/.venv/bin/python"
MAIN="$DIR/main.py"
CHECK_INTERVAL=15     # 沒插螢幕時的輪詢間隔
POLL_INTERVAL=5       # 插著時檢查裝置是否還在的間隔
RESTART_DELAY=10      # python 異常結束後重試間隔

cd "$DIR"

while true; do
    # 等裝置出現
    while [ ! -e "$DEVICE" ]; do
        sleep "$CHECK_INTERVAL"
    done
    # 確認裝置可讀(單純節點存在不代表可用)
    if [ ! -r "$DEVICE" ]; then
        sleep "$CHECK_INTERVAL"
        continue
    fi

    echo "[serve] 偵測到 $DEVICE,啟動 main.py"
    "$PYTHON" "$MAIN" &
    PY_PID=$!

    # 邊跑邊看裝置還在不在
    while [ -e "$DEVICE" ] && kill -0 "$PY_PID" 2>/dev/null; do
        sleep "$POLL_INTERVAL"
    done

    if kill -0 "$PY_PID" 2>/dev/null; then
        echo "[serve] $DEVICE 已被拔除,關閉 main.py (pid $PY_PID)"
        kill "$PY_PID" 2>/dev/null
        wait "$PY_PID" 2>/dev/null
    else
        echo "[serve] main.py 意外結束 (exit=$(wait "$PY_PID" 2>/dev/null; echo $?)),裝置還在,$RESTART_DELAY 秒後重試"
        sleep "$RESTART_DELAY"
    fi
done
