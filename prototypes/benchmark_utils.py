from functools import partial

from PyQt5.QtWidgets import QAction, QApplication, QComboBox, QLabel, QMainWindow, QWidget

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
            self.raw = mne.io.read_raw_fif(raw_fname, preload=True)
            self.raw.filter(1, None, n_jobs=-1)

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
        new_backend = backends[list(backends.keys())[idx]]
        self.setCentralWidget(new_backend[0](self.raw, **new_backend[1]))
