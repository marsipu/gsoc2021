import datetime
import platform
from functools import partial
from itertools import cycle

import numpy as np
from PyQt5.QtCore import QEvent
from PyQt5.QtGui import QColor, QFont, QIcon, QPixmap, QTransform
from PyQt5.QtWidgets import (QAction, QColorDialog, QComboBox, QDialog, QDockWidget,
                             QDoubleSpinBox, QFormLayout, QGraphicsItem, QGridLayout,
                             QHBoxLayout, QInputDialog, QLabel, QMainWindow,
                             QMessageBox, QPushButton, QScrollBar, QSizePolicy, QWidget)
from mne.viz.utils import _get_color_list
from pyqtgraph import (AxisItem, GraphicsView, InfLineLabel, InfiniteLine, LinearRegionItem,
                       PlotCurveItem, PlotItem, TextItem, ViewBox, functions,
                       mkBrush, mkPen)
from pyqtgraph.Qt import QtCore


class RawCurveItem(PlotCurveItem):
    def __init__(self, data, times, ch_name, ch_type, color, ypos, sfreq,
                 ds, ds_method, ds_chunk_size, enable_ds_cache, isbad):
        super().__init__(clickable=True)
        self._data = data
        self._times = times
        self.ch_name = ch_name
        self.ch_type = ch_type
        self.color = color
        self.ypos = ypos
        self.sfreq = sfreq
        self.ds = ds
        self.ds_method = ds_method
        self.ds_chunk_size = ds_chunk_size
        self.enable_ds_cache = enable_ds_cache
        self.isbad = isbad
        self.update_bad_color()

        self.ds_cache = dict()

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
            self.setPen(self.color)

    def get_ds_cache(self, xmin, xmax):
        if self.ds in self.ds_cache:
            x, y = self.ds_cache[self.ds]
        else:
            x, y = self.apply_ds(self.times, self.data)
            self.ds_cache[self.ds] = (x, y)

        min_ix = np.argmin(abs(x - xmin))
        max_ix = np.argmin(abs(x - xmax))

        x = x[min_ix:max_ix]
        y = y[min_ix:max_ix]

        return x, y

    def apply_ds(self, x, y):
        if self.ds_method == 'subsample':
            x = x[::self.ds]
            y = y[::self.ds]

        elif self.ds_method == 'mean':
            n = len(x) // self.ds
            stx = self.ds // 2  # start of x-values; try to select a somewhat centered point
            x = x[stx:stx + n * self.ds:self.ds]
            y = y[:n * self.ds].reshape(n, self.ds).mean(axis=1)

        elif self.ds_method == 'peak':
            n = len(x) // self.ds
            stx = self.ds // 2  # start of x-values; try to select a somewhat centered point

            x1 = np.empty((n, 2))
            x1[:] = x[stx:stx + n * self.ds:self.ds, np.newaxis]
            x = x1.reshape(n * 2)

            y1 = np.empty((n, 2))
            y2 = y[:n * self.ds].reshape((n, self.ds))
            y1[:, 0] = y2.max(axis=1)
            y1[:, 1] = y2.min(axis=1)
            y = y1.reshape(n * 2)

        return x, y

    def range_changed(self, xmin, xmax):
        start = max(0, int(xmin * self.sfreq))
        stop = min(len(self.data), int(xmax * self.sfreq + 1))
        visible_x = self.times[start:stop]
        visible_y = self.data[start:stop]

        if self.ds not in [1, None]:
            if self.enable_ds_cache:
                x, y = self.get_ds_cache(xmin, xmax)

            elif self.ds_chunk_size:
                chunkSize = (self.ds_chunk_size // self.ds) * self.ds
                sourcePtr = 0
                x = np.empty(0, dtype=self.times.dtype)
                y = np.empty(0, dtype=self.data.dtype)
                data_len = len(visible_x)
                while sourcePtr < data_len - 1:
                    xchunk = visible_x[sourcePtr:min(stop, sourcePtr + chunkSize)]
                    ychunk = visible_y[sourcePtr:min(stop, sourcePtr + chunkSize)]
                    sourcePtr += len(xchunk)

                    xchunk, ychunk = self.apply_ds(xchunk, ychunk)

                    x = np.append(x, xchunk)
                    y = np.append(y, ychunk)

            else:
                x, y = self.apply_ds(visible_x, visible_y)

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
        # Get channel-name from position of channel-description
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
        self.step_factor = None

        self.setMinimum(0)
        self.setSingleStep(1)
        self.setPageStep(self.main.tsteps_per_window)
        self.update_duration()
        self.setFocusPolicy(QtCore.Qt.WheelFocus)
        # Because valueChanged is needed (captures every input to scrollbar,
        # not just sliderMoved), there has to be made a differentiation
        # between internal and external changes.
        self.external_change = False
        self.valueChanged.connect(self.time_changed)

    def time_changed(self, value):
        if not self.external_change:
            value /= self.step_factor
            self.main.plt.setXRange(value, value + self.main.duration, padding=0)

    def update_value_external(self, _, xrange):
        # Mark change as external to avoid setting XRange again in time_changed
        self.external_change = True
        self.setValue(xrange[0] * self.step_factor)
        self.external_change = False
        self.update_duration()

    def update_duration(self):
        new_step_factor = self.main.tsteps_per_window / self.main.duration
        if new_step_factor != self.step_factor:
            self.step_factor = new_step_factor
            new_maximum = int((self.main.plt.xmax - self.main.duration) * self.step_factor)
            self.setMaximum(new_maximum)

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

    def update_value_external(self, _, yrange):
        # Mark change as external to avoid setting YRange again in channel_changed
        self.external_change = True
        self.setValue(yrange[0])
        self.external_change = False
        self.update_nchan()

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
                if self.main.annot_ctrl.current_description:
                    description = self.main.annot_ctrl.current_description
                    if event.isStart():
                        self._drag_start = self.mapSceneToView(event.scenePos()).x()
                        self._drag_region = AnnotationRegion(description=description,
                                                             values=(self._drag_start, self._drag_start),
                                                             color=self.main.annot_ctrl.get_color(description),
                                                             time_decimals=self.main.annot_ctrl.time_decimals)
                        self.main.plt.addItem(self._drag_region)
                        self.main.plt.addItem(self._drag_region.label_item)
                    elif event.isFinish():
                        drag_stop = self.mapSceneToView(event.scenePos()).x()
                        self._drag_region.setRegion((self._drag_start, drag_stop))
                        onset = min(self._drag_start, drag_stop)
                        duration = abs(self._drag_start - drag_stop)
                        self.main.annot_ctrl.add_annotation(onset, duration, self._drag_region)
                    else:
                        self._drag_region.setRegion((self._drag_start,
                                                     self.mapSceneToView(event.scenePos()).x()))
                elif event.isFinish():
                    QMessageBox.warning(self.main, 'No description!', 'No description is given, add one!')
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
            self.main.plt.hscroll(scroll * 10)
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
    regionChangeFinished = QtCore.Signal(object)
    gotSelected = QtCore.Signal(object)
    removeRequested = QtCore.Signal(object)

    def __init__(self, description, values, color, time_decimals):

        super().__init__(values=values, orientation='vertical', movable=True, swapMode='sort')

        self.sigRegionChangeFinished.connect(self._region_changed)

        self.description = description
        self.time_decimals = time_decimals
        self.old_onset = values[0]
        self.selected = False
        self.setToolTip(description)

        self.label_item = TextItem(text=description, anchor=(0.5, 0.5))
        self.label_item.setFont(QFont('AnyStyle', 10, QFont.Bold))
        self.sigRegionChanged.connect(self.change_label_pos)

        self.update_color(color)

    def _region_changed(self):
        self.regionChangeFinished.emit(self)
        self.old_onset = self.getRegion()[0]

    def getRegion(self):
        rgn = tuple([round(r, self.time_decimals) for r in super().getRegion()])
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
        vb = self.getViewBox()
        if vb and self.label_item in vb.addedItems:
            vb.removeItem(self.label_item)

    def select(self, selected):
        self.selected = selected
        if selected:
            self.gotSelected.emit(self)
        self.update()

    def mouseClickEvent(self, event):
        event.accept()
        if event.button() == QtCore.Qt.LeftButton and self.movable:
            self.select(True)
        elif event.button() == QtCore.Qt.RightButton and self.movable:
            self.remove()

    def change_label_pos(self):
        rgn = self.getRegion()
        vb = self.getViewBox()
        if vb:
            ymax = vb.viewRange()[1][1]
            self.label_item.setPos(sum(rgn) / 2, ymax - 0.25)


class AnnotationController:
    """ Controller for all Annotation-Regions."""

    def __init__(self, main):
        self.main = main
        self.first_time = main.raw.first_time
        self.time_decimals = int(np.ceil(-np.log10(1 / self.main.raw.info['sfreq'])))
        self.annotations = main.raw.annotations
        colors, self.red = _get_color_list(annotations=True)
        self.color_cycle = cycle(colors)
        self.descriptions = list(set(main.raw.annotations.description))
        if len(self.descriptions) > 0:
            self.current_description = self.descriptions[0]
        else:
            self.current_description = None
        self.annot_color_mapping = dict()
        self.selected_region = None
        self.regions = list()

        for annot in self.annotations:
            onset = round(annot['onset'] - self.first_time, self.time_decimals)
            duration = round(annot['duration'], self.time_decimals)
            description = annot['description']
            self.add_region(onset, duration, description)

    def get_color(self, description):
        # As in matplotlib-backend
        if any([b in description for b in ['bad', 'BAD', 'Bad']]):
            color = self.red
        elif description in self.annot_color_mapping:
            color = self.annot_color_mapping[description]
        else:
            color = next(self.color_cycle)
        self.annot_color_mapping[description] = color
        return color

    def update_colors(self):
        update_regions = [r for r in self.regions
                          if r.description == self.current_description]
        for u_region in update_regions:
            u_region.update_color(self.get_color(self.current_description))

    def add_region(self, onset, duration, description, region=None):
        color = self.get_color(description)
        if not region:
            region = AnnotationRegion(description=description,
                                      values=(onset, onset + duration),
                                      color=color,
                                      time_decimals=self.time_decimals)
        region.regionChangeFinished.connect(self.region_changed)
        region.gotSelected.connect(self.region_selected)
        region.removeRequested.connect(self.remove_region)
        self.main.plt.getViewBox().sigYRangeChanged.connect(region.change_label_pos)
        self.regions.append(region)

        xrange = self.main.plt.getViewBox().viewRange()[0]
        if xrange[0] < onset < xrange[1] \
                and region not in self.main.plt.items:
            self.main.plt.addItem(region)
            # Found no better way yet to initialize the region-labels
            self.main.plt.addItem(region.label_item)
            region.change_label_pos()

    def remove_region(self, region):
        # Remove from shown regions
        if region.label_item in self.main.plt.getViewBox().addedItems:
            self.main.plt.getViewBox().removeItem(region.label_item)
        if region in self.main.plt.items:
            self.main.plt.removeItem(region)

        # Remove from all regions
        if region in self.regions:
            self.regions.remove(region)

        # Remove from annotations
        idx = self._get_onset_idx(region.getRegion()[0])
        self.annotations.delete(idx)

    def region_selected(self, region):
        old_region = self.selected_region
        # Remove selected-status from old region
        if old_region:
            old_region.selected = False
            old_region.update()
        self.selected_region = region
        self.current_description = region.description
        self.main.annot_dock.update_values(region)

    def _get_onset_idx(self, onset):
        idx = np.where(np.around(self.annotations.onset - self.first_time,
                                 self.time_decimals) == onset)
        return idx

    def region_changed(self, region):
        rgn = region.getRegion()
        region.select(True)
        idx = self._get_onset_idx(region.old_onset)

        # Update Spinboxes of Annot-Dock
        self.main.annot_dock.update_values(region)

        # Change annotations
        self.annotations.onset[idx] = round(rgn[0] + self.first_time, self.time_decimals)
        self.annotations.duration[idx] = rgn[1] - rgn[0]

    def update_range(self, xmin, xmax):
        inside_onsets = self.annotations.onset[np.where((self.annotations.onset + self.annotations.duration
                                                         >= xmin + self.first_time) &
                                                        (self.annotations.onset < xmax + self.first_time))[0]]
        inside_onsets = [round(io - self.first_time, self.time_decimals) for io in inside_onsets]
        rm_regions = [r for r in self.regions
                      if r.getRegion()[0] not in inside_onsets
                      and r in self.main.plt.items]
        for rm_region in rm_regions:
            self.main.plt.removeItem(rm_region)
            self.main.plt.removeItem(rm_region.label_item)

        add_regions = [r for r in self.regions
                       if r.getRegion()[0] in inside_onsets
                       and r not in self.main.plt.items]
        for add_region in add_regions:
            self.main.plt.addItem(add_region)
            self.main.plt.addItem(add_region.label_item)
            add_region.change_label_pos()

    def add_annotation(self, onset, duration, region=None):
        """Add annotation to Annotations (onset is here the onset
        in the plot which is then adjusted with first_time)"""
        self.annotations.append(onset + self.first_time, duration, self.current_description)
        self.add_region(onset, duration, self.current_description, region)
        self.update_range(*self.main.plt.viewRange()[0])

    def change_mode(self, annotation_on):
        for region in self.regions:
            region.setMovable(annotation_on)
        if not annotation_on:
            if self.selected_region:
                self.selected_region.select(False)
                self.selected_region = None


class AnnotationDock(QDockWidget):
    def __init__(self, main):
        super().__init__('Annotations')
        self.main = main
        self.init_ui()

    def init_ui(self):
        widget = QWidget()
        layout = QHBoxLayout()
        layout.setAlignment(QtCore.Qt.AlignLeft)

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
        self.start_bx.setDecimals(self.main.annot_ctrl.time_decimals)
        self.start_bx.editingFinished.connect(self.start_changed)
        layout.addWidget(self.start_bx)

        layout.addWidget(QLabel('Stop:'))
        self.stop_bx = QDoubleSpinBox()
        self.stop_bx.setDecimals(self.main.annot_ctrl.time_decimals)
        self.stop_bx.editingFinished.connect(self.stop_changed)
        layout.addWidget(self.stop_bx)

        widget.setLayout(layout)
        self.setWidget(widget)

    def _add_description_to_cmbx(self, description):
        color_pixmap = QPixmap(25, 25)
        color = QColor(self.main.annot_ctrl.get_color(description))
        color.setAlpha(75)
        color_pixmap.fill(color)
        color_icon = QIcon(color_pixmap)
        self.description_cmbx.addItem(color_icon, description)

    def add_description(self):
        new_description, ok = QInputDialog.getText(self, 'Set the name for the new description!', 'New description: ')
        if ok and new_description and new_description not in self.main.annot_ctrl.descriptions:
            self.main.annot_ctrl.descriptions.append(new_description)
            self._add_description_to_cmbx(new_description)
        self.main.annot_ctrl.current_description = self.description_cmbx.currentText()

    def edit_description(self):
        current_description = self.description_cmbx.currentText()
        changed_description, ok = QInputDialog.getText(self, 'Set then name for the changed description!',
                                                       f'Change "{current_description}" to:')
        if ok and changed_description:
            edit_regions = [r for r in self.main.annot_ctrl.regions
                            if r.description == current_description]
            for ed_region in edit_regions:
                idx = self.main.annot_ctrl._get_onset_idx(ed_region.getRegion()[0])
                self.main.annot_ctrl.annotations.description[idx] = changed_description
                ed_region.update_description(changed_description)
            self.main.annot_ctrl.descriptions = list(set([changed_description if i == current_description
                                                          else i for i in self.main.annot_ctrl.descriptions]))
            self.main.annot_ctrl.current_description = changed_description
            self.main.annot_ctrl.annot_color_mapping[changed_description] = \
                self.main.annot_ctrl.annot_color_mapping.pop(current_description)
            self.update_description_cmbx()
            self.main.annot_ctrl.update_colors()

    def remove_description(self):
        rm_description = self.description_cmbx.currentText()
        existing_annot = list(self.main.raw.annotations.description).count(rm_description)
        if existing_annot > 0:
            answer = QMessageBox.question(self, f'Remove annotations with {rm_description}?',
                                          f'There exist {existing_annot} annotations with "{rm_description}".\n'
                                          f'Do you really want to remove them?')
            if answer == QMessageBox.Yes:
                rm_idxs = np.where(self.main.raw.annotations.description == rm_description)
                for idx in rm_idxs:
                    self.main.raw.annotations.delete(idx)
                for rm_region in [r for r in self.main.annot_ctrl.regions
                                  if r.description == rm_description]:
                    rm_region.remove()

        # Remove from descriptions
        self.main.annot_ctrl.descriptions.remove(rm_description)
        self.update_description_cmbx()

        # Remove from color-mapping
        if rm_description in self.main.annot_ctrl.annot_color_mapping:
            self.main.annot_ctrl.annot_color_mapping.pop(rm_description)

        # Set first description in Combo-Box to current description
        self.description_cmbx.setCurrentIndex(0)
        self.main.annot_ctrl.current_description = self.description_cmbx.currentText()

    def description_changed(self, descr_idx):
        new_descr = self.description_cmbx.itemText(descr_idx)
        self.main.annot_ctrl.current_description = new_descr

    def start_changed(self):
        start = self.start_bx.value()
        sel_region = self.main.annot_ctrl.selected_region
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
        sel_region = self.main.annot_ctrl.selected_region
        if sel_region:
            start = sel_region.getRegion()[0]
            if start < stop:
                sel_region.setRegion((start, stop))
            else:
                QMessageBox.warning(self, 'Invalid value!',
                                    'Stop can\'t be smaller or equal to Start!')
                self.stop_bx.setValue(sel_region.getRegion()[1])

    def set_color(self):
        current_description = self.description_cmbx.currentText()
        if current_description in self.main.annot_ctrl.annot_color_mapping:
            current_color = self.main.annot_ctrl.annot_color_mapping[current_description]
        else:
            current_color = None
        color = QColorDialog.getColor(QColor(current_color), self,
                                      f'Choose color for {current_description}!')
        if color.isValid():
            self.main.annot_ctrl.annot_color_mapping[current_description] = color
            self.update_description_cmbx()
            self.main.annot_ctrl.update_colors()

    def update_values(self, region):
        rgn = region.getRegion()
        self.description_cmbx.setCurrentText(region.description)
        self.start_bx.setValue(rgn[0])
        self.stop_bx.setValue(rgn[1])

    def update_description_cmbx(self):
        self.description_cmbx.clear()
        for description in self.main.annot_ctrl.descriptions:
            self._add_description_to_cmbx(description)
        self.description_cmbx.setCurrentText(self.main.annot_ctrl.current_description)

    def reset(self):
        if self.description_cmbx.count() > 0:
            self.description_cmbx.setCurrentIndex(0)
            self.main.annot_ctrl.current_description = self.description_cmbx.currentText()
        self.start_bx.setValue(0)
        self.stop_bx.setValue(0)


class RawPlot(PlotItem):
    def __init__(self, main):
        self.main = main
        self.axis_items = {'bottom': TimeAxis(main),
                           'left': ChannelAxis(main)}
        super().__init__(viewBox=RawViewBox(main), axisItems=self.axis_items)

        self.lines = list()
        self.scale_factor = 1

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
        for ch_idx, (ch_data, ch_name, ch_type) in enumerate(zip(self.main.data[:main.nchan],
                                                                 self.main.raw.ch_names[:main.nchan],
                                                                 self.main.ch_types)):
            self.add_line(ch_idx, ch_data, ch_name, ch_type)

        self.sigXRangeChanged.connect(self.xrange_changed)
        self.sigYRangeChanged.connect(self.yrange_changed)

    def add_line(self, ch_idx, ch_data, ch_name, ch_type):
        ypos = ch_idx + 1
        color = self.main.ch_colors[ch_type]
        ds = self._get_downsampling()
        item = RawCurveItem(data=ch_data, times=self.main.times, ch_name=ch_name,
                            ch_type=ch_type, color=color, ypos=ypos,
                            sfreq=self.main.raw.info['sfreq'], ds=ds,
                            ds_method=self.main.ds_method, ds_chunk_size=self.main.ds_chunk_size,
                            enable_ds_cache=self.main.enable_ds_cache,
                            isbad=ch_name in self.main.raw.info['bads'])

        # Apply scaling
        transform = self._get_scale_transform()
        item.setTransform(transform)

        # Add Item early to have access to viewBox
        self.addItem(item)
        self.lines.append(item)

        item.sigClicked.connect(self.bad_changed)
        item.range_changed(*self.getViewBox().viewRange()[0])

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

    def _get_downsampling(self):
        # Auto-Downsampling from pyqtgraph
        ds = self.main.ds if isinstance(self.main.ds, int) else 1
        if self.main.ds == 'auto':
            view = self.getViewBox()
            if view is not None:
                view_range = view.viewRect()
            else:
                view_range = None
            if view_range is not None and len(self.main.times) > 1:
                dx = float(self.main.times[-1] - self.main.times[0]) / (len(self.main.times) - 1)
                if dx != 0.0:
                    x0 = view_range.left() / dx
                    x1 = view_range.right() / dx
                    width = self.getViewBox().width()
                    if width != 0.0:
                        # Auto-Downsampling with 3 samples per pixel
                        ds = int(max(1, (x1 - x0) / (width * 5)))

        return ds

    def xrange_changed(self, _, xrange):
        ds = self._get_downsampling()

        for line in self.lines:
            line.ds = ds
            line.range_changed(*xrange)

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
            ch_type = self.main.ch_types[aidx]
            self.add_line(aidx, self.main.data[aidx], ch_name, ch_type)

    def _get_scale_transform(self):
        transform = QTransform()
        transform.scale(1, self.scale_factor)

        return transform

    def scale_all(self, step):
        self.scale_factor *= 2**step
        transform = self._get_scale_transform()

        for line in self.lines:
            line.setTransform(transform)

    def hscroll(self, step):
        rel_step = step * self.main.duration / self.main.tsteps_per_window
        # Get current range and add step to it
        xmin, xmax = [i + rel_step for i in self.vb.viewRange()[0]]

        if xmin < 0:
            xmin = 0
            xmax = xmin + self.main.duration
        elif xmax > self.xmax:
            xmax = self.xmax
            xmin = xmax - self.main.duration

        self.setXRange(xmin, xmax, padding=0)

    def infini_hscroll(self, step):
        vr = self.getViewBox().viewRange()
        rel_step = self.main.duration * step / self.main.tsteps_per_window
        if vr[0][1] + rel_step > self.xmax or vr[0][0] - rel_step < 0:
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

    def infini_vscroll(self, step):
        vr = self.getViewBox().viewRange()
        if vr[1][1] + step > self.ymax or vr[1][0] - step < 0:
            self._vscroll_dir *= -1
        step *= self._vscroll_dir
        self.vscroll(step)

    def change_duration(self, step):
        rel_step = (self.main.duration * step) / (self.main.tsteps_per_window * 2)
        xmin, xmax = self.vb.viewRange()[0]
        xmax += rel_step
        xmin -= rel_step

        if xmax > self.xmax:
            xmax = self.xmax

        if xmin < 0:
            xmin = 0

        self.main.duration = xmax - xmin

        self.setXRange(xmin, xmax, padding=0)

    def change_nchan(self, step):
        ymin, ymax = self.vb.viewRange()[1]
        ymax += step
        if ymax > self.ymax:
            ymax = self.ymax
            ymin -= step

        if ymin < 0:
            ymin = 0

        if ymax - ymin <= 2:
            ymax = ymin + 2

        self.main.nchan = ymax - ymin - 1

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


class BrowserView(GraphicsView):
    def __init__(self, main, plot, **kwargs):
        super().__init__(**kwargs)
        self.main = main
        self.setCentralItem(plot)
        self.setAntialiasing(self.main.antialiasing)
        self.viewport().setAttribute(QtCore.Qt.WA_AcceptTouchEvents, True)

    def viewportEvent(self, event):
        if event.type() in [QEvent.TouchBegin, QEvent.TouchUpdate,
                            QEvent.TouchEnd]:
            if event.touchPoints() == 2:
                pass
        return super().viewportEvent(event)


class PyQtGraphPtyp(QMainWindow):
    def __init__(self, raw, data, times, ch_types, duration=20,
                 nchan=30, ds='auto', ds_method='peak', ds_chunk_size=None,
                 antialiasing=False, use_opengl=False,
                 show_annotations=True, enable_ds_cache=True,
                 tsteps_per_window=100):
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
        ch_types : np.ndarray
            The channel-types in an array.
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
        antialiasing : bool
            Enable Antialiasing.
        use_opengl : bool
            Use OpenGL (seems to just work on Linux for now).
        show_annotations : bool
            Wether to show annotations (may impact performance in benchmarks).
        enable_ds_cache : bool
            If True cache the downsampled arrays inside RawCurveItems per downsampling-factor.
        tsteps_per_window : int
            Set how many single scrolling-steps are done in time for the shown time-window.
        """
        super().__init__()

        # Initialize Attributes
        self.raw = raw
        self.data = data
        # Invert data for display from the top (invertedY)
        self.data = data * -1
        self.times = times
        self.ch_types = ch_types
        self.annotation_mode = False

        self.duration = min(duration, self.raw.n_times / self.raw.info['sfreq'])
        self.nchan = min(nchan, len(self.raw.ch_names))
        self.ds = ds
        self.ds_method = ds_method
        self.ds_chunk_size = ds_chunk_size
        self.antialiasing = antialiasing
        self.show_annotations = show_annotations
        self.enable_ds_cache = enable_ds_cache
        self.tsteps_per_window = tsteps_per_window

        self.clock_ticks = False
        self.ch_colors = dict(mag='b', grad='#3a51ad', eeg='k', eog='k', ecg='m',
                              emg='k', ref_meg='#1f2951', misc='k', stim='k',
                              resp='k', chpi='k')

        # Create centralWidget and layout
        widget = QWidget()
        layout = QGridLayout()

        # Initialize Line-Plot
        self.plt = RawPlot(self)
        self.view = BrowserView(self, self.plt, background='w',
                                useOpenGL=use_opengl)
        layout.addWidget(self.view, 0, 0)

        # Initialize Scroll-Bars
        self.time_bar = TimeScrollBar(self)
        self.plt.sigXRangeChanged.connect(self.time_bar.update_value_external)
        layout.addWidget(self.time_bar, 1, 0)

        self.channel_bar = ChannelScrollBar(self)
        self.plt.sigYRangeChanged.connect(
            self.channel_bar.update_value_external)
        layout.addWidget(self.channel_bar, 0, 1)

        widget.setLayout(layout)
        self.setCentralWidget(widget)

        if self.show_annotations:
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
        adecr_time.triggered.connect(partial(self.plt.change_duration, -self.tsteps_per_window / 10))
        self.toolbar.addAction(adecr_time)

        aincr_time = QAction('+Time', parent=self)
        aincr_time.triggered.connect(partial(self.plt.change_duration, self.tsteps_per_window / 10))
        self.toolbar.addAction(aincr_time)

        adecr_nchan = QAction('-Channels', parent=self)
        adecr_nchan.triggered.connect(partial(self.plt.change_nchan, -10))
        self.toolbar.addAction(adecr_nchan)

        aincr_nchan = QAction('+Channels', parent=self)
        aincr_nchan.triggered.connect(partial(self.plt.change_nchan, 10))
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

    def toggle_annot_mode(self):
        if self.show_annotations:
            if not self.annotation_mode:
                self.annot_dock.reset()
            self.annot_dock.setVisible(self.annotation_mode)
            self.annot_ctrl.change_mode(self.annotation_mode)
            self.plt.toggle_annot_hint(self.annotation_mode)

    def keyPressEvent(self, event):
        # On MacOs additionally KeypadModifier is set when arrow-keys are pressed.
        # On Unix GroupSwitchModifier is set when ctrl is pressed.
        # To preserve cross-platform consistency the following comparison
        # of the modifier-values is done.
        modhex = hex(int(event.modifiers()))
        lil_t = 1
        big_t = 10
        if event.key() == QtCore.Qt.Key_Left:
            if '4' in modhex:
                self.plt.hscroll(-lil_t)
            else:
                self.plt.hscroll(-big_t)
        elif event.key() == QtCore.Qt.Key_Right:
            if '4' in modhex:
                self.plt.hscroll(lil_t)
            else:
                self.plt.hscroll(big_t)
        elif event.key() == QtCore.Qt.Key_Up:
            if '4' in modhex:
                self.plt.vscroll(-1)
            else:
                self.plt.vscroll(-10)
        elif event.key() == QtCore.Qt.Key_Down:
            if '4' in modhex:
                self.plt.vscroll(1)
            else:
                self.plt.vscroll(10)
        elif event.key() == QtCore.Qt.Key_Home:
            if '4' in modhex:
                self.plt.change_duration(-lil_t)
            else:
                self.plt.change_duration(-big_t)
        elif event.key() == QtCore.Qt.Key_End:
            if '4' in modhex:
                self.plt.change_duration(lil_t)
            else:
                self.plt.change_duration(big_t)
        elif event.key() == QtCore.Qt.Key_PageDown:
            if '4' in modhex:
                self.plt.change_nchan(-1)
            else:
                self.plt.change_nchan(-10)
        elif event.key() == QtCore.Qt.Key_PageUp:
            if '4' in modhex:
                self.plt.change_nchan(1)
            else:
                self.plt.change_nchan(10)
        elif event.key() == QtCore.Qt.Key_Comma:
            self.plt.scale_all(-1)
        elif event.key() == QtCore.Qt.Key_Period:
            self.plt.scale_all(1)
        elif event.key() == QtCore.Qt.Key_A:
            self.annotation_mode = not self.annotation_mode
            self.toggle_annot_mode()
        elif event.key() == QtCore.Qt.Key_T:
            self.clock_ticks = not self.clock_ticks
            self.plt.axis_items['bottom'].refresh()
