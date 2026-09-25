"""Start Sluicer's MCP server over stdio, as an MCPB host runs it.

The host installs the bundle's one dependency, ``sluicer[mcp]`` at the version
its manifest names, with uv, and runs this file in that environment. The
server is the one ``sluicer mcp`` starts: nothing here adds to it.
"""

from sluicer.mcp_server import main

if __name__ == "__main__":
    main()
