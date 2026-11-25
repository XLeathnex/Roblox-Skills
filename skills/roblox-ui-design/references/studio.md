# Into Studio

`rbxui check ui.json --build out/` writes three descriptions of the same instance tree. Use the cheapest route the session has:

| You have | Do this |
|---|---|
| A Rojo project | Copy `out/<Name>.model.json` into the folder mapped to StarterGui (make sure that node has `"$ignoreUnknownInstances": true`). Costs no tokens. |
| Studio MCP on the same machine | Run `out/<Name>.build.luau` with `execute_luau` on the **Edit** datamodel. To avoid sending the whole file, serve the folder (`python3 -m http.server 8123 -d out`) and execute `loadstring(game:GetService("HttpService"):GetAsync("http://127.0.0.1:8123/<Name>.build.luau"))()`; if HTTP is blocked, send the file contents instead. Then `screen_capture` to confirm. |
| Neither | Give the user `out/<Name>.rbxmx`: right-click **StarterGui** > **Insert from File**. Or paste the `.build.luau` into the command bar. |

The `.build.luau` is a one-time builder for edit mode. It is not a game script: it creates the instances and is done (Ctrl+Z undoes it). Never deliver UI as a LocalScript that calls `Instance.new` at runtime: the user cannot see or edit that UI in Studio.

After the build, tell the user where the UI is, which images still need uploading, and how to open panels from their own scripts.

## Behaviour

When a spec uses `autoscale`, `motion`, `opens`, `closes`, `toggles` or `startHidden`, the build adds one LocalScript, `UIRuntime`, under the ScreenGui. It reads attributes on the instances:

- `AutoScale`: scales the group per device.
- `Motion = "button"`: hover and press feedback. `Motion = "panel"`: animated open and close.
- `Opens` / `Closes` / `Toggles = "PanelName"` on a button.
- `MotionStyle` on the ScreenGui (`bouncy`, `snappy`, `calm`) comes from `meta.motion`.

Game code opens a panel with `panel:SetAttribute("Open", true)` and listens to buttons normally:

```lua
local gui = script.Parent           -- a LocalScript next to UIRuntime
gui.ShopPanel.Items.CandyEgg.Buy.Activated:Connect(function()
	game.ReplicatedStorage.Remotes.BuyEgg:FireServer("CandyEgg")
end)
```

Write game logic in separate scripts that find instances by name; keep prices, inventory and purchases on the server. Use `Activated` (works for mouse, touch and gamepad), not `MouseButton1Click`. For lists filled at runtime, build one item as a named template in the spec with `"Visible": false` and have the script `:Clone()` it.

## Updating existing UI

Read the current instances first (MCP `inspect_instance` / `search_game_tree`, or the Rojo files). Keep the user's names, fonts and colours as tokens, and rebuild only the ScreenGui you were asked to change: the builder replaces a ScreenGui of the same name.
