# MagicQ `.shw` format notes

Reverse-engineered on 2026-10-29 from MagicQ PC 1.9.7.4 (this Mac), two MQ50 shows (1.9.4 and 1.9.8.3) and the Chauvet demo (1.9.8.1). ChamSys does not document the format. Everything here was confirmed either by reading several files side by side or by writing a record by hand and having MagicQ PC load it and write it back (`scripts/mq_roundtrip.py`).

## Container

- Plain ASCII, comma-separated, numbers in hex without prefix unless noted. `\r\n` or `\n` line ends both occur.
- Header: comment lines starting with `\`, then one blank line.
- A record starts with a line `TAG,field,field,...` where TAG is one or more capitals optionally followed by digits (`V`, `T`, `P`, `L`, `H`, `F`, `G`, `W`, `S`, `C`, `M`, `N`, `E1`, ...) and runs until the next such line. Inside a record: continuation lines, blank lines, and lowercase sub-records (`u,`, `m,`, `j,`). `;` ends sub-blocks, it is not a reliable record terminator.
- Record order in files written by MagicQ: `V T Y Z... E1 P... L... H... F... G... W... S... C... X A B Q R... M N... M N... D J`. MagicQ tolerates a missing optional family, it does not tolerate a playback (`N`) without its page record (`M`) before it.
- `V,<fmt>,"MagicQ 1",<version>,...`: fmt `0091` is what 1.9.7.4 writes, `0093` 1.9.8.1, `0099` 1.9.8.3. MagicQ loads newer and older files alike and rewrites them in its own dialect.
- `T,"<path>",...` is the settings block (hundreds of fields, console settings and window state). Copied from a template, path patched.
- On load MagicQ writes the show back as `<name>.sbk` in the show folder within a second. Rejected files make MagicQ start a new, timestamp-named show. Both facts drive the round-trip harness.

## Addressing

Everything programming-related is keyed by the **absolute DMX channel**: `(universe - 1) * 512 + address`, hex. A head is identified by the channel of its first DMX slot. Group members, palette entries, cue values and FX entries all use this key.

## Records

### `P` personality (one per head type used)

```
P,<idx>,"<Manufacturer>_<Model>_<Mode>","<Manufacturer>","<Mode>","<Model>",
<nchans>,<nranges>,<npalettes>,<nmacros>,<pan deg>,<tilt deg>,0001,000x,<?>,<flags>,
"<chan name>",<type word>,<attr no>,        one per channel
<nchans>,<chan>,<default>,...                 defaults, pairs after the count
<chan>,"<range name>",<min>,<max>,<flags>,<icon>,   one per range
"<palette>",<type>,<?>,<icon>,<chan>,<val>,...      one per built-in palette
"<macro>",<n>, then n+1 short lines                  one per macro
... vis and library data (see a sample), ends with ;
```

The whole head definition is embedded, so a show is self-contained: the MagicQ head library is not needed to open it. Attribute numbers are the ones from the manual's Head Editor table (Intensity 0, Shutter 2, Iris 3, Pan 4, Tilt 5, Col1 6, Col2 7, Gobo1 8, Gobo2 9, Rotate1 10, Rotate2 11, Focus 12, Zoom 13, FX1 14, FX2 15, Cyan/Red 16, Magenta/Green 17, Yellow/Blue 18, White 19, Cont1 20, Cont2 21, Macro 22, CTC 24, CTO 25, Col Speed 26, Amber 27, Gobo3 28, Gobo4 29, Rotate3 30, Prism Rot 31, Frost1 32, Frost2 33, FX3..FX8 34..39, Beam Speed 40, Cont4..Cont8 41..45, Pos1..Pos5 46..50, Pos Speed 51, Frame1..8 52..59, Lime/UV 60, Col5 61, Col6 62).

Type words seen: `00000001` HTP 8-bit (dimmer), `00000012` LTP 8-bit fading, `00000022` LTP 8-bit instant (colour and gobo wheels), `00000036` LTP 16-bit coarse, `0000003a` LTP 16-bit fine, `00008012` LTP 8-bit with the 0x8000 flag (control channels such as Reset and Lamp).

### `L` channel (one per DMX slot of every patched head)

```
L,<abs chan>,"<head name>",<type word>,<P idx>,<offset in head>,0,ffff,0,0,<head number>,<n>,"",0,0,0,0,0,0,0,0,<gel/col?>,<?>,<?>,<rgb>,;
```

Dimmers written by 1.9.7.4 carry type word `1000001`. `<n>` is 0 for dimmers and 1 or 2 for moving heads in the samples; meaning not yet known, copied.

### `H` vis object (one per head plus one per 3D object)

`H,<id>,<kind>,...,"",<ref>,` then a line of seven obfuscated strings and a line of numbers. Kind 1 is the per-head entry, kind 2 a scene object (`20001,20.0,0.05,0.05,"Pipe 1"`). Whether MagicQ regenerates kind 1 entries when they are missing is still to be tested.

### `G` group

`G,<id>,"<name>",<count>,<abs chan>...,<flags>,` then `<flags2>,0,`, blank, `00000000,0,`, `0,`, a 10-field line, `;`. Flags seen `21000024`, `21000009`, `21000026` (low byte looks like an icon id).

### `F` palette

`F,<type><id>,"<name>",<count>,` then `count` triples `<abs chan>,<value>,<flag>` (flag 0, occasionally 1), then `<icon>`, `<?>`, `<?>`, a float line (colour palettes carry CIE x,y and 1.0 here), then a 64-row table of `a,b,c` per attribute number (colour palettes fill rows 16..19). Type nibble: `9` intensity, `a` position, `b` colour, `c` beam. Ids are 0-based within the type.

### `S` cue (Cue Store)

```
S,<id>,"<name>",<nvalues>,<nfx>,<?>,
<10 words>                                  all zero in plain cues, 0021 x5 in an FX cue
<abs chan>,<value>,...                      nvalues pairs, wrapped over several lines
<blank>
<FX block per FX>                           see below
<tail>                                      times and flags, template copied
```

Value: low byte is the 8-bit level; the upper bits reference the palette the value came from (`a00a69` = position palette 0x0a, level 0x69; `b00dff` = colour palette 0x0d, level 0xff). 16-bit attributes are two entries (coarse and fine channels). Confirmed by round trip: a cue with `1,80,2,ff,3,40` comes back unchanged.

FX block: `<fx type>,<nchans>,<W idx>,0000,0000,<size>,0000,<speed>,0001,0000,0000,0000,` then one line per channel `<abs chan>,<size>,0,<speed>,<part>,<offset>,<flags>`.

### `C` cue stack

```
C,<id>,"<name>",0000,<ncues>,<flags>,
<stack options>                             copied from the Y defaults: 000007d0,0042,003c x5,...
<next>,<prev>,<S id>,0000,<flags>,<cue number as float>,"<cue name>",   ncues lines, linked list order
... options, ends with the ;-line
```

Header flags `0000a01f` for a normal stack, `00078001`/`00060001`/`00078003` on chases. Cue-line flags `00006000` normal, `00007200` in chases. `003c` = 60 is the default fade (3.00 s in 1/20 s), `000007d0` = 2000 is likely the chase speed in ms. Per-cue times still to be located (candidates: the 10 words in `S`, the `S` tail).

### `M` page and `N` playback

`M,<page>,"<name>",00000001,0400,0300,...` then its playbacks: `N,<page>,<playback 0-based>,<flags>,<type>,<item 0-based>,00000000,<?>,"<legend>","",00000000,00000000,;`. Type 2 = cue stack (`C` index), 5 = group, 6 = colour palette (other palette types presumably 4/5/7 by family). Confirmed by round trip.

### `W` FX library

`W,<id>,"<name>",0001,<nparts>,<nsteps>,<flags>,<attr1>,<attr2>,<attr3>,<size>,<speed>,<?>,<?>,<?>,<?>,` then the step table (two columns per attribute), the part order, `03000001`, `00000002`, `0,0,0,0,;`. A pan/tilt circle: attrs 4 and 5, steps `80,00 / 00,80 / 80,ff / ff,80`.

### Others

`Y` and `Z` window layout, `E1` unknown header, `Q` and `R` grids and plan positions (`R,0065` is the rig plan: one `<abs chan>,0,0,0,<x>,<y>` row per head), `X`, `A`, `B`, `D`, `J` misc. All copied from the template or omitted.
