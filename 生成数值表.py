# -*- coding: utf-8 -*-
"""生成《电子斗蛐蛐》策划数值表。

产出：数值表/QuQu数值表.xlsx

这张表是**唯一数值真相源**：所有属性、品种、招式、克制、状态、战斗常数都由它控制。
策划直接编辑 Excel 即可，重启桌宠自动生效（由 导出数值表.py 转成 data/stats.json）。

本脚本用于初始化 / 重建表结构。日常调数值请直接改 Excel，不要跑这个脚本
（会覆盖你改过的内容）。
"""

from __future__ import annotations

import os

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "数值表")
OUT_FILE = os.path.join(OUT_DIR, "QuQu数值表.xlsx")

FONT = "微软雅黑"
HEAD_FILL = PatternFill("solid", start_color="DDEBF7", end_color="DDEBF7")
ALT_FILL = PatternFill("solid", start_color="F7F9FC", end_color="F7F9FC")
WARN_FILL = PatternFill("solid", start_color="FFC7CE", end_color="FFC7CE")
GOOD_FILL = PatternFill("solid", start_color="C6EFCE", end_color="C6EFCE")
NOTE_FILL = PatternFill("solid", start_color="FFF2CC", end_color="FFF2CC")

THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def write_sheet(wb, title, headers, rows, widths, note=None, highlight=None):
    """建一个表。highlight: {行索引: 填充色} 用来给特殊行上色。"""
    ws = wb.create_sheet(title)
    start = 1
    if note:
        ws.cell(row=1, column=1, value=note)
        ws.cell(row=1, column=1).font = Font(name=FONT, size=9, color="7F7F7F")
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(1, len(headers)))
        start = 2

    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=start, column=c, value=h)
        cell.font = Font(name=FONT, size=10, bold=True)
        cell.fill = HEAD_FILL
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for i, row in enumerate(rows):
        r = start + 1 + i
        fill = (highlight or {}).get(i)
        if fill is None and i % 2 == 1:
            fill = ALT_FILL
        for c, v in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = Font(name=FONT, size=10)
            cell.border = BORDER
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if fill is not None:
                cell.fill = fill

    for c, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(c)].width = w

    ws.freeze_panes = ws.cell(row=start + 1, column=1)
    return ws


def build() -> str:
    wb = Workbook()
    wb.remove(wb.active)

    # ---------- 0. 说明 ----------
    ws = wb.create_sheet("0-说明")
    lines = [
        ("电子斗蛐蛐 · 策划数值表", True, 14),
        ("", False, 10),
        ("这张表控制游戏里的全部数值。改完保存，重启桌宠即生效。", False, 10),
        ("", False, 10),
        ("各表用途：", True, 11),
        ("1-属性定义   属性清单与取值范围（加属性先在这登记）", False, 10),
        ("2-品种       蛐蛐品种的基础属性与外观", False, 10),
        ("3-成长       每级的属性增量与升级经验", False, 10),
        ("4-招式       战斗招式：伤害系数、耐力消耗、特效", False, 10),
        ("5-克制       招式之间的克制矩阵（石头剪刀布）", False, 10),
        ("6-状态       Buff / Debuff 定义", False, 10),
        ("7-战斗常数   全局公式参数（护甲系数、力竭时长等）", False, 10),
        ("8-天赋       随机词条与效果", False, 10),
        ("", False, 10),
        ("注意事项：", True, 11),
        ("· 不要改表头名字，不要删列，否则程序读不到", False, 10),
        ("· ID 列是程序的索引，改 ID 会导致配置失效", False, 10),
        ("· 想加新属性：先在「1-属性定义」加行，再到「2-品种」加列", False, 10),
        ("· 红底行 = 负面效果；绿底行 = 正面效果", False, 10),
    ]
    for i, (text, bold, size) in enumerate(lines, 1):
        cell = ws.cell(row=i, column=1, value=text)
        cell.font = Font(name=FONT, size=size, bold=bold)
    ws.column_dimensions["A"].width = 70

    # ---------- 1. 属性定义 ----------
    write_sheet(
        wb,
        "1-属性定义",
        ["ID", "属性名", "缩写", "分类", "说明", "默认值", "最小", "最大", "战斗可见", "备注"],
        [
            ["hp", "血量", "HP", "核心", "归零即判负", 100, 1, 9999, "是", ""],
            ["sta", "耐力", "STA", "核心", "每次出手消耗", 50, 0, 999, "是", "归零进入力竭状态"],
            ["atk", "攻击", "ATK", "核心", "伤害基数", 12, 1, 999, "是", "实际伤害=ATK×招式系数×减伤"],
            ["arm", "护甲", "ARM", "核心", "百分比减伤", 20, 0, 999, "是", "减伤=ARM/(ARM+ARM_K)"],
            ["spd", "速度", "SPD", "核心", "出手频率", 20, 1, 200, "是", "间隔=基础间隔×100/(100+SPD)"],
            ["sta_regen", "耐力回复", "REG", "派生", "每秒回复耐力", 6, 0, 99, "是", "决定续航"],
            ["crit", "暴击", "CRIT", "派生", "暴击率(%)", 5, 0, 100, "是", "倍率见战斗常数"],
            ["tough", "韧性", "TGH", "派生", "降低被暴击(%)", 0, 0, 100, "是", ""],
            ["pen", "破甲", "PEN", "派生", "无视护甲点数", 0, 0, 999, "是", "计算减伤前先从护甲扣除"],
            ["morale", "士气", "MOR", "隐藏", "归零会逃跑", 100, 0, 100, "是", "第二种败北条件"],
            ["guts", "斗性", "GUT", "隐藏", "抗士气下降(%)", 50, 0, 100, "否", "越高越不容易跑"],
            ["weight", "体重", "WT", "隐藏", "影响伤害与速度", 5, 1, 20, "是", "伤害+，速度-"],
        ],
        [12, 12, 8, 8, 22, 10, 8, 8, 10, 30],
        note="加新属性请先在此登记；分类可选：核心 / 派生 / 隐藏",
    )

    # ---------- 2. 品种 ----------
    write_sheet(
        wb,
        "2-品种",
        ["ID", "名称", "HP", "ATK", "ARM", "SPD", "STA", "耐力回复", "暴击", "斗性", "体重", "稀有度", "主色", "描述"],
        [
            ["c001", "中华斗蟋", 100, 12, 20, 20, 50, 6, 5, 50, 5, "普通", "#6FA83C", "最常见的斗蟋，各项均衡，新手之选"],
            ["c002", "铁头将军", 120, 10, 38, 13, 55, 5, 3, 65, 7, "稀有", "#8A8F98", "头壳坚硬，护甲极高，但动作迟缓"],
            ["c003", "疾风", 78, 13, 11, 34, 45, 8, 10, 40, 4, "稀有", "#4FA85F", "出手极快，血薄，靠频率取胜"],
            ["c004", "墨牙", 90, 19, 15, 22, 45, 6, 12, 60, 5, "史诗", "#3A3A3A", "牙口极好，攻击与暴击出众"],
            ["c005", "油葫芦", 135, 9, 26, 12, 62, 5, 2, 30, 8, "普通", "#B07A3A", "血厚耐打，但斗性差，容易怂"],
            ["c006", "铁砂掌", 105, 15, 24, 18, 52, 7, 8, 70, 6, "史诗", "#7A5C3A", "攻守兼备，斗性极佳，难得一遇"],
        ],
        [8, 12, 7, 7, 7, 7, 7, 10, 7, 7, 7, 8, 11, 34],
        note="主色为 16 进制 RGB，会直接决定蛐蛐身体的配色",
        highlight={1: NOTE_FILL, 3: NOTE_FILL},
    )

    # ---------- 3. 成长 ----------
    growth_rows = []
    need = 0
    for lv in range(1, 31):
        exp = 40 + (lv - 1) * 35
        need += exp
        if lv <= 10:
            hp, atk, arm, spd, sta = 10, 2, 1, 1, 3
        elif lv <= 20:
            hp, atk, arm, spd, sta = 8, 2, 2, 1, 2
        else:
            hp, atk, arm, spd, sta = 6, 3, 2, 1, 2
        growth_rows.append([lv, exp, hp, atk, arm, spd, sta, need])
    write_sheet(
        wb,
        "3-成长",
        ["等级", "本级升级经验", "HP+", "攻击+", "护甲+", "速度+", "耐力+", "累计经验"],
        growth_rows,
        [8, 14, 8, 9, 9, 9, 9, 12],
        note="升级经验 = 本级达到下一级所需；属性+ 为升到该级时的一次性增量",
    )

    # ---------- 4. 招式 ----------
    write_sheet(
        wb,
        "4-招式",
        ["ID", "名称", "类型", "伤害系数", "耐力消耗", "命中修正", "暴击修正", "附带状态", "动画", "选择权重", "描述"],
        [
            ["m001", "轻咬", "攻击", 1.0, 15, 10, 0, "", "bite", 40, "试探性的一口，命中高、消耗低"],
            ["m002", "冲撞", "攻击", 1.8, 35, -10, 10, "", "charge", 25, "全力冲撞，高伤高耗，被格挡会吃亏"],
            ["m003", "格挡", "防御", 0.0, 10, 0, 0, "s004", "guard", 20, "收翅硬抗，减伤并反弹，专克冲撞"],
            ["m004", "鸣叫", "辅助", 0.0, 8, 0, 0, "s005", "chirp", 8, "振翅示威，涨自己士气、挫对方士气"],
            ["m005", "撕咬", "攻击", 1.4, 25, 0, 5, "s002", "bite", 15, "咬住不放，造成持续流血"],
            ["m006", "摔投", "攻击", 2.2, 45, -20, 0, "s003", "throw", 7, "近身摔打，破防，但很难命中"],
        ],
        [8, 10, 8, 10, 10, 10, 10, 12, 10, 10, 40],
        note="类型：攻击 / 防御 / 辅助；选择权重用于 AI 随机选招，权重越高越常用",
        highlight={2: GOOD_FILL, 3: GOOD_FILL},
    )

    # ---------- 5. 克制 ----------
    moves = ["轻咬", "冲撞", "格挡", "鸣叫", "撕咬", "摔投"]
    counter_rows = []
    matrix = {
        ("轻咬", "格挡"): 0.45,
        ("冲撞", "格挡"): 0.30,
        ("撕咬", "格挡"): 0.50,
        ("摔投", "格挡"): 1.30,
        ("摔投", "轻咬"): 1.20,
        ("冲撞", "冲撞"): 1.10,
        ("轻咬", "鸣叫"): 1.15,
        ("冲撞", "鸣叫"): 1.15,
        ("撕咬", "撕咬"): 1.05,
    }
    for a in moves:
        row = [a]
        for b in moves:
            row.append(matrix.get((a, b), 1.0))
        counter_rows.append(row)
    ws = write_sheet(
        wb,
        "5-克制",
        ["攻方 \\ 守方"] + moves,
        counter_rows,
        [16, 10, 10, 10, 10, 10, 10],
        note="数值为伤害倍率。1.0=正常，<1=被克制，>1=克制对方。守方为「格挡」时还会触发反伤。",
    )
    for r in range(3, 3 + len(moves)):
        for c in range(2, 2 + len(moves)):
            v = ws.cell(row=r, column=c).value
            if isinstance(v, (int, float)):
                if v < 1.0:
                    ws.cell(row=r, column=c).fill = WARN_FILL
                elif v > 1.0:
                    ws.cell(row=r, column=c).fill = GOOD_FILL

    # ---------- 6. 状态 ----------
    write_sheet(
        wb,
        "6-状态",
        ["ID", "名称", "类型", "持续(秒)", "效果", "最大层数", "描述"],
        [
            ["s001", "力竭", "负面", 1.5, "无法行动，受伤+50%", 1, "耐力归零触发，恢复后耐力回满"],
            ["s002", "流血", "负面", 4.0, "每0.5秒损失3点血量", 3, "撕咬造成，可叠加"],
            ["s003", "破防", "负面", 5.0, "护甲降低30%", 1, "摔投造成，专克高护甲"],
            ["s004", "格挡", "正面", 0.8, "受到伤害-60%，反弹30%", 1, "格挡招式自带"],
            ["s005", "士气高涨", "正面", 6.0, "攻击+15%", 1, "鸣叫时自身获得"],
            ["s006", "畏缩", "负面", 4.0, "攻击-20%，士气加速下降", 1, "鸣叫时对方获得"],
        ],
        [8, 12, 8, 11, 26, 10, 34],
        note="最大层数 1 表示不可叠加，刷新持续时间",
        highlight={0: WARN_FILL, 1: WARN_FILL, 2: WARN_FILL, 5: WARN_FILL},
    )

    # ---------- 7. 战斗常数 ----------
    write_sheet(
        wb,
        "7-战斗常数",
        ["参数", "值", "单位", "说明"],
        [
            ["TICK", 0.1, "秒", "战斗逻辑推进间隔"],
            ["ARM_K", 100, "-", "护甲减伤公式分母：减伤 = ARM/(ARM+ARM_K)"],
            ["BASE_INTERVAL", 1.2, "秒", "基准速度下的出手间隔"],
            ["REF_SPD", 20, "-", "基准速度：出手间隔 = 基础间隔 × 基准速度 / 实际速度"],
            ["MIN_INTERVAL", 0.25, "秒", "出手间隔下限，防止速度过高导致无限连击"],
            ["EXHAUST_TIME", 1.5, "秒", "力竭持续时间"],
            ["EXHAUST_VULN", 0.5, "-", "力竭期间额外受伤比例(+50%)"],
            ["CRIT_MULT", 1.5, "倍", "暴击伤害倍率"],
            ["BLOCK_REDUCE", 0.6, "-", "格挡减伤比例"],
            ["BLOCK_REFLECT", 0.3, "-", "格挡反弹伤害比例"],
            ["BATTLE_TIME", 60, "秒", "战斗总时长上限"],
            ["SUDDEN_DEATH", 45, "秒", "突然死亡起始时间"],
            ["SUDDEN_DEATH_RATE", 0.05, "-", "突然死亡后每秒伤害递增"],
            ["MORALE_FLEE", 30, "-", "士气低于此值后可能逃跑"],
            ["MORALE_LOSS_PER_DMG", 0.35, "-", "每点伤害扣除的士气"],
            ["MORALE_CRIT_LOSS", 3.0, "-", "被暴击时额外扣除士气"],
            ["CHIRP_SELF_MORALE", 12, "-", "鸣叫时自身回复士气"],
            ["CHIRP_FOE_MORALE", 8, "-", "鸣叫时对方扣除士气"],
            ["MIN_DAMAGE", 1, "-", "单次伤害保底值，避免完全无伤"],
            ["BLEED_INTERVAL", 0.5, "秒", "流血跳伤害间隔"],
            ["BLEED_PER_TICK", 3, "-", "每层流血每次跳的伤害"],
        ],
        [24, 10, 8, 46],
        note="改这些参数会直接影响全部战斗手感，建议一次只调一个",
    )

    # ---------- 8. 天赋 ----------
    write_sheet(
        wb,
        "8-天赋",
        ["ID", "名称", "效果类型", "参数", "稀有度", "描述"],
        [
            ["t001", "铁壳", "属性倍率", "arm*1.15", "普通", "护甲提升15%"],
            ["t002", "快腿", "属性倍率", "spd*1.20", "普通", "速度提升20%"],
            ["t003", "咬肌发达", "属性倍率", "atk*1.15", "稀有", "攻击提升15%"],
            ["t004", "肺活量", "属性倍率", "sta_regen*1.50", "稀有", "耐力回复提升50%"],
            ["t005", "厚甲", "属性加成", "arm+30", "稀有", "护甲直接+30"],
            ["t006", "大牙", "属性加成", "crit+15", "稀有", "暴击率+15%"],
            ["t007", "越战越勇", "条件触发", "hp<30%:atk*1.30", "史诗", "血量低于30%时攻击+30%"],
            ["t008", "铁胆", "属性倍率", "guts*1.60", "史诗", "斗性提升60%，极难被吓跑"],
            ["t009", "孬种", "属性倍率", "guts*0.50", "负面", "斗性减半，士气掉得快"],
            ["t010", "虚胖", "属性倍率", "hp*1.20;spd*0.85", "负面", "血量+20%但速度-15%"],
        ],
        [8, 12, 12, 22, 8, 34],
        note="效果类型：属性倍率 / 属性加成 / 条件触发。负面天赋用红底标记。",
        highlight={8: WARN_FILL, 9: WARN_FILL},
    )

    os.makedirs(OUT_DIR, exist_ok=True)
    wb.save(OUT_FILE)
    return OUT_FILE


if __name__ == "__main__":
    path = build()
    print("已生成:", path)
    print("大小: %.1f KB" % (os.path.getsize(path) / 1024))
