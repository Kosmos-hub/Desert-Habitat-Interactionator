# ==================================================
#   SCENT SYSTEM (Diffusion + Lightweight Visualization)
# ==================================================
import pygame
import numpy as np
from utils import clamp

CELL_SIZE = 25  # coarser grid for speed
DIFFUSE_RATE = 0.22
DECAY_RATE = 0.025

class ScentField:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.cell_size = CELL_SIZE
        self.cols = width // CELL_SIZE
        self.rows = height // CELL_SIZE

        # scent layers for each type
        self.maps = {
        "food": np.zeros((self.rows, self.cols), dtype=np.float32),
        "pred": np.zeros((self.rows, self.cols), dtype=np.float32),
        "prey": np.zeros((self.rows, self.cols), dtype=np.float32),
        "toxin": np.zeros((self.rows, self.cols), dtype=np.float32),
        "corpse": np.zeros((self.rows, self.cols), dtype=np.float32),  # NEW
        }

        # pre-blurred visualization surface
        self.visual = pygame.Surface((width, height), pygame.SRCALPHA)

    def emit(self, x, y, scent_type, strength=1.0):
        """Deposit scent into grid."""
        if scent_type not in self.maps:
            return
        c = int(x // CELL_SIZE)
        r = int(y // CELL_SIZE)
        if 0 <= r < self.rows and 0 <= c < self.cols:
            self.maps[scent_type][r, c] = clamp(
                self.maps[scent_type][r, c] + strength * 0.9, 0, 1.0
            )

    def diffuse(self, grid):
        """Simple and fast diffusion using shifted sums."""
        new_grid = grid.copy()
        new_grid[1:-1, 1:-1] += DIFFUSE_RATE * (
            grid[:-2, 1:-1]
            + grid[2:, 1:-1]
            + grid[1:-1, :-2]
            + grid[1:-1, 2:]
            - 4 * grid[1:-1, 1:-1]
        )
        decay = DECAY_RATE * (0.4 if grid is self.maps.get("corpse") else 1.0)
        new_grid *= (1.0 - decay)
        np.clip(new_grid, 0, 1.0, out=new_grid)
        return new_grid

    def update(self, dt):
        """Diffuse and decay all scent maps."""
        for key in self.maps:
            self.maps[key] = self.diffuse(self.maps[key])

    def sample_gradient(self, x, y, scent_type):
        """Return normalized gradient vector toward stronger scent concentration."""
        if scent_type not in self.maps:
            return None
        c = int(x // CELL_SIZE)
        r = int(y // CELL_SIZE)
        if not (1 <= r < self.rows - 1 and 1 <= c < self.cols - 1):
            return None
        grid = self.maps[scent_type]
        dx = grid[r, c + 1] - grid[r, c - 1]
        dy = grid[r + 1, c] - grid[r - 1, c]
        if dx == 0 and dy == 0:
            return None
        return dx, dy

    def draw(self, surf):
        """Draw faint scent intensity map as soft colored fog."""
        self.visual.fill((0, 0, 0, 0))
        px = pygame.surfarray.pixels_alpha(self.visual)

        for scent_type, color in {
            "food": (60, 180, 100),
            "prey": (80, 150, 255),
            "pred": (255, 80, 80),
            "toxin": (150, 60, 200), 
        }.items():
            grid = self.maps[scent_type]
            # upscale scent grid to pixel map
            scaled = np.kron(grid, np.ones((CELL_SIZE, CELL_SIZE)))
            scaled = np.clip(scaled * 220, 0, 255).astype(np.uint8)
            h, w = scaled.shape
            px[:h, :w] = np.maximum(px[:h, :w], scaled)

        del px  # unlock surface
        surf.blit(self.visual, (0, 0))
