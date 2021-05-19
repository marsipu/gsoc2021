"""
This is a prototype of a Raw-Plot based on pyqwt.
It was originally created by Clemens Brunner (https://github.com/cbrnr).
"""
import sys
import mne
import numpy as np
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from qwt import QwtPlot, QwtLegend, QwtPlotCurve, QwtAbstractScaleDraw

raw = mne.io.read_raw_fif(
    mne.datasets.sample.data_path() + '/MEG/sample/sample_audvis_raw.fif')
data, times = raw[:, :]  # preload
n_times = 6000  # number of samples to show (about 10 sec)
n_show = 20  # channels
increment = 60  # samples per increment (10 ms)
norms = 10 * np.std(data, axis=-1, keepdims=True)
norms[norms == 0] = 1
data /= norms  # just to make the scales okay


class DataPlot(QwtPlot):

    def __init__(self, *args):
        QwtPlot.__init__(self, *args)

        self.setCanvasBackground(Qt.white)
        self.alignScales()

        # Initialize data
        self.x = np.zeros(n_times)

        self.setTitle("A Moving QwtPlot Demonstration")
        self.insertLegend(QwtLegend(), QwtPlot.BottomLegend);

        self.curves = list()
        for _ in range(n_show):
            self.curves.append(QwtPlotCurve())
            self.curves[-1].attach(self)

        self.setAxisTitle(QwtPlot.xBottom, "Time (seconds)")
        self.setAxisTitle(QwtPlot.yLeft, "Values")

        self.startTimer(1. / 60.)
        self.idx = 0

    def alignScales(self):
        self.canvas().setLineWidth(1)
        for i in range(QwtPlot.axisCnt):
            scaleWidget = self.axisWidget(i)
            if scaleWidget:
                scaleWidget.setMargin(0)
            scaleDraw = self.axisScaleDraw(i)
            if scaleDraw:
                scaleDraw.enableComponent(QwtAbstractScaleDraw.Backbone, False)

    def timerEvent(self, e):
        # y moves from left to right:
        # shift y array right and assign new value y[0]
        stop = self.idx + n_times
        if stop > len(times):
            self.idx = 0
            stop = self.idx + n_times
            assert stop < len(times)
        start = self.idx
        for ii, curve in enumerate(self.curves):
            curve.setData(times[start:stop], data[ii, start:stop] + ii)
        self.replot()
        self.idx += increment


def make():
    demo = DataPlot()
    demo.resize(500, 300)
    demo.show()
    return demo


if __name__ == '__main__':
    app = QApplication(sys.argv)
    demo = make()
    sys.exit(app.exec_())