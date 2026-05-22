import argparse
import os
import socket

import uvicorn


def get_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        hostname = socket.gethostname()
        for address in socket.gethostbyname_ex(hostname)[2]:
            if not address.startswith("127."):
                return address

    return "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run HomeCache on your local network.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-reload", action="store_true")
    args = parser.parse_args()

    lan_ip = get_lan_ip()
    base_url = f"http://{lan_ip}:{args.port}"
    os.environ["BASE_URL"] = base_url

    print(f"HomeCache is starting at {base_url}")
    print("Open that URL from another device on the same network.")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=args.port,
        reload=not args.no_reload,
    )


if __name__ == "__main__":
    main()
