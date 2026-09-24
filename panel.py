# -*- coding: utf-8 -*-
"""面板组件。

CardPanel     通用深色卡片窗口（圆角、可拖动、右上角关闭），设置面板与属性面板共用
CricketPortrait  蛐蛐大头照，会跟着主程序的状态动（呼吸/眨眼）
StatsPanel    属性面板：大头照 + 等级经验 + 全部属性 + 天赋 + 战力
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QProgressBar,
                               QPushButton, QVBoxLayout, QWidget)

from cricket import paint_cricket
from stats import StatsDB, fmt_num
from ui_theme import draw_card, PANEL_CSS

BG = QColor(26, 32, 42, 238)
LINE = QColor(255, 255, 255, 28)
TXT = "#EEE6D6"
SUB = "#AAA698"
ACCENT = "#D6B778"
FADE = "#55606E"


class CardPanel(QWidget):
    """通用深色卡片窗口：无边框、圆角、可拖动、右上角关闭。"""

    def __init__(self, title: str, w: int, h: int):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(w, h)
        self.setWindowTitle(title)
        self._drag = None
        self._title_text = title
        self.setStyleSheet(PANEL_CSS)

    def build_header(self, root: QVBoxLayout) -> None:
        head = QHBoxLayout()
        t = QLabel(self._title_text)
        t.setFont(QFont("Microsoft YaHei", 11))
        t.setStyleSheet(f"color:{TXT}; font-size:15px; font-weight:600;")
        head.addWidget(t)
        head.addStretch()
        btn = QPushButton("×")
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton{color:#8B97A6; background:transparent; border:none; font-size:13px;}"
            "QPushButton:hover{color:#FFFFFF;}"
        )
        btn.clicked.connect(self.hide)
        head.addWidget(btn)
        root.addLayout(head)

    def sep(self) -> QLabel:
        """分隔线。不用 QFrame —— 离屏渲染时 QFrame 会画出多余底块。"""
        f = QLabel()
        f.setFixedHeight(1)
        f.setStyleSheet("background-color: rgba(255,255,255,0.10); border: none;")
        return f

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        draw_card(p, r, ornaments=True)
        p.end()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.pos()
            e.accept()

    def mouseMoveEvent(self, e) -> None:
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)
            e.accept()

    def mouseReleaseEvent(self, e) -> None:
        self._drag = None

    def show_near(self, anchor: QWidget) -> None:
        """显示在蛐蛐旁边，默认左侧，放不下就放右侧。"""
        from window_layout import place_panel
        place_panel(self, anchor)
        self.show()
        self.raise_()


class CricketPortrait(QWidget):
    """蛐蛐大头照。复用主程序的 Cricket 状态，所以会呼吸、眨眼、偶尔蹦一下。"""

    def __init__(self, pet, size: int = 118):
        super().__init__()
        self.pet = pet
        self.size = size
        self.setFixedSize(size, size)
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.update)

    def showEvent(self, e) -> None:
        self.timer.start()

    def hideEvent(self, e) -> None:
        self.timer.stop()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        s = self.size
        # 底托
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 14))
        p.drawEllipse(QRectF(2, 2, s - 4, s - 4))

        scale = s / 108.0
        cx = s / 2 - 6 * scale      # 蛐蛐本地 x 中心偏右 7，往左拉回一点
        foot_y = s * 0.90
        paint_cricket(p, cx, foot_y, scale, self.pet.cricket, self.pet.palette)
        p.end()


class StatsPanel(CardPanel):
    W, H = 320, 452

    ROWS = [
        ("血量", "#FF7B72"),
        ("耐力", "#79C0FF"),
        ("攻击", "#FFA657"),
        ("护甲", "#A5D6FF"),
        ("速度", "#D2A8FF"),
        ("出手间隔", SUB),
        ("护甲减伤", SUB),
    ]

    def __init__(self, pet):
        super().__init__("蛐蛐属性", self.W, self.H)
        self.pet = pet
        self.db = StatsDB()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 16)
        root.setSpacing(6)
        self.build_header(root)

        # ---- 大头照 + 等级经验 ----
        top = QHBoxLayout()
        top.setSpacing(14)
        self.portrait = CricketPortrait(pet, 118)
        top.addWidget(self.portrait)

        info = QVBoxLayout()
        info.setSpacing(4)
        self.name = QLabel("蛐蛐")
        self.name.setFont(QFont("Microsoft YaHei", 12))
        self.name.setStyleSheet(f"color:{TXT}; font-size:19px; font-weight:600;")
        info.addWidget(self.name)

        self.meta = QLabel("")
        self.meta.setStyleSheet(f"color:{SUB}; font-size:11px;")
        info.addWidget(self.meta)

        info.addSpacing(6)
        self.bar = QProgressBar()
        self.bar.setFixedHeight(9)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet(
            "QProgressBar{background:rgba(255,255,255,0.10); border:none; border-radius:4px;}"
            "QProgressBar::chunk{background:#8FD14F; border-radius:4px;}"
        )
        info.addWidget(self.bar)

        self.exp = QLabel("")
        self.exp.setStyleSheet(f"color:{SUB}; font-size:11px;")
        info.addWidget(self.exp)
        info.addStretch()
        top.addLayout(info, 1)
        root.addLayout(top)

        root.addSpacing(8)
        root.addWidget(self.sep())
        root.addSpacing(4)

        self.grid = QGridLayout()
        self.grid.setSpacing(5)
        root.addLayout(self.grid)
        self._rows = []
        for i, (name, color) in enumerate(self.ROWS):
            n = QLabel(name)
            n.setStyleSheet(f"color:{SUB}; font-size:12px;")
            v = QLabel("--")
            v.setStyleSheet(f"color:{color}; font-size:12px; font-weight:600;")
            self.grid.addWidget(n, i, 0)
            self.grid.addWidget(v, i, 1)
            self._rows.append(v)

        root.addSpacing(6)
        root.addWidget(self.sep())
        root.addSpacing(4)

        self.sec = QLabel("")
        self.sec.setStyleSheet(f"color:{SUB}; font-size:11px;")
        root.addWidget(self.sec)

        root.addSpacing(4)
        root.addWidget(self.sep())
        root.addSpacing(2)

        self.talent = QLabel("天赋：无")
        self.talent.setStyleSheet(f"color:{TXT}; font-size:11px;")
        root.addWidget(self.talent)

        root.addStretch()

        foot = QHBoxLayout()
        pl = QLabel("战力")
        pl.setStyleSheet(f"color:{SUB}; font-size:11px;")
        foot.addWidget(pl)
        foot.addStretch()
        self.power = QLabel("0")
        self.power.setStyleSheet(f"color:{ACCENT}; font-size:20px; font-weight:600;")
        foot.addWidget(self.power)
        root.addLayout(foot)

        self.refresh()

    def refresh(self) -> None:
        import equipment
        pet = self.pet
        sp = self.db.species(pet.species_id) or {}
        stats = equipment.effective_stats(
            self.db, pet.species_id, pet.level, pet.talents)
        need = self.db.exp_need(pet.level)

        self.name.setText(f"{sp.get('名称', '蛐蛐')}  Lv.{pet.level}")
        self.meta.setText(f"{sp.get('稀有度', '')} · {sp.get('描述', '')}")
        self.bar.setMaximum(max(1, need))
        self.bar.setValue(min(int(pet.xp), need))
        self.exp.setText(
            f"经验 {pet.xp} / {need}　（还差 {max(0, need - pet.xp)}）　累计 {pet.total_xp}"
        )

        iv = self.db.attack_interval(stats.get("spd", 1))
        arm = float(stats.get("arm", 0))
        red = 100 * arm / (arm + float(self.db.const("ARM_K", 100)))
        vals = [
            fmt_num(stats.get("hp", 0)),
            fmt_num(stats.get("sta", 0)),
            fmt_num(stats.get("atk", 0)),
            fmt_num(stats.get("arm", 0)),
            fmt_num(stats.get("spd", 0)),
            f"{iv:.2f} 秒",
            f"{red:.0f}%",
        ]
        for lbl, txt in zip(self._rows, vals):
            lbl.setText(txt)

        self.sec.setText(
            f"耐力回复 {fmt_num(stats.get('sta_regen', 0))}/秒　"
            f"暴击 {fmt_num(stats.get('crit', 0))}%　"
            f"韧性 {fmt_num(stats.get('tough', 0))}　"
            f"破甲 {fmt_num(stats.get('pen', 0))}\n"
            f"斗性 {fmt_num(stats.get('guts', 0))}　"
            f"体重 {fmt_num(stats.get('weight', 0))}　"
            f"士气 {fmt_num(stats.get('morale', 100))}"
        )

        names = [self.db.talent(t).get("名称", t)
                 for t in pet.talents if self.db.talent(t)]
        self.talent.setText("天赋：" + ("、".join(names) if names else "无"))
        self.power.setText(fmt_num(round(self.db.power(stats))))

    def show_near(self, anchor: QWidget) -> None:
        self.refresh()
        super().show_near(anchor)
