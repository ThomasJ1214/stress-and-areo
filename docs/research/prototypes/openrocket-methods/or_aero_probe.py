"""
Probe OpenRocket 24.12's BarrowmanCalculator directly via JPype on a programmatically built rocket
(known geometry) and dump CD breakdown / CNa / CP vs Mach.  Used to validate a Python re-implementation
(or_aero_py.py).  Usage: python or_aero_probe.py <OpenRocket-24.12.jar> <out.json>
"""
import json
import sys

import jpype
import jpype.imports

jar, out = sys.argv[1], sys.argv[2]
jpype.startJVM(jpype.getDefaultJVMPath(), "-Djava.awt.headless=true", f"-Djava.class.path={jar}",
               convertStrings=True)
J = jpype.JClass
Guice = J("com.google.inject.Guice")
GuiModule = J("info.openrocket.swing.startup.GuiModule")
PluginModule = J("info.openrocket.core.plugin.PluginModule")
Application = J("info.openrocket.core.startup.Application")
gm = GuiModule()
Application.setInjector(Guice.createInjector(gm, PluginModule()))
# motors/presets are not needed for aero probing; don't start loaders

Rocket = J("info.openrocket.core.rocketcomponent.Rocket")
AxialStage = J("info.openrocket.core.rocketcomponent.AxialStage")
NoseCone = J("info.openrocket.core.rocketcomponent.NoseCone")
BodyTube = J("info.openrocket.core.rocketcomponent.BodyTube")
TrapezoidFinSet = J("info.openrocket.core.rocketcomponent.TrapezoidFinSet")
FinSet = J("info.openrocket.core.rocketcomponent.FinSet")
Shape = J("info.openrocket.core.rocketcomponent.Transition$Shape")
Finish = J("info.openrocket.core.rocketcomponent.ExternalComponent$Finish")
AxialMethod = J("info.openrocket.core.rocketcomponent.position.AxialMethod")
BarrowmanCalculator = J("info.openrocket.core.aerodynamics.BarrowmanCalculator")
FlightConditions = J("info.openrocket.core.aerodynamics.FlightConditions")
WarningSet = J("info.openrocket.core.logging.WarningSet")
CrossSection = J("info.openrocket.core.rocketcomponent.FinSet$CrossSection")

GEOM = dict(nose_len=0.30, R=0.04, body_len=1.0, wall=0.002,
            fin_n=4, root=0.15, tip=0.075, sweep=0.06, span=0.08, fin_t=0.003)


def build(shape="OGIVE", param=1.0, cross="SQUARE", finish="NORMAL", perfect=False):
    g = GEOM
    rocket = Rocket()
    stage = AxialStage()
    rocket.addChild(stage)
    nose = NoseCone(getattr(Shape, shape), g["nose_len"], g["R"])
    nose.setShapeParameter(param)
    nose.setThickness(g["wall"])
    nose.setFinish(getattr(Finish, finish))
    stage.addChild(nose)
    body = BodyTube(g["body_len"], g["R"], g["wall"])
    body.setFinish(getattr(Finish, finish))
    stage.addChild(body)
    fins = TrapezoidFinSet(g["fin_n"], g["root"], g["tip"], g["sweep"], g["span"])
    fins.setThickness(g["fin_t"])
    fins.setCrossSection(getattr(CrossSection, cross))
    fins.setFinish(getattr(Finish, finish))
    fins.setAxialMethod(AxialMethod.BOTTOM)
    fins.setAxialOffset(0.0)
    body.addChild(fins)
    rocket.setPerfectFinish(perfect)
    rocket.enableEvents()
    return rocket, nose, body, fins


def probe(rocket, nose, body, fins, machs, aoa=0.0):
    config = rocket.getSelectedConfiguration()
    rows = []
    for M in machs:
        calc = BarrowmanCalculator()
        cond = FlightConditions(config)
        cond.setMach(float(M))
        cond.setAOA(float(aoa))
        cond.setTheta(0.0)
        cond.setRollRate(0.0)
        cond.setPitchRate(0.0)
        cond.setYawRate(0.0)
        ws = WarningSet()
        f = calc.getAerodynamicForces(config, cond, ws)
        fa = calc.getForceAnalysis(config, FlightConditions(config) if False else cond, WarningSet())
        comp = {}
        for c, af in fa.entrySet() if hasattr(fa, "entrySet") else []:
            pass
        it = fa.entrySet().iterator()
        while it.hasNext():
            e = it.next()
            c, af = e.getKey(), e.getValue()
            comp[str(c.getName())] = dict(CD=float(af.getCD()), fric=float(af.getFrictionCD()),
                                         press=float(af.getPressureCD()), base=float(af.getBaseCD()),
                                         CNa=float(af.getCP().weight), CPx=float(af.getCP().x))
        rows.append(dict(M=float(M), CD=float(f.getCD()), CDaxial=float(f.getCDaxial()),
                         fric=float(f.getFrictionCD()), press=float(f.getPressureCD()),
                         base=float(f.getBaseCD()), CNa=float(f.getCP().weight), CPx=float(f.getCP().x),
                         Re=float(cond.getVelocity() * config.getLengthAerodynamic() /
                                  cond.getAtmosphericConditions().getKinematicViscosity()),
                         V=float(cond.getVelocity()), refA=float(cond.getRefArea()),
                         warnings=[str(w) for w in ws], comp=comp))
    return rows


machs = [0.05, 0.1, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0, 1.05, 1.1, 1.2, 1.3, 1.5, 1.75, 2.0, 2.5, 3.0]
res = {"geom": GEOM, "cases": {}}
for shape, param in [("OGIVE", 1.0), ("OGIVE", 0.5), ("CONICAL", 0.0), ("HAACK", 0.0), ("HAACK", 1.0 / 3),
                     ("POWER", 0.5), ("ELLIPSOID", 0.0), ("PARABOLIC", 1.0), ("OGIVE", 0.0)]:
    r = build(shape, param)
    res["cases"][f"{shape}_{param:.3f}_SQUARE_NORMAL"] = probe(*r, machs)
for cross in ["ROUNDED", "AIRFOIL"]:
    r = build("OGIVE", 1.0, cross=cross)
    res["cases"][f"OGIVE_1.000_{cross}_NORMAL"] = probe(*r, machs)
r = build("OGIVE", 1.0, perfect=True, finish="POLISHED")
res["cases"]["OGIVE_1.000_SQUARE_POLISHED_PERFECT"] = probe(*r, machs)
# small AoA case for normal force / CN
r = build("OGIVE", 1.0)
res["cases"]["OGIVE_1.000_SQUARE_NORMAL_aoa4deg"] = probe(*r, machs, aoa=4 * 3.141592653589793 / 180)
# record some geometry-derived values
rocket, nose, body, fins = build("OGIVE", 1.0)
config = rocket.getSelectedConfiguration()
res["derived"] = dict(
    lengthAerodynamic=float(config.getLengthAerodynamic()),
    refLength=float(config.getReferenceLength()),
    nose_wet=float(nose.getComponentWetArea()), nose_plan=float(nose.getComponentPlanformArea()),
    nose_planCenter=float(nose.getComponentPlanformCenter()), nose_fullVolume=float(nose.getFullVolume()),
    body_wet=float(body.getComponentWetArea()), body_plan=float(body.getComponentPlanformArea()),
    fin_area=float(fins.getPlanformArea()), fin_span=float(fins.getSpan()),
    nose_r_at_0p99L=float(nose.getRadius(0.99 * GEOM["nose_len"])),
)
json.dump(res, open(out, "w"), indent=1)
print("wrote", out)
jpype.shutdownJVM()
