# -*- coding: utf-8 -*-
"""JOTUNNSLAYER 复刻原型 —— 俯视角幸存者割草（Python + pygame-ce）。

运行：  python main.py            正常游玩
自测：  python main.py --smoke 90 无头模式自玩 90 秒，输出 JSON 统计并退出
"""
import math
import os
import random
import sys

# Windows 控制台 GBK 防崩
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SMOKE = "--smoke" in sys.argv
SMOKE_SECS = 90
MAP_ARG = None
DIFF_ARG = None
ENDLESS_ARG = "--endless" in sys.argv
if "--diff" in sys.argv:
    for i, a in enumerate(sys.argv):
        if a == "--diff" and i + 1 < len(sys.argv):
            DIFF_ARG = sys.argv[i + 1]
            break
if "--map" in sys.argv:
    for i, a in enumerate(sys.argv):
        if a == "--map" and i + 1 < len(sys.argv):
            MAP_ARG = sys.argv[i + 1]
            break
if SMOKE:
    for i, a in enumerate(sys.argv):
        if a == "--smoke" and i + 1 < len(sys.argv):
            try:
                SMOKE_SECS = float(sys.argv[i + 1])
            except ValueError:
                pass
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from settings import (WIDTH, HEIGHT, FPS, DT, MAX_FRAME, COL, CAM_LERP,
                      BOSS_TIME, SPAWN, XP, PLAYER, PHASE3, GOLD, QUEST,
                      CHEST, FOOD, DIFFICULTIES, DEFAULT_DIFFICULTY, ENDLESS)
from data import (WEAPONS, PASSIVES, FALLBACK_CARDS, MAX_WEAPONS,
                  EVOLUTIONS, WEAPON_MAX_LEVEL, BOSSES, MAPS, DEFAULT_MAP,
                  CHARS, DEFAULT_CHAR)
import fx
import ui
import boons as B
import bosses as BOSSAI
from vendor.alloy.core.event_bus import EventBus
from entities import (Player, Enemy, Gem, Shockwave, Shrine, init_gem_sprites,
                      EnemyBullet, Ally, Geyser, Swing, BreathZone, Food, Chest)
from weapons import Weapon, Bullet, HomingBullet, init_sprites
from spatial import SpatialHash
from spawner import Spawner
import save
import audio
import skills
import quests
import hazards
import meta

# 字段中文标签（武器升级预览用）
FIELD_CN = dict(count="弹数", damage="伤害", pierce="穿透", speed="速度",
                cooldown="冷却", radius="范围", size="体型", lifetime="射程")

# 宝箱三选一奖励池（Phase 5）
CHEST_POOL = [
    ("gold", "百金入账", "金币 +100"),
    ("reroll", "命运重掷", "重掷次数 +1"),
    ("banish", "诸神放逐", "放逐次数 +1"),
    ("food", "神赐肉块", "原地生成 2 块食物"),
    ("shrine", "神龛直传", "一座神龛降落在附近"),
    ("heal", "生命礼赞", "回复 50 生命"),
]


def _bolt_pts(x1, y1, x2, y2, jag=3):
    """生成抖动的闪电折线点列。"""
    pts = [(x1, y1)]
    for i in range(1, jag):
        t = i / jag
        mx, my = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        nx, ny = -(y2 - y1), (x2 - x1)
        n = math.hypot(nx, ny) or 1.0
        off = random.uniform(-14, 14)
        pts.append((mx + nx / n * off, my + ny / n * off))
    pts.append((x2, y2))
    return pts


class Game:
    def __init__(self, smoke=False, map_key=None, char_key=None):
        self.smoke = smoke
        self.map_key = map_key or DEFAULT_MAP
        self.char_key = char_key or DEFAULT_CHAR
        self.difficulty_key = DEFAULT_DIFFICULTY
        self.endless = False
        # 事件总线跨 reset 存活（音频/统计监听一次订阅长期有效）
        self.bus = EventBus()
        self.reset()

    def reset(self):
        self.state = "title"           # title / play / upgrade / boon / tree / pause / gameover
        self.victory = False
        self.god = False               # smoke 无头测试用
        self.time = 0.0
        self.kills = 0
        self.total_damage = 0.0
        self.level = 1
        self.xp = 0
        self.pending_cards = 0
        self.cards = []
        self.hover_idx = 0
        self.chosen = {}               # id -> 次数
        self.hurt_flash = 0.0

        # 金币（本局累计）+ 结算标记 + 跨局 meta 存档
        self.run_gold = 0
        self._settled = False
        self.meta = save.load_data()

        # Phase 5：任务 / 食物 / 宝箱 / 重掷放逐
        self.quest = None
        self.next_quest_at = QUEST["first_at"]
        self.quest_hold = (0.0, 0.0)
        self.foods = []
        self.chests = []
        self.chest_offer = None
        self.rerolls = 3
        self.banishes = 3
        self.banished_ids = set()

        # Phase 7：无尽 Boss 时间表 + 地图机关状态
        self.next_boss_at = BOSS_TIME
        self.cart_t = 0.0
        self.carts = []
        self.pillar_t = 0.0
        self.pillar_wave = None
        self.pillar_pushed = False

        # 赐福系统
        self.boons = B.BoonState()
        self.shrines = []
        self.bolts = []                # 闪电折线 [(pts, life)]
        self.boon_offer = None         # (god, [cards], rerolled)
        self.shrine_times = [35.0, 75.0, 115.0, 155.0]   # 定时神龛

        # 连杀（暗黑式 massacre）+ 浮动文字
        self.combo = 0
        self.combo_t = 0.0
        self.combo_best = 0
        self.speed_buff_t = 0.0        # 连杀 25 档的移速 buff
        self.floaters = []             # [(text, wx, wy, life, color, size)]

        # Phase 3：敌方弹幕 / 英灵 / 机关 / 挥砍 / 龙息 / 余烬
        self.enemy_bullets = []
        self.allies = []
        self.geysers = []
        self.swings = []
        self.breaths = []
        self.embers = []               # [(x, y, vy, life)]
        self.player_aura_slow = 0.0

        # 角色（Phase 4）：血量 / 起始武器 / Q 键主动技 + meta 技能树开局生效
        cd = CHARS[self.char_key]
        self.skill_cfg = cd["skill"]
        self.skill_t = 0.0
        self.settings_idx = 0
        mb = meta.bonus_of(self.meta)
        self.player = Player(0.0, 0.0, cd["hp"] + mb["hp"])
        p = self.player
        p.dmg_bonus = mb["dmg"]
        p.cdr_bonus = mb["cdr"]
        p.speed_bonus = mb["speed"]
        p.skill_cd_bonus = mb["skill_cd"]
        p.pickup_bonus = mb["pickup"]
        p.crit_bonus = mb["crit"]
        p.xp_bonus = mb["xp"]
        self.weapons = [Weapon(cd["start_weapon"])]
        # 技能树界面状态
        self.meta_tab = "char"
        self.meta_idx = self.char_key
        self.enemies = []
        self.projectiles = []
        self.gems = []
        self.pulses = []               # [x,y,r,max_r,color,width,life]
        self.shockwaves = []
        self.boss = None

        self.hash = SpatialHash(64)
        self.particles = fx.Particles()
        self.shake = fx.CameraShake()
        self.spawner = Spawner()
        self.cam_x = 0.0
        self.cam_y = 0.0

    @property
    def theme(self):
        return MAPS[self.map_key]

    def diff(self):
        """当前难度系数（无尽模式随时间再乘爬升倍率）。"""
        d = dict(DIFFICULTIES[self.difficulty_key])
        if self.endless:
            ramp = 1.0 + ENDLESS["ramp_amount"] * int(
                self.time // ENDLESS["ramp_step"])
            d["hp"] *= ramp
            d["dmg"] *= ramp
        return d

    # ============================================================ 查询
    def nearest_enemy(self, x, y, max_d=1e9):
        best, bd = None, max_d * max_d
        for e in self.enemies:
            d = (e.x - x) ** 2 + (e.y - y) ** 2
            if d < bd:
                best, bd = e, d
        return best

    def strongest_enemy(self):
        best = None
        for e in self.enemies:
            if best is None or e.hp > best.hp:
                best = e
        return best

    def random_enemy_near(self, x, y, max_d):
        cand = [e for e in self.enemies
                if (e.x - x) ** 2 + (e.y - y) ** 2 <= max_d * max_d]
        return random.choice(cand) if cand else None

    # ============================================================ 出怪
    def spawn_enemy(self, key):
        d = self.diff()
        x, y = Spawner.ring_pos(self.player.x, self.player.y)
        e = Enemy(key, x, y, SPAWN["hp_scale"](self.time) * d["hp"])
        e.dmg *= d["dmg"]
        e.speed *= d["speed"]
        self.enemies.append(e)

    def spawn_elite(self, key):
        d = self.diff()
        x, y = Spawner.ring_pos(self.player.x, self.player.y)
        e = Enemy(key, x, y, SPAWN["hp_scale"](self.time) * d["hp"], elite=True)
        e.dmg *= d["dmg"]
        e.speed *= d["speed"]
        self.enemies.append(e)
        self.shake.add(0.25)

    def spawn_boss(self):
        d = self.diff()
        x, y = Spawner.ring_pos(self.player.x, self.player.y)
        key = self.theme["boss"]
        self.boss = Enemy(key, x, y, d["hp"], is_boss=True, boss_key=key)
        self.boss.dmg *= d["dmg"]
        self.boss.speed *= d["speed"]
        self.enemies.append(self.boss)
        self.shake.add(0.8)
        self.particles.ring(x, y, COL["boss"], n=40, speed=300, life=0.8, size=5)
        self.bus.emit("boss_spawn", dict(key=key))

    # ============================================================ 连杀（暗黑式 massacre）
    def on_kill(self, e):
        self.combo += 1
        self.combo_t = 4.0             # 击杀刷新连杀窗口
        if self.combo > self.combo_best:
            self.combo_best = self.combo
        if self.combo == 10:
            self._floater("连杀 ×10  屠戮之始", COL["gold"], 30)
        elif self.combo == 25:
            self.speed_buff_t = 5.0
            self._floater("连杀 ×25  疾行加身", COL["gold"], 34)
            self.particles.ring(self.player.x, self.player.y, COL["gold"],
                                n=14, speed=200, life=0.4, size=3)
        elif self.combo == 50:
            self._floater("连杀 ×50  尸山血海", COL["gold"], 40)
            self.shake.add(0.35)
        elif self.combo == 100:
            self._floater("连杀 ×100  诸神侧目！", COL["gold"], 46)
            self.shake.add(0.6)
            self.combo_nova()
        self.bus.emit("kill", dict(key=e.key, elite=e.elite, combo=self.combo))
        if self.combo in (10, 25, 50, 100):
            self.bus.emit("combo_tier", dict(tier=self.combo))

    def combo_nova(self):
        """百连杀：金色冲击波全场伤一波。"""
        p = self.player
        self.pulses.append([p.x, p.y, 20.0, 320.0, COL["gold"], 5, 0.55])
        self.particles.ring(p.x, p.y, COL["gold"], n=40, speed=380, life=0.7, size=5)
        dmg = 30.0 + self.combo * 0.3
        for e in self.hash.query(p.x, p.y, 330.0):
            dx, dy = e.x - p.x, e.y - p.y
            if dx * dx + dy * dy <= (320.0 + e.radius) ** 2:
                self.deal_damage(e, dmg, flat=True, proc=False)

    def _settle_combo(self):
        """连杀窗口关闭：按档位结算经验爆发（暗黑 massacre 结算）。"""
        if self.combo >= 10:
            mult = 2.0 if self.combo >= 100 else 1.5 if self.combo >= 50 else 1.0
            xp = int(self.combo * 1.5 * mult)
            self.gain_xp(xp)
            self._floater(f"连杀结算  +{xp} 经验", (150, 210, 255), 24)
            self.bus.emit("combo_settle", dict(combo=self.combo, xp=xp))
        self.combo = 0

    def _floater(self, text, color, size, wx=None, wy=None):
        if wx is None:
            wx, wy = self.player.x, self.player.y - 40.0
        self.floaters.append((text, wx, wy, 1.6, color, size))

    def _update_floaters(self, dt):
        alive = []
        for text, wx, wy, life, color, size in self.floaters:
            life -= dt
            if life > 0:
                alive.append((text, wx, wy - 46 * dt, life, color, size))
        self.floaters = alive

    # ============================================================ 伤害
    def deal_damage(self, e, dmg, flat=False, proc=True):
        """flat=True：不吃任何百分比加成（天雷/寒风/厄运爆炸等二阶伤害）。
        proc=True：可触发连锁闪电/厄运标记（防止连锁递归）。"""
        if not flat:
            dmg *= self.player.dmg_mult()               # 被动·力量
            dmg *= 1.0 + self.boons.bonus("dmg_all")    # 奥丁·符文精通
            if e.slow_t > 0:
                dmg *= 1.0 + self.boons.bonus("slow_dmg")     # 斯卡蒂·碎冰
            if e.elite or e.boss:
                dmg *= 1.0 + self.boons.bonus("elite_dmg")    # 托尔·神锤
            # 奥丁·渡鸦之眼 + meta 技能树：暴击
            if random.random() < 0.05 + self.boons.bonus("crit_chance") + self.player.crit_bonus:
                cd = 2.5 if "odin" in self.boons.favors else 2.0
                dmg *= cd
                self.particles.burst(e.x, e.y, (255, 240, 160), n=6,
                                     speed=200, life=0.3, size=4)
        e.hp -= dmg
        e.tick_flash = 0.08
        if e.b_mimic and not e.awake:      # 宝箱怪受击即惊醒
            e.awake = True
            self.bus.emit("mimic_wake", dict())
        self.total_damage += dmg
        if proc:
            # 托尔·连锁闪电
            if random.random() < self.boons.bonus("chain_chance"):
                self.chain_lightning(e, dmg)
            # 洛基·厄运标记
            if e.hp > 0 and e.doom_t <= 0 and random.random() < self.boons.bonus("doom_chance"):
                e.doom_t = 3.0
                e.doom_dmg = 12.0 + self.boons.total("loki", "doom_mark") * 40.0
        return dmg

    def chain_lightning(self, src, ref_dmg):
        """托尔连锁：从命中敌人跳到最近敌人，伤害逐跳衰减。"""
        jumps = 6 if "thor" in self.boons.favors else 3
        dmg = ref_dmg * 0.6
        cur = src
        hit = {id(src)}
        for _ in range(jumps):
            nxt, bd = None, 320.0 ** 2
            for e in self.enemies:
                if id(e) in hit or e.hp <= 0:
                    continue
                d = (e.x - cur.x) ** 2 + (e.y - cur.y) ** 2
                if d < bd:
                    nxt, bd = e, d
            if nxt is None:
                break
            hit.add(id(nxt))
            self.bolts.append((_bolt_pts(cur.x, cur.y, nxt.x, nxt.y), 0.15))
            self.deal_damage(nxt, dmg, flat=True, proc=False)
            dmg *= 0.8
            cur = nxt

    def skybolt(self, e, dmg):
        """托尔天雷：从屏幕上方劈下（视觉）+ 大环。"""
        self.deal_damage(e, dmg, flat=True, proc=False)
        self.bolts.append((_bolt_pts(e.x, e.y - 240, e.x, e.y, jag=5), 0.22))
        self.bolts.append((_bolt_pts(e.x, e.y - 200, e.x, e.y, jag=4), 0.18))
        self.pulses.append([e.x, e.y, 10.0, 70.0, (255, 224, 120), 4, 0.3])
        self.particles.burst(e.x, e.y, (255, 232, 140), n=10, speed=240, life=0.4, size=4)
        self.shake.add(0.15)

    def doom_explode(self, e):
        """洛基厄运爆炸：AOE。"""
        radius = 110.0 if "loki" in self.boons.favors else 60.0
        self.pulses.append([e.x, e.y, 10.0, radius, (255, 96, 72), 4, 0.35])
        self.particles.burst(e.x, e.y, (255, 110, 80), n=12, speed=220, life=0.4, size=4)
        for o in self.hash.query(e.x, e.y, radius):
            dx, dy = o.x - e.x, o.y - e.y
            if dx * dx + dy * dy <= (radius + o.radius) ** 2 and o is not e:
                self.deal_damage(o, e.doom_dmg, flat=True, proc=False)

    def hurt_player(self, dmg):
        """玩家受击管线：洛基闪避 -> 芙蕾雅护盾 -> HP。"""
        if self.god:
            return False
        if self.boons.try_dodge():
            self.particles.ring(self.player.x, self.player.y, (140, 235, 160),
                                n=10, speed=170, life=0.3, size=3)
            return False
        dmg = self.boons.absorb_hit(dmg)
        if dmg <= 0:
            self.particles.burst(self.player.x, self.player.y, (255, 130, 190),
                                 n=6, speed=140, life=0.3, size=3)
            return False
        if self.player.hurt(dmg):
            self.boons.bifrost_retaliate(self)     # 海姆达尔·虹桥反制
            self.bus.emit("player_hurt", dict(dmg=dmg, hp=self.player.hp))
            return True
        return False

    def cast_skill(self):
        """Q 键主动技：就绪时施放，冷却吃全局 CDR（被动+赐福）。"""
        if self.state != "play" or self.skill_t > 0:
            return
        skills.cast(self)
        self.skill_t = (self.skill_cfg["cooldown"] * self.cdr_mult()
                        * (1.0 - self.player.skill_cd_bonus))

    # ============================================================ 神龛
    def spawn_shrine(self):
        if len(self.shrines) >= 2:
            return
        god = random.choice(list(B.GODS.keys()))
        a = random.uniform(0, math.tau)
        d = random.uniform(300.0, 520.0)
        x = self.player.x + math.cos(a) * d
        y = self.player.y + math.sin(a) * d
        self.shrines.append(Shrine(x, y, god, B.GODS[god]["color"]))

    def open_boon(self, shrine):
        """生成该神的三张赐福卡（含稀有度）。"""
        cands = self.boons.candidates(shrine.god)
        random.shuffle(cands)
        cands = cands[:3]
        while len(cands) < 3:                      # 该神全满：补给卡凑数
            cands.append(None)
        cards = []
        for key in cands:
            if key is None:
                cards.append(dict(kind="heal", name="神赐面包", desc="回复 30 生命",
                                  act=("heal", None), rar=None, stacks=0))
            else:
                ri = B.roll_rarity()
                cards.append(dict(
                    kind="boon", key=key, rar=ri,
                    name=B.GODS[shrine.god]["boons"][key]["name"],
                    desc=B.boon_desc(shrine.god, key, B.RARITIES[ri]["mult"]),
                    act=("boon", key),
                    stacks=self.boons.taken.get((shrine.god, key), 0)))
        self.boon_offer = (shrine.god, cards, False)
        self.state = "boon"
        self.bus.emit("shrine_open", dict(god=shrine.god))

    def reroll_boon(self):
        if self.boon_offer is None or self.boon_offer[2]:
            return
        god = self.boon_offer[0]
        # 原地重 roll：重新挑卡 + 重掷稀有度
        cands = self.boons.candidates(god)
        random.shuffle(cands)
        cands = cands[:3]
        while len(cands) < 3:
            cands.append(None)
        cards = []
        for key in cands:
            if key is None:
                cards.append(dict(kind="heal", name="神赐面包", desc="回复 30 生命",
                                  act=("heal", None), rar=None, stacks=0))
            else:
                ri = B.roll_rarity()
                cards.append(dict(
                    kind="boon", key=key, rar=ri,
                    name=B.GODS[god]["boons"][key]["name"],
                    desc=B.boon_desc(god, key, B.RARITIES[ri]["mult"]),
                    act=("boon", key),
                    stacks=self.boons.taken.get((god, key), 0)))
        self.boon_offer = (god, cards, True)
        self.particles.ring(self.player.x, self.player.y, (190, 120, 255),
                            n=12, speed=180, life=0.4, size=3)
        self.bus.emit("boon_reroll", dict(god=god))

    def choose_boon(self, i):
        if self.boon_offer is None:
            return
        god, cards, _ = self.boon_offer
        if not (0 <= i < len(cards)):
            return
        c = cards[i]
        if c["kind"] == "boon":
            ri = c["rar"]
            stacks, first, favor_on = self.boons.add(god, c["act"][1],
                                                     B.RARITIES[ri]["mult"])
            if favor_on:
                gd = B.GODS[god]
                self.particles.ring(self.player.x, self.player.y, gd["color"],
                                    n=30, speed=300, life=0.8, size=5)
                self.shake.add(0.4)
            self.bus.emit("boon_taken", dict(god=god, key=c["act"][1],
                                             favor_on=favor_on))
        else:
            self.player.hp = min(self.player.hp_max, self.player.hp + 30)
            self.bus.emit("heal", dict(amount=30))
        self.boon_offer = None
        self.state = "play"

    # ============================================================ 冷却聚合
    def cdr_mult(self):
        m = self.player.cooldown_mult()
        m *= max(0.35, 1.0 - self.boons.bonus("cdr"))
        if "heimdall" in self.boons.favors:
            m *= 0.85
        return m

    def _kill_rewards(self, e):
        self.kills += 1
        self.on_kill(e)
        # 金币：普通敌 = 经验等量，精英/Boss 固定（Phase 6）
        gold = GOLD["elite"] if e.elite else GOLD["boss"] if e.boss else e.xp
        gold = int(gold * self.diff()["gold_mult"])
        self.run_gold += gold
        self.bus.emit("gold_gain", dict(amount=gold, total=self.run_gold))
        self._floater(f"+{gold}金", COL["gold"], 15, e.x, e.y - e.radius - 8)
        quests.on_kill(self, e)
        # 食物：精英 100% 掉，普通敌小概率
        if e.elite:
            self._spawn_food(e.x, e.y)
        elif not e.boss and random.random() < FOOD["drop_chance"]:
            self._spawn_food(e.x, e.y)
        # 宝箱怪：击杀必掉宝箱（伪装的回报）
        if e.b_mimic and len(self.chests) < 5:
            self.chests.append(Chest(e.x, e.y))
        self.particles.burst(e.x, e.y, (150, 40, 40), n=6 if not e.elite else 14,
                             speed=150, life=0.4, size=4)
        if len(self.gems) >= XP["gem_cap"]:
            self.gems[0].xp += e.xp      # 超上限：并入最老的宝石
        else:
            self.gems.append(Gem(e.x, e.y, e.xp))
        # 洛基·嬉笑杀戮：概率散落额外宝石
        if random.random() < self.boons.bonus("gem_burst"):
            for _ in range(3):
                if len(self.gems) < XP["gem_cap"]:
                    self.gems.append(Gem(e.x + random.uniform(-24, 24),
                                         e.y + random.uniform(-24, 24), 1))
        if e.boss:
            if self.endless:
                # 无尽模式：继续战斗，60s 后下一只 Boss，难度每 5 分钟爬升
                self.spawner.boss_sent = False
                self.next_boss_at = self.time + ENDLESS["boss_respawn"]
                self._floater("巨人陨落！下一波 60s 后", COL["gold"], 26)
                self.bus.emit("boss_kill", dict(key=e.key, endless=True))
            else:
                self.victory = True
                self.state = "gameover"
                self.shake.add(1.0)
                self.particles.ring(e.x, e.y, COL["gold"], n=60, speed=380, life=1.2, size=6)
                self.bus.emit("boss_kill", dict(key=e.key))
                self.bus.emit("game_over", dict(victory=True))
        elif e.elite:
            self.shake.add(0.3)
            self.bus.emit("elite_kill", dict(key=e.key))
            if len(self.chests) < 5:       # 精英必掉宝箱（Phase 5）
                self.chests.append(Chest(e.x + 28, e.y))
            if len(self.shrines) < 2:      # 精英必掉神龛
                self.shrines.append(Shrine(e.x, e.y,
                                           random.choice(list(B.GODS.keys())),
                                           COL["gold"]))

    def _spawn_food(self, x, y):
        """食物掉落（带上限与随机偏移）。"""
        if len(self.foods) >= FOOD["cap"]:
            self.foods.pop(0)
        self.foods.append(Food(x + random.uniform(-14, 14),
                               y + random.uniform(-14, 14), FOOD["lifetime"]))

    def settle_run(self):
        """结算本局：金币/统计/最佳记录合并进本地存档（每局结束只跑一次）。"""
        if self._settled:
            return
        self._settled = True
        sd = self.meta
        sd.gold += self.run_gold
        sd.stats.runs += 1
        if self.victory:
            sd.stats.wins += 1
        sd.stats.total_kills += self.kills
        sd.stats.total_damage += int(self.total_damage)
        br = sd.best_run
        if (self.level, self.kills) > (br.level, br.kills):
            br.level, br.kills, br.time = self.level, self.kills, self.time
        save.save_data(sd)
        self.bus.emit("run_settled", dict(gold=sd.gold, victory=self.victory))

    # ============================================================ 经验
    def gain_xp(self, n):
        n = int(n * self.diff()["xp_mult"])                # 难度经验倍率
        n = int(n * (1.0 + self.boons.bonus("xp_gain")))   # 奥丁·贤者之血
        n = int(n * (1.0 + self.player.xp_bonus))          # meta 技能树
        self.xp += n
        while self.xp >= self.xp_need:
            self.xp -= self.xp_need
            self.level += 1
            self.pending_cards += 1
            self.bus.emit("level_up", dict(level=self.level))
        if self.pending_cards > 0 and self.state == "play":
            self.open_cards()

    @property
    def xp_need(self):
        return XP["need"](self.level)

    def open_cards(self):
        self.cards = self.gen_cards()
        self.hover_idx = -1
        self.state = "upgrade"

    # ============================================================ 卡池
    def gen_cards(self):
        cards = []
        owned = {w.key for w in self.weapons}
        # 进化卡（金色，最优先出现）
        for w in self.weapons:
            evo = EVOLUTIONS.get(w.key)
            if (evo and not w.evolved and w.level >= WEAPON_MAX_LEVEL
                    and self.player.passives[evo["passive"]] >= evo["min_level"]):
                cards.append(dict(kind="evo", id=f"evo:{w.key}", tag="进化",
                                  name=f"{w.d['name']} → {evo['name']}",
                                  desc=evo["desc"], act=("evo", w.key)))
        if len(self.weapons) < MAX_WEAPONS:
            for key, d in WEAPONS.items():
                if key in owned:
                    continue
                mo = d.get("map_only")
                if mo and mo != self.map_key:      # 地图限定武器只在对应图出现
                    continue
                cards.append(dict(kind="new", id=f"new:{key}", tag="新武器",
                                  name=d["name"], desc=d["desc"],
                                  act=("new", key)))
        for w in self.weapons:
            if w.can_upgrade():
                nxt = w.d["levels"][w.level]
                delta = " ".join(
                    f"{FIELD_CN.get(k, k)}{'+' if v > 0 else ''}{v:g}"
                    for k, v in nxt.items())
                cards.append(dict(kind="up", id=f"up:{w.key}", tag="强化",
                                  name=f"{w.display_name} {w.level}→{w.level + 1}",
                                  desc=delta or "全面微调",
                                  act=("up", w.key)))
        for k, d in PASSIVES.items():
            if self.player.passives[k] < d["max"]:
                cards.append(dict(kind="pas", id=f"pas:{k}", tag="被动",
                                  name=d["name"],
                                  desc=f"{d['desc']}（{self.player.passives[k]}/{d['max']}）",
                                  act=("pas", k)))
        # 本局已放逐的卡不再出现（Phase 5）
        cards = [c for c in cards if c["id"] not in self.banished_ids]
        random.shuffle(cards)
        cards = cards[:3]
        while len(cards) < 3:
            fb = FALLBACK_CARDS[len(cards) % len(FALLBACK_CARDS)]
            cards.append(dict(kind=fb["kind"], id=f"fb:{fb['kind']}", tag="补给",
                              name=fb["name"], desc=fb["desc"],
                              act=(fb["kind"], None)))
        return cards

    def choose_card(self, i):
        if not (0 <= i < len(self.cards)):
            return
        c = self.cards[i]
        kind, key = c["act"]
        if kind == "new":
            self.weapons.append(Weapon(key))
            self.bus.emit("weapon_new", dict(key=key))
        elif kind == "evo":
            for w in self.weapons:
                if w.key == key:
                    w.evolved = True
                    self.shake.add(0.35)
                    self.particles.ring(self.player.x, self.player.y, COL["gold"],
                                        n=26, speed=280, life=0.7, size=5)
                    self.bus.emit("weapon_evo", dict(key=key))
                    break
        elif kind == "up":
            for w in self.weapons:
                if w.key == key:
                    w.upgrade()
                    break
        elif kind == "pas":
            self.player.add_passive(key)
            self.bus.emit("passive_gain", dict(key=key,
                                               stacks=self.player.passives[key]))
        elif kind == "heal":
            self.player.hp = min(self.player.hp_max, self.player.hp + 40)
            self.bus.emit("heal", dict(amount=40))
        elif kind == "xp":
            self.gain_xp(50)
        self.chosen[c["id"]] = self.chosen.get(c["id"], 0) + 1
        self.pending_cards -= 1
        self.particles.ring(self.player.x, self.player.y, COL["gold"],
                            n=18, speed=220, life=0.5)
        if self.pending_cards > 0:
            self.open_cards()
        else:
            self.state = "play"

    def reroll_upgrade(self):
        """升级三选一重掷（消耗 1 次，宝箱可补充）。"""
        if self.state != "upgrade" or self.rerolls <= 0:
            return
        self.rerolls -= 1
        self.cards = self.gen_cards()
        self.bus.emit("upgrade_reroll", dict())

    def banish_upgrade(self):
        """放逐当前三张卡：本局不再出现（消耗 1 次）。"""
        if self.state != "upgrade" or self.banishes <= 0:
            return
        self.banishes -= 1
        for c in self.cards:
            if not c["id"].startswith("fb:"):
                self.banished_ids.add(c["id"])
        self.cards = self.gen_cards()
        self.bus.emit("upgrade_banish", dict())

    # ============================================================ 宝箱（Phase 5）
    def open_chest(self):
        p = self.player
        for c in self.chests:
            if not c.opened and (c.x - p.x) ** 2 + (c.y - p.y) ** 2 <= 64.0 ** 2:
                pool = random.sample(CHEST_POOL, 3)
                self.chest_offer = (c, [dict(kind=k, name=n, desc=d)
                                        for k, n, d in pool])
                self.state = "chest"
                self.bus.emit("chest_open", dict())
                return

    def choose_chest(self, i):
        if self.chest_offer is None:
            return
        c, cards = self.chest_offer
        if not (0 <= i < len(cards)):
            return
        k = cards[i]["kind"]
        if k == "gold":
            self.run_gold += CHEST["gold"]
            self._floater(f"+{CHEST['gold']}金", COL["gold"], 22)
        elif k == "reroll":
            self.rerolls += 1
            self._floater("重掷 +1", (150, 210, 255), 18)
        elif k == "banish":
            self.banishes += 1
            self._floater("放逐 +1", (190, 120, 255), 18)
        elif k == "food":
            for _ in range(CHEST["food_count"]):
                self._spawn_food(self.player.x + random.uniform(-60, 60),
                                 self.player.y + random.uniform(-60, 60))
        elif k == "shrine":
            self.spawn_shrine()
        elif k == "heal":
            self.player.hp = min(self.player.hp_max,
                                 self.player.hp + CHEST["heal"])
            self._floater(f"+{CHEST['heal']}", (255, 130, 160), 20)
        c.opened = True
        self.chest_offer = None
        self.state = "play"
        self.bus.emit("chest_loot", dict(kind=k))

    # ============================================================ 更新
    def update(self, dt, ix, iy):
        p = self.player
        self.time += dt
        # 连杀窗口 + 疾行 buff
        if self.combo_t > 0:
            self.combo_t -= dt
            if self.combo_t <= 0:
                self._settle_combo()
        if self.speed_buff_t > 0:
            self.speed_buff_t -= dt
        if self.skill_t > 0:
            self.skill_t -= dt
        speed_mult = (1.0 + self.boons.bonus("speed")) * \
            (1.2 if self.speed_buff_t > 0 else 1.0)
        p.move(ix, iy, dt, speed_mult)
        p.update(dt)
        self._update_floaters(dt)

        # 赐福周期效果（治疗/护盾/天雷/寒风）
        self.boons.tick(self, dt)

        # 局内任务（Phase 5）
        quests.tick(self, dt)

        # 地图机关（Phase 7：矿车/神柱）
        hazards.tick(self, dt)

        # 空间哈希重建（敌人）
        self.hash.clear()
        self.hash.insert_many(self.enemies)

        # 武器
        for w in self.weapons:
            w.update(self, dt)

        # 弹体
        alive = []
        for b in self.projectiles:
            if isinstance(b, HomingBullet):
                b.update(dt, self)
            else:
                b.update(dt)
            if b.dead():
                continue
            # 碰撞：查邻域敌人
            for e in self.hash.query(b.x, b.y, b.size + 34):
                if id(e) in b.hit or e.hp <= 0:
                    continue
                dx, dy = e.x - b.x, e.y - b.y
                if dx * dx + dy * dy <= (b.size + e.radius) ** 2:
                    b.hit.add(id(e))
                    self.deal_damage(e, b.damage)
                    self.particles.burst(b.x, b.y, (230, 220, 200), n=3,
                                         speed=110, life=0.22, size=3)
                    if getattr(b, "slow_amt", 0):      # 寒冬之弓：命中减速
                        e.apply_slow(b.slow_amt, b.slow_dur)
                    if getattr(b, "lifesteal", 0):    # 进化渡鸦/镰刀吸血
                        p.hp = min(p.hp_max, p.hp + b.lifesteal)
                    if getattr(b, "boom_radius", 0):   # 炸药桶：命中引爆
                        self._boom_explode(b.x, b.y, b.damage, b.boom_radius)
                        b.pierce = 0
                        break
                    b.pierce -= 1
                    if b.pierce <= 0:
                        break
            if not b.dead():
                alive.append(b)
        self.projectiles = alive

        # 敌人（含新行为 AI：远程/自爆/治疗/光环/吸血）
        self.player_aura_slow = 0.0
        for e in self.enemies:
            e.update(self, dt)
        if self.player_aura_slow > 0:      # 寒冰巨蛇光环减速玩家
            p.slow_amt = max(p.slow_amt, self.player_aura_slow)
            p.slow_t = max(p.slow_t, 0.25)
        self.separate_enemies()

        # 自爆尸鬼：引信到点爆炸（对敌我通伤）
        for e in self.enemies[:]:
            if e.b_bomber and e.fuse_t == 0.0 and e.hp > 0:
                self.enemies.remove(e)
                self._bomber_explode(e)

        # 敌方弹幕（哥布林箭/巨蟒水刃）
        alive_b = []
        for eb in self.enemy_bullets:
            if eb.update(dt):
                d2 = (eb.x - p.x) ** 2 + (eb.y - p.y) ** 2
                if d2 <= (eb.size + p.radius) ** 2:
                    if self.hurt_player(eb.dmg):
                        self.hurt_flash = 0.3
                        self.particles.burst(eb.x, eb.y, (255, 120, 90), n=5,
                                             speed=130, life=0.25, size=3)
                    continue
                alive_b.append(eb)
        self.enemy_bullets = alive_b

        # 英灵战士（维京号角）
        self.allies = [a for a in self.allies if a.update(self, dt)]

        # 熔岩喷泉（机关）
        if self.theme["geyser"]:
            for g in self.geysers:
                g.update(self, dt)
            self._recycle_geysers()

        # 龙息扇形（尼德霍格）
        self.breaths = [bz for bz in self.breaths if bz.update(self, dt)]

        # 厄运倒计时（洛基）
        for e in self.enemies:
            if e.doom_t > 0:
                e.doom_t -= dt
                if e.doom_t <= 0 and e.hp > 0:
                    self.doom_explode(e)

        # 敌人咬人（吸血鬼：伤害转自身回血）
        for e in self.hash.query(p.x, p.y, 40):
            dx, dy = e.x - p.x, e.y - p.y
            rr = e.radius + p.radius
            if dx * dx + dy * dy <= rr * rr and self.hurt_player(e.dmg):
                self.hurt_flash = 0.35
                self.shake.add(0.22)
                self.particles.burst(p.x, p.y, (220, 60, 60), n=8,
                                     speed=170, life=0.3, size=4)
                if e.b_vamp:
                    e.hp = min(e.hp_max, e.hp + e.dmg * e.b_vamp["lifesteal"])

        # 掉队敌人传送回场（保持尸潮压力）
        for e in self.enemies:
            if math.hypot(e.x - p.x, e.y - p.y) > 2200.0:
                nx, ny = Spawner.ring_pos(p.x, p.y)
                e.x, e.y = nx, ny

        # 死亡结算（单次；自爆尸鬼死亡也炸）
        dead = [e for e in self.enemies if e.hp <= 0]
        if dead:
            self.enemies = [e for e in self.enemies if e.hp > 0]
            for e in dead:
                self._kill_rewards(e)
                if e is self.boss:
                    self.boss = None
                elif e.b_bomber:
                    self._bomber_explode(e)

        # Boss 技能（按 pattern dispatch）
        BOSSAI.update_boss(self, dt)

        # 冲击波
        self.shockwaves = [sw for sw in self.shockwaves if not sw.update(dt)]
        for sw in self.shockwaves:
            if sw.hits(p.x, p.y, p.radius) and self.hurt_player(sw.dmg):
                sw.hit = True
                self.hurt_flash = 0.4
                self.shake.add(0.35)

        # 神龛：定时刷新 + 触碰
        while self.shrine_times and self.time >= self.shrine_times[0]:
            self.shrine_times.pop(0)
            self.spawn_shrine()
        for s in self.shrines[:]:
            if (s.x - p.x) ** 2 + (s.y - p.y) ** 2 <= 46 ** 2:
                self.shrines.remove(s)
                self.particles.ring(s.x, s.y, s.color, n=22, speed=240,
                                    life=0.6, size=4)
                self.open_boon(s)
                break

        # 宝石（拾取范围吃赐福加成）
        mag = p.pickup_radius() * (1.0 + self.boons.bonus("pickup"))
        for g in self.gems:
            g.update(dt, p.x, p.y, mag)
        taken = [g for g in self.gems
                 if (g.x - p.x) ** 2 + (g.y - p.y) ** 2 <= (p.radius + 10) ** 2]
        if taken:
            self.gems = [g for g in self.gems if g not in taken]
            total_xp = sum(g.xp for g in taken)
            for g in taken:
                self.gain_xp(g.xp)
            self.bus.emit("gem_pickup", dict(xp=total_xp, n=len(taken)))
            quests.on_gems(self, len(taken))
            self.particles.burst(p.x, p.y, COL["xp_bar"], n=5,
                                 speed=90, life=0.25, size=3)

        # 食物拾取（Phase 5）：回血 30，过期消失
        for f in self.foods[:]:
            f.life -= dt
            if (f.x - p.x) ** 2 + (f.y - p.y) ** 2 <= (p.radius + 14) ** 2:
                self.foods.remove(f)
                p.hp = min(p.hp_max, p.hp + FOOD["heal"])
                self._floater(f"+{FOOD['heal']}", (255, 130, 160), 18,
                              p.x, p.y - 34)
                self.bus.emit("food_eat", dict(heal=FOOD["heal"]))
            elif f.life <= 0:
                self.foods.remove(f)

        # 视效
        self.pulses = [pl for pl in self.pulses if self._update_pulse(pl, dt)]
        self.bolts = [(pts, life - dt) for pts, life in self.bolts if life > dt]
        self.swings = [sw for sw in self.swings if sw.update(dt)]
        self.particles.update(dt)
        self.shake.update(dt)
        if self.hurt_flash > 0:
            self.hurt_flash -= dt
        # 熔岩图余烬氛围
        if self.theme["embers"]:
            self._update_embers(dt)

        # 出怪（Boss 战期间小怪照常施压，难度曲线已封顶）
        self.spawner.update(self, dt)

        # 摄像机
        self.cam_x += (p.x - self.cam_x) * min(1.0, CAM_LERP * dt)
        self.cam_y += (p.y - self.cam_y) * min(1.0, CAM_LERP * dt)

        # 死亡
        if p.hp <= 0:
            self.state = "gameover"
            self.victory = False
            self.bus.emit("player_death", dict())
            self.bus.emit("game_over", dict(victory=False))

    def _update_pulse(self, pl, dt):
        pl[2] += (pl[3] - pl[2]) * min(1.0, 9.0 * dt)
        pl[6] -= dt
        return pl[6] > 0

    def _boom_explode(self, x, y, dmg, radius):
        """炸药桶 AOE：对范围内敌人通伤（不吃玩家加成，防连锁）。"""
        self.pulses.append([x, y, 12.0, radius, (255, 150, 60), 5, 0.4])
        self.particles.burst(x, y, (255, 160, 70), n=16, speed=280,
                             life=0.45, size=4)
        self.shake.add(0.25)
        for e in self.enemies:
            if math.hypot(e.x - x, e.y - y) <= radius + e.radius:
                self.deal_damage(e, dmg, flat=True, proc=False)

    def _bomber_explode(self, e):
        """自爆尸鬼爆炸：敌我通伤。"""
        cfg = e.b_bomber
        r = cfg["radius"]
        self.pulses.append([e.x, e.y, 10.0, r, (255, 140, 60), 4, 0.35])
        self.particles.burst(e.x, e.y, (255, 140, 60), n=14, speed=260,
                             life=0.45, size=4)
        self.shake.add(0.18)
        p = self.player
        if math.hypot(p.x - e.x, p.y - e.y) <= r + p.radius:
            if self.hurt_player(cfg["dmg"]):
                self.hurt_flash = 0.35
        for o in self.hash.query(e.x, e.y, r):
            if o is not e and math.hypot(o.x - e.x, o.y - e.y) <= r + o.radius:
                self.deal_damage(o, cfg["dmg"], flat=True, proc=False)

    def _recycle_geysers(self):
        """喷泉维持数量 + 离玩家太远的重定位。"""
        p = self.player
        while len(self.geysers) < PHASE3["geyser_count"]:
            a = random.uniform(0, math.tau)
            d = random.uniform(420.0, 760.0)
            self.geysers.append(Geyser(p.x + math.cos(a) * d,
                                       p.y + math.sin(a) * d))
        for g in self.geysers:
            if math.hypot(g.x - p.x, g.y - p.y) > 1500.0:
                a = random.uniform(0, math.tau)
                d = random.uniform(420.0, 760.0)
                g.x = p.x + math.cos(a) * d
                g.y = p.y + math.sin(a) * d
                g.t = random.uniform(0.0, PHASE3["geyser_cycle"])

    def _update_embers(self, dt):
        """熔岩图余烬：缓缓上飘的橙色光点。"""
        cap = PHASE3["ember_cap"]
        if len(self.embers) < cap and random.random() < 0.5:
            self.embers.append((self.cam_x + random.uniform(-80, WIDTH + 80),
                                self.cam_y + HEIGHT + 20,
                                random.uniform(-14, 14),
                                random.uniform(2.4, 4.5)))
        alive = []
        for x, y, vx, life in self.embers:
            y -= 36 * dt
            x += vx * dt
            life -= dt
            if life > 0:
                alive.append((x, y, vx, life))
        self.embers = alive

    def separate_enemies(self):
        """同桶两两推开，尸潮有堆积感不叠成一坨。"""
        for a, b in self.hash.query_pairs_cellwise():
            dx, dy = b.x - a.x, b.y - a.y
            rr = a.radius + b.radius
            d2 = dx * dx + dy * dy
            if 0 < d2 < rr * rr:
                d = math.sqrt(d2)
                push = (rr - d) * 0.5 * 0.6
                nx, ny = dx / d, dy / d
                a.x -= nx * push
                a.y -= ny * push
                b.x += nx * push
                b.y += ny * push

    # ============================================================ 绘制
    def draw_world(self, surf):
        w, h = surf.get_size()
        ox, oy = self.shake.offset()
        cx = self.cam_x - w / 2 + ox
        cy = self.cam_y - h / 2 + oy

        # 地面
        self._draw_ground(surf, cx, cy, w, h)

        # 装饰
        self._draw_decor(surf, cx, cy, w, h)

        # 地图机关（Phase 7：矿车/神柱脉冲）
        hazards.draw(self, surf, cx, cy)

        # 喷泉机关（熔岩图）
        if self.theme["geyser"]:
            for g in self.geysers:
                g.draw(surf, cx, cy)

        # 守点任务标记（Phase 5）
        if self.quest is not None and self.quest["kind"] == "hold":
            hx, hy = self.quest_hold
            sx, sy = int(hx - cx), int(hy - cy)
            pygame.draw.circle(surf, COL["gold"], (sx, sy), 130, 2)
            pygame.draw.circle(surf, COL["gold"], (sx, sy), 6)

        # 食物 / 宝箱（Phase 5）
        for f in self.foods:
            f.draw(surf, cx, cy)
        for c in self.chests:
            c.draw(surf, cx, cy)

        # 宝石
        for g in self.gems:
            g.draw(surf, cx, cy)

        # 神龛
        ticks = pygame.time.get_ticks()
        for s in self.shrines:
            s.draw(surf, cx, cy, ticks)

        # 英灵战士（维京号角）
        for a in self.allies:
            a.draw(surf, cx, cy)

        # 敌人（Boss 最后画，压在最上）
        for e in self.enemies:
            if not e.boss:
                e.draw(surf, cx, cy)

        # 玩家（+护盾光环）
        self.player.draw(surf, cx, cy)
        if self.boons.shield > 0:
            r = self.player.radius + 8 + 2 * math.sin(ticks * 0.004)
            pygame.draw.circle(surf, (255, 130, 190),
                               (int(self.player.x - cx), int(self.player.y - cy)),
                               int(r), 2)

        # 环绕型武器（雷锤/镰刀）统一自绘
        t = pygame.time.get_ticks() * 0.001
        for wp in self.weapons:
            wp.draw(surf, self, cx, cy, w, h, t)

        # 弹体 + 敌方弹幕
        for b in self.projectiles:
            b.draw(surf, cx, cy, w, h)
        for eb in self.enemy_bullets:
            eb.draw(surf, cx, cy)

        # Boss
        if self.boss is not None:
            self.boss.draw(surf, cx, cy)

        # 冲击波 / 脉冲 / 龙息 / 挥砍
        for sw in self.shockwaves:
            sw.draw(surf, cx, cy, w, h)
        for x, y, r, mr, color, bw, life in self.pulses:
            k = max(0.0, min(1.0, life / 0.38))
            pygame.draw.circle(surf, color, (int(x - cx), int(y - cy)), int(r), max(1, int(bw * k)))
        for bz in self.breaths:
            bz.draw(surf, cx, cy)
        for sw in self.swings:
            sw.draw(surf, cx, cy)

        # 闪电折线（托尔连锁/天雷）
        for pts, life in self.bolts:
            a = max(0, min(255, int(life / 0.15 * 255)))
            draw_pts = [(x - cx, y - cy) for x, y in pts]
            if len(draw_pts) >= 2:
                pygame.draw.lines(surf, (255, 244, 170), False, draw_pts, 3)
                pygame.draw.lines(surf, (255, 255, 230), False, draw_pts, 1)

        # 浮动文字（连杀档位/结算）
        for text, wx, wy, life, color, size in self.floaters:
            k = life / 1.6
            surf_w, surf_h = surf.get_size()
            sx = int(wx - cx)
            sy = int(wy - cy)
            if -100 <= sx <= surf_w + 100 and -60 <= sy <= surf_h + 60:
                img = ui.font(int(size * (0.8 + 0.2 * min(1.0, (1.6 - life) * 5))),
                              bold=True).render(text, True, color)
                img.set_alpha(int(255 * min(1.0, k * 1.6)))
                surf.blit(img, (sx - img.get_width() // 2, sy))

        # 粒子 + 余烬（熔岩图氛围）
        self.particles.draw(surf, cx, cy, w, h)
        if self.theme["embers"]:
            for ex, ey, vx, life in self.embers:
                k = max(0.0, min(1.0, life))
                r = max(1, int(2.5 * k))
                pygame.draw.circle(surf, (255, 150, 60),
                                   (int(ex - cx), int(ey - cy)), r)

        # 受伤红闪
        if self.hurt_flash > 0:
            k = self.hurt_flash / 0.4
            v = pygame.Surface((w, h), pygame.SRCALPHA)
            v.fill((180, 30, 30, int(70 * k)))
            surf.blit(v, (0, 0))

    def _draw_ground(self, surf, cx, cy, w, h):
        ground = _GROUNDS.get(self.map_key) or _GROUNDS["snow"]
        tile = ground.get_width()
        x0 = int(cx // tile) * tile
        y0 = int(cy // tile) * tile
        for ty in range(y0 - tile, int(cy + h) + tile, tile):
            for tx in range(x0 - tile, int(cx + w) + tile, tile):
                surf.blit(ground, (tx - int(cx), ty - int(cy)))

    def _draw_decor(self, surf, cx, cy, w, h):
        cell = 520
        kinds = self.theme["decor"]
        gx0 = int((cx - 60) // cell)
        gx1 = int((cx + w + 60) // cell)
        gy0 = int((cy - 60) // cell)
        gy1 = int((cy + h + 60) // cell)
        for gx in range(gx0, gx1 + 1):
            for gy in range(gy0, gy1 + 1):
                for x, y, kind, rot, scale in fx.decorations_for_chunk(gx, gy, cell, kinds):
                    spr = _DECOR.get(kind)
                    if spr:
                        surf.blit(spr, (int(x - cx - spr.get_width() // 2),
                                        int(y - cy - spr.get_height() // 2)))


# ---------------------------------------------------------------- 全局精灵
_GROUNDS = {}          # map_key -> 主题地砖
_DECOR = {}
_ALL_DECOR_KINDS = ("rune", "bone", "bones", "snow", "rock", "lava", "charcoal")


def init_globals():
    init_sprites()
    init_gem_sprites()
    if not _GROUNDS:
        for mk, th in MAPS.items():
            theme = dict(ground=th["ground"], line=th["line"],
                         lava=bool(th.get("geyser")))
            _GROUNDS[mk] = fx.bake_ground_tile(theme)
    if not _DECOR:
        for k in _ALL_DECOR_KINDS:
            _DECOR[k] = fx.bake_decoration(k)


# ---------------------------------------------------------------- 主循环
def run():
    pygame.init()
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("JOTUNNSLAYER 复刻原型 · Python/pygame-ce")
    clock = pygame.time.Clock()
    init_globals()

    game = Game(smoke=SMOKE, map_key=MAP_ARG)
    if DIFF_ARG in DIFFICULTIES:
        game.difficulty_key = DIFF_ARG
    if ENDLESS_ARG:
        game.endless = True

    # 程序化音频：合成音效 + BGM（无音频设备时整局静默降级）
    audio.init(game.meta.settings)
    audio.attach(game.bus)

    accum = 0.0
    bot_t = 0.0
    sim_total = 0.0     # smoke：跨重开累计的实际游玩时长（game.time 会随 reset 归零）
    deaths = 0
    wins = 0
    god = SMOKE and "--god" in sys.argv   # 无敌：无头验证后期/Boss 路径用

    while True:
        # ---------------- 输入 ----------------
        ix = iy = 0
        events = pygame.event.get()
        for ev in events:
            if ev.type == pygame.QUIT:
                pygame.quit()
                return 0
            if ev.type == pygame.KEYDOWN:
                if game.state == "title":
                    if ev.key == pygame.K_1:
                        game.state = "charsel"
                    elif ev.key == pygame.K_2:
                        game.state = "stats"
                    elif ev.key == pygame.K_3:
                        game.state = "settings"
                    elif ev.key == pygame.K_4:
                        game.state = "metatree"
                    elif ev.key == pygame.K_ESCAPE:
                        pygame.quit()
                        return 0
                elif game.state == "charsel":
                    if ev.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                        game.char_key = ("berserker", "seeress", "warden")[ev.key - pygame.K_1]
                        game.state = "mapsel"
                    elif ev.key == pygame.K_ESCAPE:
                        game.state = "title"
                elif game.state == "mapsel":
                    if ev.key == pygame.K_1:
                        game.map_key = "snow"
                    elif ev.key == pygame.K_2:
                        game.map_key = "lava"
                    elif ev.key == pygame.K_3:
                        game.map_key = "mine"
                    elif ev.key == pygame.K_4:
                        game.map_key = "temple"
                    elif ev.key == pygame.K_5:
                        game.map_key = "hel"
                    elif ev.key in (pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_9):
                        game.difficulty_key = ("easy", "normal", "hard",
                                               "insane")[ev.key - pygame.K_6]
                    elif ev.key == pygame.K_0:
                        game.endless = not game.endless
                    elif ev.key in (pygame.K_SPACE, pygame.K_RETURN):
                        game.reset()
                        game.state = "play"
                    elif ev.key == pygame.K_ESCAPE:
                        game.state = "charsel"
                elif game.state == "settings":
                    if ev.key == pygame.K_ESCAPE:
                        game.state = "title"
                    elif ev.key in (pygame.K_UP, pygame.K_DOWN):
                        game.settings_idx = 1 - game.settings_idx
                    elif ev.key in (pygame.K_LEFT, pygame.K_RIGHT):
                        k = ("sfx_vol", "music_vol")[game.settings_idx]
                        d = 0.1 if ev.key == pygame.K_RIGHT else -0.1
                        v = round(min(1.0, max(0.0, game.meta.settings[k] + d)), 2)
                        game.meta.settings[k] = v
                        save.save_data(game.meta)
                        audio.set_volumes(sfx=game.meta.settings["sfx_vol"],
                                          music=game.meta.settings["music_vol"])
                elif game.state == "stats":
                    if ev.key == pygame.K_ESCAPE:
                        game.state = "title"
                elif game.state == "metatree":
                    if ev.key == pygame.K_ESCAPE:
                        game.state = "title"
                    elif ev.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                        game.meta_tab = "char"
                        game.meta_idx = ("berserker", "seeress", "warden")[ev.key - pygame.K_1]
                    elif ev.key in (pygame.K_4, pygame.K_5, pygame.K_6,
                                    pygame.K_7, pygame.K_8, pygame.K_9):
                        game.meta_tab = "god"
                        game.meta_idx = list(B.GODS.keys())[ev.key - pygame.K_4]
                elif game.state == "play":
                    if ev.key == pygame.K_ESCAPE:
                        game.state = "pause"
                    elif ev.key == pygame.K_TAB:
                        game.state = "tree"
                    elif ev.key == pygame.K_q:
                        game.cast_skill()
                    elif ev.key == pygame.K_e:
                        game.open_chest()
                elif game.state == "tree":
                    if ev.key in (pygame.K_TAB, pygame.K_ESCAPE):
                        game.state = "play"
                elif game.state == "pause":
                    if ev.key == pygame.K_ESCAPE:
                        game.state = "play"
                    elif ev.key == pygame.K_r:
                        game.reset()
                        game.state = "play"
                elif game.state == "upgrade":
                    if ev.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                        game.choose_card(ev.key - pygame.K_1)
                    elif ev.key == pygame.K_r:
                        game.reroll_upgrade()
                    elif ev.key == pygame.K_b:
                        game.banish_upgrade()
                elif game.state == "boon":
                    if ev.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                        game.choose_boon(ev.key - pygame.K_1)
                    elif ev.key == pygame.K_r:
                        game.reroll_boon()
                elif game.state == "chest":
                    if ev.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                        game.choose_chest(ev.key - pygame.K_1)
                    elif ev.key == pygame.K_ESCAPE:
                        game.chest_offer = None
                        game.state = "play"
                elif game.state == "gameover":
                    if ev.key == pygame.K_r:
                        game.reset()
                        game.state = "play"
                    elif ev.key == pygame.K_ESCAPE:
                        pygame.quit()
                        return 0
            if (ev.type == pygame.MOUSEBUTTONDOWN and game.state == "upgrade"
                    and ev.button == 1):
                for i, r in enumerate(ui.card_rects(len(game.cards))):
                    if r.collidepoint(ev.pos):
                        game.choose_card(i)
                        break
            if (ev.type == pygame.MOUSEBUTTONDOWN and game.state == "boon"
                    and ev.button == 1 and game.boon_offer is not None):
                for i, r in enumerate(ui.card_rects(3)):
                    if r.collidepoint(ev.pos):
                        game.choose_boon(i)
                        break
            if (ev.type == pygame.MOUSEBUTTONDOWN and game.state == "metatree"
                    and ev.button == 1):
                n_nodes = (len(meta.CHAR_NODES) if game.meta_tab == "char"
                           else len(meta.GOD_NODES[game.meta_idx]))
                for i, r in enumerate(ui.metatree_node_rects()[:n_nodes]):
                    if r.collidepoint(ev.pos):
                        if meta.buy(game.meta, game.meta_tab, game.meta_idx, i):
                            save.save_data(game.meta)
                            audio.play("gold")
                            game.bus.emit("meta_buy", dict())
                        break

        if game.state in ("play", "upgrade", "boon", "tree", "pause", "gameover"):
            keys = pygame.key.get_pressed()
            ix = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
            iy = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])

        # smoke 机器人：残血逃命 / 优先找神龛 / 顺路捡宝石 / 兜圈游走；死亡自动重开
        if SMOKE:
            bot_t += DT
            if game.state in ("title", "charsel", "mapsel", "stats", "settings", "metatree"):
                game.char_key = DEFAULT_CHAR
                game.reset()
                game.state = "play"
            if game.state == "upgrade":
                game.choose_card(0)
            if game.state == "boon":
                if game.boon_offer is not None and not game.boon_offer[2]:
                    game.reroll_boon()      # 顺带验证重掷路径
                else:
                    game.choose_boon(0)
            if game.state == "chest":
                game.choose_chest(0)
            if game.state == "gameover":
                if game.victory:
                    wins += 1
                deaths += 1
                game.reset()
                game.state = "play"
            p = game.player
            game.god = god
            # 星图渲染冒烟：第 20s 和第 100s 各打开一小会
            if game.state == "play" and (19.9 < bot_t < 20.1 or 99.9 < bot_t < 100.1):
                game.state = "tree"
            if game.state == "tree" and (bot_t >= 20.4 or bot_t >= 100.4):
                game.state = "play"
            ix, iy = int(round(math.cos(bot_t * 0.7))), int(round(math.sin(bot_t * 0.7)))
            if p.hp < p.hp_max * 0.4:
                e = game.nearest_enemy(p.x, p.y, 600.0)
                if e is not None:
                    dx, dy = p.x - e.x, p.y - e.y
                    m = math.hypot(dx, dy) or 1.0
                    ix, iy = int(round(dx / m)), int(round(dy / m))
            else:
                target = None
                bd = 999999999.0
                for s in game.shrines:      # 神龛最优先
                    d = (s.x - p.x) ** 2 + (s.y - p.y) ** 2
                    if d < bd:
                        target, bd = s, d
                if target is None:
                    for g in game.gems:
                        d = (g.x - p.x) ** 2 + (g.y - p.y) ** 2
                        if d < bd:
                            target, bd = g, d
                if target is not None and bd <= 700.0 ** 2:
                    dx, dy = target.x - p.x, target.y - p.y
                    m = math.hypot(dx, dy) or 1.0
                    ix, iy = int(round(dx / m)), int(round(dy / m))

        # ---------------- 逻辑（固定步长） ----------------
        frame_t = clock.tick(FPS) / 1000.0 if not SMOKE else DT
        accum += min(frame_t, MAX_FRAME)
        steps = 0
        while accum >= DT and steps < 6:
            if game.state == "play":
                game.update(DT, ix, iy)
                if SMOKE:
                    sim_total += DT
            accum -= DT
            steps += 1
        if steps == 6:
            accum = 0.0

        # 游戏结束：结算本局入档（smoke 自动重开前执行一次）
        if game.state == "gameover" and not game._settled:
            game.settle_run()

        # 音频 BGM 状态机（标题/战斗/60s 变奏/Boss/结算）
        audio.update_bgm(game)

        # ---------------- 绘制 ----------------
        game.draw_world(screen)
        if game.state == "title":
            ui.draw_menu(screen, game)
        elif game.state == "charsel":
            ui.draw_charsel(screen, game)
        elif game.state == "mapsel":
            ui.draw_mapsel(screen, game)
        elif game.state == "settings":
            ui.draw_settings(screen, game)
        elif game.state == "stats":
            ui.draw_stats(screen, game)
        elif game.state == "metatree":
            ui.draw_metatree(screen, game)
        elif game.state == "play":
            ui.draw_hud(screen, game)
        elif game.state == "upgrade":
            ui.draw_hud(screen, game)
            ui.draw_upgrade(screen, game, game.cards, game.hover_idx, game.chosen)
        elif game.state == "boon":
            ui.draw_hud(screen, game)
            ui.draw_boon(screen, game)
        elif game.state == "chest":
            ui.draw_hud(screen, game)
            ui.draw_chest(screen, game)
        elif game.state == "tree":
            ui.draw_tree(screen, game, pygame.mouse.get_pos())
        elif game.state == "pause":
            ui.draw_hud(screen, game)
            ui.draw_pause(screen)
        elif game.state == "gameover":
            ui.draw_hud(screen, game)
            ui.draw_gameover(screen, game, game.victory)
        pygame.display.flip()

        # ---------------- smoke 收尾 ----------------
        if SMOKE and sim_total >= SMOKE_SECS:
            stats = dict(
                t=round(sim_total, 1), run_t=round(game.time, 1),
                map=game.map_key, boss=game.theme["boss"],
                diff=game.difficulty_key, endless=game.endless,
                run_gold=game.run_gold,
                deaths=deaths, wins=wins, level=game.level, kills=game.kills,
                damage=int(game.total_damage), enemies=len(game.enemies),
                projectiles=len(game.projectiles), gems=len(game.gems),
                enemy_bullets=len(game.enemy_bullets), allies=len(game.allies),
                geysers=len(game.geysers), best_combo=game.combo_best,
                weapons=[f"{w.key}:{w.level}{'*' if w.evolved else ''}"
                         for w in game.weapons],
                boons=len(game.boons.taken),
                favors=",".join(sorted(game.boons.favors)) or "none",
                state=game.state, victory=game.victory,
                hp=round(game.player.hp, 1), hp_max=game.player.hp_max,
                shield=round(game.boons.shield, 1),
            )
            print("SMOKE_OK " + str(stats).replace("'", '"'))
            pygame.quit()
            return 0


if __name__ == "__main__":
    sys.exit(run())
