# ==================================================
#   DESERT EVOLUTION SIMULATOR - MAIN
# ==================================================
import sys
import random
import pygame
from config import *
from utils import rand_point, dist
from entities import Food, Corpse
from nest import NestManager
from scent import ScentField
from renderer import draw_scent_field, draw_corpses
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
    pygame.display.set_caption("Desert Interactionator - Roman Komarov")
    flags = 0
    fullscreen = False
    screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Segoe UI", 18)

    # Initialize world
    nests = NestManager()
    scent_field = ScentField(WIDTH, HEIGHT)
    
    # Create creatures with some decomposers
    creatures = []
    for i in range(NUM_CREATURES):
        x, y = rand_point()
        if i < NUM_CREATURES // 5:  # 20% decomposers
            genome = {
                "size": random.uniform(0.6, 1.2),
                "speed": 0.5,  # Not used for decomposers
                "vision": random.uniform(70, 120),
                "metabolism": random.uniform(0.7, 1.3),
                "aggression": 0.0,
                "toxin": random.uniform(0.4, 1.0),
                "is_decomposer": True,
            }
            creatures.append(Creature(x, y, genome))
        else:
            creatures.append(Creature(x, y))
    
    foods = [Food(*rand_point()) for _ in range(INIT_FOOD)]
    corpses = []  # NEW - list of corpses
    
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

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_f:
                    fullscreen = not fullscreen
                    if fullscreen:
                        screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
                    else:
                        screen = pygame.display.set_mode((WIDTH, HEIGHT))

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
            
            # Track newly dead creatures
            newly_dead = []
            
            for c in creatures:
                was_alive = c.alive
                gen_new = c.update(dt, foods, nests, creatures, generation, scent_field, corpses)
                generation = max(generation, gen_new)
                
                # NEW: Create corpse when creature dies
                if was_alive and not c.alive:
                    newly_dead.append(c)
            
            # Create corpses from newly dead creatures
            for dead in newly_dead:
                corpse_energy = dead.energy_max * CORPSE_ENERGY_MULTIPLIER
                corpse = Corpse(
                    x=dead.x,
                    y=dead.y,
                    energy=corpse_energy,
                    max_energy=corpse_energy,
                    radius=dead.radius * 0.8
                )
                corpses.append(corpse)

            # --- Corpse scent emission ---
            for corpse in corpses:
                if not corpse.alive:
                    continue

                # Scent intensity based on remaining energy
                intensity = 0.1 + (corpse.energy / corpse.max_energy) * 0.3  # 0.1 to 0.4

                # Correct grid position
                cell_x = int(corpse.x // scent_field.cell_size)
                cell_y = int(corpse.y // scent_field.cell_size)

                # Emit stronger scent repeatedly
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        cx = cell_x + dx
                        cy = cell_y + dy
                        if 0 <= cx < scent_field.cols and 0 <= cy < scent_field.rows:
                            scent_field.maps["corpse"][cy, cx] = min(
                                0.6,  # max scent cap
                                scent_field.maps["corpse"][cy, cx] + intensity / (1 + dx * dx + dy * dy)
                            )



            
            # Clean up fully consumed corpses (remove those with no energy)
            corpses[:] = [c for c in corpses if c.alive and c.energy > 0]
            creatures[:] = [c for c in creatures if c.alive]

       # Render everything
        draw_desert(screen)
        draw_scent_field(screen, scent_field)
        nests.draw(screen)
        draw_corpses(screen, corpses)  # NEW - draw corpses
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