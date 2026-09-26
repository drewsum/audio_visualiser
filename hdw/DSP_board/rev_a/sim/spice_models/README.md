# SPICE models: anti-alias filters, filtering PGAs, audio voltage references

All of these were tested in KiCad 10's bundled ngspice (ngspice-46).

| Part | File | Subckt(s) | Source |
|---|---|---|---|
| MCP604 (quad op amp) | `MCP601_MCP604.lib` | `MCP601`, `MCP604` | Microchip macromodel, Rev D (`MCP601_MM_D.txt`), plus a local quad wrapper |
| REF35160 (1.6 V reference) | `REF35.lib` | `REF35160_DBV`, `REF35160` (the file covers the whole REF35xxx family) | TI PSpice model SNAM287, v1.1, patched for ngspice (see below) |
| TS3A24159 (dual SPDT switch) | `TS3A24159.lib` | `TS3A24159`, `TS3A24159_PAD` | **Behavioral**, written from the datasheet (TI only offers an encrypted HSPICE model) |
| MCP4451 (quad digipot) | `MCP4451.lib` | `MCP4451`, `MCP44X1_POT` | **Behavioral**, written from the datasheet (Microchip offers no SPICE model) |

## Pin order (matches the KiCad symbol pin numbers 1:1)

- **MCP604**: `1 OUTA, 2 -INA, 3 +INA, 4 VDD, 5 +INB, 6 -INB, 7 OUTB, 8 OUTC, 9 -INC, 10 +INC, 11 VSS, 12 +IND, 13 -IND, 14 OUTD`
- **MCP601** (single, Microchip order): `+IN, -IN, V+, V-, OUT`
- **REF35160_DBV**: `1 GND, 2 GND, 3 EN, 4 VIN, 5 NR, 6 VREF`
- **TS3A24159**: `1 VCC, 2 NO1, 3 COM1, 4 IN1, 5 NC1, 6 GND, 7 NC2, 8 IN2, 9 COM2, 10 NO2` (use `TS3A24159_PAD` to add pin 11)
- **MCP4451**: TSSOP-20 order `1 P3A … 20 P2A`. Params: `RAB` (5k/10k/50k/100k), `RW` (default 75), `CODE0`..`CODE3` (0–256, 0 = wiper at B)
- **MCP44X1_POT**: `A W B`. Params: `RAB`, `CODE`, `RW`

In KiCad, set each symbol's Simulation Model to "SPICE model from file", point it at the `.lib`, and pick the subckt. Because the pin order matches the symbol, the default pin assignment is correct.

## Notes and limitations

- **MCP601/604**: typical values at 25 °C only. The model gives correct DC, AC, transient and noise results, but no temperature or process variation. Iq checks out at 230 µA per amplifier. An unused section with its inputs tied to a rail draws unrealistic current in the model, so tie unused sections as mid-supply buffers. Quad circuits can need ngspice's transient-op fallback to converge; ngspice does this automatically.
- **REF35.lib** has three edits to TI's file so ngspice can use it, all marked as local additions or renames:
  1. Added `.PARAM pi = ...`, because PSpice has `pi` built in and ngspice does not.
  2. Renamed the outer `Vref` param to `VrefSel` and gave `REF35XX_0` a literal default. The original parameter chain was circular under ngspice.
  3. Appended the 6-pin `REF35160_DBV` wrapper.

  Tested result: 1.5998 V DC. A large NR cap makes startup take tens of ms, which is expected.
- **TS3A24159 (behavioral)**:
  - Modeled: ron 0.26 Ω, datasheet C(OFF), C(ON) and CI capacitances, a switching threshold around 1 V, ~20 ns switching, and break-before-make.
  - Not modeled: ron flatness vs. signal, leakage, charge injection, THD.
  - Function: IN = L connects COM to NC, IN = H connects COM to NO.
- **MCP4451 (behavioral)**:
  - Modeled: a static resistor network with `RWB = RAB·N/256 + RW` and the datasheet's 75/120/75 pF terminal capacitances.
  - Not modeled: I2C (the wiper code is a simulation parameter), RW vs. voltage, INL/DNL, tempco.
  - The part number's `xxxx` isn't set in the schematic yet, so `RAB` defaults to 10k. Set it to match the part you choose.
