"""
This is a prototype of a Raw-Plot based just on the Plotting-Capabilities of PyQt5/PySide2.
It was originally created by Clemens Brunner (https://github.com/cbrnr).
"""
import sys
from qtpy.QtWidgets import (QApplication, QGraphicsPathItem, QGraphicsScene,
                            QGraphicsView, QOpenGLWidget)
from qtpy.QtGui import QPainterPath, QColor, QSurfaceFormat, QPainter, QPen
from qtpy.QtCore import Qt
import numpy as np
import mne


class BrowserView(QGraphicsView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ensureVisible(0, 0, 1, 1)  # show top left corner

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Plus:  # zoom in
            self.scale(1.25, 1.25)
        elif event.key() == Qt.Key_Minus:  # zoom out
            self.scale(0.75, 0.75)
        elif event.key() == Qt.Key_Left:
            self.translate(-100, 0)
        elif event.key() == Qt.Key_Right:
            self.translate(100, 0)
        elif event.key() == Qt.Key_Up:
            self.translate(0, -100)
        elif event.key() == Qt.Key_Down:
            self.translate(0, 100)
        elif event.key() == Qt.Key_Escape:
            self.close()


def pathitem(x, y):
    """Convert x/y data to QGraphicsPathItem."""
    path = QPainterPath()
    path.moveTo(x[0], y[0])
    for point in zip(x[1:], y[1:]):
        path.lineTo(*point)
    pathitem = QGraphicsPathItem(path)
    pen = QPen(QColor("black"))
    pen.setCosmetic(True)  # don't scale line width
    pen.setWidth(2)
    pathitem.setPen(pen)
    return pathitem


fname = mne.datasets.sample.data_path() + '/MEG/sample/sample_audvis_raw.fif'
raw = mne.io.read_raw_fif(fname)
raw.pick_types(eeg=True)
raw.load_data()
raw.filter(1, None)  # highpass filter
data = raw.get_data() * 1e6
times = np.arange(data.shape[1])

app = QApplication(sys.argv)

scene = QGraphicsScene()
vspace = 75
for y in range(data.shape[0]):
    scene.addItem(pathitem(times, data[y] + y * vspace))

view = BrowserView(scene)

# enable OpenGL
opengl = QOpenGLWidget()
fmt = QSurfaceFormat()
fmt.setSamples(4)  # enable antialiasing with OpenGL
opengl.setFormat(fmt)
view.setViewport(opengl)

view.setRenderHint(QPainter.Antialiasing)  # enable antialiasing
view.resize(1000, 800)
view.show()

sys.exit(app.exec())
