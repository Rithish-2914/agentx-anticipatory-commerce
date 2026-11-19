"""Product search backend. Every search is counted through tools.search, as the rules require.

The agent talks to search only through this interface (search(query, filters, k) -> list of
product dicts, plus max_k, the largest page it returns), so a hosted or semantic search
service can be swapped in without touching the agent. If a backend caps its page size, the
agent detects it and confirms uniqueness with an exact search (see Agent._verify_unique).
"""


class LocalBackend:
    """The starter kit's search.py, through tools.search."""
    name = "local"
    max_k = 200

    def __init__(self, tools):
        self.tools = tools

    def search(self, query, filters, k):
        f = {key: v for key, v in filters.items() if v is not None}
        return self.tools.search(query, f, k=k)


def make_backend(tools):
    return LocalBackend(tools)
