import datetime
import platform
from functools import partial
from itertools import cycle

import numpy as np
from PyQt5.QtCore import QEvent
from PyQt5.QtGui import QColor, QFont, QIcon, QPixmap, QTransform
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import (QAction, QColorDialog, QComboBox, QDialog,
                             QDockWidget, QDoubleSpinBox, QFormLayout,
                             QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                             QMainWindow, QMessageBox, QPushButton, QScrollBar,
                             QSizePolicy, QWidget)
from mne.utils import logger
from mne.viz._figure import BrowserBase
from mne.viz.utils import _get_color_list
from pyqtgraph import (AxisItem, GraphicsView, InfLineLabel, InfiniteLine,
                       LinearRegionItem,
                       PlotCurveItem, PlotItem, TextItem, ViewBox, functions,
                       mkBrush, mkPen, setConfigOption, mkQApp)
from pyqtgraph.Qt.QtCore import Qt, Signal


class RawTraceItem(PlotCurveItem):
    """Graphics-Object for single data trace."""

    def __init__(self, mne, ch_idx):
        super().__init__(clickable=True)
        # ToDo: Does it affect performance, if the mne-object is referenced
        #  to in every RawTraceItem?
        self.mne = mne
        self.check_nan = self.mne.check_nan

        self.set_ch_idx(ch_idx)
        self.update_bad_color()
        self.set_data()

    def update_bad_color(self):
        if self.isbad:
            self.setPen('r')
        else:
            self.setPen(self.color)

    def set_ch_idx(self, ch_idx):
        self.ch_idx = ch_idx
        self.ch_name = self.mne.inst.ch_names[ch_idx]
        self.isbad = self.ch_name in self.mne.inst.info['bads']
        self.ch_type = self.mne.ch_types[ch_idx]
        self.color = self.mne.ch_color_dict[self.ch_type]
        self.ypos = np.argwhere(self.mne.ch_order == self.ch_idx)[0][0] + 1

    def set_data(self):
        if self.check_nan:
            connect = 'finite'
            skip = False
        else:
            connect = 'all'
            skip = True

        if self.mne.preload:
            data = self.mne.data[self.ch_idx]
        else:
            # If local, ypos = index + 1 of data
            data_idx = np.argwhere(self.mne.picks == self.ch_idx)[0][0]
            data = self.mne.data[data_idx]

        self.setData(self.mne.times, data,
                     connect=connect, skipFiniteCheck=skip)
        self.setPos(0, self.ypos)

    def mouseClickEvent(self, ev):
        if not self.clickable or ev.button() != Qt.MouseButton.LeftButton:
            ev.ignore()
            return
        if self.mouseShape().contains(ev.pos()):
            ev.accept()
            self.isbad = not self.isbad
            self.update_bad_color()
            self.sigClicked.emit(self, ev)


class TimeAxis(AxisItem):
    """The X-Axis displaying the time."""

    def __init__(self, mne):
        self.mne = mne
        super().__init__(orientation='bottom')

    def tickStrings(self, values, scale, spacing):

        if self.mne.time_format == 'clock':
            meas_date = self.mne.inst.info['meas_date']
            first_time = datetime.timedelta(seconds=self.mne.inst.first_time)
            digits = np.ceil(-np.log10(spacing) + 1).astype(int)
            tick_strings = list()
            for val in values:
                val_time = datetime.timedelta(seconds=val) + \
                           first_time + meas_date
                val_str = val_time.strftime('%H:%M:%S')
                if int(val_time.microsecond):
                    val_str += \
                        f'{round(val_time.microsecond * 1e-6, digits)}'[1:]
                tick_strings.append(val_str)
        else:
            tick_strings = super().tickStrings(values, scale, spacing)

        return tick_strings

    def refresh(self):
        self.picture = None
        self.update()


class ChannelAxis(AxisItem):
    """The Y-Axis displaying the channel-names."""

    def __init__(self, main):
        self.main = main
        self.mne = main.mne
        self.ch_texts = dict()
        super().__init__(orientation='left')

    def tickValues(self, minVal, maxVal, size):
        minVal, maxVal = sorted((minVal, maxVal))
        values = list(range(round(minVal) + 1, round(maxVal)))
        tick_values = [(1, values)]
        return tick_values

    def tickStrings(self, values, scale, spacing):
        # Get channel-names
        ch_idxs = [v - 1 for v in values]
        tick_strings = self.mne.ch_names[self.mne.ch_order[ch_idxs]]

        return tick_strings

    def drawPicture(self, p, axisSpec, tickSpecs, textSpecs):
        super().drawPicture(p, axisSpec, tickSpecs, textSpecs)
        for rect, flags, text in textSpecs:
            if text in self.mne.inst.info['bads']:
                p.setPen(functions.mkPen('r'))
            else:
                p.setPen(functions.mkPen('k'))
            self.ch_texts[text] = (rect.top(), rect.top() + rect.height())
            p.drawText(rect, int(flags), text)

    def redraw(self):
        self.picture = None
        self.update()

    def mouseClickEvent(self, event):
        # Clean up channel-texts
        self.ch_texts = {k: v for k, v in self.ch_texts.items()
                         if k in [li.ch_name for li in self.mne.traces]}
        # Get channel-name from position of channel-description
        ypos = event.scenePos().y()
        ch_name = [chn for chn in self.ch_texts
                   if self.ch_texts[chn][0] < ypos < self.ch_texts[chn][1]]
        if len(ch_name) > 0:
            ch_name = ch_name[0]
            print(f'{ch_name} clicked!')
            line = [li for li in self.mne.traces
                    if li.ch_name == ch_name][0]
            self.main.toggle_bad_channel(line)
        # return super().mouseClickEvent(event)


class TimeScrollBar(QScrollBar):
    """Scrolls through time."""

    def __init__(self, mne):
        super().__init__(Qt.Horizontal)
        self.mne = mne
        self.step_factor = None

        self.setMinimum(0)
        self.setSingleStep(1)
        self.setPageStep(self.mne.tsteps_per_window)
        self.update_duration()
        self.setFocusPolicy(Qt.WheelFocus)
        # Because valueChanged is needed (captures every input to scrollbar,
        # not just sliderMoved), there has to be made a differentiation
        # between internal and external changes.
        self.external_change = False
        self.valueChanged.connect(self.time_changed)

    def time_changed(self, value):
        if not self.external_change:
            value /= self.step_factor
            self.mne.plt.setXRange(value, value + self.mne.duration,
                                   padding=0)

    def update_value_external(self, xrange):
        # Mark change as external to avoid setting XRange again in time_changed
        self.external_change = True
        self.setValue(xrange[0] * self.step_factor)
        self.external_change = False
        self.update_duration()

    def update_t_start(self):
        self.update_value_external(self.mne.t_start)

    def update_duration(self):
        new_step_factor = self.mne.tsteps_per_window / self.mne.duration
        if new_step_factor != self.step_factor:
            self.step_factor = new_step_factor
            new_maximum = int((self.mne.xmax - self.mne.duration)
                              * self.step_factor)
            self.setMaximum(new_maximum)

    def keyPressEvent(self, event):
        # Let main handle the keypress
        event.ignore()


class ChannelScrollBar(QScrollBar):
    """Scrolls through channels."""

    def __init__(self, mne):
        super().__init__(Qt.Vertical)
        self.mne = mne

        self.setMinimum(0)
        self.update_nchan()
        self.setSingleStep(1)
        self.setFocusPolicy(Qt.WheelFocus)
        # Because valueChanged is needed (captures every input to scrollbar,
        # not just sliderMoved), there has to be made a differentiation
        # between internal and external changes.
        self.external_change = False
        self.valueChanged.connect(self.channel_changed)

    def channel_changed(self, value):
        new_ymin = value
        new_ymax = value + self.mne.n_channels + 1
        if not self.external_change:
            self.mne.plt.setYRange(new_ymin, new_ymax, padding=0)

    def update_value_external(self, value):
        # Mark change as external to avoid setting YRange again in
        # channel_changed.
        self.external_change = True
        self.setValue(value)
        self.external_change = False
        self.update_nchan()

    def update_ch_start(self):
        self.update_value_external(self.mne.ch_start)

    def update_nchan(self):
        self.setPageStep(self.mne.n_channels)
        self.setMaximum(self.mne.ymax - self.mne.n_channels - 1)

    def keyPressEvent(self, event):
        # Let main handle the keypress
        event.ignore()


class RawViewBox(ViewBox):
    """PyQtGraph-Wrapper for interaction with the View."""

    def __init__(self, main):
        super().__init__(invertY=True)
        self.enableAutoRange(enable=False, x=False, y=False)
        self.main = main
        self.mne = main.mne
        self._drag_start = None
        self._drag_region = None

    def mouseDragEvent(self, event, axis=None):
        event.accept()

        if event.button() == Qt.LeftButton \
                and self.mne.annotation_mode:
            if self.mne.current_description:
                description = self.mne.current_description
                if event.isStart():
                    self._drag_start = self.mapSceneToView(
                        event.scenePos()).x()
                    self._drag_region = AnnotRegion(self.mne,
                                                    description=description,
                                                    values=(self._drag_start,
                                                            self._drag_start),
                                                    color=self.main.get_color(
                                                        description),
                                                    time_decimals=
                                                    self.mne.time_decimals)
                    self.mne.plt.addItem(self._drag_region)
                    self.mne.plt.addItem(self._drag_region.label_item)
                elif event.isFinish():
                    drag_stop = self.mapSceneToView(event.scenePos()).x()
                    self._drag_region.setRegion((self._drag_start, drag_stop))
                    onset = min(self._drag_start, drag_stop)
                    duration = abs(self._drag_start - drag_stop)
                    self.main.add_annotation(onset, duration,
                                             region=self._drag_region)
                else:
                    self._drag_region.setRegion((self._drag_start,
                                                 self.mapSceneToView(
                                                     event.scenePos()).x()))
            elif event.isFinish():
                QMessageBox.warning(self.main, 'No description!',
                                    'No description is given, add one!')

    def mouseClickEvent(self, event):
        # If we want the context-menu back, uncomment following line
        # super().mouseClickEvent(event)
        if event.button() == Qt.LeftButton:
            self.main.add_vline(self.mapSceneToView(event.scenePos()).x())
        elif event.button() == Qt.RightButton:
            self.main.remove_vline()

    def wheelEvent(self, ev, axis=None):
        ev.accept()
        scroll = -1 * ev.delta() / 120
        if ev.orientation() == Qt.Horizontal:
            self.main.hscroll(scroll * 10)
        elif ev.orientation() == Qt.Vertical:
            self.main.vscroll(scroll)


class VLineLabel(InfLineLabel):
    """Label of the vline displaying the time."""

    def __init__(self, vline):
        super().__init__(vline, text='{value:.3f} s', position=0.975,
                         fill='g', color='b', movable=True)
        self.vline = vline
        self.cursorOffset = None

    def mouseDragEvent(self, ev):
        if self.movable and ev.button() == Qt.LeftButton:
            if ev.isStart():
                self.vline.moving = True
                self.cursorOffset = (self.vline.pos() -
                                     self.mapToView(ev.buttonDownPos()))
            ev.accept()

            if not self.vline.moving:
                return

            self.vline.setPos(self.cursorOffset + self.mapToView(ev.pos()))
            self.vline.sigDragged.emit(self)
            if ev.isFinish():
                self.vline.moving = False
                self.vline.sigPositionChangeFinished.emit(self)


class VLine(InfiniteLine):
    """Marker to be placed inside the Data-Trace-Plot."""

    def __init__(self, pos, bounds):
        super().__init__(pos, pen='g', hoverPen='y',
                         movable=True, bounds=bounds)
        self.line = VLineLabel(self)


class HelpDialog(QDialog):
    """Shows all keyboard-shortcuts."""

    def __init__(self, main):
        super().__init__(main)
        self.mne = main.mne
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.init_ui()
        self.open()

    def init_ui(self):
        layout = QFormLayout()
        for key, text in self.mne.keyboard_shortcuts:
            layout.addRow(key, QLabel(text))
        self.setLayout(layout)


class AnnotRegion(LinearRegionItem):
    """Graphics-Oobject for Annotations."""
    regionChangeFinished = Signal(object)
    gotSelected = Signal(object)
    removeRequested = Signal(object)

    def __init__(self, mne, description, values, color, time_decimals):

        super().__init__(values=values, orientation='vertical',
                         movable=True, swapMode='sort')

        self.sigRegionChangeFinished.connect(self._region_changed)
        self.mne = mne
        self.description = description
        self.mne.time_decimals = time_decimals
        self.old_onset = values[0]
        self.selected = False

        self.label_item = TextItem(text=description, anchor=(0.5, 0.5))
        self.label_item.setFont(QFont('AnyStyle', 10, QFont.Bold))
        self.sigRegionChanged.connect(self.change_label_pos)

        self.update_color(color)

    def _region_changed(self):
        self.regionChangeFinished.emit(self)
        self.old_onset = self.getRegion()[0]

    def getRegion(self):
        rgn = tuple([round(r, self.mne.time_decimals)
                     for r in super().getRegion()])
        return rgn

    def update_color(self, color):
        color = QColor(color)
        hover_color = QColor(color)
        text_color = QColor(color)
        color.setAlpha(75)
        hover_color.setAlpha(150)
        text_color.setAlpha(255)
        self.setBrush(color)
        self.setHoverBrush(hover_color)
        self.label_item.setColor(text_color)
        self.update()

    def update_description(self, description):
        self.description = description
        self.label_item.setText(description)
        self.label_item.update()

    def paint(self, p, *args):
        super().paint(p, *args)

        if self.selected:
            # Draw selection rectangle
            p.setBrush(mkBrush(None))
            p.setPen(mkPen(color='c', width=3))
            p.drawRect(self.boundingRect())

    def remove(self):
        self.removeRequested.emit(self)
        vb = self.mne.viewbox
        if vb and self.label_item in vb.addedItems:
            vb.removeItem(self.label_item)

    def select(self, selected):
        self.selected = selected
        if selected:
            self.gotSelected.emit(self)
        self.update()

    def mouseClickEvent(self, event):
        event.accept()
        if event.button() == Qt.LeftButton and self.movable:
            self.select(True)
        elif event.button() == Qt.RightButton and self.movable:
            self.remove()

    def change_label_pos(self):
        rgn = self.getRegion()
        vb = self.mne.viewbox
        if vb:
            ymax = vb.viewRange()[1][1]
            self.label_item.setPos(sum(rgn) / 2, ymax - 0.25)


class AnnotationDock(QDockWidget):
    """Dock-Window for Management of annotations."""

    def __init__(self, main):
        super().__init__('Annotations')
        self.main = main
        self.mne = main.mne
        self.init_ui()

    def init_ui(self):
        widget = QWidget()
        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignLeft)

        self.description_cmbx = QComboBox()
        self.description_cmbx.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.description_cmbx.activated.connect(self.description_changed)
        self.update_description_cmbx()
        layout.addWidget(self.description_cmbx)

        add_bt = QPushButton('Add Description')
        add_bt.clicked.connect(self.add_description)
        layout.addWidget(add_bt)

        edit_bt = QPushButton('Edit Description')
        edit_bt.clicked.connect(self.edit_description)
        layout.addWidget(edit_bt)

        rm_bt = QPushButton('Remove Description')
        rm_bt.clicked.connect(self.remove_description)
        layout.addWidget(rm_bt)

        color_bt = QPushButton('Change Color')
        color_bt.clicked.connect(self.set_color)
        layout.addWidget(color_bt)

        layout.addWidget(QLabel('Start:'))
        self.start_bx = QDoubleSpinBox()
        self.start_bx.setDecimals(self.mne.time_decimals)
        self.start_bx.editingFinished.connect(self.start_changed)
        layout.addWidget(self.start_bx)

        layout.addWidget(QLabel('Stop:'))
        self.stop_bx = QDoubleSpinBox()
        self.stop_bx.setDecimals(self.mne.time_decimals)
        self.stop_bx.editingFinished.connect(self.stop_changed)
        layout.addWidget(self.stop_bx)

        widget.setLayout(layout)
        self.setWidget(widget)

    def _add_description_to_cmbx(self, description):
        color_pixmap = QPixmap(25, 25)
        color = QColor(self.main.get_color(description))
        color.setAlpha(75)
        color_pixmap.fill(color)
        color_icon = QIcon(color_pixmap)
        self.description_cmbx.addItem(color_icon, description)

    def add_description(self):
        new_description, ok = QInputDialog.getText(self,
                                                   'Set the name for '
                                                   'the new description!',
                                                   'New description: ')
        if ok and new_description \
                and new_description not in self.mne.descriptions:
            self.mne.descriptions.append(new_description)
            self._add_description_to_cmbx(new_description)
        self.mne.current_description = self.description_cmbx.currentText()

    def edit_description(self):
        curr_descr = self.description_cmbx.currentText()
        ch_descr, ok = QInputDialog.getText(self, 'Set then name for '
                                                  'the changed description!',
                                            f'Change "{curr_descr}" to:')
        if ok and ch_descr:
            edit_regions = [r for r in self.mne.regions
                            if r.description == curr_descr]
            for ed_region in edit_regions:
                idx = self.main._get_onset_idx(ed_region.getRegion()[0])
                self.mne.annotations.description[idx] = ch_descr
                ed_region.update_description(ch_descr)
            self.mne.descriptions = list(set([ch_descr if i == curr_descr
                                              else i for i in
                                              self.mne.descriptions]))
            self.mne.current_description = ch_descr
            self.mne.annot_color_mapping[ch_descr] = \
                self.mne.annot_color_mapping.pop(curr_descr)
            self.update_description_cmbx()
            self.main.update_colors()

    def remove_description(self):
        rm_description = self.description_cmbx.currentText()
        existing_annot = list(self.mne.inst.annotations.description).count(
            rm_description)
        if existing_annot > 0:
            ans = QMessageBox.question(self,
                                       f'Remove annotations '
                                       f'with {rm_description}?',
                                       f'There exist {existing_annot} '
                                       f'annotations with '
                                       f'"{rm_description}".\n'
                                       f'Do you really want to remove them?')
            if ans == QMessageBox.Yes:
                rm_idxs = np.where(
                    self.mne.inst.annotations.description == rm_description)
                for idx in rm_idxs:
                    self.mne.inst.annotations.delete(idx)
                for rm_region in [r for r in self.mne.regions
                                  if r.description == rm_description]:
                    rm_region.remove()

        # Remove from descriptions
        self.mne.descriptions.remove(rm_description)
        self.update_description_cmbx()

        # Remove from color-mapping
        if rm_description in self.mne.annot_color_mapping:
            self.mne.annot_color_mapping.pop(rm_description)

        # Set first description in Combo-Box to current description
        self.description_cmbx.setCurrentIndex(0)
        self.mne.current_description = self.description_cmbx.currentText()

    def description_changed(self, descr_idx):
        new_descr = self.description_cmbx.itemText(descr_idx)
        self.mne.current_description = new_descr

    def start_changed(self):
        start = self.start_bx.value()
        sel_region = self.mne.selected_region
        if sel_region:
            stop = sel_region.getRegion()[1]
            if start < stop:
                sel_region.setRegion((start, stop))
            else:
                QMessageBox.warning(self, 'Invalid value!',
                                    'Start can\'t be bigger or equal to Stop!')
                self.start_bx.setValue(sel_region.getRegion()[0])

    def stop_changed(self):
        stop = self.stop_bx.value()
        sel_region = self.mne.selected_region
        if sel_region:
            start = sel_region.getRegion()[0]
            if start < stop:
                sel_region.setRegion((start, stop))
            else:
                QMessageBox.warning(self, 'Invalid value!',
                                    'Stop can\'t be smaller '
                                    'or equal to Start!')
                self.stop_bx.setValue(sel_region.getRegion()[1])

    def set_color(self):
        curr_descr = self.description_cmbx.currentText()
        if curr_descr in self.mne.annot_color_mapping:
            curr_col = self.mne.annot_color_mapping[curr_descr]
        else:
            curr_col = None
        color = QColorDialog.getColor(QColor(curr_col), self,
                                      f'Choose color for {curr_descr}!')
        if color.isValid():
            self.mne.annot_color_mapping[curr_descr] = color
            self.update_description_cmbx()
            self.main.update_colors()

    def update_values(self, region):
        rgn = region.getRegion()
        self.description_cmbx.setCurrentText(region.description)
        self.start_bx.setValue(rgn[0])
        self.stop_bx.setValue(rgn[1])

    def update_description_cmbx(self):
        self.description_cmbx.clear()
        for description in self.mne.descriptions:
            self._add_description_to_cmbx(description)
        self.description_cmbx.setCurrentText(self.mne.current_description)

    def reset(self):
        if self.description_cmbx.count() > 0:
            self.description_cmbx.setCurrentIndex(0)
            self.mne.current_description = self.description_cmbx.currentText()
        self.start_bx.setValue(0)
        self.stop_bx.setValue(0)


class BrowserView(GraphicsView):
    """Customized View as part of GraphicsView-Framework."""

    def __init__(self, plot, **kwargs):
        super().__init__(**kwargs)
        self.setCentralItem(plot)
        self.viewport().setAttribute(Qt.WA_AcceptTouchEvents, True)

        self.viewport().grabGesture(Qt.PinchGesture)
        self.viewport().grabGesture(Qt.SwipeGesture)

    def viewportEvent(self, event):
        if event.type() in [QEvent.TouchBegin, QEvent.TouchUpdate,
                            QEvent.TouchEnd]:
            if event.touchPoints() == 2:
                pass
        elif event.type() == QEvent.Gesture:
            print('Gesture')
        return super().viewportEvent(event)


class _PGMetaClass(type(BrowserBase), type(QMainWindow)):
    """This is class is necessary to prevent a metaclass conflict.

    The conflict arises due to the different types of QMainWindow and
    BrowserBase.
    """
    pass


class PyQtGraphPtyp(BrowserBase, QMainWindow, metaclass=_PGMetaClass):
    def __init__(self, **kwargs):
        """
        PyQtGraph-Prototype as a new backend for inst.plot() from MNE-Python.
        """

        """
        Defaults for special pyqtgraph-kwargs
        ----------
        ds : int | str
            The downsampling-factor. Either 'auto' to get the downsampling-rate
            from the visible range or an integer (1 means no downsampling).
            Defaults to 'auto'.
        ds_method : str
            The downsampling-method to use (from pyqtgraph).
            See here under "Optimization-Keywords" for more detail:
            https://pyqtgraph.readthedocs.io/en/latest/graphicsItems/plotdataitem.html?#
        ds_chunk_size : int | None
            Chunk size for downsampling. No chunking if None (default).
        antialiasing : bool
            Enable Antialiasing.
        use_opengl : bool
            Use OpenGL.
        show_annotations : bool
            Wether to show annotations (may impact performance in benchmarks).
        enable_ds_cache : bool
            If True cache the downsampled arrays inside RawCurveItems
            per downsampling-factor.
        tsteps_per_window : int
            Set how many single scrolling-steps are done in time
            for the shown time-window.
        check_nan : bool
            If to check for NaN-values.
        preload : str
            If True, preprocessing steps are applied on all data
            and are repeated only if necessary. If False (default),
            preprocessing is applied only on the visible data.
        """
        self.pg_kwarg_defaults = dict(duration=20,
                                      n_channels=30,
                                      highpass=None,
                                      lowpass=None,
                                      ds='auto',
                                      ds_method='peak',
                                      ds_chunk_size=None,
                                      antialiasing=False,
                                      use_opengl=True,
                                      show_annotations=True,
                                      enable_ds_cache=True,
                                      tsteps_per_window=100,
                                      check_nan=False,
                                      remove_dc=True,
                                      preload=False)
        for kw in [k for k in self.pg_kwarg_defaults if k not in kwargs]:
            kwargs[kw] = self.pg_kwarg_defaults[kw]

        BrowserBase.__init__(self, **kwargs)
        QMainWindow.__init__(self)

        # Initialize Attributes and add them to MNEBrowseParams
        self.mne.ds_cache = dict()
        self.mne.global_changed = True
        self.mne.traces = list()
        self.mne.scale_factor = 1
        self.mne.time_decimals = int(np.ceil(
            np.log10(self.mne.inst.info['sfreq'])))

        # Pointers for continous scrolling
        self.mne.hscroll_dir = 1
        self.mne.vscroll_dir = 1

        # Initialize Annotations (ToDo: Adjust to MPL)
        self.mne.annotation_mode = False
        self.mne.annotations = self.mne.inst.annotations
        self.mne.descriptions = list(set(
            self.mne.inst.annotations.description))
        if len(self.mne.descriptions) > 0:
            self.mne.current_description = self.mne.descriptions[0]
        else:
            self.mne.current_description = None
        colors, self.mne.red = _get_color_list(annotations=True)
        self.mne.color_cycle = cycle(colors)
        self.mne.annot_color_mapping = dict()
        self.mne.selected_region = None
        self.mne.regions = list()

        setConfigOption('antialias', self.mne.antialiasing)

        # Initialize Keyboard-Shortcuts
        is_mac = platform.system() == 'Darwin'
        dur_keys = ('fn + ←', 'fn + →') if is_mac else ('Home', 'End')
        ch_keys = ('fn + ↑', 'fn + ↓') if is_mac else ('Page up', 'Page down')
        self.mne.keyboard_shortcuts = [
            ('←', 'Move left'),
            ('→', 'Move right'),
            ('Ctrl + ←', 'Move 1s left'),
            ('Ctrl + →', 'Move 1s right'),
            ('↑', 'Move up'),
            ('↓', 'Move down'),
            ('Ctrl + ↑', 'Move 1 channel up'),
            ('Ctrl + ↓', 'Move 1 channel down'),
            (dur_keys[0], 'Increase time-window'),
            ('Ctrl + ' + dur_keys[0], 'Increase time-window'),
            (dur_keys[1], 'Decrease time-window'),
            ('Ctrl + ' + dur_keys[1], 'Decrease time-window'),
            (ch_keys[0], 'Increase channel-count'),
            ('Ctrl + ' + ch_keys[0], 'Increase channel-count'),
            (ch_keys[1], 'Decrease channel-count'),
            ('Ctrl + ' + ch_keys[1], 'Decrease channel-count'),
            ('a', 'Toggle annotation-mode'),
            ('t', 'Toggle time format')
        ]

        # Create centralWidget and layout
        widget = QWidget()
        layout = QGridLayout()

        # Initialize Axis-Items
        time_ax = TimeAxis(self.mne)
        time_ax.setLabel(text='Time', units='s')
        ch_ax = ChannelAxis(self)
        viewbox = RawViewBox(self)
        vars(self.mne).update(time_ax=time_ax, ch_ax=ch_ax, viewbox=viewbox)

        # Initialize data
        self._update_data()

        # Initialize Trace-Plot
        plt = PlotItem(viewBox=viewbox,
                       axisItems={'bottom': time_ax, 'left': ch_ax})
        # Hide AutoRange-Button
        plt.hideButtons()
        # Configure XY-Range
        self.mne.xmax = self.mne.inst.times[-1]
        plt.setXRange(0, self.mne.duration, padding=0)
        # Add one empty line as padding at top (y=0).
        # Negative Y-Axis to display channels from top.
        self.mne.ymax = len(self.mne.inst.ch_names) + 1
        plt.setYRange(0, self.mne.n_channels + 1, padding=0)
        plt.setLimits(xMin=0, xMax=self.mne.xmax,
                      yMin=0, yMax=self.mne.ymax)
        vars(self.mne).update(plt=plt)

        # Add traces
        for ch_idx in self.mne.picks:
            self.add_trace(ch_idx)

        # Check for OpenGL
        try:
            import OpenGL
        except ModuleNotFoundError:
            logger.warning('pyopengl was not found on this device.\n'
                           'Defaulting to plot without OpenGL with reduced '
                           'performance.')
            self.mne.use_opengl = False

        # Initialize BrowserView (inherits QGraphicsView)
        view = BrowserView(plt, background='w',
                           useOpenGL=self.mne.use_opengl)
        layout.addWidget(view, 0, 0)

        # Initialize Scroll-Bars
        time_bar = TimeScrollBar(self.mne)
        plt.sigXRangeChanged.connect(self.xrange_changed)
        layout.addWidget(time_bar, 1, 0)

        channel_bar = ChannelScrollBar(self.mne)
        plt.sigYRangeChanged.connect(self.yrange_changed)
        layout.addWidget(channel_bar, 0, 1)

        widget.setLayout(layout)
        self.setCentralWidget(widget)

        # Initialize Annotation-Dock
        fig_annotation = AnnotationDock(self)
        self.addDockWidget(Qt.TopDockWidgetArea, fig_annotation)
        fig_annotation.setVisible(False)
        vars(self.mne).update(fig_annotation=fig_annotation)

        # Initialize other widgets associated to annotations.
        self.annot_mode_hint = None
        self.change_annot_mode()

        if self.mne.show_annotations:
            # Add all annotation-regions to a list and plot the visible ones.
            for annot in self.mne.annotations:
                onset = round(annot['onset'] - self.mne.first_time,
                              self.mne.time_decimals)
                duration = round(annot['duration'], self.mne.time_decimals)
                description = annot['description']
                self.add_region(onset, duration, description)

        # Initialize VLine
        self.mne.vline = None

        # Initialize Toolbar
        toolbar = self.addToolBar('Tools')

        adecr_time = QAction('-Time', parent=self)
        adecr_time.triggered.connect(partial(self.change_duration,
                                             -self.mne.tsteps_per_window / 10))
        toolbar.addAction(adecr_time)

        aincr_time = QAction('+Time', parent=self)
        aincr_time.triggered.connect(partial(self.change_duration,
                                             self.mne.tsteps_per_window / 10))
        toolbar.addAction(aincr_time)

        adecr_nchan = QAction('-Channels', parent=self)
        adecr_nchan.triggered.connect(partial(self.change_nchan, -10))
        toolbar.addAction(adecr_nchan)

        aincr_nchan = QAction('+Channels', parent=self)
        aincr_nchan.triggered.connect(partial(self.change_nchan, 10))
        toolbar.addAction(aincr_nchan)

        atoggle_annot = QAction('Toggle Annotations', parent=self)
        atoggle_annot.triggered.connect(self._toggle_annotation_fig)
        toolbar.addAction(atoggle_annot)

        ahelp = QAction('Help', parent=self)
        ahelp.triggered.connect(self._toggle_help_fig)
        toolbar.addAction(ahelp)

        # Add GUI-Elements to MNEBrowserParams-Instance
        vars(self.mne).update(
            plt=plt, view=view, time_bar=time_bar, channel_bar=channel_bar,
            fig_annotation=fig_annotation, toolbar=toolbar
        )

    def _get_scale_transform(self):
        transform = QTransform()
        transform.scale(1, self.mne.scale_factor)

        return transform

    def toggle_bad_channel(self, line):
        if line.ch_name in self.mne.inst.info['bads']:
            self.mne.inst.info['bads'].remove(line.ch_name)
            line.isbad = False
            print(f'{line.ch_name} removed from bad channels!')
        else:
            self.mne.inst.info['bads'].append(line.ch_name)
            line.isbad = True
            print(f'{line.ch_name} added to bad channels!')

        # Update line color
        line.update_bad_color()

        # Update Channel-Axis
        self.mne.ch_ax.redraw()

    def add_trace(self, ch_idx):
        trace = RawTraceItem(self.mne, ch_idx)

        # Apply scaling
        transform = self._get_scale_transform()
        trace.setTransform(transform)

        # Add Item early to have access to viewBox
        self.mne.plt.addItem(trace)
        self.mne.traces.append(trace)

        trace.sigClicked.connect(lambda tr, _: self.toggle_bad_channel(tr))

    def remove_trace(self, trace):
        self.mne.plt.removeItem(trace)
        self.mne.traces.remove(trace)

    def scale_all(self, step):
        self.mne.scale_factor *= 2 ** step
        transform = self._get_scale_transform()

        for line in self.mne.traces:
            line.setTransform(transform)

    def hscroll(self, step):
        rel_step = step * self.mne.duration / self.mne.tsteps_per_window
        # Get current range and add step to it
        xmin, xmax = [i + rel_step for i in self.mne.viewbox.viewRange()[0]]

        if xmin < 0:
            xmin = 0
            xmax = xmin + self.mne.duration
        elif xmax > self.mne.xmax:
            xmax = self.mne.xmax
            xmin = xmax - self.mne.duration

        self.mne.plt.setXRange(xmin, xmax, padding=0)

    def infini_hscroll(self, step):
        vr = self.mne.viewbox.viewRange()
        rel_step = self.mne.duration * step / self.mne.tsteps_per_window
        if vr[0][1] + rel_step > self.mne.xmax or vr[0][0] - rel_step < 0:
            self.mne.hscroll_dir *= -1
        step *= self.mne.hscroll_dir
        self.hscroll(step)

    def vscroll(self, step):
        # Get current range and add step to it
        ymin, ymax = [i + step for i in self.mne.viewbox.viewRange()[1]]

        if ymin < 0:
            ymin = 0
            ymax = self.mne.n_channels + 1
        elif ymax > self.mne.ymax:
            ymax = self.mne.ymax
            ymin = ymax - self.mne.n_channels - 1

        self.mne.plt.setYRange(ymin, ymax, padding=0)

    def infini_vscroll(self, step):
        vr = self.mne.viewbox.viewRange()
        if vr[1][1] + step > self.mne.ymax or vr[1][0] - step < 0:
            self.mne.vscroll_dir *= -1
        step *= self.mne.vscroll_dir
        self.vscroll(step)

    def change_duration(self, step):
        rel_step = (self.mne.duration * step) / (
                self.mne.tsteps_per_window * 2)
        xmin, xmax = self.mne.viewbox.viewRange()[0]
        xmax += rel_step
        xmin -= rel_step

        if xmax > self.mne.xmax:
            xmax = self.mne.xmax

        if xmin < 0:
            xmin = 0

        self.mne.plt.setXRange(xmin, xmax, padding=0)

    def change_nchan(self, step):
        ymin, ymax = self.mne.viewbox.viewRange()[1]
        ymax += step
        if ymax > self.mne.ymax:
            ymax = self.mne.ymax
            ymin -= step

        if ymin < 0:
            ymin = 0

        if ymax - ymin <= 2:
            ymax = ymin + 2

        self.mne.plt.setYRange(ymin, ymax, padding=0)

    def remove_vline(self):
        if self.mne.vline:
            self.mne.plt.removeItem(self.mne.vline)

    def add_vline(self, pos):
        # Remove vline if already shown
        self.remove_vline()

        self.mne.vline = VLine(pos, bounds=(0, self.mne.xmax))
        self.mne.plt.addItem(self.mne.vline)

    def toggle_annot_hint(self, annotation_mode):
        if annotation_mode:
            self.annot_mode_hint = TextItem('Annotation-Mode', color='r',
                                            anchor=(0, 0))
            self.annot_mode_hint.setPos(0, 0)
            self.annot_mode_hint.setFont(QFont('AnyStyle', 20, QFont.Bold))
            self.mne.plt.addItem(self.annot_mode_hint)
        elif self.annot_mode_hint:
            self.mne.plt.removeItem(self.annot_mode_hint)
            self.annot_mode_hint = None

    def xrange_changed(self, _, xrange):
        # Update data
        self.mne.t_start = xrange[0]
        self.mne.duration = xrange[1] - xrange[0]
        self._redraw(update_data=True)

        # Update Time-Bar
        self.mne.time_bar.update_value_external(xrange)

        # Update Annotations
        if self.mne.show_annotations:
            self.update_annot_range(*xrange)

    def yrange_changed(self, _, yrange):
        # Update picks
        self.mne.ch_start = round(yrange[0])
        self.mne.n_channels = round(yrange[1] - yrange[0] - 1)
        self._update_picks()
        self._update_data()

        off_traces = [tr for tr in self.mne.traces
                      if tr.ch_idx not in self.mne.picks]
        add_idxs = [p for p in self.mne.picks
                    if p not in [tr.ch_idx for tr in self.mne.traces]]
        # Update number of traces.
        trace_diff = len(self.mne.picks) - len(self.mne.traces)
        # Remove unnecessary traces.
        if trace_diff < 0:
            # Only remove from traces not in picks.
            remove_traces = off_traces[:abs(trace_diff)]
            for trace in remove_traces:
                self.remove_trace(trace)
                off_traces.remove(trace)
        # Add new traces if necessary.
        if trace_diff > 0:
            # Make copy to avoid skipping iteration.
            idxs_copy = add_idxs.copy()
            for aidx in idxs_copy:
                self.add_trace(aidx)
                add_idxs.remove(aidx)

        # Update data of traces outside of yrange
        for trace, ch_idx in zip(off_traces, add_idxs):
            trace.set_ch_idx(ch_idx)
            trace.update_bad_color()
            trace.set_data()

        # Update Channel-Bar
        self.mne.channel_bar.update_ch_start()

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    # DATA HANDLING
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    def _apply_downsampling(self):
        """
        Get Downsampling-Factor and apply Downsampling
        with one of multiple methods.

        The methods are taken from PlotDataItem in pyqtgraph
        and adjusted to multi-channel data.
        """

        # Get Downsampling-Factor
        # Auto-Downsampling from pyqtgraph
        if (self.mne.ds == 'auto' and
                all([hasattr(self.mne, a) for a in ['viewbox', 'times']])):
            vb = self.mne.viewbox
            if vb is not None:
                view_range = vb.viewRect()
            else:
                view_range = None
            if view_range is not None and len(self.mne.times) > 1:
                dx = float(self.mne.times[-1] - self.mne.times[0]) / (
                        len(self.mne.times) - 1)
                if dx != 0.0:
                    x0 = view_range.left() / dx
                    x1 = view_range.right() / dx
                    width = vb.width()
                    if width != 0.0:
                        # Auto-Downsampling with 5 samples per pixel
                        self.mne.ds = int(max(1, (x1 - x0) / (width * 5)))

        if not isinstance(self.mne.ds, int):
            self.mne.ds = 1

        # Apply Downsampling
        if self.mne.ds not in [None, 1]:
            ds = self.mne.ds
            times = self.mne.times
            data = self.mne.data
            n_ch = data.shape[0]

            if ds in self.mne.ds_cache:
                # Caching is only activated if downsampling is applied
                # on all of the data.
                times, data = self.mne.ds_cache[ds]
            else:
                if self.mne.ds_method == 'subsample':
                    times = times[::ds]
                    data = data[:, ::ds]

                elif self.mne.ds_method == 'mean':
                    n = len(times) // ds
                    # start of x-values
                    # try to select a somewhat centered point
                    stx = ds // 2
                    times = times[stx:stx + n * ds:ds]
                    rs_data = data[:, n * ds].reshape(n_ch, n, ds)
                    data = rs_data.mean(axis=2)

                elif self.mne.ds_method == 'peak':
                    n = len(times) // ds
                    # start of x-values
                    # try to select a somewhat centered point
                    stx = ds // 2

                    x1 = np.empty((n, 2))
                    x1[:] = times[stx:stx + n * ds:ds, np.newaxis]
                    times = x1.reshape(n * 2)

                    y1 = np.empty((n_ch, n, 2))
                    y2 = data[:n * ds].reshape((n_ch, n, ds))
                    y1[:, :, 0] = y2.max(axis=2)
                    y1[:, :, 1] = y2.min(axis=2)
                    data = y1.reshape((n_ch, n * 2))

                if self.mne.enable_ds_cache and \
                        self.mne.preload:
                    self.mne.ds_cache[ds] = times, data

            self.mne.times, self.mne.data = times, data

    def _update_data(self):
        if self.mne.preload:
            # This is just an experimental feature
            # which won't be further developed for now.
            # Data has to be reloaded and processed, when:
            #   - projectors toggled
            #   - dc toggled (actually dc should be only applied on visible
            #   range but this could be changed if global stays an option)
            #   - filter-settings change (probably not useful here)
            if self.mne.global_changed:
                # Load and preprocess all data instead of slice
                old_duration = self.mne.duration
                self.mne.duration = self.mne.inst.times[-1]
                self.mne.picks = np.arange(self.mne.ch_names.shape[0])
                old_remove_dc = self.mne.remove_dc
                self.mne.remove_dc = False
                super()._update_data()
                self.mne.remove_dc = old_remove_dc
                # Store processed times and data
                self.mne.global_data = self.mne.data
                self.mne.global_times = self.mne.times
                # Revert to real values of duration and picks
                self.mne.duration = old_duration
                self._update_picks()

                self.mne.global_changed = False

                # Invert Data to be displayed from top on inverted Y-Axis.
                self.mne.data *= -1

            # get start/stop-samples
            start_sec = self.mne.t_start - self.mne.first_time
            stop_sec = start_sec + self.mne.duration
            if self.mne.is_epochs:
                start, stop = np.round(np.array([start_sec, stop_sec])
                                       * self.mne.info['sfreq']).astype(int)
            else:
                start, stop = self.mne.inst.time_as_index(
                    (start_sec, stop_sec))
            self.mne.times = self.mne.global_times[start:stop]
            self.mne.data = self.mne.global_data[:, start:stop]

            # remove DC
            if self.mne.remove_dc:
                self.mne.data = self.mne.data - \
                                self.mne.data.mean(axis=1, keepdims=True)
            else:
                self.mne.data = self.mne.global_data[:, start:stop]

        else:
            super()._update_data()

            # Invert Data to be displayed from top on inverted Y-Axis.
            self.mne.data *= -1

        # Apply Downsampling (if enabled)
        self._apply_downsampling()

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    # ANNOTATIONS
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    def get_color(self, description):
        # As in matplotlib-backend
        if any([b in description for b in ['bad', 'BAD', 'Bad']]):
            color = self.mne.red
        elif description in self.mne.annot_color_mapping:
            color = self.mne.annot_color_mapping[description]
        else:
            color = next(self.mne.color_cycle)
        self.mne.annot_color_mapping[description] = color
        return color

    def update_colors(self):
        update_regions = [r for r in self.mne.regions
                          if r.description == self.mne.current_description]
        for u_region in update_regions:
            u_region.update_color(self.get_color(self.mne.current_description))

    def add_region(self, onset, duration, description, region=None):
        color = self.get_color(description)
        if not region:
            region = AnnotRegion(self.mne, description=description,
                                 values=(onset, onset + duration),
                                 color=color,
                                 time_decimals=self.mne.time_decimals)
        region.regionChangeFinished.connect(self.region_changed)
        region.gotSelected.connect(self.region_selected)
        region.removeRequested.connect(self.remove_region)
        self.mne.viewbox.sigYRangeChanged.connect(
            region.change_label_pos)
        self.mne.regions.append(region)

        xrange = self.mne.viewbox.viewRange()[0]
        if xrange[0] < onset < xrange[1] \
                and region not in self.mne.plt.items:
            self.mne.plt.addItem(region)
            # Found no better way yet to initialize the region-labels
            self.mne.plt.addItem(region.label_item)
            region.change_label_pos()

    def remove_region(self, region):
        # Remove from shown regions
        if region.label_item in self.mne.viewbox.addedItems:
            self.mne.viewbox.removeItem(region.label_item)
        if region in self.mne.plt.items:
            self.mne.plt.removeItem(region)

        # Remove from all regions
        if region in self.mne.regions:
            self.mne.regions.remove(region)

        # Remove from annotations
        idx = self._get_onset_idx(region.getRegion()[0])
        self.mne.annotations.delete(idx)

    def region_selected(self, region):
        old_region = self.mne.selected_region
        # Remove selected-status from old region
        if old_region:
            old_region.selected = False
            old_region.update()
        self.mne.selected_region = region
        self.mne.current_description = region.description
        self.mne.fig_annotation.update_values(region)

    def _get_onset_idx(self, onset):
        idx = np.where(
            np.around(self.mne.annotations.onset - self.mne.first_time,
                      self.mne.time_decimals) == onset)
        return idx

    def region_changed(self, region):
        rgn = region.getRegion()
        region.select(True)
        idx = self._get_onset_idx(region.old_onset)

        # Update Spinboxes of Annot-Dock
        self.mne.fig_annotation.update_values(region)

        # Change annotations
        self.mne.annotations.onset[idx] = round(rgn[0] + self.mne.first_time,
                                                self.mne.time_decimals)
        self.mne.annotations.duration[idx] = rgn[1] - rgn[0]

    def update_annot_range(self, xmin, xmax):
        inside_onsets = self.mne.annotations.onset[
            np.where(
                (self.mne.annotations.onset + self.mne.annotations.duration
                 >= xmin + self.mne.first_time) &
                (self.mne.annotations.onset < xmax + self.mne.first_time))[0]]
        inside_onsets = [
            round(io - self.mne.first_time, self.mne.time_decimals)
            for io in inside_onsets]
        rm_regions = [r for r in self.mne.regions
                      if r.getRegion()[0] not in inside_onsets
                      and r in self.mne.plt.items]
        for rm_region in rm_regions:
            self.mne.plt.removeItem(rm_region)
            self.mne.plt.removeItem(rm_region.label_item)

        add_regions = [r for r in self.mne.regions
                       if r.getRegion()[0] in inside_onsets
                       and r not in self.mne.plt.items]
        for add_region in add_regions:
            self.mne.plt.addItem(add_region)
            self.mne.plt.addItem(add_region.label_item)
            add_region.change_label_pos()

    def add_annotation(self, onset, duration, region=None):
        """Add annotation to Annotations (onset is here the onset
        in the plot which is then adjusted with first_time)"""
        self.mne.annotations.append(onset + self.mne.first_time, duration,
                                    self.mne.current_description)
        self.add_region(onset, duration, self.mne.current_description, region)
        self.update_annot_range(*self.mne.plt.viewRange()[0])

    def change_annot_mode(self):
        if self.mne.show_annotations:
            if not self.mne.annotation_mode:
                # Reset Widgets in Annotation-Figure
                self.mne.fig_annotation.reset()

            # Show Annotation-Dock if activated.
            self.mne.fig_annotation.setVisible(self.mne.annotation_mode)

            # Make Regions movable if activated.
            for region in self.mne.regions:
                region.setMovable(self.mne.annotation_mode)

            # Remove selection-rectangle.
            if not self.mne.annotation_mode and self.mne.selected_region:
                self.mne.selected_region.select(False)
                self.mne.selected_region = None

            # Show label for Annotation-Mode.
            self.toggle_annot_hint(self.mne.annotation_mode)

    def _toggle_annotation_fig(self):
        self.mne.annotation_mode = not self.mne.annotation_mode
        self.change_annot_mode()

    def _toggle_help_fig(self):
        if self.mne.fig_help is None:
            self.mne.fig_help = HelpDialog(self)
        else:
            self.mne.fig_help.close()
            self.mne.fig_help = None

    def _toggle_butterfly(self):
        # ToDo: Still needs to be implemented
        pass

    def _toggle_dc(self):
        self.mne.remove_dc = not self.mne.remove_dc
        self._redraw()

    def _toggle_time_format(self):
        if self.mne.time_format == 'float':
            self.mne.time_format = 'clock'
            self.mne.time_ax.setLabel(text='Time')
        else:
            self.mne.time_format = 'float'
            self.mne.time_ax.setLabel(text='Time', units='s')
        self.mne.time_ax.refresh()

    def _update_trace_offsets(self):
        pass

    def _create_selection_fig(self):
        pass

    def _draw_traces(self):
        pass

    def _setup_annotation_colors(self):
        pass

    def _draw_annotations(self):
        pass

    def _toggle_proj_fig(self):
        pass

    def keyPressEvent(self, event):
        # On MacOs additionally KeypadModifier is set when arrow-keys
        # are pressed.
        # On Unix GroupSwitchModifier is set when ctrl is pressed.
        # To preserve cross-platform consistency the following comparison
        # of the modifier-values is done.
        shift_pressed = '4' in hex(int(event.modifiers()))
        lil_t = 1
        big_t = 10
        if event.key() == Qt.Key_Left:
            if shift_pressed:
                self.hscroll(-lil_t)
            else:
                self.hscroll(-big_t)
        elif event.key() == Qt.Key_Right:
            if shift_pressed:
                self.hscroll(lil_t)
            else:
                self.hscroll(big_t)
        elif event.key() == Qt.Key_Up:
            if shift_pressed:
                self.vscroll(-1)
            else:
                self.vscroll(-10)
        elif event.key() == Qt.Key_Down:
            if shift_pressed:
                self.vscroll(1)
            else:
                self.vscroll(10)
        elif event.key() == Qt.Key_Home:
            if shift_pressed:
                self.change_duration(-lil_t)
            else:
                self.change_duration(-big_t)
        elif event.key() == Qt.Key_End:
            if shift_pressed:
                self.change_duration(lil_t)
            else:
                self.change_duration(big_t)
        elif event.key() == Qt.Key_PageDown:
            if shift_pressed:
                self.change_nchan(-1)
            else:
                self.change_nchan(-10)
        elif event.key() == Qt.Key_PageUp:
            if shift_pressed:
                self.change_nchan(1)
            else:
                self.change_nchan(10)
        elif event.key() == Qt.Key_Minus:
            self.scale_all(-1)
        elif event.key() == Qt.Key_Plus:
            self.scale_all(1)
        elif event.key() == Qt.Key_A:
            self._toggle_annotation_fig()
        elif event.key() == Qt.Key_T:
            self._toggle_time_format()
        elif event.key() == Qt.Key_Question:
            self._toggle_help_fig()
        elif event.key() == Qt.Key_J:
            if shift_pressed:
                self._toggle_all_projs()
            else:
                self._toggle_proj_fig()
        elif event.key() == Qt.Key_D:
            self._toggle_dc()

    def _redraw(self, update_data=True):
        if update_data:
            self._update_data()

        # Update data in traces
        for trace in self.mne.traces:
            trace.set_data()

    def _close_event(self, fig=None):
        fig = fig or self
        fig.close()

    def _get_size(self):
        inch_width = self.width() / self.physicalDpiX()
        inch_height = self.height() / self.physicalDpiY()

        return inch_width, inch_height

    def _fake_keypress(self, key, fig=None):
        fig = fig or self
        QTest.keyPress(fig, qt_key_mapping[key])

    def _fake_click(self, point, fig=None, ax=None,
                    xform='ax', button=1, kind='press'):
        pass

    def _fake_scroll(self, x, y, step, fig=None):
        pass

    def _click_ch_name(self, ch_index, button):
        pass

    def _resize_by_factor(self, factor):
        pass

    def closeEvent(self, event):
        event.accept()

        self._close(event)


qt_key_mapping = {
    'escape': Qt.Key_Escape,
    'down': Qt.Key_Down,
    'up': Qt.Key_Up,
    'left': Qt.Key_Left,
    'right': Qt.Key_Right,
    '-': Qt.Key_Minus,
    '+': Qt.Key_Plus,
    'pageup': Qt.Key_PageUp,
    'pagedown': Qt.Key_PageDown,
    'home': Qt.Key_Home,
    'end': Qt.Key_End,
    '?': Qt.Key_Question
}
for char in 'abcdefghijklmnopyqrstuvwxyz0123456789':
    qt_key_mapping[char] = getattr(Qt, f'Key_{char.upper() or char}')


def _init_browser(inst, figsize, **kwargs):
    setConfigOption('enableExperimental', True)

    mkQApp()
    browser = PyQtGraphPtyp(inst=inst, figsize=figsize, **kwargs)
    width = int(figsize[0] * browser.physicalDpiX())
    height = int(figsize[1] * browser.physicalDpiY())
    browser.resize(width, height)

    return browser
