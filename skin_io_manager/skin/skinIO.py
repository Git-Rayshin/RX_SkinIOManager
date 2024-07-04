import json
import os

import maya.OpenMaya as om
import maya.cmds as cmds

from ..utils.file_versioning import versionFile
from .npy_skinIO import SkinClusterIO
from . import getSkinCluster


def npySaveSkin(mesh, file_path):
    cSkinClusterIO = SkinClusterIO()
    cSkinClusterIO.save(mesh, file_path=file_path)


def npyLoadSkin(file_path):
    cSkinClusterIO = SkinClusterIO()
    cSkinClusterIO.load(file_path=file_path)


def exportSkin(folderPath, objs, versioning=False, file_ext='.npySkin'):
    if not os.path.exists(folderPath):
        om.MGlobal.displayWarning('skin folder does not exist, new one created!')
        os.makedirs(folderPath)
    for each in objs:
        filePath = folderPath + '/' + each.name() + file_ext
        if versioning:
            versionFile(filePath)
        if file_ext == '.npySkin':
            npySaveSkin(each, filePath)
        else:
            print("something went wrong")


def importSkin(folderPath, objs=[], createMissingJoints=False, skipAlreadySkinned=True, file_ext='.npySkin'):
    if not os.path.exists(folderPath):
        om.MGlobal.displayWarning('skin folder does not exist')
        return False
    for each in os.listdir(folderPath):
        if not each.endswith(file_ext):
            continue
        meshName = each.split('.')[0]
        if cmds.objExists(meshName):
            if getSkinCluster(meshName) and skipAlreadySkinned:
                continue
            if not objs or (meshName in objs):
                if createMissingJoints:
                    d = json.load(open(folderPath + '/' + each))
                    for jnt in d['objDDic'][0]['weights'].keys():
                        if not cmds.objExists(jnt):
                            cmds.select(d=True)
                            cmds.joint(n=jnt)
                if file_ext == '.npySkin':
                    npyLoadSkin(folderPath + '/' + each)
                else:
                    print("something went wrong")
    return True
