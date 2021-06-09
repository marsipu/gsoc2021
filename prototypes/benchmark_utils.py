from functools import partial
from os.path import isfile

from PyQt5.QtWidgets import QAction, QApplication, QComboBox, QLabel, QMainWindow, QMessageBox, QWidget

import mne

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

    def init_toolbar(self):
        self.toolbar = self.addToolBar('Tools')
        backend_label = QLabel('<b>Backend: </b>')
        self.toolbar.addWidget(backend_label)

        self.backend_cmbx = QComboBox()
        self.backend_cmbx.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.backend_cmbx.addItems(backends.keys())
        self.backend_cmbx.activated.connect(self.backend_chosen)
        self.toolbar.addWidget(self.backend_cmbx)

        adecr_time = QAction('-Time')
        adecr_time.triggered.connect(partial(self.centralWidget().change_duration, -1))
        self.toolbar.addAction(adecr_time)

        aincr_time = QAction('+Time')
        aincr_time.triggered.connect(partial(self.centralWidget().change_duration, 1))
        self.toolbar.addAction(aincr_time)

        adecr_nchan= QAction('+Channels')
        adecr_nchan.triggered.connect(partial(self.centralWidget().change_nchan, -1))
        self.toolbar.addAction(adecr_nchan)

        aincr_nchan = QAction('+Channels')
        aincr_nchan.triggered.connect(partial(self.centralWidget().change_nchan, 1))
        self.toolbar.addAction(aincr_nchan)

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
