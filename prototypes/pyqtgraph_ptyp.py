import numpy as np
import pyqtgraph
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from pyqtgraph import GraphicsLayout, GraphicsView, PlotCurveItem


class RawCurveItem(PlotCurveItem):
    def __init__(self, raw=None, *args, **kwargs):
        self._raw = raw
        self.limit = 10000  # maximum number of samples to be plotted
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
            pass
        else:
            start = max(0, int(xrange[0]))
            stop = min(len(self.raw), int(xrange[1] + 1))

            ds = int((stop - start) / self.limit) + 1
            print(ds)
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
            self.setPos(start, 0)
            self.resetTransform()
            self.scale(scale, 1)


class PyQtGraphPtyp(QWidget):
    def __init__(self, raw, duration=20, nchan=30, use_opengl=False,
                 downsampling='peak'):
        super().__init__()
        self.plots = list()
        self.raw = raw
        self.duration = duration
        self.nchan = nchan
        self.use_opengl = use_opengl
        self.downsampling = downsampling

        pyqtgraph.setConfigOptions(background="w", foreground="k", antialias=True)
        self.data, self.times = self.raw.get_data(return_times=True)
        self.view = GraphicsView(useOpenGL=self.use_opengl)
        self.graphics_layout = GraphicsLayout()

        self.init_backend()

    def init_backend(self):
        layout = QVBoxLayout()
        self.graphics_layout.setSpacing(0)
        self.view.setCentralItem(self.graphics_layout)
        for ch in range(10 - 1):
            plot = self.graphics_layout.addPlot(row=ch, col=0, enableMenu=False)
            plot.setXRange(0, int(self.duration * self.raw.info['sfreq']))
            plot.setLimits(xMin=0, xMax=self.data.shape[1])
            if self.downsampling == 'custom':
                curve = RawCurveItem(self.data[ch])
            else:
                plot.setDownsampling(auto=True, mode=self.downsampling)
                curve = PlotCurveItem(self.data[ch], self.times)
            curve.setPen("k")
            plot.addItem(curve)
            self.plots.append(plot)
        for ch in range(10 - 2):  # link axes
            self.plots[ch].setXLink(self.plots[ch + 1])
            self.plots[ch].setYLink(self.plots[ch + 1])
            self.plots[ch].getAxis("bottom").setStyle(showValues=False)
            self.plots[ch].getAxis("bottom").hide()
        layout.addWidget(self.view)
        self.setLayout(layout)

    def change_duration(self, factor):
        pass

    def change_nchan(self, factor):
        pass