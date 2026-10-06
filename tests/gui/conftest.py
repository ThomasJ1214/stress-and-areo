import pytest

from stressaero.ui.main_window import MainWindow


@pytest.fixture
def window(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    yield w
    w.viewport.close()
