import numpy as np
from pyqtgraph import (PlotCurveItem, PlotDataItem, PlotWidget)


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
        self.viewRangeChanged()

    @property
    def times(self):
        return self._times

    @times.setter
    def times(self, value):
        self._times = value
        self.viewRangeChanged()

    def viewRangeChanged(self):
        viewbox = self.getViewBox()
        if viewbox is None or not hasattr(viewbox, 'viewRange'):
            return

        xrange = viewbox.viewRange()[0]
        start = max(0, int(xrange[0] * self.sfreq))
        stop = min(len(self.data), int(xrange[1] * self.sfreq + 1))
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
        self.viewRangeChanged()

    @property
    def times(self):
        return self._times

    @times.setter
    def times(self, value):
        self._times = value
        self.viewRangeChanged()

    def viewRangeChanged(self):
        viewbox = self.getViewBox()
        if viewbox is None or not hasattr(viewbox, 'viewRange'):
            return

        xrange = viewbox.viewRange()[0]
        start = max(0, int(xrange[0] * self.sfreq))
        stop = min(len(self.data), int(xrange[1] * self.sfreq + 1))

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


class PyQtGraphPtyp(PlotWidget):
    def __init__(self, raw, duration=20, nchan=30, p_item_type='curve', pg_ds=1,
                 pg_ds_method='subsample', custom_ds=1):
        super().__init__(background='w')

        self.raw = raw
        self.duration = duration
        self.nchan = nchan
        self.p_item_type = p_item_type
        self.pg_ds = pg_ds
        self.pg_ds_method = pg_ds_method
        self.custom_ds = custom_ds
        self.vspace = 50  # points between channels
        self.lines = list()

        self._hscroll_dir = 1

        self.data, self.times = self.raw.get_data(return_times=True)
        self.data *= 1e6  # Scale EEG-Data
        self.setXRange(0, duration)
        self.setLimits(xMin=0, xMax=self.data.shape[1] / self.raw.info['sfreq'], yMin=0)
        self.setLabel('bottom', 'Time', 's')
        self.setYRange(0, self.nchan * self.vspace)
        for idx, ch_data in enumerate(self.data[:self.nchan]):
            self.add_line(idx, ch_data)

    def add_line(self, idx, ch_data):
        ypos = idx * self.vspace + self.vspace
        if self.p_item_type == 'curve':
            item = RawCurveItem(data=ch_data, times=self.times, ypos=ypos, sfreq=self.raw.info['sfreq'],
                                custom_ds=self.custom_ds)
        else:
            item = RawDataItem(data=ch_data, times=self.times, ypos=ypos, sfreq=self.raw.info['sfreq'])
            item.setDownsampling(auto=self.pg_ds is None, ds=self.pg_ds or 1, method=self.pg_ds)
        item.setPen('k')
        self.lines.append(item)
        self.addItem(item)

    def remove_plot_item(self, idx):
        line = self.lines[idx]
        self.removeItem(self.lines[idx])
        self.lines.remove(line)

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
        self.nchan += factor
        if factor > 0 and self.nchan < self.data.shape[0]:
            self.add_line(self.nchan - 1, self.data[self.nchan])
            self.setYRange(0, self.nchan * self.vspace)
        elif factor < 0 and self.nchan != 0:
            self.remove_plot_item(self.nchan)
            self.setYRange(0, self.nchan * self.vspace)