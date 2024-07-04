import ast
import getpass
import json
import os
import re
import sys
from datetime import datetime
from functools import partial

from maya import cmds
from maya import OpenMaya as om
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

from .skin import getSkinCluster
from .utils import file_versioning

# depends on the environment(have numpy or not), import npyLoadSkin
try:
    import numpy as np
except ImportError:
    np = None
    npyLoadSkin = None
if np is not None:
    from .skin.skinIO import npyLoadSkin

# --- for standalone UI---
ICON_DIR = os.path.join(os.path.dirname(__file__), "icons").replace("\\", "/")

# --- UTILS ---
from .utils import maya_main_window, DPI_SCALE, QtCore, QtWidgets, QtGui

# --- MODULES ---
from . import operations as op
from .operations import debug
from .utils.helpers import assert_mesh, get_meshes
from .utils import showDialog

PIPLINE_AVAILABLE = False

MODULE_DIR = os.path.dirname(os.path.normpath(__file__)).replace("\\", "/")
if not PIPLINE_AVAILABLE:
    PROJECT_NAME = "standalone"
    USER_NAME = getpass.getuser()
    MGEAR_CUSTOM_PATH = os.path.join(os.path.expanduser("~"), "mGear")
    CONFIG_DIR = os.path.join(MODULE_DIR, "_config").replace("\\", "/")
# elif PIPLINE_AVAILABLE == "core_pipeline":
#     CONFIG_DIR = os.path.join(USER_PATH, "_config", "skin_tool").replace("\\", "/")
# elif PIPLINE_AVAILABLE == "Prism":
#     CONFIG_DIR = os.path.join(USER_PATH, "_config", "skin_tool").replace("\\", "/")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json").replace("\\", "/")

# print("MODULE_DIR: {}".format(MODULE_DIR))
# print("PIPLINE_AVAILABLE: {}".format(PIPLINE_AVAILABLE))
# print("CONFIG_DIR: {}".format(CONFIG_DIR))
# print("CONFIG_FILE: {}".format(CONFIG_FILE))
# print("USER_PATH: {}".format(USER_PATH))


if np is not None:
    FILE_EXTENTIONS = ([".npySkin"])
    PACK_EXTENTIONS = ([".npySkinPack"])
else:
    FILE_EXTENTIONS = ()
    PACK_EXTENTIONS = ()

SKIN_PACK_NAME = "skin"


def get_existing_versions(path):
    path = os.path.normpath(path)
    basename = os.path.basename(path)
    version_folder = os.path.join(os.path.dirname(path), "_versions", basename + ".versions")
    # version_folder = path + ".versions"
    if not os.path.exists(version_folder) or not os.path.isdir(version_folder):
        return []
    else:
        return os.listdir(version_folder)
    print(version_folder)


class MyFilter(QtCore.QSortFilterProxyModel):
    def __init__(self):
        super(MyFilter, self).__init__()

    def setFilterWildcard(self, text, case_sensitive=True):
        text = re.sub(',+', ',', text)
        text = re.sub(r"\s+", "", text)
        if text[-2] == ",":
            text = text[:-2] + text[-1:]
        list_text = list(text)
        keys = "".join(list_text).split(",")
        exps = [QtCore.QRegExp.escape(k) for k in keys]
        regExp = "|".join(exps).replace('\\*', '.*?')
        if not case_sensitive:
            regExp = "(?i)" + regExp
        self.setFilterRegularExpression(regExp)

    def filterAcceptsRow(self, sourceRow, sourceParent):
        for sourceColumn in range(1):
            filterData = self.sourceModel().index(sourceRow, sourceColumn).data(self.filterRole())
            if self.filterRegularExpression().match(filterData).hasMatch():
                return True
        return False


class MyTableView(QtWidgets.QTableView):

    def __init__(self):
        super(MyTableView, self).__init__()
        short_cut_copy_ext = QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.CTRL +
                                                                    QtCore.Qt.SHIFT + QtCore.Qt.Key_C), self)
        short_cut_copy_ext.activated.connect(self.copy_extend)
        short_cut_select_items_in_maya = QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.ALT + QtCore.Qt.Key_S), self)
        short_cut_select_items_in_maya.activated.connect(self.select_items_in_maya)

    def keyPressEvent(self, event):
        """prevent key access to maya main window"""
        super(MyTableView, self).keyPressEvent(event)
        if event.matches(QtGui.QKeySequence.Copy):
            selected_rows = [index.row() for index in
                             self.selectionModel().selectedIndexes()[::self.model().columnCount()]]
            strings_to_copy = [self.model().index(row, 0).data() for row in selected_rows]
            text = ",".join(strings_to_copy)
            if text:
                QtGui.QGuiApplication.clipboard().clear()
                QtGui.QGuiApplication.clipboard().setText(text)
        event.accept()

    def copy_extend(self):
        selected_rows = [index.row() for index in self.selectionModel().selectedIndexes()[::self.model().columnCount()]]
        strings_to_copy = [self.model().index(row, 0).data() for row in selected_rows]
        text = "[" + ", ".join(["'{}'".format(i) for i in strings_to_copy]) + "]"
        if text:
            QtGui.QGuiApplication.clipboard().clear()
            QtGui.QGuiApplication.clipboard().setText(text)

    def select_items_in_maya(self):
        selected_rows = [index.row() for index in self.selectionModel().selectedIndexes()[::self.model().columnCount()]]
        items = [self.model().index(row, 0).data() for row in selected_rows]
        selectable = [assert_mesh(i) for i in items if assert_mesh(i)]
        cmds.select(selectable)


class MyStandardDateTimeItem(QtGui.QStandardItem):
    def __init__(self, text, data):
        super(MyStandardDateTimeItem, self).__init__()
        self.setText(text)
        self.setData(data, QtCore.Qt.UserRole)

    def __lt__(self, other):
        return self.data(QtCore.Qt.UserRole) < other.data(QtCore.Qt.UserRole)


class SubTable(QtWidgets.QDialog):
    VERISON_TO_SET = QtCore.Signal()
    VERSION_DELETED = QtCore.Signal()

    def __init__(self, parent=None, source_index=None, version_paths=None):
        super(SubTable, self).__init__(parent)
        self.source_model_index = source_index
        self.version_paths = version_paths
        self.version_to_set = None
        self.source_data = None
        if sys.version_info.major < 3:
            self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        if version_paths:
            self.setWindowTitle(version_paths[-1].split("/")[-1])
            self.latest_version_dir = os.path.dirname(version_paths[-1])
            self.older_version_dir = os.path.dirname(version_paths[0])

        main_layout = QtWidgets.QVBoxLayout(self)
        v = 6 * DPI_SCALE
        main_layout.setContentsMargins(v, v, v, v)
        main_layout.setSpacing(v)

        button_layout = QtWidgets.QHBoxLayout()
        self.set_version_btn = QtWidgets.QPushButton(" Set")
        icon_path = os.path.join(ICON_DIR, "mgear_edit.svg")
        self.set_version_btn.setIcon(QtGui.QIcon(icon_path))
        self.import_version_btn = QtWidgets.QPushButton(" Import")
        icon_path = os.path.join(ICON_DIR, "mgear_log-in.svg")
        self.import_version_btn.setIcon(QtGui.QIcon(icon_path))
        self.delete_version_btn = QtWidgets.QPushButton(" Archive")
        icon_path = os.path.join(ICON_DIR, "mgear_archive.svg")
        self.delete_version_btn.setIcon(QtGui.QIcon(icon_path))
        button_layout.addWidget(self.set_version_btn)
        button_layout.addWidget(self.import_version_btn)
        button_layout.addWidget(self.delete_version_btn)

        self.table_view = MyTableView()

        main_layout.addWidget(self.table_view)
        main_layout.addLayout(button_layout)
        main_layout.setStretch(0, 1)

        self.update_model(version_paths)
        self.resize(self.sizeHint().width(), 300 * DPI_SCALE)
        self.table_view.doubleClicked.connect(self.on_double_clicked)
        self.set_version_btn.clicked.connect(self.set_version_from_sl)
        self.import_version_btn.clicked.connect(self.import_version_from_sl)
        self.delete_version_btn.clicked.connect(self.archive_versions)

    def create_model(self, version_paths=None):
        model = QtGui.QStandardItemModel()

        if version_paths:
            def make_dict(index, file_):
                if os.path.exists(os.path.normpath(file_)):
                    result = dict(
                        version_name=str(index + 1).zfill(3),
                        file_path=os.path.normpath(file_),
                        os_time=os.path.getmtime(file_),
                        file_date=datetime.fromtimestamp(os.path.getmtime(file_)).strftime('%m/%d/%Y %H:%M'),
                    )
                    return result
                else:
                    return om.MGlobal.displayError("file error")

            self.source_data = [make_dict(i, j) for i, j in enumerate(version_paths)]

            for i, item in enumerate(self.source_data):
                version_name = item["version_name"] if not i + 1 == len(
                    self.source_data) else item["version_name"] + " (latest)"
                version_name_item = MyStandardDateTimeItem(version_name.split(".")[0], item["os_time"])
                version_name_item.setTextAlignment(QtCore.Qt.AlignCenter)
                version_name_item.setFlags(version_name_item.flags() ^ QtCore.Qt.ItemIsEditable)

                file_date = item["file_date"]
                os_time = str(item["os_time"])
                file_date_item = MyStandardDateTimeItem(file_date, item["os_time"])
                file_date_item.setTextAlignment(QtCore.Qt.AlignCenter)
                file_date_item.setFlags(file_date_item.flags() ^ QtCore.Qt.ItemIsEditable)

                model.appendRow([version_name_item, file_date_item])

        return model

    def update_model(self, version_paths):
        if not version_paths or len(version_paths) < 2:
            return
        source_model = self.create_model(version_paths)

        self.table_view.verticalHeader().hide()
        source_model.setHorizontalHeaderLabels(["version", "date"])
        self.table_view.setModel(source_model)
        self.table_view.setSelectionBehavior(QtWidgets.QTableView.SelectRows)
        self.table_view.setSortingEnabled(True)

        hheader = self.table_view.horizontalHeader()
        hheader.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)

    def on_double_clicked(self):
        self.set_version_from_sl()
        self.accept()

    def set_version_from_sl(self):
        selection = self.table_view.selectionModel().selectedIndexes()
        if not selection:
            return
        index = selection[0]
        self.version_to_set = int(index.data()[:3])
        self.VERISON_TO_SET.emit()

    def import_version_from_sl(self):
        selection = self.table_view.selectionModel().selectedIndexes()
        if not selection:
            return
        index = int(selection[0].data()[:3])
        skin_file = self.version_paths[index - 1]
        if skin_file:
            om.MGlobal.displayInfo("importing {}".format(skin_file))
            if skin_file.endswith(".npySkin"):
                npyLoadSkin(skin_file)
            else:
                print("something went wrong")
                return

    def archive_versions(self):
        msgbox = QtWidgets.QMessageBox()
        msgbox.setIcon(QtWidgets.QMessageBox.Question)
        msgbox.setWindowTitle("Confirm")
        msgbox.setText("Are you sure?")
        # msgbox.setInformativeText("Are you sure?")
        msgbox.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)  # (QtCore.Qt.TextSelectableByMouse)
        msgbox.addButton("Accept", QtWidgets.QMessageBox.AcceptRole)
        msgbox.addButton("Cancel", QtWidgets.QMessageBox.NoRole)
        r = msgbox.exec_()
        if r == 1:
            return om.MGlobal.displayInfo("Canceled")
        selection = self.table_view.selectionModel().selectedIndexes()
        if not selection:
            return
        selected_versions = [int(i.data()[:3]) for i in selection[::2]]
        if len(selected_versions) >= len(self.version_paths):
            return om.MGlobal.displayWarning("Not allowed to delete all versions!")

        # move last version to version folder
        ori_names = [i for i in self.version_paths]
        temp_name = file_versioning.getVersions(self.version_paths[-1])[0]
        os.rename(self.version_paths[-1], temp_name)
        self.version_paths[-1] = temp_name
        # change older file to temp name
        for i, file_ in enumerate(self.version_paths):
            os.rename(file_, file_ + "temp")
            self.version_paths[i] = file_ + "temp"

        # archive selected versions
        now = datetime.now()
        current_time = now.strftime('%Y-%m-%d-%H%M%S')
        archive_folder_name = current_time
        archive_dir = os.path.join(self.latest_version_dir, "_archive", archive_folder_name)
        om.MGlobal.displayInfo("archiving files to -> {}".format(archive_dir))
        for i in selected_versions:
            skin_file = self.version_paths[i - 1]
            if skin_file and os.path.exists(skin_file):
                if not os.path.exists(archive_dir):
                    os.makedirs(archive_dir)
                new_path = os.path.join(archive_dir,
                                        os.path.basename(skin_file)).replace("\\", "/")
                os.rename(skin_file, new_path[:-4])
                del self.version_paths[i - 1]
        # rename remained files
        for i_, path in enumerate(self.version_paths):
            base_name = os.path.basename(path)
            split = base_name.split(".")
            if i_ + 1 != len(self.version_paths):
                split[1] = "v" + str(i_ + 1).zfill(4)
                new_name = ".".join(split)[:-4]
                os.rename(os.path.join(self.older_version_dir, base_name),
                          os.path.join(self.older_version_dir, new_name))
            else:
                del split[1]
                new_name = ".".join(split)[:-4]
                os.rename(os.path.join(self.older_version_dir, base_name),
                          os.path.join(self.latest_version_dir, new_name))

        if not os.listdir(self.older_version_dir):
            os.rmdir(self.older_version_dir)
        self.VERSION_DELETED.emit()
        self.accept()


class SkinTable(QtWidgets.QWidget):
    # VERSION_CHANGED = QtCore.Signal()

    def __init__(self, parent=None, folder_path=None, file_ext=None):

        super(SkinTable, self).__init__(parent)
        self._sub_dialogs = []
        self.file_ext = None
        self.folder_path = None
        self.source_data = {}
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        search_layout = QtWidgets.QHBoxLayout()
        search_layout.setSpacing(6 * DPI_SCALE)
        self.search_le = QtWidgets.QLineEdit()
        self.case_sensitive_btn = QtWidgets.QPushButton()
        icon_path = os.path.join(ICON_DIR, "case-sensitive.svg")
        self.case_sensitive_btn.setIcon(QtGui.QIcon(icon_path))
        self.case_sensitive_btn.setCheckable(True)
        self.case_sensitive_btn.setMaximumWidth(30 * DPI_SCALE)
        self.case_sensitive_btn.setStyleSheet("""QPushButton:checked {
                                                background-color: rgb(82, 133, 166);
                                                border-style: inset;
                                                }""")
        get_selection_btn = QtWidgets.QPushButton()
        icon_path = os.path.join(ICON_DIR, "mgear_chevrons-left.svg")
        get_selection_btn.setIcon(QtGui.QIcon(icon_path))
        get_selection_btn.setMaximumWidth(30 * DPI_SCALE)

        search_layout.addWidget(self.search_le)
        search_layout.addWidget(self.case_sensitive_btn)
        search_layout.addWidget(get_selection_btn)
        main_layout.addLayout(search_layout)

        self.table_view = MyTableView()
        main_layout.addWidget(self.table_view)

        main_layout.setStretch(1, 1)

        self.update_model(folder_path, file_ext)

        self.search_le.textChanged.connect(self.update_search)
        get_selection_btn.clicked.connect(self.get_name_form_selection)

        self.proxy_model.setFilterRole(QtCore.Qt.UserRole)
        self.proxy_model.setFilterKeyColumn(1)
        self.table_view.doubleClicked.connect(self.on_double_clicked)
        self.case_sensitive_btn.toggled.connect(self.update_sensitive)

    def create_model(self, folder_path, file_ext):
        model = QtGui.QStandardItemModel()

        if folder_path:
            file_paths = [os.path.join(folder_path, i) for i in os.listdir(folder_path)]

            def make_dict(file_):
                if os.path.exists(os.path.normpath(file_)):
                    result = dict(
                        file_name=os.path.basename(file_),
                        # file_path=os.path.normpath(file_),
                        os_time=os.path.getmtime(file_),
                        file_date=datetime.fromtimestamp(os.path.getmtime(file_)).strftime('%m/%d/%Y %H:%M'),
                        file_versions=get_existing_versions(file_)  # new
                    )
                    return result
                else:
                    return om.MGlobal.displayError("file error")

            self.source_data = [make_dict(i) for i in file_paths if i.endswith(file_ext)]

            for item in self.source_data:
                file_name = item["file_name"]
                # file_path = item["file_path"]
                file_name_item = QtGui.QStandardItem(file_name.split(file_ext)[0])
                file_name_item.setTextAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
                file_name_item.setFlags(file_name_item.flags() ^ QtCore.Qt.ItemIsEditable)
                file_name_item.setData(file_name, QtCore.Qt.UserRole)

                file_date = item["file_date"]
                os_time = str(item["os_time"])
                file_date_item = QtGui.QStandardItem(file_date)
                file_date_item.setTextAlignment(QtCore.Qt.AlignCenter)
                file_date_item.setFlags(file_date_item.flags() ^ QtCore.Qt.ItemIsEditable)
                file_date_item.setData(os_time, QtCore.Qt.UserRole + 1)

                file_versions = item["file_versions"]
                file_versions_count = str(len(file_versions) + 1)
                file_versions_item = QtGui.QStandardItem(file_versions_count)
                file_versions_item.setTextAlignment(QtCore.Qt.AlignCenter)
                file_versions_item.setFlags(file_versions_item.flags() ^ QtCore.Qt.ItemIsEditable)
                # file_versions_item.setData(file_versions_count, QtCore.Qt.UserRole + 2)
                file_versions_item.setData(file_versions, QtCore.Qt.UserRole + 2)

                if file_name.endswith(file_ext):
                    model.appendRow([file_name_item, file_date_item, file_versions_item])
        return model

    def get_name_form_selection(self):
        sl = get_meshes(sl=True)
        if not sl:
            return
        name = ",".join([i for i in sl])
        self.search_le.setText(name)

    def update_model(self, folder_path, file_ext):
        if folder_path is None:
            folder_path = ""
        if not os.path.isdir(folder_path):
            folder_path = ""
        self.folder_path = folder_path
        self.file_ext = file_ext
        self.source_model = self.create_model(folder_path, file_ext)
        self.proxy_model = MyFilter()
        self.proxy_model.setSourceModel(self.source_model)
        self.table_view.verticalHeader().hide()
        self.source_model.setHorizontalHeaderLabels(["name", "date", "version"])
        self.table_view.setModel(self.proxy_model)
        self.table_view.setSelectionBehavior(QtWidgets.QTableView.SelectRows)
        self.table_view.setSortingEnabled(True)
        self.table_view.setColumnWidth(0, 220 * DPI_SCALE)
        self.table_view.setColumnWidth(2, 50 * DPI_SCALE)

        self.source_model.dataChanged.connect(self.on_cell_changed)
        horizontal_header = self.table_view.horizontalHeader()
        horizontal_header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        if self.search_le.text():
            self.update_search(self.search_le.text())

    def refresh_model(self):
        self.update_model(self.folder_path, self.file_ext)
        om.MGlobal.displayInfo("version processing successful")

    def update_search(self, text):
        self.proxy_model.setFilterWildcard('*%s*' % text, self.case_sensitive_btn.isChecked())

    def update_sensitive(self):
        self.update_search(self.search_le.text())

    def on_double_clicked(self):
        version_index = self.table_view.selectionModel().selectedIndexes()[2]
        source_index = self.table_view.model().mapToSource(version_index)
        file_name = self.table_view.selectionModel().selectedIndexes()[0].data()
        file_path = os.path.join(self.folder_path, file_name + self.file_ext).replace("\\", "/")
        existing_versions = get_existing_versions(file_path)
        _dir = os.path.dirname(file_path)
        _name = os.path.basename(file_path)
        existing_version_paths = [os.path.join(_dir, "_versions", _name + ".versions", i).replace("\\", "/")
                                  for i in existing_versions]
        existing_version_paths.append(file_path)

        if len(existing_version_paths) > 1:
            if self._sub_dialogs:
                for w in self._sub_dialogs:
                    w.close()
                    self._sub_dialogs.remove(w)
            sub_dialog = SubTable(self, source_index, existing_version_paths)
            point = self.rect().bottomRight()
            global_point = self.mapToGlobal(point)
            sub_dialog.move(global_point - QtCore.QPoint(self.width() / -10, self.height()))
            sub_dialog.VERISON_TO_SET.connect(partial(self.set_version_from_sub_widget, dialog=sub_dialog))
            sub_dialog.VERSION_DELETED.connect(self.refresh_model)
            sub_dialog.show()
            self._sub_dialogs.append(sub_dialog)

    def set_version_from_sub_widget(self, dialog):
        self.table_view.model().sourceModel().setData(dialog.source_model_index, dialog.version_to_set)

    def on_close(self):
        for w in self._sub_dialogs:
            w.close()

    def on_cell_changed(self, index):
        if index.column() != 2:
            return
        self.table_view.model().sourceModel()
        # update new date info
        row = index.row()
        latest_date_index = self.source_model.index(row, 1)
        latest_file_name = self.source_model.index(row, 0).data() + self.file_ext
        latest_file_path = os.path.join(self.folder_path, latest_file_name).replace("\\", "/")

        all_versions = [
            os.path.join(self.folder_path, "_versions", latest_file_name + ".versions", i).replace("\\", "/")
            for i in get_existing_versions(latest_file_path)]
        all_versions.append(latest_file_path)
        new_date = datetime.fromtimestamp(os.path.getmtime(all_versions[int(index.data()) - 1])).strftime(
            '%m/%d/%Y %H:%M')
        self.source_model.setData(latest_date_index, new_date)
        # assign color to row if not latest version
        self.source_model.blockSignals(True)
        font = QtGui.QFont()
        if not index.data() == len(all_versions):
            font.setBold(True)
            for i in range(3):
                self.source_model.setData(self.source_model.index(row, i), font, QtCore.Qt.FontRole)
                self.source_model.setData(self.source_model.index(row, i), QtGui.QColor(255, 150, 100),
                                          QtCore.Qt.TextColorRole)
        else:
            font.setBold(False)
            for i in range(3):
                self.source_model.setData(self.source_model.index(row, i), font, QtCore.Qt.FontRole)
                self.source_model.setData(self.source_model.index(row, i), QtGui.QColor(200, 200, 200),
                                          QtCore.Qt.TextColorRole)
        self.source_model.blockSignals(False)


class SkinIOWidget(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super(SkinIOWidget, self).__init__(parent)
        self.error_list = None
        self.create_widgets()
        self.create_layout()
        self.create_connections()

        self.restore_config()

    def create_widgets(self):
        top_text = "Skin Folder" + " (Project: " + PROJECT_NAME + " / User: " + USER_NAME + ")" if PIPLINE_AVAILABLE else "Skin Folder"
        self.top_lb = QtWidgets.QLabel(top_text)
        self.top_lb.setStyleSheet("""QLabel {font: bold 13px;}""".replace("13px", str(int(13 * DPI_SCALE)) + "px"))
        self.open_project_folder_btn = QtWidgets.QPushButton()
        self.open_project_folder_btn.setFixedSize(22 * DPI_SCALE, 22 * DPI_SCALE)
        icon_path = os.path.join(ICON_DIR, "mgear_external-link.svg")
        self.open_project_folder_btn.setIcon(QtGui.QIcon(icon_path))
        STYLE = "QPushButton {" + "border-radius: {}px;".format(str(int(11 * DPI_SCALE))) + "}"

        STYLE += """
        QPushButton:hover:!pressed {
            background-color: #707070;
        }

        QPushButton:flat {
            border: none; /* no border for a flat push button */
        }

        QPushButton:default {
            border-color: navy; /* make the default button prominent */
        }
        QPushButton:hover {
            background-color: #181818;
        }
        """
        self.open_project_folder_btn.setStyleSheet(STYLE)
        self.open_project_folder_btn.setVisible(bool(PIPLINE_AVAILABLE))
        self.open_project_folder_btn.setToolTip("Open the project custom_steps folder")

        self.refresh_btn = QtWidgets.QPushButton(" Refresh")
        icon_path = os.path.join(ICON_DIR, "mgear_refresh-cw.svg")
        self.refresh_btn.setIcon(QtGui.QIcon(icon_path))
        self.set_path_btn = QtWidgets.QPushButton(" Set Path")
        icon_path = os.path.join(ICON_DIR, "mgear_folder.svg")
        self.set_path_btn.setIcon(QtGui.QIcon(icon_path))
        self.open_folder_btn = QtWidgets.QPushButton(" Open Folder")
        icon_path = os.path.join(ICON_DIR, "mgear_external-link.svg")
        self.open_folder_btn.setIcon(QtGui.QIcon(icon_path))
        self.folder_path_le = QtWidgets.QLineEdit()

        self.second_lb = QtWidgets.QLabel("Tracking List")
        self.second_lb.setStyleSheet("font: bold 13px;".replace("13px", str(int(13 * DPI_SCALE)) + "px"))
        self.obj_storage_chk = QtWidgets.QCheckBox()
        self.obj_storage_select_btn = QtWidgets.QPushButton()
        icon_path = os.path.join(ICON_DIR, "mgear_mouse-pointer.svg")
        self.obj_storage_select_btn.setIcon(QtGui.QIcon(icon_path))
        self.obj_storage_select_btn.setFixedSize(20 * DPI_SCALE, 20 * DPI_SCALE)
        self.obj_storage_le = QtWidgets.QLineEdit()
        self.obj_storage_le.setEnabled(False)
        self.obj_storage_set_btn = QtWidgets.QPushButton()
        icon_path = os.path.join(ICON_DIR, "mgear_chevrons-left.svg")
        self.obj_storage_set_btn.setIcon(QtGui.QIcon(icon_path))
        self.obj_storage_set_btn.setEnabled(False)
        self.obj_storage_set_btn.setMaximumWidth(30 * DPI_SCALE)
        self.obj_storage_validate_btn = QtWidgets.QPushButton()
        self.obj_storage_validate_btn.setFixedSize(22 * DPI_SCALE, 22 * DPI_SCALE)
        icon_path = os.path.join(ICON_DIR, "mgear_info.svg")
        self.obj_storage_validate_btn.setIcon(QtGui.QIcon(icon_path))
        self.obj_storage_validate_btn.setIconSize(QtCore.QSize(20 * DPI_SCALE, 20 * DPI_SCALE))

        self.obj_storage_validate_btn.setStyleSheet(STYLE)

        self.set_tracking_list_from_pack_btn = QtWidgets.QPushButton("")
        icon_path = os.path.join(ICON_DIR, "mgear_download.svg")
        self.set_tracking_list_from_pack_btn.setIcon(QtGui.QIcon(icon_path))
        self.set_tracking_list_from_pack_btn.setEnabled(False)
        self.set_tracking_list_from_pack_btn.setMaximumWidth(30 * DPI_SCALE)
        self.set_tracking_list_from_pack_btn.setEnabled(False)

        self.skin_pack_name_le = QtWidgets.QLineEdit()

        self.third_lb = QtWidgets.QLabel("General I/O")
        self.third_lb.setStyleSheet("font: bold 13px;".replace("13px", str(int(13 * DPI_SCALE)) + "px"))
        self.file_type_lb = QtWidgets.QLabel("File Type: ")
        self.export_format_cb = QtWidgets.QComboBox()
        self.export_format_cb.addItems(FILE_EXTENTIONS)
        self.import_option_lb = QtWidgets.QLabel("Import Option: ")
        self.skip_already_skinned_chk = QtWidgets.QCheckBox("Skip Already Skinned")
        self.import_skin_btn = QtWidgets.QPushButton(" Import Skin")
        icon_path = os.path.join(ICON_DIR, "mgear_log-in.svg")
        self.import_skin_btn.setIcon(QtGui.QIcon(icon_path))
        self.import_skinPack_btn = QtWidgets.QPushButton("")
        icon_path = os.path.join(ICON_DIR, "mgear_package_in.svg")
        self.import_skinPack_btn.setIcon(QtGui.QIcon(icon_path))
        self.import_skinPack_btn.setMaximumWidth(30 * DPI_SCALE)
        self.export_skin_btn = QtWidgets.QPushButton("Export SKin")
        icon_path = os.path.join(ICON_DIR, "mgear_log-out.svg")
        self.export_skin_btn.setIcon(QtGui.QIcon(icon_path))
        self.export_skinPack_btn = QtWidgets.QPushButton("")
        self.export_skinPack_btn.setMaximumWidth(30 * DPI_SCALE)
        icon_path = os.path.join(ICON_DIR, "mgear_package_out.svg")
        self.export_skinPack_btn.setIcon(QtGui.QIcon(icon_path))

        self.fourth_lb = QtWidgets.QLabel("Skin Files")
        self.fourth_lb.setStyleSheet("font: bold 13px;".replace("13px", str(int(13 * DPI_SCALE)) + "px"))
        self.skin_table = SkinTable()

        self.import_from_table_sl_btn = QtWidgets.QPushButton(" Import Selected")
        icon_path = os.path.join(ICON_DIR, "mgear_log-in.svg")
        self.import_from_table_sl_btn.setIcon(QtGui.QIcon(icon_path))
        self.version_down_btn = QtWidgets.QPushButton("ver")
        icon_path = os.path.join(ICON_DIR, "mgear_minus-square.svg")
        self.version_down_btn.setIcon(QtGui.QIcon(icon_path))
        self.version_up_btn = QtWidgets.QPushButton("ver")
        icon_path = os.path.join(ICON_DIR, "mgear_plus-square.svg")
        self.version_up_btn.setIcon(QtGui.QIcon(icon_path))

        self.button_lb = QtWidgets.QLabel("Skin Lister")

    def create_layout(self):
        # general spacing
        S = 6 * DPI_SCALE

        top_layout = QtWidgets.QVBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)

        # first label part
        top_sub_layout = QtWidgets.QHBoxLayout()
        top_sub_layout.addWidget(self.top_lb)
        top_sub_layout.addWidget(self.open_project_folder_btn)
        top_sub_layout.addStretch()
        top_layout.addLayout(top_sub_layout)
        set_path_btn_layout = QtWidgets.QHBoxLayout()
        set_path_btn_layout.setSpacing(S)
        set_path_btn_layout.addWidget(self.refresh_btn)
        set_path_btn_layout.addWidget(self.set_path_btn)
        set_path_btn_layout.addWidget(self.open_folder_btn)
        top_layout.addLayout(set_path_btn_layout)
        top_layout.addWidget(self.folder_path_le)

        # second label part
        storage_header_layout = QtWidgets.QHBoxLayout()
        storage_header_layout.setSpacing(S)
        storage_header_layout.addWidget(self.second_lb)
        storage_header_layout.addWidget(self.obj_storage_chk)
        storage_header_layout.addWidget(self.obj_storage_select_btn)
        storage_header_layout.addWidget(self.obj_storage_validate_btn)
        storage_header_layout.setSpacing(S)
        storage_header_layout.addStretch()
        obj_store_layout = QtWidgets.QHBoxLayout()
        obj_store_layout.setSpacing(S)
        obj_store_layout.addWidget(self.obj_storage_le)
        obj_store_layout.addWidget(self.obj_storage_set_btn)
        obj_store_layout.addWidget(self.set_tracking_list_from_pack_btn)
        self.obj_store_layout = obj_store_layout
        top_layout.addLayout(storage_header_layout)
        top_layout.addLayout(obj_store_layout)

        # third label part
        top_layout.addWidget(self.third_lb)
        file_type_layout = QtWidgets.QHBoxLayout()
        file_type_layout.setSpacing(S)
        file_type_layout.addWidget(self.file_type_lb)
        file_type_layout.addWidget(self.export_format_cb)
        file_type_layout.addWidget(self.import_option_lb)
        file_type_layout.addWidget(self.skip_already_skinned_chk)
        file_type_layout.addStretch()
        skin_io_btn_layout = QtWidgets.QHBoxLayout()
        skin_io_btn_layout.setSpacing(S)
        skin_io_btn_layout.addWidget(self.import_skin_btn)
        skin_io_btn_layout.addWidget(self.import_skinPack_btn)
        skin_io_btn_layout.addWidget(self.export_skin_btn)
        skin_io_btn_layout.addWidget(self.export_skinPack_btn)
        top_layout.addLayout(file_type_layout)
        top_layout.addLayout(skin_io_btn_layout)

        # table layout
        top_layout.addWidget(self.fourth_lb)
        top_layout.addWidget(self.skin_table)

        # bottom layout
        botton_layout = QtWidgets.QHBoxLayout()
        botton_layout.setSpacing(S)
        botton_layout.addWidget(self.import_from_table_sl_btn, 4)
        botton_layout.addWidget(self.version_down_btn, 1)
        botton_layout.addWidget(self.version_up_btn, 1)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addLayout(top_layout)
        main_layout.addLayout(botton_layout)

    def create_connections(self):
        self.set_path_btn.clicked.connect(self.pick_skin_folder)
        self.open_folder_btn.clicked.connect(self.open_folder)
        self.import_skin_btn.clicked.connect(self.import_skin)
        self.import_skinPack_btn.clicked.connect(partial(self.import_skin, use_skin_pack=True))
        self.export_skin_btn.clicked.connect(self.export_skin)
        self.export_skinPack_btn.clicked.connect(partial(self.export_skin, use_skin_pack=True))
        self.obj_storage_chk.toggled.connect(self.update_storage_activity)
        self.obj_storage_select_btn.clicked.connect(self.select_obj_from_storage)
        self.export_format_cb.currentIndexChanged.connect(self.update_model)
        self.set_tracking_list_from_pack_btn.clicked.connect(self.set_tracking_list_from_pack)
        self.obj_storage_set_btn.clicked.connect(self.get_obj_from_sl)
        self.refresh_btn.clicked.connect(self.update_model)
        self.folder_path_le.textChanged.connect(self.update_model)
        self.import_from_table_sl_btn.clicked.connect(self.import_skin_from_table)
        self.version_up_btn.clicked.connect(self.batch_version_up)
        self.version_down_btn.clicked.connect(self.batch_version_down)
        self.open_project_folder_btn.clicked.connect(self.open_project_base_folder)
        self.obj_storage_le.textChanged.connect(self.obj_storage_validate)
        self.obj_storage_validate_btn.clicked.connect(self.print_invalid_objs)

    def obj_storage_validate(self):
        text = self.obj_storage_le.text()
        tracked_raw = text[2:-2].split("', '")
        validated = [assert_mesh(i) for i in tracked_raw if assert_mesh(i)]
        error_list = list(set(tracked_raw) - set(validated))
        self.error_list = error_list
        if error_list:
            icon_path = os.path.join(ICON_DIR, "mgear_info_red.svg")
            self.obj_storage_validate_btn.setToolTip("click to print errors!")
            om.MGlobal.displayWarning("object not found:")
            om.MGlobal.displayWarning("{}".format(error_list))

        else:
            icon_path = os.path.join(ICON_DIR, "mgear_info_green.svg")
            self.obj_storage_validate_btn.setToolTip("all objects are valid!")
        self.obj_storage_validate_btn.setIcon(QtGui.QIcon(icon_path))

    def print_invalid_objs(self):
        if not self.error_list:
            return
        om.MGlobal.displayWarning("object not found:")
        om.MGlobal.displayWarning("{}".format(self.error_list))

    @staticmethod
    def open_project_base_folder():
        if not PIPLINE_AVAILABLE:
            return
        import webbrowser
        webbrowser.open(os.path.normpath(MGEAR_CUSTOM_PATH))

    def batch_version_up(self):
        table_view = self.skin_table.table_view
        file_ext = self.export_format_cb.currentText()
        selected_rows = {index.row() for index in table_view.selectionModel().selectedIndexes()}
        # remap to source index first.
        source_version_indices = []
        for row in selected_rows:
            current_version_index = table_view.model().index(row, 2)
            source_version_index = table_view.model().mapToSource(current_version_index)
            source_version_indices.append(source_version_index)
        for index in source_version_indices:
            source_version_index = index
            source_filename_index = table_view.model().sourceModel().index(index.row(), 0)
            latest_version_path = os.path.join(self.folder_path_le.text(),
                                               "{}{}".format(source_filename_index.data(), file_ext))
            old_version_lisdir = get_existing_versions(latest_version_path)
            item_version_count = len(old_version_lisdir) + 1
            ui_version = source_version_index.data()
            new_version = min(int(ui_version) + 1, item_version_count)
            table_view.model().sourceModel().setData(source_version_index, new_version)

    def batch_version_down(self):
        table_view = self.skin_table.table_view
        file_ext = self.export_format_cb.currentText()
        selected_rows = {index.row() for index in table_view.selectionModel().selectedIndexes()}
        source_version_indices = []
        for row in selected_rows:
            current_version_index = table_view.model().index(row, 2)
            source_version_index = table_view.model().mapToSource(current_version_index)
            source_version_indices.append(source_version_index)
        for index in source_version_indices:
            source_version_index = index
            ui_version = source_version_index.data()
            new_version = max(int(ui_version) - 1, 1)
            table_view.model().sourceModel().setData(source_version_index, new_version)

    def update_storage_activity(self, checked):
        self.obj_storage_le.setEnabled(checked)
        self.obj_storage_set_btn.setEnabled(checked)
        self.set_tracking_list_from_pack_btn.setEnabled(checked)

    def select_obj_from_storage(self):
        self.obj_storage_validate()
        text = self.obj_storage_le.text()
        # tracked_raw = text[2:-2].split("', '")
        tracked_raw = ast.literal_eval(text)
        tracking_list = [assert_mesh(i) for i in tracked_raw if assert_mesh(i)]
        # error_list = list(set(tracked_raw) - set(tracking_list))
        cmds.select(tracking_list)

    def get_obj_from_sl(self):
        selection = get_meshes(sl=True)
        if not selection:
            return
        result = [str(i) for i in selection]
        if result:
            self.obj_storage_le.setText(str(result))
        else:
            self.obj_storage_le.setText("")

    def pick_skin_folder(self):
        default_path = os.path.abspath(self.folder_path_le.text()) if os.path.isdir(
            self.folder_path_le.text()) else None
        folder_path = QtWidgets.QFileDialog.getExistingDirectory(self, 'Select Folder', default_path)
        if folder_path:
            self.folder_path_le.setText(str(folder_path))
            self.update_model()

    def pick_skin_pack(self):
        start_dir = self.folder_path_le.text() if self.folder_path_le.text() else ""
        # file_ext = self.export_format_cb.currentText()
        pack_ext = PACK_EXTENTIONS[self.export_format_cb.currentIndex()]
        start_file_path = os.path.join(start_dir, "skin{}".format(pack_ext))
        filters = 'mGear skinPack (*%s)' % pack_ext
        packPath, selected_filter = QtWidgets.QFileDialog.getOpenFileName(self, "Select SkinPack",
                                                                          start_file_path,
                                                                          filters,
                                                                          filters)
        if packPath:
            return packPath
        else:
            return om.MGlobal.displayInfo("Canceled")

    def pick_skin_pack_as_string(self):
        skin_pack = self.pick_skin_pack()
        if not skin_pack:
            return
        f = open(skin_pack)
        objs = [str(i).split(".")[0] for i in json.load(f)["packFiles"]]
        if objs:
            return str(objs)

    def set_tracking_list_from_pack(self):
        strings = self.pick_skin_pack_as_string()
        if not strings:
            return
        self.obj_storage_le.setText(strings)

    def save_skin_pack_path(self):
        start_dir = self.folder_path_le.text() if self.folder_path_le.text() else ""
        pack_ext = PACK_EXTENTIONS[self.export_format_cb.currentIndex()]
        start_file_path = os.path.join(start_dir, "skin{}".format(pack_ext))
        filters = 'mGear skinPack (*%s)' % pack_ext
        packPath, selected_filter = QtWidgets.QFileDialog.getSaveFileName(self, "Select SkinPack",
                                                                          start_file_path,
                                                                          filters,
                                                                          filters)
        return packPath if packPath else om.MGlobal.displayInfo("Canceled")

    def store_config_file(self):
        config_description = dict(skinPath=self.folder_path_le.text(),
                                  fileExt=self.export_format_cb.currentIndex(),
                                  useStoredList=self.obj_storage_chk.isChecked(),
                                  objList=self.obj_storage_le.text(),
                                  skip_already_skinned=self.skip_already_skinned_chk.isChecked(),
                                  )
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)
            om.MGlobal.displayInfo("config folder created : {}".format(CONFIG_DIR))
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config_description, f)
        debug("config stored : {}".format(config_description))

    def restore_config(self):
        if os.path.exists(CONFIG_FILE):
            f = open(CONFIG_FILE)
            config = json.load(f)
            debug("config loaded: {}".format(config))
            try:
                self.folder_path_le.setText(str(config["skinPath"]))
                self.export_format_cb.setCurrentIndex(config["fileExt"])
                self.obj_storage_chk.setChecked(config['useStoredList'])
                self.obj_storage_le.setText(str(config["objList"]))
                self.skin_table.update_model(config["skinPath"], self.export_format_cb.currentText())
                self.skip_already_skinned_chk.setChecked(config["skip_already_skinned"])
            except:
                pass

    def open_folder(self):
        path_string = self.folder_path_le.text()
        if not path_string:
            return
        elif path_string and os.path.isdir(os.path.normpath(path_string)):

            import webbrowser
            webbrowser.open(os.path.normpath(path_string))
        else:
            return om.MGlobal.displayWarning("path not valid")

    def update_model(self):
        self.skin_table.update_model(self.folder_path_le.text(), self.export_format_cb.currentText())

    @staticmethod
    def _importing_dialog():
        msgbox = QtWidgets.QMessageBox()
        msgbox.setIcon(QtWidgets.QMessageBox.Question)
        msgbox.setWindowTitle("Import Choice")
        msgbox.setText("How do you want to load weights?")
        msgbox.addButton("Everything", QtWidgets.QMessageBox.YesRole)
        msgbox.addButton("Selected", QtWidgets.QMessageBox.NoRole)
        msgbox.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
        return msgbox.exec_()

    @staticmethod
    def _versioning_dialog(text=None):
        msgbox = QtWidgets.QMessageBox()
        msgbox.setIcon(QtWidgets.QMessageBox.Question)
        msgbox.setWindowTitle("Versioning Choice")
        msgbox.setText("Export Option")
        msgbox.setInformativeText("Choose to export skin weights")
        if text:
            msgbox.setInformativeText("Choose to export skin weights\n{}".format(text))
        msgbox.setStyleSheet("font: 12px;".replace("12px", str(int(12 * DPI_SCALE)) + "px"))
        msgbox.addButton("Version", QtWidgets.QMessageBox.YesRole)
        msgbox.addButton("Overwrite", QtWidgets.QMessageBox.NoRole)
        msgbox.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
        return msgbox.exec_()

    @staticmethod
    def _confirm_dialog(info):
        msgbox = QtWidgets.QMessageBox()
        msgbox.setIcon(QtWidgets.QMessageBox.Warning)
        msgbox.setWindowTitle("Confirm")
        msgbox.setText("Untracked/Missing objects found..")
        msgbox.setInformativeText("Are you sure to export?")
        msgbox.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)  # (QtCore.Qt.TextSelectableByMouse)
        msgbox.setDetailedText(info)
        msgbox.addButton("Accept", QtWidgets.QMessageBox.AcceptRole)
        msgbox.addButton("Cancel", QtWidgets.QMessageBox.NoRole)
        return msgbox.exec_()

    def import_skin(self, use_skin_pack=False):
        # sanity check
        folder_path = self.folder_path_le.text()
        if not folder_path or not os.path.isdir(os.path.normpath(folder_path)):  # note : isdir("") will return True
            return om.MGlobal.displayWarning("Skin folder not valid")
        # use_stored_list = self.obj_storage_chk.isChecked() # TODO: not sure if this is needed
        skip_already_skinned = self.skip_already_skinned_chk.isChecked()

        if not use_skin_pack:
            # import dialog
            r = self._importing_dialog()
            if r == 2:  # cancel
                return om.MGlobal.displayInfo("Canceled")
            elif r == 0:  # everything
                objs = []
            else:
                selection = get_meshes(sl=True)
                if selection:
                    objs = selection
                else:
                    return
        else:
            strings = self.pick_skin_pack_as_string()
            if not strings:
                return
            objs = [assert_mesh(i) for i in strings[2:-2].split("', '")]
            if not objs:
                return
        op.importSkin(folder_path,
                      objs=objs,
                      skipAlreadySkinned=skip_already_skinned,
                      file_ext=self.export_format_cb.currentText())

    def import_skin_from_table(self):
        file_ext = self.export_format_cb.currentText()
        table_view = self.skin_table.table_view
        # source_model = self.skin_table.table_view.model().sourceModel()
        selected_rows = {index.row() for index in table_view.selectionModel().selectedIndexes()}
        output = []
        for row in selected_rows:
            row_data = []
            for column in range(table_view.model().columnCount()):
                index = table_view.model().index(row, column)
                row_data.append(index.data())
            output.append(row_data)
        for i in output:
            name = i[0]
            selected_version = int(i[2])
            latest_version_path = os.path.join(self.folder_path_le.text(),
                                               "{}{}".format(name, file_ext)).replace("\\", "/")
            existing_versions = get_existing_versions(latest_version_path)
            version_count = len(existing_versions) + 1
            # import latest version
            if not cmds.objExists(name):
                om.MGlobal.displayWarning("Object not found in scene: {}".format(name))
                continue
            elif selected_version == version_count:
                if getSkinCluster(name) and self.skip_already_skinned_chk.isChecked():
                    continue
                # if self.export_format_cb.currentIndex() == 0:
                if self.export_format_cb.currentText() == ".npySkin":
                    npyLoadSkin(latest_version_path)
                else:
                    folder = os.path.dirname(latest_version_path)
                    objs = [name]
                    op.importSkin(folder, objs, file_ext=file_ext)
            else:
                path = os.path.join(self.folder_path_le.text(), name + file_ext + ".versions",
                                    existing_versions[selected_version - 1]).replace("\\", "/")
                if getSkinCluster(name) and self.skip_already_skinned_chk.isChecked():
                    continue
                om.MGlobal.displayInfo("using older version: {}".format(existing_versions[selected_version - 1]))
                op.importSkin(filePath=path, file_ext=file_ext)

    def export_skin(self, use_skin_pack=False):
        # sanity check
        folder_path = self.folder_path_le.text()
        # note : isdir("") will return True, so there will be two different conditions
        if not folder_path or not os.path.isdir(os.path.normpath(folder_path)):
            return om.MGlobal.displayWarning("Skin folder not valid")
        use_stored_list = self.obj_storage_chk.isChecked()
        selection = get_meshes(sl=True)
        if not selection:
            return
        if use_stored_list:
            self.obj_storage_validate()
            tracking_list = [assert_mesh(i) for i in self.obj_storage_le.text()[2:-2].split("', '")]
            debug("tracking: {}".format(tracking_list))
            debug("selection: {}".format(selection))
            if use_skin_pack:
                if not set(selection) == set(tracking_list):
                    untracked = set(selection) - set(tracking_list)
                    untracked_list = [i for i in list(untracked) if assert_mesh(i)] if untracked else []
                    msg = "Selection not matching the tracking list: "
                    msg = msg + "\n\nUntracked: " + str(untracked_list) if untracked_list else msg
                    missing = set(tracking_list) - set(selection)
                    missing_list = [i for i in list(missing) if assert_mesh(i)] if missing else []
                    msg = msg + "\n\nMissing: " + str(missing_list) if missing_list else msg
                    not_in_scene = str(self.error_list)
                    msg = msg + "\n\nNot in Scene: " + not_in_scene
                    r = self._confirm_dialog(msg)
                    if r == 1:
                        return om.MGlobal.displayInfo("Canceled")
            if not use_skin_pack:
                if not set(selection) <= set(tracking_list):
                    untracked_list = [i for i in list(set(selection) - set(tracking_list)) if assert_mesh(i)]
                    msg = "Untracked object found: "
                    msg = msg + "\n\nUntracked: " + str(untracked_list) if untracked_list else msg
                    r = self._confirm_dialog(msg)
                    if r == 1:
                        return om.MGlobal.displayInfo("Canceled")
        file_ext = self.export_format_cb.currentText()
        debug("file_ext: {}".format(file_ext))

        # versioning check
        text = "\nNote: skinPack will also versioning up the individual files" if use_skin_pack else None
        r = self._versioning_dialog(text)
        if r == 2:
            return om.MGlobal.displayInfo("Canceled")
        elif r == 0:
            versioning = True
        else:
            versioning = False

        if use_skin_pack:
            pack_ext = PACK_EXTENTIONS[self.export_format_cb.currentIndex()]
            debug("pack_ext: {}".format(pack_ext))
            pack_path = self.save_skin_pack_path()
            debug("pack_path: {}".format(pack_path))
            if not pack_path:
                return
            op.exportSkinPack(packPath=pack_path,
                              objs=selection,
                              versioning=versioning,
                              file_ext=file_ext)
        else:
            op.exportSkin(folder_path=folder_path,
                          objs=selection,
                          versioning=versioning,
                          file_ext=file_ext,
                          )

        self.update_model()


class SkinIODialog(QtWidgets.QDialog):
    def __init__(self, parent=maya_main_window()):
        super(SkinIODialog, self).__init__(parent)
        if sys.version_info.major < 3:
            self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.setWindowTitle("Skin IO")
        self.setLayout(QtWidgets.QVBoxLayout())
        self.skin_io_widget = SkinIOWidget()
        self.layout().addWidget(self.skin_io_widget)
        self.setMinimumSize(300, 150)
        self.resize(418 * DPI_SCALE, 277 * DPI_SCALE)

    def closeEvent(self, event):
        self.skin_io_widget.store_config_file()
        self.skin_io_widget.skin_table.on_close()


class SkinIODialogDockable(MayaQWidgetDockableMixin, QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(SkinIODialogDockable, self).__init__(parent)
        self.setWindowTitle("Skin IO")
        self.setLayout(QtWidgets.QVBoxLayout())
        self.skin_io_widget = SkinIOWidget()
        self.layout().addWidget(self.skin_io_widget)
        self.setMinimumSize(300, 150)
        self.resize(418 * DPI_SCALE, 277 * DPI_SCALE * 2)

    def closeEvent(self, event):
        self.skin_io_widget.store_config_file()
        self.skin_io_widget.skin_table.on_close()


def show(dock=False):
    showDialog(SkinIODialogDockable, dockable=dock)


if __name__ == '__main__':
    show(dock=True)
