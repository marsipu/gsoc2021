import numpy as np
from pyqtgraph import PlotCurveItem, PlotWidget


class RawCurveItem(PlotCurveItem):
    def __init__(self, raw, ypos, *args, **kwargs):
        self._raw = raw
        self.ypos = ypos
        self.limit = 1000  # maximum number of samples to be plotted
        super().__init__(*args, **kwargs)

    @property
    def raw(self):
        return self._raw

    @raw.setter
    def raw(self, value):
        self._raw = value
        self.viewRangeChanged()

    def viewRangeChanged(self):
        viewbox = self.getViewBox()
        if viewbox is None:
            return
        try:
            xrange = viewbox.viewRange()[0]
        except AttributeError:
            print('No Viewbox-Error')
        else:
            start = max(0, int(xrange[0]))
            stop = min(len(self.raw), int(xrange[1] + 1))

            ds = int((stop - start) / self.limit) + 1
            if ds == 1:
                visible = self.raw[start:stop]
                scale = 1
            else:
                # Here convert data into a down-sampled array suitable for visualizing.
                # Must do this piecewise to limit memory usage.
                samples = 1 + ((stop - start) // ds)
                visible = np.zeros(samples * 2, dtype=self.raw.dtype)
                sourcePtr = start
                targetPtr = 0

                # read data in chunks of ~1M samples
                chunkSize = (1000000 // ds) * ds
                while sourcePtr < stop - 1:
                    chunk = self.raw[sourcePtr:min(stop, sourcePtr + chunkSize)]
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

                visible = visible[:targetPtr]
                scale = ds * 0.5
            self.setData(visible)
            self.setPos(start, self.ypos)
            self.resetTransform()
            self.scale(scale, 1)


class PyQtGraphPtyp(PlotWidget):
    def __init__(self, raw, duration=20, nchan=30, downsampling='peak'):
        super().__init__(background='w')
        self.raw = raw
        self.duration = duration
        self.nchan = nchan
        self.downsampling = downsampling
        self.data, self.times = self.raw.get_data(return_times=True)
        self.setXRange(0, 2000)
        self.setYRange(0, self.data.shape[0] * 6)
        # self.setLimits(xMin=0, xMax=self.times[-1])
        self.getPlotItem().setDownsampling(auto=True, mode=self.downsampling)
        for idx, ch_data in enumerate(self.data):
            curve = RawCurveItem(ch_data * 1e6, ypos=idx*6, y=self.times)
            curve.setPen('k')
            self.addItem(curve)

    def change_duration(self, factor):
        pass

    def change_nchan(self, factor):
        pass