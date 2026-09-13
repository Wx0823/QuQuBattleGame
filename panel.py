# -*- coding: utf-8 -*-
"""蛐蛐属性面板。

数据全部来自数值表（stats.StatsDB），面板只负责展示。
可拖动，右上角关闭，再次打开会刷新为最新数值。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QPoint, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from stats import StatsDB, fmt_num

BG = QColor(26, 32, 42, 238)
LINE = QColor(255, 255, 255, 28)
TXT = "#E8EDF2"
SUB = "#8B97A6"
ACCENT = "#8FD14F"


class StatsPanel(QWidget):
    W, H = 296, 392

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
        super().__init__()
        self.pet = pet
        self.db = StatsDB()
        self._drag = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(self.W, self.H)
        self.setWindowTitle("蛐蛐属性")

        self._build()
        self.refresh()

    # ---------- UI ----------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 16)
        root.setSpacing(6)

        head = QHBoxLayout()
        self.title = QLabel("蛐蛐")
        self.title.setStyleSheet(f"color:{TXT}; font-size:15px; font-weight:600;")
        self.title.setFont(QFont("Microsoft YaHei", 11))
        head.addWidget(self.title)
        head.addStretch()
        btn = QPushButton("✕")
        btn.setFixedSize(22, 22)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton{color:#8B97A6; background:transparent; border:none; font-size:13px;}"
            "QPushButton:hover{color:#FFFFFF;}"
        )
        btn.clicked.connect(self.hide)
        head.addWidget(btn)
        root.addLayout(head)

        self.sub = QLabel("")
        self.sub.setStyleSheet(f"color:{SUB}; font-size:11px;")
        root.addWidget(self.sub)

        root.addSpacing(6)
        root.addWidget(self._sep())

        # 属性行一次性建好，刷新时只改文本 —— 避免反复创建销毁造成重影
        self.grid = QGridLayout()
        self.grid.setSpacing(5)
        self.grid.setColumnStretch(0, 0)
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

        root.addSpacing(4)
        root.addWidget(self._sep())
        root.addSpacing(2)

        self.sec = QLabel("")
        self.sec.setStyleSheet(f"color:{SUB}; font-size:11px;")
        root.addWidget(self.sec)

        root.addSpacing(2)
        root.addWidget(self._sep())

        self.talent = QLabel("天赋：无")
        self.talent.setStyleSheet(f"color:{TXT}; font-size:11px;")
        self.talent.setWordWrap(True)
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

    def _sep(self) -> QLabel:
        """分隔线。用 QLabel 而不是 QFrame —— QFrame 在离屏渲染时会画出多余底块。"""
        f = QLabel()
        f.setFixedHeight(1)
        f.setStyleSheet("background-color: rgba(255,255,255,0.10); border: none;")
        return f

    # ---------- 数据 ----------

    def refresh(self) -> None:
        pet = self.pet
        sp = self.db.species(pet.species_id) or {}
        stats = pet.stats

        self.title.setText(f"{sp.get('名称', '蛐蛐')}  Lv.{pet.level}")
        self.sub.setText(
            f"{sp.get('稀有度', '')} · 已累计 {pet.total_xp} 经验 · "
            f"再 {max(0, self.db.exp_need(pet.level) - pet.xp)} 升级"
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

        names = []
        for tid in pet.talents:
            t = self.db.talent(tid)
            if t:
                names.append(t.get("名称", tid))
        self.talent.setText("天赋：" + ("、".join(names) if names else "无"))

        self.power.setText(fmt_num(round(self.db.power(stats))))

    # ---------- 行为 ----------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BG)
        p.drawRoundedRect(QRectF(0.5, 0.5, self.W - 1, self.H - 1), 14, 14)
        p.setPen(QPen(LINE, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(0.5, 0.5, self.W - 1, self.H - 1), 14, 14)
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
        """显示在蛐蛐旁边，默认放左侧，放不下就放右侧。"""
        self.refresh()
        g = anchor.frameGeometry()
        x = g.left() - self.W - 12
        if x < 0:
            x = g.right() + 12
        y = max(0, g.bottom() - self.H)
        self.move(x, y)
        self.show()
        self.raise_()
