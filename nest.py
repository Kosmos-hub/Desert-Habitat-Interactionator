# ==================================================
#   NEST SYSTEM (WITH PHYSICAL WALLS)
# ==================================================
import pygame
import math
from config import WIDTH, HEIGHT, PREY_NEST_COLOR, PRED_NEST_COLOR, NEST_BORDER, DECOMP_NEST_COLOR
from utils import dist


class Nest:
    """Zone where creatures of one type are safe from others."""
    def __init__(self, x, y, radius, nest_type):
        self.x = x
        self.y = y
        self.radius = radius
        self.type = nest_type  # "predator", "prey", or "decomposer"
        self.score = 0
        self.wall_thickness = 8  # Thickness of the wall barrier

    def contains(self, creature):
        """Check if a creature is inside this nest zone."""
        return dist(self.x, self.y, creature.x, creature.y) <= self.radius
    
    def is_at_wall(self, x, y):
        """Check if a position is at the wall boundary."""
        d = dist(self.x, self.y, x, y)
        return abs(d - self.radius) <= self.wall_thickness

    def draw(self, surf):
        """Render nest zone with walls."""
        # Draw interior
        if self.type == "prey":
            color = PREY_NEST_COLOR
        elif self.type == "predator":
            color = PRED_NEST_COLOR
        else:  # decomposer
            color = DECOMP_NEST_COLOR
        pygame.draw.circle(surf, color, (int(self.x), int(self.y)), self.radius)
        
        # Draw thick wall border
        pygame.draw.circle(surf, NEST_BORDER, (int(self.x), int(self.y)), self.radius, self.wall_thickness)


class NestManager:
    """Handles all nest zones and access checks."""
    def __init__(self):
        # static initial layout for now
        self.nests = [
            Nest(WIDTH * 0.2, HEIGHT * 0.5, 90, "prey"),
            Nest(WIDTH * 0.8, HEIGHT * 0.5, 90, "predator"),
            Nest(WIDTH * 0.5, HEIGHT * 0.2, 90, "decomposer"),  # top center
        ]

    def can_enter(self, creature, nest):
        """Check if creature type matches nest type."""
        if nest.type == "decomposer":
            return creature.genome.get("is_decomposer", False) or creature.genome["aggression"] <= 0.6
        elif nest.type == "predator":
            return creature.genome["aggression"] > 0.6 and not creature.genome.get("is_decomposer", False)
        elif nest.type == "prey":
            return creature.genome["aggression"] <= 0.6 or creature.genome.get("is_decomposer", False)
        return False
    
    def check_wall_collision(self, creature, new_x, new_y):
        """Check if movement would collide with a nest wall. Returns adjusted position."""
        for nest in self.nests:
            # Skip if creature can enter this nest
            if self.can_enter(creature, nest):
                continue
            
            # Check distance from nest center
            d = dist(nest.x, nest.y, new_x, new_y)
            
            # If trying to cross into or through the wall
            if d < nest.radius + creature.radius:
                # Push creature back outside the wall
                dx = new_x - nest.x
                dy = new_y - nest.y
                if dx == 0 and dy == 0:
                    # If exactly at center, push in a random direction
                    import random
                    angle = random.uniform(0, 6.28)
                    dx = math.cos(angle)
                    dy = math.sin(angle)
                
                length = math.sqrt(dx*dx + dy*dy)
                if length > 0:
                    # Normalize and push to just outside the nest radius
                    nx = dx / length
                    ny = dy / length
                    new_x = nest.x + nx * (nest.radius + creature.radius + 2)
                    new_y = nest.y + ny * (nest.radius + creature.radius + 2)
        
        return new_x, new_y

    def get_nest(self, creature):
        """Return nest matching creature type."""
        if creature.genome.get("is_decomposer", False):
            for n in self.nests:
                if n.type == "decomposer":
                    return n
        elif creature.genome["aggression"] > 0.6:
            for n in self.nests:
                if n.type == "predator":
                    return n
        else:
            for n in self.nests:
                if n.type == "prey":
                    return n
        return None

    def draw(self, surf):
        """Render all nest zones."""
        for n in self.nests:
            n.draw(surf)

    def is_safe_zone(self, c1, c2):
        """Return True if both are in same-type nest zone."""
        for n in self.nests:
            if (n.contains(c1) and n.contains(c2)
                and n.type in ["prey", "predator"]
                and self.can_enter(c1, n)
                and self.can_enter(c2, n)):
                return True
        return False