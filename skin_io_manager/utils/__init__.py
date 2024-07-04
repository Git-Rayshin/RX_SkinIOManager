import os
import sys
import traceback
import pymel.core as pm
from PySide2 import QtWidgets, QtCore, QtGui
from maya import OpenMayaUI as omui
from shiboken2 import wrapInstance, getCppPointer

_LOGICAL_DPI_KEY = "_LOGICAL_DPI"
PY2 = sys.version_info[0] == 2


def maya_main_window():
    """Get Maya's main window

    Returns:
        QMainWindow: main window.

    """

    main_window_ptr = omui.MQtUtil.mainWindow()
    if PY2:
        return wrapInstance(long(main_window_ptr), QtWidgets.QWidget)  # noqa
    return wrapInstance(int(main_window_ptr), QtWidgets.QWidget)


def get_logicaldpi():
    """attempting to "cache" the query to the maya main window for speed

    Returns:
        int: dpi of the monitor
    """
    if _LOGICAL_DPI_KEY not in os.environ.keys():
        try:
            logical_dpi = maya_main_window().logicalDpiX()
        except Exception:
            logical_dpi = 96
        finally:
            os.environ[_LOGICAL_DPI_KEY] = str(logical_dpi)
    return int(os.environ.get(_LOGICAL_DPI_KEY)) or 96


DPI_SCALE = get_logicaldpi() / 96.0


def showDialog(dialog, dInst=True, dockable=False, *args):
    if dInst:
        try:
            for c in maya_main_window().children():
                if isinstance(c, dialog):
                    c.deleteLater()
        except Exception:
            pass

    windw = dialog()

    # ensure clean workspace name
    if hasattr(windw, "toolName") and dockable:
        control = windw.toolName + "WorkspaceControl"
        if pm.workspaceControl(control, q=True, exists=True):
            pm.workspaceControl(control, e=True, close=True)
            pm.deleteUI(control, control=True)
    desktop = QtWidgets.QApplication.desktop()
    screen = desktop.screen()
    screen_center = screen.rect().center()
    windw_center = windw.rect().center()
    windw.move(screen_center - windw_center)

    # Delete the UI if errors occur to avoid causing winEvent
    # and event errors (in Maya 2014)
    try:
        if dockable:
            windw.show(dockable=True)
        else:
            windw.show()
        return windw
    except Exception:
        windw.deleteLater()
        traceback.print_exc()
