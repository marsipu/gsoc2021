from functools import partial
from os.path import isfile

import numpy as np
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QAction, QApplication, QComboBox, QLabel, QMainWindow, QMessageBox, QWidget

import mne
from pyqtgraph import time

from prototypes.pyqtgraph_ptyp import PyQtGraphPtyp

backends = {
    "pyqtgraph": [PyQtGraphPtyp, {}],
    "(just) PyQt": [None, {}],
    "VTK": [None, {}]
}


class BenchmarkWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.raw = None
        self.backend_name = None
        self.load_raw()

        self.last_time = None
        self.fps = None

        self.backend_chosen(0)
        self.init_toolbar()

        # Set size to ratio of current desktop
        desk_geometry = QApplication.instance().desktop().availableGeometry()
        width = int(desk_geometry.width() * 0.8)
        height = int(desk_geometry.height() * 0.8)
        self.resize(width, height)

    def load_raw(self):
        if self.raw is None:
            data_path = mne.datasets.sample.data_path()
            raw_fname = data_path + '/MEG/sample/sample_audvis_raw.fif'
            raw_hp_filtered_path = data_path + '/MEG/sample/sample_audvis_1Hz_raw.fif'
            if isfile(raw_hp_filtered_path):
                self.raw = mne.io.read_raw(raw_hp_filtered_path)
            else:
                self.raw = mne.io.read_raw(raw_fname, preload=True)
                self.raw.filter(1, None, n_jobs=-1)
                self.raw.save(raw_hp_filtered_path)
            self.raw.pick_types(eeg=True)

    def init_toolbar(self):
        self.toolbar = self.addToolBar('Tools')
        self.toolbar.addWidget(QLabel('<b>Backend: </b>'))

        self.backend_cmbx = QComboBox()
        self.backend_cmbx.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.backend_cmbx.addItems(backends.keys())
        self.backend_cmbx.activated.connect(self.backend_chosen)
        self.toolbar.addWidget(self.backend_cmbx)

        self.toolbar.addSeparator()

        adecr_time = QAction('-Time', parent=self)
        adecr_time.triggered.connect(partial(self.centralWidget().change_duration, -1))
        self.toolbar.addAction(adecr_time)

        aincr_time = QAction('+Time', parent=self)
        aincr_time.triggered.connect(partial(self.centralWidget().change_duration, 1))
        self.toolbar.addAction(aincr_time)

        adecr_nchan = QAction('-Channels', parent=self)
        adecr_nchan.triggered.connect(partial(self.centralWidget().change_nchan, -1))
        self.toolbar.addAction(adecr_nchan)

        aincr_nchan = QAction('+Channels', parent=self)
        aincr_nchan.triggered.connect(partial(self.centralWidget().change_nchan, 1))
        self.toolbar.addAction(aincr_nchan)

        atest_infini_hscroll = QAction('Test InfiniScroll', parent=self)
        atest_infini_hscroll.triggered.connect(partial(self.centralWidget().infini_hscroll, 20))
        self.toolbar.addAction(atest_infini_hscroll)

        self.toolbar.addSeparator()

        benchmark_functions = [
            'hscroll_benchmark'
        ]
        self.toolbar.addWidget(QLabel('<b>Benchmarks: </b>'))
        self.benchmark_cmbx = QComboBox()
        self.benchmark_cmbx.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.benchmark_cmbx.addItems(benchmark_functions)
        self.toolbar.addWidget(self.benchmark_cmbx)

        astart_bm = QAction('Start', parent=self)
        astart_bm.triggered.connect(self.start_benchmark)
        self.toolbar.addAction(astart_bm)

        astop_bm = QAction('Stop', parent=self)
        astop_bm.triggered.connect(self.stop_benchmark)
        self.toolbar.addAction(astop_bm)

    def backend_chosen(self, idx):
        old_backend = self.backend_name
        self.backend_name = list(backends.keys())[idx]
        new_backend = backends[self.backend_name]
        if new_backend[0] is not None:
            self.setCentralWidget(new_backend[0](self.raw, **new_backend[1]))
        else:
            QMessageBox.warning(self, 'Not implemented!',
                                f'{self.backend_name} is not implemented yet!')
            self.backend_cmbx.setCurrentText(old_backend)

    def show_fps(self):
        now = time()
        dt = now - self.last_time
        self.last_time = now
        if self.fps is None:
            self.fps = 1.0 / dt
        else:
            s = np.clip(dt * 3., 0, 1)
            self.fps = self.fps * (1 - s) + (1.0 / dt) * s
        self.centralWidget().setTitle(f'{self.fps:.2f} fps')

    def check_break(self):
        if self.bm_stopped:
            self.bm_timer.stop()

    def hscroll_benchmark(self):
        self.check_break()
        self.centralWidget().infini_hscroll(1)
        self.show_fps()

    def start_benchmark(self):
        self.bm_stopped = False
        selected_bm = self.benchmark_cmbx.currentText()
        self.last_time = time()
        self.bm_timer = QTimer()
        self.bm_timer.timeout.connect(getattr(self, selected_bm))
        self.bm_timer.start(0)

    def stop_benchmark(self):
        self.bm_stopped = True
