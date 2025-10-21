# ==================================================
#   NEST SYSTEM
# ==================================================
import pygame
from config import WIDTH, HEIGHT, PREY_NEST_COLOR, PRED_NEST_COLOR, NEST_BORDER
from utils import dist


class Nest:
    """Zone where creatures of one type are safe from others."""
    def __init__(self, x, y, radius, nest_type):
        self.x = x
        self.y = y
        self.radius = radius
        self.type = nest_type  # "predator" or "prey"
        self.score = 0

    def contains(self, creature):
        """Check if a creature is inside this nest zone."""
        return dist(self.x, self.y, creature.x, creature.y) <= self.radius

    def draw(self, surf):
        """Render nest zone."""
        color = PREY_NEST_COLOR if self.type == "prey" else PRED_NEST_COLOR
        pygame.draw.circle(surf, color, (int(self.x), int(self.y)), self.radius)
        pygame.draw.circle(surf, NEST_BORDER, (int(self.x), int(self.y)), self.radius, 3)


class NestManager:
    """Handles all nest zones and access checks."""
    def __init__(self):
        # static initial layout for now
        self.nests = [
            Nest(WIDTH * 0.2, HEIGHT * 0.5, 90, "prey"),
            Nest(WIDTH * 0.8, HEIGHT * 0.5, 90, "predator")
        ]

    def can_enter(self, creature, nest):
        """Prevent predators from entering prey nests."""
        if nest.type == "prey" and creature.genome["aggression"] > 0.6:
            return False
        return True

    def get_nest(self, creature):
        """Return nest matching creature type."""
        if creature.genome["aggression"] > 0.6:
            for n in self.nests:
                if n.type == "predator":
                    return n
        else:
            for n in self.nests:
                if n.type == "prey":
                    return n
        return None

    def draw(self, surf):
        for nest in self.nests:
            nest.draw(surf)

    def is_safe_zone(self, c1, c2):
        """Return True if both are in same-type nest zone."""
        for n in self.nests:
            if (n.contains(c1) and n.contains(c2)
                and n.type in ["prey", "predator"]
                and self.can_enter(c1, n)
                and self.can_enter(c2, n)):
                return True
        return False