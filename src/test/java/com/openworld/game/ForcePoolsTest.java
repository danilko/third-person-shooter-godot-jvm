package com.openworld.game;

import com.openworld.util.DataReader;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/** PLAN.md P1e step 3: forces held PER STATION, the tier ladder, and the restricted areas. */
class ForcePoolsTest {

    private static ForcePools fromData() throws Exception {
        return new ForcePools(ForcePools.read(DataReader.of(Files.readString(Path.of("src/main/resources/com/openworld/game/forces.json")))));
    }

    private static final List<ForcePools.PlaceRef> PLACES = List.of(
            new ForcePools.PlaceRef("Koban A", "Koban", null, 0, 0),
            new ForcePools.PlaceRef("Koban B", "Koban", null, 1000, 0),
            new ForcePools.PlaceRef("Central Police", "PoliceStation", null, 500, 500),
            new ForcePools.PlaceRef("Air Base", "Reserve_military_base", null, -600, 1300),
            new ForcePools.PlaceRef("A office", "GangOffice", "gang_a", 100, 100),
            new ForcePools.PlaceRef("A pachinko", "Pachinko", "gang_a", 200, 100),
            new ForcePools.PlaceRef("B office", "GangOffice", "gang_b", 900, 900),
            new ForcePools.PlaceRef("Konbini", "KonbiniS", null, 10, 10));

    @Test
    void everyStationHoldsItsOwnCount() throws Exception {
        ForcePools f = fromData();
        f.bind(PLACES);
        assertTrue(f.limited("police"));
        // the nearest koban answers first, and only it is debited
        ForcePools.Draw d = f.draw("police", 2, 10, 0);
        assertEquals("Koban A", d.station().place);
        assertEquals("police", d.tier().id());
        assertEquals(3, d.station().available());
        // emptied, the next nearest station of the same tier answers
        for (int i = 0; i < 3; i++) f.draw("police", 2, 10, 0);
        ForcePools.Draw next = f.draw("police", 2, 10, 0);
        assertEquals("Central Police", next.station().place, "the koban is empty: the station 700 m off answers");
    }

    @Test
    void aGangDrawsOnlyFromItsOwnPlaces() throws Exception {
        ForcePools f = fromData();
        f.bind(PLACES);
        for (ForcePools.Station st : f.stations())
            if (st.side.equals("gang_a")) assertTrue(st.place.startsWith("A "), st.place);
        ForcePools.Draw d = f.draw("gang_b", 3, 100, 100);
        assertEquals("B office", d.station().place, "gang_b never draws from gang_a's office next door");
        assertEquals(8, f.stations().stream().filter(s -> s.place.equals("A pachinko")).findFirst().orElseThrow().max,
                "a gang place of any kind holds the '*' count");
    }

    @Test
    void anEmptyTierEscalatesThenTheSideRests() throws Exception {
        ForcePools f = fromData();
        f.bind(PLACES);
        int police = 2 * 4 + 18, sf = 10, mil = 30;
        for (int i = 0; i < police; i++) assertEquals("police", f.draw("police", 3, 0, 0).tier().id());
        ForcePools.Draw esc = f.draw("police", 3, 0, 0);
        assertEquals("special_forces", esc.tier().id(), "police tier empty at 3 stars: special forces answer");
        assertEquals("special_force", esc.tier().outfit());
        for (int i = 1; i < sf; i++) f.draw("police", 3, 0, 0);
        assertEquals("military", f.draw("police", 3, 0, 0).tier().id(), "then the military");
        for (int i = 1; i < mil; i++) assertNotNull(f.draw("police", 3, 0, 0));
        assertNull(f.draw("police", 3, 0, 0), "the top is empty: nobody is sent");
        assertFalse(f.canDraw("police", 3, 1));
        assertEquals(75.0, f.emptyLull("police"));
        // regenerating: one body per regen_seconds at each station
        f.tick(90.0);
        assertTrue(f.canDraw("police", 3, 1));
    }

    @Test
    void fiveStarsStartAtSpecialForcesAndTheLivingGoBack() throws Exception {
        ForcePools f = fromData();
        f.bind(PLACES);
        ForcePools.Draw d = f.draw("police", 5, 500, 500);
        assertEquals("special_forces", d.tier().id());
        int before = d.station().available();
        f.giveBack(d.station());
        assertEquals(before + 1, d.station().available(), "a unit that leaves alive is back on hand");
        f.giveBack(d.station());
        assertEquals(d.station().max, d.station().available(), "never past the station's count");
    }

    @Test
    void noStationsMeansUnlimited() throws Exception {
        ForcePools f = fromData();
        f.bind(List.of());
        assertFalse(f.limited("police"));
        ForcePools.Draw d = f.draw("police", 5, 0, 0);
        assertNotNull(d);
        assertNull(d.station(), "an unlimited draw (DebugWorld has no places record)");
    }

    @Test
    void restrictedAreasWarnThenMakeItATrespass() throws Exception {
        List<RestrictedAreas.Area> areas = RestrictedAreas.read(DataReader.of(Files.readString(Path.of("src/main/resources/com/openworld/game/forces.json"))));
        assertEquals(3, areas.size());
        RestrictedAreas.Area base = RestrictedAreas.at(areas, -617.5, 1260.0);
        assertEquals("Air Base", base.name());
        assertFalse(RestrictedAreas.trespass(base, -617.5, 1260.0, 1.0), "just inside the fence: a warning first");
        assertTrue(RestrictedAreas.trespass(base, -617.5, 1260.0, 8.0), "still there after warn_seconds");
        assertTrue(RestrictedAreas.trespass(base, -617.5, 1347.0, 0.0), "deep inside at once");
        assertNull(RestrictedAreas.at(areas, 0, 0));
    }
}
