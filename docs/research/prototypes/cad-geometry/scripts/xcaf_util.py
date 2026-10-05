"""XCAF (names / assembly structure / instancing) STEP reader using OCP."""
import io, contextlib
from occ_util import *
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label
try:
    from OCP.TDF import TDF_LabelSequence  # OCP 7.x
except ImportError:
    from OCP.collections import Sequence_TDF_Label as TDF_LabelSequence  # OCP 8.x
from OCP.STEPCAFControl import STEPCAFControl_Reader


def label_name(lbl):
    attr = TDataStd_Name()
    if lbl.FindAttribute(TDataStd_Name.GetID_s(), attr):
        return attr.Get().ToExtString()
    return None


def read_xcaf(path):
    """Return list of (instance_name, prototype_name, located TopoDS_Shape) for every leaf part."""
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    r = STEPCAFControl_Reader()
    r.SetNameMode(True); r.SetColorMode(True)
    with contextlib.redirect_stdout(io.StringIO()):
        assert r.ReadFile(path) == IFSelect_RetDone
        assert r.Transfer(doc)
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    out = []

    def walk(lbl, loc):
        if st.IsAssembly_s(lbl):
            comps = TDF_LabelSequence()
            st.GetComponents_s(lbl, comps)
            for i in range(1, comps.Length() + 1):
                c = comps.Value(i)
                ref = TDF_Label()
                st.GetReferredShape_s(c, ref)
                walk_comp(c, ref, loc.Multiplied(st.GetLocation_s(c)))
        else:
            out.append((label_name(lbl), label_name(lbl), st.GetShape_s(lbl).Located(loc)))

    def walk_comp(c, ref, loc):
        if st.IsAssembly_s(ref):
            walk(ref, loc)
        else:
            out.append((label_name(c), label_name(ref), st.GetShape_s(ref).Located(loc)))

    roots = TDF_LabelSequence()
    st.GetFreeShapes(roots)
    for i in range(1, roots.Length() + 1):
        walk(roots.Value(i), TopLoc_Location())
    return out


