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
		local available = gui.AbsoluteSize
		local size = object.Size
		if size.X.Scale == 0 and size.X.Offset > 0 and available.X > 0 then
			scale = math.min(scale, 0.96 * available.X / size.X.Offset)
		end
		if size.Y.Scale == 0 and size.Y.Offset > 0 and available.Y > 0 then
			scale = math.min(scale, 0.94 * available.Y / size.Y.Offset)
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
-- Panels

local function setPanelOpen(panel: GuiObject, open: boolean, instant: boolean?)
	local style = currentStyle()
	local group = if panel:IsA("CanvasGroup") then panel else nil
	if open then
		panel.Visible = true
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
