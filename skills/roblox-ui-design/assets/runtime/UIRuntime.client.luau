--!strict
--[[
	UIRuntime
	Behaviour for a ScreenGui built with the roblox-ui-design skill. The UI is made of real
	instances you can edit in the Explorer; this LocalScript only adds what instances cannot do
	on their own:

	  AutoScale   attribute "hud" | "modal" on a GuiObject that has a UIScale named "AutoScale".
	              The object is authored in 1080p pixels and scaled per device. "modal" also
	              shrinks to fit the safe area.
	  Motion      attribute "button" (hover / press feedback) or "panel" (animated open / close).
	  Opens / Closes / Toggles
	              attribute on a GuiButton naming a panel in this ScreenGui.
	  StartHidden attribute true on a panel that should be closed when the game starts.
	  MotionStyle attribute on the ScreenGui: "bouncy" | "snappy" | "calm".
	  AnimEnter / AnimLeave / AnimLoop
	              choreography on any GuiObject (see the Choreography section below).

	From your own scripts, open or close a panel with:
	    panel:SetAttribute("Open", true)
]]

local GuiService = game:GetService("GuiService")
local TweenService = game:GetService("TweenService")
local Workspace = game:GetService("Workspace")

local gui = script.Parent :: LayerCollector

local REFERENCE_HEIGHT = 1080

type Style = {
	hover: number,
	press: number,
	buttonTime: number,
	openTime: number,
	closeTime: number,
	openFrom: number,
	openEasing: Enum.EasingStyle,
}

local STYLES: { [string]: Style } = {
	-- cartoon / simulator: overshoot and squash
	bouncy = {
		hover = 1.06,
		press = 0.93,
		buttonTime = 0.12,
		openTime = 0.30,
		closeTime = 0.16,
		openFrom = 0.7,
		openEasing = Enum.EasingStyle.Back,
	},
	-- clean / competitive: quick, no overshoot
	snappy = {
		hover = 1.03,
		press = 0.97,
		buttonTime = 0.08,
		openTime = 0.18,
		closeTime = 0.12,
		openFrom = 0.94,
		openEasing = Enum.EasingStyle.Quint,
	},
	-- horror / cinematic: slow fades, no scaling
	calm = {
		hover = 1,
		press = 0.985,
		buttonTime = 0.2,
		openTime = 0.6,
		closeTime = 0.4,
		openFrom = 1,
		openEasing = Enum.EasingStyle.Sine,
	},
}

local function currentStyle(): Style
	local name = gui:GetAttribute("MotionStyle")
	if typeof(name) == "string" and STYLES[name] then
		return STYLES[name]
	end
	return STYLES.snappy
end

local function reducedMotion(): boolean
	local ok, value = pcall(function()
		return GuiService.ReducedMotionEnabled
	end)
	return ok and value == true
end

-- One UIScale per object carries both the device scale and the motion factor.
type State = {
	scale: UIScale,
	auto: number,
	factor: NumberValue,
	tween: Tween?,
}

local states: { [GuiObject]: State } = {}

local function getState(object: GuiObject): State
	local existing = states[object]
	if existing then
		return existing
	end
	local uiScale = object:FindFirstChildOfClass("UIScale")
	if not uiScale then
		local created = Instance.new("UIScale")
		created.Name = "MotionScale"
		created.Parent = object
		uiScale = created
	end
	local factor = Instance.new("NumberValue")
	factor.Value = 1
	local state: State = { scale = uiScale :: UIScale, auto = 1, factor = factor, tween = nil }
	factor.Changed:Connect(function()
		state.scale.Scale = state.auto * factor.Value
	end)
	states[object] = state
	object.Destroying:Connect(function()
		states[object] = nil
		factor:Destroy()
	end)
	return state
end

local function setFactor(object: GuiObject, target: number, info: TweenInfo?)
	local state = getState(object)
	if state.tween then
		state.tween:Cancel()
		state.tween = nil
	end
	if info == nil or reducedMotion() then
		state.factor.Value = target
		state.scale.Scale = state.auto * target
		return
	end
	local tween = TweenService:Create(state.factor, info, { Value = target })
	state.tween = tween
	tween:Play()
end

---------------------------------------------------------------------------------------------
-- Device scaling

local function baseScale(): number
	local camera = Workspace.CurrentCamera
	local height = if camera then camera.ViewportSize.Y else REFERENCE_HEIGHT
	if height <= 0 then
		height = REFERENCE_HEIGHT
	end
	return math.clamp((height / REFERENCE_HEIGHT) ^ 0.4, 0.55, 1.5)
end

local function applyAutoScale(object: GuiObject)
	local mode = object:GetAttribute("AutoScale")
	if mode ~= "hud" and mode ~= "modal" then
		return
	end
	local state = getState(object)
	local scale = baseScale()
	if mode == "modal" then
		-- A modal fills most of a phone and about three quarters of a desktop, whatever size it was drawn at.
		local available = gui.AbsoluteSize
		local size = object.Size
		local camera = Workspace.CurrentCamera
		local height = if camera then camera.ViewportSize.Y else REFERENCE_HEIGHT
		local fill = 0.94 - 0.18 * math.clamp((height - 500) / 500, 0, 1)
		local fit = math.huge
		if size.X.Scale == 0 and size.X.Offset > 0 and available.X > 0 then
			fit = math.min(fit, fill * available.X / size.X.Offset)
		end
		if size.Y.Scale == 0 and size.Y.Offset > 0 and available.Y > 0 then
			fit = math.min(fit, fill * available.Y / size.Y.Offset)
		end
		if fit < math.huge then
			scale = math.min(fit, 2)
		end
	end
	state.auto = scale
	state.scale.Scale = scale * state.factor.Value
end

local function applyAllScales()
	for _, descendant in gui:GetDescendants() do
		if descendant:IsA("GuiObject") and descendant:GetAttribute("AutoScale") ~= nil then
			applyAutoScale(descendant)
		end
	end
end

---------------------------------------------------------------------------------------------
-- Choreography
-- Any GuiObject can carry AnimEnter / AnimLeave / AnimLoop attributes ("key=value;key=value").
-- They play when the panel that owns the object opens, or at start for always-on HUD.
--   AnimEnter  from=x,y  delay  dur  ease  rot  scale  fade=true  reveal=down|right
--   AnimLeave  at  to=x,y  dur  rot  scale  fade=true      (a prop that exits and hides)
--   AnimLoop   bob  sway  spin  pulse  period

type Fade = { inst: Instance, prop: string, base: number }
type Anim = {
	pos: UDim2,
	rot: number,
	size: UDim2,
	clips: boolean,
	fades: { Fade },
	alpha: NumberValue,
	tweens: { Tween },
	token: number,
}

local anims: { [GuiObject]: Anim } = {}

local EASING: { [string]: Enum.EasingStyle } = {
	Back = Enum.EasingStyle.Back,
	Quad = Enum.EasingStyle.Quad,
	Quint = Enum.EasingStyle.Quint,
	Cubic = Enum.EasingStyle.Cubic,
	Sine = Enum.EasingStyle.Sine,
	Elastic = Enum.EasingStyle.Elastic,
	Bounce = Enum.EasingStyle.Bounce,
	Linear = Enum.EasingStyle.Linear,
	Exponential = Enum.EasingStyle.Exponential,
}

local function parseAnim(text: unknown): { [string]: string }
	local out: { [string]: string } = {}
	if typeof(text) ~= "string" then
		return out
	end
	for pair in string.gmatch(text, "[^;]+") do
		local key, value = string.match(pair, "^%s*([%w_]+)%s*=%s*(.-)%s*$")
		if key and value then
			out[key] = value
		end
	end
	return out
end

local function numberOf(t: { [string]: string }, key: string, default: number): number
	local value = tonumber(t[key])
	if value then
		return value
	end
	return default
end

local function offsetOf(t: { [string]: string }, key: string): UDim2
	local x, y = string.match(t[key] or "", "^(-?[%d%.]+),(-?[%d%.]+)$")
	return UDim2.fromOffset(tonumber(x) or 0, tonumber(y) or 0)
end

local function hasAnim(object: Instance): boolean
	return object:GetAttribute("AnimEnter") ~= nil or object:GetAttribute("AnimLeave") ~= nil or object:GetAttribute("AnimLoop") ~= nil
end

local function inLayout(object: GuiObject): boolean
	local parent = object.Parent
	if not parent then
		return false
	end
	return parent:FindFirstChildOfClass("UIListLayout") ~= nil or parent:FindFirstChildOfClass("UIGridLayout") ~= nil
end

local function collectFades(object: GuiObject): { Fade }
	local list: { Fade } = {}
	if object:IsA("CanvasGroup") then
		table.insert(list, { inst = object, prop = "GroupTransparency", base = object.GroupTransparency })
		return list
	end
	local function add(inst: Instance)
		if inst:IsA("GuiObject") then
			table.insert(list, { inst = inst, prop = "BackgroundTransparency", base = inst.BackgroundTransparency })
		end
		if inst:IsA("TextLabel") or inst:IsA("TextButton") or inst:IsA("TextBox") then
			table.insert(list, { inst = inst, prop = "TextTransparency", base = inst.TextTransparency })
		elseif inst:IsA("ImageLabel") or inst:IsA("ImageButton") then
			table.insert(list, { inst = inst, prop = "ImageTransparency", base = inst.ImageTransparency })
		elseif inst:IsA("UIStroke") then
			table.insert(list, { inst = inst, prop = "Transparency", base = inst.Transparency })
		elseif inst.ClassName == "UIShadow" then
			table.insert(list, { inst = inst, prop = "Transparency", base = (inst :: any).Transparency })
		end
	end
	add(object)
	for _, descendant in object:GetDescendants() do
		add(descendant)
	end
	return list
end

local function applyAlpha(anim: Anim, alpha: number)
	for _, fade in anim.fades do
		(fade.inst :: any)[fade.prop] = 1 - (1 - fade.base) * alpha
	end
end

local function getAnim(object: GuiObject): Anim
	local existing = anims[object]
	if existing then
		return existing
	end
	local alpha = Instance.new("NumberValue")
	alpha.Value = 1
	local anim: Anim = {
		pos = object.Position,
		rot = object.Rotation,
		size = object.Size,
		clips = object.ClipsDescendants,
		fades = collectFades(object),
		alpha = alpha,
		tweens = {},
		token = 0,
	}
	alpha.Changed:Connect(function()
		applyAlpha(anim, alpha.Value)
	end)
	anims[object] = anim
	object.Destroying:Connect(function()
		anims[object] = nil
		alpha:Destroy()
	end)
	return anim
end

local function track(anim: Anim, tween: Tween)
	table.insert(anim.tweens, tween)
	tween:Play()
end

local function restAnim(object: GuiObject, anim: Anim)
	for _, tween in anim.tweens do
		tween:Cancel()
	end
	table.clear(anim.tweens)
	anim.token += 1
	object.Position = anim.pos
	object.Rotation = anim.rot
	object.Size = anim.size
	object.ClipsDescendants = anim.clips
	anim.alpha.Value = 1
	applyAlpha(anim, 1)
	setFactor(object, 1, nil)
end

local function playAnimation(object: GuiObject)
	local enter = parseAnim(object:GetAttribute("AnimEnter"))
	local leave = parseAnim(object:GetAttribute("AnimLeave"))
	local loop = parseAnim(object:GetAttribute("AnimLoop"))
	if next(enter) == nil and next(leave) == nil and next(loop) == nil then
		return
	end
	local anim = getAnim(object)
	restAnim(object, anim)
	object.Visible = true
	local token = anim.token
	local still = reducedMotion()
	local settle = 0

	if next(enter) ~= nil and not still then
		local delay = numberOf(enter, "delay", 0)
		local duration = math.max(0.01, numberOf(enter, "dur", 0.45))
		settle = delay + duration
		local info = TweenInfo.new(duration, EASING[enter.ease or ""] or Enum.EasingStyle.Back, Enum.EasingDirection.Out, 0, false, delay)
		local from = offsetOf(enter, "from")
		if (from.X.Offset ~= 0 or from.Y.Offset ~= 0) and not inLayout(object) then
			object.Position = anim.pos + from
			track(anim, TweenService:Create(object, info, { Position = anim.pos }))
		end
		if enter.rot then
			object.Rotation = anim.rot + numberOf(enter, "rot", 0)
			track(anim, TweenService:Create(object, info, { Rotation = anim.rot }))
		end
		if enter.scale then
			local state = getState(object)
			state.factor.Value = numberOf(enter, "scale", 1)
			track(anim, TweenService:Create(state.factor, info, { Value = 1 }))
		end
		if enter.fade == "true" then
			anim.alpha.Value = 0
			applyAlpha(anim, 0)
			local fadeInfo = TweenInfo.new(duration * 0.6, Enum.EasingStyle.Sine, Enum.EasingDirection.Out, 0, false, delay)
			track(anim, TweenService:Create(anim.alpha, fadeInfo, { Value = 1 }))
		end
		if enter.reveal == "down" then
			object.ClipsDescendants = true
			object.Size = UDim2.new(anim.size.X, UDim.new(0, 0))
			track(anim, TweenService:Create(object, info, { Size = anim.size }))
		elseif enter.reveal == "right" then
			object.ClipsDescendants = true
			object.Size = UDim2.new(UDim.new(0, 0), anim.size.Y)
			track(anim, TweenService:Create(object, info, { Size = anim.size }))
		end
	end

	if next(leave) ~= nil then
		if still then
			object.Visible = false
			return
		end
		local at = numberOf(leave, "at", 1)
		local duration = math.max(0.01, numberOf(leave, "dur", 0.5))
		task.delay(at, function()
			if anim.token ~= token then
				return
			end
			local info = TweenInfo.new(duration, Enum.EasingStyle.Quad, Enum.EasingDirection.In)
			local to = offsetOf(leave, "to")
			if (to.X.Offset ~= 0 or to.Y.Offset ~= 0) and not inLayout(object) then
				track(anim, TweenService:Create(object, info, { Position = anim.pos + to }))
			end
			if leave.rot then
				track(anim, TweenService:Create(object, info, { Rotation = anim.rot + numberOf(leave, "rot", 0) }))
			end
			if leave.scale then
				track(anim, TweenService:Create(getState(object).factor, info, { Value = numberOf(leave, "scale", 1) }))
			end
			if leave.fade == "true" then
				track(anim, TweenService:Create(anim.alpha, info, { Value = 0 }))
			end
			task.delay(duration, function()
				if anim.token == token then
					object.Visible = false
				end
			end)
		end)
		return
	end

	if next(loop) ~= nil and not still then
		task.delay(settle, function()
			if anim.token ~= token then
				return
			end
			local period = math.max(0.2, numberOf(loop, "period", 2))
			local swing = TweenInfo.new(period / 2, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut, -1, true)
			if loop.bob and not inLayout(object) then
				track(anim, TweenService:Create(object, swing, { Position = anim.pos + UDim2.fromOffset(0, -numberOf(loop, "bob", 0)) }))
			end
			if loop.sway then
				track(anim, TweenService:Create(object, swing, { Rotation = anim.rot + numberOf(loop, "sway", 0) }))
			elseif loop.spin then
				local speed = numberOf(loop, "spin", 30)
				if speed ~= 0 then
					local turn = TweenInfo.new(360 / math.abs(speed), Enum.EasingStyle.Linear, Enum.EasingDirection.InOut, -1)
					track(anim, TweenService:Create(object, turn, { Rotation = anim.rot + (if speed > 0 then 360 else -360) }))
				end
			end
			if loop.pulse then
				track(anim, TweenService:Create(getState(object).factor, swing, { Value = 1 + numberOf(loop, "pulse", 0) }))
			end
		end)
	end
end

local function owningPanel(object: Instance): Instance?
	local current = object.Parent
	while current and current ~= gui do
		if current:GetAttribute("Motion") == "panel" then
			return current
		end
		current = current.Parent
	end
	return nil
end

-- Plays every animated object that belongs to `owner` (a panel, or nil for always-on HUD).
local function playOwned(owner: Instance?)
	local root: Instance = owner or gui
	for _, descendant in root:GetDescendants() do
		if descendant:IsA("GuiObject") and hasAnim(descendant) and owningPanel(descendant) == owner then
			if owner ~= nil or descendant:GetAttribute("Motion") ~= "panel" then
				playAnimation(descendant)
			end
		end
	end
end

---------------------------------------------------------------------------------------------
-- Panels

local function setPanelOpen(panel: GuiObject, open: boolean, instant: boolean?)
	local style = currentStyle()
	local group = if panel:IsA("CanvasGroup") then panel else nil
	if open then
		panel.Visible = true
		if hasAnim(panel) then
			-- the panel brings its own entrance; skip the default pop
			setFactor(panel, 1, nil)
			if group then
				group.GroupTransparency = 0
			end
			playAnimation(panel)
			playOwned(panel)
			return
		end
		playOwned(panel)
		if instant or reducedMotion() then
			setFactor(panel, 1, nil)
			if group then
				group.GroupTransparency = 0
			end
			return
		end
		setFactor(panel, style.openFrom, nil)
		setFactor(panel, 1, TweenInfo.new(style.openTime, style.openEasing, Enum.EasingDirection.Out))
		if group then
			group.GroupTransparency = 1
			TweenService:Create(group, TweenInfo.new(style.openTime * 0.6, Enum.EasingStyle.Sine), { GroupTransparency = 0 }):Play()
		end
	else
		if instant or reducedMotion() or not panel.Visible then
			panel.Visible = false
			return
		end
		local info = TweenInfo.new(style.closeTime, Enum.EasingStyle.Quad, Enum.EasingDirection.In)
		setFactor(panel, style.openFrom, info)
		if group then
			TweenService:Create(group, info, { GroupTransparency = 1 }):Play()
		end
		task.delay(style.closeTime, function()
			if panel:GetAttribute("Open") ~= true then
				panel.Visible = false
				setFactor(panel, 1, nil)
			end
		end)
	end
end

local function bindPanel(panel: GuiObject)
	local startOpen = panel:GetAttribute("StartHidden") ~= true and panel.Visible
	panel:SetAttribute("Open", startOpen)
	setPanelOpen(panel, startOpen, true)
	panel:GetAttributeChangedSignal("Open"):Connect(function()
		setPanelOpen(panel, panel:GetAttribute("Open") == true)
	end)
end

local function findPanel(name: string): GuiObject?
	local found = gui:FindFirstChild(name, true)
	if found and found:IsA("GuiObject") then
		return found
	end
	warn(`UIRuntime: no panel named "{name}" in {gui:GetFullName()}`)
	return nil
end

local function requestOpen(name: unknown, open: boolean?)
	if typeof(name) ~= "string" then
		return
	end
	local panel = findPanel(name)
	if not panel then
		return
	end
	local target = if open == nil then panel:GetAttribute("Open") ~= true else open
	if panel:GetAttribute("Motion") == "panel" then
		panel:SetAttribute("Open", target)
	else
		panel.Visible = target
	end
end

---------------------------------------------------------------------------------------------
-- Buttons

local function bindButton(button: GuiButton)
	local hovering = false
	local pressing = false

	local function refresh()
		local style = currentStyle()
		local target = if pressing then style.press elseif hovering then style.hover else 1
		setFactor(button, target, TweenInfo.new(style.buttonTime, Enum.EasingStyle.Quad, Enum.EasingDirection.Out))
	end

	button.InputBegan:Connect(function(input: InputObject)
		if input.UserInputType == Enum.UserInputType.MouseMovement then
			hovering = true
		elseif input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
			pressing = true
		else
			return
		end
		refresh()
	end)
	button.InputEnded:Connect(function(input: InputObject)
		if input.UserInputType == Enum.UserInputType.MouseMovement then
			hovering = false
			pressing = false
		elseif input.UserInputType == Enum.UserInputType.MouseButton1 then
			pressing = false
		elseif input.UserInputType == Enum.UserInputType.Touch then
			pressing = false
			hovering = false
		else
			return
		end
		refresh()
	end)
	button.SelectionGained:Connect(function()
		hovering = true
		refresh()
	end)
	button.SelectionLost:Connect(function()
		hovering = false
		refresh()
	end)
end

local function bindActions(button: GuiButton)
	button.Activated:Connect(function()
		requestOpen(button:GetAttribute("Opens"), true)
		requestOpen(button:GetAttribute("Closes"), false)
		requestOpen(button:GetAttribute("Toggles"), nil)
	end)
end

---------------------------------------------------------------------------------------------
-- Wiring

local bound: { [Instance]: boolean } = {}

local function bind(instance: Instance)
	if bound[instance] or not instance:IsA("GuiObject") then
		return
	end
	bound[instance] = true
	if instance:GetAttribute("AutoScale") ~= nil then
		applyAutoScale(instance)
	end
	local motion = instance:GetAttribute("Motion")
	if motion == "panel" then
		bindPanel(instance)
	elseif motion == "button" and instance:IsA("GuiButton") then
		bindButton(instance)
	end
	if instance:IsA("GuiButton") then
		if instance:GetAttribute("Opens") ~= nil or instance:GetAttribute("Closes") ~= nil or instance:GetAttribute("Toggles") ~= nil then
			bindActions(instance)
		end
	end
end

for _, descendant in gui:GetDescendants() do
	bind(descendant)
end
gui.DescendantAdded:Connect(bind)
gui.DescendantRemoving:Connect(function(instance)
	bound[instance] = nil
end)

playOwned(nil)

gui:GetPropertyChangedSignal("AbsoluteSize"):Connect(applyAllScales)

local function watchCamera()
	local camera = Workspace.CurrentCamera
	if camera then
		camera:GetPropertyChangedSignal("ViewportSize"):Connect(applyAllScales)
	end
	applyAllScales()
end
Workspace:GetPropertyChangedSignal("CurrentCamera"):Connect(watchCamera)
watchCamera()
