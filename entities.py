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


@dataclass
class Corpse:
    """Dead creature body that decomposers can consume."""
    x: float
    y: float
    energy: float  # Remaining energy in corpse
    max_energy: float  # Original energy (for display)
    radius: float  # Size of the corpse
    alive: bool = True  # Whether it still has energy
    
    def consume(self, amount):
        """Remove energy from corpse, return actual amount consumed."""
        actual = min(amount, self.energy)
        self.energy -= actual
        self.radius = max(2, self.radius * (self.energy / self.max_energy) ** 0.5)
        if self.energy <= 0:
            self.alive = False
        return actual