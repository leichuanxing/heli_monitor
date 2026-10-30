import socket
import sys

with socket.socket() as listener:
    try:
        listener.bind(("0.0.0.0", int(sys.argv[1])))
    except OSError:
        raise SystemExit("所选应用端口已占用或不可绑定，请更换端口后重试")
print("应用端口可用")
