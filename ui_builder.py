import json
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QGroupBox, QLabel,
    QComboBox, QLineEdit, QCheckBox, QSpinBox, QPushButton,
    QPlainTextEdit, QListWidget, QListWidgetItem, QScrollArea, QMessageBox,
    QAbstractItemView, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QShortcut,
    QKeySequence,
)

from schemas import TABLE_CATEGORIES, TABLE_SCHEMAS
from engine import build_query, get_operators_for_type

LIBRARY_PATH = Path(__file__).parent / "query_library.json"


class KqlHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rules = []

        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor("#569cd6"))
        kw_fmt.setFontWeight(QFont.Bold)
        keywords = [
            r"\bwhere\b", r"\bproject\b", r"\bsort\s+by\b", r"\btake\b",
            r"\bago\b", r"\bcontains\b", r"\b!contains\b", r"\bhas\b",
            r"\b!has\b", r"\bstartswith\b", r"\bendswith\b", r"\bbetween\b",
            r"\bmatches\s+regex\b", r"\barray_length\b", r"\bdatetime\b",
            r"\bextend\b", r"\bsummarize\b", r"\bcount\b", r"\bjoin\b",
            r"\bon\b", r"\blet\b", r"\bin\b", r"\bnot\b", r"\band\b", r"\bor\b",
        ]
        for pattern in keywords:
            self._rules.append((pattern, kw_fmt))

        pipe_fmt = QTextCharFormat()
        pipe_fmt.setForeground(QColor("#d4d4d4"))
        pipe_fmt.setFontWeight(QFont.Bold)
        self._rules.append((r"^\|", pipe_fmt))

        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor("#ce9178"))
        self._rules.append((r'@?"[^"]*"', str_fmt))

        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor("#b5cea8"))
        self._rules.append((r"\b\d+[mhdw]?\b", num_fmt))

        comment_fmt = QTextCharFormat()
        comment_fmt.setForeground(QColor("#6a9955"))
        comment_fmt.setFontItalic(True)
        self._rules.append((r"//.*$", comment_fmt))

    def highlightBlock(self, text):
        import re
        # Only treat line 0 as a bare table name when it actually is one
        # (a single identifier). Raw queries may start with //, let, or a pipe.
        if self.currentBlock().blockNumber() == 0 and re.match(r"^\w+$", text.strip()):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor("#4ec9b0"))
            fmt.setFontWeight(QFont.Bold)
            self.setFormat(0, len(text), fmt)
            return
        for pattern, fmt in self._rules:
            for m in re.finditer(pattern, text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


class FilterRow(QWidget):
    changed = Signal()
    remove_requested = Signal(object)

    def __init__(self, columns_with_types, parent=None):
        super().__init__(parent)
        self._columns = columns_with_types

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        self.col_combo = QComboBox()
        self.col_combo.setMinimumWidth(180)
        self.col_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.col_combo)

        self.op_combo = QComboBox()
        self.op_combo.setMinimumWidth(120)
        layout.addWidget(self.op_combo)

        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("Value...")
        self.value_edit.setMinimumWidth(160)
        self.value_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.value_edit)

        self.bool_combo = QComboBox()
        self.bool_combo.addItems(["true", "false"])
        self.bool_combo.setMinimumWidth(80)
        self.bool_combo.setVisible(False)
        layout.addWidget(self.bool_combo)

        self.remove_btn = QPushButton("-")
        self.remove_btn.setObjectName("removeFilterBtn")
        self.remove_btn.setFixedWidth(32)
        self.remove_btn.setToolTip("Remove this filter")
        layout.addWidget(self.remove_btn)

        self._populate_columns(columns_with_types)

        self.col_combo.currentIndexChanged.connect(self._on_column_changed)
        self.op_combo.currentIndexChanged.connect(self._on_operator_changed)
        self.value_edit.textChanged.connect(self._emit_changed)
        self.bool_combo.currentIndexChanged.connect(self._emit_changed)
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))

    def _populate_columns(self, columns_with_types):
        self.col_combo.blockSignals(True)
        self.col_combo.clear()
        self._columns = columns_with_types
        for name in sorted(columns_with_types.keys()):
            info = columns_with_types[name]
            self.col_combo.addItem(f"{name}  ({info['type']})", userData=info["type"])
        self.col_combo.blockSignals(False)
        if self.col_combo.count() > 0:
            self._on_column_changed(0)

    def _on_column_changed(self, idx):
        dtype = self.col_combo.currentData()
        if dtype is None:
            return
        ops = get_operators_for_type(dtype)
        self.op_combo.blockSignals(True)
        self.op_combo.clear()
        self.op_combo.addItems(ops)
        self.op_combo.blockSignals(False)

        is_bool = dtype == "bool"
        self.value_edit.setVisible(not is_bool)
        self.bool_combo.setVisible(is_bool)

        self._update_placeholder()
        self._emit_changed()

    def _on_operator_changed(self):
        self._update_placeholder()
        self._emit_changed()

    def _update_placeholder(self):
        op = self.op_combo.currentText()
        if op in ("in", "!in"):
            self.value_edit.setPlaceholderText("e.g. 700082, 50140")
            return
        dtype = self.col_combo.currentData()
        if dtype == "datetime":
            self.value_edit.setPlaceholderText("e.g. 1h, 7d, 2026-01-15")
        elif dtype == "int":
            self.value_edit.setPlaceholderText("e.g. 443, 10..100")
        elif dtype == "dynamic":
            self.value_edit.setPlaceholderText("e.g. value or 0 for array_length")
        else:
            self.value_edit.setPlaceholderText("Value...")

    def _emit_changed(self):
        self.changed.emit()

    def get_column_name(self):
        text = self.col_combo.currentText()
        return text.split("  (")[0] if "  (" in text else text

    def get_state(self):
        dtype = self.col_combo.currentData() or "string"
        return {
            "column": self.get_column_name(),
            "operator": self.op_combo.currentText(),
            "value": self.bool_combo.currentText() if dtype == "bool" else self.value_edit.text(),
            "dtype": dtype,
        }

    def set_state(self, state):
        col_name = state.get("column", "")
        for i in range(self.col_combo.count()):
            if self.col_combo.itemText(i).startswith(col_name + "  ("):
                self.col_combo.setCurrentIndex(i)
                break

        op = state.get("operator", "")
        idx = self.op_combo.findText(op)
        if idx >= 0:
            self.op_combo.setCurrentIndex(idx)

        dtype = self.col_combo.currentData() or "string"
        val = state.get("value", "")
        if dtype == "bool":
            self.bool_combo.setCurrentText(val)
        else:
            self.value_edit.setText(val)

    def update_columns(self, columns_with_types):
        self._populate_columns(columns_with_types)


class QueryBuilderWidget(QWidget):
    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter_rows = []
        self._raw_mode = False

        splitter = QSplitter(Qt.Horizontal, self)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.addWidget(splitter)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_widget = QWidget()
        self._left_layout = QVBoxLayout(left_widget)
        self._left_layout.setSpacing(8)
        left_scroll.setWidget(left_widget)
        splitter.addWidget(left_scroll)

        right_widget = QWidget()
        self._right_layout = QVBoxLayout(right_widget)
        self._right_layout.setSpacing(8)
        splitter.addWidget(right_widget)

        splitter.setSizes([550, 500])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        self._build_preview()
        self._build_library()

        self._init_output_options()
        self._build_table_selection()
        self._build_time_range()
        self._build_filters()
        self._build_output_options_ui()
        self._left_layout.addStretch()

        self._setup_shortcuts()

        QTimer.singleShot(0, self._refresh_preview)

    def _build_table_selection(self):
        grp = QGroupBox("Table Selection")
        layout = QVBoxLayout(grp)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Category:"))
        self.category_combo = QComboBox()
        self.category_combo.addItems(TABLE_CATEGORIES.keys())
        self.category_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row1.addWidget(self.category_combo)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Table:"))
        self.table_combo = QComboBox()
        self.table_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row2.addWidget(self.table_combo)
        layout.addLayout(row2)

        self.table_desc_label = QLabel("")
        self.table_desc_label.setStyleSheet("color: #888; font-style: italic; padding: 2px;")
        self.table_desc_label.setWordWrap(True)
        layout.addWidget(self.table_desc_label)

        self.category_combo.currentIndexChanged.connect(self._on_category_changed)
        self.table_combo.currentIndexChanged.connect(self._on_table_changed)

        self._left_layout.addWidget(grp)
        self._on_category_changed(0)

    def _build_time_range(self):
        grp = QGroupBox("Time Range")
        layout = QHBoxLayout(grp)

        self.time_enabled = QCheckBox("Enable")
        self.time_enabled.setChecked(True)
        layout.addWidget(self.time_enabled)

        self.time_value = QSpinBox()
        self.time_value.setRange(1, 999)
        self.time_value.setValue(1)
        self.time_value.setFixedWidth(70)
        layout.addWidget(self.time_value)

        self.time_unit = QComboBox()
        self.time_unit.addItems(["d", "h", "m", "w"])
        self.time_unit.setFixedWidth(60)
        layout.addWidget(self.time_unit)

        unit_label = QLabel("")
        unit_label.setStyleSheet("color: #888;")
        layout.addWidget(unit_label)
        layout.addStretch()

        self.time_enabled.stateChanged.connect(self._refresh_preview)
        self.time_value.valueChanged.connect(self._refresh_preview)
        self.time_unit.currentIndexChanged.connect(self._refresh_preview)

        self._left_layout.addWidget(grp)

    def _build_filters(self):
        grp = QGroupBox("Filters")
        layout = QVBoxLayout(grp)

        header = QHBoxLayout()
        header.addWidget(QLabel("Add where clauses to filter results"))
        header.addStretch()
        add_btn = QPushButton("+ Add Filter")
        add_btn.setObjectName("addFilterBtn")
        add_btn.clicked.connect(self._add_filter_row)
        header.addWidget(add_btn)
        layout.addLayout(header)

        self._filters_container = QVBoxLayout()
        self._filters_container.setSpacing(4)
        layout.addLayout(self._filters_container)

        self._filters_grp = grp
        self._left_layout.addWidget(grp)

        self._add_filter_row()

    def _init_output_options(self):
        self.project_list = QListWidget()
        self.project_list.setObjectName("projectList")
        self.project_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.project_list.setMaximumHeight(180)

        self.sort_combo = QComboBox()
        self.sort_combo.setMinimumWidth(160)

        self.sort_dir_combo = QComboBox()
        self.sort_dir_combo.addItems(["desc", "asc"])
        self.sort_dir_combo.setFixedWidth(70)

        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(0, 50000)
        self.limit_spin.setValue(100)
        self.limit_spin.setSpecialValueText("(no limit)")
        self.limit_spin.setFixedWidth(90)

    def _build_output_options_ui(self):
        grp = QGroupBox("Output Options")
        layout = QVBoxLayout(grp)
        layout.setSpacing(12)

        proj_label = QLabel("Project columns (select to include, empty = all):")
        layout.addWidget(proj_label)
        layout.addWidget(self.project_list)

        layout.addSpacing(8)

        row = QHBoxLayout()
        row.addWidget(QLabel("Sort by:"))
        row.addWidget(self.sort_combo)
        row.addWidget(self.sort_dir_combo)
        row.addSpacing(20)
        row.addWidget(QLabel("Limit:"))
        row.addWidget(self.limit_spin)
        row.addStretch()
        layout.addLayout(row)

        self.project_list.itemChanged.connect(self._refresh_preview)
        self.sort_combo.currentIndexChanged.connect(self._refresh_preview)
        self.sort_dir_combo.currentIndexChanged.connect(self._refresh_preview)
        self.limit_spin.valueChanged.connect(self._refresh_preview)

        self._left_layout.addWidget(grp)

    def _build_preview(self):
        grp = QGroupBox("Generated KQL Query")
        layout = QVBoxLayout(grp)

        mode_row = QHBoxLayout()
        self.raw_mode_check = QCheckBox("Edit / paste raw KQL")
        self.raw_mode_check.setToolTip(
            "Free-form mode: paste or write full KQL (mv-expand, summarize, joins, "
            "let). The builder form is ignored while this is on."
        )
        self.raw_mode_check.stateChanged.connect(self._toggle_raw_mode)
        mode_row.addWidget(self.raw_mode_check)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        self.preview = QPlainTextEdit()
        self.preview.setObjectName("queryPreview")
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(180)
        layout.addWidget(self.preview)

        self._highlighter = KqlHighlighter(self.preview.document())

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.copy_btn = QPushButton("Copy to Clipboard")
        self.copy_btn.setObjectName("copyButton")
        self.copy_btn.clicked.connect(self._copy_to_clipboard)
        btn_row.addWidget(self.copy_btn)

        self.clear_btn = QPushButton("Clear Query")
        self.clear_btn.setObjectName("clearButton")
        self.clear_btn.clicked.connect(self._clear_form)
        btn_row.addWidget(self.clear_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._right_layout.addWidget(grp)

    def _build_library(self):
        grp = QGroupBox("Query Library")
        layout = QVBoxLayout(grp)

        self.library_list = QListWidget()
        self.library_list.setMaximumHeight(150)
        layout.addWidget(self.library_list)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self.query_name_edit = QLineEdit()
        self.query_name_edit.setPlaceholderText("Enter query name...")
        name_row.addWidget(self.query_name_edit)
        layout.addLayout(name_row)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_query)
        btn_row.addWidget(save_btn)

        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self._load_query)
        btn_row.addWidget(load_btn)

        del_btn = QPushButton("Delete")
        del_btn.clicked.connect(self._delete_query)
        btn_row.addWidget(del_btn)
        layout.addLayout(btn_row)

        self.library_list.itemClicked.connect(
            lambda item: self.query_name_edit.setText(item.text())
        )

        self._right_layout.addWidget(grp)
        self._right_layout.addStretch()

        self._load_library_list()

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, self._copy_to_clipboard)
        QShortcut(QKeySequence("Ctrl+S"), self, self._save_query)
        QShortcut(QKeySequence("Ctrl+N"), self, self._clear_form)

    def _get_time_column(self, table):
        cols = TABLE_SCHEMAS.get(table, {}).get("columns", {})
        for candidate in ("Timestamp", "TimeGenerated", "timestamp"):
            if candidate in cols:
                return candidate
        return "Timestamp"

    def _get_current_columns(self):
        table = self.table_combo.currentText()
        schema = TABLE_SCHEMAS.get(table)
        if schema:
            return schema["columns"]
        return {}

    def _on_category_changed(self, idx):
        cat = self.category_combo.currentText()
        tables = TABLE_CATEGORIES.get(cat, [])
        self.table_combo.blockSignals(True)
        self.table_combo.clear()
        self.table_combo.addItems(tables)
        self.table_combo.blockSignals(False)
        if tables:
            self._on_table_changed(0)

    def _on_table_changed(self, idx):
        table = self.table_combo.currentText()
        schema = TABLE_SCHEMAS.get(table)
        if not schema:
            return

        self.table_desc_label.setText(schema["description"])
        cols = schema["columns"]

        for row in self._filter_rows:
            row.update_columns(cols)

        self.project_list.blockSignals(True)
        self.project_list.clear()
        for name in sorted(cols.keys()):
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.project_list.addItem(item)
        self.project_list.blockSignals(False)

        self.sort_combo.blockSignals(True)
        self.sort_combo.clear()
        self.sort_combo.addItem("(none)")
        for name in sorted(cols.keys()):
            self.sort_combo.addItem(name)
        ts_col = self._get_time_column(table)
        ts_idx = self.sort_combo.findText(ts_col)
        if ts_idx >= 0:
            self.sort_combo.setCurrentIndex(ts_idx)
        self.sort_combo.blockSignals(False)

        self._refresh_preview()
        self.status_message.emit(f"Table: {table} ({len(cols)} columns)")

    def _add_filter_row(self):
        cols = self._get_current_columns()
        row = FilterRow(cols)
        row.changed.connect(self._refresh_preview)
        row.remove_requested.connect(self._remove_filter_row)
        self._filter_rows.append(row)
        self._filters_container.addWidget(row)
        self._update_remove_buttons()
        self._refresh_preview()

    def _remove_filter_row(self, row):
        if row not in self._filter_rows:
            return
        self._filter_rows.remove(row)
        self._filters_container.removeWidget(row)
        row.deleteLater()
        self._refresh_preview()

    def _update_remove_buttons(self):
        pass

    def _toggle_raw_mode(self, _state=None):
        enabled = self.raw_mode_check.isChecked()
        if enabled == self._raw_mode:
            return
        if enabled:
            # Entering raw mode: keep whatever is in the box as a starting point.
            self._raw_mode = True
            self.preview.setReadOnly(False)
            self.status_message.emit("Raw KQL mode — builder form is ignored")
        else:
            # Leaving raw mode regenerates from the form, discarding manual edits.
            if self.preview.toPlainText().strip():
                reply = QMessageBox.question(
                    self, "Switch to Builder?",
                    "Builder mode regenerates the query from the form. "
                    "Your manual edits will be lost. Continue?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    self.raw_mode_check.blockSignals(True)
                    self.raw_mode_check.setChecked(True)
                    self.raw_mode_check.blockSignals(False)
                    return
            self._raw_mode = False
            self.preview.setReadOnly(True)
            self._refresh_preview()
            self.status_message.emit("Builder mode")

    def _refresh_preview(self):
        if not hasattr(self, "time_enabled") or not hasattr(self, "preview"):
            return
        if getattr(self, "_raw_mode", False):
            return  # form changes never overwrite hand-edited raw KQL
        table = self.table_combo.currentText()
        if not table:
            return

        time_range = None
        if self.time_enabled.isChecked():
            time_range = f"{self.time_value.value()}{self.time_unit.currentText()}"

        filters = [r.get_state() for r in self._filter_rows]

        project_cols = []
        for i in range(self.project_list.count()):
            item = self.project_list.item(i)
            if item.checkState() == Qt.Checked:
                project_cols.append(item.text())
        project_cols = project_cols or None

        sort_col = self.sort_combo.currentText()
        if sort_col == "(none)":
            sort_col = None
        sort_dir = self.sort_dir_combo.currentText()

        limit = self.limit_spin.value() if self.limit_spin.value() > 0 else None

        query = build_query(
            table=table,
            filters=filters,
            time_range=time_range,
            project_cols=project_cols,
            sort_col=sort_col,
            sort_dir=sort_dir,
            limit=limit,
        )
        self.preview.setPlainText(query)

    def _copy_to_clipboard(self):
        from PySide6.QtWidgets import QApplication
        text = self.preview.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            original = self.copy_btn.text()
            self.copy_btn.setText("Copied!")
            QTimer.singleShot(2000, lambda: self.copy_btn.setText(original))
            self.status_message.emit("Query copied to clipboard")

    def _clear_form(self):
        if getattr(self, "_raw_mode", False):
            self.preview.clear()
            self.query_name_edit.clear()
            self.status_message.emit("Raw query cleared")
            return
        self.time_enabled.setChecked(True)
        self.time_value.setValue(1)
        self.time_unit.setCurrentIndex(0)

        while len(self._filter_rows) > 1:
            row = self._filter_rows.pop()
            self._filters_container.removeWidget(row)
            row.deleteLater()
        if self._filter_rows:
            self._filter_rows[0].update_columns(self._get_current_columns())

        for i in range(self.project_list.count()):
            self.project_list.item(i).setCheckState(Qt.Unchecked)

        ts_col = self._get_time_column(self.table_combo.currentText())
        ts_idx = self.sort_combo.findText(ts_col)
        if ts_idx >= 0:
            self.sort_combo.setCurrentIndex(ts_idx)
        self.sort_dir_combo.setCurrentIndex(0)
        self.limit_spin.setValue(100)

        self._update_remove_buttons()
        self._refresh_preview()
        self.status_message.emit("Form cleared")

    def _get_form_state(self):
        selected_cols = [
            self.project_list.item(i).text()
            for i in range(self.project_list.count())
            if self.project_list.item(i).checkState() == Qt.Checked
        ]
        return {
            "category": self.category_combo.currentText(),
            "table": self.table_combo.currentText(),
            "time_range": {
                "enabled": self.time_enabled.isChecked(),
                "value": self.time_value.value(),
                "unit": self.time_unit.currentText(),
            },
            "filters": [r.get_state() for r in self._filter_rows],
            "project_columns": selected_cols,
            "sort": {
                "column": self.sort_combo.currentText(),
                "direction": self.sort_dir_combo.currentText(),
            },
            "limit": self.limit_spin.value(),
        }

    def _set_form_state(self, state):
        cat = state.get("category", "")
        cat_idx = self.category_combo.findText(cat)
        if cat_idx >= 0:
            self.category_combo.setCurrentIndex(cat_idx)

        table = state.get("table", "")
        tbl_idx = self.table_combo.findText(table)
        if tbl_idx >= 0:
            self.table_combo.setCurrentIndex(tbl_idx)

        tr = state.get("time_range", {})
        self.time_enabled.setChecked(tr.get("enabled", True))
        self.time_value.setValue(tr.get("value", 1))
        unit_idx = self.time_unit.findText(tr.get("unit", "d"))
        if unit_idx >= 0:
            self.time_unit.setCurrentIndex(unit_idx)

        for row in list(self._filter_rows):
            self._filter_rows.remove(row)
            self._filters_container.removeWidget(row)
            row.deleteLater()

        filter_states = state.get("filters", [])
        for fs in filter_states:
            self._add_filter_row()
            self._filter_rows[-1].set_state(fs)

        proj_cols = state.get("project_columns", [])
        for i in range(self.project_list.count()):
            item = self.project_list.item(i)
            item.setCheckState(Qt.Checked if item.text() in proj_cols else Qt.Unchecked)

        sort = state.get("sort", {})
        sort_col = sort.get("column", "(none)")
        sort_idx = self.sort_combo.findText(sort_col)
        if sort_idx >= 0:
            self.sort_combo.setCurrentIndex(sort_idx)
        sort_dir = sort.get("direction", "desc")
        dir_idx = self.sort_dir_combo.findText(sort_dir)
        if dir_idx >= 0:
            self.sort_dir_combo.setCurrentIndex(dir_idx)

        self.limit_spin.setValue(state.get("limit", 100))

        self._update_remove_buttons()
        self._refresh_preview()

    def _load_library(self):
        if not LIBRARY_PATH.exists():
            return {"version": 1, "queries": {}}
        try:
            data = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
            if "queries" not in data:
                return {"version": 1, "queries": {}}
            return data
        except (json.JSONDecodeError, OSError):
            return {"version": 1, "queries": {}}

    def _save_library(self, data):
        LIBRARY_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load_library_list(self):
        lib = self._load_library()
        self.library_list.clear()
        for name in sorted(lib["queries"].keys()):
            item = QListWidgetItem(name)
            if lib["queries"][name].get("kind") == "raw":
                item.setForeground(QColor("#ce9178"))
                item.setToolTip("Raw KQL query (free-form, loads into the editor)")
            self.library_list.addItem(item)

    def _save_query(self):
        name = self.query_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Save Query", "Please enter a query name.")
            return

        lib = self._load_library()
        if name in lib["queries"]:
            reply = QMessageBox.question(
                self, "Overwrite?",
                f'A query named "{name}" already exists. Overwrite?',
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        if getattr(self, "_raw_mode", False):
            text = self.preview.toPlainText().strip()
            if not text:
                QMessageBox.warning(self, "Save Query", "The raw query is empty.")
                return
            lib["queries"][name] = {
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "kind": "raw",
                "raw": self.preview.toPlainText(),
            }
        else:
            lib["queries"][name] = {
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "kind": "structured",
                **self._get_form_state(),
            }
        self._save_library(lib)
        self._load_library_list()
        self.status_message.emit(f'Query "{name}" saved')

    def _load_query(self):
        item = self.library_list.currentItem()
        if not item:
            QMessageBox.information(self, "Load Query", "Select a query from the library first.")
            return

        name = item.text()
        lib = self._load_library()
        state = lib["queries"].get(name)
        if not state:
            QMessageBox.warning(self, "Load Query", f'Query "{name}" not found.')
            return

        if state.get("kind") == "raw":
            # Raw queries can't drive the form — load straight into the editor.
            self.raw_mode_check.blockSignals(True)
            self.raw_mode_check.setChecked(True)
            self.raw_mode_check.blockSignals(False)
            self._raw_mode = True
            self.preview.setReadOnly(False)
            self.preview.setPlainText(state.get("raw", ""))
        else:
            if getattr(self, "_raw_mode", False):
                self.raw_mode_check.blockSignals(True)
                self.raw_mode_check.setChecked(False)
                self.raw_mode_check.blockSignals(False)
                self._raw_mode = False
                self.preview.setReadOnly(True)
            self._set_form_state(state)
        self.query_name_edit.setText(name)
        self.status_message.emit(f'Query "{name}" loaded')

    def _delete_query(self):
        item = self.library_list.currentItem()
        if not item:
            QMessageBox.information(self, "Delete Query", "Select a query to delete.")
            return

        name = item.text()
        reply = QMessageBox.question(
            self, "Delete Query",
            f'Delete query "{name}"?',
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        lib = self._load_library()
        lib["queries"].pop(name, None)
        self._save_library(lib)
        self._load_library_list()
        self.status_message.emit(f'Query "{name}" deleted')
