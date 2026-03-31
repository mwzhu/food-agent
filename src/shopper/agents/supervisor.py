from __future__ import annotations

from typing import Any, Dict


async def supervisor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    return {"current_node": "supervisor"}
