import datetime
from collections import OrderedDict

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsProxyWidget, QGridLayout, QLabel, QScrollBar, QVBoxLayout, QWidget
from mne.viz.utils import _compute_scalings
from pyqtgraph import (AxisItem, GraphicsView, PlotCurveItem, PlotItem, ViewBox, functions)


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

    def xrange_changed(self, _, xrange):
        xmin, xmax = xrange
        start = max(0, int(xmin * self.sfreq))
        stop = min(len(self.data), int(xmax * self.sfreq + 1))

        visible_x = self.times[start:stop]
        visible_y = self.data[start:stop]

        if self.ds > 1:
            # Auto-Downsampling and mean method from pyqtgraph
            n = len(visible_x) // self.ds
            visible_x = visible_x[:n*self.ds].reshape(n, self.ds).mean(axis=1)
            visible_y = visible_y[:n * self.ds].reshape(n, self.ds).mean(axis=1)

        self.setData(visible_x, visible_y)
        self.setPos(0, self.ypos)
        self.resetTransform()

    def mouseClickEvent(self, ev):
        if not self.clickable or ev.button() != Qt.MouseButton.LeftButton:
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


class RawViewBox(ViewBox):
    def __init__(self, main):
        super().__init__(invertY=True)
        self.main = main

    def keyPressEvent(self, ev):
        ev.accept()
        if ev.text() == 't':
            self.main.clock_ticks = not self.main.clock_ticks
            self.sigXRangeChanged.emit(self, tuple(self.state['viewRange'][0]))


class RawPlot(PlotItem):
    def __init__(self, raw, data, times, duration, nchan, ds, all_data,
                 enable_cache):
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

        if not self.all_data:
            self.sigXRangeChanged.connect(self.xrange_changed)
            self.sigYRangeChanged.connect(self.yrange_changed)

    def add_line(self, ch_idx, ch_data, ch_name):
        ypos = ch_idx + 1
        item = RawCurveItem(data=ch_data, times=self.times, ch_name=ch_name, ypos=ypos,
                            sfreq=self.raw.info['sfreq'], ds=self.ds,
                            isbad=ch_name in self.raw.info['bads'])
        self.lines[ch_name] = (item, ypos)

        if self.all_data:
            item.set_full_data()
        else:
            item.xrange_changed(None, self.getViewBox().viewRange()[0])
            self.nchan = len(self.lines)

        if self.enable_cache:
            item.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
        item.sigClicked.connect(self.bad_changed)
        self.addItem(item)

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
            line.xrange_changed(None, xrange)

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
        xrange = self.vb.viewRange()[0]
        xrange = [i + step for i in xrange]
        if all([0 <= i <= self.xmax for i in xrange]):
            self.setXRange(*xrange, padding=0)

    def infini_hscroll(self, step, parent):
        if parent.n_bm % (int(self.xmax / step) - self.duration) == 0:
            self._hscroll_dir *= -1
        step *= self._hscroll_dir
        self.hscroll(step)

    def vscroll(self, step):
        yrange = self.vb.viewRange()[1]
        yrange = [i + step for i in yrange]
        if all([0 <= i <= self.ymax for i in yrange]):
            self.setYRange(*yrange, padding=0)

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

    def change_nchan(self, step):
        ymin, ymax = self.vb.viewRange()[1]
        newymax = ymax + step
        newymin = ymin - step
        if 2 < newymax < self.ymax:
            ymax = newymax
        elif 0 < newymin < self.ymax:
            ymin = newymin
        else:
            return

        self.nchan += step
        self.setYRange(ymin, ymax, padding=0)


class PyQtGraphPtyp(QWidget):
    def __init__(self, raw, data, times, duration=20,
                 nchan=30, ds=1, all_data=False, enable_cache=False,
                 antialiasing=False, use_opengl=False):
        super().__init__()
        self.view = GraphicsView(background='w')
        self.plot_item = RawPlot(raw=raw, data=data, times=times, duration=duration, nchan=nchan,
                                 ds=ds, all_data=all_data, enable_cache=enable_cache)
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

    def xrange_changed(self, _, xrange):
        self.time_bar.setValue(xrange[0])
        self.time_bar.update_duration()

    def yrange_changed(self, _, yrange):
        self.channel_bar.setValue(yrange[0])
        self.channel_bar.update_nchan()
