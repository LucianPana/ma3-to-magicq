# Getting a show into grandMA3 (the MagicQ to grandMA3 direction)

Counterpart of `shw-format.md`. The grandMA3 `.show` file is binary and compressed with MA's own scheme (checked 2026-10-29: entropy 8.0 bits per byte, no known compression signatures, no names in clear), so the converter does not write it. It writes an **import package** (`show.json`, generated GDTF files, `report.md`) and a Lua plugin (`ma3/import_show.lua`) builds the show inside grandMA3 with ordinary commands. What the plugin relies on, and where that knowledge comes from:

## Facts used (grandMA3 2.3 help, shipped offline in `gma3_2.3.2/shared/language/HTML/`, and MA's own plugins)

- **Command line over OSC**: `/cmd` address with one string argument executes any command (`remote_inputs_osc.html`). Needs Menu > In & Out > OSC: Enable Input, and a configuration line (port 8000 UDP) with Receive Command = Yes. The OSC configuration is stored in the show file, not in a settings file, so a new show starts with it off. `scripts/ma3_osc.py` sends such messages; `scripts/ma3_import.py` runs the plugin this way and waits for `result.json`.
- **Exact DMX values**: `Attribute "Pan" At Absolute Decimal16 32768`, `At Absolute Decimal8 128` (`keyword_decimal8.html` and the Decimal16, Decimal24, Hex8, Hex16 pages). That is how every value is set, so the result does not depend on the fixture type's physical ranges.
- **Fixture types**: `Import Library "<name>"` with the command line destination at `ShowData/Patch/FixtureTypes` and the pool's `Source` property selecting the library (`grandMA3`, `grandMA2`, `User`), the way MA's system-test plugin does it (`shared/resource/lib_plugins/systemtests/requirements/gma3internal_fixtures.lua`). GDTF files are read from `gma3_library/fixturetypes` (`ft_import_gdtf.html`). The grandMA2 library ships as 10,507 encrypted `.pxml` files in `shared/lib_fixture_types/grandma2/`, named `manufacturer@model.pxml`.
- **Patching**: Lua `AddFixtures({mode=<DMXMode handle>, amount=1, fid="1", name="...", patch={"1.001"}})` with the command line destination at `Stages/Stage 1/Fixtures` (`lua_objectfree_addfixtures.html`, signature confirmed in the 2.3.2 binary). Fallback: the command recipe of `system_test_helping_functions_patch.lua` (`Store n /NC`, `Assign FixtureType "x" At n`, `Set n Property "FID"/"Name"/"Mode"/"Patch"`). `Patch Fixture 2 3.123` only re-addresses an existing fixture; MVR import is a Patch menu button with no command (`patch_mvr.html`).
- **Storing**: `Store Group n /NC`, `Store Preset pool.no /NC`, `Store Sequence s Cue c /NC`, `Store Sequence s Cue c Part p /NC`, names with `Label`. Preset pools: 1 Dimmer, 2 Position, 3 Gobo, 4 Color, 5 Beam, 6 Focus, 7 Control, 8 Shapers. A MagicQ palette becomes one preset per pool it touches, so a MagicQ beam palette with gobo and focus values becomes a Gobo preset and a Focus preset.
- **Cue timing**: `Set Sequence s Cue c Property "CueFade" 2.5` (the plugin tries `CueFade`/`Fade`, `CueOutFade`/`OutFade`, `CueDelay`/`Delay`, `CueOutDelay`/`OutDelay` and keeps what the console accepts). MagicQ position, colour and beam fades that differ from the intensity fade become cue parts 1 to 3 with their own fade. MagicQ chases become cues with `TrigType "Time"` and `TrigTime` = step time, fade 0.
- **Executors**: `Assign Sequence s At Page p.e` (fallback `Page p` then `Assign ... At Executor e`). MagicQ playbacks 1 to 10 go to executors 201 to 210 of the same page number; groups and palettes on playbacks go to 101 onward.

## What the plugin decides at run time

- Library match: each head in `show.json` carries up to three candidates found by name in the grandMA2 and user libraries (`ma3/libmatch.py`). The plugin imports a candidate, reads its DMX modes through the object tree (`DMXModes`, `DMXChannels`, `Coarse`/`Fine`, the logical channel's `Attribute`) and keeps it only when a mode has the same footprint and, at every MagicQ channel offset, the same byte width and the same attribute family (intensity, position, colour, other). Otherwise the imported type is deleted and the generated GDTF is used.
- The result goes to `result.json` (`counts`, `failed` with every refused command, `info` with the fixture type chosen per head) and `progress.log`.

## Open until the first run in onPC (2026-10-29)

Written against the documentation and MA's own plugin sources, syntax-checked with `luac`, and exercised offline with API stubs (`scripts/lua_dryrun.lua`, see `tests/test_ma3_package.py`). Not yet run inside grandMA3 onPC. To confirm there:

1. The exact `Import Library` spelling per source and the `Source` property values; whether a GDTF with custom (duplicate) attribute names imports.
2. The property names on `DMXChannel` objects (`Coarse`, `Fine`, `Attribute` or `LogicalChannels[1].Attribute`).
3. `AddFixtures` from a `dofile` chunk (the binary says it "cannot be invoked from this context" in some contexts; the plugin falls back to the command recipe).
4. Whether `Store Preset pool.no` keeps values of other feature groups (the package already splits them per pool).
5. Cue property names (`CueFade` vs `Fade`), `TrigType "Time"` for chases, `Tracking` on the sequence.
6. Executor assignment syntax with a page number.

Run order for the spike: `python3 convert_to_ma3.py out/demo.shw out/ma3_demo`, then `python3 scripts/ma3_import.py out/ma3_demo` with onPC open on a new show and OSC enabled; then compare `GetDMXValue` after `Goto` with the `S` records of the source (`scripts/ma3_compare.py`, to be written with the spike).
