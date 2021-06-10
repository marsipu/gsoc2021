import numpy as np
from pyqtgraph import PlotCurveItem, PlotDataItem, PlotWidget


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

        ds = int((stop - start) / self.limit) + 1
        if ds == 1 or not self.custom_ds:
            visible_y = self.data[start:stop]
            scale = 1
        else:
            # Here convert data into a down-sampled array suitable for visualizing.
            # Must do this piecewise to limit memory usage.
            samples = 1 + ((stop - start) // ds)
            visible = np.zeros(samples * 2, dtype=self.data.dtype)
            sourcePtr = start
            targetPtr = 0

            # read data in chunks of ~1M samples
            chunkSize = (1000000 // ds) * ds
            while sourcePtr < stop - 1:
                chunk = self.data[sourcePtr:min(stop, sourcePtr + chunkSize)]
                sourcePtr += len(chunk)

                # reshape chunk to be integral multiple of ds
                chunk = chunk[:(len(chunk) // ds) * ds].reshape(len(chunk) // ds, ds)

                # compute max and min
                chunkMax = chunk.max(axis=1)
                chunkMin = chunk.min(axis=1)

                # interleave min and max into plot data to preserve envelope shape
                visible[targetPtr:targetPtr + chunk.shape[0] * 2:2] = chunkMin
                visible[1 + targetPtr:1 + targetPtr + chunk.shape[0] * 2:2] = chunkMax
                targetPtr += chunk.shape[0] * 2

            visible_y = visible[:targetPtr]
            scale = ds * 0.5
        self.setData(visible_x, visible_y)
        self.setPos(0, self.ypos)
        self.resetTransform()
        self.scale(scale, 1)


class PyQtGraphPtyp(PlotWidget):
    def __init__(self, raw, duration=20, nchan=30, p_item_type='data', pg_ds='peak', custom_ds=True):
        super().__init__(background='w')
        self.raw = raw
        self.duration = duration
        self.nchan = nchan
        self.p_item_type = p_item_type
        self.pg_ds = pg_ds
        self.custom_ds = custom_ds
        self.vspace = 40  # points between channels
        self.lines = list()

        self._hscroll_dir = 1

        self.data, self.times = self.raw.get_data(return_times=True)
        self.data *= 1e6  # Scale EEG-Data
        self.setXRange(0, duration)
        self.setLimits(xMin=0, xMax=self.data.shape[1] / self.raw.info['sfreq'])
        self.setLabel('bottom', 'Time', 's')
        self.setYRange(0, self.nchan * self.vspace)
        for idx, ch_data in enumerate(self.data[:self.nchan]):
            self.add_plot_item(idx, ch_data)

    def add_plot_item(self, idx, ch_data):
        ypos = idx * self.vspace
        if self.p_item_type == 'curve':
            item = RawCurveItem(data=ch_data, times=self.times, ypos=ypos, sfreq=self.raw.info['sfreq'],
                                custom_ds=self.custom_ds)
        else:
            item = RawDataItem(data=ch_data, times=self.times, ypos=ypos, sfreq=self.raw.info['sfreq'])
            item.setDownsampling(auto=self.pg_ds is not None, method=self.pg_ds)
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
            self.add_plot_item(self.nchan - 1, self.data[self.nchan])
            self.setYRange(0, self.nchan * self.vspace)
        elif factor < 0 and self.nchan != 0:
            self.remove_plot_item(self.nchan)
            self.setYRange(0, self.nchan * self.vspace)