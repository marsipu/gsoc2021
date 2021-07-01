import datetime
import platform
from collections import OrderedDict
from functools import partial

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QDialog, QFormLayout, QGraphicsItem, QGraphicsProxyWidget, QGridLayout, QLabel, QPushButton, \
    QScrollBar, \
    QSizePolicy, QVBoxLayout, \
    QWidget
from mne.viz.utils import _compute_scalings
from pyqtgraph import (AxisItem, GraphicsView, InfiniteLine, LinearRegionItem, PlotCurveItem, PlotItem, TextItem,
                       ViewBox, functions)
from pyqtgraph.Qt import QtCore


class RawCurveItem(PlotCurveItem):
    def __init__(self, data, times, ch_name, ypos, sfreq, ds=1, isbad=False):
        super().__init__(clickable=True)
        self._data = data
        self._times = times
        self.ch_name = ch_name
        self.ypos = ypos
        self.sfreq = sfreq
        self.ds = ds
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

    def set_full_data(self):
        self.setData(self.times, self.data)
        self.setPos(0, self.ypos)

    def xrange_changed(self, xrange):
        xmin, xmax = xrange
        start = max(0, int(xmin * self.sfreq))
        stop = min(len(self.data), int(xmax * self.sfreq + 1))

        visible_x = self.times[start:stop]
        visible_y = self.data[start:stop]

        # Auto-Downsampling and mean method from pyqtgraph
        ds = 1
        if self.ds == 'auto':
            view = self.getViewBox()
            if view is not None:
                view_range = view.viewRect()
            else:
                view_range = None
            if view_range is not None and len(visible_x) > 1:
                dx = float(visible_x[-1] - visible_x[0]) / (len(visible_x) - 1)
                if dx != 0.0:
                    x0 = (view_range.left() - visible_x[0]) / dx
                    x1 = (view_range.right() - visible_x[0]) / dx
                    width = self.getViewBox().width()
                    if width != 0.0:
                        # Auto-Downsampling with 5 samples per pixel
                        ds = int(max(1, int((x1 - x0) / (width * 5))))
        elif self.ds > 1:
            ds = self.ds

        if ds > 1:
            n = len(visible_x) // ds
            visible_x = visible_x[:n * ds].reshape(n, ds).mean(axis=1)
            visible_y = visible_y[:n * ds].reshape(n, ds).mean(axis=1)

        self.setData(visible_x, visible_y)
        self.setPos(0, self.ypos)
        self.resetTransform()

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
        tick_values = [(1, [self.main.lines[k][1] for k in self.main.lines.keys()])]
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
                         if k in self.main.lines}
        # Get channel-name from position of channel-label
        ypos = event.scenePos().y()
        ch_name = [chn for chn in self.ch_texts
                   if self.ch_texts[chn][0] < ypos < self.ch_texts[chn][1]]
        if len(ch_name) > 0:
            ch_name = ch_name[0]
            print(f'{ch_name} clicked!')
            self.main._addrm_bad_channel(ch_name)
        return super().mouseClickEvent(event)


class TimeScrollBar(QScrollBar):
    def __init__(self, main):
        super().__init__(Qt.Horizontal)
        self.main = main

        self.setMinimum(0)
        self.setMaximum(self.main.xmax - self.main.duration)
        self.update_duration()
        self.setSingleStep(1)
        self.setFocusPolicy(Qt.WheelFocus)
        self.valueChanged.connect(self.time_changed)

    def time_changed(self, value):
        self.main.setXRange(value, value + self.main.duration, padding=0)

    def update_duration(self):
        self.setPageStep(self.main.duration)
        self.setMaximum(self.main.xmax - self.main.duration)

    def keyPressEvent(self, event):
        # Let main handle the keypress
        event.ignore()


class ChannelScrollBar(QScrollBar):
    def __init__(self, main):
        super().__init__(Qt.Vertical)
        self.main = main

        self.setMinimum(0)
        self.setMaximum(self.main.ymax - self.main.nchan - 2)
        self.update_nchan()
        self.setSingleStep(1)
        self.setFocusPolicy(Qt.WheelFocus)
        self.valueChanged.connect(self.channel_changed)

    def channel_changed(self, value):
        new_ymin = value
        new_ymax = value + self.main.nchan + 2
        self.main.setYRange(new_ymin, new_ymax, padding=0)

    def update_nchan(self):
        self.setPageStep(self.main.nchan)
        self.setMaximum(self.main.ymax - self.main.nchan - 2)

    def keyPressEvent(self, event):
        # Let main handle the keypress
        event.ignore()


class RawViewBox(ViewBox):
    def __init__(self, main):
        super().__init__(invertY=True)
        self.main = main
        self._drag_start = None

    def mouseDragEvent(self, event, axis=None):
        event.accept()

        if event.button() == Qt.LeftButton and self.main.annotation_mode:
            if event.isStart():
                self._drag_start = self.mapSceneToView(event.scenePos()).x()
            elif event.isFinish():
                drag_stop = self.mapSceneToView(event.scenePos()).x()
                onset = min(self._drag_start, drag_stop)
                duration = abs(self._drag_start - drag_stop)
                self.main.annot_ctrl.add_annotation(onset, duration, 'Bad')
        else:
            super().mouseDragEvent(event, axis)

    def mouseClickEvent(self, event):
        # If we want the context-menu back, uncomment following line
        # super().mouseClickEvent(event)
        if event.button() == QtCore.Qt.LeftButton:
            self.main.add_vline(self.mapSceneToView(event.scenePos()).x())
        elif event.button() == QtCore.Qt.RightButton:
            self.main.remove_vline()


class VLine(InfiniteLine):
    def __init__(self, pos):
        super().__init__(pos, pen='g', hoverPen='y',
                         movable=True, label='Time: {value:.3f}',
                         labelOpts={'position': 0.95, 'fill': 'g',
                                    'color': 'b'})


class RawPlot(PlotItem):
    def __init__(self, raw, data, times, duration, nchan, ds, all_data,
                 enable_cache, show_annotations):
        self.axis_items = {'bottom': TimeAxis(self),
                           'left': ChannelAxis(self)}
        self.clock_ticks = False
        super().__init__(viewBox=RawViewBox(self), axisItems=self.axis_items)

        self.raw = raw
        self.data = data
        self.times = times

        # Invert data for display from the top (invertedY)
        self.data *= -1

        self.duration = duration
        self.nchan = nchan
        self.ds = ds
        self.all_data = all_data
        self.enable_cache = enable_cache
        self.show_annotations = show_annotations

        self.vline = None

        self.annotation_mode = False
        self.annot_label = None

        self.lines = OrderedDict()
        self._hscroll_dir = 1
        self._vscroll_dir = 1

        self.vb.disableAutoRange(ViewBox.XYAxes)
        self.hideButtons()

        self.xmax = self.times[-1]
        self.ymax = self.data.shape[0] + 2  # Add one empty line as padding at top and bottom

        self.setXRange(0, duration, padding=0)
        self.setLimits(xMin=0, xMax=self.xmax,
                       yMin=0, yMax=self.ymax)
        self.setLabel('bottom', 'Time', 's')
        self.setYRange(0, self.nchan + 2, padding=0)
        if self.all_data:
            max_idx = len(self.data)
        else:
            max_idx = self.nchan
        for ch_idx, (ch_data, ch_name) in enumerate(zip(self.data[:max_idx],
                                                        self.raw.ch_names[:max_idx])):
            self.add_line(ch_idx, ch_data, ch_name)

        # Add Annotations
        if self.show_annotations:
            self.annot_ctrl = AnnotationController(self)
            self.annot_ctrl.update_range(0, self.duration)
            self.annot_ctrl.change_mode(self.annotation_mode)

        if not self.all_data:
            self.sigXRangeChanged.connect(self.xrange_changed)
            self.sigYRangeChanged.connect(self.yrange_changed)

    def add_line(self, ch_idx, ch_data, ch_name):
        ypos = ch_idx + 1
        item = RawCurveItem(data=ch_data, times=self.times, ch_name=ch_name, ypos=ypos,
                            sfreq=self.raw.info['sfreq'], ds=self.ds,
                            isbad=ch_name in self.raw.info['bads'])
        # Add Item early to have access to viewBox
        self.addItem(item)
        self.lines[ch_name] = (item, ypos)

        if self.all_data:
            item.set_full_data()
        else:
            item.xrange_changed(self.getViewBox().viewRange()[0])
            self.nchan = len(self.lines)

        if self.enable_cache:
            item.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
        item.sigClicked.connect(self.bad_changed)

    def remove_line(self, ch_name):
        self.removeItem(self.lines[ch_name][0])
        self.lines.pop(ch_name)
        self.nchan = len(self.lines)

    def _addrm_bad_channel(self, ch_name, add=True):
        line = self.lines[ch_name][0]
        if add and ch_name not in self.raw.info['bads']:
            self.raw.info['bads'].append(ch_name)
            line.isbad = True
            print(f'{ch_name} added to bad channels!')
        elif ch_name in self.raw.info['bads']:
            self.raw.info['bads'].remove(ch_name)
            line.isbad = False
            print(f'{ch_name} removed from bad channels!')

        # Update line color
        line.update_bad_color()

        # Update Channel-Axis
        self.axes['left']['item'].picture = None
        self.axes['left']['item'].update()

    def bad_changed(self, line, ev):
        self._addrm_bad_channel(line.ch_name, add=line.isbad)

    def xrange_changed(self, _, xrange):
        for ch_name in self.lines:
            line = self.lines[ch_name][0]
            line.xrange_changed(xrange)

        if self.show_annotations:
            self.annot_ctrl.update_range(*xrange)

    def redraw_lines(self):
        self.xrange_changed(None, self.getViewBox().viewRange()[0])

    def yrange_changed(self, _, yrange):
        ymin, ymax = int(yrange[0]), int(yrange[1])
        remove_lines = [k for k in self.lines
                        if self.lines[k][1] <= ymin
                        or self.lines[k][1] >= ymax - 1]
        for ch_name in remove_lines:
            self.remove_line(ch_name)

        if len(self.lines) > 0:
            min_ch_idx = min([v[1] for v in self.lines.values()]) - 1
            ymin_ch_idx = ymin
            for idx in reversed(range(ymin_ch_idx, min_ch_idx)):
                ch_name = self.raw.ch_names[idx]
                self.add_line(idx, self.data[idx], ch_name)
                self.lines.move_to_end(ch_name, last=False)

            max_ch_idx = max([v[1] for v in self.lines.values()])
            ymax_ch_idx = ymax - 2
            for idx in range(max_ch_idx, ymax_ch_idx):
                ch_name = self.raw.ch_names[idx]
                self.add_line(idx, self.data[idx], ch_name)
                self.lines.move_to_end(ch_name, last=True)
        else:
            for idx in range(ymin, ymax):
                ch_name = self.raw.ch_names[idx]
                self.add_line(idx, self.data[idx], ch_name)
                self.lines.move_to_end(ch_name, last=True)

    def hscroll(self, step):
        # Get current range and add step to it
        xmin, xmax = [i + step for i in self.vb.viewRange()[0]]

        if xmin < 0:
            xmin = 0
            xmax = xmin + self.duration
        elif xmax > self.xmax:
            xmax = self.xmax
            xmin = xmax - self.duration

        self.setXRange(xmin, xmax, padding=0)

    def infini_hscroll(self, step, parent):
        if parent.n_bm % (int(self.xmax / step) - self.duration) == 0:
            self._hscroll_dir *= -1
        step *= self._hscroll_dir
        self.hscroll(step)

    def vscroll(self, step):
        # Get current range and add step to it
        ymin, ymax = [i + step for i in self.vb.viewRange()[1]]

        if ymin < 0:
            ymin = 0
            ymax = ymin + self.nchan + 2
        elif ymax > self.ymax:
            ymax = self.ymax
            ymin = ymax - self.nchan - 2

        self.setYRange(ymin, ymax, padding=0)

    def infini_vscroll(self, step, parent):
        if parent.n_bm % (int(self.ymax / step) - self.nchan) == 0:
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

        self.duration += step
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

        self.nchan += step
        self.setYRange(ymin, ymax, padding=0)

    def remove_vline(self):
        if self.vline:
            self.removeItem(self.vline)

    def add_vline(self, pos):
        # Remove vline if already shown
        self.remove_vline()

        self.vline = VLine(pos)
        self.addItem(self.vline)

    def keyPressEvent(self, event):
        # Let main handle the keypress
        event.ignore()

    def toggle_annot_mode(self):
        self.annot_ctrl.change_mode(self.annotation_mode)
        if self.annotation_mode:
            self.annot_label = TextItem('Annotation-Mode', color='r', anchor=(0, 0))
            self.annot_label.setPos(0, 0)
            self.annot_label.setFont(QFont('AnyStyle', 20, QFont.Bold))
            self.addItem(self.annot_label)
        elif self.annot_label:
            self.removeItem(self.annot_label)
            self.annot_label = None


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
    removeRequested = QtCore.Signal(object)

    def __init__(self, description, values):
        super().__init__(values=values, orientation='vertical', movable=True, swapMode='sort')
        self.old_onset = values[0]
        self.setToolTip(description)

    def mouseClickEvent(self, event):
        event.accept()
        if event.button() == QtCore.Qt.RightButton and self.movable:
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
        self.regions = dict()
        self.in_plot = dict()

        for annot in self.annotations:
            onset = annot['onset'] - self.first_time
            duration = annot['duration']
            description = annot['description']
            self.add_region(onset, duration, description)

    def add_region(self, onset, duration, description):
        region = AnnotationRegion(description=description, values=(onset, onset + duration))
        region.sigRegionChangeFinished.connect(self.region_changed)
        region.removeRequested.connect(self.remove_region)
        self.regions[onset] = region

    def remove_region(self, region):
        onset = region.getRegion()[0]
        # Remove from shown regions
        if onset in self.in_plot:
            self.main.removeItem(self.in_plot[onset])
            self.in_plot.pop(onset)

        # Remove from all regions
        if onset in self.regions:
            self.regions.pop(onset)

        # Remove from annotations
        idx = np.where(self.annotations.onset == onset + self.first_time)
        self.annotations.delete(idx)

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
            self.main.removeItem(self.in_plot[rm_onset])
            self.in_plot.pop(rm_onset)

        add_onsets = [o for o in self.regions if o + self.first_time in inside_onsets and o not in self.in_plot]
        for add_onset in add_onsets:
            region = self.regions[add_onset]
            self.main.addItem(region)
            self.in_plot[add_onset] = region

    def add_annotation(self, onset, duration, description):
        """Add annotation to Annotations (onset is here the onset
        in the plot which is then adjusted with first_time)"""
        self.annotations.append(onset + self.first_time, duration, description)
        self.add_region(onset, duration, description)
        self.update_range(*self.main.viewRange()[0])

    def change_mode(self, annotation_on):
        for region in self.regions.values():
            region.setMovable(annotation_on)


class PyQtGraphPtyp(QWidget):
    def __init__(self, raw, data, times, duration=20,
                 nchan=30, ds='auto', all_data=False, enable_cache=False,
                 antialiasing=False, use_opengl=False, show_annotations=True):
        super().__init__()
        self.view = GraphicsView(background='w')
        self.plot_item = RawPlot(raw=raw, data=data, times=times, duration=duration, nchan=nchan,
                                 ds=ds, all_data=all_data, enable_cache=enable_cache,
                                 show_annotations=show_annotations)
        self.plot_item.sigXRangeChanged.connect(self.xrange_changed)
        self.plot_item.sigYRangeChanged.connect(self.yrange_changed)
        self.view.setCentralItem(self.plot_item)
        self.view.setAntialiasing(antialiasing)
        self.view.useOpenGL(use_opengl)
        layout = QGridLayout()
        layout.addWidget(self.view, 0, 0)
        self.time_bar = TimeScrollBar(self.plot_item)
        layout.addWidget(self.time_bar, 1, 0)
        self.channel_bar = ChannelScrollBar(self.plot_item)
        layout.addWidget(self.channel_bar, 0, 1)
        self.setLayout(layout)

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
        self.time_bar.setValue(xrange[0])
        self.time_bar.update_duration()

    def yrange_changed(self, _, yrange):
        self.channel_bar.setValue(yrange[0])
        self.channel_bar.update_nchan()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left:
            if event.modifiers() == Qt.ControlModifier:
                self.plot_item.hscroll(-1)
            else:
                self.plot_item.hscroll(-self.plot_item.duration / 2)
        elif event.key() == Qt.Key_Right:
            if event.modifiers() == Qt.ControlModifier:
                self.plot_item.hscroll(1)
            else:
                self.plot_item.hscroll(self.plot_item.duration / 2)
        elif event.key() == Qt.Key_Up:
            if event.modifiers() == Qt.ControlModifier:
                self.plot_item.vscroll(-1)
            else:
                self.plot_item.vscroll(-self.plot_item.nchan / 2)
        elif event.key() == Qt.Key_Down:
            if event.modifiers() == Qt.ControlModifier:
                self.plot_item.vscroll(1)
            else:
                self.plot_item.vscroll(self.plot_item.nchan / 2)
        elif event.key() == Qt.Key_Home:
            if event.modifiers() == Qt.ControlModifier:
                self.plot_item.change_duration(-1)
            else:
                self.plot_item.change_duration(-self.plot_item.duration / 4)
        elif event.key() == Qt.Key_End:
            if event.modifiers() == Qt.ControlModifier:
                self.plot_item.change_duration(1)
            else:
                self.plot_item.change_duration(self.plot_item.duration / 4)
        elif event.key() == Qt.Key_PageDown:
            if event.modifiers() == Qt.ControlModifier:
                self.plot_item.change_nchan(-1)
            else:
                self.plot_item.change_nchan(-self.plot_item.nchan / 4)
        elif event.key() == Qt.Key_PageUp:
            if event.modifiers() == Qt.ControlModifier:
                self.plot_item.change_nchan(1)
            else:
                self.plot_item.change_nchan(self.plot_item.nchan / 4)
        elif event.key() == Qt.Key_A:
            self.plot_item.annotation_mode = not self.plot_item.annotation_mode
            self.plot_item.toggle_annot_mode()
        elif event.key() == Qt.Key_T:
            self.plot_item.clock_ticks = not self.plot_item.clock_ticks
            self.plot_item.axis_items['bottom'].refresh()
