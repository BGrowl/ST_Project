import sys
import re
import time
import math
from collections import deque

import serial
import serial.tools.list_ports
import numpy as np

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QComboBox, QFrame, QProgressBar
)
from PyQt6.QtCore import QTimer, Qt, QRectF, QPointF, QTime
from PyQt6.QtGui import QFont, QPainter, QColor, QLinearGradient, QPen, QBrush

import pyqtgraph as pg


class HrvWatchWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.hrv_ms = None
        self.mode = "idle"
        self.progress = 0
        self.phase = 0.0
        self.setMinimumSize(360, 360)

        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.tick)
        self.animation_timer.start(45)

    def tick(self):
        self.phase = (self.phase + 0.11) % (math.pi * 2)
        self.update()

    def set_state(self, mode, hrv_ms=None, progress=0):
        self.mode = mode
        self.hrv_ms = hrv_ms
        self.progress = max(0, min(100, int(progress)))
        self.update()

    def hrv_level(self):
        if self.hrv_ms is None:
            return "idle"
        if self.hrv_ms >= 80:
            return "excellent"
        if self.hrv_ms >= 50:
            return "normal"
        if self.hrv_ms >= 25:
            return "caution"
        return "overload"

    def describe_hrv(self, hrv_ms):
        if hrv_ms is None:
            return "准备测量", QColor("#94a3b8")
        if hrv_ms >= 80:
            return "状态优秀", QColor("#58c995")
        if hrv_ms >= 50:
            return "状态正常", QColor("#8fa0df")
        if hrv_ms >= 25:
            return "注意压力", QColor("#ff9f6e")
        return "压力过载", QColor("#f85f82")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        side = min(self.width(), self.height()) - 18
        card = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        pulse = (math.sin(self.phase) + 1.0) / 2.0

        bg = QLinearGradient(card.topLeft(), card.bottomRight())
        level = self.hrv_level()
        if self.mode == "idle":
            bg.setColorAt(0.0, QColor("#eef6f4"))
            bg.setColorAt(0.62, QColor("#dbeee8"))
            bg.setColorAt(1.0, QColor("#cad8e2"))
        elif self.mode == "measuring":
            bg.setColorAt(0.0, QColor("#daf8ed"))
            bg.setColorAt(0.55, QColor("#a6ead0"))
            bg.setColorAt(1.0, QColor("#f8c5b4"))
        elif level == "excellent":
            bg.setColorAt(0.0, QColor("#ddfaeb"))
            bg.setColorAt(0.62, QColor("#a6e7c7"))
            bg.setColorAt(1.0, QColor("#f4c6ca"))
        elif level == "normal":
            bg.setColorAt(0.0, QColor("#e4e9ff"))
            bg.setColorAt(0.62, QColor("#b9c5f0"))
            bg.setColorAt(1.0, QColor("#d7efe9"))
        elif level == "caution":
            bg.setColorAt(0.0, QColor("#ffe6d5"))
            bg.setColorAt(0.60, QColor("#ffb07a"))
            bg.setColorAt(1.0, QColor("#f7d8c7"))
        else:
            bg.setColorAt(0.0, QColor("#ffd3dc"))
            bg.setColorAt(0.60, QColor("#fb5f84"))
            bg.setColorAt(1.0, QColor("#ffc3aa"))

        painter.setPen(QPen(QColor(255, 255, 255, 42), 1))
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(card, 34, 34)

        ring = QRectF(card).adjusted(14 - pulse * 7, 14 - pulse * 7, -14 + pulse * 7, -14 + pulse * 7)
        painter.setPen(QPen(QColor(255, 255, 255, int(36 + 78 * pulse)), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(ring, 28, 28)

        top_band = QRectF(card.left(), card.top(), card.width(), card.height() * 0.15)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(15, 23, 42, 88))
        painter.drawRoundedRect(top_band, 30, 30)

        painter.setPen(QColor("#f8fafc"))
        painter.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
        top_text = "按住测量" if self.mode == "idle" else ("测量中" if self.mode == "measuring" else "本次结果")
        painter.drawText(QRectF(card.left() + 18, card.top() + 13, 92, 26), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, top_text)
        painter.drawText(QRectF(card.right() - 92, card.top() + 13, 74, 26), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, QTime.currentTime().toString("HH:mm"))

        face_radius = side * (0.17 + 0.028 * pulse)
        center = QPointF(card.center().x(), card.top() + side * (0.37 - 0.018 * pulse))
        painter.setPen(Qt.PenStyle.NoPen)
        face_colors = {
            "idle": "#c9d4df",
            "excellent": "#69c996",
            "normal": "#9aa8df",
            "caution": "#ffa673",
            "overload": "#fb5f84",
        }
        painter.setBrush(QColor(face_colors.get(level, "#93f5b2")))
        painter.drawEllipse(center, face_radius, face_radius)

        if self.mode == "idle":
            self.draw_waiting_face(painter, center, face_radius)
        elif self.mode == "measuring":
            self.draw_measuring_face(painter, center, face_radius, pulse)
        else:
            self.draw_result_face(painter, center, face_radius, pulse)

        if self.mode == "done":
            status, color = self.describe_hrv(self.hrv_ms)
            value_text = f"{self.hrv_ms:.0f} ms" if self.hrv_ms is not None else "-- ms"
        elif self.mode == "measuring":
            status, color = "保持不动", QColor("#ecfeff")
            value_text = "测量中"
        else:
            status, color = "等待手指", QColor("#cbd5e1")
            value_text = "-- ms"

        painter.setPen(color)
        painter.setFont(QFont("Microsoft YaHei", 15, QFont.Weight.Bold))
        painter.drawText(QRectF(card.left() + 24, card.top() + side * 0.60, side - 48, 32), Qt.AlignmentFlag.AlignCenter, f"{status} · {value_text}")

        bar = QRectF(card.left() + 34, card.top() + side * 0.76, side - 68, 10)
        gradient = QLinearGradient(bar.topLeft(), bar.topRight())
        gradient.setColorAt(0.0, QColor("#fb7185"))
        gradient.setColorAt(0.45, QColor("#fbbf24"))
        gradient.setColorAt(0.72, QColor("#86efac"))
        gradient.setColorAt(1.0, QColor("#38bdf8"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(bar, 5, 5)

        if self.mode == "done" and self.hrv_ms is not None:
            marker_value = max(10, min(120, self.hrv_ms))
            marker_x = bar.left() + (marker_value - 10) / 110 * bar.width()
        else:
            marker_x = bar.left() + self.progress / 100 * bar.width()
        painter.setBrush(QColor("#0f172a"))
        painter.drawEllipse(QPointF(marker_x, bar.center().y()), 8, 8)
        painter.setBrush(QColor("#a7f3d0"))
        painter.drawEllipse(QPointF(marker_x, bar.center().y()), 4, 4)

    def draw_waiting_face(self, painter, center, r):
        painter.setPen(QPen(QColor("#064e3b"), 3))
        painter.drawArc(QRectF(center.x() - r * 0.46, center.y() - r * 0.18, r * 0.32, r * 0.22), 200 * 16, 140 * 16)
        painter.drawArc(QRectF(center.x() + r * 0.14, center.y() - r * 0.18, r * 0.32, r * 0.22), 200 * 16, 140 * 16)
        painter.setFont(QFont("Arial", 17, QFont.Weight.Bold))
        painter.drawText(QRectF(center.x() - 24, center.y() + 6, 48, 26), Qt.AlignmentFlag.AlignCenter, "...")

    def draw_measuring_face(self, painter, center, r, pulse):
        painter.setPen(QPen(QColor("#064e3b"), 4))
        painter.drawPoint(QPointF(center.x() - r * 0.32, center.y() - r * 0.10))
        painter.drawPoint(QPointF(center.x() + r * 0.32, center.y() - r * 0.10))
        painter.setPen(QPen(QColor("#064e3b"), 2))
        painter.drawArc(QRectF(center.x() - 12, center.y() + 8, 24, 12), 200 * 16, 140 * 16)
        painter.setPen(QColor("#ecfeff"))
        painter.setFont(QFont("Arial", int(r * (0.36 + pulse * 0.08)), QFont.Weight.Bold))
        painter.drawText(QRectF(center.x() + r * 0.36, center.y(), 34, 34), Qt.AlignmentFlag.AlignCenter, "♥")

    def draw_result_face(self, painter, center, r, pulse):
        level = self.hrv_level()
        ink = QColor("#111827")
        painter.setPen(QPen(ink, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))

        if level == "excellent":
            painter.setBrush(ink)
            y = center.y() - r * 0.26
            painter.drawRoundedRect(QRectF(center.x() - r * 0.58, y, r * 0.44, r * 0.25), 5, 5)
            painter.drawRoundedRect(QRectF(center.x() + r * 0.12, y, r * 0.44, r * 0.25), 5, 5)
            painter.drawLine(QPointF(center.x() - r * 0.14, y + 5), QPointF(center.x() + r * 0.12, y + 5))
            painter.setPen(QPen(ink, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(center.x() - r * 0.16, center.y() + r * 0.24), QPointF(center.x() + r * 0.14, center.y() + r * 0.18))
        elif level == "normal":
            painter.drawArc(QRectF(center.x() - r * 0.48, center.y() - r * 0.34, r * 0.28, r * 0.14), 55 * 16, 70 * 16)
            painter.drawArc(QRectF(center.x() + r * 0.20, center.y() - r * 0.34, r * 0.28, r * 0.14), 55 * 16, 70 * 16)
            painter.drawPoint(QPointF(center.x() - r * 0.35, center.y() - r * 0.08))
            painter.drawPoint(QPointF(center.x() + r * 0.35, center.y() - r * 0.08))
            painter.drawArc(QRectF(center.x() - r * 0.12, center.y() + r * 0.08, r * 0.24, r * 0.16), 205 * 16, 125 * 16)
        elif level == "caution":
            painter.drawArc(QRectF(center.x() - r * 0.42, center.y() - r * 0.30, r * 0.30, r * 0.16), 205 * 16, 130 * 16)
            painter.drawArc(QRectF(center.x() + r * 0.12, center.y() - r * 0.30, r * 0.30, r * 0.16), 205 * 16, 130 * 16)
            painter.drawArc(QRectF(center.x() - r * 0.25, center.y() + r * 0.04, r * 0.50, r * 0.30), 205 * 16, 130 * 16)
        else:
            painter.drawArc(QRectF(center.x() - r * 0.46, center.y() - r * 0.30, r * 0.30, r * 0.18), 25 * 16, 110 * 16)
            painter.drawArc(QRectF(center.x() + r * 0.16, center.y() - r * 0.30, r * 0.30, r * 0.18), 25 * 16, 110 * 16)
            painter.drawArc(QRectF(center.x() - r * 0.20, center.y() + r * 0.10, r * 0.40, r * 0.25), 20 * 16, 140 * 16)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 235, 240, int(150 + 80 * pulse)))
            painter.drawEllipse(QPointF(center.x() + r * 0.56, center.y() - r * (0.06 + 0.08 * pulse)), r * 0.09, r * 0.13)

        heart_alpha = int(70 + 145 * pulse)
        painter.setPen(QColor(255, 245, 248, heart_alpha))
        painter.setFont(QFont("Arial", int(r * (0.40 + pulse * 0.08)), QFont.Weight.Bold))
        painter.drawText(QRectF(center.x() + r * 0.34, center.y() - r * 0.04, 38, 36), Qt.AlignmentFlag.AlignCenter, "♥")


class Max30105Dashboard(QWidget):
    TARGET_RR_COUNT = 8
    DISCARD_RR_COUNT = 3
    MIN_VALID_RR = 450
    MAX_VALID_RR = 1400
    MAX_RR_JUMP = 220
    MAX_HRV_RMSSD = 150
    PI_WINDOW_SIZE = 40
    PPG_WARMUP_SECONDS = 1.5

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MAX30105 HRV 测量")
        self.resize(1180, 760)

        self.serial_port = None
        self.is_connected = False
        self.max_points = 180
        self.time_data = deque(maxlen=self.max_points)
        self.bpm_data = deque(maxlen=self.max_points)
        self.avg_bpm_data = deque(maxlen=self.max_points)
        self.ir_data = deque(maxlen=self.max_points)
        self.ppg_time_data = deque(maxlen=self.max_points)
        self.rr_intervals = deque(maxlen=80)
        self.rr_seen_count = 0
        self.finger_on = False
        self.low_signal_count = 0
        self.measurement_done = False
        self.final_hrv = None
        self.latest_pi_value = None
        self.measurement_start_time = None
        self.ppg_recording_started = False
        self.last_plot_time = 0.0
        self.last_pi_time = 0.0
        self.cached_pi_value = None
        self.start_time = time.time()

        self.pattern = re.compile(r"IR\s*=\s*(\d+)\s*,\s*BPM\s*=\s*([0-9.]+)\s*,\s*Avg\s*BPM\s*=\s*(\d+)", re.IGNORECASE)
        self.hrv_pattern = re.compile(r"HRV\s*=\s*([0-9.]+)\s*(?:ms)?", re.IGNORECASE)
        self.rr_pattern = re.compile(r"(?:RR|IBI)\s*=\s*([0-9.]+)\s*(?:ms)?", re.IGNORECASE)
        self.pi_pattern = re.compile(r"PI\s*=\s*([0-9.]+)\s*(?:%)?", re.IGNORECASE)
        self.ready_pattern = re.compile(r"HRV_READY\s*=\s*([01])", re.IGNORECASE)

        self.init_ui()
        self.timer = QTimer()
        self.timer.timeout.connect(self.read_serial_data)
        self.timer.start(50)

    def init_ui(self):
        self.setStyleSheet("""
            QWidget { background-color: #eaf7f1; color: #111827; font-family: Microsoft YaHei; }
            QLabel { color: #111827; background: transparent; }
            QPushButton {
                background-color: #111827; color: white; border-radius: 8px;
                padding: 9px 16px; font-size: 14px; font-weight: 700;
            }
            QPushButton:hover { background-color: #263244; }
            QPushButton:pressed { background-color: #020617; }
            QComboBox {
                background-color: white; color: #111827; border: 1px solid #dbe3ef;
                border-radius: 8px; padding: 8px; font-size: 14px;
            }
            QProgressBar {
                background-color: #e5e7eb; border: none; border-radius: 5px; height: 10px; text-align: center;
            }
            QProgressBar::chunk { background-color: #58c995; border-radius: 5px; }
        """)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(26, 20, 26, 22)
        main_layout.setSpacing(16)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("PulseWave-PI")
        title.setFont(QFont("Microsoft YaHei", 25, QFont.Weight.Bold))
        subtitle = QLabel("指夹式外周循环监测系统 · PPG 脉搏波与灌注指数原型")
        subtitle.setStyleSheet("color: #64748b; font-size: 13px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        control = QHBoxLayout()
        self.port_box = QComboBox()
        self.refresh_ports()
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self.refresh_ports)
        self.connect_button = QPushButton("连接")
        self.connect_button.clicked.connect(self.toggle_connection)
        control.addWidget(QLabel("串口"))
        control.addWidget(self.port_box)
        control.addWidget(self.refresh_button)
        control.addWidget(self.connect_button)

        header.addLayout(title_box, stretch=1)
        header.addLayout(control)
        main_layout.addLayout(header)

        self.status_label = QLabel("未连接")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("background-color: #fff7ed; color: #c2410c; border: 1px solid #fed7aa; border-radius: 8px; padding: 8px; font-weight: 700;")
        main_layout.addWidget(self.status_label)

        content = QHBoxLayout()
        content.setSpacing(18)

        left = QVBoxLayout()
        left.setSpacing(14)
        self.hrv_watch = HrvWatchWidget()
        left.addWidget(self.hrv_watch, stretch=1)
        left.addWidget(self.create_measurement_panel())

        right = QVBoxLayout()
        right.setSpacing(14)
        card_grid = QGridLayout()
        card_grid.setSpacing(12)
        self.bpm_card = self.create_card("当前 BPM", "---", "实时心率")
        self.avg_card = self.create_card("平均 BPM", "---", "平滑心率")
        self.pi_card = self.create_card("PI", "-- %", "灌注指数")
        self.signal_card = self.create_card("信号质量", "未检测", "由 PI / PPG / RR 判断")
        self.rr_card = self.create_card("最近 RR", "-- ms", "心跳间隔")
        cards = [self.bpm_card, self.avg_card, self.pi_card, self.signal_card, self.rr_card]
        for i, card in enumerate(cards):
            card_grid.addWidget(card["frame"], i // 2, i % 2)
        right.addLayout(card_grid)
        pg.setConfigOptions(antialias=True)
        self.ppg_plot = self.create_plot("PPG waveform", "IR")
        self.ppg_curve = self.ppg_plot.plot(pen=pg.mkPen("#38bdf8", width=2))
        right.addWidget(self.ppg_plot, stretch=1)
        self.bpm_plot = self.create_plot("Heart Rate Trend", "BPM")
        self.bpm_plot.setYRange(45, 140)
        self.bpm_curve = self.bpm_plot.plot(pen=pg.mkPen("#ef4444", width=2))
        self.avg_curve = self.bpm_plot.plot(pen=pg.mkPen("#10b981", width=3))
        right.addWidget(self.bpm_plot, stretch=1)
        right.addWidget(self.create_note_panel())

        content.addLayout(left, stretch=5)
        content.addLayout(right, stretch=6)
        main_layout.addLayout(content, stretch=1)
        self.setLayout(main_layout)
        self.set_measurement_idle()

    def create_measurement_panel(self):
        frame = self.panel_frame()
        layout = QVBoxLayout()
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        self.measurement_title = QLabel("等待手指放上去")
        self.measurement_title.setFont(QFont("Microsoft YaHei", 15, QFont.Weight.Bold))
        self.measurement_desc = QLabel("保持手指轻放且不要晃动，结果会像手表卡片一样固定显示。")
        self.measurement_desc.setStyleSheet("color: #64748b; font-size: 13px;")
        self.measurement_desc.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.measurement_title)
        layout.addWidget(self.measurement_desc)
        layout.addWidget(self.progress_bar)
        frame.setLayout(layout)
        return frame

    def create_note_panel(self):
        frame = self.panel_frame()
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 14, 16, 14)
        title = QLabel("测量方式")
        title.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        body = QLabel("按下后收集 8 个有效 RR/IBI，完成后显示一次 HRV。松开手指会清空本次数据，下次按压重新测量。")
        body.setStyleSheet("color: #64748b; font-size: 13px;")
        body.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(body)
        frame.setLayout(layout)
        return frame

    def panel_frame(self):
        frame = QFrame()
        frame.setStyleSheet("QFrame { background-color: rgba(255, 255, 255, 238); border: 1px solid #d9eee5; border-radius: 8px; }")
        return frame

    def create_card(self, title, value, desc):
        frame = self.panel_frame()
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(5)
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #64748b; font-size: 12px;")
        value_label = QLabel(value)
        value_label.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        value_label.setStyleSheet("color: #0f172a;")
        desc_label = QLabel(desc)
        desc_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addWidget(desc_label)
        frame.setLayout(layout)
        return {"frame": frame, "title": title_label, "value": value_label, "desc": desc_label}

    def create_plot(self, title, left_label):
        plot = pg.PlotWidget()
        plot.setBackground("#ffffff")
        plot.setTitle(title, color="#111827", size="13pt")
        plot.setLabel("left", left_label, color="#64748b")
        plot.setLabel("bottom", "Time", units="s", color="#64748b")
        plot.showGrid(x=True, y=True, alpha=0.16)
        for axis in ("left", "bottom"):
            plot.getAxis(axis).setPen(pg.mkPen("#cbd5e1"))
            plot.getAxis(axis).setTextPen(pg.mkPen("#64748b"))
        return plot

    def refresh_ports(self):
        self.port_box.clear()
        for port in serial.tools.list_ports.comports():
            self.port_box.addItem(port.device)
        if self.port_box.count() == 0:
            self.port_box.addItem("未找到串口")
        index = self.port_box.findText("COM5")
        if index >= 0:
            self.port_box.setCurrentIndex(index)

    def toggle_connection(self):
        self.connect_serial() if not self.is_connected else self.disconnect_serial()

    def connect_serial(self):
        port_name = self.port_box.currentText()
        if port_name == "未找到串口":
            self.set_status("未找到串口", "error")
            return
        try:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
            self.serial_port = serial.Serial(port=port_name, baudrate=115200, timeout=0.01)
            time.sleep(1.5)
            self.serial_port.reset_input_buffer()
            self.is_connected = True
            self.connect_button.setText("断开")
            self.set_status(f"已连接 {port_name}", "ok")
            self.reset_data()
        except Exception as e:
            self.set_status("连接失败", "error")
            print("连接失败：", e)

    def set_status(self, text, kind):
        colors = {
            "ok": ("#ecfdf5", "#047857", "#a7f3d0"),
            "error": ("#fef2f2", "#b91c1c", "#fecaca"),
            "warn": ("#fff7ed", "#c2410c", "#fed7aa"),
        }
        bg, fg, border = colors.get(kind, colors["warn"])
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"background-color: {bg}; color: {fg}; border: 1px solid {border}; border-radius: 8px; padding: 8px; font-weight: 700;")

    def reset_data(self):
        self.start_time = time.time()
        self.time_data.clear()
        self.bpm_data.clear()
        self.avg_bpm_data.clear()
        self.ir_data.clear()
        self.ppg_time_data.clear()
        self.rr_intervals.clear()
        self.rr_seen_count = 0
        self.finger_on = False
        self.low_signal_count = 0
        self.measurement_done = False
        self.final_hrv = None
        self.latest_pi_value = None
        self.cached_pi_value = None
        self.last_pi_time = 0.0
        self.last_plot_time = 0.0
        self.measurement_start_time = None
        self.ppg_recording_started = False
        self.set_measurement_idle()
        self.bpm_curve.clear()
        self.avg_curve.clear()

        self.ppg_curve.clear()
    def disconnect_serial(self):
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        self.is_connected = False
        self.connect_button.setText("连接")
        self.set_status("未连接", "warn")
        self.set_measurement_idle()

    def read_serial_data(self):
        if not self.is_connected:
            return
        try:
            latest_sample = None
            for _ in range(20):
                if self.serial_port.in_waiting <= 0:
                    break
                line = self.serial_port.readline().decode("utf-8", errors="ignore").strip()
                match = self.pattern.search(line)
                if not match:
                    continue
                hrv_match = self.hrv_pattern.search(line)
                rr_match = self.rr_pattern.search(line)
                ready_match = self.ready_pattern.search(line)
                pi_match = self.pi_pattern.search(line)
                latest_sample = (
                    int(match.group(1)),
                    float(match.group(2)),
                    int(match.group(3)),
                    float(rr_match.group(1)) if rr_match else None,
                    float(hrv_match.group(1)) if hrv_match else None,
                    int(ready_match.group(1)) if ready_match else None,
                    float(pi_match.group(1)) if pi_match else None,
                )

            if latest_sample is not None:
                self.handle_sample(*latest_sample)
        except Exception as e:
            self.set_status("串口读取异常", "error")
            print("串口读取异常：", e)

    def handle_sample(self, ir_value, bpm_value, avg_bpm_value, rr_value, explicit_hrv, ready_flag, pi_value=None):
        now = time.time()
        current_time = now - self.start_time
        # Hysteresis prevents the state from getting stuck after one completed reading.
        # Finger-on needs a clear IR rise; finger-off is accepted after a few weak samples.
        if ir_value < 50000 or ir_value >= 250000:
            self.low_signal_count += 1
        else:
            self.low_signal_count = 0

        if self.finger_on:
            finger_now = self.low_signal_count < 3
        else:
            finger_now = 52000 <= ir_value < 250000

        if finger_now and not self.finger_on:
            self.start_measurement()
        elif not finger_now and self.finger_on:
            self.set_measurement_idle()

        self.finger_on = finger_now

        self.bpm_card["value"].setText(f"{bpm_value:.1f}" if bpm_value > 0 else "---")
        self.avg_card["value"].setText(str(avg_bpm_value) if avg_bpm_value > 0 else "---")

        if finger_now:
            self.time_data.append(current_time)
            self.bpm_data.append(bpm_value)
            self.avg_bpm_data.append(avg_bpm_value)

            if self.measurement_start_time and now - self.measurement_start_time >= self.PPG_WARMUP_SECONDS:
                if not self.ppg_recording_started:
                    self.ir_data.clear()
                    self.ppg_time_data.clear()
                    self.ppg_curve.clear()
                    self.ppg_recording_started = True
                ppg_time = now - self.measurement_start_time - self.PPG_WARMUP_SECONDS
                self.ir_data.append(ir_value)
                self.ppg_time_data.append(ppg_time)

            if now - self.last_plot_time >= 0.12:
                self.update_bpm_plot()
                self.update_ppg_plot()
                self.last_plot_time = now
        else:
            self.cached_pi_value = None

        pi_value = self.update_pi_card(pi_value, finger_now)
        self.update_signal_card(ir_value, pi_value)

        if not finger_now or self.measurement_done:
            return

        if rr_value is not None and rr_value > 0:
            self.rr_card["value"].setText(f"{rr_value:.0f} ms")
            self.add_rr_if_valid(rr_value)

        progress = min(100, int(len(self.rr_intervals) / self.TARGET_RR_COUNT * 100))
        self.set_measurement_progress(progress)

        if len(self.rr_intervals) >= self.TARGET_RR_COUNT:
            hrv_value = self.calculate_rmssd()
            if self.is_valid_hrv(hrv_value):
                self.finish_measurement(hrv_value, "RR/IBI 计算")
            else:
                self.restart_hrv_collection("RR 波动过大，已重新采集。")

    def add_rr_if_valid(self, rr_value):
        if not (self.MIN_VALID_RR <= rr_value <= self.MAX_VALID_RR):
            self.rr_card["desc"].setText("RR 超出范围，已丢弃")
            return False

        self.rr_seen_count += 1
        if self.rr_seen_count <= self.DISCARD_RR_COUNT:
            self.rr_card["desc"].setText("前几拍用于稳定")
            return False

        if self.rr_intervals:
            last_rr = self.rr_intervals[-1]
            jump = abs(rr_value - last_rr)
            if jump > self.MAX_RR_JUMP or jump / last_rr > 0.25:
                self.rr_card["desc"].setText("RR 跳变过大，已丢弃")
                return False
            if jump <= 1:
                return False

        self.rr_intervals.append(rr_value)
        self.rr_card["desc"].setText(f"有效 RR {len(self.rr_intervals)}/{self.TARGET_RR_COUNT}")
        return True

    def is_valid_hrv(self, hrv_value):
        return 5 <= hrv_value <= self.MAX_HRV_RMSSD

    def restart_hrv_collection(self, message):
        self.rr_intervals.clear()
        self.rr_seen_count = 0
        self.hrv_watch.set_state("measuring", None, 0)
        self.progress_bar.setValue(0)
        self.measurement_title.setText("正在重新采集 HRV")
        self.measurement_desc.setText(message)
        self.rr_card["value"].setText("-- ms")
        self.rr_card["desc"].setText("等待稳定 RR")
    def start_measurement(self):
        self.low_signal_count = 0
        self.rr_intervals.clear()
        self.rr_seen_count = 0
        self.ir_data.clear()
        self.ppg_time_data.clear()
        self.ppg_curve.clear()
        self.ppg_recording_started = False
        self.latest_pi_value = None
        self.cached_pi_value = None
        self.last_pi_time = 0.0
        self.measurement_done = False
        self.final_hrv = None
        self.measurement_start_time = time.time()
        self.rr_card["value"].setText("-- ms")
        self.set_measurement_progress(0)

    def set_measurement_idle(self):
        self.low_signal_count = 0
        self.rr_intervals.clear()
        self.rr_seen_count = 0
        self.ir_data.clear()
        self.ppg_time_data.clear()
        self.ppg_curve.clear()
        self.ppg_recording_started = False
        self.latest_pi_value = None
        self.cached_pi_value = None
        self.last_pi_time = 0.0
        self.measurement_done = False
        self.final_hrv = None
        self.measurement_start_time = None
        self.hrv_watch.set_state("idle", None, 0)
        self.progress_bar.setValue(0)
        self.measurement_title.setText("等待手指放上去") if hasattr(self, "measurement_title") else None
        self.measurement_desc.setText("保持手指轻放且不要晃动，结果会像手表卡片一样固定显示。") if hasattr(self, "measurement_desc") else None
        if hasattr(self, "rr_card"):
            self.rr_card["value"].setText("-- ms")

    def set_measurement_progress(self, progress):
        self.hrv_watch.set_state("measuring", None, progress)
        self.progress_bar.setValue(progress)
        self.measurement_title.setText("正在采集 HRV")
        self.measurement_desc.setText("请保持手指稳定，只会记录通过质控的 RR 间隔。")

    def finish_measurement(self, hrv_value, source):
        self.measurement_done = True
        self.final_hrv = hrv_value
        self.hrv_watch.set_state("done", hrv_value, 100)
        self.progress_bar.setValue(100)
        status_text, status_color = self.hrv_watch.describe_hrv(hrv_value)
        self.measurement_title.setText("本次测量完成")
        self.measurement_desc.setText("松开手指后会清空本次结果，下次按压将重新测量。")

    def calculate_rmssd(self):
        rr = np.array(self.rr_intervals, dtype=float)
        diffs = np.diff(rr)
        return math.sqrt(float(np.mean(diffs * diffs)))

    def update_pi_card(self, pi_value, finger_now):
        if not finger_now:
            self.pi_card["value"].setText("-- %")
            self.pi_card["value"].setStyleSheet("color: #0f172a;")
            self.pi_card["desc"].setText("等待手指")
            self.latest_pi_value = None
            self.cached_pi_value = None
            return None

        now = time.time()
        if pi_value is None:
            if self.cached_pi_value is not None and now - self.last_pi_time < 0.4:
                pi_value = self.cached_pi_value
            else:
                stats = self.ppg_stats()
                if stats is not None:
                    dc, ac = stats
                    if dc > 0 and ac > 0:
                        pi_value = ac / dc * 100.0
                        self.cached_pi_value = pi_value
                        self.last_pi_time = now
        else:
            self.cached_pi_value = pi_value
            self.last_pi_time = now

        if pi_value is None or pi_value <= 0:
            self.pi_card["value"].setText("计算中")
            self.pi_card["value"].setStyleSheet("color: #64748b;")
            self.pi_card["desc"].setText("等待稳定 PPG")
            self.latest_pi_value = None
            return None

        self.pi_card["value"].setText(f"{pi_value:.2f} %")
        if pi_value < 0.3:
            self.pi_card["value"].setStyleSheet("color: #dc2626;")
            self.pi_card["desc"].setText("灌注弱 / 信号差")
        elif pi_value < 1.0:
            self.pi_card["value"].setStyleSheet("color: #d97706;")
            self.pi_card["desc"].setText("灌注偏弱")
        else:
            self.pi_card["value"].setStyleSheet("color: #059669;")
            self.pi_card["desc"].setText("灌注良好")

        self.latest_pi_value = pi_value
        return pi_value

    def rr_is_unstable(self):
        if len(self.rr_intervals) < 5:
            return False
        rr = np.array(list(self.rr_intervals)[-5:], dtype=float)
        mean_rr = float(np.mean(rr))
        if mean_rr <= 0:
            return False
        return float(np.std(rr)) / mean_rr > 0.12

    def ppg_stats(self):
        if len(self.ir_data) < self.PI_WINDOW_SIZE:
            return None
        ir = np.array(list(self.ir_data)[-self.PI_WINDOW_SIZE:], dtype=float)
        dc = float(np.mean(ir))
        # Percentiles reduce the effect of one accidental spike or finger movement.
        ac = float(np.percentile(ir, 95) - np.percentile(ir, 5))
        return dc, ac

    def ppg_amplitude(self):
        stats = self.ppg_stats()
        return None if stats is None else stats[1]

    def update_signal_card(self, ir_value, pi_value=None):
        amplitude = self.ppg_amplitude()
        unstable_rr = self.rr_is_unstable()

        if ir_value < 50000:
            self.signal_card["value"].setText("No Finger")
            self.signal_card["value"].setStyleSheet("color: #d97706;")
            self.signal_card["desc"].setText("IR 偏低")
        elif ir_value >= 250000:
            self.signal_card["value"].setText("Saturated")
            self.signal_card["value"].setStyleSheet("color: #dc2626;")
            self.signal_card["desc"].setText("减小按压力")
        elif pi_value is None or amplitude is None:
            self.signal_card["value"].setText("Checking")
            self.signal_card["value"].setStyleSheet("color: #64748b;")
            self.signal_card["desc"].setText("正在建立稳定波形")
        elif pi_value < 0.4 or amplitude < 600:
            self.signal_card["value"].setText("Weak Signal")
            self.signal_card["value"].setStyleSheet("color: #dc2626;")
            self.signal_card["desc"].setText("调整手指位置")
        elif pi_value > 12.0:
            self.signal_card["value"].setText("Unstable")
            self.signal_card["value"].setStyleSheet("color: #d97706;")
            self.signal_card["desc"].setText("波动过大，请保持不动")
        elif unstable_rr:
            self.signal_card["value"].setText("Motion")
            self.signal_card["value"].setStyleSheet("color: #d97706;")
            self.signal_card["desc"].setText("RR 间隔波动较大")
        elif len(self.rr_intervals) < 3:
            self.signal_card["value"].setText("Checking")
            self.signal_card["value"].setStyleSheet("color: #64748b;")
            self.signal_card["desc"].setText("等待稳定 RR")
        else:
            self.signal_card["value"].setText("Good")
            self.signal_card["value"].setStyleSheet("color: #059669;")
            self.signal_card["desc"].setText("PI / PPG / RR 稳定")

    def update_bpm_plot(self):
        if len(self.time_data) < 2:
            return
        x = np.array(self.time_data)
        self.bpm_curve.setData(x, np.array(self.bpm_data))
        self.avg_curve.setData(x, np.array(self.avg_bpm_data))


    def update_ppg_plot(self):
        if len(self.ppg_time_data) < 2 or len(self.ir_data) < 2:
            return
        x = np.array(self.ppg_time_data)
        ir = np.array(self.ir_data, dtype=float)
        self.ppg_curve.setData(x, ir)

        low = float(np.min(ir))
        high = float(np.max(ir))
        if high > low:
            margin = max((high - low) * 0.15, 1000.0)
            self.ppg_plot.setYRange(low - margin, high + margin, padding=0)
    def closeEvent(self, event):
        self.disconnect_serial()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Max30105Dashboard()
    window.show()
    sys.exit(app.exec())




































