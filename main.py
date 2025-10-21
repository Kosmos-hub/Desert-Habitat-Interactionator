# ==================================================
#   DESERT EVOLUTION SIMULATOR - MAIN
# ==================================================
import sys
import pygame
from config import WIDTH, HEIGHT, FPS, NUM_CREATURES, INIT_FOOD
from utils import rand_point, dist
from entities import Food
from nest import NestManager
from scent import ScentField
from renderer import draw_scent_field
from creature import Creature
from renderer import (
    draw_desert, 
    draw_food, 
    draw_hud, 
    draw_creature_info, 
    draw_pause_overlay
)

def main():
    """Main game loop."""
    pygame.init()
    pygame.display.set_caption("Desert Evolution - Roman Komarov")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Segoe UI", 18)

    # Initialize world
    nests = NestManager()
    scent_field = ScentField(WIDTH, HEIGHT)
    creatures = [Creature(*rand_point()) for _ in range(NUM_CREATURES)]
    foods = [Food(*rand_point()) for _ in range(INIT_FOOD)]
    
    # Game state
    generation = 0
    last_gen = 0
    hud_flash_timer = 0.0
    running = True
    paused = False
    selected_creature = None
    accum_time = 0.0

    while running:
        dt = clock.tick(FPS) / 1000.0

        # Handle events
        accum_time += dt
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            if event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = pygame.mouse.get_pos()
                
                if event.button == 1:  # Left click - select creature
                    selected_creature = None
                    for c in creatures:
                        if c.alive and dist(mx, my, c.x, c.y) <= c.radius + 4:
                            selected_creature = c
                            break
                
                elif event.button == 3:  # Right click - pause
                    paused = not paused

        # Check keyboard input
        keys = pygame.key.get_pressed()
        if keys[pygame.K_ESCAPE] or keys[pygame.K_q]:
            running = False
        if keys[pygame.K_SPACE]:
            paused = not paused

        # Update simulation (if not paused)
        if not paused:
            if accum_time >= 0.08:  # reduce update frequency to ease CPU
                scent_field.update(accum_time)
                accum_time = 0.0
            for c in creatures:
                generation = c.update(dt, foods, nests, creatures, generation, scent_field)

        # Render everything
        draw_desert(screen)
        draw_scent_field(screen, scent_field)
        nests.draw(screen)
        draw_food(screen, foods)
        
        for c in creatures:
            c.draw(screen)
            c.draw_priority_icons(screen)

        # Draw UI
        max_gen = draw_hud(screen, font, creatures, foods, generation, hud_flash_timer)
        draw_creature_info(screen, font, selected_creature)

        # Handle generation flash
        if max_gen > last_gen:
            hud_flash_timer = 1.0
            last_gen = max_gen
        if hud_flash_timer > 0:
            hud_flash_timer -= dt

        # Draw pause overlay
        if paused:
            draw_pause_overlay(screen, font)

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()