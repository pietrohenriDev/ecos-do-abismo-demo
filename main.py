from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame
from pygame import Rect, Surface
from pygame.math import Vector2

WIDTH, HEIGHT, FPS = 960, 540, 60
GROUND_Y, WORLD_WIDTH = 468, 1500


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def ease(value: float) -> float:
    value = clamp(value, 0.0, 1.0)
    return value * value * (3.0 - 2.0 * value)


def draw_text(surface: Surface, value: str, pos: tuple[int, int], size: int,
              color: tuple[int, int, int], *, center: bool = False,
              bold: bool = False) -> None:
    """Render text without passing invalid None coordinates to pygame.Rect."""
    font = pygame.font.SysFont("dejavusans", size, bold=bold)
    image = font.render(value, True, color)
    rect = image.get_rect()
    if center:
        rect.center = pos
    else:
        rect.topleft = pos
    surface.blit(image, rect)


def glow(surface: Surface, center: tuple[int, int], color: tuple[int, int, int],
         radius: int, alpha: int = 70) -> None:
    radius = max(4, int(radius))
    layer = Surface((radius * 2 + 8, radius * 2 + 8), pygame.SRCALPHA)
    middle = layer.get_width() // 2
    for step in range(4, 0, -1):
        pygame.draw.circle(layer, (*color, alpha * step // 8),
                           (middle, middle), radius * step // 4)
    surface.blit(layer, (center[0] - middle, center[1] - middle))


def land_on_platform(position: Vector2, previous_bottom: float,
                     velocity_y: float, width: int, height: int,
                     platforms: list[Rect]) -> Rect | None:
    if velocity_y < 0:
        return None
    current = Rect(int(position.x), int(position.y), width, height)
    candidates = [
        platform for platform in platforms
        if current.right > platform.left
        and current.left < platform.right
        and previous_bottom <= platform.top + 4
        and current.bottom >= platform.top
    ]
    return min(candidates, key=lambda platform: platform.top) if candidates else None


@dataclass
class Particle:
    position: Vector2
    velocity: Vector2
    color: tuple[int, int, int]
    radius: float
    life: float
    gravity: float = 0.0
    drag: float = 0.0

    def update(self, dt: float) -> bool:
        self.position += self.velocity * dt
        self.velocity *= max(0.0, 1.0 - self.drag * dt)
        self.velocity.y += self.gravity * dt
        self.life -= dt
        self.radius *= 0.985
        return self.life > 0 and self.radius > 0.5

    def draw(self, surface: Surface, camera: float) -> None:
        alpha = int(clamp(self.life / 0.8, 0, 1) * 255)
        layer = Surface((20, 20), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*self.color, alpha), (10, 10),
                           max(1, int(self.radius)))
        surface.blit(layer, (int(self.position.x - camera - 10),
                             int(self.position.y - 10)))


@dataclass
class Wave:
    position: Vector2
    color: tuple[int, int, int]
    radius: float = 10
    life: float = 0.55
    width: int = 4

    def update(self, dt: float) -> bool:
        self.radius += (285 - self.radius) * min(1, dt * 9)
        self.life -= dt
        return self.life > 0

    def draw(self, surface: Surface, camera: float) -> None:
        alpha = int(clamp(self.life / 0.55, 0, 1) * 220)
        layer = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        pygame.draw.ellipse(
            layer,
            (*self.color, alpha),
            (int(self.position.x - camera - self.radius),
             int(self.position.y - self.radius * 0.45),
             int(self.radius * 2), int(self.radius * 0.9)),
            self.width,
        )
        surface.blit(layer, (0, 0))


@dataclass
class Hazard:
    position: Vector2
    velocity: Vector2
    radius: int
    damage: int
    kind: str
    telegraph: float
    life: float = 2.0
    age: float = 0.0
    hit: bool = False

    @property
    def armed(self) -> bool:
        return self.age >= self.telegraph

    def update(self, dt: float) -> bool:
        self.age += dt
        self.life -= dt
        self.position += self.velocity * dt
        return self.life > 0 and not self.hit

    def draw(self, surface: Surface, camera: float, phase: int) -> None:
        x, y = int(self.position.x - camera), int(self.position.y)
        danger = (255, 55, 100) if phase == 2 else (222, 72, 92)
        if not self.armed:
            pulse = int(5 + math.sin(self.age * 28) * 3)
            pygame.draw.circle(surface, (255, 221, 125),
                               (x, y), self.radius + 11 + pulse, 2)
            pygame.draw.line(surface, (255, 190, 90),
                             (x - 20, y), (x + 20, y), 2)
            return
        glow(surface, (x, y), danger, self.radius * 3, 65)
        if self.kind == "ring":
            pygame.draw.circle(surface, danger, (x, y),
                               self.radius + int(self.age * 32), 7)
            pygame.draw.circle(surface, (255, 240, 190), (x, y),
                               max(3, self.radius // 3), 2)
        else:
            pygame.draw.circle(surface, danger, (x, y), self.radius)
            pygame.draw.circle(surface, (255, 230, 160),
                               (x - 3, y - 3), max(2, self.radius // 3))


class Player:
    def __init__(self) -> None:
        self.position = Vector2(130, GROUND_Y - 72)
        self.velocity = Vector2()
        self.width, self.height = 42, 72
        self.facing = 1
        self.health = 100
        self.jumps = 2
        self.attack_timer = 0.0
        self.attack_cooldown = 0.0
        self.dodge_timer = 0.0
        self.dodge_cooldown = 0.0
        self.invulnerable = 0.0
        self.hurt_flash = 0.0
        self.walk_time = 0.0

    @property
    def rect(self) -> Rect:
        return Rect(int(self.position.x), int(self.position.y), self.width, self.height)

    @property
    def attack_rect(self) -> Rect:
        x = self.position.x + (self.width if self.facing > 0 else -76)
        return Rect(int(x), int(self.position.y + 17), 76, 34)

    def jump(self, particles: list[Particle]) -> None:
        if self.jumps <= 0:
            return
        self.velocity.y = -620 if self.jumps == 2 else -540
        self.jumps -= 1
        for _ in range(8):
            particles.append(Particle(
                Vector2(self.rect.centerx, self.rect.bottom),
                Vector2(random.uniform(-70, 70), random.uniform(-110, -20)),
                (170, 210, 235), 3, 0.45, 160,
            ))

    def attack(self, particles: list[Particle]) -> bool:
        if self.attack_timer > 0 or self.attack_cooldown > 0:
            return False
        self.attack_timer, self.attack_cooldown = 0.22, 0.28
        for _ in range(8):
            particles.append(Particle(
                Vector2(self.attack_rect.center),
                Vector2(random.uniform(40, 150) * self.facing,
                        random.uniform(-40, 40)),
                (220, 245, 255), 3, 0.28, 0, 3,
            ))
        return True

    def dodge(self, particles: list[Particle]) -> bool:
        if self.dodge_timer > 0 or self.dodge_cooldown > 0:
            return False
        self.dodge_timer, self.dodge_cooldown, self.invulnerable = 0.18, 0.8, 0.3
        self.velocity = Vector2(self.facing * 760, 0)
        for _ in range(12):
            particles.append(Particle(
                Vector2(self.rect.center),
                Vector2(-self.facing * random.uniform(100, 280), random.uniform(-70, 70)),
                (160, 220, 255), 4, 0.35, 150,
            ))
        return True

    def damage(self, amount: int, particles: list[Particle]) -> bool:
        if self.invulnerable > 0:
            return False
        self.health = max(0, self.health - amount)
        self.invulnerable, self.hurt_flash = 0.85, 0.2
        self.velocity.x = -240 if self.facing > 0 else 240
        for _ in range(18):
            particles.append(Particle(
                Vector2(self.rect.center),
                Vector2(random.uniform(-180, 180), random.uniform(-180, 40)),
                (255, 100, 135), 4, 0.55, 320,
            ))
        return True

    def update(self, dt: float, keys, platforms: list[Rect]) -> None:
        for name in ("attack_timer", "attack_cooldown", "dodge_timer",
                     "dodge_cooldown", "invulnerable", "hurt_flash"):
            setattr(self, name, max(0.0, getattr(self, name) - dt))
        if self.dodge_timer > 0:
            self.position.x = clamp(self.position.x + self.velocity.x * dt,
                                    20, WORLD_WIDTH - self.width - 20)
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
        self.position.x = clamp(self.position.x + self.velocity.x * dt, 20, WORLD_WIDTH - self.width - 20)
        self.position.y += self.velocity.y * dt
        landing = land_on_platform(self.position, previous_bottom, self.velocity.y, self.width, self.height, platforms)
        if landing:
            self.position.y, self.velocity.y, self.jumps = landing.top - self.height, 0, 2

    def draw(self, surface: Surface, camera: float) -> None:
        if self.invulnerable > 0 and int(self.invulnerable * 18) % 2 == 0:
            return
        x, y = int(self.position.x - camera), int(self.position.y + math.sin(self.walk_time) * (2 if abs(self.velocity.x) > 20 else 0))
        cloak = (255, 140, 155) if self.hurt_flash > 0 else (240, 245, 255)
        pygame.draw.ellipse(surface, (8, 12, 28), (x - 5, y + 61, 52, 14))
        pygame.draw.polygon(surface, (36, 42, 74), [(x + 21, y + 27), (x + 3, y + 69), (x + 39, y + 69)])
        pygame.draw.polygon(surface, cloak, [(x + 12, y + 19), (x + 7, y - 3), (x + 18, y + 8), (x + 24, y - 8), (x + 31, y + 8), (x + 39, y - 3), (x + 34, y + 23)])
        pygame.draw.ellipse(surface, (17, 21, 44), (x + 15, y + 12, 19, 17))
        pygame.draw.circle(surface, (175, 220, 255), (x + 21, y + 20), 2)
        pygame.draw.circle(surface, (175, 220, 255), (x + 29, y + 20), 2)
        if self.attack_timer > 0:
            radius = int(34 + (1 - self.attack_timer / 0.22) * 18)
            center = (x + (44 if self.facing > 0 else -2), y + 35)
            pygame.draw.arc(surface, (225, 247, 255), Rect(center[0] - radius, center[1] - radius, radius * 2, radius * 2), -1.2 if self.facing > 0 else 2, 1.2 if self.facing > 0 else 4.4, 5)


class Boss:
    def __init__(self) -> None:
        self.position = Vector2(1050, GROUND_Y - 110)
        self.width, self.height = 68, 110
        self.health = self.max_health = 240
        self.phase = 1
        self.facing = -1
        self.velocity = Vector2()
        self.attack_timer = 0.0
        self.attack_cooldown = 1.0
        self.invulnerable = self.hurt_flash = 0.0
        self.transition = 0.0
        self.anim_time = 0.0
        self.attack_serial = 0
        self.attack_kind = ""

    @property
    def rect(self) -> Rect:
        return Rect(int(self.position.x), int(self.position.y), self.width, self.height)

    def damage(self, amount: int, particles: list[Particle]) -> bool:
        if self.invulnerable > 0 or self.transition > 0:
            return False
        self.health = max(0, self.health - amount)
        self.invulnerable, self.hurt_flash = 0.16, 0.16
        for _ in range(14):
            particles.append(Particle(Vector2(self.rect.center), Vector2(random.uniform(-160, 160), random.uniform(-180, 60)), (255, 225, 135), 4, 0.55, 260))
        return True

    def transform(self, particles: list[Particle]) -> None:
        self.phase = 2
        self.transition = 2.8
        self.width, self.height = 104, 154
        self.position.y = GROUND_Y - self.height
        for _ in range(60):
            angle, speed = random.uniform(0, math.tau), random.uniform(120, 360)
            particles.append(Particle(Vector2(self.rect.center), Vector2(math.cos(angle) * speed, math.sin(angle) * speed), random.choice([(255, 50, 100), (255, 160, 80)]), random.uniform(3, 8), random.uniform(0.7, 1.5), 100))

    def update(self, dt, player, platforms, hazards, particles) -> None:
        self.anim_time += dt
        self.attack_timer = max(0.0, self.attack_timer - dt)
        self.attack_cooldown = max(0.0, self.attack_cooldown - dt)
        self.invulnerable = max(0.0, self.invulnerable - dt)
        self.hurt_flash = max(0.0, self.hurt_flash - dt)
        self.transition = max(0.0, self.transition - dt)
        if self.health <= self.max_health * 0.5 and self.phase == 1:
            self.transform(particles)
        if self.transition > 0:
            return
        distance = player.position.x - self.position.x
        self.facing = 1 if distance > 0 else -1
        if self.phase == 1:
            self.velocity.y += 1400 * dt
            self.velocity.x = self.facing * 120
        else:
            target_y = clamp(player.position.y - 120 + math.sin(self.anim_time * 2.4) * 42, 80, GROUND_Y - self.height - 20)
            self.velocity.y = (target_y - self.position.y) * 3.1
            self.velocity.x = self.facing * 230
        if abs(distance) < (170 if self.phase == 2 else 115):
            self.velocity.x *= 0.15
        if self.attack_cooldown <= 0:
            self.attack_cooldown = 1.08 if self.phase == 1 else 0.76
            self.attack_timer = 0.42 if self.phase == 1 else 0.5
            self.attack_serial += 1
            direction = 1 if distance > 0 else -1
            center = Vector2(self.rect.center)
            if self.phase == 1:
                self.attack_kind = "CORTE DA COROA"
                hazards.append(Hazard(center, Vector2(direction * 225, 0), 19, 14, "slash", 0.34, 1.7))
            elif self.attack_serial % 2:
                self.attack_kind = "LÂMINA DA FENDA"
                hazards.append(Hazard(center, Vector2(direction * 310, 0), 23, 17, "slash", 0.40, 1.7))
            else:
                self.attack_kind = "CÍRCULO DO ABISMO"
                hazards.append(Hazard(Vector2(player.position.x, GROUND_Y - 38), Vector2(), 32, 18, "ring", 0.48, 1.8))
        previous_bottom = self.position.y + self.height
        self.position.x = clamp(self.position.x + self.velocity.x * dt, 700, WORLD_WIDTH - self.width - 20)
        self.position.y += self.velocity.y * dt
        if self.phase == 1:
            landing = land_on_platform(self.position, previous_bottom, self.velocity.y, self.width, self.height, platforms)
            if landing:
                self.position.y, self.velocity.y = landing.top - self.height, 0

    def draw(self, surface, camera):
        x, y = int(self.position.x - camera), int(self.position.y)
        center = x + self.width // 2
        cloak = (255, 88, 110) if self.hurt_flash > 0 else ((90, 18, 47) if self.phase == 2 else (35, 29, 70))
        accent = (255, 50, 94) if self.phase == 2 else (110, 90, 195)
        pygame.draw.ellipse(surface, (8, 8, 20), (center - int(self.width * 0.75), y + self.height - 9, int(self.width * 1.5), 22))
        if self.phase == 2:
            wing_y = y + 60 + int(math.sin(self.anim_time * 7) * 8)
            for side in (-1, 1):
                pygame.draw.polygon(surface, (120, 16, 60), [(center + side * 25, wing_y), (center + side * 135, wing_y - 58), (center + side * 88, wing_y + 18), (center + side * 145, wing_y + 48), (center + side * 22, wing_y + 38)])
            for radius in (76, 102, 126):
                pygame.draw.arc(surface, (255, 55, 105), Rect(center - radius, y + 38 - radius // 3, radius * 2, radius * 2), 0.55, 2.6, 2)
        pygame.draw.polygon(surface, cloak, [(center, y + 28), (center - self.width // 2, y + self.height - 5), (center + self.width // 2, y + self.height - 5)])
        pygame.draw.polygon(surface, (125, 35, 70) if self.phase == 2 else (55, 49, 94), [(center, y + 32), (center - self.width // 4, y + self.height - 12), (center + self.width // 4, y + self.height - 12)])
        head = Rect(center - int(self.width * 0.31), y + 14, int(self.width * 0.62), int(self.height * 0.25))
        pygame.draw.ellipse(surface, (220, 228, 246), head)
        pygame.draw.ellipse(surface, (13, 11, 31), head.inflate(-10, -7))
        eye = (255, 65, 102) if self.phase == 2 else (252, 214, 128)
        pygame.draw.circle(surface, eye, (center - 8, head.centery), 3 + self.phase)
        pygame.draw.circle(surface, eye, (center + 8, head.centery), 3 + self.phase)
        if self.attack_timer > 0:
            radius = 48 if self.phase == 1 else 82
            attack_center = (center + (self.width // 2 + 17 if self.facing > 0 else -(self.width // 2 + 17)), y + int(self.height * 0.45))
            pygame.draw.arc(surface, accent, Rect(attack_center[0] - radius, attack_center[1] - radius, radius * 2, radius * 2), -1.1 if self.facing > 0 else 2.05, 1.1 if self.facing > 0 else 4.25, 8)
            draw_text(surface, self.attack_kind, (center, y - 48), 13, (255, 205, 140), center=True, bold=True)
        if self.transition > 0:
            draw_text(surface, "A ABISMO DESPERTA", (center, y - 62), 28, (255, 225, 175), center=True, bold=True)


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Ecos do Abismo — Demo Estável")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.running = True
        self.reset()

    def reset(self):
        self.player, self.boss = Player(), Boss()
        self.particles, self.hazards, self.waves = [], [], []
        self.camera = 0.0
        self.elapsed = 0.0
        self.screen_shake = 0.0
        self.damage_flash = 0.0
        self.pressure = 0.0
        self.state = "intro"
        self.state_timer = 2.8
        self.jump_down = self.attack_down = self.dodge_down = False
        self.platforms = [Rect(0, GROUND_Y, WORLD_WIDTH, HEIGHT - GROUND_Y), Rect(260, 390, 170, 18), Rect(640, 330, 190, 18), Rect(1000, 390, 210, 18), Rect(1260, 300, 180, 18)]

    def burst(self, position, color, count=18, vortex=False):
        for index in range(count):
            angle = self.elapsed * 2 + index * math.tau / max(1, count) if vortex else random.uniform(0, math.tau)
            speed = random.uniform(90, 340)
            velocity = Vector2(math.cos(angle) * speed, math.sin(angle) * speed)
            self.particles.append(Particle(Vector2(position), velocity, color, random.uniform(2, 6), random.uniform(.35, .9), random.uniform(-40, 240), 1.5))

    def input(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                if event.key == pygame.K_r and self.state in {"win", "lose"}:
                    self.reset()
        keys = pygame.key.get_pressed()
        jump = bool(keys[pygame.K_SPACE] or keys[pygame.K_w] or keys[pygame.K_UP])
        attack = bool(keys[pygame.K_j] or keys[pygame.K_x])
        dodge = bool(keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])
        if self.state == "fight":
            if jump and not self.jump_down:
                self.player.jump(self.particles)
            if attack and not self.attack_down:
                self.player.attack(self.particles)
            if dodge and not self.dodge_down:
                self.player.dodge(self.particles)
        self.jump_down, self.attack_down, self.dodge_down = jump, attack, dodge

    def update(self, dt):
        self.elapsed += dt
        self.screen_shake = max(0, self.screen_shake - dt * 2.5)
        self.damage_flash = max(0, self.damage_flash - dt * 5)
        self.pressure = max(0, self.pressure - dt * 1.6)
        self.particles = [particle for particle in self.particles if particle.update(dt)]
        self.waves = [wave for wave in self.waves if wave.update(dt)]
        self.hazards = [hazard for hazard in self.hazards if hazard.update(dt)]
        if self.state == "intro":
            self.state_timer -= dt
            self.boss.anim_time += dt
            self.pressure = 0.3
            if random.random() < min(1, dt * 12):
                self.burst(self.boss.rect.center, (125, 55, 190), 3, True)
            if self.state_timer <= 0:
                self.state = "fight"
            return
        if self.state != "fight":
            return
        previous_health = self.player.health
        previous_boss = self.boss.health
        previous_phase = self.boss.phase
        self.player.update(dt, pygame.key.get_pressed(), self.platforms)
        self.boss.update(dt, self.player, self.platforms, self.hazards, self.particles)
        if self.boss.attack_timer > 0 and self.boss.attack_timer > 0.35:
            self.pressure = max(self.pressure, 0.65)
        for hazard in self.hazards:
            if hazard.armed and hazard.position.distance_to(self.player.rect.center) < hazard.radius + 25:
                if self.player.damage(hazard.damage, self.particles):
                    hazard.hit = True
        if self.player.attack_timer > 0 and self.player.attack_rect.colliderect(self.boss.rect):
            if self.boss.damage(12, self.particles):
                self.screen_shake = 0.16
                self.damage_flash = 1.0
                self.waves.append(Wave(Vector2(self.boss.rect.center), (255, 225, 145)))
                self.burst(self.boss.rect.center, (255, 235, 165), 12)
        if self.player.health < previous_health or self.boss.health < previous_boss:
            self.damage_flash = 1.0
            self.screen_shake = max(self.screen_shake, 0.22)
        if previous_phase != self.boss.phase:
            self.pressure = 1.0
            self.screen_shake = 1.0
            self.waves.append(Wave(Vector2(self.boss.rect.center), (255, 50, 110), radius=25, life=1.0, width=7))
            self.burst(self.boss.rect.center, (255, 60, 110), 60, True)
        if self.player.health <= 0:
            self.state = "lose"
        elif self.boss.health <= 0:
            self.state = "win"
        target = self.player.position.x - WIDTH * 0.36
        self.camera += (target - self.camera) * min(1, dt * 5)
        self.camera = clamp(self.camera, 0, WORLD_WIDTH - WIDTH)

    def draw_background(self, surface):
        phase = self.boss.phase == 2
        top, bottom = ((38, 7, 30), (111, 15, 47)) if phase else ((8, 15, 42), (28, 44, 77))
        for y in range(HEIGHT):
            ratio = y / HEIGHT
            pygame.draw.line(surface, tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3)), (0, y), (WIDTH, y))
        moon = (255, 75, 105) if phase else (194, 224, 255)
        mx = int(770 - self.camera * 0.12)
        pygame.draw.circle(surface, moon, (mx, 104), 42)
        if phase:
            rift = WIDTH // 2 + int(math.sin(self.elapsed * 1.4) * 35)
            pygame.draw.polygon(surface, (85, 5, 45), [(rift - 24, 0), (rift + 20, 0), (rift + 8, 150), (rift + 30, 280), (rift - 30, 360)])
            for offset in (-14, 0, 15):
                pygame.draw.line(surface, (255, 55, 100), (rift + offset, 0), (rift + offset + int(math.sin(self.elapsed * 3 + offset) * 16), 320), 2)
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
        for wave in self.waves:
            wave.draw(scene, self.camera)
        for particle in self.particles:
            particle.draw(scene, self.camera)
        for hazard in self.hazards:
            hazard.draw(scene, self.camera, self.boss.phase)
        self.boss.draw(scene, self.camera)
        self.player.draw(scene, self.camera)
        self.draw_hud(scene)
        if self.state == "intro":
            overlay = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((2, 2, 12, 160))
            scene.blit(overlay, (0, 0))
            progress = 1 - self.state_timer / 2.8
            bars = int(60 * (1 - ease(progress)))
            pygame.draw.rect(scene, (1, 1, 7), (0, 0, WIDTH, bars))
            pygame.draw.rect(scene, (1, 1, 7), (0, HEIGHT - bars, WIDTH, bars))
            center = (int(self.boss.rect.centerx - self.camera), int(self.boss.rect.centery))
            glow(scene, center, (110, 45, 190), 100, 70)
            draw_text(scene, "O REI DO ABISMO", (WIDTH // 2, 180), 36, (255, 225, 175), center=True, bold=True)
            draw_text(scene, "A COROA QUE ACORDA", (WIDTH // 2, 225), 18, (255, 105, 135), center=True, bold=True)
        if self.boss.phase == 2 and self.boss.transition > 0:
            overlay = Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((150, 5, 45, 95))
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
