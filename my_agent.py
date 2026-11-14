"""Entry point for evaluate.py:  python evaluate.py --agent my_agent.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agentx.agent import Agent  # noqa: E402,F401
