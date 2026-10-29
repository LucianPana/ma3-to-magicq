-- Offline dry run of ma3/import_show.lua with stubs for the grandMA3 API.
-- usage: lua scripts/lua_dryrun.lua PACKAGE_DIR   (writes PACKAGE_DIR/dryrun_commands.txt)
local dir = arg[1]
local cmds = {}
Cmd = function(c) cmds[#cmds + 1] = c return "Ok" end
Printf = function(...) end
Enums = { PathType = { UserFixtures = 1, Library = 2 } }
GetPath = function() return dir .. "/_userfixtures" end
os.execute("mkdir -p '" .. dir .. "/_userfixtures'")
CopyFile = function(a, b) return false end
RefreshLibrary = function() end
local nextIndex = 0
local ftList = {}
local function fakeMode(name, footprint)
  local chans = {}
  for i = 1, footprint do chans[i] = { Coarse = i, Attribute = "Dimmer", Children = function() return {} end } end
  return { Name = name, DMXChannels = { Children = function() return chans end }, Children = function() return {} end }
end
local function fakeFT(name)
  return { Name = name, DMXModes = { Children = function() return { fakeMode("Mode 1", 1) } end } }
end
local fixtures = {}
Patch = function()
  return {
    FixtureTypes = { Children = function() return ftList end, Count = function() return #ftList end },
    Stages = { { Fixtures = { Count = function() return #fixtures end } } },
  }
end
-- every Import Library command creates a fixture type
local realCmd = Cmd
Cmd = function(c)
  if c:match("^Import Library") or c:match("^Import FixtureType") then ftList[#ftList + 1] = fakeFT("FT" .. (#ftList + 1)) end
  if c:match("^Delete FixtureType") then ftList[#ftList] = nil end
  return realCmd(c)
end
AddFixtures = function(t) fixtures[#fixtures + 1] = t return true end
local run = dofile("ma3/import_show.lua")
run(dir)
local f = io.open(dir .. "/dryrun_commands.txt", "w")
for _, c in ipairs(cmds) do f:write(c, "\n") end
f:close()
print(#cmds .. " commands, " .. #fixtures .. " AddFixtures calls")
