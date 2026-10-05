"""Test 1: generate STEP/IGES test geometry with OCP (OpenCASCADE)."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
import analytic as A
from occ_util import *

from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorType
from OCP.TDataStd import TDataStd_Name
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB

OUT = os.path.join(os.path.dirname(__file__), "..", "step")
os.makedirs(OUT, exist_ok=True)
T = Timer()
log = {}

o = A.OGIVE
og = make_ogive_solid(o["L"], o["R"])
_, x0 = A.ogive_hollow_vertical(o["L"], o["R"], o["t"])
ogh = make_ogive_hollow(o["L"], o["R"], o["t"], x0)
ogh_bad = make_ogive_hollow_revolve(o["L"], o["R"], o["t"], x0)
f = A.FIN
fin = make_fin(A.trapezoid_fin_pts(f["cr"], f["ct"], f["s"], f["m"]), f["t"])
t = A.TUBE
tube = make_hcyl_x(t["Ro"], t["Ri"], 0.0, t["L"])
log["build_singles_s"] = T.lap()

for name, shp in [("ogive_solid", og), ("ogive_hollow", ogh), ("fin", fin), ("tube", tube)]:
    write_step(shp, os.path.join(OUT, f"{name}.step"))
    write_iges(shp, os.path.join(OUT, f"{name}.iges"))
write_step(fin, os.path.join(OUT, "fin_inch.step"), unit="INCH")
write_step(ogh_bad, os.path.join(OUT, "ogive_hollow_badrevolve.step"))
log["write_singles_s"] = T.lap()


# ------------------------------------------------ payload assembly via XCAF (names, colours, instancing)
def payload_shapes():
    shp = {}
    for name, kind, p, rho in A.PAYLOAD:
        if kind == "hcyl":
            if name.startswith("rod"):
                continue
            shp[name] = make_hcyl_x(p["Ro"], p["Ri"], p["x0"], p["x1"])
        elif kind == "box":
            shp[name] = make_box(**p)
        elif kind == "saddle":
            shp[name] = make_saddle(**p)
    rod_proto = make_cyl_x(3.0, 0.0, 238.0)   # one prototype, instanced twice
    return shp, rod_proto


def write_payload(path, unit="MM"):
    shp, rod = payload_shapes()
    Interface_Static.SetCVal_s("write.step.unit", unit)
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    ct = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    asm = st.NewShape()
    TDataStd_Name.Set_s(asm, TCollection_ExtendedString("payload_assembly"))
    colours = {"body_tube": (0.9, 0.9, 0.2), "camera_shroud": (0.1, 0.1, 0.1)}
    for name, s in shp.items():
        lbl = st.AddShape(s, False)
        TDataStd_Name.Set_s(lbl, TCollection_ExtendedString(name))
        if name in colours:
            ct.SetColor(lbl, Quantity_Color(*colours[name], Quantity_TOC_RGB), XCAFDoc_ColorType.XCAFDoc_ColorGen)
        st.AddComponent(asm, lbl, TopLoc_Location())
    rl = st.AddShape(rod, False)
    TDataStd_Name.Set_s(rl, TCollection_ExtendedString("threaded_rod"))
    for nm, yc in (("rod_left", -25.0), ("rod_right", 25.0)):
        tr = gp_Trsf(); tr.SetTranslation(gp_Vec(6.0, yc, 12.0))
        cl = st.AddComponent(asm, rl, TopLoc_Location(tr))
        TDataStd_Name.Set_s(cl, TCollection_ExtendedString(nm))
    st.UpdateAssemblies()
    w = STEPCAFControl_Writer()
    w.SetNameMode(True)
    w.SetColorMode(True)
    w.Transfer(doc, STEPControl_AsIs)
    assert w.Write(path) == IFSelect_RetDone


write_payload(os.path.join(OUT, "payload_assembly.step"))
write_payload(os.path.join(OUT, "payload_assembly_inch.step"), unit="INCH")
log["write_payload_s"] = T.lap()

for fn in sorted(os.listdir(OUT)):
    log[f"size_{fn}"] = os.path.getsize(os.path.join(OUT, fn))
print(json.dumps(log, indent=1))
