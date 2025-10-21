# ==================================================
#   RENDERING FUNCTIONS
# ==================================================
import pygame
from config import WIDTH, HEIGHT, SAND, DUNE, FOOD_COLOR, FOOD_RADIUS
from scent import CELL_SIZE


def draw_desert(surf):
    """Draw desert background with dunes."""
    surf.fill(SAND)
    for i in range(5):
        y = int((i + 1) * HEIGHT / 6)
        pygame.draw.line(surf, DUNE, (0, y), (WIDTH, y), 1)


def draw_food(surf, foods):
    """Draw all active food items."""
    for f in foods:
        if f.alive:
            pygame.draw.circle(surf, FOOD_COLOR, (int(f.x), int(f.y)), FOOD_RADIUS)

def draw_scent_field(screen, scent_field):
    """Render scent maps with vivid diffusion heatmaps."""
    # create full-screen alpha surface
    scent_layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

    # color mapping per scent type
    colors = {
        "pred": (255, 60, 60),    # strong red glow for predators
        "prey": (80, 255, 120),   # green for prey
        "food": (255, 230, 90),   # yellowish for food
    }

    for scent_type, color in colors.items():
        grid = scent_field.maps[scent_type]
        rows, cols = grid.shape

        for r in range(rows):
            for c in range(cols):
                intensity = grid[r, c]
                if intensity <= 0.01:
                    continue

                # stronger and brighter visual scaling
                alpha = int(255 * (intensity ** 0.8))
                if alpha > 255:
                    alpha = 255

                # larger spread for obvious look
                rect = pygame.Rect(
                    c * CELL_SIZE - CELL_SIZE // 2,
                    r * CELL_SIZE - CELL_SIZE // 2,
                    CELL_SIZE * 1.5,
                    CELL_SIZE * 1.5
                )
                pygame.draw.ellipse(
                    scent_layer,
                    (*color, alpha),
                    rect
                )

    # subtle blur effect via repeated scaling
    blurred = pygame.transform.smoothscale(scent_layer, (WIDTH // 2, HEIGHT // 2))
    blurred = pygame.transform.smoothscale(blurred, (WIDTH, HEIGHT))

    # blend the scent map under everything
    screen.blit(blurred, (0, 0))

def draw_hud(surf, font, creatures, foods, generation, hud_flash_timer):
    """Draw HUD with statistics."""
    from config import HUD_COLOR
    
    alive = sum(1 for c in creatures if c.alive)
    avg_e = 0.0 if alive == 0 else sum(c.energy for c in creatures if c.alive) / alive
    max_gen = max((c.generation for c in creatures if c.alive), default=0)

    hud_lines = [
        f"Creatures: {alive}/{len(creatures)}",
        f"Food: {sum(1 for f in foods if f.alive)}",
        f"Generation: {max_gen}",
        f"Avg Energy: {avg_e:5.1f}",
        "L-click: select   R-click: pause   Esc/Q: quit",
    ]

    for i, text in enumerate(hud_lines):
        if "Generation" in text and hud_flash_timer > 0:
            fade = int(255 * (hud_flash_timer / 1.0))
            gen_color = (fade // 2, 255, fade // 2)
            surf.blit(font.render(text, True, gen_color), (12, 10 + i * 20))
        else:
            surf.blit(font.render(text, True, HUD_COLOR), (12, 10 + i * 20))

    return max_gen


def draw_creature_info(surf, font, creature):
    """Draw info panel for selected creature."""
    from config import INFO_BG, INFO_TEXT
    
    if not creature or not creature.alive:
        return

    c = creature
    bx, by = int(c.x + c.radius + 20), int(c.y - 50)
    info_lines = [
        f"Energy: {c.energy:.1f}/{c.energy_max:.1f}",
        f"Escape: {c.priorities.get('escape', 0):.2f}",
        f"Gather: {c.priorities.get('gather', 0):.2f}",
        f"Mate: {c.priorities.get('mate', 0):.2f}",
    ]
    pad = 6
    w = 140
    h = len(info_lines) * 18 + pad * 2
    panel = pygame.Surface((w, h))
    panel.fill(INFO_BG)
    pygame.draw.rect(panel, (0, 0, 0), panel.get_rect(), 1)
    for i, text in enumerate(info_lines):
        panel.blit(font.render(text, True, INFO_TEXT), (pad, pad + i * 18))
    surf.blit(panel, (bx, by))


def draw_pause_overlay(surf, font):
    """Draw pause overlay."""
    from config import PAUSE_OVERLAY
    
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill(PAUSE_OVERLAY)
    surf.blit(overlay, (0, 0))
    pause_text = font.render("PAUSED — Right-click or Space to Resume", True, (255, 255, 255))
    surf.blit(pause_text, (WIDTH/2 - pause_text.get_width()/2, HEIGHT/2))