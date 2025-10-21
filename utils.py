# ==================================================
#   UTILITY FUNCTIONS
# ==================================================
import math
import random
from config import WIDTH, HEIGHT


def clamp(x, lo, hi):
    """Clamp value between lo and hi."""
    return max(lo, min(hi, x))


def vec_len(vx, vy):
    """Calculate vector length."""
    return math.hypot(vx, vy)


def norm(vx, vy):
    """Normalize vector to unit length."""
    l = vec_len(vx, vy)
    if l == 0:
        return 0.0, 0.0
    return vx / l, vy / l


def dist(ax, ay, bx, by):
    """Calculate distance between two points."""
    return math.hypot(ax - bx, ay - by)


def rand_point(margin=20):
    """Generate random point within screen bounds."""
    return (
        random.uniform(margin, WIDTH - margin),
        random.uniform(margin, HEIGHT - margin),
    )