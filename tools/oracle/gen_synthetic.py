"""Generate a synthetic .ork (format 1.10) exercising shapes/components not present in the example files.
Writes a ZIP container (rocket.ork first entry) and a plain-XML twin."""

import os
import uuid
import zipfile

U = lambda: str(uuid.uuid4())
FG = '<material type="bulk" density="1850.0" group="Composites">Fiberglass</material>'
CB = '<material type="bulk" density="680.0" group="PaperProducts">Cardboard</material>'
PLA = '<material type="bulk" density="1250.0" group="Plastics">PLA</material>'
CFG = "b0000000-0000-4000-8000-000000000001"
xml = f'''<?xml version='1.0' encoding='utf-8'?>
<openrocket version="1.10" creator="synthetic-generator">
  <rocket>
    <name>Synthetic shapes</name><id>{U()}</id>
    <motorconfiguration configid="{CFG}" default="true"><stage number="0" active="true"/></motorconfiguration>
    <referencetype>maximum</referencetype>
    <subcomponents>
      <stage><name>Sustainer</name><id>{U()}</id>
        <subcomponents>
          <nosecone><name>Haack nose</name><id>{U()}</id><finish>smooth</finish>{FG}
            <length>0.3</length><thickness>0.002</thickness><shape>haack</shape><shapeclipped>true</shapeclipped>
            <shapeparameter>0.3333333333333333</shapeparameter><aftradius>auto 0.01</aftradius>
            <aftshoulderradius>0.038</aftshoulderradius><aftshoulderlength>0.06</aftshoulderlength>
            <aftshoulderthickness>0.002</aftshoulderthickness><aftshouldercapped>true</aftshouldercapped><isflipped>false</isflipped>
            <subcomponents>
              <masscomponent><name>Avionics</name><id>{U()}</id><axialoffset method="bottom">0.02</axialoffset>
                <packedlength>0.1</packedlength><packedradius>0.02</packedradius><radialposition>0.0</radialposition>
                <radialdirection>0.0</radialdirection><mass>0.25</mass><masscomponenttype>flightcomputer</masscomponenttype></masscomponent>
            </subcomponents>
          </nosecone>
          <bodytube><name>Upper tube</name><id>{U()}</id><finish>normal</finish>{FG}<length>0.6</length><thickness>0.002</thickness><radius>0.04</radius>
            <subcomponents>
              <parachute><name>Main</name><id>{U()}</id><axialoffset method="middle">0.0</axialoffset>
                <packedlength>0.12</packedlength><packedradius>auto 0.02</packedradius><radialposition>0.0</radialposition><radialdirection>0.0</radialdirection>
                <cd>auto</cd><material type="surface" density="0.067" group="Fabrics">Ripstop nylon</material>
                <deployevent>altitude</deployevent><deployaltitude>250.0</deployaltitude><deploydelay>0.0</deploydelay>
                <deploymentconfiguration configid="{CFG}"><deployevent>altitude</deployevent><deployaltitude>300.0</deployaltitude><deploydelay>0.5</deploydelay></deploymentconfiguration>
                <diameter>1.2</diameter><linecount>8</linecount><linelength>1.0</linelength>
                <linematerial type="line" density="0.0023" group="Threads">Nylon line</linematerial></parachute>
              <shockcord><name>Cord</name><id>{U()}</id><axialoffset method="top">0.02</axialoffset><packedlength>0.05</packedlength>
                <packedradius>0.02</packedradius><radialposition>0.0</radialposition><radialdirection>0.0</radialdirection>
                <cordlength>3.0</cordlength><material type="line" density="0.012" group="Threads">Kevlar</material></shockcord>
              <launchlug><name>Lug</name><id>{U()}</id><instancecount>2</instancecount><instanceseparation>0.2</instanceseparation>
                <angleoffset method="relative">45.0</angleoffset><axialoffset method="top">0.1</axialoffset><finish>normal</finish>{CB}
                <radius>0.0035</radius><length>0.05</length><thickness>0.0005</thickness></launchlug>
            </subcomponents></bodytube>
          <transition><name>Power boattail-ish reducer</name><id>{U()}</id><finish>normal</finish>{PLA}<length>0.1</length><thickness>0.0015</thickness>
            <shape>power</shape><shapeclipped>true</shapeclipped><shapeparameter>0.5</shapeparameter>
            <foreradius>auto 0.04</foreradius><aftradius>0.03</aftradius>
            <foreshoulderradius>0.038</foreshoulderradius><foreshoulderlength>0.04</foreshoulderlength><foreshoulderthickness>0.0015</foreshoulderthickness><foreshouldercapped>false</foreshouldercapped>
            <aftshoulderradius>0.0</aftshoulderradius><aftshoulderlength>0.0</aftshoulderlength><aftshoulderthickness>0.0</aftshoulderthickness><aftshouldercapped>false</aftshouldercapped></transition>
          <bodytube><name>Lower tube</name><id>{U()}</id><finish>normal</finish>{FG}<length>0.5</length><thickness>0.0015</thickness><radius>auto 0.01</radius>
            <subcomponents>
              <innertube><name>MMT cluster</name><id>{U()}</id><axialoffset method="bottom">0.0</axialoffset>{CB}<length>0.25</length>
                <radialposition>0.0</radialposition><radialdirection>0.0</radialdirection><outerradius>0.0095</outerradius><thickness>0.0005</thickness>
                <clusterconfiguration>3-ring</clusterconfiguration><clusterscale>1.1</clusterscale><clusterrotation>30.0</clusterrotation>
                <motormount><ignitionevent>automatic</ignitionevent><ignitiondelay>0.0</ignitiondelay><overhang>0.005</overhang>
                  <motor configid="{CFG}"><type>single</type><manufacturer>Estes</manufacturer><digest>c8743ef3fa99e14a89885cbe0ead47b2</digest>
                    <designation>C6</designation><diameter>0.018</diameter><length>0.07</length><delay>5.0</delay></motor></motormount></innertube>
              <centeringring><name>CR front</name><id>{U()}</id><instancecount>1</instancecount><instanceseparation>0.0</instanceseparation>
                <axialoffset method="bottom">-0.24</axialoffset>{CB}<length>0.005</length><radialposition>0.0</radialposition><radialdirection>0.0</radialdirection>
                <outerradius>auto</outerradius><innerradius>auto</innerradius></centeringring>
              <bulkhead><name>Bulkhead</name><id>{U()}</id><instancecount>2</instancecount><instanceseparation>0.01</instanceseparation>
                <axialoffset method="top">0.0</axialoffset>{CB}<length>0.004</length><radialposition>0.0</radialposition><radialdirection>0.0</radialdirection><outerradius>auto</outerradius></bulkhead>
              <ellipticalfinset><name>Elliptical fins</name><id>{U()}</id><instancecount>4</instancecount><fincount>4</fincount>
                <radiusoffset method="surface">0.0</radiusoffset><angleoffset method="relative">0.0</angleoffset><rotation>0.0</rotation>
                <axialoffset method="bottom">0.0</axialoffset><finish>normal</finish>{PLA}<thickness>0.003</thickness><crosssection>rounded</crosssection>
                <cant>0.0</cant><filletradius>0.005</filletradius>{FG.replace("material", "filletmaterial")}<rootchord>0.12</rootchord><height>0.07</height></ellipticalfinset>
              <railbutton><name>Buttons</name><id>{U()}</id><instancecount>2</instancecount><instanceseparation>0.3</instanceseparation>
                <angleoffset method="relative">180.0</angleoffset><axialoffset method="middle">0.0</axialoffset><finish>normal</finish>
                <material type="bulk" density="1420.0" group="Plastics">Delrin</material><outerdiameter>0.0097</outerdiameter><innerdiameter>0.008</innerdiameter>
                <height>0.0097</height><baseheight>0.002</baseheight><flangeheight>0.002</flangeheight><screwheight>0.0</screwheight></railbutton>
              <podset><name>Side pods</name><id>{U()}</id><instancecount>2</instancecount><radiusoffset method="free">0.07</radiusoffset>
                <angleoffset method="relative">90.0</angleoffset><axialoffset method="top">0.1</axialoffset>
                <subcomponents>
                  <bodytube><name>Pod tube</name><id>{U()}</id><finish>normal</finish>{CB}<length>0.2</length><thickness>0.001</thickness><radius>0.012</radius></bodytube>
                </subcomponents></podset>
            </subcomponents></bodytube>
        </subcomponents>
      </stage>
    </subcomponents>
  </rocket>
  <simulations>
    <simulation status="notsimulated"><name>Synthetic sim</name><simulator>RK4Simulator</simulator><calculator>BarrowmanCalculator</calculator>
      <conditions><configid>{CFG}</configid><launchrodlength>1.0</launchrodlength><launchintowind>false</launchintowind>
        <launchrodangle>5.0</launchrodangle><launchroddirection>45.0</launchroddirection>
        <wind model="average"><speed>3.0</speed><direction>0.0</direction><standarddeviation>0.0</standarddeviation></wind>
        <windmodeltype>Average</windmodeltype><launchaltitude>100.0</launchaltitude><launchlatitude>40.0</launchlatitude><launchlongitude>-105.0</launchlongitude>
        <geodeticmethod>spherical</geodeticmethod><atmosphere model="extendedisa"><basetemperature>300.0</basetemperature><basepressure>95000.0</basepressure></atmosphere>
        <timestep>0.01</timestep><maxtime>300.0</maxtime></conditions>
    </simulation>
  </simulations>
</openrocket>
'''
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples", "synthetic")
open(os.path.join(out, "synthetic_shapes_plain.ork"), "w").write(xml)
with zipfile.ZipFile(os.path.join(out, "synthetic_shapes.ork"), "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("rocket.ork", xml)
print("written")
