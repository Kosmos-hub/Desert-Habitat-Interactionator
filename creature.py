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
            "metabolism": random.uniform(0.6, 1.4),
            "aggression": random.uniform(0, 1),
            "toxin": 0.0,
            "is_decomposer": False,
        }

        # --- derived stats ---
        self.radius = BASE_RADIUS * self.genome["size"]
        if self.genome.get("is_decomposer", False):
            self.base_speed = DECOMPOSER_BASE_SPEED
        else:
            self.base_speed = CREATURE_BASE_SPEED * self.genome["speed"]
        
        # FIXED: Set energy_max and energy BEFORE other attributes
        self.energy_max = ENERGY_BASE_MAX * self.genome["size"]
        self.energy = random.uniform(0.6 * self.energy_max, self.energy_max)

        # --- nest reference ---
        self.last_scent_drop = 0.0
        if self.genome.get("is_decomposer", False):
            self.scent_type = "decomp"
        elif self.genome["aggression"] > 0.6:
            self.scent_type = "pred"
        else:
            self.scent_type = "prey"
        self.nest = None
        self.home_score = 0
        self.generation = 0
        self.toxin_cooldown = 0.0

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
    def update(self, dt, foods, nests, creatures, generation, scent_field, corpses):
        if not self.alive:
            return generation

        self.flash_timer = max(0.0, self.flash_timer - dt)
        self.mate_drive = clamp(self.mate_drive + MATE_DRIVE_RATE * dt, 0.0, 1.0)

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

        # Toxin cooldown decrement:
        if self.toxin_cooldown > 0:
            self.toxin_cooldown -= dt

        # === behavioral decision ===
        behavior = self.decide_behavior(creatures, nests)

        if behavior == "escape":
            # Check if decomposer
            if self.genome.get("is_decomposer", False):
                self.decomposer_escape(dt, creatures, nests, scent_field)
            else:
                self.prey_behavior(dt, creatures, foods, nests, scent_field)
        elif behavior == "gather":
            if self.genome.get("is_decomposer", False):
                self.decomposer_behavior(dt, corpses, foods, nests, scent_field)  # Need corpses!
            elif self.genome["aggression"] > 0.6:
                generation = self.predator_behavior(dt, creatures, foods, nests, scent_field, generation)
            else:
                self.standard_food_cycle(dt, foods, nests)
        elif behavior == "mate":
            # CHANGE: Break off mating if partner is invalid or too long without success
            if self.partner and not self.partner.alive:
                self.partner = None
                self.heard_call = None
            
            # CHANGE: If we've been trying to mate for too long, give up and reset
            if not hasattr(self, 'mate_attempt_timer'):
                self.mate_attempt_timer = 0.0
            
            if self.partner:
                self.mate_attempt_timer += dt
                # Give up after 8 seconds of trying
                if self.mate_attempt_timer > 8.0:
                    if self.partner:
                        self.partner.partner = None
                        self.partner.heard_call = None
                        self.partner.mate_attempt_timer = 0.0
                    self.heard_call = None
                    self.mate_attempt_timer = 0.0
                    self.mate_drive *= 0.5  # Reduce drive to avoid immediate retry
            else:
                self.mate_attempt_timer = 0.0
            
            # start calling immediately when top priority is mate
            if not self.calling and self.call_cooldown <= 0:
                self.broadcast_call(creatures, nests)
            # if both partners have heard each other go to nest to mate
            if self.partner:
                my_nest = nests.get_nest(self)
                if my_nest and nests.can_enter(self, my_nest):
                    # always return to nest once partnered
                    if not my_nest.contains(self):
                        self.seek(my_nest.x, my_nest.y)
                else:
                    # lost partner or invalid nest
                    self.partner = None

            if self.heard_call:
                self.seek(self.heard_call.x, self.heard_call.y)
                self.neutral_behavior(dt, foods, nests)
            else:
                self.neutral_behavior(dt, foods, nests)
            baby = self.try_mate(creatures, nests)
            if baby:
                creatures.append(baby)
                self.mate_attempt_timer = 0.0
        else:
            self.neutral_behavior(dt, foods, nests)

        # --- energy drain ---
        move_intensity = clamp(math.hypot(self.vx, self.vy), 0.0, 1.0)
        if self.genome.get("is_decomposer", False):
            drain = (ENERGY_IDLE_COST + ENERGY_MOVE_COST * move_intensity) * self.genome["metabolism"] * 0.5
        else:
            drain = (ENERGY_IDLE_COST + ENERGY_MOVE_COST * move_intensity) * self.genome["metabolism"]
        self.energy -= drain * dt

        # passive digestion for predators
        if hasattr(self, "digest_timer") and self.digest_timer > 0:
            if self.genome["aggression"] > 0.6:  # only predators digest meat
                digest_rate = (self.energy_max * 0.15) * dt  # digest ~15% energy per second
                self.energy = clamp(self.energy + digest_rate, 0, self.energy_max)
            self.digest_timer -= dt

        # Hibernation for decomposers
        if self.genome.get("is_decomposer", False):
            if self.energy <= self.energy_max * 0.15:
                # slow hibernation drift, but still lose energy
                self.vx *= 0.2
                self.vy *= 0.2
                self.ready_to_mate = False
                self.flash_timer = 0.0
                # die if truly starved
                if self.energy <= 0:
                    self.alive = False
        # Hibernation for predators
        elif self.genome["aggression"] > 0.6:
            if self.energy <= self.energy_max * 0.2:
                # predators enter deeper hibernation when starving
                self.vx *= 0.15
                self.vy *= 0.15
                self.ready_to_mate = False
                self.flash_timer = 0.0
                # reduced metabolism during hibernation
                self.genome["metabolism"] *= 0.7
                # die if energy reaches zero
                if self.energy <= 0:
                    self.alive = False
        else:
            if self.energy <= 0:
                self.alive = False
        return generation


    def decide_behavior(self, creatures, nests):
        """Determine priority behavior."""
        escape_p = self.get_escape_priority(creatures, nests)
        gather_p = self.get_gather_priority()
        mate_p = self.get_mate_priority(nests)

        # Decomposers: prefer mating once full energy is reached
        if self.genome.get("is_decomposer", False):
            if self.energy >= self.energy_max * 0.9:
                gather_p = 0.0
                mate_p = 1.5

        # CHANGE: If energy is critically low, force gathering regardless of other priorities
        if self.energy < self.energy_max * 0.35:
            gather_p = max(gather_p, 1.6)  # Override mating priority
            # Break off partnership if starving
            if self.partner:
                partner = self.partner
                self.partner = None
                self.heard_call = None
                partner.partner = None
                partner.heard_call = None
        
        # NEW: Toxin release overrides other behaviors for decomposers
        if self.genome.get("is_decomposer", False) and escape_p > TOXIN_THRESHOLD:
            escape_p = 1.8  # Make escape highest priority when toxin triggers

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
        """Emit a visible mating call; if outside nest, start returning home."""
        if not self.ready_to_mate or not self.alive:
            return
        if self.partner:
            return  # already paired
        
        my_nest = nests.get_nest(self)
        if not my_nest or not nests.can_enter(self, my_nest):
            return

        # CHANGE: Predators can call from anywhere, don't require being home first
        is_predator = self.genome["aggression"] > 0.6
        
        # if outside, begin heading home (but still send call)
        if not my_nest.contains(self):
            self.seek(my_nest.x, my_nest.y)

        # resend call if cooldown expired
        if self.call_cooldown <= 0:
            self.calling = True
            self.call_timer = CALL_DURATION
            self.call_cooldown = 2.5 if is_predator else 3.5  # CHANGE: Predators call more frequently

            # CHANGE: Predators have longer range calls
            call_range = 450 * (self.genome["vision"] / 100) if is_predator else 350 * (self.genome["vision"] / 100)
            
            for c in creatures:
                if c is self or not c.alive or not c.ready_to_mate:
                    continue
                if nests.get_nest(c) != my_nest:
                    continue
                if dist(self.x, self.y, c.x, c.y) < call_range:
                    c.heard_call = self
                    c.respond_to_call(self, nests)

    def respond_to_call(self, caller, nests):
        """Respond and start heading home immediately."""
        if not self.ready_to_mate or not self.alive or self.partner:
            return
        self.responding = True
        self.response_timer = RESPONSE_CALL_DURATION
        self.partner = caller
        caller.partner = self

        my_nest = nests.get_nest(self)
        if my_nest:
            self.seek(my_nest.x, my_nest.y)
        partner_nest = nests.get_nest(caller)
        if partner_nest:
            caller.seek(partner_nest.x, partner_nest.y)

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


    def try_mate(self, creatures, nests):
        """Attempt sexual reproduction."""
        if not self.ready_to_mate or not self.alive:
            return None

        my_nest = nests.get_nest(self)
        if not my_nest:
            return None
        
        is_decomposer = self.genome.get("is_decomposer", False)
        best_d = 0

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
        
        if is_decomposer:
            # Decomposers mate only if both are inside the same nest
            if not my_nest.contains(self):
                self.seek(my_nest.x, my_nest.y)
                self.move(1 / FPS)
                return None

            # Must have a valid living partner
            if not self.partner or not self.partner.alive:
                return None

            partner_nest = nests.get_nest(self.partner)
            # If both inside same decomposer nest, skip partner-search loop below
            if partner_nest == my_nest and my_nest.contains(self.partner):
                partner = self.partner
            else:
                return None



        is_predator = self.genome["aggression"] > 0.6
        # --- PARTNER SELECTION ---
        is_predator = self.genome["aggression"] > 0.6
        is_decomposer = self.genome.get("is_decomposer", False)
        partner = None

        if is_decomposer:
            # Decomposers always mate with their current partner if valid
            if self.partner and self.partner.alive and self.partner.ready_to_mate:
                partner = self.partner
            else:
                return None
        else:
            partner, best_d = None, 9999
            for c in creatures:
                if c is self or not c.alive or not c.ready_to_mate or c.partner:
                    continue
                # predators: extended range, same-nest check
                if is_predator:
                    if nests.get_nest(c) != my_nest:
                        continue
                    d = dist(self.x, self.y, c.x, c.y)
                    if d < best_d and d < self.genome["vision"] * 1.2:
                        partner, best_d = c, d
                else:
                    # prey: safe-zone restriction
                    if nests.is_safe_zone(self, c):
                        d = dist(self.x, self.y, c.x, c.y)
                        if d < best_d and d < self.genome["vision"] * 0.8:
                            partner, best_d = c, d

        if partner:
            # CHANGE: More lenient distance requirement for predators
            max_dist = self.radius * 4 if is_predator else self.radius * 3
            
            if best_d > max_dist:
                self.seek(partner.x, partner.y)
                self.move(1 / FPS)
                return None

            # CHANGE: Lower mating cost for predators
            cost = MATING_COST * 0.6 if is_predator else MATING_COST * 0.8
            self.energy *= (1 - cost)
            partner.energy *= (1 - cost)
            self.ready_to_mate = False
            partner.ready_to_mate = False

            child_genome = {}
            for key in self.genome:
                if key == "is_decomposer":
                    # Decomposers only breed with decomposers
                    child_genome[key] = self.genome["is_decomposer"] and partner.genome["is_decomposer"]
                    continue

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
            child.genome["is_decomposer"] = self.genome.get("is_decomposer", False)
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
            self.ready_to_mate = False
            partner.ready_to_mate = False
            self.call_cooldown = 2.0
            partner.call_cooldown = 2.0
            self.mate_drive = 0.0
            partner.mate_drive = 0.0




            return child

        # Reset partner if we're decomposers and got stuck
        if self.genome.get("is_decomposer", False) and self.partner:
            if not self.partner.alive or random.random() < 0.01:
                self.partner.partner = None
                self.partner = None
                self.heard_call = None
        return None


    # ==================================================
    #   PREDATOR BEHAVIOR
    # ==================================================
    def predator_behavior(self, dt, creatures, foods, nests, scent_field, generation):
        hunger = self.energy / self.energy_max
        
        # NEW: Check if in hibernation mode
        in_hibernation = self.energy <= self.energy_max * 0.2
        
        if in_hibernation:
            # In hibernation - only hunt if prey comes within vision range
            prey = self.find_prey(creatures, nests, scent_field)
            
            if prey:
                # Prey spotted! Wake up and hunt
                prey_nest = nests.get_nest(prey)
                # Don't chase if prey is in protected nest
                if prey_nest and not nests.can_enter(self, prey_nest) and prey_nest.contains(prey):
                    # Just stand still if can't reach prey
                    self.vx *= 0.05  # Almost completely still
                    self.vy *= 0.05
                    self.move(dt, nests)
                    return generation
                
                # Chase the prey
                self.seek(prey.x, prey.y)
                d = dist(self.x, self.y, prey.x, prey.y)
                
                # Try to eat if close enough
                if d <= (self.radius + prey.radius):
                    if not nests.is_safe_zone(self, prey):
                        prey.alive = False
                        # Eating wakes us up from hibernation
                        instant_gain = PREDATION_GAIN * 0.25
                        self.energy = clamp(self.energy + instant_gain, 0, self.energy_max)
                        self.flash_timer = 0.3
                        self.digest_timer = 10.0
                
                self.move(dt, nests)
                return generation
            else:
                # No prey in vision - stand completely still to conserve energy
                self.vx *= 0.05  # Almost completely still
                self.vy *= 0.05
                self.move(dt, nests)
                return generation
        
        # Normal (non-hibernation) hunting behavior below
        prey = self.find_prey(creatures, nests, scent_field)

        # try scent trail if no visible prey
        if not prey:
            grad = scent_field.sample_gradient(self.x, self.y, "prey")
            if grad:
                gx, gy = grad
                self.vx += gx * 2.0
                self.vy += gy * 2.0
                self.vx, self.vy = norm(self.vx, self.vy)
                self.move(dt, nests)
                return generation

        # === normal visual hunting ===
        if prey and hunger < 0.95:
            # stop chasing if prey ran into a protected nest
            prey_nest = nests.get_nest(prey)
            if prey_nest and not nests.can_enter(self, prey_nest) and prey_nest.contains(prey):
                # break off pursuit, wander or re-evaluate
                self.target_prey = None
                self.wander(dt)
                self.move(dt, nests)
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

            # CHANGE: Lower energy threshold for mating readiness
            if self.energy >= self.energy_max * MATING_ENERGY_REQ and not self.partner:
                # ready to mate again only when single and full
                self.ready_to_mate = True

            self.move(dt, nests)
        elif hunger < 0.5:
            food = self.find_nearest_food(foods)
            if food and dist(self.x, self.y, food.x, food.y) < self.genome["vision"]:
                self.seek(food.x, food.y)
                if dist(self.x, self.y, food.x, food.y) <= PICKUP_DIST and food.alive:
                    food.alive = False
                    self.energy = clamp(self.energy + ENERGY_DELIVERY_REWARD * 0.5, 0, self.energy_max)
                    self.flash_timer = 0.2
                    self.digest_timer = 1.5
            self.move(dt, nests)
        else:
            self.wander(dt)
            self.move(dt, nests)
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
            self.move(dt, nests)
        else:
            # look for food scent if not fleeing
            grad = scent_field.sample_gradient(self.x, self.y, "food")
            if grad:
                gx, gy = grad
                self.vx += gx * 0.5
                self.vy += gy * 0.5
                self.vx, self.vy = norm(self.vx, self.vy)
            self.standard_food_cycle(dt, foods, nests)
            self.move(dt, nests)

    # ==================================================
    #   DECOMPOSER BEHAVIOR
    # ==================================================
    def decomposer_behavior(self, dt, corpses, foods, nests, scent_field):
        """Decomposer-specific behavior: find and consume corpses, poop plants."""
        # Check if we need to release toxin
        if self.priorities.get("escape", 0) > TOXIN_THRESHOLD and self.toxin_cooldown <= 0:
            self.release_toxin(scent_field)
            self.toxin_cooldown = TOXIN_DURATION
        
        # Find nearest corpse
        target_corpse = self.find_nearest_corpse(corpses)

        # Follow scent if no corpse directly visible
        if not target_corpse:
            grad = scent_field.sample_gradient(self.x, self.y, "corpse")
            if grad:
                gx, gy = grad
                self.vx += gx * 2.5
                self.vy += gy * 2.5
                self.vx, self.vy = norm(self.vx, self.vy)
                self.move(dt, nests)
                return

        
        if target_corpse:
            d = dist(self.x, self.y, target_corpse.x, target_corpse.y)
            
            if d < self.genome["vision"]:
                self.seek(target_corpse.x, target_corpse.y)
                
                # If close enough, consume
                if d <= (self.radius + target_corpse.radius):
                    # Calculate how much we can eat
                    space_available = self.energy_max - self.energy
                    consumed = target_corpse.consume(space_available)
                    self.energy = clamp(self.energy + consumed, 0, self.energy_max)
                    self.flash_timer = 0.2
                    
                    # Poop out plants based on consumption
                    self.digest_and_poop(consumed, foods)

                    # Remove corpse if fully eaten
                    if not target_corpse.alive or target_corpse.energy <= 0:
                        corpses.remove(target_corpse)
                    
                    if self.energy >= self.energy_max * MATING_ENERGY_REQ:
                        self.ready_to_mate = True
        else:
            # No corpses, just wander
            self.wander(dt)
        
        self.move(dt, nests)

    def release_toxin(self, scent_field):
        """Release toxin cloud to deter predators."""
        strength = self.genome.get("toxin", 0.5) * TOXIN_STRENGTH
        scent_field.emit(self.x, self.y, "toxin", strength)
        self.flash_timer = 0.3

    def decomposer_escape(self, dt, creatures, nests, scent_field):
        """Decomposer escape behavior - release toxin and flee."""
        predator = self.find_predator(creatures, nests)
        
        if predator:
            # Release toxin if possible
            if self.toxin_cooldown <= 0:
                self.release_toxin(scent_field)
                self.toxin_cooldown = TOXIN_DURATION
            
            # Flee
            dx = self.x - predator.x
            dy = self.y - predator.y
            nx, ny = norm(dx, dy)
            self.vx = 0.9 * self.vx + 0.1 * nx
            self.vy = 0.9 * self.vy + 0.1 * ny
            self.vx, self.vy = norm(self.vx, self.vy)
        
        self.move(dt, nests)

    
    def digest_and_poop(self, consumed_energy, foods):
        """Convert consumed corpse energy into plant food."""
        remaining = consumed_energy
        
        while remaining >= PLANT_SPAWN_ENERGY * 0.3:  # Minimum 30% plant
            if remaining >= PLANT_SPAWN_ENERGY:
                # Full plant
                plant_energy = PLANT_SPAWN_ENERGY
            else:
                # Partial plant
                plant_energy = remaining
            
            # Spawn plant behind the decomposer
            angle = random.uniform(0, math.tau)
            offset = self.radius + FOOD_RADIUS + 5
            px = self.x + math.cos(angle) * offset
            py = self.y + math.sin(angle) * offset
            
            # Clamp to screen bounds
            px = clamp(px, 20, WIDTH - 20)
            py = clamp(py, 20, HEIGHT - 20)
            
            new_plant = Food(px, py)
            new_plant.energy = plant_energy  # Store energy value
            foods.append(new_plant)
            
            remaining -= plant_energy
    
    def find_nearest_corpse(self, corpses):
        """Find nearest corpse with remaining energy."""
        best, best_d = None, 1e9
        for corpse in corpses:
            if not corpse.alive:
                continue
            d = (self.x - corpse.x) ** 2 + (self.y - corpse.y) ** 2
            if d < best_d and d < (self.genome["vision"] * 2) ** 2:
                best_d, best = d, corpse
        return best


    def neutral_behavior(self, dt, foods, nests):
        """Default idle behavior."""
        if self.genome["aggression"] > 0.6:
            self.wander(dt)
            self.move(dt, nests)
            return
        self.standard_food_cycle(dt, foods, nests)
        self.move(dt, nests)

    def standard_food_cycle(self, dt, foods, nests, generation=None):
        """Standard foraging behavior."""
        my_nest = nests.get_nest(self)
        if self.genome.get("is_decomposer", False):
            return  # Skip food logic for decomposers
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
            self.move(dt, nests)
            return

        if not self.target_food or not self.target_food.alive:
            self.target_food = self.find_nearest_food(foods)
        else:
            # Keep targeting same food even if far away
            if dist(self.x, self.y, self.target_food.x, self.target_food.y) > self.genome["vision"] * 1.5:
                self.target_food = None

        if self.target_food and self.target_food.alive:
            d = dist(self.x, self.y, self.target_food.x, self.target_food.y)
            if d < self.genome["vision"]:
                self.seek(self.target_food.x, self.target_food.y)
            if d <= PICKUP_DIST:
                self.carrying = True
                self.target_food.alive = False
                self.target_food = None
        if self.genome["aggression"] <= 0.6:
            self.digest_timer = 0  # instant digestion for herbivores
        self.move(dt, nests)

    def move(self, dt, nests=None):
        """Move creature and handle boundary collision."""
        step = self.speed * dt
        new_x = self.x + self.vx * step
        new_y = self.y + self.vy * step
        
        # Check wall collisions if nests provided
        if nests:
            new_x, new_y = nests.check_wall_collision(self, new_x, new_y)
        
        self.x = new_x
        self.y = new_y
        
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

    def find_prey(self, creatures, nests, scent_field=None):
        """Find nearest vulnerable prey, avoiding toxin."""
        best, best_d = None, 1e9
        for c in creatures:
            if c is self or not c.alive:
                continue
            if nests.is_safe_zone(self, c):
                continue
            if c.genome["size"] * PREDATION_SIZE_RATIO < self.genome["size"]:
                d = dist(self.x, self.y, c.x, c.y)
                
                # NEW: Check for toxin scent near prey
                if scent_field:
                    grad = scent_field.sample_gradient(c.x, c.y, "toxin")
                    if grad:
                        # Skip this prey if there's toxin nearby
                        continue
                
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
        if self.genome.get("is_decomposer", False):
            return None  # Decomposers never target plants
        best, best_d = None, 1e9
        for f in foods:
            if not f.alive:
                continue
            d = (self.x - f.x) ** 2 + (self.y - f.y) ** 2
            if d < best_d and d < (self.genome["vision"] * 2) ** 2:
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

        # MOVED: Set decomposer color FIRST
        if self.genome.get("is_decomposer", False):
            color = (int(120 + self.genome["size"] * 40), 
                    int(90 + self.genome["size"] * 30), 
                    int(60 + self.genome["size"] * 20))
        else:
            hue = self.genome["aggression"]
            color = (int(52 + hue * 180), int(122 - hue * 80), int(235 - hue * 200))
        
        # Then handle flash_timer
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
        if self.genome.get("is_decomposer", False):
            # Decomposers are brownish
            color = (int(120 + self.genome["size"] * 40), 
                     int(90 + self.genome["size"] * 30), 
                     int(60 + self.genome["size"] * 20))

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
            # CHANGE: Different call ranges for predators
            is_predator = self.genome["aggression"] > 0.5
            call_range = 450 * (self.genome["vision"] / 100) if is_predator else 350 * (self.genome["vision"] / 100)
            pulse_radius = int(self.radius + t * call_range)
            alpha = max(0, 255 - int(t * 255))
            call_color = (255, 80, 80) if is_predator else (100, 255, 100)
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