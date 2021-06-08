import sys

from PyQt5.QtWidgets import QApplication

from prototypes.benchmark_utils import BenchmarkWindow

app = QApplication(sys.argv)
benchmark_win = BenchmarkWindow()
benchmark_win.show()
sys.exit(app.exec())
