-- ma3-to-magicq, the way back: build a grandMA3 show from a package written by
-- convert_to_ma3.py (show.json + fixturetypes/*.gdtf).
--
-- Run inside grandMA3 onPC 2.x with a NEW, EMPTY show loaded:
--   Lua "dofile('/full/path/ma3/import_show.lua')('/full/path/to/package')"
-- or over OSC with scripts/ma3_import.py. Progress goes to progress.log and the
-- System Monitor, the outcome to result.json in the package folder.
--
-- Everything is done with ordinary commands (Import, Store, At, Set, Assign)
-- plus the documented Lua AddFixtures(); nothing is written into the show file
-- directly, so the result is a normal show you save from grandMA3.

local VERSION = "0.2"

-- ---------------------------------------------------------------------------
-- small JSON reader (objects -> tables with string keys, arrays -> 1-based)
-- ---------------------------------------------------------------------------
local json = {}
do
  local function skip(s, i)
    local _, e = s:find("^[ \n\r\t]*", i)
    return e + 1
  end
  local parseValue
  local function parseString(s, i)
    local out, j = {}, i + 1
    while true do
      local c = s:sub(j, j)
      if c == "" then error("unterminated string") end
      if c == '"' then return table.concat(out), j + 1 end
      if c == "\\" then
        local n = s:sub(j + 1, j + 1)
        local map = { ['"'] = '"', ["\\"] = "\\", ["/"] = "/", b = "\b", f = "\f", n = "\n", r = "\r", t = "\t" }
        if n == "u" then
          local hex = s:sub(j + 2, j + 5)
          local cp = tonumber(hex, 16) or 63
          if cp < 128 then out[#out + 1] = string.char(cp)
          elseif cp < 2048 then out[#out + 1] = string.char(192 + math.floor(cp / 64), 128 + cp % 64)
          else out[#out + 1] = string.char(224 + math.floor(cp / 4096), 128 + math.floor(cp / 64) % 64, 128 + cp % 64) end
          j = j + 6
        else
          out[#out + 1] = map[n] or n
          j = j + 2
        end
      else
        out[#out + 1] = c
        j = j + 1
      end
    end
  end
  local function parseArray(s, i)
    local arr, j = {}, skip(s, i + 1)
    if s:sub(j, j) == "]" then return arr, j + 1 end
    while true do
      local v
      v, j = parseValue(s, j)
      arr[#arr + 1] = v
      j = skip(s, j)
      local c = s:sub(j, j)
      if c == "]" then return arr, j + 1 end
      if c ~= "," then error("expected , in array at " .. j) end
      j = skip(s, j + 1)
    end
  end
  local function parseObject(s, i)
    local obj, j = {}, skip(s, i + 1)
    if s:sub(j, j) == "}" then return obj, j + 1 end
    while true do
      if s:sub(j, j) ~= '"' then error("expected key at " .. j) end
      local k
      k, j = parseString(s, j)
      j = skip(s, j)
      if s:sub(j, j) ~= ":" then error("expected : at " .. j) end
      local v
      v, j = parseValue(s, skip(s, j + 1))
      obj[k] = v
      j = skip(s, j)
      local c = s:sub(j, j)
      if c == "}" then return obj, j + 1 end
      if c ~= "," then error("expected , in object at " .. j) end
      j = skip(s, j + 1)
    end
  end
  parseValue = function(s, i)
    i = skip(s, i)
    local c = s:sub(i, i)
    if c == "{" then return parseObject(s, i) end
    if c == "[" then return parseArray(s, i) end
    if c == '"' then return parseString(s, i) end
    if s:sub(i, i + 3) == "true" then return true, i + 4 end
    if s:sub(i, i + 4) == "false" then return false, i + 5 end
    if s:sub(i, i + 3) == "null" then return nil, i + 4 end
    local num = s:match("^-?%d+%.?%d*[eE]?[-+]?%d*", i)
    if num and #num > 0 then return tonumber(num), i + #num end
    error("unexpected character '" .. c .. "' at " .. i)
  end
  function json.decode(s)
    local v = parseValue(s, 1)
    return v
  end
end

-- ---------------------------------------------------------------------------
-- helpers
-- ---------------------------------------------------------------------------
local function jsonEscape(s)
  s = tostring(s)
  return (s:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n'):gsub('\r', ''))
end

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
    local isArray = (#v > 0) or (next(v) == nil)
    local parts, ni = {}, indent .. " "
    if isArray then
      for _, x in ipairs(v) do parts[#parts + 1] = ni .. toJson(x, ni) end
      if #parts == 0 then return "[]" end
      return "[\n" .. table.concat(parts, ",\n") .. "\n" .. indent .. "]"
    end
    local keys = {}
    for k in pairs(v) do keys[#keys + 1] = tostring(k) end
    table.sort(keys)
    for _, k in ipairs(keys) do parts[#parts + 1] = ni .. '"' .. jsonEscape(k) .. '": ' .. toJson(v[k], ni) end
    return "{\n" .. table.concat(parts, ",\n") .. "\n" .. indent .. "}"
  end
  return '"' .. jsonEscape(tostring(v)) .. '"'
end

local function readFile(path)
  local f = io.open(path, "r")
  if not f then return nil end
  local s = f:read("a")
  f:close()
  return s
end

local function writeFile(path, text)
  local f = io.open(path, "w")
  if not f then return false end
  f:write(text)
  f:close()
  return true
end

local function fileExists(path)
  local f = io.open(path, "r")
  if f then f:close() return true end
  return false
end

local function q(s)
  return '"' .. tostring(s):gsub('"', "'") .. '"'
end

local function fmtnum(x)
  if x == nil then return "0" end
  if type(x) ~= "number" then return tostring(x) end
  if math.type and math.type(x) == "integer" then return tostring(x) end
  if x == math.floor(x) then return string.format("%d", x) end
  return (string.format("%.3f", x):gsub("0+$", ""):gsub("%.$", ""))
end

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

local function count(obj)
  local ok, n = pcall(function() return obj:Count() end)
  if ok and n then return n end
  return #children(obj)
end

-- ---------------------------------------------------------------------------
-- the importer
-- ---------------------------------------------------------------------------
return function(dir)
  local t0 = os.clock()
  dir = tostring(dir or ""):gsub("/+$", "")
  local LOG = dir .. "/progress.log"
  writeFile(LOG, "")
  local result = { counts = {}, failed = {}, info = {}, version = VERSION }

  local function log(fmt, ...)
    local msg = string.format(fmt, ...)
    pcall(Printf, "[mq2ma3] " .. msg)
    local f = io.open(LOG, "a")
    if f then f:write(msg, "\n") f:close() end
  end

  local function dmxCheck(label)
    local ok, v = pcall(GetDMXValue, 1)
    log("dmx read-back after %s: %s", label, ok and tostring(v) or ("error " .. tostring(v)))
  end

  local function finish()
    result.seconds = os.clock() - t0
    writeFile(dir .. "/result.json", toJson(result))
    log("done in %.1f s, %d failed commands", result.seconds, #result.failed)
  end

  -- Run a command; remember the ones the console refused.
  local function cmd(fmt, ...)
    local c = select("#", ...) > 0 and string.format(fmt, ...) or fmt
    local ok, ret = pcall(Cmd, c)
    local r = tostring(ret or "")
    if not ok then
      result.failed[#result.failed + 1] = { cmd = c, err = tostring(ret) }
      return false, r
    end
    if r:find("Error") or r:find("Illegal") or r:find("rror") then
      result.failed[#result.failed + 1] = { cmd = c, err = r }
      return false, r
    end
    return true, r
  end

  -- Try several spellings of a command, keep the first the console accepts.
  local function cmdTry(variants)
    for _, c in ipairs(variants) do
      local ok, ret = pcall(Cmd, c)
      local r = tostring(ret or "")
      if ok and not (r:find("Error") or r:find("Illegal") or r:find("rror")) then
        return true, c
      end
    end
    result.failed[#result.failed + 1] = { cmd = variants[1], err = "all variants refused", variants = variants }
    return false
  end

  local text = readFile(dir .. "/show.json")
  if not text then
    log("cannot read %s/show.json", dir)
    finish()
    return
  end
  local ok, show = pcall(json.decode, text)
  if not ok then
    log("show.json does not parse: %s", tostring(show))
    finish()
    return
  end
  log("package %s: %d heads, %d fixtures, %d groups, %d presets, %d sequences", show.name or "?",
      #(show.heads or {}), #(show.fixtures or {}), #(show.groups or {}), #(show.presets or {}), #(show.sequences or {}))

  local okBody, errBody = pcall(function()

  local HOME = os.getenv("HOME") or ""
  local userFixtures = nil
  pcall(function() userFixtures = GetPath(Enums.PathType.UserFixtures) end)
  if not userFixtures or userFixtures == "" then
    pcall(function() userFixtures = GetPath("fixturetypes") end)
  end
  if not userFixtures or userFixtures == "" then
    userFixtures = HOME .. "/MALightingTechnology/gma3_library/fixturetypes"
  end
  local grandma2 = nil
  pcall(function() grandma2 = GetPath(Enums.PathType.Library) end)
  log("user fixture type folder: %s", tostring(userFixtures))

  -- ------------------------------------------------------------------ heads
  -- family of a grandMA3 attribute name, coarse enough to compare with MagicQ
  local function famOf(name)
    name = tostring(name or "")
    if name:match("^Dimmer") and name ~= "DimmerMode" and name ~= "DimmerCurve" then return "int" end
    if name == "Pan" or name == "Tilt" or name:match("^Position") or name:match("^XYZ") or name:match("Rotate$") and name:match("^[PT]") then return "pos" end
    if name:match("^Color") or name:match("^CT[OCB]") or name:match("^HSB") or name == "Tint" then return "col" end
    return "beam"
  end

  -- the edit patch (ShowData.Patch) is where imports and patching happen; the live patch follows on "cd Root"
  local function editFT() return Root().ShowData.Patch.FixtureTypes end
  local function editFixtures() return Root().ShowData.Patch.Stages[1].Fixtures end
  local function ftNames(pool)
    local t = {}
    for _, ft in ipairs(children(pool)) do t[#t + 1] = tostring(prop(ft, "Name")) end
    return t
  end
  -- One edit-patch session for imports and patching: leaving it ("cd Root") commits the patch and
  -- invalidates every handle taken inside it, so handles are never kept across a "cd Root".
  local inPatch = false
  local function enterPatch()
    if inPatch then return end
    pcall(Cmd, "cd Root")
    pcall(Cmd, "cd 'ShowData'.'Patch'")
    inPatch = true
  end
  local function leavePatch()
    pcall(Cmd, "cd Root")
    inPatch = false
  end

  -- describe a fixture type's DMX modes: {{handle=, name=, footprint=, chans={[offset]={fam=, bytes=}}}, ...}
  local function describeModes(ft)
    local modes = {}
    for _, mode in ipairs(children(prop(ft, "DMXModes") or {})) do
      local info = { handle = mode, name = tostring(prop(mode, "Name") or ""), footprint = 0, chans = {} }
      for _, dch in ipairs(children(prop(mode, "DMXChannels") or {})) do
        local coarse = tonumber(prop(dch, "Coarse")) or 0
        local fine = tonumber(prop(dch, "Fine")) or 0
        local ultra = tonumber(prop(dch, "Ultra")) or 0
        local lcs = children(dch)
        local attr = tostring((lcs[1] and prop(lcs[1], "Attribute")) or prop(dch, "Attribute") or "")
        attr = attr:match("([%w_]+)$") or attr
        local bytes = (fine > 0 and 2 or 1)
        if ultra > 0 then bytes = 3 end
        if coarse > 0 then
          info.chans[coarse] = { fam = famOf(attr), bytes = bytes, attr = attr }
          info.footprint = math.max(info.footprint, coarse, fine, ultra)
        end
      end
      modes[#modes + 1] = info
    end
    return modes
  end

  local function modeMatches(info, head)
    if info.footprint ~= head.footprint then return false, "footprint " .. info.footprint end
    for _, c in ipairs(head.channels) do
      local m = info.chans[c.offset]
      if not m then return false, "no channel at offset " .. c.offset end
      if m.bytes ~= c.bytes then return false, string.format("offset %d is %d bytes, MagicQ has %d", c.offset, m.bytes, c.bytes) end
      local fam = c.group == "Dimmer" and "int" or (c.group == "Position" and "pos" or (c.group == "Color" and "col" or "beam"))
      if m.fam ~= fam then return false, string.format("offset %d is %s (%s), MagicQ has %s", c.offset, m.attr, m.fam, fam) end
    end
    return true
  end

  local libraryScanned = {}
  -- import one library file into the fixture type pool; returns (handle, index) of the new type or nil
  local function importLibrary(source, file)
    local before = #ftNames(editFT())
    local name = file:gsub("%.pxml$", ""):gsub("%.xml$", "")
    local src = (source == "grandma2") and "grandMA2" or ((source == "grandma3") and "grandMA3" or "User")
    local lib = (source == "user") and file or name
    enterPatch()
    cmd('Set "FixtureTypes" Source="%s"', src)
    pcall(Cmd, "cd 'FixtureTypes'")
    if source ~= "user" and not libraryScanned[src] then
      -- the shipped libraries are scanned on first use; give the scan a moment (Call Library toggles, so once only)
      pcall(Cmd, "Call Library")
      local t0 = os.clock()
      while os.clock() - t0 < 1.5 do end
      libraryScanned[src] = true
    end
    local okI = cmd('Import Library %s', q(lib))
    if not okI or #ftNames(editFT()) == before then
      local t0 = os.clock()
      while os.clock() - t0 < 1.0 do end
      cmd('Import Library %s', q(lib))
    end
    pcall(Cmd, "cd Root 'ShowData'.'Patch'")
    local after = ftNames(editFT())
    if #after > before then
      return children(editFT())[#after], #after
    end
    return nil
  end

  local function renameFixtureType(idx, name)
    enterPatch()
    pcall(Cmd, "cd 'FixtureTypes'")
    cmd("Set %d Property 'Name' %s", idx, q(name))
    pcall(Cmd, "cd Root 'ShowData'.'Patch'")
  end

  local function deleteFixtureType(idx)
    enterPatch()
    local before = #ftNames(editFT())
    pcall(Cmd, "cd 'FixtureTypes'")
    pcall(Cmd, string.format("Delete %d /NC", idx))
    if #ftNames(editFT()) == before then pcall(Cmd, string.format("Delete FixtureType %d /NC", idx)) end
    pcall(Cmd, "cd Root 'ShowData'.'Patch'")
    return #ftNames(editFT()) < before
  end

  local headMode = {}      -- head key -> {ft=, mode=, source=}
  for _, head in ipairs(show.heads or {}) do
    local chosen = nil
    for _, cand in ipairs(head.candidates or {}) do
      local source, file = cand:match("^(%w+):(.+)$")
      if source then
        local ft, ftIndex = importLibrary(source, file)
        if ft then
          local modes = describeModes(ft)
          local why = {}
          for _, info in ipairs(modes) do
            local okm, reason = modeMatches(info, head)
            if okm then
              chosen = { ftIndex = ftIndex, modeName = info.name, source = cand }
              break
            end
            why[#why + 1] = info.name .. ": " .. tostring(reason)
          end
          if chosen then
            log("head %s: library %s mode '%s' matches channel for channel", head.key, cand, chosen.modeName)
            break
          end
          local removed = deleteFixtureType(ftIndex)
          log("head %s: library %s does not line up (%s)%s", head.key, cand, table.concat(why, "; "), removed and ", removed" or ", left in the pool")
        else
          log("head %s: could not import library candidate %s", head.key, cand)
        end
      end
    end
    if not chosen then
      local src = dir .. "/fixturetypes/" .. head.gdtf
      local dst = userFixtures .. "/" .. head.gdtf
      local copied = false
      pcall(function() copied = CopyFile(src, dst) end)
      if not fileExists(dst) then
        os.execute(string.format('cp "%s" "%s"', src, dst))
      end
      pcall(RefreshLibrary)
      local ft, ftIndex = importLibrary("user", head.gdtf)
      if ft then
        local modes = describeModes(ft)
        local mode = modes[1]
        for _, info in ipairs(modes) do
          if info.name == head.mode_name then mode = info end
        end
        chosen = { ftIndex = ftIndex, modeName = mode and mode.name or "", source = "generated " .. head.gdtf }
        renameFixtureType(ftIndex, "MQ " .. head.key)
        log("head %s: generated GDTF imported as fixture type %d", head.key, ftIndex)
      else
        log("head %s: GDTF import failed, fixtures of this head skipped", head.key)
        result.failed[#result.failed + 1] = { cmd = "import " .. head.gdtf, err = "no fixture type appeared" }
      end
    end
    headMode[head.key] = chosen
    result.info[#result.info + 1] = { head = head.key, source = chosen and chosen.source or "none", mode = chosen and chosen.modeName or "" }
  end
  result.counts.fixture_types = #ftNames(editFT())
  dmxCheck("fixture types")

  -- --------------------------------------------------------------- fixtures
  -- the recipe MA's own system tests use: Store an entry in Stage 1, assign the type, set the properties
  local patched = 0
  local fidOk = {}
  enterPatch()
  local function modeHandle(ftIndex, modeName)
    local ft = children(editFT())[ftIndex]
    if not ft then return nil end
    local modes = children(prop(ft, "DMXModes") or {})
    for _, m in ipairs(modes) do
      if tostring(prop(m, "Name")) == modeName then return m end
    end
    return modes[1]
  end
  pcall(Cmd, "cd 'Stages'.'Stage 1'.'Fixtures'")
  local nextIndex = #children(editFixtures()) + 1
  for _, fx in ipairs(show.fixtures or {}) do
    local hm = headMode[fx.head]
    if hm then
      local n = nextIndex
      local okStore = cmd('Store %d /NC', n)
      if okStore then
        nextIndex = nextIndex + 1
        cmd("Assign FixtureType %d At %d", hm.ftIndex, n)
        cmd("Set %d Property 'FID' %s", n, tostring(fx.fid))
        cmd("Set %d Property 'Name' %s", n, q(fx.name or ""))
        local mh = modeHandle(hm.ftIndex, hm.modeName)
        local okH, hs = pcall(HandleToStr, mh)
        if mh and okH and hs then cmd("Set %d Property 'Mode' '%s'", n, tostring(hs)) end
        cmd("Set %d Property 'Patch' %s", n, q(fx.patch))
        local e = children(editFixtures())[n]
        if e and tostring(prop(e, "Patch")) ~= "" then
          patched = patched + 1
          fidOk[fx.fid] = true
        else
          log("fixture %s %s: not patched (%s)", tostring(fx.fid), tostring(fx.name), e and tostring(prop(e, "Patch")) or "no entry")
          result.failed[#result.failed + 1] = { cmd = "patch " .. tostring(fx.fid), err = "address " .. tostring(fx.patch) .. " not accepted" }
        end
      end
    end
  end
  leavePatch()
  -- the live patch takes a moment to follow
  local t1 = os.clock()
  while os.clock() - t1 < 15 do
    if #children(Patch().Stages[1].Fixtures) >= nextIndex - 1 then break end
  end
  result.counts.fixtures = patched
  log("patched %d of %d fixtures", patched, #(show.fixtures or {}))
  dmxCheck("patch")

  -- selection string for a list of fids
  local function sel(fids)
    local parts = {}
    for _, f in ipairs(fids) do if fidOk[f] then parts[#parts + 1] = tostring(f) end end
    if #parts == 0 then return nil end
    return "Fixture " .. table.concat(parts, " + ")
  end

  -- ------------------------------------------------------------------ groups
  local groups = 0
  for _, g in ipairs(show.groups or {}) do
    local s = sel(g.fids or {})
    if s then
      cmd("ClearAll")
      cmd(s)
      if cmd('Store Group %d /NC', g.no) then
        cmd('Label Group %d %s', g.no, q(g.name or ""))
        groups = groups + 1
      end
    end
  end
  cmd("ClearAll")
  result.counts.groups = groups
  dmxCheck("groups")

  -- ------------------------------------------------------------ programmer
  -- bytes per (fid, attr) from the head description
  local headByKey, fixHead = {}, {}
  for _, h in ipairs(show.heads or {}) do
    headByKey[h.key] = {}
    for _, c in ipairs(h.channels) do headByKey[h.key][c.attr] = c end
  end
  for _, fx in ipairs(show.fixtures or {}) do fixHead[tostring(fx.fid)] = headByKey[fx.head] end

  -- values: {fidString -> {attr -> dmx}}; emits grouped At commands
  local function setValues(values)
    local groupsByAttr = {}   -- attr -> value -> {fids}
    for fid, attrs in pairs(values or {}) do
      if fidOk[tonumber(fid)] then
        for attr, v in pairs(attrs) do
          groupsByAttr[attr] = groupsByAttr[attr] or {}
          groupsByAttr[attr][v] = groupsByAttr[attr][v] or {}
          table.insert(groupsByAttr[attr][v], tonumber(fid))
        end
      end
    end
    local n = 0
    for attr, byVal in pairs(groupsByAttr) do
      for v, fids in pairs(byVal) do
        table.sort(fids)
        local h = fixHead[tostring(fids[1])]
        local c = h and h[attr]
        local bytes = c and c.bytes or 1
        local readout = bytes == 2 and "Decimal16" or "Decimal8"
        local s = sel(fids)
        if s then
          cmd(s)
          cmd('Attribute %s At Absolute %s %d', q(attr), readout, v)
          n = n + 1
        end
      end
    end
    return n
  end

  -- ----------------------------------------------------------------- presets
  local presets = 0
  for _, p in ipairs(show.presets or {}) do
    cmd("ClearAll")
    local n = setValues(p.values)
    if n > 0 then
      if cmd('Store Preset %d.%d /NC', p.pool, p.no) then
        cmd('Label Preset %d.%d %s', p.pool, p.no, q(p.name or ""))
        presets = presets + 1
      end
    end
  end
  cmd("ClearAll")
  result.counts.presets = presets
  dmxCheck("presets")

  -- --------------------------------------------------------------- sequences
  local famOfGroup = { Dimmer = "int", Position = "pos", Color = "col" }
  local function splitByFamily(values)
    local out = { int = {}, pos = {}, col = {}, beam = {} }
    for fid, attrs in pairs(values or {}) do
      for attr, v in pairs(attrs) do
        local h = fixHead[fid]
        local c = h and h[attr]
        local fam = c and (famOfGroup[c.group] or "beam") or "beam"
        out[fam][fid] = out[fam][fid] or {}
        out[fam][fid][attr] = v
      end
    end
    return out
  end

  local function setCueProp(seq, cueNo, part, names, value)
    local target = string.format('Sequence %d Cue %s', seq, fmtnum(cueNo))
    if part and part > 0 then target = target .. " Part " .. part end
    local variants = {}
    for _, nm in ipairs(names) do
      variants[#variants + 1] = string.format('Set %s Property %s %s', target, q(nm), fmtnum(value))
    end
    return cmdTry(variants)
  end

  local seqs, cues = 0, 0
  for _, s in ipairs(show.sequences or {}) do
    local stored = 0
    for _, c in ipairs(s.cues or {}) do
      cmd("ClearAll")
      -- preset references first, hard values on top
      for fid, list in pairs(c.presets or {}) do
        if fidOk[tonumber(fid)] then
          cmd('Fixture %s', fid)
          for _, ref in ipairs(list) do
            cmd('At Preset %s', ref)
          end
        end
      end
      local fams = splitByFamily(c.values)
      local parts = {}
      if c.fade_pos ~= nil and next(fams.pos) then parts[#parts + 1] = { fam = "pos", fade = c.fade_pos } end
      if c.fade_col ~= nil and next(fams.col) then parts[#parts + 1] = { fam = "col", fade = c.fade_col } end
      if c.fade_beam ~= nil and next(fams.beam) then parts[#parts + 1] = { fam = "beam", fade = c.fade_beam } end
      local inParts = {}
      for _, p in ipairs(parts) do inParts[p.fam] = true end
      local main = {}
      for fam, vals in pairs(fams) do
        if not inParts[fam] then
          for fid, attrs in pairs(vals) do
            main[fid] = main[fid] or {}
            for a, v in pairs(attrs) do main[fid][a] = v end
          end
        end
      end
      setValues(main)
      local okStore = cmd('Store Sequence %d Cue %s /NC', s.no, fmtnum(c.no))
      if okStore then
        stored = stored + 1
        if c.name and c.name ~= "" then cmd('Label Sequence %d Cue %s %s', s.no, fmtnum(c.no), q(c.name)) end
        local fade = c.fade or 0
        if s.chase then
          setCueProp(s.no, c.no, 0, { "TrigType" }, '"Time"')
          setCueProp(s.no, c.no, 0, { "TrigTime" }, s.chase_speed or 1)
          setCueProp(s.no, c.no, 0, { "CueFade", "Fade" }, 0)
        else
          setCueProp(s.no, c.no, 0, { "CueFade", "Fade" }, fade)
          if c.fade_out ~= nil then setCueProp(s.no, c.no, 0, { "CueOutFade", "OutFade" }, c.fade_out) end
          if (c.delay or 0) > 0 then
            setCueProp(s.no, c.no, 0, { "CueDelay", "Delay" }, c.delay)
            setCueProp(s.no, c.no, 0, { "CueOutDelay", "OutDelay" }, c.delay)
          end
          if c.follow ~= nil then
            setCueProp(s.no, c.no, 0, { "TrigType" }, '"Follow"')
          end
        end
        for i, p in ipairs(parts) do
          cmd("ClearAll")
          setValues(fams[p.fam])
          if cmd('Store Sequence %d Cue %s Part %d /NC', s.no, fmtnum(c.no), i) then
            setCueProp(s.no, c.no, i, { "CueFade", "Fade" }, p.fade)
            if (c.delay or 0) > 0 then setCueProp(s.no, c.no, i, { "CueDelay", "Delay" }, c.delay) end
          end
        end
      end
    end
    cmd("ClearAll")
    if stored > 0 then
      seqs = seqs + 1
      cues = cues + stored
      cmd('Label Sequence %d %s', s.no, q(s.name or ""))
      if s.tracking == false then
        cmdTry({ string.format('Set Sequence %d Property "Tracking" "No"', s.no),
                 string.format('Set Sequence %d Property "Tracking" 0', s.no) })
      end
    end
  end
  result.counts.sequences = seqs
  result.counts.cues = cues

  -- --------------------------------------------------------------- executors
  local execs = 0
  for _, e in ipairs(show.executors or {}) do
    local what
    if e.sequence then what = string.format("Sequence %d", e.sequence)
    elseif e.group then what = string.format("Group %d", e.group)
    elseif e.preset then what = string.format("Preset %s", e.preset) end
    if what then
      local okA = cmdTry({
        string.format('Assign %s At Page %d.%d', what, e.page, e.exec),
        string.format('Page %d; Assign %s At Executor %d', e.page, what, e.exec),
      })
      if okA then execs = execs + 1 end
    end
  end
  result.counts.executors = execs
  dmxCheck("executors")

  cmd("ClearAll")
  pcall(Cmd, "Page 1")
  end)
  if not okBody then
    log("plugin error: %s", tostring(errBody))
    result.failed[#result.failed + 1] = { cmd = "plugin", err = tostring(errBody) }
    pcall(Cmd, "cd Root")
    pcall(Cmd, "ClearAll")
  end
  finish()
end
