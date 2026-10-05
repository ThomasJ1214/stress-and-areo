"""
Minimal JPype driver for OpenRocket 23.09 (net.sf.openrocket) and 24.12 (info.openrocket.*).
Usage: python run_or.py <jar> <ork> [ork ...]  -> prints JSON per simulation, also writes CSV time series.

Written as a cross-validation feasibility test (not production code).
"""
import json
import os
import sys
import time

import jpype
import jpype.imports

jar = sys.argv[1]
orks = sys.argv[2:]
outdir = os.environ.get("OUTDIR", ".")

t0 = time.time()
jpype.startJVM(
    jpype.getDefaultJVMPath(),
    "-Djava.awt.headless=true",
    "-Xmx2g",
    f"-Djava.class.path={jar}",
    convertStrings=False,
)

# Detect package layout
JClass = jpype.JClass
try:
    JClass("info.openrocket.core.startup.Application")
    NEW = True
    core = "info.openrocket.core"
    gui_module_cls = "info.openrocket.swing.startup.GuiModule"
except Exception:
    NEW = False
    core = "net.sf.openrocket"
    gui_module_cls = "net.sf.openrocket.startup.GuiModule"

Guice = JClass("com.google.inject.Guice")
GuiModule = JClass(gui_module_cls)
PluginModule = JClass(core + ".plugin.PluginModule")
Application = JClass(core + ".startup.Application")
GeneralRocketLoader = JClass(core + ".file.GeneralRocketLoader")
FlightDataType = JClass(core + ".simulation.FlightDataType")
SimulationListener = JClass(core + ".simulation.listeners.SimulationListener")
JFile = JClass("java.io.File")

# Quiet logback
try:
    LoggerFactory = JClass("org.slf4j.LoggerFactory")
    Level = JClass("ch.qos.logback.classic.Level")
    root = LoggerFactory.getLogger("ROOT")
    root.setLevel(Level.ERROR)
except Exception as e:  # noqa
    print("logger setup failed:", e, file=sys.stderr)

gui_module = GuiModule()
plugin_module = PluginModule()
injector = Guice.createInjector(gui_module, plugin_module)
Application.setInjector(injector)
gui_module.startLoader()


def private_field(obj, name):
    f = obj.getClass().getDeclaredField(name)
    f.setAccessible(True)
    return f.get(obj)


private_field(gui_module, "presetLoader").blockUntilLoaded()
private_field(gui_module, "motorLoader").blockUntilLoaded()
print(f"# JVM + OpenRocket ({'info.openrocket' if NEW else 'net.sf.openrocket'}) started in {time.time()-t0:.1f}s",
      file=sys.stderr)

results = []
for ork in orks:
    doc = GeneralRocketLoader(JFile(ork)).load()
    sims = doc.getSimulations()
    for i in range(sims.size()):
        sim = sims.get(i)
        t1 = time.time()
        # Deterministic mode: zero wind + fixed seed (seed is NOT stored in .ork; it is random per load)
        if os.environ.get("NOWIND"):
            o = sim.getOptions()
            o.setWindSpeedAverage(0.0)
            o.setWindTurbulenceIntensity(0.0)
            o.setRandomSeed(42)
        if os.environ.get("TIMESTEP"):
            sim.getOptions().setTimeStep(float(os.environ["TIMESTEP"]))
        try:
            sim.simulate(jpype.JArray(SimulationListener)(0))
        except Exception as e:
            results.append({"ork": os.path.basename(ork), "sim": str(sim.getName()), "error": str(e)})
            continue
        dt = time.time() - t1
        fd = sim.getSimulatedData()
        opts = sim.getOptions()
        b = fd.getBranch(0)
        events = []
        for ev in b.getEvents():
            events.append((str(ev.getType()), round(float(ev.getTime()), 4)))
        r = {
            "ork": os.path.basename(ork),
            "sim": str(sim.getName()),
            "motor_config": str(opts.getFlightConfigurationId()) if hasattr(opts, "getFlightConfigurationId") else None,
            "max_altitude_m": float(fd.getMaxAltitude()),
            "max_velocity_mps": float(fd.getMaxVelocity()),
            "max_accel_mps2": float(fd.getMaxAcceleration()),
            "max_mach": float(fd.getMaxMachNumber()),
            "time_to_apogee_s": float(fd.getTimeToApogee()),
            "flight_time_s": float(fd.getFlightTime()),
            "ground_hit_velocity_mps": float(fd.getGroundHitVelocity()),
            "launch_rod_velocity_mps": float(fd.getLaunchRodVelocity()),
            "deployment_velocity_mps": float(fd.getDeploymentVelocity()),
            "optimum_delay_s": float(fd.getOptimumDelay()),
            "n_branches": int(fd.getBranchCount()),
            "n_points_branch0": int(b.getLength()),
            "sim_wall_time_s": round(dt, 3),
            "time_step_opt": float(opts.getTimeStep()),
            "wind_avg_opt": float(opts.getWindSpeedAverage()) if hasattr(opts, "getWindSpeedAverage") else None,
            "launch_rod_length_opt": float(opts.getLaunchRodLength()),
            "events": events,
            "warnings": [str(w) for w in fd.getWarningSet()],
        }
        # Dump a few time series to CSV
        cols = ["TYPE_TIME", "TYPE_ALTITUDE", "TYPE_VELOCITY_Z", "TYPE_VELOCITY_TOTAL", "TYPE_ACCELERATION_TOTAL",
                "TYPE_MACH_NUMBER", "TYPE_DRAG_COEFF", "TYPE_CP_LOCATION", "TYPE_CG_LOCATION", "TYPE_STABILITY",
                "TYPE_MASS", "TYPE_THRUST", "TYPE_DRAG_FORCE", "TYPE_AOA", "TYPE_REYNOLDS_NUMBER",
                "TYPE_FRICTION_DRAG_COEFF", "TYPE_PRESSURE_DRAG_COEFF", "TYPE_BASE_DRAG_COEFF",
                "TYPE_NORMAL_FORCE_COEFF", "TYPE_AIR_TEMPERATURE", "TYPE_AIR_PRESSURE", "TYPE_SPEED_OF_SOUND",
                "TYPE_TIME_STEP", "TYPE_LONGITUDINAL_INERTIA", "TYPE_ROTATIONAL_INERTIA", "TYPE_WIND_VELOCITY"]
        series = {}
        for c in cols:
            try:
                arr = b.get(getattr(FlightDataType, c))
                if arr is not None:
                    series[c] = [float(x) for x in arr]
            except Exception:
                pass
        safe = (os.path.basename(ork).replace(" ", "_").replace(".ork", "") + "__" +
                str(sim.getName()).replace(" ", "_").replace("/", "_"))
        tag = ("24.12" if NEW else "23.09") + os.environ.get("TAGSUFFIX", "")
        csvp = os.path.join(outdir, f"{tag}__{safe}.csv")
        keys = list(series.keys())
        n = len(series.get("TYPE_TIME", []))
        with open(csvp, "w") as fh:
            fh.write(",".join(keys) + "\n")
            for k in range(n):
                fh.write(",".join(f"{series[c][k]:.6g}" if k < len(series[c]) else "" for c in keys) + "\n")
        r["csv"] = csvp
        results.append(r)

print(json.dumps(results, indent=1))
jpype.shutdownJVM()
