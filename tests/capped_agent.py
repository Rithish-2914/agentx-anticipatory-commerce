import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agentx.agent import Agent as _A
from agentx.backends import LocalBackend
class Capped(LocalBackend):
    max_k = 20
class Agent(_A):
    def __init__(self, tools):
        super().__init__(tools); self.backend = Capped(tools)
