import json
import os
from functools import partial

import maya.OpenMaya as om
from maya import cmds

from .skin import getSkinCluster

# depends on the environment has numpy or not, import npyLoadSkin and npySaveSkin
try:
    import numpy as np
except ImportError:
    np, npyLoadSkin, npySaveSkin = None, None, None
if np:
    from .skin.skinIO import npyLoadSkin, npySaveSkin
from .utils.helpers import timing
from .utils.file_versioning import versionFile

DEBUG = False


# @timing
def _debug(text="debugging", debug_mode=False):
    if debug_mode:
        print("debugging--", text)


debug = partial(_debug, debug_mode=DEBUG)


@timing
def _pack_data_notchanged(data_to_write, data_loaded):
    debug("pack_info: {}".format(data_to_write))
    debug("pack_read: {}".format(data_loaded))
    return data_to_write == data_loaded


@timing
def exportSkinPack(packPath, objs, versioning=False, file_ext=".gSkin"):
    debug("operation[exportSkinPack] <file_ext>{}".format(file_ext))
    packDic = {
        "packFiles": [],
        "rootPath": []
    }

    packDic["rootPath"], packName = os.path.split(packPath)

    for obj in objs:
        fileName = obj.stripNamespace() + file_ext
        filePath = os.path.join(packDic["rootPath"], fileName)
        if versioning:
            versionFile(filePath)
        # if file_ext != ".npySkin" and skin.exportSkin(filePath, [obj]):
        #     packDic["packFiles"].append(fileName)
        #     om.MGlobal.displayInfo(filePath)
        if file_ext != ".npySkin":
            print("something went wrong")
            return
        elif file_ext == ".npySkin":
            npySaveSkin(obj, filePath)
            packDic["packFiles"].append(fileName)
            om.MGlobal.displayInfo(filePath)
        else:
            om.MGlobal.displayWarning(
                obj + ": Skipped because don't have Skin Cluster")
    if versioning:
        if os.path.exists(packPath):
            with open(packPath) as json_file:
                data = json.load(json_file)
            if not _pack_data_notchanged(packDic, data):
                om.MGlobal.displayInfo("-----------------------------------------------"
                                       "skinPack change detected, versioning"
                                       "-----------------------------------------------")
                versionFile(packPath)
        else:
            versionFile(packPath)
    if packDic["packFiles"]:
        data_string = json.dumps(packDic, indent=4, sort_keys=True)
        with open(packPath, 'w') as f:
            f.write(data_string + "\n")
        om.MGlobal.displayInfo("Skin Pack exported: " + packPath)
    else:
        om.MGlobal.displayWarning("None of the selected objects have Skin Cluster. "
                                  "Skin Pack export aborted.")


@timing
def exportSkin(folder_path, objs, versioning=False, file_ext=".npySkin", prevent_unsupported_method=True):
    if not os.path.exists(folder_path):
        return om.MGlobal.displayWarning("skin folder does not exist!")
    debug("file_ext: {}".format(file_ext))
    for each in objs:
        filePath = folder_path + "/" + each + file_ext
        if prevent_unsupported_method:
            skinCluster = getSkinCluster(each)
            skinMethod = cmds.getAttr(skinCluster + ".skinningMethod")
            print(skinMethod)
            if skinMethod < 0:
                cmds.setAttr(skinCluster + ".skinningMethod", 0)
        if versioning:
            versionFile(filePath)
        if file_ext == ".npySkin":
            npySaveSkin(each, filePath)
        else:
            print("something went wrong")
            return
    om.MGlobal.displayInfo("")
    om.MGlobal.displayInfo("= DONE ==============================================")


@timing
def importSkin(folderPath, objs=[], file_ext='.npySkin', createMissingJoints=False, skipAlreadySkinned=True):
    if not os.path.exists(folderPath):
        return om.MGlobal.displayWarning("skin folder does not exist")
    debug("file_ext: {}".format(file_ext))
    skipped = []
    not_in_scene = []
    for each in os.listdir(folderPath):
        if not each.endswith(file_ext):
            continue
        meshName = each.split(".")[0]
        if not objs or (meshName in objs):
            if skipAlreadySkinned and getSkinCluster(meshName):
                skipped.append(meshName)
                continue
            if not cmds.objExists(meshName):
                not_in_scene.append(meshName)
                continue
            # TODO: not doing missing joint check for now
            # if createMissingJoints:
            #     d = json.load(open(folderPath + "/" + each))
            #     for jnt in d["objDDic"][0]["weights"].keys():
            #         if not pm.objExists(jnt):
            #             pm.select(d=True)
            #             pm.joint(n=jnt)
            if file_ext == ".npySkin":
                npyLoadSkin(folderPath + "/" + each)
            else:
                print("something went wrong")
                return
    if skipped or not_in_scene:
        print("")
    if skipped:
        om.MGlobal.displayWarning("= skipped: {} (already skinned)==".format(skipped))
    if not_in_scene:
        om.MGlobal.displayWarning("= skipped: {} (maybe object not in scene)==".format(not_in_scene))
