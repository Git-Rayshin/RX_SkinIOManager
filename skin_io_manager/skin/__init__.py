from maya import cmds


def getSkinCluster(obj, first_SC=False):
    skinCluster = None

    if isinstance(obj, str):
        try:
            shapes = cmds.listRelatives(obj, shapes=True)
            if shapes:
                for shape in shapes:
                    if cmds.nodeType(shape) in ["mesh", "nurbsSurface", "nurbsCurve"]:
                        history = cmds.listHistory(shape)
                        if history:
                            for node in history:
                                if cmds.nodeType(node) == "skinCluster":
                                    geometry = cmds.skinCluster(node, query=True, geometry=True)
                                    if geometry and geometry[0] == shape:
                                        skinCluster = node
                                        if first_SC:
                                            return skinCluster
        except Exception:
            cmds.warning("%s: is not supported." % obj)

    return skinCluster
