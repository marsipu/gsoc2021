import functools
import inspect
import os
import sys
import traceback
from ast import literal_eval
from copy import deepcopy
from functools import partial
from itertools import cycle
from os.path import isfile, join

import mne
import numpy as np
from PyQt5.QtCore import QTimer, pyqtSignal, Qt
from PyQt5.QtWidgets import (QAction, QApplication, QComboBox, QDialog,
                             QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QMainWindow,
                             QMessageBox, QPushButton, QScrollArea,
                             QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
                             QTabWidget, QFileDialog, QFormLayout,
                             QDoubleSpinBox, QGroupBox)
from mne.preprocessing import ICA
from mne.viz._figure import set_browser_backend
from mne.viz.utils import _get_color_list
from pyqtgraph import PlotDataItem, PlotWidget, mkPen, time, BarGraphItem, \
    mkBrush, GroupBox
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg


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
        layout = QVBoxLayout()
        widget = QWidget()
        scroll_area = QScrollArea()
        grid_layout = QGridLayout()
        # Only choose kwargs with default
        for row_idx, param in enumerate(self.kd):
            param_label = QLabel(param)
            param_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
            grid_layout.addWidget(param_label, row_idx, 0)

            # Load parameter from backend_kwargs-dictionary
            default = self.kd[param]

            param_widget = EvalParam(default=default)
            param_widget.textchange.connect(
                partial(self.param_changed, param_name=param))
            self.pw_dict[param] = param_widget
            grid_layout.addWidget(param_widget, row_idx, 1)

        widget.setLayout(grid_layout)
        scroll_area.setWidget(widget)
        layout.addWidget(scroll_area)
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

def _show_error_msg(parent):
    exctype, value = sys.exc_info()[:2]
    traceback_str = traceback.format_exc(limit=-5)
    traceback.print_exc()
    QMessageBox.information(parent, 'Error!',
                            f'{exctype}: {value}\n'
                            f'{traceback_str}')

class FakeClickDialog(QDialog):
    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self.pw = parent_widget

        self.init_ui()
        self.show()

    def init_ui(self):
        layout = QVBoxLayout()

        params_bx = QGroupBox('Fake Click Parameters')
        bx_layout = QFormLayout()
        self.xbox = QDoubleSpinBox()
        self.xbox.setMaximum(1e6)
        bx_layout.addRow('X:', self.xbox)
        self.ybox = QDoubleSpinBox()
        self.xbox.setMaximum(1e6)
        bx_layout.addRow('Y:', self.ybox)
        self.button_cmbx = QComboBox()
        self.button_cmbx.addItems(['left', 'right'])
        self.button_cmbx.setCurrentIndex(0)
        bx_layout.addRow('Button:', self.button_cmbx)
        self.xform_cmbx = QComboBox()
        self.xform_cmbx.addItems(['ax', 'data', 'none'])
        self.xform_cmbx.setCurrentIndex(0)
        bx_layout.addRow('Transform:', self.xform_cmbx)
        self.target_cmbx = QComboBox()
        self.target_cmbx.addItems(['view', 'ax_hscroll', 'ax_vscroll'])
        self.target_cmbx.setCurrentIndex(0)
        bx_layout.addRow('Target:', self.target_cmbx)
        self.kind_cmbx = QComboBox()
        self.kind_cmbx.addItems(['press', 'release', 'motion'])
        self.kind_cmbx.setCurrentIndex(0)
        bx_layout.addRow('Kind:', self.kind_cmbx)
        params_bx.setLayout(bx_layout)
        layout.addWidget(params_bx)

        click_bt = QPushButton('Click')
        click_bt.clicked.connect(self.make_fake_click)
        layout.addWidget(click_bt)

        self.setLayout(layout)

    def make_fake_click(self):
        x = self.xbox.value()
        y = self.ybox.value()
        trans = self.xform_cmbx.currentText()
        target = getattr(self.pw.backend.mne, self.target_cmbx.currentText())
        button_text = self.button_cmbx.currentText()
        button = 1 if button_text == 'left' else 3
        kind = self.kind_cmbx.currentText()
        try:
            self.pw.backend._fake_click((x, y), ax=target, button=button,
                                       xform=trans, kind=kind)
        except:
            _show_error_msg(self)


class FakeKeyPressDialog(QDialog):
    def __init__(self, parent_widget):
        super().__init__(parent_widget)
        self.pw = parent_widget

        self.init_ui()
        self.show()

    def init_ui(self):
        layout = QVBoxLayout()

        layout.addWidget(QLabel('Enter key-name to press:'))

        self.key_input = QLineEdit()
        layout.addWidget(self.key_input)

        press_bt = QPushButton('Press')
        press_bt.clicked.connect(self.press_key)
        layout.addWidget(press_bt)

        self.setLayout(layout)

    def press_key(self):
        key_name = self.key_input.text()
        if key_name:
            try:
                self.pw.backend._fake_keypress(key_name)
            except:
                _show_error_msg(self)


class BenchmarkWindow(QMainWindow):
    finishedBm = pyqtSignal()
    finishedRun = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.available_backends = ['pyqtgraph', 'matplotlib']
        self.current_backend = 'pyqtgraph'
        self.backend = None
        self.backend_kwargs = dict()

        self.available_modes = ['Raw', 'Epochs', 'ICA']
        self.current_mode = 'Raw'

        self.inst = None
        self.file_path = ''
        self.raw_saved_path = join(os.getcwd(), 'test_raw.fif')
        self.epo_saved_path = join(os.getcwd(), 'test_epo.fif')
        self.ica_saved_path = join(os.getcwd(), 'test_ica.fif')

        # Initialize Status-Bar Widgets
        self.startup_status = QLabel()
        self.statusBar().addPermanentWidget(self.startup_status)
        self.fps_status = QLabel()
        self.statusBar().addPermanentWidget(self.fps_status)

        self.load_backend()

        self.backend_startup_time = None
        self.last_time = None
        self.fps = None
        self.n_bm = None
        self.n_limit = 50

        # limit for change duration/n-channel benchmarks
        # (stays inside this range)
        self.change_limit = 20
        self.hscroll_dir = True
        self.vscroll_dir = True
        self.duration_change = True
        self.channel_change = True

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

    def _load_raw(self):
        # Load Raw
        if isfile(self.raw_saved_path) and isfile(self.file_path):
            # Compare
            raw_saved_info = mne.io.read_info(self.raw_saved_path)
            raw_info = mne.io.read_info(self.file_path)

            if raw_info['meas_date'] == raw_saved_info['meas_date']:
                raw_path = self.raw_saved_path
            else:
                raw_path = self.file_path
        elif isfile(self.raw_saved_path):
            raw_path = self.raw_saved_path
        elif isfile(self.file_path):
            raw_path = self.file_path
        else:
            sample_data_folder = mne.datasets.sample.data_path()
            raw_path = os.path.join(sample_data_folder, 'MEG', 'sample',
                                    'sample_audvis_raw.fif')
        raw = mne.io.read_raw(raw_path)
        print(f'Sampling-Frequency: {raw.info["sfreq"]}')

        return raw

    def _load_epochs(self):
        # Load Epochs
        if isfile(self.epo_saved_path) and isfile(self.file_path):
            # Compare
            epo_saved_info = mne.io.read_info(self.epo_saved_path)
            epo_info = mne.io.read_info(self.file_path)

            if epo_info['meas_date'] == epo_saved_info['meas_date']:
                epo_path = self.epo_saved_path
            else:
                epo_path = self.file_path
        elif isfile(self.epo_saved_path):
            epo_path = self.epo_saved_path
        elif isfile(self.file_path):
            epo_path = self.file_path
        else:
            sample_data_folder = mne.datasets.sample.data_path()
            raw = self._load_raw()
            events_path = os.path.join(sample_data_folder, 'MEG', 'sample',
                                       'sample_audvis_raw-eve.fif')
            events = mne.read_events(events_path)
            epochs = mne.Epochs(raw, events)
            return epochs

        epochs = mne.read_epochs(epo_path)
        print(f'Sampling-Frequency: {epochs.info["sfreq"]}')

        return epochs

    def _load_ica(self):
        # Load Epochs
        if isfile(self.ica_saved_path) and isfile(self.file_path):
            # Compare
            ica_saved_info = mne.io.read_info(self.ica_saved_path)
            ica_info = mne.io.read_info(self.file_path)

            if ica_info['meas_date'] == ica_saved_info['meas_date']:
                ica_path = self.ica_saved_path
            else:
                ica_path = self.file_path
        elif isfile(self.ica_saved_path):
            ica_path = self.ica_saved_path
        elif isfile(self.file_path):
            ica_path = self.file_path
        else:
            raw = self._load_raw()
            filt_raw = raw.filter(1, None, n_jobs=-1)
            ica = ICA(n_components=10)
            ica.fit(filt_raw)
            return ica

        ica = mne.preprocessing.read_ica(ica_path)
        print(f'Sampling-Frequency: {ica.info["sfreq"]}')

        return ica

    def load_backend(self):
        # Remove existing backend
        if self.centralWidget() is not None:
            widget = self.takeCentralWidget()
            widget.deleteLater()
            del self.backend

        # Reset Benchmark-Attributes
        self.hscroll_dir = True
        self.vscroll_dir = True
        self.duration_change = True
        self.channel_change = True

        # Load data depending on mode
        if self.current_mode == 'Raw':
            self.inst = self._load_raw()
        elif self.current_mode == 'Epochs':
            self.inst = self._load_epochs()
        else:
            self.inst = self._load_ica()
        
        set_browser_backend(self.current_backend)
        pre_time = time()

        if self.current_mode == 'ICA':
            params = inspect.signature(self.inst.plot_sources).parameters
        else:
            params = inspect.signature(self.inst.plot).parameters

        # Remove kwargs (from other mode)
        for rm_kwarg in [k for k in self.backend_kwargs if k not in params]:
            self.backend_kwargs.pop(rm_kwarg)

        # Add new kwargs
        for add_kwarg in [k for k in params if k not in self.backend_kwargs]:
            self.backend_kwargs[add_kwarg] = params[add_kwarg].default

        # Need to be False to work in benchmark-window
        self.backend_kwargs['block'] = False
        self.backend_kwargs['show'] = False

        if self.current_mode == 'ICA':
            self.backend_kwargs['raw'] = self._load_raw()
            self.backend = self.inst.plot_sources(**self.backend_kwargs)
        else:
            self.backend = self.inst.plot(**self.backend_kwargs)

        self.backend_startup_time = time() - pre_time
        self.startup_status.setText(f'Startup: '
                                    f'{self.backend_startup_time:.3f} s')
        self.fps_status.setText('')

        if self.current_backend == 'matplotlib':
            canvas = FigureCanvasQTAgg(self.backend)
            # canvas.draw()
            canvas.setFocusPolicy(Qt.StrongFocus | Qt.WheelFocus)
            canvas.setFocus()
            self.setCentralWidget(canvas)
        else:
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

        aopen_file = QAction('Open File', parent=self)
        aopen_file.triggered.connect(self.open_file)
        self.toolbar.addAction(aopen_file)

        ause_sample = QAction('Use Sample-Dataset', parent=self)
        ause_sample.triggered.connect(self.use_sample_dataset)
        self.toolbar.addAction(ause_sample)

        self.toolbar.addSeparator()

        backend_cmbx = QComboBox()
        backend_cmbx.addItems(self.available_backends)
        backend_cmbx.setCurrentText(self.current_backend)
        backend_cmbx.currentTextChanged.connect(self.backend_changed)
        self.toolbar.addWidget(backend_cmbx)

        mode_cmbx = QComboBox()
        mode_cmbx.addItems(self.available_modes)
        mode_cmbx.setCurrentText(self.current_mode)
        mode_cmbx.currentTextChanged.connect(self.mode_changed)
        self.toolbar.addWidget(mode_cmbx)

        self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel('<b>Benchmarks: </b>'))
        self.benchmark_cmbx = self.get_bm_cmbx()
        self.toolbar.addWidget(self.benchmark_cmbx)

        aedit_kwargs = QAction('Edit Parameters', parent=self)
        aedit_kwargs.triggered.connect(partial(KwargDialog, self))
        self.toolbar.addAction(aedit_kwargs)

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

        afake_clickdlg = QAction('Fake Click', parent=self)
        afake_clickdlg.triggered.connect(partial(FakeClickDialog, self))
        self.toolbar.addAction(afake_clickdlg)

        afake_keypress = QAction('Fake KeyPress', parent=self)
        afake_keypress.triggered.connect(partial(FakeKeyPressDialog, self))
        self.toolbar.addAction(afake_keypress)

    def open_file(self):
        file_path = QFileDialog.getOpenFileName(self,
                                                'Open a file which is '
                                                'readable by MNE-Python.')[0]
        if file_path:
            self.file_path = file_path
            self.load_backend()

    def use_sample_dataset(self):
        self.file_path = ''
        os.remove(self.raw_saved_path)
        self.load_backend()

    def backend_changed(self, backend):
        self.current_backend = backend
        self.load_backend()

    def mode_changed(self, mode):
        self.current_mode = mode
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
            self.fps_status.setText(f'FPS: {self.fps:.3f}')
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
        if self.backend.mne.t_start + self.backend.mne.duration \
                >= self.backend.mne.inst.times[-1]:
            self.hscroll_dir = False
        elif self.backend.mne.t_start <= 0:
            self.hscroll_dir = True
        key = 'right' if self.hscroll_dir else 'left'
        self.backend._fake_keypress(key)

    @benchmark
    def benchmark_vscroll(self):
        if self.backend.mne.ch_start + self.backend.mne.n_channels \
                >= len(self.backend.mne.inst.ch_names):
            self.vscroll_dir = False
        elif self.backend.mne.ch_start <= 0:
            self.vscroll_dir = True
        key = 'down' if self.vscroll_dir else 'up'
        self.backend._fake_keypress(key)

    @benchmark
    def benchmark_duration_change(self):
        if self.n_bm % self.change_limit == 0:
            self.duration_change = not self.duration_change
        key = 'end' if self.duration_change else 'home'
        self.backend._fake_keypress(key)

    @benchmark
    def benchmark_nchan_change(self):
        if self.n_bm % self.change_limit == 0:
            self.channel_change = not self.channel_change
        key = 'pageup' if self.channel_change else 'pagedown'
        self.backend._fake_keypress(key)

    @benchmark
    def benchmark_toggle_proj(self):
        self.backend._fake_keypress('j')

    @benchmark
    def benchmark_toggle_dc(self):
        self.backend._fake_keypress('d')

    def start_single_benchmark(self):
        self.n_bm = 1
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

    def save_inst(self, _):
        if hasattr(self.inst, 'preload') and not self.inst.preload:
            self.inst.load_data()
        if self.current_mode == 'Raw':
            save_path = self.raw_saved_path
        elif self.current_mode == 'Epochs':
            save_path = self.epo_saved_path
        else:
            save_path = self.ica_saved_path
        self.inst.save(save_path, overwrite=True)

    def closeEvent(self, event):
        event.accept()
        self.backend._close(event)
        self.save_inst(None)
