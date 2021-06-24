import datetime
from collections import OrderedDict

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsProxyWidget, QGridLayout, QLabel, QScrollBar, QVBoxLayout, QWidget
from pyqtgraph import (AxisItem, GraphicsView, PlotCurveItem, PlotItem, ViewBox, functions)


class RawCurveItem(PlotCurveItem):
    def __init__(self, data, times, ch_name, ypos, sfreq, ds=1, isbad=False):
        super().__init__(clickable=True)
        self._data = data
        self._times = times
        self.ch_name = ch_name
        self.ypos = ypos
        self.sfreq = sfreq
        self.limit = 10000  # maximum number of samples to be plotted
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

    def set_first_time(self):
        viewbox = self.getViewBox()
        if viewbox is None or not hasattr(viewbox, 'viewRange'):
            return

        xrange = viewbox.viewRange()[0]
        self.xrange_changed(None, xrange)

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
        tick_values = [(self.main.vspace, [self.main.lines[k][1] for k in self.main.lines.keys()])]
        return tick_values

    def tickStrings(self, values, scale, spacing):
        if not isinstance(values, list):
            values = [values]
        # Get channel-names
        tick_strings = [self.main._get_ch_name(v) for v in values]

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
        self.setMaximum(self.main.ymax // self.main.vspace - self.main.nchan)
        self.update_nchan()
        self.setSingleStep(1)
        self.setFocusPolicy(Qt.WheelFocus)
        self.valueChanged.connect(self.channel_changed)

    def channel_changed(self, value):
        new_ymin = value * self.main.vspace
        new_ymax = value * self.main.vspace + (self.main.nchan + 1) * self.main.vspace
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
    def __init__(self, raw, duration, nchan, ds, vspace, enable_cache, xrange_directly):
        self.axis_items = {'bottom': TimeAxis(self),
                           'left': ChannelAxis(self)}
        self.clock_ticks = False
        super().__init__(viewBox=RawViewBox(self), axisItems=self.axis_items)


        self.raw = raw
        self.data, self.times = self.raw.get_data(return_times=True)
        self.data *= -1e6  # Scale EEG-Data and invert to list channels from the top
        self.duration = duration
        self.nchan = nchan
        self.ds = ds
        self.vspace = vspace
        self.enable_cache = enable_cache
        self.xrange_directly = xrange_directly

        self.lines = OrderedDict()
        self._hscroll_dir = 1
        self._vscroll_dir = 1

        self.vb.disableAutoRange(ViewBox.XYAxes)
        self.hideButtons()

        self.xmax = self.times[-1]
        self.ymax = (self.data.shape[0] + 1) * self.vspace

        self.setXRange(0, duration, padding=0)
        self.setLimits(xMin=0, xMax=self.xmax,
                       yMin=0, yMax=self.ymax)
        self.setLabel('bottom', 'Time', 's')
        self.setYRange(0, (self.nchan + 1) * self.vspace, padding=0)
        for idx, (ch_data, ch_name) in \
                enumerate(zip(self.data[:self.nchan],
                              self.raw.ch_names[:self.nchan])):
            ypos = idx * self.vspace + self.vspace
            self.add_line(ypos, ch_data, ch_name)

        self.sigXRangeChanged.connect(self.xrange_changed)
        self.sigYRangeChanged.connect(self.yrange_changed)

    def _get_ch_name(self, ypos):
        ch_name = self.raw.ch_names[int(ypos // self.vspace) - 1]

        return ch_name

    def add_line(self, ypos, ch_data, ch_name):
        item = RawCurveItem(data=ch_data, times=self.times, ch_name=ch_name, ypos=ypos, sfreq=self.raw.info['sfreq'],
                            ds=self.ds, isbad=ch_name in self.raw.info['bads'])
        if self.enable_cache:
            item.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
        item.sigClicked.connect(self.bad_changed)
        if self.xrange_directly:
            self.sigXRangeChanged.connect(item.xrange_changed)
        self.lines[ch_name] = (item, ypos)
        self.nchan = len(self.lines)
        self.addItem(item)
        item.set_first_time()

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

        # Update Channel-Axis (TODO: Is there a better way? .update() doesn't seem to work)
        self.axes['left']['item'].hide()
        self.axes['left']['item'].show()

    def bad_changed(self, line, ev):
        self._addrm_bad_channel(line.ch_name, add=line.isbad)

    def xrange_changed(self, _, xrange):
        if not self.xrange_directly:
            for ch_name in self.lines:
                line = self.lines[ch_name][0]
                line.xrange_changed(None, xrange)

    def yrange_changed(self, _, yrange):
        ymin, ymax = yrange
        remove_lines = [k for k in self.lines
                        if self.lines[k][1] <= ymin
                        or self.lines[k][1] >= ymax]
        for ch_name in remove_lines:
            self.remove_line(ch_name)
        min_ch_idx = min([v[1] for v in self.lines.values()]) // self.vspace
        ymin_ch_idx = int(ymin // self.vspace) + 1
        for idx in [i for i in reversed(range(ymin_ch_idx, min_ch_idx)) if i >= 0]:
            ypos = idx * self.vspace
            ch_name = self._get_ch_name(ypos)
            self.add_line(ypos, self.data[idx - 1], ch_name)
            self.lines.move_to_end(ch_name, last=False)

        max_ch_idx = max([v[1] for v in self.lines.values()]) // self.vspace + 1
        ymax_ch_idx = int(ymax // self.vspace)
        for idx in [i for i in range(max_ch_idx, ymax_ch_idx)
                    if i <= len(self.data)]:
                ypos = idx * self.vspace
                ch_name = self._get_ch_name(ypos)
                self.add_line(ypos, self.data[idx - 1], ch_name)
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
        if parent.n_bm % (int(self.ymax / (step * self.vspace)) - self.nchan) == 0:
            self._vscroll_dir *= -1
        step *= self._vscroll_dir * self.vspace
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
        newymax = ymax + step * self.vspace
        newymin = ymin - step * self.vspace
        if self.vspace < newymax < self.ymax:
            ymax = newymax
        elif self.vspace < newymin < self.ymax:
            ymin = newymin
        else:
            return

        self.nchan += step
        self.setYRange(ymin, ymax, padding=0)


class PyQtGraphPtyp(QWidget):
    def __init__(self, raw, duration=20, nchan=30, ds=1, vspace=50, enable_cache=False, antialiasing=False,
                 use_opengl=False, xrange_directly=False):
        super().__init__()
        self.view = GraphicsView(background='w')
        self.plot_item = RawPlot(raw=raw, duration=duration, nchan=nchan, ds=ds, vspace=vspace,
                                 enable_cache=enable_cache, xrange_directly=xrange_directly)
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
        self.channel_bar.setValue(yrange[0] // self.plot_item.vspace)
        self.channel_bar.update_nchan()
