import json  # noqa
import os
import sys

import maya.OpenMaya as om
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as om2Anim
import maya.cmds as cmds
import maya.mel as mel
import numpy as np

from . import getSkinCluster
from ..utils.helpers import get_skinCluster_mfn

NPY_EXT = ".npySkin"
PACK_NPY_EXT = ".npySkinPack"

npd_type = "float64"


class SkinClusterIO(object):

    def __init__(self):

        # ...class init
        self.cDataIO = DataIO()

        # ...vars
        self.name = ''
        self.type = 'skinCluster'
        self.weightsNonZero_Array = []
        self.weights_Array = []
        self.infMap_Array = []
        self.vertSplit_Array = []
        self.inf_Array = []
        self.skinningMethod = 1
        self.normalizeWeights = 1
        self.geometry = None
        self.blendWeights = []
        self.vtxCount = 0
        self.envelope = 1
        self.skinningMethod = 1
        self.useComponents = 0
        self.normalizeWeights = 1
        self.deformUserNormals = 1

        pass

    def get_mesh_components_from_tag_expression(self, skinPy, tag='*'):
        # Get the first geometry connected to the skin cluster
        geometries = cmds.skinCluster(skinPy, query=True, geometry=True)
        if not geometries:
            raise RuntimeError("No geometries found connected to the skin cluster.")
        geo = geometries[0]

        # Get the geo out attribute for the shape
        out_attr = cmds.deformableShape(geo, localShapeOutAttr=True)[0]

        # Get the output geometry data as MObject
        sel = om.MSelectionList()
        sel.add(geo)
        dep = om.MObject()
        sel.getDependNode(0, dep)
        fn_dep = om.MFnDependencyNode(dep)
        plug = fn_dep.findPlug(out_attr, True)
        obj = plug.asMObject()

        # Use the MFnGeometryData class to query the components for a tag
        # expression
        fn_geodata = om.MFnGeometryData(obj)

        # Components MObject
        components = fn_geodata.resolveComponentTagExpression(tag)

        dagPath = om.MDagPath.getAPathTo(dep)
        return dagPath, components

    def get_data(self, skinCluster):

        # ...get PyNode skinCluster
        # skinPy = pm.PyNode(skinCluster)

        # ...Pre Maya 2022 or new compoent tag expression
        try:
            # fnSet = OpenMaya.MFnSet(skinPy.__apimfn__().deformerSet())
            fnSet = om.MFnSet(get_skinCluster_mfn(skinCluster).deformerSet())
            members = om.MSelectionList()
            fnSet.getMembers(members, False)
            dagPath = om.MDagPath()
            components = om.MObject()
            members.getDagPath(0, dagPath, components)
        except:
            dagPath, components = self.get_mesh_components_from_tag_expression(skinCluster)

        # ...get mesh
        geometry = cmds.skinCluster(skinCluster, query=True, geometry=True)[0]

        # ...get vtxID_Array
        vtxID_Array = range(0, len(cmds.ls('%s.vtx[*]' % geometry, fl=1)))

        # ...get skin
        selList = om2.MSelectionList()
        selList.add(mel.eval('findRelatedSkinCluster %s' % geometry))
        # a = str(getSkinCluster(geometry)) or ""
        # selList.add(str(getSkinCluster(geometry)))
        skinPath = selList.getDependNode(0)

        # ...get mesh
        selList = om2.MSelectionList()
        selList.add(geometry)
        meshPath = selList.getDagPath(0)

        # ...get vtxs
        fnSkinCluster = om2Anim.MFnSkinCluster(skinPath);
        fnVtxComp = om2.MFnSingleIndexedComponent()
        vtxComponents = fnVtxComp.create(om2.MFn.kMeshVertComponent)
        fnVtxComp.addElements(vtxID_Array)

        # ...get weights/infs
        dWeights, infCount = fnSkinCluster.getWeights(meshPath, vtxComponents)
        # weights_Array = np.array(list(dWeights), dtype=npd_type)
        weights_Array = np.array(dWeights, dtype=npd_type)
        ''' manually normalize weights memo(in case sometimes this method maybe faster)
        group_size = infCount
        arr_reshaped = weights_Array.reshape((-1, group_size))
        normalized_arr_reshaped = arr_reshaped / arr_reshaped.sum(axis=1, keepdims=True)
        weights_Array = normalized_arr_reshaped.reshape(-1)
        '''

        inf_Array = [dp.partialPathName() for dp in fnSkinCluster.influenceObjects()]

        # ...convert to weightsNonZero_Array
        weightsNonZero_Array, infMap_Array, vertSplit_Array = self.compress_weightData(weights_Array, infCount)

        # ...gatherBlendWeights
        blendWeights_mArray = om.MDoubleArray()
        get_skinCluster_mfn(skinCluster).getBlendWeights(dagPath, components, blendWeights_mArray)
        blendWeights = [
            round(blendWeights_mArray[i], 6) for i in range(blendWeights_mArray.length())
            if round(blendWeights_mArray[i], 6) != 0.0
        ]

        # ...set data to self vars
        self.name = skinCluster
        self.weightsNonZero_Array = np.array(weightsNonZero_Array)
        self.infMap_Array = np.array(infMap_Array)
        self.vertSplit_Array = np.array(vertSplit_Array)
        self.inf_Array = np.array(inf_Array)
        self.geometry = geometry
        self.blendWeights = np.array(blendWeights)
        self.vtxCount = len(vertSplit_Array) - 1

        # ...get attrs
        self.envelope = cmds.getAttr(skinCluster + ".envelope")
        self.skinningMethod = cmds.getAttr(skinCluster + ".skinningMethod")
        self.useComponents = cmds.getAttr(skinCluster + ".useComponents")
        self.normalizeWeights = cmds.getAttr(skinCluster + ".normalizeWeights")
        self.deformUserNormals = cmds.getAttr(skinCluster + ".deformUserNormals")

        return True

    def set_data(self, skinCluster):

        # ...get PyNode skinCluster
        # skinPy = pm.PyNode(skinCluster)

        # ...Pre Maya 2022 or new compoent tag expression
        try:
            fnSet = om.MFnSet(get_skinCluster_mfn(skinCluster).deformerSet())
            members = om.MSelectionList()
            fnSet.getMembers(members, False)
            dagPath = om.MDagPath()
            components = om.MObject()
            members.getDagPath(0, dagPath, components)
        except:
            dagPath, components = self.get_mesh_components_from_tag_expression(skinCluster)

        ###################################################

        # ...set infs
        influencePaths = om.MDagPathArray()
        infCount = get_skinCluster_mfn(skinCluster).influenceObjects(influencePaths)
        influences_Array = [influencePaths[i].partialPathName() for i in range(influencePaths.length())]

        # ...change the order in set(i,i)
        influenceIndices = om.MIntArray(infCount)
        [influenceIndices.set(i, i) for i in range(infCount)]

        ###################################################

        # ...construct mArrays from normal/numpy arrays
        infCount = len(influences_Array)
        weightCounter = 0
        weights_Array = []
        weights_mArray = om.MDoubleArray()
        length = len(self.vertSplit_Array)
        for vtxId, splitStart in enumerate(self.vertSplit_Array):
            if vtxId < length - 1:
                vertChunk_Array = [0] * infCount
                splitEnd = self.vertSplit_Array[vtxId + 1]

                # ...unpack data and replace zeros with nonzero weight vals
                for i in range(splitStart, splitEnd):
                    infMap = self.infMap_Array[i]
                    val = self.weightsNonZero_Array[i]
                    vertChunk_Array[infMap] = val

                # ...append to raw data array
                for vert in vertChunk_Array:
                    weights_mArray.append(vert)

        ###################################################
        # ...set data
        get_skinCluster_mfn(skinCluster).setWeights(dagPath, components, influenceIndices, weights_mArray,
                                                    True)  # True for normalize
        if self.blendWeights is not None:
            blendWeights_mArray = om.MDoubleArray()
            for i in self.blendWeights:
                blendWeights_mArray.append(i)
            get_skinCluster_mfn(skinCluster).setBlendWeights(dagPath, components, blendWeights_mArray)
        ###################################################
        # ...set attrs of skinCluster
        cmds.setAttr('%s.envelope' % skinCluster, self.envelope)
        cmds.setAttr('%s.skinningMethod' % skinCluster, self.skinningMethod)
        cmds.setAttr('%s.useComponents' % skinCluster, self.useComponents)
        cmds.setAttr('%s.normalizeWeights' % skinCluster, self.normalizeWeights)
        cmds.setAttr('%s.deformUserNormals' % skinCluster, self.deformUserNormals)

        # ...name
        cmds.rename(skinCluster, self.geometry + "_skinCls")

    def save(self, node=None, file_path=None):

        # ...get selection
        if node is None:
            node = cmds.ls(sl=1)
            if node is None:
                print('ERROR: Select Something!')
                return False
            else:
                node = node[0]

        # ...get skinCluster
        # skinCluster = mel.eval('findRelatedSkinCluster ' + node)
        skinCluster = str(getSkinCluster(node)) or ""
        print("save", skinCluster, node, "-------------")
        if not cmds.objExists(skinCluster):
            print('ERROR: Node has no skinCluster!')
            return False

        # ...get dirpath
        if file_path is None:
            startDir = cmds.workspace(q=True, rootDirectory=True)
            file_path = cmds.fileDialog2(caption='Save Skinweights', dialogStyle=2, fileMode=3,
                                         startingDirectory=startDir, fileFilter='*.npySkin', okCaption="Select")

        # ...get filepath
        # skinCluster = 'skinCluster_%s' % node
        # filepath = '%s/%s.npySkin' % (file_path, node)

        # ...get data
        self.get_data(skinCluster)
        transformNode, meshNode = self._geometry_compatibility()
        self.geometry = transformNode
        if self.skinningMethod < 0:
            self.skinningMethod = 0
        # ...construct data_array
        legend = ('legend',
                  'weightsNonZero_Array',
                  'vertSplit_Array',
                  'infMap_Array',

                  'inf_Array',
                  'geometry',
                  'blendWeights',
                  'vtxCount',

                  'name',
                  'envelope',
                  'skinningMethod',
                  'useComponents',

                  'normalizeWeights',
                  'deformUserNormals',

                  'type',
                  )

        data = [legend,
                self.weightsNonZero_Array,
                self.vertSplit_Array,
                self.infMap_Array,

                self.inf_Array,
                self.geometry,
                self.blendWeights,
                self.vtxCount,

                self.name,
                self.envelope,
                self.skinningMethod,
                self.useComponents,

                self.normalizeWeights,
                self.deformUserNormals,

                self.type,
                ]
        # for i in data:
        #     print(type(i))

        # ...write data (temporarily add pickle method for python3.9)
        if sys.version_info[0] == 3 and sys.version_info[1] == 9:
            import pickle
            with open(file_path, 'wb') as fh:
                pickle.dump(data, fh)
        else:
            with open(file_path, 'wb') as fh:
                np.save(fh, data, allow_pickle=True)

        # region --- debug codes region ---
        # _data = [legend,
        #          self.weightsNonZero_Array.tolist(),
        #          list(self.vertSplit_Array.tolist()),
        #          list(self.infMap_Array.tolist()),

        #          list(self.inf_Array.tolist()),
        #          self.geometry,
        #          list(self.blendWeights.tolist()),
        #          int(self.vtxCount),

        #          self.name,
        #          self.envelope,
        #          int(self.skinningMethod),
        #          self.useComponents,

        #          int(self.normalizeWeights),
        #          self.deformUserNormals,

        #          self.type,
        #          ]
        # print("---------------")
        # filepath = file_path.replace(".npySkin", ".json")
        # with open(filepath, 'w') as fh:
        #     json.dump(_data, fh, indent=4, sort_keys=True)
        # endregion --- debug codes region ---

    def load(self, file_path=None, createMissingJoints=True):

        # ...get dirpath
        if file_path is None:
            startDir = cmds.workspace(q=True, rootDirectory=True)
            file_path = cmds.fileDialog2(caption='Load Skinweights', dialogStyle=2, fileMode=1,
                                         startingDirectory=startDir, fileFilter='*.npySkin', okCaption="Select")

        # ...get filepath
        # skinCluster = 'skinCluster_%s' % node
        # filepath = '%s/%s.npySkin' % (file_path, node)

        # ...check if skinCluster exists
        if not os.path.exists(file_path):
            print('ERROR: file {} does not exist!'.format(file_path))
            return False

        # ...read data
        data = np.load(file_path, allow_pickle=True)

        # ...get item data from numpy array
        self.legend_Array = self.cDataIO.get_legendArrayFromData(data)
        self.weightsNonZero_Array = self.cDataIO.get_dataItem(data, 'weightsNonZero_Array', self.legend_Array)
        self.infMap_Array = self.cDataIO.get_dataItem(data, 'infMap_Array', self.legend_Array)
        self.vertSplit_Array = self.cDataIO.get_dataItem(data, 'vertSplit_Array', self.legend_Array)
        self.inf_Array = self.cDataIO.get_dataItem(data, 'inf_Array', self.legend_Array)
        self.blendWeights = self.cDataIO.get_dataItem(data, 'blendWeights', self.legend_Array)
        self.vtxCount = self.cDataIO.get_dataItem(data, 'vtxCount', self.legend_Array)
        self.geometry = self.cDataIO.get_dataItem(data, 'geometry', self.legend_Array)
        self.name = self.cDataIO.get_dataItem(data, 'name', self.legend_Array)
        self.envelope = self.cDataIO.get_dataItem(data, 'envelope', self.legend_Array)
        self.skinningMethod = self.cDataIO.get_dataItem(data, 'skinningMethod', self.legend_Array)
        self.useComponents = self.cDataIO.get_dataItem(data, 'useComponents', self.legend_Array)
        self.normalizeWeights = self.cDataIO.get_dataItem(data, 'normalizeWeights', self.legend_Array)
        self.deformUserNormals = self.cDataIO.get_dataItem(data, 'deformUserNormals', self.legend_Array)

        node = self.geometry
        transformNode, meshNode = self._geometry_compatibility()
        dataVertexCount = self.vtxCount
        nodeVertexCount = cmds.polyEvaluate(node, vertex=True)
        if dataVertexCount != nodeVertexCount:
            return om.MGlobal.displayWarning(
                'SKIPPED: vertex count mismatch! %s != %s' % (dataVertexCount, nodeVertexCount))
        # ...unbind current skinCluster
        skinCluster = mel.eval('findRelatedSkinCluster ' + node)
        # skinCluster = str(getSkinCluster(node)) or ""
        # print(skinCluster, node, "-------------")
        if cmds.objExists(skinCluster):
            # mel.eval('skinCluster -e  -ub ' + skinCluster)
            cmds.skinCluster(skinCluster, e=True, ub=True)

        # ...bind skin
        missing_joints = [inf for inf in self.inf_Array if not cmds.objExists(inf)]
        if missing_joints:
            if createMissingJoints:
                if not cmds.objExists('missingJoints'):
                    grp = cmds.createNode("transform", n="missingJoints")
                else:
                    grp = 'missingJoints'
                for inf in missing_joints:
                    jnt = cmds.joint(n=inf)
                    cmds.parent(jnt, grp)
            else:
                return om.MGlobal.displayError('ERROR: %s does not exist!' % missing_joints[0])

        # skinCluster = 'skinCluster_%s' % node
        # skinCluster = cmds.skinCluster(self.inf_Array, node, n=skinCluster, tsb=True)[0]
        # skinCluster = cmds.skinCluster(self.inf_Array, node, n=self.name, tsb=True)[0]
        skinCluster = cmds.skinCluster(self.inf_Array, node, n=self.geometry + "_skinCls", tsb=True)[0]
        # ...set data
        self.set_data(skinCluster)

        ###################################

    def compress_weightData(self, weights_Array, infCount):

        # ...convert to weightsNonZero_Array
        weightsNonZero_Array = []
        infCounter = 0
        infMap_Chunk = []
        infMap_ChunkCount = 0
        vertSplit_Array = [infMap_ChunkCount]
        infMap_Array = []

        for w in weights_Array:
            if w != 0.0:
                weightsNonZero_Array.append(w)
                infMap_Chunk.append(infCounter)

            # ...update inf counter
            infCounter += 1
            if infCounter == infCount:
                infCounter = 0

                # ...update vertSplit_Array
                infMap_Array.extend(infMap_Chunk)
                infMap_ChunkCount = len(infMap_Chunk) + infMap_ChunkCount
                vertSplit_Array.append(infMap_ChunkCount)
                infMap_Chunk = []

        return weightsNonZero_Array, infMap_Array, vertSplit_Array

    # def _geometry_compatibility(self):
    #     """ save&load skin data with shape node is not compatible enough,
    #         so I try to use the mesh-Transform node instead, but keep compatibility
    #     """
    #     meshData = pm.PyNode(self.geometry)
    #     if meshData.nodeType() == "mesh":
    #         transformNode = meshData.getParent()
    #         meshNode = meshData
    #     elif meshData.nodeType() == "transform":
    #         transformNode = meshData
    #         meshNode = meshData.getShape()
    #     return transformNode.name(), meshNode.name()

    def _geometry_compatibility(self):
        """ save&load skin data with shape node is not compatible enough,
            so I try to use the mesh-Transform node instead, but keep compatibility
        """
        meshData = self.geometry
        transformNode = None
        meshNode = None

        # Check if geometry is a mesh node
        if cmds.nodeType(meshData) == "mesh":
            transformNode = cmds.listRelatives(meshData, parent=True, fullPath=True)[0]
            meshNode = meshData
        # Check if geometry is a transform node
        elif cmds.nodeType(meshData) == "transform":
            transformNode = meshData
            shapes = cmds.listRelatives(meshData, shapes=True, fullPath=True) or []
            for shape in shapes:
                if cmds.nodeType(shape) == "mesh":
                    meshNode = shape
                    break

        if not transformNode or not meshNode:
            raise RuntimeError(f"Failed to find compatible geometry for node: {meshData}")
        transformNode = transformNode.split("|")[-1]
        return transformNode, meshNode


class DataIO(object):

    def __init__(self):

        pass

    @staticmethod
    def get_legendArrayFromData(data):

        return data[0]

    @staticmethod
    def get_dataItem(data, item, legend_Array=None):
        if item not in data[0]:
            print('ERROR: "%s" Not Found in data!' % item)
            return False
        # ...no legend_Array
        if legend_Array is None:
            legend_Array = [key for key in data[0]]
            # ...with legend_Array
        return data[legend_Array.index(item)]

    @staticmethod
    def set_dataItems(data, itemData_Array):

        return data
