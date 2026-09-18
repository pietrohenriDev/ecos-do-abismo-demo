from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame
from pygame import Rect, Surface
from pygame.math import Vector2

W, H, FPS = 960, 540, 60
GROUND, WORLD = 468, 1500


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def ease(v):
    v = clamp(v, 0.0, 1.0)
    return v * v * (3 - 2 * v)


def draw_text(surface, value, pos, size, color, *, center=False, bold=False):
    font = pygame.font.SysFont("dejavusans", size, bold=bold)
    image = font.render(value, True, color)
    rect = image.get_rect()
    rect.center = pos if center else rect.center
    if not center:
        rect.topleft = pos
    surface.blit(image, rect)


def glow(surface, center, color, radius, alpha=70):
    radius = max(4, int(radius))
    layer = Surface((radius * 2 + 8, radius * 2 + 8), pygame.SRCALPHA)
    c = layer.get_width() // 2
    for step in range(4, 0, -1):
        pygame.draw.circle(layer, (*color, alpha * step // 8), (c, c), radius * step // 4)
    surface.blit(layer, (center[0] - c, center[1] - c))


@dataclass
class Particle:
    position: Vector2
    velocity: Vector2
    color: tuple[int, int, int]
    radius: float
    life: float
    gravity: float = 0

    def update(self, dt):
        self.position += self.velocity * dt
        self.velocity.y += self.gravity * dt
        self.life -= dt
        self.radius *= .985
        return self.life > 0 and self.radius > .5

    def draw(self, surface, camera):
        alpha = int(clamp(self.life / .8, 0, 1) * 255)
        layer = Surface((20, 20), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*self.color, alpha), (10, 10), max(1, int(self.radius)))
        surface.blit(layer, (int(self.position.x - camera - 10), int(self.position.y - 10)))


@dataclass
class Wave:
    position: Vector2
    color: tuple[int, int, int]
    radius: float = 10
    life: float = .55

    def update(self, dt):
        self.radius += (300 - self.radius) * min(1, dt * 9)
        self.life -= dt
        return self.life > 0

    def draw(self, surface, camera):
        layer = Surface((W, H), pygame.SRCALPHA)
        alpha = int(clamp(self.life / .55, 0, 1) * 220)
        pygame.draw.ellipse(layer, (*self.color, alpha), (int(self.position.x - camera - self.radius), int(self.position.y - self.radius * .45), int(self.radius * 2), int(self.radius * .9)), 4)
        surface.blit(layer, (0, 0))


@dataclass
class Hazard:
    position: Vector2
    velocity: Vector2
    radius: int
    damage: int
    kind: str
    delay: float
    life: float = 2
    age: float = 0
    hit: bool = False

    @property
    def armed(self):
        return self.age >= self.delay

    def update(self, dt):
        self.age += dt
        self.life -= dt
        self.position += self.velocity * dt
        return self.life > 0 and not self.hit

    def draw(self, surface, camera, phase):
        x, y = int(self.position.x - camera), int(self.position.y)
        color = (255, 55, 100) if phase == 2 else (220, 75, 95)
        if not self.armed:
            pulse = int(5 + math.sin(self.age * 28) * 3)
            pygame.draw.circle(surface, (255, 220, 125), (x, y), self.radius + 10 + pulse, 2)
            pygame.draw.line(surface, (255, 190, 90), (x - 20, y), (x + 20, y), 2)
            return
        glow(surface, (x, y), color, self.radius * 3, 65)
        if self.kind == "ring":
            pygame.draw.circle(surface, color, (x, y), self.radius + int(self.age * 32), 7)
        else:
            pygame.draw.circle(surface, color, (x, y), self.radius)
            pygame.draw.circle(surface, (255, 230, 160), (x - 3, y - 3), max(2, self.radius // 3))


def land(pos, previous_bottom, velocity_y, width, height, platforms):
    if velocity_y < 0:
        return None
    current = Rect(int(pos.x), int(pos.y), width, height)
    options = [p for p in platforms if current.right > p.left and current.left < p.right and previous_bottom <= p.top + 4 and current.bottom >= p.top]
    return min(options, key=lambda p: p.top) if options else None


class Player:
    def __init__(self):
        self.position = Vector2(130, GROUND - 72)
        self.velocity = Vector2()
        self.width, self.height = 42, 72
        self.facing = 1
        self.health = 100
        self.jumps = 2
        self.attack_timer = self.attack_cooldown = 0
        self.dodge_timer = self.dodge_cooldown = 0
        self.invulnerable = self.hurt_flash = 0
        self.walk_time = 0

    @property
    def rect(self): return Rect(int(self.position.x), int(self.position.y), self.width, self.height)

    @property
    def attack_rect(self):
        return Rect(int(self.position.x + (self.width if self.facing > 0 else -76)), int(self.position.y + 17), 76, 34)

    def attack(self, particles):
        if self.attack_timer > 0 or self.attack_cooldown > 0: return False
        self.attack_timer, self.attack_cooldown = .22, .28
        for _ in range(8):
            particles.append(Particle(Vector2(self.attack_rect.center), Vector2(random.uniform(40, 150) * self.facing, random.uniform(-40, 40)), (220, 245, 255), 3, .28))
        return True

    def jump(self, particles):
        if self.jumps <= 0: return
        self.velocity.y = -620 if self.jumps == 2 else -540
        self.jumps -= 1
        for _ in range(8): particles.append(Particle(Vector2(self.rect.centerx, self.rect.bottom), Vector2(random.uniform(-70, 70), random.uniform(-100, -20)), (170, 210, 235), 3, .45, 160))

    def dodge(self, particles):
        if self.dodge_timer > 0 or self.dodge_cooldown > 0: return False
        self.dodge_timer, self.dodge_cooldown, self.invulnerable = .18, .8, .3
        self.velocity.x = self.facing * 760
        for _ in range(12): particles.append(Particle(Vector2(self.rect.center), Vector2(-self.facing * random.uniform(100, 280), random.uniform(-70, 70)), (160, 220, 255), 4, .35, 150))
        return True

    def damage(self, amount, particles):
        if self.invulnerable > 0: return False
        self.health = max(0, self.health - amount)
        self.invulnerable, self.hurt_flash = .85, .2
        self.velocity.x = -240 if self.facing > 0 else 240
        for _ in range(18): particles.append(Particle(Vector2(self.rect.center), Vector2(random.uniform(-180, 180), random.uniform(-180, 40)), (255, 100, 135), 4, .55, 320))
        return True

    def update(self, dt, keys, platforms):
        for name in ("attack_timer", "attack_cooldown", "dodge_timer", "dodge_cooldown", "invulnerable", "hurt_flash"):
            setattr(self, name, max(0, getattr(self, name) - dt))
        if self.dodge_timer > 0:
            self.position.x = clamp(self.position.x + self.velocity.x * dt, 20, WORLD - self.width - 20)
            return
        direction = (1 if keys[pygame.K_d] or keys[pygame.K_RIGHT] else 0) - (1 if keys[pygame.K_a] or keys[pygame.K_LEFT] else 0)
        if direction:
            self.facing, self.velocity.x = direction, direction * 300
            self.walk_time += dt * 12
        else:
            self.velocity.x *= max(0, 1 - 13 * dt)
            self.walk_time += dt * 3
        previous_bottom = self.position.y + self.height
        self.velocity.y += 1450 * dt
        self.position.x = clamp(self.position.x + self.velocity.x * dt, 20, WORLD - self.width - 20)
        self.position.y += self.velocity.y * dt
        landing = land(self.position, previous_bottom, self.velocity.y, self.width, self.height, platforms)
        if landing: self.position.y, self.velocity.y, self.jumps = landing.top - self.height, 0, 2

    def draw(self, surface, camera):
        if self.invulnerable > 0 and int(self.invulnerable * 18) % 2 == 0: return
        x, y = int(self.position.x - camera), int(self.position.y + math.sin(self.walk_time) * (2 if abs(self.velocity.x) > 20 else 0))
        cloak = (255, 140, 155) if self.hurt_flash > 0 else (240, 245, 255)
        pygame.draw.ellipse(surface, (8, 12, 28), (x - 5, y + 61, 52, 14))
        pygame.draw.polygon(surface, (36, 42, 74), [(x + 21, y + 27), (x + 3, y + 69), (x + 39, y + 69)])
        pygame.draw.polygon(surface, cloak, [(x + 12, y + 19), (x + 7, y - 3), (x + 18, y + 8), (x + 24, y - 8), (x + 31, y + 8), (x + 39, y - 3), (x + 34, y + 23)])
        pygame.draw.ellipse(surface, (17, 21, 44), (x + 15, y + 12, 19, 17))
        pygame.draw.circle(surface, (175, 220, 255), (x + 21, y + 20), 2)
        pygame.draw.circle(surface, (175, 220, 255), (x + 29, y + 20), 2)
        if self.attack_timer > 0:
            radius = int(34 + (1 - self.attack_timer / .22) * 18)
            center = (x + (44 if self.facing > 0 else -2), y + 35)
            pygame.draw.arc(surface, (225, 247, 255), Rect(center[0] - radius, center[1] - radius, radius * 2, radius * 2), -1.2 if self.facing > 0 else 2, 1.2 if self.facing > 0 else 4.4, 5)


class Boss:
    def __init__(self):
        self.position = Vector2(1050, GROUND - 110)
        self.width, self.height = 68, 110
        self.health = self.max_health = 240
        self.phase = 1
        self.facing = -1
        self.facing_visual = -1.0
        self.velocity = Vector2()
        self.attack_timer = 0
        self.attack_cooldown = 1.0
        self.invulnerable = self.hurt_flash = 0
        self.transition = 0
        self.anim_time = 0
        self.attack_serial = 0
        self.attack_kind = ""
        self.step_time = 0
        self.idle_phase = 0

    @property
    def rect(self): return Rect(int(self.position.x), int(self.position.y), self.width, self.height)

    def damage(self, amount, particles):
        if self.invulnerable > 0 or self.transition > 0: return False
        self.health = max(0, self.health - amount)
        self.invulnerable, self.hurt_flash = .16, .16
        for _ in range(14): particles.append(Particle(Vector2(self.rect.center), Vector2(random.uniform(-160, 160), random.uniform(-180, 60)), (255, 225, 135), 4, .55, 260))
        return True

    def transform(self, particles):
        self.phase = 2
        self.transition = 2.8
        self.width, self.height = 104, 154
        self.position.y = GROUND - self.height
        for _ in range(60):
            angle, speed = random.uniform(0, math.tau), random.uniform(120, 360)
            particles.append(Particle(Vector2(self.rect.center), Vector2(math.cos(angle) * speed, math.sin(angle) * speed), random.choice([(255, 50, 100), (255, 160, 80)]), random.uniform(3, 8), random.uniform(.7, 1.5), 100))

    def update(self, dt, player, platforms, hazards, particles):
        self.anim_time += dt
        for name in ("attack_timer", "attack_cooldown", "invulnerable", "hurt_flash", "transition"):
            setattr(self, name, max(0, getattr(self, name) - dt))
        if self.health <= self.max_health * .5 and self.phase == 1: self.transform(particles)
        if self.transition > 0: return
        distance = player.position.x - self.position.x
        desired_facing = 1 if distance > 0 else -1
        self.facing_visual += (desired_facing - self.facing_visual) * min(1, dt * 8)
        self.facing = desired_facing
        if self.phase == 1:
            self.velocity.y += 1400 * dt
            self.velocity.x = self.facing * 120
        else:
            target_y = clamp(player.position.y - 120 + math.sin(self.anim_time * 2.4) * 42, 80, GROUND - self.height - 20)
            self.velocity.y = (target_y - self.position.y) * 3.1
            self.velocity.x = self.facing * 230
        moving = abs(self.velocity.x) > 30
        self.step_time += dt * (8 if moving else 2)
        if abs(distance) < (170 if self.phase == 2 else 115): self.velocity.x *= .15
        if self.attack_cooldown <= 0:
            self.attack_cooldown = 1.08 if self.phase == 1 else .76
            self.attack_timer = .42 if self.phase == 1 else .5
            self.attack_serial += 1
            direction = 1 if distance > 0 else -1
            center = Vector2(self.rect.center)
            if self.phase == 1:
                self.attack_kind = "CORTE DA COROA"
                hazards.append(Hazard(center, Vector2(direction * 225, 0), 19, 14, "slash", .34, 1.7))
            elif self.attack_serial % 2:
                self.attack_kind = "LÂMINA DA FENDA"
                hazards.append(Hazard(center, Vector2(direction * 310, 0), 23, 17, "slash", .40, 1.7))
            else:
                self.attack_kind = "CÍRCULO DO ABISMO"
                hazards.append(Hazard(Vector2(player.position.x, GROUND - 38), Vector2(), 32, 18, "ring", .48, 1.8))
        previous_bottom = self.position.y + self.height
        self.position.x = clamp(self.position.x + self.velocity.x * dt, 700, WORLD - self.width - 20)
        self.position.y += self.velocity.y * dt
        if self.phase == 1:
            landing = land(self.position, previous_bottom, self.velocity.y, self.width, self.height, platforms)
            if landing: self.position.y, self.velocity.y = landing.top - self.height, 0

    def draw(self, surface, camera):
        x, y = int(self.position.x - camera), int(self.position.y + math.sin(self.step_time) * (2 if abs(self.velocity.x) > 30 else 0))
        center = x + self.width // 2
        cloak = (255, 88, 110) if self.hurt_flash > 0 else ((90, 18, 47) if self.phase == 2 else (35, 29, 70))
        accent = (255, 50, 94) if self.phase == 2 else (110, 90, 195)
        pygame.draw.ellipse(surface, (8, 8, 20), (center - int(self.width * .75), y + self.height - 9, int(self.width * 1.5), 22))
        if self.phase == 2:
            wing_y = y + 60 + int(math.sin(self.anim_time * 7) * 8)
            for side in (-1, 1):
                pygame.draw.polygon(surface, (120, 16, 60), [(center + side * 25, wing_y), (center + side * 135, wing_y - 58), (center + side * 88, wing_y + 18), (center + side * 145, wing_y + 48), (center + side * 22, wing_y + 38)])
            for radius in (76, 102, 126): pygame.draw.arc(surface, (255, 55, 105), Rect(center - radius, y + 38 - radius // 3, radius * 2, radius * 2), .55, 2.6, 2)
        pygame.draw.polygon(surface, cloak, [(center, y + 28), (center - self.width // 2, y + self.height - 5), (center + self.width // 2, y + self.height - 5)])
        pygame.draw.polygon(surface, (125, 35, 70) if self.phase == 2 else (55, 49, 94), [(center, y + 32), (center - self.width // 4, y + self.height - 12), (center + self.width // 4, y + self.height - 12)])
        head = Rect(center - int(self.width * .31), y + 14, int(self.width * .62), int(self.height * .25))
        pygame.draw.ellipse(surface, (220, 228, 246), head)
        pygame.draw.ellipse(surface, (13, 11, 31), head.inflate(-10, -7))
        eye = (255, 65, 102) if self.phase == 2 else (252, 214, 128)
        pygame.draw.circle(surface, eye, (center - 8, head.centery), 3 + self.phase)
        pygame.draw.circle(surface, eye, (center + 8, head.centery), 3 + self.phase)
        if self.attack_timer > 0:
            radius = 48 if self.phase == 1 else 82
            attack_center = (center + (self.width // 2 + 17 if self.facing > 0 else -(self.width // 2 + 17)), y + int(self.height * .45))
            pygame.draw.arc(surface, accent, Rect(attack_center[0] - radius, attack_center[1] - radius, radius * 2, radius * 2), -1.1 if self.facing > 0 else 2.05, 1.1 if self.facing > 0 else 4.25, 8)
            draw_text(surface, self.attack_kind, (center, y - 48), 13, (255, 205, 140), center=True, bold=True)
        if self.transition > 0: draw_text(surface, "A ABISMO DESPERTA", (center, y - 62), 28, (255, 225, 175), center=True, bold=True)


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Ecos do Abismo — Entrada Cinematográfica")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.running = True
        self.reset()

    def reset(self):
        self.player, self.boss = Player(), Boss()
        self.particles, self.hazards, self.waves = [], [], []
        self.camera = self.elapsed = self.screen_shake = 0.0
        self.damage_flash = self.pressure = 0.0
        self.state, self.state_timer = "intro", 3.6
        self.jump_down = self.attack_down = self.dodge_down = False
        self.platforms = [Rect(0, GROUND, WORLD - 500, HEIGHT - GROUND), Rect(260, 390, 170, 18), Rect(640, 330, 190, 18), Rect(1000, 390, 210, 18), Rect(1260, 300, 180, 18)]
        self.intro_camera = 0.0

    def burst(self, position, color, count=18, vortex=False):
        for index in range(count):
            angle = self.elapsed * 2 + index * math.tau / max(1, count) if vortex else random.uniform(0, math.tau)
            speed = random.uniform(90, 340)
            self.particles.append(Particle(Vector2(position), Vector2(math.cos(angle) * speed, math.sin(angle) * speed), color, random.uniform(2, 6), random.uniform(.35, .9), random.uniform(-40, 240), 1.5))

    def input(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT: self.running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: self.running = False
                if event.key == pygame.K_r and self.state in {"win", "lose"}: self.reset()
        keys = pygame.key.get_pressed()
        jump = bool(keys[pygame.K_SPACE] or keys[pygame.K_w] or keys[pygame.K_UP])
        attack = bool(keys[pygame.K_j] or keys[pygame.K_x])
        dodge = bool(keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])
        if self.state == "fight":
            if jump and not self.jump_down: self.player.jump(self.particles)
            if attack and not self.attack_down: self.player.attack(self.particles)
            if dodge and not self.dodge_down: self.player.dodge(self.particles)
        self.jump_down, self.attack_down, self.dodge_down = jump, attack, dodge

    def update(self, dt):
        self.elapsed += dt
        self.screen_shake = max(0, self.screen_shake - dt * 2.5)
        self.damage_flash = max(0, self.damage_flash - dt * 5)
        self.pressure = max(0, self.pressure - dt * 1.6)
        self.particles = [p for p in self.particles if p.update(dt)]
        self.waves = [w for w in self.waves if w.update(dt)]
        self.hazards = [h for h in self.hazards if h.update(dt)]
        if self.state == "intro":
            self.state_timer -= dt
            self.intro_camera += dt
            self.boss.anim_time += dt
            self.pressure = .35
            if random.random() < min(1, dt * 18): self.burst(self.boss.rect.center, (125, 55, 190), 4, True)
            if self.state_timer <= 0: self.state = "fight"
            return
        if self.state != "fight": return
        before_p, before_b, before_phase = self.player.health, self.boss.health, self.boss.phase
        self.player.update(dt, pygame.key.get_pressed(), self.platforms)
        self.boss.update(dt, self.player, self.platforms, self.hazards, self.particles)
        if self.boss.attack_timer > 0 and self.boss.attack_timer > .35: self.pressure = max(self.pressure, .65)
        for hazard in self.hazards:
            if hazard.armed and hazard.position.distance_to(self.player.rect.center) < hazard.radius + 25 and self.player.damage(hazard.damage, self.particles):
                hazard.hit = True
                self.waves.append(Wave(Vector2(self.player.rect.center), (255, 65, 115)))
        if self.player.attack_timer > 0 and self.player.attack_rect.colliderect(self.boss.rect) and self.boss.damage(12, self.particles):
            self.damage_flash, self.screen_shake = 1.0, .18
            self.waves.append(Wave(Vector2(self.boss.rect.center), (255, 225, 145)))
            self.burst(self.boss.rect.center, (255, 235, 165), 12)
        if self.player.health < before_p or self.boss.health < before_b:
            self.damage_flash, self.screen_shake = 1.0, max(self.screen_shake, .24)
        if before_phase != self.boss.phase:
            self.pressure, self.screen_shake = 1.0, 1.0
            self.waves.append(Wave(Vector2(self.boss.rect.center), (255, 50, 110), 25, 1.0, 7))
            self.burst(self.boss.rect.center, (255, 60, 110), 60, True)
        if self.player.health <= 0: self.state = "lose"
        elif self.boss.health <= 0: self.state = "win"
        target = self.player.position.x - WIDTH * .36
        self.camera += (target - self.camera) * min(1, dt * 5)
        self.camera = clamp(self.camera, 0, WORLD - WIDTH)

    def draw_background(self, surface):
        phase = self.boss.phase == 2
        top, bottom = ((38, 7, 30), (111, 15, 47)) if phase else ((8, 15, 42), (28, 44, 77))
        for y in range(HEIGHT):
            ratio = y / HEIGHT
            pygame.draw.line(surface, tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3)), (0, y), (WIDTH, y))
        moon = (255, 75, 105) if phase else (194, 224, 255)
        mx = int(770 - self.camera * .12)
        glow(surface, (mx, 104), moon, 90, 35)
        pygame.draw.circle(surface, moon, (mx, 104), 42)
        if phase:
            rift = WIDTH // 2 + int(math.sin(self.elapsed * 1.4) * 35)
            pygame.draw.polygon(surface, (85, 5, 45), [(rift - 24, 0), (rift + 20, 0), (rift + 8, 150), (rift + 30, 280), (rift - 30, 360)])
            for offset in (-14, 0, 15): pygame.draw.line(surface, (255, 55, 100), (rift + offset, 0), (rift + offset + int(math.sin(self.elapsed * 3 + offset) * 16), 320), 2)
        for layer, (color, height, speed) in enumerate([((20, 28, 58), 220, .18), ((17, 24, 48), 280, .3), ((12, 17, 35), 350, .5)]):
            points = [(x, height + math.sin((x + self.camera * speed) * .012 + layer * 2) * 28) for x in range(-100, WIDTH + 140, 100)]
            points += [(WIDTH + 100, HEIGHT), (-100, HEIGHT)]
            pygame.draw.polygon(surface, color, points)

    def draw_hud(self, surface):
        draw_text(surface, "LIRA", (24, 18), 14, (185, 205, 235), bold=True)
        pygame.draw.rect(surface, (12, 15, 32), (24, 40, 230, 16), border_radius=5)
        pygame.draw.rect(surface, (95, 205, 235), (27, 43, int(224 * self.player.health / 100), 10), border_radius=4)
        title = "REI DO ABISMO — FÚRIA" if self.boss.phase == 2 else "REI DO ABISMO"
        draw_text(surface, title, (WIDTH - 320, 18), 14, (255, 110, 135) if self.boss.phase == 2 else (230, 215, 180), bold=True)
        pygame.draw.rect(surface, (12, 15, 32), (WIDTH - 300, 40, 276, 16), border_radius=5)
        pygame.draw.rect(surface, (245, 75, 100), (WIDTH - 297, 43, int(270 * self.boss.health / self.boss.max_health), 10), border_radius=4)

    def draw(self):
        scene = Surface((WIDTH, HEIGHT))
        self.draw_background(scene)
        for platform in self.platforms:
            rect = platform.move(-int(self.camera), 0)
            pygame.draw.rect(scene, (18, 28, 54), rect)
            pygame.draw.line(scene, (180, 70, 100) if self.boss.phase == 2 else (95, 125, 165), (rect.left, rect.top), (rect.right, rect.top), 3)
        for wave in self.waves: wave.draw(scene, self.camera)
        for particle in self.particles: particle.draw(scene, self.camera)
        for hazard in self.hazards: hazard.draw(scene, self.camera, self.boss.phase)
        self.boss.draw(scene, self.camera)
        self.player.draw(scene, self.camera)
        self.draw_hud(scene)
        if self.state == "intro":
            overlay = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((2, 2, 12, 160))
            scene.blit(overlay, (0, 0))
            progress = 1 - self.state_timer / 3.6
            bars = int(64 * (1 - ease(progress)))
            pygame.draw.rect(scene, (1, 1, 7), (0, 0, WIDTH, bars))
            pygame.draw.rect(scene, (1, 1, 7), (0, HEIGHT - bars, WIDTH, bars))
            center = (int(self.boss.rect.centerx - self.camera), int(self.boss.rect.centery))
            glow(scene, center, (110, 45, 190), 100 + int(ease(progress) * 65), 70)
            pygame.draw.circle(scene, (255, 210, 130), center, 25 + int(ease(progress) * 90), 2)
            for index in range(16):
                angle = self.intro_camera * .8 + index * math.tau / 16
                length = 35 + int(ease(progress) * 125)
                pygame.draw.line(scene, (255, 55, 110), center, (center[0] + int(math.cos(angle) * length), center[1] + int(math.sin(angle) * length)), 2)
            title = Surface((WIDTH, 120), pygame.SRCALPHA)
            draw_text(title, "O REI DO ABISMO", (WIDTH // 2, 28), 38, (255, 225, 175), center=True, bold=True)
            draw_text(title, "A COROA QUE ACORDA", (WIDTH // 2, 76), 18, (255, 105, 135), center=True, bold=True)
            title.set_alpha(int(clamp(math.sin(clamp(progress, 0, 1) * math.pi) * 1.5, 0, 1) * 255))
            scene.blit(title, (0, 132))
        if self.boss.phase == 2 and self.boss.transition > 0:
            overlay = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((150, 5, 45, 105))
            scene.blit(overlay, (0, 0))
            draw_text(scene, "O ABISMO DESPERTA", (WIDTH // 2, 130), 31, (255, 230, 180), center=True, bold=True)
            draw_text(scene, "A ARENA PERTENCE AO REI", (WIDTH // 2, 172), 17, (255, 105, 140), center=True, bold=True)
        if self.pressure > 0 and self.state == "fight":
            border = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.rect(border, (255, 35, 90, int(75 * self.pressure)), (8, 88, WIDTH - 16, HEIGHT - 112), 3)
            scene.blit(border, (0, 0))
        if self.damage_flash > 0:
            flash = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            flash.fill((255, 245, 210, int(125 * self.damage_flash)))
            scene.blit(flash, (0, 0))
        if self.state in {"win", "lose"}:
            overlay = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((3, 4, 14, 185))
            scene.blit(overlay, (0, 0))
            title = "O ABISMO SILENCIOU" if self.state == "win" else "A ESCURIDÃO VENCEU"
            color = (200, 240, 255) if self.state == "win" else (255, 135, 155)
            draw_text(scene, title, (WIDTH // 2, 210), 34, color, center=True, bold=True)
            draw_text(scene, "Pressione R para tentar novamente", (WIDTH // 2, 270), 17, (220, 225, 240), center=True)
        shake = int(self.screen_shake * 22)
        self.screen.fill((3, 5, 16))
        self.screen.blit(scene, (random.randint(-shake, shake), random.randint(-shake, shake)) if shake else (0, 0))
        pygame.display.flip()

    def run(self):
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000, 0.033)
            self.input()
            self.update(dt)
            self.draw()
        pygame.quit()


if __name__ == "__main__":
    Game().run()
