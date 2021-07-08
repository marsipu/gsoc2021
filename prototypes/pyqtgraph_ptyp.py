import datetime
import platform
from collections import OrderedDict
from functools import partial
from math import floor

import numpy as np
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (QAction, QColorDialog, QComboBox, QDialog, QDockWidget,
                             QDoubleSpinBox, QFormLayout, QGraphicsItem, QGridLayout,
                             QHBoxLayout, QInputDialog, QLabel, QMainWindow,
                             QMessageBox, QPushButton, QScrollBar, QSizePolicy, QWidget)
from pyqtgraph import (AxisItem, GraphicsView, InfLineLabel, InfiniteLine, LinearRegionItem,
                       PlotCurveItem, PlotItem, TextItem, ViewBox, functions,
                       mkBrush, mkPen)
from pyqtgraph.Qt import QtCore


class RawCurveItem(PlotCurveItem):
    def __init__(self, data, times, ch_name, ypos, sfreq,
                 ds, ds_method, ds_chunk_size, isbad):
        super().__init__(clickable=True)
        self._data = data
        self._times = times
        self.ch_name = ch_name
        self.ypos = ypos
        self.sfreq = sfreq
        self.ds = ds
        self.ds_method = ds_method
        self.ds_chunk_size = ds_chunk_size
        self.isbad = isbad
        self.update_bad_color()

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        self._data = value

    @property
    def times(self):
        return self._times

    @times.setter
    def times(self, value):
        self._times = value

    def update_bad_color(self):
        if self.isbad:
            self.setPen('r')
        else:
            self.setPen('k')

    def apply_ds(self, x, y, ds):
        if self.ds_method == 'subsample':
            x = x[::ds]
            y = y[::ds]
        elif self.ds_method == 'mean':
            n = len(x) // ds
            stx = ds // 2  # start of x-values; try to select a somewhat centered point
            x = x[stx:stx + n * ds:ds]
            y = y[:n * ds].reshape(n, ds).mean(axis=1)
        elif self.ds_method == 'peak':
            n = len(x) // ds
            x1 = np.empty((n, 2))
            stx = ds // 2  # start of x-values; try to select a somewhat centered point
            x1[:] = x[stx:stx + n * ds:ds, np.newaxis]
            x = x1.reshape(n * 2)
            y1 = np.empty((n, 2))
            y2 = y[:n * ds].reshape((n, ds))
            y1[:, 0] = y2.max(axis=1)
            y1[:, 1] = y2.min(axis=1)
            y = y1.reshape(n * 2)

        return x, y

    def xrange_changed(self, xrange):
        xmin, xmax = xrange
        start = max(0, int(xmin * self.sfreq))
        stop = min(len(self.data), int(xmax * self.sfreq + 1))
        visible_x = self.times[start:stop]
        visible_y = self.data[start:stop]

        # Auto-Downsampling from pyqtgraph
        if self.ds == 'auto':
            ds = 1
            view = self.getViewBox()
            if view is not None:
                view_range = view.viewRect()
            else:
                view_range = None
            if view_range is not None and len(self.times) > 1:
                dx = float(self.times[-1] - self.times[0]) / (len(self.times) - 1)
                if dx != 0.0:
                    x0 = view_range.left() / dx
                    x1 = view_range.right() / dx
                    width = self.getViewBox().width()
                    if width != 0.0:
                        # Auto-Downsampling with 3 samples per pixel
                        ds = int(max(1, (x1 - x0) / (width * 3)))
                        print(f'Auto-Downsampling: {ds}')
        else:
            ds = self.ds

        if ds not in [1, None]:
            if self.ds_chunk_size:
                chunkSize = (self.ds_chunk_size // ds) * ds
                sourcePtr = 0
                x = np.empty(0, dtype=self.times.dtype)
                y = np.empty(0, dtype=self.data.dtype)
                data_len = len(visible_x)
                while sourcePtr < data_len - 1:
                    xchunk = visible_x[sourcePtr:min(stop, sourcePtr + chunkSize)]
                    ychunk = visible_y[sourcePtr:min(stop, sourcePtr + chunkSize)]
                    sourcePtr += len(xchunk)

                    xchunk, ychunk = self.apply_ds(xchunk, ychunk, ds)

                    x = np.append(x, xchunk)
                    y = np.append(y, ychunk)

            else:
                x, y = self.apply_ds(visible_x, visible_y, ds)

        else:
            x = visible_x
            y = visible_y

        self.setData(x, y)
        self.setPos(0, self.ypos)

    def mouseClickEvent(self, ev):
        if not self.clickable or ev.button() != QtCore.Qt.MouseButton.LeftButton:
            ev.ignore()
            return
        if self.mouseShape().contains(ev.pos()):
            ev.accept()
            self.isbad = not self.isbad
            self.update_bad_color()
            self.sigClicked.emit(self, ev)


class TimeAxis(AxisItem):
    def __init__(self, main):
        self.main = main
        super().__init__(orientation='bottom')

    def tickStrings(self, values, scale, spacing):

        if self.main.clock_ticks:
            meas_date = self.main.raw.info['meas_date']
            first_time = datetime.timedelta(seconds=self.main.raw.first_time)
            digits = np.ceil(-np.log10(spacing) + 1).astype(int)
            tick_strings = list()
            for val in values:
                val_time = datetime.timedelta(seconds=val) + first_time + meas_date
                val_str = val_time.strftime('%H:%M:%S')
                if int(val_time.microsecond):
                    val_str += f'{round(val_time.microsecond * 1e-6, digits)}'[1:]
                tick_strings.append(val_str)
        else:
            tick_strings = super().tickStrings(values, scale, spacing)

        return tick_strings

    def refresh(self):
        self.picture = None
        self.update()


class ChannelAxis(AxisItem):
    def __init__(self, main):
        self.main = main
        self.ch_texts = dict()
        super().__init__(orientation='left')

    def tickValues(self, minVal, maxVal, size):
        minVal, maxVal = sorted((minVal, maxVal))
        values = list(range(round(minVal) + 1, round(maxVal)))
        tick_values = [(1, values)]
        return tick_values

    def tickStrings(self, values, scale, spacing):
        if not isinstance(values, list):
            values = [values]
        # Get channel-names
        tick_strings = [self.main.raw.ch_names[v - 1] for v in values]

        return tick_strings

    def drawPicture(self, p, axisSpec, tickSpecs, textSpecs):
        super().drawPicture(p, axisSpec, tickSpecs, textSpecs)
        for rect, flags, text in textSpecs:
            if text in self.main.raw.info['bads']:
                p.setPen(functions.mkPen('r'))
            else:
                p.setPen(functions.mkPen('k'))
            self.ch_texts[text] = (rect.top(), rect.top() + rect.height())
            p.drawText(rect, int(flags), text)

    def mouseClickEvent(self, event):
        # Clean up channel-texts
        self.ch_texts = {k: v for k, v in self.ch_texts.items()
                         if k in [li.ch_name for li in self.main.plt.lines]}
        # Get channel-name from position of channel-label
        ypos = event.scenePos().y()
        ch_name = [chn for chn in self.ch_texts
                   if self.ch_texts[chn][0] < ypos < self.ch_texts[chn][1]]
        if len(ch_name) > 0:
            ch_name = ch_name[0]
            print(f'{ch_name} clicked!')
            line = [li for li in self.main.plt.lines if li.ch_name == ch_name][0]
            self.main.plt.addrm_bad_channel(line)
        # return super().mouseClickEvent(event)


class TimeScrollBar(QScrollBar):
    def __init__(self, main):
        super().__init__(QtCore.Qt.Horizontal)
        self.main = main

        self.setMinimum(0)
        self.setMaximum(self.main.plt.xmax - self.main.duration)
        self.update_duration()
        self.setSingleStep(1)
        self.setFocusPolicy(QtCore.Qt.WheelFocus)
        # Because valueChanged is needed (captures every input to scrollbar,
        # not just sliderMoved), there has to be made a differentiation
        # between internal and external changes.
        self.external_change = False
        self.valueChanged.connect(self.time_changed)

    def time_changed(self, value):
        if not self.external_change:
            self.main.plt.setXRange(value, value + self.main.duration, padding=0)

    def update_duration(self):
        self.setPageStep(self.main.duration)
        self.setMaximum(self.main.plt.xmax - self.main.duration)

    def keyPressEvent(self, event):
        # Let main handle the keypress
        event.ignore()


class ChannelScrollBar(QScrollBar):
    def __init__(self, main):
        super().__init__(QtCore.Qt.Vertical)
        self.main = main

        self.setMinimum(0)
        self.setMaximum(self.main.plt.ymax - self.main.nchan - 1)
        self.update_nchan()
        self.setSingleStep(1)
        self.setFocusPolicy(QtCore.Qt.WheelFocus)
        # Because valueChanged is needed (captures every input to scrollbar,
        # not just sliderMoved), there has to be made a differentiation
        # between internal and external changes.
        self.external_change = False
        self.valueChanged.connect(self.channel_changed)

    def channel_changed(self, value):
        new_ymin = value
        new_ymax = value + self.main.nchan + 1
        if not self.external_change:
            self.main.plt.setYRange(new_ymin, new_ymax, padding=0)

    def update_nchan(self):
        self.setPageStep(self.main.nchan)
        self.setMaximum(self.main.plt.ymax - self.main.nchan - 1)

    def keyPressEvent(self, event):
        # Let main handle the keypress
        event.ignore()


class RawViewBox(ViewBox):
    def __init__(self, main):
        super().__init__(invertY=True)
        self.enableAutoRange(enable=False, x=False, y=False)
        self.main = main
        self._drag_start = None
        self._drag_region = None

    def mouseDragEvent(self, event, axis=None):
        event.accept()

        if event.button() == QtCore.Qt.LeftButton:
            if self.main.annotation_mode:
                if event.isStart():
                    self._drag_start = self.mapSceneToView(event.scenePos()).x()
                    self._drag_region = AnnotationRegion(description=self.main.annot_label,
                                                         values=(self._drag_start, self._drag_start))
                    self.main.plt.addItem(self._drag_region)
                elif event.isFinish():
                    drag_stop = self.mapSceneToView(event.scenePos()).x()
                    self._drag_region.setRegion((self._drag_start, drag_stop))
                    onset = min(self._drag_start, drag_stop)
                    duration = abs(self._drag_start - drag_stop)
                    self.main.annot_ctrl.add_annotation(onset, duration, self._drag_region)
                else:
                    self._drag_region.setRegion((self._drag_start,
                                                 self.mapSceneToView(event.scenePos()).x()))
            # else:
            #     super().mouseDragEvent(event, axis)

    def mouseClickEvent(self, event):
        # If we want the context-menu back, uncomment following line
        # super().mouseClickEvent(event)
        if event.button() == QtCore.Qt.LeftButton:
            self.main.plt.add_vline(self.mapSceneToView(event.scenePos()).x())
        elif event.button() == QtCore.Qt.RightButton:
            self.main.plt.remove_vline()

    def wheelEvent(self, ev, axis=None):
        ev.accept()
        scroll = -1 * ev.delta() / 120
        if ev.orientation() == QtCore.Qt.Horizontal:
            hscroll = scroll * self.main.duration / 100
            self.main.plt.hscroll(hscroll)
        elif ev.orientation() == QtCore.Qt.Vertical:
            self.main.plt.vscroll(scroll)


class VLineLabel(InfLineLabel):
    def __init__(self, vline):
        super().__init__(vline, text='{value:.3f} s', position=0.975,
                         fill='g', color='b', movable=True)
        self.vline = vline

    def mouseDragEvent(self, ev):
        if self.movable and ev.button() == QtCore.Qt.LeftButton:
            if ev.isStart():
                self.vline.moving = True
                self.cursorOffset = self.vline.pos() - self.mapToView(ev.buttonDownPos())
            ev.accept()

            if not self.vline.moving:
                return

            self.vline.setPos(self.cursorOffset + self.mapToView(ev.pos()))
            self.vline.sigDragged.emit(self)
            if ev.isFinish():
                self.vline.moving = False
                self.vline.sigPositionChangeFinished.emit(self)


class VLine(InfiniteLine):
    def __init__(self, pos, bounds):
        super().__init__(pos, pen='g', hoverPen='y',
                         movable=True, bounds=bounds)
        self.line = VLineLabel(self)


class HelpDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.init_ui()
        self.open()

    def init_ui(self):
        layout = QFormLayout()
        for key, text in self.main.keyboard_shortcuts:
            layout.addRow(key, QLabel(text))
        self.setLayout(layout)


class AnnotationRegion(LinearRegionItem):
    gotSelected = QtCore.Signal(object)
    removeRequested = QtCore.Signal(object)

    def __init__(self, description, values):
        super().__init__(values=values, orientation='vertical', movable=True, swapMode='sort')
        self.old_onset = values[0]
        self.selected = False
        self.setToolTip(description)

    def paint(self, p, *args):
        super().paint(p, *args)
        if self.selected:
            p.setBrush(mkBrush(None))
            p.setPen(mkPen(color='g', width=3))
            p.drawRect(self.boundingRect())

    def mouseClickEvent(self, event):
        event.accept()
        if event.button() == QtCore.Qt.LeftButton and self.movable:
            self.gotSelected.emit(self)
            self.selected = True
            self.update()
        elif event.button() == QtCore.Qt.RightButton and self.movable:
            self.removeRequested.emit(self)

    def mouseDragEvent(self, event):
        event.accept()
        super().mouseDragEvent(event)
        if event.isFinish():
            self.old_onset = self.getRegion()[0]

    def lineMoveFinished(self):
        super().lineMoveFinished()
        self.old_onset = self.getRegion()[0]


class AnnotationController:
    """ Controller for all Annotation-Regions."""

    def __init__(self, main):
        self.main = main
        self.first_time = main.raw.first_time
        self.annotations = main.raw.annotations
        self.annotation_colors = dict()
        self.current_label = None
        self.selected_region = None
        self.regions = dict()
        self.in_plot = dict()

        for annot in self.annotations:
            onset = annot['onset'] - self.first_time
            duration = annot['duration']
            description = annot['description']
            self.add_region(onset, duration, description)

    def add_region(self, onset, duration, description, region=None):
        if not region:
            region = AnnotationRegion(description=description,
                                      values=(onset, onset + duration))
        region.sigRegionChangeFinished.connect(self.region_changed)
        region.gotSelected.connect(self.region_selected)
        region.removeRequested.connect(self.remove_region)
        self.regions[onset] = region

    def remove_region(self, region):
        onset = region.getRegion()[0]
        # Remove from shown regions
        if onset in self.in_plot:
            self.main.plt.removeItem(self.in_plot[onset])
            self.in_plot.pop(onset)

        # Remove from all regions
        if onset in self.regions:
            self.regions.pop(onset)

        # Remove from annotations
        idx = np.where(self.annotations.onset == onset + self.first_time)
        self.annotations.delete(idx)

    def region_selected(self, region):
        old_region = self.selected_region
        # Remove selected-status from old region
        if old_region:
            old_region.selected = False
            old_region.update()
        self.selected_region = region

    def region_changed(self, region):
        idx = np.where(self.annotations.onset == region.old_onset + self.first_time)
        rgn = region.getRegion()

        # Change entries in region-dictionaries
        self.regions[rgn[0]] = self.regions.pop(region.old_onset)
        self.in_plot[rgn[0]] = self.in_plot.pop(region.old_onset)

        # Change annotations
        self.annotations.onset[idx] = rgn[0] + self.first_time
        self.annotations.duration[idx] = rgn[1] - rgn[0]

    def update_range(self, xmin, xmax):
        inside_onsets = self.annotations.onset[np.where((self.annotations.onset + self.annotations.duration
                                                         >= xmin + self.first_time) &
                                                        (self.annotations.onset < xmax + self.first_time))[0]]
        rm_onsets = [o for o in self.in_plot if o + self.first_time not in inside_onsets]
        for rm_onset in rm_onsets:
            self.main.plt.removeItem(self.in_plot[rm_onset])
            self.in_plot.pop(rm_onset)

        add_onsets = [o for o in self.regions if o + self.first_time in inside_onsets and o not in self.in_plot
                      and self.regions[o] not in self.main.plt.items]
        for add_onset in add_onsets:
            region = self.regions[add_onset]
            self.main.plt.addItem(region)
            self.in_plot[add_onset] = region

    def add_annotation(self, onset, duration, region=None):
        """Add annotation to Annotations (onset is here the onset
        in the plot which is then adjusted with first_time)"""
        self.annotations.append(onset + self.first_time, duration, self.current_label)
        self.add_region(onset, duration, self.current_label, region)
        self.update_range(*self.main.plt.viewRange()[0])

    def change_mode(self, annotation_on):
        for region in self.regions.values():
            region.setMovable(annotation_on)


class AnnotationDock(QDockWidget):
    def __init__(self, main):
        super().__init__('Annotations')
        self.main = main
        self.init_ui()

    def init_ui(self):
        widget = QWidget()
        layout = QHBoxLayout()

        self.label_cmbx = QComboBox()
        self.label_cmbx.currentTextChanged.connect(self.label_changed)
        self.label_cmbx.addItems(set(self.main.raw.annotations.description))
        layout.addWidget(self.label_cmbx)

        add_bt = QPushButton('Add Label')
        add_bt.clicked.connect(self.add_label)
        layout.addWidget(add_bt)

        rm_bt = QPushButton('Remove Label')
        rm_bt.clicked.connect(self.remove_label)
        layout.addWidget(rm_bt)

        color_bt = QPushButton('Change Color')
        color_bt.clicked.connect(self.get_color)
        layout.addWidget(color_bt)

        self.onset_bx = QDoubleSpinBox()
        self.onset_bx.valueChanged.connect(self.onset_changed)
        layout.addWidget(self.onset_bx)

        self.duration_bx = QDoubleSpinBox()
        self.duration_bx.valueChanged.connect(self.duration_changed)
        layout.addWidget(self.duration_bx)

        widget.setLayout(layout)
        self.setWidget(widget)

    def add_label(self):
        new_label = QInputDialog.getText(self, 'Set the name for the new label', 'New label: ')
        if new_label != '':
            self.label_cmbx.addItem(new_label)
            self.label_cmbx.setCurrentText(new_label)

    def remove_label(self):
        rm_label = self.label_cmbx.currentText()
        existing_annot = list(self.main.raw.annotations.description).count(rm_label)
        if existing_annot > 0:
            answer = QMessageBox.question(self, f'Remove annotations with {rm_label}?',
                                          f'There exist {existing_annot} annotations with {rm_label}.\n'
                                          f'Do you really want to remove them?')
            if answer == QMessageBox.Yes:
                rm_idxs = np.where(self.main.raw.annotations.description == rm_label)
                for idx in rm_idxs:
                    self.main.raw.annotations.delete(idx)

    def label_changed(self, label):
        self.main.annot_ctrl.current_label = label

    def onset_changed(self, val):
        sel_region = self.main.annot_ctrl.selected_region
        if sel_region:
            sel_region.setRange((val, sel_region.getRegion()[1]))

    def duration_changed(self, val):
        sel_region = self.main.annot_ctrl.selected_region
        if sel_region:
            onset = sel_region.getRegion()[0]
            sel_region.setRange(onset, onset + val)
        current_idx = self.label_cmbx.currentIndex()
        self.main.raw.annotations.duration[current_idx] = val

    def get_color(self):
        current_label = self.label_cmbx.currentText()
        color = QColorDialog.getColor(QColor('red'), self,
                                      f'Choose color for {current_label}')
        if color.isValid():
            self.main.annot_ctrl.annot_colors[current_label] = color


class RawPlot(PlotItem):
    def __init__(self, main):
        self.main = main
        self.axis_items = {'bottom': TimeAxis(main),
                           'left': ChannelAxis(main)}
        super().__init__(viewBox=RawViewBox(main), axisItems=self.axis_items)

        self.lines = list()

        # Additional GraphicsItems
        self.vline = None
        self.annot_mode_hint = None

        # Pointers for continous scrolling
        self._hscroll_dir = 1
        self._vscroll_dir = 1

        # Hide AutoRange-Button
        self.hideButtons()

        # Configure XY-Range
        self.xmax = main.times[-1]
        self.ymax = main.data.shape[0] + 1  # Add one empty line as padding at top and bottom
        self.setXRange(0, main.duration, padding=0)
        self.setYRange(0, main.nchan + 1, padding=0)
        self.setLimits(xMin=0, xMax=self.xmax,
                       yMin=0, yMax=self.ymax)
        self.setLabel('bottom', 'Time', 's')

        # Add lines
        for ch_idx, (ch_data, ch_name) in enumerate(zip(self.main.data[:main.nchan],
                                                        self.main.raw.ch_names[:main.nchan])):
            self.add_line(ch_idx, ch_data, ch_name)

        self.sigXRangeChanged.connect(self.xrange_changed)
        self.sigYRangeChanged.connect(self.yrange_changed)

    def add_line(self, ch_idx, ch_data, ch_name):
        ypos = ch_idx + 1
        item = RawCurveItem(data=ch_data, times=self.main.times, ch_name=ch_name, ypos=ypos,
                            sfreq=self.main.raw.info['sfreq'], ds=self.main.ds,
                            ds_method=self.main.ds_method, ds_chunk_size=self.main.ds_chunk_size,
                            isbad=ch_name in self.main.raw.info['bads'])
        # Add Item early to have access to viewBox
        self.addItem(item)
        self.lines.append(item)

        item.sigClicked.connect(self.bad_changed)
        item.xrange_changed(self.getViewBox().viewRange()[0])

        if self.main.enable_cache:
            item.setCacheMode(QGraphicsItem.DeviceCoordinateCache)

    def remove_line(self, line):
        self.removeItem(line)
        self.lines.remove(line)

    def addrm_bad_channel(self, line, add=True):
        if add and line.ch_name not in self.main.raw.info['bads']:
            self.main.raw.info['bads'].append(line.ch_name)
            line.isbad = True
            print(f'{line.ch_name} added to bad channels!')
        elif line.ch_name in self.main.raw.info['bads']:
            self.main.raw.info['bads'].remove(line.ch_name)
            line.isbad = False
            print(f'{line.ch_name} removed from bad channels!')

        # Update line color
        line.update_bad_color()

        # Update Channel-Axis
        self.axes['left']['item'].picture = None
        self.axes['left']['item'].update()

    def bad_changed(self, line, ev):
        self.addrm_bad_channel(line, add=line.isbad)

    def xrange_changed(self, _, xrange):
        for line in self.lines:
            line.xrange_changed(xrange)

        if self.main.show_annotations:
            self.main.annot_ctrl.update_range(*xrange)

    def redraw_lines(self):
        self.xrange_changed(None, self.getViewBox().viewRange()[0])

    def yrange_changed(self, _, yrange):
        new_ypos = list(range(round(yrange[0]) + 1, round(yrange[1])))
        # Remove lines outside of view-range
        remove_lines = [li for li in self.lines if li.ypos not in new_ypos]
        for rm_line in remove_lines:
            self.remove_line(rm_line)
        # Add new lines
        add_idxs = [p - 1 for p in new_ypos if p not in [li.ypos for li in self.lines]]
        for aidx in add_idxs:
            ch_name = self.main.raw.ch_names[aidx]
            self.add_line(aidx, self.main.data[aidx], ch_name)

    def hscroll(self, step):
        # Get current range and add step to it
        xmin, xmax = [i + step for i in self.vb.viewRange()[0]]

        if xmin < 0:
            xmin = 0
            xmax = xmin + self.main.duration
        elif xmax > self.xmax:
            xmax = self.xmax
            xmin = xmax - self.main.duration

        self.setXRange(xmin, xmax, padding=0)

    def infini_hscroll(self, step, parent):
        if parent.n_bm % (int(self.xmax / step) - self.main.duration) == 0:
            self._hscroll_dir *= -1
        step *= self._hscroll_dir
        self.hscroll(step)

    def vscroll(self, step):
        # Get current range and add step to it
        ymin, ymax = [i + step for i in self.vb.viewRange()[1]]

        if ymin < 0:
            ymin = 0
            ymax = self.main.nchan + 1
        elif ymax > self.ymax:
            ymax = self.ymax
            ymin = ymax - self.main.nchan - 1

        self.setYRange(ymin, ymax, padding=0)

    def infini_vscroll(self, step, parent):
        if parent.n_bm % (int(self.ymax / step) - self.main.nchan) == 0:
            self._vscroll_dir *= -1
        step *= self._vscroll_dir
        self.vscroll(step)

    def change_duration(self, step):
        xmin, xmax = self.vb.viewRange()[0]
        newxmax = xmax + step
        newxmin = xmin - step
        if 0 < newxmax < self.xmax:
            xmax = newxmax
        elif 0 < newxmin < self.xmax:
            xmin = newxmin
        else:
            return

        self.main.duration += step
        self.setXRange(xmin, xmax, padding=0)

    # Todo: Make failsafe at boundaries
    def change_nchan(self, step):
        ymin, ymax = self.vb.viewRange()[1]
        newymax = ymax + step
        newymin = ymin - step
        if 2 < newymax < self.ymax:
            ymax = newymax
        elif 0 < newymin < self.ymax:
            ymin = newymin
        elif newymax > self.ymax:
            ymax = self.ymax
        elif newymin < 1:
            ymin = 1

        self.main.nchan += step
        self.setYRange(ymin, ymax, padding=0)

    def remove_vline(self):
        if self.vline:
            self.removeItem(self.vline)

    def add_vline(self, pos):
        # Remove vline if already shown
        self.remove_vline()

        self.vline = VLine(pos, bounds=(0, self.xmax))
        self.addItem(self.vline)

    def toggle_annot_hint(self, annotation_mode):
        if annotation_mode:
            self.annot_mode_hint = TextItem('Annotation-Mode', color='r', anchor=(0, 0))
            self.annot_mode_hint.setPos(0, 0)
            self.annot_mode_hint.setFont(QFont('AnyStyle', 20, QFont.Bold))
            self.addItem(self.annot_mode_hint)
        elif self.annot_mode_hint:
            self.removeItem(self.annot_mode_hint)
            self.annot_mode_hint = None

    def keyPressEvent(self, event):
        # Let main handle the keypress
        event.ignore()


class PyQtGraphPtyp(QMainWindow):
    def __init__(self, raw, data, times, duration=20,
                 nchan=30, ds='auto', ds_method='peak', ds_chunk_size=None,
                 enable_cache=False, antialiasing=False, use_opengl=False,
                 show_annotations=True):
        """
        PyQtGraph-Prototype as a new backend for raw.plot() from MNE-Python.

        Parameters
        ----------
        raw : mne.io.Raw
            The Raw-object.
        data : np.ndarray
            Scaled data in an array.
        times : np.ndarray
            Times in an array.
        duration : int
            The time-window to display in seconds.
        nchan : int
            The number of channels to display in the window simultaneously.
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
        enable_cache : bool
            Enable DeviceCoordinateCaching for RawCurveItems.
        antialiasing : bool
            Enable Antialiasing.
        use_opengl : bool
            Use OpenGL (seems to just work on Linux for now).
        show_annotations :
            Wether to show annotations (may impact performance in benchmarks).
        """
        super().__init__()

        # Initialize Attributes
        self.raw = raw
        self.data = data
        # Invert data for display from the top (invertedY)
        self.data *= -1
        self.times = times
        self.annotation_mode = False

        self.duration = duration
        self.nchan = nchan
        self.ds = ds
        self.ds_method = ds_method
        self.ds_chunk_size = ds_chunk_size
        self.enable_cache = enable_cache
        self.show_annotations = show_annotations

        self.clock_ticks = False

        # Create centralWidget and layout
        self.setCentralWidget(QWidget())
        layout = QGridLayout()

        # Initialize Line-Plot
        self.view = GraphicsView(background='w')
        self.plt = RawPlot(self)
        self.plt.sigXRangeChanged.connect(self.xrange_changed)
        self.plt.sigYRangeChanged.connect(self.yrange_changed)
        self.view.setCentralItem(self.plt)
        self.view.setAntialiasing(antialiasing)
        self.view.useOpenGL(use_opengl)
        layout.addWidget(self.view, 0, 0)

        # Initialize Scroll-Bars
        self.time_bar = TimeScrollBar(self)
        layout.addWidget(self.time_bar, 1, 0)
        self.channel_bar = ChannelScrollBar(self)
        layout.addWidget(self.channel_bar, 0, 1)
        self.centralWidget().setLayout(layout)

        # Initialize annotation-controller
        self.annot_ctrl = AnnotationController(self)
        self.annot_ctrl.update_range(0, self.duration)
        self.annot_ctrl.change_mode(self.annotation_mode)

        # Initialize Annotation-Dock
        self.annot_dock = AnnotationDock(self)
        self.addDockWidget(QtCore.Qt.TopDockWidgetArea, self.annot_dock)
        self.annot_dock.setVisible(False)

        # Initialize Toolbar
        self.toolbar = self.addToolBar('Tools')

        adecr_time = QAction('-Time', parent=self)
        adecr_time.triggered.connect(partial(self.plt.change_duration, -1))
        self.toolbar.addAction(adecr_time)

        aincr_time = QAction('+Time', parent=self)
        aincr_time.triggered.connect(partial(self.plt.change_duration, 1))
        self.toolbar.addAction(aincr_time)

        adecr_nchan = QAction('-Channels', parent=self)
        adecr_nchan.triggered.connect(partial(self.plt.change_nchan, -1))
        self.toolbar.addAction(adecr_nchan)

        aincr_nchan = QAction('+Channels', parent=self)
        aincr_nchan.triggered.connect(partial(self.plt.change_nchan, 1))
        self.toolbar.addAction(aincr_nchan)

        ahelp = QAction('Help', parent=self)
        ahelp.triggered.connect(partial(HelpDialog, self))
        self.toolbar.addAction(ahelp)

        # Initialize Keyboard-Shortcuts
        is_mac = platform.system() == 'Darwin'
        dur_keys = ('fn + ←', 'fn + →') if is_mac else ('Home', 'End')
        ch_keys = ('fn + ↑', 'fn + ↓') if is_mac else ('Page up', 'Page down')
        self.keyboard_shortcuts = [
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

    def xrange_changed(self, _, xrange):
        # Mark change as external
        self.time_bar.external_change = True
        self.time_bar.setValue(xrange[0])
        self.time_bar.external_change = False
        self.time_bar.update_duration()

    def yrange_changed(self, _, yrange):
        # Mark change as external
        self.channel_bar.external_change = True
        self.channel_bar.setValue(yrange[0])
        self.channel_bar.external_change = False
        self.channel_bar.update_nchan()

    def toggle_annot_mode(self):
        self.annot_dock.setVisible(self.annotation_mode)
        self.annot_ctrl.change_mode(self.annotation_mode)
        self.plt.toggle_annot_hint(self.annotation_mode)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Left:
            if event.modifiers() == QtCore.Qt.ControlModifier:
                self.plt.hscroll(-1)
            else:
                self.plt.hscroll(-self.duration / 2)
        elif event.key() == QtCore.Qt.Key_Right:
            if event.modifiers() == QtCore.Qt.ControlModifier:
                self.plt.hscroll(1)
            else:
                self.plt.hscroll(self.duration / 2)
        elif event.key() == QtCore.Qt.Key_Up:
            if event.modifiers() == QtCore.Qt.ControlModifier:
                self.plt.vscroll(-1)
            else:
                self.plt.vscroll(int(-self.nchan / 2))
        elif event.key() == QtCore.Qt.Key_Down:
            if event.modifiers() == QtCore.Qt.ControlModifier:
                self.plt.vscroll(1)
            else:
                self.plt.vscroll(int(self.nchan / 2))
        elif event.key() == QtCore.Qt.Key_Home:
            if event.modifiers() == QtCore.Qt.ControlModifier:
                self.plt.change_duration(-1)
            else:
                self.plt.change_duration(-self.duration / 4)
        elif event.key() == QtCore.Qt.Key_End:
            if event.modifiers() == QtCore.Qt.ControlModifier:
                self.plt.change_duration(1)
            else:
                self.plt.change_duration(self.duration / 4)
        elif event.key() == QtCore.Qt.Key_PageDown:
            if event.modifiers() == QtCore.Qt.ControlModifier:
                self.plt.change_nchan(-1)
            else:
                self.plt.change_nchan(int(-self.nchan / 4))
        elif event.key() == QtCore.Qt.Key_PageUp:
            if event.modifiers() == QtCore.Qt.ControlModifier:
                self.plt.change_nchan(1)
            else:
                self.plt.change_nchan(int(self.nchan / 4))
        elif event.key() == QtCore.Qt.Key_A:
            self.annotation_mode = not self.annotation_mode
            self.toggle_annot_mode()
        elif event.key() == QtCore.Qt.Key_T:
            self.clock_ticks = not self.clock_ticks
            self.plt.axis_items['bottom'].refresh()
