import info.openrocket.core.startup.OpenRocketCore;
import info.openrocket.core.file.GeneralRocketLoader;
import info.openrocket.core.document.OpenRocketDocument;
import info.openrocket.core.document.Simulation;
import info.openrocket.core.rocketcomponent.*;
import info.openrocket.core.masscalc.MassCalculator;
import info.openrocket.core.masscalc.RigidBody;
import info.openrocket.core.aerodynamics.BarrowmanCalculator;
import info.openrocket.core.aerodynamics.FlightConditions;
import info.openrocket.core.logging.WarningSet;
import info.openrocket.core.util.Coordinate;
import info.openrocket.core.simulation.FlightData;
import java.io.File;
import java.util.*;

/** Headless probe: prints OpenRocket 24.12's own full-precision geometry / mass / CP numbers. */
public class ORProbe {
    static String f(double d) { return String.format(Locale.ROOT, "%.9g", d); }
    public static void main(String[] args) throws Exception {
        boolean resim = System.getProperty("resim") != null;
        OpenRocketCore.initialize(new info.openrocket.core.plugin.PluginModule(),
            (com.google.inject.Module) binder -> binder.bind(info.openrocket.core.database.ComponentPresetDao.class)
                    .to(info.openrocket.core.database.ComponentPresetDatabase.class));
        List<String> paths = new ArrayList<>();
        for (String a : args) {
            if (a.startsWith("@")) paths.addAll(java.nio.file.Files.readAllLines(java.nio.file.Path.of(a.substring(1))));
            else paths.add(a);
        }
        for (String path : paths) {
          try {
            OpenRocketDocument doc = new GeneralRocketLoader(new File(path)).load();
            Rocket rocket = doc.getRocket();
            System.out.println("FILE\t" + path);
            int idx = 0;
            for (RocketComponent c : rocket) {
                StringBuilder sb = new StringBuilder();
                sb.append("COMP\t").append(idx++).append('\t').append(c.getClass().getSimpleName()).append('\t')
                  .append(c.getName().replace('\t',' ')).append('\t').append(f(c.getComponentLocations()[0].x))
                  .append('\t').append(f(c.getLength())).append('\t').append(c.getInstanceCount());
                if (c instanceof SymmetricComponent s) sb.append("\tfore=").append(f(s.getForeRadius())).append("\taft=").append(f(s.getAftRadius()));
                if (c instanceof RingComponent r) sb.append("\tro=").append(f(r.getOuterRadius())).append("\tri=").append(f(r.getInnerRadius()));
                if (c instanceof TubeFinSet t) sb.append("\tro=").append(f(t.getOuterRadius()));
                if (c instanceof FinSet fs) sb.append("\tbodyr=").append(f(fs.getBodyRadius()));
                Coordinate cg = c.getComponentCG();
                sb.append("\tcompmass=").append(f(c.getComponentMass())).append("\tcompcgx=").append(f(cg.x));
                System.out.println(sb);
            }
            for (int i = 0; i < doc.getSimulationCount(); i++) {
                Simulation sim = doc.getSimulation(i);
                FlightConfiguration cfg = rocket.getFlightConfiguration(sim.getFlightConfigurationId());
                RigidBody st = MassCalculator.calculateStructure(cfg);
                RigidBody la = MassCalculator.calculateLaunch(cfg);
                FlightConditions fc = new FlightConditions(cfg);
                fc.setMach(0.3); fc.setAOA(0.0);
                Coordinate cp = new BarrowmanCalculator().getCP(cfg, fc, new WarningSet());
                System.out.println("SIM\t" + i + "\t" + sim.getName() + "\tstructMass=" + f(st.getMass()) + "\tstructCG=" + f(st.getCM().x)
                        + "\tlaunchMass=" + f(la.getMass()) + "\tlaunchCG=" + f(la.getCM().x) + "\tCP(M0.3)=" + f(cp.x)
                        + "\tCNa=" + f(cp.weight) + "\trefLen=" + f(cfg.getReferenceLength()) + "\tlength=" + f(cfg.getLength()));
                if (resim && i == 0) {
                    FlightData old = sim.getSimulatedData();
                    double oldApo = old == null ? Double.NaN : old.getMaxAltitude();
                    sim.getOptions().getAverageWindModel().setTurbulenceIntensity(sim.getOptions().getAverageWindModel().getTurbulenceIntensity());
                    sim.simulate();
                    FlightData d = sim.getSimulatedData();
                    System.out.println("RESIM\t" + i + "\tstoredApogee=" + f(oldApo) + "\tnewApogee=" + f(d.getMaxAltitude())
                            + "\tnewMaxV=" + f(d.getMaxVelocity()) + "\tnewTtA=" + f(d.getTimeToApogee()));
                }
            }
            if (System.getProperty("resave") != null) {
                java.io.File out = new java.io.File(path + ".resaved.ork");
                new info.openrocket.core.file.GeneralRocketSaver().save(out, doc);
                System.out.println("RESAVED\t" + out);
            }
            if (System.getProperty("simall") != null) {
                for (int i = 0; i < doc.getSimulationCount(); i++) {
                    Simulation sim = doc.getSimulation(i);
                    sim.simulate();
                    FlightData d = sim.getSimulatedData();
                    System.out.println("SIMRUN\t" + i + "\tapogee=" + f(d.getMaxAltitude()) + "\tmaxV=" + f(d.getMaxVelocity())
                        + "\tmaxMach=" + f(d.getMaxMachNumber()) + "\ttApogee=" + f(d.getTimeToApogee()) + "\tflightTime=" + f(d.getFlightTime())
                        + "\trodV=" + f(d.getLaunchRodVelocity()) + "\tgroundV=" + f(d.getGroundHitVelocity()) + "\twarnings=" + d.getWarningSet().size());
                }
            }
          } catch (Throwable t) { System.out.println("ERROR\t" + path + "\t" + t); }
        }
        System.exit(0);
    }
}
