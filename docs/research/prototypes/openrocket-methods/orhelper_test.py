import sys, orhelper
from orhelper import FlightDataType, FlightEvent
jar, ork = sys.argv[1], sys.argv[2]
with orhelper.OpenRocketInstance(jar, log_level='ERROR') as instance:
    orh = orhelper.Helper(instance)
    doc = orh.load_doc(ork)
    sim = doc.getSimulations()[0]
    orh.run_simulation(sim)
    data = orh.get_timeseries(sim, [FlightDataType.TYPE_TIME, FlightDataType.TYPE_ALTITUDE, FlightDataType.TYPE_VELOCITY_Z])
    events = orh.get_events(sim)
    print("orhelper OK: max alt %.2f m, n=%d, events=%s" % (data[FlightDataType.TYPE_ALTITUDE].max(), len(data[FlightDataType.TYPE_TIME]), {str(k):v for k,v in events.items()}))
