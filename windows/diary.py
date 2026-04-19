import html
import json
import os
import sys

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from print_templates import render_template
from .primary_exam import EnhancedMultiSelectButton


TREATMENT_CATS = [
    ("Ангиоретинопротектор", "angio_retino"),
    ("Для улучшения обмена веществ", "metabolism"),
    ("Десенсибилизанты", "desensitization"),
    ("Антибиотики", "antibiotics"),
    ("Ангиопротекторы", "angioprotectors"),
    ("Миотики", "myotics"),
    ("Биостимуляторы", "biostimulators"),
    ("Сосудорасширяющие", "vasodilators"),
    ("Анальгетики", "analgesics"),
    ("Антиагреганты", "antiaggregants"),
    ("Противогрибковые", "antifungal"),
    ("Мидриатики", "mydriatics"),
    ("К-сберегающий", "k_sparing"),
    ("Анестетики", "anesthetics"),
    ("Сахоропонижающие", "hypoglycemic"),
    ("Гипотензивное", "hypotensive"),
    ("Мочегонное", "diuretic"),
    ("Антитромбической цели", "antithrombotic"),
]


def _escape(value):
    return html.escape(value or "")


def _diopter_text(value):
    text = (value or "").strip()
    if not text:
        return ""
    if text.lower().endswith(("d", "д")):
        return text
    return f"{text}D"


def _vis_status(text):
    if text == "пусто":
        return ""
    if text == "n.k. (не коррег.)":
        return "n.k."
    return text or ""


def _diary_vis_html(data):
    vis_od = (data.get("vis_od") or "").strip()
    vis_os = (data.get("vis_os") or "").strip()
    vgd_od = (data.get("vgd_od") or "").strip()
    vgd_os = (data.get("vgd_os") or "").strip()
    if not any([vis_od, vis_os, vgd_od, vgd_os]):
        return ""

    parts = ['<table class="vision-block" border="0" cellpadding="1" cellspacing="0" style="margin-top:6px; page-break-inside:avoid;"><tr>']
    if vis_od or vis_os:
        od_status = _vis_status(data.get("vis_correction_od"))
        os_status = _vis_status(data.get("vis_correction_os"))
        od_has_corr = data.get("vis_correction_od") == "с коррекцией"
        os_has_corr = data.get("vis_correction_os") == "с коррекцией"
        od_corr = _diopter_text(data.get("vis_od_corr")) if od_has_corr else ""
        os_corr = _diopter_text(data.get("vis_os_corr")) if os_has_corr else ""
        od_result = (data.get("vis_od_result") or "").strip() if od_has_corr else ""
        os_result = (data.get("vis_os_result") or "").strip() if os_has_corr else ""
        parts.append(f'''
            <td style="vertical-align:middle; padding-right:4px; white-space:nowrap;"><b>Vis</b></td>
            <td style="text-align:center; padding:0 4px; white-space:nowrap;">
                <table border="0" cellpadding="1" cellspacing="0">
                    <tr><td style="border-bottom:1px solid black;">OD</td></tr>
                    <tr><td>OS</td></tr>
                </table>
            </td>
            <td style="vertical-align:middle; padding:0 4px; white-space:nowrap;">=</td>
            <td style="text-align:center; padding:0 4px; white-space:nowrap;">
                <table border="0" cellpadding="1" cellspacing="0">
                    <tr><td style="border-bottom:1px solid black;">{_escape(vis_od) or "—"}</td></tr>
                    <tr><td>{_escape(vis_os) or "—"}</td></tr>
                </table>
            </td>
            <td style="text-align:center; padding:0 8px; white-space:nowrap; min-width:70px;">
                <table border="0" cellpadding="1" cellspacing="0">
                    <tr><td style="border-bottom:1px solid black; white-space:nowrap;">{_escape(od_status)}</td></tr>
                    <tr><td style="white-space:nowrap;">{_escape(os_status)}</td></tr>
                </table>
            </td>
            <td style="text-align:center; padding:0 4px; white-space:nowrap;">
                <table border="0" cellpadding="1" cellspacing="0">
                    <tr><td style="border-bottom:1px solid black;">{_escape(od_corr)}</td></tr>
                    <tr><td>{_escape(os_corr)}</td></tr>
                </table>
            </td>
            <td style="vertical-align:middle; padding:0 4px; white-space:nowrap;">=</td>
            <td style="text-align:center; padding:0 4px; white-space:nowrap;">
                <table border="0" cellpadding="1" cellspacing="0">
                    <tr><td style="border-bottom:1px solid black;">{_escape(od_result)}</td></tr>
                    <tr><td>{_escape(os_result)}</td></tr>
                </table>
            </td>
            <td style="width:28px;"></td>
        ''')

    if vgd_od or vgd_os:
        parts.append(f'''
            <td style="vertical-align:middle; padding-right:4px; white-space:nowrap;"><b>ВГД</b></td>
            <td style="text-align:center; padding:0 4px; white-space:nowrap;">
                <table border="0" cellpadding="1" cellspacing="0">
                    <tr><td style="border-bottom:1px solid black;">OD</td></tr>
                    <tr><td>OS</td></tr>
                </table>
            </td>
            <td style="vertical-align:middle; padding:0 4px; white-space:nowrap;">=</td>
            <td style="text-align:center; padding:0 4px; white-space:nowrap;">
                <table border="0" cellpadding="1" cellspacing="0">
                    <tr><td style="border-bottom:1px solid black;">{_escape(vgd_od) or "—"}</td></tr>
                    <tr><td>{_escape(vgd_os) or "—"}</td></tr>
                </table>
            </td>
            <td style="white-space:nowrap;">мм.рт.ст.</td>
        ''')
    parts.append("</tr></table>")
    return "".join(parts)


def _diary_treatment_basis_lines(data):
    basis = data.get("basis") or {}
    lines = []
    for label, category in TREATMENT_CATS:
        item = basis.get(category) or {}
        selected = item.get("selected") or []
        note = item.get("note") or ""
        text = "; ".join(selected)
        if note:
            text = f"{text} (прим.: {note})" if text else f"(прим.: {note})"
        if text:
            lines.append(f"<b>{_escape(label)}:</b> {_escape(text)}")
    return lines


def render_diary_html(data):
    left_parts = [
        f"АД {_escape(data.get('bp'))} мм. рт. ст.<br>" if data.get("bp") else "",
        f"ЧСС {_escape(data.get('hr'))} уд/мин<br>" if data.get("hr") else "",
        f"Пульс {_escape(data.get('pulse'))} уд/мин<br>" if data.get("pulse") else "",
    ]
    right_parts = [
        f"Общее состояние: {_escape(data.get('general_state'))}<br>" if data.get("general_state") else "",
        f"Жалобы: {_escape(data.get('complaints'))}<br>" if data.get("complaints") else "",
    ]

    vis_html = _diary_vis_html(data)
    if vis_html:
        right_parts.append(vis_html)

    for label, key in (("OS", "os_text"), ("OD", "od_text"), ("OU", "ou_text")):
        value = (data.get(key) or "").strip()
        if value:
            right_parts.append(f"<div>{label}: {_escape(value)}</div>")

    treatment = data.get("treatment") or ""
    if treatment:
        right_parts.append(f'<div>Лечение: {_escape(treatment).replace(chr(10), "<br>")}</div>')

    basis_lines = _diary_treatment_basis_lines(data)
    if basis_lines:
        right_parts.append("<div>" + "; ".join(basis_lines) + "</div>")

    return render_template("diary.html", {
        "left": "".join(left_parts),
        "right": "".join(right_parts),
    })


class DiaryWindow(QDialog):
    def __init__(self, parent, db, patient_id, records_table, load_records_list_callback, history_id=None):
        super().__init__(parent)
        self.db = db
        self.patient_id = patient_id
        self.history_id = history_id
        self.records_table = records_table
        self.load_records_list = load_records_list_callback
        self.setWindowTitle("Дневник")
        self.setModal(True)
        self.resize(980, 720)
        self.create_widgets()

    def create_widgets(self):
        main_layout = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)

        common_grid = QGridLayout()
        common_grid.setHorizontalSpacing(10)
        common_grid.setVerticalSpacing(6)
        layout.addLayout(common_grid)

        common_grid.addWidget(QLabel("Дата"), 0, 0)
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        common_grid.addWidget(self.date_edit, 0, 1)

        common_grid.addWidget(QLabel("АД"), 0, 2)
        self.bp_edit = QLineEdit("120/80")
        self.bp_edit.setPlaceholderText("120/80")
        common_grid.addWidget(self.bp_edit, 0, 3)
        common_grid.addWidget(QLabel("мм. рт. ст."), 0, 4)

        common_grid.addWidget(QLabel("ЧСС"), 1, 0)
        self.hr_edit = QLineEdit("76")
        self.hr_edit.setPlaceholderText("76")
        common_grid.addWidget(self.hr_edit, 1, 1)
        common_grid.addWidget(QLabel("уд/мин"), 1, 2)

        common_grid.addWidget(QLabel("Пульс"), 1, 3)
        self.pulse_edit = QLineEdit("76")
        self.pulse_edit.setPlaceholderText("76")
        common_grid.addWidget(self.pulse_edit, 1, 4)
        common_grid.addWidget(QLabel("уд/мин"), 1, 5)

        common_grid.addWidget(QLabel("Общее состояние"), 2, 0)
        self.general_state_combo = QComboBox()
        self.general_state_combo.setEditable(True)
        self.general_state_combo.addItems(["удовлетворительное", "средней тяжести", "тяжёлое"])
        self.general_state_combo.setCurrentText("удовлетворительное")
        common_grid.addWidget(self.general_state_combo, 2, 1, 1, 2)

        common_grid.addWidget(QLabel("Жалобы"), 2, 3)
        self.complaints_edit = QLineEdit()
        self.complaints_edit.setPlaceholderText("если пусто, в печать не попадет")
        common_grid.addWidget(self.complaints_edit, 2, 4, 1, 2)

        copy_previous_btn = QPushButton("Скопировать предыдущий дневник")
        copy_previous_btn.clicked.connect(self.copy_previous_diary)
        common_grid.addWidget(copy_previous_btn, 3, 0, 1, 3)

        ophthalmic_box = QGroupBox("Офтальмологический осмотр")
        ophthalmic_layout = QVBoxLayout(ophthalmic_box)
        layout.addWidget(ophthalmic_box)

        vis_vgd_layout = QHBoxLayout()
        vis_vgd_layout.setSpacing(18)
        ophthalmic_layout.addLayout(vis_vgd_layout)

        vis_vgd_layout.addWidget(QLabel("<b>Vis</b>"))
        vis_grid = QGridLayout()
        vis_grid.setHorizontalSpacing(6)
        vis_grid.setVerticalSpacing(6)
        self._build_vis_row(vis_grid, 0, "OD")
        self._build_vis_row(vis_grid, 1, "OS")
        vis_vgd_layout.addLayout(vis_grid)
        vis_vgd_layout.addSpacing(18)

        vis_vgd_layout.addWidget(QLabel("<b>ВГД</b>"))
        vgd_grid = QGridLayout()
        vgd_grid.addWidget(QLabel("OD"), 0, 0)
        self.vgd_od = QLineEdit()
        self.vgd_od.setFixedWidth(90)
        vgd_grid.addWidget(self.vgd_od, 0, 1)
        vgd_grid.addWidget(QLabel("OS"), 1, 0)
        self.vgd_os = QLineEdit()
        self.vgd_os.setFixedWidth(90)
        vgd_grid.addWidget(self.vgd_os, 1, 1)
        vis_vgd_layout.addLayout(vgd_grid)
        vis_vgd_layout.addStretch(1)

        eye_text_grid = QGridLayout()
        ophthalmic_layout.addLayout(eye_text_grid)
        eye_text_grid.addWidget(QLabel("OS"), 0, 0)
        self.os_text = QLineEdit()
        eye_text_grid.addWidget(self.os_text, 0, 1)
        eye_text_grid.addWidget(QLabel("OD"), 1, 0)
        self.od_text = QLineEdit()
        eye_text_grid.addWidget(self.od_text, 1, 1)
        eye_text_grid.addWidget(QLabel("OU"), 2, 0)
        self.ou_text = QLineEdit()
        eye_text_grid.addWidget(self.ou_text, 2, 1)

        treatment_box = QGroupBox("Лечение")
        treatment_layout = QVBoxLayout(treatment_box)
        layout.addWidget(treatment_box)

        quick_row = QHBoxLayout()
        continue_btn = QPushButton("продолжить")
        continue_btn.clicked.connect(lambda: self._set_treatment_text("продолжить"))
        quick_row.addWidget(continue_btn)
        plan_btn = QPushButton("по листу назначения")
        plan_btn.clicked.connect(lambda: self._set_treatment_text("по листу назначения"))
        quick_row.addWidget(plan_btn)
        add_basis_btn = QPushButton("к лечению добавить")
        add_basis_btn.clicked.connect(self._add_to_treatment)
        quick_row.addWidget(add_basis_btn)
        quick_row.addStretch(1)
        treatment_layout.addLayout(quick_row)

        self.treatment_text = QTextEdit()
        self.treatment_text.setMaximumHeight(90)
        treatment_layout.addWidget(self.treatment_text)

        self.basis_box = QGroupBox("Обоснование лечения")
        self.basis_box.setVisible(False)
        basis_layout = QGridLayout(self.basis_box)
        basis_layout.setColumnStretch(1, 1)
        treatment_layout.addWidget(self.basis_box)

        self.treatment_basis_fields = {}
        treatment_json = self._data_path("treatment_basis.json")
        treatment_data = self._read_json(treatment_json)
        for row, (label, category) in enumerate(TREATMENT_CATS):
            basis_layout.addWidget(QLabel(label + ":"), row, 0)
            button = EnhancedMultiSelectButton(label, treatment_data.get(category, []), file_path=treatment_json, category=category)
            basis_layout.addWidget(button, row, 1)
            self.treatment_basis_fields[category] = (label, button)

        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(self.save_diary)
        buttons.addWidget(save_button)
        main_layout.addLayout(buttons)

    def _build_vis_row(self, grid, row, eye):
        grid.addWidget(QLabel(eye), row, 0)
        value = QLineEdit()
        value.setFixedWidth(60)
        grid.addWidget(value, row, 1)

        correction = QComboBox()
        correction.addItems([
            "пусто",
            "с коррекцией",
            "n.k. (не коррег.)",
            "счет пальцев у лица",
            "движ. руки у лица",
            "pr. certa",
            "pr. incerta",
            "(ноль)",
            "анофтальм",
            "эксцентрично",
        ])
        correction.setFixedWidth(155)
        grid.addWidget(correction, row, 2)

        corr_value = QLineEdit()
        corr_value.setFixedWidth(60)
        grid.addWidget(corr_value, row, 3)
        eq_label = QLabel("=")
        grid.addWidget(eq_label, row, 4, Qt.AlignCenter)
        result = QLineEdit()
        result.setFixedWidth(60)
        grid.addWidget(result, row, 5)

        setattr(self, f"vis_{eye.lower()}", value)
        setattr(self, f"vis_correction_{eye.lower()}", correction)
        setattr(self, f"vis_{eye.lower()}_corr", corr_value)
        setattr(self, f"vis_{eye.lower()}_result", result)
        setattr(self, f"vis_eq_{eye.lower()}_label", eq_label)

        correction.currentTextChanged.connect(lambda _text, e=eye: self._update_vis_corr_fields(e))
        self._update_vis_corr_fields(eye)

    def _update_vis_corr_fields(self, eye):
        correction = getattr(self, f"vis_correction_{eye.lower()}")
        corr_value = getattr(self, f"vis_{eye.lower()}_corr")
        result = getattr(self, f"vis_{eye.lower()}_result")
        eq_label = getattr(self, f"vis_eq_{eye.lower()}_label")
        enabled = correction.currentText() == "с коррекцией"
        for widget in (corr_value, result):
            widget.setEnabled(enabled)
            widget.setStyleSheet("" if enabled else "background-color: #e0e0e0; color: #888;")
            if not enabled:
                widget.clear()
        eq_label.setEnabled(enabled)

    def _data_path(self, file_name):
        base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(base_path, "data", file_name)

    def _read_json(self, path):
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _set_treatment_text(self, text):
        self.treatment_text.setPlainText(text)

    def _add_to_treatment(self):
        if not self.treatment_text.toPlainText().strip():
            self.treatment_text.setPlainText("к лечению добавить")
        self.basis_box.setVisible(True)

    def _escape(self, value):
        return html.escape(value or "")

    def _diopter_text(self, value):
        text = (value or "").strip()
        if not text:
            return ""
        if text.lower().endswith(("d", "д")):
            return text
        return f"{text}D"

    def _vis_status(self, text):
        if text == "пусто":
            return ""
        if text == "n.k. (не коррег.)":
            return "n.k."
        return text

    def _vis_html(self):
        vis_od = self.vis_od.text().strip()
        vis_os = self.vis_os.text().strip()
        vgd_od = self.vgd_od.text().strip()
        vgd_os = self.vgd_os.text().strip()
        if not any([vis_od, vis_os, vgd_od, vgd_os]):
            return ""

        parts = ['<table class="vision-block" border="0" cellpadding="1" cellspacing="0" style="margin-top:6px; page-break-inside:avoid;"><tr>']
        if vis_od or vis_os:
            od_status = self._vis_status(self.vis_correction_od.currentText())
            os_status = self._vis_status(self.vis_correction_os.currentText())
            od_has_corr = self.vis_correction_od.currentText() == "с коррекцией"
            os_has_corr = self.vis_correction_os.currentText() == "с коррекцией"
            od_corr = self._diopter_text(self.vis_od_corr.text()) if od_has_corr else ""
            os_corr = self._diopter_text(self.vis_os_corr.text()) if os_has_corr else ""
            od_result = self.vis_od_result.text().strip() if od_has_corr else ""
            os_result = self.vis_os_result.text().strip() if os_has_corr else ""
            parts.append(f'''
                <td style="vertical-align:middle; padding-right:4px;"><b>Vis</b></td>
                <td style="text-align:center; padding:0 4px;">
                    <table border="0" cellpadding="1" cellspacing="0">
                        <tr><td style="border-bottom:1px solid black;">OD</td></tr>
                        <tr><td>OS</td></tr>
                    </table>
                </td>
                <td style="vertical-align:middle; padding:0 4px;">=</td>
                <td style="text-align:center; padding:0 4px;">
                    <table border="0" cellpadding="1" cellspacing="0">
                        <tr><td style="border-bottom:1px solid black;">{self._escape(vis_od) or "—"}</td></tr>
                        <tr><td>{self._escape(vis_os) or "—"}</td></tr>
                    </table>
                </td>
                <td style="text-align:center; padding:0 7px;">
                    <table border="0" cellpadding="1" cellspacing="0">
                        <tr><td style="border-bottom:1px solid black;">{self._escape(od_status)}</td></tr>
                        <tr><td>{self._escape(os_status)}</td></tr>
                    </table>
                </td>
                <td style="text-align:center; padding:0 4px;">
                    <table border="0" cellpadding="1" cellspacing="0">
                        <tr><td style="border-bottom:1px solid black;">{self._escape(od_corr)}</td></tr>
                        <tr><td>{self._escape(os_corr)}</td></tr>
                    </table>
                </td>
                <td style="vertical-align:middle; padding:0 4px;">=</td>
                <td style="text-align:center; padding:0 4px;">
                    <table border="0" cellpadding="1" cellspacing="0">
                        <tr><td style="border-bottom:1px solid black;">{self._escape(od_result)}</td></tr>
                        <tr><td>{self._escape(os_result)}</td></tr>
                    </table>
                </td>
                <td style="width:45px;"></td>
            ''')

        if vgd_od or vgd_os:
            parts.append(f'''
                <td style="vertical-align:middle; padding-right:4px;"><b>ВГД</b></td>
                <td style="text-align:center; padding:0 4px;">
                    <table border="0" cellpadding="1" cellspacing="0">
                        <tr><td style="border-bottom:1px solid black;">OD</td></tr>
                        <tr><td>OS</td></tr>
                    </table>
                </td>
                <td style="vertical-align:middle; padding:0 4px;">=</td>
                <td style="text-align:center; padding:0 4px;">
                    <table border="0" cellpadding="1" cellspacing="0">
                        <tr><td style="border-bottom:1px solid black;">{self._escape(vgd_od) or "—"}</td></tr>
                        <tr><td>{self._escape(vgd_os) or "—"}</td></tr>
                    </table>
                </td>
                <td>мм.рт.ст.</td>
            ''')
        parts.append("</tr></table>")
        return "".join(parts)

    def _treatment_basis_lines(self):
        lines = []
        for label, button in self.treatment_basis_fields.values():
            text = button.get_text()
            if text:
                lines.append(f"<b>{self._escape(label)}:</b> {self._escape(text)}")
        return lines

    def _build_diary_html(self, data):
        return render_diary_html(data)

    def save_diary(self):
        data = self._state()
        html_record = self._build_diary_html(data)
        self.db.add_history(
            self.patient_id,
            "diary",
            html_record,
            "",
            data.get("treatment", ""),
            json.dumps(data, ensure_ascii=False),
            history_id=self.history_id,
        )
        QMessageBox.information(self, "Успех", "Дневник сохранен.")
        self.load_records_list(self.records_table, self.patient_id)
        parent = self.parent()
        while parent is not None and not hasattr(parent, "_nav_back"):
            parent = parent.parent()
        if parent is not None and hasattr(parent, "_nav_back"):
            try:
                parent._nav_back()
                return
            except Exception:
                pass
        try:
            self.accept()
        except Exception:
            pass

    def _state(self):
        basis = {}
        for category, (_label, button) in self.treatment_basis_fields.items():
            basis[category] = {
                "selected": list(getattr(button, "_selected", [])),
                "note": getattr(button, "_note", ""),
            }
        data = {
            "bp": self.bp_edit.text().strip(),
            "hr": self.hr_edit.text().strip(),
            "pulse": self.pulse_edit.text().strip(),
            "general_state": self.general_state_combo.currentText().strip(),
            "complaints": self.complaints_edit.text().strip(),
            "vis_od": self.vis_od.text().strip(),
            "vis_os": self.vis_os.text().strip(),
            "vis_correction_od": self.vis_correction_od.currentText(),
            "vis_correction_os": self.vis_correction_os.currentText(),
            "vis_od_corr": self.vis_od_corr.text().strip(),
            "vis_os_corr": self.vis_os_corr.text().strip(),
            "vis_od_result": self.vis_od_result.text().strip(),
            "vis_os_result": self.vis_os_result.text().strip(),
            "vgd_od": self.vgd_od.text().strip(),
            "vgd_os": self.vgd_os.text().strip(),
            "os_text": self.os_text.text().strip(),
            "od_text": self.od_text.text().strip(),
            "ou_text": self.ou_text.text().strip(),
            "treatment": self.treatment_text.toPlainText().strip(),
            "basis": basis,
        }
        return data

    def copy_previous_diary(self):
        state = self._latest_diary_state()
        if not state:
            QMessageBox.information(self, "Дневник", "Предыдущий дневник не найден или он был создан в старом формате.")
            return
        self._apply_state(state)
        QMessageBox.information(self, "Дневник", "Предыдущий дневник скопирован. Проверьте и отредактируйте запись перед сохранением.")

    def _latest_diary_state(self):
        histories = self.db.get_histories(self.patient_id)
        for history in histories:
            if history[3] != "diary":
                continue
            if self.history_id is not None and history[11] != self.history_id:
                continue
            try:
                data = json.loads(history[7] or "")
            except Exception:
                data = None
            if isinstance(data, dict):
                return data
        return None

    def _apply_state(self, data):
        self.bp_edit.setText(data.get("bp", ""))
        self.hr_edit.setText(data.get("hr", ""))
        self.pulse_edit.setText(data.get("pulse", ""))
        self.general_state_combo.setCurrentText(data.get("general_state", ""))
        self.complaints_edit.setText(data.get("complaints", ""))
        self.vis_od.setText(data.get("vis_od", ""))
        self.vis_os.setText(data.get("vis_os", ""))
        self.vis_correction_od.setCurrentText(data.get("vis_correction_od", "пусто"))
        self.vis_correction_os.setCurrentText(data.get("vis_correction_os", "пусто"))
        self.vis_od_corr.setText(data.get("vis_od_corr", ""))
        self.vis_os_corr.setText(data.get("vis_os_corr", ""))
        self.vis_od_result.setText(data.get("vis_od_result", ""))
        self.vis_os_result.setText(data.get("vis_os_result", ""))
        self.vgd_od.setText(data.get("vgd_od", ""))
        self.vgd_os.setText(data.get("vgd_os", ""))
        self.os_text.setText(data.get("os_text", ""))
        self.od_text.setText(data.get("od_text", ""))
        self.ou_text.setText(data.get("ou_text", ""))
        self.treatment_text.setPlainText(data.get("treatment", ""))

        basis = data.get("basis", {})
        has_basis = False
        for category, (_label, button) in self.treatment_basis_fields.items():
            value = basis.get(category, {})
            selected = value.get("selected", []) if isinstance(value, dict) else []
            note = value.get("note", "") if isinstance(value, dict) else ""
            button._selected = list(selected or [])
            button._note = note or ""
            button._refresh_text()
            if selected or note:
                has_basis = True
        self.basis_box.setVisible(has_basis)
