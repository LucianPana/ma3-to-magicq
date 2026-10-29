-- ma3-to-magicq: dump the loaded grandMA3 show for the converter.
--
-- Run inside grandMA3 onPC 2.x with the show loaded:
--   1. Menu > Show Creator > Plugins (or the Plugin pool): Import this file,
--      or type in the command line:  Lua "dofile('/full/path/ma3/dump_show.lua')"
--   2. The plugin writes everything under OUT_DIR (change it below if needed):
--        patch.xml, fixturetypes/*.xml, groups.xml, presets_<pool>.xml,
--        sequences.xml, pages.xml, macros.xml, timecodes.xml, layouts.xml,
--        dump.json  (patch addresses, cue list, DMX snapshot per cue)
--   3. Hand OUT_DIR to the converter:  python3 convert.py OUT_DIR show.shw
--
-- Nothing in the show is modified, but cues are played back to take the DMX
-- snapshots (every sequence is switched off first and at the end).

local OUT_DIR = os.getenv("HOME") .. "/ma3dump"
local SNAPSHOT_SETTLE = 0.30   -- seconds to wait after Goto before reading DMX
local MAX_CUES = 2000

local function log(fmt, ...) Printf("[ma3dump] " .. fmt, ...) end

local function mkdir(path)
  os.execute(string.format('mkdir -p "%s"', path))
end

local function jsonEscape(s)
  s = tostring(s)
  s = s:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n'):gsub('\r', '')
  return s
end

-- minimal JSON writer (tables with string keys = objects, integer keys = arrays)
local function toJson(v, indent)
  indent = indent or ""
  local t = type(v)
  if t == "nil" then return "null" end
  if t == "boolean" then return v and "true" or "false" end
  if t == "number" then
    if v ~= v or v == math.huge or v == -math.huge then return "null" end
    if math.type and math.type(v) == "integer" then return tostring(v) end
    return string.format("%.6g", v)
  end
  if t == "string" then return '"' .. jsonEscape(v) .. '"' end
  if t == "table" then
    local isArray = (#v > 0) or (next(v) == nil and v.__array)
    local parts = {}
    local ni = indent .. " "
    if isArray then
      for _, x in ipairs(v) do parts[#parts + 1] = ni .. toJson(x, ni) end
      if #parts == 0 then return "[]" end
      return "[\n" .. table.concat(parts, ",\n") .. "\n" .. indent .. "]"
    else
      local keys = {}
      for k in pairs(v) do if k ~= "__array" then keys[#keys + 1] = tostring(k) end end
      table.sort(keys)
      for _, k in ipairs(keys) do
        parts[#parts + 1] = ni .. '"' .. jsonEscape(k) .. '": ' .. toJson(v[k], ni)
      end
      if #parts == 0 then return "{}" end
      return "{\n" .. table.concat(parts, ",\n") .. "\n" .. indent .. "}"
    end
  end
  return '"' .. jsonEscape(tostring(v)) .. '"'
end

local function writeFile(path, text)
  local f, err = io.open(path, "w")
  if not f then log("cannot write %s: %s", path, tostring(err)); return false end
  f:write(text); f:close()
  return true
end

-- Export a pool or object with the Export keyword into OUT_DIR.
local function exportCmd(what, filename)
  local cmd = string.format('Export %s "%s" /Path="%s" /NoConfirm', what, filename, OUT_DIR)
  local ok, err = pcall(Cmd, cmd)
  if not ok then log("export failed: %s (%s)", cmd, tostring(err)) end
  return ok
end

-- Safe property read.
local function prop(obj, name)
  local ok, v = pcall(function() return obj[name] end)
  if ok and v ~= nil then return v end
  ok, v = pcall(function() return obj:Get(name) end)
  if ok then return v end
  return nil
end

local function children(obj)
  local ok, list = pcall(function() return obj:Children() end)
  if ok and list then return list end
  return {}
end

-- ---------------------------------------------------------------------------
-- Patch: walk every fixture (including sub fixtures) and record what the
-- converter needs even if the XML parser cannot cope with the patch export.
-- ---------------------------------------------------------------------------
local fixtures = {}
local fixtureTypesUsed = {}

local function addrToString(a)
  if a == nil then return nil end
  return tostring(a)
end

local function walkFixture(fx, depth)
  local fid = prop(fx, "FID")
  local entry = {
    name = prop(fx, "Name"),
    fid = fid,
    cid = prop(fx, "CID"),
    idtype = prop(fx, "IDType"),
    fixturetype = tostring(prop(fx, "FixtureType") or ""),
    mode = tostring(prop(fx, "DMXMode") or ""),
    patch = addrToString(prop(fx, "Patch")),
    address = prop(fx, "DMXAddress") and tostring(prop(fx, "DMXAddress")) or nil,
    posx = prop(fx, "PosX"), posy = prop(fx, "PosY"), posz = prop(fx, "PosZ"),
    rotx = prop(fx, "RotX"), roty = prop(fx, "RotY"), rotz = prop(fx, "RotZ"),
    color = prop(fx, "Color") and tostring(prop(fx, "Color")) or nil,
    layer = prop(fx, "Layer") and tostring(prop(fx, "Layer")) or nil,
    depth = depth,
  }
  -- the fixture type handle gives the file name used for the GDTF export
  local ok, ft = pcall(function() return fx.FixtureType end)
  if ok and ft then
    local ftname = prop(ft, "Name") or entry.fixturetype
    entry.fixturetype = tostring(ftname)
    entry.fixturetype_file = prop(ft, "File") and tostring(prop(ft, "File")) or nil
    fixtureTypesUsed[tostring(ftname)] = ft
  end
  fixtures[#fixtures + 1] = entry
  for _, sub in ipairs(children(fx)) do walkFixture(sub, depth + 1) end
end

local function dumpPatch()
  local ok, patch = pcall(Patch)
  if not ok or not patch then log("Patch() not available"); return end
  local stages = children(patch.Stages or patch)
  for _, stage in ipairs(stages) do
    local fixturesRoot = prop(stage, "Fixtures")
    if fixturesRoot then
      for _, fx in ipairs(children(fixturesRoot)) do walkFixture(fx, 0) end
    end
  end
  log("patch: %d fixture rows", #fixtures)
end

-- ---------------------------------------------------------------------------
-- Cue list and DMX snapshots.
-- ---------------------------------------------------------------------------
local function patchedAddresses()
  -- universe.address list of every patched DMX channel, from the fixture table
  local addrs = {}
  for _, fx in ipairs(fixtures) do
    if fx.patch and fx.patch ~= "" then addrs[#addrs + 1] = fx.patch end
  end
  return addrs
end

local function snapshotDMX(universes)
  -- Read every channel of the universes in use. GetDMXValue(addr, universe)
  -- returns the current output value (0..255) of one channel.
  local snap = {}
  for _, u in ipairs(universes) do
    local row = {}
    for a = 1, 512 do
      local ok, v = pcall(GetDMXValue, a, u, true)
      if not ok or v == nil then ok, v = pcall(GetDMXValue, a, u) end
      row[a] = (ok and v) or 0
    end
    snap[tostring(u)] = row
  end
  return snap
end

local function usedUniverses()
  local set, list = {}, {}
  for _, fx in ipairs(fixtures) do
    if fx.patch then
      local u = tonumber(tostring(fx.patch):match("^(%d+)%."))
      if u and not set[u] then set[u] = true; list[#list + 1] = u end
    end
  end
  table.sort(list)
  return list
end

local function dumpSequences(universes)
  local seqs = {}
  local ok, pool = pcall(function() return DataPool().Sequences end)
  if not ok or not pool then log("no sequence pool"); return seqs end
  local total = 0
  for _, seq in ipairs(children(pool)) do
    local sname = prop(seq, "Name")
    local sno = prop(seq, "No") or prop(seq, "Index")
    if sname and sname ~= "" then
      local cues = {}
      for _, cue in ipairs(children(seq)) do
        local cno = prop(cue, "No")
        local cname = prop(cue, "Name") or ""
        -- skip CueZero and OffCue, keep real cues
        if cno and tonumber(cno) and tonumber(cno) > 0 and cname ~= "OffCue" then
          local parts = {}
          for _, part in ipairs(children(cue)) do
            parts[#parts + 1] = {
              no = prop(part, "No"), name = prop(part, "Name"),
              fadein = prop(part, "CueInFade"), fadeout = prop(part, "CueOutFade"),
              delayin = prop(part, "CueInDelay"), delayout = prop(part, "CueOutDelay"),
            }
          end
          cues[#cues + 1] = {
            no = cno, name = cname,
            trigtype = prop(cue, "TrigType") and tostring(prop(cue, "TrigType")) or nil,
            trigtime = prop(cue, "TrigTime"),
            fadein = prop(cue, "CueInFade"), fadeout = prop(cue, "CueOutFade"),
            delayin = prop(cue, "CueInDelay"), delayout = prop(cue, "CueOutDelay"),
            parts = parts,
          }
        end
      end
      seqs[#seqs + 1] = { no = sno, name = sname, cues = cues }
      total = total + #cues
    end
  end
  log("sequences: %d with %d cues", #seqs, total)

  -- DMX snapshots: one per cue, each sequence alone, fades forced to zero.
  if total > MAX_CUES then log("too many cues for snapshots (%d), skipping", total); return seqs end
  pcall(Cmd, "Off Sequence Thru /NoConfirm")
  pcall(Cmd, "ClearAll")
  for _, s in ipairs(seqs) do
    for _, c in ipairs(s.cues) do
      pcall(Cmd, string.format("Goto Cue %s Sequence %s Fade 0", tostring(c.no), tostring(s.no)))
      coroutine.yield(SNAPSHOT_SETTLE)
      c.dmx = snapshotDMX(universes)
    end
    pcall(Cmd, string.format("Off Sequence %s /NoConfirm", tostring(s.no)))
    coroutine.yield(0.05)
  end
  pcall(Cmd, "Off Sequence Thru /NoConfirm")
  return seqs
end

local function dumpGroups()
  local groups = {}
  local ok, pool = pcall(function() return DataPool().Groups end)
  if not ok or not pool then return groups end
  for _, g in ipairs(children(pool)) do
    local name = prop(g, "Name")
    if name and name ~= "" then
      groups[#groups + 1] = { no = prop(g, "No"), name = name }
    end
  end
  return groups
end

local function dumpPresetPools()
  local pools = {}
  local ok, root = pcall(function() return DataPool().PresetPools end)
  if not ok or not root then return pools end
  for i, pool in ipairs(children(root)) do
    local pname = prop(pool, "Name") or tostring(i)
    local items = {}
    for _, p in ipairs(children(pool)) do
      local name = prop(p, "Name")
      if name and name ~= "" then
        local data = nil
        local okd, d = pcall(GetPresetData, p)
        if okd then data = d end
        items[#items + 1] = { no = prop(p, "No"), name = name, data = data }
      end
    end
    pools[#pools + 1] = { index = i, name = pname, presets = items }
    exportCmd(string.format("Preset %d.*", i), string.format("presets_%02d_%s", i, pname:gsub("[^%w]", "_")))
  end
  return pools
end

-- ---------------------------------------------------------------------------
local function main()
  mkdir(OUT_DIR)
  mkdir(OUT_DIR .. "/fixturetypes")
  log("writing to %s", OUT_DIR)

  dumpPatch()
  local universes = usedUniverses()

  -- XML exports (the converter parses these when they are present)
  exportCmd("Patch", "patch")
  exportCmd("Group *", "groups")
  exportCmd("Sequence *", "sequences")
  exportCmd("Page *", "pages")
  exportCmd("Macro *", "macros")
  exportCmd("Timecode *", "timecodes")
  exportCmd("Layout *", "layouts")
  for name, ft in pairs(fixtureTypesUsed) do
    local safe = name:gsub("[^%w%._-]", "_")
    local okx = pcall(function() ft:Export(OUT_DIR .. "/fixturetypes", safe .. ".xml") end)
    if not okx then exportCmd(string.format('FixtureType "%s"', name), "fixturetypes/" .. safe) end
    exportCmd(string.format('FixtureType "%s" /GDTF', name), "fixturetypes/" .. safe)
  end

  local groups = dumpGroups()
  local presets = dumpPresetPools()
  local sequences = dumpSequences(universes)

  local dump = {
    generator = "ma3-to-magicq dump_show.lua",
    version = tostring(Version and Version() or "?"),
    show = tostring(prop(Root().ShowData, "Name") or ""),
    universes = universes,
    fixtures = fixtures,
    groups = groups,
    presetpools = presets,
    sequences = sequences,
  }
  writeFile(OUT_DIR .. "/dump.json", toJson(dump))
  log("done: %d fixtures, %d groups, %d sequences", #fixtures, #groups, #sequences)
end

return main
