# ==================================================
#   WORLD ENTITIES
# ==================================================
from dataclasses import dataclass


@dataclass
class Food:
    """Food item that can be collected by creatures."""
    x: float
    y: float
    alive: bool = True