# SPICE models: anti-alias filters, filtering PGAs, audio voltage references

All of these were tested in KiCad 10's bundled ngspice (ngspice-46).

| Part | File | Subckt(s) | Source |
|---|---|---|---|
| MCP604 (quad op amp) | `MCP601_MCP604.lib` | `MCP601`, `MCP604` | Microchip macromodel, Rev D (`MCP601_MM_D.txt`), plus a local quad wrapper |
| REF35160 (1.6 V reference) | `REF35.lib` | `REF35160_DBV`, `REF35160` (the file covers the whole REF35xxx family) | TI PSpice model SNAM287, v1.1, patched for ngspice (see below) |
| TS3A24159 (dual SPDT switch) | `TS3A24159.lib` | `TS3A24159`, `TS3A24159_PAD` | **Behavioral**, written from the datasheet (TI only offers an encrypted HSPICE model) |
| MCP4451 (quad digipot) | `MCP4451.lib` | `MCP4451`, `MCP44X1_POT` | **Behavioral**, written from the datasheet (Microchip offers no SPICE model) |
| BAT54SW (dual series Schottky) | `BAT54SW.lib` | `BAT54SW_SOT323`, `BAT54SW` (single diode) | Nexperia model (`BAT54SW.txt`), plus a local series-pair wrapper |
| SD15C (15 V bidirectional TVS) | `SD15C.lib` | `SD15C` | **Behavioral**, fitted to the Littelfuse SD-C datasheet (Littelfuse's models aren't publicly downloadable) |

## Pin order (matches the KiCad symbol pin numbers 1:1)

- **MCP604**: `1 OUTA, 2 -INA, 3 +INA, 4 VDD, 5 +INB, 6 -INB, 7 OUTB, 8 OUTC, 9 -INC, 10 +INC, 11 VSS, 12 +IND, 13 -IND, 14 OUTD`
- **MCP601** (single, Microchip order): `+IN, -IN, V+, V-, OUT`
- **REF35160_DBV**: `1 GND, 2 GND, 3 EN, 4 VIN, 5 NR, 6 VREF`
- **TS3A24159**: `1 VCC, 2 NO1, 3 COM1, 4 IN1, 5 NC1, 6 GND, 7 NC2, 8 IN2, 9 COM2, 10 NO2` (use `TS3A24159_PAD` to add pin 11)
- **MCP4451**: TSSOP-20 order `1 P3A … 20 P2A`. U25 uses the QFN-20 (`-E/ML`) symbol, whose pin numbers differ, so its `Sim.Pins` maps by name: `19=P3A 20=P3W 1=P3B 2=HVC 3=SCL 4=SDA 5=VSS 6=P1B 7=P1W 8=P1A 9=P0A 10=P0W 11=P0B 12=NC 13=RESET 14=A1 15=VDD 16=P2B 17=P2W 18=P2A` (pin 21 = EP, not modelled). Params: `RAB` (5k/10k/50k/100k), `RW` (default 75), `CODE0`..`CODE3` (0–256, 0 = wiper at B)
- **MCP44X1_POT**: `A W B`. Params: `RAB`, `CODE`, `RW`
- **BAT54SW_SOT323**: `1 A, 2 K, 3 COM` (D1 A→COM, D2 COM→K). `BAT54SW` alone is one diode: `anode, cathode`
- **SD15C**: `1 A1, 2 A2` (symmetrical)

In KiCad, set each symbol's Simulation Model to "SPICE model from file", point it at the `.lib`, and pick the subckt. Because the pin order matches the symbol, the default pin assignment is correct.

## Notes and limitations

- **MCP601/604**: typical values at 25 °C only. The model gives correct DC, AC, transient and noise results, but no temperature or process variation. Iq checks out at 230 µA per amplifier. An unused section with its inputs tied to a rail draws unrealistic current in the model, so tie unused sections as mid-supply buffers.
  - Local addition: `R50` (1 MΩ) on the output-current sense node, which otherwise floats at low output current. Without it, ngspice's DC operating point fails for two or more cascaded MCP601s and falls back to transient-op. That lands on a false bias point, and AC then shows a fake low-pass because it's linearized around it. It also gives nonsense diode conductances elsewhere in the circuit. Iq, short-circuit current and open-loop gain are unchanged to within 0.3%. If a sim log ever shows "Transient op started", the `.op` and AC results can't be trusted.
- **REF35.lib** has three edits to TI's file so ngspice can use it, all marked as local additions or renames:
  1. Added `.PARAM pi = ...`, because PSpice has `pi` built in and ngspice does not.
  2. Renamed the outer `Vref` param to `VrefSel` and gave `REF35XX_0` a literal default. The original parameter chain was circular under ngspice.
  3. Appended the 6-pin `REF35160_DBV` wrapper.

  Tested result: 1.5998 V DC. A large NR cap makes startup take tens of ms, which is expected.
- **TS3A24159 (behavioral)**:
  - Modeled: ron 0.26 Ω, datasheet C(OFF), C(ON) and CI capacitances, a switching threshold around 1 V, ~20 ns switching, and break-before-make.
  - The switches are B-source conductances, not ngspice `SW` elements. KiCad's ngspice treats `SW` as open (ROFF) in `.ac` whatever its DC state, which blocked the signal in AC sims. No hysteresis.
  - Multi-unit symbol: use `TS3A24159_PAD` on all three units, with `Sim.Pins` `1=VCC 2=NO1 3=COM1 4=IN1 5=NC1 6=GND 7=NC2 8=IN2 9=COM2 10=NO2 11=PAD`. `TS3A24159_CH` is only for standalone tests. On a unit it drops the other channel and leaves the channel's GND pin unmapped.
  - The IN pins need a defined voltage (a source) in the sim. A floating IN gives a singular matrix.
  - Not modeled: ron flatness vs. signal, leakage, charge injection, THD.
  - Function: IN = L connects COM to NC, IN = H connects COM to NO.
- **MCP4451 (behavioral)**:
  - Modeled: a static resistor network with `RWB = RAB·N/256 + RW`, the datasheet's 75/120/75 pF terminal capacitances, and 1 GΩ terminal leakage to VSS (so unused or open sections don't leave floating nodes).
  - Not modeled: I2C (the wiper code is a simulation parameter), RW vs. voltage, INL/DNL, tempco.
  - The KiCad symbol is split into 5 units, but KiCad netlists all units of a reference as one SPICE instance. Use the full 20-pin `MCP4451` subckt on every unit, with identical `Sim.*` fields. `MCP44X1_POT` on a unit only picks up pins 1–3 (P3), and the other three pots are silently dropped.
  - U25 is an MCP4451-103 (`RAB=10k`). Set per-pot wiper positions with `CODE0`..`CODE3` in the symbol's Simulation Model parameters.
- **BAT54SW**: Nexperia's file header lists common-cathode pinning; that's a copy error in their file, and the `BAT54SW_SOT323` wrapper uses the real series pinout. Tested: 0.61 V at 100 mA, 0.9 µA at 25 V reverse; as a 3.3 V rail clamp through 1k it holds 6 V to 3.55 V and −3 V to −0.26 V.
- **SD15C (behavioral)**: two anti-series junctions with a soft breakdown knee (`NBV`) fitted to the datasheet. Tested: 18.4 V at 1 mA (spec ≥16.7 V), 0.4 µA at 15 V (spec ≤1 µA), 22.3 V at 1 A and 30.3 V at 10 A (spec ≤24 V / ≤31 V), 75 pF at 0 V dropping to 37 pF at 12 V (spec 75 pF max). No self-heating, temperature or ESD turn-on dynamics.
