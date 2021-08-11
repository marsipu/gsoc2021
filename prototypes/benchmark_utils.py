import functools
import inspect
import os
from ast import literal_eval
from copy import deepcopy
from functools import partial
from itertools import cycle
from os.path import isfile, join

import mne
import numpy as np
from PyQt5.QtCore import QTimer, pyqtSignal
from PyQt5.QtWidgets import (QAction, QApplication, QComboBox, QDialog,
                             QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QMainWindow,
                             QMessageBox, QPushButton, QScrollArea,
                             QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
                             QTabWidget)
from mne.viz._figure import set_browser_backend
from mne.viz.utils import _get_color_list
from pyqtgraph import PlotDataItem, PlotWidget, mkPen, time, BarGraphItem, \
    mkBrush

from .pyqtgraph_ptyp import PyQtGraphPtyp
from .qt_ptyp import PyQtPtyp


class EvalParam(QLineEdit):
    textchange = pyqtSignal(object)

    def __init__(self, parent=None, default=None):
        super().__init__(parent)
        super().editingFinished.connect(self._text_edited)
        self.setText(default)

    def _text_edited(self):
        self.textchange.emit(self.text())

    def text(self):
        text = super().text()
        try:
            value = literal_eval(text)
        except ValueError:
            value = text
        except SyntaxError:
            QMessageBox.warning(self.parent(), 'Evaluation-Error',
                                f'"{text}" could not be evaluated!')
            self.setText('')
            value = None
        return value

    def setText(self, value):
        if not isinstance(value, str):
            value = str(value)
        super().setText(value)


class KwargDialog(QDialog):
    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self.pw = parent_widget
        layout = QVBoxLayout()
        layout.addWidget(KwargEditor(self.pw.backend_kwargs))
        close_bt = QPushButton('Close')
        close_bt.clicked.connect(self.close)
        layout.addWidget(close_bt)
        self.setLayout(layout)
        self.show()

    def closeEvent(self, event):
        self.pw.load_backend()
        event.accept()


class KwargEditor(QWidget):
    def __init__(self, kwarg_dict):
        super().__init__()
        self.kd = kwarg_dict
        self.pw_dict = dict()

        self.init_ui()

    def param_changed(self, text, param_name):
        self.kd[param_name] = text

    def init_ui(self):
        layout = QGridLayout()
        # Only choose kwargs with default
        for row_idx, param in enumerate(self.kd):
            param_label = QLabel(param)
            param_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
            layout.addWidget(param_label, row_idx, 0)

            # Load parameter from backend_kwargs-dictionary
            default = self.kd[param]

            param_widget = EvalParam(default=default)
            param_widget.textchange.connect(
                partial(self.param_changed, param_name=param))
            self.pw_dict[param] = param_widget
            layout.addWidget(param_widget, row_idx, 1)

        self.setLayout(layout)

    def update_params(self):
        for p_name in self.pw_dict:
            p_widget = self.pw_dict[p_name]
            p_widget.setText(self.kd[p_name])

    def change_kwarg_dict(self, new_dict):
        self.kd = new_dict
        self.update_params()


class BenchmarkEditor(QDialog):
    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self.pw = parent_widget

        self.init_ui()
        self.show()

    def init_ui(self):
        layout = QGridLayout()

        self.list_widget = QListWidget()
        self.list_widget.currentTextChanged.connect(self.bm_run_changed)
        self.populate_list()
        layout.addWidget(self.list_widget, 0, 0, 2, 1)

        self.benchmark_cmbx = self.pw.get_bm_cmbx()
        layout.addWidget(self.benchmark_cmbx, 0, 1)

        self.kwarg_editor = KwargEditor(self.pw.backend_kwargs)
        layout.addWidget(self.kwarg_editor, 1, 1)

        add_bt = QPushButton('Add')
        add_bt.clicked.connect(self.add_bm)
        layout.addWidget(add_bt, 2, 0)

        rm_bt = QPushButton('Remove')
        rm_bt.clicked.connect(self.remove_bm)
        layout.addWidget(rm_bt, 2, 1)

        start_bt = QPushButton('Start')
        start_bt.clicked.connect(self.start_benchmark)
        layout.addWidget(start_bt)

        close_bt = QPushButton('Close')
        close_bt.clicked.connect(self.close)
        layout.addWidget(close_bt, 3, 1)

        self.setLayout(layout)

    def populate_list(self):
        for bm_func in self.pw.benchmark_runs:
            for bm_run in self.pw.benchmark_runs[bm_func]:
                self.list_widget.addItem(bm_run)

    def bm_run_changed(self, bm_run):
        if bm_run != '':
            bm_func = bm_run.split(' ')[0]
            if bm_run in self.pw.benchmark_runs[bm_func]:
                new_dict = self.pw.benchmark_runs[bm_func][bm_run]
                self.kwarg_editor.change_kwarg_dict(new_dict)

    def add_bm(self):
        bm_func = self.benchmark_cmbx.currentText()
        func_idx = len(self.pw.benchmark_runs[bm_func]) + 1
        bm_run = f'{bm_func} #{func_idx}'
        # Add to benchmark-runs
        self.pw.benchmark_runs[bm_func][bm_run] = deepcopy(
            self.kwarg_editor.kd)
        # Add to list_widget
        self.list_widget.addItem(bm_run)

    def remove_bm(self):
        current_row = self.list_widget.currentRow()
        if current_row != -1:
            bm_run = self.list_widget.item(current_row).text()
            bm_func = bm_run.split(' ')[0]
            # Remove from benchmark-runs
            self.pw.benchmark_runs[bm_func].pop(bm_run)
            # Remove List-Item
            self.list_widget.takeItem(current_row)

    def start_benchmark(self):
        self.pw.start_benchmark(True)
        self.close()


class ResultDialog(QDialog):
    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self.pw = parent_widget
        colors, self.red = _get_color_list(annotations=True)
        self.color_cycle = cycle(colors)

        self.init_ui()

        # Set size to ratio of current desktop
        desk_geometry = QApplication.instance().desktop().availableGeometry()
        width = int(desk_geometry.width() * 0.8)
        height = int(desk_geometry.height() * 0.8)
        self.resize(width, height)

        self.show()

    def init_ui(self):
        layout = QHBoxLayout()

        tab_widget = QTabWidget()
        self.fps_widget = PlotWidget()
        self.fps_widget.plotItem.setLabel('bottom', 'No. Iteration')
        self.fps_widget.plotItem.setLabel('left', 'FPS')
        tab_widget.addTab(self.fps_widget, 'FPS')
        self.startup_widget = PlotWidget()
        self.startup_widget.plotItem.setLabel('bottom', 'Benchmark')
        self.startup_widget.plotItem.setLabel('left', 'Time', 's')
        tab_widget.addTab(self.startup_widget, 'Startup')
        scroll_area = QScrollArea()
        scroll_area.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        legend_widget = QWidget()
        legend_layout = QVBoxLayout()
        for idx, bm_run in enumerate(self.pw.benchmark_results):
            fps_y = self.pw.benchmark_results[bm_run]['fps']
            color = next(self.color_cycle)
            data_item = PlotDataItem(fps_y, pen=mkPen(color=color, width=2))
            self.fps_widget.addItem(data_item)

            brush = mkBrush(color=color)
            startup_y = self.pw.benchmark_results[bm_run]['startup']
            startup_item = BarGraphItem(x=[idx + 1], height=[startup_y],
                                        width=1, brush=brush)
            self.startup_widget.addItem(startup_item)

            bm_func = bm_run.split(' ')[0]
            p_dict = self.pw.benchmark_runs[bm_func][bm_run]
            legend_string = f'<b>{idx + 1}: {bm_run}</b><br>'
            legend_string += '<br>'.join(
                [f'{p} = {p_dict[p]}' for p in p_dict])
            legend_label = QLabel(legend_string)
            legend_label.setStyleSheet(f"QLabel {{ color : {color}}}")
            legend_layout.addWidget(legend_label)
        layout.addWidget(tab_widget)
        legend_widget.setLayout(legend_layout)
        scroll_area.setWidget(legend_widget)
        layout.addWidget(scroll_area)

        self.setLayout(layout)


class BenchmarkWindow(QMainWindow):
    finishedBm = pyqtSignal()
    finishedRun = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.available_backends = ['pyqtgraph', 'matplotlib']
        self.backend_name = 'pyqtgraph'
        self.backend_kwargs = dict()

        self.raw_test_path = join(os.getcwd(), 'test_raw.fif')

        self.load_backend()

        self.last_time = None
        self.fps = None
        self.n_bm = None
        self.n_limit = 50

        # limit for change duration/n-channel benchmarks (stays inside this range)
        self.change_limit = 50

        self.bm_run = None
        self.stop_multi_run = False
        self.benchmark_runs = dict()
        self.benchmark_results = dict()

        self.init_toolbar()

        # Set size to ratio of current desktop
        desk_geometry = QApplication.instance().desktop().availableGeometry()
        width = int(desk_geometry.width() * 0.9)
        height = int(desk_geometry.height() * 0.9)
        self.resize(width, height)

        self.finishedRun.connect(self.run_finished)
        self.finishedBm.connect(self.bm_finished)

    def load_backend(self):
        # Remove existing backend
        if self.centralWidget() is not None:
            self.takeCentralWidget()
            self.backend.deleteLater()
            del self.backend

        # Load Raw
        if isfile(self.raw_test_path):
            raw_path = self.raw_test_path
        else:
            sample_data_folder = mne.datasets.sample.data_path()
            raw_path = os.path.join(sample_data_folder, 'MEG', 'sample',
                                    'sample_audvis_raw.fif')
        self.raw = mne.io.read_raw(raw_path)

        set_browser_backend(self.backend_name)
        pre_time = time()
        self.backend = self.raw.plot(block=False, time_format='float',
                                     duration=20, **self.backend_kwargs)
        self.backend_startup_time = time() - pre_time
        # Get backend parameters (all parameters with default-value)
        if hasattr(self.backend, 'pg_kwarg_defaults'):
            backend_defaults = self.backend.pg_kwarg_defaults
        else:
            backend_defaults = dict()
        # Load backend_kwargs from Benchmark-Class if available
        if self.backend_kwargs:
            backend_defaults = {
                k: self.backend_kwargs[k] if k in self.backend_kwargs
                else backend_defaults[k] for k in backend_defaults}
        self.backend_kwargs = backend_defaults

        self.setCentralWidget(self.backend)

    def get_bm_cmbx(self):
        bm_cmbx = QComboBox()
        bm_cmbx.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        benchmark_functions = [m[0] for m in inspect.getmembers(self,
                                                                predicate=inspect.ismethod)
                               if m[0].startswith('benchmark_')]
        for bm_func in [bf for bf in benchmark_functions if
                        bf not in self.benchmark_runs]:
            self.benchmark_runs[bm_func] = dict()
        bm_cmbx.addItems(benchmark_functions)

        return bm_cmbx

    def init_toolbar(self):
        self.toolbar = self.addToolBar('Tools')

        # backend_cmbx = QComboBox()
        # backend_cmbx.addItems(self.available_backends.keys())
        # backend_cmbx.setCurrentText(self.backend_name)
        # backend_cmbx.currentTextChanged.connect(self.backend_changed)
        # self.toolbar.addWidget(backend_cmbx)

        aedit_kwargs = QAction('Edit Parameters', parent=self)
        aedit_kwargs.triggered.connect(partial(KwargDialog, self))
        self.toolbar.addAction(aedit_kwargs)

        # self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel('<b>Benchmarks: </b>'))
        self.benchmark_cmbx = self.get_bm_cmbx()
        self.toolbar.addWidget(self.benchmark_cmbx)

        astart_bm = QAction('Start', parent=self)
        astart_bm.triggered.connect(self.start_single_benchmark)
        self.toolbar.addAction(astart_bm)

        astop_bm = QAction('Stop', parent=self)
        astop_bm.triggered.connect(self.stop_benchmark)
        self.toolbar.addAction(astop_bm)

        self.toolbar.addWidget(QLabel('No. Repetitions: '))
        self.nbem_spinbox = QSpinBox()
        self.nbem_spinbox.setMaximum(1e6)
        self.nbem_spinbox.setSpecialValueText('Infinite')
        self.nbem_spinbox.setValue(self.n_limit)
        self.toolbar.addWidget(self.nbem_spinbox)

        aedit_bm = QAction('Benchmark-Queue', parent=self)
        aedit_bm.triggered.connect(partial(BenchmarkEditor, self))
        self.toolbar.addAction(aedit_bm)

        ads_test = QAction('Downsampling-Test', parent=self)
        ads_test.triggered.connect(self.toggle_ds_test)
        self.toolbar.addAction(ads_test)

        ampl_plot = QAction('MPL-Plot', parent=self)
        ampl_plot.triggered.connect(self.mpl_plot)
        self.toolbar.addAction(ampl_plot)

    def backend_changed(self, backend):
        self.backend_name = backend
        self.load_backend()

    def change_duration(self, step):
        self.backend.change_duration(step)

    def change_nchan(self, step):
        self.backend.change_nchan(step)

    def show_fps(self):
        now = time()
        if self.last_time:
            dt = now - self.last_time
        else:
            dt = None
        self.last_time = now
        if dt:
            if self.fps is None:
                self.fps = 1.0 / dt
            else:
                s = np.clip(dt * 3., 0, 1)
                self.fps = self.fps * (1 - s) + (1.0 / dt) * s
            self.backend.mne.plt.setTitle(f'{self.fps:.2f} fps')
            if self.bm_run:
                self.benchmark_results[self.bm_run]['fps'].append(self.fps)

    def get_n_limit(self):
        n = self.nbem_spinbox.value()
        if n == 0:
            n = float('inf')
        return n

    def check_break(self):
        if self.n_bm >= self.get_n_limit():
            self.bm_timer.stop()
            if self.bm_run:
                self.finishedRun.emit('multi')
            else:
                self.finishedRun.emit('single')
        else:
            self.n_bm += 1

    def benchmark(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            func(self, *args, **kwargs)
            self.show_fps()
            self.check_break()

        return wrapper

    @benchmark
    def benchmark_hscroll(self):
        self.backend.infini_hscroll(10)

    @benchmark
    def benchmark_vscroll(self):
        self.backend.infini_vscroll(1)

    @benchmark
    def benchmark_duration_change(self):
        if self.n_bm % self.change_limit == 0:
            self.duration_bm *= -1
        self.backend.change_duration(self.duration_bm)

    @benchmark
    def benchmark_nchan_change(self):
        if self.n_bm % self.change_limit == 0 and self.n_bm != 0:
            self.nchan_bm *= -1
        self.backend.change_nchan(self.nchan_bm)

    @benchmark
    def benchmark_toggle_proj(self):
        self.backend._fake_keypress('j')

    @benchmark
    def benchmark_toggle_dc(self):
        self.backend._fake_keypress('d')

    def start_single_benchmark(self):
        self.n_bm = 1
        self.duration_bm = 2
        self.nchan_bm = 1
        self.bm_run = None
        selected_bm = self.benchmark_cmbx.currentText()
        self.last_time = None
        self.bm_timer = QTimer()
        self.bm_timer.timeout.connect(getattr(self, selected_bm))
        self.bm_timer.start(0)

    def start_benchmark(self, first_run):
        if first_run:
            self.cp_bm_runs = deepcopy(self.benchmark_runs)
            self.benchmark_results = dict()
            self.stop_multi_run = False
            self._old_backend_kwargs = self.backend_kwargs

        if not self.stop_multi_run:
            self.last_time = None
            self.n_bm = 1
            self.duration_bm = 2
            self.nchan_bm = 2
            # Very cluttered way to get and pop first benchmark-run from nested dictionary.
            while len(self.cp_bm_runs) > 0 and len(
                    self.cp_bm_runs[list(self.cp_bm_runs.keys())[0]]) == 0:
                self.cp_bm_runs.pop(list(self.cp_bm_runs.keys())[0])
            if len(self.cp_bm_runs) > 0:
                bm_func = list(self.cp_bm_runs.keys())[0]
                if len(self.cp_bm_runs[bm_func]) > 0:
                    self.bm_run = list(self.cp_bm_runs[bm_func].keys())[0]
                    self.backend_kwargs = self.cp_bm_runs[bm_func][self.bm_run]
                    self.cp_bm_runs[bm_func].pop(self.bm_run)
                    # Add to result-dict
                    self.benchmark_results[self.bm_run] = dict()
                    self.load_backend()
                    self.benchmark_results[self.bm_run]['startup'] = \
                        self.backend_startup_time
                    self.benchmark_results[self.bm_run]['fps'] = list()
                    self.bm_timer = QTimer()
                    self.bm_timer.timeout.connect(getattr(self, bm_func))
                    self.bm_timer.start(0)
            else:
                self.finishedBm.emit()

    def stop_benchmark(self):
        self.n_bm = self.get_n_limit()
        self.stop_multi_run = True

    def run_finished(self, run_type):
        if run_type == 'multi':
            self.start_benchmark(False)
            self.n_bm = 1

    def bm_finished(self):
        # Restore backend-kwargs as before the benchmark
        self.backend_kwargs = self._old_backend_kwargs
        self.load_backend()
        ResultDialog(self)

    def save_raw(self, _):
        if not self.raw.preload:
            self.raw.load_data()
        self.raw.save(self.raw_test_path, overwrite=True)

    def toggle_ds_test(self):
        self.ds_test = not self.ds_test
        self.load_backend()

    def mpl_plot(self):
        fig = self.raw.plot(duration=self.backend_kwargs['duration'],
                            n_channels=self.backend_kwargs['n_channels'])
        fig.canvas.mpl_connect('close_event', self.save_raw)

    def closeEvent(self, event):
        event.accept()
        self.save_raw(None)
