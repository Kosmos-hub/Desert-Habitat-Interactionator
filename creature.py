# ==================================================
#   CREATURE CLASS
# ==================================================
import math
import random
import pygame
from config import *
from utils import clamp, vec_len, norm, dist, rand_point
from entities import Food


class Creature:
    """Autonomous agent with evolving genome and priorities."""
    def __init__(self, x, y, genome=None):
        # --- position + motion ---
        self.x, self.y = x, y
        theta = random.uniform(0, math.tau)
        self.vx, self.vy = math.cos(theta), math.sin(theta)
        self.wander_t = random.uniform(0.5, 2.0)

        # --- state ---
        self.carrying = False
        self.target_food = None
        self.target_prey = None
        self.alive = True
        self.ready_to_mate = False
        self.flash_timer = 0.0
        self.calling = False
        self.call_timer = 0.0
        self.mate_drive = 0.0
        self.responding = False
        self.response_timer = 0.0
        self.partner = None
        self.call_cooldown = random.uniform(0, CALL_COOLDOWN)
        self.heard_call = None

        # --- genome ---
        self.genome = genome if genome else {
            "size": random.uniform(0.6, 1.6),
            "speed": random.uniform(0.7, 1.4),
            "vision": random.uniform(60, 140),
            "metabolism": random.uniform(0.6, 1.4) if genome and genome.get("aggression", 0) > 0.6 else random.uniform(0.8, 1.8),
            "aggression": random.uniform(0, 1),
        }

        # --- derived stats ---
        self.radius = BASE_RADIUS * self.genome["size"]
        self.base_speed = CREATURE_BASE_SPEED * self.genome["speed"]
        self.energy_max = ENERGY_BASE_MAX * self.genome["size"]
        self.energy = random.uniform(0.6 * self.energy_max, self.energy_max)

        # --- nest reference ---
        self.last_scent_drop = 0.0
        self.scent_type = "pred" if self.genome["aggression"] > 0.6 else "prey"
        self.nest = None
        self.home_score = 0
        self.generation = 0

    @property
    def speed(self):
        """Calculate current speed based on state."""
        s = self.base_speed * (CARRY_SLOWDOWN if self.carrying else 1.0)
        if self.energy < LOW_ENERGY_THRESH:
            s *= 0.65 + 0.35 * (self.energy / LOW_ENERGY_THRESH)
        return s
    
    def draw_heart_pulse(self, surf):
        """Draws a fading heart pulse around mating pairs."""
        if not hasattr(self, "heart_pulse_timer") or self.heart_pulse_timer <= 0:
            return
        self.heart_pulse_timer -= 0.016  # ~60fps frame delta
        t = 1 - (self.heart_pulse_timer / 1.2)
        alpha = max(0, 255 - int(t * 255))
        size = int(self.radius + 30 * t)
        color = (255, 100, 180, alpha)

        ring_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        # heart shape points (scaled & centered)
        for i in range(6):
            heart_x = self.x + size * 0.8 * math.sin(i * math.pi / 3)
            heart_y = self.y - size * 0.6 * math.cos(i * math.pi / 3)
            pygame.draw.circle(ring_surface, color, (int(heart_x), int(heart_y)), 5)
        pygame.draw.circle(ring_surface, color, (int(self.x), int(self.y)), size, 2)
        surf.blit(ring_surface, (0, 0))


    # ==================================================
    #   UPDATE LOOP
    # ==================================================
    def update(self, dt, foods, nests, creatures, generation, scent_field):
        if not self.alive:
            return generation

        self.flash_timer = max(0.0, self.flash_timer - dt)
        self.mate_drive = clamp(self.mate_drive + MATE_DRIVE_RATE * dt, 0.0, 0.9)

        # --- drop scent less often for performance ---
        self.last_scent_drop += dt
        if self.last_scent_drop > 0.9:
            scent_field.emit(self.x, self.y, self.scent_type, 1.0)
            self.last_scent_drop = 0.0

        # --- call / response timing (unchanged) ---
        if self.call_timer > 0:
            self.call_timer -= dt
            if self.call_timer <= 0:
                self.calling = False
        if self.call_cooldown > 0:
            self.call_cooldown -= dt
        if self.response_timer > 0:
            self.response_timer -= dt
            if self.response_timer <= 0:
                self.responding = False

        # === behavioral decision ===
        behavior = self.decide_behavior(creatures, nests)

        if behavior == "escape":
            self.prey_behavior(dt, creatures, foods, nests, scent_field)
        elif behavior == "gather":
            if self.genome["aggression"] > 0.6:
                generation = self.predator_behavior(dt, creatures, foods, nests, scent_field, generation)
            else:
                self.standard_food_cycle(dt, foods, nests)
        elif behavior == "mate":
            # start calling immediately when top priority is mate
            if not self.calling and self.call_cooldown <= 0:
                self.broadcast_call(creatures, nests)
            # if both partners have heard each other → go to nest to mate
            if self.partner:
                my_nest = nests.get_nest(self)
                if my_nest and nests.can_enter(self, my_nest):
                    # always return to nest once partnered
                    if not my_nest.contains(self):
                        self.seek(my_nest.x, my_nest.y)
                    else:
                        self.courtship_behavior(dt, nests)
                else:
                    # lost partner or invalid nest
                    self.partner = None

            if self.partner:
                self.courtship_behavior(dt, nests)
            elif self.heard_call:
                self.seek(self.heard_call.x, self.heard_call.y)
                self.neutral_behavior(dt, foods, nests)
            else:
                self.neutral_behavior(dt, foods, nests)
            baby = self.try_mate(creatures, nests)
            if baby:
                creatures.append(baby)
        else:
            self.neutral_behavior(dt, foods, nests)

        # --- energy drain ---
        move_intensity = clamp(math.hypot(self.vx, self.vy), 0.0, 1.0)
        drain = (ENERGY_IDLE_COST + ENERGY_MOVE_COST * move_intensity) * self.genome["metabolism"]
        self.energy -= drain * dt

        # passive digestion for predators
        if hasattr(self, "digest_timer") and self.digest_timer > 0:
            if self.genome["aggression"] > 0.6:  # only predators digest meat
                digest_rate = (self.energy_max * 0.15) * dt  # digest ~15% energy per second
                self.energy = clamp(self.energy + digest_rate, 0, self.energy_max)
            self.digest_timer -= dt

        if self.energy <= 0:
            self.alive = False
        return generation

    def decide_behavior(self, creatures, nests):
        """Determine priority behavior."""
        escape_p = self.get_escape_priority(creatures, nests)
        gather_p = self.get_gather_priority()
        mate_p = self.get_mate_priority(nests)

        self.priorities = {
            "escape": escape_p,
            "gather": gather_p,
            "mate": mate_p,
        }
        return max(self.priorities, key=self.priorities.get)

    def get_escape_priority(self, creatures, nests):
        """Calculate escape priority based on nearby threats."""
        pred = self.find_predator(creatures, nests)
        if not pred:
            return 0.0
        d = dist(self.x, self.y, pred.x, pred.y)
        return clamp(1.0 - d / self.genome["vision"], 0.0, 1.0)

    def get_gather_priority(self):
        """Calculate gathering priority based on hunger."""
        e_ratio = self.energy / self.energy_max
        gather_p = (1.5 * (1.0 - e_ratio))
        gather_p += random.uniform(-0.05, 0.05)
        return clamp(gather_p, 0.0, 1.5)

    def get_mate_priority(self, nests):
        """Mate drive priority equals the accumulated drive; no proximity/energy scaling."""
        if not self.alive:
            return 0.0
        return self.mate_drive


    def broadcast_call(self, creatures, nests):
        """Emit a mating call inside nest."""
        if not self.ready_to_mate or not self.alive:
            return
        if self.partner:
            return

        my_nest = nests.get_nest(self)
        if not my_nest or not nests.can_enter(self, my_nest) or not my_nest.contains(self):
            return

        if self.call_cooldown <= 0:
            self.calling = True
            self.call_timer = CALL_DURATION
            self.call_cooldown = CALL_COOLDOWN

            call_range = 350 * (self.genome["vision"] / 100)
            for c in creatures:
                if c is self or not c.alive or not c.ready_to_mate:
                    continue
                if nests.get_nest(c) != my_nest:
                    continue
                if dist(self.x, self.y, c.x, c.y) < call_range:
                    c.heard_call = self
                    c.respond_to_call(self, nests)

    def respond_to_call(self, caller, nests):
        """Send a response call and set partnership if both are ready."""
        if not self.ready_to_mate or not self.alive or self.partner:
            return
        self.responding = True
        self.response_timer = RESPONSE_CALL_DURATION
        self.partner = caller
        caller.partner = self


        # heart pulse cue when partners agree to mate
        self.flash_timer = 0.8
        caller.flash_timer = 0.8
        self.heart_pulse_timer = 1.2
        caller.heart_pulse_timer = 1.2

        # both creatures head back toward their nests immediately
        self_nest = nests.get_nest(self)
        caller_nest = nests.get_nest(caller)
        if self_nest and nests.can_enter(self, self_nest):
            self.seek(self_nest.x, self_nest.y)
        if caller_nest and nests.can_enter(caller, caller_nest):
            caller.seek(caller_nest.x, caller_nest.y)


    def courtship_behavior(self, dt, nests):
        """Partnered movement - synchronized orbit inside nest."""
        if not self.partner or not self.partner.alive:
            self.partner = None
            return

        my_nest = nests.get_nest(self)
        if not my_nest or not nests.can_enter(self, my_nest):
            self.partner = None
            return

        d = dist(self.x, self.y, self.partner.x, self.partner.y)
        desired_dist = (self.radius + self.partner.radius) * 3.0

        if d > desired_dist * 1.2:
            self.seek(self.partner.x, self.partner.y)
        elif d < desired_dist * 0.8:
            away_x = self.x - self.partner.x
            away_y = self.y - self.partner.y
            nx, ny = norm(away_x, away_y)
            self.vx, self.vy = 0.9 * self.vx + 0.1 * nx, 0.9 * self.vy + 0.1 * ny
            self.vx, self.vy = norm(self.vx, self.vy)
        else:
            mid_x = (self.x + self.partner.x) / 2
            mid_y = (self.y + self.partner.y) / 2
            angle = math.atan2(self.y - mid_y, self.x - mid_x)
            if id(self) % 2 == 0:
                angle += 0.03
            else:
                angle -= 0.03
            orbit_dist = desired_dist / 2
            self.vx = math.cos(angle)
            self.vy = math.sin(angle)
            self.x = mid_x + orbit_dist * self.vx
            self.y = mid_y + orbit_dist * self.vy

        self.move(dt)

    def try_mate(self, creatures, nests):
        """Attempt sexual reproduction."""
        if not self.ready_to_mate or not self.alive:
            return None

        my_nest = nests.get_nest(self)
        if not my_nest:
            return None

        # predators must go home before mating
        if self.genome["aggression"] > 0.6 and not (nests.can_enter(self, my_nest) and my_nest.contains(self)):
            self.seek(my_nest.x, my_nest.y)
            self.move(1 / FPS)
            return None

        # prey can mate anywhere inside their nest as usual
        if not my_nest.contains(self):
            self.seek(my_nest.x, my_nest.y)
            self.move(1 / FPS)
            return None


        partner, best_d = None, 9999
        for c in creatures:
            if c is self or not c.alive or not c.ready_to_mate or c.partner:
                continue

            if nests.is_safe_zone(self, c):
                d = dist(self.x, self.y, c.x, c.y)
                if d < best_d and d < self.genome["vision"] * 0.8:
                    partner, best_d = c, d
        
        if not nests.can_enter(self, my_nest):
            return None

        if partner:
            if best_d > self.radius * 3:
                self.seek(partner.x, partner.y)
                self.move(1 / FPS)
                return None

            self.energy *= (1 - MATING_COST * 0.8)
            partner.energy *= (1 - MATING_COST * 0.8)
            self.ready_to_mate = False
            partner.ready_to_mate = False

            child_genome = {}
            for key in self.genome:
                avg_val = (self.genome[key] + partner.genome[key]) / 2
                mutated = avg_val + random.gauss(0, 0.07)
                if key == "vision":
                    mutated = clamp(mutated, 40, 160)
                elif key == "speed":
                    mutated = clamp(mutated, 0.5, 1.6)
                elif key == "size":
                    mutated = clamp(mutated, 0.5, 1.6)
                elif key == "metabolism":
                    mutated = clamp(mutated, 0.5, 1.5)
                elif key == "aggression":
                    mutated = clamp(mutated, 0.0, 1.0)
                else:
                    mutated = clamp(mutated, 0.4, 2.0)
                child_genome[key] = mutated

            cx = (self.x + partner.x) / 2 + random.uniform(-30, 30)
            cy = (self.y + partner.y) / 2 + random.uniform(-30, 30)
            child = Creature(cx, cy, genome=child_genome)
            child.energy = child.energy_max * random.uniform(0.7, 0.9)
            child.flash_timer = 0.6
            child.birth_flash = True

            angle = random.uniform(0, math.tau)
            child.vx, child.vy = math.cos(angle), math.sin(angle)
            child.wander_t = random.uniform(0.2, 1.0)
            child.decide_behavior([self, partner], nests)
            child.move(1 / FPS)
            child.generation = max(self.generation, partner.generation) + 1

            self.partner = None
            partner.partner = None
            self.heard_call = None
            partner.heard_call = None
            self.responding = False
            partner.responding = False
            self.mate_drive = 0.0
            partner.mate_drive = 0.0

            return child

        return None

    # ==================================================
    #   PREDATOR BEHAVIOR (with scent tracking)
    # ==================================================
    def predator_behavior(self, dt, creatures, foods, nests, scent_field, generation):
        prey = self.find_prey(creatures, nests)
        hunger = self.energy / self.energy_max

        # try scent trail if no visible prey
        if not prey:
            grad = scent_field.sample_gradient(self.x, self.y, "prey")
            if grad:
                gx, gy = grad
                self.vx += gx * 2.0
                self.vy += gy * 2.0
                self.vx, self.vy = norm(self.vx, self.vy)
                self.move(dt)
                return generation

        # === normal visual hunting ===
        if prey and hunger < 0.95:
            # stop chasing if prey ran into a protected nest
            prey_nest = nests.get_nest(prey)
            if prey_nest and not nests.can_enter(self, prey_nest) and prey_nest.contains(prey):
                # break off pursuit, wander or re-evaluate
                self.target_prey = None
                self.wander(dt)
                self.move(dt)
                return generation

            # normal pursuit
            self.seek(prey.x, prey.y)
            d = dist(self.x, self.y, prey.x, prey.y)
            if d <= (self.radius + prey.radius):
                if not nests.is_safe_zone(self, prey):
                    prey.alive = False
                    # meat = partial instant gain + slow digestion
                    instant_gain = PREDATION_GAIN * 0.25
                    self.energy = clamp(self.energy + instant_gain, 0, self.energy_max)
                    self.flash_timer = 0.3
                    self.digest_timer = 10.0  # longer digestion = more energy over time




            self.move(dt)
        elif hunger < 0.5:
            food = self.find_nearest_food(foods)
            if food and dist(self.x, self.y, food.x, food.y) < self.genome["vision"]:
                self.seek(food.x, food.y)
                if dist(self.x, self.y, food.x, food.y) <= PICKUP_DIST and food.alive:
                    food.alive = False
                    self.energy = clamp(self.energy + ENERGY_DELIVERY_REWARD * 0.5, 0, self.energy_max)
                    self.flash_timer = 0.2
                    self.digest_timer = 1.5
            self.move(dt)
        else:
            self.wander(dt)
            self.move(dt)
        return generation

    # ==================================================
    #   PREY BEHAVIOR (avoid predator scent)
    # ==================================================
    def prey_behavior(self, dt, creatures, foods, nests, scent_field):
        predator = self.find_predator(creatures, nests)
        escape_dir = None

        # check for visible predator
        if predator:
            dx = self.x - predator.x
            dy = self.y - predator.y
            escape_dir = norm(dx, dy)
        else:
            # check scent gradient instead
            grad = scent_field.sample_gradient(self.x, self.y, "pred")
            if grad:
                gx, gy = grad
                escape_dir = norm(-gx, -gy)  # opposite direction of higher pred scent

        if escape_dir:
            nx, ny = escape_dir
            self.vx = 0.8 * self.vx + 0.2 * nx
            self.vy = 0.8 * self.vy + 0.2 * ny
            self.vx, self.vy = norm(self.vx, self.vy)
            self.move(dt)
        else:
            # look for food scent if not fleeing
            grad = scent_field.sample_gradient(self.x, self.y, "food")
            if grad:
                gx, gy = grad
                self.vx += gx * 0.5
                self.vy += gy * 0.5
                self.vx, self.vy = norm(self.vx, self.vy)
            self.standard_food_cycle(dt, foods, nests)
            self.move(dt)

    def neutral_behavior(self, dt, foods, nests):
        """Default idle behavior."""
        if self.genome["aggression"] > 0.6:
            self.wander(dt)
            self.move(dt)
            return
        self.standard_food_cycle(dt, foods, nests)
        self.move(dt)

    def standard_food_cycle(self, dt, foods, nests, generation=None):
        """Standard foraging behavior."""
        my_nest = nests.get_nest(self)
        if self.carrying:
            if my_nest:
                self.seek(my_nest.x, my_nest.y)
                if dist(self.x, self.y, my_nest.x, my_nest.y) <= DROP_DIST:
                    self.carrying = False
                    my_nest.score += 1
                    self.energy = clamp(self.energy + ENERGY_DELIVERY_REWARD, 0, self.energy_max)
                    self.ready_to_mate = self.energy >= self.energy_max * MATING_ENERGY_REQ
                    if RESPAWN_FOOD_ON_DELIVER:
                        foods.append(Food(*rand_point()))
            self.move(dt)
            return

        if not self.target_food or not self.target_food.alive:
            self.target_food = self.find_nearest_food(foods)

        if self.target_food and self.target_food.alive:
            d = dist(self.x, self.y, self.target_food.x, self.target_food.y)
            if d < self.genome["vision"]:
                self.seek(self.target_food.x, self.target_food.y)
            if d <= PICKUP_DIST:
                self.carrying = True
                self.target_food.alive = False
                self.target_food = None
        else:
            self.wander_t = 0
            self.wander(dt)
        if self.genome["aggression"] <= 0.6:
            self.digest_timer = 0  # instant digestion for herbivores
        self.move(dt)

    def move(self, dt):
        """Move creature and handle boundary collision."""
        step = self.speed * dt
        self.x += self.vx * step
        self.y += self.vy * step
        bounced = False
        if self.x < 0 or self.x > WIDTH:
            self.vx *= -1
            self.x = clamp(self.x, 0, WIDTH)
            bounced = True
        if self.y < 0 or self.y > HEIGHT:
            self.vy *= -1
            self.y = clamp(self.y, 0, HEIGHT)
            bounced = True
        if bounced:
            self.vx, self.vy = norm(self.vx, self.vy)

    def find_prey(self, creatures, nests):
        """Find nearest vulnerable prey."""
        best, best_d = None, 1e9
        for c in creatures:
            if c is self or not c.alive:
                continue
            if nests.is_safe_zone(self, c):
                continue
            if c.genome["size"] * PREDATION_SIZE_RATIO < self.genome["size"]:
                d = dist(self.x, self.y, c.x, c.y)
                if d < self.genome["vision"] and d < best_d:
                    best_d, best = d, c
        return best

    def find_predator(self, creatures, nests):
        """Find nearby threatening predator."""
        for c in creatures:
            if c is self or not c.alive:
                continue
            if nests.is_safe_zone(self, c):
                continue
            if c.genome["size"] >= self.genome["size"] * PREDATION_SIZE_RATIO and c.genome["aggression"] > 0.6:
                if dist(self.x, self.y, c.x, c.y) < self.genome["vision"]:
                    return c
        return None

    def find_nearest_food(self, foods):
        """Find nearest available food."""
        best, best_d = None, 1e9
        for f in foods:
            if not f.alive:
                continue
            d = (self.x - f.x) ** 2 + (self.y - f.y) ** 2
            if d < best_d:
                best_d, best = d, f
        return best

    def seek(self, tx, ty):
        """Steer toward target position."""
        dx, dy = tx - self.x, ty - self.y
        nx, ny = norm(dx, dy)
        self.vx = 0.9 * self.vx + 0.1 * nx
        self.vy = 0.9 * self.vy + 0.1 * ny
        self.vx, self.vy = norm(self.vx, self.vy)

    def wander(self, dt):
        """Random wandering movement."""
        self.wander_t -= dt
        if self.wander_t <= 0:
            self.wander_t = random.uniform(0.4, 1.2)
            angle = random.uniform(-1.0, 1.0)
            cs, sn = math.cos(angle), math.sin(angle)
            nvx = self.vx * cs - self.vy * sn
            nvy = self.vx * sn + self.vy * cs
            self.vx, self.vy = norm(nvx, nvy)

    def draw(self, surf):
        """Render creature on screen."""
        if not self.alive:
            dead = (120, 120, 120)
            pygame.draw.circle(surf, dead, (int(self.x), int(self.y)), int(self.radius))
            return
        
        if hasattr(self, "digest_timer") and self.digest_timer > 0 and self.genome["aggression"] > 0.6:
            digest_alpha = int(150 * (self.digest_timer / 6.0))
            ring = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.circle(ring, (255, 100, 80, digest_alpha), (int(self.x), int(self.y)), int(self.radius + 5), 2)
            surf.blit(ring, (0, 0))

        hue = self.genome["aggression"]
        color = (int(52 + hue * 180), int(122 - hue * 80), int(235 - hue * 200))
        if self.flash_timer > 0:
            if hasattr(self, "flash_color"):
                color = self.flash_color
            elif hasattr(self, "birth_flash") and self.birth_flash:
                color = (60, 255, 120)
            else:
                color = (min(255, color[0] + 80),
                        min(255, color[1] + 80),
                        min(255, color[2] + 80))
        if self.carrying:
            color = (245, 190, 30)
        if hasattr(self, "birth_flash") and self.flash_timer <= 0:
            self.birth_flash = False

        pygame.draw.circle(surf, color, (int(self.x), int(self.y)), int(self.radius))
        hx = self.x + self.vx * (self.radius + 4)
        hy = self.y + self.vy * (self.radius + 4)
        pygame.draw.line(surf, (20, 20, 20), (int(self.x), int(self.y)), (int(hx), int(hy)), 2)

        vision = int(self.genome["vision"])
        pygame.draw.circle(surf, (200, 200, 200), (int(self.x), int(self.y)), vision, 1)

        w, h = 16, 3
        pct = self.energy / self.energy_max
        bx = int(self.x - w // 2)
        by = int(self.y - self.radius - 8)
        pygame.draw.rect(surf, HP_BG, pygame.Rect(bx, by, w, h))
        if pct > 0:
            col = HP_OK if pct > 0.5 else HP_LOW if pct > 0.2 else HP_CRIT
            pygame.draw.rect(surf, col, pygame.Rect(bx, by, int(w * pct), h))

        # mating call visualization
        if self.calling:
            t = 1 - (self.call_timer / CALL_DURATION)
            call_range = 350 * (self.genome["vision"] / 100)
            pulse_radius = int(self.radius + t * call_range)
            alpha = max(0, 255 - int(t * 255))
            call_color = (255, 80, 80) if self.genome["aggression"] > 0.5 else (100, 255, 100)
            ring_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.circle(ring_surface, (*call_color, alpha), (int(self.x), int(self.y)), pulse_radius, 2)
            surf.blit(ring_surface, (0, 0))

        if self.responding:
            t = 1 - (self.response_timer / RESPONSE_CALL_DURATION)
            response_range = 350 * (self.genome["vision"] / 100)
            pulse_radius = int(self.radius + t * response_range)
            alpha = max(0, 255 - int(t * 255))
            response_color = RESPONSE_COLOR_PRED if self.genome["aggression"] > 0.5 else RESPONSE_COLOR_PREY
            ring_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.circle(ring_surface, (*response_color, alpha), (int(self.x), int(self.y)), pulse_radius, 2)
            surf.blit(ring_surface, (0, 0))

        self.draw_heart_pulse(surf)

    def draw_priority_icons(self, surf):
        """Draw icons showing dominant priorities visually."""
        if not hasattr(self, "priorities"):
            return

        base_x = int(self.x + self.radius + 6)
        base_y = int(self.y - self.radius - 6)

        icons = []
        if self.priorities["gather"] > 0.8:
            icons.append(((255, 200, 0), "🍞"))
        if self.priorities["mate"] > 0.8:
            icons.append(((255, 120, 200), "♥"))
        if self.priorities["escape"] > 0.8:
            icons.append(((255, 80, 80), "⚠"))

        for i, (color, symbol) in enumerate(icons):
            offset_y = base_y - i * 14
            pygame.draw.circle(surf, color, (base_x, offset_y), 5)