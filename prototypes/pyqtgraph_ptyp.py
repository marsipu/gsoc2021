from collections import OrderedDict

import numpy as np
from pyqtgraph import (GraphicsView, PlotCurveItem, PlotDataItem, PlotItem, PlotWidget)


class RawDataItem(PlotDataItem):
    def __init__(self, data, times, ypos, sfreq, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._data = data
        self._times = times
        self.ypos = ypos
        self.sfreq = sfreq

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
        self.setData(visible_x, visible_y)
        # Use GraphicsObject.setPos to avoid infinite recursion
        super(PlotDataItem, self).setPos(0, self.ypos)
        self.resetTransform()


class RawCurveItem(PlotCurveItem):
    def __init__(self, data, times, ypos, sfreq, *args, custom_ds=True, **kwargs):
        super().__init__(*args, **kwargs)
        self._data = data
        self._times = times
        self.ypos = ypos
        self.sfreq = sfreq
        self.limit = 10000  # maximum number of samples to be plotted
        self.custom_ds = custom_ds

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

        if self.custom_ds > 1:
            # Auto-Downsampling and mean method from pyqtgraph
            n = len(visible_x) // self.custom_ds
            visible_x = visible_x[:n*self.custom_ds].reshape(n, self.custom_ds).mean(axis=1)
            visible_y = visible_y[:n * self.custom_ds].reshape(n, self.custom_ds).mean(axis=1)

        self.setData(visible_x, visible_y)
        self.setPos(0, self.ypos)
        self.resetTransform()


class RawPlot(PlotItem):
    def __init__(self, raw, duration, nchan, p_item_type, pg_ds,
                 pg_ds_method, custom_ds, vspace):
        super().__init__()
        self.raw = raw
        self.data, self.times = self.raw.get_data(return_times=True)
        self.data *= 1e6  # Scale EEG-Data
        self.duration = duration
        self.nchan = nchan
        self.p_item_type = p_item_type
        self.pg_ds = pg_ds
        self.pg_ds_method = pg_ds_method
        self.custom_ds = custom_ds
        self.vspace = vspace

        self.lines = OrderedDict()
        self._hscroll_dir = 1

        self.setXRange(0, duration)
        self.setLimits(xMin=0, xMax=self.data.shape[1] / self.raw.info['sfreq'],
                       yMin=0, yMax=self.data.shape[0] * self.vspace)
        self.setLabel('bottom', 'Time', 's')
        self.setYRange(0, self.nchan * self.vspace)
        for idx, ch_data in enumerate(self.data[:self.nchan]):
            ypos = idx * self.vspace + self.vspace
            self.add_line(ypos, ch_data)

        self.sigYRangeChanged.connect(self.yrange_changed)

    def add_line(self, ypos, ch_data):
        if self.p_item_type == 'curve':
            item = RawCurveItem(data=ch_data, times=self.times, ypos=ypos, sfreq=self.raw.info['sfreq'],
                                custom_ds=self.custom_ds)
        else:
            item = RawDataItem(data=ch_data, times=self.times, ypos=ypos, sfreq=self.raw.info['sfreq'])
            item.setDownsampling(auto=self.pg_ds is None, ds=self.pg_ds or 1, method=self.pg_ds)
        item.setPen('k')
        self.sigXRangeChanged.connect(item.xrange_changed)
        self.lines[ypos] = item
        self.nchan = len(self.lines)
        self.addItem(item)
        item.set_first_time()

    def remove_line(self, ypos):
        self.removeItem(self.lines[ypos])
        self.lines.pop(ypos)
        self.nchan = len(self.lines)

    def yrange_changed(self, _, yrange):
        ymin, ymax = yrange
        # # Add padding
        # ymin += self.vspace * 1.5
        # ymax -= self.vspace * 1.5
        remove_lines = [k for k in self.lines if k < ymin or k > ymax]
        for ypos in remove_lines:
            self.remove_line(ypos)
        min_ch_idx = min(self.lines.keys()) // self.vspace
        ymin_ch_idx = int(ymin // self.vspace) + 1
        for idx in reversed(range(ymin_ch_idx, min_ch_idx)):
            if idx >= 0:
                ypos = idx * self.vspace
                self.add_line(ypos, self.data[idx - 1])
                self.lines.move_to_end(ypos, last=False)

        max_ch_idx = max(self.lines.keys()) // self.vspace + 1
        ymax_ch_idx = int(ymax // self.vspace)
        for idx in range(max_ch_idx, ymax_ch_idx):
            if idx <= len(self.data):
                ypos = idx * self.vspace
                self.add_line(ypos, self.data[idx - 1])
                self.lines.move_to_end(ypos, last=True)

    def infini_hscroll(self, step):
        left = self.viewRect().left()
        right = left + self.duration
        if left + step * self._hscroll_dir <= 0:
            self._hscroll_dir = 1
        if right + step * self._hscroll_dir >= self.data.shape[1] / self.raw.info['sfreq']:
            self._hscroll_dir = -1
        left += step * self._hscroll_dir
        right += step * self._hscroll_dir
        self.setXRange(left, right)

    def change_duration(self, factor):
        self.duration += factor
        left = self.viewRect().left()
        self.setXRange(max(0, left), left + self.duration)

    def change_nchan(self, factor):
        if factor > 0 and self.nchan < self.data.shape[0]:
            ypos = self.nchan * self.vspace
            self.add_line(ypos, self.data[self.nchan])
            self.setYRange(0, self.nchan * self.vspace)
        elif factor < 0 and self.nchan != 0:
            ypos = list(self.lines.keys())[self.nchan - 1]
            self.remove_line(ypos)
            self.setYRange(0, self.nchan * self.vspace)


class PyQtGraphPtyp(GraphicsView):
    def __init__(self, raw, duration=20, nchan=30, p_item_type='curve', pg_ds=1,
                 pg_ds_method='subsample', custom_ds=1, vspace=50):
        super().__init__(background='w')

        self.plot_item = RawPlot(raw, duration, nchan, p_item_type, pg_ds,
                                 pg_ds_method, custom_ds, vspace)
        self.setCentralItem(self.plot_item)
