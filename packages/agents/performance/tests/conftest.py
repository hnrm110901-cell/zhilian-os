import sys
from pathlib import Path

# Add agent root dir so `from src.agent import ...` works (src is a package)
agent_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(agent_root))
# Add base_agent (lives in apps/api-gateway/src/core)
sys.path.insert(0, str(agent_root.parent.parent.parent / "apps" / "api-gateway" / "src" / "core"))
