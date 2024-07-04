import os
import re
import shutil

import maya.OpenMaya as om


def getVersions(path, new=True, numberOfVersionOldToArchive=0):
    """ Get the (version, path) to the latest (highest+1) backup of the given folder or file.
        This looks in the ".versions" folder.
    """
    if not os.path.exists(path):
        raise ValueError("Path {}0 does not exist".format(path))

    versionRe = re.compile(r"^(.+)\.v(\d+)(.*)|()$")
    parentFolder, fileName = os.path.split(path)
    # testFields if in a backup version folder
    m = versionRe.match(fileName)
    if m:
        parentFolderName = os.path.basename(parentFolder)
        if parentFolderName == "%s%s.versions" % (m.group(1), m.group(3)):
            parentFolder = os.path.dirname(parentFolder)
            fileName = "%s%s" % (m.group(1), m.group(3))

    # if not then find version number
    backupFolderName = fileName + ".versions"
    backupFolderPath = os.path.join(parentFolder, "_versions", backupFolderName)
    if os.path.exists(backupFolderPath):
        versions = []
        for file in os.listdir(backupFolderPath):
            m = versionRe.match(file)
            if m:
                versions.append(int(m.group(2)))
        version = max(versions or [0])
    else:
        versions = []
        version = 0

    version += 1
    backupFolderPath = backupFolderPath.replace("\\", "/")
    fileNameSplit = fileName.rsplit(".", 1)
    latestFileName = "%s.v%04d" % (fileNameSplit[0], version)
    if len(fileNameSplit) > 1: latestFileName += ".%s" % fileNameSplit[1]
    newVersion = "%s/%s" % (backupFolderPath, latestFileName)

    archiveList = []
    if numberOfVersionOldToArchive:
        n = (numberOfVersionOldToArchive - 1) * -1
        keeplist = versions[n:]
        removeList = list(set(versions) - set(keeplist))
        for version in removeList:
            latestFileName = "%s.v%04d" % (fileNameSplit[0], version)
            if len(fileNameSplit) > 1: latestFileName += ".%s" % fileNameSplit[1]
            filePath = "%s/%s" % (backupFolderPath, latestFileName)
            archiveList.append(filePath)

    print(newVersion, archiveList, version)
    return newVersion, archiveList, version


def versionFile(path, numberOfVersionToKeep=0):
    """ Create a Backup of the given folder or file into a ".versions" folder.
        This is not a publishing.
    """
    moveFiles = False
    # path = os.path.abspath(path)

    if not os.path.exists(path):
        om.MGlobal.displayInfo("Path {} does not exist".format(path))
        return

    newBackupPath, archiveList, version = getVersions(path, numberOfVersionOldToArchive=numberOfVersionToKeep)
    if version == 1:
        os.makedirs(os.path.dirname(newBackupPath), exist_ok=True)
    parentFolder = os.path.dirname(newBackupPath)
    if not os.path.exists(parentFolder):
        os.mkdir(parentFolder)

    if moveFiles:
        shutil.move(path, newBackupPath)
    else:
        if os.path.isfile(path):
            shutil.copy2(path, newBackupPath)
        else:
            shutil.copytree(path, newBackupPath)

    for each in archiveList:
        os.remove(each)
        om.MGlobal.displayInfo("File Deleted > {}".format(each))
