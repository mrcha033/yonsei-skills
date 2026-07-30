"""Shared command runtime for authenticated Yonsei student services."""

if __name__ == "__main__":
    print("Yonsei Bridge package. Run cli.py --help or mcp_server.py.")
else:
    from .bridge import YonseiBridge

    __all__ = ["YonseiBridge"]
