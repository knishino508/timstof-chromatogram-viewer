# main_en.py
import sys
import csv
import time
from pathlib import Path
import numpy as np
import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QLabel, QDoubleSpinBox, QSpinBox,
    QGroupBox, QListWidget, QListWidgetItem, QCheckBox, QScrollArea,
    QDialog, QDialogButtonBox, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
import pyqtgraph as pg


class DataContainer:
    """Holds data for one file"""
    def __init__(self, path):
        self.path = path
        self.name = path.name
        self.D = None
        self.ms1_ids = None
        self.ms2_ids = None
        self.rt = None
        self.rt_ms2 = None
        self.tic = None
        self.bpi = None
        self.tic_ms2 = None
        self.bpi_ms2 = None
        self.loaded = False
        self.multi_xic = None  # Multi XIC cache
        self.multi_xic_params = None  # Cache key (mz_list, tol_list)
        self.rtqc_rt_table = None  # {precursor_id: {run_name: (rt_start, rt_end)}}
        # Pump pressure data
        self.pump_a_rt = None
        self.pump_a_pressure = None
        self.pump_b_rt = None
        self.pump_b_pressure = None
        self.pump_loaded = False
        
    def load(self):
        """Load actual data"""
        if self.loaded:
            return True
        
        from opentimspy.opentims import OpenTIMS
        
        try:
            self.D = OpenTIMS(self.path)
            
            # db.frames から全フレーム情報を一括取得（SQLite直接接続不要）
            frames = self.D.frames  # {'Id', 'Time', 'MsMsType', 'SummedIntensities', 'MaxIntensity', ...}
            
            all_ids = frames['Id']
            all_times = frames['Time']
            all_msms_type = frames['MsMsType']
            all_tic = frames['SummedIntensities']
            all_bpi = frames['MaxIntensity']
            
            # MS1 (MsMsType == 0)
            ms1_mask = all_msms_type == 0
            self.ms1_ids = all_ids[ms1_mask]
            self.rt = all_times[ms1_mask] / 60
            self.tic = all_tic[ms1_mask]
            self.bpi = all_bpi[ms1_mask]  # BPIも同時にキャッシュ
            
            # MS2 (MsMsType != 0)
            ms2_mask = all_msms_type != 0
            if ms2_mask.any():
                self.ms2_ids = all_ids[ms2_mask]
                self.rt_ms2 = all_times[ms2_mask] / 60
                self.tic_ms2 = all_tic[ms2_mask]
                self.bpi_ms2 = all_bpi[ms2_mask]  # MS2 BPIも同時にキャッシュ
            
            self.loaded = True
            return True
            
        except Exception as e:
            print(f"Error loading {self.path}: {e}")
            return False
    
    def load_pump_data(self):
        """Load pump pressure data"""
        if self.pump_loaded:
            return True
        
        try:
            # Search for separation folder
            separation_folders = [f for f in self.path.iterdir() 
                                  if f.is_dir() and 'separation' in f.name.lower()]
            
            if not separation_folders:
                print(f"No separation folder found in {self.path}")
                return False
            
            sep_folder = separation_folders[0]
            
            # Search for pump-a and pump-b files
            pump_a_file = None
            pump_b_file = None
            
            for f in sep_folder.iterdir():
                if 'pump-a' in f.name.lower() and 'pressure' in f.name.lower():
                    pump_a_file = f
                elif 'pump-b' in f.name.lower() and 'pressure' in f.name.lower():
                    pump_b_file = f
            
            if pump_a_file:
                self.pump_a_rt, self.pump_a_pressure = self._parse_pump_file(pump_a_file)
            
            if pump_b_file:
                self.pump_b_rt, self.pump_b_pressure = self._parse_pump_file(pump_b_file)
            
            self.pump_loaded = True
            return True
            
        except Exception as e:
            print(f"Error loading pump data: {e}")
            return False
    
    def _parse_pump_file(self, filepath):
        """Parse pump pressure file"""
        rt_list = []
        pressure_list = []
        
        with open(filepath, 'r') as f:
            lines = f.readlines()
        
        for line in lines[1:]:  # Skip header
            parts = line.strip().split('\t')
            if len(parts) >= 3:
                # Parse Relative Time (00:05:24.697 format)
                time_str = parts[1]
                try:
                    time_parts = time_str.split(':')
                    hours = int(time_parts[0])
                    minutes = int(time_parts[1])
                    seconds = float(time_parts[2])
                    total_minutes = hours * 60 + minutes + seconds / 60
                    
                    pressure = float(parts[2])
                    
                    rt_list.append(total_minutes)
                    pressure_list.append(pressure)
                except:
                    continue
        
        return np.array(rt_list), np.array(pressure_list)


class ChromatogramViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("timsTOF Chromatogram Viewer")
        screen = QApplication.primaryScreen().availableGeometry()
        w = int(screen.width() * 0.9)
        h = int(screen.height() * 0.9)
        x = (screen.width() - w) // 2
        y = (screen.height() - h) // 2
        self.setGeometry(x, y, w, h)

        self.data_dict = {}
        self.plot_height = 150
        self.current_plots = []

        # Persistent settings (survive dialog close)
        self.multi_xic_mz_list       = []
        self.multi_xic_tol_list      = []
        self.multi_xic_rt_list       = []
        self.multi_xic_rt_width_list = []

        # === Central widget: 3-pane layout ===
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # ── LEFT PANEL ──────────────────────────────────────────
        left_panel = QWidget()
        left_panel.setFixedWidth(200)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(6, 6, 6, 6)
        left_layout.setSpacing(4)

        # Folder
        folder_group = QGroupBox("Folder")
        folder_layout = QVBoxLayout(folder_group)
        folder_layout.setSpacing(3)
        self.load_btn = QPushButton("Load Parent Folder")
        self.load_btn.clicked.connect(self.load_parent_folder)
        folder_layout.addWidget(self.load_btn)
        self.load_single_btn = QPushButton("Add Single .d")
        self.load_single_btn.clicked.connect(self.load_single_folder)
        folder_layout.addWidget(self.load_single_btn)
        self.clear_btn = QPushButton("Clear List")
        self.clear_btn.clicked.connect(self.clear_all)
        folder_layout.addWidget(self.clear_btn)
        left_layout.addWidget(folder_group)

        # File list
        list_group = QGroupBox("File List")
        list_layout = QVBoxLayout(list_group)
        list_layout.setSpacing(3)
        sel_btn_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("All")
        self.select_all_btn.clicked.connect(self.select_all)
        self.deselect_all_btn = QPushButton("None")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        sel_btn_layout.addWidget(self.select_all_btn)
        sel_btn_layout.addWidget(self.deselect_all_btn)
        list_layout.addLayout(sel_btn_layout)
        self.file_list = QListWidget()
        list_layout.addWidget(self.file_list)
        left_layout.addWidget(list_group)

        # ── Mode buttons ──
        mode_group = QGroupBox("Chromatogram")
        mode_layout = QVBoxLayout(mode_group)
        mode_layout.setSpacing(3)

        btn_style_simple = (
            "QPushButton { text-align: left; padding: 5px 8px; }"
            "QPushButton:hover { background: #ddeeff; }"
        )
        btn_style_dialog = (
            "QPushButton { text-align: left; padding: 5px 8px; }"
            "QPushButton:hover { background: #ddffd8; }"
        )

        # Simple 1-click buttons
        for label, slot in [
            ("TIC  (MS1)",  lambda: self._run_simple(0)),
            ("BPI  (MS1)",  lambda: self._run_simple(1)),
            ("TIC  (MS2)",  lambda: self._run_simple(3)),
            ("BPI  (MS2)",  lambda: self._run_simple(4)),
            ("Pump",        lambda: self._run_simple(5)),
        ]:
            b = QPushButton(label)
            b.setStyleSheet(btn_style_simple)
            b.clicked.connect(slot)
            mode_layout.addWidget(b)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        mode_layout.addWidget(sep)

        # Dialog buttons
        self.xic_btn = QPushButton("XIC  (MS1) ▶")
        self.xic_btn.setStyleSheet(btn_style_dialog)
        self.xic_btn.clicked.connect(self._open_xic_dialog)
        mode_layout.addWidget(self.xic_btn)

        self.mxic_csv_btn = QPushButton("mXIC  CSV ▶")
        self.mxic_csv_btn.setStyleSheet(btn_style_dialog)
        self.mxic_csv_btn.clicked.connect(self._open_mxic_csv_dialog)
        mode_layout.addWidget(self.mxic_csv_btn)

        self.mxic_diann_btn = QPushButton("mXIC  DIA-NN ▶")
        self.mxic_diann_btn.setStyleSheet(btn_style_dialog)
        self.mxic_diann_btn.clicked.connect(self.run_rt_qc)
        mode_layout.addWidget(self.mxic_diann_btn)

        left_layout.addWidget(mode_group)

        # Status
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)
        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(50)
        status_layout.addWidget(self.status_label)
        left_layout.addWidget(status_group)

        left_layout.addStretch()

        main_layout.addWidget(left_panel)

        # ── PLOT AREA ────────────────────────────────────────────
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.plot_container = pg.GraphicsLayoutWidget()
        self.plot_container.setBackground('w')
        self.scroll_area.setWidget(self.plot_container)
        main_layout.addWidget(self.scroll_area)

        # ── RIGHT PANEL (Display settings) ───────────────────────
        right_panel = QWidget()
        right_panel.setFixedWidth(170)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(4)

        disp_group = QGroupBox("Display")
        disp_layout = QVBoxLayout(disp_group)
        disp_layout.setSpacing(6)

        self.overlay_check = QCheckBox("Overlay")
        disp_layout.addWidget(self.overlay_check)

        lw_layout = QHBoxLayout()
        lw_layout.addWidget(QLabel("Line Width:"))
        self.line_width_input = QDoubleSpinBox()
        self.line_width_input.setRange(0.5, 5.0)
        self.line_width_input.setDecimals(1)
        self.line_width_input.setValue(1.0)
        self.line_width_input.setSingleStep(0.5)
        self.line_width_input.valueChanged.connect(self._update_line_width)
        lw_layout.addWidget(self.line_width_input)
        disp_layout.addLayout(lw_layout)

        right_layout.addWidget(disp_group)

        # RT QC display options
        rtqc_disp_group = QGroupBox("RT QC Display")
        rtqc_disp_layout = QVBoxLayout(rtqc_disp_group)
        rtqc_disp_layout.setSpacing(6)

        self.rtqc_redline_check = QCheckBox("RT median line")
        self.rtqc_redline_check.setChecked(True)
        self.rtqc_redline_check.stateChanged.connect(self._toggle_rtqc_redlines)
        rtqc_disp_layout.addWidget(self.rtqc_redline_check)

        # RT bins setting (moved here from dialog)
        bins_layout = QHBoxLayout()
        bins_layout.addWidget(QLabel("RT bins:"))
        self.rtqc_bins_input = QSpinBox()
        self.rtqc_bins_input.setRange(2, 20)
        self.rtqc_bins_input.setValue(6)
        self.rtqc_bins_input.setToolTip(
            "RT range divided into N bins.\n"
            "Top 2 peptides per bin. Max = bins × 2."
        )
        bins_layout.addWidget(self.rtqc_bins_input)
        rtqc_disp_layout.addLayout(bins_layout)

        self.rtqc_info = QLabel("No parquet loaded")
        self.rtqc_info.setWordWrap(True)
        self.rtqc_info.setStyleSheet("font-size: 10px; color: #444;")
        rtqc_disp_layout.addWidget(self.rtqc_info)

        right_layout.addWidget(rtqc_disp_group)
        right_layout.addStretch()

        main_layout.addWidget(right_panel)

        # Stretch: left=0 (fixed), center=1 (expand), right=0 (fixed)
        main_layout.setStretch(0, 0)
        main_layout.setStretch(1, 1)
        main_layout.setStretch(2, 0)

        # Storage for live-update
        self._current_plot_items = []  # (PlotDataItem, color) for line width update
        self._rtqc_redlines      = []  # (InfiniteLine, plot) for show/hide

        # Hidden storage widgets (kept for logic compatibility)
        self.mz_input = QDoubleSpinBox()
        self.mz_input.setRange(0, 10000)
        self.mz_input.setDecimals(4)
        self.mz_input.setValue(696.6600)
        self.mz_input.setSingleStep(0.0001)

        self.ppm_input = QSpinBox()
        self.ppm_input.setRange(1, 100)
        self.ppm_input.setValue(10)

        self.rt_center_input = QDoubleSpinBox()
        self.rt_center_input.setRange(0, 9999)
        self.rt_center_input.setDecimals(2)
        self.rt_center_input.setValue(41.0)

        self.rt_width_input = QDoubleSpinBox()
        self.rt_width_input.setRange(0.1, 999)
        self.rt_width_input.setDecimals(2)
        self.rt_width_input.setValue(1.0)

        self.scan_stride_input = QSpinBox()
        self.scan_stride_input.setRange(1, 800)
        self.scan_stride_input.setValue(3)

        self.multi_xic_info = QLabel("No CSV loaded")
        self.update_btn = QPushButton("Update")
        self.multi_xic_btn = QPushButton("mXIC CSV")
        self.rtqc_btn = QPushButton("RT QC")

    # ── Dialog launchers ────────────────────────────────────────

    def _run_simple(self, mode_id):
        """Run TIC/BPI/Pump directly (no dialog needed)."""
        # Temporarily set mode and call update
        self._current_mode_override = mode_id
        self.update_plot()
        self._current_mode_override = None

    def _open_xic_dialog(self):
        """Open XIC settings dialog."""
        dlg = QDialog(self)
        dlg.setWindowTitle("XIC (MS1) Settings")
        dlg.setMinimumWidth(280)
        layout = QVBoxLayout(dlg)

        # m/z
        mz_layout = QHBoxLayout()
        mz_layout.addWidget(QLabel("m/z:"))
        mz_spin = QDoubleSpinBox()
        mz_spin.setRange(0, 10000)
        mz_spin.setDecimals(4)
        mz_spin.setValue(self.mz_input.value())
        mz_spin.setSingleStep(0.0001)
        mz_layout.addWidget(mz_spin)
        layout.addLayout(mz_layout)

        # ppm
        ppm_layout = QHBoxLayout()
        ppm_layout.addWidget(QLabel("± ppm:"))
        ppm_spin = QSpinBox()
        ppm_spin.setRange(1, 100)
        ppm_spin.setValue(self.ppm_input.value())
        ppm_spin.setSuffix(" ppm")
        ppm_layout.addWidget(ppm_spin)
        layout.addLayout(ppm_layout)

        # Center RT
        rt_c_layout = QHBoxLayout()
        rt_c_layout.addWidget(QLabel("Center RT:"))
        rt_c_spin = QDoubleSpinBox()
        rt_c_spin.setRange(0, 9999)
        rt_c_spin.setDecimals(2)
        rt_c_spin.setValue(self.rt_center_input.value())
        rt_c_spin.setSuffix(" min")
        rt_c_layout.addWidget(rt_c_spin)
        layout.addLayout(rt_c_layout)

        # RT width
        rt_w_layout = QHBoxLayout()
        rt_w_layout.addWidget(QLabel("± Width:"))
        rt_w_spin = QDoubleSpinBox()
        rt_w_spin.setRange(0.1, 999)
        rt_w_spin.setDecimals(2)
        rt_w_spin.setValue(self.rt_width_input.value())
        rt_w_spin.setSuffix(" min")
        rt_w_layout.addWidget(rt_w_spin)
        layout.addLayout(rt_w_layout)

        # Scan stride
        st_layout = QHBoxLayout()
        st_layout.addWidget(QLabel("Scan stride:"))
        st_spin = QSpinBox()
        st_spin.setRange(1, 800)
        st_spin.setValue(self.scan_stride_input.value())
        st_spin.setToolTip(
            "Scan decimation step.\n"
            "1 = all scans, 3 = every 3rd scan.\n"
            "Reduces load time at the cost of accuracy."
        )
        st_layout.addWidget(st_spin)
        layout.addLayout(st_layout)

        # Buttons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.mz_input.setValue(mz_spin.value())
            self.ppm_input.setValue(ppm_spin.value())
            self.rt_center_input.setValue(rt_c_spin.value())
            self.rt_width_input.setValue(rt_w_spin.value())
            self.scan_stride_input.setValue(st_spin.value())
            self._current_mode_override = 2
            self.update_plot()
            self._current_mode_override = None

    def _open_mxic_csv_dialog(self):
        """Open mXIC CSV dialog."""
        dlg = QDialog(self)
        dlg.setWindowTitle("mXIC (MS1 - CSV)")
        dlg.setMinimumWidth(320)
        layout = QVBoxLayout(dlg)

        # CSV file path
        csv_layout = QHBoxLayout()
        csv_layout.addWidget(QLabel("CSV:"))
        csv_label = QLabel("(not selected)")
        csv_label.setWordWrap(True)
        csv_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        csv_layout.addWidget(csv_label)
        browse_btn = QPushButton("Browse...")

        self._pending_csv_path = None

        def browse_csv():
            path, _ = QFileDialog.getOpenFileName(
                dlg, "Select CSV", "", "CSV Files (*.csv)"
            )
            if path:
                self._pending_csv_path = path
                csv_label.setText(Path(path).name)

        browse_btn.clicked.connect(browse_csv)
        layout.addLayout(csv_layout)
        layout.addWidget(browse_btn)

        # Scan stride
        st_layout = QHBoxLayout()
        st_layout.addWidget(QLabel("Scan stride:"))
        st_spin = QSpinBox()
        st_spin.setRange(1, 800)
        st_spin.setValue(self.scan_stride_input.value())
        st_layout.addWidget(st_spin)
        layout.addLayout(st_layout)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.scan_stride_input.setValue(st_spin.value())
            if self._pending_csv_path:
                self._load_csv_and_run(self._pending_csv_path)
            else:
                self.status_label.setText("No CSV selected")

    def load_parent_folder(self):
        """Select parent folder and search for .d folders"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Parent Folder",
            "",
            QFileDialog.Option.ShowDirsOnly
        )
        
        if not folder:
            return
        
        parent_path = Path(folder)
        
        # Search for .d folders directly under parent
        d_folders = sorted([f for f in parent_path.iterdir() 
                           if f.is_dir() and f.suffix == '.d'])
        
        if not d_folders:
            self.status_label.setText(f"No folders found:\n{parent_path.name}")
            return
        
        # Add to list
        added_count = 0
        for d_folder in d_folders:
            if d_folder not in self.data_dict:
                # Create DataContainer (don't load yet)
                self.data_dict[d_folder] = DataContainer(d_folder)
                
                # Add to list (with checkbox)
                item = QListWidgetItem(d_folder.name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                item.setData(Qt.ItemDataRole.UserRole, d_folder)  # Save path
                self.file_list.addItem(item)
                added_count += 1
        
        self.status_label.setText(f"Added: {added_count} files\nTotal: {self.file_list.count()} files")
        
    def load_single_folder(self):
        """Select and add a single .d folder"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select .d Folder",
            "",
            QFileDialog.Option.ShowDirsOnly
        )
        
        if not folder:
            return
        
        folder_path = Path(folder)
        
        if folder_path.suffix != '.d':
            self.status_label.setText("Error:\nPlease select a .d folder")
            return
        
        if folder_path in self.data_dict:
            self.status_label.setText(f"Skipped:\n{folder_path.name}\n(Already added)")
            return
        
        # Create DataContainer
        self.data_dict[folder_path] = DataContainer(folder_path)
        
        # Add to list (with checkbox, checked by default)
        item = QListWidgetItem(folder_path.name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked)
        item.setData(Qt.ItemDataRole.UserRole, folder_path)
        self.file_list.addItem(item)
        
        self.status_label.setText(f"Added:\n{folder_path.name}")
        
    def get_checked_paths(self):
        """Get list of checked file paths"""
        checked = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                path = item.data(Qt.ItemDataRole.UserRole)
                checked.append(path)
        return checked
    
    def select_all(self):
        """Select all"""
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(Qt.CheckState.Checked)
    
    def deselect_all(self):
        """Deselect all"""
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(Qt.CheckState.Unchecked)
    
    def clear_all(self):
        """Clear all data"""
        self.data_dict.clear()
        self.file_list.clear()
        self.plot_container.clear()
        self.status_label.setText("Cleared")
    
    def calculate_bpi(self, data):
        """Calculate BPI (loaded from db.frames['MaxIntensity'] at load time)"""
        # data.bpi はロード時に db.frames['MaxIntensity'] から既にキャッシュ済み
        return data.bpi
    
    def calculate_xic(self, data, target_mz, ppm, rt_start=None, rt_end=None, scan_stride=1):
        """Calculate XIC — RT範囲内のデータのみ返す (rt_arr, intensity_arr) のペア

        Returns
        -------
        rt_arr        : np.ndarray  RT範囲内のRT配列 (min)
        intensity_arr : np.ndarray  対応するXIC強度配列
        """
        self.status_label.setText(f"Calculating XIC:\n{data.name}")
        
        mz_tol = target_mz * ppm / 1e6
        mz_min = target_mz - mz_tol
        mz_max = target_mz + mz_tol
        
        # RT範囲でMS1フレームを絞り込む
        if rt_start is not None and rt_end is not None and rt_end > rt_start:
            rt_mask = (data.rt >= rt_start) & (data.rt <= rt_end)
        else:
            rt_mask = np.ones(len(data.ms1_ids), dtype=bool)
        
        target_ids = data.ms1_ids[rt_mask]
        target_rt  = data.rt[rt_mask]       # RT範囲内のRT配列（そのまま返す）
        
        if len(target_ids) == 0:
            return target_rt, np.zeros(0, dtype=np.float64)
        
        # 絞り込んだフレームを1回のAPIコールで取得
        all_data = data.D.query(
            frames=target_ids,
            columns=('frame', 'scan', 'mz', 'intensity')
        )
        
        # Scan間引き: scan % stride == 0 のみ残す（stride=1なら全scan）
        if scan_stride > 1:
            scan_mask = (all_data['scan'] % scan_stride) == 0
            frame_arr = all_data['frame'][scan_mask]
            mz_arr    = all_data['mz'][scan_mask]
            int_arr   = all_data['intensity'][scan_mask].astype(np.float64)
        else:
            frame_arr = all_data['frame']
            mz_arr    = all_data['mz']
            int_arr   = all_data['intensity'].astype(np.float64)
        
        # m/z範囲でマスク
        mz_mask = (mz_arr >= mz_min) & (mz_arr <= mz_max)
        filtered_frames      = frame_arr[mz_mask]
        filtered_intensities = int_arr[mz_mask]
        
        # frame_id → インデックス変換 + np.add.at で集計
        frame_to_idx = np.searchsorted(target_ids, filtered_frames)
        intensity_arr = np.zeros(len(target_ids), dtype=np.float64)
        np.add.at(intensity_arr, frame_to_idx, filtered_intensities)
        
        return target_rt, intensity_arr
    
    def calculate_bpi_ms2(self, data):
        """Calculate MS2 BPI (loaded from db.frames['MaxIntensity'] at load time)"""
        if data.ms2_ids is None:
            return None
        # data.bpi_ms2 はロード時に db.frames['MaxIntensity'] から既にキャッシュ済み
        return data.bpi_ms2
    
    def calculate_multi_xic(self, data, mz_list, tol_list, rt_start=None, rt_end=None, scan_stride=1):
        """Calculate Multi XIC — RT絞り込み + Scan間引き + np.add.at で高速集計"""
        # Check cache (scan_strideもキャッシュキーに含める)
        params = (tuple(mz_list), tuple(tol_list), rt_start, rt_end, scan_stride)
        if data.multi_xic is not None and data.multi_xic_params == params:
            return data.multi_xic
        
        self.status_label.setText(f"Calculating Multi XIC:\n{data.name}\n({len(mz_list)} targets)")
        
        # Build m/z ranges
        mz_ranges = []
        for mz, tol in zip(mz_list, tol_list):
            mz_tol = mz * tol / 1e6
            mz_ranges.append((mz - mz_tol, mz + mz_tol))
        
        # RT範囲でMS1フレームを絞り込む
        if rt_start is not None and rt_end is not None and rt_end > rt_start:
            rt_mask = (data.rt >= rt_start) & (data.rt <= rt_end)
            target_ids = data.ms1_ids[rt_mask]
        else:
            rt_mask = np.ones(len(data.ms1_ids), dtype=bool)
            target_ids = data.ms1_ids
        
        # 絞り込んだフレームを1回のAPIコールで取得（scan間引きのためscanカラムも取得）
        all_data = data.D.query(
            frames=target_ids,
            columns=('frame', 'scan', 'mz', 'intensity')
        )
        
        # Scan間引き: scan % stride == 0 のみ残す（stride=1なら全scan）
        if scan_stride > 1:
            scan_mask = (all_data['scan'] % scan_stride) == 0
            frame_arr = all_data['frame'][scan_mask]
            mz_arr    = all_data['mz'][scan_mask]
            int_arr   = all_data['intensity'][scan_mask].astype(np.float64)
        else:
            frame_arr = all_data['frame']
            mz_arr    = all_data['mz']
            int_arr   = all_data['intensity'].astype(np.float64)
        
        # 全ターゲットのマスクを一括作成してOR結合
        combined_mask = np.zeros(len(mz_arr), dtype=bool)
        for mz_min, mz_max in mz_ranges:
            combined_mask |= (mz_arr >= mz_min) & (mz_arr <= mz_max)
        
        filtered_frames = frame_arr[combined_mask]
        filtered_intensities = int_arr[combined_mask]
        
        # np.add.at でループなし集計
        frame_to_idx = np.searchsorted(target_ids, filtered_frames)
        xic_target = np.zeros(len(target_ids), dtype=np.float64)
        np.add.at(xic_target, frame_to_idx, filtered_intensities)
        
        # 全フレーム分の配列に戻す
        multi_xic = np.zeros(len(data.ms1_ids), dtype=np.float64)
        multi_xic[rt_mask] = xic_target
        
        data.multi_xic = multi_xic
        data.multi_xic_params = params
        return data.multi_xic
    
    def run_rt_qc(self):
        """Load DIA-NN report.parquet, auto-select RT QC peptides, run Multi XIC.

        Selection logic:
        1. Filter Q.Value < 0.01
        2. Keep only Precursor.Id detected in ALL runs
        3. Per Precursor.Id: compute median RT, median FWHM, median Ms1.Area
           across runs (robust to outliers)
        4. Divide RT range into N bins
        5. Per bin: pick top-2 by Ms1.Area, enforcing unique Stripped.Sequence
           (avoids duplicate charge states of the same peptide)
        6. Pass selected peptides directly to Multi XIC
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select DIA-NN report.parquet", "", "Parquet Files (*.parquet)"
        )
        if not file_path:
            return

        # Settings dialog
        dlg = QDialog(self)
        dlg.setWindowTitle("mXIC DIA-NN Settings")
        dlg.setMinimumWidth(260)
        dlg_layout = QVBoxLayout(dlg)

        file_label = QLabel(f"File: {Path(file_path).name}")
        file_label.setWordWrap(True)
        file_label.setStyleSheet("font-size: 10px; color: #444;")
        dlg_layout.addWidget(file_label)

        st_layout = QHBoxLayout()
        st_layout.addWidget(QLabel("Scan stride:"))
        st_spin = QSpinBox()
        st_spin.setRange(1, 800)
        st_spin.setValue(self.scan_stride_input.value())
        st_spin.setToolTip(
            "Scan decimation step.\n"
            "1 = all scans, 3 = every 3rd scan.\n"
            "Reduces load time at the cost of accuracy."
        )
        st_layout.addWidget(st_spin)
        dlg_layout.addLayout(st_layout)

        margin_layout = QHBoxLayout()
        margin_layout.addWidget(QLabel("RT margin:"))
        margin_spin = QDoubleSpinBox()
        margin_spin.setRange(0.0, 10.0)
        margin_spin.setDecimals(2)
        margin_spin.setSingleStep(0.25)
        margin_spin.setValue(getattr(self, '_rtqc_margin', 1.0))
        margin_spin.setToolTip(
            "Margin added to both sides of the peak window.\n"
            "Multiplied by peak width (RT.Stop - RT.Start).\n"
            "e.g. 1.0 = add one peak-width on each side."
        )
        margin_layout.addWidget(margin_spin)
        dlg_layout.addLayout(margin_layout)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        dlg_layout.addWidget(btn_box)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        self.scan_stride_input.setValue(st_spin.value())
        self._rtqc_margin = margin_spin.value()

        self.mxic_diann_btn.setEnabled(False)
        self.rtqc_info.setText("Loading parquet...")
        QApplication.processEvents()

        try:
            self._run_rt_qc_impl(file_path, margin=self._rtqc_margin)
        except Exception as e:
            self.rtqc_info.setText(f"Error:\n{e}")
            import traceback
            traceback.print_exc()
        finally:
            self.mxic_diann_btn.setEnabled(True)

    def _run_rt_qc_impl(self, file_path: str, margin: float = 1.0):
        """RT QC implementation"""
        needed_cols = [
            'Run', 'Precursor.Id', 'Precursor.Mz',
            'Stripped.Sequence', 'RT', 'RT.Start', 'RT.Stop',
            'Ms1.Area', 'Q.Value',
        ]

        self.rtqc_info.setText("Reading parquet...")
        QApplication.processEvents()

        df = pd.read_parquet(file_path, columns=needed_cols)

        # --- Step 1: quality filter ---
        df = df[df['Q.Value'] < 0.01].copy()
        if df.empty:
            self.rtqc_info.setText("Error:\nNo rows pass Q.Value < 0.01")
            return

        all_runs = df['Run'].unique()
        n_runs = len(all_runs)

        self.rtqc_info.setText(f"Filtering ({n_runs} runs)...")
        QApplication.processEvents()

        # --- Step 2: keep Precursor.Id detected in ALL runs ---
        run_counts = df.groupby('Precursor.Id')['Run'].nunique()
        common_ids = run_counts[run_counts == n_runs].index
        df = df[df['Precursor.Id'].isin(common_ids)]

        if df.empty:
            self.rtqc_info.setText(
                f"Error:\nNo precursor detected in all {n_runs} runs.\n"
                "Try reducing the number of runs loaded."
            )
            return

        # --- Step 3: per-precursor summary (median across runs) ---
        summary = df.groupby(['Precursor.Id', 'Precursor.Mz', 'Stripped.Sequence']).agg(
            rt_median=('RT', 'median'),
            ms1_median=('Ms1.Area', 'median'),
        ).reset_index()

        # --- Step 4: RT bin assignment ---
        n_bins = self.rtqc_bins_input.value()
        rt_min = summary['rt_median'].min()
        rt_max = summary['rt_median'].max()
        bin_edges = np.linspace(rt_min, rt_max, n_bins + 1)
        summary['rt_bin'] = pd.cut(
            summary['rt_median'],
            bins=bin_edges,
            labels=False,
            include_lowest=True
        )

        # --- Step 5: select top-2 per bin (unique Stripped.Sequence) ---
        selected_rows = []
        for bin_idx in range(n_bins):
            bin_df = summary[summary['rt_bin'] == bin_idx].copy()
            if bin_df.empty:
                continue
            bin_df = bin_df.sort_values('ms1_median', ascending=False)
            seen_seqs = set()
            count = 0
            for _, row in bin_df.iterrows():
                if row['Stripped.Sequence'] in seen_seqs:
                    continue
                seen_seqs.add(row['Stripped.Sequence'])
                selected_rows.append(row)
                count += 1
                if count >= 2:
                    break

        if not selected_rows:
            self.rtqc_info.setText("Error:\nNo peptides selected")
            return

        selected = pd.DataFrame(selected_rows)

        # --- Step 6: build per-Run RT table ---
        # rtqc_rt_table: {precursor_id: {run_name: (rt_start, rt_end)}}
        # Use RT.Start / RT.Stop with configurable margin on each side
        # margin = peak_width × factor (clipped to min 0.05 min)
        selected_ids = set(selected['Precursor.Id'])
        df_sel = df[df['Precursor.Id'].isin(selected_ids)].copy()
        df_sel['peak_width'] = df_sel['RT.Stop'] - df_sel['RT.Start']
        df_sel['margin']     = (df_sel['peak_width'] * margin).clip(lower=0.05)
        df_sel['win_start']  = df_sel['RT.Start'] - df_sel['margin']
        df_sel['win_end']    = df_sel['RT.Stop']  + df_sel['margin']

        rtqc_rt_table = {}
        for pid, grp in df_sel.groupby('Precursor.Id'):
            rtqc_rt_table[pid] = {
                row['Run']: (float(row['win_start']), float(row['win_end']))
                for _, row in grp.iterrows()
            }

        # Store for use in update_rtqc_plot
        self.rtqc_rt_table = rtqc_rt_table
        self.rtqc_selected = selected  # DataFrame: Precursor.Id, Precursor.Mz, Stripped.Sequence
        self.rtqc_ppm      = self.ppm_input.value()

        # Build display summary
        lines = [f"RT QC: {len(selected)} peptides selected"]
        lines.append(f"Runs: {n_runs}  |  Bins: {n_bins}")
        lines.append(f"RT: {rt_min:.1f} – {rt_max:.1f} min")
        lines.append("")
        for _, row in selected.iterrows():
            lines.append(
                f"[{row['rt_median']:.1f} min] {row['Stripped.Sequence']}"
                f"  m/z={row['Precursor.Mz']:.4f}"
            )
        self.rtqc_info.setText("\n".join(lines))

        print(f"[RT QC] {len(selected)} peptides selected from {n_runs} runs")
        for _, row in selected.iterrows():
            print(f"  RT={row['rt_median']:.2f}  mz={row['Precursor.Mz']:.4f}"
                  f"  seq={row['Stripped.Sequence']}"
                  f"  ms1={row['ms1_median']:.0f}")

        QApplication.processEvents()

        # --- Run RT QC plot with per-run RT windows ---
        self.update_rtqc_plot()

    def update_rtqc_plot(self):
        """RT QC plot: each file uses its own per-run RT window from DIA-NN result."""
        _t_start = time.perf_counter()
        self.mxic_diann_btn.setEnabled(False)
        try:
            self._update_rtqc_plot_impl()
        finally:
            self.mxic_diann_btn.setEnabled(True)
            elapsed = time.perf_counter() - _t_start
            print(f"[update_rtqc_plot] elapsed={elapsed:.3f}s")

    def _update_rtqc_plot_impl(self):
        """RT QC plot implementation using per-run RT windows."""
        checked_paths = self.get_checked_paths()
        if not checked_paths:
            self.plot_container.clear()
            self.status_label.setText("Please select files")
            return

        if not hasattr(self, 'rtqc_rt_table') or self.rtqc_rt_table is None:
            self.status_label.setText("Please load report.parquet first")
            return

        # Load MS data for checked files
        data_list = []
        for path in checked_paths:
            data = self.data_dict[path]
            if not data.loaded:
                self.status_label.setText(f"Loading:\n{data.name}")
                QApplication.processEvents()
                if not data.load():
                    continue
            data_list.append(data)

        if not data_list:
            self.status_label.setText("No files could be loaded")
            return

        # Build ordered list of selected peptides
        selected     = self.rtqc_selected
        rt_table     = self.rtqc_rt_table
        ppm          = self.rtqc_ppm
        scan_stride  = self.scan_stride_input.value()
        overlay      = self.overlay_check.isChecked()
        n_peptides   = len(selected)

        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                  '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
                  '#FF6600', '#9900FF', '#00CC99', '#FF0066', '#6600FF']

        self.plot_container.clear()

        # --- Overlay mode: single plot, all files × all peptides ---
        # Color = file, each peptide drawn in the same file color
        # Red dashed vertical lines at each peptide's median RT
        if overlay:
            self.plot_container.setMinimumHeight(0)

            plot = self.plot_container.addPlot(row=0, col=0)
            plot.setTitle("RT QC – Overlay", size="10pt")
            plot.setLabel('left', '%')
            plot.setLabel('bottom', 'Retention Time (min)')
            plot.showGrid(x=True, y=True, alpha=0.3)

            red_pen = pg.mkPen(color='#FF0000', width=1,
                               style=Qt.PenStyle.DashLine)

            # Phase 1: collect all XICs, track global_max
            plot_items = []   # (item, rt_arr, intensity)
            all_max    = []

            for i, data in enumerate(data_list):
                color = colors[i % len(colors)]
                pen   = pg.mkPen(color=color, width=self.line_width_input.value())

                for p_idx, (_, prow) in enumerate(selected.iterrows()):
                    pid = prow['Precursor.Id']
                    mz  = float(prow['Precursor.Mz'])

                    run_key = self._match_run_key(data.name, rt_table.get(pid, {}))
                    if run_key is None:
                        continue
                    rt_s, rt_e = rt_table[pid][run_key]

                    self.status_label.setText(
                        f"RT QC {i+1}/{len(data_list)} pep {p_idx+1}/{n_peptides}\n{data.name}")
                    QApplication.processEvents()

                    rt_arr, intensity = self.calculate_xic(
                        data, mz, ppm,
                        rt_start=rt_s,
                        rt_end=rt_e,
                        scan_stride=scan_stride
                    )
                    if len(intensity) == 0:
                        continue

                    peak_max = intensity.max()
                    all_max.append(peak_max)

                    # Temporary per-peptide norm (replaced in Phase 2)
                    tmp = intensity / peak_max * 100 if peak_max > 0 else intensity
                    item = plot.plot(rt_arr, tmp, pen=pen)
                    plot_items.append((item, rt_arr, intensity))

            # Phase 2: rescale with global_max
            self.status_label.setText("RT QC: rescaling...")
            QApplication.processEvents()
            global_max = max(all_max) if all_max else 1.0
            for item, rt_arr, intensity in plot_items:
                norm = intensity / global_max * 100 if global_max > 0 else intensity
                item.setData(rt_arr, norm)

            # Red vertical lines at each peptide's median RT
            self._rtqc_redlines = []
            for rt_med in selected['rt_median'].tolist():
                line = pg.InfiniteLine(pos=rt_med, angle=90, pen=red_pen)
                self._rtqc_redlines.append((line, plot))
                if self.rtqc_redline_check.isChecked():
                    plot.addItem(line)

            # Save plot items for live line-width update
            self._current_plot_items = [
                (item, colors[i % len(colors)])
                for i, data in enumerate(data_list)
                for item in [pi[0] for pi in plot_items
                             if pi[0] in plot.listDataItems()]
            ]
            # Simpler: store all items from plot_items with their file index color
            self._current_plot_items = []
            fi = 0
            for ii, (item, rt_arr, intensity) in enumerate(plot_items):
                # Approximate file index from order
                self._current_plot_items.append((item, None))  # color managed by pen

            self.setup_plot_interaction(plot)
            plot.scene().sigMouseClicked.connect(self.on_double_click)
            self.current_plots = [plot]

        # --- Split mode: one plot per file, all peptides overlaid per file ---
        # Two-phase: Phase1 calculate all XICs and find global_max,
        #            Phase2 redraw with common normalization + vertical RT lines
        else:
            total_height = self.plot_height * len(data_list)
            self.plot_container.setMinimumHeight(total_height)
            plots      = []
            plot_items = []   # (plot_data_item, rt_arr, intensity) for Phase2 redraw
            all_max    = []   # collect all peak maxima for global_max
            # rt_medians: median RT per peptide across all runs (for vertical lines)
            rt_medians = selected['rt_median'].tolist()

            # --- Phase 1: calculate XICs, draw with temporary per-peptide 100% ---
            for i, data in enumerate(data_list):
                plot = self.plot_container.addPlot(row=i, col=0)
                plot.setTitle(data.name, size="10pt")
                plot.setLabel('left', '%')
                plot.showGrid(x=True, y=True, alpha=0.3)
                # No legend: vertical lines serve as peptide position markers

                for p_idx, (_, prow) in enumerate(selected.iterrows()):
                    pid = prow['Precursor.Id']
                    mz  = float(prow['Precursor.Mz'])

                    run_key = self._match_run_key(data.name, rt_table.get(pid, {}))
                    if run_key is None:
                        continue
                    rt_s, rt_e = rt_table[pid][run_key]

                    self.status_label.setText(
                        f"RT QC {i+1}/{len(data_list)} pep {p_idx+1}/{n_peptides}\n{data.name}")
                    QApplication.processEvents()

                    rt_arr, intensity = self.calculate_xic(
                        data, mz, ppm,
                        rt_start=rt_s,
                        rt_end=rt_e,
                        scan_stride=scan_stride
                    )
                    if len(intensity) == 0:
                        continue

                    peak_max = intensity.max()
                    all_max.append(peak_max)

                    # Temporary: draw per-peptide 100% (will be replaced in Phase2)
                    tmp_norm = intensity / peak_max * 100 if peak_max > 0 else intensity
                    color = colors[p_idx % len(colors)]
                    pen = pg.mkPen(color=color, width=self.line_width_input.value())
                    item = plot.plot(rt_arr, tmp_norm, pen=pen)
                    plot_items.append((item, rt_arr, intensity))

                if i == len(data_list) - 1:
                    plot.setLabel('bottom', 'Retention Time (min)')
                else:
                    plot.getAxis('bottom').setStyle(showValues=False)

                self.setup_plot_interaction(plot)
                plots.append(plot)

            # --- Phase 2: rescale all items with global_max ---
            self.status_label.setText("RT QC: rescaling...")
            QApplication.processEvents()

            global_max = max(all_max) if all_max else 1.0
            for item, rt_arr, intensity in plot_items:
                norm = intensity / global_max * 100 if global_max > 0 else intensity
                item.setData(rt_arr, norm)

            # --- Phase 3: add vertical red lines at median RT for each peptide ---
            red_pen = pg.mkPen(color='#FF0000', width=1,
                               style=Qt.PenStyle.DashLine)
            self._rtqc_redlines = []
            for plot in plots:
                for rt_med in rt_medians:
                    line = pg.InfiniteLine(pos=rt_med, angle=90, pen=red_pen)
                    self._rtqc_redlines.append((line, plot))
                    if self.rtqc_redline_check.isChecked():
                        plot.addItem(line)

            # Save plot items for live line-width update
            self._current_plot_items = [(item, None) for item, _, _ in plot_items]

            # --- X-axis sync across all files ---
            if len(plots) > 1:
                for j in range(1, len(plots)):
                    plots[j].setXLink(plots[0])
            if plots:
                plots[0].scene().sigMouseClicked.connect(self.on_double_click)
                self.current_plots = plots

        self.status_label.setText(
            f"RT QC\n{n_peptides} peptides / {len(data_list)} files")

    def _toggle_rtqc_redlines(self, state):
        """Show/hide RT median lines without reloading data."""
        visible = (state == Qt.CheckState.Checked.value)
        for line, plot in getattr(self, '_rtqc_redlines', []):
            if visible:
                if line not in plot.items:
                    plot.addItem(line)
            else:
                if line in plot.items:
                    plot.removeItem(line)

    def _update_line_width(self, value):
        """Update line width of current plot items without reloading data."""
        for item, _ in getattr(self, '_current_plot_items', []):
            pen = item.opts.get('pen')
            if pen is not None:
                new_pen = pg.mkPen(pen.color(), width=value)
                item.setPen(new_pen)

    def _match_run_key(self, data_name: str, run_dict: dict) -> str | None:
        """Match DataContainer.name to a DIA-NN Run key.

        DIA-NN Run values are typically the raw file name without extension,
        e.g. 'PJ2188_Tamura_1_WT_FLAG_IP_timsHT_DIA_Slot2-16_1_8843'
        while data.name is the .d folder name, e.g.
        'PJ2188_Tamura_1_WT_FLAG_IP_timsHT_DIA_Slot2-16_1_8843.d'

        Strategy: strip .d suffix from data_name and try exact match,
        then fall back to substring match.
        """
        if not run_dict:
            return None

        # Exact match (Run == data_name)
        if data_name in run_dict:
            return data_name

        # Strip .d suffix
        stem = data_name[:-2] if data_name.endswith('.d') else data_name
        if stem in run_dict:
            return stem

        # Substring match: find a Run key that contains the stem
        for key in run_dict:
            if stem in key or key in stem:
                return key

        return None

    def _load_csv_and_run(self, file_path=None):
        """Load CSV and run Multi XIC
        
        CSV format (required columns: mz, rt):
            mz          : target m/z (Da)
            rt          : center retention time (min)
            mz_tolerance: m/z tolerance in ppm  [optional, fallback to UI value]
            rt_width    : RT window half-width (min) [optional, fallback to UI value]
        """
        if file_path is None:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Select CSV File", "", "CSV Files (*.csv)"
            )
        if not file_path:
            return
        
        try:
            mz_list = []
            tol_list = []
            rt_list = []
            rt_width_list = []
            
            # UI defaults as fallback
            default_ppm = self.ppm_input.value()
            default_rt_width = self.rt_width_input.value()
            
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                
                # Normalize column names (case-insensitive)
                fieldnames_lower = [name.lower().strip() for name in reader.fieldnames]
                if 'mz' not in fieldnames_lower or 'rt' not in fieldnames_lower:
                    self.status_label.setText("Error:\nCSV must have 'mz' and 'rt' columns")
                    return
                
                col_map = {name.lower().strip(): name for name in reader.fieldnames}
                mz_col       = col_map.get('mz')
                rt_col       = col_map.get('rt')
                tol_col      = col_map.get('mz_tolerance')   # optional
                rt_width_col = col_map.get('rt_width')       # optional
                
                for row in reader:
                    try:
                        mz  = float(row[mz_col])
                        rt  = float(row[rt_col])
                        tol = float(row[tol_col]) if tol_col and row.get(tol_col) else default_ppm
                        rtw = float(row[rt_width_col]) if rt_width_col and row.get(rt_width_col) else default_rt_width
                        mz_list.append(mz)
                        rt_list.append(rt)
                        tol_list.append(tol)
                        rt_width_list.append(rtw)
                    except (ValueError, KeyError):
                        continue
            
            if not mz_list:
                self.status_label.setText("Error:\nNo valid data found in CSV")
                return
            
            self.multi_xic_mz_list      = mz_list
            self.multi_xic_tol_list     = tol_list
            self.multi_xic_rt_list      = rt_list
            self.multi_xic_rt_width_list = rt_width_list
            
            self.multi_xic_info.setText(
                f"Loaded: {len(mz_list)} targets\n"
                f"m/z: {mz_list[0]:.4f} – {mz_list[-1]:.4f}\n"
                f"RT:  {min(rt_list):.1f} – {max(rt_list):.1f} min"
            )
            
            self.update_multi_xic_plot()
            
        except Exception as e:
            self.status_label.setText(f"Error loading CSV:\n{e}")
            import traceback
            traceback.print_exc()
    
    def update_multi_xic_plot(self):
        """Update Multi XIC plot"""
        _t_start = time.perf_counter()
        self.mxic_csv_btn.setEnabled(False)
        self.mxic_diann_btn.setEnabled(False)
        try:
            self._update_multi_xic_plot_impl()
        finally:
            self.mxic_csv_btn.setEnabled(True)
            self.mxic_diann_btn.setEnabled(True)
            elapsed = time.perf_counter() - _t_start
            print(f"[update_multi_xic_plot] targets={len(self.multi_xic_mz_list)} elapsed={elapsed:.3f}s")

    def _update_multi_xic_plot_impl(self):
        """update_multi_xic_plot の実装本体"""
        checked_paths = self.get_checked_paths()
        
        if not checked_paths:
            self.plot_container.clear()
            self.status_label.setText("Please select files")
            return
        
        if not self.multi_xic_mz_list:
            self.status_label.setText("Please load CSV first")
            return
        
        # Load data for selected files
        data_list = []
        for path in checked_paths:
            data = self.data_dict[path]
            if not data.loaded:
                self.status_label.setText(f"Loading:\n{data.name}")
                QApplication.processEvents()
                if not data.load():
                    continue
            data_list.append(data)
        
        if not data_list:
            self.status_label.setText("No files could be loaded")
            return
        
        self.plot_container.clear()
        
        overlay = self.overlay_check.isChecked()
        
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                  '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
                  '#FF6600', '#9900FF', '#00CC99', '#FF0066', '#6600FF']
        
        # プロット表示範囲：全ターゲットのRT範囲をカバー
        min_rt = min(rt - w for rt, w in zip(self.multi_xic_rt_list, self.multi_xic_rt_width_list))
        max_rt = max(rt + w for rt, w in zip(self.multi_xic_rt_list, self.multi_xic_rt_width_list))
        min_rt = max(min_rt, 0)

        scan_stride = self.scan_stride_input.value()
        n_targets = len(self.multi_xic_mz_list)
        
        # ターゲットごとにRTが異なる → 各ターゲットのRT範囲内データのみ合算
        # 合算後の (rt_arr, intensity) を numpy の sorted union で扱う
        # 実装: 全ターゲットのRT点を union してから各ターゲットの intensity を補間なしで加算
        #       → 同じフレームを何度も読まないよう、ターゲットごとに (rt, intensity) ペアを取得し
        #          共通RTグリッド（data.rt のうち min_rt〜max_rt 内）に散布して合算する

        # 共通RTグリッド = data.rt のうち表示範囲内のフレームのみ
        intensities = []   # 各ファイルの (rt_grid, combined_intensity)
        rt_grids    = []

        for data in data_list:
            rt_grid_mask = (data.rt >= min_rt) & (data.rt <= max_rt)
            rt_grid  = data.rt[rt_grid_mask]
            grid_ids = data.ms1_ids[rt_grid_mask]
            combined = np.zeros(len(rt_grid), dtype=np.float64)

            for j, (mz, tol, rt_c, rtw) in enumerate(zip(
                self.multi_xic_mz_list,
                self.multi_xic_tol_list,
                self.multi_xic_rt_list,
                self.multi_xic_rt_width_list
            )):
                self.status_label.setText(
                    f"Calc Multi XIC {data_list.index(data)+1}/{len(data_list)} "
                    f"target {j+1}/{n_targets}:\n{data.name}")
                QApplication.processEvents()

                tgt_rt, tgt_int = self.calculate_xic(
                    data, mz, tol,
                    rt_start=rt_c - rtw,
                    rt_end=rt_c + rtw,
                    scan_stride=scan_stride
                )
                if len(tgt_rt) == 0:
                    continue

                # tgt_rt は data.rt のサブセット → searchsorted で rt_grid へ対応付け
                idx_in_grid = np.searchsorted(rt_grid, tgt_rt)
                # 範囲外を除く（念のため）
                valid = (idx_in_grid >= 0) & (idx_in_grid < len(rt_grid))
                np.add.at(combined, idx_in_grid[valid], tgt_int[valid])

            intensities.append(combined)
            rt_grids.append(rt_grid)

        mode_name = f"Multi XIC\n({n_targets} targets)"

        if overlay:
            self.plot_container.setMinimumHeight(0)

            global_max = max((c.max() for c in intensities if len(c) > 0), default=1)

            plot = self.plot_container.addPlot(row=0, col=0)
            plot.setTitle(mode_name.replace('\n', ' '), size="10pt")
            plot.setLabel('left', 'Intensity', units='%')
            plot.setLabel('bottom', 'Retention Time (min)')
            plot.showGrid(x=True, y=True, alpha=0.3)
            plot.addLegend(offset=(10, 10))

            for i, (data, rt_grid, combined) in enumerate(zip(data_list, rt_grids, intensities)):
                intensity_norm = combined / global_max * 100 if global_max > 0 else combined
                color = colors[i % len(colors)]
                pen = pg.mkPen(color=color, width=self.line_width_input.value())
                plot.plot(rt_grid, intensity_norm, pen=pen, name=data.name)

            plot.setXRange(min_rt, max_rt, padding=0.02)
            self.setup_plot_interaction(plot)
            plot.scene().sigMouseClicked.connect(self.on_double_click)
            self.current_plots = [plot]

        else:
            total_height = self.plot_height * len(data_list)
            self.plot_container.setMinimumHeight(total_height)

            plots = []
            for i, (data, rt_grid, combined) in enumerate(zip(data_list, rt_grids, intensities)):
                max_val = combined.max() if len(combined) > 0 else 0
                intensity_norm = combined / max_val * 100 if max_val > 0 else combined

                plot = self.plot_container.addPlot(row=i, col=0)
                plot.setTitle(data.name, size="10pt")
                plot.setLabel('left', '%')
                plot.showGrid(x=True, y=True, alpha=0.3)

                if i == len(data_list) - 1:
                    plot.setLabel('bottom', 'Retention Time (min)')
                else:
                    plot.getAxis('bottom').setStyle(showValues=False)

                color = colors[i % len(colors)]
                pen = pg.mkPen(color=color, width=self.line_width_input.value())
                plot.plot(rt_grid, intensity_norm, pen=pen)

                self.setup_plot_interaction(plot)
                plot.setXRange(min_rt, max_rt, padding=0.02)
                plots.append(plot)

            for i in range(1, len(plots)):
                plots[i].setXLink(plots[0])

            plots[0].scene().sigMouseClicked.connect(self.on_double_click)
            self.current_plots = plots

        self.status_label.setText(f"Displaying:\n{mode_name}\n{len(data_list)} files")
    
    def on_double_click(self, evt):
        """Reset all plots on double click"""
        if evt.double():
            mode = getattr(self, '_current_mode_override', None) or 0
            
            # Pump mode
            if mode == 5:
                for plot in self.current_plots:
                    plot.enableAutoRange()
                return
            
            # Normal mode
            checked_paths = self.get_checked_paths()
            if not checked_paths:
                return
            
            data_list = [self.data_dict[p] for p in checked_paths if self.data_dict[p].loaded]
            if not data_list:
                return
            
            # MS2 mode
            if mode in [3, 4]:
                data_list = [d for d in data_list if d.ms2_ids is not None]
                if not data_list:
                    return
                min_rt = min(data.rt_ms2.min() for data in data_list)
                max_rt = max(data.rt_ms2.max() for data in data_list)
            else:
                min_rt = min(data.rt.min() for data in data_list)
                max_rt = max(data.rt.max() for data in data_list)
            
            for plot in self.current_plots:
                plot.setXRange(min_rt, max_rt, padding=0)
                plot.setYRange(0, 105, padding=0)
    
    def setup_plot_interaction(self, plot):
        """Set up plot interaction"""
        vb = plot.getViewBox()
        
        # Right drag for range selection -> zoom
        vb.setMouseMode(pg.ViewBox.RectMode)
        
        # X-axis only zoom
        vb.setMouseEnabled(x=True, y=False)
        
        # Fix Y-axis range
        vb.setYRange(0, 105, padding=0)
        vb.enableAutoRange(axis='y', enable=False)
        
        # Force reset Y-axis on range change
        def on_range_changed():
            vb.setYRange(0, 105, padding=0)
        
        vb.sigRangeChanged.connect(on_range_changed)
                
    def update_plot(self):
        """Update plot"""
        _t_start = time.perf_counter()
        try:
            self._update_plot_impl()
        finally:
            pass
            elapsed = time.perf_counter() - _t_start
            print(f"[update_plot] elapsed={elapsed:.3f}s")

    def _update_plot_impl(self):
        """update_plot の実装本体"""
        checked_paths = self.get_checked_paths()
        
        if not checked_paths:
            self.plot_container.clear()
            self.status_label.setText("Please select files")
            return
        
        mode = getattr(self, '_current_mode_override', None)
        if mode is None:
            mode = 0  # default: TIC MS1
        
        # Pump mode uses separate processing
        if mode == 5:
            self.update_pump_plot(checked_paths)
            return
        
        # Load data for selected files
        data_list = []
        for path in checked_paths:
            data = self.data_dict[path]
            if not data.loaded:
                self.status_label.setText(f"Loading:\n{data.name}")
                QApplication.processEvents()
                if not data.load():
                    continue
            data_list.append(data)
        
        if not data_list:
            self.status_label.setText("No files could be loaded")
            return
        
        # Check for MS2 data in MS2 mode
        if mode in [3, 4]:
            data_list = [d for d in data_list if d.ms2_ids is not None]
            if not data_list:
                self.status_label.setText("No MS2 data available")
                return
        
        self.plot_container.clear()
        
        target_mz = self.mz_input.value()
        ppm = self.ppm_input.value()
        overlay = self.overlay_check.isChecked()
        scan_stride = self.scan_stride_input.value()
        
        # RT range from center ± width (always applied for XIC)
        rt_center = self.rt_center_input.value()
        rt_width = self.rt_width_input.value()
        xic_rt_start = rt_center - rt_width
        xic_rt_end = rt_center + rt_width
        
        if mode == 0:
            mode_name = "TIC (MS1)"
        elif mode == 1:
            mode_name = "BPI (MS1)"
        elif mode == 2:
            mode_name = f"XIC (MS1)\nm/z={target_mz:.4f}\n± {ppm} ppm\nRT: {xic_rt_start:.1f}–{xic_rt_end:.1f} min"
        elif mode == 3:
            mode_name = "TIC (MS2)"
        elif mode == 4:
            mode_name = "BPI (MS2)"
        
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                  '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
                  '#FF6600', '#9900FF', '#00CC99', '#FF0066', '#6600FF']
        
        # Get RT range (different for MS1/MS2)
        if mode in [3, 4]:
            max_rt = max(data.rt_ms2.max() for data in data_list)
            min_rt = min(data.rt_ms2.min() for data in data_list)
        else:
            max_rt = max(data.rt.max() for data in data_list)
            min_rt = min(data.rt.min() for data in data_list)
        
        # === Phase 1: ファイルごとに計算 → 個別100%で即座に仮描画 ===
        intensities = []
        rt_arrays = []

        if not overlay:
            total_height = self.plot_height * len(data_list)
            self.plot_container.setMinimumHeight(total_height)
        else:
            self.plot_container.setMinimumHeight(0)
            # オーバーレイ用プロットを先に作成
            plot_overlay = self.plot_container.addPlot(row=0, col=0)
            plot_overlay.setTitle(mode_name.replace('\n', ' '), size="10pt")
            plot_overlay.setLabel('left', 'Intensity', units='%')
            plot_overlay.setLabel('bottom', 'Retention Time (min)')
            plot_overlay.showGrid(x=True, y=True, alpha=0.3)
            plot_overlay.addLegend(offset=(10, 10))
            plot_overlay.setXRange(min_rt, max_rt, padding=0)
            self.setup_plot_interaction(plot_overlay)
            plot_overlay.scene().sigMouseClicked.connect(self.on_double_click)
            self.current_plots = [plot_overlay]

        plots = []
        plot_items = []  # 再描画用に PlotDataItem を保持

        for i, data in enumerate(data_list):
            # 強度計算 — XICは (rt_arr, intensity) のペアを返す
            if mode == 0:
                intensity = data.tic
                rt_arr = data.rt
            elif mode == 1:
                intensity = self.calculate_bpi(data)
                rt_arr = data.rt
            elif mode == 2:
                self.status_label.setText(f"Calculating XIC ({i+1}/{len(data_list)}):\n{data.name}")
                QApplication.processEvents()
                rt_arr, intensity = self.calculate_xic(
                    data, target_mz, ppm, xic_rt_start, xic_rt_end, scan_stride)
            elif mode == 3:
                intensity = data.tic_ms2
                rt_arr = data.rt_ms2
            elif mode == 4:
                intensity = self.calculate_bpi_ms2(data)
                rt_arr = data.rt_ms2

            intensities.append(intensity)
            rt_arrays.append(rt_arr)

            color = colors[i % len(colors)]
            pen = pg.mkPen(color=color, width=self.line_width_input.value())

            # 仮描画（個別100%正規化）
            max_val = intensity.max() if len(intensity) > 0 else 0
            intensity_norm = intensity / max_val * 100 if max_val > 0 else intensity

            # XICはrt_arr自体が既にRT範囲内のみ → min/max_rtはrt_arrから算出
            plot_min_rt = rt_arr.min() if len(rt_arr) > 0 else min_rt
            plot_max_rt = rt_arr.max() if len(rt_arr) > 0 else max_rt

            if overlay:
                item = plot_overlay.plot(rt_arr, intensity_norm, pen=pen, name=data.name)
                plot_items.append(item)
            else:
                plot = self.plot_container.addPlot(row=i, col=0)
                plot.setTitle(data.name, size="10pt")
                plot.setLabel('left', '%')
                plot.showGrid(x=True, y=True, alpha=0.3)
                if i == len(data_list) - 1:
                    plot.setLabel('bottom', 'Retention Time (min)')
                else:
                    plot.getAxis('bottom').setStyle(showValues=False)
                item = plot.plot(rt_arr, intensity_norm, pen=pen)
                plot_items.append(item)
                self.setup_plot_interaction(plot)
                plot.setXRange(plot_min_rt, plot_max_rt, padding=0.02)
                plots.append(plot)

            QApplication.processEvents()

        if overlay:
            # オーバーレイはrt_arrの全ファイル分の範囲をカバー
            all_rt = np.concatenate([r for r in rt_arrays if len(r) > 0])
            if len(all_rt) > 0:
                plot_overlay.setXRange(all_rt.min(), all_rt.max(), padding=0.02)
        else:
            for j in range(1, len(plots)):
                plots[j].setXLink(plots[0])
            plots[0].scene().sigMouseClicked.connect(self.on_double_click)
            self.current_plots = plots

        # === Phase 2: 全ファイル完了後に global_max で再正規化して再描画 ===
        self.status_label.setText(f"Rescaling...\n{mode_name}")
        QApplication.processEvents()

        global_max = max((i.max() for i in intensities if len(i) > 0), default=1)
        for item, intensity, rt_arr in zip(plot_items, intensities, rt_arrays):
            intensity_norm = intensity / global_max * 100 if global_max > 0 else intensity
            item.setData(rt_arr, intensity_norm)

        self.status_label.setText(f"Displaying:\n{mode_name}\n{len(data_list)} files")
        
    def update_pump_plot(self, checked_paths):
        """Pump pressure plot"""
        _t_start = time.perf_counter()
        data_list = []
        for path in checked_paths:
            data = self.data_dict[path]
            self.status_label.setText(f"Loading pump data:\n{data.name}")
            QApplication.processEvents()
            
            if not data.pump_loaded:
                if not data.load_pump_data():
                    continue
            
            if data.pump_a_rt is not None or data.pump_b_rt is not None:
                data_list.append(data)
        
        if not data_list:
            self.status_label.setText("Pump data not found")
            return
        
        self.plot_container.clear()
        
        overlay = self.overlay_check.isChecked()
        
        # Get RT range for all data
        all_rts = []
        for data in data_list:
            if data.pump_a_rt is not None:
                all_rts.extend([data.pump_a_rt.min(), data.pump_a_rt.max()])
            if data.pump_b_rt is not None:
                all_rts.extend([data.pump_b_rt.min(), data.pump_b_rt.max()])
        
        min_rt = min(all_rts)
        max_rt = max(all_rts)
        
        colors_a = ['#1f77b4', '#2ca02c', '#9467bd', '#17becf', '#bcbd22']  # Blue series
        colors_b = ['#ff7f0e', '#d62728', '#e377c2', '#8c564b', '#FF6600']  # Red series
        
        if overlay:
            self.plot_container.setMinimumHeight(0)
            
            plot = self.plot_container.addPlot(row=0, col=0)
            plot.setTitle("Pump Pressure", size="10pt")
            plot.setLabel('left', 'Pressure (bar)')
            plot.setLabel('bottom', 'Retention Time (min)')
            plot.showGrid(x=True, y=True, alpha=0.3)
            plot.addLegend(offset=(10, 10))
            
            for i, data in enumerate(data_list):
                if data.pump_a_rt is not None:
                    pen_a = pg.mkPen(color=colors_a[i % len(colors_a)], 
                                     width=self.line_width_input.value())
                    plot.plot(data.pump_a_rt, data.pump_a_pressure, 
                             pen=pen_a, name=f"{data.name} - Pump A")
                
                if data.pump_b_rt is not None:
                    pen_b = pg.mkPen(color=colors_b[i % len(colors_b)], 
                                     width=self.line_width_input.value(),
                                     style=Qt.PenStyle.DashLine)
                    plot.plot(data.pump_b_rt, data.pump_b_pressure, 
                             pen=pen_b, name=f"{data.name} - Pump B")
            
            plot.setXRange(min_rt, max_rt, padding=0)
            
            # Y-axis auto scale (absolute pressure value)
            vb = plot.getViewBox()
            vb.setMouseMode(pg.ViewBox.RectMode)
            vb.setMouseEnabled(x=True, y=True)  # Y-axis also zoomable
            
            plot.scene().sigMouseClicked.connect(self.on_double_click)
            self.current_plots = [plot]
            
        else:
            total_height = self.plot_height * len(data_list)
            self.plot_container.setMinimumHeight(total_height)
            
            plots = []
            for i, data in enumerate(data_list):
                plot = self.plot_container.addPlot(row=i, col=0)
                plot.setTitle(data.name, size="10pt")
                plot.setLabel('left', 'bar')
                plot.showGrid(x=True, y=True, alpha=0.3)
                plot.addLegend(offset=(10, 10))
                
                if i == len(data_list) - 1:
                    plot.setLabel('bottom', 'Retention Time (min)')
                else:
                    plot.getAxis('bottom').setStyle(showValues=False)
                
                if data.pump_a_rt is not None:
                    pen_a = pg.mkPen(color='#1f77b4', width=self.line_width_input.value())
                    plot.plot(data.pump_a_rt, data.pump_a_pressure, 
                             pen=pen_a, name="Pump A")
                
                if data.pump_b_rt is not None:
                    pen_b = pg.mkPen(color='#ff7f0e', width=self.line_width_input.value(),
                                    style=Qt.PenStyle.DashLine)
                    plot.plot(data.pump_b_rt, data.pump_b_pressure, 
                             pen=pen_b, name="Pump B")
                
                plot.setXRange(min_rt, max_rt, padding=0)
                
                # Y-axis auto scale
                vb = plot.getViewBox()
                vb.setMouseMode(pg.ViewBox.RectMode)
                vb.setMouseEnabled(x=True, y=True)
                
                plots.append(plot)
            
            for i in range(1, len(plots)):
                plots[i].setXLink(plots[0])
            
            plots[0].scene().sigMouseClicked.connect(self.on_double_click)
            self.current_plots = plots
        
        elapsed = time.perf_counter() - _t_start
        print(f"[update_pump_plot] files={len(data_list)} -> {elapsed:.3f}s")
        self.status_label.setText(f"Displaying:\nPump Pressure\n{len(data_list)} files")


def main():
    app = QApplication(sys.argv)
    viewer = ChromatogramViewer()
    viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
