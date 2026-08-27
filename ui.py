# -*- coding: utf-8 -*-
"""UI 层：HUD / 升级三选一 / 结算画面。"""
import math

import pygame

from settings import WIDTH, HEIGHT, COL
from data import PASSIVES, WEAPON_MAX_LEVEL, CHARS, WEAPONS, MAPS, BOSSES
from settings import DIFFICULTIES
import meta
import boons as B
from vendor.alloy.utils.font import load_local_font as _local_font

_FONT_CACHE = {}


def font(size, bold=False):
    key = (size, bold)
    f = _FONT_CACHE.get(key)
    if f is None:
        # 本地打包 CJK 手写字体优先（vendor/alloy/fonts），失败回退系统字体
        try:
            f = _local_font(size, bold=bold)
        except Exception:
            f = None
        if f is None:
            names = "microsoftyahei,msyh,simhei,dengxian"
            f = pygame.font.SysFont(names, size, bold=bold)
        if not f:                                    # 兜底
            f = pygame.font.Font(None, size)
        _FONT_CACHE[key] = f
    return f


def text(surf, s, size, x, y, color=COL["text"], bold=False, anchor="topleft"):
    img = font(size, bold).render(s, True, color)
    rect = img.get_rect(**{anchor: (x, y)})
    surf.blit(img, rect)
    return rect


def bar(surf, x, y, w, h, frac, fg, bg, border=(10, 12, 18)):
    pygame.draw.rect(surf, bg, (x, y, w, h), border_radius=3)
    if frac > 0:
        pygame.draw.rect(surf, fg, (x, y, int(w * min(1.0, frac)), h), border_radius=3)
    pygame.draw.rect(surf, border, (x, y, w, h), 2, border_radius=3)


# ================================================================ HUD
def draw_hud(surf, game):
    p = game.player

    # 左上：HP（+护盾粉条）
    bar(surf, 16, 16, 240, 18, p.hp / p.hp_max, COL["hp_bar"], COL["hp_back"])
    if game.boons.shield > 0:
        bar(surf, 16, 38, 240, 8, min(1.0, game.boons.shield / 45.0),
            (255, 130, 190), (40, 22, 32))
    text(surf, f"{max(0, int(p.hp))} / {p.hp_max}", 14, 136, 19, bold=True)
    if game.boons.shield > 0:
        text(surf, f"盾 {int(game.boons.shield)}", 12, 16, 40,
             (255, 130, 190), bold=True)
    # 本局金币（Phase 6）+ 难度/无尽（Phase 7）
    text(surf, f"金币 {game.run_gold}", 15, 16, 54, COL["gold"], bold=True)
    dlabel = DIFFICULTIES[game.difficulty_key]["name"] + (" · 无尽" if game.endless else "")
    text(surf, dlabel, 13, 16, 74, COL["dim"])

    # 顶中：时间
    m, s = divmod(int(game.time), 60)
    boss_in = max(0, int(180 - game.time))
    label = f"{m:02d}:{s:02d}"
    if game.boss is None and game.time < 180:
        label += f"   巨人降临 {boss_in}s"
    text(surf, label, 26, WIDTH // 2, 12, bold=True, anchor="midtop")

    # 右上：击杀 / 等级 / 赐福栏
    text(surf, f"击杀 {game.kills}", 18, WIDTH - 16, 16, anchor="topright")
    text(surf, f"Lv {game.level}", 18, WIDTH - 16, 40, COL["accent"], bold=True, anchor="topright")
    bx = WIDTH - 16
    by = 64
    for gkey in B.GODS:
        cnt = game.boons.god_count(gkey)
        if cnt:
            gd = B.GODS[gkey]
            fav = gkey in game.boons.favors
            label = f"{gd['sym']}{cnt}{'★' if fav else ''}"
            img = font(16, bold=fav).render(label, True, gd["color"])
            bx -= img.get_width() + 10
            surf.blit(img, (bx, by))

    # 右中：连杀计数（暗黑式 massacre）
    if game.combo > 1:
        k = 1.0 if game.combo < 25 else 1.15 if game.combo < 50 else 1.3
        text(surf, "连杀", 15, WIDTH - 24, HEIGHT // 2 - 46,
             COL["dim"], anchor="topright")
        text(surf, f"×{game.combo}", int(38 * k), WIDTH - 24, HEIGHT // 2 - 30,
             COL["gold"], bold=True, anchor="topright")
        bar(surf, WIDTH - 144, HEIGHT // 2 + 16, 120, 6,
            game.combo_t / 4.0, COL["gold"], (50, 42, 24))
        if game.speed_buff_t > 0:
            text(surf, "疾行", 13, WIDTH - 24, HEIGHT // 2 + 28,
                 (255, 224, 130), anchor="topright")

    # 底部：XP
    bar(surf, 0, HEIGHT - 16, WIDTH, 16,
        game.xp / max(1, game.xp_need), COL["xp_bar"], COL["xp_back"])

    # 武器栏（左下，进化形态金色）
    x = 14
    for w in game.weapons:
        label = f"{w.display_name} {w.level}/{WEAPON_MAX_LEVEL}"
        text(surf, label, 14, x, HEIGHT - 44,
             COL["gold"] if w.evolved else COL["dim"],
             bold=w.evolved)
        x += font(14).size(label)[0] + 18
    # 被动层数
    y = HEIGHT - 66
    for k, v in p.passives.items():
        if v:
            text(surf, f"{PASSIVES[k]['name']} {v}", 13, 14, y, COL["dim"])
            y -= 17

    # Boss 血条
    if game.boss is not None and game.boss.hp > 0:
        b = game.boss
        bar(surf, WIDTH // 2 - 260, 52, 520, 14, b.hp / b.hp_max,
            COL["boss"], COL["hp_back"])
        text(surf, b.name, 15, WIDTH // 2, 70, COL["boss"], bold=True, anchor="midtop")

    # 主动技（Q）：右下（Phase 4）
    sk = game.skill_cfg
    ready = game.skill_t <= 0
    label = f"[Q] {sk['name']}"
    if game.player.berserk_t > 0:
        label += "  狂暴中"
    text(surf, label, 16, WIDTH - 16, HEIGHT - 64,
         COL["gold"] if ready else COL["dim"], bold=ready, anchor="topright")
    if not ready:
        frac = 1.0 - game.skill_t / max(0.01, sk["cooldown"])
        bar(surf, WIDTH - 136, HEIGHT - 40, 120, 8, frac,
            COL["gold"], (50, 42, 24))

    # 任务横幅（Phase 5）
    if game.quest is not None:
        q = game.quest
        frac = min(1.0, q["progress"] / max(1, q["target"]))
        text(surf, q["label"], 17, WIDTH // 2, 88, COL["gold"], bold=True,
             anchor="midtop")
        bar(surf, WIDTH // 2 - 150, 112, 300, 8, frac, COL["gold"],
            (50, 42, 24))
        text(surf, f"剩余 {max(0, int(q['t_left']))}s", 13, WIDTH // 2, 124,
             COL["dim"], anchor="midtop")


# ================================================================ 升级选卡
def card_rects(n):
    """n 张卡的矩形（绘制与点击检测共用同一几何）。"""
    cw, ch, gap = 300, 200, 34
    total = n * cw + (n - 1) * gap
    x0 = (WIDTH - total) // 2
    y = HEIGHT // 2 - 80
    return [pygame.Rect(x0 + i * (cw + gap), y, cw, ch) for i in range(n)]


def draw_upgrade(surf, game, cards, hover_idx, chosen_this_run):
    # 蒙层
    dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    dim.fill((8, 10, 16, 190))
    surf.blit(dim, (0, 0))

    text(surf, "LEVEL UP", 40, WIDTH // 2, HEIGHT // 2 - 190,
         COL["gold"], bold=True, anchor="midtop")
    text(surf, f"等级 {game.level}", 16, WIDTH // 2, HEIGHT // 2 - 142,
         COL["dim"], anchor="midtop")

    n = len(cards)
    rects = card_rects(n)
    mouse = pygame.mouse.get_pos()
    for i, c in enumerate(cards):
        rect = rects[i]
        x, y, cw, ch = rect.x, rect.y, rect.w, rect.h
        sel = (i == hover_idx) or rect.collidepoint(mouse)
        pygame.draw.rect(surf, COL["card_sel"] if sel else COL["card"], rect,
                         border_radius=10)
        pygame.draw.rect(surf, COL["accent"] if sel else (52, 58, 76), rect, 2,
                         border_radius=10)

        # 类别条
        kind_color = {"new": COL["gold"], "up": COL["accent"], "pas": (140, 210, 160),
                      "heal": (220, 120, 120), "xp": (160, 140, 220)}.get(c["kind"], COL["dim"])
        pygame.draw.rect(surf, kind_color, (x + 10, y + 12, 46, 22), border_radius=4)
        text(surf, c.get("tag", ""), 14, x + 33, y + 14, (14, 16, 24), bold=True,
             anchor="midtop")

        # 名字 + 描述
        text(surf, c["name"], 24, x + cw // 2, y + 56, bold=True, anchor="midtop")
        text(surf, c["desc"], 15, x + cw // 2, y + 100, COL["dim"], anchor="midtop")

        # 已选次数提示
        if chosen_this_run.get(c.get("id")):
            text(surf, f"已选 {chosen_this_run[c['id']]} 次", 13, x + cw // 2, y + 150,
                 (120, 126, 140), anchor="midtop")

        # 快捷键
        text(surf, f"[{i + 1}]", 18, x + cw // 2, y + ch - 30,
             COL["gold"] if sel else COL["dim"], bold=True, anchor="midtop")

    text(surf, "按 1 / 2 / 3 或点击选择", 15, WIDTH // 2, y + ch + 26,
         COL["dim"], anchor="midtop")
    text(surf, f"R 重掷 ×{game.rerolls}   ·   B 放逐 ×{game.banishes}", 14,
         WIDTH // 2, y + ch + 52, COL["dim"], anchor="midtop")


# ================================================================ 宝箱选卡（Phase 5）
def draw_chest(surf, game):
    dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    dim.fill((8, 10, 16, 200))
    surf.blit(dim, (0, 0))
    text(surf, "宝 箱", 44, WIDTH // 2, HEIGHT // 2 - 200, COL["gold"],
         bold=True, anchor="midtop")
    text(surf, "选择一个奖励", 16, WIDTH // 2, HEIGHT // 2 - 148, COL["dim"],
         anchor="midtop")
    _, cards = game.chest_offer
    rects = card_rects(3)
    mouse = pygame.mouse.get_pos()
    for i, c in enumerate(cards):
        rect = rects[i]
        sel = rect.collidepoint(mouse)
        pygame.draw.rect(surf, COL["card_sel"] if sel else COL["card"], rect,
                         border_radius=10)
        pygame.draw.rect(surf, COL["gold"] if sel else (52, 58, 76), rect, 2,
                         border_radius=10)
        text(surf, c["name"], 24, rect.centerx, rect.y + 70, bold=True,
             anchor="midtop")
        text(surf, c["desc"], 15, rect.centerx, rect.y + 110, COL["dim"],
             anchor="midtop")
        text(surf, f"[{i + 1}]", 18, rect.centerx, rect.y + rect.h - 30,
             COL["gold"] if sel else COL["dim"], bold=True, anchor="midtop")
    text(surf, "ESC 放弃（宝箱保留）", 14, WIDTH // 2, rects[0].bottom + 26,
         COL["dim"], anchor="midtop")


# ================================================================ 标题
def draw_title(surf, game=None):
    dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    dim.fill((8, 10, 16, 150))
    surf.blit(dim, (0, 0))
    cx = WIDTH // 2
    text(surf, "JOTUNNSLAYER", 64, cx, HEIGHT // 2 - 170, COL["snow"],
         bold=True, anchor="center")
    text(surf, "霜 原 割 草 · 复 刻 原 型", 24, cx, HEIGHT // 2 - 104,
         COL["accent"], anchor="center")

    # 地图选择（Phase 3）
    sel = game.map_key if game else "snow"
    y0 = HEIGHT // 2 - 58
    for i, (mk, name) in enumerate((("snow", "霜雪平原"), ("lava", "熔岩废土"))):
        on = (sel == mk)
        box = pygame.Rect(cx - 190 + i * 200, y0, 180, 46)
        pygame.draw.rect(surf, COL["card_sel"] if on else COL["card"], box,
                         border_radius=8)
        pygame.draw.rect(surf, COL["accent"] if on else (52, 58, 76), box, 2,
                         border_radius=8)
        text(surf, f"[{i + 1}] {name}", 18, box.centerx, box.centery,
             COL["text"] if on else COL["dim"], bold=on, anchor="center")

    text(surf, "WASD / 方向键 移动，武器全自动攻击", 17, cx, HEIGHT // 2 + 14,
         COL["dim"], anchor="center")
    text(surf, "吃宝石升级三选一 · 触碰神龛领诸神赐福", 17,
         cx, HEIGHT // 2 + 42, COL["dim"], anchor="center")
    text(surf, "连杀不间断可获经验爆发 · Tab 查看命运星图", 15, cx, HEIGHT // 2 + 70,
         COL["dim"], anchor="center")
    if (pygame.time.get_ticks() // 600) % 2 == 0:
        text(surf, "按 1 / 2 选地图，任意其他键开始", 22, cx, HEIGHT // 2 + 128,
             COL["gold"], bold=True, anchor="center")
    # 跨局 meta（存档）概览
    if game is not None and getattr(game, "meta", None) is not None:
        m = game.meta
        mm, ss = divmod(int(m.best_run.time), 60)
        info = (f"金币 {m.gold}   ·   最佳 Lv{m.best_run.level} "
                f"{m.best_run.kills} 杀 {mm:02d}:{ss:02d}   ·   "
                f"总局 {m.stats.runs} 胜 {m.stats.wins}")
        text(surf, info, 16, cx, HEIGHT // 2 + 168, COL["dim"], anchor="center")
    text(surf, "Python 3.14 + pygame-ce · 玩法致敬 Jotunnslayer: Hordes of Hel",
         13, cx, HEIGHT - 26, (110, 116, 130), anchor="center")


# ================================================================ 主菜单（Phase 6）
def _dim(surf, alpha=190):
    d = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    d.fill((8, 10, 16, alpha))
    surf.blit(d, (0, 0))


def draw_menu(surf, game=None):
    _dim(surf)
    cx = WIDTH // 2
    text(surf, "JOTUNNSLAYER", 64, cx, 90, COL["snow"], bold=True, anchor="midtop")
    text(surf, "诸神黄昏 · 幸存者复刻", 20, cx, 162, COL["dim"], anchor="midtop")
    items = [("1", "开始游戏", "选择角色与战场"),
             ("2", "最高分", "最佳记录与终身统计"),
             ("3", "设置", "音效 / 音乐音量"),
             ("4", "技能树", "用金币强化角色与众神")]
    mouse = pygame.mouse.get_pos()
    y0 = 240
    for i, (k, name, sub) in enumerate(items):
        rect = pygame.Rect(cx - 190, y0 + i * 62, 380, 52)
        sel = rect.collidepoint(mouse)
        pygame.draw.rect(surf, COL["card_sel"] if sel else COL["card"], rect,
                         border_radius=10)
        pygame.draw.rect(surf, COL["accent"] if sel else (52, 58, 76), rect, 2,
                         border_radius=10)
        text(surf, f"[{k}] {name}", 24, rect.x + 24, rect.centery, bold=True,
             anchor="midleft")
        text(surf, sub, 14, rect.right - 20, rect.centery, COL["dim"],
             anchor="midright")
    if game is not None and getattr(game, "meta", None) is not None:
        m = game.meta
        mm, ss = divmod(int(m.best_run.time), 60)
        info = (f"金币 {m.gold}   ·   最佳 Lv{m.best_run.level} "
                f"{m.best_run.kills} 杀 {mm:02d}:{ss:02d}   ·   "
                f"总局 {m.stats.runs} 胜 {m.stats.wins}")
        text(surf, info, 16, cx, 520, COL["dim"], anchor="center")
    text(surf, "ESC 退出", 15, cx, HEIGHT - 60, (110, 116, 130), anchor="center")
    text(surf, "Python 3.14 + pygame-ce · 玩法致敬 Jotunnslayer: Hordes of Hel",
         13, cx, HEIGHT - 26, (110, 116, 130), anchor="center")


# ================================================================ 角色选择（Phase 4）
def draw_charsel(surf, game):
    _dim(surf)
    cx = WIDTH // 2
    text(surf, "选择你的勇士", 44, cx, 60, COL["snow"], bold=True, anchor="midtop")
    rects = card_rects(3)
    mouse = pygame.mouse.get_pos()
    for i, key in enumerate(("berserker", "seeress", "warden")):
        d = CHARS[key]
        rect = rects[i]
        sel = rect.collidepoint(mouse)
        pygame.draw.rect(surf, COL["card_sel"] if sel else COL["card"], rect,
                         border_radius=10)
        pygame.draw.rect(surf, d["color"] if sel else (52, 58, 76), rect, 2,
                         border_radius=10)
        pygame.draw.rect(surf, d["color"], (rect.x + 10, rect.y + 12, 58, 22),
                         border_radius=4)
        text(surf, d["title"], 14, rect.x + 39, rect.y + 14, (14, 16, 24),
             bold=True, anchor="midtop")
        text(surf, d["name"], 26, rect.centerx, rect.y + 52, bold=True,
             anchor="midtop")
        text(surf, f"HP {d['hp']} · 起始武器 {WEAPONS[d['start_weapon']]['name']}",
             14, rect.centerx, rect.y + 88, COL["dim"], anchor="midtop")
        sk = d["skill"]
        text(surf, f"主动技 [Q] {sk['name']}（{sk['cooldown']:.0f}s）", 15,
             rect.centerx, rect.y + 112, d["color"], bold=True, anchor="midtop")
        text(surf, sk["desc"], 13, rect.centerx, rect.y + 138, COL["dim"],
             anchor="midtop")
        text(surf, d["desc"], 13, rect.centerx, rect.y + 162, (120, 126, 140),
             anchor="midtop")
        text(surf, f"[{i + 1}]", 18, rect.centerx, rect.y + rect.h - 28,
             COL["gold"] if sel else COL["dim"], bold=True, anchor="midtop")
    text(surf, "ESC 返回", 15, cx, rects[0].bottom + 24, COL["dim"],
         anchor="midtop")


# ================================================================ 地图选择（Phase 7）
def draw_mapsel(surf, game):
    _dim(surf)
    cx = WIDTH // 2
    text(surf, "选择战场", 40, cx, 44, COL["snow"], bold=True, anchor="midtop")
    keys = ("snow", "lava", "mine", "temple", "hel")
    cw, ch, gap = 220, 190, 24
    x0 = (WIDTH - (5 * cw + 4 * gap)) // 2
    y = 110
    mouse = pygame.mouse.get_pos()
    for i, mk in enumerate(keys):
        th = MAPS[mk]
        rect = pygame.Rect(x0 + i * (cw + gap), y, cw, ch)
        sel = rect.collidepoint(mouse) or game.map_key == mk
        pygame.draw.rect(surf, COL["card_sel"] if sel else COL["card"], rect,
                         border_radius=10)
        pygame.draw.rect(surf, COL["accent"] if sel else (52, 58, 76), rect, 2,
                         border_radius=10)
        text(surf, th["name"], 20, rect.centerx, rect.y + 30, bold=True,
             anchor="midtop")
        text(surf, f"Boss：{BOSSES[th['boss']]['name']}", 13, rect.centerx,
             rect.y + 64, COL["boss"], anchor="midtop")
        feat = []
        if th.get("geyser"):
            feat.append("喷泉机关")
        if th.get("carts"):
            feat.append("矿车冲撞")
        if th.get("pillar"):
            feat.append("神柱脉冲")
        if th.get("embers"):
            feat.append("余烬")
        text(surf, " · ".join(feat) or "常规", 12, rect.centerx, rect.y + 88,
             COL["dim"], anchor="midtop")
        text(surf, f"[{i + 1}]", 15, rect.centerx, rect.y + ch - 24,
             COL["gold"] if sel else COL["dim"], bold=True, anchor="midtop")
    y2 = y + ch + 26
    text(surf, "难度：", 20, cx - 420, y2, COL["dim"], anchor="midleft")
    for i, dk in enumerate(("easy", "normal", "hard", "insane")):
        d = DIFFICULTIES[dk]
        on = game.difficulty_key == dk
        text(surf, f"[{6 + i}] {d['name']}", 17, cx - 300 + i * 150, y2,
             COL["gold"] if on else COL["text"], bold=on)
    y3 = y2 + 34
    text(surf, f"[0] 无尽模式：{'开' if game.endless else '关'}", 17,
         cx - 420, y3, COL["gold"] if game.endless else COL["dim"],
         bold=game.endless)
    text(surf, "空格 / 回车 出发 · ESC 返回", 16, cx, y3 + 44, COL["gold"],
         anchor="center")


# ================================================================ 设置（Phase 6）
def draw_settings(surf, game):
    _dim(surf)
    cx = WIDTH // 2
    text(surf, "设置", 44, cx, 80, COL["snow"], bold=True, anchor="midtop")
    labels = [("音效音量", "sfx_vol"), ("音乐音量", "music_vol")]
    for i, (label, k) in enumerate(labels):
        y = 250 + i * 90
        sel = i == game.settings_idx
        text(surf, label, 24, cx - 220, y, COL["gold"] if sel else COL["text"],
             bold=sel, anchor="midleft")
        v = game.meta.settings[k]
        bar(surf, cx - 20, y - 9, 260, 18, v,
            COL["accent"] if sel else COL["card_sel"], COL["card"])
        text(surf, f"{int(v * 100)}%", 20, cx + 260, y, COL["dim"],
             anchor="midleft")
    text(surf, "↑/↓ 切换 · ←/→ 调整（自动保存并即时生效）", 16, cx, 500,
         COL["dim"], anchor="center")
    text(surf, "ESC 返回", 15, cx, 536, COL["dim"], anchor="center")


# ================================================================ 跨局技能树（Phase 6 剩余）
def metatree_node_rects():
    """节点行矩形（绘制与点击共用）。"""
    return [pygame.Rect(190, 200 + i * 32, 620, 28) for i in range(8)]


def draw_metatree(surf, game):
    _dim(surf)
    cx = WIDTH // 2
    m = game.meta
    text(surf, "技 能 树", 40, cx, 34, COL["gold"], bold=True, anchor="midtop")
    text(surf, f"金币 {m.gold}", 18, cx, 84, COL["gold"], anchor="midtop")
    # 角色标签（1-3）
    for i, key in enumerate(("berserker", "seeress", "warden")):
        on = game.meta_tab == "char" and game.meta_idx == key
        text(surf, f"[{i + 1}]{CHARS[key]['name']}", 16, 120 + i * 128, 126,
             COL["gold"] if on else COL["dim"], bold=on)
    # 众神标签（4-9）
    for i, key in enumerate(B.GODS):
        on = game.meta_tab == "god" and game.meta_idx == key
        gd = B.GODS[key]
        text(surf, f"[{i + 4}]{gd['sym']}{gd['name']}", 16,
             120 + i * 168, 154, COL["gold"] if on else COL["dim"], bold=on)
    # 节点列表（点击购买）
    nodes = (meta.CHAR_NODES if game.meta_tab == "char"
             else meta.GOD_NODES[game.meta_idx])
    mouse = pygame.mouse.get_pos()
    for i, (name, key, val, mx) in enumerate(nodes):
        rect = metatree_node_rects()[i]
        lv = meta.level_of(m, game.meta_tab, game.meta_idx, i)
        full = lv >= meta.MAX_NODE_LEVEL
        afford = (not full) and m.gold >= meta.cost(lv)
        sel = rect.collidepoint(mouse)
        pygame.draw.rect(surf, COL["card_sel"] if sel else COL["card"], rect,
                         border_radius=6)
        pygame.draw.rect(surf, COL["gold"] if (sel and afford) else (52, 58, 76),
                         rect, 1, border_radius=6)
        text(surf, f"{name}", 17, rect.x + 14, rect.centery,
             COL["gold"] if lv > 0 else COL["text"], bold=lv > 0, anchor="midleft")
        unit = "级" if key == "hp" else "%"
        text(surf, f"{key}: +{val}{unit if key == 'hp' else ''}" if key == "hp"
             else f"{key}: +{int(val * 100)}%", 13, rect.x + 240, rect.centery,
             COL["dim"], anchor="midleft")
        text(surf, f"Lv{lv}/{mx}", 15, rect.x + 420, rect.centery, COL["dim"],
             anchor="midleft")
        text(surf, "已满级" if full else f"{meta.cost(lv)} 金", 14, rect.right - 14,
             rect.centery, COL["gold"] if afford else COL["dim"], anchor="midright")
    text(surf, "1-9 切换角色/众神 · 点击节点购买 · ESC 返回", 14, cx,
         HEIGHT - 40, COL["dim"], anchor="center")


# ================================================================ 最高分（Phase 6）
def draw_stats(surf, game):
    _dim(surf)
    cx = WIDTH // 2
    text(surf, "最高分 · 终身统计", 44, cx, 80, COL["gold"], bold=True,
         anchor="midtop")
    m = game.meta
    mm, ss = divmod(int(m.best_run.time), 60)
    rows = [
        ("累计金币", f"{m.gold}"),
        ("最佳等级", f"Lv {m.best_run.level}"),
        ("最佳击杀", f"{m.best_run.kills}"),
        ("最佳存活", f"{mm:02d}:{ss:02d}"),
        ("总局数", f"{m.stats.runs}"),
        ("胜利场次", f"{m.stats.wins}"),
        ("总击杀", f"{m.stats.total_kills}"),
        ("总伤害", f"{m.stats.total_damage}"),
    ]
    y = 190
    for k, v in rows:
        text(surf, k, 20, cx - 170, y, COL["dim"])
        text(surf, v, 20, cx + 170, y, bold=True, anchor="topright")
        y += 34
    text(surf, "ESC 返回", 15, cx, HEIGHT - 60, COL["dim"], anchor="center")


# ================================================================ 赐福选卡
def draw_boon(surf, game):
    god, cards, rerolled = game.boon_offer
    gd = B.GODS[god]

    dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    dim.fill((8, 10, 16, 200))
    surf.blit(dim, (0, 0))

    # 神名标题
    title = f"{gd['sym']}  {gd['name']} · {gd['title']}"
    text(surf, title, 40, WIDTH // 2, HEIGHT // 2 - 200,
         gd["color"], bold=True, anchor="midtop")
    cnt = game.boons.god_count(god)
    fav = god in game.boons.favors
    sub = f"已有其赐福 {cnt} / 3" + ("（神眷已临）" if fav else "—— 集齐三种将获神眷")
    text(surf, sub, 16, WIDTH // 2, HEIGHT // 2 - 148, COL["dim"], anchor="midtop")

    rects = card_rects(3)
    mouse = pygame.mouse.get_pos()
    for i, c in enumerate(cards):
        rect = rects[i]
        x, y, cw, ch = rect.x, rect.y, rect.w, rect.h
        sel = rect.collidepoint(mouse)
        rar = B.RARITIES[c["rar"]] if c["rar"] is not None else None
        border = rar["color"] if rar else COL["dim"]
        pygame.draw.rect(surf, COL["card"], rect, border_radius=10)
        pygame.draw.rect(surf, COL["gold"] if sel else border, rect, 3 if sel else 2,
                         border_radius=10)
        # 稀有度顶条
        if rar:
            pygame.draw.rect(surf, rar["color"], (x + 10, y + 12, 58, 22), border_radius=4)
            text(surf, rar["name"], 14, x + 39, y + 14, (14, 16, 24), bold=True,
                 anchor="midtop")
        else:
            pygame.draw.rect(surf, COL["dim"], (x + 10, y + 12, 58, 22), border_radius=4)
            text(surf, "补给", 14, x + 39, y + 14, (14, 16, 24), bold=True,
                 anchor="midtop")

        text(surf, c["name"], 24, x + cw // 2, y + 56, bold=True, anchor="midtop")
        text(surf, c["desc"], 15, x + cw // 2, y + 100, COL["dim"], anchor="midtop")
        if c.get("stacks"):
            text(surf, f"已有 ×{c['stacks']}，叠加增强", 13, x + cw // 2, y + 140,
                 (120, 126, 140), anchor="midtop")
        text(surf, f"[{i + 1}]", 18, x + cw // 2, y + ch - 30,
             COL["gold"] if sel else COL["dim"], bold=True, anchor="midtop")

    hint = "按 R 重掷（一次） · 1 / 2 / 3 选择" if not rerolled else "按 1 / 2 / 3 选择"
    text(surf, hint, 15, WIDTH // 2, rects[0].bottom + 26, COL["dim"], anchor="midtop")


# ================================================================ 命运星图（PoE 式）
def _star_pts(cx, cy, r, n=5, rot=-math.pi / 2):
    pts = []
    for i in range(n * 2):
        rr = r if i % 2 == 0 else r * 0.45
        a = rot + i * math.pi / n
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    return pts


# 布局：中央战士 -> 6 神扇区（中枢 -> 3 赐福 -> 神眷星）
_R_HUB, R_BOON, R_FAVOR = 140.0, 230.0, 300.0


def tree_layout():
    """返回 (nodes, edges)。node id: ('hub',god)/('boon',god,key)/('favor',god)"""
    cx, cy = WIDTH / 2, HEIGHT / 2
    nodes = {"center": (cx, cy)}
    edges = []
    for i, gkey in enumerate(B.GODS):
        ang = -math.pi / 2 + i * math.pi / 3          # 从正上开始顺时针
        hx, hy = cx + math.cos(ang) * _R_HUB, cy + math.sin(ang) * _R_HUB
        nodes[("hub", gkey)] = (hx, hy)
        edges.append(("center", ("hub", gkey)))
        # 3 赐福：中枢角 ±26° 与正中
        keys = list(B.GODS[gkey]["boons"].keys())
        bx0 = cx + math.cos(ang) * R_BOON, cy + math.sin(ang) * R_BOON
        for j, k in enumerate(keys):
            a = ang + (j - 1) * (26 * math.pi / 180)
            nodes[("boon", gkey, k)] = (cx + math.cos(a) * R_BOON,
                                        cy + math.sin(a) * R_BOON)
            edges.append((("hub", gkey), ("boon", gkey, k)))
        fx, fy = cx + math.cos(ang) * R_FAVOR, cy + math.sin(ang) * R_FAVOR
        nodes[("favor", gkey)] = (fx, fy)
        edges.append((("boon", gkey, keys[1]), ("favor", gkey)))
    return nodes, edges


def _node_state(game, nid):
    """(obtained, label, desc, color, stacks)"""
    boons = game.boons
    if nid == "center":
        return True, "无畏者", "星图的原点：你", (232, 238, 248), 0
    if nid[0] == "hub":
        g = nid[1]
        gd = B.GODS[g]
        got = boons.god_count(g)
        return got > 0, f"{gd['sym']} {gd['name']}·{gd['title']}", \
            gd["favor"]["desc"], gd["color"], got
    if nid[0] == "boon":
        g, k = nid[1], nid[2]
        bd = B.GODS[g]["boons"][k]
        st = boons.taken.get((g, k), 0)
        rm = boons.rarity.get((g, k), 1.0)
        rar = next((r["name"] for r in B.RARITIES if r["mult"] == rm), "普通")
        return st > 0, bd["name"], \
            f"{rar} · {B.boon_desc(g, k, rm)}", B.GODS[g]["color"], st
    if nid[0] == "favor":
        g = nid[1]
        gd = B.GODS[g]
        on = g in boons.favors
        return on, f"★ {gd['favor']['name']}", \
            f"{gd['name']}神眷：{gd['favor']['desc']}（集齐其 3 种赐福）", \
            COL["gold"], 1 if on else 0
    return False, "?", "", COL["dim"], 0


def draw_tree(surf, game, mouse_pos=None):
    nodes, edges = tree_layout()
    boons = game.boons

    # 背景
    dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    dim.fill((6, 8, 14, 225))
    surf.blit(dim, (0, 0))
    # 背景星点（确定性，平铺星夜氛围）
    import random as _r
    _rr = _r.Random(99)
    for _ in range(90):
        sx, sy = _rr.randrange(WIDTH), _rr.randrange(HEIGHT)
        b = _rr.randrange(70, 150)
        pygame.draw.circle(surf, (b, b + 6, b + 16), (sx, sy), 1)

    # 连线
    for a, b in edges:
        x1, y1 = nodes[a]
        x2, y2 = nodes[b]
        lit = _node_state(game, b)[0]
        color = (120, 128, 150) if lit else (44, 50, 66)
        pygame.draw.line(surf, color, (x1, y1), (x2, y2), 2 if lit else 1)

    # 节点
    hover_info = None
    for nid, (x, y) in nodes.items():
        got, label, desc, color, stacks = _node_state(game, nid)
        if nid == "center":
            pygame.draw.circle(surf, COL["player_helm"], (int(x), int(y)), 20)
            pygame.draw.circle(surf, (255, 255, 255), (int(x), int(y)), 20, 2)
            text(surf, "无畏者", 13, x, y + 26, anchor="midtop")
            continue
        r = 20 if nid[0] == "hub" else 13 if nid[0] == "boon" else 16
        if nid[0] == "favor":
            pts = _star_pts(x, y, r + 6)
            if got:
                pygame.draw.polygon(surf, COL["gold"], pts)
                pygame.draw.polygon(surf, (255, 240, 200), pts, 2)
            else:
                pygame.draw.polygon(surf, (70, 62, 40), pts)
                pygame.draw.polygon(surf, (120, 106, 66), pts, 1)
        else:
            if got:
                pygame.draw.circle(surf, color, (int(x), int(y)), r)
                pygame.draw.circle(surf, (255, 255, 255), (int(x), int(y)), r, 2)
            else:
                pygame.draw.circle(surf, (26, 30, 42), (int(x), int(y)), r)
                pygame.draw.circle(surf, (60, 66, 84), (int(x), int(y)), r, 1)
        # 中枢符文 / 层数
        if nid[0] == "hub":
            text(surf, B.GODS[nid[1]]["sym"], 18, x, y - 10,
                 (20, 24, 34) if got else (110, 118, 136), bold=True, anchor="center")
            text(surf, B.GODS[nid[1]]["name"], 14, x, y + 26,
                 color if got else COL["dim"], anchor="midtop")
        elif nid[0] == "boon" and stacks:
            text(surf, f"×{stacks}", 12, x, y - 26, color, bold=True, anchor="midtop")

        # 悬停检测
        if mouse_pos and (mouse_pos[0] - x) ** 2 + (mouse_pos[1] - y) ** 2 <= (r + 12) ** 2:
            hover_info = (label, desc, color, mouse_pos)

    # 标题与统计
    total = len(boons.taken)
    text(surf, "命 运 星 图", 30, WIDTH // 2, 14, COL["snow"], bold=True, anchor="midtop")
    text(surf, f"赐福 {total}/18 · 神眷 {len(boons.favors)}/6 · 按 Tab/ESC 返回",
         14, WIDTH // 2, 48, COL["dim"], anchor="midtop")

    # 悬停 tooltip
    if hover_info:
        label, desc, color, (mx, my) = hover_info
        tw = max(260, font(15).size(label)[0] + 40, font(13).size(desc)[0] + 40)
        th = 58
        tx = min(WIDTH - tw - 8, mx + 18)
        ty = max(8, my - th - 12)
        tip = pygame.Surface((tw, th), pygame.SRCALPHA)
        tip.fill((16, 20, 32, 235))
        pygame.draw.rect(surf, color, (tx, ty, tw, th), 2, border_radius=6)
        surf.blit(tip, (tx, ty))
        text(surf, label, 15, tx + 12, ty + 8, color, bold=True)
        text(surf, desc, 13, tx + 12, ty + 32, COL["dim"])


# ================================================================ 暂停
def draw_pause(surf):
    dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    dim.fill((8, 10, 16, 170))
    surf.blit(dim, (0, 0))
    text(surf, "已暂停", 42, WIDTH // 2, HEIGHT // 2 - 60, bold=True, anchor="center")
    text(surf, "ESC 继续 · R 重新开始", 17, WIDTH // 2, HEIGHT // 2 + 6,
         COL["dim"], anchor="center")


# ================================================================ 结算
def draw_gameover(surf, game, victory):
    dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    dim.fill((8, 10, 16, 205))
    surf.blit(dim, (0, 0))

    cx = WIDTH // 2
    if victory:
        text(surf, "巨人陨落", 56, cx, HEIGHT // 2 - 160, COL["gold"], bold=True, anchor="center")
        text(surf, "诸神黄昏暂退，雪原迎来了黎明", 18, cx, HEIGHT // 2 - 92,
             COL["dim"], anchor="center")
    else:
        text(surf, "勇士长眠", 56, cx, HEIGHT // 2 - 160, COL["hp_bar"], bold=True, anchor="center")
        text(surf, "尸潮淹没了最后的篝火", 18, cx, HEIGHT // 2 - 92,
             COL["dim"], anchor="center")

    m, s = divmod(int(game.time), 60)
    rows = [
        ("存活时间", f"{m:02d}:{s:02d}"),
        ("最终等级", f"Lv {game.level}"),
        ("击杀数", f"{game.kills}"),
        ("造成伤害", f"{int(game.total_damage)}"),
        ("本局金币", f"+{game.run_gold}"),
        ("累计金币", f"{game.meta.gold}"),
        ("武器", "、".join(
            (f"{w.display_name}Lv{w.level}★" if w.evolved else f"{w.display_name}Lv{w.level}")
            for w in game.weapons)),
    ]
    boon_rows = game.boons.summary()
    if boon_rows:
        rows.append(("诸神赐福", f"{len(boon_rows)} 项"))
    y = HEIGHT // 2 - 40
    for k, v in rows:
        text(surf, k, 18, cx - 170, y, COL["dim"])
        text(surf, v, 18, cx + 170, y, bold=True, anchor="topright")
        y += 30

    # 赐福明细（右侧竖排，最多 8 行）
    for i, line in enumerate(boon_rows[:8]):
        text(surf, line, 14, cx + 240, HEIGHT // 2 - 40 + i * 22,
             (200, 205, 220))
    if len(boon_rows) > 8:
        text(surf, f"…等共 {len(boon_rows)} 项", 14, cx + 240,
             HEIGHT // 2 - 40 + 8 * 22, (140, 145, 160))

    text(surf, "按 R 重新开始 · ESC 退出", 16, cx, y + 26, COL["gold"], anchor="center")
